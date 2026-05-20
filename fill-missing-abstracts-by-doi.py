#!/usr/bin/env python3
"""
Fill missing Abstract cells in a database spreadsheet by DOI.

Fallback order:
1. Semantic Scholar Graph API (primary).
2. Crossref metadata API.
3. PubMed E-utilities (esearch by DOI → efetch abstract). Free, biomed-focused.
4. DOI redirect URL → parse common HTML meta tags (citation_abstract, og:description, etc.).
5. Unpaywall (if `UNPAYWALL_EMAIL` set) → scrape OA landing pages it surfaces.
6. RMIT OpenAthens via Playwright (`--playwright`):
   Launches Chrome via Playwright, prompts for OpenAthens login at start, then re-fetches
   paywalled landing pages through the OpenAthens redirector
   (https://go.openathens.net/redirector/rmit.edu.au?url=<target>) so the publisher
   receives a SAML token. Persistent profile keeps you logged in between runs (default
   `~/.cache/literature-search/chrome-profile`; override with `CHROME_PROFILE_DIR`).
7. Optional: [NLPatVCU/PaperScraper](https://github.com/NLPatVCU/PaperScraper) only if the
   `paperscraper` package is importable.

Loads `.env` via python-dotenv. Useful env vars:
  SEMANTIC_SCHOLAR_API_KEY  authenticated S2 access (1 req/s enforced in code)
  UNPAYWALL_EMAIL           required by Unpaywall as a contact (no key)
  OPENATHENS_REDIRECTOR     OpenAthens redirector base; defaults to RMIT scope
  RMIT_LOGIN_URL            page Playwright opens for login (default my.openathens.net)
  CHROME_PROFILE_DIR        override the persistent Playwright profile dir
Reads the **MERGED** worksheet by default (`--sheet` to use another tab, e.g. PsycInfo).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

S2_BASE = "https://api.semanticscholar.org/graph/v1/paper"
CROSSREF_WORKS = "https://api.crossref.org/works"
UNPAYWALL_BASE = "https://api.unpaywall.org/v2"
NCBI_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DUPLICATE_COL = "is_duplicate"
DEFAULT_INPUT = Path("search-results-from-database") / "Test 15.03 (1).xls"
DEFAULT_SHEET = "MERGED"

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "literature-search-fill-abstracts/1.0",
        "Accept": "application/json",
    }
)

# Semantic Scholar: at most 1 request per second (minimum interval between request starts).
S2_MIN_INTERVAL_SEC = 1.0
_s2_last_request_start: float | None = None


def _throttle_semantic_scholar() -> None:
    """Wait so consecutive Semantic Scholar requests start at least S2_MIN_INTERVAL_SEC apart."""
    global _s2_last_request_start
    if _s2_last_request_start is not None:
        wait = S2_MIN_INTERVAL_SEC - (time.monotonic() - _s2_last_request_start)
        if wait > 0:
            time.sleep(wait)


def _read_table(path: Path, sheet_name: str | int) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".xls":
        return pd.read_excel(path, sheet_name=sheet_name, engine="xlrd")
    return pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")


def find_column(df: pd.DataFrame, names: list[str]) -> str | None:
    lowered = {str(c).strip().lower(): c for c in df.columns}
    for n in names:
        if n.lower() in lowered:
            return lowered[n.lower()]
    for col in df.columns:
        cl = str(col).strip().lower()
        for n in names:
            if n.lower() in cl:
                return col
    return None


def normalize_doi(raw: Any) -> str | None:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).strip()
    if not s or s.lower() in ("nan", "none", "n/a", ""):
        return None
    s = re.sub(r"^https?://(dx\.)?doi\.org/", "", s, flags=re.I).strip()
    return s.rstrip(".").strip() or None


def _dedup_key(
    row: pd.Series,
    doi_col: str,
    title_col: str | None,
) -> tuple[str, str] | None:
    """Normalized key for duplicate detection. DOI first; title fallback when no DOI."""
    doi = normalize_doi(row[doi_col])
    if doi:
        return ("doi", doi.lower())
    if title_col is not None:
        title = row.get(title_col)
        if isinstance(title, str) and title.strip():
            t = re.sub(r"[^a-z0-9 ]+", "", title.lower())
            t = re.sub(r"\s+", " ", t).strip()
            if t:
                return ("title", t)
    return None


def deduplicate(
    df: pd.DataFrame,
    doi_col: str,
    abs_col: str,
) -> tuple[dict[Any, Any], int, int]:
    """Mark duplicates in `is_duplicate` column and copy abstracts within groups.

    A 'group' is a set of rows that share a DOI (or title when DOI is missing).
    The first row in each group is the primary (`is_duplicate` blank); subsequent
    rows are tagged 'Y'. Within a group, any row missing an abstract gets one
    from the first row in the group that has one (in row order). Returns
    (duplicate→primary index map, count of duplicates, count of backfills).
    """
    title_col = find_column(df, ["title", "article title", "ti"])
    if DUPLICATE_COL not in df.columns:
        df[DUPLICATE_COL] = ""
    df[DUPLICATE_COL] = df[DUPLICATE_COL].astype(object)

    groups: dict[tuple[str, str], list[Any]] = {}
    for idx, row in df.iterrows():
        key = _dedup_key(row, doi_col, title_col)
        if key is None:
            df.at[idx, DUPLICATE_COL] = ""
            continue
        groups.setdefault(key, []).append(idx)

    duplicate_to_primary: dict[Any, Any] = {}
    duplicates_marked = 0
    backfilled = 0
    for indices in groups.values():
        primary_idx = indices[0]
        df.at[primary_idx, DUPLICATE_COL] = ""
        donor_idx: Any = None
        for i in indices:
            if not is_missing_abstract(df.at[i, abs_col]):
                donor_idx = i
                break
        for i in indices[1:]:
            df.at[i, DUPLICATE_COL] = "Y"
            duplicate_to_primary[i] = primary_idx
            duplicates_marked += 1
            if donor_idx is not None and is_missing_abstract(df.at[i, abs_col]):
                df.at[i, abs_col] = df.at[donor_idx, abs_col]
                backfilled += 1
        if (
            donor_idx is not None
            and donor_idx != primary_idx
            and is_missing_abstract(df.at[primary_idx, abs_col])
        ):
            df.at[primary_idx, abs_col] = df.at[donor_idx, abs_col]
            backfilled += 1

    return duplicate_to_primary, duplicates_marked, backfilled


def is_missing_abstract(val: Any) -> bool:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return True
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "n/a", "na", ".", "-"):
        return True
    return False


def semantic_scholar_paper_url(doi: str) -> str:
    paper_id = f"DOI:{doi}"
    encoded = quote(paper_id, safe="")
    return f"{S2_BASE}/{encoded}"


def fetch_abstract_semantic_scholar(doi: str, api_key: str | None) -> str | None:
    global _s2_last_request_start
    headers = dict(SESSION.headers)
    if api_key:
        headers["x-api-key"] = api_key
    url = semantic_scholar_paper_url(doi)
    for attempt in range(5):
        _throttle_semantic_scholar()
        _s2_last_request_start = time.monotonic()
        r = SESSION.get(
            url,
            params={"fields": "abstract,title"},
            headers=headers,
            timeout=60,
        )
        if r.status_code == 200:
            data = r.json()
            abs_text = data.get("abstract")
            if isinstance(abs_text, str) and abs_text.strip():
                return abs_text.strip()
            return None
        if r.status_code == 429:
            wait = min(60, 2 ** attempt)
            time.sleep(wait)
            continue
        if r.status_code == 404:
            return None
        if r.status_code in (401, 403):
            # Auth / geo block — fall back to Crossref etc. without aborting the run
            return None
        if 500 <= r.status_code < 600:
            wait = min(60, 2 ** attempt)
            time.sleep(wait)
            continue
        # Other client errors (e.g. 400): skip this source
        return None
    return None


def strip_markup_to_text(fragment: str) -> str:
    soup = BeautifulSoup(fragment, "html.parser")
    return " ".join(soup.stripped_strings)


def fetch_abstract_pubmed(doi: str) -> str | None:
    """Look up the DOI in PubMed (esearch) and fetch the abstract via efetch.
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
    combined = " ".join(parts).strip()
    return combined or None


