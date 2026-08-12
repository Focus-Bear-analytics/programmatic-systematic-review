"""Recover abstracts for still-missing snowball papers with the fixed fetchers.
Order: improved landing-page (Springer/JSON-LD) -> Elsevier API (10.1016*, needs
RMIT IP/insttoken) -> keyless Semantic Scholar. Updates screened.csv. Resumable.
"""
import os, sys
from collections import Counter
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv(override=True)
import pandas as pd
from steps.abstract_fetcher import resolve_doi_url, fetch_landing_page, fetch_semantic_scholar, fetch_elsevier
from steps.io import normalize_doi

SCREENED = "search-results-from-database/screened.csv"
ELS_PREFIXES = ("10.1016", "10.1006", "10.1053", "10.1067", "10.1078")
scr = pd.read_csv(SCREENED, dtype=str).fillna("")
todo = [(i, normalize_doi(scr.at[i, "DOI"])) for i in scr.index
        if scr.at[i, "Screen_Reason"] == "no_abstract" and normalize_doi(scr.at[i, "DOI"])]
print(f"{len(todo)} still-missing (landing -> elsevier -> S2)", flush=True)
rec = 0; bysrc = Counter()
for n, (i, doi) in enumerate(todo, 1):
    ab = None; src = None
    try:
        url = resolve_doi_url(doi)
        if url:
            ab = fetch_landing_page(url); src = "landing"
        if not ab and doi.startswith(ELS_PREFIXES):
            ab = fetch_elsevier(doi); src = "elsevier"
        if not ab:
            ab = fetch_semantic_scholar(doi, None); src = "s2"
    except Exception:
        ab = None
    if ab and len(ab) > 60:
        scr.at[i, "Abstract"] = ab; scr.at[i, "Screen_Pass"] = ""; scr.at[i, "Screen_Reason"] = ""
        rec += 1; bysrc[src] += 1
    if n % 50 == 0:
        scr.to_csv(SCREENED, index=False)
        print(f"  [{n}/{len(todo)}] recovered {rec} {dict(bysrc)}", flush=True)
scr.to_csv(SCREENED, index=False)
print(f"DONE: recovered {rec}/{len(todo)} {dict(bysrc)}", flush=True)
