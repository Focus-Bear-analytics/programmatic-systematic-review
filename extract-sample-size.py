"""Extract each candidate's total participant count (N) from title+abstract, so
the children review can screen out clearly-underpowered studies (< 20 enrolled).

Recall-safe: N is set to null when the abstract does not state a count, so a
study is NEVER dropped merely because its abstract omits the sample size — only
studies that clearly report N < 20 are flagged. Uses the cheap rater (Nova 2
Lite via Bedrock). Resumable: writes n_total back into children/adjudicated.csv
and skips rows already filled.

Usage: poetry run python extract-sample-size.py
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.getcwd())
import pandas as pd

from steps import llm
from steps.config import load_config, set_active
from steps.io import is_missing_abstract

DIGITAL = {"mobile_app", "web_app", "software_tool", "video_game", "neurofeedback",
           "cbt", "cognitive_training", "mindfulness", "chatbot", "biofeedback",
           "vr_ar", "video_modeling", "elearning", "aac", "robotics", "wearable",
           "telecoaching", "telecounselling", "parent_training"}
ND = {"adhd", "autistic", "audhd"}

SYSTEM = (
    "You extract the SAMPLE SIZE of a study from its title and abstract. "
    'Return ONLY a JSON object: {"n_total": <integer or null>}. '
    "n_total = the total number of human participants ENROLLED or ANALYSED (sum across all "
    "groups/arms/conditions). If only per-group Ns are given, sum them. Count the index "
    "participants (children/adolescents, or the dyads' children; parents in parent-mediated "
    "studies count as participants too). Do NOT count sessions, trials, stimuli, or studies "
    "reviewed. Use null if the abstract states no participant count. Never guess a number."
)
WORKERS = int(os.getenv("CLASSIFY_WORKERS", "8"))
CHECKPOINT_EVERY = 50


def nz(v) -> str:
    return str(v).strip().lower()


def any_rater(row, field: str, allowed: set) -> bool:
    return any(nz(row.get(c)) in allowed
               for c in (f"Final_{field}", f"Consensus_{field}", f"RaterA_{field}", f"RaterB_{field}"))


def parse_n(raw) -> str:
    """Coerce the model's answer to a non-negative int string, or '' for null/unknown."""
    if isinstance(raw, dict):
        raw = raw.get("n_total")
    if raw is None:
        return ""
    try:
        n = int(float(str(raw).strip()))
        return str(n) if n >= 0 else ""
    except (TypeError, ValueError):
        return ""


def main() -> None:
    cfg = load_config("children")
    set_active(cfg)
    rater = cfg.rater_a  # Nova 2 Lite — cheap
    path = cfg.adjudicated_csv
    df = pd.read_csv(path, dtype=str).fillna("")
    if "n_total" not in df.columns:
        df["n_total"] = ""

    pending = []
    for idx, row in df.iterrows():
        if nz(row.get("Screen_Pass")) != "y":
            continue
        if not (any_rater(row, "intervention_type", DIGITAL) and any_rater(row, "neurotypes", ND)):
            continue
        if str(row.get("n_total", "")).strip():
            continue  # already extracted
        if is_missing_abstract(str(row.get("Abstract", "") or "")):
            continue
        pending.append(idx)

    print(f"candidates needing sample-size extraction: {len(pending)} (rater {rater.label})")
    llm.warm(rater)

    def work(idx):
        title = str(df.at[idx, "Title"] or "")
        abstract = str(df.at[idx, "Abstract"] or "")
        try:
            raw = llm.invoke_json(rater, system_prompt=SYSTEM,
                                  user_prompt=f"Title: {title}\n\nAbstract: {abstract}",
                                  temperature=0.0, max_tokens=120)
            return idx, parse_n(raw)
        except Exception as e:  # noqa: BLE001
            print(f"    [{idx}] error: {e}")
            return idx, None  # leave unset -> retried next run

    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(work, idx) for idx in pending]
        for fut in as_completed(futures):
            idx, val = fut.result()
            if val is None:
                continue
            df.at[idx, "n_total"] = val
            done += 1
            if done % CHECKPOINT_EVERY == 0:
                df.to_csv(path, index=False)
                print(f"  [{done}/{len(pending)}] checkpoint", flush=True)

    df.to_csv(path, index=False)
    got = df.loc[df.n_total.str.strip() != "", "n_total"]
    nums = pd.to_numeric(got, errors="coerce").dropna()
    print(f"\nextracted N for {len(nums)} candidates | stated <20: {(nums < 20).sum()} | "
          f">=20: {(nums >= 20).sum()} | N not stated (kept, recall-safe): "
          f"{len(pending) - done if done < len(pending) else 0}+")


if __name__ == "__main__":
    main()
