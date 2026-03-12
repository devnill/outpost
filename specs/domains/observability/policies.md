# Policies: Observability

## P-1: Every session lifecycle event must be logged
JSONL log entries are written for session start, completion, and timeout. No lifecycle transition is silent. Log entries include session_id, timing, status, and token usage where available.
- **Derived from**: GP-4 (Transparency and Observability)
- **Established**: planning phase
- **Status**: active

## P-2: Status queries return complete information
Status responses include job state, timing (duration_ms), exit code, error message, and output. Nothing is omitted from a completed or failed job's status response.
- **Derived from**: GP-4 (Transparency and Observability), GP-10 (Result Integrity)
- **Established**: planning phase
- **Status**: active

## P-3: Absent token data is null, not omitted
When token usage cannot be extracted from session output, token_usage is explicitly set to null in log entries and status responses. Fields are never silently omitted.
- **Derived from**: GP-10 (Result Integrity)
- **Established**: implementation phase (WI-046 rework)
- **Status**: active
