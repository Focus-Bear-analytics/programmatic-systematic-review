"""Fetch abstracts (by DOI) for the no-abstract snowball papers, isolated in the
snowball/ review subdir so the database review's abstracts_filled.csv is untouched.
"""
import os, sys, dataclasses
sys.path.insert(0, os.getcwd())
import pandas as pd
from steps.config import load_config, set_active
from steps import fill_abstracts
from steps.io import is_missing_abstract

cfg = load_config("adults")
cfg = dataclasses.replace(cfg, review_subdir="snowball")
set_active(cfg)
os.makedirs(cfg.review_dir, exist_ok=True)

df = pd.read_csv("search-results-from-database/deduped-with-snowball.csv", dtype=str).fillna("")
new = df[df["origin"] == "snowball"].copy()
missing = new[new["Abstract"].apply(is_missing_abstract)].copy()
print(f"{len(missing)} no-abstract snowball papers -> fetching by DOI", flush=True)
fill_abstracts.run(missing)
