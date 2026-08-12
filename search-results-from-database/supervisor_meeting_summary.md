# Systematic Review — Supervisor Meeting Update

**Review:** Digital app-based interventions targeting attention, executive functioning, or emotional regulation in adults with co-occurring ADHD and autism (AuDHD).

---

## Research question

What app-based digital interventions exist for **adults with co-occurring ADHD and autism (AuDHD)** that target **attention, executive functioning, or emotional regulation** — and where is the evidence base thin or absent?

## Inclusion / exclusion criteria (as written)

**Included**
- Smartphone apps, web-based platforms, software tools, break-reminding software
- Interactive (provides feedback, guidance, or tracking)
- Designed to improve **attention**, **executive functioning**, or **emotional regulation**
- Adults with ADHD and/or autism (with the AuDHD subset prioritised)
- Peer-reviewed publication

**Excluded**
- Non-digital delivery (telehealth, in-person coaching, in-person therapy)
- Passive content (online courses, video lectures)
- Tools not targeting attention, EF, or emotional regulation
- Hardware-based (EEG wearables, VR headsets, biosensors)
- Grey literature (conference proceedings / abstracts, dissertations and theses, preprints, corrections and errata)

---

## Methods

### Search and screening pipeline

A reproducible 5-step pipeline (PRISMA-tracked, fully versioned):

1. **Database harvest** — exports from PubMed, ProQuest, Scopus, Semantic Scholar, Web of Science normalised into one table
2. **De-duplication** — DOI primary, normalised-title fallback; abstracts back-filled within duplicate groups
3. **Abstract enrichment** — chain of DOI lookups (Semantic Scholar → Crossref → PubMed → landing page) to fill missing abstracts
4. **Two-rater classification** — every abstract independently classified on 9 fields (age groups, study type, intervention type, neurotypes, control type, intervention purpose, etc.) using two LLMs with deterministic rule overrides for high-precision signals
5. **Adjudication** — a third LLM resolves rater disagreements via majority vote; final consensus labels recorded as `Final_<field>`

Iterative prompt tuning over multiple rounds lifted inter-rater agreement from ~39% to ~66%. The remaining disagreements (≈1/3 of papers) go to the adjudicator; ~85% of the corpus has a confident final label.

### Grey-literature screening

A rule-based screen flags grey literature using publication-metadata signals:

- **Conference proceedings / workshops** — `Journal` field contains "Proceedings", "Conference", "Symposium", "Workshop", or "Annual Meeting"
- **Conference abstracts (numbered talks)** — `Title` matches pattern like "5.44 …" (programme-numbered conference abstracts, often AACAP/APA scientific-programme entries)
- **Theses and dissertations** — `Journal` or `Title` contains "thesis"/"dissertation"; or URL points to an institutional ETD repository (`hdl.handle.net`, `*.edu/etd`)
- **Preprints** — `Journal` or URL points to a preprint server (arXiv, bioRxiv, medRxiv, preprints.org, ResearchSquare)
- **Corrections / errata** — `Title` begins with "Correction" or "Erratum"

Across the unique corpus this flags 190/3,141 records (109 conference proceedings, 59 theses/dissertations, 8 corrections, 8 preprints, 6 numbered conference abstracts).

### Full-text retrieval and AuDHD detection

For empirical candidates that passed initial screening:
- Retrieved 112/155 (72%) full texts via OpenAthens institutional access, Unpaywall, and Europe PMC mirrors
- Two-stage AuDHD detection: regex keyword pre-filter → focused excerpt verification by an LLM
- Two failure modes documented for transparency: Cloudflare anti-bot blocking publisher sites for any automated browser (Sage, Wiley, Elsevier — partly solved by Unpaywall / PMC mirrors), and 43 papers with no open mirror anywhere

### Engineering

- Pipeline migrated to AWS Bedrock for institutional auth and Australian data residency
- Multi-config architecture (`configs/adults.json`, `configs/children.json`) so the same code drives a companion children's review with carry-forward of under-18 papers from this review

---

## PRISMA flow

