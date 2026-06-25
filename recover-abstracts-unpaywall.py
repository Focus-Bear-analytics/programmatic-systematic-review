"""Recover abstracts for the no-abstract snowball papers via Unpaywall (headless).
Reuses the standalone filler's Unpaywall fetcher. Updates screened.csv in place:
recovered rows get their Abstract set and Screen_Pass cleared for re-screening.
Resumable + checkpointed.
"""
import importlib.util, os, sys
sys.path.insert(0, os.getcwd())
import pandas as pd

spec = importlib.util.spec_from_file_location("filler", "fill-missing-abstracts-by-doi.py")
filler = importlib.util.module_from_spec(spec); spec.loader.exec_module(filler)  # loads .env too

SCREENED = "search-results-from-database/screened.csv"
email = os.getenv("UNPAYWALL_EMAIL")
print(f"Unpaywall recovery (contact={email})", flush=True)

scr = pd.read_csv(SCREENED, dtype=str).fillna("")
todo = [(i, filler.normalize_doi(scr.at[i, "DOI"]))
        for i in scr.index
        if scr.at[i, "Screen_Reason"] == "no_abstract" and filler.normalize_doi(scr.at[i, "DOI"])]
print(f"{len(todo)} no-abstract papers with a DOI to try", flush=True)

rec = 0
for n, (i, doi) in enumerate(todo, 1):
    try:
        ab = filler.fetch_abstract_unpaywall(doi, email)
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
print(f"Unpaywall done: recovered {rec}/{len(todo)} abstracts", flush=True)
