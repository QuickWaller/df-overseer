# Handoff: no execution without a project (server-enforced)

Date: 2026-10-05. **Executor, Sonnet, worktree. Offline build; read-only on
hosts; no deploys.**

## Why

The user saw on the Board that no ongoing proposal has a job graph. The live
queue (VM 103, read-only, 2026-10-05) has **zero project records** ever:
kinds are only proposal, ruling, executed, ask, answer, and `step_targets` is
empty. In the 2026-10-05 05:40 cycle the Overseer accepted proposal-0013 and
proposal-0014 and went straight to execution, calling `queue.project_status`
twice but never `queue.project`, although its deployed charter
(`agents/overseer/role.md`, Execution bullet) says every accepted proposal gets
a project before anything is executed. A charter rule is not a boundary; the
server is (`docs/AGENT-ARCHITECTURE.md` principle 8).

## What to build

- `queue.executed` (`dfmcp/queue_tools.py` `_executed`, and/or the store write
  in `dfqueue/store.py`, whichever is the validation point for other
  queue-write rules) **refuses** an executed record for an accepted proposal
  that has no project (from `queue.project` with `from_ruling` for that
  ruling/proposal). The refusal message is written for the model: it says to
  call `queue.project` with `from_ruling` first, one step per action, then
  call `queue.executed` naming the `step_id`. Decide whether `step_id` should
  become required when a project exists, and say why.
- Decide what happens to the two accepted-but-projectless proposals already
  live (0013, 0014, and older accepted ones): the rule must not make an
  existing accepted proposal un-executable forever. Preferred: the Overseer can
  still create a project for an older ruling with `from_ruling`; check that
  path works for a ruling written before the project existed. No data
  migration on the live DB.
- Optionally (say in the plan): should acting tools (`workjob.queue`,
  `blueprint.apply`, `orders.create` and the like) also refuse without a
  project? Probably no, since the server cannot reliably link a raw game action
  to a proposal; enforcement at `queue.executed` plus the record is enough.
  Do not build it without a reason.
- Shorten and sharpen the charter's Execution bullet so the order is a short
  numbered sequence (accept, `queue.project`, act, `queue.executed` with
  `step_id`), and mention the server now refuses otherwise. Keep it short.

## Tasks, in order (commit after each)

1. Plan in this file's Result section.
2. Build the rule plus the charter change.
3. Tests: refusal without project; success with project; older ruling can get
   a project and then execute; refusal text names `queue.project`; existing
   queue tests updated where they executed without a project (fix the
   fixtures, do not weaken the rule).
4. Result section: what was built, tests, deploy targets (expect
   `vm103-dfmcp` and `vm106-agents`), and anything the Board needs.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early and after
  every milestone.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md`.
- Touched surfaces: `dfmcp/queue_tools.py` (not `gotchas_store.py`),
  `dfqueue/store.py` and `dfqueue/schema.py` if the rule lives there,
  `agents/overseer/role.md` (Execution bullet only), `agents/overseer/tools.yaml`
  (descriptions of `queue.executed`/`queue.project` only), tests, this handoff.
  Not `conductor/`, `web/`, `dfqueue/feed.py`.
- No armok powers. Public repo: no hostnames, IPs or tokens. No em dashes. No
  attribution lines in commits.
- Full ambient `python -m pytest` and `dfmcp/tests` (in `.venv-dfmcp`) green.

## Result

### Plan (executor, 2026-10-05)

- Rule lives in `dfqueue/store.py` `append`, the existing EXECUTED validation block (where `step_id` and project checks already live), so every writer gets it, not only the MCP handler. `queue.executed` surfaces it as a normal refusal.
- Accepted ruling with no project: refuse, message tells the model to call `queue.project` with `from_ruling` first, then `queue.executed` with `step_id`.
- `step_id` becomes required once a project exists (otherwise no step_targets row advances and the job graph never moves), except for a legacy implicit-step project (empty `steps`), which has no step id to name.
- Older accepted rulings (0013, 0014 and older): `queue.project from_ruling` already works for any accepted ruling with no project, regardless of age; add a test that writes the ruling, a long gap, then the project, then executes. No migration.
- Acting tools (`workjob.queue`, `blueprint.apply`, `orders.create`) are NOT gated: the server cannot link a raw game action to a proposal; enforcement at `queue.executed` plus the record is enough.
- Charter Execution bullet becomes a short numbered order; tools.yaml descriptions for the two tools get one line.
- Fix fixtures that executed without a project (do not weaken the rule).

### Built

- `dfqueue/store.py` `append` (EXECUTED block): accepted ruling with no project is refused (text names `queue.project`, `from_ruling=<id>`, `step_id`); with a project, `step_id` is required unless the project's steps are all implicit (legacy one-step). Applies to every writer, `queue.executed` surfaces it as a refusal.
- Older accepted rulings (0013, 0014, older): `queue.project from_ruling` already accepted any accepted ruling with no project; new tests prove ruling, long gap, refused execution, project, then execution works. No migration.
- Acting tools not gated (server cannot link a raw action to a proposal).
- `agents/overseer/role.md` Execution bullet is now a numbered 4-step order; `dfmcp/queue_tools.py` tool descriptions for `queue.executed`/`queue.project` and `agents/overseer/tools.yaml` note updated.
- Fixtures that executed without a project now create an implicit-step project first.

### Tests

Ambient `python -m pytest`: 2749 passed, 3 skipped. `dfmcp/tests` in `.venv-dfmcp`: 799 passed.

### Deploy targets

`vm103-dfmcp` (store.py and queue_tools.py live on the MCP server side) and `vm106-agents` (role.md charter; also redeploy dfqueue where the conductor imports it).

### Board

Nothing new required: projects already render from `project` records. Expect projects to start appearing once the Overseer next accepts, and the first post-deploy refusal will be visible in tool-call logs as a `queue.executed` error naming `queue.project`.
