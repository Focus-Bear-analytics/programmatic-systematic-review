"""Build Bedrock batch input to RE-SCREEN (Phase-1: age + is_empirical) all
has_adults=yes survivors under the redefined has_adults criterion. Per-model
JSONL (Nova + Sonnet), uploaded to S3.
"""
import os, json, boto3
os.environ.setdefault("AWS_PROFILE", "phd")
import pandas as pd
from steps.schema import SCREEN_PROMPT

ACCT = "369598751361"; BUCKET = f"audhd-bedrock-batch-{ACCT}"
WORK = "search-results-from-database/combined/adjudicated.csv"
MAXTOK = 400
def nz(v): return str(v).strip().lower()

df = pd.read_csv(WORK, dtype=str).fillna("")
def fin(r, f):
    return nz(r.get("Final_" + f)) if nz(r.get("Adjudicated")) == "human" and nz(r.get("Final_" + f)) else nz(r.get("Consensus_" + f))
tgt = df[(df["Screen_Pass"].astype(str).str.upper() == "Y") & (df["Abstract"].str.len() >= 20)]
tgt = tgt[[fin(r, "has_adults") == "yes" for _, r in tgt.iterrows()]]
print(f"re-screen targets (has_adults=yes survivors): {len(tgt)}")

nova, sonnet = [], []
for idx, r in tgt.iterrows():
    rid = f"rec{int(idx):07d}"
    up = f"Title: {r.get('Title','')}\n\nAbstract: {r.get('Abstract','')}"
    sonnet.append({"recordId": rid, "modelInput": {
        "anthropic_version": "bedrock-2023-05-31", "max_tokens": MAXTOK,
        "system": SCREEN_PROMPT, "messages": [{"role": "user", "content": up}]}})
    nova.append({"recordId": rid, "modelInput": {
        "system": [{"text": SCREEN_PROMPT}],
        "messages": [{"role": "user", "content": [{"text": up}]}],
        "inferenceConfig": {"maxTokens": MAXTOK, "temperature": 0}}})

os.makedirs("/tmp/batch_in", exist_ok=True)
s3 = boto3.Session(region_name="us-east-1").client("s3")
for name, recs in [("screen_sonnet", sonnet), ("screen_nova", nova)]:
    p = f"/tmp/batch_in/{name}.jsonl"
    with open(p, "w") as f:
        for rec in recs: f.write(json.dumps(rec) + "\n")
    s3.upload_file(p, BUCKET, f"input/{name}.jsonl")
    print(f"  uploaded {len(recs)} -> s3://{BUCKET}/input/{name}.jsonl")
