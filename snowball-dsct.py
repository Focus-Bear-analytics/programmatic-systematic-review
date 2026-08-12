"""Targeted snowball off the DSCT review (10.1145/3571810): pull its referenced
works (backward) + citing works (forward), dedupe against the existing corpus,
and screen the genuinely-new papers for the gating criteria (neurotype / adult /
digital intervention / empirical) to surface any missed AuDHD-adult candidates.
Writes citation-scraping/dsct_citations.csv and dsct_screened.csv.
"""
import os, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv(override=True)
import requests, pandas as pd
from steps.config import load_config, set_active
from steps import llm
from steps.io import normalize_doi

SEED_DOI = "10.1145/3571810"
MAILTO = os.getenv("OPENALEX_MAILTO") or "s3255727@student.rmit.edu.au"
BASE = "https://api.openalex.org"
SEL = "id,title,abstract_inverted_index,publication_year,doi,authorships,primary_location,ids"

def oa(path, params):
    for a in range(8):
        r = requests.get(f"{BASE}/{path}", params={**params, "mailto": MAILTO}, timeout=60)
        if r.status_code == 200: return r.json()
        time.sleep(min(2**a, 30))
    return None

def abstract(inv):
    if not inv: return ""
    pos = sorted((i, w) for w, idxs in inv.items() for i in idxs)
    return " ".join(w for _, w in pos)

def row(w):
    ids = w.get("ids") or {}
    return {"Title": w.get("title") or "", "Abstract": abstract(w.get("abstract_inverted_index")),
            "Authors": ", ".join((a.get("author") or {}).get("display_name","") for a in (w.get("authorships") or [])),
            "Year": w.get("publication_year") or "", "DOI": (w.get("doi") or "").replace("https://doi.org/",""),
            "PMID": (ids.get("pmid") or "").rsplit("/",1)[-1],
            "Journal": ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or "",
            "URL": w.get("id") or ""}

def short(i): return (i or "").rsplit("/",1)[-1]

# 1) seed work
seed = oa(f"works/https://doi.org/{SEED_DOI}", {"select": "id,referenced_works,title"})
sid = short(seed["id"])
print(f"SEED: {seed['title'][:70]}  ({sid})", flush=True)

# 2) backward: referenced works
refs = [short(r) for r in (seed.get("referenced_works") or [])]
rows = []
for i in range(0, len(refs), 50):
    d = oa("works", {"filter": f"openalex_id:{'|'.join(refs[i:i+50])}", "select": SEL, "per-page": 50})
    if d: rows += [{**row(w), "snowball_dir": "backward"} for w in d.get("results", [])]
    time.sleep(0.2)
print(f"backward refs: {len(rows)}", flush=True)

# 3) forward: citing works
cur = "*"; fwd = []
while cur:
    d = oa("works", {"filter": f"cites:{sid}", "select": SEL, "per-page": 200, "cursor": cur})
    if not d: break
    fwd += [{**row(w), "snowball_dir": "forward"} for w in d.get("results", [])]
    cur = (d.get("meta") or {}).get("next_cursor")
    time.sleep(0.2)
print(f"forward citing: {len(fwd)}", flush=True)
rows += fwd

# 4) dedupe vs existing corpus + within
def nd(d): return normalize_doi(d) or ""
def nt(t): import re; return re.sub(r"[^a-z0-9 ]"," ",str(t).lower()).strip()
corpus = pd.read_csv("search-results-from-database/combined/adjudicated.csv", dtype=str).fillna("")
seen_doi = {nd(d) for d in corpus["DOI"] if nd(d)}
seen_title = {nt(t) for t in corpus["Title"] if str(t).strip()}
new, dup = [], 0
seen_local = set()
for r in rows:
    k = nd(r["DOI"]) or nt(r["Title"])
    if not k or k in seen_local: continue
    seen_local.add(k)
    if (nd(r["DOI"]) and nd(r["DOI"]) in seen_doi) or nt(r["Title"]) in seen_title:
        dup += 1; continue
    new.append(r)
print(f"unique new (not already in corpus): {len(new)}  | dropped {dup} dups", flush=True)
ndf = pd.DataFrame(new)
os.makedirs("citation-scraping", exist_ok=True)
ndf.to_csv("citation-scraping/dsct_citations.csv", index=False)

# 5) screen the new ones (one combined gating pass, Sonnet)
cfg = load_config("adults"); set_active(cfg); rater = cfg.rater_b; llm.warm(rater)
SYS = """Screen a paper for a systematic review of DIGITAL app-based interventions for ADULTS with co-occurring ADHD AND autism (AuDHD), targeting attention/executive-function/emotional-regulation.
Return ONLY JSON: {"neurotype":"adhd|autistic|audhd|neither","has_adults":"yes|no|unclear","is_digital_intervention":"yes|no","is_empirical_eval":"yes|no","note":"<=12 words"}
- neurotype = the studied population's diagnosis (audhd only if co-occurring in same people).
- has_adults = adults (18+) are direct study subjects.
- is_digital_intervention = evaluates a digital/app/software/online tool as an intervention.
- is_empirical_eval = reports an empirical evaluation with outcomes (not a review/opinion)."""
def scr(r):
    try:
        d = llm.invoke_json(rater, system_prompt=SYS,
            user_prompt=f"Title: {r['Title']}\n\nAbstract: {r['Abstract'][:2500]}", temperature=0, max_tokens=150)
        return d
    except Exception as e:
        return {"note": f"err {e}"}
res = [None]*len(new)
with ThreadPoolExecutor(max_workers=8) as p:
    futs = {p.submit(scr, r): i for i, r in enumerate(new) if r["Abstract"].strip()}
    for f in as_completed(futs):
        res[futs[f]] = f.result()
for i, d in enumerate(res):
    for k in ("neurotype","has_adults","is_digital_intervention","is_empirical_eval","note"):
        ndf.at[i, k] = (d or {}).get(k, "")
ndf.to_csv("citation-scraping/dsct_screened.csv", index=False)

# candidates: neurotype relevant + adults + digital + empirical
cand = ndf[(ndf.neurotype.isin(["adhd","autistic","audhd"])) & (ndf.has_adults.isin(["yes","unclear"]))
          & (ndf.is_digital_intervention=="yes") & (ndf.is_empirical_eval=="yes")]
print(f"\nscreened {sum(1 for x in res if x)} with abstracts")
print("neurotype mix:", ndf.neurotype.value_counts().to_dict())
print(f"\n=== CANDIDATES (relevant neurotype + adult + digital + empirical): {len(cand)} ===")
for _, r in cand.iterrows():
    print(f"  [{r.neurotype}/{r.has_adults}] {r.Year} {r.Title[:62]}  ({r.note})")
print("\nwrote citation-scraping/dsct_screened.csv")
