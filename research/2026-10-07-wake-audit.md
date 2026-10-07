# Wake audit: every reason that wakes an agent, what it led to, what to keep

Date: 2026-10-07. Read-only audit (code, the archived run envelopes on the
agent VM, the runs and queue databases on the fort VM). Nothing was run,
written or restarted on any VM.

Question (user, 2026-10-07): which wakes are needed, which are overkill, and
which should be warnings (a line in the briefing on the role's next natural
wake) instead of wakes.

## 1. Answer

The audit lists 33 rows (rows 1 to 26 live in code or policy, rows 27 to 33
designed or in flight; row 8 is a wake that does not exist and row 3 is not a
wake). By primary class: **14 WAKE (several narrowed to an edge or a single
owner), 7 WARNING, 1 LOG, 8 REMOVE, 3 MERGE** (table in section 3; the
table, not the tally, is the recommendation, since some rows are split).

The findings that matter most, in order of cost:

1. **Five different wakes can fire for one fact and each produces a
   proposal.** Between 2026-10-05 and 2026-10-06 the Quartermaster ran 9 times
   (`runs` rows 1, 3, 5, 6, 9, 11, 14, 18, 20), woken by `stalled_order` (x3),
   `prediction_graded` (x2), `stuck_job`, `alert_crossed` and `ruling_on_own`.
   Every run ended in a proposal or an ask, 9 of 9, and most are about
   one fact: drink is 0. The Overseer then rejected 6 of the Quartermaster's 13
   work orders ever (4 of them in this window, as duplicates or infeasible)
   and deferred one three times. A wake whose answer is always "file
   something" is the proposal-spam failure the charters warn about, produced
   by the wake design, not the model.
2. **`queue_pending` is a level trigger and a defer does not clear it.**
   `proposal-0017` (Architect) and `proposal-0020` (Quartermaster) were each
   deferred three times in three consecutive Overseer wakes with nothing
   changed (6 of the 15 rulings since 2026-10-05 were defers, 4 of them
   repeats of an earlier defer). The
   Overseer is the most expensive role per run (avg $0.059, 317 s, 5 to 14
   turns) and woke 6 times for $0.353, the single largest wake line.
3. **Four wake reasons can never fire.** `season_change`, `migrant_wave`,
   `caravan_present` and the `stock_below_threshold` lane event are mapped from
   diff events that no Lua file emits (grep of `scripts/dfhack/` finds none);
   `prediction_due` and `hostile_seen_unreachable` are hardcoded off in the
   cycle. The Quartermaster's whole `events:` lane is dead code. The
   Planner design already knows about two of these (F-3).
4. **Tick-based renotify is shorter than a cycle.** At 100 FPS one game day
   (1200 ticks) is 12 real seconds. `stalled_order_renotify_ticks: 1200` is
   12 s, `stuck_job_renotify_ticks` and `ore_renotify_ticks` (12000) are 120 s,
   the 7-day routine review is 84 s. Cycles are minutes apart, so each of
   these is, in practice, "every cycle while the fort runs". They are silent
   in the archive only because the fort sat paused under the operator hold and
   the tick was frozen at 12784828 for the last four cycles.
5. **An operator hold gates no wake.** `hold.held` is read at
   `conductor/cycle.py:152, 200, 563, 1256` and only gates the unexecuted
   carry-out, the execute phase and pause-resume. The ore wake and the drink
   alert wake both fired on 2026-10-06 with `held_by_operator: true`. The
   unsupplied-building handoff says "suppressed under an operator hold like
   the other watches if they are": they are not, and it should not assume so.
6. **A role can be woken for what it cannot do.** The Architect's ore wake
   (run 17, $0.022, 4 turns, a `queue.pass`) was a 61-second pass because
   `construction.mine-vein-site` is not routable (handoff
   `route-ore-mining`), and with `ore_renotify_ticks` it re-wakes every 10 game
   days until that lands. The pre-lane `stuck_job` wake sent the Quartermaster
   at suspended `Construct building` jobs (run 9). The conductor has no
   check that a wake's owner holds a tool that can answer it.
