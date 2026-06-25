"""Retrieve full text for PAYWALLED Elsevier (10.1016-family) snowball candidates
via the ScienceDirect Article Retrieval API (FULL view).

Entitlement: returns full text only from a subscribing IP — run while connected
to the RMIT network/wifi (ELSEVIER_API_KEY is already set). Off-campus -> 401s.

Fills full_text_snowball/<id>.txt and flips ft_status paywalled -> retrieved
(source=elsevier_api) in snowball/fulltext_candidates.csv. Resumable. Free, no
browser — unlike the OpenAthens pass, which is only needed for non-Elsevier
paywalled publishers afterward.

After it runs:  poetry run python classify-snowball-audhd.py
"""
import os, sys
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv(override=True)
import pandas as pd
from steps.full_text import fetch_elsevier_fulltext
from steps.io import normalize_doi

CAND = "search-results-from-database/snowball/fulltext_candidates.csv"
TEXT_DIR = "full_text_snowball"
ELS_PREFIXES = ("10.1016", "10.1006", "10.1053", "10.1067", "10.1078")
os.makedirs(TEXT_DIR, exist_ok=True)

if not os.getenv("ELSEVIER_API_KEY"):
    sys.exit("ELSEVIER_API_KEY not set in .env")

cand = pd.read_csv(CAND, dtype=str).fillna("")
todo = []
for i in cand.index:
    if cand.at[i, "ft_status"] != "paywalled":
        continue
    doi = normalize_doi(cand.at[i, "DOI"])
    if doi and doi.startswith(ELS_PREFIXES):
        todo.append((i, doi))
print(f"{len(todo)} paywalled Elsevier candidates; trying ScienceDirect FULL API", flush=True)

rec = 0
for n, (i, doi) in enumerate(todo, 1):
    fidv = cand.at[i, "fulltext_id"]
    path = os.path.join(TEXT_DIR, f"{fidv}.txt")
    try:
        text = fetch_elsevier_fulltext(doi)
    except Exception as e:
        print(f"  row {i}: error {e}", file=sys.stderr); text = None
    if text:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        cand.at[i, "ft_status"] = "retrieved"
        cand.at[i, "ft_source"] = "elsevier_api"
        cand.at[i, "ft_chars"] = len(text)
        rec += 1
    if n == 5 and rec == 0:
        print("  (0/5 — likely not on the RMIT network; abstracts entitled but full "
              "text may need it too. Verify you're on RMIT wifi.)", flush=True)
    if n % 20 == 0:
        cand.to_csv(CAND, index=False)
        print(f"  [{n}/{len(todo)}] retrieved {rec}", flush=True)

cand.to_csv(CAND, index=False)
print(f"\nElsevier full text done: retrieved {rec}/{len(todo)}")
print("Next: poetry run python classify-snowball-audhd.py (folds these in)")
