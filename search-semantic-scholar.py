import os
import time

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

# Boolean query mirroring the other databases' searches (see
# search-results-from-database/database-csvs/search_queries.txt), translated to
# Semantic Scholar bulk-search operators:
#   `|` = OR, `+` = AND, `*` = prefix wildcard, `"..."` = phrase, `()` = grouping.
SEARCH_QUERY = (
    '(ADHD | autis* | ASD | Asperger* | AuDHD) '
    '+ (app | "mobile application" | mHealth | eHealth | "digital tool" '
    '| "web-based" | software | "digital therapeutics") '
    '+ adult'
)

MAX_RESULTS = 5000
FIELDS = "title,abstract,authors,year,url,venue,externalIds"

# The bulk endpoint supports the boolean query syntax above (the relevance
# `/paper/search` endpoint does not) and paginates with a continuation token,
# returning up to 1000 records per page.
S2_BULK_URL = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"

# Output lands in the pipeline's input directory so combine.py picks it up as
# another source (Source = "semantic_scholar").
OUTPUT_CSV = os.path.join(
    "search-results-from-database", "database-csvs", "semantic_scholar.csv"
)


def search_semantic_scholar(query, api_key=None):
    """Fetch papers from Semantic Scholar's bulk search, following the token.

    If an API key is supplied but rejected (401/403), fall back to
    unauthenticated requests for the rest of the run rather than failing.
    """
    use_key = bool(api_key)
    all_results = []
    token = None

    while len(all_results) < MAX_RESULTS:
        params = {"query": query, "fields": FIELDS}
        if token:
            params["token"] = token

        for attempt in range(5):
            headers = {"Accept": "application/json"}
            if use_key:
                headers["x-api-key"] = api_key
            response = requests.get(S2_BULK_URL, headers=headers, params=params)

            if response.status_code == 200:
                break
            if response.status_code in (401, 403) and use_key:
                print("⚠️ API key rejected (HTTP "
                      f"{response.status_code}); falling back to unauthenticated.")
                use_key = False
                continue
            if response.status_code == 429:
                wait = 2 ** attempt
                print(f"⚠️ Rate limited. Waiting {wait}s before retry...")
                time.sleep(wait)
                continue
            print(f"❌ Error {response.status_code}: {response.text[:200]}")
            return all_results[:MAX_RESULTS]
        else:
            print("❌ Max retries hit. Stopping.")
            break

        data = response.json()
        papers = data.get("data") or []
        if not all_results:
            print(f"📊 Semantic Scholar reports {data.get('total')} total matches.")
        all_results.extend(papers)
        print(f"📄 Retrieved {len(all_results)} papers so far...")

        token = data.get("token")
        if not token or not papers:
            break
        # Be polite to the shared rate-limit pool when unauthenticated.
        time.sleep(1 if use_key else 2)

    return all_results[:MAX_RESULTS]


def to_rows(papers):
    """Map S2 records to the pipeline's standard columns, de-duped within the run."""
    rows = []
    seen = set()
    for p in papers:
        ext = p.get("externalIds") or {}
        doi = (ext.get("DOI") or "").strip()
        key = doi.lower() if doi else p.get("paperId", "")
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "Title": p.get("title") or "",
            "Abstract": p.get("abstract") or "",
            "Authors": ", ".join(a.get("name", "") for a in (p.get("authors") or [])),
            "Year": p.get("year") or "",
            "DOI": doi,
            "PMID": ext.get("PubMed") or "",
            "URL": p.get("url") or "",
            "Journal": p.get("venue") or "",
        })
    return rows


def main():
    print("🔍 Searching Semantic Scholar (bulk boolean query)...")
    # DISABLED 2026-06: dead institutional key (403). Force keyless S2 (200, 1 req/s).
    api_key = None  # os.getenv("SEMANTIC_SCHOLAR_API_KEY") or os.getenv("S2_API_KEY")
    if api_key:
        print("Semantic Scholar: API key loaded.")
    else:
        print("Semantic Scholar: no key — using unauthenticated limits.")

    papers = search_semantic_scholar(SEARCH_QUERY, api_key=api_key)
    rows = to_rows(papers)

    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"✅ Saved {len(df)} unique papers to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
