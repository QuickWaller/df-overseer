# Stream: conductor pre-deploy fixes (agent loop MVP)

**Written** 2026-09-22. **Status:** dispatched. **User go-ahead:** the MVP
build plan, 2026-09-22. Offline only: **no VM, no deploy, no model call, no
push.** Sonnet executor, worktree-isolated. **No attribution lines in commit
messages** (no Co-Authored-By, no "Generated with Claude Code"): the user's
instruction.

## Why

The conductor stream (`handoffs/2026-09-22-loop-conductor-service.md`, read
its Result section, "Design flags") landed with gaps that would break or
blind the first real run. Fix these before the deploy:

1. **Blocking: the Consultant is never woken.** `queue.pending` branches on
   the caller's authenticated role, so the conductor cannot see open asks.
   An Overseer fact-check blocks `queue.rule` on its proposal until answered,
   so that proposal would sit blocked forever. Give the conductor a read of
   open asks (a conductor-only native tool, or a role argument on a
   conductor-only tool; not a way for any agent to read another role's
   queue), and make the conductor wake the Consultant on open asks, with a
   test that runs ask, wake, answer and then the ruling going through.
2. **Refusals pass as successes.** `dfmcp/server.py` marks a result `isError`
   only when the object is exactly `{"error": ...}`; the clock and quicksave
   tools refuse with `{"ok": false, "error": ..., ...}`. Make a refusal from
   these tools reach the client as `isError: true` with its detail kept, by
   the narrowest fix you can justify (the server rule or the tools' output),
   tested. The conductor's own `ok` checks must still work.
3. **No escalation convention.** Define how the Overseer escalates to the
   human (its charter's Escalation section already lists when): a queue
   record or tool call, not free text, so the conductor detects it
   mechanically and leaves the fort paused. Update `agents/overseer/role.md`
   and the conductor. A clean run with no escalation must no longer be
   treated as one; a failed or timed-out run still leaves the fort paused.
4. **Hostile-reachable signal.** The conductor has no hostile read, so
   `hostile_seen_unreachable` is always false. Grant it the existing
   read-only threat scan if its cost is bounded (check `TOOLS.yaml`'s notes),
   or say why not and leave it documented as a gap.
5. **Small owed items:** `conductor/requirements.txt` (pinned, matching
   `dfmcp/requirements.txt` where shared); `MCP_ROLE_TOKEN_QUARTERMASTER=` in
   `infra/local.example.env`.

## First

`git merge --ff-only main` in your worktree (local `main` is ahead of
`origin/main`).

## Touched surfaces (yours only)

`conductor/` and its tests; `dfmcp/queue_tools.py`,
`dfmcp/tests/test_queue_tools.py`; `dfmcp/server.py`,
`dfmcp/tests/test_server.py` (item 2); `scripts/dfhack/df-overseer-clock.lua`
and `df-overseer-fort.lua` and their `TOOLS.yaml` entries (only if item 2 is
fixed at the tool); `dfqueue/` (only if item 3 needs a record kind);
`agents/overseer/`, `agents/conductor/`; `dfmcp/tests/test_roles.py`;
`infra/local.example.env`; `dfmcp/README.md`, `dfqueue/README.md`; this doc
and its `handoffs/INDEX.md` row.

## Hard lines

- No VM, no SSH, no deploy, no model call, no Docker run. No push.
- No attribution lines in commits.
- Do not write `Working.md`, `decisions/` or `memory/`. No em dashes in prose.
- Commit after each milestone and extend the Result section as you go.

## Done when

Both suites pass (ambient `python -m pytest`, baseline **1175 passed / 3
skipped**; `dfmcp/tests` in the main checkout's `.venv-dfmcp`, baseline
**609**), counts reported, and the Result section lists each fix, its test,
and any change to the deploy steps.

## Result

**DONE 2026-09-22, offline, no VM, no SSH, no deploy, no model call, no
Docker run, no push.** Commits on this worktree's branch (see `git log`,
each one a milestone): `queue.overview`/`queue.escalate` native tools plus
the `dfmcp/server.py` isError generalisation and `conductor/cycle.py`/
`conductor/status.py` wiring; rewiring the existing conductor tests onto
`queue.overview`; new conductor tests for the Consultant wake, the tolerant
write-call helper and mechanical escalation (tripwire and ordinary-cycle);
`dfmcp`/`dfqueue` tests for the two new native tools and the `escalation`
record kind; `conductor/requirements.txt` and the `MCP_ROLE_TOKEN_QUARTERMASTER`
placeholder; README updates.

### Fix 1: the Consultant is never woken

**Built a new native tool, `queue.overview`** (`dfmcp/queue_tools.py`,
`QUEUE_OVERVIEW`/`_overview`), not a role-override argument: role-independent
by construction (ignores `role` entirely, unlike `_pending`), always returns
`{"proposals": {"count", "proposal_ids"}, "asks": {"count", "ask_ids"}}` in
one read (`store.pending_proposals()` + `store.open_asks()`). Granted only
in `agents/conductor/tools.yaml` (replacing `queue.pending` there), the same
"restricted by allowlist only, not a structural check" pattern `queue.grade`
already established -- not a way for any role to read another role's queue
view; no other `tools.yaml` grants this id.

`conductor/cycle.py`'s Tier 0 read now calls `queue.overview` instead of
`queue.pending`. `Signals.queue_holds_for_overseer` reads the `proposals`
half, `Signals.open_ask_for_consultant` the `asks` half (both previously
hard-coded `False`/derived from the wrong half). A new `_queue_summary_for(role,
queue_state)` picks which half a given role's own briefing sees (`asks` for
the Consultant, `proposals` for everyone else), so `build_briefing`'s
existing `queue_summary.get("proposal_ids") or queue_summary.get("ask_ids")`
logic needed no change.

**Tested**: `dfmcp/tests/test_queue_tools.py`'s `TestQueueOverview` (6
tests) includes the handoff's own requirement directly --
`test_the_full_ask_wake_answer_ruling_loop_through_queue_overview`: propose,
ask (fact-check), `queue.overview` as `conductor` sees both counts, `queue.rule`
refused while open, `queue.answer`, `queue.overview` shows the ask gone,
`queue.rule` goes through, `queue.overview` shows the proposal gone too.
Plus: an empty queue, role-independence (identical result called as
`conductor` vs. `architect`), argument/limit refusals, a storage-error
refusal. `conductor/tests/test_cycle.py`: `test_an_open_ask_wakes_the_consultant`,
`test_the_consultants_briefing_carries_ask_ids_not_proposal_ids`.
`conductor/triage.py` itself needed no change (`open_ask_for_consultant`'s
wake rule already existed; only the plumbing that populated it was broken).

