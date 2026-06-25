"""
Citation scraping (backward snowballing) for systematic reviews on digital
interventions for autism and ADHD.

Two steps, each cached:

  1. find systematic reviews (relevance search, filtered to review-type works)
     -> citation-scraping/<backend>_systematic_reviews.csv
  2. for every review, fetch its reference list (the papers it cites), dedupe
     across reviews, and record which review(s) cited each paper
     -> citation-scraping/<backend>_scraped_citations.csv

The scraped citations are also written to
search-results-from-database/database-csvs/<backend>_citations.csv so they flow
straight into pipeline.py (combine -> dedupe -> classify) as another source.

Backends (set CITATION_BACKEND):
  - "openalex"        (default) free, no key, generous limits
  - "semantic_scholar"          needs SEMANTIC_SCHOLAR_API_KEY for a usable rate
                                limit (the keyless pool is heavily throttled)

No year restriction, no LLM filtering. Step 2 saves after every review and is
resumable (tracks processed review ids), so a long run is crash-safe.

Env vars:
  CITATION_BACKEND       openalex | semantic_scholar   (default openalex)
  OPENALEX_MAILTO        contact email for the OpenAlex polite pool
  SEMANTIC_SCHOLAR_API_KEY
  SCRAPE_REVIEW_LIMIT    cap reviews processed in step 2 this run (testing)
  MAX_REVIEWS_PER_QUERY  cap search hits considered per query (default 1000)
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

# --- Config ---------------------------------------------------------------

BACKEND = os.getenv("CITATION_BACKEND", "openalex").lower()

MAX_REVIEWS_PER_QUERY = int(os.getenv("MAX_REVIEWS_PER_QUERY", "1000"))
MAX_RETRIES = 12

# Optional LLM relevance gate on the seed reviews (between find and scrape). When
# on, only reviews judged "include" get their citations scraped. This is a
# precision/cost optimisation, not a correctness requirement — the real screen is
# pipeline.py's per-citation classifier. Set SCREEN_REVIEWS=0 to skip.
SCREEN_REVIEWS = os.getenv("SCREEN_REVIEWS", "1") != "0"
REVIEW_SCREEN_MODEL = os.getenv("REVIEW_SCREEN_MODEL", os.getenv("OPENAI_MODEL", "gpt-5.4-mini"))

DATA_DIR = "citation-scraping"
DATABASE_CSVS_DIR = os.path.join("search-results-from-database", "database-csvs")

# Per-backend output paths so the two backends never clobber each other.
REVIEWS_CSV = os.path.join(DATA_DIR, f"{BACKEND}_systematic_reviews.csv")
CITATIONS_CSV = os.path.join(DATA_DIR, f"{BACKEND}_scraped_citations.csv")
PROCESSED_REVIEWS_FILE = os.path.join(DATA_DIR, f"{BACKEND}_processed_review_ids.txt")
PIPELINE_EXPORT = os.path.join(DATABASE_CSVS_DIR, f"{BACKEND}_citations.csv")
SOURCE_LABEL = f"{BACKEND}_citation_scrape"

PIPELINE_COLS = ["Title", "Abstract", "Authors", "Year", "DOI", "PMID", "Journal", "URL"]

# Standard flattened paper row used everywhere downstream.
ROW_KEYS = ["paperId", *PIPELINE_COLS]


# --- HTTP -----------------------------------------------------------------


def _request(url: str, params: dict[str, Any], headers: dict[str, str]) -> dict | None:
    """GET with exponential backoff on 403/429/5xx. Returns parsed JSON or None."""
    for attempt in range(MAX_RETRIES):
        resp = requests.get(url, headers=headers, params=params, timeout=60)
        if resp.status_code == 200:
            return resp.json()
        # 403 is returned (alongside 429) by throttled pools under load, so treat
        # it as retryable rather than a hard auth failure.
        if resp.status_code in (403, 429, 500, 502, 503, 504):
            wait = min(2 ** attempt, 60)
            print(f"   ⚠️  {resp.status_code}; retry in {wait}s "
                  f"(attempt {attempt + 1}/{MAX_RETRIES})")
            time.sleep(wait)
            continue
        print(f"   ❌ {resp.status_code} on {url}: {resp.text[:200]}")
        return None
    print(f"   ❌ gave up on {url} after {MAX_RETRIES} attempts")
    return None


def _empty_row() -> dict:
    return {k: "" for k in ROW_KEYS}


# ==========================================================================
# OpenAlex backend
# ==========================================================================

OPENALEX_BASE = "https://api.openalex.org"
OPENALEX_MAILTO = (
    os.getenv("OPENALEX_MAILTO")
    or os.getenv("UNPAYWALL_EMAIL")
    or "s3255727@student.rmit.edu.au"
)
OPENALEX_PAUSE_S = 0.2  # polite pool allows ~10 req/s

# Each query is ANDed (with stemming) against title+abstract, so every term must
# appear -> a precise seed of reviews that are genuinely about a digital
# intervention for autism/ADHD, not full-text-incidental mentions. Pair a digital
# term with a neurotype term in each query.
OPENALEX_REVIEW_QUERIES = [
    "digital intervention autism",
    "digital intervention ADHD",
    "mobile app autism intervention",
    "mobile app ADHD intervention",
    "technology intervention autism",
    "technology intervention ADHD",
    "online intervention autism ADHD",
    "smartphone intervention autism ADHD",
    "telehealth autism ADHD intervention",
    "serious game autism ADHD",
    "wearable autism ADHD",
    "computerised cognitive training ADHD autism",
]

OA_REVIEW_SELECT = (
    "id,title,abstract_inverted_index,publication_year,doi,authorships,"
    "primary_location,ids,referenced_works_count"
)
OA_REF_SELECT = (
    "id,title,abstract_inverted_index,publication_year,doi,authorships,"
    "primary_location,ids"
)


def _oa_get(path: str, params: dict[str, Any]) -> dict | None:
    return _request(
        f"{OPENALEX_BASE}/{path.lstrip('/')}",
        {**params, "mailto": OPENALEX_MAILTO},
        {"Accept": "application/json"},
    )


def _oa_short_id(openalex_id: str) -> str:
    """https://openalex.org/W123 -> W123"""
    return (openalex_id or "").rsplit("/", 1)[-1]


