"""Recall-safe re-screen of the DSCT snowball papers, matching the main review's
standard: backfill missing abstracts, screen with BOTH raters, allow 'unspecified',
and EXCLUDE only when both raters agree on a clearly-excluding value. Everything
else is REFERRED to full-text review. Writes dsct_recallsafe.csv + dsct_refer_fulltext.csv.
"""
import os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv(override=True)
import pandas as pd
from steps.config import load_config, set_active
from steps import llm
from steps.io import is_missing_abstract
from steps import abstract_fetcher as af

df = pd.read_csv("citation-scraping/dsct_citations.csv", dtype=str).fillna("")
print(f"{len(df)} DSCT snowball papers", flush=True)

# 1) backfill missing abstracts (Europe PMC -> Crossref -> PubMed)
miss = [i for i in df.index if is_missing_abstract(df.at[i, "Abstract"])]
print(f"backfilling {len(miss)} missing abstracts...", flush=True)
def backfill(i):
    doi = df.at[i, "DOI"].strip(); pmid = df.at[i, "PMID"].strip()
    for fn in (lambda: af.fetch_europepmc(doi=doi or None, pmid=pmid or None),
               lambda: af.fetch_crossref(doi) if doi else None,
               lambda: af.fetch_pubmed(doi) if doi else None):
        try:
            a = fn()
            if a and len(a) > 40: return i, a
        except Exception: pass
    return i, ""
with ThreadPoolExecutor(max_workers=8) as p:
    for f in as_completed([p.submit(backfill, i) for i in miss]):
        i, a = f.result()
        if a: df.at[i, "Abstract"] = a
got = sum(1 for i in miss if not is_missing_abstract(df.at[i, "Abstract"]))
print(f"  recovered {got}/{len(miss)} abstracts", flush=True)

# 2) two-rater recall-safe screen
cfg = load_config("adults"); set_active(cfg)
ra, rb = cfg.rater_a, cfg.rater_b
for r in (ra, rb): llm.warm(r)
SYS = """Screen a paper for a systematic review of DIGITAL app-based interventions for ADULTS with co-occurring ADHD AND autism (AuDHD), targeting attention/executive-function/emotional-regulation.
Use "unspecified" whenever the abstract does not give enough information to decide — do NOT guess "no"/"neither".
Return ONLY JSON: {"neurotype":"adhd|autistic|audhd|neither|unspecified","has_adults":"yes|no|unspecified","is_digital_intervention":"yes|no|unspecified","is_empirical_eval":"yes|no|unspecified","note":"<=12 words"}
- neurotype: studied population's diagnosis. "neither" ONLY if the population is clearly stated as not ADHD/not autistic (e.g. general public, students, other condition). "unspecified" if diagnosis not stated.
- has_adults: adults (18+) are direct study subjects.
- is_digital_intervention: evaluates a digital/app/software/online tool as an intervention.
- is_empirical_eval: reports an empirical evaluation with outcomes (not a review/opinion/design paper)."""
KEYS = ["neurotype","has_adults","is_digital_intervention","is_empirical_eval","note"]
def ask(rater, i):
    try:
        return llm.invoke_json(rater, system_prompt=SYS,
            user_prompt=f"Title: {df.at[i,'Title']}\n\nAbstract: {df.at[i,'Abstract'][:2800] or '(none)'}",
            temperature=0, max_tokens=150)
    except Exception as e:
        return {"note": f"err {e}"}
def do(i):
    return i, ask(ra, i), ask(rb, i)
todo = list(df.index)
with ThreadPoolExecutor(max_workers=8) as p:
    for f in as_completed([p.submit(do, i) for i in todo]):
        i, a, b = f.result()
        for k in KEYS:
            df.at[i, f"A_{k}"] = (a or {}).get(k, ""); df.at[i, f"B_{k}"] = (b or {}).get(k, "")

# 3) recall-safe gate: exclude ONLY if both raters agree on an excluding value
def both(field, val): return lambda i: df.at[i, f"A_{field}"] == val and df.at[i, f"B_{field}"] == val
EXCL = [("neurotype","neither"), ("has_adults","no"), ("is_digital_intervention","no"), ("is_empirical_eval","no")]
def decide(i):
    reasons = [f"{f}=both_{v}" for f, v in EXCL if both(f, v)(i)]
    return ("exclude", ";".join(reasons)) if reasons else ("refer_fulltext", "")
df["screen"] = [decide(i)[0] for i in df.index]
df["screen_reason"] = [decide(i)[1] for i in df.index]
df["no_abstract"] = [is_missing_abstract(df.at[i,"Abstract"]) for i in df.index]
df.to_csv("citation-scraping/dsct_recallsafe.csv", index=False)
refer = df[df.screen == "refer_fulltext"]
refer.to_csv("citation-scraping/dsct_refer_fulltext.csv", index=False)

print(f"\nscreen: {df.screen.value_counts().to_dict()}")
print(f"referred-to-fulltext with NO abstract (can't exclude): {int(refer.no_abstract.sum())}")
print(f"\n=== REFERRED TO FULL TEXT: {len(refer)} ===")
for _, r in refer.iterrows():
    print(f"  [{r.A_neurotype}/{r.B_neurotype} | ad {r.A_has_adults}/{r.B_has_adults} | dig {r.A_is_digital_intervention}/{r.B_is_digital_intervention}] {r.Year} {r.Title[:55]}")
print("\nwrote citation-scraping/dsct_refer_fulltext.csv")