7. **The warning mechanism half exists.** Every briefing already carries
   standing `alerts`, `stuck_jobs`, `ore_exposed` (role-filtered) and diff
   events (`conductor/briefing.py:130-160`), but these are only seen on a wake
   for another reason, are unfiltered by role (an Architect is shown the
   drink alert), have no expiry, and the wake reasons that explain *why*
   a role ran are collapsed to the first one (see 3 below). A small generic
   extension turns it into the warning channel (section 5).
8. **The record is lossy.** `wake_for()` (`conductor/triage.py:100-107`)
   returns only the first Wake naming a role; the briefing, the archive and
   the `runs` table (`wake_reason`, `wake_detail`) keep that one. A role woken
   for three reasons shows as one. This audit could therefore count only first
   reasons (the observability gap the user already wants closed).

## 2. Evidence base and its limits

- **Runs DB** (`Uniboslan.runs.sqlite3`): 21 runs, 2026-10-05 05:23 to
  2026-10-06 22:29, with wake reason, duration, cost. Joined to the queue DB
  (`Uniboslan.sqlite3`, 86 records) by role and the run's time window to get
  what each run wrote (proposal, pass, ask, answer, ruling, executed).
  Confidence high for 10-05 onward.
- **Archived envelopes** on the agent VM: 17 cycle directories (2026-09-25
  to 2026-10-06), including 4 failed or timed-out runs and 7 pre-DB cycles.
  Pre-10-05 cycles give wake reason and cost but no turn count or exact
  outcome join (the `runs` table did not exist; time windows are fuzzy).
  Turns are recorded only from 2026-10-05 08:29.
- **Journal** for `conductor-once-*`: 73 lines, start and exit only. The
  conductor logs nothing at INFO to the journal for these transient units, so
  the journal gave no wake counts. (Not a finding about the code; it is how
  the transient runs were launched.)
- **Volume is small.** 21 DB runs, 11 real cycles, about 1.7 days of
  wall time (DB window) of mostly paused fort. $1.075 and 116 minutes of agent wall clock
  across the 21 runs. Per-wake dollar cost is small ($0.02 to $0.10, mean
  $0.051) so the case for trimming is wall clock, rounds and proposal churn,
  not spend (consistent with `research/2026-10-07-cross-run-cache.md`:
  every avoided round is the saving).
- **Rates are not rates.** The archive is hand-run cycles under an operator
  hold, not the service cadence. "Fired N times" below means "in the archive",
  not "per day". Any wake whose key is game ticks is frozen while paused.
- **Never observed live:** tripwire, unexplained_pause, slow_announcement,
  vital_nearing_threshold, blocked_order, step_done, step_attention,
  project_idle (execute phase was skipped, "operator hold", in every cycle
  summary that carries it), lane_event (cannot tell, only first reason is
  kept). These are classified from code and design only.

Per-reason live ledger (first-listed wake reason per role run; wake to
outcome):

| Reason (role) | Runs | Total $ | Mean $ | Mean wall s | What it led to |
|---|---|---|---|---|---|
| queue_pending (Overseer) | 6 | 0.353 | 0.059 | 317 | 13 rulings, 6 executed; 6 of the 15 rulings in the window were defers, 4 repeats |
| prediction_graded (Architect, QM) | 6 | 0.292 | 0.049 | 372 | 3 proposals, 2 asks, 2 architect timeouts (607 s) with no output |
| stalled_order (QM) | 3 | 0.135 | 0.045 | 373 | 3 work orders, same three orders each time, 2 rejected as duplicate or infeasible |
| ruling_on_own (QM) | 1 | 0.102 | 0.102 | 584 | 1 more work order (14 turns, the costliest advisor run) |
| alert_crossed (QM) | 1 | 0.055 | 0.055 | 266 | 1 work order, accepted |
| routine_review (Architect) | 1 (+4 pre-DB) | 0.047 | 0.047 | 361 | 1 room_siting, then deferred 3 times for lack of beds |
| open_ask (Consultant) | 1 (+3 pre-DB) | 0.042 | 0.042 | 295 | 2 answers |
| stuck_job (QM, pre-lane) | 1 | 0.027 | 0.027 | 178 | 1 work order about a stall it could not fix |
| ore_exposed (Architect) | 1 | 0.022 | 0.022 | 61 | `queue.pass`, nothing done (no routed tool) |

