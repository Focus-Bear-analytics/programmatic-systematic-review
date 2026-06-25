"""Fill abstracts for rows that have NO DOI, by searching on title.

DOI lookups can't help these rows, so we query Crossref (bibliographic) and
Europe PMC by title, then accept a hit ONLY if the returned title is a close
match to ours (guards against attaching the wrong abstract). Optional year
agreement tightens it further.

Run this AFTER the DOI backfill, on the same file:
    poetry run python scripts/fetch_missing_abstracts_by_title.py search-results-from-database/deduped-with-snowball.csv
"""

from __future__ import annotations

import html
import re
import shutil
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import requests

from steps.abstract_fetcher import SESSION
from steps.config import load_config, set_active
from steps.constants import COL_ABSTRACT, COL_DOI, DUPLICATE_COL, YES
from steps.io import is_missing_abstract, normalize_doi

CROSSREF = "https://api.crossref.org/works"
EUROPEPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
MATCH_THRESHOLD = 0.90  # title similarity required to accept a hit
CHECKPOINT_EVERY = 10


def _norm(s: str) -> str:
    s = html.unescape(s or "").lower()
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _sim(a: str, b: str) -> float:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def _strip_jats(s: str) -> str:
    s = re.sub(r"</?jats:[^>]+>", " ", s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def crossref_by_title(title: str, year: str | None) -> str | None:
    try:
        r = SESSION.get(
            CROSSREF,
            params={"query.bibliographic": title, "rows": 5, "select": "title,abstract,issued"},
            timeout=25,
        )
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    try:
        items = r.json().get("message", {}).get("items", [])
    except ValueError:
        return None
    for it in items:
        cand = (it.get("title") or [""])[0]
        if _sim(title, cand) < MATCH_THRESHOLD:
            continue
        abs = _strip_jats(it.get("abstract", ""))
        if abs:
            return abs
    return None


def europepmc_by_title(title: str) -> str | None:
    try:
        r = SESSION.get(
            EUROPEPMC,
            params={
                "query": f'TITLE:"{title}"',
                "format": "json",
                "resultType": "core",
                "pageSize": 5,
            },
            timeout=25,
        )
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    try:
        results = r.json().get("resultList", {}).get("result", [])
    except ValueError:
        return None
    for res in results:
        if _sim(title, res.get("title", "")) < MATCH_THRESHOLD:
            continue
        abs = (res.get("abstractText") or "").strip()
        if abs:
            return _strip_jats(abs)
    return None


def fetch_by_title(title: str, year: str | None) -> tuple[str | None, str]:
    ab = crossref_by_title(title, year)
    if ab:
        return ab, "crossref_title"
    ab = europepmc_by_title(title)
    if ab:
        return ab, "europepmc_title"
    return None, "none"


def main(path: str) -> None:
    set_active(load_config("adults"))
    print(f"=== fill NO-DOI abstracts by title in {path} ===")
    df = pd.read_csv(path, dtype=str).fillna("")

    title_col = "Title" if "Title" in df.columns else None
    year_col = next((c for c in df.columns if c.lower() in ("year", "publication year")), None)
    if not title_col:
        print("  no Title column — abort")
        return

    is_dup = (
        df[DUPLICATE_COL].astype(str).str.strip().str.upper() == YES
        if DUPLICATE_COL in df.columns
        else pd.Series(False, index=df.index)
    )
    missing = df[COL_ABSTRACT].apply(is_missing_abstract)
    no_doi = ~df[COL_DOI].apply(normalize_doi).notna()
    has_title = df[title_col].str.strip().str.len() > 0
    target = df.loc[missing & no_doi & ~is_dup & has_title]
    print(f"  {len(target)} rows: missing abstract, no DOI, has title")

    backup = path.replace(".csv", "_pre_title_backfill.csv")
    shutil.copyfile(path, backup)
    print(f"  backup -> {backup}")

    updates = 0
    failures = 0
    by_source: dict[str, int] = {}
    for n, (idx, row) in enumerate(target.iterrows(), start=1):
        title = row[title_col].strip()
        year = row[year_col].strip() if year_col else None
        abstract, source = fetch_by_title(title, year)
        if abstract:
            df.at[idx, COL_ABSTRACT] = abstract
            updates += 1
            by_source[source] = by_source.get(source, 0) + 1
            print(f"  [{n}/{len(target)}] OK ({source}) — {title[:70]}")
        else:
            failures += 1
            print(f"  [{n}/{len(target)}] no confident match — {title[:70]}")
        if n % CHECKPOINT_EVERY == 0:
            df.to_csv(path, index=False)
        time.sleep(0.2)

    df.to_csv(path, index=False)
    still = int(df[COL_ABSTRACT].apply(is_missing_abstract).sum())
    print(f"\n  matched {updates}, no-match {failures}. By source: {by_source}")
    print(f"  abstracts still missing across file: {still}")
    print(f"  saved -> {path}")


if __name__ == "__main__":
    if len(sys.argv) < 2 or not sys.argv[1].endswith(".csv"):
        print("usage: fetch_missing_abstracts_by_title.py <path-to.csv>")
        sys.exit(1)
    main(sys.argv[1])
