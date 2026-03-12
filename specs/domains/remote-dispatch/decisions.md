# Decisions: Remote Dispatch

## D-1: HTTP/REST transport, not gRPC or WebSocket
- **Decision**: Remote workers expose a simple HTTP/REST API. No other transport is supported.
- **Rationale**: Broad compatibility and deployment simplicity. HTTP is universally supported without additional client libraries.
- **Source**: steering/constraints.md (C5), steering/interview.md
- **Status**: settled

## D-2: In-memory job queue with no persistence across restarts
- **Decision**: Jobs are queued in the worker process's memory. A worker restart clears the queue. Persistent job queues require an external orchestration layer.
- **Rationale**: Deliberate scope boundary — adding queue persistence would require a database or durable message broker, significantly increasing deployment complexity.
- **Source**: steering/constraints.md (C16)
- **Status**: settled

## D-3: Single-user assumption for remote worker instances
- **Decision**: Each remote worker daemon assumes a single trusted user. Multi-tenant isolation is out of scope; separate worker instances with separate API keys serve multiple users.
- **Rationale**: Multi-tenant isolation requires user identity propagation throughout the job model, adding significant complexity that is not needed for the target use case.
- **Source**: steering/constraints.md (C17)
- **Status**: settled

## D-4: API key comparison uses hmac.compare_digest (not equality)
- **Decision**: API key validation uses `hmac.compare_digest` instead of `!=` string comparison.
- **Rationale**: Timing attack — constant-time comparison prevents character-by-character key recovery by a network-adjacent attacker.
- **Source**: archive/incremental/030-remote-worker-daemon.md (C1)
- **Status**: settled

## D-5: poll_remote_job returns auth error immediately on 401/403
- **Decision**: When polling a job across workers, a 401 or 403 response from any worker causes immediate return of an auth error. The fan-out loop does not continue to the next worker.
- **Rationale**: Auth failure means the caller has a misconfiguration, not a routing issue. Continuing the loop would produce a misleading "job not found" error.
- **Source**: archive/incremental/033-remote-dispatch-tools.md (S2)
- **Status**: settled

## D-6: Worker health polling uses concurrent asyncio.gather
- **Decision**: When listing remote workers, health checks for all workers run concurrently via asyncio.gather, not serially.
- **Rationale**: Serial polling creates worst-case latency of N×timeout when any worker is unreachable.
- **Source**: archive/incremental/033-remote-dispatch-tools.md (M3)
- **Status**: settled

## D-7: git_diff captured after job completion when workspace is a git repo
- **Decision**: The remote worker runs `git diff` after a job completes and returns the output to the caller. Non-git workspaces return null for git_diff.
- **Rationale**: Callers can inspect workspace changes without re-reading files. Not enforced as a requirement on the workspace.
- **Assumes**: git is available on the remote host.
- **Source**: plan/architecture.md §4, steering/constraints.md (C18)
- **Status**: settled
