"""Run Phase-2 classify (+ the free agreement pass of adjudicate) for the
children review over ``children/enriched.csv`` built by build-children-dataset.py.

Only the child-only papers the adult screen had dropped are sent to Bedrock;
rows that already carry both raters' detail labels are skipped (reused). The
adjudicator is human, so ``adjudicate.run`` only auto-resolves rows where the
two raters already agree and leaves genuine disagreements for adjudicate_ui.py.
Resumable: re-running picks up where a Ctrl-C / token expiry left off.
"""
import os
import sys

sys.path.insert(0, os.getcwd())
import pandas as pd

from steps import adjudicate, classify
from steps.config import load_config, set_active


def main() -> None:
    cfg = load_config("children")
    set_active(cfg)
    if not os.path.exists(cfg.enriched_csv):
        sys.exit(f"missing {cfg.enriched_csv} — run build-children-dataset.py first")
    df = pd.read_csv(cfg.enriched_csv, dtype=str).fillna("")
    print(f"=== children classify: {len(df)} rows (from {cfg.enriched_csv}) ===")
    df = classify.run(df)
    adjudicate.run(df)


if __name__ == "__main__":
    main()