### Fix 2: refusals pass as successes

**Fixed at the server, not the tool.** `dfmcp/server.py`'s `_run_dfhack_tool`
already special-cased the exact `{"error": "<string>"}` single-key shape;
added a second, narrow check right after it: a dict with `ok is False` and a
string `error` (the clock/fort family's own convention, confirmed against
`scripts/dfhack/df-overseer-clock.lua`/`df-overseer-fort.lua` source: every
`ok=true` return there never carries an `error` key, so this cannot misfire
on a real success) now also returns `isError=True`, with the FULL parsed
object kept as `structuredContent` and the complete raw JSON kept in the
text block -- detail kept, not dropped, unlike the single-key case above it
which only ever carried the bare message. Chose the server fix over
rewriting both Lua files: one place, covers this convention for any future
tool that adopts it too, and Lua changes were flagged as needing this
stream's touched-surfaces grant "only if fixed at the tool" -- not needed.

**`conductor/cycle.py` still works, by design change, not luck.** A new
`_call_write(call, tool_id, arguments, clock_changes, cycle_index)` helper
wraps every `clock.*`/`fort.quicksave` call. On the real, now-fixed server,
a refusal raises `MCPToolError`; `_call_write` catches it, logs once at
`ERROR` (tool id and reason -- previously only `clock.resume` did this, now
every write in the family does), and synthesises the same `{"ok": False,
"error": <text>}` shape the OLD, unfixed tool used to return directly, so
every existing `.get("ok", False)` check downstream keeps meaning exactly
what it always meant. Applied to `clock.arm`, `fort.quicksave` (both call
sites), `clock.clear`, `clock.resume`, `clock.set-speed`, `clock.pause` (new,
fix 3). A refusal is always still recorded in `clock_changes`, never
silently dropped.

