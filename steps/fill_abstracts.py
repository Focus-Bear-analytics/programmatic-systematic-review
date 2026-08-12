"""Step 2.5: fill missing Abstract cells via DOI lookups.

Runs between dedupe and classify so the classifier sees as many abstracts as
possible.  Skips rows already marked as duplicates (their abstracts are
backfilled from the primary in the dedupe step) and rows without a DOI.

For deeper coverage (paywalled content via OpenAthens), run the standalone CLI
``fill-missing-abstracts-by-doi.py --playwright`` over the input spreadsheet
before kicking off the pipeline.
"""

from __future__ import annotations

import os
from typing import Any

import pandas as pd

from . import prisma
from .abstract_fetcher import fetch_abstract_basic
from .config import active, semantic_scholar_key
from .constants import COL_ABSTRACT, COL_DOI, DUPLICATE_COL, YES
from .io import is_missing_abstract, normalize_doi

# How often (in candidates processed) to checkpoint progress to disk so an
# interrupted run can resume without re-fetching.
CHECKPOINT_EVERY = 10


def _propagate_to_duplicates(df: pd.DataFrame) -> int:
    """After fetching, copy each primary's abstract down to any blank duplicate rows."""
    propagated = 0
    if DUPLICATE_COL not in df.columns:
        return 0

    # Build a map from each duplicate row to its primary by re-grouping on DOI.
    # Primary = first non-duplicate row with that DOI.
    primary_by_doi: dict[str, Any] = {}
    for idx, row in df.iterrows():
        if str(row.get(DUPLICATE_COL, "")).strip().upper() == YES:
            continue
        doi = normalize_doi(row.get(COL_DOI))
        if doi:
            primary_by_doi.setdefault(doi.lower(), idx)

    for idx, row in df.iterrows():
        if str(row.get(DUPLICATE_COL, "")).strip().upper() != YES:
            continue
        if not is_missing_abstract(row.get(COL_ABSTRACT)):
            continue
        doi = normalize_doi(row.get(COL_DOI))
        if not doi:
            continue
        primary_idx = primary_by_doi.get(doi.lower())
        if primary_idx is None:
            continue
        primary_abs = df.at[primary_idx, COL_ABSTRACT]
        if not is_missing_abstract(primary_abs):
            df.at[idx, COL_ABSTRACT] = primary_abs
            propagated += 1
    return propagated


def run(df: pd.DataFrame) -> pd.DataFrame:
    """Fetch abstracts for non-duplicate rows missing them; checkpoint as we go.

    Progress is written to ``ABSTRACTS_FILLED_CSV`` every ``CHECKPOINT_EVERY``
    candidates (and at the end), so an interrupted run resumes from the last
    checkpoint instead of re-fetching everything.  On resume we reload that
    file and only fetch rows that are *still* missing an abstract (which
    includes earlier fetch failures); delete the file to start completely
    fresh.
    """
    cfg = active()
    abstracts_filled_csv = cfg.abstracts_filled_csv
    resuming = os.path.exists(abstracts_filled_csv)
    if resuming:
        df = pd.read_csv(abstracts_filled_csv, dtype=str).fillna("")
        have = int((~df[COL_ABSTRACT].apply(is_missing_abstract)).sum())
        print(
            f"Step 2.5 [{cfg.slug}]: resuming from {abstracts_filled_csv} "
            f"({len(df)} rows, {have} already have abstracts)..."
        )
    else:
        df = df.copy().fillna("")
        print(
            f"Step 2.5 [{cfg.slug}]: filling missing abstracts "
            f"({len(df)} rows in deduped set)..."
        )

    is_dup = (
        df[DUPLICATE_COL].astype(str).str.strip().str.upper() == YES
        if DUPLICATE_COL in df.columns
        else pd.Series(False, index=df.index)
    )
    missing = df[COL_ABSTRACT].apply(is_missing_abstract)
    doi_norm = df[COL_DOI].apply(normalize_doi)
    has_doi = doi_norm.notna()
    target_mask = missing & has_doi & ~is_dup

    skipped_no_doi = int((missing & ~has_doi & ~is_dup).sum())
    skipped_dup = int((missing & is_dup).sum())
    to_fix = df.loc[target_mask].copy()
    print(
        f"  candidates: {len(to_fix)} rows still to fetch "
        f"(skipped {skipped_no_doi} no-DOI, "
        f"{skipped_dup} duplicates — those inherit from primary)."
    )

    api_key = semantic_scholar_key()
    if api_key:
        print("  Semantic Scholar: API key loaded (1 req/s rate).")
    else:
        print("  Semantic Scholar: no API key — using public limits (1 req/s).")

    os.makedirs(cfg.review_dir, exist_ok=True)
    updates = 0
    failures = 0
    by_source: dict[str, int] = {}
    for n, (idx, row) in enumerate(to_fix.iterrows(), start=1):
        doi = normalize_doi(row[COL_DOI])
        if not doi:
            continue
        abstract, source = fetch_abstract_basic(doi, api_key)
        if abstract:
            df.at[idx, COL_ABSTRACT] = abstract
            updates += 1
            by_source[source] = by_source.get(source, 0) + 1
            print(f"  row {idx}: OK ({source}) DOI {doi}")
        else:
            failures += 1
            print(f"  row {idx}: failed — DOI {doi}")
        if n % CHECKPOINT_EVERY == 0:
            df.to_csv(abstracts_filled_csv, index=False)
            print(f"  checkpoint: saved progress after {n}/{len(to_fix)} candidates")

    propagated = _propagate_to_duplicates(df)
    if propagated:
        print(f"  propagated {propagated} fetched abstract(s) to duplicate row(s).")

    os.makedirs(cfg.review_dir, exist_ok=True)
    df.to_csv(abstracts_filled_csv, index=False)
    with_abs = int((~df[COL_ABSTRACT].apply(is_missing_abstract)).sum())
    print(f"  saved {len(df)} rows ({with_abs} have abstracts) to {abstracts_filled_csv}")

    prisma.record_stage(
        "fill_abstracts",
        total=len(df),
        with_abstract=with_abs,
        candidates=len(to_fix),
        fetched=updates,
        failed=failures,
        propagated_to_duplicates=propagated,
        by_source=by_source,
        skipped_no_doi=skipped_no_doi,
        skipped_duplicate=skipped_dup,
    )
    return df
