# Fetch log

- Started: 2026-10-14T13:30:28Z
- Tool: gh version 2.102.0 (2026-09-30)
- Command per file: `gh api --paginate --slurp <endpoint>`

| File | Endpoint | Records | Finished (UTC) |
|---|---|---:|---|
| `labels.json` | `repos/google-gemini/gemini-cli/labels?per_page=100` | 86 | 2026-10-14T13:30:29Z |
| `commits.json` | `repos/google-gemini/gemini-cli/commits?per_page=100` | 6491 | 2026-10-14T13:31:26Z |
| `pull_requests.json` | `repos/google-gemini/gemini-cli/pulls?state=all&per_page=100` | 13062 | 2026-10-14T13:35:29Z |
| `issues.json` | `repos/google-gemini/gemini-cli/issues?state=all&per_page=100` | 27375 | 2026-10-14T13:41:06Z |
| `issue_comments.json` | `repos/google-gemini/gemini-cli/issues/comments?since=2025-09-17T00:00:00Z&per_page=100` | 30000 | 2026-10-14T13:45:35Z |
| `review_comments.json` | `repos/google-gemini/gemini-cli/pulls/comments?since=2025-09-17T00:00:00Z&per_page=100` | 25692 | 2026-10-14T13:54:09Z |

- Finished: 2026-10-14T13:54:09Z
| `issue_comments.pass0.json` | `repos/google-gemini/gemini-cli/issues/comments?since=2025-09-17T00:00:00Z&sort=created&direction=asc&per_page=100` | 30000 | 2026-10-14T13:59:45Z |
| `issue_comments.pass1.json` | `repos/google-gemini/gemini-cli/issues/comments?since=2026-01-15T14:28:49Z&sort=created&direction=asc&per_page=100` | 30000 | 2026-10-14T14:04:49Z |
| `issue_comments.pass2.json` | `repos/google-gemini/gemini-cli/issues/comments?since=2026-04-27T16:34:52Z&sort=created&direction=asc&per_page=100` | 20075 | 2026-10-14T14:07:54Z |
| `issue_comments.json` | merged passes, duplicates removed by id | 80003 | 2026-10-14T14:07:59Z |

## Notes

- The first single-pass `issue_comments.json` (30000 records, created up to 2026-01-15) hit the endpoint's 300-page limit and was replaced by the three-pass sliding-window fetch above (`bash scripts/fetch_raw.sh issue_comments`).
- Window counts vs interim report (fetched ~Sep 2026): commits 4107 = 4107; issues 9776 vs 9782; PRs 9167 vs 9197. Differences = items deleted or transferred since the interim fetch.
- Repository snapshot for file citations: `main` @ `9450ade797302e7c89e13423271aabdea74c7abb` (last commit before 2026-09-17T23:59:59Z).

## GraphQL details (fetched 2026-10-15)

| File | Source | Records | Finished (UTC) |
|---|---|---:|---|
| `pr_details.json` | GraphQL `repository.pullRequests` (merger, approvals, closer) via `scripts/fetch_graphql.py` | 13074 | 2026-10-15T18:07:26Z |
| `issue_details.json` | GraphQL `repository.issues` (closer, state reason) via `scripts/fetch_graphql.py` | 14507 | 2026-10-15T18:14:22Z |
| `pr_details.json` | `fetch_graphql.py pulls`; created <= 2026-09-17T23:59:59Z; all review and close/reopen pages, actor types | 12817 | 2026-10-16T10:22:57Z |
| `issue_details.json` | `fetch_graphql.py issues`; created <= 2026-09-17T23:59:59Z; all review and close/reopen pages, actor types | 14392 | 2026-10-16T10:25:03Z |
