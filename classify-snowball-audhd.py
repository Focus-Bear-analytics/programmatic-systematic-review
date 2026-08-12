"""AuDHD detection on the retrieved snowball full texts.

Two stages, matching the database-review approach:
  1. Regex pre-filter — the full text must mention BOTH an autism-family term
     and an ADHD-family term; otherwise co-occurring AuDHD is impossible and we
     skip the (expensive) LLM call, recording audhd=no (reason=no_cooccurrence).
  2. LLM excerpt verification — for pre-filtered texts, send the abstract plus
     focused excerpts around the co-mentions to one Bedrock rater, which judges
     whether the STUDY SAMPLE actually has co-occurring ADHD+autism (or reports
     an AuDHD subgroup), and whether that AuDHD signal applies to adults.

Reads snowball/fulltext_candidates.csv + full_text_snowball/<id>.txt.
Writes snowball/fulltext_audhd.csv. Resumable (skips rows already judged).
"""
import os, re, sys
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv(override=True)
import pandas as pd
from steps.config import load_config, set_active
from steps import llm

CAND = "search-results-from-database/snowball/fulltext_candidates.csv"
OUT = "search-results-from-database/snowball/fulltext_audhd.csv"
TEXT_DIR = "full_text_snowball"

AUTISM = re.compile(r"\b(autis\w*|asd|asperger|pervasive developmental)\b", re.I)
ADHD = re.compile(r"\b(adhd|a\.d\.h\.d|attention[- ]deficit|hyperkinetic)\b", re.I)

SYSTEM = """You determine, from excerpts of a study's full text, whether the STUDY SAMPLE includes participants with CO-OCCURRING ADHD AND autism (AuDHD) — either the whole sample, or an identifiable subgroup the study reports on.

Rules:
- "audhd" = yes only if the SAME participants are described as having both ADHD and autism (e.g. "adults with ASD and comorbid ADHD", "the AuDHD subgroup", "42% also met ADHD criteria"). Two separate groups (an ADHD group AND a separate autism group) with no overlap is NOT audhd -> "no".
- If ADHD and autism are only mentioned as background/related conditions, not as characteristics of the participants -> "no".
- "unclear" if co-occurrence is plausibly implied but not stated.
- adult_audhd = "yes" if the co-occurring participants include adults (18+); "no" if only children; "unclear" otherwise.

Return ONLY a JSON object: {"reasoning": "<1-2 sentences citing the text>", "audhd": "yes|no|unclear", "adult_audhd": "yes|no|unclear", "evidence": "<short quote or ''>"}"""


def excerpt(text: str, limit: int = 9000) -> str:
    """Abstract/intro head + windows around ADHD/autism co-mentions."""
    head = text[:3000]
    windows = []
    for m in ADHD.finditer(text):
        s = max(0, m.start() - 400); e = min(len(text), m.end() + 400)
        seg = text[s:e]
        if AUTISM.search(seg):
            windows.append(seg)
        if sum(len(w) for w in windows) > limit - 3000:
            break
    return (head + "\n...\n" + "\n...\n".join(windows[:12]))[:limit]


def main():
    cfg = load_config("adults"); set_active(cfg)
    rater = cfg.rater_b  # Sonnet — strongest for nuanced co-occurrence judgement
    cand = pd.read_csv(CAND, dtype=str).fillna("")
    ret = cand[cand["ft_status"] == "retrieved"].copy()
    print(f"{len(ret)} retrieved full texts to scan for AuDHD", flush=True)

    done = {}
    if os.path.exists(OUT):
        prev = pd.read_csv(OUT, dtype=str).fillna("")
        done = {r["fulltext_id"]: r for r in prev.to_dict("records")}

    llm.warm(rater)
    rows = []; sent = 0; audhd_hits = 0
    for n, r in enumerate(ret.to_dict("records"), 1):
        fidv = r["fulltext_id"]
        if fidv in done:
            rows.append(done[fidv]); continue
        path = os.path.join(TEXT_DIR, f"{fidv}.txt")
        text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
        has_both = bool(AUTISM.search(text) and ADHD.search(text))
        rec = {k: r.get(k, "") for k in ("fulltext_id", "DOI", "Title", "Year",
               "Consensus_intervention_type", "Consensus_neurotypes")}
        if not has_both:
            rec.update(audhd="no", adult_audhd="no", reason="no_cooccurrence",
                       evidence="", reasoning="full text does not mention both ADHD and autism")
        else:
            try:
                res = llm.invoke_json(rater, system_prompt=SYSTEM,
                    user_prompt=excerpt(text), temperature=0, max_tokens=500)
                sent += 1
            except Exception as e:
                res = {}
                print(f"  [{fidv}] LLM error: {e}", flush=True)
            rec.update(audhd=res.get("audhd", ""), adult_audhd=res.get("adult_audhd", ""),
                       reason="llm", evidence=str(res.get("evidence", ""))[:300],
                       reasoning=str(res.get("reasoning", ""))[:300])
            if str(rec["audhd"]).lower() == "yes":
                audhd_hits += 1
        rows.append(rec)
        if n % 10 == 0:
            pd.DataFrame(rows).to_csv(OUT, index=False)
            print(f"  [{n}/{len(ret)}] llm-checked {sent}, audhd=yes {audhd_hits}", flush=True)

    pd.DataFrame(rows).to_csv(OUT, index=False)
    out = pd.DataFrame(rows)
    print(f"\nDone. LLM-verified {sent}; AuDHD=yes {int((out['audhd']=='yes').sum())}, "
          f"adult-AuDHD {int((out['adult_audhd']=='yes').sum())}")
    print("audhd:", out["audhd"].value_counts().to_dict())


if __name__ == "__main__":
    main()
