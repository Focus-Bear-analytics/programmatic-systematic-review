"""Prompt-optimisation harness for the two new raters (Nova 2 Lite + Sonnet).

Runs both raters from the ACTIVE config over a small stratified sample, then
reports how often they agree with each other and with the existing adjudicated
``Final_<field>`` labels (the historical 3-rater consensus, treated as a silver
standard for now). Disagreements are dumped to a CSV so you can read the cases,
adjust each model's ``prompt_suffix`` in its config, and re-run.

Iterate:
    1. poetry run python scripts/prompt_opt.py adults 40
    2. open /tmp/prompt_opt_disagreements.csv, read the failures
    3. edit configs/adults.json -> raters.a.prompt_suffix / raters.b.prompt_suffix
    4. re-run step 1 (same sample is cached) and watch agreement move

Usage:
    poetry run python scripts/prompt_opt.py [<config>] [<n>]   # default: adults 40
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.getcwd())
import pandas as pd  # noqa: E402

from steps.config import load_config, set_active  # noqa: E402
from steps import llm  # noqa: E402
from steps.schema import (  # noqa: E402
    CLASSIFICATION_PROMPT,
    CONSENSUS_FIELDS,
    coerce_classification,
)

SAMPLE_PATH = "/tmp/prompt_opt_sample.json"
REPORT_CSV = "/tmp/prompt_opt_disagreements.csv"
SEED = 17


def stratified(df: pd.DataFrame, n: int) -> list[int]:
    elig = df[
        (df["is_duplicate"].astype(str).str.upper() != "Y")
        & df["Final_intervention_type"].astype(str).str.strip().ne("")
        & df["Final_has_under_18"].astype(str).str.strip().ne("")
        & df["Abstract"].astype(str).str.strip().ne("")
    ]
    cells = elig.groupby(["Final_intervention_type", "Final_has_under_18"])
    per = max(1, n // max(1, cells.ngroups))
    rng = random.Random(SEED)
    picks: list[int] = []
    for _, g in cells:
        idxs = list(g.index)
        rng.shuffle(idxs)
        picks.extend(idxs[:per])
    rest = [i for i in elig.index if i not in set(picks)]
    rng.shuffle(rest)
    while len(picks) < n and rest:
        picks.append(rest.pop())
    return [int(i) for i in picks[:n]]


def kappa(x: list[str], y: list[str]) -> float:
    n = len(x)
    if not n:
        return 0.0
    cats = set(x) | set(y)
    po = sum(a == b for a, b in zip(x, y)) / n
    pe = sum((x.count(c) / n) * (y.count(c) / n) for c in cats)
    return 1.0 if pe >= 1 else (po - pe) / (1 - pe)


def main() -> int:
    slug = sys.argv[1] if len(sys.argv) > 1 else "adults"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    cfg = load_config(slug)
    set_active(cfg)
    ra, rb = cfg.rater_a, cfg.rater_b
    print(f"Prompt-opt [{slug}]: {ra.label} vs {rb.label}, n={n}")
    if ra.prompt_suffix:
        print(f"  rater A suffix: {ra.prompt_suffix[:80]}...")
    if rb.prompt_suffix:
        print(f"  rater B suffix: {rb.prompt_suffix[:80]}...")

    df = pd.read_csv(cfg.adjudicated_csv, dtype=str).fillna("")
    if os.path.exists(SAMPLE_PATH):
        idxs = json.load(open(SAMPLE_PATH))
        print(f"  reusing cached sample of {len(idxs)}")
    else:
        idxs = stratified(df, n)
        json.dump(idxs, open(SAMPLE_PATH, "w"))
        print(f"  sampled {len(idxs)} (stratified by intervention_type × under_18)")

    sample = df.loc[idxs]

    def work(args):
        idx, rater = args
        title = str(sample.at[idx, "Title"] or "")
        abstract = str(sample.at[idx, "Abstract"] or "")
        try:
            # Call raw so we keep the model's "reasoning" field (coerce drops it),
            # then snap the enum fields for comparison.
            raw = llm.invoke_json(
                rater, CLASSIFICATION_PROMPT,
                f"Title: {title}\n\nAbstract: {abstract}", temperature=0.0,
            )
            out = coerce_classification(raw)
            out["reasoning"] = str(raw.get("reasoning", ""))
            return idx, rater.key, out, None
        except Exception as e:  # noqa: BLE001
            return idx, rater.key, {}, str(e)[:160]

    tasks = [(i, ra) for i in idxs] + [(i, rb) for i in idxs]
    res: dict[tuple[int, str], dict] = {}
    t0 = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        for fut in as_completed([pool.submit(work, t) for t in tasks]):
            idx, key, r, err = fut.result()
            res[(idx, key)] = r
            done += 1
            if err:
                print(f"    ERR idx={idx} {key}: {err}")
            if done % 20 == 0:
                print(f"    [{done}/{len(tasks)}] {time.time()-t0:.0f}s", flush=True)

    # Agreement metrics
    print(f"\n{'field':24s}  A–B agree   A–Final   B–Final   κ(A,B)")
    print("-" * 72)
    rows = []
    for f in CONSENSUS_FIELDS:
        a_vals, b_vals, fin = [], [], []
        for i in idxs:
            a = str(res.get((i, "a"), {}).get(f, "")).strip().lower()
            b = str(res.get((i, "b"), {}).get(f, "")).strip().lower()
            ff = str(sample.at[i, f"Final_{f}"]).strip().lower()
            if a and b:
                a_vals.append(a); b_vals.append(b); fin.append(ff)
        if not a_vals:
            continue
        ab = sum(x == y for x, y in zip(a_vals, b_vals)) / len(a_vals)
        af = sum(x == y for x, y in zip(a_vals, fin) if y) / max(1, sum(1 for y in fin if y))
        bf = sum(x == y for x, y in zip(b_vals, fin) if y) / max(1, sum(1 for y in fin if y))
        k = kappa(a_vals, b_vals)
        print(f"{f:24s}  {ab:7.1%}   {af:7.1%}   {bf:7.1%}   {k:+.3f}")
        rows.append((f, ab, af, bf, k))

    # Dump disagreements for human reading
    recs = []
    for i in idxs:
        a = res.get((i, "a"), {})
        b = res.get((i, "b"), {})
        disagreed = [f for f in CONSENSUS_FIELDS
                     if str(a.get(f, "")).strip().lower() != str(b.get(f, "")).strip().lower()]
        if not disagreed:
            continue
        rec = {"idx": i, "title": str(sample.at[i, "Title"])[:120],
               "disagreed_fields": ",".join(disagreed)}
        for f in disagreed:
            rec[f"A_{f}"] = a.get(f, "")
            rec[f"B_{f}"] = b.get(f, "")
            rec[f"Final_{f}"] = sample.at[i, f"Final_{f}"]
        rec["A_reasoning"] = str(a.get("reasoning", ""))[:300]
        rec["B_reasoning"] = str(b.get("reasoning", ""))[:300]
        recs.append(rec)
    pd.DataFrame(recs).to_csv(REPORT_CSV, index=False)
    print(f"\n{len(recs)}/{len(idxs)} papers had A–B disagreement → {REPORT_CSV}")
    print("Read it, then tune raters.a.prompt_suffix / raters.b.prompt_suffix and re-run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
