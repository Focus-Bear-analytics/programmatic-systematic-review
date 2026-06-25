"""Column aliasing and classification schema for the pipeline.

`COLUMN_ALIASES` maps the standard column name we use internally to the
case-insensitive aliases seen across database exports.  When you encounter a
new database with different headers, add its aliases here.
"""

from __future__ import annotations

from typing import Any

from .constants import (
    COL_ABSTRACT,
    COL_AUTHORS,
    COL_DOI,
    COL_JOURNAL,
    COL_PMID,
    COL_SOURCE,
    COL_TITLE,
    COL_URL,
    COL_YEAR,
    UNSPECIFIED,
)

COLUMN_ALIASES: dict[str, list[str]] = {
    COL_TITLE: [
        "title", "article title", "articletitle", "ti",
        "document title", "primary title",
    ],
    COL_ABSTRACT: ["abstract", "ab", "abstract note", "summary"],
    COL_AUTHORS: [
        "authors", "author", "au", "author full names",
        "byline", "creator", "creators",
    ],
    COL_YEAR: [
        "year", "publication year", "py", "pub year",
        "publish year", "pubyear", "date",
    ],
    COL_DOI: ["doi", "digital object identifier", "digitalobjectidentifier"],
    COL_URL: [
        "url", "link", "permalink", "source url",
        "document url", "documenturl",
    ],
    COL_PMID: ["pmid", "pubmed id"],
    COL_JOURNAL: [
        "journal", "journal/book", "source title", "publication title",
        "publication", "source", "journal title", "pubtitle",
    ],
}
STANDARD_COLUMNS = [COL_SOURCE, *COLUMN_ALIASES.keys()]


# --- Classification schema ----------------------------------------------
ALLOWED = {
    "has_adults": ["yes", "no", UNSPECIFIED],
    "has_under_18": ["yes", "no", UNSPECIFIED],
    "study_type": [
        "empirical_with_results", "commentary", "review", "protocol",
        "proposal", "case_study", "qualitative_only_study", UNSPECIFIED,
    ],
    "intervention_type": [
        "mobile_app", "web_app", "software_tool", "video_game", "telecoaching",
        "telecounselling", "wearable", "vr_ar", "video_modeling", "non_software_based",
        "parent_training", "data_collection_only", "no_intervention", UNSPECIFIED,
    ],
    "neurotypes": [
        "adhd", "autistic", "audhd", "neither_adhd_nor_autistic", UNSPECIFIED,
    ],
    "control_type": [
        "no_control_group", "rct", "non_randomised_control", UNSPECIFIED,
    ],
}

ALL_FIELDS = [
    "has_adults",
    "has_under_18",
    "study_type",
    "intervention_type",
    "intervention_details",
    "neurotypes",
    "control_type",
    "study_duration_days",
    "outcomes_measured",
]

# Fields that must agree across raters for the row to be flagged as
# "consensus reached" — narrative fields like intervention_details are
# excluded because they are free-text and will rarely match verbatim.
CONSENSUS_FIELDS = [
    "has_adults", "has_under_18", "study_type", "intervention_type", "neurotypes",
]

