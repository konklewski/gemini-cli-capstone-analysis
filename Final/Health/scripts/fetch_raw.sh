#!/usr/bin/env bash
# Download raw GitHub exports for the Project health analysis.
#
# Run from Final/Health/: bash scripts/fetch_raw.sh
# Commits, pull requests and issues cover the full repository history (needed
# to tell real newcomers apart from earlier contributors). Comments only cover
# the analysis window: `since` filters on updated_at, so every comment created
# in the window is included.
#
# Optional argument: the name of one export to (re)fetch, e.g.
#   bash scripts/fetch_raw.sh issue_comments
set -euo pipefail
ONLY="${1:-}"

REPO="google-gemini/gemini-cli"
SINCE="2025-09-17T00:00:00Z"
RAW="data/raw"
LOG="$RAW/fetch_log.md"

mkdir -p "$RAW"
[ -z "$ONLY" ] && {
  echo "# Fetch log"
  echo
  echo "- Started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "- Tool: $(gh --version | head -1)"
  echo "- Command per file: \`gh api --paginate --slurp <endpoint>\`"
  echo
  echo "| File | Endpoint | Records | Finished (UTC) |"
  echo "|---|---|---:|---|"
} > "$LOG"

fetch() {
  local name="$1" endpoint="$2" attempt
  for attempt in 1 2 3; do
    echo "[$(date -u +%H:%M:%S)] $name (attempt $attempt): $endpoint"
    if gh api --paginate --slurp "$endpoint" > "$RAW/$name.json.part"; then
      mv "$RAW/$name.json.part" "$RAW/$name.json"
      local count
      count=$(python3 -c 'import json,sys; print(sum(len(p) for p in json.load(open(sys.argv[1]))))' "$RAW/$name.json")
      echo "| \`$name.json\` | \`$endpoint\` | $count | $(date -u +%Y-%m-%dT%H:%M:%SZ) |" >> "$LOG"
      echo "  -> $count records"
      return 0
    fi
    sleep 30
  done
  echo "FAILED: $name" >&2
  return 1
}

# The comment endpoints stop after 300 pages (30,000 records). Re-query from the
# newest created_at seen until a pass returns fewer records, then merge the
# passes and drop duplicates by comment id.
fetch_sliding() {
  local name="$1" base="$2" since="$SINCE" pass=0 count last
  while :; do
    fetch "$name.pass$pass" "$base?since=$since&sort=created&direction=asc&per_page=100"
    read -r count last < <(python3 -c 'import json,sys; r=[x for p in json.load(open(sys.argv[1])) for x in p]; print(len(r), max(x["created_at"] for x in r))' "$RAW/$name.pass$pass.json")
    [ "$count" -lt 30000 ] && break
    since="$last"
    pass=$((pass + 1))
  done
  count=$(python3 - "$RAW/$name.json" "$RAW/$name".pass*.json <<'EOF'
import json, sys
merged = {}
for path in sys.argv[2:]:
    for page in json.load(open(path)):
        for record in page:
            merged[record["id"]] = record
json.dump([sorted(merged.values(), key=lambda r: r["id"])], open(sys.argv[1], "w"))
print(len(merged))
EOF
)
  rm "$RAW/$name".pass*.json
  echo "| \`$name.json\` | merged passes, duplicates removed by id | $count | $(date -u +%Y-%m-%dT%H:%M:%SZ) |" >> "$LOG"
  echo "  -> $count unique records"
}

want() { [ -z "$ONLY" ] || [ "$ONLY" = "$1" ]; }

want labels          && fetch labels        "repos/$REPO/labels?per_page=100"
want commits         && fetch commits       "repos/$REPO/commits?per_page=100"
want pull_requests   && fetch pull_requests "repos/$REPO/pulls?state=all&per_page=100"
want issues          && fetch issues        "repos/$REPO/issues?state=all&per_page=100"
want issue_comments  && fetch_sliding issue_comments  "repos/$REPO/issues/comments"
want review_comments && fetch_sliding review_comments "repos/$REPO/pulls/comments"

if [ -z "$ONLY" ]; then { echo; echo "- Finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)"; } >> "$LOG"; fi
echo "Done. See $LOG"
