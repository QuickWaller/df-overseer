# Is the role charter reaching the model? (2026-10-08, read-only)

## Answer

**No. In the one real run whose prompt could be read directly, the charter was not
delivered.** The conductor writes each charter to the right place on its own terms,
but openclaw inside the container looks for its bootstrap files in `/app`, not in the
configured workspace, so `SOUL.md` (and `AGENTS.md`, `IDENTITY.md`) read as `[MISSING]`.

| Role | Charter reaches model? | Evidence level |
|---|---|---|
| architect | **No** | Confirmed directly: real run `run-0033` (2026-10-07 23:10 UTC), system prompt read from the retained state dir |
| overseer | No (very likely) | Same mechanism and config shape; the 2026-10-07 cache-miss reproduction on the overseer config showed the same `[MISSING]`. No real overseer prompt is retained |
| quartermaster | No (very likely) | Inferred, same mechanism |
| planner | No (very likely) | Inferred, same mechanism |
| consultant | No (very likely) | Inferred, same mechanism |

Only the latest run's state dir is retained, which is why only one real prompt exists.
The runs database transcript column holds the conversation, not the system prompt, so
it cannot settle this for the other roles (checked runs 0030, 0032, 0034, 0036, 0038:
no `MISSING`, `SOUL` or charter heading text, as expected, since it never holds the
system prompt).

## Evidence trail

1. **Runner side is correct and wired.** `conductor/runner.py` (`write_soul`, around
   line 453) writes `agents/<role>/role.md` as `<workspace_root>/<role>-workspace/SOUL.md`
   before the run and unlinks it after (`cleanup_workspace`, around line 465); the
   docker command bind-mounts that workspace at the same path (around line 500).
   `conductor/service.py:57-66` (`load_charters`) reads every `agents/<role>/role.md`;
   `conductor/cycle.py:581` passes `charter=deps.charters.get(role)`. Confirmed by reading.
2. **Charters ship.** On the agent VM the conductor's `WorkingDirectory` holds
   `agents/{architect,overseer,planner,quartermaster,consultant,conductor,chronicler,marshal}/role.md`
   (listed live, read-only). The `vm106-agents` target is the deploy path. Confirmed.
3. **Pinned configs point at the workspace.** `/opt/openclaw/conductor/pinned-configs/<role>.json`
   has `agents.defaults.systemAgent.agentId = <role>` and
   `agents.entries.<role>.workspace = /opt/openclaw/<role>-workspace` (architect and
   overseer read; the dirs exist for all five roles and are empty between runs, which
   is the cleanup working). Confirmed.
4. **But the model's prompt says otherwise.** Retained state of the last architect
   run: `/var/lib/conductor/thinking/conductor-architect-561c891b2070/agents/architect/agent/openclaw-agent.sqlite`,
   table `trajectory_runtime_events`, seq 2, run id `e8e2cee3-3e8c-4a81-9058-d80be718ddd4`.
   The system prompt contains:
   `## Workspace Files (injected)` ... `# Project Context` ...
   `## /app/AGENTS.md [MISSING] Expected at: /app/AGENTS.md`,
   `## /app/SOUL.md [MISSING] Expected at: /app/SOUL.md`,
   `## /app/IDENTITY.md [MISSING] Expected at: /app/IDENTITY.md`.
   A search of that run's events for charter text (`Kind:`, `Owns`) found none.
   The bootstrap directory is the container working directory `/app`, not the
   configured workspace. Confirmed by reading the primary record.
5. **Same finding in the earlier reproduction:** `evals/live/2026-10-07-cache-miss-cause/README.md`
   ("Caveat that needs a follow-up check"). This answers its open question: real runs
   behave the same.

## Since when

