# Peer review (adversarial) — Decision: MAJOR REVISION (bordering on reject)

*Simulated hostile-but-competent review of the v1 draft, as if submitted to a journal such as* Autism *or* Journal of Autism and Developmental Disorders. *Purpose: surface every defensible weakness so the manuscript can be hardened.*

---

## Resolution status (after v3 revision + PROSPERO CRD420251082015 retrieval)
| # | Reviewer point | Status in v3 |
|---|---|---|
| 1 | No protocol/registration | **Resolved** — PROSPERO CRD420251082015, registered 8 Aug 2025, predates the 25 May 2026 searches; full protocol uploaded. |
| 2 | Post-hoc/unstable criteria | **Resolved/disclosed** — §2.4 reconciles each criterion; only N≥20 is a post-hoc amendment, shown immaterial (§3.2). |
| 3 | AI-only screening undisclosed | **Resolved** — dual-LLM + human adjudication was *pre-registered*; κ 0.68–0.90 now reported; human-validation subsample still recommended (residual). |
| 4 | Thesis rests on unvalidated outcome coding | **Mitigated** — §4.2 explicitly flagged as interpretation; down-weighted in Limitations; full intent-coding named as next step (residual). |
| 5 | Denominator dishonesty | **Resolved** — design rates reported over determinable cases (59%), missingness foregrounded. |
| 6 | Two studies in one | **Resolved** — primary review vs secondary scoping explicitly separated. |
| 7 | Search reporting absent | **Resolved** — 5 databases + verbatim strings + date (25 May 2026) in §2.1. |
| 8 | No risk-of-bias | **Resolved** — pre-registered RoB-2/ROBINS-I/GRADE stated; N/A given 0 studies; near-miss RoB described. |
| 9 | Op-ed tone | **Improved** — title softened; politics demarcated as interpretation; data leads. |
| 10 | Over-generalisation to AuDHD/ADHD | **Mitigated** — priority claims bounded to autism evidence; gap named explicitly. |
| 11 | Fix-vs-support asserted not coded | **Resolved** — systematic two-rater intent coding of all 543 adult studies (κ=0.51): 49.5% normalisation vs 49.2% support; claim narrowed to "substantial half" + uniformly-normalisation AuDHD slice. |
| 12 | "Engineered void" | **Resolved** — relaxation analysis: 0 under all criteria vs 26 if co-occurrence relaxed. |
| 13 | Diagnostic framing | **Resolved** — DSM-IV→DSM-5 (2013) framing added. |
| 14 | Hypocrisy on co-production | **Resolved** — positionality + COI (Focus Bear) declared. |
| 15 | Missing theory | **Resolved** — monotropism [13] + double-empathy [12] added. |

Residual items to strengthen pre-submission: **complete the blind human-screening validation** (tooling now built — `ADJ_VALIDATE=1`; 596-paper 5% sample) and run `validation-accuracy.py` to report screening sensitivity/specificity (point 3); optionally human-code an intent subsample to corroborate the κ=0.51 LLM coding (point 11).

---

## Editor's summary
The manuscript reports an "empty" systematic review and uses it to launch a neurodiversity critique of the autism/ADHD digital-intervention field. The topic is timely and an empty review is publishable in principle. However, in its current form the paper reads as an advocacy essay wearing the costume of a systematic review. Two reviewers raise overlapping and, in places, fatal concerns about methodological transparency, the validity of an AI-only screening pipeline, criteria that appear to have shifted mid-review, and a discussion that vastly over-reaches its own data. I cannot accept without major revision addressing every point below.

---

## Reviewer 1 (methods / evidence synthesis)

**1. No protocol, no registration (major).** There is no mention of a pre-registered protocol (PROSPERO or OSF). For an empty review this is not a formality — when zero studies are included, the *credibility of the criteria* is the entire result. Without pre-registration, readers cannot distinguish a genuine evidence gap from criteria reverse-engineered to produce one.

**2. Eligibility criteria appear post-hoc and unstable (major).** The narrative betrays criteria that moved during the review: SCEDs excluded, then included, then rendered moot by a newly-introduced N≥20 rule; "digital app-based" defined so as to exclude VR/AR, telecoaching, and wearables. Each choice is individually defensible, but their introduction *after* seeing the data is the cardinal sin of evidence synthesis. The N≥20 threshold in particular is arbitrary and unreferenced — why 20? Justify against a power/precision rationale or a published standard, and report sensitivity to it.

**3. AI-only screening with no human verification (major).** Two LLMs replacing two human screeners is a substantial and under-justified departure from PRISMA/Cochrane norms. There is no inter-rater reliability statistic, no human-screened validation subsample, no accuracy/recall estimate against a gold standard, and no acknowledgement that LLM outputs are non-deterministic and model-version-dependent. The "recall-safe" rule is asserted, not evidenced. At minimum: report κ between raters, validate against a human-screened random sample with sensitivity/specificity, and pin model versions, temperature, and dates.