CLASSIFICATION_PROMPT = f"""You analyse a research abstract and return a JSON object classifying the study. Use the listed enum values verbatim. Apply the rules below precisely — they are written so two independent raters reach the same label.

GENERAL RULE: prefer a specific value when the abstract clearly supports one; use "{UNSPECIFIED}" when it does not, following each field's rule below. Do not guess.

REASONING FIRST: the FIRST key in your JSON must be "reasoning" — 1-3 sentences that, citing the abstract, state (a) the study population, its ages (any participants under 18? any 18+?), and whether it is identified as ADHD/autistic or some other group, (b) whether an intervention is actually delivered and, if so, exactly what it is, and (c) the study design (primary study with results, qualitative, review, protocol, etc.). Derive every label below from this reasoning.

Fields:

- has_adults: one of {ALLOWED['has_adults']}. "yes" if the study sample includes any participants aged 18 or older; "no" if the sample is entirely under 18; "{UNSPECIFIED}" if no age information is given.
- has_under_18: one of {ALLOWED['has_under_18']}. "yes" if the sample includes any participants younger than 18; "no" if the sample is entirely 18 or older; "{UNSPECIFIED}" if no age information is given.
  Treat the described population ITSELF as an age cue (not only explicit numbers). Inherently-adult samples — adults, patients of an adult/general clinic, university or college students, employees/workers, parents, carers, teachers, clinicians, military personnel, or a general adult public — are has_adults=yes, has_under_18=no. Inherently-minor samples — infants, preschoolers, schoolchildren, adolescents, paediatric patients — are has_under_18=yes, has_adults=no. An explicit age range or groups spanning the 18 boundary (e.g. ages 15-25, "6 to 18", "adolescents and young adults", or "children and their parents") -> BOTH yes (treat an upper bound of exactly 18 as including adults). Use "{UNSPECIFIED}" ONLY when the abstract gives neither ages nor any age-indicating population descriptor (e.g. only "participants" or "individuals" with no further cue).

- study_type: one of {ALLOWED['study_type']}.
  empirical_with_results = a primary study reporting quantitative or mixed-methods results.
  qualitative_only_study = a primary study using ONLY qualitative methods (e.g. interviews, thematic analysis) with no quantitative results — this takes precedence over empirical_with_results when no quantitative result is reported.
  review = a secondary synthesis (systematic/scoping/narrative review or meta-analysis).
  protocol = a planned study not yet conducted. proposal = proposes a method/intervention/framework without a completed study. case_study = single- or very-small-N case report. commentary = editorial/opinion/perspective with no original data.

- intervention_type: one of {ALLOWED['intervention_type']}.
  STEP 1 — does the study DELIVER or EVALUATE an intervention (something actively done to participants to change an outcome)? If NO, distinguish two cases:
    - "data_collection_only": a DIGITAL tool (smartphone/tablet app, web platform, wearable, or software) is used, but ONLY to collect data, assess, measure, detect, monitor, screen, or capture experience (e.g. an Ecological Momentary Assessment app, a smartphone reaction-time test, a symptom-tracking app used purely for measurement) — NOT to treat or change an outcome. The technology exists but is a measurement instrument, not the intervention.
    - "no_intervention": no digital tool is delivered as part of the study at all — e.g. surveys, interview/focus-group studies, prevalence/epidemiology studies, paper questionnaire/scale validation, observational or group-comparison studies with no app/software involved.
  Classify a specific software type (mobile_app, web_app, etc.) ONLY when that technology is delivered AS the intervention (to change an outcome), not when it merely measures.
  REVIEWS: a systematic review or meta-analysis OF interventions counts as evaluating an intervention — classify the TYPE of intervention reviewed (most prominent), NOT "no_intervention". Only use "no_intervention" for a review whose topic is not an intervention (e.g. a review of prevalence or aetiology).
  REVIEWS: a systematic review or meta-analysis OF interventions counts as evaluating an intervention — classify the TYPE of intervention reviewed (most prominent), NOT "no_intervention". Only use "no_intervention" for a review whose topic is not an intervention (e.g. a review of prevalence or aetiology).
  STEP 2 — if an intervention IS delivered/evaluated, FIRST check for parent/caregiver mediation: if the intervention is training, education, or coaching delivered to PARENTS or CAREGIVERS so they can support/manage a child (e.g. Behavioural Parent Training, parent management training, caregiver-mediated programmes) -> use "parent_training", regardless of how it is delivered (app, web, in person). The index participant being trained is the parent, not the person with ADHD/autism, so it is off-target for this review.
  Otherwise choose by this precedence (first that applies): vr_ar (immersive virtual reality via a headset or CAVE, or an augmented-reality system) > video_modeling (the intervention is watching video demonstrations/models of target behaviours or skills — including video self-modeling — to observe and imitate; passive video content even if shown on a device) > video_game (the active intervention is a video game, "serious game", or gamified training program — interactive play with goals/feedback to train attention, EF, or emotion regulation — regardless of whether it runs on a phone, web, or console) > mobile_app (smartphone/tablet app) > web_app (browser/online program or website) > wearable (body-worn device) > telecoaching (remote human coaching) > telecounselling (remote therapy/counselling) > software_tool (other standalone/desktop software with no app or web delivery) > non_software_based (a real intervention with NO digital component — e.g. face-to-face therapy, medication, in-person coaching, a printed workbook, an exercise programme).
  For a review spanning several intervention types, pick the single most prominent; if none dominates, use "{UNSPECIFIED}". Use "{UNSPECIFIED}" only when an intervention clearly exists but its nature cannot be determined from the abstract.

- intervention_details: short sentence describing the intervention, or "no intervention" if there is none (free text, max ~25 words).

- neurotypes: one of {ALLOWED['neurotypes']}. audhd = both ADHD and autistic. Decide in two steps:
  (1) Is the studied SAMPLE made up of people with ADHD, autism, or both? If yes, use adhd / autistic / audhd accordingly. (If ADHD/autism appears only as background, topic, or context and the participants are a general or different population, this is NOT a yes.) In particular, studies OF attitudes toward, knowledge of, perceptions of, or services for ADHD/autism whose PARTICIPANTS are clinicians, teachers, parents, or the general public have a non-ADHD/autistic sample -> neither_adhd_nor_autistic.
  CASE-CONTROL / SUBGROUP: if ANY studied group is selected/diagnosed with ADHD/autism (e.g. an ADHD or autistic case group compared with controls, or a diagnosed subgroup within the sample), label by that condition — a control or comparison group does NOT make it "neither". Only the condition group matters.
  (2) If no group has ADHD/autism, use "neither_adhd_nor_autistic" — the DEFAULT for any population not selected for ADHD/autism (another condition, or a general/typical sample such as students, workers, or the public). Non-human (animal-model) studies are also "neither_adhd_nor_autistic".
  Use "{UNSPECIFIED}" ONLY in the rare case where the abstract gives no indication at all of what population was studied. Judge by the population actually studied, not conditions mentioned only in passing.

- control_type: one of {ALLOWED['control_type']}. rct = randomised controlled trial; non_randomised_control = has a comparison group but not randomised; no_control_group = single-arm / no comparison; "{UNSPECIFIED}" if not determinable.

- study_duration_days: integer number of days, or null if not stated. Convert weeks/months if needed.

- outcomes_measured: comma-separated outcome measures or scales used (e.g. "ASRS, AAQoL"), or empty string.

WORKED EXAMPLES (illustrating the tricky boundaries):
1) "We validated a smartphone reaction-time test in 150 university students (mean age 21)." -> a digital tool used only to MEASURE, not treat -> intervention_type=data_collection_only, neurotypes=neither_adhd_nor_autistic, has_adults=yes, has_under_18=no, study_type=empirical_with_results.
5) "29 autistic adults used an Ecological Momentary Assessment smartphone app for one week to label their emotions; we analysed emotion-control patterns." -> the app only captures self-report data (no treatment delivered) -> intervention_type=data_collection_only, neurotypes=autistic, has_adults=yes, has_under_18=no, study_type=empirical_with_results.
2) "Semi-structured interviews with 15 autistic adolescents (aged 14-17) explored their use of school apps." -> qualitative interview study; sample is autistic and entirely under 18; no intervention delivered -> study_type=qualitative_only_study, neurotypes=autistic, intervention_type=no_intervention, has_adults=no, has_under_18=yes.
3) "An 8-week RCT of a CBT mobile app versus waitlist in adults aged 19-58 with ADHD." -> app delivered as treatment; ADHD sample; all adults -> intervention_type=mobile_app, neurotypes=adhd, control_type=rct, has_adults=yes, has_under_18=no, study_type=empirical_with_results.
4) "A survey of 300 schoolteachers' attitudes toward ADHD in the classroom." -> sample is teachers (adults), not people with ADHD; ADHD is only the topic; no intervention -> neurotypes=neither_adhd_nor_autistic, intervention_type=no_intervention, has_adults=yes, has_under_18=no, study_type=empirical_with_results.
6) "An RCT of clinician-delivered Behavioural Parent Training for parents of children with ADHD." -> the intervention trains the PARENTS to manage their child; the index participant is the parent, not the child with ADHD -> intervention_type=parent_training, has_adults=yes (parents), has_under_18=yes (children), study_type=empirical_with_results.

Return ONLY a JSON object with exactly these keys: reasoning, has_adults, has_under_18, study_type, intervention_type, intervention_details, neurotypes, control_type, study_duration_days, outcomes_measured. Use the listed enum values verbatim. When torn between a specific value and "{UNSPECIFIED}", follow the per-field rules above instead of defaulting to "{UNSPECIFIED}"."""


