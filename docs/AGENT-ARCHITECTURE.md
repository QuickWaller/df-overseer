# Agent Architecture

How the overseer is actually built: what components exist, who may act, how they
communicate, what they read, and how they learn.

> **Status: design artifact, written 2026-09-12 and revised the same day
> against research. Almost none of this is built.** It is the record of a design
> conversation, not a report on working code. Anything marked **(verified)**
> cites something this project has actually run; everything else is **proposed**.
>
> **All four research briefs are back** (`research/2026-09-12-*`) and are folded
> in throughout rather than appended. They confirmed the central choices (single
> writer, no peer chat, per-agent tool scoping) and broke several assumptions
> (no host spend cap, lane-serialised fan-out, no breach signal, a hostile
> signal that is blind by construction). §14 lists what remains open.
>
> **What exists in code:** `agents/` (the roster, charters and allowlists) and
> the `mcp/` registry and role-scoping layer. **What does not:** the MCP server
> itself, the Sentry, Triage, the queue, snapshots, playbooks, and the two safety
> detectors §14 names as required work.

Companion documents: [`PURPOSE.md`](PURPOSE.md) for the design commitments this
must not break, [`MEMORY-ARCHITECTURE.md`](MEMORY-ARCHITECTURE.md) for the
learning substrate this extends, `decisions/DECISIONS.md` 2026-09-12 rows for
the calls made here and why.

---

## 1. Principles

Eight rules. Everything below is a consequence of one of them, and a change to
one of them invalidates the parts that rest on it.

1. **If it is computable, it is a tool. An agent exists only where there is
   judgment under uncertainty.** This is design commitment #2 restated. It is
   the test applied to every proposed role, and it demoted two of them to code.
2. **One writer.** Exactly one component may mutate the fortress. DF has no
   transaction boundary, so parallel writers would require a reservation layer
   that costs more than it buys at five frames per second.
3. **Specialists propose, the Overseer decides.** Advisors are read-only. Their
   only write is appending a proposal. The chain of command is the mechanism,
   not a metaphor.
4. **Speed comes from precommitment, not from more actors.** An agent round trip
   is tens of seconds. A precompiled reflex is milliseconds. Anything that must
   be fast is decided in advance and executed by code.
5. **Every message is a structured record.** Agents communicate by tool call
   with typed fields, never by prose. The audit log is therefore the
   communication channel itself, not a transcript written alongside it.
6. **Confidence is stated by tools and measured from outcomes. It is never
   self-reported into a decision.** LLM self-assessment is confident and largely
   uncorrelated with truth (`decisions/DECISIONS.md` 2026-08-25).
7. **Prompt size must not scale with fortress size.** A fort at 100 dwarves has
   many times the raw state of one at 15. Any representation that grows with the
   fort will fail exactly when the fort becomes interesting.
8. **A role is defined by its tool allowlist.** Prompts are editable opinions;
   the allowlist is the actual boundary, and it is what makes a role swappable.

---

## 2. Components

| Component | Kind | Runs | May write to the fort |
|---|---|---|---|
| **Sentry** | code | continuously, seconds | yes, reflexes only, from playbooks |
| **Triage** | code | every heartbeat | no |
| **Projection** | code | per cycle | no |
| **Overseer** | model, strongest | when woken | **yes, sole general writer** |
| **Specialists** | models, per role | when woken, concurrently where the host allows (§14) | no, propose only |

Two of the five are code with no model in them. That is deliberate: the
components responsible for keeping the fortress alive and for keeping costs
bounded are the ones that must not be probabilistic.

### Sentry

Code, supervised by systemd alongside the existing DF units. Polls cheap signals
every few seconds and does three things:

- **Executes reflexes** from playbooks when a trigger fires. No model in the
  loop, no pause needed for most of them.
- **Escalates**, using the graded response in §6, up to pausing the game and
  waking the Overseer.
- **Publishes state** (`normal` / `throttled` / `paused`, with trigger, game
  tick and expected duration) as a small JSON file for the stream banner (§8).

The Sentry is the only component whose failure is fatal to the fortress, which
is why it holds no model and why it carries a dead man's handle (§6).

### Triage

Code, one call per heartbeat: read the diff since the last cycle, apply
thresholds, decide whether to wake anyone. **A quiet cycle costs zero tokens.**
Given how little changes in a minute at `FPS_CAP:5`, most cycles should be
quiet. This single component is the main defence against the cost profile that
makes a resident roster unaffordable.

Built on `get_diff_since` (**verified**: live `eventful` callback firing
confirmed, `decisions/DECISIONS.md` 2026-09-11).

### Projection

Code. Takes one snapshot and renders the per-role, per-tier views described in
§5. Deterministic, so it is unit-testable and contributes no variance.

### Overseer

The only agent that acts. Reads Tier 0 signals plus the proposal queue, resolves
conflicts, sets priorities, enforces the work-in-progress limit, writes an
ordered plan, executes it. Also, during quiet cycles, does the deliberate work
that makes fast response possible: **writing and revising playbooks**.

Strongest available model. Its outage is not fatal (§9), so it is the right
place to spend capability rather than reliability.

### Specialists

Read-only advisors, one per domain, run concurrently against a shared snapshot.
Each gets a narrow projection and may call exactly one write tool: `propose`.

**Concurrency is a host constraint, not a free assumption.** openclaw's agent
concurrency is lane-based and its inter-agent send lane is serialised, so
waking five specialists may cost minutes rather than seconds (§14). Read-only
advisors are *safe* to run concurrently, which is a correctness property and
holds regardless; whether they are *cheap* to run concurrently depends on the
host, and currently they may not be. This is what makes the scheduler in §4 a
requirement rather than an optimisation.

---

## 3. The roster

| Role | Owns | Explicitly does not own | Cadence |
|---|---|---|---|
| **Overseer** | Arbitration, priority, the plan, the WIP limit, playbook revision, the calendar | Domain analysis | Woken by Triage or Sentry |
| **Architect** | Rooms, workshops, stockpile siting, smoothing, dig order | Anything military; what to produce | Called |
| **Quartermaster** | Food, drink, seeds, work orders, stock thresholds | Where things go physically | Called |
| **Marshal** | Military posture, burrows, squads, equipment, training; post-fight triage. **Deliverable is playbooks, not live orders** | Real-time tactics (see §11) | Called, and on threat events |
| **Consultant** | DF domain knowledge, wiki and community practice, cited | Any fort-specific decision | On demand only |
| **Chronicler** | The history, written for humans | Any decision at all | Cheap model, per cycle |

