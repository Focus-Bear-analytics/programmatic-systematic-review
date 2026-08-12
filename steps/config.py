"""Declarative config: each review is a JSON file in ``configs/<slug>.json``.

The pipeline historically had paths and model names baked in as module-level
constants. They now live in a per-review JSON config (so a second review
— e.g. for under-18 participants — can share all the code with a different
input/output layout and a different LLM lineup).

Usage:
    cfg = load_config("adults")        # or "children", or any other slug
    cfg.combined_csv                   # -> "search-results-from-database/combined.csv"
    cfg.adjudicated_csv                # -> "search-results-from-database/adjudicated.csv"
    cfg.rater("a").model_id            # -> "apac.amazon.nova-lite-v1:0"

The classify and adjudicate steps consume ``cfg.rater(<which>)`` to drive
Bedrock invocation. Path-only steps (combine, dedupe, ...) read attributes like
``cfg.combined_csv`` so nothing else hard-codes file locations.

The module also exposes a thread-local CURRENT_CONFIG so the ``pipeline.py``
entry-point can install the active config once and downstream imports can
reach it without threading the object through every function signature.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIGS_DIR = PROJECT_ROOT / "configs"


# --- Data classes --------------------------------------------------------


@dataclass
class RaterConfig:
    """One LLM rater (a, b, or adjudicator) backed by Bedrock."""

    key: str
    provider: str
    model_id: str
    label: str
    region: str
    prompt_suffix: str = ""
    column_prefix: str = ""  # filled by Config from legacy_column_prefixes
    aws_profile: str = ""  # filled by Config from top-level aws_profile

    @property
    def is_bedrock(self) -> bool:
        return self.provider == "bedrock"


@dataclass
class CarryForward:
    """Pull rows from another review's output as additional inputs."""

    from_config: str
    csv: str
    filter_column: str | None
    filter_value: str | None
    source_label: str


@dataclass
class Config:
    """One systematic-review configuration.

    All path properties are derived from ``data_dir`` + ``review_subdir`` so a
    review can either share the legacy root layout (``review_subdir=""``) or
    live under its own subfolder.
    """

    slug: str
    name: str
    description: str
    data_dir: str
    review_subdir: str
    database_csvs_subdir: str
    raters: dict[str, RaterConfig]
    carry_forward: CarryForward | None = None
    screening_include: dict[str, list[str]] = field(default_factory=dict)
    screening_exclude: dict[str, list[str]] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    # --- Path helpers (the only place file layout is computed) -----------

    @property
    def review_dir(self) -> str:
        """Directory holding this review's output CSVs."""
        if self.review_subdir:
            return os.path.join(self.data_dir, self.review_subdir)
        return self.data_dir

    @property
    def database_csvs_dir(self) -> str:
        return os.path.join(self.data_dir, self.database_csvs_subdir)

    @property
    def combined_csv(self) -> str:
        return os.path.join(self.review_dir, "combined.csv")

    @property
    def deduped_csv(self) -> str:
        return os.path.join(self.review_dir, "deduped.csv")

    @property
    def abstracts_filled_csv(self) -> str:
        return os.path.join(self.review_dir, "abstracts_filled.csv")

    @property
    def screened_csv(self) -> str:
        return os.path.join(self.review_dir, "screened.csv")

    @property
    def enriched_csv(self) -> str:
        return os.path.join(self.review_dir, "enriched.csv")

    @property
    def adjudicated_csv(self) -> str:
        return os.path.join(self.review_dir, "adjudicated.csv")

    @property
    def prisma_counts_json(self) -> str:
        return os.path.join(self.review_dir, "prisma_counts.json")

    # --- Rater helpers ---------------------------------------------------

    def rater(self, which: str) -> RaterConfig:
        if which not in self.raters:
            raise KeyError(f"no rater '{which}' in config {self.slug!r}")
        return self.raters[which]

    @property
    def rater_a(self) -> RaterConfig:
        return self.rater("a")

    @property
    def rater_b(self) -> RaterConfig:
        return self.rater("b")

    @property
    def adjudicator(self) -> RaterConfig:
        return self.rater("adjudicator")


# --- Loader --------------------------------------------------------------


