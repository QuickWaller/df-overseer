# Stream: wire `dfqueue` into `dfmcp` as MCP tools (Phase A, local code)

**Written** 2026-09-15. **Status:** dispatched (Phase A). **User go-ahead:**
given for the whole of Working.md item 1, including the later deploy to VM 103
and one live architect run. **This stream is Phase A only: local code, tests,
commits on your own branch. No VM, no deploy, no model call.** Phase B (deploy,
live verify, the architect run) is dispatched separately after the orchestrator
reviews and merges your branch.

## Why

`dfqueue/` validates proposals at write time, but nothing can write to it: an
agent's only route is prose in its final answer, and architect run #2 showed
that a prompt-only format rule fails (it dropped the proposal record entirely).
`docs/AGENT-ARCHITECTURE.md` §4: "A specialist cannot emit prose into the
queue. It calls `propose(...)` with typed fields, validated at write time, and
a malformed proposal is refused." This stream makes that sentence true.

## Read first (small, targeted)

1. `dfqueue/README.md` (whole file, it is the queue's contract).
2. `dfqueue/store.py` (`append`, `latest`), `dfqueue/schema.py` (`validate`,
   `COMMON_FIELDS`, `KIND_FIELDS`, `TYPE_VOCAB_BY_ROLE`), `dfqueue/grade.py`
   (`game_tick_from_overview`), `dfqueue/render.py` (`to_xml`).
3. `learning/live_signals.py` docstring (the signal grammar a proposal's
   prediction must use).
4. `dfmcp/server.py` (whole), `dfmcp/roles.py` (whole), `dfmcp/registry.py`,
   `dfmcp/tools.py` module docstring and `tool_definitions`/`argv_for_call`.
5. `agents/architect/tools.yaml`, `agents/overseer/tools.yaml`,
   `agents/consultant/tools.yaml`, `agents/ROSTER.yaml`,
   `agents/architect/role.md`.
6. `docs/AGENT-ARCHITECTURE.md` §4 "Writes are tool calls; reads are XML"
   (around line 278) and §13 "The trust boundary" (around line 1033).

## Decisions already made, do not relitigate

- **Role identity comes from the credential, never from arguments.** The
  record's `role` is the authenticated role (`_current_role()`). `role`, `id`,
  `ts` must not be tool arguments at all, so a caller cannot even attempt to
  set them. A test must prove a supplied `role` argument is refused, not
  silently ignored.
- **The game tick is stamped server-side at write time**: call `overview.get`
  through the same DFHack pool, parse with `dfqueue.grade.game_tick_from_overview`,
  pass as `append(..., game_tick=...)`. **If DFHack is unreachable or the date
  does not parse, the proposal is refused (`isError`) and nothing is written.**
  Never stamp a guess or a wall-clock stand-in.
- **dfmcp is the single writer of the SQLite file.** Use `dfqueue.store` as
  is. SQLite calls are synchronous: run them off the event loop
  (`asyncio.to_thread`) so a write never blocks other MCP sessions.
- **The DB path is explicit config, no default**, in the same style as
  `bind_host`: a new env key (suggested `MCP_SERVER_QUEUE_DB`), missing means
  `ConfigError` at startup. Reason: the default `dfqueue/<fort>.sqlite3` sits
  inside the code tree, and a code redeploy on VM 103 must never be able to
  clobber live data. Add a placeholder to `infra/local.example.env`.
- **A queue refusal is an MCP tool result with `isError: true`** carrying
  every validation error from `QueueError`, so the model can read what was
  wrong and retry. This is the mechanical enforcement the stream exists for.
- **Queue writes are not fort mutations.** `Tool.mutates` / roles.py rule 2
  mean "mutates fort state" and must keep meaning exactly that, so advisors
  can be granted `queue.propose` without weakening "advisors are read-only".
  But **`queue.rule` must be grantable only to the roster's `sole_writer`**,
  enforced as a hard load-time rule in `roles.py` (a roster granting it to
  anyone else refuses to load), on top of `dfqueue.schema`'s own sole-writer
  check. Two independent layers, both tested.
- **Queue tools go through `Roster.check` like every other tool.** One
  boundary, not a second permission path. Their ids must therefore resolve in
  the registry (roles.py rule 1 stays intact: a typo still grants nothing).

## What to build

1. **Server-side ("native") tools, not DFHack commands.** They are not in
   `scripts/dfhack/TOOLS.yaml` and must not be added there (that file is the
   DFHack manifest). Find the smallest clean way to make the registry and
   roster know about them, e.g. a `dfmcp/queue_tools.py` that defines them with
   **hand-written, explicit JSON schemas** (not the TOOLS.yaml token
   heuristic) and a registry that holds both kinds. Your call on the shape;
   justify it in `dfmcp/README.md`. Do not break the existing 27-tool
   name/id tables or their tests.
2. **The tools** (canonical id, MCP name):
   - `queue.propose` (`queue__propose`): `type`, `summary`, `rationale`,
     `prediction` {`signal`, `op`, `value`, `check_after_ticks`}, `cost`
     {`estimate`, `unit`}, `suggested_priority`, `preconditions` [...],
     `public_rationale`. Returns the written record's `id`.
   - `queue.pass` (`queue__pass`): `reason`. An explicit decline.
   - `queue.rule` (`queue__rule`): `proposal_id`, `decision`, `reason`,
     `public_rationale`.
   - `queue.pending` (`queue__pending`): read-only, proposals with no ruling
     yet, rendered with `dfqueue.render.to_xml` ("reads are XML"). Optional
     small `limit`. If this needs a new query in `dfqueue/store.py`, add it
     there, additively, with its own test.
3. **Descriptions and schemas must teach the format**, because the tool
   description is now the only place the model learns it:
   - `type` is an `enum` of **the calling role's own vocabulary**
     (`TYPE_VOCAB_BY_ROLE`); `tools/list` is already per role, so this is
     possible.
   - `prediction.signal`'s description states the closed live-signal grammar
     from `learning/live_signals.py` (derive the text from that module, do not
     hand-copy a list that can drift), including the quoting rule for landmark
     names.
   - `op` is an enum of `PREDICATE_OPS`; `unit` an enum of `COST_UNITS`;
     `decision` an enum of `RULING_DECISIONS`; `suggested_priority` 1-7.
   - Say plainly that free-text fields are refused if they contain a raw
     coordinate.
4. **`cycle` and `snapshot`** are required common fields and there is no
   scheduler yet to own a cycle number. Pick the simplest honest option
   (server-stamped, never model-supplied), document it in `dfmcp/README.md`,
   and call it out in your report as a stand-in. Do not build a scheduler.
5. **Grants:**
   - `agents/architect/tools.yaml`: move `queue.propose` from `planned` to a
     real grant, and grant `queue.pass`. Architect gets no `queue.rule` and no
     `queue.pending` (no cross-advisor visibility in v1, §4).
   - `agents/overseer/tools.yaml`: grant `queue.rule` and `queue.pending`.
     Overseer gets no `queue.propose` (its vocabulary is empty by design).
   - `agents/consultant/tools.yaml`: **no change**; its vocabulary is empty,
     so `queue.propose` stays planned.
   - Keep each file's comments honest (`status: exists` only where true).
6. **Charter**: `agents/architect/role.md` "Your tools" and "Required proposal
   format" sections: the architect now records a proposal by calling
   `df-overseer__queue__propose` (or `df-overseer__queue__pass` to decline),
   and a refused call returns the reasons to fix. Keep the XML block only as
   "this is how your record will be rendered back", or drop it; your call.
   **Do not touch the "Does NOT own" scope text** (the run #2 scope slip is a
   separate open item).
7. **Call log**: queue calls must produce the same one-line JSON log as every
   other call (they should, via `_on_call_tool`'s wrapper; prove it with a
   test). Never log a token.

## Tests (required, not optional)

At least: per-role `tools/list` shows exactly the right queue tools; a valid
proposal is written with the tick taken from a fake `overview.get`; a supplied
`role` argument is refused and nothing is written; a malformed proposal
returns `isError` listing the errors and writes nothing; architect calling
`queue.rule` is refused by `Roster.check`; a roster granting `queue.rule` to a
non-sole-writer fails to load; DFHack unreachable at propose time means refused
and nothing written; `queue.pending` returns XML and drops a proposal once
ruled; a ruling on a nonexistent proposal is refused; missing queue DB config
is a `ConfigError`; the queue call is logged.

**Baselines before you start** (confirm them first, report both before and
after):
- ambient: `python -m pytest` from the repo root → `229 passed, 1 skipped`
  (the skip is correct: transport tests guard their own SDK import).
- venv: `dfmcp/tests` under the main checkout's `.venv-dfmcp` (it lives at
  `C:/website-projects/df-automation/.venv-dfmcp`, **not** inside your
  worktree) → `128 passed`.
