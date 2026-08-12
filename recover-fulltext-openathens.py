"""Retrieve PAYWALLED full text for the snowball candidates via RMIT OpenAthens
(Playwright), filling in what the open-access pass (fetch-snowball-fulltext.py)
couldn't reach.

WHY THIS IS A SEPARATE, USER-RUN SCRIPT:
OpenAthens needs an interactive RMIT login in a real Chrome window the first time
(the saved session expires after ~a couple of weeks). Run it yourself:

    poetry run python recover-fulltext-openathens.py

A Chrome window opens; log into RMIT OpenAthens when prompted, press Enter, and it
grinds through the paywalled candidates, rendering each authenticated publisher
page and saving the extracted full text to full_text_snowball/<id>.txt. It then
flips ft_status paywalled -> retrieved (source=openathens) in
snowball/fulltext_candidates.csv. Resumable + checkpointed. Slow (real browser).

After it runs:  poetry run python classify-snowball-audhd.py
to fold the newly-retrieved texts into the AuDHD detection.

Env: OA_LIMIT=N caps the run for a trial. CHROME_PROFILE_DIR / OPENATHENS_REDIRECTOR
/ RMIT_LOGIN_URL as per the abstract OpenAthens script.
"""
import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, os.getcwd())
import pandas as pd
from bs4 import BeautifulSoup

from steps.full_text import _html_to_text, MIN_FULL_TEXT_CHARS

# Reuse the interactive login + OpenAthens redirect/DOI primitives from the filler.
_spec = importlib.util.spec_from_file_location("filler", "fill-missing-abstracts-by-doi.py")
filler = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(filler)  # also loads .env

CAND = "search-results-from-database/snowball/fulltext_candidates.csv"
TEXT_DIR = "full_text_snowball"
LIMIT = int(os.getenv("OA_LIMIT", "0")) or None
os.makedirs(TEXT_DIR, exist_ok=True)


def render_full_text(doi: str, redirector_base: str, ctx) -> str | None:
    """Render the OpenAthens-proxied publisher page in the authenticated context
    and return its main body text (full article when entitled)."""
    landing = filler.resolve_doi_url(doi)
    if not landing:
        return None
    proxied = filler._openathens_redirect(landing, redirector_base)
    page = ctx.new_page()
    try:
        try:
            page.goto(proxied, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            return None
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        try:
            html = page.content()
        except Exception:
            return None
        if not html:
            return None
        text = _html_to_text(html)
        return text if text and len(text) >= MIN_FULL_TEXT_CHARS else None
    finally:
        try:
            page.close()
        except Exception:
            pass


def main() -> int:
    redirector = os.getenv("OPENATHENS_REDIRECTOR", "https://go.openathens.net/redirector/rmit.edu.au")
    login_url = os.getenv("RMIT_LOGIN_URL", "https://my.openathens.net/")
    profile_dir = Path(
        os.getenv("CHROME_PROFILE_DIR")
        or (Path.home() / ".cache" / "literature-search" / "chrome-profile")
    ).expanduser()

    cand = pd.read_csv(CAND, dtype=str).fillna("")
    todo = [
        i for i in cand.index
        if cand.at[i, "ft_status"] == "paywalled" and filler.normalize_doi(cand.at[i, "DOI"])
    ]
    if LIMIT:
        todo = todo[:LIMIT]
    print(f"OpenAthens full text: {len(todo)} paywalled candidates with a DOI\n", flush=True)
    if not todo:
        print("Nothing to do — no paywalled candidates remain.")
        return 0

    pw, browser, ctx, state_file = filler.setup_playwright(login_url, profile_dir)
    rec = 0
    try:
        for n, i in enumerate(todo, 1):
            doi = filler.normalize_doi(cand.at[i, "DOI"])
            fidv = cand.at[i, "fulltext_id"]
            path = os.path.join(TEXT_DIR, f"{fidv}.txt")
            try:
                text = render_full_text(doi, redirector, ctx)
            except Exception as e:  # noqa: BLE001
                print(f"  row {i}: error {e}", file=sys.stderr)
                text = None
            if text:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)
                cand.at[i, "ft_status"] = "retrieved"
                cand.at[i, "ft_source"] = "openathens"
                cand.at[i, "ft_chars"] = len(text)
                rec += 1
                print(f"  row {i}: OK  {doi}  ({len(text)} chars)")
            if n % 25 == 0:
                cand.to_csv(CAND, index=False)
                print(f"  [{n}/{len(todo)}] retrieved {rec}; checkpoint saved", flush=True)
        cand.to_csv(CAND, index=False)
        print(f"\nOpenAthens done: retrieved {rec}/{len(todo)} -> {CAND}")
        print("Next: poetry run python classify-snowball-audhd.py")
    finally:
        try:
            ctx.storage_state(path=str(state_file))
        except Exception:
            pass
        for closer in (ctx.close, browser.close, pw.stop):
            try:
                closer()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