**4. The "off-target outcome" exclusions drive the entire thesis but rest on unvalidated LLM abstract coding (major).** The polemic ("fixing not supporting") is built on the claim that the literature targets social skills/normalisation rather than attention/EF/emotion-regulation. Yet that outcome split was produced by an LLM, largely from abstracts, with no validation and no human check. If those labels are wrong, the thesis collapses. You cannot make a strong interpretive claim rest on the least-validated step in your pipeline.

**5. Denominator dishonesty in the rigour table (moderate–major).** Table 3 reports "~15% RCT" while simultaneously showing 41% of designs as "not determinable from abstract." Reporting a percentage over a denominator that is 41% missing is misleading. Either retrieve full text to classify design properly, or report rates only over the determinable subset and foreground the missingness.

**6. Two studies masquerading as one (moderate).** The "field characterization" (n=1,338) is a scoping review with its own classification scheme, bolted onto the systematic review. Its labels are never validated and its objective was not stated up front. Separate the questions explicitly, or present the characterization as clearly secondary/exploratory.

**7. Search reporting is absent (major).** No databases named, no date ranges, no search strings, no language limits, no grey-literature strategy. This is non-negotiable for a systematic review and currently makes the search irreproducible. The DSCT snowball seed is given; nothing else is.

**8. Risk-of-bias assessment is missing.** Even with zero included studies, you assessed ~106 at full text. A risk-of-bias treatment of the near-miss studies (the AuDHD SCEDs) would strengthen the rigour argument and is expected.

## Reviewer 2 (the nasty one — neurodiversity / conceptual)

**9. This is an op-ed, not a review.** "Fixing Us, Not Supporting Us"? Section headers that editorialise ("the wrong people, in the wrong way")? The tone will get this desk-rejected at half the journals you'd target. I happen to agree with the politics. That is exactly why you must discipline the rhetoric — a reviewer who *disagrees* will use the tone to dismiss the data. Make the data inescapable and let it carry the argument.

**10. Over-generalisation from autism to AuDHD to ADHD (major).** Your priorities argument leans almost entirely on *autism* community priority-setting. You have no ADHD-specific priority evidence and essentially no *AuDHD-specific* priority evidence, yet you generalise to "ND adults" and "AuDHD adults" throughout. That is precisely the kind of erasure you accuse the field of. Either source ADHD/AuDHD priorities or sharply narrow the claim.

**11. The "fix vs support" dichotomy is asserted, not coded (major).** You never systematically coded intervention *intent* (normalisation vs accommodation/support). You infer it from a non-random, exclusion-selected handful of titles. This is confirmation bias with a footnote. If you want to claim the field is normalisation-oriented, code a defined sample of interventions on a transparent normalisation–accommodation rubric and report the distribution.

**12. "Zero" may be an artifact of your own narrow lens (major).** You stack five conjunctive criteria and act surprised that nothing survives. A hostile reader will say you engineered the void. You must directly engage the counterargument: show what relaxing each criterion yields (you clearly have the data), and argue why the gap is substantive rather than definitional.

**13. Diagnostic framing is sloppy (moderate).** "AuDHD" is colloquial; define it against DSM-5/DSM-5-TR and note that DSM-IV *prohibited* the dual diagnosis until 2013 — which is central to your "historically invisible" claim and currently underexploited. Get the nosology right.

**14. The reviewers' own hypocrisy check (moderate).** You argue for participatory, co-produced research — was *this* review co-produced with AuDHD adults? If not, say so in a positionality/limitations statement. An un-co-produced paper lecturing the field about co-production invites the obvious retort.

**15. Missing constructs.** No mention of monotropism, the double-empathy problem, or sensory/regulation frameworks that would give your "support not correction" argument theoretical teeth. Right now the critique is vibes; give it scaffolding.

---

## Required revisions (consolidated checklist)
- [ ] State registration status honestly (and register if possible); add a protocol-deviation paragraph listing every post-hoc criterion change.
- [ ] Justify N≥20 and the "digital app-based" scope; add sensitivity analyses for the key thresholds.
- [ ] Report AI-screening IRR (κ), a human-validated accuracy estimate, model versions/temperature/dates; reframe as a documented limitation.
- [ ] Validate or explicitly down-weight the outcome and intent coding; do not rest the thesis on unvalidated labels.
- [ ] Fix denominators; report design rates over determinable cases and foreground missingness.
- [ ] Separate the systematic review from the scoping characterization.
- [ ] Report the full search strategy (sources, dates, strings, limits, grey literature).
- [ ] Add risk-of-bias appraisal of the near-miss studies.
- [ ] Tone down to journal register; move politics into a clearly-demarcated Discussion.
- [ ] Narrow priority claims to the evidence (or add ADHD/AuDHD sources); stop generalising.
- [ ] Engage the "criteria-engineered-the-void" counterargument with relaxation analyses.
- [ ] Correct diagnostic framing (DSM-IV→DSM-5 change).
- [ ] Add positionality + co-production limitation.
- [ ] Add theoretical scaffolding (monotropism, double empathy, etc., with citations).
