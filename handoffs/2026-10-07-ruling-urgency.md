# Handoff: the Overseer sets a project's urgency in its ruling

Date: 2026-10-07. **Executor, Sonnet, worktree. Offline; no deploys.**
First: `git merge --ff-only main`.

## Why

User's call, 2026-10-07: a project's urgency is set by the Overseer, in its
ruling. Today `queue.open_project` (dfmcp/executor_run.py `open_project`)
takes urgency from the proposal's `preview.urgency`, defaulting to normal,
so the proposer sets it and the Overseer cannot.

## Scope

- `queue.rule`: an optional `urgency` argument (vocabulary
  `dfqueue.schema.URGENCIES`), valid only on an accept; refused on any other
  decision. Stored on the ruling record; schema validation at write time.
- `queue.open_project`: urgency comes from the ruling; if the ruling gave
  none, the proposal's `preview.urgency`; else normal. Update the tool
  description in dfmcp/executor_tools.py (currently "The project's urgency
  is the proposal's").
- Follow-ups (`apply_followup`) keep the parent project's urgency; do not
  change that.
- The ruling briefing (conductor/briefing.py RULING_ASK) gets one short
  clause: give an urgency on an accept when it is not normal. Keep the
  prompt prefix stable (append, do not reorder).
- Do NOT edit `agents/overseer/` (stage 2E holds it). Put the charter line
  you would add, and the `queue.rule` description change for the Overseer's
  `tools.yaml` if any, in the Result for the orchestrator to add after 2E.
- Tests: rule with urgency stored; refused on reject/defer; open_project
  prefers ruling over proposal over normal; schema rejects a bad value.

## Rules

Touched surfaces: `dfmcp/queue_tools.py`, `dfmcp/executor_run.py`,
`dfmcp/executor_tools.py`, `dfqueue/schema.py`, `dfqueue/store.py` if
needed, `conductor/briefing.py`, tests, this handoff. Public repo: no
hostnames, IPs or tokens. No em dashes. No attribution lines in commits.
Commit after each milestone. Do not write Working.md, DECISIONS.md or
memory. Full ambient `python -m pytest` and `dfmcp/tests` in
`.venv-dfmcp` green on the branch.

## Result

(executor fills this in)
