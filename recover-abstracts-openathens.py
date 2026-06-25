"""Recover paywalled abstracts for the no-abstract snowball papers via RMIT
OpenAthens (institutional access), using Playwright.

WHY THIS IS A SEPARATE, USER-RUN SCRIPT:
OpenAthens needs an interactive RMIT login in a real Chrome window the first time
(the saved session expires after ~a couple of weeks). That login can't be driven
headlessly, so run this yourself in a terminal:

    poetry run python recover-abstracts-openathens.py

A Chrome window opens; log into RMIT OpenAthens when prompted, press Enter, and it
will grind through the paywalled DOIs, writing recovered abstracts back into
search-results-from-database/screened.csv and clearing Screen_Pass so they get
re-screened. It's resumable (re-run to continue) and checkpoints every 25 rows.

Note: this renders each publisher page in a real browser, so it's slow
(~1,800 papers ≈ a couple of hours). Set OA_LIMIT=N to cap it for a trial run.
"""
import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, os.getcwd())
import pandas as pd

# Reuse the battle-tested fetchers + interactive login from the standalone filler.
_spec = importlib.util.spec_from_file_location("filler", "fill-missing-abstracts-by-doi.py")
filler = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(filler)  # also loads .env

SCREENED = "search-results-from-database/screened.csv"
LIMIT = int(os.getenv("OA_LIMIT", "0")) or None


def main() -> int:
    redirector = os.getenv("OPENATHENS_REDIRECTOR", "https://go.openathens.net/redirector/rmit.edu.au")
    login_url = os.getenv("RMIT_LOGIN_URL", "https://my.openathens.net/")
    profile_dir = Path(
        os.getenv("CHROME_PROFILE_DIR")
        or (Path.home() / ".cache" / "literature-search" / "chrome-profile")
    ).expanduser()

    scr = pd.read_csv(SCREENED, dtype=str).fillna("")
    todo = [
        (i, filler.normalize_doi(scr.at[i, "DOI"]))
        for i in scr.index
        if scr.at[i, "Screen_Reason"] == "no_abstract" and filler.normalize_doi(scr.at[i, "DOI"])
    ]
    if LIMIT:
        todo = todo[:LIMIT]
    print(f"OpenAthens recovery: {len(todo)} no-abstract papers with a DOI\n")

    # Interactive login (opens Chrome; reuses saved session if still valid).
    pw, browser, ctx, state_file = filler.setup_playwright(login_url, profile_dir)
    rec = 0
    try:
        for n, (i, doi) in enumerate(todo, 1):
            try:
                ab = filler.fetch_abstract_playwright(doi, redirector, ctx, debug=False)
            except Exception as e:  # noqa: BLE001
                print(f"  row {i}: error {e}", file=sys.stderr)
                ab = None
            if ab and len(ab) > 60:
                scr.at[i, "Abstract"] = ab
                scr.at[i, "Screen_Pass"] = ""    # clear so it gets re-screened
                scr.at[i, "Screen_Reason"] = ""
                rec += 1
                print(f"  row {i}: OK  {doi}")
            if n % 25 == 0:
                scr.to_csv(SCREENED, index=False)
                print(f"  [{n}/{len(todo)}] recovered {rec}; checkpoint saved", flush=True)
        scr.to_csv(SCREENED, index=False)
        print(f"\nOpenAthens done: recovered {rec}/{len(todo)} abstracts -> {SCREENED}")
        print("Next: re-run screen-snowball.py then classify-snowball.py to fold these in.")
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
