# WI-026: Documentation Sweep — token_usage, cancel_remote_job, max_jobs

## complexity
easy

## scope
['mcp/session-spawner/README.md (modify)', 'mcp/remote-worker/README.md (modify)', 'specs/plan/architecture.md (modify)']

## depends
[]

## blocks
[]

## criteria
['mcp/session-spawner/README.md no longer says token_usage is omitted when absent; states it is always present with null value when unavailable', 'mcp/session-spawner/README.md tool table includes cancel_remote_job', 'specs/plan/architecture.md component map tool list includes cancel_remote_job', 'mcp/remote-worker/README.md env var table includes IDEATE_WORKER_MAX_JOBS with default 1000', 'specs/plan/architecture.md health endpoint response schema includes max_jobs field']

