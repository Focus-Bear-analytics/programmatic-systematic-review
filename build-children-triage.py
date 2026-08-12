"""Triage the children full-text candidates that still NEED retrieval, so manual
effort targets real primary studies rather than recall-safe noise.

The candidate net is deliberately generous (a paper is kept when EITHER rater
flags a digital intervention AND EITHER flags ADHD/autism). This ranks the
still-missing papers by how strongly BOTH raters agree, and separates out the
rows both raters call non-empirical (reviews / commentaries / protocols /
proposals) — not primary-study full-text targets.

Tiers (over ft_status=need only):
  1 STRONG   — both raters: digital intervention + ND + empirical study type.
  2 MODERATE — empirical-plausible but one-sided on some dimension.
  3 DROP     — both raters call it non-empirical.
  4 DROP     — abstract clearly reports N < 20 (recall-safe: unstated N is KEPT).

Outputs:
  children/fulltext_to_retrieve_priority.csv — Tier 1 then Tier 2, ranked.
  children/fulltext_triage_dropped.csv       — Tiers 3-4 (non-empirical / underpowered).
"""
import os
import sys

sys.path.insert(0, os.getcwd())
import pandas as pd

from steps.io import normalize_doi

BASE = "search-results-from-database/"
SRC = BASE + "children/adjudicated.csv"

DIGITAL = {"mobile_app", "web_app", "software_tool", "video_game", "neurofeedback",
           "cbt", "cognitive_training", "mindfulness", "chatbot", "biofeedback",
           "vr_ar", "video_modeling", "elearning", "aac", "robotics", "wearable",
           "telecoaching", "telecounselling", "parent_training"}
ND = {"adhd", "autistic", "audhd"}
EMPIRICAL = {"empirical_with_results", "qualitative_only_study", "case_study"}
NON_EMPIRICAL = {"review", "commentary", "proposal", "protocol"}
MIN_N = 20  # studies clearly reporting fewer enrolled participants are set aside

SNOWBALL_TXT, DB_TXT, MANUAL_PDF = "full_text_snowball", "full_text", "manual_fulltext"


def nz(v) -> str:
    return str(v).strip().lower()


def fid(doi) -> str:
    d = normalize_doi(doi) or ""
    return d.replace("/", "_").replace(":", "_") if d else ""


def any_rater(row, field: str, allowed: set) -> bool:
    return any(nz(row.get(c)) in allowed
               for c in (f"Final_{field}", f"Consensus_{field}", f"RaterA_{field}", f"RaterB_{field}"))


def rater_agreement(row, field: str, allowed: set) -> int:
    """How many of the two raters put this field in `allowed` (0/1/2)."""
    return sum(1 for p in ("RaterA_", "RaterB_") if nz(row.get(p + field)) in allowed)


def pick(row, field: str) -> str:
    for col in (f"Final_{field}", f"Consensus_{field}"):
        if nz(row.get(col)):
            return str(row.get(col)).strip()
    a, b = str(row.get(f"RaterA_{field}", "")).strip(), str(row.get(f"RaterB_{field}", "")).strip()
    return a if a == b else (f"{a}|{b}" if (a or b) else "")


def have_fulltext(doi: str, pmid: str) -> bool:
    f = fid(doi)
    for path in ([os.path.join(SNOWBALL_TXT, f + ".txt"), os.path.join(MANUAL_PDF, f + ".pdf")] if f else []) \
            + ([os.path.join(DB_TXT, f"{pmid}.txt")] if pmid else []):
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            return True
    return False


def main() -> None:
    df = pd.read_csv(SRC, dtype=str).fillna("")
    rows = []
    for _, r in df.iterrows():
        if nz(r.get("Screen_Pass")) != "y":
            continue
        if not (any_rater(r, "intervention_type", DIGITAL) and any_rater(r, "neurotypes", ND)):
            continue
        if have_fulltext(r.get("DOI", ""), r.get("PMID", "")):
            continue  # already retrieved — not a triage target
        dig = rater_agreement(r, "intervention_type", DIGITAL)
        nd = rater_agreement(r, "neurotypes", ND)
        emp = rater_agreement(r, "study_type", EMPIRICAL)
        nonemp = rater_agreement(r, "study_type", NON_EMPIRICAL)
        try:
            n = int(str(r.get("n_total", "")).strip())
        except ValueError:
            n = None
        underpowered = n is not None and n < MIN_N
        if nonemp == 2:
            tier = 3
        elif underpowered:
            tier = 4  # abstract clearly reports < MIN_N participants
        elif dig == 2 and nd == 2 and emp == 2:
            tier = 1
        else:
            tier = 2
        rows.append({
            "tier": tier, "score": dig + nd + emp,
            "DOI": r.get("DOI", ""), "PMID": r.get("PMID", ""), "Title": r.get("Title", ""),
            "Authors": r.get("Authors", ""), "Year": r.get("Year", ""), "Journal": r.get("Journal", ""),
            "origin": r.get("origin", ""),
            "study_type": pick(r, "study_type"),
            "intervention_type": pick(r, "intervention_type"),
            "neurotypes": pick(r, "neurotypes"),
            "n_total": r.get("n_total", ""),
            "dig_agree": dig, "nd_agree": nd, "emp_agree": emp,
            "save_as": (fid(r.get("DOI", "")) + ".pdf") if fid(r.get("DOI", "")) else f"PMID{r.get('PMID','')}.pdf",
            "URL": r.get("URL", ""),
        })

    t = pd.DataFrame(rows)
    n = {i: int((t.tier == i).sum()) for i in (1, 2, 3, 4)}
    print(f"still-missing candidates: {len(t)}")
    print(f"  Tier 1 STRONG   (both digital + both ND + both empirical): {n[1]}")
    print(f"  Tier 2 MODERATE (empirical-plausible, one-sided somewhere): {n[2]}")
    print(f"  Tier 3 DROP     (both raters non-empirical):                {n[3]}")
    print(f"  Tier 4 DROP     (abstract clearly reports N < {MIN_N}):          {n[4]}")

    priority = t[t.tier <= 2].sort_values(["tier", "score", "neurotypes"], ascending=[True, False, True])
    out1 = BASE + "children/fulltext_to_retrieve_priority.csv"
    priority.drop(columns=["score"]).to_csv(out1, index=False)
    print(f"\n{out1}: {len(priority)} papers worth retrieving ({n[1]} strong + {n[2]} moderate)")
    print("  priority by neurotype:", dict(priority.neurotypes.value_counts().head(6)))

    dropped = t[t.tier >= 3].sort_values(["tier", "neurotypes"])
    out2 = BASE + "children/fulltext_triage_dropped.csv"
    dropped.drop(columns=["score"]).to_csv(out2, index=False)
    print(f"{out2}: {len(dropped)} set aside ({n[3]} non-empirical + {n[4]} underpowered N<{MIN_N})")


if __name__ == "__main__":
    main()
