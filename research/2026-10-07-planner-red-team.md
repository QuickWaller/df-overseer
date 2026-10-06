# Planner design: red-team review

Date: 2026-10-07. Reviewer: independent Opus pass, not the author of
`research/2026-10-07-planner-design.md` (commit `ac75b05`). Review only: no
code changed, no live VM touched, nothing deployed.

Read in full: the design; `conductor/briefing.py`, `conductor/lanes.py`
(alert and ore edges), `conductor/policy.yaml`, `conductor/triage.py` (wake
assembly), `learning/live_signals.py`, `agents/architect/role.md`,
`agents/overseer/role.md`, `blueprints/templates/bedroom-cell-v1.yaml`,
`dfqueue/action_tools.yaml`, `evals/live/2026-10-07-stuck-bed/README.md`.
Read in the parts that bear on the design: `conductor/cycle.py` (triage,
alert reads, briefing loop), `conductor/policy.py` (alert parsing),
`conductor/config.py`, `dfqueue/schema.py` (kinds, role restrictions,
vocabularies, coordinate pattern, duplicate check), `dfqueue/store.py`
(`open_projects`, `unexecuted_accepted_proposals`), `dfmcp/queue_tools.py`
(tool ids, cited-fact reads), `dfmcp/roles.py` (rules), the `zone list`
path of `scripts/dfhack/df-overseer-zone.lua`, `df-overseer-landmarks.lua`
(exits), `df-overseer-diff.lua` (emitted event types),
`df-overseer-blueprint.lua` (phase `done`), `docs/CONDUCTOR-EXECUTION.md`
§2 to §5, `infra/deploy-manifest.yaml`, `infra/conductor.example.env`,
`agents/ROSTER.yaml`, the register rows of 2026-10-06 and 2026-10-07, and
`research/2026-09-30-goal-tree-red-team.md` F-8 (cited by the design).
Registry existence of the Planner's 17 reads was checked by loading
`dfmcp.registry.load_registry()` locally.

Labels: **[verified: file:line]** read in this repo at the cited line;
**[repo record]** from an eval or register row, not re-checked live;
**[reasoned]** my inference from verified pieces, untested.

Severity: **blocker** (the stage named cannot work as written), **major**
(fix before the stage named), **minor** (fix when convenient or watch).

---

## 0. The answer, up front

The shape is right: the plan is intent, never action; targets are measured
by code, not judged by a model; the plan is per kind so it grows with
variety, not size; (s, S) bands are the correct fix for flapping; and option
C is honoured, since nothing in the design lets a plan version mutate the
fort. Most of the file and function references check out.

But four things break the staged build as written, and every one of them
is a place where the design reasoned from policy data or a docstring rather
than from what the live code and the live fort do:

1. **The bedroom gap is not a wake gap, and P0 targets the wrong role.**
   The Architect is already woken every 7 game days, and it did file bedroom
   proposals (0013, 0017). They stalled because no BED item has ever existed
   and nothing in the Architect's lane can make one; the Overseer deferred
   them four times (`evals/live/2026-10-07-stuck-bed`). A target with a
   single `owner: architect` reproduces exactly that stall, and the
   unfinished room then holds a WIP slot indefinitely. (F-1, F-2.)
2. **`plan_review` hangs on an event nothing emits.** `season_change` (and
   `migrant_wave`) are in `policy.yaml`, but `df-overseer-diff.lua` never
   logs either type, so the Planner would never be woken for a review.
   (F-3.)
3. **The conductor cannot measure the plan.** It reaches the queue only over
   MCP, and the design grants `plan.read` to four roles but not to the
   conductor; in-flight counts have no read at all. (F-4.)
4. **P0 deploys to the wrong host.** Role allowlists are enforced by the
   server on VM 103; adding `zone.list` to the conductor's allowlist and
   deploying only `vm106-conductor` makes the read refused and the alert
   silently absent. (F-5.)

Then the major cracks: the bedroom count measures painted zones, so a
bedless room counts as built and is double-counted while its project is
open (F-6); per-target `max_in_flight` does not bound the sum against the
Overseer's WIP of 3 (F-7); an unreachable target renotifies about every two
real minutes at 100 FPS, forever (F-8); an accepted `plan_change` is
reported unexecuted forever (F-9); the built-room guardrail the user asked
for has no data to check against until districts are stamped on sites
(F-10); the interval and the season wake together allow a revision only
every other season (F-11).

---

## 1. Findings

### F-1. A capacity target with one owner reproduces the live bedroom stall (blocker, P0 and P1)

