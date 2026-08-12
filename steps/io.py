"""Low-level CSV/Excel/text helpers shared across pipeline steps."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from .constants import COL_SOURCE
from .schema import COLUMN_ALIASES, STANDARD_COLUMNS

EXCEL_EXTENSIONS = (".xls", ".xlsx", ".xlsm")


def read_csv_any_encoding(path: str) -> pd.DataFrame:
    """Read a CSV trying several common encodings; raise if none decode."""
    last_err: Exception | None = None
    for enc in ("utf-8-sig", "utf-8", "utf-16", "latin-1"):
        try:
            return pd.read_csv(path, encoding=enc, dtype=str)
        except UnicodeDecodeError as e:
            last_err = e
    raise RuntimeError(f"could not decode {path}: {last_err}")


def read_excel(path: str) -> pd.DataFrame:
    """Read the first sheet of an Excel export as strings.

    Some databases (e.g. Web of Science) hand out an HTML table under a
    ``.xls`` name; if the real Excel engines reject the file, fall back to
    parsing it as HTML before giving up.
    """
    try:
        return pd.read_excel(path, dtype=str)
    except ValueError:
        return pd.read_html(path)[0].astype(str)


def read_table(path: str) -> pd.DataFrame:
    """Read a database export, dispatching on extension (CSV vs Excel)."""
    if Path(path).suffix.lower() in EXCEL_EXTENSIONS:
        return read_excel(path)
    return read_csv_any_encoding(path)


def _coalesce(df: pd.DataFrame, columns: list[Any]) -> pd.Series:
    """First non-empty value across `columns`, row-wise; '' where none."""
    result = pd.Series("", index=df.index, dtype=object)
    for col in columns:
        vals = df[col]
        filled = vals.notna() & (vals.astype(str).str.strip() != "")
        take = filled & (result == "")
        result[take] = vals[take].astype(str)
    return result


def normalise_columns(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """Map a DataFrame's columns to the pipeline's standard column names.

    For each standard column, every input column whose lowercase,
    whitespace-trimmed name matches an entry in `COLUMN_ALIASES` is coalesced
    (first non-empty value wins, in column order).  Coalescing — rather than a
    plain rename — means a source providing two candidate columns for the same
    field (e.g. ProQuest's empty ``URL`` plus its populated ``DocumentURL``)
    yields one populated column instead of a name collision.  Missing standard
    columns are filled with empty strings so every step downstream sees a
    uniform schema.
    """
    out = pd.DataFrame(index=df.index)
    for std, aliases in COLUMN_ALIASES.items():
        matches = [
            c for c in df.columns
            if c is not None and str(c).strip().lower() in aliases
        ]
        out[std] = _coalesce(df, matches) if matches else ""
    out[COL_SOURCE] = source
    return out[STANDARD_COLUMNS].fillna("")


def norm_title(t: Any) -> str:
    """Normalise a title for fuzzy duplicate detection (lowercase alphanum + spaces)."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(t).lower())).strip()


def is_missing_abstract(val: Any) -> bool:
    """True if a CSV cell looks like a missing/blank abstract."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return True
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "n/a", "na", ".", "-"):
        return True
    return False


def normalize_doi(raw: Any) -> str | None:
    """Strip a DOI of URL prefixes and trailing punctuation; return None when blank."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).strip()
    if not s or s.lower() in ("nan", "none", "n/a", ""):
        return None
    s = re.sub(r"^https?://(dx\.)?doi\.org/", "", s, flags=re.I).strip()
    return s.rstrip(".").strip() or None
