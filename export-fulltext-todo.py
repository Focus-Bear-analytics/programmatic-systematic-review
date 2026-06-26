"""Export a CSV of the in-scope candidates that still need full-text retrieval.

Candidate = survivor whose FINAL (adjudicated, else consensus) intervention_type is
in-scope AND neurotype is ADHD/autistic/AuDHD. Joins prior full-text status
(snowball/fulltext_candidates.csv) so already-retrieved ones are excluded.
"""
import os, sys, re
sys.path.insert(0, os.getcwd())
import pandas as pd
import adjudicate_ui as ui

base = "search-results-from-database/"
INC = ui.INCLUDING_AGREED["intervention_type"]; ND = {"adhd", "autistic", "audhd"}
def nz(v): return str(v).strip().lower()
def nd(d): return str(d).strip().lower().replace("https://doi.org/", "")

df = pd.read_csv(base + "combined/adjudicated.csv", dtype=str).fillna("")

def final(r, f):
    if nz(r.get("Adjudicated")) == "human" and nz(r.get(f"Final_{f}")):
        return nz(r[f"Final_{f}"])
    return nz(r.get(f"Consensus_{f}"))

# prior full-text status by DOI
ftmap = {}
ftf = base + "snowball/fulltext_candidates.csv"
if os.path.exists(ftf):
    ft = pd.read_csv(ftf, dtype=str).fillna("")
    ftmap = {nd(r["DOI"]): (r.get("ft_status", ""), r.get("ft_source", ""))
             for r in ft.to_dict("records") if str(r.get("DOI", "")).strip()}

rows = []
for _, r in df.iterrows():
    if nz(r.get("Screen_Pass")) != "y":
        continue
    if final(r, "intervention_type") not in INC or final(r, "neurotypes") not in ND:
        continue
    doi = nd(r.get("DOI", ""))
    status, source = ftmap.get(doi, ("", ""))
    if status == "retrieved":
        continue  # already have full text
    need = "no_doi" if not doi else (status or "not_attempted")
    rows.append({
        "need_status": need,
        "DOI": r.get("DOI", ""), "PMID": r.get("PMID", ""),
        "Title": r.get("Title", ""), "Authors": r.get("Authors", ""),
        "Year": r.get("Year", ""), "Journal": r.get("Journal", ""),
        "intervention_type": final(r, "intervention_type"),
        "neurotypes": final(r, "neurotypes"),
        "has_adults": final(r, "has_adults"),
        "origin": r.get("origin", ""), "source_databases": r.get("source_databases", ""),
        "URL": r.get("URL", ""),
    })

out = pd.DataFrame(rows).sort_values(
    ["has_adults", "neurotypes", "need_status"], ascending=[False, True, True])
dest = base + "fulltext_to_retrieve.csv"
out.to_csv(dest, index=False)
print(f"wrote {dest}: {len(out)} papers needing full text")
print("  by need_status:", out["need_status"].value_counts().to_dict())
print("  by intervention_type:", out["intervention_type"].value_counts().to_dict())
print("  adult-inclusive:", int((out["has_adults"] == "yes").sum()))
