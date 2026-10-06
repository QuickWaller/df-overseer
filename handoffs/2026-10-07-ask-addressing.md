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

Done, offline. Branch `worktree-agent-a40212511f2cf4cdb`.

- `agents/ROSTER.yaml`: `answerer: true` on the consultant only.
- `dfqueue/schema.py`: `answer_roles()` (enabled roles marked answerer),
  `ask_addressee()` (absent `to` means consultant), `DEFAULT_ASK_ADDRESSEE`;
  `ANSWER_ROLE` kept as an alias of the default. `ask.to` must be an answerer
  role and not the asker. Answers may be written by any answerer role; the
  store refuses anyone but the ask's addressee. Optional `answer.pile_spec`
  validated: list of at most 8 entries; new-pile entries `purpose`,
  `classes` (the 17 stockpile categories), `tiles` 1..961, optional
  `adjacent_to`, `links_only`, `note`; reuse entries `purpose: reuse`, `pile`,
  `note`. Unknown keys (x, y, pos, ...) and raw-coordinate text refused.
- `dfqueue/store.py`: `open_asks(path, limit, to=None)` filters by addressee;
  the answer-addressee check lives in `append`.
- `dfqueue/render.py` (not on the touched list, needed so the addressee sees
  `to` and `pile_spec`): renders both.
- `dfmcp/queue_tools.py`: `to` and `pile_spec` in the schemas;
  `queue.pending` for any answerer lists asks addressed to it;
  `queue.overview` asks gains `to`: `{role: [ask ids]}` (count and ask_ids
  unchanged).
- `conductor/triage.py`, `conductor/cycle.py`: wake and briefing follow the
  addressee, including the post-advisor re-wake; a summary without the `to`
  map is still all the Consultant's. An addressee the conductor has no runner
  for (not in its fixed four) wakes nobody and is logged.
- Tests: `dfqueue/tests/test_ask_addressing.py` (39),
  `dfmcp/tests/test_queue_ask_addressing.py` (5),
  `conductor/tests/test_ask_routing.py` (4); two existing assertions updated
  (answer-role message text, overview `asks.to`). Fixture roster for logistics.
- Results: ambient `python -m pytest --ignore=dfmcp/tests` 2412 passed;
  `dfmcp/tests` in `.venv-dfmcp` 935 passed.

Deploy targets (none done): VM 103 (`dfmcp-server`, `dfqueue`, roster) and
VM 106 (conductor). The conductor reads `asks.to` from the server, so deploy
server first; the conductor tolerates the old shape.

Open design points for the orchestrator: (1) `ASK_ROLES` does not yet gain
`planner` (that waits for the role); (2) `queue.pending` for a role that is
both a proposer and an answerer would list asks, not proposals, as the
consultant branch always did; (3) the conductor will need a runner and charter
for logistics before an ask to it can be answered; until then it is logged and
left open.
