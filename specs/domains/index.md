# Domain Registry

current_cycle: 1

## Domains

### session-lifecycle
Local subprocess session management — spawning, resource limits (concurrency, timeout, output size, depth), role-based capability constraints, and filesystem-based state tracking.
Files: domains/session-lifecycle/policies.md, decisions.md, questions.md

### remote-dispatch
Remote worker daemon and HTTP REST API — job submission, job lifecycle states, worker pool management, API key authentication, working directory validation, and git diff capture.
Files: domains/remote-dispatch/policies.md, decisions.md, questions.md

### observability
Session event logging, JSONL audit trail, token budget tracking, status table output, and the manager agent for structured worker status reporting.
Files: domains/observability/policies.md, decisions.md, questions.md

## Cross-Cutting Concerns

- **Configuration via environment variables only**: All three domains share this constraint (C19). No config files, no command-line flags. Applies equally to session-spawner and remote-worker.
- **Minimal dependencies**: GP-12 applies across all components. FastAPI/aiohttp for remote work, mcp for protocol — no heavy frameworks added by any domain.
- **Outpost is infrastructure, not a participant**: GP boundary that applies across all domains — Outpost orchestrates sessions; it does not execute the work itself (constraints C15).