# --- Phase 1: coarse screen (age group + is_empirical) -------------------
# A cheap first pass run on EVERY paper. Papers that fail the coarse criteria
# (not empirical, or wrong age group for the review) are short-circuited and
# never sent to the expensive detailed classifier. is_empirical follows the
# "primary studies only" definition.

SCREEN_ALLOWED = {
    "has_adults": ["yes", "no", UNSPECIFIED],
    "has_under_18": ["yes", "no", UNSPECIFIED],
    "is_empirical": ["yes", "no", UNSPECIFIED],
}

# Order matters: age first, then is_empirical (matches the reasoning order).
SCREEN_FIELDS = ["has_adults", "has_under_18", "is_empirical"]

# Detailed fields are only classified for papers that pass the screen.
DETAIL_FIELDS = [
    "study_type",
    "intervention_type",
    "intervention_details",
    "neurotypes",
    "control_type",
    "study_duration_days",
    "outcomes_measured",
]

# Phase-2 consensus is judged on these (free-text/numeric detail fields excluded).
# has_adults/has_under_18 are judged in Phase 1 (the screen), not here.
DETAIL_CONSENSUS_FIELDS = ["study_type", "intervention_type", "neurotypes"]

# Map the adjudicated Final_study_type onto a silver-standard is_empirical, so
# the screen can be validated without any new human labelling. "Primary studies
# only": a study that collects and reports its own data.
EMPIRICAL_STUDY_TYPES = {"empirical_with_results", "qualitative_only_study", "case_study"}
NON_EMPIRICAL_STUDY_TYPES = {"review", "commentary", "proposal", "protocol"}


