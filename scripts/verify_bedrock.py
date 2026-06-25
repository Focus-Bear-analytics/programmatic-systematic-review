"""Verify the configured Bedrock models are reachable in their region.

Run this after `aws sso login --profile phd`. It:
  * lists the SYSTEM_DEFINED inference profiles in each rater's region
  * checks whether each config's model_id is invokable (a tiny Converse call)
  * if a model_id fails but a close match exists, suggests the correct ID

Usage:
    poetry run python scripts/verify_bedrock.py [<config>]   # default: adults
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.getcwd())
import boto3  # noqa: E402

from steps.config import load_config  # noqa: E402
from steps import llm  # noqa: E402


def list_profiles(profile: str, region: str) -> list[str]:
    session = boto3.Session(profile_name=profile, region_name=region)
    br = session.client("bedrock")
    out: list[str] = []
    try:
        resp = br.list_inference_profiles(typeEquals="SYSTEM_DEFINED")
        out = [p["inferenceProfileId"] for p in resp["inferenceProfileSummaries"]]
    except Exception as e:  # noqa: BLE001
        print(f"  ! could not list profiles in {region}: {str(e)[:160]}")
    return out


def suggest(model_id: str, profiles: list[str]) -> list[str]:
    """Heuristic: surface profiles sharing the model's distinctive token."""
    key = model_id.split(".")[-1].split(":")[0]  # e.g. 'nova-2-lite-v1' / 'claude-sonnet-4-6'
    base = key.rsplit("-", 1)[0] if key[-1].isdigit() else key
    return [p for p in profiles if base in p or key in p]


def main() -> int:
    slug = sys.argv[1] if len(sys.argv) > 1 else "adults"
    cfg = load_config(slug)
    print(f"=== Verifying Bedrock models for config '{slug}' ===\n")

    # Cache profile lists per region.
    region_profiles: dict[str, list[str]] = {}
    ok_all = True
    for key in ("a", "b", "adjudicator"):
        r = cfg.rater(key)
        print(f"[{key}] {r.label}  provider={r.provider}")
        if r.provider != "bedrock":
            print("    (non-Bedrock — skipping invoke check)\n")
            continue
        print(f"    model_id = {r.model_id}   region = {r.region}   profile = {r.aws_profile}")
        if r.region not in region_profiles:
            region_profiles[r.region] = list_profiles(r.aws_profile, r.region)
        profs = region_profiles[r.region]

        # Try a tiny invoke.
        try:
            out = llm.invoke_json(
                r, "Return only JSON. No prose.",
                'Return {"ok": true, "family": "<your model family>"}',
                max_tokens=64,
            )
            print(f"    ✓ INVOKE OK → {out}\n")
        except llm.LLMError as e:
            ok_all = False
            msg = str(e)
            print(f"    ✗ INVOKE FAILED: {msg[:170]}")
            cand = suggest(r.model_id, profs)
            if cand:
                print(f"    → candidate profile IDs in {r.region}:")
                for c in sorted(cand):
                    print(f"        {c}")
            else:
                print(f"    → no obvious alternative among {len(profs)} profiles in {r.region}")
            print()

    print("=" * 60)
    print("ALL MODELS OK ✓" if ok_all else "Some models failed — patch configs with a suggested ID above.")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
