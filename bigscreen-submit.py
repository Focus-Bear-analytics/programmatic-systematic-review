"""Submit the two Bedrock batch-inference jobs (Nova + Sonnet) for the big
re-classification. Saves job ARNs to /tmp/batch_jobs.json for polling/merge.
"""
import os, json, time, boto3
os.environ.setdefault("AWS_PROFILE", "phd")

ACCT = "369598751361"; BUCKET = f"audhd-bedrock-batch-{ACCT}"
ROLE = f"arn:aws:iam::{ACCT}:role/service-role/audhd-bedrock-batch-role"
REGION = "us-east-1"
MODELS = {"big_nova": "us.amazon.nova-2-lite-v1:0",
          "big_sonnet": "us.anthropic.claude-sonnet-4-6"}
br = boto3.Session(region_name=REGION).client("bedrock")
stamp = time.strftime("%Y%m%d-%H%M%S")
jobs = {}
for name, model in MODELS.items():
    resp = br.create_model_invocation_job(
        jobName=f"bigscreen-{name.replace('_','-')}-{stamp}",
        roleArn=ROLE,
        modelId=model,
        inputDataConfig={"s3InputDataConfig": {"s3Uri": f"s3://{BUCKET}/input/{name}.jsonl"}},
        outputDataConfig={"s3OutputDataConfig": {"s3Uri": f"s3://{BUCKET}/output/{name}/"}},
    )
    jobs[name] = resp["jobArn"]
    print(f"submitted {name}: {resp['jobArn']}")
json.dump(jobs, open("/tmp/batch_jobs.json", "w"))
print("saved /tmp/batch_jobs.json")
