"""Final intent distribution after human adjudication of the disagreements.
final intent = human-adjudicated value where present, else the two-rater consensus.
"""
import os, sys
sys.path.insert(0, os.getcwd())
import pandas as pd

SRC = os.getenv("INTENT_SRC", "search-results-from-database/nd_digital_adults_intent.csv")
full = pd.read_csv(SRC, dtype=str).fillna("")
def nz(v): return str(v).strip().lower()
def final(r):
    f = nz(r.get("intent_final", ""))
    if f: return f
    c = nz(r.get("intent_consensus", ""))
    return c if c != "disagree" else "unresolved"
full["intent_FINAL"] = [final(r) for _, r in full.iterrows()]
full.to_csv(SRC, index=False)

# Restrict to adult-population studies (hybrid rule):
#  - human age-gate said "no"                          -> exclude
#  - no human age judgment AND flagged has_under_18=yes -> exclude (flag fallback)
#  - human said "yes", or ungated-and-not-flagged       -> keep
gated = full["intent_has_adults"].str.lower() if "intent_has_adults" in full.columns else pd.Series([""]*len(full))
under18 = full["L_has_under_18"].str.lower() if "L_has_under_18" in full.columns else pd.Series([""]*len(full))
human_no = full["intent_FINAL"] == "excluded_not_adults"
flag_drop = (~gated.isin(["yes", "no"])) & (under18 == "yes")
drop = human_no | flag_drop
df = full[~drop].copy()
print(f"adult-population restriction: {len(full)} -> {len(df)}  "
      f"(human age-gate excluded {int(human_no.sum())}; flag fallback excluded {int((flag_drop & ~human_no).sum())})")

n = len(df)
adj = int((df.get("intent_adjudicated", "").astype(str).str.lower() == "human").sum())
dis = int((df["intent_consensus"].astype(str).str.lower() == "disagree").sum())
print(f"{n} adult ND digital studies | {dis} were disagreements | {adj} human-adjudicated")
vc = df["intent_FINAL"].value_counts().to_dict()
print("FINAL intent distribution:", vc)
norm = vc.get("normalisation", 0); supp = vc.get("accommodation_support", 0)
resolved = sum(v for k, v in vc.items() if k != "unresolved")
if resolved:
    print(f"  normalisation: {norm} ({100*norm/resolved:.1f}% of resolved)")
    print(f"  accommodation_support: {supp} ({100*supp/resolved:.1f}% of resolved)")
if "unresolved" in vc:
    print(f"  STILL UNRESOLVED (adjudicate these): {vc['unresolved']} — run ADJ_INTENT=1 poetry run python adjudicate_ui.py")
