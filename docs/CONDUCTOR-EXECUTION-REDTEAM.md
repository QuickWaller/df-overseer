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

---

# Pass 2: revision 2 (commit 68fb6aa)

Date: 2026-10-05. Repo code only this pass; no host access. Same severity
scale as pass 1.

**Verdict.** Revision 2 closes the three pass-1 blockers in design: tool
verdicts, the issuing marker and Uncertain class, and one completion rule
with a synthetic target. The simpler route removes `open`, `fill_step` and
`from_step`, and the cracks they carried go with them. Nothing blocks stage 0.
**Stage 1 needs one fix first** (P2-M6: "defer closes with a flag" depends on
`queue.flag`, which is stage 5). Four new high findings (P2-H1 to P2-H4)
must be settled before stages 3 and 4 are built.

## Pass-1 findings: closed or open

| Finding | Status | Note |
|---|---|---|
| C1 | **Closed in principle; the example data is wrong** | `blueprint.reserve` has no `ok` field. A conflict returns `refused: true` with `blocked_reason` (`df-overseer-blueprint.lua:1525-1535`), and a stranded footprint only sets `would_strand` and still reserves (`:1536-1540`). A declared `verdict: {ok: ok}` sees no verdict. See P2-H1. |
| C2 | Closed | Marker and tick before the call, and nothing after it needs DFHack (4.2). Residual in P2-M2. |
| C3 | Closed for sequencing | A synthetic target per step and one completion rule make `step_prerequisites_satisfied` (`store.py:1032-1057`) and `step_status` agree. Its new "done" input has its own problem, P2-H2. |
| H1, M4, M9 | Closed | `open`, `confirm` and `from_step` are gone. |
| H2 | Closed | Canonical `dry_run` refused, set after merge, echo required. |
| H3 | **Open until stage 5** | A defer closes and flags the proposer, but `queue.flag` lands in stage 5 while the defer change is stage 1. See P2-M6. |
| H4 | Closed | Tripwires now need an explicit `pause.verdict`; owners are woken. New questions in P2-M5. |
| H5 | Closed | Per-tool removal plus a mapping test. |
| H6 | Closed | The 300 s timeout moves to stage 6. |
| H7 | **Partly** | The cutover id and the project-first abandon work against `store.py:754-768`. New problem in P2-H4. |
| M1 | Partly | Arms on done. Covered follow-ups' own predictions never arm (P2-M3), and done comes too early for non-dig phases (P2-H2). |
| M2 | Closed in principle; data wrong | `designated` is a table (`dig_tiles`, `zones`, `buildings`, `df-overseer-blueprint.lua:988`), so `nothing_applied: {field: designated, equals: 0}` never holds and every not-ok call becomes Uncertain. Fail-safe, but fix the path. |
| M3 | **Closed for digs only** | See P2-H2. |
| M5 | Mostly gone | `replaces_step` brings a variant back, P2-M4. |
| M6 | Closed, one gap | P2-M1. |
| M7 | Closed, to measure | Stage 0 `--hostname`; see P2-L2. |
| M8, M10 | Closed | |
| M11 | **Open as worded** | P2-H3. |
| L1, L2, L5 | Closed | L3 deferred with a sound reason; L4 is the orchestrator's. |

## New findings

### P2-H1. A missing verdict field must refuse, and the reserve example has none (high)

The design says `ok: false` or `blocked: true` refuses (2.2 item 3), but not
what a result with neither means. `blueprint.reserve`'s conflict result has
neither (`refused: true` instead, `df-overseer-blueprint.lua:1525-1535`). With
the declared map, a conflicting reserve passes filing, and at execution its
real call "succeeds" with no handle issued. **Fix:** a declared verdict field
that is absent is a refusal (fail closed). The reserve entry declares
`refused`, and treats `would_strand` as a refusal too, since a stranded
reservation can only feed a dig the access gate will block. Add a build-time
test that every routed tool's declared verdict, echo and handle fields appear
in a recorded real output.

### P2-H2. `progress` is per tool, but done differs per phase (high)

`blueprint.apply` has one `progress` entry: done at `dig.state:
none_pending`. `dig_progress` counts only `flags.dig`
(`df-overseer-blueprint.lua:835-866`, the test at `:844`), not smoothing, and
a build, zone or meta phase makes no dig designations at all. So:

