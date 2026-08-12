"""Step 1: combine per-database CSV/Excel exports into a single normalised table.

Each input file in the configured ``database_csvs_dir`` becomes part of the
combined table, with the filename stem captured as the ``Source`` column.

A review can optionally inherit rows from another review's adjudicated output
via ``inputs.carry_forward`` in its JSON config — used so the children review
re-uses the under-18 papers already harvested for the adults review without
re-running the database searches.
"""

from __future__ import annotations

import glob
import os
from pathlib import Path

import pandas as pd

from . import prisma
from .config import CarryForward, active, load_config
from .io import EXCEL_EXTENSIONS, normalise_columns, read_table
from .schema import COLUMN_ALIASES, STANDARD_COLUMNS

INPUT_EXTENSIONS = (".csv", *EXCEL_EXTENSIONS)


def _read_csv_inputs(database_csvs_dir: str) -> tuple[list[pd.DataFrame], dict[str, int]]:
    """Read every CSV/Excel in the dir, normalising columns."""
    if not os.path.isdir(database_csvs_dir):
        raise FileNotFoundError(f"Drop database exports into {database_csvs_dir}/ first.")
    paths = sorted(
        p
        for p in glob.glob(os.path.join(database_csvs_dir, "*"))
        if Path(p).suffix.lower() in INPUT_EXTENSIONS
    )
    per_source: dict[str, int] = {}
    frames: list[pd.DataFrame] = []
    for p in paths:
        source = Path(p).stem
        try:
            raw = read_table(p)
        except Exception as e:  # noqa: BLE001
            print(f"  ! skipping {p}: {e}")
            continue
        norm = normalise_columns(raw, source)
        mapped_cols = [c for c in COLUMN_ALIASES if (norm[c] != "").any()]
        print(f"  {source}: {len(norm)} rows, mapped {mapped_cols}")
        per_source[source] = len(norm)
        frames.append(norm)
    return frames, per_source


def _read_carry_forward(cf: CarryForward) -> tuple[pd.DataFrame | None, int]:
    """Load rows from another review's adjudicated CSV, optionally row-filtered.

    Returns ``(dataframe_with_only_standard_columns, count)``. We project down
    to ``STANDARD_COLUMNS`` so downstream steps see the same schema regardless
    of source; the carry-forward review's classification columns aren't
    forwarded — the new review will reclassify under its own criteria.
    """
    src_cfg = load_config(cf.from_config)
    src_path = os.path.join(src_cfg.review_dir, cf.csv)
    if not os.path.exists(src_path):
        print(f"  carry-forward source not found: {src_path} (skipping)")
        return None, 0
    src = pd.read_csv(src_path, dtype=str).fillna("")
    before = len(src)
    if cf.filter_column and cf.filter_value is not None:
        mask = src[cf.filter_column].astype(str).str.strip().str.lower() == cf.filter_value.lower()
        src = src[mask]
    if src.empty:
        print(
            f"  carry-forward from {cf.from_config}: 0 rows after filter "
            f"({cf.filter_column}={cf.filter_value!r} of {before})"
        )
        return None, 0
    # Keep only the standard schema columns; coerce missing columns to empty.
    out = pd.DataFrame()
    for col in STANDARD_COLUMNS:
        out[col] = src[col] if col in src.columns else ""
    # Stamp Source so the audit trail shows the row came from carry-forward.
    out["Source"] = cf.source_label
    print(
        f"  carry-forward from {cf.from_config}: {len(out)} rows "
        f"(filter {cf.filter_column}={cf.filter_value!r} of {before})"
    )
    return out, len(out)


def run() -> pd.DataFrame:
    """Combine database exports + optional carry-forward into ``combined.csv``.

    Caches at ``combined.csv`` unless ``FORCE_COMBINE`` is set.
    """
    cfg = active()
    combined_csv = cfg.combined_csv
    review_dir = cfg.review_dir
    database_csvs_dir = cfg.database_csvs_dir

    if os.path.exists(combined_csv) and not os.getenv("FORCE_COMBINE"):
        df = pd.read_csv(combined_csv, dtype=str).fillna("")
        print(
            f"Step 1 [{cfg.slug}]: using cached {combined_csv} ({len(df)} rows). "
            "Set FORCE_COMBINE=1 to rebuild."
        )
        prisma.record_stage("combine", total=len(df), from_cache=1)
        return df

    print(f"Step 1 [{cfg.slug}]: combining database exports from {database_csvs_dir}/")
    frames, per_source = _read_csv_inputs(database_csvs_dir)

    cf_count = 0
    if cfg.carry_forward:
        print(f"  carry-forward source: {cfg.carry_forward.from_config}/{cfg.carry_forward.csv}")
        cf_df, cf_count = _read_carry_forward(cfg.carry_forward)
        if cf_df is not None and not cf_df.empty:
            frames.insert(0, cf_df)
            per_source[cfg.carry_forward.source_label] = len(cf_df)

    if not frames:
        raise FileNotFoundError(
            f"No CSV/Excel exports found in {database_csvs_dir}/ and no carry-forward rows."
        )

    df = pd.concat(frames, ignore_index=True)
    os.makedirs(review_dir, exist_ok=True)
    df.to_csv(combined_csv, index=False)
    print(f"  saved {len(df)} rows to {combined_csv}")
    prisma.record_stage(
        "combine", total=len(df), per_source=per_source, carry_forward=cf_count
    )
    return df
