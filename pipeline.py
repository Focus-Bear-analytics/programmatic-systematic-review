"""
Three-step literature-search pipeline:

  1. combine CSVs from multiple databases (PubMed, ProQuest, etc.) into one
  2. remove duplicates (by DOI, falling back to a normalised title)
  3. classify each abstract with OpenAI and Gemini, writing per-model
     and consensus columns

Drop each database export into search-results-from-database/database-csvs/
(filename = source name, e.g. pubmed.csv, proquest.csv). Column names per
database are normalised against COLUMN_ALIASES below.

Each step caches its output. To force a step to re-run, delete its CSV
(or set FORCE_COMBINE=1 for step 1).

Required env vars: OPENAI_KEY, GEMINI_API_KEY.
"""

from __future__ import annotations

import glob
import json
import os
import re
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from google import genai
from google.genai import types
from openai import OpenAI

load_dotenv()

# --- Config ---
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

DATA_DIR = "search-results-from-database"
DATABASE_CSVS_DIR = os.path.join(DATA_DIR, "database-csvs")
COMBINED_CSV = os.path.join(DATA_DIR, "combined.csv")
DEDUPED_CSV = os.path.join(DATA_DIR, "deduped.csv")
ENRICHED_CSV = os.path.join(DATA_DIR, "enriched.csv")

# Standard column → accepted aliases (matched case-insensitively, whitespace-trimmed).
# Add new database column names here as you encounter them.
COLUMN_ALIASES: dict[str, list[str]] = {
    "Title": [
        "title", "article title", "articletitle", "ti",
        "document title", "primary title",
    ],
    "Abstract": ["abstract", "ab", "abstract note", "summary"],
    "Authors": [
        "authors", "author", "au", "author full names",
        "byline", "creator", "creators",
    ],
    "Year": [
        "year", "publication year", "py", "pub year",
        "publish year", "pubyear", "date",
    ],
    "DOI": ["doi", "digital object identifier"],
    "URL": ["url", "link", "permalink", "source url", "document url"],
    "PMID": ["pmid", "pubmed id"],
    "Journal": [
        "journal", "journal/book", "source title", "publication title",
        "publication", "source", "journal title",
    ],
}
STANDARD_COLUMNS = ["Source", *COLUMN_ALIASES.keys()]

# --- Classification schema ---
ALLOWED = {
    "age_group": [
        "children", "adolescents", "young_adults", "middle_age",
        "elderly", "mixed", "unspecified",
    ],
    "study_type": [
        "empirical_with_results", "commentary", "review", "protocol",
        "proposal", "case_study", "qualitative_only_study", "unspecified",
    ],
    "intervention_type": [
        "mobile_app", "web_app", "software_tool", "telecoaching",
        "telecounselling", "wearable", "non_software_based", "unspecified",
    ],
    "neurotypes": [
        "adhd", "autistic", "audhd", "neither_adhd_nor_autistic", "unspecified",
    ],
    "control_type": [
        "no_control_group", "rct", "non_randomised_control", "unspecified",
    ],
}

ALL_FIELDS = [
    "age_group",
    "study_type",
    "intervention_type",
    "intervention_details",
    "neurotypes",
    "control_type",
    "study_duration_days",
    "outcomes_measured",
]
CONSENSUS_FIELDS = ["age_group", "study_type", "intervention_type", "neurotypes"]

CLASSIFICATION_PROMPT = f"""You analyse a research abstract and return a JSON object with these fields:

- age_group: one of {ALLOWED['age_group']}. Definitions: young_adults=18-30, middle_age=30-60, elderly=60+. Use "mixed" if the abstract spans multiple groups, "unspecified" if not stated.
- study_type: one of {ALLOWED['study_type']}.
- intervention_type: one of {ALLOWED['intervention_type']}. Use "non_software_based" when the intervention has no digital component.
- intervention_details: short sentence describing the intervention (free text, max ~25 words).
- neurotypes: one of {ALLOWED['neurotypes']}. audhd = both ADHD and autistic.
- control_type: one of {ALLOWED['control_type']}.
- study_duration_days: integer number of days, or null if not stated. Convert weeks/months if needed.
- outcomes_measured: comma-separated outcome measures or scales used (e.g. "ASRS, AAQoL"), or empty string.

Return ONLY a JSON object with exactly those keys. Use the listed enum values verbatim. If you cannot determine a value, use "unspecified" (or null/empty as noted)."""


# --- Step 1: combine -------------------------------------------------------


