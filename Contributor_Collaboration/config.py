"""Central configuration for the Gemini CLI empirical analysis.

The analysis window is inclusive at both ends.  Timestamps use UTC so that
records close to a boundary are handled consistently on every machine.
"""

OWNER = "google-gemini"
REPO = "gemini-cli"

START_DATE = "2025-09-17T00:00:00Z"
END_DATE = "2026-09-17T23:59:59Z"