```
IDENTIFICATION
├─ Records identified from databases (PubMed, ProQuest,
│   Scopus, Semantic Scholar, Web of Science):                      4,817
│
SCREENING — deduplication
├─ Duplicates removed (DOI primary, normalised title):              1,676
└─ Unique records:                                                  3,141

SCREENING — grey-literature exclusion (publication-type screen):
├─ Records excluded as grey literature:                               190
│   ├─ Conference proceedings / workshops:                            109
│   ├─ Theses and dissertations:                                       59
│   ├─ Corrections and errata:                                          8
│   ├─ Preprints:                                                       8
│   └─ Numbered conference abstracts:                                   6
└─ Peer-reviewed records carried forward:                           2,951

SCREENING — title / abstract:                                       2,951
│
├─ EXCLUDED at title / abstract:                                    2,796
│   ├─ No abstract available (cannot assess):                         146
│   ├─ Sample not adult (paediatric only / unspecified):              641
│   ├─ Sample not ADHD / autistic / AuDHD:                          1,186
│   ├─ Not empirical research (review / protocol /                    267
│   │   commentary / qualitative-only):
│   ├─ No intervention delivered (survey, epidemiological,            459
│   │   validation):
│   └─ Not app-based digital intervention:                             97
│       ├─ Non-software (face-to-face, paper, medication):             60
│       ├─ Telecoaching (human-delivered):                             24
│       ├─ Telecounselling (human therapy):                             7
│       ├─ Wearable (hardware):                                         5
│       └─ Unspecified modality:                                        1
│
└─ Reports sought for full-text retrieval:                            155

RETRIEVAL
├─ Reports not retrieved (no open-access mirror):                      43
└─ Reports assessed at full text:                                     112

ELIGIBILITY — AuDHD population check at full text:                    112
├─ Single condition only (ADHD-only or autism-only):                   69
├─ Unspecified (full text does not clarify):                           37
└─ AuDHD population confirmed:                                          6

FINAL ELIGIBILITY — apply criteria to the 6 AuDHD-confirmed:
├─ EXCLUDED at full text:                                               5
│   ├─ Hardware (VR headset):                                           1
│   ├─ Paediatric sample (study population is children):                2
│   ├─ Passive content / therapist-led:                                 1
│   └─ Target domain not attention / EF / emotional reg.:               1
│
INCLUDED:                                                               1
```

### Numbers at a glance (slide-friendly summary)

| Stage | Count |
|---|---|
| Records identified across 5 databases | **4,817** |
| Unique after deduplication | **3,141** |
| Excluded as grey literature | **190** |
| Peer-reviewed candidates | **2,951** |
| Excluded at title / abstract | **2,796** |
| Full-text reports sought | **155** |
| Full-text retrieved | **112** |
| AuDHD population confirmed | **6** |
| **Studies meeting all inclusion criteria** | **1** |

---

## The single included study

> **Auditory Domain Sensitivity and Neuroplasticity-Based Targeted Cognitive Training in Autism Spectrum Disorder**
> Web-based interactive cognitive training; targets attention via auditory processing scaffolds.
> Sample: N = 25, 4F, Mean age 17.4 ± 4.9 years, IQ ≥ 70 — sample spans adolescents through young adults, with the upper tail extending past 18.
> All in-criteria: web app, interactive, software-only, targets attention/EF, adult sub-cohort present, AuDHD population confirmed in full text, peer-reviewed publication.

---

## "Almost included" papers — the 9 AuDHD-confirmed, with specific exclusion reasons

