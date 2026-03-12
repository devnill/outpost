# Questions: Remote Dispatch

## Q-1: Caller recovery pattern when a worker restarts and clears the queue
- **Question**: The job queue is in-memory (C16). When a worker restarts, all queued and running jobs are lost. What is the expected caller-side recovery pattern? Should spawn_remote_session callers detect this and re-submit, or is this entirely caller-managed?
- **Source**: steering/constraints.md (C16)
- **Impact**: Without a documented recovery pattern, callers may silently lose work when a worker restarts during a long execution run.
- **Status**: open
- **Reexamination trigger**: A user reports lost jobs after a worker restart during brrr execution.

## Q-2: Worker selection strategy when multiple workers are configured
- **Question**: When `spawn_remote_session` is called without specifying `worker_url`, the job goes to "the first configured worker." Is there any load-balancing or affinity logic, or is it always index-0?
- **Source**: plan/architecture.md §3 (spawn_remote_session definition)
- **Impact**: Uneven load distribution across a worker pool; all unrouted jobs pile onto one worker while others are idle.
- **Status**: open
- **Reexamination trigger**: A user configures multiple workers and reports uneven utilization.
