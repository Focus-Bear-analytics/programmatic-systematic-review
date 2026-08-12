# TODO — finish the AuDHD digital-interventions review + manuscript

Everything left to do, in priority order, with exact commands.
Run all commands from the repo root: `/Users/s3255727/dev/literature-search`.

---

## 0. Prerequisite — AWS login (only for steps that call the AI)
The Bedrock SSO token expires ~daily. If a command errors with "Token has expired", run:
```
aws sso login --profile phd
```
(In a Claude Code session, run inline: `! aws sso login --profile phd`.)
**Steps 1 and 2 are manual browser screening — they do NOT need AWS.**

---

## 1. ⭐ Blind screening validation (PRIORITY — answers Reviewer point #3)
Screen a random 5% of the corpus *blind* (AI answers hidden) to report screening accuracy.
This validates the **primary inclusion decisions** — the most important manual task.

**Start it (ENRICHED — recommended, gives a real recall estimate):**
```
ADJ_VALIDATE=1 VALIDATE_ENRICHED=1 poetry run python adjudicate_ui.py
```
Open <http://localhost:8000>. You'll see **598 papers** (title + abstract, keyword-highlighted;
no AI labels), stratified so recall is actually testable:
- **keep 238** — every paper the AI kept at screen level (tests over-inclusion / precision)
- **border 220** — AI-excluded but raters disagreed or hit `unspecified` (where missed includes hide)
- **excl 140** — confident excludes (bounds the false-negative rate in the mass)
Strata are interleaved and each carries a population weight, so `validation-accuracy.py` reports
an unbiased **population** sensitivity/specificity (weights: keep 1.0, border 27.1, excl 40.8 → 11,916).
- Pick a value for every field, save, repeat. Keyboard: `1`–`9` pick · `Tab` next field · `Enter` save & next · `[` / `]` prev/next.
- **Early-exit:** picking a decisive-exclude value — `has_adults=no` (children), a non-empirical `study_type` (review/commentary/protocol/proposal), `neurotypes=neither_adhd_nor_autistic`, or a non-digital `intervention_type` — auto-saves and skips to the next paper (no need to fill the rest). `unspecified` never skips (recall-safe).
- **Resumable** — Ctrl-C anytime; rerun the same command to continue.
- Tune sizes BEFORE starting, e.g. `VALIDATE_N_BORDER=150 VALIDATE_N_EXCL=100 ...` (keep = all 238 unless `VALIDATE_N_KEEP` set).
- Plain flat 5% random instead (weaker on recall): drop `VALIDATE_ENRICHED=1` (→ 596 unstratified).
- Saved to `search-results-from-database/validation_sample.csv` (`Validate_*` + `Validate_stratum*`).

**When done (no AWS needed):**
```
poetry run python validation-accuracy.py
```
Prints per-field κ + screen sensitivity/specificity (you = reference standard).
→ **Then ask Claude** to paste those numbers into Methods §2.2 + Limitations §5.

---

## 2. ✅ DONE — Intent-disagreement adjudication (firms up Discussion §4.2)
FINAL (hybrid adult restriction, 213 studies): normalisation 36.6% / accommodation_support 31.0%
/ skills_training ~29.6% / unclear. Robust: normalisation is the largest single orientation but
never a majority across every cut. Age-gate excluded 8 (human) + 102 (under-18 flag fallback).
→ next: ask Claude to wire these into manuscript §4.2.

<details><summary>original instructions</summary>
Resolve the intervention-intent disagreements under the **3-way** scheme: **normalisation**
(internal → neurotypical standard) vs **skills_training** (internal → ND-affirming) vs
**accommodation_support** (external). Both raters' picks shown; you choose.
(Set is now **323 unique adults** — PRISMA-flagged duplicates `is_duplicate=Y` removed.
101 disagreements total; **40 already decided** (recovered from your earlier session), so **64 remain**.)

**Start it:**
```
ADJ_INTENT=1 poetry run python adjudicate_ui.py
```
Open <http://localhost:8000> (~64 left to resolve; already-decided + agreed rows are skipped).
- Keyboard: `1`–`4` pick (normalisation / skills_training / accommodation_support / unclear) · `a`/`b` copy Rater A/B · `Enter` save & next. Resumable.
- Key call is normalisation vs skills_training: decide by WHOSE standard defines success —
  neurotypical standard (fewer symptoms, fitting in) = normalisation; the person's own goals
  worked with their neurotype = skills_training.
- Intervention description shown atop each abstract to aid the call.
- Saved to `search-results-from-database/nd_digital_adults_intent.csv` (`intent_final`).

**When done (no AWS needed):**
```
poetry run python intent-summary.py
```
→ **Then ask Claude** to update §4.2 with the final 3-way split. Agreed-only baseline (of 221):
normalisation 48.4% / accommodation_support 28.1% / skills_training 20.8% (κ=0.540); it shifts
once all 323 are resolved.
</details>

---

## 3. Manuscript — final touches
Files in `manuscript/`: `audhd-digital-interventions-review.md` (paper v3),
`prisma-flow.md` (PRISMA), `peer-review.md` (adversarial review + resolution table).
- [ ] Insert **validation accuracy** numbers (step 1) → §2.2 + §5.
- [ ] Insert **final intent split** (step 2) → §4.2.
- [ ] Co-author review / sign-off (Karimi, de Courten, Conduit, Ko).
- [ ] Confirm the **COI statement** (Focus Bear) with the team — drafted in Declarations.
- [ ] Optional: render `prisma-flow.md` Mermaid → PNG/SVG (ask Claude).
- [ ] Choose target journal; tune the polemical register to fit.

Already done: PROSPERO (CRD420251082015), 5 search strings + date (25 May 2026), 28 verified
references, inter-rater κ, criterion-relaxation analysis, COI declaration.

---

## Key results (so you don't re-derive)
- **Included: 0** — confirmed empty review (adults + co-occurring AuDHD + digital app + attention/EF/emotion-reg + controlled design).
- Robustness: 0 under all criteria; **26** if co-occurrence relaxed to single diagnosis → gap is AuDHD-specific.
- Field: 1,338 ND digital studies; only 18 (1.3%) AuDHD; child-dominant; ~24% of adult studies controlled.

## File map
- Unified corpus + AI labels: `search-results-from-database/all_papers.csv` (14,253)
- Candidates + full-text decisions: `search-results-from-database/fulltext_review_master.csv`
- Field set: `search-results-from-database/nd_digital_empirical.csv` (1,338)
- Intent coding: `search-results-from-database/nd_digital_adults_intent.csv` (543)

---
---

# Developer / pipeline backlog (historical — mostly complete)
- [x] Semantic scholar should use the SEMANTIC_SCHOLAR_API_KEY ENV var
- [x] Semantic scholar shouldn't be restricted by year
- [x] Remove LLM filtering from semantic scholar

## Pipeline
- [x] Pipeline should be split: separate files for separate operations (now in `steps/`)
- [x] De-dupe needs to keep records PRISMA style (rows tagged `is_duplicate=Y`; counts in `prisma_counts.json`)
- [x] Add Gemini API key (already wired up alongside OpenAI for inter-rater reliability)
- [x] Replace magic strings with constants (separate file) return "N" (see `steps/constants.py`)
- [x] Fill missing abstracts needs to be part of pipeline (`steps/fill_abstracts.py` runs between dedupe and classify)
- [ ] Full text screening needs to be separate step in pipeline for ambiguous entries where age group, study type are ok and ND = ADHD or autism. Probably not going to work the way it's laid out. Fill missing abstracts will work better