def _oa_abstract(inverted: dict | None) -> str:
    if not inverted:
        return ""
    positions: list[tuple[int, str]] = []
    for word, idxs in inverted.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)


def _oa_row(w: dict) -> dict:
    ids = w.get("ids") or {}
    pmid = (ids.get("pmid") or "").rsplit("/", 1)[-1]
    doi = (w.get("doi") or "").replace("https://doi.org/", "")
    venue = ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
    authors = ", ".join(
        (a.get("author") or {}).get("display_name", "")
        for a in (w.get("authorships") or [])
    )
    return {
        "paperId": _oa_short_id(w.get("id", "")),
        "Title": w.get("title") or "",
        "Abstract": _oa_abstract(w.get("abstract_inverted_index")),
        "Authors": authors,
        "Year": w.get("publication_year") or "",
        "DOI": doi,
        "PMID": pmid,
        "Journal": venue,
        "URL": w.get("id") or "",
    }


def oa_find_reviews() -> list[dict]:
    by_id: dict[str, dict] = {}
    for query in OPENALEX_REVIEW_QUERIES:
        print(f"  🔎 {query}")
        cursor = "*"
        kept = 0
        while cursor and kept < MAX_REVIEWS_PER_QUERY:
            data = _oa_get(
                "works",
                {
                    "filter": f"type:review,title_and_abstract.search:{query}",
                    "select": OA_REVIEW_SELECT,
                    "per-page": 200,
                    "cursor": cursor,
                },
            )
            if not data:
                break
            results = data.get("results", []) or []
            for w in results:
                sid = _oa_short_id(w.get("id", ""))
                if not sid or sid in by_id:
                    continue
                row = _oa_row(w)
                row["referenceCount"] = w.get("referenced_works_count") or 0
                row["found_via_query"] = query
                by_id[sid] = row
                kept += 1
            cursor = (data.get("meta") or {}).get("next_cursor")
            if kept >= MAX_REVIEWS_PER_QUERY or not results:
                break
            time.sleep(OPENALEX_PAUSE_S)
        print(f"     kept {kept} reviews from this query")
    return list(by_id.values())


def oa_fetch_references(review: dict) -> list[dict]:
    sid = review["paperId"]
    work = _oa_get(f"works/{sid}", {"select": "referenced_works"})
    if not work:
        return []
    ref_ids = [_oa_short_id(r) for r in (work.get("referenced_works") or [])]
    rows: list[dict] = []
    for i in range(0, len(ref_ids), 50):  # OpenAlex OR-filter allows up to 50 ids
        chunk = ref_ids[i : i + 50]
        data = _oa_get(
            "works",
            {
                "filter": f"openalex_id:{'|'.join(chunk)}",
                "select": OA_REF_SELECT,
                "per-page": 50,
            },
        )
        if data:
            rows.extend(_oa_row(w) for w in (data.get("results", []) or []))
        time.sleep(OPENALEX_PAUSE_S)
    return rows


