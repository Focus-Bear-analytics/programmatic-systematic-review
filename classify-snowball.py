"""Phase-2 detailed classification on snowball papers that passed the screen.
Isolated in the snowball/ subdir so the database review's enriched.csv is untouched.
Resumable (checkpoints to snowball/enriched.csv every 25 rows).
"""
import os, sys, dataclasses
sys.path.insert(0, os.getcwd())
import pandas as pd
from steps.config import load_config, set_active
from steps import classify

cfg = dataclasses.replace(load_config("adults"), review_subdir="snowball")
set_active(cfg)
os.makedirs(cfg.review_dir, exist_ok=True)
df = pd.read_csv("search-results-from-database/screened.csv", dtype=str).fillna("")
print(f"Phase 2: {(df['Screen_Pass']=='Y').sum()} survivors to classify", flush=True)
classify.run(df)