- a **finish** (smooth) phase reads `none_pending` as soon as it is applied,
  before DF has made jobs (the file's own note: jobs appear lazily);
- a **furnish** phase reads done before the bed exists;
- the next phase's dry run is then blocked by the shell check, which does
  count smoothing (`:521`). Its prerequisite already reads done, so the step
  is "blocked with no moving prerequisite": **Needs judgment on every room**;
- a phased room's prediction arms at the last phase's designation, not its
  completion, which undoes M1 for the case M1 was about.

`state: unknown` (read failures or a job census error, `:862`) matches none
of done, moving or stalled, so a step can stay issued forever with no flag.
**Fix:** key `progress` by tool and phase `mode` (from `blueprint.plan`'s
`phases[].mode`, `:1006-1025`). Dig mode is done on `shell_done` plus no
pending smoothing; build, place and zone modes are done on the built items
and zone existing (the `shell`/`surface` fields `site_status` already
returns, `:1360-1395`). Repeated `unknown` flags the proposer after N reads.

### P2-H3. Stages 2 and 3 together leave rooms with no route (high)

Stage 3 routes only work-order tools. After its cutover, 3.5 refuses
accepting a proposal with no `step` "when its type has action tools", and
2.2 item 1 accepts a `step` for any tool listed in `action_tools.yaml`. If
the table lists room tools at stage 2, an Architect room proposal does one
of two things. It carries a `step` the executor cannot run, and the Overseer,
still holding the tool, runs it by hand (the mixed case 9.2 says cannot
happen). Or it carries none and cannot be accepted. Either way rooms stall
from stage 3 to stage 4. **Fix:** both rules apply only to **routed** types
(types whose tools have left the Overseer). Until a type is routed, a `step`
is refused for it and step-less proposals stay valid. With that, shipping
stages 2 and 3 together is safe.

### P2-H4. The migration fills the WIP cap for a week (high)

9.1 writes 9 projects, of which 7 read done. 5.4 closes a done project only
when its proposer passes, or when `follow_up_window_ticks` (start: 7 game
days) runs out. 3.5 refuses accepts while 3 projects are open. Once the
stage 4 WIP cap lands, the 7 legacy projects count as open and every
non-`high` accept is refused until the window runs out. If any of the 7 has
only failure records, section 7's success-only rule for implicit steps keeps
it active indefinitely. **Fix:** the same operator script closes the 7 (an
abandon or close with reason "pre-executor history"), and the WIP count
excludes rulings at or below the cutover id.

### P2-M1. A begun run that never ends caps the next one (medium)

`run.begin`/`run.end` counts per role (3.4). A conductor crash, an OOM, or a
manual `--once` interrupted between the two leaves the role's count open.
The next run then inherits a spent budget, including a manual run that is
supposed to have no cap. The exempt list also misses `queue.pass` (the
follow-up wake's close verb, 5.1), `queue.abandon` and `queue.flag_close`.
**Fix:** `run.begin` carries an expiry (role timeout plus grace) and replaces
any open run; exempt every verb that ends a turn's business.

### P2-M2. Uncertain is terminal for tools with no progress read (medium)

4.3 reconciles Uncertain through `queue.observe`, but only tools with a
`progress` entry have a read. For `orders.create`, `workjob.queue` and
`farm.set-crop` (all of stage 3), nothing proves whether a call landed. Every
timeout therefore ends held and flagged, and the proposer's only moves are a
re-file that risks a duplicate, or a close. With a 10 s RPC timeout against
the design's own 45 to 80 s figure, that could be most stage 3 runs.
**Fix:** a declared `landed` read per tool (for orders: `orders.list` matched
on exact job, amount and material, with the matching count before the call
stored in the `step_runs` row). Measure real-call latency in stage 0, before
stage 3's live check depends on it.

### P2-M3. Follow-up rulings and covered proposals do not map to the parent project (medium)

The store finds a project by `from_ruling` (`store.py:282-294`) and refuses
`executed` for an accepted ruling with no project (`store.py:577-618`). An
ordinary follow-up is accepted by its own ruling, which has no project:

- the execute phase's "open projects for accepted post-cutover rulings"
  (4.5) would open a second, separate project for it unless `open_project`
  refuses proposals that carry `project_id`;
- its `executed` must cite the parent's ruling to pass the store, so
  `unexecuted_accepted_proposals` (`store.py:1374-1405`) lists the
  follow-up's own ruling as unexecuted forever;
- a covered follow-up has no ruling at all, so its own prediction is never
  armed or graded, which hides the proposer's per-phase hit rate.

**Fix:** state the mapping. `open_project` refuses follow-ups; `executed`
carries the step's proposal id; the unexecuted report and prediction arming
key on the step's `proposal_id` (which section 7 already adds to each step).

### P2-M4. `replaces_step` breaks dependents and can strand a live action (medium)

Dropping step S while a later step `requires: [S]` leaves a dangling edge,
which `_validate_step` refuses (`schema.py:1008-1021`). The design's "no
earlier step changes" argument for the fresh-id rule (4.1) holds for
`apply_followup`, not here. Replacing an issued or Uncertain step also drops
the only plan entry recording that a designation may still be live in the
game. **Fix:** allow `replaces_step` only for a step with no dependents and
no `issued` or `issuing` run; otherwise the move is a recovery follow-up
(release first).

### P2-M5. Covered follow-ups do not pin their order; tripwires can loop (medium)

Covered checks the tool, the carried arguments, the next phase and an issued
handle (5.2), but not `after_step`. A proposer can attach the finish phase to
the reserve step instead of the dig step, so it runs while the dig is still
going. `finish` is dig mode, which the order guard does not cover
(`NEEDS_DUG_SHELL` is build, place and zone only,
`df-overseer-blueprint.lua:165`). Nothing else in a covered follow-up can
exceed the accepted plan. With `after_step` pinned, the answer to "can one be
crafted to do something the Overseer never accepted" is no. **Fix:** a covered
follow-up's `after_step` must be the step that applied the previous declared
phase, and that step must be done.

Separately, on tripwires (4.6): if the cause persists (thirst still critical
after a resume verdict), the watcher re-latches, and each cycle runs an
advisor and the Overseer again. Whether the in-game watcher has any
hysteresis was not checked this pass. **Fix:** a per-cause episode counter
that escalates on the second episode within N ticks.

### P2-M6. Stage 1 depends on a stage 5 tool (medium; blocks stage 1 as written)

Stage 1 ships "defer closes with a flag (H3)", but `queue.flag`, its record
kinds and its wake are stage 5 (9.2). Built as listed, a stage 1 defer either
cannot be written or closes silently, whereas today a deferred proposal at
least stays visible. Deploying the new `pending_proposals` rule also silently
closes every live deferred proposal. **Fix:** move "defer closes" to stage 5,
or ship a minimal flag in stage 1 (the record plus an owner briefing line, no
wake). Record the live deferred proposals before the deploy.

### P2-L1. Amends are whole plans with no base check (low)

`_current_steps_and_version` reads the latest amend as the full plan
(`store.py:348-361`), and append does not check that every previous step is
kept or named in `drops`/`replaces`. Two follow-ups built from the same base
would silently drop one step. The conductor applies them in sequence, so the
risk is small. **Fix:** `apply_followup` reads and appends under the one write
lock, and the store refuses an amend that omits a previous step not named in
`drops`/`replaces`.

### P2-L2. Fixed hostnames and openclaw's state (low)

All runs share one bind-mounted openclaw state directory, which holds a
device-identity lock file. Whether openclaw keys anything on the hostname was
not checked. Stage 0's live check should confirm that a second run with the
same `--hostname` still authenticates and is not refused by a lock.

### P2-L3. Resolution fields are coarse (low)

Near landmark, direction, distance and footprint (`reserve_site`'s
`site_brief`, `df-overseer-blueprint.lua:1516-1524`) can match for two
different sites, for example on different levels. **Fix:** add `orientation`
and the level the tools already take.

### P2-L4. The migration writes in the Overseer's name (low)

The 9 projects, 2 abandons and any rejects carry role `overseer` (9.1, open
question 1). The rejects count in the Overseer's accept-rate figures, and the
public Board shows the Overseer doing it. **Fix:** a `written_by: operator`
field that the Board and the rate figures read, or wait for the executor
role.

## Checked and sound in revision 2

- Apart from P2-M5's `after_step`, covered follow-ups cannot exceed the
  accepted plan: tool, carried arguments, next declared phase and an issued
  handle are all checked, and `blueprint.apply` refuses a reservation made
  for another template or already carved
  (`df-overseer-blueprint.lua:1161-1170`).
- `apply_followup` adds a step without changing earlier ones, so the fresh-id
  rule (`store.py:732-755`) holds.
- The `step_runs` order (preconditions, dry run, tick and marker, call,
  record) leaves nothing that needs DFHack after the real call.
- No rendered map, no armok power, no per-kind code: phases come from the
  template through `blueprint.plan`, and `resolution_fields` are
  coordinate-free.
- Stage 0 is safe. Stage 1 is safe alone once P2-M6 is resolved.