# ==========================================================================
# Semantic Scholar backend
# ==========================================================================

S2_BASE = "https://api.semanticscholar.org/graph/v1"
S2_KEY = None  # DISABLED 2026-06: dead key (403). os.getenv("SEMANTIC_SCHOLAR_API_KEY")
S2_PAUSE_S = 3.0  # gentle on the heavily-throttled keyless pool
S2_REFERENCES_PAGE_SIZE = 1000

S2_REVIEW_QUERIES = [
    "(digital | app | technology | online | mobile | smartphone | e-health | software) (autism | autistic | ADHD | neurodevelopmental) intervention",
    "(digital | app | technology | online | telehealth) (autism | ADHD) (children | adolescents | adults)",
    "(mobile health | mHealth | ehealth | web-based) (autism | ADHD | neurodevelopmental)",
]
S2_REVIEW_PUB_TYPES_PARAM = "Review,MetaAnalysis"
S2_REVIEW_FIELDS = "title,abstract,authors,year,externalIds,url,venue,publicationTypes,referenceCount"
S2_REF_FIELDS = "title,abstract,authors,year,externalIds,url,venue"


def _s2_get(path: str, params: dict[str, Any]) -> dict | None:
    headers = {"Accept": "application/json"}
    if S2_KEY:
        headers["x-api-key"] = S2_KEY
    return _request(f"{S2_BASE}/{path.lstrip('/')}", params, headers)


def _s2_row(p: dict) -> dict:
    ext = p.get("externalIds") or {}
    authors = ", ".join(a.get("name", "") for a in (p.get("authors") or []))
    return {
        "paperId": p.get("paperId", ""),
        "Title": p.get("title") or "",
        "Abstract": p.get("abstract") or "",
        "Authors": authors,
        "Year": p.get("year") or "",
        "DOI": ext.get("DOI", ""),
        "PMID": ext.get("PubMed", ""),
        "Journal": p.get("venue") or "",
        "URL": p.get("url") or "",
    }


def s2_find_reviews() -> list[dict]:
    by_id: dict[str, dict] = {}
    for query in S2_REVIEW_QUERIES:
        print(f"  🔎 {query}")
        token: str | None = None
        kept = 0
        seen = 0
        while seen < MAX_REVIEWS_PER_QUERY:
            params = {
                "query": query,
                "publicationTypes": S2_REVIEW_PUB_TYPES_PARAM,
                "fields": S2_REVIEW_FIELDS,
            }
            if token:
                params["token"] = token
            data = _s2_get("paper/search/bulk", params)
            if not data:
                break
            papers = data.get("data", []) or []
            if not papers:
                break
            for p in papers:
                seen += 1
                pid = p.get("paperId")
                if not pid or pid in by_id:
                    continue
                row = _s2_row(p)
                row["referenceCount"] = p.get("referenceCount") or 0
                row["found_via_query"] = query
                by_id[pid] = row
                kept += 1
            token = data.get("token")
            if not token:
                break
            time.sleep(S2_PAUSE_S)
        print(f"     kept {kept} reviews (scanned {seen}) from this query")
    return list(by_id.values())


def s2_fetch_references(review: dict) -> list[dict]:
    pid = review["paperId"]
    rows: list[dict] = []
    offset = 0
    while True:
        data = _s2_get(
            f"paper/{pid}/references",
            {"offset": offset, "limit": S2_REFERENCES_PAGE_SIZE, "fields": S2_REF_FIELDS},
        )
        if not data:
            break
        items = data.get("data", []) or []
        if not items:
            break
        for item in items:
            cp = item.get("citedPaper") or {}
            if cp.get("paperId") or cp.get("title"):
                rows.append(_s2_row(cp))
        if data.get("next") is None:
            break
        offset = data["next"]
        time.sleep(S2_PAUSE_S)
    return rows


# --- Backend dispatch -----------------------------------------------------

BACKENDS: dict[str, dict[str, Callable]] = {
    "openalex": {"find": oa_find_reviews, "refs": oa_fetch_references},
    "semantic_scholar": {"find": s2_find_reviews, "refs": s2_fetch_references},
}


