"""Classify study DESIGN rigour for the in-scope candidates, to apply the
controlled-design inclusion criterion. Two raters, full text where available.
Writes design_raterA / design_raterB / design_class to the master.
"""
import os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv(override=True)
import pandas as pd
from steps.config import load_config, set_active
from steps import llm
from steps.io import normalize_doi

MASTER = "search-results-from-database/fulltext_review_master.csv"
TEXT = "full_text_snowball"
ALLOWED = {"rct", "controlled_nonrandomized", "single_case_experimental",
           "uncontrolled_prepost", "case_study_series", "qualitative_only",
           "review_editorial", "conference_abstract", "other"}
SYSTEM = """You classify a study's RESEARCH DESIGN into exactly ONE category:
- rct: randomised controlled trial — participants randomly allocated to >=2 groups/conditions.
- controlled_nonrandomized: has a separate control/comparison GROUP or condition but allocation not randomised (quasi-experimental, non-randomised controlled, waitlist without randomisation, between-groups comparison).
- single_case_experimental: single-case/small-n EXPERIMENTAL design with phases providing experimental control — multiple-baseline, ABAB/withdrawal/reversal, alternating-treatments, changing-criterion. (Has within-subject experimental control but NO separate control group.)
- uncontrolled_prepost: single-arm pre-post / one-group before-after with NO comparator and NO single-case experimental control.
- case_study_series: descriptive report of one or a few cases with no experimental manipulation or control.
- qualitative_only: only qualitative data (interviews, themes), no quantitative outcome evaluation.
- review_editorial: review, meta-analysis, protocol, proposal, commentary, editorial, theoretical paper.
- conference_abstract: conference abstract/poster with no full paper.
- other: none of the above / cannot tell.
Judge the ACTUAL design used to evaluate the intervention. Return ONLY: {"reasoning":"<1 sentence>","design":"<one category>"}"""

cfg = load_config("adults"); set_active(cfg)
ra, rb = cfg.rater_a, cfg.rater_b
m = pd.read_csv(MASTER, dtype=str).fillna("")
def nd(d): return normalize_doi(d) or ""
comb = pd.read_csv("search-results-from-database/combined/adjudicated.csv", dtype=str).fillna("")
AMAP = {nd(r["DOI"]): r.get("Abstract", "") for r in comb.to_dict("records") if nd(r["DOI"])}
for c in ("design_raterA", "design_raterB", "design_class"):
    if c not in m.columns: m[c] = ""
for r in (ra, rb): llm.warm(r)

# only the in-scope candidates (outcome filter passed or pending)
todo = [i for i in m.index if str(m.at[i, "outcome_in_scope"]) in ("yes", "review")]
print(f"{len(todo)} in-scope candidates to classify for design", flush=True)

def evidence(i):
    p = os.path.join(TEXT, str(m.at[i, "full_text_filename"]).replace(".pdf", ".txt"))
    if os.path.exists(p):
        t = open(p, encoding="utf-8").read()
        return t[:12000]  # full text: methods usually within first chunk
    return f"Abstract: {AMAP.get(nd(str(m.at[i, 'DOI'])), '')}"

def design(rater, title, ev):
    raw = llm.invoke_json(rater, system_prompt=SYSTEM,
        user_prompt=f"Title: {title}\n\n{ev}", temperature=0, max_tokens=300)
    d = str(raw.get("design", "")).strip().lower().replace(" ", "_")
    return d if d in ALLOWED else "other"

def do(i):
    try:
        ev = evidence(i)
        return i, design(ra, str(m.at[i, "Title"]), ev), design(rb, str(m.at[i, "Title"]), ev)
    except Exception as e:
        print(f"  [{i}] err {e}", flush=True); return None

CONTROLLED = {"rct", "controlled_nonrandomized"}
done = 0
with ThreadPoolExecutor(max_workers=8) as pool:
    for fut in as_completed([pool.submit(do, i) for i in todo]):
        res = fut.result()
        if not res: continue
        i, a, b = res
        m.at[i, "design_raterA"] = a; m.at[i, "design_raterB"] = b
        if a == b:
            m.at[i, "design_class"] = a
        elif a in CONTROLLED or b in CONTROLLED or "single_case_experimental" in (a, b):
            m.at[i, "design_class"] = "review"  # disagreement that could affect inclusion
        else:
            m.at[i, "design_class"] = "review"
        done += 1
m.to_csv(MASTER, index=False)
ins = m[m.outcome_in_scope.isin(["yes", "review"])]
print(f"classified {done}")
print("design_class:", ins.design_class.value_counts().to_dict())
