# Red team: conductor execution design

Date: 2026-10-05. Target: `docs/CONDUCTOR-EXECUTION.md` at commit 2f1bf68.
Method: every design claim below was checked against the code at that
commit; line numbers are from it. The openclaw prompt builder was read
read-only inside the image on VM 106 (no container left behind, nothing
changed). Findings only; the design doc is not edited.

**Verdict.** The direction holds (proposer picks, Overseer rules, code acts,
one decider). Three findings are blockers for stages 3 and 4 as written
(C1 to C3): the executor would record blocked calls as successes, would
re-run calls that may already have happened, and the queue's own step model
cannot represent or sequence the steps the design files. Stage 1 can ship
alone if its timeout change waits (H6).

Severity: **critical** = an action the Overseer did not accept, or a
duplicate or unrecorded fort mutation; **high** = the fort left without a
remedy, a livelock, or a capability silently lost; **medium** = wrong state
or wasted turns; **low** = a claim to correct.

---

## Critical

### C1. Refusals that are not MCP errors are classed as successes

**Evidence.** The design classifies by error result: filing refuses on "an
error result" (2.2 item 1), and execution's Success row is "real call not an
error" (4.4). But `blueprint.apply` refuses with `{ok: false, blocked: true,
blocked_reason}` and no `error` string: stranded dig
(`scripts/dfhack/df-overseer-blueprint.lua:1213-1217`), reservation conflict
(`:1244-1250`), shell not finished (`:1260-1266`). `dfmcp/server.py:742-792`
turns only `{"error": str}` or `{ok: false, error: str}` into `isError`;
everything else is `isError=False`. `construction`'s single-cell path also
returns `ok = false` without `error` unless the pcall itself failed
(`df-overseer-construction.lua:300-321`).

**Effect.** A blocked dry run passes filing, so "nothing unrunnable reaches
the Overseer" is false. The "waiting" class (4.3) never fires, because the
build phase's shell-not-finished refusal is not an error. A real
`blueprint.apply` that the access or reservation gate blocked is recorded
`executed` success, the step reads done, and its dependents become ready.

**Smallest fix.** Classify by the tool's own verdict, declared as data per
tool in `TOOLS.yaml` (for example `verdict_field: ok`, plus `blocked`), and
refuse to make a tool proposable if it declares none. Treat any `ok: false`
as a refusal at filing and as Waiting or Needs judgment at execution.

### C2. A timed-out real call is retried, so it can run twice

**Evidence.** 4.4 classes "DFHack unreachable, timeout, protocol error" as
Transient: "no record; retry next cycle". The DFHack pool uses a 10 s socket
timeout (`dfmcp/dfhack_client.py:151`; `dfmcp/server.py:873` passes no
override), while the design itself cites 45 to 80 s tick-gated latencies
(4.2). A client-side timeout does not cancel a command DFHack has already
queued. Separately, `run_step` must write `executed` after the real call, and
every queue write first calls `overview.get` to stamp the tick
(`dfmcp/queue_tools.py:1073-1091`), so a DFHack hiccup after a successful
real call leaves no record. The design's Uncertain row ("issuing marker with
no executed") covers a crash, but the Transient row covers the same situation
and wins in practice.

**Effect.** `orders.create` run twice doubles production; `blueprint.apply`
with a landmark `SITE` re-resolves to a new rank and digs a second room.

**Smallest fix.** Transient only for failures before the real call is sent.
Any failure at or after sending it is Uncertain and never auto-retried. Stamp
the tick and write the `issuing` marker (as a row in the same SQLite file,
which the design does not yet place anywhere) before the real call, so the
post-call write needs no DFHack read.

### C3. The queue's step model cannot hold or sequence the design's steps

**Evidence.** 2.1 says `requires` "reuses the existing project step
validation unchanged". It cannot:

- `_validate_step` refuses unknown keys (`dfqueue/schema.py:955-958`), so
  `open` and `confirm` are refused, and it requires `targets`; an empty
  literal set is refused (`_validate_handle_list`, `schema.py:784-790`). The
  design's steps have no targets.
- `step_prerequisites_satisfied` treats a prerequisite with no target rows as
  never satisfied, "never vacuously true" (`dfqueue/store.py:1032-1057`), and
  `store.append` refuses an `executed` for a step whose `requires` are not
  satisfied (`store.py:648`). So every dependent of a targetless step is
  blocked forever, or, if `run_step` runs the real call before the append, the
  mutation happens and its record is refused.
- In the other direction, `step_status` counts any `executed` record as done
  (`store.py:1116-1135`), and `_step_has_executed_record` does not filter by
  outcome (`store.py:1138-1160`). A step whose only record is a failure reads
  done on the Board and in `project_status`, which contradicts 4.4's "one
  retry next cycle".

**Smallest fix.** Give a targetless step an explicit completion rule in one
place: done means a `success` record, used by both `step_status` and
`step_prerequisites_satisfied`; filter by outcome; allow `targets` absent;
add `open`/`confirm` to the step schema. In `run_step`, run the store's full
precondition check before the real call, never after.

---

## High

### H1. `open` is a blank cheque

**Evidence.** `fill_step` is refused only if a key is outside `open` or the
dry run fails (5). `open` is free: nothing stops `open: [site]`, `[kind]`,
`[allow_stranded]`, `[override]` or `[res_id]`. `allow_stranded` bypasses the
access gate on a real apply (`df-overseer-blueprint.lua:1205-1221`); `override`
bypasses a reservation's allowed-kinds gate (`TOOLS.yaml:298-310`). The
Overseer rules on a slot, not a value.

**Smallest fix.** Make refillable arguments data per tool (for site tools:
`rank`, `radius_tiles`) and refuse anything else in `open`. Mark
override-class arguments (`allow_stranded`, `override`) as data too; refuse
them in `steps` unless the proposal type allows them, and always show them in
the briefing line rather than among omitted "key arguments" (3.3 item 4).

### H2. Dry-run argument smuggling at filing

**Evidence.** Argument names are canonicalised to lower case
(`dfmcp/tools.py:621-635`), so the real key is `dry_run`, not `DRY_RUN`
(2.1). The filing dry run calls a mutating tool through the server's own
bypass of `Roster.check` (2.2), on behalf of an advisor that does not hold
the tool. If the check matches the wrong spelling, or the build merges
`{"dry_run": true, **args}`, a proposer's `dry_run: false` turns the preview
into a real mutation by an advisor, before any ruling.

**Smallest fix.** Refuse any step argument whose canonical name is
`dry_run`; set it after merging; and refuse the result unless the tool echoes
`dry_run: true` (blueprint does, `df-overseer-blueprint.lua:1122`; make it a
rule for every proposable tool).

### H3. Deferred proposals never close, so the Overseer re-wakes every cycle

**Evidence.** A defer-only proposal stays pending (`store.py:1315-1346`), and
any pending proposal wakes the Overseer (`conductor/triage.py:234-238`). The
design makes defer the standard repair ("defer with the missing fact named,
the proposer re-files", 3.2) and the WIP cap forces more defers (3.5). The
proposer is not woken by a defer and has no tool to withdraw; its re-filing
adds a second pending proposal (flagged duplicate) while the first stays.

**Effect.** A ruling turn per cycle over the same stale proposals, a growing
pending block, and "costs one cycle" becomes "costs until the next routine
review" (7 game days, `conductor/policy.yaml`).

**Smallest fix.** A re-filing may name `supersedes: proposal-N`, which closes
it. The `queue_pending` wake counts only proposals with no ruling since they
were filed or superseded. A defer that names a missing fact opens a flag to
the proposer (6.1).

### H4. A tripwire now has no automated remedy, yet a quiet run still resumes

**Evidence.** The tripwire branch wakes only the Overseer and returns with no
execute phase (4.5; `conductor/cycle.py:493-575`). After stage 3 the Overseer
holds no acting tool and owns no proposal type (`dfqueue/schema.py:334`). A
clean run that does not call `queue.escalate` clears the latch and resumes
(`cycle.py:534-547`). So a thirst-critical tripwire can end in "nothing done,
resumed", where today the Overseer could queue drink.

**Smallest fix.** On a tripwire, also wake the owning proposer and run an
execute phase for steps accepted that cycle with `urgency: high` while the
fort stays paused (designations and orders work paused, 4.5). Or, minimum:
treat a tripwire run that recorded no ruling, no verdict and no escalation as
escalated, the rule `pause.verdict` already applies to unexplained pauses.

### H5. Stage 3 silently drops half the fort's actions

**Evidence.** The Overseer holds 35 mutating tools today
(`agents/overseer/tools.yaml`, counted through the registry). The draft
`action_tools.yaml` (2.3) routes about 18. No proposal type covers
`trees.fell`, `farm.build`, `well.build`, `nobles.appoint`,
`nobles.unappoint`, `labor.quota`, `zone.clear-owner`, `blueprint.release`
(the stalled-dig recovery), `blueprint.unreserve`, `stockpile.unlink`,
`construction.build`, `construction.door` or `construction.audit`. After the
Rule 2 change nobody can call them, and no refusal tells anyone.

**Smallest fix.** Before stage 3, map every mutating tool to a type or list it
in the doc as deliberately retired, with a test that fails on an unmapped
mutating tool. Recovery verbs (`blueprint.release`, `unreserve`) need an
owner.

### H6. Stage 1's shorter timeout lands while the Overseer still acts

**Evidence.** Stage 1 ships per-reason timeouts (`queue_pending` 300 s,
3.4; table 8.2) but tools are only removed in stage 3. The measured acting
turn was 645 s (1). The runner kills at timeout plus 60 s
(`conductor/runner.py:57-66`, `:396-412`). A kill between a blueprint apply
and `queue.executed` leaves an applied action with no record; the ruling
stays unexecuted and the next wake applies it again.

**Smallest fix.** Move the per-reason timeouts to stage 3. Stage 1 is
otherwise safe to ship alone: it adds reads and briefing order, and changes
no write path.

### H7. Migration: the execute phase would open projects for legacy rulings

**Evidence.** Execute step 1 opens a project for "each accepted ruling
without a project" (4.2). Live, that is 9 rulings: 7 already executed by the
Overseer, plus `ruling-0001` (voided proposal) and `ruling-0006` (design 8.1).
Their proposals have no `steps`, so the project gets one implicit,
tool-null step (`normalize_project`, `schema.py:633-663`) that `run_step`
cannot run. 8.1's plan to `queue.abandon` 0001 and 0006 first cannot work:
abandon needs a project id (`store.py:754-768`). Pending pre-cutover proposals
without `steps` become unacceptable (3.5) and fall into H3.

**Smallest fix.** Execute phase acts only on rulings after a recorded cutover
id. A one-off, operator-run migration writes implicit projects for 0001 and
0006 and abandons them, and rejects pre-cutover pending proposals with a
public reason, before the execute phase is enabled.

---

## Medium

**M1. Predictions arm on the wrong execution.**
`_arm_prediction_on_first_execution` arms on the first `executed` for a
ruling, failure included (`store.py:894-950`). With multi-step projects that
is the dig designation, not the finished room, and a failed first try still
starts the window. The design leans on per-proposer grade rates to catch
rubber-stamping (9.1). Fix: arm on the last step's first success; never on a
failure.

**M2. "Failed" retries can double-apply.** A real call that errored after a
passing dry run (4.4) may have partly applied (quickfort designates, then
errors). Fix: retry only when the result proves nothing applied (for
blueprint, `designated` zero), else Uncertain.

**M3. The waiting window treats a slow dig as a stuck one.** Past
`wait_after_prereq_ticks` a still-digging room goes to Needs judgment, then
release, then abandon (4.3, 4.4). Fix: stay Waiting while the prerequisite
shows progress (`blueprint.status` pending designations falling, or jobs
claimed); go to judgment only on a stuck-job signal for that step.

**M4. Follow-up loops.** `confirm: true` always needs judgment, but
`fill_step` has no "run as is" form, so an empty `open` can only be released.
The `resolved_key` baseline after a fill is unspecified (2.4 compares with the
filing key), so a refilled step can mismatch every cycle. Nothing caps
follow-ups per step. Fix: `fill_step` with `{}` confirms; the baseline is the
latest accepted preview; two follow-ups, then automatic release.

**M5. `fill_step`'s record conflicts with the design's own authority rule.**
It appends an `amend` (5), but 4.1 makes `amend` executor-only. The fresh-id
rule (`store.py:732-755`) also forces every dependent whose `requires` or
`from_step` names the old id to take a fresh id too, a cascade the design
does not describe. Fix: a `step_fill` record kind owned by the proposer, or
spell out the cascade and who writes it.

**M6. The call cap keys on the wrong thing and can block the decisive
calls.** The cap uses the MCP session id (`dfmcp/server.py:401-412`). The
design only considers sessions being reused (stricter); if openclaw opens a
session per call or reconnects, the cap never fires. As written it would also
refuse `queue.rule`, `queue.escalate` and `pause.verdict` past 20 calls,
which in a tripwire wake can make an escalating run look clean (H4). Fix: key
on a run id the conductor issues; exempt the decision tools.

**M7. The cache layout table is not what openclaw sends.** In the image on
VM 106, `buildAgentSystemPrompt` (`dist/system-prompt-params-*.mjs`) puts the
framework text and Project Context (`SOUL.md`) before
`SYSTEM_PROMPT_CACHE_BOUNDARY`, then a dynamic tail ending in a `## Runtime`
line that carries `host=` and `sessionId=`. The runner sets `--name` but no
`--hostname` (`conductor/runner.py:280-293`), so the host value is a fresh
container id each run. The system message therefore ends in per-run bytes,
and whatever the provider renders after it (the tool list, probably;
unverified) is outside any cross-run cached prefix. Within one turn the
prefix still grows round by round, which is where most of the saving is.
`userTimezone` is unset in the pinned config, so no date line is added. Fix:
pass `--hostname <role>` in `build_command`; let stage 0 measure cache reads
before any layout work. Also, 8.2 says the archive keeps no `toolSummary`; it
does (`cycle.py:1004`), only `usage` and `assistantTurns` are dropped.