# ==========================================================================
# Shared orchestration
# ==========================================================================


def _citation_key(row: dict) -> str:
    return (
        str(row.get("DOI", "")).strip().lower()
        or str(row.get("paperId", ""))
        or str(row.get("Title", "")).strip().lower()
    )


def find_reviews() -> pd.DataFrame:
    if os.path.exists(REVIEWS_CSV) and os.path.getsize(REVIEWS_CSV) > 0:
        df = pd.read_csv(REVIEWS_CSV, dtype=str).fillna("")
        print(f"Step 1: using cached {REVIEWS_CSV} ({len(df)} reviews). Delete it to re-search.")
        return df

    print(f"Step 1: searching {BACKEND} for systematic reviews")
    reviews = BACKENDS[BACKEND]["find"]()
    df = pd.DataFrame(reviews)
    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_csv(REVIEWS_CSV, index=False)
    print(f"  ✅ {len(df)} unique systematic reviews saved to {REVIEWS_CSV}")
    return df


# --- Optional Step 1b: LLM relevance gate on the seed reviews -------------

_openai_client = None

REVIEW_SCREEN_PROMPT = (
    "You screen candidate papers as the SEED for a systematic review of DIGITAL or "
    "TECHNOLOGICAL interventions for autistic and/or ADHD (broadly neurodevelopmental) "
    "people. Include a paper ONLY if it is itself a review (systematic review, scoping "
    "review, literature review, or meta-analysis) AND it concerns a digital/technological "
    "intervention (app, software, online/web program, telehealth, virtual reality, serious "
    "game, wearable, computerised training, etc.) AND the population is autistic and/or "
    "ADHD or otherwise neurodevelopmental. Exclude non-review articles, non-digital "
    "interventions, and unrelated populations/topics. When genuinely unsure, lean include "
    "(this is only a recall-oriented seed). "
    'Return ONLY JSON: {"include": true|false, "rationale": "<=20 words"}.'
)


def _openai():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        key = os.getenv("OPENAI_KEY") or os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_KEY is not set")
        _openai_client = OpenAI(api_key=key)
    return _openai_client