def load_config(slug: str) -> Config:
    """Read configs/<slug>.json and build a Config. Missing fields fall back to safe defaults."""
    path = CONFIGS_DIR / f"{slug}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"no config at {path}. Available: "
            f"{sorted(p.stem for p in CONFIGS_DIR.glob('*.json'))}"
        )
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    paths = data.get("paths", {})
    legacy = data.get("legacy_column_prefixes", {})
    # AWS profile resolution order: explicit AWS_PROFILE env var > config field
    # > the project default of "phd". Per-rater entries can still override.
    default_profile = os.getenv("AWS_PROFILE") or data.get("aws_profile", "phd")

    raters: dict[str, RaterConfig] = {}
    for key, raw in (data.get("raters") or {}).items():
        raters[key] = RaterConfig(
            key=key,
            provider=raw.get("provider", "bedrock"),
            model_id=raw["model_id"],
            label=raw.get("label", raw["model_id"]),
            region=raw.get("region", os.getenv("AWS_REGION", "ap-southeast-2")),
            prompt_suffix=raw.get("prompt_suffix", ""),
            column_prefix=legacy.get(key, key.capitalize()),
            aws_profile=raw.get("aws_profile", default_profile),
        )

    cf_raw = (data.get("inputs") or {}).get("carry_forward")
    cf: CarryForward | None = None
    if cf_raw:
        filt = cf_raw.get("filter") or {}
        cf = CarryForward(
            from_config=cf_raw["from_config"],
            csv=cf_raw.get("csv", "adjudicated.csv"),
            filter_column=filt.get("column"),
            filter_value=filt.get("value"),
            source_label=cf_raw.get("source_label", f"{cf_raw['from_config']}-carryforward"),
        )

    return Config(
        slug=data.get("slug", slug),
        name=data.get("name", slug),
        description=data.get("description", ""),
        data_dir=paths.get("data_dir", "search-results-from-database"),
        review_subdir=paths.get("review_subdir", ""),
        database_csvs_subdir=paths.get("database_csvs_subdir", "database-csvs"),
        raters=raters,
        carry_forward=cf,
        screening_include=(data.get("screening") or {}).get("include_when", {}) or {},
        screening_exclude=(data.get("screening") or {}).get("exclude_when", {}) or {},
        raw=data,
    )


# --- Active-config singleton ----------------------------------------------

_active_lock = threading.Lock()
_active_config: Config | None = None


def set_active(cfg: Config) -> None:
    """Install the active config for downstream modules to read via :func:`active`."""
    global _active_config
    with _active_lock:
        _active_config = cfg


def active() -> Config:
    """Return the currently-installed Config; raises if none has been set."""
    if _active_config is None:
        # Fall back to "adults" so legacy scripts (and tests that import config
        # paths at module-import time) keep working without an explicit call.
        return load_config("adults")
    return _active_config


# --- Misc env-var helpers (API keys for non-LLM services) ---------------


def semantic_scholar_key() -> str | None:
    # DISABLED 2026-06: the institutional S2 API key is dead (returns 403).
    # Keyless S2 returns 200 with ~1 req/s throttling, which the fetcher already
    # enforces, so we deliberately ignore any env var to avoid re-attaching the
    # dead key. Re-enable by restoring the getenv lookup below once a live key exists.
    return None
    # return os.getenv("SEMANTIC_SCHOLAR_API_KEY") or os.getenv("S2_API_KEY")


def unpaywall_email() -> str | None:
    return os.getenv("UNPAYWALL_EMAIL")


# --- Back-compat shims (so existing imports keep working) ---------------
# The whole point of the refactor is to consume cfg.* attributes, but
# older modules and ad-hoc scripts import DATA_DIR, COMBINED_CSV, etc. as
# module-level constants. We expose them by deferring to the active config.

def _resolve(attr: str) -> str:
    return getattr(active(), attr)


class _Lazy:
    """Module-level descriptor that proxies to ``active().attr``.

    Existing code reads ``from steps.config import COMBINED_CSV`` and uses it
    directly — we want that to follow whichever config is currently active,
    not be frozen at import time. ``__getattr__`` on the module gives us a
    per-access proxy without breaking that import shape.
    """


def __getattr__(name: str) -> Any:  # PEP 562 module-level __getattr__
    mapping = {
        "DATA_DIR": "review_dir",
        "DATABASE_CSVS_DIR": "database_csvs_dir",
        "COMBINED_CSV": "combined_csv",
        "DEDUPED_CSV": "deduped_csv",
        "ABSTRACTS_FILLED_CSV": "abstracts_filled_csv",
        "ENRICHED_CSV": "enriched_csv",
        "ADJUDICATED_CSV": "adjudicated_csv",
        "PRISMA_COUNTS_JSON": "prisma_counts_json",
    }
    if name in mapping:
        return _resolve(mapping[name])
    raise AttributeError(name)
