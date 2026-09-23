# Proposals and checks, now that the loop has run

Date: 2026-09-23. Researcher stream, read-only throughout. No file on VM 103
was written, no tile was designated, no VM was touched, the fort was never
unpaused. All evidence is repo-internal: `docs/AGENT-ARCHITECTURE.md`,
`docs/AGENT-LOOP.md`, `dfqueue/`, `learning/live_signals.py`,
`scripts/dfhack/TOOLS.yaml`, `agents/*/role.md`, and the three live run
records in `evals/live/2026-09-23-*/` plus the one earlier real proposal in
`evals/live/2026-09-14-architect-first-charter/`. No live DFHack query was
needed; every question this brief asks is answerable from committed records
of what has already happened, so nothing here required touching the VM.

## Verdict, stated up front

**This project has already built two different classical check shapes
without naming either of them, and the friction the loop hit so far comes
from using the wrong shape for a given claim, not from either mechanism
being broken.** `dfqueue`'s `prediction` field is a one-shot postcondition,
in the sense design-by-contract and database transactions use that word:
state something, name a deadline, grade it once. The tripwire and vitals
layer (`docs/AGENT-LOOP.md` §3, `df-overseer-clock.lua`) is a continuous
invariant, in the sense property-based testing and control theory use that
word: a condition re-checked on every cycle, with no deadline and no single
grading moment. `proposal-0001`'s void did not happen because postcondition
prediction is a bad idea; it happened because the *deadline* was anchored to
the wrong event (write time, not execution time — fixed since) and because
nobody had yet measured the actual unit the deadline should be denominated
in (ticks at a 100 FPS cap, not wall-clock minutes). The Chair run's sharper
finding is that the project has, so far, defaulted to predicting **mechanism**
(which route produces the outcome) rather than **outcome** (whether the fort
end state is what was wanted), and the Chair run is direct, if narrow, live
evidence that mechanism-shaped predictions can be correct about the fort and
wrong about the story: order id 3 never validated, and the Chair still got
built, by the direct-job route. What can actually be *checked* today is
narrower than what an advisor might want to predict: `scripts/dfhack/
TOOLS.yaml` and `learning/live_signals.py` together define a small, closed
set of readable postconditions (building existence/stage, job presence and
origin, order validated/active flags, item counts by location, zone owner,
vitals thresholds, tripwire/advisory latch state), and nothing outside that
set is honestly checkable no matter how an advisor phrases a prediction. Who
checks is, in every case built so far, code: `dfqueue/grade.py` grades
mechanically, the conductor's stalled-order poller wakes a role mechanically,
and the one place a second *party* is genuinely consulted before a decision
(the Consultant fact-check) is pre-hoc, not post-hoc, and answers a factual
question rather than verifying an outcome. What happens on failure has, in
every real instance so far, been "record and continue" (void, or a graded
`false` row); "escalate" exists as a mechanical record type but has never
fired for real; "revert" is available only as the quicksave, which is
project-wide and destructive of intervening progress, never selective. These
findings are drawn entirely from what has already been built and run; the
open items below are for the user to decide, not resolved here.

---

## 0. Prior art, read before designing anything

Per this repo's standing rule, the problem stated domain-neutrally: an
autonomous agent proposes an action; something must decide whether the
action is allowed, whether it worked, and what to conclude when it did not.
Six fields were named in the brief as worth checking. Read against what this
project has actually built, they split cleanly into two families.

**Design by contract** (Meyer, Eiffel, 1986 onward — general software
engineering knowledge, not independently re-verified against a primary
source this session, since the concept is settled and uncontested enough
that a citation check would not change the analysis). A routine states a
**precondition** (what must hold to call it), a **postcondition** (what it
guarantees afterward), and a class carries **invariants** (what must hold
between any two calls). This maps almost exactly onto `dfqueue`'s existing
shape: `proposal.preconditions` (re-validated at execution time, §7's
"optimistic validation") is the precondition; `proposal.prediction` is the
postcondition, checked once at `due_game_tick`. **What DbC does not have**,
and this project had to invent for itself, is a notion of *who* checks the
postcondition — in Eiffel the same running program checks its own contract
inline. Here the postcondition is checked by a wholly separate component
(`dfqueue/grade.py`, run by the conductor, never by the Overseer that wrote
the ruling), which is closer to the next item.

