"""Compare the human BLIND validation labels (Validate_* in validation_sample.csv)
against the AI consensus, to estimate screening accuracy. Reports per-field percent
agreement + Cohen's κ, and a screen-level confusion matrix (sensitivity/specificity,
treating the human as the reference standard). Run AFTER completing blind validation.
"""
import os, sys
sys.path.insert(0, os.getcwd())
import pandas as pd
from steps.schema import CONSENSUS_FIELDS

SAMPLE = os.getenv("VALIDATE_OUT", "search-results-from-database/validation_sample.csv")
DIGITAL = {"mobile_app", "web_app", "software_tool", "video_game", "neurofeedback", "cbt",
           "cognitive_training", "mindfulness", "chatbot", "biofeedback"}
EMPIRICAL = {"empirical_with_results", "qualitative_only_study", "case_study"}
ND = {"adhd", "autistic", "audhd"}
FIELDS = ["has_adults", "study_type", "intervention_type", "neurotypes"]

def nz(v): return str(v).strip().lower()
def ai(row, f):  # AI label: consensus, else Sonnet (rater B)
    c = nz(row.get(f"Consensus_{f}", ""))
    return c if c else nz(row.get(f"RaterB_{f}", ""))

def kappa(pairs):
    cats = sorted({x for p in pairs for x in p}); n = len(pairs)
    if not n: return 0.0, 0.0
    po = sum(a == b for a, b in pairs) / n
    from collections import Counter
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum((ca[c]/n)*(cb[c]/n) for c in cats)
    return po, (po - pe)/(1 - pe) if pe < 1 else 1.0

df = pd.read_csv(SAMPLE, dtype=str).fillna("")
done = df[df.get("Validated", "").astype(str).str.lower() == "human"]
print(f"validation sample: {len(df)} | human-screened: {len(done)}")
if len(done) == 0:
    print("No papers screened yet — run blind validation first (ADJ_VALIDATE=1 poetry run python adjudicate_ui.py).")
    sys.exit(0)

print("\n=== per-field agreement (human blind vs AI) ===")
for f in FIELDS:
    pairs = [(nz(r[f"Validate_{f}"]), ai(r, f)) for _, r in done.iterrows()
             if nz(r.get(f"Validate_{f}", ""))]
    if not pairs: continue
    po, k = kappa(pairs)
    print(f"  {f:<18} n={len(pairs):<4} %agree={po*100:5.1f}  κ={k:.3f}")

# screen-level decision: potentially includable on the gating criteria
def passes(get):
    return (get("neurotypes") in ND and get("has_adults") in ("yes", "unspecified")
            and get("intervention_type") in DIGITAL and get("study_type") in EMPIRICAL)

def cell(h, a):  # confusion-matrix cell name (human = reference)
    return "tp" if (h and a) else "fp" if (a and not h) else "tn" if (not a and not h) else "fn"

enriched = "Validate_stratum" in done.columns and done["Validate_stratum"].str.strip().ne("").any()

# Per-paper classification (+ sampling weight for population estimates).
rows = []
for _, r in done.iterrows():
    h = passes(lambda f: nz(r.get(f"Validate_{f}", "")))
    a = passes(lambda f: ai(r, f))
    if enriched:
        pop = float(r.get("Validate_stratum_pop", 0) or 0)
        ns = float(r.get("Validate_stratum_n", 0) or 0)
        w = pop / ns if ns else 1.0
    else:
        w = 1.0
    rows.append((str(r.get("Validate_stratum", "")).strip() or "all", cell(h, a), w))

def confusion(subset):
    c = {"tp": 0.0, "fp": 0.0, "tn": 0.0, "fn": 0.0}
    n = 0
    for _, cl, w in subset:
        c[cl] += w; n += 1
    return c, n

def report(c, label):
    sens = c["tp"]/(c["tp"]+c["fn"]) if (c["tp"]+c["fn"]) else float("nan")
    spec = c["tn"]/(c["tn"]+c["fp"]) if (c["tn"]+c["fp"]) else float("nan")
    tot = sum(c.values())
    po = (c["tp"]+c["tn"])/tot if tot else float("nan")
    print(f"  [{label}] TP={c['tp']:.0f} FP={c['fp']:.0f} TN={c['tn']:.0f} "
          f"FN={c['fn']:.0f}  sens={sens:.3f} spec={spec:.3f} agree={po:.3f}")

if enriched:
    print("\n=== screen-level per stratum (RAW sample counts, human = reference) ===")
    for st in ("keep", "border", "excl"):
        sub = [x for x in rows if x[0] == st]
        if not sub: continue
        c, n = confusion(sub)
        report(c, f"{st} n={n}")
    fn_raw = sum(1 for st, cl, w in rows if cl == "fn")
    print(f"  >>> raw false-negatives found (AI excluded, you would include): {fn_raw}")
    print("      (BORDER/EXCL false-negatives are the recall-critical ones)")
    print("\n=== screen-level POPULATION estimate (stratum-weighted, human = reference) ===")
    c, _ = confusion(rows)
    report(c, "weighted → population")
    print("  (each paper weighted by stratum_pop / stratum_n so rare strata don't dominate)")
else:
    print("\n=== screen-level (human = reference) ===")
    c, _ = confusion(rows)
    print(f"  AI include / human include (TP): {c['tp']:.0f}")
    print(f"  AI include / human exclude (FP): {c['fp']:.0f}")
    print(f"  AI exclude / human exclude (TN): {c['tn']:.0f}")
    print(f"  AI exclude / human include (FN): {c['fn']:.0f}   <- missed includes (recall-critical)")
    report(c, "overall")
