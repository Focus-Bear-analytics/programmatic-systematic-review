"""Recover abstracts via Europe PMC for the still-missing snowball papers.

Europe PMC is free/no-auth, fast (no S2-style throttle), and often carries an
abstract where Semantic Scholar / Crossref / PubMed-by-DOI / landing-page all
came up empty (the sources already tried in the main backfill). Tries by DOI,
then by PMID for rows that have one.

Updates search-results-from-database/screened.csv in place: recovered rows get
their Abstract set and Screen_Pass / Screen_Reason cleared so the next screen
run re-evaluates them. Resumable + checkpointed every 50 rows.
"""
import os, sys
from collections import Counter
sys.path.insert(0, os.getcwd())
import pandas as pd
from steps.abstract_fetcher import fetch_europepmc
from steps.io import normalize_doi

SCREENED = "search-results-from-database/screened.csv"
scr = pd.read_csv(SCREENED, dtype=str).fillna("")

todo = [
    i for i in scr.index
    if scr.at[i, "Screen_Reason"] == "no_abstract"
    and (normalize_doi(scr.at[i, "DOI"]) or str(scr.at[i, "PMID"]).strip())
]
print(f"{len(todo)} still-missing papers (have DOI or PMID); trying Europe PMC", flush=True)

rec = 0
src = Counter()
for n, i in enumerate(todo, 1):
    doi = normalize_doi(scr.at[i, "DOI"])
    pmid = str(scr.at[i, "PMID"]).strip()
    try:
        ab = fetch_europepmc(doi=doi, pmid=pmid)
    except Exception:
        ab = None
    if ab and len(ab) > 60:
        scr.at[i, "Abstract"] = ab
        scr.at[i, "Screen_Pass"] = ""
        scr.at[i, "Screen_Reason"] = ""
        rec += 1
        src["doi" if doi else "pmid"] += 1
    if n % 50 == 0:
        scr.to_csv(SCREENED, index=False)
        print(f"  [{n}/{len(todo)}] recovered {rec}", flush=True)

scr.to_csv(SCREENED, index=False)
print(f"Europe PMC done: recovered {rec}/{len(todo)} ({dict(src)})", flush=True)
