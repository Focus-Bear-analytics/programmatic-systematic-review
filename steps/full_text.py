"""Full-text retrieval for screened candidates, open-access sources only.

Order, all free / no login:
  1. Europe PMC fullTextXML  — OA biomedical (PMC) content, returned as XML.
  2. Unpaywall best OA location — PDF (parsed with pypdf) or HTML landing.

Paywalled papers (no OA location) are left for the OpenAthens/Playwright pass,
which needs an interactive RMIT login and is run separately.

``fetch_open_full_text(doi, pmid, email)`` returns ``(text|None, source)``.
"""
from __future__ import annotations

import io
import re
from typing import Tuple

import requests
from bs4 import BeautifulSoup

EUROPEPMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
# Europe PMC's own fullTextXML endpoint is unreliable; NCBI's PMC efetch returns
# the JATS full text for any OA PMC article (id = numeric PMCID, no "PMC" prefix).
NCBI_PMC_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
UNPAYWALL_BASE = "https://api.unpaywall.org/v2"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "literature-search-pipeline/1.0 (mailto:research)"})

_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

MIN_FULL_TEXT_CHARS = 1500  # below this it's an abstract/landing stub, not full text


def _clean(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


def _xml_to_text(xml: str) -> str | None:
    soup = BeautifulSoup(xml, "lxml-xml") if _has_lxml() else BeautifulSoup(xml, "html.parser")
    body = soup.find("body") or soup
    for tag in body.find_all(["ref-list", "back", "fig", "table-wrap"]):
        tag.decompose()
    text = _clean(body.get_text(separator="\n", strip=True))
    return text or None


def _has_lxml() -> bool:
    try:
        import lxml  # noqa: F401
        return True
    except Exception:
        return False


def _europepmc_record(doi: str | None, pmid: str | None) -> dict | None:
    for q in ([f'DOI:"{doi}"'] if doi else []) + ([f"EXT_ID:{pmid} AND SRC:MED"] if pmid else []):
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
            res = (r.json().get("resultList") or {}).get("result") or []
        except ValueError:
            continue
        if res:
            return res[0]
    return None


def fetch_pmc_fulltext(doi: str | None, pmid: str | None) -> str | None:
    """Find the OA PMC article (via Europe PMC search) then pull JATS XML from
    NCBI efetch and reduce it to body text."""
    rec = _europepmc_record(doi, pmid)
    if not rec or str(rec.get("isOpenAccess", "")).upper() != "Y":
        return None
    pmcid = str(rec.get("pmcid") or "").upper().replace("PMC", "").strip()
    if not pmcid:
        return None
    try:
        r = SESSION.get(
            NCBI_PMC_EFETCH,
            params={"db": "pmc", "id": pmcid, "rettype": "xml", "retmode": "xml"},
            timeout=90,
        )
    except requests.RequestException:
        return None
    if r.status_code != 200 or not r.text:
        return None
    text = _xml_to_text(r.text)
    return text if text and len(text) >= MIN_FULL_TEXT_CHARS else None


def _pdf_to_text(data: bytes) -> str | None:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception:
        return None
    text = _clean(text)
    return text if len(text) >= MIN_FULL_TEXT_CHARS else None


def _html_to_text(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "header", "footer", "nav", "form", "aside"]):
        tag.decompose()
    main = soup.find("article") or soup.find("main") or soup.body or soup
    text = _clean(main.get_text(separator="\n", strip=True))
    return text if len(text) >= MIN_FULL_TEXT_CHARS else None


def fetch_unpaywall_fulltext(doi: str, email: str | None) -> str | None:
    if not email:
        return None
    try:
        r = SESSION.get(f"{UNPAYWALL_BASE}/{doi}", params={"email": email}, timeout=60)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    try:
        loc = r.json().get("best_oa_location") or {}
    except ValueError:
        return None
    for url in (loc.get("url_for_pdf"), loc.get("url")):
        if not url:
            continue
        try:
            resp = SESSION.get(url, headers=_BROWSER, timeout=90, allow_redirects=True)
        except requests.RequestException:
            continue
        if resp.status_code != 200 or not resp.content:
            continue
        ctype = resp.headers.get("Content-Type", "").lower()
        if "pdf" in ctype or url.lower().endswith(".pdf"):
            text = _pdf_to_text(resp.content)
        else:
            text = _html_to_text(resp.text)
        if text:
            return text
    return None


