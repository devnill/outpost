# Work Item 032: Role System

## Objective

Define a JSON role configuration format and add role-aware spawning to `spawn_session`. Built-in roles ship with the package; users can override or extend via `IDEATE_ROLES_FILE`.

## Acceptance Criteria

1. Role definition JSON schema: `{name: string, description: string, system_prompt?: string, allowed_tools?: string[], model?: string, max_turns?: integer, permission_mode?: string}`.
2. Built-in roles file at `mcp/roles/default-roles.json` defines three roles: `worker` (can edit files, full tools), `reviewer` (read-only tools: Read, Grep, Glob), `manager` (Read, Grep, Glob, Bash, plus coordination system prompt).
3. `spawn_session` accepts a new optional `role` string parameter.
4. When `role` is provided, the server resolves it from loaded roles:
   - `system_prompt` (if set) is prepended to the prompt as `[ROLE: {name}]\n{system_prompt}\n\n{original_prompt}`
   - `allowed_tools` (if set) replaces the call's `allowed_tools` parameter unless caller also provides explicit `allowed_tools` (caller wins)
   - `model` (if set) is passed as `--model {model}` to the claude CLI
   - `max_turns` (if set) overrides the call's `max_turns` unless caller provides explicit value (caller wins)
   - `permission_mode` (if set) overrides unless caller provides explicit value
5. If `role` not found in loaded roles, `spawn_session` returns structured error with `exit_code: 1` and descriptive message — no subprocess spawned.
6. Roles loaded at `main()` startup from: `IDEATE_ROLES_FILE` env var if set, otherwise `~/.ideate/roles.json` if exists, otherwise built-in defaults only.
7. Loaded roles merged with built-ins: user file wins on name collision.
8. `list_tools()` response for `spawn_session` documents the new `role` parameter.

## File Scope

- create: `mcp/roles/default-roles.json`
- modify: `mcp/session-spawner/server.py` — add role loading in `main()`, add `role` parameter to `spawn_session`, add role resolution logic in `call_tool()`

## Dependencies

None (parallel with WI 030, 035, 036).

## Implementation Notes

- Built-in `worker` role: no system_prompt override, allowed_tools not set (uses caller's), no model override. Effectively a no-op role that documents intent.
- Built-in `reviewer` role: `allowed_tools: ["Read", "Grep", "Glob"]`, system_prompt: "You are a code reviewer. Your task is to read and analyze — do not modify files."
- Built-in `manager` role: `allowed_tools: ["Read", "Grep", "Glob", "Bash"]`, system_prompt: "You are a team manager coordinating parallel workers. Monitor progress, identify blockers, and report status. Do not implement tasks yourself."
- Role loading: `json.load(open(path))` — list of role objects. Build a dict keyed by `name`.
- `--model` flag: verify this is a valid claude CLI flag. If not supported, omit model override and log a warning.
- Prompt size validation uses original prompt, before role system_prompt injection (consistent with exec_instructions behavior).

## Complexity

Medium
