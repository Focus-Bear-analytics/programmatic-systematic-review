"""Merge the big batch re-classification back into all_papers.csv. Downloads each
job's .jsonl.out from S3, extracts the model JSON, coerces to the enum, applies
deterministic rule overrides, and writes RaterA_ (Nova) / RaterB_ (Sonnet) +
Consensus_ for every classified row. Backs up first.
"""
import os, json, boto3
os.environ.setdefault("AWS_PROFILE", "phd")
import shutil, pandas as pd
from steps.schema import coerce_classification, CONSENSUS_FIELDS
from steps import rules

ACCT = "369598751361"; BUCKET = f"audhd-bedrock-batch-{ACCT}"
WORK = "search-results-from-database/all_papers.csv"
WRITE = CONSENSUS_FIELDS + ["intervention_details"]
s3 = boto3.Session(region_name="us-east-1").client("s3")

def out_text(name, mo):
    if "sonnet" in name:
        return "".join(b.get("text", "") for b in mo.get("content", []) if b.get("type") == "text")
    return "".join(b.get("text", "") for b in mo.get("output", {}).get("message", {}).get("content", []))

def load_results(name):
    pref = f"output/{name}/"
    keys = [o["Key"] for p in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=pref)
            for o in p.get("Contents", []) if o["Key"].endswith(".jsonl.out")]
    res = {}
    for k in keys:
        body = s3.get_object(Bucket=BUCKET, Key=k)["Body"].read().decode()
        for line in body.splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            mo = rec.get("modelOutput")
            if not mo:
                continue
            idx = int(rec["recordId"][3:])
            txt = out_text(name, mo)
            try:
                raw = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
            except Exception:
                continue
            res[idx] = coerce_classification(raw)
    return res

def main():
    nova = load_results("big_nova"); sonnet = load_results("big_sonnet")
    print(f"parsed nova={len(nova)} sonnet={len(sonnet)}")
    df = pd.read_csv(WORK, dtype=str).fillna("")
    shutil.copy(WORK, WORK.replace(".csv", "_pre_bigscreen_backup.csv"))
    def nzc(v): return str(v).strip().lower()
    updated = 0
    for idx in set(nova) & set(sonnet):
        if idx not in df.index:
            continue
        title = str(df.at[idx, "Title"] or ""); ab = str(df.at[idx, "Abstract"] or "")
        ov = rules.apply_rules(title, ab)
        a = {**nova[idx], **{k: v for k, v in ov.items() if k in nova[idx]}}
        b = {**sonnet[idx], **{k: v for k, v in ov.items() if k in sonnet[idx]}}
        for f in WRITE:
            df.at[idx, f"RaterA_{f}"] = a.get(f, "")
            df.at[idx, f"RaterB_{f}"] = b.get(f, "")
            if f in CONSENSUS_FIELDS:
                av, bv = a.get(f, ""), b.get(f, "")
                df.at[idx, f"Consensus_{f}"] = av if nzc(av) == nzc(bv) else ""
        df.at[idx, "RaterA_model"] = "Nova 2 Lite"; df.at[idx, "RaterB_model"] = "Claude Sonnet 4.6"
        df.at[idx, "Consensus_Reached"] = "Y" if all(nzc(a.get(f)) == nzc(b.get(f)) for f in CONSENSUS_FIELDS) else "N"
        updated += 1
    df.to_csv(WORK, index=False)
    print(f"merged {updated} rows -> {WORK} (backup: _pre_bigscreen_backup.csv)")

if __name__ == "__main__":
    main()
