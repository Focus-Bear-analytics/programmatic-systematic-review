"""Re-screen the snowball seed reviews for ADULT relevance, then prune citations.

The original review screen in scrape-citations.py was topic-only (digital
intervention x autism/ADHD) with NO age criterion, so ~37% of included reviews
were child-only and injected paediatric studies. This pass:

  1. asks Claude Sonnet whether each included review's scope includes adults
     (recall-safe: only "no" for reviews EXCLUSIVELY about under-18s),
  2. drops citations whose citing reviews are ALL confidently child-only,
     using the cited_by_reviews provenance (no re-scrape needed).

A citation is kept unless every review that cited it is a known child-only
review — unmatched/unknown provenance is kept (recall-safe).

Outputs:
  citation-scraping/openalex_systematic_reviews.csv          (+ adult_relevant col)
  citation-scraping/openalex_scraped_citations_adults.csv    (pruned)
  search-results-from-database/database-csvs/openalex_citations.csv  (pruned export)
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.getcwd())
import pandas as pd  # noqa: E402

from steps.config import load_config, set_active  # noqa: E402
from steps import llm  # noqa: E402

REVIEWS_CSV = "citation-scraping/openalex_systematic_reviews.csv"
CITATIONS_CSV = "citation-scraping/openalex_scraped_citations.csv"
ADULTS_CITATIONS_CSV = "citation-scraping/openalex_scraped_citations_adults.csv"
PIPELINE_EXPORT = "search-results-from-database/database-csvs/openalex_citations.csv"
PIPELINE_COLS = ["Title", "Abstract", "Authors", "Year", "DOI", "PMID", "Journal", "URL"]

ADULT_PROMPT = (
    "You decide whether a SYSTEMATIC REVIEW's scope includes ADULTS (people aged 18 or older). "
    "You are given its title and abstract.\n"
    'Answer "yes" if the review includes adults — it covers adults, spans all ages, states no age '
    "restriction, or is age-ambiguous (e.g. 'individuals with autism' with no stated age limit).\n"
    'Answer "no" ONLY if the review is EXCLUSIVELY about children and/or adolescents under 18 '
    "(e.g. 'in children', 'paediatric', 'school-aged', 'adolescents', 'young people') with no "
    "indication adults are included.\n"
    'Be recall-safe: when in doubt, answer "yes". '
    'Return ONLY JSON: {"addresses_adults": true|false, "rationale": "<=15 words"}.'
)


def screen_reviews() -> pd.DataFrame:
    cfg = load_config("adults")
    set_active(cfg)
    rater = cfg.rater_b  # Claude Sonnet 4.6 (the stronger rater)

    rv = pd.read_csv(REVIEWS_CSV, dtype=str).fillna("")
    if "review_screen" in rv.columns:
        mask_inc = rv["review_screen"] == "include"
    else:
        mask_inc = pd.Series(True, index=rv.index)
    for col in ("adult_relevant", "adult_rationale"):
        if col not in rv.columns:
            rv[col] = ""

    todo = [i for i in rv.index[mask_inc] if not str(rv.at[i, "adult_relevant"]).strip()]
    print(f"Screening {len(todo)} included reviews for adult relevance with {rater.label}")

    def work(i):
        title = str(rv.at[i, "Title"] or "")
        abstract = str(rv.at[i, "Abstract"] or "")
        try:
            raw = llm.invoke_json(
                rater, ADULT_PROMPT, f"Title: {title}\n\nAbstract: {abstract}",
                temperature=0.0, max_tokens=120,
            )
            return i, ("yes" if raw.get("addresses_adults") else "no"), str(raw.get("rationale", ""))[:120]
        except Exception as e:  # noqa: BLE001
            return i, "yes", f"screen_error_default_keep: {str(e)[:60]}"  # recall-safe

    done = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        for fut in as_completed([pool.submit(work, i) for i in todo]):
            i, verdict, why = fut.result()
            rv.at[i, "adult_relevant"] = verdict
            rv.at[i, "adult_rationale"] = why
            done += 1
            if done % 50 == 0:
                rv.to_csv(REVIEWS_CSV, index=False)
                print(f"  [{done}/{len(todo)}]")
    rv.to_csv(REVIEWS_CSV, index=False)

    inc = rv[mask_inc]
    n_adult = int((inc["adult_relevant"] == "yes").sum())
    n_child = int((inc["adult_relevant"] == "no").sum())
    print(f"  adult-relevant reviews: {n_adult} | child-only reviews dropped: {n_child}")
    return rv


def prune_citations(rv: pd.DataFrame) -> None:
    # Keys (Title[:70]) of reviews CONFIDENTLY child-only — these match the
    # cited_by_reviews provenance written during scraping.
    child_only = {
        str(t)[:70] for t, a in zip(rv["Title"], rv["adult_relevant"]) if a == "no"
    }

    cit = pd.read_csv(CITATIONS_CSV, dtype=str).fillna("")

    def keep(prov: str) -> bool:
        revs = [p.strip() for p in str(prov).split(" | ") if p.strip()]
        if not revs:
            return True
        # Drop only if EVERY citing review is a known child-only review.
        return not all(r in child_only for r in revs)

    mask = cit["cited_by_reviews"].map(keep)
    kept = cit[mask].reset_index(drop=True)
    dropped = len(cit) - len(kept)
    print(f"\nCitations: {len(cit)} -> {len(kept)} kept, {dropped} dropped (child-only-sourced)")

    kept.to_csv(ADULTS_CITATIONS_CSV, index=False)
    os.makedirs(os.path.dirname(PIPELINE_EXPORT), exist_ok=True)
    kept.reindex(columns=PIPELINE_COLS).to_csv(PIPELINE_EXPORT, index=False)
    print(f"  wrote {ADULTS_CITATIONS_CSV}")
    print(f"  wrote pipeline export {PIPELINE_EXPORT}")


def main() -> None:
    rv = screen_reviews()
    prune_citations(rv)


if __name__ == "__main__":
    main()
