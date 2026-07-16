# Absent at the Intersection: An Empty Systematic Review of Digital App-Based Interventions for Attention, Executive Function, and Emotional Regulation in Adults with Co-occurring ADHD and Autism (AuDHD)

*Running title: Digital interventions for AuDHD adults — an empty review*

**Jeremy Nagel¹, Leila Karimi¹, Barbora de Courten¹, Russell Conduit¹, Kimmi Ko¹**
¹ RMIT University, Melbourne, Australia. Corresponding author: Jeremy Nagel (s3255727@student.rmit.edu.au; ORCID 0009-0002-6635-7232).
*Registered title (PROSPERO CRD420251082015): "Effectiveness of Digital App-Based Interventions for Adults with Co-occurring ADHD and Autism: A Systematic Review."*

> **Manuscript draft (v3).** All quantitative figures are reproducible from the project pipeline (see Data availability). References [1]–[28] verified online (DOIs/PMIDs confirmed). Five database search strings included verbatim (§2.1); PROSPERO registration (CRD420251082015; registered 8 Aug 2025) and search date (25 May 2026) recorded; eligibility criteria reconciled against the registered protocol (§2.4). Author conflict of interest disclosed (Declarations).

---

## Abstract

**Background.** Co-occurring ADHD and autism ("AuDHD") is common — roughly two in five autistic people meet criteria for ADHD [1,2] — and produces a cognitive–emotional profile that is not simply the sum of its parts [5,6]. Adults with AuDHD report difficulties with attention, executive function (EF), and emotional regulation, yet historically the comorbidity was excluded from study by diagnostic convention [3,4] and adult samples remain scarce [7]. Digital app-based tools are widely promoted as scalable supports for exactly these domains.

**Objectives.** *Primary:* to identify and appraise digital app-based interventions evaluated in adults with co-occurring AuDHD that target attention, EF, or emotional regulation using a controlled design with an adequate sample. *Secondary (scoping):* to characterise the broader autism/ADHD digital-intervention literature for context.

