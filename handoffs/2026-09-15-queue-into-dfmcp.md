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

**DONE 2026-09-15, Phase A only.** Branch `worktree-agent-a6fda7335003292d0`
(this stream's worktree branch, based on `main`'s `6105612`). No VM access,
no SSH, no deploy, no model call, as scoped.

First pass, two commits: `28bb3ee` (registry/roles/tools/server wiring,
dfqueue/store.py's additive `pending_proposals`, the real agents/*.yaml
grants and role.md update) and `13a3b94` (the `TestQueueTools` end-to-end
coverage in `dfmcp/tests/test_server.py`), then `33975a5` (this Result
section, first draft). After coordinator review (three fixes required
before merge): `a16c930`, `10c7f61`, `4a5c866` -- see "Review fixes,
2026-09-15" below for what each one closed.

### Baselines, confirmed before any change

- Ambient `python -m pytest` from the repo root: `229 passed, 1 skipped`,
  matching the brief exactly.
- `dfmcp/tests` under `C:/website-projects/df-automation/.venv-dfmcp`
  (`.venv-dfmcp/Scripts/python.exe`, run from this worktree's directory):
  `128 passed`. Confirmed the venv was importing **this worktree's** code,
  not the main checkout's: `python -c "import dfmcp, dfqueue; print(dfmcp.__file__, dfqueue.__file__)"`
  printed paths under
  `...\.claude\worktrees\agent-a6fda7335003292d0\dfmcp\__init__.py` /
  `...\dfqueue\__init__.py`.
- One correction to the task message: it said the worktree was already
  based on `6105612`; `git log` showed it was actually at `72c7e2d`, two
  commits behind (missing `8d076b0`'s docs pass and `6105612` itself, which
  is this handoff doc). Fast-forwarded (`git merge --ff-only main`) before
  doing anything else, since the branch was a strict ancestor with no
  divergent commits of its own -- a real fast-forward, not a merge that
  could have introduced conflicts.

### Counts after

- Ambient `python -m pytest`: **229 -> 241 passed, 1 skipped** (skip count
  unchanged: still `test_server.py`'s own guarded skip when the ambient
  `mcp` package is not the 2.x line). +12, all in files ambient already
  runs: `dfmcp/tests/test_registry.py` (native_tools merge + collision, +3),
  `test_roles.py` (rule 6, both directions plus the sole-writer-positive
  case, +3; one existing test was also rewritten in place, not counted as
  new -- see "Surprises" below), `test_tools.py` (the native `.describe`
  branch is role-scoped, +1), `dfqueue/tests/test_store.py`
  (`pending_proposals`, +5).
- `.venv-dfmcp`'s `dfmcp/tests`: **128 -> 146 passed**, +18: the same +3/+3/+1
  = 7 from registry/roles/tools above, plus `test_server.py`'s own +11 (10
  new `TestQueueTools` tests plus 1 new `TestServerConfig` test for the
  required `queue_db`). `dfqueue/tests` is not part of `dfmcp/tests`, so its
  +5 does not appear in this count. 128 + 7 + 11 = 146.

### The registry shape chosen, and why

