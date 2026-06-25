"""Track PRISMA-style record counts at each stage of the pipeline.

The PRISMA flow diagram requires reporting how many records were:
  - identified (combined from all databases),
  - screened (after duplicate removal),
  - assessed for eligibility (had an abstract to read),
  - included (consensus reached / passed full classification).

This module keeps a running JSON file at `PRISMA_COUNTS_JSON`, updated by each
step.  The file is preserved across runs so a step that resumes from cache can
still see counts produced by earlier steps.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from .config import active


def _path() -> str:
    return active().prisma_counts_json


def _load() -> dict[str, Any]:
    path = _path()
    if not os.path.exists(path):
        return {"stages": {}}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"stages": {}}


def _save(data: dict[str, Any]) -> None:
    path = _path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def record_stage(stage: str, **counts: int) -> None:
    """Record counts for a named pipeline stage.

    Example:
        record_stage("dedupe", before=1234, after=987, duplicates_removed=247)
    """
    data = _load()
    data["stages"][stage] = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        **counts,
    }
    _save(data)


def summary() -> dict[str, Any]:
    """Return the full PRISMA counts dict (for printing / inspection)."""
    return _load()
