"""Consolidate the two review arms into ONE canonical dataset:

  * original database review  (search-results-from-database/adjudicated.csv)
      raters = OpenAI + Gemini ; carries existing Final_/Adjudicated
  * snowball review           (search-results-from-database/snowball/enriched.csv)
      raters = Nova + Sonnet ; not yet adjudicated

Output: search-results-from-database/combined/enriched.csv

What it does:
  - normalises the two rater families into common RaterA_<f> / RaterB_<f> columns
    (so a single adjudication pass works across both), keeping Consensus_<f>.
  - adds a `source` column (database_search | snowball | both) + source_databases.
  - records `rater_models` per row for transparency.
  - merges snowball full-text + AuDHD status (ft_status / ft_source / audhd /
    adult_audhd) by DOI.
  - dedupes across arms by DOI / normalised title (original wins on overlap).
  - carries the original arm's existing Final_/Human_/Adjudicated (incl. the 173
    re-queued decision-relevant rows); snowball rows start unadjudicated.

Then adjudicate both arms in one go:
    ADJ_REVIEW_SUBDIR=combined poetry run python adjudicate_ui.py adults
"""
import os, re, sys
sys.path.insert(0, os.getcwd())
import pandas as pd
from steps.schema import CONSENSUS_FIELDS

base = "search-results-from-database/"
ORIG = base + "adjudicated.csv"
SNOW = base + "snowball/enriched.csv"
FT = base + "snowball/fulltext_candidates.csv"
AUDHD = base + "snowball/fulltext_audhd.csv"
OUT_DIR = base + "combined"
OUT = OUT_DIR + "/enriched.csv"
os.makedirs(OUT_DIR, exist_ok=True)

ID_COLS = ["Title", "Abstract", "Authors", "Year", "DOI", "URL", "PMID", "Journal"]


def nt(t): return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(t).lower())).strip()
def nd(d): return str(d).strip().lower().replace("https://doi.org/", "")
def key(r): return nd(r.get("DOI", "")) or nt(r.get("Title", "")) or ""


def detail_fields(df, pref):
    return [c[len(pref) + 1:] for c in df.columns if c.startswith(pref + "_")]


orig = pd.read_csv(ORIG, dtype=str).fillna("")
snow = pd.read_csv(SNOW, dtype=str).fillna("")

# Union of all rater fields across both arms.
FIELDS = sorted(set(detail_fields(orig, "OpenAI")) | set(detail_fields(snow, "Nova"))
                | set(CONSENSUS_FIELDS))

FINAL_CARRY = [c for c in orig.columns if c.startswith(("Final_", "Human_"))]


def norm_row(r, a_pref, b_pref, src_origin, src_dbs, a_model, b_model):
    out = {c: r.get(c, "") for c in ID_COLS}
    out["origin"] = src_origin
    out["source_databases"] = src_dbs
    out["RaterA_model"] = a_model
    out["RaterB_model"] = b_model
    out["cited_by_reviews"] = r.get("cited_by_reviews", "")
    out["is_duplicate"] = r.get("is_duplicate", "")
    out["Screen_Pass"] = r.get("Screen_Pass", "")
    out["Screen_Reason"] = r.get("Screen_Reason", "")
    for f in FIELDS:
        out[f"RaterA_{f}"] = r.get(f"{a_pref}_{f}", "")
        out[f"RaterB_{f}"] = r.get(f"{b_pref}_{f}", "")
        out[f"Consensus_{f}"] = r.get(f"Consensus_{f}", "")
    out["Consensus_Reached"] = r.get("Consensus_Reached", "")
    # adjudication carry-over (original only); snowball blank
    for c in FINAL_CARRY:
        out[c] = r.get(c, "")
    out["Adjudicated"] = r.get("Adjudicated", "")
    return out


rows, seen = [], {}
# original first so it wins on overlap
for r in orig.to_dict("records"):
    k = key(r)
    rec = norm_row(r, "OpenAI", "Gemini", "database_search", r.get("Source", ""),
                   "GPT (OpenAI)", "Gemini")
    rows.append(rec); seen[k] = rec
dup_dropped = 0
for r in snow.to_dict("records"):
    k = key(r)
    if k and k in seen:
        # mark the existing (database) record as found in both arms too
        if seen[k]["origin"] == "database_search":
            seen[k]["origin"] = "both"
        dup_dropped += 1
        continue
    rows.append(norm_row(r, "Nova", "Sonnet", r.get("origin", "snowball"),
                         r.get("source_databases", ""), "Nova 2 Lite", "Claude Sonnet 4.6"))

df = pd.DataFrame(rows)

# Merge snowball full-text + AuDHD status by normalised DOI.
if os.path.exists(FT):
    ft = pd.read_csv(FT, dtype=str).fillna("")
    ftm = {nd(r["DOI"]): r for r in ft.to_dict("records") if str(r.get("DOI", "")).strip()}
    df["ft_status"] = df["DOI"].map(lambda d: ftm.get(nd(d), {}).get("ft_status", ""))
    df["ft_source"] = df["DOI"].map(lambda d: ftm.get(nd(d), {}).get("ft_source", ""))
if os.path.exists(AUDHD):
    au = pd.read_csv(AUDHD, dtype=str).fillna("")
    aum = {nd(r["DOI"]): r for r in au.to_dict("records") if str(r.get("DOI", "")).strip()}
    df["audhd"] = df["DOI"].map(lambda d: aum.get(nd(d), {}).get("audhd", ""))
    df["adult_audhd"] = df["DOI"].map(lambda d: aum.get(nd(d), {}).get("adult_audhd", ""))

df.to_csv(OUT, index=False)
print(f"wrote {OUT}: {len(df)} unique papers ({dup_dropped} cross-arm duplicates merged)")
print("  by source:", df["origin"].value_counts().to_dict())
print("  RaterA/RaterB models:",
      df.groupby(["RaterA_model", "RaterB_model"]).size().to_dict())
if "ft_status" in df:
    print("  full text retrieved:", int((df["ft_status"] == "retrieved").sum()))
if "audhd" in df:
    print("  adult_audhd=yes:", int((df["adult_audhd"] == "yes").sum()))
