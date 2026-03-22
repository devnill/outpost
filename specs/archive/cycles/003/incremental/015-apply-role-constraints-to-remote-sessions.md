# Incremental Review: 015-Apply-Role-Constraints-to-Remote-Sessions

**Work Item**: 015 - Apply Role Constraints to Remote Sessions  
**Review Date**: 2026-03-16  
**Reviewer**: Claude Code  
**Files Reviewed**:
- `/Users/dan/code/outpost/mcp/session-spawner/server.py` (lines 682-767)
- `/Users/dan/code/outpost/mcp/session-spawner/test_server.py` (lines 1549-1647)

---

## Verdict: Pass

The implementation satisfies all acceptance criteria. Role constraints are correctly resolved and applied to remote session payloads, with proper error handling for unknown roles. All 65 tests pass, including 3 new tests specifically covering the role constraint functionality.

---

## Critical Findings

None.

---

## Significant Findings

None.

---

## Minor Findings

None.

---

## Unmet Acceptance Criteria

None.

---

## Implementation Verification

### Role Name Resolution (`server.py:686-691`)

Role names are correctly resolved against the `_roles` dictionary before any HTTP calls are made. Unknown role names return a structured error immediately.

```python
if isinstance(role_arg, str):
    if role_arg not in _roles:
        return [TextContent(type="text", text=json.dumps({
            "error": f"Unknown role: '{role_arg}'. Available roles: {list(_roles.keys())}"
        }))]
    resolved_role = _roles[role_arg]
```

### Role Payload Fields (`server.py:755-761`)

Resolved role fields are correctly included in the HTTP payload only when the caller has not explicitly provided them:

- `permission_mode` at line 757: Uses role value unless caller provides override
- `allowed_tools` at lines 760-761: Uses role value only if caller omits the field
- `max_turns` at line 755: Uses role value unless caller provides override

### Inline Role Dict (`server.py:692-693`)

Inline role dictionaries pass through without lookup, satisfying the requirement:

```python
elif isinstance(role_arg, dict):
    resolved_role = role_arg
```

### No Role Behavior

When no role is provided (`role_arg` is `None`), `resolved_role` stays `None` and the payload is built with default values, leaving the payload unchanged as required.

---

## Test Coverage Verification

Three new tests were added in section 24 of the test file:

1. **`test_spawn_remote_session_role_name_resolves_constraints`** (line 1550)
   - Verifies that a known role name propagates `allowed_tools` and `permission_mode`
   - Captures the POST payload and asserts correct field values
   - Also verifies the `role` field is included for observability

2. **`test_spawn_remote_session_unknown_role_returns_error`** (line 1590)
   - Verifies unknown role names return structured errors
   - Asserts no HTTP calls (neither POST nor GET) are made before the error is returned

3. **`test_spawn_remote_session_inline_role_dict_passes_through`** (line 1611)
   - Verifies inline role dictionaries are used directly without lookup
   - Asserts the dict's `allowed_tools` and `permission_mode` are propagated
   - Verifies the role name in payload uses the dict's `name` field

All existing `spawn_remote_session` tests continue to pass (65/65).

---

## Test Results

```
pytest mcp/session-spawner/test_server.py -v
============================= test session starts ==============================
platform darwin -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0
...
collected 65 items

mcp/session-spawner/test_server.py::test_spawn_remote_session_role_name_resolves_constraints PASSED [ 96%]
mcp/session-spawner/test_server.py::test_spawn_remote_session_unknown_role_returns_error PASSED [ 98%]
mcp/session-spawner/test_server.py::test_spawn_remote_session_inline_role_dict_passes_through PASSED [100%]

============================== 65 passed in 0.73s ==============================
```

---

## Compliance with GP-8: Role-Based Sessions

The implementation follows the guiding principle by:
- Resolving role names to their constraint definitions before dispatch
- Applying role constraints (`allowed_tools`, `permission_mode`, `max_turns`) to the remote session payload
- Supporting both named role references and inline role definitions
- Returning clear errors for unknown roles before making any network requests
- Preserving the role label in the payload for observability purposes
