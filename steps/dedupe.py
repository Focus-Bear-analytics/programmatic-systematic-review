"""Step 2: PRISMA-style duplicate detection.

Rather than dropping duplicate rows outright, we mark them in an
``is_duplicate`` column so the audit trail is preserved.  Counts at each
sub-stage (records identified, duplicates, unique records carried forward) are
written to the PRISMA counts file.

A 'group' is rows sharing a DOI (or, when DOI is missing, a normalised title).
The first row in each group is the primary; subsequent rows are tagged
``is_duplicate = "Y"``.  Within a group, any row missing an abstract gets one
backfilled from the first group-mate that has one (handy when one database
gives a richer record than another).
"""

from __future__ import annotations

import os
from typing import Any

import pandas as pd

from . import prisma
from .config import active
from .constants import (
    COL_ABSTRACT,
    COL_DOI,
    COL_TITLE,
    DUPLICATE_COL,
    YES,
)
from .io import is_missing_abstract, norm_title, normalize_doi


def _dedup_key(
    row: pd.Series, doi_col: str, title_col: str
) -> tuple[str, str] | None:
    """Return a normalised key for duplicate detection. DOI first; title fallback."""
    doi = normalize_doi(row[doi_col])
    if doi:
        return ("doi", doi.lower())
    title = row.get(title_col)
    if isinstance(title, str) and title.strip():
        t = norm_title(title)
        if t:
            return ("title", t)
    return None


def _mark_duplicates(
    df: pd.DataFrame, doi_col: str, abs_col: str, title_col: str
) -> tuple[dict[Any, Any], int, int]:
    """Mark duplicates in DUPLICATE_COL and backfill abstracts within groups.

    Returns ``(duplicate_idx -> primary_idx, duplicates_marked, abstracts_backfilled)``.
    """
    if DUPLICATE_COL not in df.columns:
        df[DUPLICATE_COL] = ""
    df[DUPLICATE_COL] = df[DUPLICATE_COL].astype(object)

    groups: dict[tuple[str, str], list[Any]] = {}
    for idx, row in df.iterrows():
        key = _dedup_key(row, doi_col, title_col)
        if key is None:
            df.at[idx, DUPLICATE_COL] = ""
            continue
        groups.setdefault(key, []).append(idx)

    duplicate_to_primary: dict[Any, Any] = {}
    duplicates_marked = 0
    backfilled = 0
    for indices in groups.values():
        primary_idx = indices[0]
        df.at[primary_idx, DUPLICATE_COL] = ""

        donor_idx: Any = None
        for i in indices:
            if not is_missing_abstract(df.at[i, abs_col]):
                donor_idx = i
                break

        for i in indices[1:]:
            df.at[i, DUPLICATE_COL] = YES
            duplicate_to_primary[i] = primary_idx
            duplicates_marked += 1
            if donor_idx is not None and is_missing_abstract(df.at[i, abs_col]):
                df.at[i, abs_col] = df.at[donor_idx, abs_col]
                backfilled += 1

        if (
            donor_idx is not None
            and donor_idx != primary_idx
            and is_missing_abstract(df.at[primary_idx, abs_col])
        ):
            df.at[primary_idx, abs_col] = df.at[donor_idx, abs_col]
            backfilled += 1

    return duplicate_to_primary, duplicates_marked, backfilled


def run(df: pd.DataFrame) -> pd.DataFrame:
    """Mark duplicates and persist to ``DEDUPED_CSV``.

    Unlike a typical pandas ``drop_duplicates`` step, this preserves duplicate
    rows so PRISMA counts can be reconstructed later.  Filter on
    ``is_duplicate != "Y"`` downstream when you only want unique records.
    """
    cfg = active()
    deduped_csv = cfg.deduped_csv
    if os.path.exists(deduped_csv):
        out = pd.read_csv(deduped_csv, dtype=str).fillna("")
        n_dups = int((out[DUPLICATE_COL].astype(str).str.upper() == YES).sum())
        print(
            f"Step 2 [{cfg.slug}]: using cached {deduped_csv} ({len(out)} rows, "
            f"{n_dups} marked duplicate). Delete it to re-dedupe."
        )
        prisma.record_stage(
            "dedupe",
            identified=len(out),
            duplicates=n_dups,
            unique=len(out) - n_dups,
            from_cache=1,
        )
        return out

    print(f"Step 2 [{cfg.slug}]: dedup-marking {len(df)} rows...")
    df = df.copy().fillna("")

    duplicate_to_primary, dup_count, backfilled = _mark_duplicates(
        df, doi_col=COL_DOI, abs_col=COL_ABSTRACT, title_col=COL_TITLE
    )
    unique_count = len(df) - dup_count

    print(
        f"  marked {dup_count} duplicate row(s); "
        f"backfilled {backfilled} abstract(s) within duplicate groups."
    )
    print(f"  {unique_count} unique records carried forward.")

    os.makedirs(cfg.review_dir, exist_ok=True)
    df.to_csv(deduped_csv, index=False)
    print(f"  saved {len(df)} rows to {deduped_csv}")

    prisma.record_stage(
        "dedupe",
        identified=len(df),
        duplicates=dup_count,
        unique=unique_count,
        abstracts_backfilled_within_groups=backfilled,
    )
    return df