def study_type_to_is_empirical(study_type: str) -> str:
    s = str(study_type).strip().lower()
    if s in EMPIRICAL_STUDY_TYPES:
        return "yes"
    if s in NON_EMPIRICAL_STUDY_TYPES:
        return "no"
    return UNSPECIFIED


SCREEN_PROMPT = f"""You screen a research abstract for a systematic review using two coarse criteria only: the participants' age group, and whether the paper is empirical. Return a JSON object using the listed enum values verbatim. Apply the rules precisely so two independent raters reach the same label.

REASONING FIRST: the FIRST key in your JSON must be "reasoning" — 1-2 sentences that, citing the abstract, state (a) the study population and its ages (any participants under 18? any aged 18+?), and (b) whether this is a PRIMARY study reporting its own collected data, or a non-empirical work (review, commentary, proposal, or protocol). Derive the labels below from this reasoning.

Fields (decide in this order):

- has_adults: one of {SCREEN_ALLOWED['has_adults']}. "yes" if the sample includes any participants aged 18 or older; "no" if entirely under 18; "{UNSPECIFIED}" if no age information at all.
- has_under_18: one of {SCREEN_ALLOWED['has_under_18']}. "yes" if the sample includes any participant under 18; "no" if entirely 18 or older; "{UNSPECIFIED}" if no age information at all.
  Treat the described population ITSELF as an age cue, not only explicit numbers. Inherently-adult samples — adults, patients of an adult/general clinic, university/college students, employees/workers, parents, carers, teachers, clinicians, military personnel, or a general adult public — are has_adults=yes, has_under_18=no. Inherently-minor samples — infants, preschoolers, schoolchildren, adolescents, paediatric patients — are has_under_18=yes, has_adults=no. An explicit range or groups spanning the 18 boundary (e.g. "15-25", "6 to 18", "adolescents and young adults", or "children and their parents") -> BOTH yes (treat an upper bound of exactly 18 as including adults). Use "{UNSPECIFIED}" ONLY when there is neither an age nor any age-indicating population descriptor.

- is_empirical: one of {SCREEN_ALLOWED['is_empirical']}. The test: does this paper report findings from data it collected from its own participants/subjects?
  "yes" (PRIMARY study, reports its own data) = quantitative or mixed-methods results (trials, experiments, cohort/observational studies, surveys/questionnaires WITH results), a qualitative-only study (interviews, focus groups, thematic analysis), or a case study / case report (single- or very-small-N).
  "no" (NOT a primary data study) = a literature/systematic/scoping review or meta-analysis (synthesises others' work); an editorial, commentary, opinion, perspective, viewpoint, or letter; a proposal/design/framework/"we present a system" paper that describes a method or tool WITHOUT evaluating it on participants; or a protocol for a study not yet conducted.
  When torn, ask only: did they collect and report their OWN data? Yes -> "yes". Only synthesise, opine, propose, or plan -> "no". Use "{UNSPECIFIED}" only if the abstract gives no indication of the study design at all.

WORKED EXAMPLES:
1) "An 8-week RCT of a CBT app vs waitlist in 60 adults with ADHD; symptoms fell significantly." -> primary data, adults -> has_adults=yes, has_under_18=no, is_empirical=yes.
2) "We systematically reviewed 32 studies of digital interventions for autistic children." -> a review (no own data); children -> has_adults=no, has_under_18=yes, is_empirical=no.
3) "This paper proposes a wearable design to support task initiation in adults with ADHD." -> a proposal, not evaluated -> has_adults=yes, has_under_18=no, is_empirical=no.
4) "Semi-structured interviews with 15 autistic adolescents about school apps." -> qualitative primary study; under 18 -> has_adults=no, has_under_18=yes, is_empirical=yes.

Return ONLY a JSON object with exactly these keys: reasoning, has_adults, has_under_18, is_empirical."""


