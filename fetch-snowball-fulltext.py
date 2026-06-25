"""Retrieve OPEN-ACCESS full text for the snowball digital-intervention
candidates (Phase-2 survivors: digital intervention + ADHD/autism/AuDHD).

Free sources only (Europe PMC OA + Unpaywall). Paywalled papers are recorded as
status=paywalled for the later OpenAthens/Playwright pass. Resumable: re-running
skips candidates whose text file already exists.

Outputs:
  full_text_snowball/<doi-sanitised>.txt   — extracted full text
  search-results-from-database/snowball/fulltext_candidates.csv  — status table
"""
import os, sys
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv(override=True)
import pandas as pd
from steps.full_text import fetch_open_full_text
from steps.io import normalize_doi

ENR = "search-results-from-database/snowball/enriched.csv"
OUT = "search-results-from-database/snowball/fulltext_candidates.csv"
TEXT_DIR = "full_text_snowball"
os.makedirs(TEXT_DIR, exist_ok=True)
EMAIL = os.getenv("UNPAYWALL_EMAIL")

DIGITAL = {"mobile_app", "web_app", "software_tool", "wearable"}
ND = {"adhd", "autistic", "audhd"}

enr = pd.read_csv(ENR, dtype=str).fillna("")
cand = enr[
    (enr["Screen_Pass"].astype(str).str.upper() == "Y")
    & (enr["Consensus_intervention_type"].isin(DIGITAL))
    & (enr["Consensus_neurotypes"].isin(ND))
].copy()

KEEP = ["DOI", "PMID", "Title", "Year", "Journal", "Abstract",
        "Consensus_intervention_type", "Consensus_neurotypes",
        "Consensus_has_adults", "Consensus_study_type"]
cand = cand[[c for c in KEEP if c in cand.columns]].reset_index(drop=True)


def fid(doi: str, i: int) -> str:
    d = normalize_doi(doi)
    return d.replace("/", "_").replace(":", "_") if d else f"noidx_{i}"


cand["fulltext_id"] = [fid(cand.at[i, "DOI"], i) for i in cand.index]

# resume: merge prior status if present
prior = {}
if os.path.exists(OUT):
    pdf = pd.read_csv(OUT, dtype=str).fillna("")
    prior = {r["fulltext_id"]: r for r in pdf.to_dict("records")}

print(f"{len(cand)} candidates; retrieving OA full text (Europe PMC + Unpaywall)", flush=True)
rows = []
got = 0
for i in cand.index:
    r = cand.loc[i].to_dict()
    fidv = r["fulltext_id"]
    path = os.path.join(TEXT_DIR, f"{fidv}.txt")
    # resume: already retrieved
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        prev = prior.get(fidv, {})
        r["ft_status"] = "retrieved"; r["ft_source"] = prev.get("ft_source", "cached")
        r["ft_chars"] = os.path.getsize(path); rows.append(r); got += 1
        continue
    doi = normalize_doi(r.get("DOI", ""))
    pmid = str(r.get("PMID", "")).strip()
    text, src = fetch_open_full_text(doi, pmid, EMAIL)
    if text:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        r["ft_status"] = "retrieved"; r["ft_source"] = src; r["ft_chars"] = len(text)
        got += 1
    else:
        r["ft_status"] = "no_doi" if not doi else "paywalled"
        r["ft_source"] = ""; r["ft_chars"] = 0
    rows.append(r)
    if (i + 1) % 20 == 0:
        pd.DataFrame(rows).to_csv(OUT, index=False)
        print(f"  [{i+1}/{len(cand)}] retrieved {got}", flush=True)

pd.DataFrame(rows).to_csv(OUT, index=False)
out = pd.DataFrame(rows)
print(f"\nDone. OA full text retrieved: {got}/{len(cand)}")
print("status:", out["ft_status"].value_counts().to_dict())
print("source:", out[out["ft_status"]=="retrieved"]["ft_source"].value_counts().to_dict())
print(f"-> {len(out[out['ft_status']=='paywalled'])} paywalled remain for the OpenAthens pass")
