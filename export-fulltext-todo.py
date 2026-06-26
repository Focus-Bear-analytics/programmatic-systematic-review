"""Export a CSV of in-scope candidates that still need full-text retrieval.

Candidate = survivor whose FINAL (adjudicated, else consensus) intervention_type is
in-scope AND neurotype is ADHD/autistic/AuDHD. Recognises DOI, PMID, AND OpenAlex
ID as retrieval routes (so a missing DOI isn't a dead end), backfilling DOI/PMID
from OpenAlex when both are absent. Excludes already-retrieved papers.
"""
import os, re, sys, requests
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv(override=True)
import pandas as pd
import adjudicate_ui as ui

base = "search-results-from-database/"
INC = ui.INCLUDING_AGREED["intervention_type"]; ND = {"adhd", "autistic", "audhd"}
EMAIL = os.getenv("UNPAYWALL_EMAIL", "research@example.com")
def nz(v): return str(v).strip().lower()
def nd(d): return str(d).strip().lower().replace("https://doi.org/", "")
def oaid(url):
    m = re.search(r"openalex\.org/(W\d+)", str(url)); return m.group(1) if m else ""

df = pd.read_csv(base + "combined/adjudicated.csv", dtype=str).fillna("")
def final(r, f):
    if nz(r.get("Adjudicated")) == "human" and nz(r.get(f"Final_{f}")):
        return nz(r[f"Final_{f}"])
    return nz(r.get(f"Consensus_{f}"))

ftmap = {}
if os.path.exists(base + "snowball/fulltext_candidates.csv"):
    ft = pd.read_csv(base + "snowball/fulltext_candidates.csv", dtype=str).fillna("")
    ftmap = {nd(r["DOI"]): r.get("ft_status", "") for r in ft.to_dict("records") if str(r.get("DOI", "")).strip()}

def openalex_ids(wid):
    try:
        j = requests.get(f"https://api.openalex.org/works/{wid}", params={"mailto": EMAIL}, timeout=20).json()
        ids = j.get("ids", {})
        return nd(ids.get("doi", "")), str(ids.get("pmid", "")).rsplit("/", 1)[-1]
    except Exception:
        return "", ""

rows = []
for _, r in df.iterrows():
    if nz(r.get("Screen_Pass")) != "y":
        continue
    if final(r, "intervention_type") not in INC or final(r, "neurotypes") not in ND:
        continue
    doi = nd(r.get("DOI", "")); pmid = str(r.get("PMID", "")).strip(); wid = oaid(r.get("URL", ""))
    if doi and ftmap.get(doi) == "retrieved":
        continue
    if not doi and not pmid and wid:               # backfill from OpenAlex
        doi, pmid = openalex_ids(wid)
    route = "doi" if doi else ("pmid" if pmid else ("openalex" if wid else "none"))
    prior = "retrieved_excluded" if ftmap.get(doi) == "retrieved" else (ftmap.get(doi, "") or "not_attempted")
    if prior == "retrieved_excluded":
        continue
    rows.append({"retrieval_route": route, "prior_ft": prior,
                 "DOI": doi, "PMID": pmid, "openalex_id": wid,
                 "Title": r.get("Title", ""), "Authors": r.get("Authors", ""),
                 "Year": r.get("Year", ""), "Journal": r.get("Journal", ""),
                 "intervention_type": final(r, "intervention_type"),
                 "neurotypes": final(r, "neurotypes"), "has_adults": final(r, "has_adults"),
                 "origin": r.get("origin", ""), "URL": r.get("URL", "")})

out = pd.DataFrame(rows).sort_values(
    ["has_adults", "retrieval_route", "neurotypes"], ascending=[False, True, True])
out.to_csv(base + "fulltext_to_retrieve.csv", index=False)
print(f"wrote {base}fulltext_to_retrieve.csv: {len(out)} papers")
print("  retrieval_route:", out["retrieval_route"].value_counts().to_dict())
print("  prior_ft:", out["prior_ft"].value_counts().to_dict())
print("  adult-inclusive:", int((out["has_adults"] == "yes").sum()))
