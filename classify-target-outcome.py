"""Classify the target OUTCOME of each candidate intervention (multi-label:
attention / executive_function / emotional_regulation / other) with two raters,
and flag whether it's in scope (targets >=1 of the three review outcomes).
Writes target_raterA / target_raterB / outcome_in_scope to the master.
"""
import os, sys, json
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv(override=True)
import pandas as pd
from steps.config import load_config, set_active
from steps import llm

MASTER = "search-results-from-database/fulltext_review_master.csv"
THREE = {"attention", "executive_function", "emotional_regulation"}
ALLOWED = THREE | {"other"}
SYSTEM = """You identify which outcome(s) a study's intervention is designed to TARGET / improve. Choose ALL that apply from:
- attention: sustained/selective attention, focus, on-task behaviour, distractibility, vigilance.
- executive_function: working memory, planning, organisation, inhibition/impulse control, task-switching, cognitive flexibility, self-regulation of cognition/behaviour, time management.
- emotional_regulation: managing emotions, anxiety, stress, mood, frustration tolerance, emotional self-control.
- other: any other target — communication, social skills, employment/vocational, leisure, motor, academic content, daily living, sleep, etc.
Judge the intervention's PRIMARY aim(s). If it targets attention/EF/emotion-regulation, include that label even if "other" also applies.
Return ONLY: {"reasoning":"<1 sentence>","targets":["..."]}"""

cfg = load_config("adults"); set_active(cfg)
ra, rb = cfg.rater_a, cfg.rater_b
m = pd.read_csv(MASTER, dtype=str).fillna("")
# abstracts live in the combined dataset, not the master — join by normalised DOI
from steps.io import normalize_doi
def nd(d): return normalize_doi(d) or ""
comb = pd.read_csv("search-results-from-database/combined/adjudicated.csv", dtype=str).fillna("")
AMAP = {nd(r["DOI"]): r.get("Abstract", "") for r in comb.to_dict("records") if nd(r["DOI"])}
for c in ("target_raterA", "target_raterB", "outcome_in_scope"):
    if c not in m.columns: m[c] = ""
for r in (ra, rb): llm.warm(r)

def targets(rater, title, ab, det):
    raw = llm.invoke_json(rater, system_prompt=SYSTEM,
        user_prompt=f"Title: {title}\n\nAbstract: {ab}\n\nIntervention: {det}", temperature=0, max_tokens=300)
    t = raw.get("targets", [])
    t = [t] if isinstance(t, str) else (t or [])
    return sorted({str(x).strip().lower().replace(" ", "_") for x in t} & ALLOWED)

def get_ab(i):
    ab = AMAP.get(nd(str(m.at[i, "DOI"])), "")
    if ab.strip(): return ab
    # fall back to full text (first 4k chars) when no abstract
    p = os.path.join("full_text_snowball", str(m.at[i, "full_text_filename"]).replace(".pdf", ".txt"))
    return open(p, encoding="utf-8").read()[:4000] if os.path.exists(p) else ""

def do(i):
    try:
        ab = get_ab(i)
        a = targets(ra, str(m.at[i, "Title"]), ab, str(m.at[i, "intervention_type"]))
        b = targets(rb, str(m.at[i, "Title"]), ab, str(m.at[i, "intervention_type"]))
    except Exception as e:
        print(f"  [{i}] err {e}", flush=True); return None
    return i, a, b

done = 0
with ThreadPoolExecutor(max_workers=8) as pool:
    for fut in as_completed([pool.submit(do, i) for i in m.index]):
        res = fut.result()
        if not res: continue
        i, a, b = res
        ain, bin_ = bool(set(a) & THREE), bool(set(b) & THREE)
        m.at[i, "target_raterA"] = ";".join(a); m.at[i, "target_raterB"] = ";".join(b)
        m.at[i, "outcome_in_scope"] = "yes" if (ain and bin_) else ("no" if (not ain and not bin_) else "review")
        done += 1
m.to_csv(MASTER, index=False)
vc = m["outcome_in_scope"].value_counts().to_dict()
print(f"classified {done} | outcome_in_scope: {vc}")