**Methods.** We screened 14,253 de-duplicated records (database searching, citation snowballing, and a targeted snowball of the digital self-control–tools literature) using a recall-safe, dual-rater large-language-model (LLM) screening protocol (Nova 2 Lite + Claude Sonnet 4.6) with full-text adjudication and human oversight. Inter-rater agreement was substantial-to-excellent (Cohen's κ 0.68–0.90). Per the registered protocol, eligibility required: adults formally diagnosed with *both* ASD and ADHD as direct subjects; an interactive digital app-based intervention; a target outcome of attention/EF/emotional regulation; and a controlled design (RCT, quasi-experimental, or controlled observational). The review was prospectively registered (PROSPERO CRD420251082015; registered 8 Aug 2025). We test the robustness of the result with criterion-relaxation analyses and a post-hoc N≥20 sensitivity threshold.

**Results.** **No study met all eligibility criteria (n = 0).** This is not an artefact of stacked criteria: relaxing the co-occurrence requirement to *single*-diagnosis autism or ADHD yielded **26** adult digital studies that met every other criterion, whereas relaxing outcome or rigour while keeping the AuDHD-adult requirement yielded 0–3. The few studies that genuinely enrolled AuDHD adults (n ≈ 3–4) were small single-case designs (N = 1–6) targeting employment, leisure, and behaviour reduction — not attention, EF, or emotional regulation. In the broader field, only 18/1,338 (1.3%) digital-intervention studies involved AuDHD samples, the literature was child-dominant, and among 543 adult studies only ~24% used any control group (41% of designs were not determinable from the abstract).

**Conclusions.** Robust digital-intervention evidence exists for autistic *or* ADHD adults but is effectively absent at their intersection. We argue — explicitly as interpretation, not as a finding — that this pattern, together with the normalisation-oriented focus of the few AuDHD-adult studies that exist, reflects a research agenda misaligned with the priorities neurodivergent communities consistently voice [21–25]. We call for pre-registered, adequately-powered, co-produced research that treats AuDHD as a population in its own right and supports self-defined goals over the correction of visible difference.

**Keywords:** AuDHD; autism; ADHD; digital intervention; executive function; emotional regulation; neurodiversity; empty review.

---

## 1. Introduction

ADHD and autism co-occur far more often than chance: meta-analytic estimates place current ADHD at roughly 38–40% among autistic individuals [1,2]. The combination — increasingly termed "AuDHD" — is not merely additive. Behavioural and neurocognitive studies report distinctive, sometimes opposing, profiles in attention allocation, planning, and self-regulation that differentiate co-occurring cases from either single diagnosis [5,6].

Despite this, adults with AuDHD have been structurally marginalised in the evidence base. Until DSM-5 (2013), diagnostic rules *prohibited* assigning autism and ADHD concurrently, so the comorbidity was, by definition, excluded from a generation of research [3,4]. Autism and ADHD intervention research has also centred children, leaving the adult overlap comparatively unstudied [7]. Where adults are studied, samples are frequently partitioned into "pure" single-diagnosis groups, rendering AuDHD invisible as a population.

Digital, app-based tools — focus and reminder aids, scaffolding and planning apps, mood- and regulation-support apps — are widely marketed as low-cost, in-context supports, and are plausibly well-matched to the self-directed needs of neurodivergent adults. This motivates a specific, answerable question: **what controlled, adequately-powered evidence exists that digital app-based interventions improve attention, executive function, or emotional regulation in adults with co-occurring AuDHD?**

We conducted a systematic review to answer it, with a secondary scoping characterisation of the surrounding literature. We anticipated a thin evidence base; we found an empty one — and, on probing why, a gap that is specific to the AuDHD intersection rather than to our criteria.

---

## 2. Methods

We report against PRISMA 2020. The review was **prospectively registered on PROSPERO (CRD420251082015; first submitted 27 June 2025, registered 8 August 2025)**, with a full protocol uploaded to the registry. Registration and the protocol predate all searches (conducted 25 May 2026), establishing the eligibility criteria — and, notably, the semi-automated dual-LLM screening approach (§2.2) — in advance of record screening. We state eligibility criteria explicitly, reconcile every operational decision against the registered protocol in §2.4, and provide criterion-relaxation sensitivity analyses (§3.2) to demonstrate the robustness of the result.

### 2.1 Information sources and search
Records were drawn from three streams: (1) structured searches of five bibliographic databases — **PubMed, Scopus, PsycINFO, ProQuest, and Web of Science** (all searched on 25 May 2026; no publication-date limits and no language restriction beyond database defaults); (2) backward and forward citation snowballing from relevant systematic reviews via OpenAlex; and (3) a targeted snowball (backward + forward) from a key digital self-control–tools (DSCT) review (seed: doi:10.1145/3571810), included because DSCTs directly target attention and self-regulation. After de-duplication the unified corpus comprised 14,253 records (database 4,817; citation snowballing 9,141; DSCT 295). The PRISMA flow diagram is provided separately (`prisma-flow.md`).

**Search strings (verbatim).** Where supported, searches combined a neurotype block, a digital-intervention block, and an adult block:

- **PubMed / PsycINFO / Web of Science:**
  `((ADHD OR (autis* OR ASD OR Asperger*)) OR (AuDHD)) AND (app OR "mobile application" OR mHealth OR eHealth OR "digital tool" OR web-based OR software OR "digital therapeutics") AND (adult)`
- **Scopus:**
  `((ADHD OR (autis* OR ASD OR Asperger*)) OR (AuDHD)) AND (app OR "mobile application" OR mHealth OR eHealth OR "digital tool" OR web-based OR software OR "digital therapeutics") AND (adult)`
- **ProQuest (broader neurotype/intervention terms with an age filter):**
  `AB,TI(ADHD OR "attention deficit*" OR autis* OR ASD OR Asperger* OR AuDHD OR neurodiverg*) AND AB,TI(mHealth OR eHealth OR "digital health" OR "digital therapeutic*" OR "digital intervention*" OR "digital tool*" OR "online intervention*" OR "internet-based*" OR "web-based*" OR smartphone OR wearable* OR "mobile app*" OR "mobile application*" OR app OR apps OR software) NOT (AB,TI(child* OR paediatric* OR pediatric* OR adolescen* OR infant* OR toddler* OR preschool*) NOT AB,TI(adult* OR "young adult*" OR university OR college OR undergraduate OR workplace OR employee*))`

We note that the database "adult" term was a keyword (not an indexed age limit) and that recall for the AuDHD intersection rests primarily on the broad neurotype block plus citation snowballing; the recall-safe screen (§2.2) and full-text adjudication were the operative eligibility filters.

### 2.2 Screening: recall-safe dual-LLM protocol
As pre-specified in the registered protocol (a "multi-stage, semi-automated screening process … automated full-text parsing and dual LLM-based assessment, followed by human adjudication"), and given corpus size, two LLMs served as independent raters in place of two human screeners: Nova 2 Lite (rater A) and Claude Sonnet 4.6 (rater B), via Amazon Bedrock, temperature 0, fixed prompts, June 2026. Each record with a usable abstract (n = 13,580) was independently classified for population (neurotype; adult; under-18; parent-mediated), intervention type, and study type. A record was excluded **only when both raters agreed on an explicitly excluding value** ("recall-safe"); any disagreement or "unspecified" judgment was carried forward, to full text where necessary.

**Inter-rater reliability** (Cohen's κ; percent agreement) on the unified corpus: neurotype κ = 0.90 (93.8%); study type κ = 0.85 (91.9%); has-adults κ = 0.79 (87.5%); has-under-18 κ = 0.80 (87.2%); intervention type κ = 0.68 (75.4%). Agreement was therefore substantial-to-excellent, weakest (substantial) for the more granular intervention-type taxonomy. All inclusion-critical judgments were confirmed against full text by the review team; abstract-level labels were treated as provisional and never used as the sole basis for inclusion.

### 2.3 Eligibility criteria
Studies were eligible if they met **all** of the following registered criteria:
1. **Adults as direct subjects** — adults (18+) formally diagnosed and directly receiving and measured on the intervention (not parents/carers/teachers/clinicians; not children in parent-mediated designs). Per protocol, samples restricted to the elderly (70+) were excluded unless a broader adult range was reported.
2. **Co-occurring AuDHD sample** — the *same* participants formally diagnosed with both ASD and ADHD using validated criteria (DSM-5/ICD-11). Single-diagnosis groups, or ADHD/autism appearing only as background prevalence or a comorbidity aside, did not qualify.
3. **Digital app-based intervention** — interactive mobile/web apps, software tools, and app-delivered programs designed to improve attention, EF, or emotional regulation. Per protocol, interventions *not* delivered via digital apps (telehealth, coaching, in-person therapy) and passive educational content (online courses, video lectures) were excluded; we additionally treated VR/AR and monitoring-only wearables as outside the "interactive app-based" definition.
4. **Target outcome** — attention, executive function, or emotional regulation (≥1), measured with validated tools (the registered primary outcomes).
5. **Controlled design** — RCT, quasi-experimental, or controlled observational (matched-cohort/case-control) study. Per protocol, uncontrolled (pre-post without comparator), case studies, case series, qualitative-only studies, reviews, editorials, and conference abstracts without full papers were excluded. Eligible comparators included waiting-list, usual care, health coaching, and self-administration of medication.

**Post-hoc robustness threshold (not in the registered protocol).** We additionally applied a minimum sample of **≥20 intervention recipients** as a sensitivity threshold (below which single-group precision is poor). This was an amendment, not a registered criterion; §3.2 shows it is immaterial — the result is identical (0) under the registered design criteria alone, because the only on-target AuDHD-adult study is a single-participant case report excluded under the protocol's case-study exclusion.

### 2.4 Reconciliation with the registered protocol (full disclosure)
We reconcile every consequential operational decision against PROSPERO CRD420251082015:
- **Pre-specified (no deviation).** The population (adults formally diagnosed with *both* ASD and ADHD), the intervention scope (interactive app-based tools; telehealth/coaching and passive content excluded), the outcomes (attention, EF, emotional regulation), the controlled-design requirement (with case studies/series/uncontrolled/qualitative-only excluded), the semi-automated dual-LLM-plus-human screening, and the fallback to structured narrative synthesis where meta-analysis is not feasible were all specified in the registered protocol.
- **Operationalisation, not criterion change.** The outcome criterion was *applied* via a multi-label classification step during full-text review; this is a fidelity/implementation detail, not a change to the registered criterion.
- **One amendment (disclosed).** The **N≥20** minimum sample was added post-registration as a robustness threshold. It is the only substantive departure and is immaterial: applying the registered design criteria alone yields the same result (§3.2). VR/AR and monitoring-only wearables were treated as outside the "interactive app-based" definition — a clarification consistent with, though not explicit in, the protocol.

§3.2 demonstrates the headline result (0 included) is robust to all of these.

### 2.5 Analysis, risk of bias, and certainty
For the primary review, candidates surviving to full text were appraised on population, intervention, outcome, and design (including participant count) from full text. For the secondary scoping characterisation, abstract-level consensus labels (Sonnet where consensus was absent) were tabulated; we report denominators including "not determinable" categories and avoid percentages over heavily-missing denominators. Cohen's κ was computed between raters on the corpus.

Per the registered protocol, risk of bias was to be assessed with Cochrane RoB-2 (randomised) and ROBINS-I (non-randomised), reporting bias via funnel plots/Egger's test, and certainty via GRADE; data were to be synthesised by random-effects meta-analysis (standardised mean differences) or, if infeasible, by structured narrative synthesis. **Because no study met eligibility, formal risk-of-bias scoring, GRADE, and meta-analysis were not applicable**; we instead provide a narrative synthesis (as the protocol pre-specified for the no/insufficient-data case) and a descriptive risk-of-bias characterisation of the near-miss studies (§3.1).

---

## 3. Results

### 3.1 Primary review: the empty result
**No study met all five eligibility criteria (n = 0).** Of 106 reports assessed at full text (78 main-arm candidates + 28 DSCT-snowball referrals), all were excluded — for wrong population (not co-occurring adult AuDHD; n = 58), off-target outcome (n = 17), or insufficient rigour (n = 31). The entire set of studies that genuinely enrolled adults with confirmed co-occurring AuDHD comprised a handful of small single-subject reports (Table 1).

**Table 1. Studies enrolling adults with confirmed co-occurring AuDHD (any outcome/design).**

| Year | Design | N (intervention) | Target | Excluded because |
|---|---|---|---|---|
| 2010 | SCED (multiple-baseline + reversal) | 3 | Employment / job-skill performance | Off-target; N<20 |
| 2013 | Case series | 3 | Employment support | Off-target; uncontrolled; N<20 |
| 2018 | SCED | 1 | Reducing "inappropriate vocalisations" | Off-target; N=1 |
| 2020 | SCED (multiple-baseline) | 6 | Independent leisure engagement | Off-target; N<20 |

Risk of bias in these near-miss studies is high by design: single-subject and case-series methods provide weak control of confounding and limited external validity, and none reported the cognitive/emotional outcomes of interest.

### 3.2 Is the void an artefact of the criteria? (sensitivity analysis)
A natural objection to any empty review is that conjunctive criteria manufacture the emptiness. The data refute this for the criterion that matters (Table 2): relaxing rigour or outcome while retaining the AuDHD-adult requirement still yields 0–3 studies, but relaxing the **co-occurrence** requirement to single-diagnosis autism *or* ADHD yields **26** adult digital studies that meet every other criterion (controlled, N≥20, on-target). The gap is therefore specific to the AuDHD intersection, not to our outcome or rigour thresholds.

**Table 2. Criterion-relaxation analysis (full-text candidate set).**

| Criteria applied | Studies |
|---|---|
| All five (adult + AuDHD + digital + on-target + controlled + N≥20) | **0** |
| Drop outcome (any outcome) | 0 |
| Drop N≥20 (allow small controlled/SCED) | 1 |
| Drop rigour entirely | 1 |
| Drop outcome **and** rigour (just adult + AuDHD + digital) | 3 |
| **Relax AuDHD → single diagnosis** (adult + digital + on-target + controlled + N≥20) | **26** |
| Relax adults → any age (keep AuDHD + on-target + controlled + N≥20) | 0 |

### 3.3 Secondary scoping characterisation
Of 14,253 records, 6,906 concerned autistic and/or ADHD populations (autistic 4,650; ADHD 2,081; AuDHD 175). Of these, 1,338 empirically evaluated a digital intervention (autistic 924; ADHD 396; **AuDHD 18 — 1.3%**); 934 studied children/adolescents and 543 adults. Among AuDHD-labelled digital studies only 11 involved adults, and full-text scrutiny dissolved nearly all into separate diagnostic groups, comorbidity asides, or excluded modalities (a telecoaching cluster; one VR study).

The most common modalities were VR/AR (281), mobile apps (266), robotics (144), and serious games (107). Among the 543 ND-adult digital studies, design could be determined for 322 (59%): RCT 80, non-randomised controlled 51, no control group 191; 220 (41%) were not determinable from the abstract. **Restricted to determinable cases, ~41% had a control group (131/322)**; we foreground the missingness rather than quote a corpus-wide rate.

*These scoping labels are abstract-level and unvalidated against full text beyond the candidate set; they are exploratory context, not primary findings.*

---

## 4. Discussion

We sought controlled, adequately-powered evidence that digital app-based interventions help AuDHD adults with attention, EF, or emotional regulation, and found none. The sensitivity analysis (Table 2) shows the gap is real and specific: a substantial single-diagnosis adult literature exists (26 studies meeting every other bar), but co-occurring AuDHD adults have essentially no controlled evidence. Three observations follow; we distinguish what the data show from how we interpret them.

### 4.1 The intersection is an evidence desert (data)
AuDHD appears in 1.3% of the digital-intervention literature and collapses toward zero once co-occurrence, adulthood, and rigour are jointly required. This is consistent with a field shaped by a diagnostic history that prohibited the dual label until 2013 [3,4] and that still partitions the comorbidity into "pure" groups [7]. AuDHD adults fall through the gap between the autism, ADHD, and paediatric literatures.

### 4.2 What little exists targets correction, not the stated difficulties
*Data (AuDHD-adult studies).* Every study that genuinely enrolled AuDHD adults targeted employment, leisure, or the reduction of observer-defined "inappropriate" behaviour (Table 1) — none targeted attention, EF, or emotional regulation; all were normalisation-oriented.

*Data (field-level intent coding).* To test the broader claim rather than assert it, we coded all 543 adult ND digital-intervention studies on a normalisation–accommodation spectrum with two independent LLM raters (Cohen's κ = 0.51, moderate — intent is inherently contestable). Among the 392 studies on which both raters agreed, the field was almost evenly split: **194 (49.5%) normalisation-oriented** (remediating/reducing neurodivergent traits, or training toward neurotypical behaviour — e.g. social-skills, face/emotion-recognition, behaviour-reduction) and **193 (49.2%) accommodation/support-oriented** (scaffolding self-defined goals, planning/organisation aids, user-directed tools). Normalisation is therefore a *substantial half* of the adult ND digital field — not its entirety.

*Interpretation.* That a field devotes roughly half of its effort to normalising neurodivergent people — and that the AuDHD-adult slice specifically does so uniformly — echoes long-standing neurodiversity critiques of interventions designed to make autistic people *appear* less autistic rather than to support their lived difficulties [12,14,15], and of camouflaging pressures linked to poor mental health and suicidality [16,17,18]. The moderate inter-rater reliability underscores that intent classification is interpretive; we report the full rater split transparently (`nd_digital_adults_intent.csv`) rather than over-claim a single figure.

### 4.3 Misalignment with community priorities (interpretation, bounded by evidence)
Stakeholder priority-setting consistently ranks mental health, well-being, services, and adult-life outcomes above biological cause/cure and behavioural normalisation, and documents a disparity between funding and community priorities [21,22,23,24,25]; autistic adults specifically report unmet needs and a preference for tailored support over standardised correction [26]. We note two boundaries on this argument: the priority evidence is predominantly *autism*-focused, with little ADHD-specific and essentially no AuDHD-specific priority research — itself an instance of the erasure we describe — and we therefore frame the misalignment as a hypothesis consistent with the available evidence rather than a demonstrated fact for AuDHD adults. Conceptually, frameworks such as monotropism [13] and the double-empathy problem [12] reframe attention and social difference as features to be accommodated rather than deficits to be corrected, aligning a "support" model with how neurodivergent adults describe their needs [8,9,10,11,19,20].

### 4.4 Implications and research agenda
- **Treat AuDHD as a population.** Recruit and analyse co-occurring samples rather than discarding the comorbidity.
- **Pre-register and power.** Conduct pre-registered, adequately-powered controlled trials (and rigorous, replicated SCEDs) rather than one-off pilots.
- **Measure what matters.** Prioritise attention, EF, and emotional regulation as experienced by participants, over observable-normalisation endpoints.
- **Co-produce.** Partner with AuDHD adults in setting questions, designing tools, and choosing outcomes [27,28].
- **Reframe digital tools as scaffolds** for self-defined goals and accommodations, not instruments of behavioural correction.

---

## 5. Limitations
**AI-based screening**: two LLMs replaced two human screeners. We mitigated risk with a recall-safe two-rater rule, an "unspecified→carry-forward" pathway, full-text confirmation of all inclusion-critical judgments, fixed prompts/temperature, and reported inter-rater reliability (κ 0.68–0.90); nonetheless LLM outputs are model-version-dependent and non-deterministic, and a human-screened validation subsample with sensitivity/specificity estimates would strengthen confidence and is recommended. **Scoping labels** are abstract-level and unvalidated beyond the candidate set; design determinability was only 59%, and we report rates over determinable cases. **Intent classification** (§4.2) was performed systematically (two raters over all 543 adult studies) but has only moderate inter-rater reliability (κ = 0.51), reflecting the genuine contestability of coding intervention "intent"; we report the full rater split transparently and treat the normalisation–support balance as indicative rather than definitive. Human-coded validation of a subsample would strengthen it. **Scope choices** (treating VR/AR and monitoring wearables as outside the app-based definition; the post-hoc N≥20 threshold) are defensible but consequential; Table 2 shows the central result is robust to them. **Conflict of interest:** the lead author founds and develops a commercial executive-function app for neurodivergent adults (see Declarations); although no such product was eligible or assessed (the review found zero eligible studies), readers should weigh this interest, particularly in the interpretive §4.2–4.3. **Positionality / co-production:** this review was conducted by the research team and was **not itself co-produced with AuDHD adults** — a limitation we name directly given our call for participatory research, and which future iterations should remedy.

## 6. Conclusion
There is currently **no controlled, adequately-powered evidence** that digital app-based interventions improve attention, executive function, or emotional regulation in adults with co-occurring AuDHD. The emptiness is specific: rigorous, on-target digital interventions exist for autistic or ADHD adults, but not for their common co-occurrence, and the little AuDHD-adult work that exists aims at correcting visible behaviour rather than supporting lived cognitive and emotional difficulty. Naming that gap — and the misalignment it implies between research effort and community priority — is the contribution of this empty review. AuDHD adults need rigorous, co-produced tools that support how they think and feel; until the field's questions align with theirs, the centre will stay empty while the periphery fills.

---

## Declarations

**Conflict of interest.** JN is the founder of Focus Bear, a commercial digital application designed to support executive functioning in neurodivergent individuals, including people with ADHD and autism; this interest is disclosed in the PROSPERO registration and here. The review is independent of that product, which was neither eligible for nor assessed in this review (no study met eligibility). To mitigate interpretive bias, eligibility and screening were pre-registered, screening decisions were dual-rater with human adjudication, and the data-driven findings (§3) are separated from interpretation (§4). The remaining authors (LK, BdC, RC, KK) declare no competing interests.

**Funding.** No specific or external funding. JN is supported by an RMIT University PhD scholarship; the review is supported non-commercially by the review team's institution.

**Author contributions.** JN (guarantor) designed and registered the review, built the screening pipeline, conducted screening/adjudication, and drafted the manuscript. LK, BdC, RC, and KK provided supervision, methodological guidance, and critical revision. All authors approved the final manuscript.

**Ethics.** Secondary analysis of published literature; no human-participant data were collected.

---

## References
1. Lai M-C, Kassee C, Besney R, et al. Prevalence of co-occurring mental health diagnoses in the autism population: a systematic review and meta-analysis. *Lancet Psychiatry*. 2019;6(10):819–829. doi:10.1016/S2215-0366(19)30289-5
2. Rong Y, Yang C-J, Jin Y, Wang Y. Prevalence of attention-deficit/hyperactivity disorder in individuals with autism spectrum disorder: a meta-analysis. *Res Autism Spectr Disord*. 2021;83:101759. doi:10.1016/j.rasd.2021.101759
3. Leitner Y. The co-occurrence of autism and attention deficit hyperactivity disorder in children — what do we know? *Front Hum Neurosci*. 2014;8:268. doi:10.3389/fnhum.2014.00268
4. Gargaro BA, Rinehart NJ, Bradshaw JL, Tonge BJ, Sheppard DM. Autism and ADHD: how far have we come in the comorbidity debate? *Neurosci Biobehav Rev*. 2011;35(5):1081–1088. doi:10.1016/j.neubiorev.2010.11.002
5. Wang T, Bai M, Zhang Z, Jia F. The unique cognitive phenotype of ASD + ADHD co-occurrence: evidence for planning and attention deficits as a differentiating approach. *Front Pediatr*. 2025;13:1703264. doi:10.3389/fped.2025.1703264
6. Watanabe D, Watanabe T. Distinct frontoparietal brain dynamics underlying the co-occurrence of autism and ADHD. *eNeuro*. 2023;10(7):ENEURO.0146-23.2023. doi:10.1523/ENEURO.0146-23.2023
7. Lau-Zhu A, Fritz A, McLoughlin G. Overlaps and distinctions between ADHD and ASD in young adulthood: systematic review and guiding framework for EEG-imaging research. *Neurosci Biobehav Rev*. 2019;96:93–115. doi:10.1016/j.neubiorev.2018.10.009
8. Kapp SK, Gillespie-Lynch K, Sherman LE, Hutman T. Deficit, difference, or both? Autism and neurodiversity. *Dev Psychol*. 2013;49(1):59–71. doi:10.1037/a0028353
9. Pellicano E, den Houting J. Annual Research Review: shifting from 'normal science' to neurodiversity in autism science. *J Child Psychol Psychiatry*. 2022;63(4):381–396. doi:10.1111/jcpp.13534
10. Dwyer P. The neurodiversity approach(es): what are they and what do they mean for researchers? *Hum Dev*. 2022;66(2):73–92. doi:10.1159/000523723
11. den Houting J. Neurodiversity: an insider's perspective. *Autism*. 2019;23(2):271–273. doi:10.1177/1362361318820762
12. Milton DEM. On the ontological status of autism: the 'double empathy problem'. *Disabil Soc*. 2012;27(6):883–887. doi:10.1080/09687599.2012.710008
13. Murray D, Lesser M, Lawson W. Attention, monotropism and the diagnostic criteria for autism. *Autism*. 2005;9(2):139–156. doi:10.1177/1362361305051398
14. Wilkenfeld DA, McCarthy AM. Ethical concerns with applied behavior analysis for autism spectrum "disorder". *Kennedy Inst Ethics J*. 2020;30(1):31–69. doi:10.1353/ken.2020.0000
15. Bottema-Beutel K, Park H, Kim SY. Commentary on social skills training curricula for individuals with ASD: social interaction, authenticity, and stigma. *J Autism Dev Disord*. 2018;48(3):953–964. doi:10.1007/s10803-017-3400-1
16. Cassidy S, Bradley L, Shaw R, Baron-Cohen S. Risk markers for suicidality in autistic adults. *Mol Autism*. 2018;9:42. doi:10.1186/s13229-018-0226-4
17. Cage E, Troxell-Whitman Z. Understanding the reasons, contexts and costs of camouflaging for autistic adults. *J Autism Dev Disord*. 2019;49(5):1899–1911. doi:10.1007/s10803-018-03878-x
18. Hull L, Petrides KV, Allison C, et al. "Putting on my best normal": social camouflaging in adults with autism spectrum conditions. *J Autism Dev Disord*. 2017;47(8):2519–2534. doi:10.1007/s10803-017-3166-5
19. Leadbitter K, Buckle KL, Ellis C, Dekker M. Autistic self-advocacy and the neurodiversity movement: implications for autism early intervention research and practice. *Front Psychol*. 2021;12:635690. doi:10.3389/fpsyg.2021.635690
20. Bottema-Beutel K, Kapp SK, Lester JN, Sasson NJ, Hand BN. Avoiding ableist language: suggestions for autism researchers. *Autism Adulthood*. 2021;3(1):18–29. doi:10.1089/aut.2020.0014
21. Pellicano E, Dinsmore A, Charman T. What should autism research focus upon? Community views and priorities from the United Kingdom. *Autism*. 2014;18(7):756–770. doi:10.1177/1362361314529627
22. Roche L, Adams D, Clark M. Research priorities of the autism community: a systematic review of key stakeholder perspectives. *Autism*. 2021;25(2):336–348. doi:10.1177/1362361320967790
23. Frazier TW, Dawson G, Murray D, Shih A, Sachs JS, Geiger A. Brief report: a survey of autism research priorities across a diverse community of stakeholders. *J Autism Dev Disord*. 2018;48(11):3965–3971. doi:10.1007/s10803-018-3642-6
24. Autistica & James Lind Alliance Autism Priority Setting Partnership. *Your priorities for autism research (Top 10)*. London: Autistica; 2016. https://www.autistica.org.uk/our-research/your-research-priorities
25. Cage E, Crompton CJ, Dantas S, et al. What are the autism research priorities of autistic adults in Scotland? *Autism*. 2024;28(9):2179–2190. doi:10.1177/13623613231222656
26. Jose C, George-Zwicker P, Bouma A, et al. The associations between clinical, social, financial factors and unmet needs of autistic adults. *Autism Adulthood*. 2021;3(3):266–274. doi:10.1089/aut.2020.0027
27. Fletcher-Watson S, Adams J, Brook K, et al. Making the future together: shaping autism research through meaningful participation. *Autism*. 2019;23(4):943–953. doi:10.1177/1362361318786721
28. den Houting J, Higgins J, Isaacs K, Mahony J, Pellicano E. 'I'm not just a guinea pig': academic and community perceptions of participatory autism research. *Autism*. 2021;25(1):148–163. doi:10.1177/1362361320951696

---

### Data availability
Unified corpus and labels: `all_papers.csv` (14,253). Relevant-field subset: `nd_digital_empirical.csv` (1,338). Candidate-level decisions and full-text appraisal: `fulltext_review_master.csv`. DSCT snowball: `dsct_recallsafe.csv`, `dsct_resolved.csv`. PRISMA flow: `prisma-flow.md`. Screening prompts, pipeline code, and the criterion-relaxation script are in the project repository.
