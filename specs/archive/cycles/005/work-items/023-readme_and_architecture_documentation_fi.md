# WI-023: README and Architecture Documentation Fixes

## complexity
easy

## scope
['mcp/remote-worker/README.md (modify)', 'mcp/session-spawner/README.md (modify)', 'specs/plan/architecture.md (modify)']

## depends
[]

## blocks
[]

## criteria
['mcp/remote-worker/README.md DELETE endpoint section states both queued and running jobs can be cancelled', 'mcp/remote-worker/README.md 409 condition lists non-cancellable states as completed, failed, and cancelled', "mcp/session-spawner/README.md does not describe role as 'observability label only' — accurately states role resolves allowed_tools, permission_mode, max_turns, and system_prompt for both local and remote sessions", 'mcp/remote-worker/README.md does not state that role constraints are not applied', "specs/plan/architecture.md cancelled state description includes 'or running'", 'specs/plan/architecture.md env var table: OUTPOST_TIMEOUT row is removed or annotated as not implemented', 'specs/plan/architecture.md env var table: IDEATE_WORKER_HOST is listed with purpose and default 0.0.0.0']

