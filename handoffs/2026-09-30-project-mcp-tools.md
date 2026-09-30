# Handoff: let agents use projects (MCP tools over dfqueue's project/step records)

Date: 2026-09-30. **Executor, Sonnet, worktree.**

## Context

`dfqueue` gained `project`/`step`/`observation` records on 2026-09-28
(`handoffs/2026-09-28-dfqueue-project-step-schema.md`, commit `b6afd13`):
schema, store (`store.project_status`, `step_prerequisites_satisfied`,
`rollback_drift`), and XML renderers (`render.project_status_line`). Nothing
exposes them over MCP, so no agent can create or read a project today. The
design is `research/2026-09-28-job-dependency-graph.md`; read §6 (roles and
who writes what) and §7 (what agents see) in full before starting.

## What to build

1. **`queue.project` (write, overseer only).** Creates a project from an
   accepted ruling, following the design's rule that the Overseer's ruling
   instantiates the project. Enforce it through the same `sole_writer`
   machinery `queue.rule`/`queue.executed` use in `dfmcp/roles.py`, not a
   role-name check. Validation is the store's own (one project per ruling,
   ruling must be accepted, step tool ids from the registry, `requires`
   acyclic). Surface store errors the way the other queue tools do.
2. **`queue.project_status` (read).** One line per project, per design §6,
   using `render.project_status_line`. Grant it to overseer and architect.
   Grant it to the conductor too if its allowlist takes queue reads today;
   check `agents/conductor/` and say what you did.
3. **Step execution records.** Check whether `queue.executed` already
   accepts `step_id` and per-action `targets`/`game_refs`/`target_state`
   end to end (the schema supports them). If the tool's input schema
   strips or rejects them, fix that. Coordinates stay filtered as today.
4. **`observation` stays conductor-only.** Do not expose an observation
   write to any model role. If the conductor needs an MCP path to write
   one, say so in your Result; do not build the reconciler (out of scope).
5. **Docs.** Name the `project` record in `docs/AGENT-ARCHITECTURE.md` §9,
   where it is listed as missing today, pointing at the schema and design
   doc. Update the tool descriptions in `dfmcp/tools.py`/`queue_tools.py`,
   the role allowlists under `agents/*/tools.yaml`, and any test that pins
   role tool counts.

## Since this brief was written

- `dfmcp/tools.py` now scopes argument descriptions per command, then per
  script, then bare (`handoffs/2026-09-30-reservation-gaps.md`, merged
  `36d9c67`); `_describe` takes an optional `tool_id`. Use that, do not
  assume the older shape.
- Everything through `36d9c67` is deployed on VM 103; live role counts are
  overseer 85, architect 51, consultant 29, quartermaster 24, conductor 15.
  Report the new counts your grants would give.
- Read the codebase-wide rules list in
  `handoffs/2026-09-30-reservation-gaps.md` and follow it.

## Out of scope

- The conductor reconciler and blueprint template `steps:` blocks (design
  build-order items 3 and 4).
- Any deploy to VM 103 or live mutation.
- Guard predicate implementations beyond what exists.

## Rules

- `git merge --ff-only main` first.
- `dfmcp/tests` in `.venv-dfmcp` (the main checkout's venv; worktrees carry
  none) and ambient `python -m pytest` (lupa on `PYTHONPATH`) stay green;
  report both counts. Add tests for: overseer creates a project from an
  accepted ruling; a non-writer is refused by the roles layer; a second
  project for the same ruling refused; status renders one line per project
  and never a coordinate; `queue.executed` with a `step_id` round-trips.
- Do not write `Working.md`, `decisions/DECISIONS.md` or `memory/`.
- No em dashes in prose. No attribution lines in any commit.
- Commit as you go. Stop and report on any permission refusal.
- Fill in the Result section below, including the new per-role tool counts.

## Result

