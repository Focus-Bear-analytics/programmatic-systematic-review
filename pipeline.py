"""Five-step literature-search pipeline.

Usage::

    poetry run python pipeline.py [<config>]

``<config>`` is the slug of a JSON file in ``configs/``. Defaults to ``adults``.
Available out of the box: ``adults`` (original review) and ``children`` (an
under-18 companion review that carries forward under-18 papers from adults
and adds children-specific database exports).

Stages:
  1. combine        — concatenate per-database CSV/Excel exports (and any
                      carry-forward rows from another review) into one table.
  2. dedupe         — mark duplicate rows (DOI, falling back to normalised title).
  3. fill_abstracts — fetch missing Abstract cells by DOI (Semantic Scholar,
                      Crossref, PubMed, landing page).
  4. screen         — Phase 1 coarse gate: TWO raters classify age group +
                      is_empirical on every paper. Papers that fail the coarse
                      criteria (both raters say non-empirical, or both say the
                      required age group is absent) are short-circuited and never
                      reach Phase 2. Recall-safe: only dropped on rater agreement.
  5. classify       — Phase 2 detail: only on papers that PASS the screen, the
                      two raters classify study_type, intervention_type,
                      neurotypes, etc., recording per-rater and consensus columns.
  6. adjudicate     — resolve rater A/B disagreements with the adjudicator
                      (default: Claude Sonnet 4.6 via Bedrock) as a 3rd rater
                      (majority vote), writing Final_<field>.

Drop database exports for each review into the folder named by its config's
``paths.database_csvs_subdir`` (filename stem = source name, e.g. ``pubmed.csv``).
Column names per database are normalised against ``COLUMN_ALIASES`` in
``steps/schema.py``.

Each step caches its output. To force a step to re-run, delete its CSV (or set
``FORCE_COMBINE=1`` for step 1). Stage record counts are written to
``<review_dir>/prisma_counts.json`` for PRISMA reporting.

Required env vars:
  AWS credentials (one of):
    AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY (+ optional AWS_SESSION_TOKEN), or
    AWS_PROFILE referring to a credentials file profile, or
    an attached IAM role (when running on EC2/ECS).
  AWS_REGION                — defaults to the rater's configured region.
Optional:
  SEMANTIC_SCHOLAR_API_KEY  — higher-throughput abstract lookups.
  FORCE_COMBINE             — set to 1 to force step 1 to rebuild from CSVs.
  CLASSIFY_WORKERS          — parallelism for the classify step (default 8).
  CLASSIFY_TEMPERATURE      — sampling temperature (default 0).
"""

from __future__ import annotations

import json
import sys

from steps import adjudicate, classify, combine, dedupe, fill_abstracts, prisma, screen
from steps.config import load_config, set_active


def main(slug: str = "adults") -> None:
    cfg = load_config(slug)
    set_active(cfg)
    print(f"=== Pipeline: {cfg.name} (slug={cfg.slug}) ===")
    print(f"  data dir:   {cfg.review_dir}")
    print(f"  rater A:    {cfg.rater_a.label} ({cfg.rater_a.model_id})")
    print(f"  rater B:    {cfg.rater_b.label} ({cfg.rater_b.model_id})")
    print(f"  adjudicate: {cfg.adjudicator.label} ({cfg.adjudicator.model_id})")
    print()

    combined = combine.run()
    deduped = dedupe.run(combined)
    filled = fill_abstracts.run(deduped)
    screened = screen.run(filled)          # Phase 1: coarse age + is_empirical gate
    enriched = classify.run(screened)      # Phase 2: detail only on papers that pass
    adjudicate.run(enriched)

    print("\nPRISMA stage counts:")
    print(json.dumps(prisma.summary(), indent=2))


if __name__ == "__main__":
    slug = sys.argv[1] if len(sys.argv) > 1 else "adults"
    main(slug)
