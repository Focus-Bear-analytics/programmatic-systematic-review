"""Deterministic, high-precision classification rules.

Each ``*_rule`` returns a label when the abstract gives an unambiguous textual
signal, or ``None`` to defer to the LLM raters. These rules OVERRIDE the LLM
when they fire, so they are deliberately conservative: high precision, low
recall. Anything genuinely requiring judgement (e.g. whether a study has *no*
intervention, or whether ADHD is the sample vs just the topic) is left to the
LLM by returning ``None``.

``apply_rules(title, abstract)`` returns a dict of ``field -> value`` for only
the fields a rule decided.
"""

from __future__ import annotations

import re

from .constants import UNSPECIFIED


def _norm(text: str) -> str:
    return " " + re.sub(r"\s+", " ", str(text or "").lower()) + " "


# --- Age -----------------------------------------------------------------
# Strong, sample-indicating population terms only. Provider/topic-prone words
# ("clinician", "adulthood", etc.) are deliberately excluded — they fire on
# mentions that aren't the study sample, which is what the LLM is better at.
_ADULT_POP = (
    "adults", "older adults", "elderly", "geriatric",
    "university student", "college student", "undergraduate", "postgraduate",
    "graduate student", "employee", "employees", "workers", "workplace",
    "workforce", "veterans", "parents", "caregivers", "mothers", "fathers",
)
_MINOR_POP = (
    "infant", "toddler", "preschool", "kindergarten", "child", "children",
    "schoolchild", "school-age", "school age", "elementary", "primary school",
    "high school", "high-school", "adolescent", "teenager", "paediatric",
    "pediatric", "boys", "girls", "pupils",
)


def age_flags(text: str) -> tuple[str | None, str | None]:
    """Return (has_adults, has_under_18), each 'yes'/'no'/None (None -> defer).

    Conservative by design: assert a flag only from POSITIVE evidence (an
    explicit in-range age, or a strong population term). Assert "no" only from a
    clean one-sided explicit range with no opposing population cue. Everything
    else returns None so the LLM (which can tell the sample from mere mentions)
    decides.
    """
    t = _norm(text)
    has_adult: bool | None = None
    has_minor: bool | None = None

    ranges: list[tuple[int, int]] = []
    for m in re.finditer(
        r"(\d{1,2})\s*(?:-|–|—|to)\s*(\d{1,3})\s*"
        r"(?:years|yrs|year-olds?|years old|years of age)", t
    ):
        lo, hi = int(m.group(1)), int(m.group(2))
        if 0 < lo < hi <= 120:
            ranges.append((lo, hi))
    for m in re.finditer(r"(?:age[ds]?|aged)\D{0,6}(\d{1,2})\s*(?:-|–|—|to)\s*(\d{1,3})", t):
        lo, hi = int(m.group(1)), int(m.group(2))
        if 0 < lo < hi <= 120:
            ranges.append((lo, hi))
    older = [int(x) for x in re.findall(r"(\d{1,2})\s*years?\s*(?:and|or)\s*(?:older|above|over)", t)]
    older += [int(x) for x in re.findall(r"(?:≥|>=|at least|older than|over|aged)\s*(\d{1,2})\s*(?:years|yrs|\+)", t)]
    under = [int(x) for x in re.findall(r"(?:under|younger than|below|less than)\s*(\d{1,2})\s*(?:years|yrs)?", t)]
    means = [float(x) for x in re.findall(r"(?:mean|median|average)\s*age\D{0,10}(\d{1,2}(?:\.\d)?)", t)]

    adult_kw = any(k in t for k in _ADULT_POP)
    minor_kw = any(k in t for k in _MINOR_POP)

    # Positive evidence only.
    # Adults: explicit adult ages OR a strong adult population term (in this
    # adult-focused corpus "adults"/"university students"/etc. are reliably the
    # sample). Minors: explicit child AGES only — minor *words* like "children"
    # fire constantly in background text ("ADHD is a childhood disorder",
    # "parents of children"), so they're left to the LLM.
    if any(hi >= 18 for _, hi in ranges) or any(x >= 18 for x in older) or any(x >= 18 for x in means):
        has_adult = True
    if adult_kw:
        has_adult = True
    if any(lo < 18 for lo, _ in ranges) or any(x <= 18 for x in under) or any(x < 18 for x in means):
        has_minor = True

    # Assert "no" only from a clean one-sided explicit range with no opposing cue.
    if ranges and all(lo >= 18 for lo, _ in ranges) and not minor_kw and not under:
        has_minor = False
    if ranges and all(hi < 18 for _, hi in ranges) and not adult_kw:
        has_adult = False

    def fmt(v: bool | None) -> str | None:
        return None if v is None else ("yes" if v else "no")

    return fmt(has_adult), fmt(has_minor)


# --- Study type ----------------------------------------------------------
def study_type_rule(text: str) -> str | None:
    t = _norm(text)
    # Protocols first (an RCT protocol is a protocol, not an empirical result).
    if re.search(r"\b(study protocol|trial protocol|protocol for (?:a|an|the)|protocol of (?:a|an|the))\b", t):
        return "protocol"
    if re.search(r"\b(systematic review|scoping review|meta-?analysis|umbrella review|literature review|narrative review|bibliometric)\b", t):
        return "review"
    if re.search(r"\b(editorial|commentary|opinion piece|perspective article|viewpoint)\b", t):
        return "commentary"
    if re.search(r"\bcase report\b", t):
        return "case_study"
    return None


# --- Neurotypes ----------------------------------------------------------
_ADHD = re.compile(r"\b(adhd|attention[- ]deficit|hyperactivit)", re.I)
_AUT = re.compile(r"(autis|\basd\b|asperger|neurodiverg|neurodivers)", re.I)


def neurotypes_rule(text: str) -> str | None:
    """Only the safe negative case: no ADHD/autism mention at all -> neither."""
    t = _norm(text)
    if not _ADHD.search(t) and not _AUT.search(t):
        return "neither_adhd_nor_autistic"
    return None  # mention present -> LLM decides sample vs topic


# --- Dispatcher ----------------------------------------------------------
def apply_rules(title: str, abstract: str) -> dict[str, str]:
    """Return {field: value} for only the fields a deterministic rule decided."""
    text = f"{title or ''}. {abstract or ''}"
    out: dict[str, str] = {}

    has_adults, has_under_18 = age_flags(text)
    if has_adults is not None:
        out["has_adults"] = has_adults
    if has_under_18 is not None:
        out["has_under_18"] = has_under_18

    # study_type_rule is intentionally NOT applied as an override: at ~82%
    # precision the LLM (≈95%) is the better rater for it.

    nt = neurotypes_rule(text)
    if nt is not None:
        out["neurotypes"] = nt

    return out