def fetch_abstract_unpaywall(doi: str, email: str) -> str | None:
    """Unpaywall has no abstract field for many records, but for OA papers with
    metadata it surfaces titles + provides OA landing URLs we can scrape next."""
    enc = quote(doi, safe="")
    try:
        r = SESSION.get(f"{UNPAYWALL_BASE}/{enc}", params={"email": email}, timeout=60)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    data = r.json() or {}
    # Unpaywall doesn't include abstracts directly. We use it to find an OA URL
    # and then scrape that page's meta tags (which usually have the abstract).
    best = data.get("best_oa_location") or {}
    candidates = []
    for key in ("url_for_landing_page", "url"):
        v = best.get(key)
        if v:
            candidates.append(v)
    for loc in data.get("oa_locations") or []:
        for key in ("url_for_landing_page", "url"):
            v = loc.get(key)
            if v and v not in candidates:
                candidates.append(v)
    for url in candidates:
        ab = fetch_abstract_from_html(url)
        if ab:
            return ab
    return None


def _openathens_redirect(url: str, redirector_base: str) -> str:
    """Wrap a URL in the OpenAthens redirector so the publisher gets a SAML token."""
    return f"{redirector_base}?url={quote(url, safe='')}"


def _extract_abstract_from_soup(soup: "BeautifulSoup") -> str | None:
    meta = soup.find("meta", attrs={"name": "citation_abstract"})
    if meta and meta.get("content"):
        t = meta["content"].strip()
        if len(t) > 80:
            return t
    for name in ("dc.Description", "DC.Description", "description"):
        m = soup.find("meta", attrs={"name": name})
        if m and m.get("content"):
            t = m["content"].strip()
            if len(t) > 120:
                return t
    og = soup.find("meta", attrs={"property": "og:description"})
    if og and og.get("content"):
        t = og["content"].strip()
        if len(t) > 120:
            return t
    # Last resort: common abstract container patterns
    for sel in (
        "section.abstract", "div.abstract", "div#abstract",
        "div.abstractSection", "div[class*='abstract' i]",
    ):
        node = soup.select_one(sel)
        if node:
            text = " ".join(node.stripped_strings)
            if len(text) > 200:
                return text
    return None


