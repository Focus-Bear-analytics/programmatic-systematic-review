"""Build ONE unified corpus (database+orig-snowball + DSCT snowball) and a Bedrock
batch-inference input (Nova + Sonnet) to re-classify EVERY paper with an abstract,
using the tuned CLASSIFICATION_PROMPT + each rater's prompt_suffix. recordId encodes
the all_papers.csv row index. Uploads JSONL to S3.
"""
import os, json, re, boto3
os.environ.setdefault("AWS_PROFILE", "phd")
import pandas as pd
from steps.config import load_config
from steps.schema import CLASSIFICATION_PROMPT
from steps.io import normalize_doi

ACCT = "369598751361"; BUCKET = f"audhd-bedrock-batch-{ACCT}"
ALL = "search-results-from-database/all_papers.csv"
MAXTOK = 1024
cfg = load_config("adults")
sa, sb = cfg.rater("a").prompt_suffix, cfg.rater("b").prompt_suffix

def nd(d): return normalize_doi(d) or ""
def nt(t): return re.sub(r"[^a-z0-9 ]", " ", str(t).lower()).strip()

# 1) unify corpus + DSCT (dedupe DSCT against corpus)
comb = pd.read_csv("search-results-from-database/combined/adjudicated.csv", dtype=str).fillna("")
comb.loc[comb["origin"].str.strip() == "", "origin"] = "database_search"
seen_doi = {nd(d) for d in comb["DOI"] if nd(d)}
seen_t = {nt(t) for t in comb["Title"] if str(t).strip()}
dsct = pd.read_csv("citation-scraping/dsct_recallsafe.csv", dtype=str).fillna("")
keep = []
for _, r in dsct.iterrows():
    if (nd(r["DOI"]) and nd(r["DOI"]) in seen_doi) or nt(r["Title"]) in seen_t:
        continue
    keep.append({"Title": r["Title"], "Abstract": r["Abstract"], "Authors": r["Authors"],
                 "Year": r["Year"], "DOI": r["DOI"], "URL": r["URL"], "PMID": r["PMID"],
                 "Journal": r["Journal"], "origin": "dsct_snowball"})
allp = pd.concat([comb, pd.DataFrame(keep)], ignore_index=True).fillna("")
allp.to_csv(ALL, index=False)
print(f"all_papers.csv: {len(allp)} rows (+{len(keep)} new DSCT)")

# 2) batch input for every paper with a usable abstract
tgt = allp[allp["Abstract"].str.len() >= 20]
print(f"to classify (abstract>=20 chars): {len(tgt)}  | skipped no-abstract: {len(allp)-len(tgt)}")
nova, sonnet = [], []
for idx, r in tgt.iterrows():
    rid = f"rec{int(idx):07d}"
    up = f"Title: {r['Title']}\n\nAbstract: {r['Abstract']}"
    sys_a = CLASSIFICATION_PROMPT + (("\n\n" + sa) if sa else "")
    sys_b = CLASSIFICATION_PROMPT + (("\n\n" + sb) if sb else "")
    sonnet.append({"recordId": rid, "modelInput": {
        "anthropic_version": "bedrock-2023-05-31", "max_tokens": MAXTOK,
        "system": sys_b, "messages": [{"role": "user", "content": up}]}})
    nova.append({"recordId": rid, "modelInput": {
        "system": [{"text": sys_a}], "messages": [{"role": "user", "content": [{"text": up}]}],
        "inferenceConfig": {"maxTokens": MAXTOK, "temperature": 0}}})

os.makedirs("/tmp/batch_in", exist_ok=True)
s3 = boto3.Session(region_name="us-east-1").client("s3")
for name, recs in [("big_sonnet", sonnet), ("big_nova", nova)]:
    p = f"/tmp/batch_in/{name}.jsonl"
    with open(p, "w") as f:
        for rec in recs:
            f.write(json.dumps(rec) + "\n")
    s3.upload_file(p, BUCKET, f"input/{name}.jsonl")
    print(f"  uploaded {len(recs)} -> s3://{BUCKET}/input/{name}.jsonl")
print("done")
