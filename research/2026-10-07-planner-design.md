# The Planner and Logistics: who owns the fort plan, and who runs its chains

Date: 2026-10-07. **Revision 2.** Status: **design, nothing built except
what P0 is building now.** Author: Opus design pass for the orchestrator.
Revision 1 (commit `ac75b05`) was red-teamed in
`research/2026-10-07-planner-red-team.md` (23 findings, F-1 to F-23); this
revision folds every finding in, adds the **Logistics** role (register
2026-10-07, user's call), checks every role against the user's
**more, narrower agents** principle, and leaves one new question open for
the user (section 12, question 1). It takes over the owed
districting/zoning session (`decisions/DECISIONS.md` 2026-09-24 site-ranking
row, 2026-10-06 room-access row; memory `zoning-design-session-owed`).

**[verified]** means read in code, data or a register row this session or by
the red team at the cited line; everything else is **[proposed]**. No live
VM was touched.

Decided before writing, and designed to here:

- **Planner** (register 2026-10-07 "A Planner role, now"): owns the fort
  plan, districts, industries, which chains exist, per-citizen targets, with
  broad scope to design and revise it. The Architect places, designs and
  builds rooms.
- **Authority, option C** (user's call): a plan version stands on the
  Planner's say-so; the Overseer rules every action proposal; the server
  enforces two guardrails only, a **minimum interval between revisions**
  and **no change to a built room without an Overseer ruling.**
- **Logistics** (register 2026-10-07 "A Logistics role"): owns stockpiles,
  links between piles and workshops, links-only, container limits and pile
  upkeep. Consultative like the Consultant; woken by code when a workshop is
  ready and when a linked pile runs dry or a workshop starves; its proposals
  ruled by the Overseer and executed by the conductor. Stockpile tools leave
  the Overseer and the Architect.
- **More, narrower agents** (user, 2026-10-07): the wide-tool Overseer was
  the one that mucked around. The cross-run cache study
  (`research/2026-10-07-cross-run-cache.md`) found output is 52% of cost and
  uncached input 45%, cache reads 3%: **fewer rounds and less reasoning per
  wake matter most**, cache layout hardly at all.

---

## Changelog: revision 1 to revision 2

Each red-team finding, and how it is resolved here. "P0 stream" means
`handoffs/2026-10-07-p0-bedroom-alert.md`, being built now with F-5, F-12,
F-15, F-16 and an Architect charter line folded in. "Unsupplied stream"
means `handoffs/2026-10-07-unsupplied-building-watch.md`, a separate stream.
Neither is redesigned here.

| Finding | Severity | Resolution in revision 2 | Where |
|---|---|---|---|
| F-1 one owner reproduces the bed stall | blocker | P0 side: the unsupplied stream is the general form of the red team's BED alert (any planned building waiting on an item nothing makes wakes the Quartermaster; standing buffer orders are the preferred response). P1 side: a target's **inputs are derived by code** from the serving template's `requires:`, never authored; `serves` accepts the input's owner (Quartermaster). The stuck-bed fix still precedes the supervised bedroom unless the unsupplied watch has landed and a bed order exists. | 2.2, 2.6, 9 |
| F-2 rooms waiting on an item hold WIP | major | A step whose only unfinished work is a planned building the unsupplied read lists is marked `waiting_on_input` by a conductor `observation`; such projects leave the WIP count and are listed separately in `pending_brief`. | 2.7, P1 |
| F-3 `season_change` never emitted | blocker | Season computed from the tick with a cursor, in code. This also revives the Quartermaster's existing `season_change` wake, which is dead today for the same reason. `migrant_wave` computed from the alive count, or deleted. | 5.1, P1 |
| F-4 conductor cannot read the plan | major | A conductor-only native read, `plan.status`, with in-flight computed in the store. | 2.5, P1 |
| F-5 P0 needs the VM 103 deploy | blocker | Folded into the P0 stream (deploy `vm103-dfmcp` as well as `vm106-conductor`). | 9 |
| F-6 painted zones counted, double count | major | Bedrooms measured as **furnished** Bedroom zones (`zones."KIND".furnished`, generic over a kind's defining furniture). In-flight counts a site only until that site's own zone is counted on hand, never both. | 2.2, 2.6 |
| F-7 per-target cap does not bound the total | major | Per-owner ceiling `plan_in_flight_per_owner` (start 2) in policy; targets compete in plan order; briefing says "1 of 2 plan slots in use". | 2.6, 5.2 |
| F-8 unreachable target renotifies forever | major | Exponential renotify backoff capped at a season; a rejected or deferred serving proposal suppresses renotify; after 3 unchanged renotifies the target is `stalled`, stops waking its owner, and wakes the Planner once. | 5.2 |
| F-9 `plan_change` unexecuted forever | major | A third class in `dfqueue/action_tools.yaml`, `ruling_only`, excluded from the unexecuted list; closed (`completed`) by the store when the version citing it files. `planner` added to the ask roles. | 2.4, P1 |
| F-10 built-room guardrail has nothing to check | major | Stated: guardrail 2 is vacuous in P1 (targets only) and tested as such. From P2: a server-stamped `site_handle -> district` binding table written at reserve time, and a claimed-sites bootstrap. Industry and access bindings wait for their reads and the refusal says so. | 2.4, P2 |
| F-11 two-season revision cadence | major | One version per **season index**, not per 100,800 ticks; `last_reviewed_tick` recorded separately so a pass is visible; ticks only a reload floor. | 2.4 |
| F-12 `missing: 0` on an error result | major | Folded into the P0 stream (`missing` applies to the leaf only, when the parent exists and there is no `error` key). P1's signals inherit the same rule. | 9, 2.6 |
| F-13 kind tokens unvalidated | major | Validated at filing against `zone.list-kinds` and `building.list-kinds`; `read()` returns UNRESOLVABLE, not 0. **Whether this is a refusal or a flag is now open question 1.** | 2.3, 12 |
| F-14 cited facts refuse absent keys | major | `relies_on` may cite a live signal, read by `live_signals.read`, which returns a number for zero. | 2.2 |
| F-15 briefing content, Quartermaster `"*"` | major | Folded into the P0 stream (explicit Quartermaster alert list, Architect charter sentence on `queue.project_status`). Correcting the register's "nothing woke the Architect" framing is the orchestrator's. Revision 2's own framing is corrected in 0 and 7. | 9, 7 |
| F-16 rounding hides a one-bed gap | minor | Folded into the P0 stream; P1 arithmetic never rounds before comparing. | 2.6 |
| F-17 ratio reorder leaves dwarves on the floor | minor | `reorder_gap` (absolute units short) as an alternative to ratio `reorder`; used for per-citizen needs in the default plan. | 2.2 |
| F-18 role plumbing missing | major | Full plumbing list for the Planner **and** Logistics: triage constants and run order, config, service, env, tokens, ask and answer roles, pinned openclaw configs, `docs/STATE.md`, secrets rotation rows. | P1, L |
| F-19 bootstrap re-fires every cycle | major | Bootstrap on the same backoff; three failed bootstrap wakes escalate to the human with the last refusal text. P1's live check is a supervised bootstrap. | 5.1 |
| F-20 one nested 6,000-character argument | major | `plan.write` takes `base_version` plus only the sections changed; the server composes the full record, refuses a stale base (also makes a retry safe), and returns `changes`. Caps are item caps with per-field length limits, so the record size follows from them and is never the first refusal. History bounded to 8 lines. | 2.1, 2.3 |
| F-21 cache placement | minor | Re-read against the cache study: the briefing is already the last positional argument, and cache reads are 3% of cost. Within the briefing, the season-stable plan slice goes first and numbers last, because it is free, not because it saves money. The real lever is fewer rounds: wake lines carry the facts so a typical turn needs few reads (7). | 2.5, 7 |
| F-22 smaller claims | minor | Template `provides` read by a `dfqueue` loader, `blueprint.plan` dropped from the Planner. Plan `prediction` deferred to P5, window from the filing tick. Kind named **`fort_plan`**. Serving proposals for one target excluded from the duplicate check. `stockpiles."CATEGORY".tiles` dropped: pile capacity is Logistics' now. Reload: an active version from a later season counts as elapsed. Conductor service disabled: P0 and P1 checks run by `--once`. | 2.1, 2.2, 2.5, 8 |
| F-23 anchors and distances unfit for P2 | major | Before P2: a direct relation read per closeness pair (horizontal distance, level difference, reachability), unique anchor names at filing, a missing anchor suspends that district's siting guidance as a digest line. | 3.1, P2 |

Changes not from the red team:

- **Logistics** added (section 6): charter outline, 14 tools, wakes,
  routed `stockpiles` group, tool gaps, stage L landing with P3.
- **Narrower agents** applied (section 7): the Planner's P1 tool list falls
  from 22 to 12 and grows by stage; stockpile tools leave the Overseer and
  Architect; the Overseer gets the plan slice in its briefing instead of a
  `plan.read` tool; trim candidates named for the Architect and the Overseer;
  the Architect's 7-day routine wake is retired once shortfall wakes exist.
- **Revision 1's open question 1** (ship P0 now) is answered yes by the user
  and P0 is in build; questions 2 and 3 are kept; a new question 1 asks
  whether filing-time format checks should refuse or flag (section 12).
- **Correction of revision 1's premise.** "Nothing woke the Architect to start
  bedrooms" was wrong: `routine_review` wakes it every 7 game days and it
  did file bedrooms (0013, 0017). What was missing was the shortfall fact in
  the briefing and a supply path for the bed (F-1, F-15). The design's
  value is the target, its inputs and its owners, not the wake alone.

---

## 0. The design in one screen

1. **The plan is intent, never action.** It names targets, districts,
   industries and which chains exist, by kind and landmark anchor, never a
   tile, site or step. Every physical change is a proposal, ruled by the
   Overseer, executed by the conductor.
2. **One append-only record kind, `fort_plan`, in `dfqueue`**, written only
   by the Planner, each version a full document with a reason. The call that
   files it carries only the changed sections against a `base_version`.
3. **Targets are measured by code.** Each names a live signal, a wanted
   level and a reorder level (ratio or absolute gap). Code computes the
   position (on hand plus in flight, never double-counted) and the
   **inputs** a target's serving template needs, and wakes the right owner:
   the Architect for the room, the Quartermaster for the bed.
4. **The Planner wakes rarely:** a supervised bootstrap, then once a season
   (season computed from the tick), plus once when a target stalls.
5. **Logistics builds and runs the chains the plan names.** The Architect
   asks it what pile space a workshop needs before siting; code wakes it
   when a workshop is ready and when a linked pile starves; it proposes
   piles, links and settings, ruled by the Overseer, executed by the
   conductor through a newly routed `stockpiles` group.
6. **Wakes are bounded.** Renotify backs off, rejected work suppresses,
   stalled targets stop waking their owner, a per-owner ceiling leaves WIP
   room for other work, and rooms waiting on an item are not WIP.
7. **Guardrails are server refusals:** one version per season, and from P2
   no change to a built room's binding without a ruled `plan_change`.
   Format checks at filing are either refusals or flags: **open question 1**.
8. **Narrow roles.** Planner 12 tools at P1 (17 by P3), Logistics 14, the
   Overseer and Architect lose their stockpile tools, and every wake line
   carries the facts its role needs to act in a few rounds.
9. **Staged.** P0 (in build) and the unsupplied watch (separate stream) now;
   P1 Planner with targets; P2 districts; L Logistics with P3 industries and
   flows; P4 room access; P5 learning.

---

## 1. Role boundaries

One sentence each:

- **Planner:** *what* the fort needs, *how much*, *roughly where*, and
  *which chains exist*, as data.
- **Architect:** *exactly where and how* a room or workshop is built, one
  exact action per proposal, within the plan's districts and access rules.
- **Logistics:** *how materials reach and leave each workshop*: piles,
  links, links-only, containers, finer filters and pile upkeep, within the
  plan's flows.
- **Quartermaster:** *what gets made and how much is kept*: orders (pinned
  to workshops with `WORKSHOP_ID` where a chain names one), crops, stock par
  levels, standing buffer orders.
- **Overseer:** *whether* each action happens and *when*: rulings, urgency,
  WIP, and rulings on plan changes the guardrails send it.
- **Conductor (code):** measures the plan, raises shortfall, input,
  workshop-ready and starvation wakes, briefs each role with its slice,
  executes accepted routed steps.

| Concern | Planner | Architect | Logistics | Quartermaster | Overseer | Conductor |
|---|---|---|---|---|---|---|
| Capacity targets (bedrooms, dining seats, workshops per kind) | **owns** | serves (rooms) | | serves derived inputs (beds, chairs) | rules | measures, wakes owners |
| Districts, anchors, closeness table | **owns** | sites inside them | sites piles inside them | | rules built-room changes | relation facts |
| Which industries run, workshops per kind | **owns** | sites workshops | | runs them (orders) | rules | measures |
| Which chains exist (flows: from industry, to industry, item classes) | **owns** | | builds and runs them | pins orders to chain workshops | rules | flags unrealised flows |
| Per-kind inputs, outputs, containers, fuel | repo data | | reads | reads | | validates |
| Pile siting, links, links-only, containers, filters, upkeep | | asks Logistics what space to leave | **owns** | | rules | executes (routed `stockpiles`) |
| Material policy per workshop kind (no ore in the mason's pile) | doctrine data | | **applies** via links and filters | uses order filters only for exceptions | rules | |
| Room access per kind | **owns** policy | complies | | | | checks at filing (P4) |
| Room design, template, finish, doors, exact site | | **owns** | | | rules | executes (routed `rooms`) |
| Stock par levels, cover days (`stock_target`), standing buffer orders | reads | | | **owns** | rules | alerts |
| Priority, urgency, WIP cap, season goal | reads | | | | **owns** | enforces WIP |
| Repurposing a built room | `plan_change` | the physical change | | | **rules** | executes |
| Any fort mutation | never | never | never | never | never (rules only, for routed groups) | executes routed steps |

Boundary notes:

- **Stock targets stay with the Quartermaster** (`STOCK_TARGET`,
  `conductor/policy.yaml` `threshold_alerts` **[verified]**). The Planner's
  targets are capacity. A target's derived inputs (a bed per bedroom) are
  items, so their owner is the Quartermaster; the user's preferred response
  is a standing manager order with an item condition keeping a small buffer
  (unsupplied stream).
- **Planner versus Logistics on chains.** The Planner says "farming feeds
  brewing with plants"; Logistics decides which piles, of what size, with
  which links, links-only and container settings make that true, and keeps
  them working. A flow the Planner names and Logistics has not realised is a
  code-computed digest line (3.1), not a Planner action.
- **Quartermaster versus Logistics on starvation.** One code fact splits
  them: if the starved input class is **available fort-wide** but not in the
  linked piles, it is a chain fault (Logistics); if it is **absent
  fort-wide** and nothing makes it, it is a supply fault (Quartermaster, the
  unsupplied stream's shape). No role decides which it is.
- **Links and orders.** Manager orders obey workshop links because links live
  on the workshop (user, from play, `research/2026-10-07-stockpile-logistics.md`
  §8). So links fix *what* a workshop may use and `WORKSHOP_ID` fixes *where*
  an order runs. Logistics sets the first, the Quartermaster the second.
- **"Owns the plan"** in `agents/ROSTER.yaml` and
  `docs/AGENT-ARCHITECTURE.md` §3 means the Overseer's ordered plan of
  accepted work **[verified]**; P1 rewords both, and the record kind is
  `fort_plan` so code never shares the word either (F-22).
- **The Overseer's season goal** (register 2026-10-01, not built) stays its
  own; its briefing lists the plan's open shortfalls as candidates.

Why the Planner and Logistics are roles and not code
(`docs/AGENT-ARCHITECTURE.md` principle 1): choosing targets, industries and
district relationships is judgment without flow data (SLP's qualitative
chart, `research/2026-09-25-district-layout-prior-art.md` Q1); choosing
which pile feeds which workshop, how big, and what material to reserve is
judgment over a fort's actual stock. Measuring, deriving per-kind
requirements and detecting starvation are computable and stay code. The
register's splitting test for Logistics (own wake signal, own tool set,
little shared reasoning) holds: its wakes are workshop and pile states no
other role watches, its tools are the stockpile verbs no other role keeps,
and its reasoning (feeders, containers, filters) is not the Architect's
(rooms) nor the Quartermaster's (what to make).

---

## 2. The plan as data

### 2.1 Storage: a new record kind, `fort_plan`, in `dfqueue`

- **Where:** the existing SQLite store, new kind `fort_plan` beside
  `proposal`, `ruling`, `amend` (`dfqueue/schema.py` `KINDS` **[verified]**).
  One audit log, Board rendering, JSONL export, coordinate refusal
  (`_COORDINATE_PATTERN` **[verified]**; it catches only `x=12` and
  triples, so free-text fields still depend on the charter, red team §2).
- **Who writes:** only `planner`, a single-role restriction shaped like
  `ANSWER_ROLE` and `OBSERVATION_ROLE` **[verified pattern]**. A ledger
  write, never a fort write.
- **Versioned, never overwritten:** each record is a full document with
  `version`, `supersedes`, `reason` (required from version 2), `changes`
  (server-computed), `public_rationale`, `relies_on` (up to six, see 2.2),
  `season_index` (stamped), and `ruling_id` when an accepted `plan_change`
  authorises it. Active plan is the latest record; nothing deletes one.
- **Filed by sections** (F-20): `plan.write` takes `base_version`, a `set`
  mapping of only the sections being replaced (`targets`, `districts`,
  `closeness`, `industries`, `flows`, `access`), `reason`, `relies_on`,
  `public_rationale`, `dry_run`. The server composes the full record from
  the active version, refuses a `base_version` that is not the active one
  (optimistic concurrency; a retry after a timeout is safe), and returns
  `changes` and the guardrail verdict. Version 1 composes from
  `plans/default-v1.yaml` as the base.
- **Bounded by item caps, not a character cap** (F-20, principle 7):
  targets 16, districts 10, closeness rows 15, industries 16, flows 30,
  access rules 10; every free-text field (`note`, `purpose`, `reason`) at
  most 160 characters. The record size follows from these, so no first
  refusal can be a size the model could not foresee. Policy data.

### 2.2 Schema

Field names are the proposal; shape is the decision.

```yaml
kind: fort_plan
role: planner                      # stamped by the server
version: 3
supersedes: fort_plan-0002
season_index: 9                    # stamped: game tick // 100800
reason: "Bedroom shortfall closed; dining is now the gap"     # required from v2
relies_on:                         # a tool field OR a live signal (F-14)
  - {signal: 'zones."DiningHall".count'}                      # reads 0 when there are none
  - {tool: vitals.summary, args: {}, field: alive}
public_rationale: "..."
ruling_id: null                    # set only when an accepted plan_change authorises it

targets:                           # capacity the fort should hold; ORDER IS PRIORITY (F-7)
  - id: bedrooms
    signal: 'zones."Bedroom".furnished'   # zones of the kind holding all its defining furniture, complete (F-6)
    per: alive
    want: 1.0                      # order-up-to level S
    reorder_gap: 2                 # open a shortfall when 2 or more units short (F-17)
    owner: architect               # role that serves the target itself
    district: living               # P2
    max_in_flight: 2               # per target; the per-owner ceiling also applies (F-7)
    note: "One bedroom each; dormitory acceptable as overflow"
  - id: dining_seats
    signal: 'zones."DiningHall".furniture."Chair"'
    per: alive
    want: 1.0
    reorder: 0.7                   # a ratio band, for a need that scales loosely
    owner: architect

districts: [...]                   # P2, unchanged in shape from revision 1
closeness: [...]                   # P2, between district KINDS, SLP A/E/I/O/U/X with reason codes
industries:                        # P3
  - {id: brewing, workshop_kind: Still, count: 1, district: workshops,
     purpose: "Drink; cover level is the Quartermaster's stock_target"}
flows:                             # P3: which chains exist; Logistics realises them
  - {from: farming, to: brewing, item_classes: [plants]}
  - {from: woodcutting, to: carpentry, item_classes: [wood], note: "common wood only; reserve the best"}
access: [...]                      # P4, unchanged in shape from revision 1
```

What changed from revision 1, and why:

- **No `inputs` field.** A target's inputs are derived by code from the
  serving template's `requires:` (`bedroom-cell-v1.yaml` declares
  `requires: [bed]` **[verified by the red team]**), read through the
  template loader (2.3). The Planner never authors them, so a plan cannot
  forget the bed (F-1). Code maps an item requirement to the
  Quartermaster's lane.
- **No `feeder` settings on flows.** Links-only, containers and pile sizes
  are Logistics' decisions, not plan data. A flow says only which chain
  must exist and, in `note`, any material intent.
- **No `prediction`** until P5 (F-22): the grader's window starts at
  `queue.executed`, which a plan never has. P5 defines the window from the
  filing tick.
- **`reorder_gap`** (absolute) or **`reorder`** (ratio), exactly one per
  target (F-17).
- **Signals** use the furnished family for rooms (F-6). `zones."KIND".count`
  stays in the grammar for kinds whose zone is the whole thing (a
  Tomb over an existing coffin). `stockpiles."CATEGORY".tiles` is dropped
  (F-22): pile capacity is Logistics' concern, measured by its own reads.

### 2.3 Filing-time checks, and what is repo data

**Checks the server makes at `plan.write`** (whether each refuses or flags
is **open question 1**, section 12; the list is the same either way):

- `signal` parses under `learning/live_signals.py` **[verified: `parse`
  is syntactic only]**, and each `zones."KIND"` resolves against
  `zone.list-kinds` tokens, each `buildings."KIND"` and `workshop_kind`
  against `building.list-kinds` (F-13), naming the nearest token. `read()`
  returns UNRESOLVABLE, never 0, for a kind the game lacks.
- District kinds, closeness ratings and reason codes from the closed data
  file; `item_classes` from the per-kind table; `owner` a role with a
  type that can serve the signal's family (data: family to serving types).
- `anchor` names a landmark that exists now and is **unique** (F-23).
- Item caps and field lengths (2.1).
- Coordinates refused anywhere (always a refusal; not part of question 1,
  since it is the public-repo and no-map commitment, not plan format).

**Repo data, not plan data** (`tools-must-be-generalisable`):

- **Per workshop kind: input classes, containers, fuel, output classes**,
  derived from the game's job and reaction requirements with per-kind
  policy only for exceptions (`research/2026-10-07-stockpile-logistics.md`
  recommendation 2). Read by plan validation (P3), by Logistics'
  `stockpile.plan-feed` (section 6) and by the starvation watch.
- **Per template: `provides` and `requires`**, read by a new loader in
  `dfqueue` (deployed with `vm103-dfmcp`), because no server code reads
  `blueprints/templates/*.yaml` today and `blueprint.plan` reads the `.csv`
  on the VM (F-22 **[verified by the red team]**).
- **Material policy per workshop kind** (stockpile research recommendation
  9): doctrine rows naming the classes a kind's linked input pile accepts
  and which to reserve. Logistics applies them; needs the finer filters.
- **A default plan**, `plans/default-v1.yaml`: generic, no fort coordinates
  or landmark names in kinds; anchors filled at bootstrap.

### 2.4 Guardrails, as server refusals

1. **One version per season index** (F-11). A version is refused while the
   active version's `season_index` equals the current one. Version 1 and a
   version carrying an accepted `plan_change`'s `ruling_id` are exempt. An
   active version from a later season than now (a test-harness reload,
   `docs/ARMOK-RULINGS.md`) counts as elapsed (F-22). `min_revision_ticks`
   stays as a reload floor only. The refusal names the next season and the
   early route. A review that ends in `queue.pass` writes
   `last_reviewed_tick` to the plan state, shown in the digest and Board.
2. **Built rooms are not changed by plan say-so** (F-10). **Vacuous in P1**
   (targets only bind nothing built) and tested so: no target change is
   ever a binding change. From P2: at `blueprint.reserve` filing the server
   stamps `site_handle -> district` from the proposal's validated `district`
   field into a store table; the first P2 version must claim every existing
   built site (`blueprint.sites`) for a district or `unassigned`, refused
   until it does; after that a binding change is a set difference on that
   table (a district holding a site removed, re-kinded or re-anchored).
   "An industry whose workshop exists" is checked only once a building
   count by kind exists, and access bindings only from P4; until then the
   refusal text says the server does not check them. The refusal routes to
   a `plan_change` naming each binding.
3. **`plan_change`** is a Planner proposal type of a new **`ruling_only`**
   class in `dfqueue/action_tools.yaml` (beside routed and unrouted, a data
   flag, not a type branch) (F-9). It is excluded from
   `unexecuted_accepted_proposals`; while accepted and uncited it is listed
   as "awaiting the Planner", never as the Overseer's to-do; the store
   writes its `close` (`completed`) when the version citing its
   `ruling_id` files. An accepted one authorises exactly the bindings it
   names, once.

Schema validity (2.3) is not authority: option C's "two guardrails only"
means two *ruling-gated* cases. Question 1 asks only how invalid format is
handled, not who may decide the plan.

### 2.5 How others read it

- **`plan.status`, conductor only** (F-4): active version id, season index,
  `last_reviewed_tick`, and per target `{signal, want, reorder or
  reorder_gap, owner, on_hand, in_flight, serving_ids, inputs: [{item,
  needed, available, owner}], state: open|quiet|stalled|unresolved,
  renotify_due}`, all computed in the store from records and the per-cycle
  signal reads the conductor passes in or the server reads itself. The
  conductor does arithmetic only on numbers the server computed.
- **Briefing slices.** Each woken role gets only its lane's plan lines.
  Season-stable text (version line, its targets, districts or flows) is the
  first key of the briefing, before `game_tick`; lines with live numbers
  come after the wake facts (F-21). The Overseer gets the version line and
  open shortfalls in its briefing and **no `plan.read` tool** (section 7).
- **`plan.read`**, native, on the Planner, the Architect, and from P3 the
  Quartermaster and Logistics: active or named version, one section,
  computed target status, and the last 8 version lines (F-20).
- **`serves` on proposals:** optional list of target ids. The server checks
  each exists and that the proposer is the target's owner **or the owner of
  one of its derived inputs** (F-1). Proposals serving the same target are
  excluded from the `duplicate_of` check (`dfqueue/schema.py:467-470`
  **[verified by the red team]**), or the target slot is part of the
  duplicate key (F-22).

### 2.6 Shortfall arithmetic (code)

Per target per cycle, one read per distinct signal, cached per cycle as
`_read_alert_state` does **[verified]**:

```
on_hand    = signal value now
in_flight  = sum over open projects and pending proposals serving this target
             of the template's `provides`, counting a site ONLY until that
             site's own zone is counted in on_hand (per site, via the
             site_handle and its zone; never both) (F-6)
position   = on_hand + in_flight          # never rounded before comparing (F-16)
per alive:   divide each by alive for comparison with want / reorder;
             reorder_gap compares (want * alive) - position in units
open       = position below reorder, or units short >= reorder_gap
close      = position >= want
```

Missing-field rule (F-12, as P0 builds it): an absent leaf under a present
parent with no `error` key reads 0; anything else drops the reading, and
the target shows `unresolved` for that cycle, never a shortfall.

**Derived inputs.** For each open or in-flight target, the store sums the
serving templates' `requires` over in-flight sites still waiting on them and
compares with `stocks.availability` plus items in production (active jobs
and orders producing it). A gap becomes an input line on the item owner's
lane (Quartermaster). Where the unsupplied stream's watch already fires for
the same item, the two merge into one line: the watch reports what is
waiting now, the input line what in-flight rooms will need next.

**Per-owner ceiling** (F-7): `plan_in_flight_per_owner` (start 2, leaving a
WIP slot free of plan work) bounds the sum over an owner's targets;
targets earlier in the plan's order get the budget first.

### 2.7 Rooms waiting on an item are not WIP (F-2)

The red team's deadlock is real: a phase is `done` only when its buildings
complete (`df-overseer-blueprint.lua:773`), a project stays open while a
step is not done (`dfqueue/store.py:2645-2683`), and the cap is 3. Fix:

- The conductor reads the unsupplied stream's planned-buildings read each
  cycle. When a routed step's only unfinished buildings are ones that read
  lists as waiting on an unavailable item, it writes an `observation`
  (conductor-only kind **[verified]**) marking the step `waiting_on_input`
  with the item.
- `open_projects` for the WIP count excludes a project whose every
  unfinished step is `waiting_on_input`; `pending_brief` lists them
  separately ("2 rooms waiting on BED").
- When the item arrives (the read no longer lists it), the next
  observation clears the state and the project counts again.
- Input orders for an open target's derived input are not deferred for
  WIP (test: three bedrooms waiting on BED plus a pending bed order; the
  order is not deferred for WIP).

---

## 3. Learning and revision

### 3.1 The outcome digest (code-built)

| Outcome | Source | Status |
|---|---|---|
| Each target: value at version start, now, shortfall age in game days, state (open, stalled, unresolved) | `plan.status` plus a per-version baseline | proposed |
| Serving proposals: filed, accepted, rejected or deferred (with reason), done, abandoned | `serves` plus queue records | proposed |
| Targets short with **no** serving proposal; targets `stalled` and why | same | proposed |
| Derived inputs short (beds for rooms in flight) and whether a standing order exists | `plan.status` inputs, `orders.list` | proposed |
| Flows not realised: a plan flow with no linked chain; chains Logistics reports starved | Logistics' `stockpile.health` (section 6) | **gap**, built in L |
| Idle workshops: a planned industry's workshop with no job or order for N game days | no per-workshop idle read | **gap**, small read in P3 |
| Relations per closeness pair: horizontal distance, level difference, reachability, stated not composed | new relation read (F-23) | **gap**, before P2 |
| Missing anchors (an anchor's building gone): district siting guidance suspended | `landmarks.list` | proposed, P2 |
| Stuck jobs per industry | `stuckjobs.find` | exists |
| Room requirements of nobles | `nobles.requirements` | exists |
| Citizen unhappy thoughts (floor sleeping, eating without a table) | none | **gap**, built only if a run asks |

Relations are **stated by tools, never composed by the model**
(`research/2026-09-25-district-layout-prior-art.md` Q5). Revision 1's
"exits' `distance_tiles`" row is withdrawn: exits are straight-line in x
and y, ignore z, and keep only the three nearest (`df-overseer-landmarks.lua:125,129-131`
**[verified by the red team]**).

### 3.2 How it revises

A revision is a `plan.write` with only the changed sections, a `reason`,
and `relies_on` citing the digest facts (signals allowed, F-14). Its track
record is measured by the targets it set and, from P5, by its graded
predictions.

### 3.3 Guardrails against thrash

- One version per season (2.4); built-room bindings from P2 (2.4).
- (s, S) bands and `reorder_gap`, unrounded (2.6).
- Renotify backoff, rejection suppression and the `stalled` state (5.2).
- Per-target and per-owner in-flight ceilings (2.6).
- An oscillation **detector**, not a refusal: a target whose `want` moved
  up then down across three versions is flagged to the digest and the user;
  promoted to a refusal only after two real cases.

---

## 4. Authority (decided, with one question open on format)

**Option C, the user's call, 2026-10-07.** Not reopened.

| Option | What needs a ruling | Considered |
|---|---|---|
| A. Every version ruled by the Overseer | everything | rejected: grows the Overseer, against the narrower-agents principle |
| B. Pure say-so, no guardrails | nothing | rejected: thrash, orphaned built rooms |
| **C. Say-so with server guardrails (chosen)** | a revision inside the season (early route, question 2) or one changing a built room's binding (from P2) | the plan is intent; every physical act is still ruled |

What makes C safe is structural: a plan cannot mutate the fort. The worst
a bad plan does is wake owners for work the Overseer rejects, and with 5.2
those wakes back off, stall and return to the Planner instead of repeating.

The user's remark "maybe the planner should be in charge of the plans, it's
hard to say" is taken as a question about the **filing-time format checks**,
not the two guardrails: section 12, question 1.

---

## 5. Wakes and cadence

### 5.1 What wakes the Planner

| Wake reason | When | Notes |
|---|---|---|
| `plan_bootstrap` | no active plan | supervised the first time (question 3); renotify on the 5.2 backoff; after 3 failed bootstrap wakes, escalate to the human with the last refusal text (F-19) |
| `plan_review` | the computed season index changes **and** the active version is from an earlier season | season from the tick: `season_index = tick // 100800` with a cursor of the last index seen (the `__routine_review__` cursor pattern, `conductor/cycle.py:1336-1352` **[verified by the red team]**); a tick that goes backwards is a reload and resets the cursor (as `apply_ore_edges` does) (F-3, F-11) |
| `plan_target_stalled` | a target entered `stalled` (5.2) | once per target per version; the review is the one place that can lower, re-scope or drop it. Inside the season it can file a `plan_change` (or, if question 2 adopts it, a narrowing-only revision), or pass |
| `ruling_on_own` | a ruling on its own `plan_change` | existing lane-trigger mechanism |
| `answer` | the Consultant answered its ask | existing |

The same computed season cursor feeds the **existing** `season_change` wake
reason, which wakes the Quartermaster for crop planning and has never fired
(F-3). `migrant_wave` becomes a computed rise of `vitals.summary` alive by
`migrant_wave_min` (start 3) between cycles, or is deleted; either way the
register says so (orchestrator's). Not waking the Planner: migrant waves
(per-citizen targets absorb growth), routine reviews, other roles' grades.

### 5.2 The shortfall watch

`conductor/plan_watch.py`, shaped like `ore_watch.py`, reading
`plan.status` once a cycle:

- **Opens** a shortfall per 2.6 and wakes the owner (`plan_shortfall`), and
  an input line for the input owner (`plan_input_short`), each edge-triggered.
- **Suppressed** while the target holds `max_in_flight` serving work, while
  the owner's plan budget (`plan_in_flight_per_owner`) is used, under an
  operator hold, or while the owner's group is frozen
  (`dfqueue/action_tools.yaml` `frozen` **[verified]**).
- **Rejection suppression** (F-8): a serving proposal rejected or deferred
  suppresses that target's renotify until the next plan version or the
  next backoff step, whichever is later.
- **Backoff** (F-8): renotify starts at `plan_shortfall_renotify_ticks`
  (12,000, ten game days, about 2 real minutes at 100 FPS) and doubles per
  consecutive renotify with no change in position, capped at one season.
- **Stalled** (F-8): after `plan_stall_after` renotifies (start 3) with the
  position unchanged, the target is `stalled`: no more owner wakes this
  version; the Planner gets `plan_target_stalled` once. Test: a target whose
  position never moves wakes its owner at most 3 times per version.
- **Briefing line,** fixed shape, facts first so the owner acts in few
  rounds: `Plan v3 target bedrooms: 9 furnished of 22 citizens (want 22,
  open at 2 short); 2 in flight (site-4, site-5); 1 of 2 plan slots in use;
  district living (anchor Dining Hall, below). Derived input: BED 0
  available, 2 needed, Quartermaster notified. File a room proposal with
  serves: [bedrooms], or pass with a reason.`

### 5.3 Planner turn shape

The digest and its plan slice are in the briefing, so a review is a few
reads to check a doubt, an optional `queue.ask`, a `plan.write` dry run and
the real write, or `queue.pass` with a reason. The dry run returns every
problem at once with repair text (nested JSON is this model's weak spot,
`research/2026-10-05-procedure-briefing-and-bounded-turns.md` §7.2), and
filing only changed sections keeps the argument small (F-20). Budget: at
most 8 rounds per review, measured from the run envelope's
`assistant_turns`, revisited after the first three real reviews.

---

## 6. The Logistics role

### 6.1 Charter outline (for `agents/logistics/role.md`)

- **Owns:** stockpiles and their siting; links between piles and between
  piles and workshops; links-only; container limits (bins, barrels,
  wheelbarrows); category and finer material filters; pile upkeep (a pile
  that never fills, a source pile always full, a pile holding only
  forbidden items). The pile half of material policy (the mason's pile
  takes plain stone, the best wood sits in a reserve pile).
- **Answers:** the Architect's question before it sites a workshop: what
  pile space to leave and where, as a structured `pile_spec` (6.3).
- **Proposes:** `stockpile_siting` (a new pile), `stockpile_link` (link,
  unlink between piles or pile and workshop), `stockpile_settings`
  (categories, finer filters, links-only, containers on an existing pile).
  Ruled by the Overseer, executed by the conductor (6.5).
- **Does not own:** what gets made or how much is kept (Quartermaster),
  where a room or workshop goes (Architect), which chains exist (Planner),
  whether anything happens (Overseer). Never mutates the fort.
- **Rules of thumb in the charter, one line each:** a linked workshop needs
  a linked source for **every** input class including containers and fuel
  (the wiki's single-class trap); an output link must accept what the
  workshop makes; feeders are small (a few jobs' worth), sources are near
  producers; link only when there is a reason (a link restricts a workshop
  that otherwise takes from anywhere, so an unneeded link can only starve
  it). Read the starvation line's routing fact before acting: absent
  fort-wide is the Quartermaster's, not yours.

### 6.2 What wakes Logistics

| Wake reason | Raised by | When | Notes |
|---|---|---|---|
| `ask` | queue | an ask addressed to `logistics` | the post-advisor pass wakes answerers in the same cycle, as for the Consultant today (`conductor/policy.yaml` comment at line 260 **[verified]**) |
| `workshop_ready` | code | a workshop id appears that was not there last cycle (state, not an event: the F-3 lesson), or a `workshop_siting` project's build step is `done` | one line per workshop: kind, landmark name, the per-kind input, container, fuel and output classes, the plan flow it belongs to if any, nearby existing piles. On first enable, one wake lists all existing workshops once |
| `feeder_starved` | code (`logistics_watch.py`) | `stockpile.health`: a linked workshop has an input class whose linked sources are all empty **and** the class is available fort-wide **and** the workshop has a waiting job or an active pinned order | absent fort-wide routes to the Quartermaster instead (1, boundary notes). Edge-triggered, F-8 backoff |
| `output_blocked` | code | `stockpile.health`: a workshop's products are not accepted by any of its linked output piles | edge-triggered |
| `flow_unrealised` | code, P3 | a plan flow with no linked chain between its industries' workshops | once per flow per version, F-8 backoff |
| `ruling_on_own`, `step_done`, `step_attention` | existing | on its own proposals and routed projects | existing mechanisms, role from the project |

**No routine review wake.** Logistics has nothing to do on a timer; every
reason above is a state change. Pile upkeep wakes beyond these (a source
always full, forbidden-only piles) wait for a run that shows the need.

### 6.3 The consult before siting

Flow: the Architect, before filing a `workshop_siting`, files
`queue.ask` with `to: logistics` and the workshop kind (and the plan
industry if any). Logistics answers in the same cycle's post-advisor pass
with a `pile_spec`:

```yaml
pile_spec:                     # validated: classes from the category list, tiles within place's 31 x 31 cap
  - {purpose: feeder, classes: [stone], tiles: 9, adjacent_to: workshop, links_only: true}
  - {purpose: output, classes: [furniture], tiles: 6, adjacent_to: workshop}
  - {purpose: reuse, pile: "Stockpile #2", note: "existing wood source is close enough"}
```

The Architect is woken with `answer` next cycle and sites a template (or a
reserve) leaving that much free floor beside the workshop. Coordinate-free:
tiles and adjacency, never a position.

**Enforced by the server, not the charter:** once Logistics is enabled, a
`workshop_siting` proposal for a kind whose per-kind row lists linked inputs
must cite a Logistics answer for that kind (`pile_spec_answer: ask-N`);
missing, the filing is refused naming the route ("ask logistics, then file
with its answer id"). A kind with no inputs (none in the table) is exempt.
Whether to enforce it is question 4.

Cost: one Logistics answer turn (typically one `stockpile.plan-feed` read
and one `queue.answer`, two or three rounds) and one extra Architect wake per
workshop. Workshops are rare, so this is small next to the stall it
prevents.

### 6.4 Tools: 14

| Tool | Kind | Why | Status |
|---|---|---|---|
| `stockpile.list` | read | every pile: accepts, fill | exists, live-verified 2026-09-18 |
| `stockpile.links` | read | the four link vectors for a pile or workshop | exists, live-verified 2026-09-18 |
| `stockpile.health` | read | per linked workshop: input classes with no non-empty linked source, whether each is available fort-wide, whether the output link accepts its products | **new** (stockpile research rec 3) |
| `stockpile.plan-feed` | read | dry-run spec for a workshop kind or id: piles, classes, sizes, links, containers, from the per-kind table | **new** (rec 2) |
| `landmarks.list` | read | workshop and pile names to site near | exists |
| `openarea.find` | read | free floor near a workshop, the same `is_free` finder `stockpile.place` uses, as a read-only preview | exists |
| `stocks.availability` | read | whether a class is on hand, for material policy and starvation | exists |
| `stuckjobs.find` | read | jobs waiting at a starved workshop | exists |
| `plan.read` | read | the flows slice (P3) | new with P1 |
| `queue.project_status` | read | its piles in flight | exists |
| `queue.pending` | read | asks addressed to it | exists (answerer form, `dfmcp/queue_tools.py` `_pending_description` **[verified]**, generalised from the Consultant) |
| `queue.propose` | write (ledger) | `stockpile_siting`, `stockpile_link`, `stockpile_settings` | exists |
| `queue.pass` | write (ledger) | a wake with nothing to do, with a reason | exists |
| `queue.answer` | write (ledger) | answers to asks addressed to it, with `pile_spec` | exists; `ANSWER_ROLE` generalised (6.6) |

No `doctrine.get` (withheld for every proposer until a citation field exists,
`agents/architect/tools.yaml` deny note **[verified]**); the pile pattern
reaches it through the charter's rules of thumb and the per-kind data. No
`queue.ask`: it asks no one, which keeps its turns short.

### 6.5 Execution: the `stockpiles` group goes routed

`dfqueue/action_tools.yaml` already has a `stockpiles` group, `types:
[stockpile_siting]`, `tools: [stockpile.place, stockpile.configure,
stockpile.link]`, `routed: false` **[verified]**. Stage L:

- Types become `[stockpile_siting, stockpile_link, stockpile_settings]`,
  owned by `logistics` in `TYPE_VOCAB_BY_ROLE`; `stockpile_siting` leaves
  `ARCHITECT_TYPES` **[verified: it is there today]**.
- Tools add `stockpile.unlink` and the new settings verbs (6.6).
- Each tool gets execution metadata in the `docs/CONDUCTOR-EXECUTION.md`
  §2 shape (`issues_handle`, `landed`, `progress`) **[verified that shape
  exists for rooms tools]**: `stockpile.place` issues a pile id, landed when
  `stockpile.list` shows a new pile whose `accepts` match; link steps cite
  that handle, so "place the feeder, then link it" is one project.
- Cutover as for rooms (freeze, `conductor.cutover stockpiles --apply`,
  `routed: true`): the group's tools leave the Overseer's allowlist in the
  same deploy, as the file's own header says.

### 6.6 Tool gaps Logistics needs

1. **Links-only, read and write** on `stockpile.list`/`links` and a settings
   verb; read the field live, never hard-code its default (research §1,
   "Not verified").
2. **Container counts** (max bins, barrels, wheelbarrows), read and write.
3. **Finer material filters** than the 17 coarse categories (which stone,
   which wood): the largest gap for material policy (research §7).
4. **`stockpile.health`** and **`stockpile.plan-feed`** (6.4), on the
   per-kind input table.
5. **`stockpile.link` warns or refuses** the single-class trap in dry run
   (rec 4).
6. **A pile removal verb** (none exists): upkeep sometimes means retiring a
   pile.
7. **Live verification of the write verbs.** `scripts/dfhack/TOOLS.yaml`
   marks `place`, `configure`, `link` and `unlink` `live_deployed: false,
   verified: unverified` **[verified]**; none has run on the fort. A live
   check of each on a throwaway pile precedes the cutover.
8. **The order-starved-of-its-link check** (research §7, owed): an order
   whose linked pile lacks its material waits rather than falling back.
   The user's play settles that orders obey links; this checks the waiting.
9. **Ask addressing.** `queue.ask` gains an optional `to` (closed set:
   roster roles marked as answerers; default `consultant`, so every existing
   ask is unchanged); `ANSWER_ROLE` becomes `ANSWER_ROLES` and the server
   refuses an answer from anyone but the ask's addressee; `queue.pending`
   for an answerer lists asks addressed to it; `ASK_ROLES` gains `planner`
   (F-9) and the answer record gains the optional, validated `pile_spec`.
   Today asks have no recipient (`_ASK_FIELDS = {"question",
   "proposal_id"}` **[verified]**).

### 6.7 Where it lands

**Stage L, landing with P3, buildable in parallel with P2.** Logistics
needs no plan to be useful: `workshop_ready`, `feeder_starved` and
`output_blocked` work from the per-kind table alone. P3's flows then become
one more input (`flow_unrealised`). Order inside L: per-kind table and the
read gaps (6.6 items 1 to 5), live verification (item 7), ask addressing
(item 9), the role, then the `stockpiles` cutover.

---

## 7. More, narrower agents: tool counts and wakes per role

Counts from `docs/STATE.md` and the deploy 2b register row (overseer 82,
architect 53, conductor 34, consultant 29, quartermaster 26 live)
**[verified]**. "After" is after the stage named; trims marked
*recommended* are not decided here.

| Role | Now | After this design | Change |
|---|---|---|---|
| Planner | (new) | **12** at P1, 14 at P2, 17 at P3 | revision 1 had 22 from the start |
| Logistics | (new) | **14** at L | |
| Architect | 53 | **52** (minus `stockpile.list`, `stockpile.links`; plus `plan.read`) | *recommended trim* to about 45: `stocks.food-drink`, `stocks.seeds`, `orders.list`, `orders.check-duplicate`, `workjob.list`, `labor.quota-status`, `labor.enabled-counts` are the Quartermaster's concerns |
| Quartermaster | 26 | **26** at P3 (minus `stockpile.list`; keeps `stockpile.links` to pin orders to linked workshops; plus `plan.read` at P3) | |
| Overseer | 82 | **76** at L (all six stockpile tools leave; no `plan.read`, its briefing carries the plan line) | the orders group's cutover removes 7 more; *recommended* next: route or retire the remaining mutating tools and drop reads a ruling-only role does not use (`surface.*`, `series.*`), toward a ruling-only role of about 40 |
| Conductor | 34 | 35 (P0 `zone.list`), 36 (P1 `plan.status`), 37 (L `stockpile.health`), plus the unsupplied stream's read | code, not a model; width costs nothing per wake |
| Consultant | 29 | 29 | unchanged |

Wake lists, checked against "fewer rounds, less reasoning per wake":

| Role | Wakes after this design | Check |
|---|---|---|
| Planner | bootstrap, season review, target stalled, own rulings, answers | about 4 a game year plus rare stalls; fine |
| Logistics | addressed asks, workshop ready, feeder starved, output blocked, flow unrealised, own rulings and steps | all state changes, no timer; fine |
| Architect | today: routine review every 7 game days (84 real seconds at 100 FPS), predictions, dig and construct `JOB_COMPLETED` lane events, stuck dig jobs, ore, execution, P0 alert, answers | **recommended at P1:** retire the Architect's `routine_review` (shortfall wakes and ore now say when there is work) and narrow its `JOB_COMPLETED` lane events, which duplicate `step_done` since rooms are routed. The routine wake is a timer that invites a model to look for work |
| Quartermaster | routine review, season change (revived, F-3), explicit alert list (P0), stuck production jobs, stalled and blocked orders, stock below target, unsupplied building (stream), derived inputs (P1) | many reasons but each a state change except the routine review; keep the routine review until the unsupplied and input lines have run a few seasons, then measure |
| Overseer | pending proposals, accepted-not-carried-out (shrinks with each cutover; `plan_change` excluded, F-9), tripwire and pause paths | fine; its cost is width, not wakes |
| Consultant | asks addressed to it | fine |

Per-wake shape, the bigger lever: every code-raised wake line in this design
carries the decision facts (counts, names, the routing fact, the next
action) so the woken role needs few or no confirming reads. The cache
study's levers 1 and 2 (keep charters and tool lists byte-stable between
deploys, run wakes close together) apply to both new roles: batch their
charter edits, and run Logistics in the same cycle as the advisor that
woke it.

---

## 8. Planner tools by stage

| Stage | Reads | Writes | Total |
|---|---|---|---|
| P1 | `overview.get`, `vitals.summary`, `zone.list`, `zone.list-kinds`, `nobles.requirements`, `blueprint.sites`, `queue.project_status`, `plan.read` (new) | `plan.write` (new), `queue.propose` (`plan_change` only), `queue.pass`, `queue.ask` | **12** |
| P2 | plus `landmarks.list`, the relation read (new, F-23) | | **14** |
| P3 | plus `building.list-kinds`, `stocks.availability`, `series.rate` | | **17** |

Dropped from revision 1's 22: `blueprint.plan` (no `provides` there, F-22),
`landmarks.get` (the relation read replaces it, F-23), `stockpile.list` and
`stockpile.links` (Logistics' domain; chain health reaches the Planner as
digest lines), `orders.list` and `workjob.list-jobs` (the Quartermaster's;
the per-kind table and the idle-workshop digest line serve the Planner).
The Planner holds no mutating tool (`dfmcp/roles.py` rule 2 **[verified
pattern]**).

---

## 9. P0 and the unsupplied watch (in flight, referenced not redesigned)

- **P0, bedroom alert:** `handoffs/2026-10-07-p0-bedroom-alert.md`, in
  build. Folded in from the red team: deploy to `vm103-dfmcp` (the
  conductor allowlist) as well as `vm106-conductor` and verify the
  `zone.list` read succeeds in the journal (F-5); `missing` applies to the
  leaf only (F-12); unrounded comparison (F-16); the Quartermaster's
  `alerts` an explicit list instead of `"*"` and an Architect charter
  sentence to read `queue.project_status` before filing (F-15). Its signal
  is a painted-zone count (F-6 accepted for P0: it understates the gap,
  which errs toward waking). P1 retires it in the same deploy that turns on
  `plan_watch`, so the Architect is not woken twice for one gap.
- **Unsupplied building watch:** `handoffs/2026-10-07-unsupplied-building-watch.md`,
  separate stream, dispatched after P0 merges. It is the general form of
  F-1's P0 fix: a planned building waiting on an item nothing makes wakes the
  Quartermaster, whose preferred response is a standing manager order with an
  item condition keeping a small buffer (user's call). This design reuses
  its planned-buildings read for `waiting_on_input` (2.7) and merges its
  line with P1's derived-input line (2.6).
- **Before the supervised bedroom:** either the stuck-bed fix (one
  `ConstructBed` job, `evals/live/2026-10-07-stuck-bed`) or the unsupplied
  watch live with a bed order filed, or the new room stalls at its finish
  phase as site-3 did. The conductor service is disabled
  (`docs/STATE.md` **[verified]**), so "this week" means `--once` cycles by
  hand.

---

## 10. Staged build

Every stage is one or more handoffs in the CONDUCTOR-EXECUTION style: `git
merge --ff-only main` first, commit after each milestone, full ambient
pytest and `dfmcp/tests` in `.venv-dfmcp` green, executors never write
`Working.md`, the register or `memory/`.

### P0. Bedroom alert (in build, section 9)

### U. Unsupplied building watch (separate stream, section 9)

### P1. The Planner with targets only

**Files:** `agents/ROSTER.yaml` (role `planner`, advisor, enabled),
`agents/planner/{role.md,tools.yaml,model.yaml}` (12 tools);
`dfqueue/schema.py` (`fort_plan` kind, `PLAN_ROLE`, `plan_change` type,
`serves`, `planner` in `ASK_ROLES`, duplicate-check exclusion);
`dfqueue/action_tools.yaml` (`ruling_only` class); `dfqueue/store.py`
(append, active plan, season index, `last_reviewed_tick`, in-flight with
per-site no-double-count, derived inputs, `waiting_on_input` exclusion from
WIP, `plan_change` close); new `dfqueue/plan.py` (section composition,
`base_version`, caps, checks per question 1's answer, `changes`); new
`dfqueue/templates.py` (template `provides`/`requires` loader);
`learning/live_signals.py` (`zones."KIND".count`, `.furnished`,
`.furniture."F"` families, UNRESOLVABLE for unknown kinds); the Lua read
for furnished and furniture counts in `zone.list`; native `plan.write`,
`plan.read`, `plan.status` in `dfmcp/`; `relies_on` signal citations;
`blueprints/templates/*.yaml` (`provides`); `plans/default-v1.yaml`;
`conductor/plan_watch.py`; `conductor/cycle.py` (computed season cursor
feeding `plan_review` and the existing `season_change`; `migrant_wave`
computed or deleted; `waiting_on_input` observations); `conductor/briefing.py`
(plan slice first, number lines last); `conductor/policy.yaml` (season
policy, renotify, backoff, `plan_stall_after`, `plan_in_flight_per_owner`,
retire the P0 alert, retire the Architect's `routine_review` per section 7
if the user agrees); Architect `tools.yaml` (`plan.read`) and charter
(`serves`, shortfall line); Overseer charter and roster wording;
conductor `tools.yaml` (`plan.status`).
**Role plumbing (F-18):** a `PLANNER` constant in `conductor/triage.py`,
run **first** so a new version is in place before others are briefed;
`conductor/config.py` `ROLES` with model and timeout; `conductor/service.py`;
`infra/conductor.example.env` (`CONDUCTOR_MODEL_PLANNER`, a pinned openclaw
config path); `dfmcp/auth.py` token `MCP_ROLE_TOKEN_PLANNER` (and a row in
the gitignored secrets rotation list); a pinned openclaw config on VM 106;
a live probe that its tool count matches `docs/STATE.md`, regenerated.
**Tests:** non-Planner write refused; coordinate refused; stale
`base_version` refused; a second version in one season refused, version 1
and a ruled version accepted, a later-season active version (reload) counts
as elapsed; checks per question 1 (refusal or flag, each with the nearest
token named); caps refused by item count; `changes` correct; no target
change is ever a binding change (guardrail 2 vacuous in P1); `serves`
accepts the target owner and the input owner, refuses others; parallel
serving proposals not flagged duplicates; a site counted in flight until its
zone is furnished, never both; derived input BED short for two in-flight
rooms raises one Quartermaster line, merged with the unsupplied line; three
rooms waiting on BED do not fill WIP and a bed order is not deferred;
shortfall opens below `reorder` and at `reorder_gap`, quiet in the band,
closes at `want`, never rounded; per-owner ceiling suppresses in plan order;
rejection suppression; backoff doubling to the season cap; stalled after 3
and one Planner wake; bootstrap backoff and escalation after 3; accepted
`plan_change` not in the unexecuted list and closed by the citing version;
season cursor fires once per index and resets on a backwards tick.
**Deploy:** vm103-dfmcp, vm106-agents, vm106-conductor. **Live check:**
supervised bootstrap; the user reads v1 on the Board (question 3); then
`plan_watch` on; a shortfall wakes the Architect with the fixed line; a
bedroom with `serves` is counted in flight; the bed input line reaches the
Quartermaster.

### P2. Districts and closeness

**Before it:** the relation read (per closeness pair, horizontal distance,
level difference, reachability, directly between anchors) and unique anchor
names (F-23).
**Files:** `dfqueue/plan.py` (districts, closeness, binding table checks),
district-kind and reason-code data file, the `district` field on room
proposals, the binding table stamped at `blueprint.reserve` filing, the
claimed-sites bootstrap (F-10), digest lines, Architect charter (site
inside the district, anchor as `site`), Planner tools to 14.
**Tests:** an anchor that is not a unique landmark refused or flagged per
question 1; the first P2 version refused until every built site is claimed;
a revision removing or re-kinding a district holding a site refused naming
the site; the same version with an accepted `plan_change` accepted, once;
an X pair close in plan distance but ten levels apart reported with its
level difference; a missing anchor suspends that district's guidance.
**Known limit carried forward:** site ranking inside a district stays
distance-to-anchor (register 2026-09-24); the redesign waits for a run that
shows the anchor is not enough.

### L. Logistics (lands with P3; buildable in parallel with P2)

**Files:** the per-kind input table (from game job and reaction data, with
per-kind exceptions); `scripts/dfhack/df-overseer-stockpile.lua`
(links-only and container read and write, finer filters, `health`,
`plan-feed`, single-class warning, a removal verb) and `TOOLS.yaml`;
`dfqueue/schema.py` (three Logistics types, `stockpile_siting` out of
`ARCHITECT_TYPES`, ask `to`, `ANSWER_ROLES`, `pile_spec`, the
`pile_spec_answer` requirement on `workshop_siting`);
`dfqueue/action_tools.yaml` (`stockpiles` group types and tools, execution
metadata, then routed); new `conductor/logistics_watch.py`
(`workshop_ready`, `feeder_starved`, `output_blocked`, with the
fort-wide-availability routing fact and F-8 backoff); `conductor/triage.py`
(Logistics as an answerer in the post-advisor pass, and as an advisor in
order after the Quartermaster); `agents/logistics/{role.md,tools.yaml,model.yaml}`
(14 tools); allowlist removals: six stockpile tools from the Overseer,
`stockpile.list`/`links` from the Architect, `stockpile.list` from the
Quartermaster; Architect charter (ask Logistics before a workshop);
Quartermaster charter (pin orders with `WORKSHOP_ID` to a linked workshop
of the chain); the same role plumbing as P1 for `logistics`.
**Live checks before the cutover:** each stockpile write verb on a
throwaway pile; links-only and container fields read live; an order whose
linked pile lacks its material waits (research §7).
**Tests:** a starved input available fort-wide wakes Logistics, absent
fort-wide does not (Quartermaster's); an output pile that refuses the
product raises `output_blocked`; a new workshop id raises one
`workshop_ready`; a `workshop_siting` for a kind with inputs refused without
a Logistics answer, exempt for a kind with none; an answer from a role other
than the addressee refused; an ask with no `to` still goes to the Consultant;
`plan-feed` for a still includes a barrel class; `link` warns on the
single-class trap; place then link in one project via the issued handle.
**Deploy:** vm103-dfhack-scripts, vm103-dfmcp, vm106-agents,
vm106-conductor; cutover per the rooms pattern.

### P3. Industries and flows

**Files:** plan validation of industries and flows against the per-kind
table (a flow missing a container or fuel class refused or flagged, named);
`flow_unrealised` in `logistics_watch.py`; idle-workshop read and digest
line; Planner tools to 17; Quartermaster `plan.read`.
**Tests:** a still flow without a barrel source class flagged; an
unrealised flow wakes Logistics once per version; an idle planned workshop
appears in the digest.

### P4. Room access per kind

Unchanged from revision 1: `entrance.opens_onto` in template metadata,
reserve dry run reports what the entrance opens onto, filing refuses a room
whose access contradicts its kind's rule, a corridor-row template, a
retrofit corridor for today's bedroom block (register 2026-10-06 agenda).
Access bindings join guardrail 2 here.

### P5. Learning

Plan predictions with a window from the filing tick; the oscillation
detector; citizen-need reads if runs ask. Lessons go to the gotchas store or
doctrine as derived records, never written by the Planner directly
(`docs/AGENT-ARCHITECTURE.md` §10).

---

## 11. Cost

From the red team's §3 and the cache study's fitted rates ($0.435 per M
uncached input, $0.0036 per M cache read, $0.87 per M output): a Planner
review of 8 rounds or fewer is about $0.05 to $0.10, three or four a game
year plus bootstrap; a Logistics answer or workshop wake of two or three
rounds is a few cents, and workshops are rare. The risk was the shortfall
watch re-waking an owner every two real minutes (red team: about $1.50 an
hour per stuck target); backoff, rejection suppression and the stalled
state cap that at three owner wakes per target per version. The same
pattern applies to Logistics' starvation wakes.

---

## 12. Open questions for the user

Authority is option C, decided. Each question below has a recommendation.

1. **Filing-time format checks: server refusals, or should the Planner own
   its plans more fully?** The checks are kind tokens, item caps, landmark
   validity and signal grammar (2.3). Coordinates are always refused and
   are not part of this question.
   - **(a) Refuse** (revision 1). Every invalid entry blocks the filing
     until fixed. Pros: a typo never becomes a permanent shortfall (F-13);
     matches "server refusals over charter prose"; the dry run already
     returns every problem at once, so a refusal costs at most the round
     already budgeted. Cons: the Planner's say-so is conditional on the
     server's format; a stubborn error loops (bounded by F-19's backoff).
   - **(b) Accept and flag.** Anything structurally parseable files; an
     entry that fails a check is stored as `unresolved`, never measured or
     woken on, and reported in `plan.status` and the next digest. Pros: the
     plan is wholly the Planner's; no refusal loops. Cons: a bad entry sits
     inert for up to a season unless a correction route exists; the digest
     grows; a wrong kind token is silently a missing target.
   - **(c) Split by what the error is about (recommended).** Refuse what is
     static and always wrong (unparseable signal grammar, a kind token the
     game does not have, over caps, a type mismatch), since no world change
     can make it right and the dry run surfaces it in the same turn. Accept
     and flag what is about the world and can change (an anchor landmark
     missing or duplicated today, a district that has no room near its
     anchor yet), since refusing would let the map veto the plan. Pair it
     with a correction route: a revision that changes only entries flagged
     `unresolved` is exempt from the season interval (code-checkable, so
     it adds no ruling).

2. **Early revisions inside the season: only through an Overseer-ruled
   `plan_change`, or never?** A siege or deaths mid-season may make the plan
   wrong before the next season. The stalled-target wake (5.1) now gives the
   Planner a mid-season moment to act. **Recommendation: through a ruled
   `plan_change`**, the same route as a built-room change, plus one
   code-checkable exemption: a revision that only **narrows** (lowers or
   drops a target code marked `stalled`, or fixes an entry flagged
   `unresolved` under question 1's option c) files without a ruling.
   Everything else waits for the season or a ruling.

3. **Should you see the Planner's first plan (v1) before its shortfall wakes
   go live?** **Recommendation: yes, once**: run the bootstrap supervised,
   read v1 on the Board, then switch `plan_watch` on. Later versions stand
   on the Planner's say-so as decided. This is also P1's live check (F-19).

4. **Should the server refuse a `workshop_siting` that does not cite a
   Logistics `pile_spec` answer?** It turns the user's "the Architect asks
   Logistics before siting" into a refusal rather than a charter line, at
   the cost of one extra Architect wake per workshop. **Recommendation:
   yes**, for kinds whose per-kind row lists linked inputs, exempt
   otherwise, switched on with the Logistics enable.

5. **Retire the Architect's 7-day `routine_review` wake at P1?** Shortfall,
   ore and execution wakes now say when it has work; a timer wake invites a
   wide-tool role to look for work, the behaviour the narrower-agents
   principle names. **Recommendation: yes at P1**, keep the Quartermaster's
   until its unsupplied and input lines have run a few seasons, and take the
   Architect and Overseer tool trims in section 7 as their own small
   handoffs.

---

## 13. Risks

- **Signals that read wrong.** A false negative wakes owners for rooms that
  exist (the room-value proxy, register 2026-09-24). Mitigation: the
  leaf-only missing rule, UNRESOLVABLE for unknown kinds, and a live check
  of the furnished family against known zones before P1's watch goes on.
- **Plan and siting disagree.** A district with no room near its anchor is a
  pass reason and a digest line, flagged not refused under question 1 (c).
- **Logistics starves a workshop.** A link is a restriction; a wrong one
  stops a workshop that worked unlinked. Mitigations: the charter's "link
  only with a reason", the single-class warning, `stockpile.health`, and the
  fort-wide availability fact that keeps supply faults off Logistics' desk.
- **Two roles, one item.** A starved still with no barrels anywhere could
  wake both Logistics and the Quartermaster. The routing fact (available
  fort-wide or not) is computed once and sends it to exactly one.
- **Over-planning.** Set intent, let the game execute: the plan sets
  capacity and chains; links and standing orders are the game's own pull
  mechanisms; nothing here schedules dwarves or hauling.
- **Unverified primitives.** Every stockpile write verb is unverified live,
  and links-only's default polarity is unknown; stage L's live checks come
  before its cutover, not after.
