"""String literals reused across the pipeline.

Centralised here so a typo in one step can't drift away from the rest of the
code.  Add new strings here when you find yourself writing the same literal in
more than one place.
"""

# Yes/No-style flags written to CSV columns
YES = "Y"
NO = "N"

# Classification fallback when a field can't be determined
UNSPECIFIED = "unspecified"

# Bookkeeping column added by the dedupe step
DUPLICATE_COL = "is_duplicate"

# Column written by the classify step recording inter-rater agreement
CONSENSUS_REACHED_COL = "Consensus_Reached"

# Phase-1 coarse-screen bookkeeping columns + short-circuit sentinel
SCREEN_PASS_COL = "Screen_Pass"
SCREEN_REASON_COL = "Screen_Reason"
NON_EMPIRICAL = "non_empirical"

# Standardised input column names (after alias normalisation)
COL_SOURCE = "Source"
COL_TITLE = "Title"
COL_ABSTRACT = "Abstract"
COL_AUTHORS = "Authors"
COL_YEAR = "Year"
COL_DOI = "DOI"
COL_URL = "URL"
COL_PMID = "PMID"
COL_JOURNAL = "Journal"
