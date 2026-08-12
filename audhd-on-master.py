"""Run AuDHD detection on every fulltext_review_master.csv candidate that has a
full-text file but no AuDHD label yet. Two-stage: regex co-mention pre-filter ->
LLM excerpt verification (Sonnet). Writes audhd/adult_audhd back to the master.
"""
import os, re, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv(override=True)
import pandas as pd
from steps.config import load_config, set_active
from steps import llm

MASTER = "search-results-from-database/fulltext_review_master.csv"
TEXT = "full_text_snowball"
AUTISM = re.compile(r"\b(autis\w*|asd|asperger|pervasive developmental)\b", re.I)
ADHD = re.compile(r"\b(adhd|a\.d\.h\.d|attention[- ]deficit|hyperkinetic)\b", re.I)
SYSTEM = """You determine, from excerpts of a study's full text, whether the STUDY SAMPLE includes participants with CO-OCCURRING ADHD AND autism (AuDHD) — either the whole sample, or an identifiable subgroup the study reports on.
- "audhd"=yes only if the SAME participants are described as having both ADHD and autism. Two separate single-diagnosis groups -> "no". Background mentions -> "no". "unclear" if implied but not stated.
- adult_audhd="yes" if those co-occurring participants include adults (18+); "no" if only children; "unclear" otherwise.
Return ONLY: {"reasoning":"<1-2 sentences citing the text>","audhd":"yes|no|unclear","adult_audhd":"yes|no|unclear","evidence":"<short quote or ''>"}"""

def excerpt(t, limit=9000):
    head = t[:3000]; wins = []
    for m in ADHD.finditer(t):
        s = max(0, m.start()-400); e = min(len(t), m.end()+400)
        if AUTISM.search(t[s:e]): wins.append(t[s:e])
        if sum(len(w) for w in wins) > limit-3000: break
    return (head + "\n...\n" + "\n...\n".join(wins[:12]))[:limit]

cfg = load_config("adults"); set_active(cfg); rater = cfg.rater_b
m = pd.read_csv(MASTER, dtype=str).fillna("")
todo = [i for i in m.index
        if str(m.at[i, "audhd"]).strip() == ""
        and os.path.exists(os.path.join(TEXT, str(m.at[i, "full_text_filename"]).replace(".pdf", ".txt")))]
print(f"{len(todo)} candidates with text + no AuDHD label", flush=True)
llm.warm(rater)

def do(i):
    p = os.path.join(TEXT, str(m.at[i, "full_text_filename"]).replace(".pdf", ".txt"))
    t = open(p, encoding="utf-8").read()
    if not (AUTISM.search(t) and ADHD.search(t)):
        return i, {"audhd": "no", "adult_audhd": "no", "evidence": "", "reasoning": "no ADHD+autism co-mention"}
    try:
        r = llm.invoke_json(rater, system_prompt=SYSTEM, user_prompt=excerpt(t), temperature=0, max_tokens=500)
    except Exception as e:
        print(f"  [{i}] err {e}", flush=True); return None
    return i, r

done = 0
with ThreadPoolExecutor(max_workers=8) as pool:
    for fut in as_completed([pool.submit(do, i) for i in todo]):
        res = fut.result()
        if not res: continue
        i, r = res
        m.at[i, "audhd"] = r.get("audhd", ""); m.at[i, "adult_audhd"] = r.get("adult_audhd", "")
        done += 1
m.to_csv(MASTER, index=False)
yes = int((m["audhd"] == "yes").sum()); adult = int((m["adult_audhd"] == "yes").sum())
print(f"labelled {done} | AuDHD=yes total: {yes} | adult-AuDHD total: {adult}", flush=True)
