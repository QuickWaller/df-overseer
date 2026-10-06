# The Planner: a role that owns the fort plan

Date: 2026-10-07. Status: **design, nothing built.** Author: Opus design
pass for the orchestrator, ahead of an Opus red team. It takes over the owed
districting/zoning session (`decisions/DECISIONS.md` 2026-09-24 site-ranking
row, 2026-10-06 room-access row; memory `zoning-design-session-owed`).
**[verified]** means read in code, data or a register row this session;
everything else is **[proposed]**. No live VM was touched.

Decided before writing, and designed to here (register 2026-10-07 "A Planner
role, now"; the user's answer on authority, relayed 2026-10-07):

- The Architect places, designs and builds rooms; a new **Planner** owns the
  fort plan: districts, industries, the crafting graph and stockpile chains,
  per-citizen targets. Broad scope to design it and to revise it as it learns.
- **Authority, option C (user's call):** a plan version stands on the
  Planner's own say-so, with no Overseer ruling per version. The Overseer
  still rules every action proposal. The server enforces two guardrails only:
  a **minimum interval between revisions** (about a season, as policy data)
  and **no revision may change or repurpose an already-built room without an
  Overseer ruling.**

---

## 0. The design in one screen

1. **The plan is intent, never action.** It says what the fort should have
   and roughly where: targets, districts, which industries, how materials flow
   between them. It names no tile, no site and no step. Every physical change
   still goes through a proposal, the Overseer's ruling and the conductor.
2. **The plan is one append-only record kind, `plan`, in `dfqueue`**,
   written only by the Planner, each version a full document with a reason,
   never a diff and never overwritten.
3. **Targets are measured by code, not judged by models.** Each target names a
   live signal from the existing closed grammar (`learning/live_signals.py`),
   a wanted level and a lower reorder level, usually per citizen. The
   conductor compares live value plus work in flight against the target and
   wakes the target's owner (the Architect for rooms) when it falls short.
   That closes the gap found after the rooms cutover: nothing woke the
   Architect to start bedrooms.
4. **Per-citizen targets make growth free.** A migrant wave raises the need
   without a new plan version, so the Planner can wake rarely.
5. **The Planner wakes rarely:** a first-plan bootstrap, then a seasonal
   review once the revision interval has elapsed. It reads a code-built
   outcome digest (which targets close, which stall, which proposals serving
   them were rejected) and revises with a stated reason.
6. **Guardrails are server refusals:** the interval, and a plan change that
   touches a built room, both refuse with a message naming the route (file a
   `plan_change` proposal for the Overseer). An early revision inside the
   interval uses the same route.
7. **Built in stages.** Stage P0 is a data-only threshold alert that wakes the
   Architect on a bedroom shortfall this week, before any Planner exists.
   Stage P1 is the Planner with targets only. Districts, the crafting graph
   with stockpile chains, and room access follow.

---

## 1. Role boundaries

The line, in one sentence each:

- **Planner:** *what* the fort needs, *how much*, and *roughly where*, as data.
- **Architect:** *exactly where and how* a room or workshop is built, as one
  exact action per proposal, within the plan's districts and access rules.
- **Quartermaster:** *what gets made and how much is kept* (orders, crops,
  stock par levels), within the plan's industries.
- **Overseer:** *whether* each action happens and *when* (rulings, urgency,
  WIP), plus rulings on plan changes that the guardrails send it.
- **Conductor (code):** measures the plan, raises shortfall wakes, briefs
  each role with its own slice, executes accepted routed steps.

| Concern | Planner | Architect | Quartermaster | Overseer | Conductor (code) |
|---|---|---|---|---|---|
| Per-citizen and per-kind capacity targets (bedrooms, dining seats, workshops per kind, pile capacity) | **owns** (sets) | serves (proposes rooms) | serves (workshop jobs, furniture orders) | rules the proposals | measures, raises shortfall wakes |
| Districts: names, kinds, purpose, anchor landmark, level band | **owns** | sites inside them | reads | rules any change touching built rooms | computes relation facts |
| Closeness table between district kinds (SLP A/E/I/O/U/X with reasons) | **owns** | obeys when siting | reads | reads | checks pairs, reports violations |
| Which industries the fort runs, and how many workshops of each kind | **owns** | sites the workshops | runs them (orders) | rules | measures |
| Crafting graph and feeder-pile chains, link policy per workshop kind | **owns** the instance plan; per-kind input classes are repo data | sites piles, proposes links | pins orders to workshops (`WORKSHOP_ID`) | rules | derives missing piles and links, wakes owners |
| Room access per kind (corridor, suite of a kind, any) | **owns** policy | picks templates that comply | | | checks at filing (stage P4) |
| Room design, template choice, finish, doors, exact site, phases | | **owns** | | rules | executes |
| Stock par levels and cover days (`stock_target`) | reads | | **owns** (unchanged) | rules | alerts (`threshold_alerts`) |
| Manager orders, crops, direct jobs | | | **owns** | rules | executes once routed (stage 3) |
| Priority, urgency, WIP cap, season goal | reads | | | **owns** | enforces WIP count |
| Repurposing or retiring a built room | proposes (`plan_change`) | proposes the physical change | | **rules** | executes |
| Any fort mutation | never | never | never | rules only (routed types) | executes routed steps |

Three boundary notes:

- **Stock targets stay with the Quartermaster.** The Planner's targets are
  *capacity* (things built and standing); the Quartermaster's are *stock*
  (things made and consumed), already a closed proposal type with an alert
  path (`dfqueue/schema.py` `STOCK_TARGET`, `conductor/policy.yaml`
  `threshold_alerts`) **[verified]**. Moving them would split one working
  mechanism for no gain. The Planner may name an industry's purpose ("drink
  for the fort, a cover-days level the Quartermaster sets").
- **"The Overseer owns the plan"** in `agents/ROSTER.yaml` and
  `docs/AGENT-ARCHITECTURE.md` §3 **[verified]** means the ordered plan of
  accepted work. Stage P1 rewords both to "the ordered plan of accepted
  work" so two roles never claim one word.
- **The Overseer's season goal** (register 2026-10-01, not built) stays the
  Overseer's alone; its natural candidates are the plan's open shortfalls,
  which its seasonal briefing lists. No new mechanism.

Why a role and not code (`docs/AGENT-ARCHITECTURE.md` principle 1): choosing
targets, industries and district relationships is judgment under
uncertainty with no flow data, exactly the case Systematic Layout Planning's
qualitative chart exists for (`research/2026-09-25-district-layout-prior-art.md`
Q1). Measuring and comparing are computable and stay code.

---

## 2. The plan as data

### 2.1 Storage: a new record kind, `plan`, in `dfqueue`

- **Where:** the existing SQLite store (`dfqueue/<fort>.sqlite3`), new kind
  `plan` beside `proposal`, `ruling`, `amend` and the rest
  (`dfqueue/schema.py` `KINDS` **[verified]**). Reasons: one audit log and
  write-ahead store; the Board and stream page already render queue records;
  JSONL export comes free; dfqueue already refuses coordinates
  (`_COORDINATE_PATTERN` **[verified]**).
- **Who writes:** only the `planner` role, a single-role restriction of the
  same shape as `ANSWER_ROLE` and `OBSERVATION_ROLE` (`dfqueue/schema.py`
  **[verified]** for the pattern). It is a ledger write, never a fort write,
  so it does not touch the sole-writer rule (`agents/ROSTER.yaml`
  `sole_writer: overseer`), exactly as `queue.propose` does not.
- **Versioned, never overwritten:** each `plan` record is a full document
  with `version`, `supersedes` (the previous plan record id), `reason`
  (required from version 2), `changes` (declarative bookkeeping of what
  differs, computed by the server, like `amend`'s `replaces/adds/drops`
  **[verified]** pattern), `public_rationale`, and `relies_on` (up to six
  cited facts, read and stored by the server at filing, the deployed stage 1
  mechanism). The **active** plan is the latest record. History is every
  record. Nothing deletes one.
- **Bounded size** (principle 7, prompt size must not scale with the fort):
  caps held as policy data, starting values: 12 districts, 30 targets, 20
  industries, 40 graph edges, 12 access rules, 6000 characters total. The
  plan is per *kind* almost everywhere, so it grows with the fort's variety,
  not its size.

### 2.2 Schema

Field names are the proposal; shape is the decision.

```yaml
kind: plan
role: planner                      # stamped by the server
version: 3
supersedes: plan-0002
reason: "Bedroom shortfall closed; dining is now the gap"   # required from v2
relies_on: [{tool: zone.list, args: {KIND_FILTER: "", OWNER_FILTER: "", VALID_FILTER: "", NEAR_LANDMARK_FILTER: ""}, field: counts_by_kind.DiningHall}]
public_rationale: "..."
ruling_id: null                    # set only when an accepted plan_change ruling authorises this version (2.4)
prediction:                        # optional, graded by the existing grader
  {signal: 'zones."Bedroom".count', op: gte, value: 22, check_after_ticks: 100800}

targets:                           # capacity the fort should hold
  - id: bedrooms
    signal: 'zones."Bedroom".count'    # live-signal grammar, closed set
    per: alive                         # or omitted for an absolute count
    want: 1.0                          # fill-up level S
    reorder: 0.8                       # wake when position falls below s
    owner: architect                   # which role a shortfall wakes
    district: living                   # optional (stage P2)
    max_in_flight: 2                   # projects serving it at once (WIP courtesy)
    note: "One bedroom each; dormitory acceptable as overflow"
  - id: dining_seats
    signal: 'zones."DiningHall".furniture."Chair"'   # new signal family, stage P1 build item
    per: alive
    want: 1.0
    reorder: 0.7
    owner: architect

districts:                         # stage P2
  - name: living
    kind: living                     # closed vocabulary of district kinds (data)
    purpose: "Bedrooms and the dining hall, away from workshop noise"
    anchor: "Dining Hall"            # an existing landmark name, never a tile
    level: below                     # below | same | above, relative to the anchor
  - name: workshops
    kind: industry
    anchor: "Carpenter's Workshop"
    level: same

closeness:                         # stage P2; between district KINDS, not instances
  - {a: living, b: industry, rating: X, reason: noise}
  - {a: living, b: dining,   rating: A, reason: shared_workforce}
  - {a: industry, b: storage, rating: E, reason: material_flow}

industries:                        # stage P3
  - id: brewing
    workshop_kind: Still             # token from building.list-kinds
    count: 1
    district: workshops
    purpose: "Drink; cover level is the Quartermaster's stock_target"
flows:                             # stage P3: the crafting graph
  - from: farming
    to: brewing
    item_classes: [plants]           # classes from the per-kind input table (repo data)
    feeder: {links_only: true, barrels: 0}   # source pile any-source, satellite links-only
  - from: woodcutting
    to: carpentry
    item_classes: [wood]

access:                            # stage P4: room kind -> what its entrance opens onto
  - {room_kind: Bedroom, opens_onto: corridor}
  - {room_kind: Office, opens_onto: any}
  - {room_kind: Bedroom, opens_onto: "suite_of:Office", when: "noble owner"}
```

Vocabulary rules, all checked by the server at filing (decision rule
`research/2026-10-05-procedure-briefing-and-bounded-turns.md` §3.3 step 2:
the server can see compliance and a false refusal is cheap):

- `signal` must parse under `learning/live_signals.py` **[verified: the
  grammar and its `parse`/`read` split exist]**. New families are added
  there, one entry per family, never per instance: `zones."KIND".count` and
  `zones."KIND".valid` (from `zone.list`, whose summary returns
  `counts_by_kind` and whose filters return `matched_counts_by_kind`
  **[verified in `df-overseer-zone.lua`]**),
  `zones."KIND".furniture."FURNITURE"` (needs one new count field per kind
  in `zone.list` rows or a summary; `zone.contents` exists per zone only
  **[verified]**), `buildings."KIND".count` (no fort-wide building-by-kind
  count read exists today; `landmarks.list` lists buildings **[verified
  summary]**, a count field is a small Lua addition), and
  `stockpiles."CATEGORY".tiles` (from `stockpile.list` **[verified
  summary]**).
- District kinds, closeness ratings (A, E, I, O, U, X) and reason codes
  (`shared_workforce`, `material_flow`, `noise`, `safety`, `sequence`,
  `hygiene`, `convenience`) are closed lists in a data file, the SLP shape
  the prior art recommends (`research/2026-09-25-district-layout-prior-art.md`
  Q1, Q6). Adding a kind is one entry.
- `anchor` must name a landmark that exists now (`landmarks.list`), so a
  district always resolves to a place the tools already understand.
- `workshop_kind` must be a `building.list-kinds` token; `item_classes` must
  be in the per-kind input table (2.3).
- `owner` must be a role whose vocabulary has a type that can serve the
  signal (data: signal family to serving types, e.g. `zones.*` to
  `room_siting`).
- Coordinates are refused anywhere in the record, as for every queue record.

### 2.3 What is repo data, not plan data

The Planner decides *which* and *how many*; the repo holds *what each kind
needs*, read from the game where possible (`tools-must-be-generalisable`):

- **Per workshop kind: input classes, containers, fuel, output classes**
  (`research/2026-10-07-stockpile-logistics.md` recommendation 2). Derived
  from the game's job and reaction requirements, with per-kind policy only
  for exceptions (a still needs a barrel class, a smelter needs fuel unless
  magma). Without it a plan flow cannot be checked for the single-class
  starvation trap the wiki names.
- **Per template: what it provides**, a new `provides` line in each
  `blueprints/templates/*.yaml` (`bedroom-cell-v1` provides one Bedroom
  zone; a future dormitory provides N sleeping places). This is how code
  counts work in flight against a target without a model estimating it.
- **A default plan**, `plans/default-v1.yaml`: generic by rule (no fort
  coordinates, no landmark names in kinds; anchors filled in at bootstrap),
  which the Planner adapts at its first wake rather than inventing from
  nothing. Same rule as blueprint templates (`docs/PURPOSE.md` commitment 1,
  register 2026-09-24).

### 2.4 Guardrails, as server refusals

1. **Minimum interval.** A new version is refused while fewer than
   `planner.min_revision_ticks` game ticks have passed since the active
   version's tick. Starting value 100,800 ticks, one DF season (1200 ticks a
   day, 28-day months, three months a season; `conductor/policy.yaml` cites
   1200 ticks a day **[verified]**), about 17 real minutes at the fort's 100
   FPS cap. Policy data, retuned from runs. Exempt: version 1, and a version
   carrying the `ruling_id` of an accepted `plan_change` (below). The refusal
   says when the next revision may file and how to file early.
2. **Built rooms are not changed by plan say-so.** The server computes, for
   the proposed version against the active one, every **built room binding**
   it would change: a district that holds a built site (any `site-N` with dug
   tiles, `blueprint.sites`, or a zone tagged to the district) being removed,
   renamed to another kind, or re-anchored; an access rule that a built room
   would then violate; an industry dropped whose workshop exists. If any, the
   version is refused naming each binding, and the refusal says: "file a
   `plan_change` proposal naming these; when it is accepted, file this
   version again with its `ruling_id`." Adding districts, raising or
   lowering targets, adding industries and editing purposes never trip it.
3. **`plan_change`** is a new proposal type in the Planner's closed
   vocabulary, unrouted (it changes the plan, not the fort), ruled by the
   Overseer like any other. An accepted one authorises exactly the bindings
   it names, once. The physical work that follows (re-zoning a room, a
   retrofit corridor) is still the Architect's ordinary proposals.

Option C kept small: two refusals, one proposal type, nothing else gated.

### 2.5 How others read it

- **Briefing slice, per role, edge-stable.** The conductor renders, for each
  woken role, only the plan lines in its lane: the Architect gets its
  targets, the districts and closeness rows it sites against, and the access
  rules; the Quartermaster gets industries and flows; the Overseer gets the
  plan version line and open shortfalls. **Placed after the charter and
  before the per-wake facts**, since it changes at most once a season: the
  longest stable prefix gives DeepSeek's prefix cache the most to reuse
  (`research/2026-10-05-procedure-briefing-and-bounded-turns.md` §7.4,
  inference there, to be measured from `prompt_cache_hit_tokens`).
- **One read tool, `plan.read`**, on every proposing role and the Overseer:
  the active plan (or a named version), optionally one section, plus the
  computed status per target (2.6). Bounded, never the history in full;
  `plan.history` is folded in as an argument returning version lines only.
- **On proposals, `serves`:** an optional proposal field naming plan target
  ids the proposal works toward. The server checks each id exists in the
  active plan and that the proposer is the target's owner. This is what lets
  code count work in flight, suppress duplicate wakes, and score each target
  by the proposals that served it.

### 2.6 Shortfall arithmetic (code)

For each target, every cycle the conductor reads (one read per distinct
tool and arguments, cached per cycle exactly as `_read_alert_state` does
**[verified]** in `conductor/cycle.py`):

```
on_hand    = signal value now (divided by alive if per: alive)
in_flight  = sum over open projects and pending proposals that serve this
             target of the template's `provides` (1 when unknown)
             (divided by alive if per: alive)
position   = on_hand + in_flight
```

Inventory position (on hand plus on order) against a reorder point `s`
and an order-up-to level `S` is the standard (s, S) policy, the fix the
goal-tree red team asked for to stop standing goals thrashing
(`research/2026-09-30-goal-tree-red-team.md` F-8). A shortfall opens when
`position < reorder` and closes when `position >= want`; between the two,
nothing fires. That band is the hysteresis.

---

## 3. Learning and revision

### 3.1 What the Planner sees: an outcome digest built by code

At each review the Planner gets a short digest, computed, never asked of a
model (principle 6):

| Outcome | Source | Status |
|---|---|---|
| Each target: value at the version's start, now, and the shortfall's age in game days | target signals, plus a per-version baseline stored at filing | proposed (reads exist) |
| Proposals serving each target: filed, accepted, rejected (with the Overseer's reason), done, abandoned | `serves` plus queue records | proposed (records exist) |
| A target short for long with **no** proposal serving it | same | proposed |
| Idle workshops: a planned industry's workshop with no job or order in N game days | `orders.list`, `workjob` reads, `series.*` history; no per-workshop idle read exists | **gap**, small Lua or series addition |
| Stalled links: a linked workshop whose input class has no non-empty linked source, or whose output link refuses its product | `stockpile.links` exists; the health read does not | **gap**, `stockpile-logistics` rec 3 |
| Haul distance, coordinate-free: walking distance between district anchors, and between a workshop and its feeder pile's landmark | `landmarks.get` exits' `distance_tiles` | exists; **unverified** whether it is path or straight-line distance |
| Closeness violations: an X pair whose anchors sit close, an A pair with no connection | `connectivity.check`, anchor distances | proposed; `connectivity.check` is tagged unverified |
| Stuck jobs per industry | `stuckjobs.find` | exists |
| Citizen needs: room requirements of nobles | `nobles.requirements` | exists |
| Citizen needs: unhappy thoughts about sleeping on the floor, eating without a table | no read exists | **gap**; named, not built until a run asks |
| Last version's prediction: hit or miss | existing grader (`dfqueue/grade.py`) | exists for proposals; extend to `plan` |

Relations are **stated by tools, never composed by the model**: the RCC-8
evidence shows models are weakest at chaining stated relations into new
ones (`research/2026-09-25-district-layout-prior-art.md` Q5). So the digest
says "living to industry: X pair, anchors 9 tiles apart: violated", never
two facts for the model to combine.

### 3.2 How it revises

A revision is a new full `plan` record with `reason`, `relies_on` citing the
digest facts it rests on, and optionally a `prediction` the grader checks
(for example "the dining seat shortfall closes within one season"). The
plan's own track record is then measurable like any proposer's, which is
the learning loop `docs/AGENT-ARCHITECTURE.md` §10 describes: outcomes
recorded by code, not self-assessment.

### 3.3 Guardrails against thrash

- **The interval** (2.4 item 1). A season is long enough for a bedroom row
  to be dug and furnished, so a revision judges real outcomes.
- **The built-room rule** (2.4 item 2): a revision can redirect future work
  freely but cannot undo built work without a ruling.
- **(s, S) bands** (2.6) so a target near its level does not flap.
- **Renotify ticks** on shortfall wakes, as `ore_renotify_ticks` and
  `stuck_job_renotify_ticks` already do **[verified pattern]**.
- **`max_in_flight` per target**, so one shortfall does not fill the
  Overseer's WIP cap of 3 (`docs/CONDUCTOR-EXECUTION.md` §3).
- **A detector, not a refusal,** for oscillation: a target whose `want`
  moved up then down across three versions is flagged in the digest and to
  the user. Promote to a refusal only after two real cases (§3.3 step 6 of
  the briefing research).

---

## 4. Authority (decided)

**Option C, the user's call, 2026-10-07.** Recorded here for the design's
completeness; it is not an open question.

| Option | What needs a ruling | Considered |
|---|---|---|
| A. Every plan version ruled by the Overseer | everything | rejected: the Overseer is being cut toward a ruling-only role with fewer tools and turns; plan review would grow it again |
| B. Pure say-so, no guardrails | nothing | rejected: nothing stops thrash or a plan quietly orphaning built rooms |
| **C. Say-so, with server guardrails (chosen)** | only a revision that changes a built room, or one filed inside the interval | the plan is intent; every physical act is still ruled, so the real gate is unchanged |

What makes C safe is structural, not trust: a plan cannot mutate the fort.
The worst a bad plan can do is wake the Architect for things the Overseer
then rejects, and those rejections appear in the next digest with their
reasons.

---

## 5. Wakes and cadence

### 5.1 What wakes the Planner

| Wake reason | When | Notes |
|---|---|---|
| `plan_bootstrap` | no active plan exists | once; the Planner adapts `plans/default-v1.yaml` |
| `plan_review` | the season changes **and** the interval has elapsed | reuses the existing `season_change` event (`conductor/policy.yaml` **[verified]**), adding the Planner to its roles behind the interval check |
| `ruling_on_own` | a ruling on its own `plan_change` | existing lane-trigger mechanism (`lane_triggers.<role>.rulings`) **[verified]** |
| `answer` | the Consultant answers its ask | existing |

Deliberately **not** waking it: migrant waves (per-citizen targets absorb
growth), routine reviews, graded predictions of other roles. A big shock
mid-season (deaths, a siege) can still change the plan through a
`plan_change` filed when the Planner next wakes, or the Overseer can
commission one (register 2026-10-01, top-down commissioning). If runs show
the season is too slow, an extra wake reason is one policy entry.

### 5.2 The shortfall signal it produces

A new conductor module, `conductor/plan_watch.py`, shaped like
`ore_watch.py` (edge-triggered, renotify ticks) and reusing
`_read_alert_state`'s per-cycle read cache:

- **Opens** a shortfall when position falls below `reorder`; wakes the
  target's `owner` with reason `plan_shortfall`. No new role list: the role
  comes from the target, as `ore_exposed` takes its role from
  `lane_triggers` **[verified pattern]**.
- **Suppressed** while the target already has `max_in_flight` serving
  projects or proposals, under an operator hold, or while the owner's group
  is frozen (`dfqueue/action_tools.yaml` `frozen` **[verified]**).
- **Renotifies** after `plan_shortfall_renotify_ticks` (start at 12000, ten
  game days) while still open and unserved.
- **Briefing line,** one per open shortfall in the owner's lane, fixed
  shape: `Plan v3 target bedrooms: 9 of 22 (0.41 per citizen, want 1.0); 2
  in flight; district living (anchor Dining Hall, below). File room
  proposals with serves: [bedrooms].` Numbers, an anchor and a next action;
  no map.

This is the same family as `threshold_alerts`, generalised: an alert's
threshold is fixed policy, a target's threshold is plan data the Planner
sets, and a target also knows its owner and its work in flight.

### 5.3 Planner turn shape (DeepSeek v4 pro)

Short and fixed: the digest is in the briefing, so a review is roughly
three to eight reads to check a doubt, one optional `queue.ask`, then one
`plan.write` dry run and one real write, or `queue.pass` with a reason. The
charter is short and stable for the cache; the plan and digest come after
it. `plan.write` takes the full document as one argument and returns every
problem at once with repair text (nested JSON is where this model is least
reliable, `research/2026-10-05-procedure-briefing-and-bounded-turns.md`
§7.2), plus a dry-run mode returning the server's computed `changes` and the
guardrail verdict before the real write.

---

## 6. Tools

### 6.1 Reads (all exist unless marked)

Chosen for a review, not for siting: no `*.find`, no blueprint previews.

| Tool | Why |
|---|---|
| `overview.get` | population, landmarks, alerts in one read |
| `vitals.summary` | alive count for per-citizen targets |
| `landmarks.list` | anchors must name existing landmarks |
| `landmarks.get` | exits and `distance_tiles` between anchors |
| `zone.list` | rooms by kind, validity, owner: the main capacity read |
| `zone.list-kinds` | which room kinds exist, owner-capable, defining furniture |
| `building.list-kinds` | workshop kind tokens for industries |
| `workjob.list-jobs` | what each workshop kind can make (graph edges) |
| `stockpile.list` | pile categories and fill |
| `stockpile.links` | today's links (stage P3) |
| `orders.list` | what industries are actually running |
| `stocks.availability` | raw material on hand for an industry decision |
| `nobles.requirements` | room demands by position |
| `blueprint.sites` | built rooms, for the built-room rule |
| `blueprint.plan` | what each template provides |
| `queue.project_status` | work in flight |
| `series.rate` | trends (production and consumption) |

17 reads. `doctrine.get` stays withheld, as for the Architect, until a
proposal and plan field exists to cite doctrine entries
(`agents/architect/tools.yaml` deny note **[verified]**); the Planner asks
the Consultant instead.

### 6.2 Writes and new native tools

| Tool | Holder | What |
|---|---|---|
| `plan.write` (new) | Planner only | files a plan version; `dry_run` returns changes and guardrail verdict |
| `plan.read` (new) | Planner, Architect, Quartermaster, Overseer | active or named version, a section, computed target status, version history lines |
| `queue.propose` | Planner | only type `plan_change` |
| `queue.pass` | Planner | a review with no revision is recorded |
| `queue.ask` | Planner | lookup questions to the Consultant |

**Planner total: 22 tools** (17 reads, 5 writes or queue tools), against
the Architect's 53 and the Quartermaster's 26 (`docs/STATE.md`
**[verified]**). Others gain one tool each (`plan.read`). The Planner holds
no mutating game tool; `dfmcp/roles.py` rule 2 already refuses one to a
non-sole-writer role **[verified, per the architect allowlist notes]**.

### 6.3 Lua and server additions, by stage

- P1: live-signal families `zones."KIND".count` and `zones."KIND".valid`
  (no Lua; `zone.list` already returns the counts), `plan.write`,
  `plan.read`, the `serves` field, `provides` in template metadata.
- P1 or P2: a per-kind furniture count in zones (dining seats), and a
  building count by kind.
- P3: `stockpile` links-only and container counts (read and write), finer
  filters, a `links-health` read, the per-kind input table
  (`research/2026-10-07-stockpile-logistics.md` recommendations 1 to 4).
- P4: access facts at reserve dry run: what a site's entrance opens onto
  (corridor, a room of kind K, open ground).

---

## 7. Interim: the minimum that unblocks a supervised bedroom

The supervised bedroom is owed now (register 2026-10-07, deploy 2b) and
needs only one thing: something that wakes the Architect because bedrooms
are short.

**Stage P0, data plus one small code change, no new role:**

1. Add `zone.list` to `agents/conductor/tools.yaml` (one allowlist line).
2. Add a threshold alert to `conductor/policy.yaml`:
   ```yaml
   - name: bedrooms_per_citizen
     read: {tool: zone.list, args: {KIND_FILTER: "", OWNER_FILTER: "", VALID_FILTER: "", NEAR_LANDMARK_FILTER: ""}, field: counts_by_kind.Bedroom}
     per: alive
     below: 1
     missing: 0
     text: "Bedrooms are short: {value} for the fort, {per_value} per citizen (alert below {threshold}). File a room proposal."
   ```
3. Add `bedrooms_per_citizen` to `lane_triggers.architect.alerts`.
4. **The one code change:** `missing: 0`. `counts_by_kind` is an empty
   object when no zone of a kind exists (`df-overseer-zone.lua`
   `empty_object()` **[verified]**), and `evaluate_threshold_alerts` drops
   the line on a missing field (`conductor/briefing.py` **[verified]**), so
   without it a fort with *no* bedrooms would never alert. `missing` is a
   generic per-alert default, not a bedroom branch.
5. Tests: the alert reads zero when the key is absent; crosses below one per
   citizen; wakes the Architect once per edge; a failed read still drops the
   line.

Deploys to vm106-conductor only. Edge-triggered (`conductor/lanes.py`
`apply_alert_edges` **[verified]**): the Architect wakes once when it
crosses, again only after it clears and re-crosses. It does not count work
in flight, so the Architect must read `queue.project_status` before filing
(its charter already says so); the P1 shortfall watch replaces it.

Caveat to state at the supervised run: the 2026-10-05 bedroom block was
dug before zones were painted last; whether those cells carry Bedroom zones
decides the first reading. Read it live before trusting the alert.

---

## 8. Staged build

Each stage is one or more handoffs in the CONDUCTOR-EXECUTION style: `git
merge --ff-only main` first, commit after each milestone, full ambient
pytest and `dfmcp/tests` in `.venv-dfmcp` green, no edits to `Working.md`,
the register or `memory/`.

### P0. Bedroom alert (section 7)
**Files:** `conductor/policy.yaml`, `conductor/policy.py` (`missing`),
`conductor/briefing.py`, `agents/conductor/tools.yaml`, `conductor/tests/`.
**Deploy:** vm106-conductor. **Live check:** one cycle reads the alert,
the Architect wakes with `alert_crossed`, files a bedroom; supervised
bedroom proceeds as planned.

### P1. The Planner with targets only
**Files:** `agents/ROSTER.yaml` (role `planner`, kind advisor, enabled),
`agents/planner/{role.md,tools.yaml,model.yaml}`, `dfqueue/schema.py`
(`plan` kind, `PLAN_ROLE`, `plan_change` type, `serves` on proposals),
`dfqueue/store.py` (append, active plan, in-flight counts, interval check),
new `dfqueue/plan.py` (validation, `changes` computation, caps),
`learning/live_signals.py` (zone families), new native tools `plan.write`,
`plan.read` in `dfmcp/`, `blueprints/templates/*.yaml` (`provides`), new
`plans/default-v1.yaml`, new `conductor/plan_watch.py`, `conductor/cycle.py`
and `briefing.py` (plan slice, `plan_bootstrap`, `plan_review`,
`plan_shortfall`), `conductor/policy.yaml` (interval, renotify, caps),
Architect and Quartermaster `tools.yaml` (`plan.read`), Architect charter
(`serves`, shortfall wakes), Overseer charter and roster wording ("ordered
plan of accepted work"), `docs/STATE.md` regenerated.
**Tests:** a non-Planner `plan` write refused; a coordinate refused; an
unparseable signal refused; an unknown owner, or an owner with no serving
type, refused; a version inside the interval refused, version 1 accepted;
caps refused with counts; `changes` computed correctly; `serves` naming an
unknown target or another role's target refused; in-flight counts from
open projects and pending proposals; shortfall opens below `reorder`,
stays quiet in the band, closes at `want`; suppressed at `max_in_flight`,
under hold, under freeze; renotify timing; the P0 alert retired in the same
deploy so the Architect is not woken twice for one gap.
**Deploy:** vm103-dfmcp, vm106-agents, vm106-conductor. **Live check:**
bootstrap wake produces v1; a shortfall wakes the Architect with the fixed
line; a bedroom proposal with `serves` is counted in flight.

### P2. Districts and closeness
**Files:** `dfqueue/plan.py` (district, closeness, built-room rule),
district-kind and reason-code data file, `serves`-adjacent `district` field
on room proposals (validated against the plan), a relation-facts read
(anchor distances and connectivity per closeness pair, stated, never left
to composition), digest lines, Architect charter (site inside the
district, anchor as `site`).
**Tests:** an anchor that is not a landmark refused; a revision removing or
re-kinding a district holding a built site refused naming the site; the
same version with an accepted `plan_change` ruling id accepted, once; an X
pair at close range reported violated.
**Known limit carried forward:** site ranking inside a district is still
distance-to-anchor (`ranked_rects`); the district gives it the right anchor
and level, which removes the coffin-class failure for planned kinds. The
ranker redesign stays deferred (register 2026-09-24) until a run shows the
district anchor is not enough.

### P3. Industries, the crafting graph and stockpile chains
**Files:** `scripts/dfhack/df-overseer-stockpile.lua` (links-only, container
counts, finer filters, `links-health`), the per-kind input table, plan
validation of flows against it (refuse the single-class trap at plan time),
digest lines (idle workshops, stalled links), Quartermaster charter (pin
orders with `WORKSHOP_ID` to the planned workshop), Architect charter
(propose feeder piles and links the graph implies).
**Tests:** a flow missing a container or fuel class refused with the
missing class named; `links-health` reports a starved input; a derived
missing link raises a shortfall for the Architect.
**Live check, owed by the research:** an order whose linked pile lacks its
material waits rather than falling back (`stockpile-logistics` §7).

### P4. Room access per kind
**Files:** template metadata (`entrance.opens_onto` on each entrance edge;
`bedroom-cell-v1.yaml` already declares an `entrance` role per edge
**[verified]**), reserve dry run reports what the entrance opens onto,
filing refuses a room whose access contradicts the plan's rule for its kind,
a corridor-row template, a retrofit corridor proposal for today's bedroom
block (register 2026-10-06 agenda).
**Tests:** a bedroom opening into another bedroom refused under
`opens_onto: corridor`; a suite allowed under `suite_of`.

### P5. Learning
Plan predictions graded; the digest's oscillation detector; idle-workshop
and citizen-need reads if runs show they are needed. Lessons go to the
gotchas store or doctrine as derived records, never written by the Planner
directly (`docs/AGENT-ARCHITECTURE.md` §10).

---

## 9. Open questions for the user

Authority is settled (section 4). Three remain, each with a recommendation.

1. **Ship the P0 bedroom alert now, before the Planner exists?**
   Recommendation: **yes.** One small conductor deploy wakes the Architect
   for the supervised bedroom this week; P1 retires it.

2. **Early revisions inside the interval: only through an Overseer-ruled
   `plan_change`, or never?** Your guardrail set a minimum interval; a siege
   or a wave of deaths mid-season may make the plan wrong before it elapses.
   Recommendation: **through a ruled `plan_change`**, the same route as a
   built-room change, so the interval holds by default and the Overseer is
   the exception gate.

3. **Should you see the Planner's first plan (v1) before its shortfall wakes
   go live?** Recommendation: **yes, once**: run the bootstrap supervised,
   read v1 on the Board, then switch `plan_watch` on. Later versions stand
   on the Planner's say-so as decided.

---

## 10. Risks

- **Signals that read wrong.** A target measured by a false-negative read
  (the room-value proxy did this once, register 2026-09-24) wakes the
  Architect for rooms that exist. Mitigation: counts by kind for P1, the
  validity family only after a live check against known zones.
- **Plan and siting disagree.** The plan names a district the ranker cannot
  find room near. The Architect reports it in a pass reason; the digest
  carries it; the Planner re-anchors at review. Not a refusal.
- **Over-planning.** Set intent, let the game execute: the plan sets
  capacity and flows, never schedules dwarves, orders or hauling; feeder
  links are the game's own pull mechanism. Anything resembling an allocator
  stays out.
- **Cost.** One Planner wake a season plus a bootstrap is cheap next to the
  advisors' per-cycle wakes; the shortfall watch adds one cached read per
  distinct target signal per cycle.