- `py -3` on this workstation is 3.13 without pytest; use `python`.

## Hard lines

- **No VM access of any kind. No SSH, no deploy, no model call.** Phase B.
- Do not edit `Working.md`, `decisions/DECISIONS.md` or `memory/`; the
  orchestrator owns those. Update this doc's Result section and your row in
  `handoffs/INDEX.md` only.
- Do not rename `dfmcp` or `dfqueue`, and never add a `sys.path` hack (the
  `mcp`/`queue` shadowing traps in `CLAUDE.md`).
- Public repo: no address, hostname or token anywhere.
- Commit each meaningful chunk to your branch as you go.

## Touched surfaces

`dfmcp/server.py`, `dfmcp/registry.py`, `dfmcp/roles.py`, `dfmcp/tools.py`
(only if needed), `dfmcp/queue_tools.py` (new, or equivalent), `dfmcp/tests/*`,
`dfmcp/README.md`, `dfqueue/store.py` (additive only), `dfqueue/tests/test_store.py`
(additive only), `dfqueue/README.md` ("not here yet" section),
`agents/architect/tools.yaml`, `agents/overseer/tools.yaml`,
`agents/architect/role.md`, `infra/local.example.env`,
`infra/dfmcp-server.service.example` (only if the new env key needs it).

## Report

Executor shape, plus: the branch name and commit list; test counts before and
after for both suites; the registry shape you chose and why; how `cycle` and
`snapshot` are stamped; anything in the queue or server that surprised you;
and **a draft Phase B checklist** (which files must now be deployed to VM 103,
since `dfqueue/` and `learning/` were never part of the deployed tree, and the
new env key).

## Result

(executor fills in)