def coerce_screen(result: dict) -> dict:
    """Snap screen output to allowed enum values."""
    out = {f: result.get(f) for f in SCREEN_FIELDS}
    for field, allowed in SCREEN_ALLOWED.items():
        v = out.get(field)
        if v is None:
            out[field] = UNSPECIFIED
            continue
        v_norm = str(v).strip().lower().replace(" ", "_").replace("-", "_")
        out[field] = v_norm if v_norm in allowed else UNSPECIFIED
    return out


# NOTE: This file previously defined OPENAI_ADDENDUM and GEMINI_ADDENDUM —
# per-rater bias-correction prompts tuned against the disagreement-failure
# patterns of those specific models. The pipeline now runs on Bedrock-hosted
# models (Nova Lite + Llama 3.1 8B as the default raters, Claude Sonnet 4.5 as
# adjudicator), which exhibit different biases, so those tuned addenda no
# longer apply.
#
# To add model-specific guidance, populate ``prompt_suffix`` on the rater in
# the relevant configs/<slug>.json — it's appended to CLASSIFICATION_PROMPT
# for that rater only. See ``steps/llm.py::invoke_json``.


def coerce_classification(result: dict) -> dict:
    """Snap LLM output to the allowed enum values, with UNSPECIFIED as fallback."""
    out = {f: result.get(f) for f in ALL_FIELDS}
    for field, allowed in ALLOWED.items():
        v = out.get(field)
        if v is None:
            out[field] = UNSPECIFIED
            continue
        v_norm = str(v).strip().lower().replace(" ", "_").replace("-", "_")
        out[field] = v_norm if v_norm in allowed else UNSPECIFIED
    if out.get("intervention_details") is None:
        out["intervention_details"] = ""
    if out.get("outcomes_measured") is None:
        out["outcomes_measured"] = ""
    dur: Any = out.get("study_duration_days")
    if isinstance(dur, str):
        try:
            out["study_duration_days"] = int(dur)
        except (ValueError, TypeError):
            out["study_duration_days"] = None
    return out
