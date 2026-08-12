"""Code the INTENT of each adult ND digital-intervention study on a
normalisation–accommodation spectrum, to put the §4.2 "fixing not supporting"
claim on systematic footing. Two raters (Nova + Sonnet) for inter-rater
reliability. Writes intent_* columns to nd_digital_adults_intent.csv and reports
the distribution + Cohen's κ.

Run: ADJ ... ensure SSO is fresh first:  aws sso login --profile phd
"""
import os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv(override=True)
import pandas as pd
from steps.config import load_config, set_active
from steps import llm

SRC = "search-results-from-database/nd_digital_empirical.csv"
OUT = "search-results-from-database/nd_digital_adults_intent.csv"
ALLOWED = {"normalisation", "skills_training", "accommodation_support", "unclear"}
SYS = """You classify the PRIMARY INTENT of a digital intervention for neurodivergent (autistic and/or ADHD) adults.
First ask the key question: does the intervention try to change the PERSON (internal change), or does it provide EXTERNAL supports/tools/environmental adaptation while leaving the person as they already are? Then choose ONE:
- normalisation: INTERNAL change toward a NEUROTYPICAL standard. The aim is to remediate, reduce, suppress, or correct neurodivergent traits, or to train the person to behave/communicate/appear more neurotypical or fit in socially. Examples: social-skills training, face/emotion-recognition training, masking, reducing stereotyped or "inappropriate" behaviours, improving compliance, symptom reduction framed as the goal.
- skills_training: INTERNAL change that is NEURODIVERGENT-AFFIRMING. The aim is to help the person build skills, strategies, or self-understanding that serve THEIR OWN self-defined goals and work WITH their neurotype — NOT to make them more neurotypical. Examples: self-advocacy, psychoeducation about one's own ADHD/autism, self-regulation or planning strategies taught on the person's own terms, strengths-based coaching.
- accommodation_support: EXTERNAL supports rather than changing the person — tools, reminders, planning/organisation aids, environmental adaptation, user-directed tracking, scaffolds the user controls.
- unclear: the text genuinely does not say enough to tell.
Judge the DOMINANT aim — do NOT answer "mixed"; if more than one element is present, pick the one that dominates the intervention's stated purpose and primary outcome. The hardest line is normalisation vs skills_training: decide by WHOSE standard defines success — a neurotypical standard (fewer symptoms, appearing/behaving typical, fitting in) = normalisation; the person's own goals worked with their neurotype = skills_training.
Return ONLY: {"reasoning":"<1 sentence>","intent":"<one value>"}"""

cfg = load_config("adults"); set_active(cfg)
ra, rb = cfg.rater_a, cfg.rater_b
df = pd.read_csv(SRC, dtype=str).fillna("")
# Exclude PRISMA-flagged duplicates (is_duplicate=Y) — else the same study is
# coded and adjudicated multiple times, inflating the distribution.
adults = df[(df.L_has_adults == "yes") & (df.is_duplicate != "Y")].copy().reset_index(drop=True)
print(f"{len(adults)} adult ND digital-intervention studies to code", flush=True)
for c in ("intent_raterA", "intent_raterB", "intent_consensus"):
    adults[c] = ""
for r in (ra, rb): llm.warm(r)

def details(r):
    d = str(r.get("Consensus_intervention_details") or r.get("RaterB_intervention_details") or "")
    return d[:600]

def code(rater, r):
    raw = llm.invoke_json(rater, system_prompt=SYS,
        user_prompt=f"Title: {r['Title']}\n\nAbstract: {r['Abstract'][:2500]}\n\nIntervention: {details(r)}",
        temperature=0, max_tokens=200)
    v = str(raw.get("intent", "")).strip().lower().replace(" ", "_")
    return v if v in ALLOWED else "unclear"

def do(i):
    r = adults.loc[i]
    try:
        return i, code(ra, r), code(rb, r)
    except Exception as e:
        print(f"  [{i}] err {e}", flush=True); return None

done = 0
with ThreadPoolExecutor(max_workers=8) as pool:
    for fut in as_completed([pool.submit(do, i) for i in adults.index]):
        res = fut.result()
        if not res: continue
        i, a, b = res
        adults.at[i, "intent_raterA"] = a; adults.at[i, "intent_raterB"] = b
        adults.at[i, "intent_consensus"] = a if a == b else "disagree"
        done += 1
adults.to_csv(OUT, index=False)

# report
def kappa(pairs):
    cats = sorted({x for p in pairs for x in p}); n = len(pairs)
    po = sum(a == b for a, b in pairs)/n
    from collections import Counter
    ca, cb = Counter(a for a,_ in pairs), Counter(b for _,b in pairs)
    pe = sum((ca[c]/n)*(cb[c]/n) for c in cats)
    return po, (po-pe)/(1-pe) if pe < 1 else 1.0
pairs = [(r.intent_raterA, r.intent_raterB) for r in adults.itertuples() if r.intent_raterA]
po, k = kappa(pairs)
print(f"\ncoded {done} | inter-rater %agree={po*100:.1f} κ={k:.3f}")
print("RaterA:", adults.intent_raterA.value_counts().to_dict())
print("RaterB:", adults.intent_raterB.value_counts().to_dict())
print("consensus:", adults.intent_consensus.value_counts().to_dict())
# headline: of the studies both raters agreed on, share normalisation vs support
agreed = adults[adults.intent_consensus != "disagree"]
print(f"\nAmong {len(agreed)} agreed: "
      f"normalisation={int((agreed.intent_consensus=='normalisation').sum())}, "
      f"skills_training={int((agreed.intent_consensus=='skills_training').sum())}, "
      f"accommodation_support={int((agreed.intent_consensus=='accommodation_support').sum())}, "
      f"unclear={int((agreed.intent_consensus=='unclear').sum())}")
print(f"\nwrote {OUT}")
