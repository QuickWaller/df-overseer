# Handoff: asks addressed to a named role

Date: 2026-10-07. **Executor, Sonnet, worktree. Offline; no deploys.**
First: `git merge --ff-only main`.

## Why

`research/2026-10-07-planner-design.md` revision 2 section 6.6 item 9 and
6.3: the Architect must be able to ask Logistics (and later the Planner)
before siting a workshop. Today every ask goes to the Consultant
(`_ASK_FIELDS = {"question", "proposal_id"}`, a single `ANSWER_ROLE`).

## Scope

- `queue.ask` gains an optional `to`: a closed set of roster roles marked as
  answerers (a roster field, data); default `consultant`, so every existing
  ask and test is unchanged.
- `ANSWER_ROLE` becomes `ANSWER_ROLES`; the server refuses an answer from
  anyone but the ask's addressee.
- `queue.pending` for an answerer lists only asks addressed to it.
- The answer record gains an optional, validated `pile_spec` (shape in
  design 6.3: purpose, classes from the stockpile category list, tiles
  within the 31 x 31 place cap, adjacent_to, links_only; or a reuse entry
  naming an existing pile). Coordinate-free; refuse anything positional.
- The conductor's ask routing (who is woken to answer) follows `to`.
- Roles that do not exist yet (logistics, planner) are not added to the
  roster here; tests use a fixture roster.
- Tests for each refusal and the default path.

## Rules

Touched surfaces: `dfqueue/schema.py`, `dfqueue/store.py`,
`dfmcp/queue_tools.py`, `dfmcp/roles.py` if the answerer set lives there,
`agents/ROSTER.yaml` (the answerer field on the consultant only),
conductor ask routing (`conductor/cycle.py` or wherever asks wake the
answerer), tests, this handoff. Public repo: no hostnames, IPs or tokens.
No em dashes. No attribution lines. Commit after each milestone. Do not
write Working.md, DECISIONS.md, memory or INDEX.md. Full ambient
`python -m pytest` (lupa on PYTHONPATH) and `dfmcp/tests` in `.venv-dfmcp`
green.

## Result

(executor fills this in, with deploy targets)