**Database transactions and ACID.** The precondition/postcondition split
recurs here as constraint checks before and after commit, but the load-bearing
piece for this project is the thing DF does not offer at all:
**`docs/AGENT-ARCHITECTURE.md` §2 states plainly that "DF has no transaction
boundary."** There is no atomic commit, no rollback of a single action, no
isolation between one write and the next. The optimistic-concurrency pattern
(§7, "every action tool re-validates the proposal's preconditions against
live state and refuses if the world moved") is the one piece of the
transactional toolkit that *does* transfer, because a precondition check
before acting costs nothing extra and needs no rollback machinery. Rollback
itself does not transfer: the project's own only real rollback is the
quicksave (§9, "the quicksave is the only real rollback this project has,"
repeated in the brief itself), which is a whole-world snapshot, not a
per-action undo — the DB analogy's most useful export is naming *why*
rollback is off the table here, not a technique to adopt.

**Control theory: setpoint and feedback.** A controller compares a measured
value against a setpoint continuously and corrects the error, with no
notion of "done" — the loop simply keeps running. This is the right shape
for a *quantity that should stay in a band forever*: booze stock, hunger and
thirst vitals, hauling distance. It is the wrong shape for "does this
workshop exist yet," which either becomes true once or never does. This
project's `doctrine/seed.yaml` par-level and reserve-floor material policy
(`docs/AGENT-ARCHITECTURE.md` §4, "Three proposal layers," Strategy) is
exactly a setpoint in this sense, and it is telling that it is explicitly
**not** modelled as a `dfqueue` prediction with a `check_after_ticks`
deadline — it needs continuous re-evaluation, which the current schema has
no way to express (see §4 below).

**Aviation checklists and challenge-response.** One party reads an item
aloud, a second party confirms or performs it, before the next item is
read. The clean analogue in this project is **not** post-hoc outcome
checking at all — it is the Consultant fact-check
(`docs/AGENT-ARCHITECTURE.md` §4, "Consultant fact-check before ruling,"
agreed 2026-09-17, not yet built): the Overseer issues a challenge
(`queue.ask` naming a `proposal_id`), and `queue.rule` on that proposal is
refused until `queue.answer` closes it. That is genuine two-party
verification, but it verifies a **claim in the proposal**, before the
action, never the **outcome after** the action. No challenge-response
pattern exists anywhere in the post-hoc-checking half of this project, and
nothing in the architecture forces one to — see §5.

**Change management: plan, verify, rollback.** The expectation from this
field (ITIL and equivalents) is that every change carries an explicit,
inspectable backout plan before it runs, not just a definition of what
"done" looks like. `dfqueue` has no such field today: `proposal.
preconditions` says what must hold before, `prediction` says what must hold
after, and nothing says what a caller should do if the action partially
succeeds (the Chair building sat `buildingplan`-suspended for most of a day
waiting on a material — a partial, recoverable state this project handled
correctly by inspection, not because any record said what to do about it).
This is a real gap the field names cleanly, even though — see §6 — this
project genuinely has nowhere to put a "rollback" beyond the whole-fort
quicksave.

**Property-based testing: invariants over all inputs.** A PBT invariant is
checked against every generated state, not one designated deadline —
"for all reachable states, P holds," rather than "eventually P holds." This
is precisely the shape of the tripwire and vitals-threshold layer
(`docs/AGENT-LOOP.md` §3): a citizen death, a critical vital, a reachable
hostile are checked **every cycle**, forever, with no `check_after_ticks`
and no grading event. The project independently arrived at the right shape
for this class of check (code, inside the game loop, continuous) without
ever describing it in PBT's vocabulary. Naming it is useful because it
clarifies, precisely, why tripwires and predictions are built as two
separate mechanisms rather than one generalised "check" type: they answer
"for all" and "eventually" respectively, and conflating them (as a
single-deadline `prediction` record would, if used for a vital threshold)
would be a category error.

**What does not fit, said plainly.** Aviation's challenge-response and DB
transactions' atomic rollback both describe machinery this project cannot
build (no second live party checking every action in real time; no undo).
They are useful for naming what is missing, not for a design to adopt
wholesale.

---

## 1. What has a proposal actually been, so far?

Two real proposals exist in this project's history: `p-0001`
(`evals/live/2026-09-14-architect-first-charter/run.json`, ruled
`ruling-0001`, 2026-09-16, **accepted**) and its successor form after the
2026-09-15 signal-registry rebuild (`dfqueue/tests/test_run1_fixture.py`
documents both the old, refused form and the rewritten, passing form). Only
one proposal has ever been written through the live `queue.propose` MCP
tool for real (`proposal-0001`, `handoffs/2026-09-15-queue-live-deploy.md`);
everything else in `dfqueue`'s test suite is a fixture.

**What its shape got right, read from the record itself:**

- Every required field was present and well-formed: `type`
  (`workshop_siting`, from the closed vocabulary — confirmed in
  `evals/live/2026-09-14-architect-first-charter/README.md`'s own
  charter-check pass), `rationale` reasoned entirely in named landmarks and
  directions (zero raw coordinates, grepped and confirmed), a falsifiable
  `prediction` (`landmark."new_workshop".exit."Wagon".distance_tiles" op="lte"
  value="7"`), a named `cost`, a `suggested_priority`, two `preconditions`,
  and a `public_rationale` distinct from the reasoning field. The schema
  did its job: a proposal with a missing or malformed field is refused at
  write time (`dfqueue/schema.py`), so what reached the queue was
  structurally complete by construction, not by the model happening to
  remember every field.
- The prediction's *signal* was gradeable in principle: it named a live,
  mid-fort quantity (a distance between two landmarks), not an end-of-fort
  ledger claim. `dfqueue/README.md` records that this proposal's raw form
  actually **failed** validation once the signal registry was rebuilt
  2026-09-15 to require live signals rather than ledger fields — the
  schema caught a real category error in the very first real proposal, and
  the record of that refusal (and the rewritten form that passes) is kept
  as a test fixture rather than quietly edited away. That is the schema
  behaving exactly as designed.

**What the void exposed, and why it is structural rather than bad luck:**

`proposal-0001`'s `check_after_ticks="1200"` was denominated correctly (in
ticks, per §4's rule that ticks are the only stable unit) but **anchored to
the wrong event**. At write time, `check_after_ticks` was added to the tick
the proposal was written at, not the tick it was actually acted on. Between
the ruling (2026-09-16) and the fort's later unattended unpause, real
elapsed game time on the ruled decision vastly exceeded 1200 ticks before
any execution record existed at all — at the fort's real 100 FPS cap
(not the 5 several early design docs assumed, `docs/AGENT-ARCHITECTURE.md`
§14), 1200 ticks is about 12 seconds of game time, which elapses inside a
single unattended run before a grading cycle could plausibly run at all.
Grading it as written would score **latency between ruling and execution**,
not a verdict on whether the Architect's siting judgment was any good. This
is not a one-off measurement error: it is structural, because nothing in
the original schema distinguished "the clock the prediction runs against"
from "the clock the ruling happened on." The fix (`docs/AGENT-LOOP.md` item
4: "a proposal's prediction window starts at the FIRST `executed` record
referencing its ruling, never at the proposal's own write time") closes
this specific gap by construction — but it was not designed until after the
first real proposal had already been broken by it, and the fix itself has
never been exercised against a real graded outcome, since `proposal-0001`
was voided rather than regraded under the corrected rule. **Whether the
corrected anchoring actually produces a meaningful grade has not been
tested.** This is a real gap, not glossed over: it is inferred from reading
the fix's own description, not observed.

A second, narrower structural issue: the prediction targeted a *mechanism
that had not yet happened* (a not-yet-built workshop's future distance from
the Wagon). That is legitimate under `learning/live_signals.py`'s own
explicit design (`UNRESOLVABLE` is a first-class grading outcome precisely
for this case), but it means the proposal's postcondition and its
precondition were, in substance, the same claim under two names: "this
workshop gets built roughly here" is both what the proposal requests
(via `preconditions`) and what it predicts (via `prediction`). This did not
cause the void, but it is worth naming because §3 below found a sharper,
live example of exactly this conflation mattering.

## 2. What can a check actually read?

Read against `scripts/dfhack/TOOLS.yaml` (2135 lines, 27 tool files) and
`learning/live_signals.py` (the closed registry `dfqueue`'s own predictions
are restricted to). Two different vocabularies exist and they are not the
same size: the *tool* surface is broad, the *dfqueue-prediction* surface is
a small, deliberately closed subset of it.

**Genuinely checkable today, concretely, each grounded in a specific tool
this project has actually run live:**

| Class | Tool / read | What it actually returns | Live evidence |
|---|---|---|---|
| Building existence/state | `df.building.find(id)` direct read (used ad hoc by the Chair run, not yet its own MCP tool) | `btype`, `construction_stage`, `flags.exists`, `#jobs` | Chair run: `exists` flipped `false→true`, `construction_stage` `0→1`, `jobs_n` `1→0`, read three times across the run |
| Job presence, worker state, origin | `stuckjobs.find`, `workjob.list-jobs`, `job.order_id`/`from_order` | whether a job exists, `waiting_on` reason, whether it was spawned by an order or a direct job | Chair run: job 2249 tracked by presence/absence plus a direct `id==2249` lookup, since a vanished job is ambiguous between "finished" and "cancelled" from that read alone |
| Order status | `orders.list` (`validated`, `active`, `finished_year`, `finished_year_tick`, `frequency`, `max_workshops`), `orders.check-duplicate` | whether the Manager validated an order, whether it is running, whether it finished | `evals/live/2026-09-23-order-job-attribution/`: all fields read live and match the design; order id 3 tracked `validated: false` for an entire 900+4483-tick span across two runs |
| Item stock, by location | `stocks.availability ITEM` (`total_item_count`, `available_item_count`, `in_job_item_count`, `in_building_item_count`) | where a specific item type currently sits | Chair run: the one CHAIR item's count moved `in_job → in_building` across the run, the strongest single piece of evidence the build completed |
| Zone ownership, indoor flag | `zone.place`/`check-owner`/`getRoomDescription` | owner unit id, `indoors` boolean | Office run: two zones placed, owner read back twice, `room_description` read `null` both times (see gap below) |
| Unit vitals | `vitals.summary` | `alive`, `dead_total`, `worst_hunger`, `worst_thirst`, `warning_count` | read at every checkpoint of all three 2026-09-23 runs, zero deaths and no threshold crossing recorded honestly each time |
| Tripwire/advisory latch state | `clock.status` | `paused`, `armed`, `tripwire`/`advisory` fields, `abs_tick` | Chair run: distinguished a `slow`-tier advisory (non-blocking) from a `pause`-tier tripwire (blocking) at every window boundary |

**The `dfqueue`-prediction surface is narrower, though not as narrow as this
stream first wrote.** *(Corrected by the orchestrating session on merge, after
checking `SIGNAL_KINDS` directly; the original text said ten signals and
enumerated ten. The correction shrinks the gap this section argues for, so it
is flagged here rather than quietly patched.)*
`learning/live_signals.py`'s closed registry has **twelve** signals:
`fort.population`, `fort.alerts.count`, `fort.stuck_jobs.count`,
`fort.landmarks.count`, `landmark."A".exists`,
`landmark."A".exit."B".distance_tiles`, four `stocks.*.units` signals
(`drink`, `prepared_meals`, `raw_edibles`, `seeds`), and **two added on
2026-09-22** for the Quartermaster
(`handoffs/2026-09-22-loop-queue-quartermaster.md`):
`order."ID".exists` (boolean, backed by `orders.list`) and
`stocks.availability."TYPE".available_units` (integer, any item class
`stocks.availability` knows, which is what generalised the four fixed food
and drink buckets).

Those two change the picture in the two places it matters most to this
document. The Chair run's strongest single piece of evidence, the CHAIR
item's count moving as the build completed, **is** expressible as a graded
prediction today via `stocks.availability."CHAIR".available_units`. And a
manager order's *existence* is predictable, so an order completing and
vanishing can be predicted as `op="not_exists"`, though the module's own
docstring is careful that this project has never watched a real order
complete and vanish, so such a prediction rides on documented but unwitnessed
engine behaviour.

What remains genuinely outside the vocabulary is still substantial:
**building state, job origin (`order_id`), an order's `validated`/`active`
status as distinct from its existence, and zone ownership** are all
**readable by a tool call, but not legal `prediction.signal` strings**. An
advisor could not today write a mechanically graded prediction that a
specific building will exist, that a specific order will *validate*, or that
a specific job will carry a specific `order_id`. Those are the gap that
questions 4 and 5 below turn on, and the order-status one is exactly the
prediction the Chair run would have falsified.

**Concrete, honest gaps — where a check cannot yet be evaluated, which is
worse than no check because it reads as a guarantee:**

- **"Is the office sufficient" is not directly checkable.** `room_description`
  read `null` on both office zones, both times, immediately after placement
  and after a 900-tick window. There is no tool that reports DF's own
  internal room-value score directly; the only available proxy is whether a
  dependent order (`ConstructThrone`, `required_office: 1`) later validates,
  which is itself confounded by whatever else is competing for the Manager's
  attention (`evals/live/2026-09-23-chair-completion-run/README.md`'s own
  finding: the office question "is not settled, and this run adds real
  evidence against one branch of it, not for it"). A check phrased as "the
  office is sufficient" would today have to be phrased as a proxy
  ("order 3 validates within N ticks"), and the proxy is known to be
  confounded by a fact this project has already observed live.
- **No timing baseline exists for any threshold this project has set.** The
  stalled-order poller's 1200-tick threshold
  (`handoffs/2026-09-23-stalled-order-poller.md`) is explicitly "reasoned,
  not measured" — no order has ever gone `active` on this fort, so there is
  no real distribution to check the threshold against. The same is true of
  the threat-tier classifier's distance/decay numbers
  (`research/2026-09-23-wildlife-threat-classes.md`). A check against an
  unmeasured threshold is checkable mechanically (the comparison itself is
  a real read) but its *calibration* is unverified, which is a distinct and
  narrower failure than "cannot be read at all."
- **Breach/flood has no reliable signal at all**, confirmed again this
  session by re-reading `research/2026-09-23-flood-relevance-and-traffic.md`:
  the `update_liquid` flag is real and DFHack's own `flows` tool agrees with
  this project's own detector, but whether it reliably sets and clears
  during genuinely active flow (as opposed to a settled, known water source
  like the Well) remains unverified — there is no real breach on this fort
  to observe. Any check phrased in terms of flooding is currently guessing.
- **`job.order_id`'s populated shape on a real order-spawned job has never
  been observed.** The field exists, the code path that reads it is
  source-confirmed, but no order on this fort has ever produced a job, so
  whether the field actually carries the right id when it matters is
  inferred from source, not from a live positive case. This is exactly the
  class of gap the brief warns about: a check that reads as a guarantee
  ("job attribution works") when what is actually true is "the code that
  would attribute it has never fired."

## 3. What did the three live runs show about predictions?

The Chair run (`evals/live/2026-09-23-chair-completion-run/README.md`) is
the sharpest evidence this project has produced on the mechanism-versus-
outcome question, and it resolves cleanly in one direction: **predicting
the mechanism would have been wrong; predicting the outcome would have been
right, and only the outcome prediction would have told the truth about what
the fort actually needed.**

The exact counterfactual the brief asks about is stated in the run's own
words: "If a proposal had predicted 'order id 3 goes active', it would have
been wrong, and the fort would still have got its Chair by another route."
This is not hypothetical — it is what happened. Order id 3
(`ConstructThrone`, created specifically to supply the Chair building's
missing material) sat `validated: false, active: false` for the entire
Chair run, including roughly 3600 real ticks *after* the direct job had
already finished the identical production the order was asking for. A
mechanism prediction anchored to that order would have graded `false` on a
fort that, by every outcome measure, succeeded: the Chair building now
reads `flags.exists: true`, `construction_stage: 1`, and the one CHAIR item
moved cleanly from `in_job` to `in_building`.

**But the mechanism failure is not noise — it is the more useful finding of
the two, and an outcome-only prediction would have buried it.** The run's
own write-up says this plainly: "The Chair's completion is not evidence the
office is sufficient — it is evidence the direct-job route works
independently of the office, which is a different, narrower claim than the
one `docs/AGENT-LOOP.md` still has open." An advisor that only ever
predicted "does the fort get a Chair" would have scored a clean win on this
cycle and never surfaced that the office-and-Manager pathway this project
actually wants to validate (because direct jobs do not generalise — no
Manager, no work-order queue, no prioritisation across many simultaneous
production goals) has still never produced a single real result, three
manager orders and one office deep. This is the strongest counter-argument
against "always predict outcomes, never mechanisms": **outcome predictions
are robust to which of several valid routes fires, but they are also
incurious about it**, and the mechanism this project most wants to learn
about (does the manager-order pathway work at all) is exactly the kind of
question an outcome-only prediction would silently stop asking the moment
any route succeeds.

**Recommendation (marked as such): predict outcomes as the graded claim,
and record the mechanism as an unscored, structured note on the same
record, not as a second scored prediction.** This keeps calibration
(§10 of `docs/AGENT-ARCHITECTURE.md`, per-role/per-type hit rates) meaningful
— it stays anchored to what actually matters to the fort — while keeping
the mechanism question visible for a human or a later analysis pass to
notice "the order route has a 0% real-production rate across N attempts"
without needing a second graded prediction type to carry that finding.
**Strongest argument against this recommendation:** it produces two classes
of claim in one record, and the ungraded one has no calibration story at
all — nothing stops it from silently drifting into noise the way self-
reported confidence already was shown to (`docs/AGENT-ARCHITECTURE.md` §10,
the 2026-08-25 finding that self-reported confidence predicts nothing). If
the mechanism note is never read by anyone, it costs tokens and delivers
the same "vent into a file nobody reads" failure §10 already names for
`vent.md`. The honest resolution is that this only works if something
(the learning role from §4's "not built" item, or a human maintenance pass)
actually reads mechanism notes on a cadence, which is not designed yet.

## 4. What is the unit of time a prediction can be made in?

**Ticks, unambiguously, and this is already settled rather than open.**
`docs/AGENT-LOOP.md` §2 states the fort runs at 100 FPS (not the 5 several
early design docs assumed), so wall-clock minutes are meaningless as a
prediction unit — the same 1200-tick window that voided `proposal-0001`
is about 12 seconds of game time at full speed. Every mechanism this
project actually uses (`check_after_ticks`, the stalled-order poller's
threshold, the tripwire hunger/thirst defaults) is denominated in ticks,
and `dfqueue/grade.py`'s `game_tick_from_overview` derives one absolute,
monotonic tick count (`year * 403200 + tick`) specifically so a prediction
stays comparable across a year boundary. This part of the design is not in
question.

**What the brief's question is actually asking, read against the evidence,
is a different one: not "what unit is a deadline measured in" (ticks,
settled) but "what unit should the *cadence of checking* be measured in."**
The two live unattended runs (`evals/live/2026-09-23-office-and-first-real-
build/`, the Chair run) both used a **bounded-window pattern**: at most N
ticks per window, quicksave between windows, a fixed set of reads repeated
at every window boundary regardless of whether anything changed. This is
not the same thing as a `check_after_ticks` deadline — a window boundary is
an operational checkpoint (safety envelope, human-legible progress report,
a point to re-confirm nothing silently went wrong), while a prediction's
`due_game_tick` is a semantic claim about when an effect should be visible.
**Recommendation: keep these as two separate axes, not one.** A prediction's
deadline stays in ticks, because that is the engine's own native unit and
because it must survive whatever `base_fps` is set to
(`docs/AGENT-LOOP.md` §2: "every rule below is written in ticks, so it
holds whatever `base_fps` is set to"). Windows stay as an **operational**
unit — a count of bounded runs, each with its own tick cap and its own
quicksave — because that is the pattern that has actually held up in
practice, twice, without a single instance of losing track of fort state.
**Strongest argument against keeping them separate:** it adds a second
vocabulary a human reading the record has to translate between ("due at
tick 12611099" versus "checked every window") when a single "N windows"
unit might read more naturally to a person watching the fort and would tie
a prediction's deadline to the same safety cadence the runs already use.
The counter to that counter is that a window's length is itself a run-time
decision (2000 ticks in the runs so far, but nothing forces that to stay
fixed), so a prediction anchored to "N windows" would silently mean a
different number of ticks depending on what window size a later run chose
— exactly the kind of anchoring ambiguity that broke `proposal-0001` in
the first place.

## 5. Who checks, and when?

**Today, in every real instance, checking is entirely code's job**, and
this is forced more strongly than the brief's framing ("writer, peer, or
conductor's code") suggests, because two of those three options are close
to structurally unavailable.

- **The writer checking its own work (self-report) is explicitly excluded
  by design**, not merely undesirable in this instance. Principle 6
  (`docs/AGENT-ARCHITECTURE.md` §1): "Confidence is stated by tools and
  measured from outcomes. It is never self-reported into a decision." The
  Overseer's own `queue.executed` record ("actions... and its outcome") is
  the closest thing to self-report that exists, and it is explicitly framed
  as a write-ahead log entry (§9, crash-consistency), not as the
  authoritative grade — the record of *what was attempted*, never the
  record of *whether it worked*. Grading against `prediction` is a wholly
  separate, later, mechanical step (`dfqueue/grade.py`), run by the
  conductor, never by the Overseer.
- **A peer checking (an advisor verifying another advisor's, or the
  Overseer's, outcome) is not built, and principle 8 makes it an unusual
  shape to build.** "A role is defined by its tool allowlist" — every
  advisor's allowlist is read-only by construction (§2: "Specialists...
  no, propose only"), so a peer *can* read enough to observe an outcome
  (all the tools in §2's table above are already granted to at least one
  advisor role), but nothing routes that observation back into a grading
  decision today. The one genuine peer-verification mechanism that exists,
  the Consultant fact-check (`queue.ask`/`queue.answer` naming a
  `proposal_id`), checks a **claim inside the proposal before it is ruled
  on**, never an **outcome after it was executed**. Building a post-hoc peer
  check would mean either widening an advisor's role to write a `check`
  record (a new write path, which principle 2's "one writer" argument
  would need to be revisited for, not casually extended) or having the
  Overseer solicit a peer opinion after the fact via another `ask`, which
  the schema already supports mechanically (any `ask` proposal_id could, in
  principle, be a post-hoc one) but which nothing in `docs/AGENT-LOOP.md`'s
  triage rules currently triggers.
- **Code checking (the conductor, or a mechanical grader it calls) is what
  is actually built, in both places this matters:** `dfqueue/grade.py`
  grades every `prediction` whose `due_game_tick` has arrived, every cycle,
  with no model call; and `conductor/order_watch.py`'s stalled/blocked-order
  poller is exactly the same shape for a claim `dfqueue` cannot express at
  all (an order's status, not a `dfqueue.prediction.signal`). Both are
  forced into this shape by the same argument principle 4 already makes for
  reflexes generally ("Speed comes from precommitment, not from more
  actors... a precompiled reflex is milliseconds"): grading and stalled-
  order detection are deterministic reads with a threshold, and running
  them as a model call would be nondeterministic and expensive at something
  code does exactly, the same argument §3 already used to reject an
  "efficiency analysis" agent.

**Where the answer is forced by principle 8, stated explicitly as the brief
asked:** the allowlist, not the charter, is the real boundary, and every
advisor's allowlist today is read-only by construction. A "peer checks the
outcome" design is not merely undesirable, it requires either a new write
path (widening single-writer) or routing every post-hoc check through the
Overseer as another fact-check-shaped `ask`, which is available today but
unused for this purpose. Nothing about the tool surface prevents building
this; nothing in the triage rules currently calls for it.

## 6. What should happen when a check fails?

Four options have real support in the prior art read for §0. Ranked by how
much this project can actually do, today, with what exists:

1. **Record and continue.** This is the option every real instance in this
   project's history has actually used. `store.void_prediction` (admin-only,
   not a role tool) is the mechanism used on `proposal-0001`; a normal
   `graded_false` row is the mechanism the schema supports for any future
   miss. Both leave the record visible with its reason rather than deleting
   anything (`dfqueue/README.md`: "voiding keeps the record visible with
   its reason rather than deleting anything"). This is cheap, always
   available, and matches control theory's own "the loop simply keeps
   running" shape — a single failed check is an error term, not a crisis,
   unless it recurs or compounds.
2. **Escalate.** A real record type (`escalation`, `queue.escalate`,
   Overseer-only) exists and is designed to leave the fort paused for a
   human (`dfqueue/README.md`: "so `conductor/cycle.py` can detect it
   mechanically... and leave the fort paused"). This is the closest
   analogue to change management's "abort and call the on-call" — but it
   has **never fired for real**. Every stop condition the three live runs
   actually hit (the office-and-first-build tripwire, the Chair run's job-
   vanished check) was a **pause**, triggered by the in-game tripwire or by
   an executor's own explicit stop condition, not by `queue.escalate`. This
   is a real gap: the mechanism that exists for "a check failed and a human
   needs to decide" has design and a schema, but zero live exercises.
3. **Replan.** Design-by-contract and change management both assume a
   failed postcondition triggers a revised plan, not merely a recorded
   miss. `docs/AGENT-ARCHITECTURE.md` §9 names the natural home for this — a
   `plan` record kind, "not built yet... the natural next kind, once the
   Overseer actually executes anything" — and `dfqueue/README.md`
   independently confirms it is still unbuilt as of this pass. This option
   is currently unavailable, not merely unused.
4. **Revert.** **Explicitly named, in this project's own words, as mostly
   off the table.** `docs/AGENT-ARCHITECTURE.md` §2: "DF has no transaction
   boundary." The brief itself states it directly: "reverting a fort action
   is often not possible at all, and that the quicksave is the only real
   rollback this project has." This is confirmed structurally, not just
   asserted: there is no per-action undo anywhere in `scripts/dfhack/
   TOOLS.yaml` (every `mutate`-tagged command is a forward-only action —
   designation, order creation, job queuing — and the one command with
   "cancel" in its name, `orders.cancel`/`workjob.cancel`, removes a
   *pending, not-yet-executed* item, which is precondition-cancellation, not
   postcondition-rollback of something that already happened). The
   quicksave is real, exercised on every single live run this project has
   done, and it is genuinely the only safety net — but it reverts the
   **whole fort**, discarding everything since the last save, not the one
   action whose check failed. Using it as a response to a single failed
   check would be a wildly disproportionate response for anything short of
   a fort-ending event, which is exactly why every live run's actual
   practice has been "quicksave as a checkpoint before risk, not as an undo
   after a miss."

**What this rules out, stated plainly:** a design that expects "revert" to
be a normal response to an ordinary graded miss is designing against a
capability this project does not have and, per the DB-transaction reading
in §0, structurally cannot cheaply build (a per-action undo would need
DF's own save format to support partial rollback, which nothing here
argues is possible). The realistic menu, today, is record-and-continue as
the default, escalate as the rare, human-facing exception, with replan and
selective-revert both requiring new machinery this project has deliberately
not built yet.

---

## Decisions the user actually has to make

Phrased as choices, not as a recommendation dressed up as a summary.

1. **Does a `dfqueue.prediction` stay strictly outcome-shaped, or does it
   grow an unscored mechanism field?** §3's Chair-run evidence argues for
   outcome as the graded claim; the counter-argument is that an unscored
   field with nobody reading it repeats the `vent.md` failure mode. If
   mechanism tracking is wanted, something (a role, or a scheduled human
   pass) needs to be named as its reader before the field is added.
2. **Is a window (bounded-tick, quicksave-delimited) ever the right unit for
   a prediction's own deadline, or does it stay purely operational, never
   semantic?** §4 argues for keeping the two axes separate; the
   counter-argument is a single more legible unit for a human reading the
   record, at the cost of an anchoring ambiguity the same shape as the one
   that broke `proposal-0001`.
3. **Does post-hoc peer checking get built at all, and if so, through what
   path?** §5 found it requires either widening single-writer (a new write
   path for a `check` record) or reusing the existing `ask`/`answer`
   mechanism after execution rather than only before ruling. Neither is
   built; the second is cheaper and does not touch principle 2, but nothing
   currently triggers it for this purpose.
4. **Is `queue.escalate` exercised on the next live run, or does the
   project keep relying on tripwire pauses and executor-defined stop
   conditions as the de facto escalation path?** §6 found escalate has a
   full mechanical design and zero live exercises; the gap between "exists"
   and "has ever fired" is worth closing deliberately rather than leaving
   it to happen by accident on some future run.
5. **Does a `plan` record (write-ahead, replan-capable) get built before or
   after the proposals-and-checks design settles?** §6 found "replan" is
   currently unavailable as an option, not merely unused, and §9 already
   names it as the natural next `dfqueue` record kind. Building it changes
   what "record and continue" versus "escalate" actually cost, so the order
   of operations matters.