**M8. Filing can be slow and its timeouts read as wrong proposals.** One
`queue.propose` may now make up to 8 dry runs, 6 citation reads and the tick
stamp, each under the 10 s RPC timeout. A timeout refuses the proposal with
text the proposer will read as "your action is wrong" and re-file. Fix: a
distinct "server busy, retry" refusal that is not counted toward the
refused-filing detector, and a total time bound per filing.

**M9. `from_step` paths are unconstrained, and the name collides.** The
example `field: site` resolves to a table; the handle is `site.handle`
(`df-overseer-blueprint.lua:1153`, `:1185`, `:1303`). Any path is allowed, so
`site.near_landmark` would make a later dig phase find a new site, a value the
Overseer never saw. `from_step` already means "that step's done targets"
under `targets` (`schema.py:907-940`). Fix: substitutable fields declared as
data per tool, values checked against the handle pattern (`site-N`, `res-N`,
zone id); rename the key.

**M10. Flags can wake forever.** If `flag_open` is level-triggered the owner
wakes every cycle until it closes the flag; expired flags go to the Overseer,
which cannot close or reassign one (6.1). Fix: edge-triggered wake (once per
new flag, again at expiry); the Overseer may close or reassign.

**M11. Mixed period by charter prose.** Between stages 2 and 3 the
Overseer acts under "run exactly the proposal's steps" (8.1), the kind of
rule the 2026-10-05 register row moved to server refusals. Fix: ship 2 and 3
in one deploy, or refuse a `queue.executed` whose action arguments differ from
the step's.

