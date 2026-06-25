"""Validate the Phase-1 coarse screen (age group + is_empirical).

Runs both raters from the ACTIVE config over a stratified sample using the
SCREEN_PROMPT, then reports agreement between the two raters and against a
silver standard:
  - has_adults / has_under_18  -> adjudicated Final_has_adults / Final_has_under_18
  - is_empirical               -> derived from adjudicated Final_study_type
                                  (primary studies => yes; review/commentary/
                                   proposal/protocol => no)

Usage:
    poetry run python scripts/screen_opt.py [<config>] [<n>]   # default: adults 80
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
    SCREEN_PROMPT,
    SCREEN_FIELDS,
    coerce_screen,
    study_type_to_is_empirical,
)

SAMPLE_PATH = "/tmp/screen_opt_sample.json"
REPORT_CSV = "/tmp/screen_opt_disagreements.csv"
SEED = 23


def stratified(df: pd.DataFrame, n: int) -> list[int]:
    elig = df[
        (df["is_duplicate"].astype(str).str.upper() != "Y")
        & df["Final_study_type"].astype(str).str.strip().ne("")
        & df["Abstract"].astype(str).str.strip().ne("")
    ]
    # Stratify by the silver is_empirical so we get a balanced yes/no mix.
    elig = elig.assign(
        _emp=elig["Final_study_type"].map(study_type_to_is_empirical)
    )
    cells = elig.groupby(["_emp", "Final_has_under_18"])
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


def silver(sample: pd.DataFrame, idx: int, field: str) -> str:
    if field == "is_empirical":
        return study_type_to_is_empirical(sample.at[idx, "Final_study_type"])
    return str(sample.at[idx, f"Final_{field}"]).strip().lower()


def main() -> int:
    slug = sys.argv[1] if len(sys.argv) > 1 else "adults"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 80
    cfg = load_config(slug)
    set_active(cfg)
    ra, rb = cfg.rater_a, cfg.rater_b
    print(f"Screen-opt [{slug}]: {ra.label} vs {rb.label}, n={n}")

    df = pd.read_csv(cfg.adjudicated_csv, dtype=str).fillna("")
    if os.path.exists(SAMPLE_PATH):
        idxs = json.load(open(SAMPLE_PATH))
        print(f"  reusing cached sample of {len(idxs)}")
    else:
        idxs = stratified(df, n)
        json.dump(idxs, open(SAMPLE_PATH, "w"))
        print(f"  sampled {len(idxs)} (stratified by is_empirical × under_18)")
    sample = df.loc[idxs]

    def work(args):
        idx, rater = args
        title = str(sample.at[idx, "Title"] or "")
        abstract = str(sample.at[idx, "Abstract"] or "")
        try:
            raw = llm.invoke_json(
                rater, SCREEN_PROMPT,
                f"Title: {title}\n\nAbstract: {abstract}", temperature=0.0, max_tokens=400,
            )
            out = coerce_screen(raw)
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
            if done % 40 == 0:
                print(f"    [{done}/{len(tasks)}] {time.time()-t0:.0f}s", flush=True)

    print(f"\n{'field':16s}  A-B agree   A-Silver   B-Silver   kappa(A,B)")
    print("-" * 64)
    for f in SCREEN_FIELDS:
        a_vals, b_vals, sv = [], [], []
        for i in idxs:
            a = str(res.get((i, "a"), {}).get(f, "")).strip().lower()
            b = str(res.get((i, "b"), {}).get(f, "")).strip().lower()
            s = silver(sample, i, f)
            if a and b:
                a_vals.append(a); b_vals.append(b); sv.append(s)
        if not a_vals:
            continue
        ab = sum(x == y for x, y in zip(a_vals, b_vals)) / len(a_vals)
        af = sum(x == y for x, y in zip(a_vals, sv) if y) / max(1, sum(1 for y in sv if y))
        bf = sum(x == y for x, y in zip(b_vals, sv) if y) / max(1, sum(1 for y in sv if y))
        k = kappa(a_vals, b_vals)
        print(f"{f:16s}  {ab:7.1%}   {af:8.1%}   {bf:8.1%}   {k:+.3f}")

    # is_empirical confusion vs silver (the decision that gates Phase 2).
    print("\nis_empirical vs silver (gate decision):")
    for who in ("a", "b"):
        tp = fp = tn = fn = 0
        for i in idxs:
            pred = str(res.get((i, who), {}).get("is_empirical", "")).strip().lower()
            gold = silver(sample, i, "is_empirical")
            if gold not in ("yes", "no") or pred not in ("yes", "no"):
                continue
            if gold == "yes" and pred == "yes": tp += 1
            elif gold == "no" and pred == "yes": fp += 1
            elif gold == "no" and pred == "no": tn += 1
            elif gold == "yes" and pred == "no": fn += 1
        label = (ra if who == "a" else rb).label
        # Recall on empirical = how many real primary studies we keep (don't wrongly drop).
        rec = tp / max(1, tp + fn)
        print(f"  {label:18s}: empirical-recall={rec:.0%}  "
              f"(kept {tp}/{tp+fn} primary studies; wrongly dropped {fn}; "
              f"let through {fp} non-empirical)")

    # Dump disagreements / errors for reading.
    recs = []
    for i in idxs:
        a = res.get((i, "a"), {}); b = res.get((i, "b"), {})
        ga = silver(sample, i, "is_empirical")
        disagreed = [f for f in SCREEN_FIELDS
                     if str(a.get(f, "")).strip().lower() != str(b.get(f, "")).strip().lower()]
        a_emp_wrong = str(a.get("is_empirical", "")).strip().lower() != ga and ga in ("yes", "no")
        b_emp_wrong = str(b.get("is_empirical", "")).strip().lower() != ga and ga in ("yes", "no")
        if not disagreed and not a_emp_wrong and not b_emp_wrong:
            continue
        rec = {"idx": i, "title": str(sample.at[i, "Title"])[:110],
               "Final_study_type": sample.at[i, "Final_study_type"],
               "silver_is_empirical": ga, "disagreed": ",".join(disagreed)}
        for f in SCREEN_FIELDS:
            rec[f"A_{f}"] = a.get(f, ""); rec[f"B_{f}"] = b.get(f, "")
        rec["A_reasoning"] = str(a.get("reasoning", ""))[:280]
        rec["B_reasoning"] = str(b.get("reasoning", ""))[:280]
        recs.append(rec)
    pd.DataFrame(recs).to_csv(REPORT_CSV, index=False)
    print(f"\n{len(recs)} rows with disagreement or is_empirical error -> {REPORT_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