def _screen_one(title: str, abstract: str) -> tuple[str, str]:
    user = f"Title: {title}\n\nAbstract: {abstract or '(no abstract available)'}"
    resp = _openai().chat.completions.create(
        model=REVIEW_SCREEN_MODEL,
        messages=[
            {"role": "system", "content": REVIEW_SCREEN_PROMPT},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
    )
    data = json.loads(resp.choices[0].message.content)
    verdict = "include" if data.get("include") else "exclude"
    return verdict, str(data.get("rationale", ""))[:200]


def screen_reviews(reviews: pd.DataFrame) -> pd.DataFrame:
    """Add review_screen / review_screen_rationale columns. Cached & resumable:
    re-runs only screen rows that aren't decided yet, and resave REVIEWS_CSV."""
    df = reviews.copy()
    for col in ("review_screen", "review_screen_rationale"):
        if col not in df.columns:
            df[col] = ""
    df["review_screen"] = df["review_screen"].fillna("")

    pending = df.index[df["review_screen"].str.strip() == ""].tolist()
    if not pending:
        kept = (df["review_screen"] == "include").sum()
        print(f"Step 1b: reviews already screened ({kept} included). Delete columns to re-screen.")
        return df

    print(f"Step 1b: LLM-screening {len(pending)} reviews with {REVIEW_SCREEN_MODEL}")
    for n, idx in enumerate(pending, start=1):
        title = str(df.at[idx, "Title"] or "")
        abstract = str(df.at[idx, "Abstract"] or "")
        try:
            verdict, rationale = _screen_one(title, abstract)
        except Exception as e:
            print(f"    screen error ({e}); defaulting to include")
            verdict, rationale = "include", "screen_error_default_include"
        df.at[idx, "review_screen"] = verdict
        df.at[idx, "review_screen_rationale"] = rationale
        mark = "✓" if verdict == "include" else "✗"
        print(f"  [{n}/{len(pending)}] {mark} {title[:70]}")
        if n % 10 == 0:
            df.to_csv(REVIEWS_CSV, index=False)

    df.to_csv(REVIEWS_CSV, index=False)
    kept = (df["review_screen"] == "include").sum()
    print(f"  ✅ screened: {kept}/{len(df)} reviews included; saved to {REVIEWS_CSV}")
    return df


def _save_citations(cited: dict[str, dict]) -> None:
    """Write both the master citations CSV and the pipeline-ready export."""
    df = pd.DataFrame(cited.values())
    if not df.empty:
        df = df.sort_values("cited_by_count", ascending=False).reset_index(drop=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_csv(CITATIONS_CSV, index=False)
    os.makedirs(DATABASE_CSVS_DIR, exist_ok=True)
    df.reindex(columns=PIPELINE_COLS).to_csv(PIPELINE_EXPORT, index=False)


def scrape_references(reviews: pd.DataFrame) -> pd.DataFrame:
    fetch = BACKENDS[BACKEND]["refs"]

    # Resume: rebuild the dedup dict and processed-review set from prior output.
    cited: dict[str, dict] = {}
    processed: set[str] = set()
    if os.path.exists(CITATIONS_CSV) and os.path.getsize(CITATIONS_CSV) > 0:
        prior = pd.read_csv(CITATIONS_CSV, dtype=str).fillna("")
        for r in prior.to_dict(orient="records"):
            r["cited_by_count"] = int(r.get("cited_by_count") or 1)
            cited[_citation_key(r)] = r
        print(f"Step 2: resuming with {len(cited)} citations already scraped")
    if os.path.exists(PROCESSED_REVIEWS_FILE):
        processed = set(Path(PROCESSED_REVIEWS_FILE).read_text().split())

    todo = [
        r for _, r in reviews.iterrows()
        if r.get("paperId") and r["paperId"] not in processed
    ]
    limit = os.getenv("SCRAPE_REVIEW_LIMIT")
    if limit:
        todo = todo[: int(limit)]
    print(f"Step 2: scraping references from {len(todo)} reviews "
          f"({len(processed)} already done)")

    for i, review in enumerate(todo, start=1):
        pid = review["paperId"]
        rtitle = (review.get("Title", "") or "")[:70]
        print(f"  [{i}/{len(todo)}] {rtitle}")
        rows = fetch(dict(review))
        for row in rows:
            key = _citation_key(row)
            if not key:
                continue
            if key in cited:
                cited[key]["cited_by_count"] = int(cited[key]["cited_by_count"]) + 1
                if rtitle not in str(cited[key].get("cited_by_reviews", "")):
                    cited[key]["cited_by_reviews"] = (
                        f"{cited[key].get('cited_by_reviews', '')} | {rtitle}"
                    )
            else:
                row["cited_by_count"] = 1
                row["cited_by_reviews"] = rtitle
                row["Source"] = SOURCE_LABEL
                cited[key] = row

        # Persist after every review so a long run is crash-safe/resumable.
        processed.add(pid)
        _save_citations(cited)
        Path(PROCESSED_REVIEWS_FILE).write_text("\n".join(sorted(processed)))
        print(f"      {len(rows)} references pulled (unique total: {len(cited)})")

    _save_citations(cited)
    print(f"  ✅ {len(cited)} unique cited papers saved to {CITATIONS_CSV}")
    print(f"  ✅ pipeline-ready export written to {PIPELINE_EXPORT}")
    return pd.DataFrame(cited.values())


# --- Entry point ----------------------------------------------------------


def main() -> None:
    if BACKEND not in BACKENDS:
        raise SystemExit(f"Unknown CITATION_BACKEND={BACKEND!r}; choose one of {list(BACKENDS)}")
    print(f"Backend: {BACKEND}")
    if BACKEND == "openalex":
        print(f"OpenAlex polite-pool contact: {OPENALEX_MAILTO}\n")
    elif BACKEND == "semantic_scholar" and not S2_KEY:
        print("⚠️  SEMANTIC_SCHOLAR_API_KEY not set — keyless pool is heavily throttled.\n")

    reviews = find_reviews()
    if reviews.empty:
        print("No reviews found; nothing to scrape.")
        return

    if SCREEN_REVIEWS:
        reviews = screen_reviews(reviews)
        included = reviews[reviews["review_screen"] == "include"]
        print(f"Scraping citations from {len(included)}/{len(reviews)} included reviews "
              f"(SCREEN_REVIEWS=0 to scrape all).")
        reviews = included
    else:
        print("Review screening disabled (SCREEN_REVIEWS=0); scraping all reviews.")

    if reviews.empty:
        print("No reviews passed screening; nothing to scrape.")
        return
    scrape_references(reviews)


if __name__ == "__main__":
    main()
