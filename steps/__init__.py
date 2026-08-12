"""Pipeline steps for the literature-search workflow.

Each module corresponds to one stage:
    combine        — concatenate database CSV exports into a single table
    dedupe         — remove duplicate records (by DOI, falling back to title)
    fill_abstracts — fill missing Abstract cells via DOI lookups
    classify       — classify each abstract with OpenAI + Gemini (inter-rater)

`pipeline.py` at the repo root orchestrates the steps and emits PRISMA counts.
"""
