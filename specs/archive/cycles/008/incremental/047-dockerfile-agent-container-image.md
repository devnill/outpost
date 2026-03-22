# Review: WI-047 — Dockerfile for outpost agent container image

**Verdict: Pass**

The rework correctly resolves the prior critical finding. The image builds successfully and all acceptance criteria are met.

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

## Rework Verification

### C1 fix: `usermod`/`groupmod` rename

The prior finding required replacing `useradd -u 1000` with a rename of the base image's pre-existing `node` user. The fix applied is:

```dockerfile
RUN usermod -l agent -d /home/agent -m node \
  && groupmod -n agent node
```

Verified against the live base image (`node:20-bookworm-slim`):

- `/home/node` exists in the base image, so `-m` (move home contents) does not fail.
- After the rename, `id agent` returns `uid=1000(agent) gid=1000(agent) groups=1000(agent)`.
- The rename is correct and complete.

### M1 fix: removed `mkdir -p /workspace` and `chown`

`WORKDIR /workspace` appears after `USER agent`, so Docker creates `/workspace` owned by `agent:agent` at build time. The `ls -la /` output from a running container confirms `workspace` is owned by `agent agent`. The `agent` user can write to `/workspace` without the removed `chown` step.

The rework note that bind mounts replace the directory at runtime is also correct — host bind mounts supersede the baked-in directory at container start, so the build-time ownership is irrelevant to runtime behavior. No regression was introduced by removing the `chown`.

### Full build and runtime test

`docker build -t outpost-agent:latest mcp/remote-worker/` exits 0 in 5 layers. Runtime checks:

- `id` inside container: `uid=1000(agent) gid=1000(agent) groups=1000(agent)`
- `pwd` inside container: `/workspace`
- Write to `/workspace`: succeeds
