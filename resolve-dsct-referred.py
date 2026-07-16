"""Resolve the 28 referred DSCT papers: drop obvious non-studies (books/theory),
retrieve open full text for the plausible empirical digital-intervention studies,
and run a population/AuDHD check on each. Writes dsct_resolved.csv.
"""
import os, sys, re
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv(override=True)
import pandas as pd
from steps.config import load_config, set_active
from steps import llm
from steps.full_text import fetch_open_full_text

EMAIL = os.getenv("UNPAYWALL_EMAIL") or "s3255727@student.rmit.edu.au"
df = pd.read_csv("citation-scraping/dsct_refer_fulltext.csv", dtype=str).fillna("")
print(f"{len(df)} referred papers", flush=True)
cfg = load_config("adults"); set_active(cfg); ra, rb = cfg.rater_a, cfg.rater_b
for r in (ra, rb): llm.warm(r)

# 1) gate: is this an empirical study evaluating a digital intervention with human participants?
GATE = """Is this an EMPIRICAL STUDY that evaluates a digital/software/app intervention with HUMAN PARTICIPANTS and reports outcomes? Books, theoretical/conceptual papers, essays, opinion, reviews, scale-validation, and pure design papers are NOT. Return ONLY: {"is_study":"yes|no","reason":"<=12 words"}"""
def gate(i):
    try:
        d = llm.invoke_json(rb, system_prompt=GATE,
            user_prompt=f"Title: {df.at[i,'Title']}\n\nAbstract: {df.at[i,'Abstract'][:2000] or '(none)'}",
            temperature=0, max_tokens=80)
        return i, d.get("is_study",""), d.get("reason","")
    except Exception as e:
        return i, "yes", f"gate-err {e}"  # recall-safe: keep on error
with ThreadPoolExecutor(max_workers=8) as p:
    for f in as_completed([p.submit(gate, i) for i in df.index]):
        i, s, why = f.result(); df.at[i,"is_study"]=s; df.at[i,"gate_reason"]=why

studies = df[df.is_study=="yes"].index.tolist()
print(f"plausible empirical studies: {len(studies)} (dropped {len(df)-len(studies)} non-studies)", flush=True)

# 2) retrieve open full text for the studies
def ft(i):
    try:
        txt, src = fetch_open_full_text(df.at[i,"DOI"] or None, df.at[i,"PMID"] or None, EMAIL)
        return i, (txt or ""), src
    except Exception as e:
        return i, "", f"err {e}"
with ThreadPoolExecutor(max_workers=6) as p:
    for f in as_completed([p.submit(ft, i) for i in studies]):
        i, txt, src = f.result()
        df.at[i,"ft_source"]=src; df.at[i,"ft_chars"]=str(len(txt))
        if txt: df.at[i,"_ft"]=txt[:14000]
got = sum(1 for i in studies if df.at[i,"ft_chars"] not in ("","0"))
print(f"full text retrieved: {got}/{len(studies)}", flush=True)

# 3) population / AuDHD check (full text if available, else abstract)
POP = """Determine the STUDY POPULATION for inclusion in a review of adults with co-occurring ADHD AND autism (AuDHD).
Return ONLY: {"neurotype":"adhd|autistic|audhd|neither|unspecified","has_adults":"yes|no|unspecified","audhd":"yes|no|unclear","note":"<=15 words"}
- neurotype: diagnosis of the enrolled participants. "neither" if clearly general/non-clinical or a different condition. "unspecified" if not stated.
- audhd: "yes" only if the SAME participants have BOTH ADHD and autism."""
def pop(i):
    ftxt = str(df.at[i,"_ft"]) if ("_ft" in df.columns and pd.notna(df.at[i,"_ft"]) and str(df.at[i,"_ft"]).strip()) else ""
    ev = ftxt if ftxt else f"Abstract: {df.at[i,'Abstract'][:3000]}"
    try:
        d = llm.invoke_json(rb, system_prompt=POP, user_prompt=f"Title: {df.at[i,'Title']}\n\n{ev}",
                            temperature=0, max_tokens=150)
        return i, d
    except Exception as e:
        return i, {"note": f"err {e}"}
with ThreadPoolExecutor(max_workers=8) as p:
    for f in as_completed([p.submit(pop, i) for i in studies]):
        i, d = f.result()
        for k in ("neurotype","has_adults","audhd","note"): df.at[i, f"pop_{k}"]=d.get(k,"")

if "_ft" in df.columns: df = df.drop(columns=["_ft"])
df.to_csv("citation-scraping/dsct_resolved.csv", index=False)
res = df[df.is_study=="yes"]
print(f"\npopulation neurotype mix (studies): {res.pop_neurotype.value_counts().to_dict()}")
hits = res[(res.pop_neurotype.isin(['adhd','autistic','audhd'])) | (res.pop_audhd=='yes')]
print(f"\n=== any ADHD/autistic/AuDHD population? : {len(hits)} ===")
for _,r in hits.iterrows():
    print(f"  [{r.pop_neurotype}/audhd={r.pop_audhd}/adults={r.pop_has_adults}] {r.Year} {r.Title[:55]} ({r.ft_source},{r.ft_chars}c)")
print("\n=== studies, full result ===")
for _,r in res.iterrows():
    print(f"  {r.pop_neurotype:<12} ad={r.pop_has_adults:<11} ft={r.ft_source or '-':<10} {r.Year} {r.Title[:48]}")
print("\nwrote citation-scraping/dsct_resolved.csv")
