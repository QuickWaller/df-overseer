# The agent loop (MVP)

How the fort runs unattended: what wakes an agent, what the game clock does
while one thinks, and who carries out a decision.

> **Status: design, 2026-09-22, and largely built since.** Written in a
> design conversation with the user, whose goal is "design the agent loop,
> fill in the gaps, let the fort run": an MVP that runs, to be improved
> from what it does. Each decision is marked **agreed** (the user's call)
> or **default** (the orchestrator's gap-fill, standing until the user
> overrides it). **UPDATE 2026-09-23: most of §4's build items are built
> and deployed to VM 103/106** (the in-game clock and tripwire script, the
> conductor dfmcp role, the conductor systemd service on VM 106, the
> Quartermaster enabled, local and web Consultant retrieval), but **the
> conductor has never run as a live service** -- only manually, in the
> foreground, with `--dry-run`. §3's tripwires now number five, not four
> (an announcement-level tripwire and a tier system replaced the flat
> hostile-reachable rule), and a live-caught bug in that tier system was
> found and fixed the same day it deployed (see §3 and
> `docs/TRAPS.md`, "A pcall-guarded read..."). See §7 for what changed
> and what is still open, checked item by item.
> Companion to `docs/AGENT-ARCHITECTURE.md`, which this narrows to a first
> buildable slice rather than replaces.

---

## 1. Shape

**Agreed, 2026-09-22:** the 2026-09-19 open question ("dispatcher plus queue,
or openclaw-native?") is answered **dispatcher plus queue**. A code
**conductor** wakes each role as an independent one-shot `agent exec` run with
fresh context; roles talk only through `dfqueue`. openclaw's Gateway, its
heartbeat and cron triggers, and `sessions_send`/`sessions_spawn` are not used.
Reasons: `research/2026-09-18-openclaw-capabilities.md` §3 (the queue is the
typed channel and the audit log, the native send lane is serialised, no
Gateway has ever run here), and every live run so far already works this way.

One cycle:

1. **Read.** The conductor reads vitals, the diff since each role last woke,
   and the queue.
2. **Grade.** Predictions now due are graded by code (`dfqueue/grade.py`).
3. **Triage.** Code rules decide who, if anyone, to wake, and set the clock
   policy for the cycle (§2). A quiet cycle wakes nobody and costs nothing.
4. **Advise.** Woken advisors propose or pass.
5. **Decide and act.** The Overseer, woken only if the queue holds something
   for it, rules and carries out what it accepted.
6. **Save** before any action on the fort (the existing quicksave rule,
   `docs/TRAPS.md`).

The fort keeps running between and during cycles, at the speed §2 sets.

## 2. The game clock

The fort runs at **100 FPS**, not the 5 several design docs assumed
(`docs/PURPOSE.md`, finding 2026-09-15), so a 60-second agent turn at full
speed is about 6,000 ticks, roughly five game days. That is what let
`proposal-0001`'s prediction window elapse before anything could act on it.

`docs/AGENT-ARCHITECTURE.md` §6 already chose **throttling, not pausing**,
as the ordinary way to buy thinking time ("a frequently frozen fortress is a
failure, not a safe default"), with game time per cycle about `f·T + k` ticks.
This section makes that concrete.

**Agreed, 2026-09-22: the clock speed while an agent thinks is set by why it
was woken, not by the fact that it is thinking.** Choosing where the next
workshop goes can take minutes at full speed with nothing lost; deciding what
to do about thirst nearing critical cannot.

Three levels, each a config value:

| Level | Setting | Starting value |
|---|---|---|
| Full speed | `base_fps` | 100 |
| Slowed | `think_fps` | 10 |
| Paused | n/a | fort stopped |

**Agreed: `base_fps` is a setting, not a constant.** The user may lower full
speed later if the fort moves too fast to watch or to steer (at 100 a game
year is about 1.1 real hours; at 20, about 5.6). Every rule below is written
in **ticks**, so it holds whatever `base_fps` is set to.

**Policy per wake reason** (fallback table, held as data, not code branches):

| Wake reason | Clock while thinking |
|---|---|
| Routine review (every N game days), prediction graded, season change, migrant wave | full speed |
| Learning, court, doctrine, chronicle (later roles) | full speed, always |
| Stuck job, stock below target | full speed, unless closing in (below) |
| Vital nearing its threshold, caravan present, hostile seen but not yet able to reach the fort | slowed |
| Tripwire: a death, a critical vital, a hostile that can reach the fort | paused |

**Closing in, computed where code can** (agreed direction): slow the fort
only when the ticks until a consequence are fewer than a few multiples of the
expected thinking time, measured in ticks at the current `base_fps`. Code
already derives the inputs (thirst and hunger against their critical values,
food and drink cover days, a caravan's departure). The table is the fallback
for wake reasons with no computable deadline. The multiple is a config value.

**The most urgent live reason wins.** If a reason that slows the fort arrives
during a full-speed cycle, the conductor slows it then, and restores
`base_fps` once nothing urgent is being deliberated.

**Starting and stopping the fort belong to code, never to a model.** The
Overseer's charter line "never unpause without being asked to" is unchanged.

**The frame cap does not survive a game process restart**
(`docs/AGENT-ARCHITECTURE.md` §6), so the conductor re-asserts it.

## 3. Safety: tripwires inside the game

**Default.** Tripwires run **inside the game loop**, in a DFHack script
registered the way `overseer-autosave` is, not over SSH: on 2026-09-19 a
wedged command pipe took the remote watchdog's own pause call with it
(`docs/TRAPS.md`). On a tripwire the script pauses the fort and records why;
the conductor sees the pause and wakes the Overseer. So if the conductor or
openclaw dies, the fort keeps running at whatever speed it was set to and
still pauses itself on a death, a critical vital or a reachable hostile.

Tripwires, v1 as designed: a citizen death; hunger or thirst past a
critical threshold; a hostile `threat.scan` admits (reachability, not the
danger flag); a new announcement of an alert class. **Built and deployed
2026-09-22 (`handoffs/2026-09-22-loop-clock-conductor-role.md`,
`evals/live/2026-09-22-loop-mvp-deploy/`): the first three.**

**Built and deployed 2026-09-23, a fifth tripwire replaces the flat
hostile-reachable rule** (`handoffs/2026-09-23-attention-tiers-ingame.md`,
`evals/live/2026-09-23-attention-deploy/`): a candidate `threat.scan` admits
now carries a `tier` (`pause`/`slow`/`record_only`,
`research/2026-09-23-wildlife-threat-classes.md`), and only `pause` latches
the clock; `slow` sets FPS to `think_fps` and writes a non-blocking
advisory instead; `record_only` only feeds the new observation ledger. A
separate, fifth mechanism pauses on a newly-arrived announcement whose type
is one of 25 generated `PAUSE_REPORT_IDS`
(`research/2026-09-23-announcement-severity.md`), independent of the threat
scan. **Live-caught bug in the same deploy, fixed and re-verified same
day** (`handoffs/2026-09-23-creature-tag-fields-fix.md`,
`docs/TRAPS.md` "A pcall-guarded read..."): the six creature-tag reads that
feed `tier` classification were all at the wrong struct level and
partly misspelled, silently returning `false` for every read. The `pause`
boundary happened to stay correct by luck (a kea's real tags are not the
ones gating `pause`); the `slow` boundary could never have fired for the
theft case it was built for, until the fix. Fixed and live-verified against
the same live kea the same day. Still owed: a live check that a
deliberately broken field name actually surfaces in the new
`read_failures` array (only a failing read can prove the guard fires, and
none has failed live yet).

Defaults hunger 75,000 and thirst 50,000 ticks, from DFHack's
`full-heal.lua` (`research/2026-09-16-food-clock-and-farm-lead-time.md`).
`fort.quicksave` fires and reports `cur_savegame.save_dir` ("DF's own record
of the save") as it stood beforehand, with a separate confirm call, never a
predicted slot and never a file mtime -- fixed twice, live, 2026-09-22
(`handoffs/2026-09-22-loop-diff-reregister-quicksave-slot.md`): a live
prediction miss, then a live finding that `dfhack.filesystem.mtime` itself
is broken on this install. Waiting inside Lua would hold the suspend lock
the save itself needs. **Not covered: flooding**, since the breach
detector is inconclusive (`ROADMAP.md`).

**The tripwire's own live tests remain unrun** (true positive and true
negative both, `docs/AGENT-LOOP.md`'s own owed list below): the first and
only real trip so far was `hostile_reachable` on a kea, 900 ticks into the
first unattended run, against the PRE-fix tier code
(`evals/live/2026-09-23-office-and-first-real-build/`); no tripwire has yet
fired against the corrected code.

**The `slow` tier clears, as a rule, not just an implementation note**
(`handoffs/2026-09-23-slow-tier-clearing.md`). `pause` and `record_only`
each have a natural way back (a human/conductor clears and resumes; a
`record_only` candidate simply never latches anything). `slow` did not:
until this fix, nothing in `df-overseer-clock.lua` ever restored FPS or
emptied the advisory except a fresh `arm`. The bug was found live, not in
design: the Chair completion run's kea (`theft_tag_close_range`) tripped
`slow` once and then stayed latched, unchanging, across all three windows
of that run, right through to the final paused read
(`evals/live/2026-09-23-chair-completion-run/README.md`) -- every
unattended run from there would have ended throttled, with the conductor's
triage reading a stale reason to be careful long after the threat had
gone.

The rule, now built:

1. **What the fort restores to.** `base_fps` is a new, explicit `clock.arm`
   argument (default 100, the same "Full speed" starting value from the
   table above), captured once at arm time and persisted to its own state
   file, never inferred from whatever FPS happened to be in effect at the
   moment of a drop -- a fort already slowed for an unrelated reason must
   not have that incidental value adopted as its new "normal". `clock.status`
   now exposes `base_fps` so the restore target is always visible.
2. **What counts as cleared.** `find_threats` sorts its candidates by the
   worst tier present first, so the code's own `threats[1]` already
   reflects the worst tier anywhere in a scan's whole candidate list; no
   separate whole-list scan is needed. Clearing fires the moment a scan
   finds nothing at `slow` tier or worse: either the top candidate has
   downgraded to `record_only`, or there were no candidates at all
   (`#threats == 0`). Both are the same case.
3. **Cadence.** Clearing runs inside the exact same `threat_check_every_n`
   branch that sets the advisory, never a separate schedule -- setting and
   clearing always see the same scan.
4. **Sticky or immediate.** Immediate, no hysteresis. This mirrors how the
   `pause` tier already behaves (no debounce there either), and the coarse
   threat-scan cadence itself is the only smoothing either tier gets; giving
   `slow` a stricter debounce than `pause` would be an inconsistency, not a
   safety improvement.
5. **`clock.clear`'s contract.** `clear` now clears a latched slow-tier
   advisory too (restoring `base_fps`), not only the pause latch, since
   `clear` is this project's one "I have seen this, carry on" verb and
   leaving it unable to answer for the other kind of latch would be half a
   fix. Its return value now reports `had_latch` and `had_advisory`
   separately, so a caller can tell what was actually cleared.

**Owed, from this fix, offline-only** (`handoffs/2026-09-23-slow-tier-
clearing.md`): a live re-arm under the new argument, and a live clearing
event both ways -- naturally, by watching the same kea (or a fresh
candidate) recede out of `slow` range without any human action, and
explicitly, via a live `clock.clear` call while an advisory is latched. A
live check should confirm `clock.status`'s `advisory` field actually goes
back to nil and `fps` actually returns to `base_fps`, not just that the
fort no longer looks throttled.

## 4. Build items

All **default** unless marked.

| # | Piece | Where | Notes |
|---|---|---|---|
| 1 | In-game clock and tripwire script | VM 103 | Sets the frame cap on request; pauses on a tripwire and records the reason. **Built and deployed 2026-09-22/23**, live-verified |
| 2 | A `conductor` role in dfmcp | `dfmcp/` | New token held only by code, never by an agent: `clock.set-speed`, `pause`, `resume`, `status`, `arm`, `disarm`, `clear`, `fort.quicksave`, `vitals.summary` (**built and deployed 2026-09-22**, live-verified, `evals/live/2026-09-22-loop-mvp-deploy/`) |
| 3 | The conductor service | VM 106, systemd | Python. Runs the cycle, triage, the clock policy; launches `docker run --rm ... agent exec` as the 2026-09-16 run did; archives each run's JSON, tool calls and `costUsd` under `runtime/` for the public report. **Built and installed 2026-09-22** (`conductor.service` on VM 106, disabled/inactive, Docker socket access granted the same day). **Never run as a live service**: only a manual, foreground `--dry-run --once`, which completed cleanly from a real unseeded cursor after the encoding fix (`evals/live/2026-09-22-loop-game-text-encoding/`) |
| 4 | Queue: an execution record and a grading schedule | `dfqueue/` | `queue.executed` references the ruling and the call ids. **A prediction's window starts at execution, not at writing.** The grader runs every cycle |
| 5 | Enable the Quartermaster | `agents/` | Food, drink, work orders, farms and workjobs are where this fort actually needs decisions; the Architect covers only placement. Needs a proposal-type vocabulary (`dfqueue/schema.py` has only the Architect's three) and a real allowlist |
| 6 | Per-cycle briefing | conductor | Tier 0 figures only (vitals, cover days, stuck jobs, the role's diff, queue state), placed in the prompt. Nothing that grows with the fort |
| 7 | `ask` / `answer` and fact-check records | `dfqueue/` | Any advisor may ask the Consultant (register 2026-09-15); the Overseer may route a proposal for fact-checking (2026-09-17). One ask, one answer, no threads |
| 8 | Consultant retrieval, local | `dfmcp/`, VM 103 | **Agreed.** `knowledge.wiki_lookup` over a local wiki snapshot (register 2026-09-15: capped section excerpts, not the open web), and a read-only search-and-read tool over DFHack's own installed scripts, docs and Lua on VM 103 (exact to 53.16, which the wiki cannot promise) |
| 9 | Consultant retrieval, web (forums) | `dfmcp/` | **Agreed, user's call 2026-09-22: needed for the MVP.** Read-only search and fetch. Everything fetched is **untrusted data, never instructions**, and can support only a `prior`, never `verified`. **Search backend: Brave Search API** (user's call 2026-09-22; the user supplies the key). Runs inside dfmcp, so the per-role allowlist and the call log cover it. The Consultant is guided, not fenced, by `agents/consultant/sites.yaml`: the major DF sites, what each is for, and its version caveat |

**Roster, agreed 2026-09-22:** Overseer, Architect, **Quartermaster** and
**Consultant**. The Consultant is woken only when an `ask` or a fact-check is
open; within a cycle the order is advisors, then Consultant, then Overseer, and
a proposal sent for fact-checking is ruled on the next cycle.

**Triage rules, v1:** wake advisors on a vital crossing a threshold, a stuck
job, a prediction falling due or graded, a migrant or caravan event, or at
least every 7 game days; wake the Overseer only when the queue holds
something for it. All thresholds are config.

**Models:** DeepSeek for every role, as in every live run. No spend-cap work
(user's standing call); each run's `costUsd` is logged and summed per day.

**Alerts:** a status JSON and journald lines. Telegram and the public feed
later.

## 5. Deliberately left out of the MVP

Each can be added without changing the loop's shape: the full per-step
write-ahead log (a quicksave before acting plus the call journal stand in),
playbooks and Sentry reflexes, the Consultant inside the loop, `amend`, the
court and the learning role, the public feed.

**Known risk, accepted:** most write tools have never done a real build
(`Working.md`, "Where the MVP stands"). Early cycles will surface tool
failures. That is intended; it produces the evidence the confidence levels
and gotchas are for.

## 6. Objectives: a default flow with deviations (in design)

Every wake reason above is reactive; nothing yet says what the fort is trying
to achieve. **Agreed direction, 2026-09-22 (user):**

- **The Overseer keeps the agenda** and changes it through queue proposals,
  so every change is audited. How those proposals are ruled is open, pending
  the wider proposals design.
- **It starts preseeded** from forum and guide research, and grows and is
  polished over time. **The seed waits until this design settles.**
- **Two lifetimes** (orchestrator's suggestion, not yet confirmed): a
  **progression template** that survives across forts and is what gets
  polished, and a per-fort **agenda** instantiated from it, which dies with
  the fort.
- **An ordered graph with a default flow and deviations** (user's proposal):
  the site decides not only *what* to do but *when*. Nodes are objectives
  (`done_when`, prerequisites, `because`, sources); default-flow edges give
  the standard progression; **deviation rules** (`when` a site or state fact
  holds, insert, skip, move earlier or later, with `because` and sources)
  adapt it. "Fishing needs a river, lake or ocean" is a visible rule with its
  reason, whether or not it fired.
- **Both code and the Overseer decide applicability** (user: "A and B"):
  code evaluates rules against a closed vocabulary of site and state facts,
  from a site-profile read tool, reporting `unknown` rather than guessing;
  the Overseer may deviate where no rule foresaw it, recorded as a
  **variance** with its reason and evidence.
- **Viewable logic:** every objective carries its history (what changed, who
  proposed it, the ruling, the evidence), returned by `agenda.get(id)`.
- **Prompt size:** a prompt shows the top few open objectives in full plus a
  one-line index of the rest; never the whole graph.

Prior art being read before the schema is fixed: clinical pathways with
variance tracking, and RTS build orders adapting to scouting
(`research/2026-09-22-objective-graph-prior-art.md`, dispatched).

## 7. Open

**Closed since the 2026-09-22 list below was written, checked one by one
2026-09-23:**

- **The announcement tripwire (§3)** is built and deployed
  (`handoffs/2026-09-23-attention-tiers-ingame.md`).
- **A wiki snapshot** exists and is deployed (referenced throughout
  `evals/live/2026-09-22-loop-mvp-deploy/`, "30-page wiki snapshot at
  `/var/lib/dfwiki/`", `Working.md`).
- **The VM 103 DFHack source path check** and **the Brave key into VM 103's
  service environment** are both done; `dfhack.source_search`/`source_read`
  and `web.search`/`web.fetch` all ran live in the 2026-09-22 MVP deploy
  (`evals/live/2026-09-22-loop-mvp-deploy/README.md`, "Live checks").
- **`order."ID".exists`'s assumption is still genuinely open**, not
  answered: no order on this fort has ever gone `active`, let alone
  finished, so whether DF removes a completed order from its list remains
  untested as of the first unattended run (`evals/live/2026-09-23-office-
  and-first-real-build/`, "orders watched"). Left in this list rather than
  moved to closed.
- **One new answer, not previously listed here: `job.order_id` links a
  spawned job back to the order that made it**, contradicting an earlier
  research claim that no such link existed
  (`handoffs/2026-09-23-order-job-attribution-and-checks.md`, live-
  introspected on VM 103, DFHack's own `do-job-now.lua:106` matches on it).
  `orders.list` now carries `validated`/`active`/`finished_year`/
  `frequency`/`max_workshops`, deployed and live-verified 2026-09-23
  (`evals/live/2026-09-23-order-job-attribution/`); the populated
  `order_id`/`from_order` field shape on a real order-spawned job is still
  unverified, since no order on this fort has ever spawned one.

**Still open, from the 2026-09-22 build streams (all merged and deployed
now, but the underlying gaps are unresolved):**

- **A failed execution still starts the grading window**, so a later miss
  cannot yet tell "the proposal was wrong" from "carrying it out failed".
  Needed before any role's hit rate is trusted; it is also the attribution
  split `docs/PRODUCTION-MODEL.md` §3 describes.
- **Only the first execution arms the window.** Manager orders on this fort
  have queued without ever running, so a `work_order` window may start long
  before its effect can land.
- **Deploy trap:** the queue migration keeps old rows on their write-time
  deadlines. On VM 103 that includes `proposal-0001`, voided during the
  2026-09-22 deploy rather than graded (register 2026-09-16, grading it
  would record a latency miss, not a verdict).

**New, from the 2026-09-23 streams:**

- **The stalled/blocked order poller's thresholds are reasoned, not
  measured** (`conductor/order_watch.py`, 1200 ticks;
  `handoffs/2026-09-23-stalled-order-poller.md`). No order has ever gone
  active on this fort, so there is no real timing data yet to check the
  threshold against.
- **The placeholder distance and decay numbers in the observation ledger
  and the threat tier classifier are reasoned defaults, not measured**
  (`research/2026-09-23-wildlife-threat-classes.md` notes no tick-timing
  data exists for how fast a threat develops; the pause tier deliberately
  does not depend on one).
- **The unproven failed-read reporting**: `class_flags`'s new
  `read_failures` array has never actually been observed non-empty live
  (see `docs/TRAPS.md`, "A pcall-guarded read..."). It is proven correct by
  the fix that populated it, not yet proven to fire on a genuine failure.
- **The office-and-first-build question is open, not answered**: two real
  Office zones exist (one owned by the Manager), both outdoors, and 900
  ticks was not enough to tell "needs more time" from "needs more room
  value" for `required_office: 1` (`evals/live/2026-09-23-office-and-
  first-real-build/`). The next unattended window is the way to settle it,
  pending a decision on whether harmless wildlife should keep tripping
  `hostile_reachable` at long range (now softened by the tier system above,
  but the first trip was against the pre-fix code).
- **Whether harmless wildlife should stop an unattended run at long range
  at all** is a design decision for the user, not resolved by the tier
  system alone: the tier system changes what counts as `pause`-worthy, but
  a `pause`-tier candidate still stops the run exactly as before.

- Web retrieval (item 9): Brave's current pricing and limits are unchecked
  (the key itself is in place and working).
- The Quartermaster's proposal-type vocabulary (item 5): the Quartermaster
  role is enabled and has tools (`orders.*`, `workjob.*`,
  `ledger.read`), but no closed proposal-type vocabulary for it exists in
  `dfqueue/schema.py` yet.
- Where the conductor runs (VM 106, as installed; `conductor.service`
  exists there, disabled and inactive, and has never run as a live
  service, only a manual foreground `--dry-run`).
- Cycle wall-clock time, and so the right `think_fps`, is unmeasured
  (`docs/AGENT-ARCHITECTURE.md` §14 item 8). Instrument it from the first
  real (non-dry-run) run.

**2026-09-25 addition:** observability (every inter-agent message with
sender, recipient, type and a one-line rationale, joinable to its tool
calls) is now an agreed requirement, not yet built (`docs/AGENT-ARCHITECTURE.md`
§8, `ROADMAP.md` Later's agent activity feed). The loop above produces the
wake reasons and calls that feed would join; nothing in this document's
shape changes because of it.
