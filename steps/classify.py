"""Step 3: classify each abstract with two raters for inter-rater reliability.

Each row produces three column groups (named via the active config's
``legacy_column_prefixes`` for backward compatibility with the historic
OpenAI/Gemini column names):

  - ``<A>_<field>``: Rater A's classification (default model: Nova Lite via Bedrock).
  - ``<B>_<field>``: Rater B's classification (default model: Llama 3.1 8B via Bedrock).
  - ``Consensus_<field>``: the value if both raters agree, otherwise blank.

``Consensus_Reached`` records ``"Y"`` when raters agree on every field in
``CONSENSUS_FIELDS``, else ``"N"``.

Both models are invoked through ``steps.llm.invoke_json`` (Bedrock Converse
API). Keys for AWS auth come from the standard environment (``AWS_ACCESS_KEY_ID``
/ ``AWS_SECRET_ACCESS_KEY``, ``AWS_PROFILE``, or an instance role).
"""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pandas as pd

# Classification is I/O-bound (two API calls per abstract), so we fan rows out
# across a thread pool instead of classifying strictly one at a time.
MAX_WORKERS = int(os.getenv("CLASSIFY_WORKERS", "8"))
# Write enriched.csv every N completed rows (rather than every row) so the big
# CSV write isn't on the hot path, while keeping the run resumable.
CHECKPOINT_EVERY = 25
# Deterministic decoding: temperature 0 removes sampling noise so the two raters
# converge on clear-cut cases instead of differing by chance.
TEMPERATURE = float(os.getenv("CLASSIFY_TEMPERATURE", "0"))

from . import llm, prisma, rules
from .config import RaterConfig, active
from .constants import (
    COL_ABSTRACT,
    COL_TITLE,
    CONSENSUS_REACHED_COL,
    DUPLICATE_COL,
    NO,
    NON_EMPIRICAL,
    SCREEN_PASS_COL,
    YES,
)
from .io import is_missing_abstract
from .schema import (
    CLASSIFICATION_PROMPT,
    DETAIL_CONSENSUS_FIELDS,
    DETAIL_FIELDS,
    coerce_classification,
)

# Phase 2 stores/judges only the detail fields; age + is_empirical are owned by
# the Phase-1 screen step and must not be re-written or re-checked here.
ALL_FIELDS = DETAIL_FIELDS
CONSENSUS_FIELDS = DETAIL_CONSENSUS_FIELDS


# --- Bedrock-backed rater calls -----------------------------------------


def _user_prompt(title: str, abstract: str) -> str:
    return f"Title: {title}\n\nAbstract: {abstract}"


def classify_with(rater: RaterConfig, title: str, abstract: str) -> dict:
    """Run a single rater on one abstract and snap to the allowed enum values."""
    raw = llm.invoke_json(
        rater,
        system_prompt=CLASSIFICATION_PROMPT,
        user_prompt=_user_prompt(title, abstract),
        temperature=TEMPERATURE,
    )
    return coerce_classification(raw)


# Back-compat shims so any external scripts that import these still work.
# They look up the active config every call so config switching keeps working.

def classify_openai(title: str, abstract: str) -> dict:
    return classify_with(active().rater_a, title, abstract)


def classify_gemini(title: str, abstract: str) -> dict:
    return classify_with(active().rater_b, title, abstract)


def classify_claude(title: str, abstract: str) -> dict:
    """Adjudicator (3rd rater) entry-point. Still named for back-compat."""
    return classify_with(active().adjudicator, title, abstract)


# --- Consensus + column bookkeeping --------------------------------------


def _consensus_value(a: Any, b: Any) -> Any:
    if a is None or b is None:
        return ""
    if str(a).strip().lower() == str(b).strip().lower():
        return a
    return ""


def _consensus_reached(a_res: dict, b_res: dict) -> str:
    if not a_res or not b_res:
        return NO
    for field in CONSENSUS_FIELDS:
        if (
            str(a_res.get(field, "")).strip().lower()
            != str(b_res.get(field, "")).strip().lower()
        ):
            return NO
    return YES