**Tool-surface reality check, 2026-09-12.** Two briefs disagreed in emphasis and
both were right. `research/2026-09-12-write-conflict-matrix.md` found that
**this repo** has no work-order or stockpile-settings tools, and that DFHack's
`stocks` and `workflow` are tagged unavailable on this install. But
`research/2026-09-12-dfhack-capability-checks.md` found that **`workorder.lua`
is present and callable**, with a real `create_orders()`. So the Quartermaster
has a genuine path, it just has no tools *yet*.

**DECIDED 2026-09-12, user's call: v1 enables exactly three roles, Overseer,
Architect and Consultant.** These are the three whose tools already exist, so
all three can do real work rather than write proposals nothing can execute, and
it exercises the propose-and-arbitrate loop for real instead of deferring the
architecture's central mechanism. Quartermaster, Marshal and Chronicler keep
their charters and directories but stay disabled, so enabling one later is a
config change (§11). Accepted costs: roughly 3x single-agent token spend, and
the lane-serialisation delay (§14) showing up from day one, **which makes the
§4 scheduler load-bearing immediately rather than at some future scale.**
→ `decisions/DECISIONS.md` 2026-09-12.

Two roles that were proposed and **rejected as agents**, per principle 1:

- **Efficiency analysis.** Idle counts, stalled jobs, hauling distances and
  unlinked stockpiles are deterministic analysis over structured state. It
  became a tool that returns ranked findings. An LLM "running algorithms" is
  nondeterministic and expensive at something code does exactly.
- **Safety veto.** Fort-enders (aquifer breach, magma, unsealed caverns,
  atom-smashing something alive) are enforced as **refusals in the tool layer**,
  not as an agent's remembered vigilance. A guardrail that can be forgotten is
  not a guardrail.

---

## 4. Communication

### The queue is the channel and the audit log

One append-only record per fort. Specialists write proposals to it; the Overseer
writes plans and decisions to it. Nothing else carries meaning between agents.
Because it is the channel rather than a log of the channel, an unaudited
communication is structurally impossible.

### No peer-to-peer chat in v1

Specialists do not talk to each other. If a specialist needs another's input, it
is routed as a request through the Overseer, which keeps it in the log.

**This was flagged as the design's most-likely-wrong call and it survived
review** (`research/2026-09-12-multi-agent-architecture-prior-art.md`, 2026-09-12).
Convergent multi-source evidence: two independent production postmortems both
landed on hierarchical orchestrator-to-worker with no worker-to-worker channel;
a failure taxonomy built on 1,600+ real multi-agent traces with validated
inter-annotator agreement attributes roughly a third of multi-agent LLM failures
to inter-agent misalignment, which is precisely the class peer chat enables; and
a debate-failure paper supplies the mechanism, peers negotiating one shared
answer drift toward conformity more often than toward correctness.

The debate literature's apparent counter-evidence resolves in favour of this
design rather than against it: debate helps for *many independent attempts,
arbitrated afterward*, which is **what a single decider with advisors already
is**, minus the advisors seeing each other's reasoning. It hurts for *peers
jointly negotiating one answer*, which is the shape peer chat would add.

**Two honest qualifications, both from the same brief.**

First, the evidence says "not now, with today's models and coordination
patterns," not "never." Do not read this as a permanent structural prohibition.

Second, and this is a real correction to the flat ban: **incident command
doctrine explicitly permits read-only information exchange between peers while
keeping authority singular.** So the considered v2 relaxation is not peer chat,
it is **read-only cross-advisor visibility without cross-advisor authority**: a
specialist may *see* another's proposal, and still may not negotiate with it or
act on the fort. That is doctrine-backed, cheap, and preserves everything the
ban was protecting. Recorded as a deliberate option, not adopted yet.

### This is a blackboard system, and we had rebuilt only a third of one

The most useful correction the prior art produced. A modern multi-agent stack
that gives agents a shared workspace has reimplemented one third of the classic
blackboard architecture and discarded the other two:

| Blackboard element | Our status |
|---|---|
| Shared workspace | the queue. **Have it** |
| Credibility-weighted contributions | §10's tool reliability tags plus measured track record. **Have it, via measurement rather than self-report** |
| Hierarchical, typed store: observation, interpretation, proposed action kept distinct rather than one undifferentiated transcript | §10's four record types. **Have it, corroborated rather than new** |
| **An explicit, separately-engineered scheduler deciding who acts next** | **Was implicit. Now named below** |

### Scheduling advisors is an explicit decision, not prompt order

Which specialists are woken in a given cycle, and in what order their proposals
are considered, deserves to be a deliberately designed and separately tuned
component rather than an accident of prompt ordering. It lives in Triage.

Two constraints shape it:

- **The economics differ from a classical blackboard.** Its knowledge sources
  were small deterministic experts that could cheaply ask "am I relevant?" many
  times. An LLM advisor cannot be polled that cheaply, so the scheduling
  question here is coarser: **which one or two advisors are worth their token
  cost this cycle**, not which of fifty might contribute.
- **A span-of-control ceiling.** Incident command uses roughly five reports per
  supervisor. Our roster has exactly five specialists under one Overseer, which
  is corroboration rather than design, and the number is a starting guess to
  tune, not gospel. The operative rule is that the Overseer should rarely hear
  from all five in one cycle.

This matters more than it sounds, because a published multi-agent research
system measured roughly **15x the token cost of single-agent**, with token usage
explaining most of the performance variance, and reported the approach
performing **worse on tightly interdependent tasks.** Fortress management is
moderately interdependent. So the roster is not free and not obviously correct:
the scheduler is the component that keeps it honest.

One further transferable finding, from medical multidisciplinary teams:
**arbitration quality is gated by advisor output quality at least as much as by
the arbitrator.** That is the case for enforcing required proposal fields at
write time rather than accepting whatever an advisor volunteers.

### Writes are tool calls; reads are XML

A specialist **cannot emit prose into the queue.** It calls `propose(...)` with
typed fields, validated at write time, and a malformed proposal is refused. That
guarantees the queue is machine-readable forever, and it means schema violations
surface immediately instead of becoming a parsing problem later.

Records are rendered **as XML** when placed into a prompt, which is the form
models handle most reliably.

Proposal record:

```xml
<proposal id="p-0142" role="architect" cycle="317" snapshot="s-0317">
  <type>stockpile_siting</type>          <!-- closed vocabulary, see below -->
  <summary>Site a food stockpile adjacent to the Dining Hall.</summary>
  <rationale>Hauling distance from the still is the largest single
    contributor to current idle-hauler time.</rationale>
  <prediction signal="hauling.still_to_food.tiles" op="lt" value="12"
              check_after_ticks="20000"/>
  <cost estimate="41" unit="dwarf_ticks"/>
  <suggested_priority>4</suggested_priority>       <!-- see note below -->
  <preconditions>
    <requires landmark="Dining Hall" state="exists"/>
    <requires area="candidate_3" state="unclaimed"/>
  </preconditions>
  <public_rationale>The brewers are walking too far. Put the food
    beside the dining hall.</public_rationale>
</proposal>
```

