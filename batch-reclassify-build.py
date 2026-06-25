"""Build Bedrock batch-inference input for re-rating the SURVIVORS with the
updated taxonomy, one JSONL per model (Nova + Sonnet, different InvokeModel
schemas), and upload to S3. recordId encodes the combined-dataset row index so
the merge step can map results back.
"""
import os, json, boto3
os.environ.setdefault("AWS_PROFILE", "phd")
import pandas as pd
from steps.schema import CLASSIFICATION_PROMPT

ACCT = "369598751361"; BUCKET = f"audhd-bedrock-batch-{ACCT}"
WORK = "search-results-from-database/combined/adjudicated.csv"
MAXTOK = 1024
def nz(v): return str(v).strip().lower()

df = pd.read_csv(WORK, dtype=str).fillna("")
surv = df[(df["Screen_Pass"].astype(str).str.upper() == "Y") &
          (df["Abstract"].str.len() >= 20)]
print(f"survivors to re-rate: {len(surv)}")

def user_prompt(r):
    return f"Title: {r.get('Title','')}\n\nAbstract: {r.get('Abstract','')}"

nova, sonnet = [], []
for idx, r in surv.iterrows():
    rid = f"rec{int(idx):07d}"
    up = user_prompt(r)
    sonnet.append({"recordId": rid, "modelInput": {
        "anthropic_version": "bedrock-2023-05-31", "max_tokens": MAXTOK,
        "system": CLASSIFICATION_PROMPT,
        "messages": [{"role": "user", "content": up}]}})
    nova.append({"recordId": rid, "modelInput": {
        "system": [{"text": CLASSIFICATION_PROMPT}],
        "messages": [{"role": "user", "content": [{"text": up}]}],
        "inferenceConfig": {"maxTokens": MAXTOK, "temperature": 0}}})

os.makedirs("/tmp/batch_in", exist_ok=True)
s3 = boto3.Session(region_name="us-east-1").client("s3")
for name, recs in [("sonnet", sonnet), ("nova", nova)]:
    p = f"/tmp/batch_in/{name}.jsonl"
    with open(p, "w") as f:
        for rec in recs:
            f.write(json.dumps(rec) + "\n")
    key = f"input/{name}.jsonl"
    s3.upload_file(p, BUCKET, key)
    print(f"  uploaded {len(recs)} -> s3://{BUCKET}/{key}")
print("done")
