- [ ] Semantic scholar should use the SEMANTIC_SCHOLAR_API_KEY ENV var
- [ ] Semantic scholar shouldn't be restricted by year
- [ ] Remove LLM filtering from semantic scholar

# Pipeline
- [ ] Pipeline should be split: separate files for separate operations
- [ ] De-dupe needs to keep records PRISMA style
- [ ] Add Gemini API key
- [ ] Replace magic strings with constants (separate file) return "N"
- [ ] Fill missing abstracts needs to be part of pipeline
- [ ] Full text screening needs to be separate step in pipeline for ambiguous entries where age group, study type are ok and ND = ADHD or autism. Probably not going to work the way it's laid out. Fill missing abstracts will work better