def _read_csv_any_encoding(path: str) -> pd.DataFrame:
    last_err: Exception | None = None
    for enc in ("utf-8-sig", "utf-8", "utf-16", "latin-1"):
        try:
            return pd.read_csv(path, encoding=enc, dtype=str)
        except UnicodeDecodeError as e:
            last_err = e
    raise RuntimeError(f"could not decode {path}: {last_err}")


def _normalise_columns(df: pd.DataFrame, source: str) -> pd.DataFrame:
    rename_map: dict[str, str] = {}
    for std, aliases in COLUMN_ALIASES.items():
        for col in df.columns:
            if col is None or col in rename_map:
                continue
            if str(col).strip().lower() in aliases:
                rename_map[col] = std
                break
    df = df.rename(columns=rename_map)
    for std in COLUMN_ALIASES:
        if std not in df.columns:
            df[std] = ""
    df["Source"] = source
    return df[STANDARD_COLUMNS].fillna("")


def step1_combine() -> pd.DataFrame:
    if os.path.exists(COMBINED_CSV) and not os.getenv("FORCE_COMBINE"):
        df = pd.read_csv(COMBINED_CSV, dtype=str).fillna("")
        print(
            f"Step 1: using cached {COMBINED_CSV} ({len(df)} rows). "
            "Set FORCE_COMBINE=1 to rebuild."
        )
        return df

    print(f"Step 1: combining database CSVs from {DATABASE_CSVS_DIR}/")
    if not os.path.isdir(DATABASE_CSVS_DIR):
        raise FileNotFoundError(
            f"Drop database export CSVs into {DATABASE_CSVS_DIR}/ first."
        )
    paths = sorted(glob.glob(os.path.join(DATABASE_CSVS_DIR, "*.csv")))
    if not paths:
        raise FileNotFoundError(f"No CSVs found in {DATABASE_CSVS_DIR}/")

    frames: list[pd.DataFrame] = []
    for p in paths:
        source = Path(p).stem
        try:
            raw = _read_csv_any_encoding(p)
        except Exception as e:
            print(f"  ! skipping {p}: {e}")
            continue
        norm = _normalise_columns(raw, source)
        mapped_cols = [c for c in COLUMN_ALIASES if (norm[c] != "").any()]
        print(f"  {source}: {len(norm)} rows, mapped {mapped_cols}")
        frames.append(norm)

    df = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=STANDARD_COLUMNS)
    )
    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_csv(COMBINED_CSV, index=False)
    print(f"  saved {len(df)} rows to {COMBINED_CSV}")
    return df


# --- Step 2: dedup ---------------------------------------------------------


def _norm_title(t: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(t).lower())).strip()


def step2_deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    if os.path.exists(DEDUPED_CSV):
        out = pd.read_csv(DEDUPED_CSV)
        print(
            f"Step 2: using cached {DEDUPED_CSV} ({len(out)} rows). "
            "Delete it to re-dedup."
        )
        return out

    print(f"Step 2: deduplicating {len(df)} rows...")
    df = df.copy()
    df["Abstract"] = df["Abstract"].fillna("").astype(str)
    df = df[df["Abstract"].str.strip() != ""]
    df["_doi"] = df.get("DOI", "").fillna("").astype(str).str.strip().str.lower()
    df["_title"] = df["Title"].fillna("").map(_norm_title)

    seen_doi: set[str] = set()
    seen_title: set[str] = set()
    keep_idx = []
    for idx, row in df.iterrows():
        doi, title = row["_doi"], row["_title"]
        if doi:
            if doi in seen_doi:
                continue
            seen_doi.add(doi)
        elif title:
            if title in seen_title:
                continue
            seen_title.add(title)
        else:
            continue
        keep_idx.append(idx)

    out = df.loc[keep_idx].drop(columns=["_doi", "_title"]).reset_index(drop=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    out.to_csv(DEDUPED_CSV, index=False)
    print(f"  {len(out)} unique rows saved to {DEDUPED_CSV}")
    return out


# --- Step 3: classify ------------------------------------------------------

_openai_client: OpenAI | None = None
_gemini_client: genai.Client | None = None


def _openai() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        key = os.getenv("OPENAI_KEY") or os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_KEY is not set")
        _openai_client = OpenAI(api_key=key)
    return _openai_client


def _gemini() -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        _gemini_client = genai.Client(api_key=key)
    return _gemini_client


def _user_prompt(title: str, abstract: str) -> str:
    return f"Title: {title}\n\nAbstract: {abstract}"


def _coerce(result: dict) -> dict:
    out = {f: result.get(f) for f in ALL_FIELDS}
    for f, allowed in ALLOWED.items():
        v = out.get(f)
        if v is None:
            out[f] = "unspecified"
            continue
        v_norm = str(v).strip().lower().replace(" ", "_").replace("-", "_")
        out[f] = v_norm if v_norm in allowed else "unspecified"
    if out.get("intervention_details") is None:
        out["intervention_details"] = ""
    if out.get("outcomes_measured") is None:
        out["outcomes_measured"] = ""
    dur = out.get("study_duration_days")
    if isinstance(dur, str):
        try:
            out["study_duration_days"] = int(dur)
        except (ValueError, TypeError):
            out["study_duration_days"] = None
    return out


def classify_openai(title: str, abstract: str) -> dict:
    response = _openai().chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": CLASSIFICATION_PROMPT},
            {"role": "user", "content": _user_prompt(title, abstract)},
        ],
        response_format={"type": "json_object"},
    )
    return _coerce(json.loads(response.choices[0].message.content))


