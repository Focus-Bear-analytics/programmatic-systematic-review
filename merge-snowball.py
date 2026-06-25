"""
Merge the database-search corpus with the OpenAlex citation-snowball results into
one deduplicated master file: search-results-from-database/deduped-with-snowball.csv

Dedup is PRISMA-style: by DOI first, then normalised title, tracking provenance
(which origin and which database sources each record came from) and reporting the
duplicate counts removed.

  base    : search-results-from-database/combined.csv   (all 6 database exports)
  snowball: citation-scraping/openalex_scraped_citations.csv
"""

from __future__ import annotations

import re

import pandas as pd

COMBINED_CSV = "search-results-from-database/combined.csv"
# Adult-relevant snowball citations (child-only-sourced citations pruned out by
# screen-reviews-adults.py). Falls back to the full set if the pruned file is absent.
SNOWBALL_CSV = (
    "citation-scraping/openalex_scraped_citations_adults.csv"
    if __import__("os").path.exists("citation-scraping/openalex_scraped_citations_adults.csv")
    else "citation-scraping/openalex_scraped_citations.csv"
)
OUT_CSV = "search-results-from-database/deduped-with-snowball.csv"

STD_COLS = ["Title", "Abstract", "Authors", "Year", "DOI", "URL", "PMID", "Journal"]
OUT_COLS = [
    "origin",            # database_search | snowball | both
    "source_databases",  # e.g. "pubmed; scopus_export..."
    *STD_COLS,
    "cited_by_count",    # snowball: how many reviews cited it
    "cited_by_reviews",  # snowball provenance
]


def _nt(t: object) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(t).lower())).strip()


def _nd(d: object) -> str:
    return str(d).strip().lower().replace("https://doi.org/", "")


def _key(row: dict) -> str:
    return _nd(row.get("DOI", "")) or _nt(row.get("Title", "")) or ""


def _load() -> list[dict]:
    rows: list[dict] = []

    base = pd.read_csv(COMBINED_CSV, dtype=str).fillna("")
    for r in base.to_dict("records"):
        rows.append({
            **{c: r.get(c, "") for c in STD_COLS},
            "origin": "database_search",
            "source_databases": r.get("Source", ""),
            "cited_by_count": "",
            "cited_by_reviews": "",
        })

    snow = pd.read_csv(SNOWBALL_CSV, dtype=str).fillna("")
    for r in snow.to_dict("records"):
        rows.append({
            **{c: r.get(c, "") for c in STD_COLS},
            "origin": "snowball",
            "source_databases": "",
            "cited_by_count": r.get("cited_by_count", ""),
            "cited_by_reviews": r.get("cited_by_reviews", ""),
        })
    return rows


def _merge_into(dst: dict, src: dict) -> None:
    """Fold a duplicate src record into the already-kept dst record."""
    # origin: database_search + snowball -> both
    if src["origin"] != dst["origin"]:
        dst["origin"] = "both"
    # union of database sources
    srcs = {s.strip() for s in (dst["source_databases"], src["source_databases"]) if s.strip()}
    dst["source_databases"] = "; ".join(sorted(srcs))
    # keep the longer abstract / fill any empty standard field
    for c in STD_COLS:
        if len(str(src.get(c, ""))) > len(str(dst.get(c, ""))):
            dst[c] = src[c]
    # keep snowball citation info if present
    if src.get("cited_by_count"):
        dst["cited_by_count"] = src["cited_by_count"]
        dst["cited_by_reviews"] = src["cited_by_reviews"]


def main() -> None:
    rows = _load()
    n_db = sum(r["origin"] == "database_search" for r in rows)
    n_snow = sum(r["origin"] == "snowball" for r in rows)
    print(f"loaded {n_db} database-search rows + {n_snow} snowball rows = {len(rows)} total")

    merged: dict[str, dict] = {}
    dropped = 0
    for r in rows:
        k = _key(r)
        if not k:
            continue
        if k in merged:
            _merge_into(merged[k], r)
            dropped += 1
        else:
            merged[k] = r

    out = pd.DataFrame(merged.values())[OUT_COLS]
    # Stable, useful ordering: both-origin first, then by citation count desc.
    out["_o"] = out["origin"].map({"both": 0, "snowball": 1, "database_search": 2})
    out["_c"] = pd.to_numeric(out["cited_by_count"], errors="coerce").fillna(0)
    out = out.sort_values(["_o", "_c"], ascending=[True, False]).drop(columns=["_o", "_c"])
    out.to_csv(OUT_CSV, index=False)

    counts = out["origin"].value_counts()
    print(f"\nduplicates merged away: {dropped}")
    print(f"unique records: {len(out)}")
    print("  by origin:")
    for o in ("database_search", "snowball", "both"):
        print(f"    {o:16s}: {int(counts.get(o, 0))}")
    print(f"\n✅ wrote {OUT_CSV}")


if __name__ == "__main__":
    main()