`dfmcp/queue_tools.py` (new) defines four `NativeTool` objects (`queue.
propose`/`pass`/`rule`/`pending`), a frozen dataclass carrying only what
`roles.py` and `tools.py` actually read off a registry entry: `.mutates`
(always `False` -- a queue write is not a fort mutation, and the brief's
hard line says `Tool.mutates` must keep meaning exactly "mutates fort
state"), `.sole_writer_only` (`True` only for `queue.rule`), `.args = ()`
(so a DFHack-shaped generic sweep over `registry.all()` degrades to
"nothing to check" instead of `AttributeError`), `.native = True`, and a
`.describe(role) -> (description, input_schema)` method for a **hand-written**
JSON schema per the brief (never `TOOLS.yaml`'s token heuristic).

`registry.py` gained one kwarg, `load_registry(path=..., native_tools=None)`:
merges an extra `{id: tool}` mapping in additively, after the normal
`TOOLS.yaml` parse and its own collision check, refusing to load
(`RegistryError`) if a native id collides with a real one. It stays
generic and importless of `dfqueue`/`queue_tools` -- the default is `None`
(no native tools at all), so every existing caller of `load_registry()`
with no arguments is completely unaffected. `dfmcp/server.py`'s `main()` is
the one production caller that opts in
(`load_registry(native_tools=queue_tools.NATIVE_TOOLS)`); every test
fixture that loads the **real** `agents/` roster had to opt in the same
way, because the real `agents/architect/tools.yaml` and `agents/overseer/
tools.yaml` now grant real `queue.*` ids, which `roles.py` rule 1 requires
to exist in the registry -- without this, `load_roster(registry)` would
fail to load for every test in `test_roles.py`, `test_auth.py`,
`test_tools.py` and `test_server.py` that uses the real roster, not just
new ones. That was the single biggest surprise of this stream (see below).

`tools.py`'s `tool_definitions` duck-types (`hasattr(tool, "describe")`)
rather than `isinstance`-checking against `dfmcp.queue_tools.NativeTool`,
so it never imports `queue_tools` and stays what its own docstring says:
"a pure function of the registry and the roster." `server.py`'s
`_handle_call_tool` duck-types the same way (`getattr(tool, "native",
False)`) to route a call to `queue_tools.call(...)` instead of
`argv_for_call`/`pool.run_command`, before either of those DFHack-specific
functions ever sees a native tool.

**`roles.py` gained one new hard load-time rule (rule 6), independent of
rule 2**: a tool the registry marks `sole_writer_only` may only be granted
to the roster's `sole_writer`, checked generically
(`getattr(tool, "sole_writer_only", False)`) regardless of section (`read`
or `write`). This had to be a *new* rule rather than reusing rule 2
(`mutates`) because `queue.rule` deliberately does not mutate fort state --
widening `Tool.mutates` to also mean "or is otherwise sensitive" was
explicitly barred by the brief. `dfqueue.schema.validate` still
independently refuses a `ruling` record whose `role` is not the roster's
`sole_writer` at write time, so this is a second, load-time layer, not a
replacement -- both directions tested in `dfmcp/tests/test_roles.py`
(`test_rule6_sole_writer_only_tool_granted_to_non_sole_writer_refuses_to_load`,
its `_hidden_under_read` sibling, and
`test_rule6_sole_writer_may_hold_the_sole_writer_only_tool`).

### `cycle`/`snapshot`: what got stamped, and how

Per the brief's own framing (no scheduler/Projection component exists yet,
`docs/AGENT-ARCHITECTURE.md` §5), the stand-in chosen is: **every** queue
write (`propose`, `pass`, and `rule` -- not only `propose`) calls
`overview.get` through the DFHack pool, parses it with
`dfqueue.grade.game_tick_from_overview`, and stamps `cycle` as that
absolute game tick and `snapshot` as `f"tick-{cycle}"`. This is real,
monotonic, and mechanically read, never a guess or a wall-clock
fallback -- but it is a real behavioural consequence worth stating plainly,
not only a comment: **every queue write, not only `propose`, now needs
DFHack reachable to succeed at all.** `queue.propose` already needed
`overview.get` for its prediction's `due_game_tick`; extending the same
call to `pass`/`rule` for `cycle`/`snapshot` was the simplest option that
kept all three writes honest in the same way, at the cost of that new
dependency. Documented in `dfmcp/queue_tools.py`'s own module docstring and
`dfmcp/README.md`'s new "What `queue_tools.py` exposes" section, flagged as
a stand-in to revisit once a real Projection component exists.

### Surprises

1. **The worktree was two commits behind `main`** (see baselines above) --
   caught before doing any work, by reading `git log` rather than trusting
   the task message.
2. **Granting `queue.propose`/`queue.pass` to architect broke an existing
   test's premise**, not just added new ones:
   `test_only_the_sole_writer_has_write_entries` asserted
   `not roster.roles["architect"].write`, which stopped being true the
   moment architect legitimately got queue writes. Renamed to
   `test_only_the_sole_writer_has_fort_mutating_write_entries` and rewritten
   to assert architect's write set is exactly `{queue.propose, queue.pass}`
   and that neither mutates -- a deliberate, documented change to an
   existing test's assertion, not a workaround.
3. **The shared `registry`/`roster` module-scoped fixtures in four test
   files** (`test_server.py`, `test_roles.py`, `test_auth.py`,
   `test_tools.py`) all had to switch to
   `load_registry(native_tools=NATIVE_TOOLS)`, because they load the
   **real** `agents/` directory and `roles.py` rule 1 (every allow-listed
   id must resolve in the registry) would otherwise fail the whole roster
   load for every test in each of those files, not just the new ones. This
   was the single largest source of "collateral" edits in this stream and
   the reason `NativeTool` needed an `.args = ()` field at all (for
   `test_tools.py`'s generic argument-token sweep over `registry.all()` to
   degrade harmlessly rather than crash).
4. **`Server.streamable_http_app()`'s session manager can only run its
   lifespan once per app instance** (already documented in
   `test_server.py`'s own module docstring, but easy to trip over writing
   new multi-session tests): three of my first-draft `TestQueueTools` tests
   reused one `app` object across more than one `mcp_session(...)` call and
   failed with `StreamableHTTPSessionManager .run() can only be called once
   per instance`. Fixed by building a fresh `app` per session throughout
   (state persists across them via the shared SQLite `queue_db` path, not
   via the app object) -- the file's own existing convention, just missed
   on the first pass.
5. **`_call_dfhack`'s internal `overview.get` call deliberately bypasses
   `Roster.check`.** Flagged as a real design question in
   `dfmcp/queue_tools.py`'s docstring rather than silently decided: every
   role that can reach a queue-write tool today also holds `overview.get`
   directly, so this is not yet load-bearing, but the design should not
   quietly depend on that coincidence continuing if a future role could
   write to the queue without also being allowed to read `overview.get`.

### Draft Phase B deploy checklist (not run; needs explicit go-ahead)

1. **Files to sync to VM 103's checkout** that have never been deployed
   there before: the whole `dfqueue/` package, `learning/live_signals.py`
   (and the rest of `learning/` if not already there --
   `handoffs/2026-09-15-live-signals-sqlite.md` was itself local-only),
   `learning/predictions/grade.py`'s additive `apply_predicate`. Plus this
   stream's own changes: `dfmcp/queue_tools.py` (new),
   `dfmcp/registry.py`, `dfmcp/roles.py`, `dfmcp/tools.py`,
   `dfmcp/server.py`, `agents/architect/tools.yaml`,
   `agents/overseer/tools.yaml`, `agents/architect/role.md`.
2. **A new required env var, `MCP_SERVER_QUEUE_DB`**, in VM 103's real
   `.env` (not the example), pointing **outside** the code checkout (e.g.
   `/var/lib/dfmcp/uniboslan.sqlite3`) -- `dfmcp.server.ServerConfig`
   refuses to start without it, matching `MCP_SERVER_BIND_HOST`'s own
   no-default contract.
3. **A real operational gotcha this stream's own service-file comment now
   flags**: `dfmcp-server.service`'s `ProtectSystem=strict` +
   `ReadWritePaths=/CHANGEME/df-automation` (checkout only) would make the
   queue db's directory read-only under systemd unless that directory gets
   its own `ReadWritePaths` entry. Create the directory and grant the
   service's `User`/`Group` write access to it *before* the first start,
   and add it to `ReadWritePaths`.
4. Install/refresh `dfmcp/requirements.txt` into the existing dedicated
   venv (unchanged by this stream -- no new dependency), `systemctl
   daemon-reload` if the unit file changed, `systemctl restart
   dfmcp-server.service`.
5. **Live-verify, in order**: a raw `tools/list` with the architect token
   shows `queue__propose`/`queue__pass`; the overseer token shows
   `queue__rule`/`queue__pending`; neither shows the other's. A real
   `queue__propose` call against the live fort produces a row visible via a
   follow-up `queue__pending` call (and/or `sqlite3
   <MCP_SERVER_QUEUE_DB> "select id, role, cycle from records"` on the
   host). A real `queue__rule` call against that proposal's id, from the
   overseer token, drops it from a subsequent `queue__pending`.
6. Only after 1-5 pass: the live architect charter run (run #3) the user
   already gave go-ahead for, this time with the real `queue.propose` tool
   in place of the prompt-only XML format that failed once already (run
   #2's regression).
7. This is its own dispatched stream (VM access, live writes to a running
   fort's MCP server), not something this Phase A executor runs -- per this
   repo's explicit-confirmation-each-time rule.

### Review fixes, 2026-09-15 (same stream, same branch/worktree)

The coordinator's Phase A review confirmed both suite counts above
independently and found three real gaps before merge. All three fixed on
this same branch, three more commits: `a16c930` (defer semantics),
`10c7f61` (storage errors and write serialisation), `4a5c866` (docs).

**1. Defer no longer makes a proposal vanish.** `dfqueue/store.py`'s
`pending_proposals()` used to exclude a proposal once *any* ruling existed
against it, so a `defer` ("decide later") silently removed it from the
Overseer's own view for good. Fixed: a new `FINAL_DECISIONS = (ACCEPT,
REJECT)`; `pending_proposals()` excludes a proposal only once a ruling
with a *final* decision exists (via `json_extract(payload,
'$.decision')`, no `schema_version` bump); `append()` refuses a second
ruling on a proposal that already has a final one (a repeat accept/reject,
or any ruling, even another defer, after one), but allows a ruling
(including another defer) after a defer. **JSON1 confirmed working in
both interpreters this project runs SQLite from**: ambient `python` and
`.venv-dfmcp` both report `sqlite3.sqlite_version == "3.45.3"`, and a
direct `SELECT json_extract('{"decision":"accept"}', '$.decision')`
against an in-memory database returned `('accept',)` in both -- SQLite's
JSON functions moved into core (no longer a loadable extension) at 3.38.0
(2022-02-22), so 3.45.3 has them unconditionally. **Not assumed for VM
103**: flagged in the "not built yet"/Phase B section above as a live
fact to re-confirm (Ubuntu noble ships Python 3.12, whose stdlib
`sqlite3` links against a recent-enough system SQLite in every noble
build this project has seen, but "seen elsewhere" is not "checked on VM
103"). Five new tests in `dfqueue/tests/test_store.py`: defer keeps a
proposal pending, reject removes it, a ruling (including a second defer)
after a defer is allowed, a second final ruling is refused and writes
nothing, and a defer after a reject is refused too (proving the rule is
about the *existing* ruling being final, not about what the new one says).

**2. Storage errors are refusals now, not crashes.** Only
`store.QueueError` used to become a `QueueToolError`; a `sqlite3.Error` or
`OSError` from the store (the exact `ProtectSystem=strict`/read-only-queue-
directory scenario this stream's own Phase B checklist flags) would have
propagated out of `_handle_call_tool` as an unhandled exception, not an
`isError=True` tool result. Fixed: every `dfqueue.store` call in
`dfmcp/queue_tools.py` now goes through `_append_locked` (writes) or a
direct `try/except` (the read in `_pending`), both catching
`(sqlite3.Error, OSError)` alongside `store.QueueError` and wrapping into
`QueueToolError` via a new `_storage_error` helper. Tested with a real
`NotADirectoryError` (a file placed where `store._connect`'s own
`mkdir(parents=True)` expects a directory -- no mocking needed, this
reproduces the real failure class directly) for both `queue.propose` and
`queue.pending`, plus one monkeypatched `sqlite3.OperationalError`
("database is locked") to prove a genuine `sqlite3.Error`, not only
`OSError`, is caught.

**3. SQLite moved off the event loop, and writes are serialised.** The
original brief's own decision ("SQLite calls are synchronous: run them
off the event loop, asyncio.to_thread") was missed in the first pass --
every store call ran synchronously, directly on the event loop, blocking
every other in-flight MCP session for its duration. Moving them onto
`asyncio.to_thread` alone would have introduced a real, previously-latent
race: `store._next_id` is `COUNT(*)`-based and runs, along with the
existing-id check, *before* the row it names is inserted -- safe only
because a purely synchronous call never yields between the two. Fixed
with one `asyncio.Lock` per running server (`build_mcp_server` creates it
fresh and passes it to every `queue_tools.call`; deliberately not a
`queue_tools`-module-level singleton, since an `asyncio.Lock` binds to
whichever event loop first acquires it and raises if reused from a
different one -- a real hazard for a module-level object touched by more
than one event loop across a server restart, or one test after another),
held only around the `store.append` call itself (`_append_locked`), never
around `_stamp_cycle_snapshot`'s `overview.get` call: DFHack latency has
been observed at 40-80s under load elsewhere in this project, and
serialising every queue write behind whichever one is waiting on that
would be a worse failure mode than the race it replaces.

New `dfmcp/tests/test_queue_tools.py` (imports nothing from the `mcp`
SDK, so it runs under ambient `python` too, not only `.venv-dfmcp`):
storage-error tests as described above, plus the concurrency pair --
`test_concurrent_raw_appends_without_serialization_can_collide` (direct
`asyncio.to_thread(store.append, ...)` calls, no lock, with `_next_id`
monkeypatched to `time.sleep(0.05)` so the race is deterministic rather
than occasional) and
`test_concurrent_proposes_through_queue_tools_get_distinct_ids_and_all_land`
(the same forced slowdown, through the real `queue_tools.call` path,
which does hold the lock) -- and a third test proving the lock is never
held across the DFHack call (two concurrent proposes' `call_dfhack`
calls must both start before either can finish, or the test hangs to its
own timeout).

**Verified the verification, as asked, not just asserted it.** Backed up
`dfmcp/queue_tools.py`, temporarily made `_append_locked` skip the
`async with write_lock:` block entirely (an `if True: return ...` before
it), and re-ran
`test_concurrent_proposes_through_queue_tools_get_distinct_ids_and_all_land`
alone: it failed, with a real `sqlite3.IntegrityError: UNIQUE constraint
failed: records.id` (now surfaced through fix 2's own `QueueToolError`
wrapping, a nice confirmation the two fixes compose correctly) raised
from inside `_append_locked`. Reverted the edit, confirmed the file was
byte-identical to the pre-edit backup via `diff`, and re-ran the same
test: it passed again, and the full suite (`dfmcp/tests/test_queue_tools.py`,
6 tests) passed clean immediately after.

**Counts after all three fixes**: ambient `python -m pytest`:
**241 -> 252 passed, 1 skipped** (+11: +5 `dfqueue/tests/test_store.py`
defer/final-ruling tests, +6 `dfmcp/tests/test_queue_tools.py`, all
collected under ambient since neither file imports the `mcp` SDK).
`.venv-dfmcp`'s `dfmcp/tests`: **146 -> 152 passed** (+6,
`test_queue_tools.py` only -- `dfqueue/tests` is not part of
`dfmcp/tests`). Skip count unchanged throughout (still `test_server.py`'s
own guarded SDK-version skip).