Prediction misses: 5 predictions graded false in the queue DB, 3 true, 3
void or pending. Both advisors woke on each miss. On 2026-09-27 (a
Quartermaster drink miss) and 2026-10-02 (an Architect stuck-jobs miss) the
non-proposing advisor ran for $0.024 and $0.028 to no effect. The lane
change of 2026-10-05 narrowed it to misses only, but not to the proposer
(`conductor/policy.yaml:110`, `lanes.py` docstring: "queue.grade omits the
proposer").

## 3. Inventory and classification

Class key: **WAKE** needs a turn now; **WARNING** briefing line on the next
natural wake; **LOG** operator or Board only; **REMOVE** dead or net-negative;
**MERGE** fold into another row. E = edge, L = level. "Hold" = behaviour under
the operator hold. Line refs are to the repo as of 2026-10-07 (HEAD 3cf941c).

### 3.1 Safety and pause paths

| # | Reason | Wakes | Trigger, E/L, repeat | Hold | Live | Class | Where |
|---|---|---|---|---|---|---|---|
| 1 | `tripwire` (death, hunger_critical, thirst_critical, hostile_reachable, announcement) | owner role(s) then Overseer (`tripwire_owners`) | in-game latch (E, one episode per (reason, tick)); sequence re-runs only while latch stands; same cause > 3 times in 4800 ticks goes to the human | not gated; hold only blocks resume | none in archive | **WAKE** (keep) | policy.yaml:200,217,227; cycle.py:1002; tripwire.py |
| 2 | `unexplained_pause` | Overseer | pause no tripwire explains and not harmless (E: `overseer_woken` set once per episode, pause_watch.py:287); plain pause past 600 s grace | ORDINARY_HELD under hold: no wake | none | **WAKE** (keep) | policy.yaml:207; pause_watch.py:261-298,546 |
| 3 | pause liveness alert, tripwire repeat brake, frozen-fort alert | human | CRITICAL log line (`_alert`, `_human_alert`) | n/a | n/a | **LOG** (keep; Telegram later) | pause_watch.py `_alert`; cycle.py `_human_alert` |
| 4 | `slow_announcement` | roles named in each event's own `wake` list (data in severity YAML) | `announcement_slow` diff event from Lua (emitted, `df-overseer-diff.lua:369`), dedup by (type, tick); L-ish: one wake per drain | not gated | none seen | **WARNING** for entries with an empty or advisory list; **WAKE** only where the severity data says so. Default new entries to warning | policy.yaml:185; cycle.py `_classify_slow_announcements`; triage.py:252 |

Event types Lua does emit and what the conductor does with them:
`JOB_COMPLETED` (lane events only), `UNIT_DEATH`, `REPORT`, `UNIT_ATTACK`
(briefing diff lines only, **LOG/WARNING**, wake nobody, correct),
`announcement_slow` (row 4).

### 3.2 Queue, asks and execution

| # | Reason | Wakes | Trigger, E/L, repeat | Hold | Live | Class | Where |
|---|---|---|---|---|---|---|---|
| 5 | `queue_pending` | Overseer | **L**: `queue.overview.proposals.count > 0` every cycle; a `defer` leaves the proposal pending, so it re-wakes forever | wake not gated; carry-out part is | 6 runs, $0.353; 6 of 15 rulings defers, 4 repeats | **WAKE**, but change to edge: wake when a proposal is new, changed, or a defer's recheck window has elapsed; a deferred proposal alone is a WARNING | triage.py:265; cycle.py:742; dfqueue/store.py:1429 |
| 6 | accepted-not-carried-out (`to_carry_out`, folded into 5) | Overseer | `queue.grade.unexecuted` once the legacy cutover is set | gated: none under hold (cycle.py:152) | none (cutover not set until 2a) | **MERGE** into 5 (already is); keep, shrinks as groups route | cycle.py:132-170,742 |
| 7 | `open_ask` | Consultant | **L**: `asks.count > 0` every cycle; plus same-cycle re-wake after the advisors file one | not gated | 1 run + 3 pre-DB, 2 answers | **WAKE** (keep). L is fine: an ask has a single answer and closes | triage.py:273; cycle.py:775-800; policy.yaml:262 |
| 8 | answer to the asker | nobody | **no such wake exists in `conductor/`** (grep of policy, triage, lanes, cycle). The Planner design 5.1 table lists `answer` as "existing"; code says otherwise. The asker sees the answer only on its next wake for some other reason | n/a | n/a | **WARNING** (note to the asker: "ask-N answered: ..."), a wake only if its proposal is blocked on it | research/2026-10-07-planner-design.md:531 vs conductor/ |
| 9 | `ruling_on_own` | proposing advisor | **E**: once when its proposal leaves pending (accept or reject, not defer); line is only "proposal-N was ruled on", no verdict | not gated | 1 run, $0.102, 14 turns, 584 s, then one more work order | **WARNING** carrying the verdict and reason. Wake only if the role holds an open project step waiting (that is `step_done`) | lanes.py:225-233; policy.yaml:132 |
| 10 | `step_done` | project's proposer (fallback Architect) | **E**: once per step; text asks for the next step or a `queue.pass` | execute skipped under hold unless `--allow-execution` | none | **WAKE** while `phases_remaining > 0` (the project cannot advance without a follow-up); **no wake** when 0 left: conductor closes it | execute.py:215-230; policy.yaml:191 |
| 11 | `step_attention` | project's proposer | **E** per (step, cause), "same cause does not wake twice" | same | none | **WAKE** (keep): a blocked or failed step needs judgement | execute.py:200-210 |
| 12 | `project_idle` | project's proposer | one wake after `idle_wake_ticks` 8400, closes after 8400 more | same | none | **WARNING** (the auto close already covers the no-reply case) | execute.py; policy.yaml:197,executions |

### 3.3 Fort-state watches and alerts

| # | Reason | Wakes | Trigger, E/L, repeat | Hold | Live | Class | Where |
|---|---|---|---|---|---|---|---|
| 13 | `alert_crossed` (`drink_per_citizen`, `raw_food_per_citizen`) | Quartermaster (`alerts: ["*"]`) | **E** on clear to crossed; re-arms when it clears; failed read keeps state | not gated (fired under hold 10-06) | 1 run, accepted work order; alert has stood since | **WAKE** (keep). It is the survival signal. Make it the *only* wake for the drink fact (see overlaps). Standing line stays in the owner's briefing only | lanes.py:163-182; policy.yaml:273 |
| 14 | `stalled_order` / `blocked_order` | Quartermaster | **L with a fast renotify**: held >= 1200 ticks, renotify 1200 ticks (12 s real). Fires every cycle while the fort runs. Frozen while paused | not gated, tick frozen | 3 runs in one day, the same orders 0,1,2 each time; ids 0-2 still stalled on 10-06 | **MERGE** the two into one `order_attention`; **WAKE once** per order id per stall episode, then **WARNING** (standing briefing line); renotify with doubling backoff capped at one season | order_watch.py:126-185; policy.yaml:62-63,162,170 |
| 15 | `stuck_job` (job_watch) | role whose lane regex matches (Architect dig/construct, QM production) | **L with renotify** 12000 ticks (120 s real); threshold 2400 ticks; per-job first-seen clock | not gated | 1 run (pre-lane misroute); `job_watch.json` shows Bed and Wall re-notified at the frozen tick | **WARNING** by default (stuck lines are already in every briefing). **WAKE** only for an unclaimed dig job (Architect can act) or a job stuck > 1 season. A **suspended** `Construct building` waiting on an item is the supply problem: drop it from the Architect lane, let the unsupplied-building watch own it | job_watch.py:158-215; lanes.py:147-160; policy.yaml:74-76,137,310-326 |
| 16 | `ore_exposed` | Architect | **E** per (site, material); re-arms when mined; **renotify 12000 ticks while still exposed** | not gated (fired under hold 10-06) | 1 run, $0.022, pass; no tool to act | **WARNING** until `construction.mine-vein-site` is routable; then **WAKE** edge-once with doubling backoff | ore_watch.py; lanes.py:185-213; policy.yaml:85,126 |
| 17 | `vital_nearing_threshold` (hungry or thirsty) | Quartermaster | **L, no edge, no backoff**: `worst_hunger/thirst_status` in (hungry, thirsty) every cycle; also slows the clock | not gated | never (all archived vitals "fine") | **MERGE** into threshold alerts (drink and raw-food per citizen already carry it); keep the clock-slowing effect, drop the wake | cycle.py:720 and `_vital_nearing`; triage.py:162-212; policy.yaml:145 |
| 18 | `lane_event` (Architect `JOB_COMPLETED` dig, channel, carve, smooth, engrave, construct, build, detail) | Architect | diff event in its own drain; regex is case-insensitive, so "Dig" and "Smooth wall" match; one wake per drain with any match | not gated | drains show 5 to 10 Dig completions per cycle while the fort runs | **REMOVE** for rooms (routed projects raise `step_done`, which says the same with more facts) | lanes.py:128-144; policy.yaml:310-322 |
| 19 | `lane_event` (Quartermaster `stock_below_threshold`) | Quartermaster | **event never emitted** | n/a | cannot fire | **REMOVE** (alerts replaced it) | policy.yaml:323-326; cycle.py:97 |

### 3.4 Timers and graded predictions

| # | Reason | Wakes | Trigger, E/L, repeat | Hold | Live | Class | Where |
|---|---|---|---|---|---|---|---|
| 20 | `routine_review` | Architect and Quartermaster, both | timer, 7 game days (84 s at 100 FPS); cursor advances only on an ok run | tick frozen under hold | 1 run + 4 pre-DB; the proposal it produced was deferred 3 times | **REMOVE** for the Architect now (design agrees; shortfall, ore and step wakes say when there is work); Quartermaster: keep as a **season-length** backstop (`routine_review_interval_game_days` 7 to 84) until the unsupplied and input lines have run | triage.py:214; cycle.py:741,877,1335; policy.yaml:36,104 |
| 21 | `prediction_graded` (a MISS) | both advisors | event from `queue.grade` each cycle a miss lands; hits wake nobody | not gated | 6 runs, $0.292; 2 non-proposer runs wasted | **WAKE the proposer only**, and only if it has no pending proposal on that signal; otherwise **WARNING**. Needs the proposer on the grade record (data, cheap) | cycle.py:657-665; triage.py:181; policy.yaml:110 |
| 22 | `prediction_due` | both | `Signals.prediction_due` hardcoded False (folded into graded) | n/a | cannot fire | **REMOVE** | cycle.py:731; triage.py:175; policy.yaml:107 |
| 23 | `season_change` | Quartermaster | event never emitted | n/a | cannot fire | **REMOVE** the event path; **WAKE** once per season if recomputed from the tick (Planner design F-3, crop planning is real work) | cycle.py:97; policy.yaml:115 |
| 24 | `migrant_wave` | both | event never emitted | n/a | cannot fire | **REMOVE**. Per-citizen alerts (bedrooms, drink) absorb population growth, as the design says | cycle.py:97; policy.yaml:119 |
| 25 | `caravan_present` | Quartermaster | event never emitted | n/a | cannot fire | **REMOVE** (no trading lane exists) | cycle.py:97; policy.yaml:149 |
| 26 | `hostile_seen_unreachable` | nobody (clock only) | hardcoded False, "gap 2" | n/a | cannot fire | **REMOVE** the stub, or implement as **WARNING** | cycle.py:729; policy.yaml:152 |

### 3.5 In flight and designed

| # | Reason | Wakes | Design, E/L, repeat | Class and note |
|---|---|---|---|---|
| 27 | P0 `bedrooms_per_citizen` alert (handoff `p0-bedroom-alert`) | Architect | **E**, a threshold alert, re-arms on clear; `missing` default when the key is absent | **WAKE once**, with a cap. It is true now (1 bed for 22) and will stay true for days, so the one wake must not re-fire; and it duplicates `plan_shortfall` for bedrooms when P1 lands. Sequence matters: the Overseer deferred bedroom proposals 3 times for lack of beds, so the unsupplied watch (28) should land first or the wake only produces another deferral. **MERGE** into `plan_shortfall` at P1 |
| 28 | `unsupplied_building` (handoff `unsupplied-building-watch`) | Quartermaster | **E** per item kind, one line per kind, standing-order preferred response | **WAKE** (best-evidenced new wake: the stuck bed sat 38 game days with no owner). Needs a backoff and a stalled state like the plan watch, and **must not assume the operator hold suppresses it** (finding 5). Overlaps `stuck_job` (15) and `plan_input_short` (30): see section 4 |
| 29 | `plan_bootstrap` | Planner | no active plan, F-8 backoff, human escalation after 3 | **WAKE** (supervised first time) |
| 30 | `plan_review` (season) | Planner | computed season index changes | **WAKE** (about 4 a game year) |
| 31 | `plan_target_stalled`, `plan_shortfall`, `plan_input_short` | Planner, owner, input owner | **E** with doubling backoff, rejection suppression, 3 renotifies then stalled (design 5.2) | `plan_shortfall` **WAKE**; `plan_target_stalled` **WAKE** once; `plan_input_short` **MERGE** into `unsupplied_building` for any input that is an item kind (BED), a **WARNING** line otherwise |
| 32 | Logistics: `workshop_ready`, `feeder_starved` | Logistics | state change, **E**, F-8 backoff | **WAKE** |
| 33 | Logistics: `output_blocked`, `flow_unrealised` | Logistics, Planner | **E**, once per version | **WARNING** first; wake only if it persists a season. No pile is urgent |

Totals by primary class: WAKE 14 (rows 1, 2, 5, 7, 10, 11, 13, 21, 27 to 32,
the last group narrowed), WARNING 7 (4, 8, 9, 12, 15, 16, 33), LOG 1 (3),
REMOVE 8 (18, 19, 20 for the Architect, 22 to 26), MERGE 3 (6, 14, 17).
Rows 14, 31 and 21 are split verdicts (wake once, then warning).

---

## 4. Overlaps, forever-wakes and dead ends

**Two wakes for one fact (same role, same cause):**

| Fact | Wakes that fire for it | Keep |
|---|---|---|
| Drink is 0 (live, 10-05 to 10-06) | `alert_crossed`, `prediction_graded` miss (drink target), `stalled_order` (the brew order), `stuck_job` (the Still job), `ruling_on_own` (the last drink order) | `alert_crossed` only. The others become lines in that wake's briefing |
| No bed supply (live) | `stuck_job` (suspended Bed), P0 `bedrooms_per_citizen`, `unsupplied_building`, `plan_input_short`, Overseer defers | `unsupplied_building` to the Quartermaster; P0 to the Architect once |
| Room dug (Architect) | `lane_event` JOB_COMPLETED, `step_done`, `ore_exposed`, `plan_shortfall` | `step_done`, `ore_exposed` |
| Plan target short | P0 alert, `plan_shortfall` | `plan_shortfall` at P1 |

**Can re-fire forever (no cap, no stalled state):**
`queue_pending` on a deferred proposal (L, confirmed live, 3x each for two
proposals); `stalled_order` (L, 12 s renotify); `stuck_job` and `ore_exposed`
(renotify every 12000 ticks, unbounded, no backoff growth); `vital_nearing_threshold`
(no edge, no backoff, never seen live); `open_ask` on an unanswered ask
(benign, one answer closes it). Lane `pending` wakes persist until the role
completes an ok run, so a role that times out twice (the Architect did on
10-05, 607 s each) is re-woken, which is correct, but it re-reads everything
at the cost of another long turn.

**Woken for what it cannot act on:**
Architect on ore without a routed mining tool (live, 10-07; handoff
`route-ore-mining`); Quartermaster on suspended construct jobs (live,
pre-lane); Architect on suspended construct jobs still in its lane regex
(`stuck_jobs: ['...construct|build...']`, lanes policy line 313); asker on
nothing when its ask is answered (inverse: not woken for what it can act
on). The general fix is data: each wake reason declares the tools that can
answer it (`acts_with`), and policy load fails if its owner's allowlist holds
none (`agents/<role>/tools.yaml` is already machine readable). That would have
caught the ore case at deploy time.

**Hold semantics are mixed up in the docs.** Nothing in the triage path
reads the hold; time-based reasons are silent under it only because the tick
is frozen, and level or edge reasons still fire. This will surprise anyone
reading "suppressed under hold" in a handoff. Either gate the optional
reasons on the hold (reasonable: a held, paused fort is being steered by a
human) or say plainly in `docs/AGENT-LOOP.md` that it does not.

## 5. Mechanism: warnings as data

What exists: `build_briefing` (`conductor/briefing.py`) already attaches
`alerts` (all roles), `stuck_jobs` (all roles), `ore_exposed` (role lane
only, `cycle.py:1210 _ore_lines_for`), `frozen` and capped diff events. The
Overseer's ruling prompt carries `ALERT` lines and an `OTHER OPEN ITEMS`
block. What is missing is a delivery choice per reason, role scoping,
expiry, and a way for a warning that is ignored to escalate.

Proposal, all in `conductor/policy.yaml`, evaluated in `conductor/lanes.py`
(which already owns `pending` and its single-writer `lane_state.json`):

```yaml
# Each wake reason picks how it reaches a role. Default `wake` (today's behaviour).
wake_reasons:
  ruling_on_own:  {clock: full_speed, delivery: note, fact: proposal_outcome}
  project_idle:   {clock: full_speed, delivery: note}
  stuck_job:      {clock: full_speed, delivery: note, escalate_after_shows: 3, fact: stuck}
  ore_exposed:    {clock: full_speed, delivery: wake_once_then_note, acts_with: [dig_order]}
  alert_crossed:  {clock: full_speed, delivery: wake, mandatory: true, fact: from_alert}
  prediction_graded: {clock: full_speed, delivery: wake, to: proposer, suppress_if: pending_on_signal}
  hostile_seen_unreachable: {clock: slowed, delivery: log}

# One shared cap and lifetime for every note.
notes:
  max_lines_per_briefing: 6
  max_line_chars: 200
  default: {ttl_cycles: 3, max_shows: 2}   # cycles, not ticks: ticks freeze under a hold

# One wake per (role, fact) per window; later reasons for the same fact
# arrive as lines in that wake, not as wakes.
coalesce:
  window_cycles: 4
```

Behaviour, generic, no per-reason branch:

1. **Where it lives.** `LaneState` gains `notes: {role: {key: {text,
   first_cycle, shows, expires_cycle}}}` beside `pending`. A reason with
   `delivery: note` adds to `notes` instead of `pending`/`Wake`.
2. **Who sees it.** The role(s) the reason would have woken (`lane_triggers`
   already names them), and no other role. This also fixes the unfiltered
   `alerts` and `stuck_jobs` lines: filter them by the same lane data.
3. **When it is delivered.** In any briefing for that role (any wake reason,
   `build_briefing` gets a `notes` list; `build_ruling_briefing` a `NOTES`
   block, which suits the Overseer). A note never enters `triage()`, never
   changes the clock, never counts as a wake.
4. **When it expires.** Whichever comes first: the condition clears (same
   `apply_*_edges` that today drop pending entries), `ttl_cycles`, or
   `max_shows` after an ok run (shows increment in the same place
   `clear_served` runs, `cycle.py:854-863`).
5. **A warning cannot hide a real problem.** `escalate_after_shows` turns a
   note that has been shown that many times with the condition still true
   into one wake (then a longer backoff). This gives `stuck_job` its
   "wake once it is really old" behaviour without a second code path.
6. **Fact coalescing.** `fact` names the underlying fact; the first reason
   to wake a role for a fact in a window wins, the rest become that wake's
   lines. This is the structural fix for the drink pile-up. Today
   `wake_for()` already picks one Wake per role, so the change is to keep the
   rest (record all wakes per role in the briefing, archive and `runs`
   row; the observability the user already asked for).
7. **Dead-end guard.** `acts_with` is checked at policy load against the
   owner's `tools.yaml`; a wake whose owner cannot act on it is refused or
   forced to `note`.

**Per-role wake budget.** Justified, but second to coalescing and edge
fixes (they remove the cause; a budget only hides it). If added: optional
(non-`mandatory`) wakes per role per `window_cycles`, excess demoted to notes
not dropped; `mandatory` set to survival, ruling, ask, tripwire, pause.
Count in cycles, not game ticks (frozen under a hold, and a cycle is the
cost unit). Starting values: Architect 2 and Quartermaster 3 per 6 cycles.
It also makes the planner's "at most 8 rounds per review" budget enforceable
at the conductor.

## 6. Recommendations, in order

1. **Make `queue_pending` an edge** (new, changed, or defer window elapsed)
   and make a bare deferral a note. Biggest single saving and the clearest
   live waste (two proposals, three rulings each, no change).
2. **Delete the dead reasons** (rows 19, 22 to 26): policy.yaml entries,
   `EVENT_TYPE_TO_SIGNAL` entries, the `Signals` fields. No behaviour change;
   removes false comfort. Revive `season_change` from the tick only if the
   Planner lands.
3. **Fix tick-vs-cycle renotify.** Replace renotify-in-ticks with
   exponential backoff in wakes per fact (1, 2, 4, then a cap of one
   season), and a stalled state after 3, as the Planner design already does
   in 5.2. Apply the same to `stalled_order`, `stuck_job`, `ore_exposed`.
4. **Add `delivery`, `fact`, `acts_with` and `notes` to policy** (section 5),
   then move `ruling_on_own`, `project_idle`, stuck jobs, order stalls after
   the first, and the re-fired ore wake onto notes. Record every wake reason
   per role run in the briefing, archive and `runs` table.
5. **Narrow `prediction_graded` to the proposer** (put the proposer on the
   grade record).
6. **Retire the Architect's `routine_review` and `lane_event`**, lengthen the
   Quartermaster's to a season. Do this when `step_done` is live for rooms;
   `lane_event` dig completions are the rooms' own steps.
7. **Land the unsupplied watch before the P0 alert**, give both an explicit
   backoff and stalled state, and correct the "suppressed under hold"
   assumption in the unsupplied handoff.
8. **Decide the hold's meaning for optional wakes** and write it into
   `docs/AGENT-LOOP.md`.
9. **Fix the answer gap**: the Planner design says an `answer` wake exists;
   it does not. Deliver an answer to the asker as a note (and as a wake only
   when a proposal is blocked on it).

## 7. Confidence and gaps

Confirmed by reading source (high): the reason inventory and line refs; the
dead events (no emitter in `scripts/dfhack/`, one grep each); the case-
insensitive lane regex; the hold gating only unexecuted, execute and
pause paths; defer leaving a proposal pending (`dfqueue/store.py:1429`);
no answer wake in `conductor/`.

Confirmed from live data (high for 10-05 onward): run counts, costs,
outcomes, the repeated defers, the five-way drink overlap, the ore pass,
the ore and alert wakes under hold.

Inferred (medium): that renotify in ticks fires "every cycle" at the
service cadence (arithmetic from `base_fps: 100` and observed cycle gaps;
the service has never run unattended); that `lane_event` fires on most
running cycles (drain contents show Dig completions, but the first-reason
record hides it).

**Not verified:** any wake rate per game day under real unattended
operation; the tripwire, pause, slow-announcement, step and vital wakes
(no live fire in the archive); whether the 2026-10-05 lane deploy was live
for the 09:22 cycle (the stuck-job misroute and a prediction hit waking
both advisors suggest not); costs or turns for pre-10-05 runs beyond the
cost file; `usage` token counts per wake (present in the envelopes, not
analysed here); how often a role would have used a note (no such mechanism
to measure).
