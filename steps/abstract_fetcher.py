"""DOI → abstract lookup, trying multiple free sources in order.

Sources, in priority order:
  1. Semantic Scholar Graph API (throttled to 1 req/s).
  2. Crossref metadata.
  3. PubMed E-utilities (esearch by DOI → efetch).
  4. The publisher's landing page HTML (citation_abstract meta tag, og:description, etc.).

The standalone CLI ``fill-missing-abstracts-by-doi.py`` extends this with
Unpaywall, OpenAthens via Playwright, and PaperScraper.  Those are kept out of
the pipeline step to avoid spinning up a browser during automated runs.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from typing import Tuple
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

S2_BASE = "https://api.semanticscholar.org/graph/v1/paper"
CROSSREF_WORKS = "https://api.crossref.org/works"
NCBI_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ELSEVIER_ABSTRACT = "https://api.elsevier.com/content/abstract/doi"

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "literature-search-pipeline/1.0",
        "Accept": "application/json",
    }
)

# Semantic Scholar: at most 1 request per second, measured between request starts.
S2_MIN_INTERVAL_SEC = 1.0
_s2_last_request_start: float | None = None


def _throttle_semantic_scholar() -> None:
    global _s2_last_request_start
    if _s2_last_request_start is not None:
        wait = S2_MIN_INTERVAL_SEC - (time.monotonic() - _s2_last_request_start)
        if wait > 0:
            time.sleep(wait)


def _strip_markup_to_text(fragment: str) -> str:
    soup = BeautifulSoup(fragment, "html.parser")
    return " ".join(soup.stripped_strings)


# meta names that carry a real abstract (matched case-insensitively against both
# the `name` and `property` attributes). The first group are true abstracts; the
# og/twitter ones are sometimes blurbs, so we require more length for those.
_ABSTRACT_META = ("citation_abstract", "dc.description", "eagle-abstract", "prism.teaser")
_DESC_META = ("description", "og:description", "twitter:description")


def _extract_abstract_from_soup(soup: BeautifulSoup) -> str | None:
    # 1. meta tags (name OR property), case-insensitive — handles 'dc.description'
    #    vs 'DC.Description' etc. that the old exact-match check missed.
    for meta in soup.find_all("meta"):
        nm = (meta.get("name") or meta.get("property") or "").strip().lower()
        content = (meta.get("content") or "").strip()
        if not content:
            continue
        if nm in _ABSTRACT_META and len(content) > 80:
            return content
        if nm in _DESC_META and len(content) > 150:
            return content
    # 2. JSON-LD blocks — Springer, Wiley, and many others embed the abstract here
    #    as "description"/"abstract" even when no meta tag carries it.
    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = s.string or s.get_text() or ""
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue
        for obj in (data if isinstance(data, list) else [data]):
            if isinstance(obj, dict):
                d = obj.get("abstract") or obj.get("description")
                if isinstance(d, str) and len(d.strip()) > 150:
                    return d.strip()
    # 3. common abstract containers (incl. Springer's c-article markup)
    for sel in (
        "section.abstract", "div.abstract", "div#abstract", "div.abstractSection",
        "div.c-article-section__content", "#Abs1-content", "div[class*='abstract' i]",
    ):
        node = soup.select_one(sel)
        if node:
            text = " ".join(node.stripped_strings)
            if len(text) > 200:
                return text
    return None


def fetch_semantic_scholar(doi: str, api_key: str | None) -> str | None:
    global _s2_last_request_start
    headers = dict(SESSION.headers)
    if api_key:
        headers["x-api-key"] = api_key
    encoded = quote(f"DOI:{doi}", safe="")
    url = f"{S2_BASE}/{encoded}"

    for attempt in range(5):
        _throttle_semantic_scholar()
        _s2_last_request_start = time.monotonic()
        r = SESSION.get(
            url, params={"fields": "abstract,title"}, headers=headers, timeout=60
        )
        if r.status_code == 200:
            data = r.json()
            abs_text = data.get("abstract")
            if isinstance(abs_text, str) and abs_text.strip():
                return abs_text.strip()
            return None
        if r.status_code == 429:
            time.sleep(min(60, 2 ** attempt))
            continue
        if r.status_code in (401, 403, 404):
            return None
        if 500 <= r.status_code < 600:
            time.sleep(min(60, 2 ** attempt))
            continue
        return None
    return None


def fetch_elsevier(doi: str, api_key: str | None = None, insttoken: str | None = None) -> str | None:
    """Elsevier Abstract Retrieval API (ScienceDirect publishers, DOI prefix 10.1016 etc.).

    Abstract content (the META_ABS view) is entitled by institution: it returns the
    abstract only when the request comes from a subscribing IP (e.g. on the RMIT
    network/VPN) or carries an institution token (``X-ELS-Insttoken``). Off-campus
    with only an API key you get metadata but a 401 for the abstract view.
    """
    api_key = api_key or os.getenv("ELSEVIER_API_KEY")
    if not api_key:
        return None
    insttoken = insttoken or os.getenv("ELSEVIER_INSTTOKEN")
    headers = {"X-ELS-APIKey": api_key, "Accept": "application/json"}
    if insttoken:
        headers["X-ELS-Insttoken"] = insttoken
    try:
        r = SESSION.get(
            f"{ELSEVIER_ABSTRACT}/{quote(doi, safe='')}",
            params={"view": "META_ABS"},
            headers=headers,
            timeout=60,
        )
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    try:
        cd = r.json()["abstracts-retrieval-response"]["coredata"]
    except (ValueError, KeyError, TypeError):
        return None
    desc = cd.get("dc:description")
    if isinstance(desc, str) and desc.strip():
        return re.sub(r"^abstract\s+", "", desc.strip(), flags=re.I).strip() or None
    return None


def fetch_crossref(doi: str) -> str | None:
    enc = quote(doi, safe="")
    try:
        r = SESSION.get(f"{CROSSREF_WORKS}/{enc}", timeout=60)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    msg = r.json().get("message") or {}
    abstract = msg.get("abstract")
    if not isinstance(abstract, str) or not abstract:
        return None
    text = _strip_markup_to_text(abstract)
    text = re.sub(r"^abstract\s+", "", text.strip(), flags=re.I)
    return text.strip() or None


def fetch_pubmed(doi: str) -> str | None:
    """Look up DOI in PubMed (esearch), then fetch abstract via efetch.
    Free, no auth, works for most biomedical/clinical/psych papers."""
    try:
        r = SESSION.get(
            f"{NCBI_EUTILS}/esearch.fcgi",
            params={"db": "pubmed", "term": f"{doi}[AID]", "retmode": "json"},
            timeout=60,
        )
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    try:
        ids = (r.json().get("esearchresult") or {}).get("idlist") or []
    except ValueError:
        return None
    if not ids:
        return None
    pmid = ids[0]

    try:
        r = SESSION.get(
            f"{NCBI_EUTILS}/efetch.fcgi",
            params={"db": "pubmed", "id": pmid, "retmode": "xml"},
            timeout=60,
        )
    except requests.RequestException:
        return None
    if r.status_code != 200 or not r.text:
        return None

    try:
        root = ET.fromstring(r.text)
    except ET.ParseError:
        return None
    parts: list[str] = []
    for node in root.iter("AbstractText"):
        text = "".join(node.itertext()).strip()
        if not text:
            continue
        label = node.get("Label")
        parts.append(f"{label}: {text}" if label else text)
    return " ".join(parts).strip() or None


SPRINGER_META = "https://api.springernature.com/meta/v2/json"
SPRINGER_OA = "https://api.springernature.com/openaccess/json"


def _springer_abstract_from(records: list) -> str | None:
    if not records:
        return None
    rec = records[0]
    ab = rec.get("abstract")
    # meta/v2 sometimes nests abstract as {"p": "..."} or a list of paragraphs
    if isinstance(ab, dict):
        ab = ab.get("p") or ab.get("#text") or ""
    if isinstance(ab, list):
        ab = " ".join(str(x.get("p", x) if isinstance(x, dict) else x) for x in ab)
    if isinstance(ab, str):
        text = _strip_markup_to_text(ab)
        text = re.sub(r"^abstract\s+", "", text.strip(), flags=re.I)
        return text.strip() or None
    return None


def fetch_springer(doi: str, meta_key: str | None = None, oa_key: str | None = None) -> str | None:
    """Springer Nature API → abstract for 10.1007 / 10.1023 / 10.1038 etc. DOIs.

    Tries the Meta API (broad: returns abstracts for subscription + OA content),
    then the Open Access API. Keys from SPRINGER_META_API_KEY / SPRINGER_OA_API_KEY.
    """
    meta_key = meta_key or os.getenv("SPRINGER_META_API_KEY")
    oa_key = oa_key or os.getenv("SPRINGER_OA_API_KEY")
    for base, key in ((SPRINGER_META, meta_key), (SPRINGER_OA, oa_key)):
        if not key:
            continue
        try:
            r = SESSION.get(
                base, params={"q": f"doi:{doi}", "api_key": key}, timeout=60,
                headers={"Accept": "application/json"},
            )
        except requests.RequestException:
            continue
        if r.status_code != 200:
            continue
        try:
            records = r.json().get("records") or []
        except ValueError:
            continue
        ab = _springer_abstract_from(records)
        if ab and len(ab) > 60:
            return ab
    return None


EUROPEPMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def fetch_europepmc(doi: str | None = None, pmid: str | None = None) -> str | None:
    """Europe PMC REST search → abstractText. Free, no auth, broad coverage
    (life-sciences + much of psychology/medicine), and frequently carries an
    abstract where PubMed-by-DOI came up empty. Tries DOI first, then PMID."""
    queries: list[str] = []
    if doi:
        queries.append(f'DOI:"{doi}"')
    if pmid and str(pmid).strip():
        queries.append(f'EXT_ID:{str(pmid).strip()} AND SRC:MED')
    for q in queries:
        try:
            r = SESSION.get(
                EUROPEPMC_SEARCH,
                params={"query": q, "format": "json", "resultType": "core", "pageSize": 1},
                timeout=60,
            )
        except requests.RequestException:
            continue
        if r.status_code != 200:
            continue
        try:
            results = (r.json().get("resultList") or {}).get("result") or []
        except ValueError:
            continue
        if not results:
            continue
        abstract = results[0].get("abstractText")
        if isinstance(abstract, str) and abstract.strip():
            return _strip_markup_to_text(abstract).strip() or None
    return None


# Publisher landing pages frequently block non-browser User-Agents and
# content-negotiate on Accept, so requests to them must look like a browser
# asking for HTML (not the session default of application/json).
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def resolve_doi_url(doi: str) -> str | None:
    """Follow doi.org redirects to the publisher landing page."""
    try:
        r = SESSION.get(
            f"https://doi.org/{quote(doi, safe='')}",
            headers=_BROWSER_HEADERS,
            allow_redirects=True,
            timeout=25,
        )
    except requests.RequestException:
        return None
    if r.status_code >= 400:
        return None
    return r.url


def fetch_landing_page(url: str) -> str | None:
    try:
        r = SESSION.get(url, headers=_BROWSER_HEADERS, timeout=25, allow_redirects=True)
    except requests.RequestException:
        return None
    if r.status_code >= 400 or not r.text:
        return None
    return _extract_abstract_from_soup(BeautifulSoup(r.text, "html.parser"))


def fetch_abstract_basic(doi: str, api_key: str | None) -> Tuple[str | None, str]:
    """Try the free, headless sources in order.  Returns (abstract|None, source_label)."""
    tried: list[str] = []

    tried.append("semantic_scholar")
    ab = fetch_semantic_scholar(doi, api_key)
    if ab:
        return ab, "semantic_scholar"

    tried.append("crossref")
    ab = fetch_crossref(doi)
    if ab:
        return ab, "crossref"

    tried.append("pubmed")
    ab = fetch_pubmed(doi)
    if ab:
        return ab, "pubmed"

    tried.append("landing_page_html")
    url = resolve_doi_url(doi)
    if url:
        ab = fetch_landing_page(url)
        if ab:
            return ab, "landing_page_html"

    # Elsevier (ScienceDirect) papers aren't in the open aggregators and their
    # landing page is a JS stub — use the Elsevier Abstract API (needs an
    # institution-entitled IP/insttoken to return the abstract).
    if os.getenv("ELSEVIER_API_KEY") and doi.startswith(("10.1016", "10.1006", "10.1053", "10.1067", "10.1078")):
        tried.append("elsevier")
        ab = fetch_elsevier(doi)
        if ab:
            return ab, "elsevier"

    final_url = url if url else "(could not resolve DOI)"
    print(
        f"    [diag] tried {', '.join(tried)} — none yielded an abstract. "
        f"DOI redirects to: {final_url}",
        file=sys.stderr,
    )
    return None, "none"
