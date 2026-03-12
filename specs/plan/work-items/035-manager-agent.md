# Work Item 035: Manager Agent

## Objective

Create an agent definition for the team manager role. The manager coordinates parallel workers, monitors job health, detects stalls, and produces structured status reports. It operates as part of an agent team alongside worker agents.

## Acceptance Criteria

1. Agent definition at `agents/manager.md` with valid YAML frontmatter.
2. Frontmatter fields: `name: manager`, `model: claude-sonnet-4-6`, `background: false`, `maxTurns: 30`.
3. Tools list: `[Read, Grep, Glob, Bash, Agent]`. Bash enables health check commands and git inspection. Agent enables spawning sub-agents if needed.
4. Agent prompt covers all of the following responsibilities:
   a. Checking worker status via `list_remote_workers` MCP tool invocation (via Bash: `claude --print ...` or direct tool use)
   b. Reviewing session registry and JSONL log to detect stalled or failed jobs
   c. Identifying jobs that have not progressed within an expected window
   d. Writing a structured status report to `{artifact_dir}/status/manager-report-{timestamp}.md` with sections: Active Workers, Job Summary, Stalled Jobs, Blockers, Recommendations
   e. Escalating unresolvable blockers via Andon cord (appending to `{artifact_dir}/andon-queue.md`)
   f. Coordinating handoff of completed remote work (noting git diffs that need to be applied)
5. Agent prompt includes: input contract (artifact_dir, polling interval hint, list of worker names), output contract (status report path written, andon entries appended if any).
6. Agent prompt specifies it does NOT implement tasks, modify project code, or make architectural decisions.

## File Scope

- create: `agents/manager.md`

## Dependencies

None (parallel with 030, 032, 036).

## Implementation Notes

- Follow the same agent definition format as existing agents (see `agents/architect.md` for reference YAML frontmatter structure).
- The manager's "predefined inspection tools" are Bash commands: `git log --oneline -10`, `git status`, `git diff HEAD`, health check via `curl -s -H "X-API-Key: $KEY" $WORKER_URL/health`. Document these patterns in the agent prompt.
- Status report format should be machine-readable enough that a subsequent agent can parse it (use consistent section headings).
- The manager does not need to understand the content of tasks — it only needs to know whether they are progressing.

## Complexity

Medium
