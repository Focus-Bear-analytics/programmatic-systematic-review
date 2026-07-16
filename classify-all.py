"""Unified re-classification of ALL 78 master candidates from FULL TEXT (abstract
fallback), with the tuned prompts: target outcome, design rigour, and AuDHD — both
raters, consistently. Recomputes design_verdict + outcome_in_scope. AuDHD-positive
hits are left for manual verification (printed at the end).
"""
import os, re, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv(override=True)
import pandas as pd
from steps.config import load_config, set_active
from steps import llm
from steps.io import normalize_doi

MASTER = "search-results-from-database/fulltext_review_master.csv"
TEXT = "full_text_snowball"
AUTISM = re.compile(r"\b(autis\w*|asd|asperger|pervasive developmental)\b", re.I)
ADHD = re.compile(r"\b(adhd|a\.d\.h\.d|attention[- ]deficit|hyperkinetic)\b", re.I)
THREE = {"attention", "executive_function", "emotional_regulation"}
T_ALLOWED = THREE | {"other"}
D_ALLOWED = {"rct", "controlled_nonrandomized", "single_case_experimental",
             "uncontrolled_prepost", "case_study_series", "qualitative_only",
             "review_editorial", "conference_abstract", "other"}

T_SYS = """You identify which outcome(s) a study's intervention is designed to TARGET / improve. Choose ALL that apply from:
- attention: sustained/selective attention, focus, on-task behaviour, distractibility, vigilance.
- executive_function: working memory, planning, organisation, inhibition/impulse control, task-switching, cognitive flexibility, self-regulation of cognition/behaviour, time management.
- emotional_regulation: managing emotions, anxiety, stress, mood, frustration tolerance, emotional self-control.
- other: any other target — communication, social skills, employment/vocational, leisure, motor, academic content, daily living, sleep, etc.
Judge the intervention's PRIMARY aim(s). If it targets attention/EF/emotion-regulation, include that label even if "other" also applies.
Return ONLY: {"reasoning":"<1 sentence>","targets":["..."]}"""

D_SYS = """You classify a study's RESEARCH DESIGN into exactly ONE category:
- rct: randomised controlled trial — participants randomly allocated to >=2 groups/conditions.
- controlled_nonrandomized: separate control/comparison GROUP or condition, allocation not randomised (quasi-experimental, non-randomised controlled, waitlist without randomisation, between-groups comparison).
- single_case_experimental: single-case/small-n EXPERIMENTAL design with phases providing experimental control — multiple-baseline, ABAB/withdrawal/reversal, alternating-treatments, changing-criterion. (Within-subject control, NO separate control group. Requires >=1 participant with a manipulated design; if it is just a narrative description of cases with no experimental manipulation, use case_study_series.)
- uncontrolled_prepost: single-arm pre-post / one-group before-after with NO comparator and NO single-case experimental control.
- case_study_series: descriptive report of one or a few cases, no experimental manipulation or control.
- qualitative_only: only qualitative data, no quantitative outcome evaluation.
- review_editorial: review, meta-analysis, protocol, proposal, commentary, editorial, theoretical paper.
- conference_abstract: conference abstract/poster with no full paper.
- other: none of the above / cannot tell.
Judge the ACTUAL design used to evaluate the intervention. Also report n_participants = the number of participants who actually RECEIVED/completed the intervention (sum across intervention arms; EXCLUDE control-only participants who got no intervention). Use the analysed sample size; null only if truly unstated.
Return ONLY: {"reasoning":"<1 sentence>","design":"<one category>","n_participants":<int or null>}"""

A_SYS = """You determine, from excerpts of a study's text, whether the STUDY SAMPLE includes participants with CO-OCCURRING ADHD AND autism (AuDHD) — the whole sample or an identifiable subgroup the study reports on.
- audhd="yes" only if the SAME participants are described as having BOTH ADHD and autism. Two separate single-diagnosis groups -> "no". ADHD mentioned only as background/prevalence/comorbidity-in-general/exclusion-criterion (not an actual enrolled co-occurring participant) -> "no". "unclear" if implied but not explicitly stated for enrolled participants.
- adult_audhd="yes" if those co-occurring participants include adults (18+); "no" if only children/adolescents; "unclear" otherwise.
Return ONLY: {"reasoning":"<1-2 sentences citing the text>","audhd":"yes|no|unclear","adult_audhd":"yes|no|unclear","evidence":"<short quote or ''>"}"""

cfg = load_config("adults"); set_active(cfg)
ra, rb = cfg.rater_a, cfg.rater_b
m = pd.read_csv(MASTER, dtype=str).fillna("")
def nd(d): return normalize_doi(d) or ""
comb = pd.read_csv("search-results-from-database/combined/adjudicated.csv", dtype=str).fillna("")
AMAP = {nd(r["DOI"]): r.get("Abstract", "") for r in comb.to_dict("records") if nd(r["DOI"])}
for c in ("target_raterA","target_raterB","outcome_in_scope","design_raterA","design_raterB",
          "design_verdict","design_n","audhd","adult_audhd","audhd_evidence"):
    if c not in m.columns: m[c] = ""