**1. `queue.project` (write, overseer only).** Added to `dfmcp/queue_tools.py`
as a `NativeTool` with `sole_writer_only=True`, the same two-layer pattern
`queue.rule`/`queue.executed`/`queue.escalate` already use: `dfmcp.roles`
rule 6 refuses to load a roster that grants it to anyone but the sole writer
(new test, see below), and `dfqueue.schema.validate`'s own `role ==
sole_writer()` check for `PROJECT` records (already present from the
2026-09-28 schema stream) catches it again at write time. The handler
(`_project`) does nothing more than stamp `role`/`cycle`/`snapshot` and call
`store.append` -- every real rule (one project per ruling, ruling must be
accepted, step tool ids resolve against the registry, `requires` acyclic)
already lived in `dfqueue/schema.py`/`dfqueue/store.py` from the prior
stream; this tool only makes that reachable over MCP. The JSON schema
declares the full step shape (`id`/`tool`/`args`/`targets`/`requires`/
`trigger`/`prefer_after`/`guards`) but never `implicit`, so a caller cannot
forge an implicit step; `steps` is optional, matching `normalize_project`'s
"omit for a one-step project" contract. Granted in
`agents/overseer/tools.yaml`, replacing the `queue.plan` placeholder that
file carried under `planned:` (wrong id, since the design settled on
`project` as the record kind).

**2. `queue.project_status` (read).** Added the same way, `sole_writer_only`
left `False` (it writes nothing). `dfqueue.store` had `project_status(path,
project_id)` (one project) but nothing to enumerate every project id, so I
added `store.list_project_ids(path)` (oldest first, mirroring the shape
`queue.overview`'s own caller already uses for `pending_proposals`/
`open_asks`). The tool: no `project_id` arg reads every project, one line
each via `render.project_status_line`, joined with newlines
("(no projects)" if there are none); `project_id` set reads just that one
(refused, "no such project", if it does not exist). Granted to
`agents/overseer/tools.yaml` and `agents/architect/tools.yaml` (design §6:
"Gets a read tool for project status to avoid re-proposing held work") and
also to `agents/conductor/tools.yaml`: its allowlist already takes a
role-independent queue read today (`queue.overview`), so this follows the
same "granted ahead of the reconciler that would actually use it every
cycle" pattern `queue.grade`/`queue.overview` themselves were granted under
-- flagged plainly rather than silently, since the design's own §6 table
does not name the conductor as a `queue.project_status` reader (its row is
about the reconciler, out of scope here).

**3. Step execution records.** `dfqueue.schema`/`dfqueue.store` already
accepted `executed`'s `step_id` and each action's `targets`/`game_refs`/
`target_state` end to end (from the 2026-09-28 stream) -- but
`dfmcp/queue_tools.py`'s tool layer did not: `_EXECUTED_FIELDS` was still
`{"ruling_id", "actions", "notes"}`, so `_reject_unknown_arguments` refused
any call naming `step_id` as an "unexpected argument" before it ever reached
`dfqueue`, and `_EXECUTED_SCHEMA`'s action-item schema only declared `tool`/
`outcome`/`detail` (with `additionalProperties: false`), silently
description-level hiding `targets`/`target_state`/`game_refs` from a calling
model even though the code-level enforcement (`_reject_unknown_arguments`,
not the JSON schema) would not itself have stripped an action-level field.
Fixed both: `step_id` added to `_EXECUTED_FIELDS` and `_EXECUTED_SCHEMA`;
`targets`/`target_state`/`game_refs` added to the action item schema with
the same "both or neither" note `dfqueue.schema._validate_action` enforces.
Verified end to end with a real `queue.project` (two steps) followed by a
`queue.executed` call naming `step_id` plus `targets`/`target_state`, then
reading `store.project_status` back and confirming both named targets show
`done` (`test_executed_with_step_id_round_trips_into_the_target_state_fold`).

**4. `observation` stays conductor-only.** No MCP write path was added for
it, per the brief. The reconciler that would call one is out of scope here
and is not built; `dfqueue.schema.OBSERVATION_ROLE` already restricts a
would-be write to the `conductor` role at the schema layer regardless.
Documented explicitly in `dfqueue/schema.py`'s and `dfqueue/README.md`'s own
kind lists (both were stale -- see "Also found and fixed" below) so the gap
reads as a known, named absence rather than an oversight.

**5. Docs.** `docs/AGENT-ARCHITECTURE.md` §9 now names the `project` record
directly under the write-ahead-log paragraph it was always describing in
prose only, pointing at `dfqueue/schema.py`, the design doc, and
`queue.project`/`queue.project_status`. `dfmcp/queue_tools.py`'s own tool
descriptions were written in full for both new tools (see the `_PROJECT_*`/
`_PROJECT_STATUS_*` constants) and `_EXECUTED_DESCRIPTION` was extended to
mention `step_id`. Role allowlists: `agents/overseer/tools.yaml` (write:
`queue.project`; read: `queue.project_status`; also extended the existing
`queue.executed` entry's own note), `agents/architect/tools.yaml` (read:
`queue.project_status`), `agents/conductor/tools.yaml` (read:
`queue.project_status`, with the reasoning above). No test in this repo
pins an exact per-role tool count (checked: no `len(...) == <number>`
assertion anywhere in `dfmcp/tests/`), so there was nothing to update there
beyond the counts reported below, which the CLAUDE.md status line/Working.md
convention re-measures from the roster at each deploy rather than pinning
in a test.

**Also found and fixed, not asked for but directly in scope's own files:**
`dfqueue/schema.py`'s own module docstring still said "Seven record kinds"
and "No `plan` record yet" -- stale since the 2026-09-28 stream added
`project`/`observation` without updating the docstring above them in the
same file. `dfqueue/README.md`'s "What this is" section had the same drift
("Seven record kinds", no `project`/`observation` entries at all). Both
corrected (nine kinds, full `project`/`observation` bullets, the "not built
yet" `plan` paragraph replaced with what actually exists now) rather than
left compounding a third time, matching this repo's own rule that a stale
doc gets flagged and fixed, not left to drift further.

**New per-role tool counts** (read + write, measured from the real roster via
`dfmcp.roles.load_roster` against the full merged registry, the same way
this repo's own status line is measured -- not counted by hand):

| role | before this stream | after |
|---|---|---|
| overseer | 85 | **87** (+2: `queue.project` write, `queue.project_status` read) |
| architect | 51 | **52** (+1: `queue.project_status` read) |
| consultant | 29 | 29 (unchanged) |
| quartermaster | 24 | 24 (unchanged) |
| conductor | 15 | **16** (+1: `queue.project_status` read) |

**Test counts.** `.venv-dfmcp`: `C:/website-projects/df-automation/.venv-dfmcp/
Scripts/python.exe -m pytest -q dfmcp/tests` = **713 passed, 0 skipped** (up
from this stream's own starting baseline of 701: +12, all in
`dfmcp/tests/test_queue_tools.py` -- `TestProject` (4), `TestProjectStatus`
(4), `TestExecutedStepId` (3) -- plus one in `dfmcp/tests/test_roles.py`
(`test_rule6_also_restricts_queue_project_to_the_sole_writer`)). Ambient
`python -m pytest -q` (lupa importable in this environment's own `python`,
already on its default path, no separate `PYTHONPATH` step needed here) =
**2070 passed, 3 skipped** (up from the stated baseline of 2058/3: +12,
the same twelve tests, which the ambient run also collects). The one
known-flaky race test
(`test_queue_tools.py::TestWriteSerialisation::
test_concurrent_raw_appends_without_serialization_can_collide`) did not
flake in either full run.

**Left unverified / real, named gaps, not silently left:**
- Nothing here ran against a real DFHack process or VM 103; no credentials
  in this worktree, and no deploy was in scope. `queue.project`/
  `queue.project_status`/the extended `queue.executed` are offline-built and
  offline-tested only (direct `queue_tools.call()` tests, no ASGI transport,
  same class of residual risk `dfmcp/tests/test_queue_tools.py`'s own
  docstring already names for every native tool here).
- Whether an actual DeepSeek-backed Overseer or Architect can compose a
  sensible multi-step `steps` block, or would even reliably call
  `queue.project` at all once ruling on something multi-step, is untested --
  design §7's own open question 4 ("Whether DeepSeek advisors will write
  sensible step lists"), unchanged by this stream.
- The dynamic-discovery target-set case (design §4.3, a query-shaped target
  set beyond `{from_step, select: "done"}`) was already flagged unbuilt by
  the schema stream and stays unbuilt; `queue.project`'s own JSON schema
  mirrors `dfqueue.schema._validate_target_spec` exactly, so it inherits the
  same limitation, not a new one.
- Conductor's `queue.project_status` grant is ahead of any code that reads
  it (the reconciler is out of scope) -- named plainly above, not hidden in
  the diff.

**Deploy/live mutation:** none, per scope. No VM 103 credentials in this
worktree.
