"""Run open-access (+ Elsevier-API on RMIT wifi) full-text retrieval over the
candidates in fulltext_to_retrieve.csv. Saves text to full_text_snowball/ and
writes back a ft_got / ft_source column. Resumable (skips existing text files).
"""
import os, sys
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv(override=True)
import pandas as pd
from steps.full_text import fetch_open_full_text, fetch_elsevier_fulltext
from steps.io import normalize_doi

# CSV path overridable so the same OA retrieval runs for either review's
# fulltext_to_retrieve.csv (adults default; pass children/… as argv[1]).
CSV = sys.argv[1] if len(sys.argv) > 1 else "search-results-from-database/fulltext_to_retrieve.csv"
TEXT_DIR = "full_text_snowball"
ELS = ("10.1016", "10.1006", "10.1053", "10.1067", "10.1078")
os.makedirs(TEXT_DIR, exist_ok=True)
EMAIL = os.getenv("UNPAYWALL_EMAIL")

df = pd.read_csv(CSV, dtype=str).fillna("")
got = 0; bysrc = {}
df["ft_got"] = df.get("ft_got", ""); df["ft_source"] = df.get("ft_source", "")
for i in df.index:
    doi = normalize_doi(df.at[i, "DOI"]); pmid = str(df.at[i, "PMID"]).strip()
    fid = (doi or f"row{i}").replace("/", "_").replace(":", "_")
    path = os.path.join(TEXT_DIR, f"{fid}.txt")
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        df.at[i, "ft_got"] = "y"; got += 1; continue
    text, src = fetch_open_full_text(doi, pmid, EMAIL)
    if not text and doi and doi.startswith(ELS):
        try:
            text = fetch_elsevier_fulltext(doi); src = "elsevier_api" if text else src
        except Exception:
            pass
    if text:
        open(path, "w", encoding="utf-8").write(text)
        df.at[i, "ft_got"] = "y"; df.at[i, "ft_source"] = src
        got += 1; bysrc[src] = bysrc.get(src, 0) + 1
    if (i + 1) % 20 == 0:
        df.to_csv(CSV, index=False); print(f"  [{i+1}] retrieved {got}", flush=True)
df.to_csv(CSV, index=False)
print(f"\nretrieved {got}/{len(df)} | by source: {bysrc}")
print(f"still need manual/paywalled: {len(df) - got}")