def _classification_columns(cfg) -> list[str]:
    """Column list per the active config's prefixes."""
    a_pref = cfg.rater_a.column_prefix
    b_pref = cfg.rater_b.column_prefix
    cols: list[str] = []
    for f in ALL_FIELDS:
        cols.append(f"{a_pref}_{f}")
    for f in ALL_FIELDS:
        cols.append(f"{b_pref}_{f}")
    for f in ALL_FIELDS:
        cols.append(f"Consensus_{f}")
    cols.append(CONSENSUS_REACHED_COL)
    return cols


def _existing_rater(df: pd.DataFrame, idx: Any, prefix: str) -> dict:
    """Read a rater's already-stored classification for one row back into a dict.

    Returns ``{}`` when that rater has no stored result yet (so a row that only
    has one rater can be detected and re-run for the missing rater only).
    """
    out: dict = {}
    for f in ALL_FIELDS:
        col = f"{prefix}_{f}"
        if col not in df.columns:
            continue
        v = df.at[idx, col]
        if pd.isna(v):
            continue
        s = str(v).strip()
        if s and s.lower() != "nan":
            out[f] = v
    return out


def _classify_row(
    idx: Any,
    title: str,
    abstract: str,
    need_a: bool,
    need_b: bool,
    rater_a: RaterConfig,
    rater_b: RaterConfig,
) -> tuple[Any, dict | None, dict | None]:
    """Run the requested raters for one row in a worker thread; never raises.

    Returns ``None`` for a rater that wasn't requested (caller keeps the stored
    value) and ``{}`` for one that was requested but failed.
    """
    a_res: dict | None = None
    b_res: dict | None = None
    if need_a:
        a_res = {}
        try:
            a_res = classify_with(rater_a, title, abstract)
        except Exception as e:  # noqa: BLE001
            print(f"    [{idx}] {rater_a.label} error: {e}")
    if need_b:
        b_res = {}
        try:
            b_res = classify_with(rater_b, title, abstract)
        except Exception as e:  # noqa: BLE001
            print(f"    [{idx}] {rater_b.label} error: {e}")

    # Apply high-precision deterministic rules as overrides on BOTH raters, so
    # fields with a clear textual signal (age flags, no-mention neurotype) are
    # reproducible and don't depend on rater variance. Only overrides fields a
    # rule decided; everything else is left to the LLM.
    overrides = rules.apply_rules(title, abstract)
    if overrides:
        for res in (a_res, b_res):
            if res:
                res.update(overrides)
    return idx, a_res, b_res