**Evidence.**
- `evals/live/2026-10-07-stuck-bed/README.md:7-8,17`: site-3's finish phase
  placed a planned Bed on 2026-10-02; no BED item has ever existed; "No
  proposal ever asks for a bed to be made"; proposals 0013 and 0017 were
  filed and rulings 0015, 0020, 0021 and 0025 deferred them on "no unsuspend
  or bed-supply tool" **[repo record]**. The recommended fix there is a
  Quartermaster `work_order` (`README.md:35-36`), not an Architect proposal.
- Design §2.2 (`owner: architect` on `bedrooms`), §2.5 ("the server checks
  ... that the proposer is the target's owner"), §5.2 (a shortfall "wakes
  the target's `owner`"). The §1 table says the Quartermaster "serves
  (workshop jobs, furniture orders)" but no mechanism ever wakes it, and
  the `serves` owner check refuses its proposals.
- `dining_seats` has the same shape: chairs are made by the Quartermaster's
  orders, placed by the Architect's rooms group.

**Failure.** P0 or P1 wakes the Architect, it files another bedroom, the
Overseer accepts or defers, the finish phase places another planned bed
that waits for an item nobody orders. The shortfall never closes, and the
design's digest only reports it a season later.

**Fix.** Give a target its inputs as data, not a second owner in prose:
`inputs: [{signal: 'stocks.availability."BED".available_units', per_unit:
1, owner: quartermaster}]`, one entry per required item class, generated
from the template's own `requires:` list (`bedroom-cell-v1.yaml` already
declares `requires: [bed]`). `plan_watch` then raises a derived input
shortfall for the input's owner when the in-flight rooms need more items
than are available, and `serves` accepts a proposal from either the target
owner or an input owner. For P0, add a second alert alongside the bedroom
one: `stocks.availability` `{type: BED}` `available_units` below 1 while
bedrooms are short, on the Quartermaster's lane (and add
`stocks.availability` to `agents/conductor/tools.yaml`). Until either
exists, the supervised bedroom should be preceded by the stuck-bed fix (one
`ConstructBed` job), or it will stall at its finish phase the same way.

### F-2. Rooms waiting on an item hold the Overseer's WIP slots: deadlock (major, before P1)

