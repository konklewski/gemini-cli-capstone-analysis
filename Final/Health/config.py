"""Central configuration for the Project health analysis.

The analysis window matches the interim report (inclusive, UTC).  Raw data is
fetched from the repository's creation onward to distinguish earlier recorded
authorship from newcomer authorship. Earlier comment history is incomplete;
this cannot establish someone's first-ever participation.
"""

OWNER = "google-gemini"
REPO = "gemini-cli"

START_DATE = "2025-09-17T00:00:00Z"
END_DATE = "2026-09-17T23:59:59Z"