Not established. The 2026-09-15 manual overseer run placed `SOUL.md` in
`/opt/openclaw/config/overseer-workspace` and treated it as loaded; whether it truly
was is unverified (no prompt capture then). The conductor runner has used the
`<root>/<role>-workspace` convention since the charter threading commits; the
`agent exec --state-dir` capture that made this visible only began 2026-10-05. So
the safe statement is: every conductor run whose prompt is unverified may have lacked
it; the one verified run (2026-10-07) did. Possibly the roles have been working from
the tool descriptions, briefings and role names alone, which would explain behaviours
the charters were written to prevent.

## Smallest fix (not applied, not tested)

The prompt names the exact expected paths, so the least invasive change is in
`DockerOpenClawRunner` command building: add a read-only bind mount of the role's
charter onto the expected path, `-v <workspace>/SOUL.md:/app/SOUL.md:ro`, or set the
container working directory to the role workspace (`-w <workspace>`), since the
loader appears to resolve relative to the cwd. Prefer the explicit file mount (does
not depend on how the cwd is resolved). Caveat: `cleanup_workspace` unlinks SOUL.md
after the run, which is fine; the mount source must exist at launch (it does, written
just before). A side effect to expect: the system message grows by the charter size
and the stable prefix changes once, so the first run after the change is a cache miss.

## How to verify live

Repeat the cache-miss capture method (loopback capture server standing in for the
model provider, temporary state dir, real runner command shape) against the changed
command, or simpler, run one supervised `--once` cycle with `CONDUCTOR_THINKING_STATE_DIR`
set (already on), then read `trajectory_runtime_events` seq 2 from the retained state
dir as above. Pass criteria: the `## /app/SOUL.md` heading is followed by the
role's charter text instead of `[MISSING]`, and the system message length grows by
about the charter's size. Check each of the five roles, since only one is verified today.

## Not verified

- Other four roles' real prompts (no retained state; inferred).
- Why openclaw resolves `/app` rather than `entries.<role>.workspace` under
  `systemAgent` (not read from openclaw source; that would settle which of the two
  fixes is right).
- Whether the fix works: nothing was modified or launched (no docker access from the
  read-only session, by design).
- The date it started.

## Result (fix applied and verified live, 2026-10-08)

**Fix.** `DockerOpenClawRunner.build_command` now adds a read-only bind mount of the
per-run charter, `-v <workspace>/SOUL.md:/app/SOUL.md:ro` (`CHARTER_MOUNT` in
`conductor/runner.py`). The file mount was chosen over `-w` or a workspace setting
because the prompt names the exact path it looked in, and it does not depend on how
openclaw resolves its working directory or `agents.entries.<role>.workspace`. The
image could not be listed (the session's docker access is denied, and a mount over a
shipped file was the risk), but the earlier run reported `/app/SOUL.md` as `[MISSING]`,
so nothing of that name is shipped to be shadowed.

**Fail loud.** `run()` now refuses a role whose charter is `None`, empty or
whitespace: no launch, status `charter_missing`, an ERROR log line "refusing to run
without a charter". Previously `charter=None` skipped the charter silently.
Tests: command contains the mount, parametrised refusal (None, "", whitespace).

**Live check (VM 106, no conductor cycle).** `verify_driver.py` (this directory) called
`DockerOpenClawRunner.run` for the Consultant through a transient unit mirroring
`conductor.service`, prompt "Reply with the first heading of your charter and nothing
else." Result: status ok, $0.0047, 9.6 s, answer `# Consultant`. The kept state dir's
`trajectory_runtime_events` seq 2 system prompt shows `## /app/SOUL.md` followed by
the Consultant charter text (`# Consultant`, `**Kind:** advisor...`, `## Owns`...),
not `[MISSING]`. The conductor service stayed inactive and disabled; the driver and
kept state were removed afterwards; vm106-conductor drift-clean at 4521d26.

**Still open.** `/app/AGENTS.md` and `/app/IDENTITY.md` remain `[MISSING]` (the
conductor writes neither; AGENTS.md could carry shared rules if wanted). Only the
Consultant was verified live; the other roles use the identical code path. The first
run of each role after this change is a prompt-cache miss (the stable prefix grew by
the charter).
