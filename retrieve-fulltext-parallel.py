"""Parallel open-access full-text retrieval over a fulltext_to_retrieve.csv.

Same sources as retrieve-fulltext-candidates.py (Europe PMC OA + Unpaywall, plus
the Elsevier API for Elsevier DOIs) but fans DOIs out across a thread pool so a
large candidate list finishes in minutes rather than an hour. Resumable: skips
any candidate whose text file already exists (>1000 bytes). Fetches run in
worker threads; the CSV/ft_got bookkeeping is written from the main thread only.

Usage: poetry run python retrieve-fulltext-parallel.py <fulltext_to_retrieve.csv> [workers]
"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv

load_dotenv(override=True)
import pandas as pd

from steps.full_text import fetch_elsevier_fulltext, fetch_open_full_text
from steps.io import normalize_doi

CSV = sys.argv[1] if len(sys.argv) > 1 else "search-results-from-database/fulltext_to_retrieve.csv"
WORKERS = int(sys.argv[2]) if len(sys.argv) > 2 else 8
TEXT_DIR = "full_text_snowball"
ELS = ("10.1016", "10.1006", "10.1053", "10.1067", "10.1078")
EMAIL = os.getenv("UNPAYWALL_EMAIL")
os.makedirs(TEXT_DIR, exist_ok=True)


def path_for(doi: str, i: int) -> str:
    fid = (doi or f"row{i}").replace("/", "_").replace(":", "_")
    return os.path.join(TEXT_DIR, f"{fid}.txt")


def fetch_one(i: int, doi: str, pmid: str):
    """Worker: returns (i, path, text, source) or (i, path, None, ...) on miss."""
    path = path_for(doi, i)
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return i, path, None, "cached"
    text, src = fetch_open_full_text(doi, pmid, EMAIL)
    if not text and doi and doi.startswith(ELS):
        try:
            text = fetch_elsevier_fulltext(doi)
            src = "elsevier_api" if text else src
        except Exception:
            pass
    return i, path, text, src


def main() -> None:
    df = pd.read_csv(CSV, dtype=str).fillna("")
    df["ft_got"] = df.get("ft_got", "")
    df["ft_source"] = df.get("ft_source", "")

    todo = []
    cached = 0
    for i in df.index:
        doi = normalize_doi(df.at[i, "DOI"])
        if os.path.exists(path_for(doi, i)) and os.path.getsize(path_for(doi, i)) > 1000:
            df.at[i, "ft_got"] = "y"
            cached += 1
            continue
        todo.append((i, doi, str(df.at[i, "PMID"]).strip()))

    print(f"{CSV}: {len(df)} candidates | already have {cached} | fetching {len(todo)} across {WORKERS} workers")
    got = 0
    bysrc: dict[str, int] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(fetch_one, i, doi, pmid) for i, doi, pmid in todo]
        for fut in as_completed(futures):
            i, path, text, src = fut.result()
            if text:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)
                df.at[i, "ft_got"] = "y"
                df.at[i, "ft_source"] = src
                got += 1
                bysrc[src] = bysrc.get(src, 0) + 1
            done += 1
            if done % 50 == 0:
                df.to_csv(CSV, index=False)
                print(f"  [{done}/{len(todo)}] new full texts this run: {got}", flush=True)

    df.to_csv(CSV, index=False)
    total = cached + got
    print(f"\nnew this run: {got} | by source: {bysrc}")
    print(f"TOTAL have: {total}/{len(df)} | still paywalled/missing: {len(df) - total}")


if __name__ == "__main__":
    main()
