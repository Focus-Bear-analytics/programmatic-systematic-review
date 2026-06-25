- [x] Semantic scholar should use the SEMANTIC_SCHOLAR_API_KEY ENV var
- [x] Semantic scholar shouldn't be restricted by year
- [x] Remove LLM filtering from semantic scholar

# Pipeline
- [x] Pipeline should be split: separate files for separate operations (now in `steps/`)
- [x] De-dupe needs to keep records PRISMA style (rows tagged `is_duplicate=Y`; counts in `prisma_counts.json`)
- [x] Add Gemini API key (already wired up alongside OpenAI for inter-rater reliability)
- [x] Replace magic strings with constants (separate file) return "N" (see `steps/constants.py`)
- [x] Fill missing abstracts needs to be part of pipeline (`steps/fill_abstracts.py` runs between dedupe and classify)
- [ ] Full text screening needs to be separate step in pipeline for ambiguous entries where age group, study type are ok and ND = ADHD or autism. Probably not going to work the way it's laid out. Fill missing abstracts will work better
