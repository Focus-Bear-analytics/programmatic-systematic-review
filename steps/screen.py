"""Phase 1: coarse screen — age group + is_empirical — run on every paper.

A cheap two-rater pass that decides, per paper, whether it clears the coarse
criteria for this review. Papers that fail are SHORT-CIRCUITED: the expensive
detailed classifier (Phase 2, ``steps.classify``) skips them entirely.

Gate is RECALL-SAFE: a paper is only marked ``Screen_Pass = "N"`` when BOTH
raters agree it fails a criterion, so a single rater's miss can't drop a study.

  - is_empirical fail: both raters say is_empirical == "no"  -> reason "non_empirical"
  - age fail:          both raters say <require_age> == "no"  -> reason "wrong_age"
    (``require_age`` comes from the config's screening.require_age, e.g.
     "has_adults" for the adults review; omit it to disable the age gate.)

Columns written (prefixes from the config's legacy_column_prefixes):
  <A>_has_adults, <A>_has_under_18, <A>_is_empirical   (+ <B>_…)
  Consensus_has_adults, Consensus_has_under_18, Consensus_is_empirical
  Screen_Pass ("Y"/"N"), Screen_Reason ("" | "non_empirical" | "wrong_age")
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pandas as pd

from . import llm, prisma, rules
from .config import RaterConfig, active
from .constants import (
    COL_ABSTRACT,
    COL_TITLE,
    DUPLICATE_COL,
    NO,
    SCREEN_PASS_COL,
    SCREEN_REASON_COL,
    YES,
)
from .io import is_missing_abstract
from .schema import SCREEN_FIELDS, SCREEN_PROMPT, coerce_screen

MAX_WORKERS = int(os.getenv("SCREEN_WORKERS", os.getenv("CLASSIFY_WORKERS", "8")))
CHECKPOINT_EVERY = 50
TEMPERATURE = float(os.getenv("CLASSIFY_TEMPERATURE", "0"))


def _user_prompt(title: str, abstract: str) -> str:
    return f"Title: {title}\n\nAbstract: {abstract}"


def screen_with(rater: RaterConfig, title: str, abstract: str) -> dict:
    raw = llm.invoke_json(
        rater, system_prompt=SCREEN_PROMPT,
        user_prompt=_user_prompt(title, abstract), temperature=TEMPERATURE, max_tokens=400,
    )
    return coerce_screen(raw)


def _consensus_value(a: Any, b: Any) -> Any:
    if a is None or b is None:
        return ""
    return a if str(a).strip().lower() == str(b).strip().lower() else ""


def _require_age(cfg) -> str | None:
    """Which age flag must be possible for a paper to pass (or None to disable)."""
    val = (cfg.raw.get("screening") or {}).get("require_age")
    return val or None


def _gate(a_res: dict, b_res: dict, require_age: str | None) -> tuple[str, str]:
    """Recall-safe pass/fail. Returns (Screen_Pass, Screen_Reason)."""
    def both_no(field: str) -> bool:
        return (
            str(a_res.get(field, "")).strip().lower() == NO.lower() or
            str(a_res.get(field, "")).strip().lower() == "no"
        ) and (
            str(b_res.get(field, "")).strip().lower() == "no"
        )
    def both_yes(field: str) -> bool:
        return (str(a_res.get(field, "")).strip().lower() == "yes"
                and str(b_res.get(field, "")).strip().lower() == "yes")
    if both_no("is_empirical"):
        return NO, "non_empirical"
    if both_yes("is_parent_mediated"):
        return NO, "parent_mediated"
    if require_age and both_no(require_age):
        return NO, "wrong_age"
    return YES, ""


def _screen_columns(cfg) -> list[str]:
    a, b = cfg.rater_a.column_prefix, cfg.rater_b.column_prefix
    cols = [f"{a}_{f}" for f in SCREEN_FIELDS]
    cols += [f"{b}_{f}" for f in SCREEN_FIELDS]
    cols += [f"Consensus_{f}" for f in SCREEN_FIELDS]
    cols += [SCREEN_PASS_COL, SCREEN_REASON_COL]
    return cols


def _screen_row(idx, title, abstract, rater_a, rater_b):
    """Run both raters for one row; never raises. Applies deterministic age rules."""
    a_res, b_res = {}, {}
    try:
        a_res = screen_with(rater_a, title, abstract)
    except Exception as e:  # noqa: BLE001
        print(f"    [{idx}] {rater_a.label} screen error: {e}")
    try:
        b_res = screen_with(rater_b, title, abstract)
    except Exception as e:  # noqa: BLE001
        print(f"    [{idx}] {rater_b.label} screen error: {e}")
    # High-precision age overrides (same rules the classifier uses), screen fields only.
    overrides = {k: v for k, v in rules.apply_rules(title, abstract).items() if k in SCREEN_FIELDS}
    if overrides:
        for res in (a_res, b_res):
            if res:
                res.update(overrides)
    return idx, a_res, b_res


def run(df: pd.DataFrame) -> pd.DataFrame:
    cfg = active()
    a_pref, b_pref = cfg.rater_a.column_prefix, cfg.rater_b.column_prefix
    require_age = _require_age(cfg)
    screened_csv = cfg.screened_csv

    if os.path.exists(screened_csv):
        df = pd.read_csv(screened_csv, dtype=str).fillna("")
        print(f"Phase 1 [screen]: resuming from {screened_csv} ({len(df)} rows)")

    for col in _screen_columns(cfg):
        if col not in df.columns:
            df[col] = pd.NA

    print(f"Phase 1 [screen]: {cfg.rater_a.label} + {cfg.rater_b.label} — age + is_empirical")
    if require_age:
        print(f"  age gate: require_age={require_age} (drop only if both raters say no)")

    # Pending = unique rows with an abstract that haven't been screened yet.
    pending: list[Any] = []
    for idx, row in df.iterrows():
        if str(row.get(DUPLICATE_COL, "")).strip().upper() == YES:
            continue
        if is_missing_abstract(str(row.get(COL_ABSTRACT, "") or "")):
            df.at[idx, SCREEN_PASS_COL] = NO
            df.at[idx, SCREEN_REASON_COL] = "no_abstract"
            continue
        prev = row.get(SCREEN_PASS_COL)
        if pd.notna(prev) and str(prev).strip():
            continue  # already screened
        pending.append(idx)

    print(f"  {len(pending)} rows to screen across {MAX_WORKERS} workers")
    os.makedirs(cfg.review_dir, exist_ok=True)
    for r in (cfg.rater_a, cfg.rater_b):
        llm.warm(r)

    done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [
            pool.submit(
                _screen_row, idx,
                str(df.at[idx, COL_TITLE] or ""), str(df.at[idx, COL_ABSTRACT] or ""),
                cfg.rater_a, cfg.rater_b,
            )
            for idx in pending
        ]
        for fut in as_completed(futures):
            idx, a_res, b_res = fut.result()
            for f in SCREEN_FIELDS:
                df.at[idx, f"{a_pref}_{f}"] = a_res.get(f) if a_res else None
                df.at[idx, f"{b_pref}_{f}"] = b_res.get(f) if b_res else None
                df.at[idx, f"Consensus_{f}"] = _consensus_value(
                    a_res.get(f) if a_res else None, b_res.get(f) if b_res else None
                )
            if a_res and b_res:
                passed, reason = _gate(a_res, b_res, require_age)
            elif a_res or b_res:
                passed, reason = YES, ""  # one rater ok -> recall-safe keep
            else:
                # both raters failed (transient/auth) — leave Screen_Pass unset so
                # a resumed run retries this row instead of treating it as done.
                continue
            df.at[idx, SCREEN_PASS_COL] = passed
            df.at[idx, SCREEN_REASON_COL] = reason
            done += 1
            if done % CHECKPOINT_EVERY == 0:
                df.to_csv(screened_csv, index=False)
                print(f"  [{done}/{len(pending)}] checkpoint saved")

    df.to_csv(screened_csv, index=False)

    passed_n = int((df[SCREEN_PASS_COL].astype(str).str.upper() == YES).sum())
    failed_n = int((df[SCREEN_PASS_COL].astype(str).str.upper() == NO).sum())
    reasons = df.loc[df[SCREEN_PASS_COL].astype(str).str.upper() == NO, SCREEN_REASON_COL]
    print(f"  screen complete: {passed_n} pass -> Phase 2, {failed_n} short-circuited")
    if failed_n:
        print("   reasons: " + ", ".join(f"{k}={v}" for k, v in reasons.value_counts().items()))
    prisma.record_stage(
        "screen", total=len(df), passed=passed_n, short_circuited=failed_n
    )
    return df


if __name__ == "__main__":  # convenience: run just the screen on the deduped/filled csv
    import sys
    from .config import load_config, set_active
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "adults")
    set_active(cfg)
    src = cfg.abstracts_filled_csv if os.path.exists(cfg.abstracts_filled_csv) else cfg.deduped_csv
    run(pd.read_csv(src, dtype=str).fillna(""))