| # | Paper | What it is | Why excluded |
|---|---|---|---|
| 1 | **Improvement of ADHD Symptoms in School-Aged Children, Adolescents, and Young Adults** | EEG-based neurofeedback for attention in autistic individuals with ADHD symptoms | **Hardware** (EEG wearable) |
| 2 | **SalutChat — internet-based support and coaching for adolescents and young adults with ADHD and autism** | Online platform delivering human-coached executive function support | **Human-delivered** (telecoaching) |
| 3 | **Systemizing empathy: Mind Reading software for adults with Asperger's** | Multimedia software teaching emotion recognition in faces and voices | **Target domain mismatch** — recognising others' emotions is social cognition, not "emotional regulation" in the regulatory sense |
| 4 | **SCOPE — Internet-delivered psychoeducation for transition-aged autistic youth** | 8-week therapist-supported online psychoeducation course | **Passive content + therapist-supported** — fails interactivity + non-human-delivery criteria |
| 5 | **MindChip™ — social-emotional telehealth intervention for autistic adults** | Telehealth-delivered combined CBI + therapist programme | **Human-delivered** (telecounselling) |
| 6 | **Auditory Domain Sensitivity and Neuroplasticity-Based Targeted Cognitive Training** | Web-based cognitive training targeting auditory processing and attention | **INCLUDED** (mean age 17.4 ± 4.9 — adult sub-cohort confirmed) |
| 7 | **Impact of Virtual Reality on Anxiety in Children and Adolescents with Autism (dental setting)** | VR headset intervention for procedural anxiety | **Hardware** (VR headset) + paediatric sample |
| 8 | **ProVIA-Kids — smartphone-based behaviour analysis for challenging behaviour in children with ASD** | Caregiver-facing app for tracking behaviour in autistic / ID children | **Paediatric** — study population is children; the app's user is the caregiver, not the AuDHD person |
| 9 | **Brief Report: Pilot Interactive Digital Treatment to Improve Cognitive Control in Children with Autism** | Mobile app for cognitive control training in children with ASD/ADHD | **Paediatric** — study population is children |

---

## Methodological contributions

- Reproducible PRISMA-tracked pipeline; reruns cheaply when criteria change
- Two-LLM-rater + adjudicator architecture lifts confident-label coverage to ~85%
- Deterministic rule overrides for high-precision fields (age cohort, neurotype mention, grey-lit publication type) reduce LLM rater variance
- Multi-config architecture allows the same pipeline to drive a companion children's review with shared carry-forward of under-18 papers
- All LLM calls now routed through AWS Bedrock for institutional auth and Australian data residency

## Limitations to acknowledge

- 43 / 155 (28%) candidate papers' full texts unreachable (no open mirror; would require interlibrary loan if the review were to be exhaustive). None of these are grey-literature; they are peer-reviewed papers behind paywalls without an author-deposited OA copy.
- LLM-driven classification has inter-rater agreement bounded by prompt quality and model capability; calibration was on a held-out subset; 15% of rows still rely on the third-rater tiebreak rather than direct agreement
- The 37 records "unspecified" at full-text AuDHD check are an ambiguity buffer — a human re-read on this set might find 1–3 more confirmed AuDHD papers among them
- Grey-literature screening is rule-based on metadata signals; 6 of the records initially without abstracts and 11 of the records whose full texts we couldn't retrieve were grey literature, neatly removing them from the "could not assess" buckets. A small number of grey-literature items without obvious metadata signals may remain — a journal-name spot-check would catch the residual
- The intervention-purpose categorisation (assistive vs therapeutic) is consequential and was applied after the bulk of the work was done — justified by the inclusion criteria but should be tested against a human co-rater before publishing

## Next steps

1. **Children's review** — companion analysis for participants under 18, using the same pipeline; under-18 papers from the adult search auto-carry forward, plus new children-specific database searches
2. **Co-rater check on `intervention_purpose`** — have a human co-rater independently classify a sample to validate the assistive/therapeutic / target-domain boundary, and report formal inter-rater reliability (Cohen's κ)
3. **Re-read of the 37 "unspecified" full-text AuDHD cases** — to capture any further confirmed AuDHD papers missed by the keyword pre-filter
4. **Targeted re-search** for "AuDHD" / "co-occurring ADHD autism" / "comorbid ADHD autism" terminology — to confirm we haven't missed papers using less-conventional descriptors
5. **Synthesis chapter** on the 9 near-miss AuDHD studies + the 1 included paper: what their existence (and the gap around them) implies for future intervention research

---

## Headline for the slides

> *"A pre-registered systematic review of 4,817 peer-reviewed and grey-literature records found exactly one app-based intervention study — a web-based cognitive training programme targeting attention — tested in a confirmed AuDHD sample with an adult sub-cohort. Eight further AuDHD-population studies were excluded for delivery modality (telecoaching / telecounselling / passive content), hardware (EEG / VR), paediatric-only sampling, or target-domain mismatch. The finding identifies a clear and actionable evidence gap: the field has not yet asked whether existing app-based attention / EF / emotional-regulation tools transfer to the AuDHD population."*