Four fields earn their place:

- **`type` comes from a closed vocabulary.** Without it, every proposal is
  bespoke, no two are ever the same kind of decision, and no hit rate can ever
  accumulate. The whole calibration scheme in §10 fails without this one field.
- **`prediction` is falsifiable and mechanically gradeable**, its `signal` a
  dotted path validated against the ledger's own field registry (**verified**
  mechanism: `learning/predictions/` already validates signals against
  `ledger.store.field_source` and refuses anything not `MECHANICAL`/`DERIVED`).
- **`preconditions`** are what the action tool re-checks at execution time (§9).
- **`suggested_priority` means two different things**, verified 2026-09-12. For
  dig designations, DF's 1-7 is real and `quickfort` exposes it (`#dig` accepts
  `-p 1-7`). For manager work orders there is **no priority field at all**: the
  `manager_order` struct has none, and priority is realised purely as position
  in the ordered `world.manager_orders.all` vector. So the Overseer's "set the
  priority" action is a number in one case and a list insertion in the other,
  and the tool layer must not pretend otherwise.
- **`public_rationale`** is written deliberately for an audience, and is the only
  reasoning field that reaches the public stream (§8).

### Wake events

A **closed** vocabulary, each with a severity and a named owning role, so that no
event can arrive with nobody responsible for it:

`hostile_detected`, `breach`, `cave_in`, `unit_critical`, `migrant_wave`,
`caravan_arrived`, `job_stalled`, `stock_below_threshold`, `season_change`.

**Checked 2026-09-12 against DFHack's real `EventType` enum and the live
install's own enabled announcement types. Five of nine have a real signal, and
the two that matter most for safety are the weakest:**

| Signal | Reality |
|---|---|
| `cave_in`, `migrant_wave`, `caravan_arrived`, `season_change` | **Real**, via the generic `REPORT` event filtered by announcement type, each confirmed enabled by default in this install |
| `unit_critical` | **Real event, no severity judgment.** `UNIT_ATTACK` hands back an actual wound struct; "badly" is our logic over it |
| `job_stalled`, `stock_below_threshold` | Ours already, via `get_stuck_jobs` and threshold polling. Never were events |
| **`hostile_detected`** | **Real but dangerously narrow.** `INVASION` fires only when DF registers an actual invasion. It does **not** fire for an ambush, a lone thief, a sneaking creature, or hostile wildlife turning aggressive |
| **`breach`** | **No signal of any kind exists.** A checked negative, not an unexamined gap: no event type and no announcement type matches. Must be built as a poller from scratch |

Two consequences worth stating plainly, because both are safety-relevant.

**The hostile blind spot is structural, not a bad sensor.** This project already
knows `unit-status hostile` missed a real kea attack. The event layer has the
same blind spot **by construction**, so treating `onInvasion` as coverage for
"a hostile appeared" would reproduce exactly that false-confidence failure. The
Marshal's playbooks cannot rest on either signal as-is: a purpose-built detector
is required work, not a recalibration of something that already exists.

**`breach` is the one trigger with no substrate at all**, and it is also among
the fastest fort-killers (§6). The nearest polling targets are
`df.global.world.flows` and map-block liquid scanning, neither confirmed
sufficient. Until that poller exists, flood response is not covered by anything
in this design.

**Only the Sentry and the Overseer may wake anyone.** Specialists cannot wake
each other, which forecloses wake loops.

Each role keeps **its own cursor** into the diff stream, so a woken specialist
receives "what changed in your domain since you last woke" rather than a general
briefing. Cheaper and sharper, and `get_diff_since` already has the
since-a-point shape for it.

---

## 5. Information architecture

### One snapshot, many projections

**A shared snapshot is not a shared briefing.** One canonical read of the world
per cycle, immutable, stamped with the **game tick** (not just wall clock) and
with the tool versions that produced it. Every specialist in that cycle reads
only from it, through its own projection.

Why the snapshot must be shared: DF keeps running while specialists think. If
the Architect reads at t=0 and the Marshal at t=12s, they write proposals about
two different worlds, and the Overseer cannot tell whether a disagreement is
judgment or timing. The concrete failure: the Architect proposes a room reached
through the east corridor, the Marshal (twelve seconds later, hostile now
visible) proposes sealing that corridor, both are correct at their own read
time, and accepting both digs a sealed room.

Why the projection must not be shared: the Marshal has no use for stockpile
contents, and every token of it costs money and dilutes attention.

Two further payoffs of snapshots, both real:

- **Replayability.** A snapshot plus the proposals it produced is a
  self-contained test case. It is the only way to A/B two models on the same
  situation, because the live world is never the same twice. This is how per-role
  model selection becomes an eval rather than a guess.
- **Archive.** Snapshots are exactly the accumulating experiment data the
  project's public-report goal wants.

### Three tiers, earned

| Tier | Content | Scale | Read by |
|---|---|---|---|
| **0, signals** | Numbers and booleans only. Booze 38, idle 5, alerts 0, stalled 2, food-days 47 | O(1) in fort size | Triage, Overseer by default |
| **1, briefing** | Named-landmark / exits-graph summary, scoped to one domain | O(landmarks) | A woken specialist |
| **2, detail** | Per-unit, per-stockpile, per-job drill-down | O(fort) | Only on a flagged anomaly, on request |

**An agent earns its way down the tiers.** Start cheapest, drill only on
something flagged. Tier 2 is never in a default prompt, which is what keeps
principle 7 true.

Note that **the roster is itself a compression scheme**: six specialists reading
Tier 1 in narrow domains and emitting a paragraph each is far cheaper than one
brain reading everything. The org chart and the token budget want the same shape.

### What the code layer owes the models

Every number a model would otherwise compute, code computes. Specifically:

- **Aggregation**: counts, totals, rates of change.
- **Anomaly detection instead of reporting.** Never 200 job rows; "2 jobs
  stalled beyond 500 ticks".
- **Deltas, not states** (`get_diff_since`).
- **Ranking** (the pattern `find_open_area` and `find_diggable_area` already
  set: ranked, named candidates, **verified**).
- **Thresholding**: continuous state to named conditions.
- **Derived metrics**: food-days remaining, booze-days remaining, hauling
  distance, military coverage. Food-days is the exemplar, one integer replacing
  an entire inventory listing, and arithmetic over many rows is precisely what
  models are worst at.