**Evidence.** A phase is `done` only when its buildings are complete
(`scripts/dfhack/df-overseer-blueprint.lua:773`, `build_done` false while a
planned building is unbuilt, `:748`). `open_projects` keeps a project open
while any step is not done (`dfqueue/store.py:2645-2683`). Idle close
applies only to a project whose steps are all done
(`docs/CONDUCTOR-EXECUTION.md` §5, "a project with every step done and no
follow-up"). The WIP cap is 3 (`docs/CONDUCTOR-EXECUTION.md` §3) and the
Overseer is told to "defer the rest without guilt" (`agents/overseer/role.md:20-21`).

**Failure** [reasoned]. Three plan-driven bedroom projects reach their
finish phase with no BED. Each stays open forever and fills the WIP cap.
The Quartermaster's bed `work_order` is a new project, so the Overseer
defers it at the cap. Beds wait for a WIP slot; the slots wait for beds.
Only an `urgency: high` ruling escapes, and the charter reserves `high` for
survival.

**Fix.** Two parts. (1) A step waiting only on an item supply is not WIP:
add a `waiting_on_input` state to the open-project definition (the step's
`blueprint.status` shows a planned building with `complete: false` and the
building read reports a missing item) and exclude it from the cap, listing
it separately in `pending_brief`. (2) Input work orders that serve an open
target's input (F-1) are ruled outside the cap, or the cap reserves one
slot for them. Test: three bedroom projects waiting on BED plus a pending
bed order; the order is not deferred for WIP.

### F-3. `plan_review` is keyed to `season_change`, which nothing emits (blocker, P1)

**Evidence.** `conductor/cycle.py:97-102` maps a drained event `type` of
`season_change` or `migrant_wave` to a signal, and the comment above it
says the mapping is "Unverified against a real diff.since payload".
`df-overseer-diff.lua` logs only `JOB_COMPLETED` (`:289`), `UNIT_DEATH`
(`:313`), `REPORT` (`:328`, with the announcement name inside `detail`),
`announcement_slow` (`:369`) and `UNIT_ATTACK` (`:401`). A repo-wide search
of `scripts/`, `dfmcp/`, `learning/` and `conductor/` finds no emitter of
`season_change` or `migrant_wave` outside tests. The design marks the event
**[verified]** from `conductor/policy.yaml` alone (§5.1).

**Failure.** P1's review wake never fires. The Planner files v1 at
bootstrap and is never woken again except for its own `plan_change`
rulings and answers. It also explains part of the original gap: the
`migrant_wave` wake that `policy.yaml:119` says exists "for beds
(Architect)" has never fired.

**Fix.** Compute the season in code, not from an event: the conductor
already reads the game tick every cycle; `season_index = (tick // 100800) %
4` with a cursor of the last season seen (the `__routine_review__` cursor
pattern, `conductor/cycle.py:1336-1352`), handling a tick that goes
backwards as a reload (as `apply_ore_edges` does, `conductor/lanes.py:202-203`).
Fix `migrant_wave` the same way (population rise in `vitals.summary` alive
by N or more between cycles) or delete the dead mapping; either way say so
in the register so nobody counts on it.

### F-4. The conductor has no read for the plan or for work in flight (major, before P1)

**Evidence.** The conductor reaches the queue only through MCP tools on
its own allowlist (`agents/conductor/tools.yaml`, `queue.overview`,
`queue.pending_brief`, `queue.execution_state`, `queue.project_status`;
`conductor/` imports nothing from `dfqueue.store`). Design §6.2 grants
`plan.read` to the Planner, Architect, Quartermaster and Overseer only.
§2.6's `in_flight` needs a server-side sum over open projects and pending
proposals by `serves`, which no tool returns.

**Fix.** Add one conductor-only native read, `plan.status`: the active
plan's id and version, and per target `{on_hand_signal, want, reorder,
owner, in_flight, serving_ids}` with in-flight computed in the store, so
`plan_watch` does arithmetic only on numbers the server already computed.
Add it to `agents/conductor/tools.yaml` and to P1's file and test list.

### F-5. P0's allowlist change needs the VM 103 server deploy (blocker, P0)

**Evidence.** Design §7: "Deploys to vm106-conductor only." The allowlist
is enforced server-side: `vm103-dfmcp` ships `agents/`
(`infra/deploy-manifest.yaml:48-52`), and the server loads each role's
`tools.yaml` (`dfmcp/roles.py`). The cycle drops a failed alert read
without a line (`conductor/cycle.py:943-952`, a refused call raises
`MCPToolError`, `conductor/mcp_client.py:137-141`).

**Failure.** The conductor's `zone.list` call is refused, the alert reads
as failed, no line, no wake, nothing in the briefing. A quiet no-op.

**Fix.** Deploy `vm103-dfmcp` (for `agents/conductor/tools.yaml`) and
`vm106-conductor` (for the policy and code), and regenerate
`docs/STATE.md` (conductor 34 to 35 tools). Live check: one cycle's journal
shows the `zone.list` read succeeding, not just the absence of an error.

### F-6. The bedroom signal counts painted zones, and double-counts rooms in progress (major, P0 and P1)

**Evidence.** `counts_by_kind` counts every civzone of a kind with no
regard to validity or furniture (`df-overseer-zone.lua:1499-1504`). The
finish meta paints the zone and places the bed in one apply
(`bedroom-cell-v1.csv:54-56`), and the stuck-bed eval shows site-3's zone
existing with a bed that is not built (`README.md:7,17`). So site-3 already
counts as a bedroom. Design §2.6 adds `in_flight` from open projects, and
F-2 shows that project stays open.

**Failure.** For P0: bedless rooms count as on hand, so the alert
understates the gap. For P1: site-3 is counted once in `on_hand` and again
in `in_flight` (open project, `provides: 1`), so the position overstates by
one per stalled room and the shortfall closes early or never opens.

**Fix.** Measure the thing dwarves use: a count of Bedroom zones holding a
complete Bed (`zones."Bedroom".furniture."Bed"`, the per-kind furniture
count the design already lists as a P1 or P2 build item), or
`VALID_FILTER: met` once a live check confirms Bedroom's `room_value_status`
means "has its defining furniture". Make that the P1 signal, not
`zones."KIND".count`. In-flight counts a project's `provides` only until
its own site's zone exists and is counted on hand (per-site, via
`blueprint.sites`), never both.

### F-7. Per-target `max_in_flight` does not bound the total against the WIP cap (major, P1)

**Evidence.** Design §3.3: "`max_in_flight` per target, so one shortfall
does not fill the Overseer's WIP cap of 3." The cap on targets is 30
(§2.1). Two targets at `max_in_flight: 2` already exceed 3.

**Failure** [reasoned]. Two or three open shortfalls each fill to their
own limit, the Overseer's cap is full of plan work, and ad hoc work (a
stair, ore mining, a survival order) is deferred, or the Overseer starts
rejecting plan proposals, which (F-8) re-wake the Architect.

**Fix.** Add a per-owner ceiling in policy data, `plan_in_flight_per_owner`
(start at 2, leaving one WIP slot free), enforced by `plan_watch`
suppression, plus the per-target value. Shortfalls compete for the
per-owner budget in plan order (the Planner orders `targets`, which is
judgment it should own), and the briefing line says "1 of 2 plan slots in
use".

### F-8. An unreachable target wakes its owner every ~2 real minutes forever (major, P1)

**Evidence.** `plan_shortfall_renotify_ticks` starts at 12000 (design §5.2),
copying `ore_renotify_ticks` and `stuck_job_renotify_ticks`
(`conductor/policy.yaml:76,85`). At the fort's 100 FPS that is 120 real
seconds of unpaused play. Rejected and deferred serving proposals are fed
back only into the seasonal digest (§3.1), not into the watch. Each
Architect run costs about $0.05 (2b cycle: three roles, $0.14,
register 2026-10-07) against an Architect ceiling of $2 a day
(`agents/architect/model.yaml`, `budget.ceiling_usd_per_day: 2`, enforcement
"ours", not built).

**Failure** [reasoned]. A target the fort cannot meet (no wood, no
reachable rock, a refused template, the BED case of F-1) wakes the
Architect about thirty times an hour; each wake files or passes; the
Overseer rejects the same thing again. Ore and stuck jobs have the same
cadence but end when the vein is mined or the job runs; a plan target has
no such end until the next plan version.

**Fix.** (1) A serving proposal rejected or deferred suppresses that
target's renotify until the next plan version or an exponential backoff
(double per consecutive unserved renotify, capped at one season). (2) After
N renotifies with an unchanged position (start 3), mark the target
`stalled` in `plan.status`, stop waking its owner, and wake the Planner
with `plan_target_stalled` once (its review is the one place that can
lower, re-scope or drop the target). (3) Test: a target whose position
never moves wakes its owner at most N times per version.

### F-9. An accepted `plan_change` is reported unexecuted forever (major, P1)

**Evidence.** `unexecuted_accepted_proposals` lists every accepted
unrouted proposal with no `executed` or `close` record
(`dfqueue/store.py:1487-1534`). `plan_change` is designed as an unrouted
type (§2.4 item 3). The Overseer's charter and ruling ask tell it to carry
each accepted unrouted proposal out with `queue.project`, act,
`queue.executed` (`agents/overseer/role.md:37-49`,
`conductor/briefing.py` `RULING_ASK`), and the unexecuted wake re-wakes it
(`conductor/cycle.py:666-672`).

**Failure.** The Overseer accepts a `plan_change`, holds no tool that
carries it out, and is woken to carry it out every cycle until a `close`
exists. Nothing writes one.

**Fix.** Treat `plan_change` as a ruling-only type: when the Planner files
the plan version carrying its `ruling_id`, the store (or the conductor as
executor) writes `close` with outcome `completed`; until then it is listed
as "awaiting the Planner", never as the Overseer's to-do. Exclude it from
`unexecuted_accepted_proposals` by a data flag in `dfqueue/action_tools.yaml`
(a third class beside routed and unrouted), not a type branch. Also
`ASK_ROLES` (`dfqueue/schema.py:211`) must gain `planner` for its
`queue.ask`.

### F-10. The built-room guardrail has nothing to check against (major, P1 statement, P2 build)

**Evidence.** Design §2.4 item 2 refuses a version that changes a district
"that holds a built site (any `site-N` with dug tiles, `blueprint.sites`,
or a zone tagged to the district)", an access rule a built room "would then
violate", or a dropped industry "whose workshop exists". No record ties a
site to a district: `blueprint.sites` rows carry a blueprint, phases,
footprint and nearest landmark (registry description of `blueprint.sites`);
zones have no tag field; the `district` field on proposals arrives only in
P2 (§8 P2); access facts arrive only in P4; a building count by kind does
not exist (§2.2). The legacy bedroom block and every pre-plan room have no
district at all.

**Failure.** The guardrail the user decided on cannot detect most of what
it is meant to stop. In P1 (targets only) it is vacuous, which is correct
but unstated; in P2 a re-anchor that moves a district away from its built
rooms passes because the server cannot tell the rooms were in it.

**Fix.** (1) Say in the design that guardrail 2 applies from P2, and test
in P1 that no target change is ever a binding change. (2) Stamp bindings
server-side, never from model prose: at `blueprint.reserve` filing the
server records `site_handle -> district` from the proposal's validated
`district` field, in a store table. (3) Bootstrap: v1 (or the first P2
version) must claim each existing built site (`blueprint.sites`) for a
district or `unassigned`, and the server refuses a version that leaves a
built site unclaimed; after that, a binding change is a set difference on
that table. (4) "Industry whose workshop exists" waits for the building
count by kind; until then the server does not claim to check it, and the
refusal text says so. (5) Access-rule bindings wait for P4 for the same
reason. All of these keep option C's two guardrails and add no ruling.

### F-11. A one-season interval plus a season-change wake allows a revision only every other season (major, P1)

**Evidence.** Interval: refuse while fewer than `min_revision_ticks` =
100800 ticks have passed since the active version's tick (§2.4 item 1).
Wake: "the season changes **and** the interval has elapsed" (§5.1). A
version is filed some time after a season boundary (the wake, then a run
of 60 to 270 seconds at think FPS, `conductor/policy.yaml` `role_timeout`
notes and register 2026-10-07). The next boundary is then fewer than
100800 ticks later.

**Failure** [reasoned]. At the next boundary the interval has not elapsed,
so no wake; the one after is the first eligible. Every revision is two
seasons apart. A Planner that passes (`queue.pass`) never moves the version
tick, so the next check uses the last version, which is fine, but nothing
records that a review happened.

**Fix.** Key the interval to the season, not ticks: at most one version
per season index (version 1 and ruled early versions exempt as designed),
which is what "about a season" means. Record `last_reviewed_tick`
separately from the version tick so a pass is visible in the digest and in
the Board. Keep `min_revision_ticks` only as a floor against reload
oddities.

### F-12. `missing: 0` turns an error-shaped result into "no bedrooms" (major, P0)

**Evidence.** Design §7 item 4 defaults an absent field to 0. Lua tools in
this repo return failures as `{"error": ...}` objects in some paths, which
`learning/live_signals.py:339-347` already treats as an ordinary result
shape for `landmarks.list`; `zone.list` builds its result only after a
successful pass, and its `kinds()` path fails loud on a changed table
layout (`df-overseer-zone.lua:317`).

**Failure** [reasoned]. Any read that comes back as an error object
without `counts_by_kind` reads as zero bedrooms, raises the alert, and
wakes the Architect for rooms that exist (the room-value proxy false
negative of 2026-09-24 in a new form).

**Fix.** Apply `missing` only to the last path segment, and only when the
parent mapping exists and the result has no `error` key: `missing_leaf: 0`.
Test: `{}` and `{"error": "x"}` drop the line; `{"counts_by_kind": {}}`
reads 0.

### F-13. Zone kind tokens are not validated, so a typo becomes a permanent shortfall (major, P1)

**Evidence.** `parse()` is purely syntactic and does not check that a
named thing exists (`learning/live_signals.py:279-282`). A Bedroom count
absent from `counts_by_kind` reads as zero under F-12's default.

**Failure.** `zones."Bedrooms".count` parses, always reads 0, and opens a
shortfall nothing can close.

**Fix.** At `plan.write` filing, resolve each `zones."KIND"` against
`zone.list-kinds` tokens and each `buildings."KIND"` against
`building.list-kinds`, and refuse with the nearest token named. Keep
`read()` returning `UNRESOLVABLE` (not 0) for a kind the game does not
have.

### F-14. Cited facts refuse an absent key, including the design's own example (major, P1)

**Evidence.** `read_cited_fact` refuses any field not present in the
result (`dfmcp/queue_tools.py:1331-1337`). The design's `relies_on`
example cites `counts_by_kind.DiningHall` (§2.2). A fort with no dining
hall has no such key (`df-overseer-zone.lua:1572`).

**Failure.** The Planner cannot cite the fact a bootstrap plan most needs
("there are zero dining halls"); the filing is refused and the repair text
points it at a field that does not exist.

**Fix.** Either cite through live signals (a `relies_on` entry may name a
signal, read by `live_signals.read`, which returns a number for zero), or
give `zone.list` a `kinds` argument that returns every requested token
with an explicit 0. The signal route is generic and reuses the closed
grammar.

### F-15. The real gap is briefing content, and the bedroom alert also wakes the Quartermaster (major, P0)

**Evidence.**
- `routine_review` wakes the Architect and the Quartermaster every 7 game
  days (`conductor/policy.yaml:36,104-106`, `conductor/triage.py:214-221`),
  which is 84 real seconds of play at 100 FPS. Bedroom proposals 0013 and
  0017 were filed (F-1). So "nothing woke the Architect" (register
  2026-10-07, design §0 item 3) is not what the code or the queue shows;
  what was missing is a fact in the briefing and a supply path.
- Alert lines are passed to every role's briefing, not only the lane's
  (`conductor/cycle.py:821,833`; `policy.yaml:265`).
- The Quartermaster's lane has `alerts: ["*"]` (`conductor/policy.yaml:327`),
  and a fresh crossing wakes every lane that lists the alert or `*`
  (`conductor/lanes.py:176-179`).
- The design claims the Architect's charter "already says" to read
  `queue.project_status` before filing (§7). It does not: the charter's
  project section covers follow-ups only (`agents/architect/role.md:105-118`).

**Failure.** P0 wakes the Quartermaster on every bedroom crossing as well;
and without a charter line the Architect may file a duplicate of a bedroom
already in flight, since P0 does not count work in flight.

**Fix.** Change the Quartermaster's `alerts` from `"*"` to an explicit list
(`drink_per_citizen`, `raw_food_per_citizen`, and P0's BED alert from
F-1), add one Architect charter sentence ("before filing a room for a
shortfall, read `queue.project_status`; a room in flight counts"), and
correct the register's framing of the gap when P0 lands.

### F-16. Rounding hides a one-bedroom shortfall (minor, P0; carry into P1)

**Evidence.** `per_value = round(measured / float(alive), 1)` and the
comparison uses the rounded value (`conductor/briefing.py:87-92`).

**Failure.** 21 bedrooms for 22 citizens is 0.95, rounds to 1.0, and is
not below 1: no alert. Any ratio from 0.95 up reads as met.

**Fix.** Compare the unrounded ratio; round only for the text. Test:
21 of 22 crosses `below: 1`. P1's arithmetic must not round either.

### F-17. A ratio reorder point lets a fixed number of dwarves sleep on the floor (minor, P1)

**Evidence.** Design §2.2 `bedrooms`: `want: 1.0`, `reorder: 0.8`, per
alive; a shortfall opens only below 0.8.

**Failure** [reasoned]. After the fort fills to 22 of 22, a wave of five
migrants gives 22 of 27 (0.81): no shortfall, five dwarves without beds
until the next wave. For needs (beds, seats) a ratio band grows with the
fort.

**Fix.** Allow `reorder_gap` (absolute units short, e.g. 2) as an
alternative to a ratio `reorder`, and use it in `plans/default-v1.yaml`
for per-citizen needs; ratios stay for capacities like pile tiles.

### F-18. P1's file list misses the role plumbing (major, P1)

**Evidence.** Hard-coded role lists: `conductor/triage.py:33` (`ADVISORS`),
`conductor/config.py:22` (`ROLES`, per-role models and timeouts),
`conductor/service.py:51`. Per-role launch config and tokens:
`infra/conductor.example.env:31-36` (one pinned openclaw config per role,
`CONDUCTOR_MODEL_<ROLE>`), `dfmcp/auth.py:77` (`MCP_ROLE_TOKEN_<ROLE>`).
`ASK_ROLES` (`dfqueue/schema.py:211`). The run order is advisors in tuple
order (`conductor/cycle.py:88,421`), so a Planner appended to `ADVISORS`
runs after the Architect in its bootstrap cycle.

**Failure.** A Planner directory and roster line alone launch nothing;
appended to `ADVISORS` it also inherits advisor-wide behaviour
(`conductor/cycle.py:785,814,823,855`: routing reads, frozen types, lane
triggers) that may or may not fit.

**Fix.** Add to P1: a `PLANNER` constant beside `CONSULTANT`, run first in
the order (so a new version is in place before other roles are briefed),
its own `ROLES` and model entries, a new token (and a row in the gitignored
secrets rotation list), a pinned openclaw config on VM 106, `ASK_ROLES`,
and a live probe that its tool count matches `docs/STATE.md`.

### F-19. Bootstrap re-fires every cycle until v1 lands (major, P1)

**Evidence.** `plan_bootstrap` fires while "no active plan exists" (§5.1);
no renotify or failure limit is given. The Planner's write is one nested
document that DeepSeek is least reliable at (§5.3, citing
`research/2026-10-05-procedure-briefing-and-bounded-turns.md` §7.2).

**Failure** [reasoned]. Repeated refusals mean a Planner run every cycle,
each the most expensive kind of turn (many reads, a large write).

**Fix.** Bootstrap renotify on the same backoff as F-8, and after three
failed bootstrap wakes escalate to the human with the last refusal text.
The user's open question 3 (see v1 before shortfall wakes) already implies
a supervised first run; make that the P1 live check.

### F-20. One 6,000-character nested JSON argument is the riskiest shape for this model; the caps disagree (major, P1)

**Evidence.** §5.3: `plan.write` "takes the full document as one argument".
§2.1 caps: 30 targets, 12 districts, 20 industries, 40 edges, 12 access
rules, and 6000 characters total. Thirty targets in the §2.2 shape alone
are about 6,000 characters.

**Fix.** Keep the record a full document, but let the call carry
`base_version` plus only the sections being changed
(`set: {targets: [...]}`); the server composes the full record, refuses a
stale `base_version` (optimistic concurrency, which also makes a retry after
a timeout safe), and returns `changes`. Set the character cap from the
item caps (or the reverse) so the first refusal is never a cap the model
could not have known it would hit. Bound `plan.read` history to the last
eight version lines.

### F-21. Prompt-cache placement needs a briefing reorder, and live numbers must be split out (minor, P1)

**Evidence.** The briefing is `json.dumps` of a dict whose first keys are
`role`, `game_tick`, `wake_reason` (`conductor/briefing.py:142-147`,
`conductor/cycle.py:826`), so anything after `game_tick` cannot share a
prefix between wakes. The design's shortfall line carries live numbers
("9 of 22", "2 in flight", §5.2). The same research the design cites says
cost is dominated by output tokens, not briefing size
(`research/2026-10-05-procedure-briefing-and-bounded-turns.md:181`).

**Fix.** Put the plan slice (version, targets, districts: season-stable
text) as the first key of the briefing, before `game_tick`, and the
shortfall lines with numbers after the wake facts. Do not size anything
around the cache until `prompt_cache_hit_tokens` is measured; the case is
attention, not money.

### F-22. Smaller claims that are wrong or incomplete (minor)

- **Template `provides` has no reader.** No server code reads
  `blueprints/templates/*.yaml`; `df-overseer-blueprint.lua:26` says the
  metadata is "for people", and `blueprint.plan` reads the `.csv` on the
  VM. Design §6.1 says `blueprint.plan` shows "what each template
  provides". Fix: a loader in `dfqueue` for the metadata (deployed with
  `vm103-dfmcp`) and drop `blueprint.plan` from the Planner's reads.
- **Plan predictions are not "graded by the existing grader".** The grader
  starts a window at `queue.executed` for proposals
  (`agents/overseer/role.md:51-54`); a plan record has neither. Defer the
  `prediction` field to P5 or define its window start (the filing tick).
- **The word `plan` is taken.** `dfqueue/schema.py:161` calls `project`
  "the Overseer's ordered plan"; `amend` writes "a new numbered plan
  version"; `docs/AGENT-ARCHITECTURE.md:976-982` likewise. Name the kind
  `fort_plan` so two roles never claim one word in code either.
- **Parallel serving proposals look like duplicates.** Same type, near-same
  summary is flagged `duplicate_of` (`dfqueue/schema.py:467-470`). Two
  bedrooms for one target will be. Exclude proposals that serve the same
  target from the duplicate check, or include the target slot in the flag.
- **`stockpiles."CATEGORY".tiles`** would sum `total_tiles` over piles that
  accept a category, double-counting a pile that accepts several
  (`stockpile.list` returns per-pile `accepts`). Define it as tiles of
  piles accepting only that category, or drop it until a run needs it.
- **Reload.** A tick that moves backwards (the test-harness reload ruled in
  `docs/ARMOK-RULINGS.md`) makes the interval look unelapsed for a long
  time. Treat an active version tick in the future as elapsed, as
  `apply_ore_edges` does.
- **The conductor service is disabled** (`docs/STATE.md:34`). P0's "this
  week" assumes cycles run; by hand, that is one `--once` per wake.

### F-23. Anchors and distances will not support P2's closeness checks (major, before P2)

**Evidence.** Landmark exits use straight-line distance in x and y only,
ignoring z (`df-overseer-landmarks.lua:129-131`), and only the three
nearest exits per landmark are kept (`:125`). Every named building is a
landmark (`:160-174`), so names repeat across kinds of furniture and
workshops; an anchor can also disappear when its building does.

**Failure** [reasoned]. "Living to industry: X pair, anchors 9 tiles
apart" can be two places ten levels apart; two anchors not among each
other's three nearest have no distance at all; a duplicated anchor name
resolves to whichever comes first. This resolves the design's own
**unverified** row in §3.1.

**Fix.** Before P2: a relation-facts read that returns, per closeness
pair, horizontal distance, level difference and reachability between the
two anchors directly (not via the exit list); anchors must be unique names
at filing; a missing anchor is a digest line and suspends that district's
siting guidance rather than failing the plan.

---

## 2. Checked and found sound

- **No rendered map, no coordinates.** The plan names kinds, landmark
  anchors, a level relation and counts; relations are stated by tools, not
  composed by the model (§3.1); `dfqueue` refuses coordinates in every
  record (`dfqueue/schema.py:440-449`), though the pattern catches only
  `x=12` and triples, so free-text fields (`note`, `purpose`) depend on the
  charter. Keep it that way: never add a district extent or bounding box,
  even one computed server-side for display. Site handles (`site-N`) stay
  opaque.
- **Option C is preserved.** No plan version needs a ruling except by the
  two decided routes, and nothing in the plan mutates the fort. The
  filing-time validations (signal grammar, caps, anchors, kind tokens) are
  schema validity of the record, not authority; flag that distinction to
  the user so "two guardrails only" is not read as "no validation". The
  design's open question 2 (early revisions through a ruled `plan_change`)
  would add a third ruling-gated case; it is correctly left to the user.
- **References verified as stated:** `KINDS` without `plan`
  (`dfqueue/schema.py:183-186`); `ANSWER_ROLE` and `OBSERVATION_ROLE` as the
  single-role pattern (`:216,227`); `STOCK_TARGET` (`:331`); `amend`'s
  `replaces/adds/drops` (`:418-428`); `counts_by_kind` and
  `matched_counts_by_kind` with `empty_object()`
  (`df-overseer-zone.lua:1566-1585`); `evaluate_threshold_alerts` dropping a
  missing field (`conductor/briefing.py:69-81`); `_read_alert_state`'s
  per-cycle cache (`conductor/cycle.py:933-967`); `apply_alert_edges`
  edge-triggering (`conductor/lanes.py:163-182`); renotify ticks
  (`policy.yaml:76,85`); `frozen` (`dfqueue/action_tools.yaml`);
  `lane_triggers.<role>.rulings`; `bedroom-cell-v1.yaml`'s per-edge
  `entrance` role; the "owns the plan" wording in `agents/ROSTER.yaml`;
  tool counts 53 and 26 (`docs/STATE.md:26,30`); 1200 ticks a day and
  100800 a season. All 15 DFHack-backed Planner reads exist in the registry
  as reads with `coordinate_bearing: false`; `series.rate` and
  `queue.project_status` are native tools (`dfmcp/series_tools.py:219`,
  `dfmcp/queue_tools.py:248`).
- **(s, S) with inventory position** is the right fix for flapping, and it
  is what F-8 of the goal-tree red team asked for.
- **Stock targets staying with the Quartermaster** is right; F-1 extends
  this, it does not reverse it (inputs are item classes the
  Quartermaster's existing mechanism serves).

## 3. Cost (DeepSeek v4 pro)

[reasoned, from repo prices and one measured cycle] Prices in
`research/2026-10-05-procedure-briefing-and-bounded-turns.md:181`: input
cache hit $0.022 to $0.044 per million tokens, miss $0.66 to $1.32, output
$1.98 to $3.96. A Planner review as designed (charter, 22 tool schemas, a
plan up to 6,000 characters, the digest, three to eight reads, an optional
ask, dry run, write) is roughly 10 to 12 rounds of 20,000 to 30,000 input
tokens, mostly cached, plus 30,000 new tokens of tool results, plus 10,000
to 20,000 output tokens: about $0.05 to $0.15 a wake. For scale, the 2b
cycle ran three roles for $0.14 (register 2026-10-07).

A season is about 17 real minutes at 100 FPS, so "rarely" is about three
reviews an hour of unpaused play: under $0.50 an hour. The Planner is not
the cost risk. **The shortfall watch is**: an unserved target re-wakes its
owner about every two real minutes (F-8), roughly $1.50 an hour per stuck
target, beyond the Architect's $2 a day ceiling within two hours. F-8's
backoff and stall state are the cost control.

## 4. Verdict

Build it, but not as written. The data model and the authority model are
sound; the measurement and wake plumbing are not yet. P0 as written would
deploy to the wrong host, wake the wrong role, and lead the supervised
bedroom into the same item stall the fort is in today. P1 as written would
never wake for a review, could not measure its own targets, and would let
one unreachable target cost more than the rest of the roster.

**Before P0:**
1. Deploy to `vm103-dfmcp` as well as `vm106-conductor` (F-5).
2. Add the BED supply alert on the Quartermaster's lane, and do the
   stuck-bed `ConstructBed` fix before the supervised bedroom (F-1).
3. `missing_leaf` semantics, not `missing` (F-12); compare unrounded
   ratios (F-16).
4. Quartermaster `alerts` from `"*"` to an explicit list; one Architect
   charter sentence on reading `queue.project_status` (F-15).

**Before P1:**
5. Targets carry `inputs` with their own owners; `serves` accepts input
   owners (F-1); rooms waiting on an input are not WIP (F-2).
6. Season computed from the tick, with a review cursor and one version
   per season index (F-3, F-11).
7. A conductor-only `plan.status` read with server-computed in-flight
   (F-4); bedrooms measured by complete beds in Bedroom zones, and no
   double count (F-6).
8. A per-owner in-flight ceiling (F-7); renotify backoff, rejection
   suppression and a `stalled` state that wakes the Planner once (F-8);
   bootstrap backoff and escalation (F-19).
9. `plan_change` as a ruling-only class closed by the version that cites
   it (F-9); `planner` in `ASK_ROLES`; role plumbing (F-18).
10. Kind tokens validated at filing (F-13); cited facts through live
    signals (F-14); section-level `plan.write` with `base_version` and
    consistent caps (F-20); state that guardrail 2 is vacuous until P2 and
    test that (F-10).

Before P2: binding table stamped at reserve time and a claimed-sites
bootstrap (F-10); a direct anchor relation read with level difference and
unique anchors (F-23).
