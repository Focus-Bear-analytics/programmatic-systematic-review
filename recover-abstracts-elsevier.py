"""Recover abstracts via the Elsevier Abstract Retrieval API for still-missing
snowball papers with an Elsevier (ScienceDirect) DOI — 10.1016 dominates the
missing set at ~397.

IMPORTANT — entitlement: Elsevier gates the abstract view (META_ABS) by
institution. Off-campus with only the free API key you get HTTP 401. To make
this work, EITHER:
  • run this while connected to the RMIT VPN / network (your IP becomes
    entitled — no insttoken needed), OR
  • set ELSEVIER_INSTTOKEN in .env (one-time token from the RMIT library).
ELSEVIER_API_KEY must also be set (it already is).

Updates search-results-from-database/screened.csv in place: recovered rows get
their Abstract set and Screen_Pass / Screen_Reason cleared for re-screening.
Resumable + checkpointed every 50 rows. Do NOT run while the screen is running
(both write screened.csv).
"""
import os, sys
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv(override=True)
import pandas as pd
from steps.abstract_fetcher import fetch_elsevier
from steps.io import normalize_doi

SCREENED = "search-results-from-database/screened.csv"
ELS_PREFIXES = ("10.1016", "10.1006", "10.1053", "10.1067", "10.1078")

if not os.getenv("ELSEVIER_API_KEY"):
    sys.exit("ELSEVIER_API_KEY not set in .env")
if not os.getenv("ELSEVIER_INSTTOKEN"):
    print("note: no ELSEVIER_INSTTOKEN — you must be on the RMIT VPN/network for "
          "the abstract view to be entitled (otherwise every call 401s).", flush=True)

scr = pd.read_csv(SCREENED, dtype=str).fillna("")
todo = []
for i in scr.index:
    if scr.at[i, "Screen_Reason"] != "no_abstract":
        continue
    doi = normalize_doi(scr.at[i, "DOI"])
    if doi and doi.startswith(ELS_PREFIXES):
        todo.append((i, doi))
print(f"{len(todo)} still-missing Elsevier-DOI papers; trying Elsevier Abstract API", flush=True)

rec = 0
for n, (i, doi) in enumerate(todo, 1):
    try:
        ab = fetch_elsevier(doi)
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
    if n == 10 and rec == 0:
        print("  (0/10 so far — if these are all 401s, you're likely not on the "
              "RMIT VPN; abort, connect, and re-run.)", flush=True)

scr.to_csv(SCREENED, index=False)
print(f"Elsevier done: recovered {rec}/{len(todo)}", flush=True)
