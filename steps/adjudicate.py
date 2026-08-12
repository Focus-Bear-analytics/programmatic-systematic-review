"""Step 4: adjudicate residual inter-rater disagreements with a 3rd model.

Raters A and B rate every paper in the classify step. Wherever they disagree
on a consensus field, this step asks an independent third rater (the
adjudicator — Claude Sonnet by default, configured per review) and resolves
each field by majority vote of the three — so where the two original raters
already agree, the agreed value stands (2-of-3), and where they split,
the adjudicator breaks the tie. The result is one confident
``Final_<field>`` per paper.

The adjudicator is only called for rows that actually have a disagreement
(~a third of the unique set), so this is cheap. Output is checkpointed to
``adjudicated_csv`` and resumable.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pandas as pd

from . import prisma
from .classify import MAX_WORKERS, classify_with
from .config import active
from .constants import COL_ABSTRACT, COL_TITLE, DUPLICATE_COL, NO, YES
from .io import is_missing_abstract
from .schema import CONSENSUS_FIELDS

# Column flagging whether a row was sent to the 3rd rater.
ADJUDICATED_COL = "Adjudicated"
CHECKPOINT_EVERY = 25


def _nz(v: Any) -> str:
    return str(v).strip().lower()


def _present(v: Any) -> bool:
    s = _nz(v)
    return s != "" and s != "nan"


def _resolve(a: Any, b: Any, adj: Any) -> Any:
    """Majority vote of the three raters; adjudicator decides a genuine 3-way split."""
    av, bv, cv = _nz(a), _nz(b), _nz(adj)
    if av == bv:
        return a
    if cv == av:
        return a
    if cv == bv:
        return b
    return adj  # all three differ — the adjudicator's call


def _final_cols(adj_prefix: str) -> list[str]:
    return (
        [f"Final_{f}" for f in CONSENSUS_FIELDS]
        + [f"{adj_prefix}_{f}" for f in CONSENSUS_FIELDS]
        + [ADJUDICATED_COL]
    )


def run(df: pd.DataFrame) -> pd.DataFrame:
    """Resolve consensus-field disagreements with the adjudicator; write Final_<field>."""
    cfg = active()
    adjudicator = cfg.adjudicator
    a_pref = cfg.rater_a.column_prefix
    b_pref = cfg.rater_b.column_prefix
    adj_pref = adjudicator.column_prefix

    enriched_csv = cfg.enriched_csv
    adjudicated_csv = cfg.adjudicated_csv

    if os.path.exists(adjudicated_csv):
        df = pd.read_csv(adjudicated_csv, dtype=str).fillna("")
        print(f"Step 4: resuming from {adjudicated_csv} ({len(df)} rows)")
    elif os.path.exists(enriched_csv):
        df = pd.read_csv(enriched_csv, dtype=str).fillna("")
        print(f"Step 4: adjudicating from {enriched_csv} ({len(df)} rows)")
    else:
        df = df.copy().fillna("")

    for col in _final_cols(adj_pref):
        if col not in df.columns:
            df[col] = ""
    df = df.astype({col: object for col in _final_cols(adj_pref)})

    # Classify each row into: skip (duplicate / no abstract / unrated),
    # agreement (resolve directly), or needs-adjudicator (disagreement).
    pending: list[Any] = []  # row indices needing the 3rd rater
    agreed = 0
    for idx, row in df.iterrows():
        if str(row.get(DUPLICATE_COL, "")).strip().upper() == YES:
            continue
        if is_missing_abstract(str(row.get(COL_ABSTRACT, "") or "")):
            continue
        # Both original raters must have rated every consensus field.
        a_res = {f: row.get(f"{a_pref}_{f}") for f in CONSENSUS_FIELDS}
        b_res = {f: row.get(f"{b_pref}_{f}") for f in CONSENSUS_FIELDS}
        if not all(_present(a_res[f]) and _present(b_res[f]) for f in CONSENSUS_FIELDS):
            continue
        if str(row.get(ADJUDICATED_COL, "")).strip() != "":
            continue  # already resolved (resume)

        if all(_nz(a_res[f]) == _nz(b_res[f]) for f in CONSENSUS_FIELDS):
            for f in CONSENSUS_FIELDS:
                df.at[idx, f"Final_{f}"] = a_res[f]
            df.at[idx, ADJUDICATED_COL] = NO
            agreed += 1
        else:
            pending.append(idx)

    os.makedirs(cfg.review_dir, exist_ok=True)

    # Human adjudication: don't call an LLM. Persist the agreement pass and leave
    # disagreements pending (Adjudicated="") for the web UI (adjudicate_ui.py) to
    # resolve. This is a no-op-on-disagreements checkpoint that the UI picks up.
    if adjudicator.provider != "bedrock":
        df.to_csv(adjudicated_csv, index=False)
        print(
            f"  {agreed} rows auto-resolved by 2-rater agreement; "
            f"{len(pending)} rows need HUMAN adjudication."
        )
        print(
            f"  → run:  poetry run python adjudicate_ui.py {cfg.slug}\n"
            f"    then open http://localhost:8000 to resolve the {len(pending)} disagreements."
        )
        prisma.record_stage(
            "adjudicate",
            total=len(df),
            agreed=agreed,
            pending_human=len(pending),
            method="human",
        )
        return df

    print(
        f"  {agreed} rows already in full agreement; "
        f"{len(pending)} rows need the adjudicator "
        f"({adjudicator.label}, {MAX_WORKERS} workers)"
    )

    def _judge(idx: Any) -> tuple[Any, dict]:
        title = str(df.at[idx, COL_TITLE] or "")
        abstract = str(df.at[idx, COL_ABSTRACT] or "")
        try:
            return idx, classify_with(adjudicator, title, abstract)
        except Exception as e:  # noqa: BLE001
            print(f"    [{idx}] {adjudicator.label} error: {e}")
            return idx, {}

    done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(_judge, idx) for idx in pending]
        for fut in as_completed(futures):
            idx, adj_res = fut.result()
            if not adj_res:
                continue  # leave pending so a later run retries it
            for f in CONSENSUS_FIELDS:
                a_val = df.at[idx, f"{a_pref}_{f}"]
                b_val = df.at[idx, f"{b_pref}_{f}"]
                adj_val = adj_res.get(f, "")
                df.at[idx, f"{adj_pref}_{f}"] = adj_val
                df.at[idx, f"Final_{f}"] = _resolve(a_val, b_val, adj_val)
            df.at[idx, ADJUDICATED_COL] = YES
            done += 1
            if done % CHECKPOINT_EVERY == 0:
                df.to_csv(adjudicated_csv, index=False)
                print(f"  [{done}/{len(pending)}] checkpoint saved")

    df.to_csv(adjudicated_csv, index=False)
    n_adj = int((df[ADJUDICATED_COL].astype(str).str.upper() == YES).sum())
    n_agree = int((df[ADJUDICATED_COL].astype(str).str.upper() == NO).sum())
    with_final = n_adj + n_agree
    print(
        f"  saved {adjudicated_csv}: {with_final} unique papers have a Final label "
        f"({n_agree} by 2-rater agreement, {n_adj} adjudicated by {adjudicator.label})"
    )
    prisma.record_stage(
        "adjudicate",
        total=len(df),
        final_labelled=with_final,
        agreed=n_agree,
        adjudicated=n_adj,
    )
    return df