**Tested**: `dfmcp/tests/test_server.py`, three new tests --
`test_ok_false_refusal_shape_is_a_tool_error_with_detail_kept` (against
`clock.resume`'s own real refusal shape, through a real `conductor`-token
MCP call, not a hand-invented payload or role), `test_ok_true_clock_result_is_unaffected_by_the_new_check`
(the "conductor's own ok checks must still work" requirement, proven
against a real success), `test_ok_false_without_a_string_error_field_is_still_a_result`
(narrow-by-convention, not "any falsy ok", proven the same way
`test_object_with_error_field_beside_data_is_still_a_result` already proves
the single-key case is narrow). `conductor/tests/test_cycle.py`'s
`test_a_clock_resume_refusal_is_logged_and_does_not_crash_the_cycle` proves
the client side: an injected `MCPToolError` from `clock.resume` does not
crash `run_cycle`, is logged at `ERROR`, and lands in `clock_changes` as an
`{"ok": False, ...}` dict.

### Fix 3: no escalation convention

**A new record kind, `escalation`** (`dfqueue/schema.py`'s `ESCALATION`,
one field: `reason`), and a new native tool, **`queue.escalate`**
(`dfmcp/queue_tools.py`, `sole_writer_only=True`, same restriction as
`queue.rule`/`queue.executed`, enforced twice: `dfmcp.roles`'s load-time
`SYSTEM_CLASS`-adjacent check via `sole_writer_only` and `dfqueue.schema.validate`'s
own `role == sole_writer()` check at write time). Granted only in
`agents/overseer/tools.yaml`. `dfqueue/render.py` gained `_escalation_xml`;
`dfqueue/store.py` needed no change (no cross-reference to validate, same
class of record as `pass`).

**`agents/overseer/role.md`'s Escalation section** now says explicitly:
escalate ONLY by calling `queue.escalate`; saying so in a final answer is
never read as an escalation.

**`conductor/cycle.py`'s `_overseer_called_escalate`** (replacing
`_overseer_escalated`) is now purely mechanical: it checks openclaw's own
`toolSummary.tools` (the "stable agent-exec JSON envelope",
`research/2026-09-18-openclaw-capabilities.md`; a real `run.json`'s own
shape, confirmed against `evals/live/2026-09-15-architect-third-charter/run.json`,
not assumed) for this tool's wire name -- never `final_answer`'s prose, and
never treats an unclean run as equivalent to an escalation by itself
anymore. Two independent reasons the fort stays paused, no longer conflated:
`run_unclean` (`not ok` or `timed_out` -- "a failed or timed-out run still
leaves the fort paused", unchanged) and `called_escalate` (the actual fix: a
CLEAN run that DID call `queue.escalate` now correctly stays paused too,
which the old `ok`/`timed_out` proxy could never detect at all). "A clean
run with no escalation must no longer be treated as one" holds as the
companion invariant, proven directly.

**Generalised beyond the tripwire, since the charter's own Escalation
section is not tripwire-specific**: the ordinary (non-tripwire) advise/act
loop now also checks `_overseer_called_escalate` after the Overseer's own
run and, if true, calls `clock.pause` (via `_call_write`) and marks
`CycleResult.escalated`/`clock_level=PAUSED`, so an escalation during an
ordinary cycle (queue holds something for the Overseer, no tripwire latched)
pauses the fort immediately rather than only being caught the next time a
tripwire happens to latch. `conductor/status.py`'s `log_cycle` updated to
log this new `escalated=True, tripwire=None` case at `ERROR` too (it used to
fall through to the `INFO` branch, since the old code only ever checked
`tripwire is not None and escalated`).