def run(df: pd.DataFrame) -> pd.DataFrame:
    """Classify every row that hasn't been classified yet."""
    cfg = active()
    a_pref = cfg.rater_a.column_prefix
    b_pref = cfg.rater_b.column_prefix
    enriched_csv = cfg.enriched_csv

    if os.path.exists(enriched_csv):
        df = pd.read_csv(enriched_csv)
        print(f"Step 3: resuming from {enriched_csv} ({len(df)} rows)")

    for col in _classification_columns(cfg):
        if col not in df.columns:
            df[col] = pd.NA

    # Only classify unique records: duplicates share a primary, so paying to
    # classify them again is wasted spend. Mark unprocessed duplicates as
    # not-applicable (blank) so they neither count as pending nor get sent to
    # the LLMs. Filter on is_duplicate != "Y" downstream for the unique set.
    skipped_dups = 0
    if DUPLICATE_COL in df.columns:
        dup_unprocessed = (
            df[DUPLICATE_COL].astype(str).str.strip().str.upper() == YES
        ) & df[CONSENSUS_REACHED_COL].isna()
        skipped_dups = int(dup_unprocessed.sum())
        df.loc[dup_unprocessed, CONSENSUS_REACHED_COL] = ""

    print(
        f"Step 3: classifying with {cfg.rater_a.label} + {cfg.rater_b.label} via Bedrock"
    )

    # Per unique row with an abstract, decide which raters still need to run.
    # A row is "done" only once BOTH raters have a stored result, so a row that
    # only got one rater (e.g. an API hit a transient failure) is picked up
    # again and we re-run just the missing rater — no wasted re-spend.
    pending: list[tuple[Any, bool, bool]] = []
    for idx, row in df.iterrows():
        if str(row.get(DUPLICATE_COL, "")).strip().upper() == YES:
            continue
        if is_missing_abstract(str(row.get(COL_ABSTRACT, "") or "")):
            df.at[idx, CONSENSUS_REACHED_COL] = NO
            continue
        # Phase-1 short-circuit: papers that failed the coarse screen (non-empirical
        # or wrong age group) skip detailed classification entirely. Mark the
        # intervention_type as non_empirical so the disposition is visible, and
        # don't spend any LLM calls on them.
        if str(row.get(SCREEN_PASS_COL, "")).strip().upper() == NO:
            if pd.isna(row.get("Consensus_intervention_type")) or not str(
                row.get("Consensus_intervention_type", "") or ""
            ).strip():
                df.at[idx, "Consensus_intervention_type"] = NON_EMPIRICAL
            df.at[idx, CONSENSUS_REACHED_COL] = NO
            continue
        a_have = _existing_rater(df, idx, a_pref)
        b_have = _existing_rater(df, idx, b_pref)
        if a_have and b_have:
            if pd.isna(row.get(CONSENSUS_REACHED_COL)):
                df.at[idx, CONSENSUS_REACHED_COL] = _consensus_reached(a_have, b_have)
            continue
        pending.append((idx, not a_have, not b_have))

    need_a = sum(1 for _, a, _ in pending if a)
    need_b = sum(1 for _, _, b in pending if b)
    print(
        f"  {len(pending)} rows to (re)classify across {MAX_WORKERS} workers "
        f"({need_a} need {cfg.rater_a.label}, {need_b} need {cfg.rater_b.label}; "
        f"{skipped_dups} duplicates skipped)"
    )
    os.makedirs(cfg.review_dir, exist_ok=True)

    # Warm Bedrock clients in the main thread so workers don't race on init.
    for r in (cfg.rater_a, cfg.rater_b):
        llm.warm(r)

    rater_a = cfg.rater_a
    rater_b = cfg.rater_b
    done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [
            pool.submit(
                _classify_row,
                idx,
                str(df.at[idx, COL_TITLE] or ""),
                str(df.at[idx, COL_ABSTRACT] or ""),
                need_a_flag,
                need_b_flag,
                rater_a,
                rater_b,
            )
            for idx, need_a_flag, need_b_flag in pending
        ]
        # All DataFrame writes happen here in the main thread.
        for fut in as_completed(futures):
            idx, a_new, b_new = fut.result()
            # Persist whichever rater we (re)computed this round.
            if a_new is not None:
                for field in ALL_FIELDS:
                    df.at[idx, f"{a_pref}_{field}"] = a_new.get(field) if a_new else None
            if b_new is not None:
                for field in ALL_FIELDS:
                    df.at[idx, f"{b_pref}_{field}"] = b_new.get(field) if b_new else None

            # Merge with whatever each rater had stored, then finalize only when
            # BOTH are present; otherwise leave the row pending for a later run.
            a_full = a_new if a_new is not None else _existing_rater(df, idx, a_pref)
            b_full = b_new if b_new is not None else _existing_rater(df, idx, b_pref)
            if not a_full or not b_full:
                continue
            for field in ALL_FIELDS:
                df.at[idx, f"Consensus_{field}"] = _consensus_value(
                    a_full.get(field), b_full.get(field)
                )
            df.at[idx, CONSENSUS_REACHED_COL] = _consensus_reached(a_full, b_full)
            done += 1
            if done % CHECKPOINT_EVERY == 0:
                df.to_csv(enriched_csv, index=False)
                print(f"  [{done}/{len(pending)}] checkpoint saved")

    df.to_csv(enriched_csv, index=False)
    print(f"  saved enriched data to {enriched_csv} ({done} rows finalized this run)")

    consensus_y = int((df[CONSENSUS_REACHED_COL].astype(str).str.upper() == YES).sum())
    consensus_n = int((df[CONSENSUS_REACHED_COL].astype(str).str.upper() == NO).sum())
    prisma.record_stage(
        "classify",
        total=len(df),
        consensus_reached=consensus_y,
        consensus_not_reached=consensus_n,
    )
    return df