for r in (ra, rb): llm.warm(r)

def ftext(i):
    p = os.path.join(TEXT, str(m.at[i, "full_text_filename"]).replace(".pdf", ".txt"))
    return open(p, encoding="utf-8").read() if os.path.exists(p) else ""

def excerpt(t, limit=9000):
    head = t[:3000]; wins = []
    for mm in ADHD.finditer(t):
        s = max(0, mm.start()-400); e = min(len(t), mm.end()+400)
        if AUTISM.search(t[s:e]): wins.append(t[s:e])
        if sum(len(w) for w in wins) > limit-3000: break
    return (head + "\n...\n" + "\n...\n".join(wins[:12]))[:limit]

def j(rater, sys, usr, mx=400):
    return llm.invoke_json(rater, system_prompt=sys, user_prompt=usr, temperature=0, max_tokens=mx)

def targets(rater, title, ev):
    raw = j(rater, T_SYS, f"Title: {title}\n\n{ev}")
    t = raw.get("targets", []); t = [t] if isinstance(t, str) else (t or [])
    return sorted({str(x).strip().lower().replace(" ", "_") for x in t} & T_ALLOWED)

def design(rater, title, ev):
    raw = j(rater, D_SYS, f"Title: {title}\n\n{ev}")
    d = str(raw.get("design", "")).strip().lower().replace(" ", "_")
    return (d if d in D_ALLOWED else "other"), raw.get("n_participants")

CTRL = {"rct", "controlled_nonrandomized"}
EXC = {"uncontrolled_prepost", "case_study_series", "qualitative_only", "review_editorial", "conference_abstract", "other"}
def verdict(a, b):
    if "single_case_experimental" in (a, b) and (a in CTRL or b in CTRL):
        return "flip"
    if a == "single_case_experimental" or b == "single_case_experimental":
        return "sced"
    A, B = a in CTRL, b in CTRL
    if A and B: return "controlled"
    if (A and b in EXC) or (B and a in EXC): return "flip"
    return "excluded"

def do(i):
    try:
        ft = ftext(i); ab = AMAP.get(nd(str(m.at[i, "DOI"])), "")
        title = str(m.at[i, "Title"])
        t_ev = (f"Abstract: {ab}\n\n{ft[:6000]}").strip() if (ab or ft) else title
        d_ev = ft[:12000] if ft else f"Abstract: {ab}"
        ta, tb = targets(ra, title, t_ev), targets(rb, title, t_ev)
        (da, na), (db, nb) = design(ra, title, d_ev), design(rb, title, d_ev)
        # audhd
        src = ft if ft else ab
        if not (AUTISM.search(src) and ADHD.search(src)):
            au = {"audhd": "no", "adult_audhd": "no", "evidence": "no ADHD+autism co-mention"}
        else:
            au = j(rb, A_SYS, excerpt(src) if ft else f"Abstract: {ab}", mx=500)
        return i, ta, tb, da, db, (na or nb), au
    except Exception as e:
        print(f"  [{i}] err {e}", flush=True); return None

done = 0
with ThreadPoolExecutor(max_workers=8) as pool:
    for fut in as_completed([pool.submit(do, i) for i in m.index]):
        r = fut.result()
        if not r: continue
        i, ta, tb, da, db, n, au = r
        ain, bin_ = bool(set(ta) & THREE), bool(set(tb) & THREE)
        m.at[i, "target_raterA"] = ";".join(ta); m.at[i, "target_raterB"] = ";".join(tb)
        m.at[i, "outcome_in_scope"] = "yes" if (ain and bin_) else ("no" if not (ain or bin_) else "review")
        m.at[i, "design_raterA"] = da; m.at[i, "design_raterB"] = db
        m.at[i, "design_verdict"] = verdict(da, db); m.at[i, "design_n"] = "" if n is None else str(n)
        m.at[i, "audhd"] = au.get("audhd", ""); m.at[i, "adult_audhd"] = au.get("adult_audhd", "")
        m.at[i, "audhd_evidence"] = str(au.get("evidence", ""))[:300]
        done += 1
m.to_csv(MASTER, index=False)
print(f"re-classified {done}/{len(m)}")
print("outcome_in_scope:", m.outcome_in_scope.value_counts().to_dict())
print("design_verdict  :", m.design_verdict.value_counts().to_dict())
print("audhd=yes       :", int((m.audhd == 'yes').sum()), "| adult_audhd=yes:", int((m.adult_audhd == 'yes').sum()))
print("\n=== AuDHD-positive hits — VERIFY MANUALLY ===")
for _, r in m[m.audhd == "yes"].iterrows():
    print(f"  adult_audhd={r.adult_audhd} | design={r.design_verdict}(n={r.design_n}) | outcome={r.outcome_in_scope}")
    print(f"    {r.Title[:75]}")
    print(f"    evidence: {r.audhd_evidence[:160]}")
