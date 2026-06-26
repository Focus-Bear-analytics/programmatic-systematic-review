"""Build the two clean deliverables from combined/adjudicated.csv:

  1. fulltext_review_master.csv  — every in-scope candidate that needs full-text
     review: final screening/classification labels + the full-text filename +
     ft_status (have | need) + AuDHD result if already checked.
  2. fulltext_to_retrieve.csv    — ONLY the papers still needing a PDF (ft_status
     = need), with the exact save_as filename to download them under.
"""
import os, sys
sys.path.insert(0, os.getcwd())
import pandas as pd
import adjudicate_ui as ui
from steps.io import normalize_doi

base = "search-results-from-database/"
INC = ui.INCLUDING_AGREED["intervention_type"]; ND = {"adhd", "autistic", "audhd"}
TEXT_DIR = "full_text_snowball"
def nz(v): return str(v).strip().lower()
def nd(d): return normalize_doi(d) or ""
def fid(doi): return nd(doi).replace("/", "_").replace(":", "_") if nd(doi) else ""

df = pd.read_csv(base + "combined/adjudicated.csv", dtype=str).fillna("")
def fin(r, f):
    return nz(r.get("Final_" + f)) if nz(r.get("Adjudicated")) == "human" and nz(r.get("Final_" + f)) else nz(r.get("Consensus_" + f))

# AuDHD results by DOI
au = {}
if os.path.exists(base + "snowball/fulltext_audhd.csv"):
    a = pd.read_csv(base + "snowball/fulltext_audhd.csv", dtype=str).fillna("")
    au = {nd(r["DOI"]): (r.get("audhd", ""), r.get("adult_audhd", "")) for r in a.to_dict("records")}

rows = []
for _, r in df.iterrows():
    if nz(r.get("Screen_Pass")) != "y":
        continue
    if fin(r, "intervention_type") not in INC or fin(r, "neurotypes") not in ND:
        continue
    doi = nd(r.get("DOI", "")); fname = (fid(doi) + ".txt") if doi else ""
    have = bool(fname) and os.path.exists(os.path.join(TEXT_DIR, fname)) and os.path.getsize(os.path.join(TEXT_DIR, fname)) > 1000
    audhd, adult_audhd = au.get(doi, ("", ""))
    rows.append({
        "DOI": r.get("DOI", ""), "PMID": r.get("PMID", ""), "Title": r.get("Title", ""),
        "Authors": r.get("Authors", ""), "Year": r.get("Year", ""), "Journal": r.get("Journal", ""),
        "origin": r.get("origin", ""), "source_databases": r.get("source_databases", ""),
        "has_adults": fin(r, "has_adults"), "has_under_18": fin(r, "has_under_18"),
        "is_empirical": fin(r, "is_empirical"), "is_parent_mediated": fin(r, "is_parent_mediated"),
        "study_type": fin(r, "study_type"), "intervention_type": fin(r, "intervention_type"),
        "neurotypes": fin(r, "neurotypes"),
        "full_text_filename": (fname if doi else f"PMID{r.get('PMID','')}.pdf"),
        "ft_status": "have" if have else "need",
        "audhd": audhd, "adult_audhd": adult_audhd, "URL": r.get("URL", ""),
    })

master = pd.DataFrame(rows).sort_values(["ft_status", "has_adults", "intervention_type"],
                                        ascending=[True, False, True])
master.to_csv(base + "fulltext_review_master.csv", index=False)
print(f"fulltext_review_master.csv: {len(master)} candidates "
      f"(have full text: {(master.ft_status=='have').sum()}, need: {(master.ft_status=='need').sum()})")

# to-retrieve = need only, with save_as = the filename to save the PDF under
todo = master[master.ft_status == "need"].copy()
todo["save_as"] = todo["full_text_filename"].str.replace(".txt", ".pdf", regex=False)
cols = ["save_as", "DOI", "PMID", "Title", "Authors", "Year", "Journal",
        "intervention_type", "neurotypes", "has_adults", "URL"]
todo[cols].to_csv(base + "fulltext_to_retrieve.csv", index=False)
print(f"fulltext_to_retrieve.csv: {len(todo)} papers to fetch (PDFs into manual_fulltext/)")