**Tested**: `dfmcp/tests/test_queue_tools.py`'s `TestQueueEscalate` (5
tests: a valid escalation, role restriction, empty reason, unexpected
argument, and that an escalation never pollutes `queue.pending`/`queue.overview`'s
counts). `dfqueue/tests/test_schema.py` (5), `test_render.py` (2),
`test_store.py` (1) for the record kind itself. `conductor/tests/test_cycle.py`:
`test_a_tripwire_stays_paused_when_a_clean_run_calls_queue_escalate` (the
actual gap this fixes), `test_a_tripwire_resumes_when_a_clean_run_never_calls_queue_escalate`
(the companion invariant), `test_the_overseer_can_escalate_during_an_ordinary_cycle_and_pauses_the_fort`,
`test_an_ordinary_cycle_with_no_escalate_call_never_pauses`.
`conductor/tests/test_status.py`'s `test_log_cycle_an_ordinary_cycle_escalation_with_no_tripwire_logs_at_error`.

### Fix 4: hostile-reachable signal

**Checked, not fixed, and documented why not** (`conductor/cycle.py`'s own
module docstring, gap 2). `threat.scan` (`scripts/dfhack/df-overseer-threat.lua`'s
`scan [RADIUS_TILES]`) does exist and its cost is bounded (read from
source: one pass over `world.units.active`, `MAX_RADIUS`/`MAX_RESULTS`
capped) -- but granting it to the conductor would not fix
`hostile_seen_unreachable`, because that tool answers a different question.
`find_threats`'s own admission rule is `shares_walkable_group OR
near_a_landmark` -- **reachability**, by design (its header: "reachability
gets both right") -- so it structurally cannot return a hostile that is
seen but NOT yet reachable, which is exactly what this signal needs
(`docs/AGENT-LOOP.md` §1/§3: "hostile seen but not yet able to reach the
fort" -> slowed, vs. the in-game tripwire, which already runs this same
`find_threats` check itself for `hostile_reachable`). Anything the
conductor read from `threat.scan` would duplicate the tripwire's own
reachable case, not cover the unreachable one. The real fix needs the
still-owed announcement-class tripwire/event (`docs/AGENT-LOOP.md` §3)
feeding a genuine sighting into `diff.since`, not a new grant of this tool.
`Signals.hostile_seen_unreachable` stays `False` always, left as a
documented gap.

### Fix 5: small owed items

**`conductor/requirements.txt`** (new): `mcp==2.2.0` and `pyyaml==6.0.3`,
the exact same pins `dfmcp/requirements.txt` uses, for the same reasons
(the 2.x low-level Server/session API; the version that installed and ran
live on VM 103). Every other module in this package needs only the stdlib.

**`infra/local.example.env`**: added `MCP_ROLE_TOKEN_QUARTERMASTER=`, the
one genuinely missing role token the conductor-service stream's own report
flagged (the other four -- overseer/architect/consultant/conductor -- were
already present, confirmed by `grep` before touching this file).

### How it was verified

- **Every new/changed behaviour has a direct, offline test** -- see each
  fix's own section above for the exact test names.
- **Both full suites, before and after every commit.** Final: ambient
  `python -m pytest` **1202 passed, 3 skipped** (baseline 1175/3, **+27**: 7
  in `conductor/tests/test_cycle.py`, 1 in `conductor/tests/test_status.py`,
  8 in `dfqueue/tests/` (5 schema + 2 render + 1 store), 11 in
  `dfmcp/tests/test_queue_tools.py` -- this last file needs no MCP SDK
  import, so it runs under the ambient interpreter too, unlike
  `test_server.py`). `dfmcp/tests` run via the main checkout's `.venv-dfmcp`
  interpreter with this worktree as `cwd`
  (confirmed by `import dfmcp, conductor; print(...)` to resolve to THIS
  worktree's own packages, not the main checkout's, both before starting
  and again just now): **623 passed** (baseline 609, **+14**: the same 11
  `test_queue_tools.py` tests plus 3 new `test_server.py` tests that need
  the real MCP SDK).
- **Secret scan**: `grep -rEn "sk-[A-Za-z0-9]{10,}|Bearer [A-Za-z0-9]{10,}"`
  and a private-IPv4-literal sweep over every file this stream touched --
  zero hits.

### Change to the deploy steps (relative to the conductor-service handoff's own "Exact deploy steps")

- **VM 103, step 2** ("Grant `queue.grade` to the conductor role: already
  done... part of the same redeploy") now also covers `queue.overview`:
  `agents/conductor/tools.yaml` grants it in the same file, same redeploy,
  no separate step.
- **VM 103, new**: `agents/overseer/tools.yaml` now grants `queue.escalate`
  -- covered by the same `dfmcp`/roster redeploy that already has to happen
  for `queue.grade`/`queue.overview`, not an extra step, but worth knowing
  the Overseer's own tool count changed too (`openclaw mcp probe df-overseer
  --json` against the real server, per every prior eval's own practice, will
  now show one more tool for that role than the conductor-service stream's
  own deploy checklist assumed).
- **VM 106, step 2** ("Install a dedicated venv... a `conductor/requirements.txt`
  was not written this stream; it should mirror the relevant subset of
  `dfmcp/requirements.txt`, flagged as owed"): **no longer owed.**
  `conductor/requirements.txt` now exists; `pip install -r conductor/requirements.txt`
  inside that venv.
- **VM 106, step 1** ("Only `MCP_ROLE_TOKEN_QUARTERMASTER` is genuinely
  missing... flagged as a line owed to `infra/local.example.env`"): **no
  longer owed** -- the placeholder line now exists; still needs a real
  token minted before deploy, same as every other role.
- Every other deploy step in that handoff's Result section is unchanged by
  this stream.

### Anything I think is still wrong, or found while building

1. **`queue.escalate`'s cost is not itself bounded by anything except the
   Overseer's own judgement.** Nothing stops a future charter edit (or a
   model ignoring the charter) from calling it every cycle, which would
   pause the fort constantly. This is the same trust boundary every other
   sole-writer tool already has (the Overseer is trusted with `queue.rule`
   too), not a new one, but worth naming: there is no rate limit or
   escalation-count budget anywhere in this design.
2. **The ordinary-cycle escalation path (fix 3's generalisation beyond the
   tripwire) was not explicitly asked for by the handoff's own wording** --
   the handoff's item 3 reads most naturally as being about the tripwire's
   own resume decision. Built anyway because `agents/overseer/role.md`'s
   Escalation section is not tripwire-scoped (an irreversible action or a
   contradicted fact can come up any cycle, not only while a tripwire is
   already latched), and leaving it undetected outside a tripwire would
   mean the mechanical-detection fix only half-closes the gap it names.
   Flagged here rather than silently assumed obviously in scope, since it
   is the one piece of this stream that goes beyond a literal reading of
   the brief.
3. **`_call_write`'s synthesised `{"ok": False, "error": <text>}` on a
   caught `MCPToolError` loses whatever OTHER fields the real refusal
   carried** (e.g. `clock.resume`'s own `"tripwire"` key) -- the exception
   message (`str(exc)`) is built from the full raw JSON text in
   `dfmcp/server.py`'s new check, so the information is not gone, but a
   caller reading `clock_changes[i]["result"]` programmatically (rather than
   the log line) only gets `ok`/`error`, not the original extra keys, as a
   plain dict. Not fixed here: parsing structured detail back out of an
   `MCPToolError`'s own text would need `conductor/mcp_client.py`'s
   `MCPToolError` to carry structured data itself, which it does not today
   and was not in this stream's scope to add.
4. **`threat.scan`'s own live-verification status is more solid than fix 4's
   text implies in isolation**: `agents/overseer/tools.yaml`'s own note says
   it was "Live-verified 2026-09-12" against both the failure cases that
   motivated it. The reason it is still not granted to the conductor is
   purely the semantic mismatch (reachable vs. unreachable), not any doubt
   about the tool's own correctness.
