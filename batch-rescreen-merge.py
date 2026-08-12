"""Merge batch re-screen results: update has_adults/has_under_18/is_empirical +
Screen_Pass/Screen_Reason under the redefined has_adults criterion. Rows where
both raters now say has_adults=no -> wrong_age -> Screen_Pass=N (drop out).
Reports flips. Backs up first. Run with the UI stopped.
"""
import os, json, boto3
os.environ.setdefault("AWS_PROFILE", "phd")
import shutil, pandas as pd
from steps.schema import coerce_screen, SCREEN_FIELDS
from steps import rules, screen
from steps.config import load_config, set_active

ACCT = "369598751361"; BUCKET = f"audhd-bedrock-batch-{ACCT}"
WORK = "search-results-from-database/combined/adjudicated.csv"
s3 = boto3.Session(region_name="us-east-1").client("s3")
jobs = json.load(open("/tmp/rescreen_jobs.json"))
cfg = load_config("adults"); set_active(cfg)
require_age = (cfg.raw.get("screening") or {}).get("require_age")
def nz(v): return str(v).strip().lower()

def out_text(name, mo):
    if "sonnet" in name:
        return "".join(b.get("text", "") for b in mo.get("content", []) if b.get("type") == "text")
    return "".join(b.get("text", "") for b in mo.get("output", {}).get("message", {}).get("content", []))

def load(name):
    pref = f"output/{name}/"
    keys = [o["Key"] for p in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=pref)
            for o in p.get("Contents", []) if o["Key"].endswith(".jsonl.out")]
    res = {}
    for k in keys:
        for line in s3.get_object(Bucket=BUCKET, Key=k)["Body"].read().decode().splitlines():
            if not line.strip(): continue
            rec = json.loads(line); mo = rec.get("modelOutput")
            if not mo: continue
            txt = out_text(name, mo)
            try:
                raw = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
            except Exception:
                continue
            res[int(rec["recordId"][3:])] = coerce_screen(raw)
    return res

def main():
    nova = load("screen_nova"); sonnet = load("screen_sonnet")
    print(f"parsed nova={len(nova)} sonnet={len(sonnet)}")
    df = pd.read_csv(WORK, dtype=str).fillna("")
    shutil.copy(WORK, WORK.replace(".csv", "_pre_rescreen_age_backup.csv"))
    flips_drop = 0; flips_adult_no = 0
    for idx in set(nova) & set(sonnet):
        if idx not in df.index: continue
        t = str(df.at[idx, "Title"] or ""); a = str(df.at[idx, "Abstract"] or "")
        ov = {k: v for k, v in rules.apply_rules(t, a).items() if k in SCREEN_FIELDS}
        ar = {**nova[idx], **ov}; br = {**sonnet[idx], **ov}
        for f in SCREEN_FIELDS:
            df.at[idx, f"RaterA_{f}"] = ar.get(f, ""); df.at[idx, f"RaterB_{f}"] = br.get(f, "")
            df.at[idx, f"Consensus_{f}"] = ar.get(f) if nz(ar.get(f)) == nz(br.get(f)) else ""
        p, reason = screen._gate(ar, br, require_age)
        if nz(ar.get("has_adults")) == "no" and nz(br.get("has_adults")) == "no":
            flips_adult_no += 1
        if nz(df.at[idx, "Screen_Pass"]) == "y" and nz(p) == "n":
            flips_drop += 1
        df.at[idx, "Screen_Pass"] = p; df.at[idx, "Screen_Reason"] = reason
    df.to_csv(WORK, index=False)
    print(f"merged {len(set(nova)&set(sonnet))} | both-raters has_adults=no: {flips_adult_no} | "
          f"newly dropped (Y->N): {flips_drop}")

if __name__ == "__main__":
    main()
