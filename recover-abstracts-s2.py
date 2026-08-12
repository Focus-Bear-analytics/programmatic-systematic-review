"""Recover abstracts via KEYLESS Semantic Scholar for still-missing snowball papers.
The dead API key (403) was disabled; keyless S2 (200) can now be reached. The other
sources (crossref/pubmed/landing) already failed these rows, so we try S2 only.
Updates screened.csv (clears Screen_Pass for recovered rows). Resumable.
"""
import os, sys
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv(override=True)
import pandas as pd
from steps.abstract_fetcher import fetch_semantic_scholar  # throttles to 1 req/s
from steps.io import normalize_doi

SCREENED = "search-results-from-database/screened.csv"
scr = pd.read_csv(SCREENED, dtype=str).fillna("")
todo = [(i, normalize_doi(scr.at[i, "DOI"])) for i in scr.index
        if scr.at[i, "Screen_Reason"] == "no_abstract" and normalize_doi(scr.at[i, "DOI"])]
print(f"{len(todo)} still-missing papers; trying keyless Semantic Scholar", flush=True)
rec = 0
for n, (i, doi) in enumerate(todo, 1):
    try:
        ab = fetch_semantic_scholar(doi, None)
    except Exception:
        ab = None
    if ab and len(ab) > 60:
        scr.at[i, "Abstract"] = ab; scr.at[i, "Screen_Pass"] = ""; scr.at[i, "Screen_Reason"] = ""
        rec += 1
    if n % 50 == 0:
        scr.to_csv(SCREENED, index=False)
        print(f"  [{n}/{len(todo)}] recovered {rec}", flush=True)
scr.to_csv(SCREENED, index=False)
print(f"S2 keyless done: recovered {rec}/{len(todo)}", flush=True)
