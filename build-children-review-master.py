"""Build the children (under-18) full-text candidate list from
``children/adjudicated.csv``.

Candidate selection is RECALL-SAFE / open-minded, matching how the adults review
treats ambiguity: a paper is a full-text candidate when it clears the child
screen gate AND *either* rater (or the consensus/final label) marks it a digital
intervention AND *either* rater marks the sample ADHD / autistic / AuDHD. A paper
whose abstract only mentions ADHD or autism is therefore KEPT for the full-text
check rather than dropped — the full text resolves it, not the abstract.

Outputs (namespaced under children/, adults deliverables untouched):
  1. children/fulltext_review_master.csv — every candidate + labels + ft_status
     (have | need) + the full-text filename.
  2. children/fulltext_to_retrieve.csv   — only candidates still missing a PDF.
"""
import os
import sys

sys.path.insert(0, os.getcwd())
import pandas as pd

from steps.io import normalize_doi

BASE = "search-results-from-database/"
SRC = BASE + "children/adjudicated.csv"

# Digital-intervention inclusion set. The children review uses the BROAD net:
# the adults' 10 types PLUS the modalities common in childhood autism/ADHD
# interventions (VR/AR, video modelling, e-learning, AAC, robotics, wearables,
# telehealth), PLUS parent_training so parent-/caregiver-mediated DIGITAL
# programmes surface as candidates (digital delivery confirmed at full text).
DIGITAL = {
    "mobile_app", "web_app", "software_tool", "video_game", "neurofeedback",
    "cbt", "cognitive_training", "mindfulness", "chatbot", "biofeedback",
    "vr_ar", "video_modeling", "elearning", "aac", "robotics", "wearable",
    "telecoaching", "telecounselling", "parent_training",
}
ND = {"adhd", "autistic", "audhd"}

# Where retrieved full text already lives.
SNOWBALL_TXT = "full_text_snowball"
DB_TXT = "full_text"
MANUAL_PDF = "manual_fulltext"


def nz(v) -> str:
    return str(v).strip().lower()


def nd(doi) -> str:
    return normalize_doi(doi) or ""


def fid(doi) -> str:
    d = nd(doi)
    return d.replace("/", "_").replace(":", "_") if d else ""


def any_rater(row, field: str, allowed: set) -> bool:
    """Recall-safe: true if ANY of final/consensus/raterA/raterB is in `allowed`."""
    for col in (f"Final_{field}", f"Consensus_{field}", f"RaterA_{field}", f"RaterB_{field}"):
        if nz(row.get(col)) in allowed:
            return True
    return False


def pick(row, field: str) -> str:
    """Best single label for display: Final, else Consensus, else 'A|B' if they differ."""
    for col in (f"Final_{field}", f"Consensus_{field}"):
        if nz(row.get(col)):
            return str(row.get(col)).strip()
    a, b = str(row.get(f"RaterA_{field}", "")).strip(), str(row.get(f"RaterB_{field}", "")).strip()
    return a if a == b else (f"{a}|{b}" if (a or b) else "")


def have_fulltext(doi: str, pmid: str) -> tuple[bool, str]:
    """Return (have, filename) checking snowball .txt, db .txt, manual .pdf."""
    f = fid(doi)
    if f:
        txt = os.path.join(SNOWBALL_TXT, f + ".txt")
        if os.path.exists(txt) and os.path.getsize(txt) > 1000:
            return True, f + ".txt"
        pdf = os.path.join(MANUAL_PDF, f + ".pdf")
        if os.path.exists(pdf) and os.path.getsize(pdf) > 1000:
            return True, f + ".pdf"
    if pmid:
        txt = os.path.join(DB_TXT, f"{pmid}.txt")
        if os.path.exists(txt) and os.path.getsize(txt) > 1000:
            return True, f"{pmid}.txt"
    return False, (f + ".pdf" if f else (f"PMID{pmid}.pdf" if pmid else ""))


def main() -> None:
    df = pd.read_csv(SRC, dtype=str).fillna("")
    rows = []
    for _, r in df.iterrows():
        if nz(r.get("Screen_Pass")) != "y":
            continue
        if not any_rater(r, "intervention_type", DIGITAL):
            continue
        if not any_rater(r, "neurotypes", ND):
            continue
        doi, pmid = r.get("DOI", ""), r.get("PMID", "")
        have, fname = have_fulltext(doi, pmid)
        rows.append({
            "DOI": doi, "PMID": pmid, "Title": r.get("Title", ""),
            "Authors": r.get("Authors", ""), "Year": r.get("Year", ""),
            "Journal": r.get("Journal", ""), "origin": r.get("origin", ""),
            "source_databases": r.get("source_databases", ""),
            "has_adults": pick(r, "has_adults"), "has_under_18": pick(r, "has_under_18"),
            "study_type": pick(r, "study_type"),
            "intervention_type": pick(r, "intervention_type"),
            "neurotypes": pick(r, "neurotypes"),
            "full_text_filename": fname,
            "ft_status": "have" if have else "need",
            "URL": r.get("URL", ""),
        })

    master = pd.DataFrame(rows).sort_values(
        ["ft_status", "neurotypes", "intervention_type"], ascending=[True, True, True])
    out = BASE + "children/fulltext_review_master.csv"
    master.to_csv(out, index=False)
    have_n = int((master.ft_status == "have").sum())
    need_n = int((master.ft_status == "need").sum())
    print(f"{out}: {len(master)} candidates (have full text: {have_n}, need: {need_n})")
    print(f"  by origin:     {dict(master.origin.value_counts())}")
    print(f"  by neurotype:  {dict(master.neurotypes.value_counts())}")

    todo = master[master.ft_status == "need"].copy()
    todo["save_as"] = todo["full_text_filename"]
    cols = ["save_as", "DOI", "PMID", "Title", "Authors", "Year", "Journal",
            "intervention_type", "neurotypes", "has_under_18", "has_adults", "URL"]
    out2 = BASE + "children/fulltext_to_retrieve.csv"
    todo[cols].to_csv(out2, index=False)
    print(f"{out2}: {len(todo)} papers to fetch")


if __name__ == "__main__":
    main()
