"""Fill missing abstracts on the canonical adjudicated.csv (or any review's file).

Operates in place on ``cfg.adjudicated_csv`` so it does NOT re-run the LLM
classify/adjudicate steps (which would clobber human decisions). Only rows that
are missing an abstract, have a DOI, and are not duplicates are fetched.

Source order per DOI: Semantic Scholar (keyless) -> Crossref -> PubMed ->
Europe PMC -> Elsevier (institutional IP) -> publisher landing page.

Usage:
    poetry run python scripts/fetch_missing_abstracts.py [slug]   # default: adults
"""

from __future__ import annotations

import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import requests

from steps.abstract_fetcher import (
    SESSION,
    fetch_crossref,
    fetch_elsevier,
    fetch_pubmed,
    fetch_semantic_scholar,
)
from steps.config import load_config, set_active
from steps.constants import COL_ABSTRACT, COL_DOI, DUPLICATE_COL, YES
from steps.io import is_missing_abstract, normalize_doi

CHECKPOINT_EVERY = 50
FAST_WORKERS = 10
EUROPEPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def fetch_europepmc(doi: str) -> str | None:
    """Europe PMC abstract by DOI (broad OA/MED coverage, no key)."""
    try:
        r = SESSION.get(
            EUROPEPMC,
            params={
                "query": f'DOI:"{doi}"',
                "format": "json",
                "resultType": "core",
                "pageSize": 1,
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
    if not results:
        return None
    abs = (results[0].get("abstractText") or "").strip()
    return abs or None


def fetch_fast(doi: str) -> tuple[str | None, str]:
    """No-throttle sources only — safe to call from many threads at once."""
    for fn, label in (
        (fetch_crossref, "crossref"),
        (fetch_europepmc, "europepmc"),
        (fetch_pubmed, "pubmed"),
    ):
        try:
            ab = fn(doi)
        except Exception:
            ab = None
        if ab and ab.strip():
            return ab.strip(), label
    return None, "none"


def fetch_slow(doi: str) -> tuple[str | None, str]:
    """Throttled / institutional sources — run sequentially on the residual."""
    for fn, label in (
        (lambda d: fetch_semantic_scholar(d, None), "semantic_scholar"),
        (fetch_elsevier, "elsevier"),  # entitled by institutional IP
    ):
        try:
            ab = fn(doi)
        except Exception:
            ab = None
        if ab and ab.strip():
            return ab.strip(), label
    return None, "none"


def main(target: str = "adults") -> None:
    # ``target`` is either a config slug (fills that review's adjudicated.csv)
    # or a direct path to a CSV (fills that file in place).
    if target.endswith(".csv"):
        path = target
        set_active(load_config("adults"))
    else:
        cfg = load_config(target)
        set_active(cfg)
        path = cfg.adjudicated_csv
    print(f"=== fill missing abstracts in {path} ===")

    df = pd.read_csv(path, dtype=str).fillna("")

    is_dup = (
        df[DUPLICATE_COL].astype(str).str.strip().str.upper() == YES
        if DUPLICATE_COL in df.columns
        else pd.Series(False, index=df.index)
    )
    missing = df[COL_ABSTRACT].apply(is_missing_abstract)
    doi_norm = df[COL_DOI].apply(normalize_doi)
    has_doi = doi_norm.notna()
    target = df.loc[missing & has_doi & ~is_dup]
    print(
        f"  {int(missing.sum())} missing total | "
        f"{len(target)} fetchable (have DOI, not duplicate) | "
        f"{int((missing & ~has_doi & ~is_dup).sum())} have no DOI (skipped)"
    )

    backup = path.replace(".csv", "_pre_abstract_backfill.csv")
    if not Path(backup).exists():
        shutil.copyfile(path, backup)
        print(f"  backup -> {backup}")

    by_source: dict[str, int] = {}
    tasks = [(idx, normalize_doi(row[COL_DOI])) for idx, row in target.iterrows()]

    # --- Phase 1: parallel, no-throttle sources (Crossref / Europe PMC / PubMed)
    print(f"\n  Phase 1: {len(tasks)} DOIs via fast sources ({FAST_WORKERS} workers)…")
    done = 0
    with ThreadPoolExecutor(max_workers=FAST_WORKERS) as ex:
        futs = {ex.submit(fetch_fast, doi): idx for idx, doi in tasks}
        for fut in as_completed(futs):
            idx = futs[fut]
            done += 1
            try:
                abstract, source = fut.result()
            except Exception:
                abstract, source = None, "none"
            if abstract:
                df.at[idx, COL_ABSTRACT] = abstract
                by_source[source] = by_source.get(source, 0) + 1
            if done % CHECKPOINT_EVERY == 0:
                df.to_csv(path, index=False)
                print(f"    …{done}/{len(tasks)} processed, {sum(by_source.values())} filled")
    df.to_csv(path, index=False)
    print(f"  Phase 1 done: {sum(by_source.values())} filled. By source: {by_source}")

    # --- Phase 2: sequential, throttled S2 + institutional Elsevier on residual
    still = df[COL_ABSTRACT].apply(is_missing_abstract) & df[COL_DOI].apply(normalize_doi).notna() & ~is_dup
    residual = [(idx, normalize_doi(df.at[idx, COL_DOI])) for idx in df.index[still]]
    print(f"\n  Phase 2: {len(residual)} still missing — Semantic Scholar (1 r/s) + Elsevier…")
    for n, (idx, doi) in enumerate(residual, start=1):
        abstract, source = fetch_slow(doi)
        if abstract:
            df.at[idx, COL_ABSTRACT] = abstract
            by_source[source] = by_source.get(source, 0) + 1
        if n % CHECKPOINT_EVERY == 0:
            df.to_csv(path, index=False)
            print(f"    …{n}/{len(residual)} processed, {by_source.get('semantic_scholar', 0)} via S2")

    df.to_csv(path, index=False)
    miss_final = df[COL_ABSTRACT].apply(is_missing_abstract)
    no_doi_left = int((miss_final & ~df[COL_DOI].apply(normalize_doi).notna()).sum())
    print(
        f"\n  TOTAL filled this run: {sum(by_source.values())}. By source: {by_source}\n"
        f"  abstracts still missing across file: {int(miss_final.sum())} "
        f"(no-DOI, needs title search: {no_doi_left})"
    )
    print(f"  saved -> {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "adults")
