"""Recover abstracts via the Springer Nature API for still-missing snowball
papers with a Springer-family DOI (10.1007 dominates the missing set at ~457).

Springer's Meta API returns abstracts for subscription + OA content, so it
reaches paywalled papers the open aggregators (S2/Crossref/PubMed/landing) miss.
Keys come from SPRINGER_META_API_KEY / SPRINGER_OA_API_KEY in .env.

Updates search-results-from-database/screened.csv in place: recovered rows get
their Abstract set and Screen_Pass / Screen_Reason cleared for re-screening.
Resumable + checkpointed every 50 rows.
"""
import os, sys
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv(override=True)
import pandas as pd
from steps.abstract_fetcher import fetch_springer
from steps.io import normalize_doi

SCREENED = "search-results-from-database/screened.csv"
# Springer Nature DOI prefixes (10.1007 = Springer journals/books; others are
# Nature, BMC, Palgrave, Adis, etc.).
SPRINGER_PREFIXES = (
    "10.1007", "10.1023", "10.1038", "10.1057", "10.1065", "10.1140",
    "10.1186", "10.1245", "10.1361", "10.1365", "10.3758", "10.1617",
)

scr = pd.read_csv(SCREENED, dtype=str).fillna("")
todo = []
for i in scr.index:
    if scr.at[i, "Screen_Reason"] != "no_abstract":
        continue
    doi = normalize_doi(scr.at[i, "DOI"])
    if doi and doi.startswith(SPRINGER_PREFIXES):
        todo.append((i, doi))
print(f"{len(todo)} still-missing Springer-DOI papers; trying Springer Nature API", flush=True)

rec = 0
for n, (i, doi) in enumerate(todo, 1):
    try:
        ab = fetch_springer(doi)
    except Exception:
        ab = None
    if ab and len(ab) > 60:
        scr.at[i, "Abstract"] = ab
        scr.at[i, "Screen_Pass"] = ""
        scr.at[i, "Screen_Reason"] = ""
        rec += 1
    if n % 50 == 0:
        scr.to_csv(SCREENED, index=False)
        print(f"  [{n}/{len(todo)}] recovered {rec}", flush=True)

scr.to_csv(SCREENED, index=False)
print(f"Springer done: recovered {rec}/{len(todo)}", flush=True)
