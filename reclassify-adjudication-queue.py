"""Re-rate the papers currently in the human adjudication queue with the two
Bedrock models under the UPDATED classification prompt (which now distinguishes
`data_collection_only` from `no_intervention`).

Scope = pending, decision-relevant disagreements in the combined working file
(combined/adjudicated.csv) — i.e. exactly the papers you'd otherwise adjudicate
by hand. Human-resolved rows (Adjudicated=human) and auto-agreed/auto-excluded
rows are left untouched.

For each target row it re-runs Rater A (Nova 2 Lite) + Rater B (Claude Sonnet
4.6), rewrites RaterA_/RaterB_ for the consensus fields (+ details/reasoning),
sets RaterA_model/RaterB_model, and recomputes Consensus_/Consensus_Reached.
Leaves Adjudicated blank so the UI re-derives the queue on reload: rows that now
AGREE (e.g. both -> data_collection_only) auto-resolve and drop out.

Resumable-safe (idempotent). Stop the adjudication UI before running, then
restart it afterwards:  ADJ_REVIEW_SUBDIR=combined poetry run python adjudicate_ui.py adults
"""
import os, sys, shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv(override=True)
import pandas as pd
from steps.config import load_config, set_active
from steps import llm, rules
from steps.schema import CLASSIFICATION_PROMPT, coerce_classification, CONSENSUS_FIELDS, ALLOWED

base = "search-results-from-database/combined/"
WORK = base + "adjudicated.csv" if os.path.exists(base + "adjudicated.csv") else base + "enriched.csv"

EXCLUDING_AGREED = {
    "has_adults": {"no"},
    "neurotypes": {"neither_adhd_nor_autistic"},
    "study_type": {"review", "protocol", "proposal", "commentary"},
    "intervention_type": {"no_intervention", "data_collection_only", "parent_training",
                          "telecoaching", "telecounselling", "wearable", "vr_ar",
                          "video_modeling", "social_skills_training", "physical_activity",
                          "robotics", "music_art_therapy", "elearning", "non_software_based"},
}
INCLUDING_AGREED = {
    "has_adults": {"yes"},
    "study_type": {"empirical_with_results", "qualitative_only_study", "case_study"},
    "intervention_type": {"mobile_app", "web_app", "software_tool", "video_game", "neurofeedback",
                          "cbt", "cognitive_training", "mindfulness", "chatbot", "biofeedback"},
    "neurotypes": {"adhd", "autistic", "audhd"},
}
# has_under_18 doesn't gate the adults review, so a disagreement on it alone is
# not decision-relevant — mirror the UI's queue_fields.
QUEUE_FIELDS = [f for f in CONSENSUS_FIELDS if f != "has_under_18"]
HUMAN = "human"
def nz(v): return str(v).strip().lower()
def present(v): return nz(v) not in ("", "nan")
def includes(f, av, bv):
    av, bv = nz(av), nz(bv)
    if av == bv: return av not in EXCLUDING_AGREED.get(f, set())
    return av in INCLUDING_AGREED.get(f, set()) and bv in INCLUDING_AGREED.get(f, set())


def is_target(r):
    """Pending, decision-relevant disagreement on the consensus fields."""
    if nz(r.get("is_duplicate")) == "y":
        return False
    if len(str(r.get("Abstract", "")).strip()) < 20:
        return False
    if nz(r.get("Adjudicated")) in (HUMAN, "y", "yes", "no", "n"):
        return False  # already resolved (human) or finalised
    a = {f: r.get(f"RaterA_{f}", "") for f in QUEUE_FIELDS}
    b = {f: r.get(f"RaterB_{f}", "") for f in QUEUE_FIELDS}
    if not all(present(a[f]) and present(b[f]) for f in QUEUE_FIELDS):
        return False
    dead = any(nz(a[f]) in EXCLUDING_AGREED.get(f, set()) and nz(b[f]) in EXCLUDING_AGREED.get(f, set())
               for f in QUEUE_FIELDS)
    included = all(includes(f, a[f], b[f]) for f in QUEUE_FIELDS)
    return not (dead or included)  # queue only if outcome could still flip


def rate(rater, title, abstract):
    raw = llm.invoke_json(rater, system_prompt=CLASSIFICATION_PROMPT,
                          user_prompt=f"Title: {title}\n\nAbstract: {abstract}", temperature=0)
    res = coerce_classification(raw)
    ov = rules.apply_rules(title, abstract)
    res.update({k: v for k, v in ov.items() if k in res})
    return res, str(raw.get("reasoning", ""))[:400]


def main():
    cfg = load_config("adults"); set_active(cfg)
    ra, rb = cfg.rater_a, cfg.rater_b
    df = pd.read_csv(WORK, dtype=str).fillna("")
    targets = [i for i in df.index if is_target(df.loc[i].to_dict())]
    print(f"{WORK}: {len(targets)} pending queue rows to re-rate with {ra.label} + {rb.label}", flush=True)
    if not targets:
        return
    shutil.copy(WORK, WORK.replace(".csv", "_pre_reclassify_backup.csv"))
    for r in (ra, rb): llm.warm(r)

    WRITE = CONSENSUS_FIELDS + ["intervention_details"]
    done = 0
    with ThreadPoolExecutor(max_workers=int(os.getenv("CLASSIFY_WORKERS", "8"))) as pool:
        futs = {pool.submit(_row, i, df, ra, rb, WRITE): i for i in targets}
        for fut in as_completed(futs):
            done += 1
            if done % 25 == 0:
                df.to_csv(WORK, index=False)
                print(f"  [{done}/{len(targets)}] re-rated; checkpoint", flush=True)
    df.to_csv(WORK, index=False)

    # Report outcome
    now_agree = dci = 0
    for i in targets:
        r = df.loc[i]
        if all(nz(r.get(f"RaterA_{f}")) == nz(r.get(f"RaterB_{f}")) for f in CONSENSUS_FIELDS):
            now_agree += 1
        if "data_collection_only" in (nz(r.get("RaterA_intervention_type")), nz(r.get("RaterB_intervention_type"))):
            dci += 1
    print(f"\nre-rated {len(targets)} | now agree (auto-resolve on reload): {now_agree} | "
          f"with a data_collection_only label: {dci}")
    print("Restart the UI:  ADJ_REVIEW_SUBDIR=combined poetry run python adjudicate_ui.py adults")


def _row(i, df, ra, rb, write_fields):
    title = str(df.at[i, "Title"] or ""); abs = str(df.at[i, "Abstract"] or "")
    try:
        a_res, a_reason = rate(ra, title, abs)
    except Exception as e:
        print(f"  [{i}] {ra.label} error: {e}"); return
    try:
        b_res, b_reason = rate(rb, title, abs)
    except Exception as e:
        print(f"  [{i}] {rb.label} error: {e}"); return
    for f in write_fields:
        df.at[i, f"RaterA_{f}"] = a_res.get(f, "")
        df.at[i, f"RaterB_{f}"] = b_res.get(f, "")
        if f in CONSENSUS_FIELDS:
            av, bv = a_res.get(f, ""), b_res.get(f, "")
            df.at[i, f"Consensus_{f}"] = av if nz(av) == nz(bv) else ""
    df.at[i, "RaterA_model"] = ra.label
    df.at[i, "RaterB_model"] = rb.label
    df.at[i, "RaterA_reasoning"] = a_reason
    df.at[i, "RaterB_reasoning"] = b_reason
    df.at[i, "Consensus_Reached"] = "Y" if all(
        nz(a_res.get(f)) == nz(b_res.get(f)) for f in CONSENSUS_FIELDS) else "N"


if __name__ == "__main__":
    main()
