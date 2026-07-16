"""Assemble the children (under-18) review dataset by REUSING the adult labels.

The adults corpus (``all_papers.csv``) already merges + de-duplicates all three
arms — database search, the adult review, and the systematic-review snowball —
and carries every paper's two-rater SCREEN labels (has_adults / has_under_18 /
is_empirical / is_parent_mediated) plus, for papers that passed the adult
screen, the two-rater DETAIL classification (study_type / intervention_type /
neurotypes / …).

The adults screen gated on ``has_adults`` — so child-ONLY papers (both raters
said has_adults=no) were short-circuited and never classified. This script:

  1. Takes the recall-safe under-18 universe: every non-duplicate paper the two
     raters did NOT both mark has_under_18=no.
  2. RE-DERIVES Screen_Pass under the CHILD age gate (require_age=has_under_18)
     from the EXISTING rater labels — no Bedrock spend on screening.
  3. Preserves the adult DETAIL classification, so the downstream classify step
     only pays to label the child-only papers the adult gate had dropped.

Output ``children/enriched.csv`` is exactly the shape ``steps.classify.run``
resumes from: it skips rows already carrying both raters' detail labels and
classifies only the rest.
"""
import os
import sys

sys.path.insert(0, os.getcwd())
import pandas as pd

from steps.config import load_config, set_active
from steps.screen import _gate
from steps.schema import SCREEN_FIELDS

SOURCE = "search-results-from-database/all_papers.csv"
REQUIRE_AGE = "has_under_18"


def nz(v) -> str:
    return str(v).strip().lower()


def both_no(a: dict, b: dict, field: str) -> bool:
    return nz(a.get(field)) == "no" and nz(b.get(field)) == "no"


def main() -> None:
    cfg = load_config("children")
    set_active(cfg)
    a_pref, b_pref = cfg.rater_a.column_prefix, cfg.rater_b.column_prefix
    assert a_pref == "RaterA" and b_pref == "RaterB", (
        f"children config must reuse RaterA/RaterB prefixes to match {SOURCE}; got {a_pref}/{b_pref}"
    )

    df = pd.read_csv(SOURCE, dtype=str).fillna("")
    n_all = len(df)
    df = df[df["is_duplicate"].str.strip().str.lower() != "y"].copy()
    print(f"{SOURCE}: {n_all} rows -> {len(df)} non-duplicate")

    def rater(row, pref: str) -> dict:
        return {f: row.get(f"{pref}_{f}", "") for f in SCREEN_FIELDS}

    # Recall-safe under-18 universe + re-derive Screen_Pass under the child gate.
    keep_rows, passes, reasons = [], [], []
    for _, row in df.iterrows():
        a, b = rater(row, a_pref), rater(row, b_pref)
        if both_no(a, b, REQUIRE_AGE):
            continue  # both raters agree no under-18 participant -> not a child paper
        keep_rows.append(row)
        p, why = _gate(a, b, REQUIRE_AGE)
        passes.append(p)
        reasons.append(why)

    kids = pd.DataFrame(keep_rows)
    kids["Screen_Pass"] = passes
    kids["Screen_Reason"] = reasons
    # Clear the carried-over adult Final_/Adjudicated verdicts: they were decided
    # under the adults gate. Detail RaterA/RaterB/Consensus labels are age-neutral
    # and kept, so classify reuses them; adjudication re-runs for this review.
    for f in ["study_type", "intervention_type", "neurotypes", "has_adults", "has_under_18"]:
        if f"Final_{f}" in kids.columns:
            kids[f"Final_{f}"] = ""
    if "Adjudicated" in kids.columns:
        kids["Adjudicated"] = ""

    classified = kids["Consensus_intervention_type"].str.strip() != ""
    passed = kids["Screen_Pass"].str.upper() == "Y"
    to_classify = passed & ~classified
    print(f"child universe (recall-safe under-18): {len(kids)}")
    print(f"  screen-pass under child gate: {int(passed.sum())}")
    print(f"    already classified (reuse, 0 Bedrock): {int((passed & classified).sum())}")
    print(f"    to classify via Bedrock:              {int(to_classify.sum())}")
    print(f"  screen-fail reasons: {dict(kids.loc[~passed, 'Screen_Reason'].value_counts())}")

    os.makedirs(cfg.review_dir, exist_ok=True)
    out = cfg.enriched_csv
    kids.to_csv(out, index=False)
    print(f"\nwrote {out} ({len(kids)} rows) — run: poetry run python pipeline_children_classify.py")


if __name__ == "__main__":
    main()
