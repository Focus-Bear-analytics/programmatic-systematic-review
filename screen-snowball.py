"""Phase-1 screen on the NEW snowball papers (origin=snowball) from the
adult-pruned master file. Writes screened.csv. Non-destructive: the existing
adjudicated database review is untouched. Resumable.
"""
import os, sys
sys.path.insert(0, os.getcwd())
import pandas as pd
from steps.config import load_config, set_active
from steps import screen

cfg = load_config("adults"); set_active(cfg)
df = pd.read_csv("search-results-from-database/deduped-with-snowball.csv", dtype=str).fillna("")
new = df[df["origin"] == "snowball"].reset_index(drop=True)
print(f"Screening {len(new)} new snowball papers (age + is_empirical)\n", flush=True)
screen.run(new)