---

## Low

- **L1.** `ledger.record` is also mutating without `DRY_RUN` (2.2 lists four
  exceptions); harmless under the signature rule but the claim is short.
- **L2.** Uncertain steps flag the Overseer (4.4), which has lost the reads
  to check the world; the proposer holds them. Route there.
- **L3.** 3.3's overlap flag only catches identical `resolved_key`s;
  adjacent ranks can share tiles. The execution-time key check covers it.
- **L4.** The register row "Advisors may propose amendments" says an accepted
  one becomes the Overseer's own `queue.amend`; stage 6 has the executor apply
  it. Needs a register line.
- **L5.** "Accepted work proceeds without spending a model turn" (4.2)
  assumes the conductor service runs; today it is disabled and run by hand,
  so accepted steps wait and their previews age.

---

## Checked and found sound

- No rendered map: previews, refusals and handles stay coordinate-free
  (`df-overseer-blueprint.lua` header "NEVER RETURNED"); `resolved_key` is
  code-only.
- No armok power: every action still goes through the same player-level
  tools; `run_step` never resumes the clock; system-class tools stay
  conductor-only (`dfmcp/roles.py:47-58`).
- No per-kind code: `action_tools.yaml`, threshold alerts and the stuck-job
  owner table are data; kinds stay argument values.
- Execute phase gating on tripwire, owned pause, ordinary escalation and
  hold matches the cycle's existing early returns (`cycle.py:580-595`).
- `open_project(ruling_id)` with no other argument removes the hollow-record
  risk; the existing one-project-per-ruling refusal holds.

## Simpler routes to the same goals

1. **Drop stage 4's machinery.** One step per proposal; the next phase is a
   new proposal citing the issued handle literally. Pin the first phase with
   what already exists: `blueprint.apply` with `SITE: res-N` carves exactly
   that reservation (`df-overseer-blueprint.lua:1154-1175`). That removes
   `from_step`, `open`, `fill_step`, `confirm` and the Lua `resolved_key` work
   (C3's dependency half, H1, M4, M5, M9) at the price of one more short
   Overseer ruling per room phase.
2. **One judgment path.** A step that will not run is marked failed with the
   tool's own reason and the proposer files an amendment proposal (already the
   user's call, 2026-10-05). That replaces `fill_step` and `release_step`.
3. **Overseer turn.** With content in the briefing, a ruling turn needs only
   `queue.rule` per proposal; keep `queue.pending` and drop the rest of the
   reads from the start, as the design proposes, rather than adding the call
   cap first.