def setup_playwright(login_url: str, profile_dir: Path):
    """Launch Chrome via Playwright with a saved storage-state file (cookies +
    localStorage), prompt user to log in only if the existing session is invalid.

    Returns (pw, browser, ctx, state_file_path). storage-state.json captures session
    cookies that launch_persistent_context drops on close, so the OpenAthens session
    survives between runs.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "playwright not installed. Run: poetry add playwright && poetry run playwright install chromium"
        ) from e

    profile_dir.mkdir(parents=True, exist_ok=True)
    state_file = profile_dir / "storage-state.json"

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.launch(channel="chrome", headless=False)
    except Exception:
        # Fall back to bundled Chromium if user doesn't have Chrome installed
        browser = pw.chromium.launch(headless=False)

    ctx_kwargs: dict[str, Any] = {"viewport": {"width": 1280, "height": 900}}
    if state_file.is_file():
        ctx_kwargs["storage_state"] = str(state_file)
    ctx = browser.new_context(**ctx_kwargs)

    page = ctx.new_page()
    print(f"\nChecking OpenAthens session at {login_url} ...")
    try:
        page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        print(f"  (nav warning: {e})", file=sys.stderr)
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass

    # Detect login state from page content. URL alone is unreliable because
    # my.openathens.net shows the "Find your account" page when unauthenticated.
    # Positive signals: a "Sign out" affordance, or "My resources" dashboard heading.
    looks_logged_in = False
    positive_selectors = (
        "a:has-text('Sign out')",
        "button:has-text('Sign out')",
        "a:has-text('Log out')",
        "button:has-text('Log out')",
        "*:has-text('My resources')",
    )
    for sel in positive_selectors:
        try:
            if page.locator(sel).count() > 0:
                looks_logged_in = True
                break
        except Exception:
            continue
    # Negative signal — if we see the institution-finder form, definitely not logged in.
    try:
        if page.locator("input[type='email'], input[name*='org' i]").count() > 0:
            looks_logged_in = False
    except Exception:
        pass

    if looks_logged_in:
        print("Playwright: existing OpenAthens session is valid — login skipped.")
    else:
        print("Log in via OpenAthens (RMIT), then return here.")
        print("Tip: tick 'Stay signed in' if offered, so future runs can skip this step.")
        try:
            input("Press Enter once you're logged in (or Ctrl-C to abort)... ")
        except (EOFError, KeyboardInterrupt):
            try:
                ctx.close()
                browser.close()
                pw.stop()
            except Exception:
                pass
            raise

    return pw, browser, ctx, state_file


def fetch_abstract_playwright(
    doi: str,
    redirector_base: str,
    ctx,
    debug: bool = False,
) -> str | None:
    """Resolve DOI, wrap in OpenAthens redirector, render the resulting page in the
    authenticated Playwright context, parse the HTML for an abstract.

    On failure, prints diagnostic info (final URL, status, title). With debug=True,
    pauses with the page open so the user can inspect before closing it.
    """
    landing = resolve_doi_url(doi)
    if not landing:
        print(f"    [paywall] could not resolve DOI {doi}", file=sys.stderr)
        return None
    proxied = _openathens_redirect(landing, redirector_base)
    page = ctx.new_page()
    abstract: str | None = None
    err: str | None = None
    response = None
    html = ""
    try:
        try:
            response = page.goto(proxied, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            err = f"navigation error: {type(e).__name__}: {e}"
        if err is None:
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            try:
                html = page.content()
            except Exception as e:
                err = f"content read error: {type(e).__name__}: {e}"
        if err is None and html:
            soup = BeautifulSoup(html, "html.parser")
            abstract = _extract_abstract_from_soup(soup)
            if abstract is None:
                err = "no abstract found in page"

        if abstract is None:
            try:
                final_url = page.url
            except Exception:
                final_url = "(unknown)"
            try:
                title = page.title()
            except Exception:
                title = "(unknown)"
            status = response.status if response is not None else "?"
            print(
                f"    [paywall] {err} (status={status}, title={title!r})",
                file=sys.stderr,
            )
            print(f"    [paywall]   redirector: {proxied}", file=sys.stderr)
            print(f"    [paywall]   final URL:  {final_url}", file=sys.stderr)

            if debug:
                snapshot_dir = Path("/tmp/literature-search-debug")
                snapshot_dir.mkdir(parents=True, exist_ok=True)
                slug = re.sub(r"[^A-Za-z0-9]+", "_", doi)[:80]
                html_path = snapshot_dir / f"{slug}.html"
                png_path = snapshot_dir / f"{slug}.png"
                try:
                    if html:
                        html_path.write_text(html, encoding="utf-8")
                    page.screenshot(path=str(png_path), full_page=True)
                    print(
                        f"    [paywall]   saved {html_path} and {png_path}",
                        file=sys.stderr,
                    )
                except Exception as snap_err:
                    print(f"    [paywall]   snapshot failed: {snap_err}", file=sys.stderr)
                try:
                    input(
                        "    [paywall] page is open in browser — inspect, then press Enter "
                        "to continue (Ctrl-C to abort)... "
                    )
                except (EOFError, KeyboardInterrupt):
                    raise
    finally:
        try:
            page.close()
        except Exception:
            pass

    return abstract


def fetch_abstract_crossref(doi: str) -> str | None:
    enc = quote(doi, safe="")
    r = SESSION.get(f"{CROSSREF_WORKS}/{enc}", timeout=60)
    if r.status_code != 200:
        return None
    msg = r.json().get("message") or {}
    abstract = msg.get("abstract")
    if not abstract or not isinstance(abstract, str):
        return None
    text = strip_markup_to_text(abstract)
    text = re.sub(r"^abstract\s+", "", text.strip(), flags=re.I)
    return text.strip() or None


def resolve_doi_url(doi: str) -> str | None:
    """Follow doi.org redirects to the publisher landing page.

    Must override the session's `Accept: application/json`, otherwise doi.org
    content-negotiates and returns a Crossref API URL instead of the publisher page.
    """
    r = SESSION.get(
        f"https://doi.org/{quote(doi, safe='')}",
        headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
        allow_redirects=True,
        timeout=60,
    )
    if r.status_code >= 400:
        return None
    return r.url


def fetch_abstract_from_html(url: str) -> str | None:
    try:
        r = SESSION.get(url, timeout=60, allow_redirects=True)
    except requests.RequestException:
        return None
    if r.status_code >= 400 or not r.text:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    return _extract_abstract_from_soup(soup)


def fetch_abstract_paperscraper(doi: str) -> str | None:
    """Only runs if paperscraper is on PYTHONPATH / installed."""
    try:
        from paperscraper import PaperScraper  # type: ignore
    except ImportError:
        return None

    try:
        from paperscraper.aggregators.doi_aggregator import DOIAggregator  # type: ignore
    except ImportError:
        return None

    try:
        loc = DOIAggregator().extract(doi)
        landing = loc.get("l0")
    except Exception:
        return None
    if not landing:
        return None

    scraper = None
    try:
        scraper = PaperScraper()
        data = scraper.extract_from_url(landing)
        if not data:
            return None
        if isinstance(data, dict):
            ab = data.get("abstract")
            if isinstance(ab, str) and ab.strip():
                return ab.strip()
    except Exception:
        return None
    finally:
        if scraper is not None:
            try:
                scraper.driver.quit()
            except Exception:
                pass
    return None


def fetch_abstract(
    doi: str,
    api_key: str | None,
    use_paperscraper: bool,
    unpaywall_email: str | None,
    openathens_redirector: str | None,
    playwright_ctx=None,
    debug_paywall: bool = False,
) -> tuple[str | None, str]:
    """
    Returns (abstract_or_none, source_label).

    Order: Semantic Scholar → Crossref → PubMed → DOI landing-page HTML → Unpaywall OA copy
           → OpenAthens via Playwright (if logged in) → optional PaperScraper.
    """
    tried: list[str] = []

    tried.append("semantic_scholar")
    ab = fetch_abstract_semantic_scholar(doi, api_key)
    if ab:
        return ab, "semantic_scholar"

    tried.append("crossref")
    ab = fetch_abstract_crossref(doi)
    if ab:
        return ab, "crossref"

    tried.append("pubmed")
    ab = fetch_abstract_pubmed(doi)
    if ab:
        return ab, "pubmed"

    tried.append("landing_page_html")
    url = resolve_doi_url(doi)
    if url:
        ab = fetch_abstract_from_html(url)
        if ab:
            return ab, "landing_page_html"

    if unpaywall_email:
        tried.append("unpaywall")
        ab = fetch_abstract_unpaywall(doi, unpaywall_email)
        if ab:
            return ab, "unpaywall"

    if playwright_ctx and openathens_redirector:
        tried.append("openathens")
        ab = fetch_abstract_playwright(
            doi, openathens_redirector, playwright_ctx, debug=debug_paywall
        )
        if ab:
            return ab, "openathens"

    if use_paperscraper:
        tried.append("paperscraper")
        ab = fetch_abstract_paperscraper(doi)
        if ab:
            return ab, "paperscraper"

    final_url = url if url else "(could not resolve DOI)"
    print(
        f"    [diag] tried {', '.join(tried)} — none yielded an abstract. "
        f"DOI redirects to: {final_url}",
        file=sys.stderr,
    )
    return None, "none"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fill missing Abstract values using DOI (Semantic Scholar, then fallbacks)."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Spreadsheet path (.xls or .xlsx). Default: {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "--sheet",
        default=DEFAULT_SHEET,
        help=f"Worksheet name or 0-based index. Default: {DEFAULT_SHEET!r} (not the first sheet).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path (.xlsx). Default: <input stem>_abstracts_filled.xlsx",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Extra seconds to sleep after each row (Semantic Scholar is already limited to 1 req/s). Default: 0",
    )
    parser.add_argument(
        "--paperscraper",
        action="store_true",
        help="After Crossref, try PaperScraper (requires working paperscraper + Chrome/Selenium).",
    )
    parser.add_argument(
        "--playwright",
        action="store_true",
        help="Open Chrome via Playwright at start, prompt for RMIT OpenAthens login, "
             "then fetch paywalled landing pages through the OpenAthens redirector "
             "in that authenticated session.",
    )
    parser.add_argument(
        "--debug-paywall",
        action="store_true",
        help="When a Playwright/OpenAthens fetch fails, save HTML+screenshot to "
             "/tmp/literature-search-debug and pause with the page open for inspection.",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Always read from --input. By default, if a previously-filled output "
             "file exists, the script reads from that and overwrites it in place so "
             "re-runs skip already-filled rows.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List rows that would be updated without writing or calling APIs.",
    )
    args = parser.parse_args()

    inp = args.input.resolve()
    if not inp.is_file():
        print(f"Input not found: {inp}", file=sys.stderr)
        return 1

    # Determine output path first so we can decide whether to auto-resume from it.
    if args.output is not None:
        out = Path(args.output).resolve()
    elif inp.suffix.lower() == ".xlsx" and inp.stem.endswith("_abstracts_filled"):
        # User explicitly pointed at a previously-filled file → overwrite in place.
        out = inp
    else:
        out = inp.with_name(f"{inp.stem}_abstracts_filled.xlsx")

    # Auto-resume: if a filled output already exists alongside the original input,
    # read from it so already-filled rows are skipped (is_missing_abstract handles that).
    if not args.no_resume and out.is_file() and out.resolve() != inp.resolve():
        print(f"Resuming from {out} (pass --no-resume to start from {inp.name}).")
        inp = out.resolve()

    raw_sheet = args.sheet
    if isinstance(raw_sheet, str) and re.fullmatch(r"\d+", raw_sheet.strip()):
        sheet: str | int = int(raw_sheet.strip())
    else:
        sheet = raw_sheet

    try:
        df = _read_table(inp, sheet_name=sheet)
    except ValueError as e:
        print(f"Could not read sheet {sheet!r} from {inp}: {e}", file=sys.stderr)
        return 1

    out_sheet = sheet if isinstance(sheet, str) else f"sheet_{sheet}"
    out_sheet = str(out_sheet)[:31]
    abs_col = find_column(df, ["abstract"])
    doi_col = find_column(df, ["digitalobjectidentifier", "doi", "digital object identifier"])

    if not abs_col:
        print("Could not find an Abstract column.", file=sys.stderr)
        return 1
    if not doi_col:
        print("Could not find a DOI column (expected digitalObjectIdentifier or DOI).", file=sys.stderr)
        return 1

    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY") or os.getenv("S2_API_KEY")
    if api_key:
        print("Semantic Scholar: API key loaded; enforcing 1 request/s to api.semanticscholar.org.")
    else:
        print(
            "Semantic Scholar: no SEMANTIC_SCHOLAR_API_KEY — using unauthenticated limits; still 1 request/s.",
            file=sys.stderr,
        )

    unpaywall_email = os.getenv("UNPAYWALL_EMAIL")
    if unpaywall_email:
        print(f"Unpaywall: enabled (contact={unpaywall_email}).")
    else:
        print("Unpaywall: disabled (set UNPAYWALL_EMAIL to enable).", file=sys.stderr)

    openathens_redirector = os.getenv(
        "OPENATHENS_REDIRECTOR",
        "https://go.openathens.net/redirector/rmit.edu.au",
    )
    playwright_ctx = None
    playwright_pw = None
    playwright_browser = None
    playwright_state_file: Path | None = None
    if args.playwright:
        login_url = os.getenv("RMIT_LOGIN_URL", "https://my.openathens.net/")
        profile_dir = Path(
            os.getenv("CHROME_PROFILE_DIR")
            or (Path.home() / ".cache" / "literature-search" / "chrome-profile")
        ).expanduser()
        try:
            (
                playwright_pw,
                playwright_browser,
                playwright_ctx,
                playwright_state_file,
            ) = setup_playwright(login_url, profile_dir)
            print(
                f"Playwright: ready (state={playwright_state_file}, "
                f"redirector={openathens_redirector})."
            )
        except Exception as e:
            print(f"Playwright setup failed: {e}", file=sys.stderr)
            return 1
    else:
        print("OpenAthens: disabled (pass --playwright to enable).", file=sys.stderr)

    print(f"Worksheet: {sheet!r} ({len(df)} rows)")

    duplicate_to_primary, dup_count, dup_backfilled = deduplicate(df, doi_col, abs_col)
    print(
        f"Duplicates: marked {dup_count} row(s) as is_duplicate=Y; "
        f"backfilled {dup_backfilled} abstract(s) within duplicate groups."
    )

    missing_mask = df[abs_col].apply(is_missing_abstract)
    doi_norm = df[doi_col].apply(normalize_doi)
    has_doi = doi_norm.notna()
    not_dup = df[DUPLICATE_COL].fillna("").astype(str).str.upper() != "Y"
    skipped_no_doi = int((missing_mask & ~has_doi & not_dup).sum())
    skipped_dup = int((missing_mask & ~not_dup).sum())
    to_fix = df.loc[missing_mask & has_doi & not_dup].copy()
    extras = []
    if skipped_no_doi:
        extras.append(f"{skipped_no_doi} row(s) missing abstract but no DOI")
    if skipped_dup:
        extras.append(f"{skipped_dup} duplicate row(s) — will inherit from primary")
    print(
        f"Rows with missing abstract and a DOI (non-duplicates): {len(to_fix)} / {len(df)}"
        + (f" (skipped {'; '.join(extras)})" if extras else "")
    )
    print(f"Abstract column: {abs_col!r}, DOI column: {doi_col!r}")

    if args.dry_run:
        for idx, row in to_fix.iterrows():
            doi = normalize_doi(row[doi_col])
            print(f"  row {idx}: doi={doi!r}")
        return 0

    updates = 0
    failures: list[tuple[Any, str | None]] = []

    for idx, row in to_fix.iterrows():
        doi = normalize_doi(row[doi_col])
        if not doi:
            failures.append((idx, None))
            print(f"  row {idx}: skip — no DOI")
            time.sleep(args.delay)
            continue

        abstract, source = fetch_abstract(
            doi,
            api_key,
            use_paperscraper=args.paperscraper,
            unpaywall_email=unpaywall_email,
            openathens_redirector=openathens_redirector,
            playwright_ctx=playwright_ctx,
            debug_paywall=args.debug_paywall,
        )
        if abstract:
            df.at[idx, abs_col] = abstract
            updates += 1
            print(f"  row {idx}: OK ({source}) DOI {doi}")
        else:
            failures.append((idx, doi))
            print(f"  row {idx}: failed — DOI {doi}")

        time.sleep(args.delay)

    # Propagate newly-fetched primary abstracts to their duplicate rows.
    propagated = 0
    for dup_idx, primary_idx in duplicate_to_primary.items():
        if (
            is_missing_abstract(df.at[dup_idx, abs_col])
            and not is_missing_abstract(df.at[primary_idx, abs_col])
        ):
            df.at[dup_idx, abs_col] = df.at[primary_idx, abs_col]
            propagated += 1
    if propagated:
        print(f"Propagated {propagated} fetched abstract(s) to duplicate row(s).")

    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=out_sheet, index=False)
    print(f"Wrote {out} sheet {out_sheet!r} ({updates} abstracts filled).")

    if playwright_ctx is not None and playwright_state_file is not None:
        try:
            playwright_ctx.storage_state(path=str(playwright_state_file))
            print(f"Playwright: saved session state to {playwright_state_file}")
        except Exception as e:
            print(f"Playwright: state save failed ({e})", file=sys.stderr)
    if playwright_ctx is not None:
        try:
            playwright_ctx.close()
        except Exception:
            pass
    if playwright_browser is not None:
        try:
            playwright_browser.close()
        except Exception:
            pass
    if playwright_pw is not None:
        try:
            playwright_pw.stop()
        except Exception:
            pass

    if failures:
        print(f"Could not fill {len(failures)} row(s).")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
