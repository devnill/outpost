# Questions: Session Lifecycle

## Q-1: Output truncation — head vs tail preference
- **Question**: When truncating session output to `max_output_bytes`, does the implementation preserve the beginning or the end of the output? GP-10 states "preserves the most relevant content" but does not specify which end.
- **Source**: steering/guiding-principles.md (GP-10), plan/architecture.md §2
- **Impact**: Callers relying on truncated output for debugging get different information depending on which end is preserved. Documentation should match implementation behavior.
- **Status**: open
- **Reexamination trigger**: A caller reports that truncated output is missing the actionable part of a session's work.

## Q-2: Security posture of exec_instructions propagation
- **Question**: The `exec_instructions` parameter propagates to all descendant sessions via environment variable. If outpost is used with untrusted prompts, this creates a potential for prompt injection via crafted exec_instructions. Is this risk documented and accepted?
- **Source**: specs/journal.md — WI-024, steering/constraints.md (C13 OUTPOST_SAFE_ROOT)
- **Impact**: Untrusted callers with API key access could inject instructions into all descendant sessions.
- **Status**: open
- **Reexamination trigger**: Outpost is deployed in a context where the calling session is not fully trusted.