def classify_gemini(title: str, abstract: str) -> dict:
    response = _gemini().models.generate_content(
        model=GEMINI_MODEL,
        contents=f"{CLASSIFICATION_PROMPT}\n\n{_user_prompt(title, abstract)}",
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return _coerce(json.loads(response.text))


def _consensus_value(a: Any, b: Any) -> Any:
    if a is None or b is None:
        return ""
    if str(a).strip().lower() == str(b).strip().lower():
        return a
    return ""


def _consensus_reached(openai_res: dict, gemini_res: dict) -> str:
    if not openai_res or not gemini_res:
        return "N"
    for f in CONSENSUS_FIELDS:
        if (
            str(openai_res.get(f, "")).strip().lower()
            != str(gemini_res.get(f, "")).strip().lower()
        ):
            return "N"
    return "Y"


def _classification_columns() -> list[str]:
    cols = []
    for f in ALL_FIELDS:
        cols.append(f"OpenAI_{f}")
    for f in ALL_FIELDS:
        cols.append(f"Gemini_{f}")
    for f in ALL_FIELDS:
        cols.append(f"Consensus_{f}")
    cols.append("Consensus_Reached")
    return cols


def step3_classify(df: pd.DataFrame) -> pd.DataFrame:
    if os.path.exists(ENRICHED_CSV):
        df = pd.read_csv(ENRICHED_CSV)
        print(f"Step 3: resuming from {ENRICHED_CSV} ({len(df)} rows)")

    for col in _classification_columns():
        if col not in df.columns:
            df[col] = pd.NA

    print(f"Step 3: classifying with {OPENAI_MODEL} + {GEMINI_MODEL}")
    pending = df["Consensus_Reached"].isna().sum()
    print(f"  {pending} rows pending")

    for idx, row in df.iterrows():
        if pd.notna(row.get("Consensus_Reached")):
            continue
        title = str(row.get("Title", "") or "")
        abstract = str(row.get("Abstract", "") or "")
        if not abstract.strip():
            df.at[idx, "Consensus_Reached"] = "N"
            continue

        print(f"  [{idx + 1}/{len(df)}] {title[:80]}")
        openai_res: dict = {}
        gemini_res: dict = {}
        try:
            openai_res = classify_openai(title, abstract)
        except Exception as e:
            print(f"    OpenAI error: {e}")
        try:
            gemini_res = classify_gemini(title, abstract)
        except Exception as e:
            print(f"    Gemini error: {e}")

        for f in ALL_FIELDS:
            df.at[idx, f"OpenAI_{f}"] = openai_res.get(f) if openai_res else None
            df.at[idx, f"Gemini_{f}"] = gemini_res.get(f) if gemini_res else None
            df.at[idx, f"Consensus_{f}"] = _consensus_value(
                openai_res.get(f) if openai_res else None,
                gemini_res.get(f) if gemini_res else None,
            )
        df.at[idx, "Consensus_Reached"] = _consensus_reached(openai_res, gemini_res)
        df.to_csv(ENRICHED_CSV, index=False)

    df.to_csv(ENRICHED_CSV, index=False)
    print(f"  saved enriched data to {ENRICHED_CSV}")
    return df


# --- Entry point -----------------------------------------------------------


def main() -> None:
    combined = step1_combine()
    deduped = step2_deduplicate(combined)
    step3_classify(deduped)


if __name__ == "__main__":
    main()