This is not a new philosophy. It is the perception layer's existing one
(commitments #1 and #3, no rendered map, computed facts asserted in text)
extended from spatial representation to volume.

---

## 6. Urgency: a graded response

Because the fort is an ambient display and a public stream, a frequently frozen
fortress is a failure, not a safe default. So the Sentry has four levels rather
than one:

| Level | Mechanism | Game time | Use |
|---|---|---|---|
| **Reflex** | Playbook, executed by code | runs normally | Anything precompilable: raise the bridge, forbid a breach, route to a burrow |
| **Throttle** | Lower the frame cap (`df.global.enabler.fps`, **verified**) | runs slowly | Thinking time needed, freeze not warranted. But see the tick-window warning below |
| **Pause** | Stop the game | stopped | Urgent *and* not precompilable. Rare, budgeted, logged |
| **Alert** | Notify the human | either | Beyond the roster's authority |

Three notes on the mechanics.

**Throttling works** (**verified** from source: `setfps.lua` writes
`df.global.enabler.fps` directly, and it persists in-process across map loads
though not across a process restart).

**But throttling is not free, and this is a trap worth naming.** DFHack opens
its suspend window **once per simulation tick**, after the tick's own work
finishes (§7). So lowering the frame cap slows the game *and* slows every tool
call the agents make, because each call waits for a tick boundary that now
arrives less often. Throttling therefore trades game speed for agent latency
rather than buying thinking time outright.

**Settled 2026-09-12, from source and confirmed live: pausing does NOT stall
tool calls.** `Core::Update()` has no pause guard around either `doUpdate()` or
the `CoreWakeup.wait()` suspend hand-off; the only pause-aware code on that path
gates a performance metric, not the call. Confirmed live against VM 103 with the
fort paused throughout: ten round trips, all between 0.66s and 1.28s, no stall
and no outlier, with the tick counter correctly not advancing.
→ `research/2026-09-12-dfhack-capability-checks.md` §9.

**But wall-clock latency is the wrong thing to optimise. The currency that
matters is game time elapsed per decision**, because that is what the fortress
experiences. For a cycle that thinks for `T` seconds and makes `k` tool calls at
frame cap `f`:

- Thinking costs **`f·T` ticks**. The game runs while the model thinks.
- Each tool call costs about **one tick**, regardless of `f`, since it waits for
  the next suspend window.
- **Game time per cycle ≈ `f·T + k` ticks.**

Three things follow, and they matter more than a latency comparison:

1. **Throttling really does buy thinking time.** Lowering `f` shrinks the `f·T`
   term linearly, down to a floor of `k` ticks. The price is paid in wall-clock
   by the human watching, not by the fortress. An earlier draft of this section
   claimed throttling "trades game speed for agent latency rather than buying
   thinking time outright", which was wrong, and the error came from measuring
   in the wrong currency.
2. **Pause is the only thing that reaches zero.** `f = 0` means no game time
   passes however long deliberation takes, while tool calls stay fast because
   suspend windows keep opening at render rate.
3. **Choose on the shape of the cycle, not on urgency alone.** A *think-heavy*
   cycle (long deliberation, few calls) benefits from throttling almost
   linearly. A *call-heavy* cycle cannot get below the `k`-tick floor and gets
   much worse in wall-clock (`k/f` seconds of waiting), so pause that instead.

**A fourth consequence, and a real optimisation.** `CoreWakeup.wait()` waits
until `toolCount` reaches zero, so **every suspender pending at the same moment
is serviced in one window.** So `k` *sequential* calls cost about `k` ticks,
while `k` *concurrent* calls cost about **one**. Batching independent reads is
therefore not just token-efficient, it is game-time-efficient, which is an
argument for the single-snapshot read pass (§5) that has nothing to do with
consistency.

Scale note, so this is not over-tuned: at `FPS_CAP:5` a tick is 200ms and the
measured round trips were 0.66s to 1.28s, so **transport overhead currently
dominates the tick wait.** Throttling to `f = 1` makes the tick wait 1s and
flips which term dominates. The arithmetic above only bites at low `f` or high
`k`.

**Pausing is the safe direction while resuming is the sensitive one**
(`Working.md` records that flipping pause state is gated here), so the asymmetry
is deliberate.

How few things are genuinely sub-minute urgent is worth stating, because it is
the reason this tiering works: a siege takes many in-game minutes to cross the
map, starvation takes seasons, mood spirals take weeks. The fast killers are a
short enumerable list: water or magma breach, a dwarf bleeding out, a cave-in,
something already inside the walls. Pausing should be rare **by construction**.

### Playbooks, and why they must be data

The Overseer's quiet-cycle work includes writing contingencies: *if a siege is
detected, raise the bridge, station squads at the entrance, pull everyone inside
burrow Home, resume when clear.* The Sentry then executes with no pause and no
model call. **This, and not extra actors, is the answer to reaction latency.**

A playbook is **structured data, never prose**: triggers, thresholds and actions
as typed fields. A threshold you can tune is a threshold you can learn; a
paragraph of instructions can only be rewritten. And **no reflex retunes
itself**: the Overseer proposes threshold changes through the normal queue,
auditable like any other decision. Silent self-modification would destroy the
ability to explain what the fortress did.

### The dead man's handle

If the Sentry pauses and the Overseer never comes back, the fort freezes
indefinitely, which quietly defeats "runs unattended" and is visible to anyone
watching the public feed. So: **auto-resume on timeout, plus an alert.** A
pause must expire.

### Reflexes are logged, and that is how the threat sensor gets fixed

Every firing records the trigger, the world state at fire, the action, its
measured cost, and a follow-up check. What this yields, honestly:

- **Cost accounting.** Work stopped, dwarves locked out, a caravan turned away,
  hauling halted for N ticks. Directly measurable.
- **False-positive rate.** Fired on `hostile_detected`, and post-hoc the hostile
  was a cavern demon forty z-levels down behind solid rock. Also directly
  measurable, and this matters immediately: `unit-status hostile` is **verified
  unreliable in both directions** (`decisions/DECISIONS.md` 2026-09-11, it
  missed a real kea attack and flagged harmless demons). **The reflex log is the
  dataset that repairs that sensor.** That alone justifies building it.
- **Trigger tuning**, from base rates over many firings.

What it cannot yield: **whether a reflex ever saved the fortress.** That needs a
counterfactual, and the counterfactual harness rests on DF replay determinism,
which this repo records as unverified. Stated here so it is not quietly
overclaimed later.

The practical consequence: since benefit is unprovable and cost is measurable,
**keep the reflex set small and cost-capped.** Unprovable benefit plus
measurable cost is how a system accumulates expensive superstitions.

---

## 7. Write authority

### Single writer in v1

Only the Overseer acts. The argument is not tidiness, it is that DF offers no
transaction boundary: two actors that can both designate and both assign labor
will corrupt each other's work, and preventing that means building reservations
and locking, which is strictly more work than a serial decider and buys nothing
at this tick rate.

### What is sliceable and what is not

The write paths already fall into two classes:

- **Cleanly sliceable: DFHack Lua and quickfort.** `quickfort run -c x,y,z`
  takes an explicit absolute anchor (**verified**, and note the anchor is the
  blueprint's **top-left**, not its centre, a bug this project already paid for
  twice, `decisions/DECISIONS.md` 2026-09-11). No dependence on cursor or screen
  state.
- **Never sliceable: the UI automation path.** `df-overseer-ui.lua` and
  `xdotool` depend on one keyboard, one mouse, one focused screen, one cursor.
  Concurrent menu driving would corrupt input in near-undebuggable ways. If
  parallel writers are ever allowed, **the UI path is a single mutex-held
  resource**, and ideally steady-state play never touches it (it was needed for
  embark, which is one-time bootstrap).

Crossed dependencies that are not cursor-shaped but bite the same way:
designations over overlapping tiles; `autolabor`, which is a **global policy
writer already enabled on the live fort** (**verified**, 2026-09-11) and will
reassign labors a specialist sets by hand; burrows, where military assignment
meets civilian restriction; the manager work-order queue, a single ordered list
where order is the semantics; pause state, global, with a nasty race if one
actor resumes while another assumes frozen; and `dfhack.persistent`, shared
mutable state behind the landmark system.

### If throughput ever justifies carving

Escalate to **single-writer-per-resource**, not to multiple general writers.
Ranked by whether carving pays:

1. **Quartermaster: the clean candidate.** Work orders and stockpile settings
   are a named, separate subsystem, largely disjoint from tiles. Frequent,
   fire-and-forget, no contention if it is the sole writer there.
2. **Marshal: carvable with one documented interlock** (the bridge, which the
   Quartermaster cares about for caravans; and burrows, which meet civilian
   labor).
3. **Architect: the worst candidate.** Touches the most shared state, and is
   slow and rare, so carving it buys the least.

The decisive argument: **carving only pays for a role that is both urgent and
frequent, and playbooks already gave the urgent path its own fast lane.** What
remains is throughput, which has not been measured and should not be pre-solved.

So: v1 single writer; Quartermaster designated first carve-out candidate;
allowlists designed so that carve is a config change rather than a rewrite.

### Resolved 2026-09-12: carving buys safety but no throughput

`research/2026-09-12-dfhack-capability-checks.md` §3 settled the mechanics from
DFHack's actual C++ synchronisation primitive at the matching version tag, and
the answer reframes this whole section.

**Concurrent `dfhack-run` calls are safe.** The RPC server really is
multi-threaded (a thread per client connection), but every actual touch of game
state passes through one `std::recursive_timed_mutex`
(`Core::CoreSuspendMutex`) via `CoreSuspender`, so concurrent writers cannot
corrupt fortress state. Memory safety was never the risk.

**But it is a lock with cooperative hand-off, not a queue, and the suspend
window opens only once per simulation tick.** Three consequences:

- **No ordering guarantee.** `recursive_timed_mutex` offers no fairness, so
  which of several waiting writers is serviced next is neither deterministic nor
  priority-orderable from outside.
- **No throughput win from carving.** Every writer's work serialises against
  every other writer *and* against the tick itself, and the more writers there
  are, the longer each waits. **So partitioning write authority cannot make the
  fortress respond faster.** The throughput argument for carving, which was
  already weak because playbooks handle urgency, is now **dead**: the only
  remaining reasons to carve are organisational, and there are none worth the
  costs listed above. Single writer should be treated as the settled design, not
  as a v1 simplification.
- **It explains an existing mystery.** This is the source-confirmed root cause of
  the 45-80s command-to-effect delay `research/2026-09-11-quicksave-silent-noop.md`
  measured live and could only call "the most parsimonious explanation, not
  independently confirmed." That report's confidence framing should be upgraded.

What source reading cannot settle is measured cycle time under a real roster.
That still needs instrumenting (§14).

Costs of carving, recorded so the trade is explicit: you lose the single
coherent plan, the WIP limit fragments per role so the fort can again accumulate
half-finished projects, and the audit log becomes interleaved rather than an
ordered narrative.

### Staleness: optimistic validation

Distinct from snapshot consistency (§5) and often conflated with it. The
snapshot is stale by the time the Overseer acts, so **every action tool
re-validates the proposal's `preconditions` against live state and refuses if
the world moved.** That is optimistic concurrency, and it is the cheap version
of the locking layer we declined to build.

---

## 8. The public reasoning stream

The project's own position is that the distinctive content is the reasoning
beside the image, not the image. A fort where you watch six specialists argue and
an overseer rule on it is better viewing than a fort that merely moves.

**Publish the structured stream, not raw thinking.** Raw chain-of-thought is
long, repetitive, poor content, and it is where accidents live: tool errors carry
file paths, stack traces carry host details, and this is a public page in a
project that keeps infrastructure specifics out of a public repo on purpose.
The queue is already structured, so the public feed is a *rendering* of it, at
near-zero extra cost.

Three conditions, all load-bearing:

1. **Allowlist the fields published. Never regex-redact a firehose.** A denylist
   fails silently, and silent failure on a public page cannot be walked back.
   Published fields: `role`, `type`, `public_rationale`, the decision and its
   priority. Nothing else.
2. **Delay it** by thirty to sixty seconds, so a filter can run and a kill
   switch exists.
3. **Sentry state is published too**, so a throttle or pause reads as visible
   deliberation ("Overseer is deciding: siege response") rather than as a crash.

Mechanism: the Sentry's status JSON plus a queue rendering, read by the existing
stream page beside the noVNC frame. Deliberately **outside the game**, because
anything drawing into DF's window is a write path into the thing we are
observing, and this project has been bitten by input-path surprises before. A
DFHack in-game overlay would look better and is question 2 of the capability
checks.

Publishing is outward-facing, so it needs explicit go-ahead and its own register
row at the time, not merely this design note.

---

## 9. Reliability

**The Overseer does not need to be the most survivable component, because its
outage is not fatal.** A fortress that makes no decisions for six hours is fine.
A fortress with no watchdog is not.

So reliability is held by code under systemd: the Sentry, save rotation, the
existing DF units. The agent host sits above that floor and may crash. This
inverts the intuition that the brain should be the sturdiest thing, and it is
why the Overseer seat takes the most capable model rather than the most reliable
host.

**The survival property that actually matters is crash-consistency, not
uptime.** The damaging failure is dying halfway through applying a plan, leaving
the fort in a state nobody recorded. So the Overseer **writes its ordered plan to
the queue before executing, and marks each step done as it goes**: the queue is
a write-ahead log. A crash mid-plan is then recoverable and re-application is
detectable. That buys more real survival than any choice of host, and it is ours
to build rather than something to select for.

---

## 10. Recording and learning

### Four record types, which must not be conflated

| # | Type | What it is | Written by |
|---|---|---|---|
| 1 | **Snapshots** | What the world was. Immutable, replayable | code |
| 2 | **Queue** | What was decided, by whom, why. Audit trail and write-ahead log | agents, via tool calls |
| 3 | **Outcomes** | What happened next. Mechanical fields, graded by the game | code |
| 4 | **Doctrine** | What we now believe. Small, budgeted, loaded into prompts | **derived from 1-3** |

The failure mode is letting 4 be written directly from an agent's
self-assessment. **Only 1 to 3 are recorded; doctrine is derived, and its size
is capped**, because the compliance eval found perfect-response rate collapsing
toward zero well past a few dozen simultaneous rules (**verified for
`deepseek-chat`**: 0% at n≥40, `evals/compliance/`, 2026-09-11). That is the
existing "outcome tracking, not self-critique" rule made operational for a
roster instead of a single brain, and it is also a real argument *for* the
roster: six small charters each clear a cliff that one combined charter would
not.

### Confidence in facts comes from tools, not models

A tool knows its own reliability, and asking a model to re-guess it per call
produces noise. So every tool output carries a reliability tag, extending the
vocabulary `learning/ledger`'s `field_source` already uses:

| Tag | Meaning |
|---|---|
| `MECHANICAL` | Read directly from game state. Trust it |
| `DERIVED` | Computed from mechanical inputs. Trust it if they hold |
| `HEURISTIC` | A guess with known error modes. Cite with caution |

Agents **inherit** stated reliability rather than inventing it. The learning loop
is then mechanical and central: when the reflex log shows the hostile sensor has
a high false-positive rate, you change **one line in `TOOLS.yaml`** and every
agent's view improves at once. `unit-status hostile` is the first `HEURISTIC`
entry, and it is already evidenced.

### Confidence in proposals comes from measured track record

Do not ask a model for a confidence number. Numbers like that cluster around 80
and predict nothing, and averaging them into decisions produces a field that
looks rigorous and is not.

Instead: every proposal carries a **falsifiable prediction** (§4), graded
mechanically against the ledger. Then **the confidence that matters is the
measured historical hit rate, per role and per proposal type**: *the Architect's
`stockpile_siting` predictions have held 11 of 13; its `workshop_siting`
predictions 3 of 9.* That is earned confidence, fully mechanical, and the
Overseer weights proposals by it. It answers "learn what deserves confidence"
without any agent introspecting at all.

This is why `type` must come from a closed vocabulary. Bespoke proposal types
never accumulate enough samples for a rate, and the scheme yields nothing.

Self-reported confidence may still be **captured as a field to be graded, never
as an input to a decision.** We are logging everything anyway, so it costs
nothing to discover whether a given model's stated confidence predicts its own
hit rate. If it turns out calibrated for some role, start using it then. That is
a cheap experiment and publishable material for the report.

### How calibration is actually scored

From `research/2026-09-12-multi-agent-architecture-prior-art.md`, which asked
which of these methods are affordable at the data scale one fortress produces:

| Method | Verdict |
|---|---|
| **Brier score plus a coarse reliability diagram** | **Adopt now.** Cheap, and fits the planned ledger as it already exists |
| **Track-record weighting**: an advisor's future influence scaled by its historical score | **Adopt next.** Cheap, and closer to the well-replicated basic-feedback-loop finding than to heavy aggregation machinery |
| **Reference-class forecasting, formal recalibration curves** | **Explicitly deferred.** Strong in their home domains, but they need far more history than this project will have for a long time. Recorded as deferred rather than quietly built |

This resolves what looks like a contradiction with the rule above. Brier scoring
needs a **stated probability**, so advisors do attach one to each prediction.
That is not a reversal: the probability is **scored, not obeyed**. Scoring it is
precisely how we find out whether it deserves to be obeyed, which is what "a
field to be graded" meant. Track-record weighting is then the mechanism by which
*earned* confidence, and only earned confidence, influences a decision.

Note also that this is the blackboard architecture's credibility-weighting
element (§4), satisfied by measurement rather than by self-report.

### Scoping

One shared ledger, because a fortress has one history. Lessons carry an owning
role, so each agent loads its own plus universal doctrine and stays under
budget. Generalisation across forts is already handled by the hierarchical
partial-pooling design (`research/2026-08-25-learning-architecture.md`) rather
than by hand-sorting lessons into buckets.

**Honest prerequisite:** `learning/predictions/` grades only ledger-backed
signals, and the **fort dossier (mid-fort state) is still uncoded**, which is why
the design's own "food stores" example cannot yet be expressed
(`ROADMAP.md`, 2026-09-11). **The dossier is the gating piece for any per-cycle
learning**, not anything about the roster.

### Vent and friction: a separate pipeline, different destination

Two streams, because self-report alone will not find tool gaps. Models vent
about the wrong things: they blame themselves for a broken tool, or are politely
vague about a real blocker.

| Stream | Nature | Use |
|---|---|---|
| `vent.md` | Subjective, free-form, cheap | **Hypothesis generator** about tool gaps. Never evidence |
| `friction.jsonl` | Mechanical, from the tool-call log | Failed calls, retry loops, gave-up-after-N, tools never called by a role that has them |

An agent that vented nothing but hit the same tool fourteen times is the real
signal, and only the mechanical stream sees it.

**These feed `ROADMAP.md`, never doctrine.** "The tool is broken" and "the
fortress should do X" are different claims with different evidence standards,
and the pipeline needs a named owner: reviewed per cycle in a maintenance
session and turned into repo work items. Otherwise the roster vents into files
nobody reads.

---

## 11. Modularity

The requirement is that roles can be added, removed and reassigned under human
authority, and that a person can read the setup and understand it. So: one
directory per role, strict file contract, one enabling file.

```
agents/
  ROSTER.yaml              # enabled roles, one line each. The only file you edit to add or remove one.
  overseer/
    role.md                # charter: owns, does NOT own, escalation, refusals
    tools.yaml             # allowlist by id, referencing scripts/dfhack/TOOLS.yaml
    model.yaml             # model, budget ceiling, cadence
    evals/                 # this role's decision suite, run against recorded snapshots
  architect/ ...
  quartermaster/ ...
playbooks/                 # structured data, not prose. Owned by the Overseer, revised through the queue.
runtime/                   # gitignored
  snapshots/
  queue.jsonl              # channel, audit log, and write-ahead log
  <role>/vent.md
  <role>/friction.jsonl
```

Properties this buys:

- **Adding a role is a directory plus one line.** Removing one is deleting that
  line. No code change.
- **Tool allowlists reference the manifest by id**, so the tool surface stays
  single-source and a role cannot quietly gain a capability.
- **A role's charter, its permissions, its model and its tests sit together**,
  which is what makes a role reviewable by a person in one sitting.
- **Read and write allowlists are separable**, which is what makes the
  Quartermaster carve-out (§7) a config change.

### Where this lives, and commitment #5

Design commitment #5 says the brain lives outside this repo. The split that
respects it:

| In this repo | Outside |
|---|---|
| Role charters, tool allowlists, eval suites, playbook schema, the queue schema | API keys, provider config, openclaw's own runtime wiring |

Rationale: charters and allowlists are about the DF domain and this repo's tool
surface, and they port to any MCP-speaking brain, which is the entire point of
the boundary. This also matches the reasoning already recorded on 2026-09-12
about not hand-fitting one brain's conventions ahead of the MCP seam existing.

---

## 12. Explicitly not doing

Recorded so they are not re-proposed without new evidence.

- **One agent per squad, talking to each other.** DF combat resolves in seconds
  while an agent round trip is tens of seconds, so no agent conversation can ever
  be inside a fight. Everything that decides a fight happens before it (burrows,
  stationing, equipment, training, the bridge) or after it (hospital, recovery).
  Compounding reason: the threat sensor is verified unreliable, so a command
  hierarchy built on it would be confidently wrong on a schedule.
- **Peer-to-peer specialist chat in v1.** See §4. Revisit on the prior-art
  brief's evidence, not on preference.
- **Multiple general writers.** See §7. Revisit per-resource, if measured
  throughput justifies it and `dfhack-run` concurrency turns out safe.
- **Self-reported confidence as a decision input.** See §10.
- **An agent that runs efficiency algorithms**, or **an agent that remembers to
  check for fort-enders.** Both are code. See §3.
- **Publishing raw agent thinking.** See §8.

---

## 13. Deployment topology

Decided 2026-09-12. Three VMs, and the split is about trust boundaries rather
than latency, because §14's persistence finding established that locality barely
matters once a connection is held.

| Component | Where | Why there |
|---|---|---|
| DF + DFHack | **VM 103** | Exists. The fort. |
| **MCP server** | **VM 103**, alongside DF | DFHack's RPC socket is local and unauthenticated |
| **Sentry** | **VM 103**, systemd | Polls and fires reflexes; needs to be close and to survive brain outages |
| **openclaw** | **its own new VM** | Holds provider credentials and write authority. Restarted constantly during iteration |
| Public view-only feed, admin VNC | relay VM, unchanged | Already there |

### Why the MCP server stays on VM 103

**DFHack's RPC socket is unauthenticated.** Anything that can reach it has full
scripting control of the game process, so moving the MCP server off VM 103 would
mean exposing that socket across the network. Supporting reasons: the two hops
have opposite traffic profiles (MCP↔DFHack is chatty and tick-gated, openclaw↔MCP
is one batched snapshot per cycle, so keep the chatty hop local); separating them
buys no availability, since if VM 103 is down the server has nothing to serve;
and blast radius does not improve, because an attacker who can reach DFHack's RPC
directly already owns the game host.

### Why openclaw gets its own VM rather than sharing the relay

The relay is the most exposed surface in the estate: a public Cloudflare tunnel
and an unauthenticated view-only feed. openclaw holds **provider API credentials
and write authority over the fort**, so co-locating them would mean a relay
compromise reaches the brain's keys. Also: its memory footprint is unmeasured
(`research/2026-09-12-openclaw-primitives.md`), and it will be restarted
constantly while roles are iterated on, which on the relay would drop the public
feed every time.

### The trust boundary, and two requirements that follow

The boundary is the MCP HTTP endpoint between openclaw's VM and VM 103.

1. **The allowlist is enforced by the MCP server, not by openclaw's config.**
   openclaw's per-agent tool scoping is real and useful, but once the brain and
   the fort are separate hosts at different trust levels it is **defence in
   depth, not the boundary**. Client-side enforcement is not enforcement. So
   `mcp/roles.py` is the authority; the host's `tools.allow/deny` is a second
   layer.
2. **Role identity must be a credential, not a claim.** A self-declared role
   header means the Architect can assert it is the Overseer and obtain write
   tools, which would silently void the entire single-writer design. So: **one
   token per role**, issued at the seam and mapped to a role server-side.

Transport: MCP over HTTP on the tailnet, never publicly exposed. openclaw
supports remote MCP servers with OAuth/TLS, so authentication does not need
inventing.

### Upstream obligation, NOT yet discharged

**Creating openclaw's VM makes `home-lab/inventory/` wrong**, per `CLAUDE.md`'s
upstream obligation. Before it is assigned an address: allocate the IP through
`home-lab/inventory/ips.yaml` (that file is an allocation registry, consult
before assigning), record the guest in `inventory/hosts/SRV-0x.yaml`'s `guests:`
block, and update `inventory/services.yaml` if a service moves. This repo is
**not authorised to edit home-lab**, so it must be routed to a home-lab session.
It should land on **SRV-01**: SRV-02 is currently crashing roughly every 2.5
hours with root cause open.

## 14. Open questions

### Answered by research, 2026-09-12

1. **Does openclaw support per-agent models and per-agent tool scoping?
   YES, both, as real features rather than workarounds.** Named agents under
   `agents.entries.<id>`, each with its own model as `"provider/model"` and its
   own workspace. Scoping comes from three mechanisms: `tools.allow/deny` per
   agent, `sandbox.workspaceAccess`, and MCP-level `toolFilter.include/exclude`
   plus per-server agent allowlists. **Principle 8 is therefore enforceable and
   §11 stands.** This was the design's biggest single risk and it cleared.
   → `research/2026-09-12-openclaw-primitives.md`
2. **Is "no peer chat" well-founded? YES, and it survived review**, with one
   doctrine-backed relaxation identified for v2 (read-only cross-advisor
   visibility without authority). Folded into §4.
   → `research/2026-09-12-multi-agent-architecture-prior-art.md`
3. **Can write authority be partitioned? Partly, and there is already a
   violation in production.** `set_labor` races `autolabor` on ordinary
   citizens today. The Quartermaster hypothesis is **untestable rather than
   confirmed**, because work orders and stockpile settings have no tool surface
   at all. Folded into §7 and §3.
   → `research/2026-09-12-write-conflict-matrix.md`

4. **All six DFHack capabilities settled from source** at the matching version
   tag (53.16-r1.1), five with high confidence.
   → `research/2026-09-12-dfhack-capability-checks.md`
   - **Runtime frame cap: yes** (§6), with a latency trap now documented.
   - **In-game overlay: yes and headlessly drivable** (§8), though whether a
     widget renders correctly in *our* Xvfb/VNC pipeline is the one live check
     still outstanding.
   - **`dfhack-run` concurrency: safe, not ordered, tick-gated** (§7). Killed
     the throughput argument for carving write authority, and confirmed the
     root cause of a previously-unexplained 45-80s command delay.
   - **Priorities: two different mechanisms** (§4), 1-7 for digs, list position
     for work orders.
   - **Wake vocabulary: five of nine real**, `breach` has nothing at all and
     `hostile_detected` is structurally blind to everything but registered
     invasions (§4).
   - **`dfhack.persistent`: no internal locking** (it borrows the same suspend
     convention), a hard limit of **7 integer slots per entry**, and every save
     rewrites an entity bucket's whole JSON file rather than updating
     incrementally. Constrains the landmark store and anything else tempted to
     use it as general state.

### Still open

- **A breach poller does not exist and must be built** before flood response is
  covered by anything here.
- **A real hostile detector must be built.** Neither the polling signal nor the
  event layer covers ambushes, thieves or aggressive wildlife.
- **Two live checks** deliberately not executed by a read-only brief: whether
  the frame cap survives loading a different save in one process, and whether an
  overlay widget renders in this project's headless pipeline.
- ~~Whether `Core::Update` still runs while paused~~ **ANSWERED 2026-09-12: it
  does.** Pausing preserves fast tool calls; throttling does not. §6 revised.
  One caveat recorded honestly: no unpaused comparison was run, so this is
  "paused calls are fast in absolute terms", not a measured paused-versus-
  unpaused gap. The absolute result is what the design needed.

### New constraints the openclaw brief imposed

These are not open questions, they are facts the design must now accommodate.

- **There is no hard spend cap in the host.** Only context-size limits and cost
  visibility exist; the real backstop is provider-side billing caps. So the
  per-role `model.yaml` budget ceiling in §11 **cannot be enforced by openclaw**
  and must be enforced by our own Triage gating plus provider-side caps. Given
  this project already overran $9-13 in one afternoon on an eval, this is the
  single most important operational consequence in the brief.
- **Fan-out is not free.** Agent concurrency is lane-based rather than
  unlimited, and the inter-agent send lane is hardcoded to one concurrent
  operation, so messaging several agents serialises at roughly 30 seconds per
  target. So §2's and §5's "specialists run in parallel" is **conditional, not
  free**: if specialist invocation goes through that path, five specialists cost
  minutes rather than seconds. This makes the §4 scheduler load-bearing rather than an optimisation,
  and it may force sequential consultation of one or two advisors per cycle.
- **The only true external push wake is an authenticated HTTP hooks endpoint.**
  Everything else is heartbeat or cron, with a 30-second floor on condition
  watchers. So **the Sentry reaches the Overseer by calling that endpoint**,
  which is the concrete mechanism §6 needed and did not have.
- **Host crash recovery covers its own conversational state, not external side
  effects.** Nothing found addresses whether a partially-applied fortress
  mutation is detectable after a crash. So §9's write-ahead queue is not
  belt-and-braces, it is **the actual mechanism**, and this project's existing
  quicksave-checkpoint discipline remains the real safety net.
- **Tool-call logs are machine-parseable JSONL** with correlating ids, so the
  mechanical friction log in §10 is buildable without inventing capture. Caveat
  that bears directly on §8: the host's own **log redaction is best-effort**,
  which is exactly why the public feed allowlists fields and never renders host
  logs.
- **Correction to this repo's own prior claim.** The 2026-08-25 register row
  asserting openclaw has exponential retry backoff **does not hold for the
  heartbeat path**, per two issues the brief cites as closed-not-fixed
  documenting linear or uncapped retry storms. Treat heartbeat retry as unsafe
  by default. Recorded as reported-by-brief rather than independently confirmed
  here. The sole-host decision does not turn on it: it turned on the structural
  argument in §9, not on a scheduler comparison.

Not yet gated on anything, and needing a decision:

5. **The MCP server itself does not exist.** `scripts/dfhack/TOOLS.yaml` is a
   first-draft schema, not a server. Everything here assumes the seam, and the
   seam needs per-role scoping designed in from the start, because retrofitting
   identity-aware allowlists later is painful.

   **Three performance requirements, derived 2026-09-12 from the measured
   round trips.** Today's 0.66-1.28s per call decomposes into per-call SSH
   setup, a `dfhack-run` process spawn, an RPC connect, and only then the
   ~200ms tick wait at `FPS_CAP:5`. **The tick wait is the smallest term**, so:

   - **Hold one persistent DFHack RPC connection.** Do not shell out to
     `dfhack-run` per call. This removes both dominant terms and leaves latency
     roughly tick-bound (~200ms at `f=5`), a 3-5x improvement.
   - **Persistence matters far more than locality.** Same-host and same-LAN are
     within a millisecond or two of each other once the connection is held;
     per-call SSH from anywhere is 0.5s+. So co-location is not the lever it
     looks like, and the server may sit wherever lifecycle and resource
     isolation argue for.
   - **Batch a cycle's reads into one suspend window, deliberately.** Every
     suspender pending at the same instant is serviced together (§6), so the
     server should issue a snapshot's reads concurrently rather than in
     sequence: ~1 tick instead of ~`k`. This is the implementation half of
     §5's single-snapshot read pass.

   Keep it in proportion: a model API call is seconds, so for a think-heavy
   cycle 200ms versus 700ms per tool call is noise. It matters for call-heavy
   cycles, where `k=20` is the difference between about 4s and about 14s.
6. **The fort dossier is unbuilt**, and it gates per-cycle prediction grading
   (§10).
7. **Several roster roles have no tool surface at all** (work orders, squads,
   burrows, smoothing). Being enumerated by the write-conflict brief.
8. **Cycle wall-clock, queue depth and urgent-event frequency are unmeasured.**
   Instrument all three in v1 rather than pre-solving a throughput problem that
   may not exist.