ELSEVIER_ARTICLE = "https://api.elsevier.com/content/article/doi"


def fetch_elsevier_fulltext(doi: str, api_key: str | None = None) -> str | None:
    """ScienceDirect Article Retrieval API (FULL view) → article body text.

    Entitled by institution: returns full text only from a subscribing IP (e.g.
    on the RMIT network/wifi) or with an institution token. Off-campus -> 401.
    Extracts the <ce:para> body paragraphs (clean), falling back to <originalText>.
    """
    import os
    api_key = api_key or os.getenv("ELSEVIER_API_KEY")
    if not api_key:
        return None
    try:
        from urllib.parse import quote
        r = SESSION.get(
            f"{ELSEVIER_ARTICLE}/{quote(doi, safe='')}",
            params={"view": "FULL"},
            headers={"X-ELS-APIKey": api_key, "Accept": "text/xml"},
            timeout=120,
        )
    except requests.RequestException:
        return None
    if r.status_code != 200 or not r.text:
        return None
    soup = BeautifulSoup(r.text, "lxml-xml") if _has_lxml() else BeautifulSoup(r.text, "html.parser")
    paras = soup.find_all("para")
    if paras:
        text = _clean("\n".join(" ".join(p.stripped_strings) for p in paras))
    else:
        node = soup.find("originalText")
        text = _clean(" ".join(node.stripped_strings)) if node else ""
    return text if len(text) >= MIN_FULL_TEXT_CHARS else None


def _url_to_text(url: str | None) -> str | None:
    """Download an OA URL and extract text (PDF or HTML landing)."""
    if not url:
        return None
    try:
        resp = SESSION.get(url, headers=_BROWSER, timeout=90, allow_redirects=True)
    except requests.RequestException:
        return None
    if resp.status_code != 200 or not resp.content:
        return None
    ctype = resp.headers.get("Content-Type", "").lower()
    text = _pdf_to_text(resp.content) if ("pdf" in ctype or url.lower().endswith(".pdf")) \
        else _html_to_text(resp.text)
    return text or None


S2_PAPER = "https://api.semanticscholar.org/graph/v1/paper"


def fetch_s2_fulltext(doi: str | None, pmid: str | None) -> str | None:
    """Semantic Scholar openAccessPdf — often a repository/preprint copy Unpaywall
    lacks. Keyless (the project's S2 key is dead); tolerant of rate limits."""
    ident = f"DOI:{doi}" if doi else (f"PMID:{pmid}" if pmid else None)
    if not ident:
        return None
    try:
        r = SESSION.get(f"{S2_PAPER}/{ident}", params={"fields": "openAccessPdf"}, timeout=60)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    try:
        oa = (r.json() or {}).get("openAccessPdf") or {}
    except ValueError:
        return None
    return _url_to_text(oa.get("url"))


OPENALEX_WORK = "https://api.openalex.org/works"


def fetch_openalex_fulltext(doi: str | None, email: str | None) -> str | None:
    """OpenAlex OA locations — aggregates repository/publisher OA PDFs, sometimes
    catching copies Unpaywall's best_oa_location misses."""
    if not doi:
        return None
    params = {"mailto": email} if email else {}
    try:
        r = SESSION.get(f"{OPENALEX_WORK}/doi:{doi}", params=params, timeout=60)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    try:
        w = r.json() or {}
    except ValueError:
        return None
    seen: set[str] = set()
    locs = [w.get("best_oa_location"), w.get("primary_location"), *(w.get("locations") or [])]
    for loc in locs:
        if not loc:
            continue
        url = loc.get("pdf_url") or (loc.get("is_oa") and loc.get("landing_page_url"))
        if not url or url in seen:
            continue
        seen.add(url)
        text = _url_to_text(url)
        if text:
            return text
    return None


def fetch_open_full_text(doi: str | None, pmid: str | None, email: str | None) -> Tuple[str | None, str]:
    """Try the free OA sources in order. Returns (text|None, source_label)."""
    if doi or pmid:
        text = fetch_pmc_fulltext(doi, pmid)
        if text:
            return text, "pmc"
    if doi:
        text = fetch_unpaywall_fulltext(doi, email)
        if text:
            return text, "unpaywall"
    if doi or pmid:
        text = fetch_s2_fulltext(doi, pmid)
        if text:
            return text, "semantic_scholar"
    if doi:
        text = fetch_openalex_fulltext(doi, email)
        if text:
            return text, "openalex"
    return None, "none"
