# Manager work orders versus direct jobs: who should own which

Date: 2026-09-23. Read-only research, answering
`research/BRIEF-2026-09-23-work-orders-vs-direct-jobs.md`. No VM changes, no
live writes, no unpause, no deploy. Primary sources read this session: this
repo's own `scripts/dfhack/df-overseer-orders.lua`,
`df-overseer-workjob.lua`, `df-overseer-stuckjobs.lua`,
`docs/AGENT-LOOP.md`, `agents/quartermaster/role.md` and `tools.yaml`,
`agents/overseer/tools.yaml`, `agents/ROSTER.yaml`,
`decisions/DECISIONS.md` (2026-09-12 rows), `research/2026-09-18-work-orders.md`,
`research/2026-09-16-opening-priority-ladder.md`,
`handoffs/2026-09-21-nobles-appoint.md`, `learning/live_signals.py`,
`Working.md`. Web sources (DF wiki, DFHack docs, Steam community threads)
were fetched this session and are cited by URL; every web claim is labelled
**web-sourced** and treated as untrusted data about this install, not fact,
per the brief. Nothing this session reads or claims about this install's own
struct data is a new live call: it is re-reading what the 2026-09-21 `nobles`
stream and 2026-09-18/2026-09-21 research already captured live from VM 103.
No new live call was made this session.

## Bottom line

The two routes are not symmetric alternatives; they trade different things
away. **A manager work order buys conditions, repeat frequency and
dependency ordering, at the cost of needing a Manager with an Office (a real,
install-verified precondition, not merely a wiki claim) and offering zero
feedback when it silently fails to run.** **A direct workshop job buys
independence from the Manager entirely (this fort's only real completed
production used it), at the cost of no conditions, no repeat, no duplicate
detection, and a narrower, hand-maintained job vocabulary (3 kinds versus
12).** Neither route can do something the other categorically cannot at the
DF engine level: both ultimately create a `df.job` at a workshop. The real
asymmetry is capability (conditions/repeat: orders only) versus reliability
today on this specific fort (direct jobs: proven; manager orders: proven
stuck). My recommendation (part E) is to keep both under one `work_order`
proposal type as already designed, not split them, and instead build two
cheap code-level checks that do not exist yet: a duplicate-production check
across both routes' job lists, and a "has this route ever actually worked on
this fort" gate on trusting the manager-order route again.

---

## A. The two routes, mechanically

### A1. Manager work orders

**The office requirement is verified, install-specific, and stronger than
the earlier wiki-only finding suggested.** `research/2026-09-18-work-orders.md`
(2026-09-18, before an Office or a Manager existed on this fort) could only
cite the wiki's own claim that office validation kicks in "once your
fortress reaches 20 citizens" and flagged it explicitly as unconfirmed,
single-source, community_prior. The 2026-09-21 `nobles` appointment stream
then **read the MANAGER position's own struct fields live** on this
install: `requires_population 0`, `required_office 1`, description text "the
manager must work in an office to validate work orders"
(`handoffs/2026-09-21-nobles-appoint.md`). **Verified from this install's own
data**: the office requirement is not population-gated at all on this
build's own position struct; it is present at `requires_population = 0`. The
20-citizen figure the wiki gives (**web-sourced**,
[DF2014:Manager](https://dwarffortresswiki.org/index.php/DF2014:Manager),
fetched this session: "Once your fortress reaches 20 citizens, work orders
will not be performed until they are validated by the manager") most likely
describes a *different* gate: whether jobs can be dispatched **without** any
manager at all below that population, not whether an *appointed* manager
needs an office. Those are two separable claims that the earlier report
conflated; this session's install-level read only speaks to the second. Not
independently resolved: whether Uniboslan (22-23 citizens, over the
wiki's 20-citizen line already) would behave any differently below that
line — moot for this fort's current population either way.

**What the Manager does with an order (web-sourced, DF wiki
[Manager](https://dwarffortresswiki.org/index.php/Manager), fetched this
session):** validates queued orders from the office, "gain[s] experience
when validating the order, not when the order is finished." **Not
independently confirmed** against this install's code: `create_orders`
(`workorder.lua`) never writes `status.validated`/`status.active`
(`research/2026-09-18-work-orders.md` §6, source-read), so validation is
something the engine does at runtime, off a code path this project cannot
read (closed-source binary).

**Struct-level validation/approval mechanics, verified by direct source read
this session (carried from `research/2026-09-18-work-orders.md`, re-checked
against this session's other findings, not re-derived):** `manager_order`
carries `item_conditions` (compare op, item/material/flags, reaction-product
matching), `order_conditions` (a real dependency edge between two orders:
"activate only if order X is Completed/Activated"), and `frequency`
(`NONE/OneTime/Daily/Monthly/Seasonally/Yearly`, a plain enum). **No
priority field exists on the struct at all** (full field read,
`decisions/DECISIONS.md` 2026-09-12 row 222). No manager-skill requirement
was found anywhere in the position struct or in `create_orders`; the only
readable requirements are `requires_population` and `required_office`
(nobles handoff). This is a checked negative, not an assumption: skill was
looked for and not found, not simply unexamined.

**Live, install-verified result (`handoffs/2026-09-21-nobles-appoint.md`):**
manager appointed, no Office exists (the fort has no zones at all), three
pre-validated orders (`ConstructBlocks`, `ConstructMechanisms`,
`BREW_DRINK_FROM_PLANT x8`) sat `validated=true active=false` through a
3,900-tick supervised unpause, no job of those types ever appeared, and the
game raised **no announcement of any kind** mentioning manager, office, or
work order. This is the strongest single finding in this report: it is not
merely "orders haven't run yet," it is "the game gives zero observable
feedback that anything is wrong." The office is the leading suspect
(matches the position's own `required_office` field and the user's own play
experience, per `CLAUDE.md`'s status block) but is **not yet causally
proven** — no Office has been built and assigned to test the fix.

### A2. Direct job creation

`df-overseer-workjob.lua`'s `queue_job` reproduces `idle-crafting.lua`'s
`makeRockCraft` sequence (`dfhack.job.createLinked` → populate `job_items`
→ `dfhack.job.assignToWorkshop`), cited to the exact DFHack source files in
the script's own header (verified this session by re-reading the header
against the committed source, not re-derived). This **bypasses the Manager
system entirely**: no `manager_order` struct is touched, no validation step,
no conditions, no `order_conditions` dependency, no `frequency`/repeat
field. Concretely, what the game does *not* do for you on this route,
verified by reading what the tool itself does and does not set:

- **No conditions.** A direct job either has the raw materials it needs
  right now (via its `job_items` spec) or it does not; there is no
  "wait until X is true" mechanism at all.
- **No repeat/standing order.** Every `workjob.queue` call is exactly one
  job. `Working.md` START HERE item 4 notes DFHack's `workshops.getJobs`
  exposes a live job's own `repeat` flag as a real, readable/writable
  primitive ("a standing order with no manager") but `df-overseer-workjob.lua`
  does not read or write it today — a real, named gap, not yet built.
- **No material reservation beyond the job's own `job_items`.** The
  `job_item` fields (`item_type`/`mat_type`/`quantity`/`flags3`) are the
  same reservation mechanism a manager-order job uses once it spawns; the
  difference is only that a direct job's `job_items` are hand-built by this
  project's own code (`fixed_boulder_job_item`/`reagent_job_item`) rather
  than derived from a raw reaction by the engine. No project code stops two
  `workjob.queue` calls from both reserving against the same scarce
  material.
- **No workshop distribution.** `queue_job` always targets one named
  workshop; there is no equivalent of the Manager's own behaviour of
  spreading a job across every matching workshop (see B below).
- **No duplicate detection.** Nothing in `queue_job` checks whether an
  equivalent job already exists at the target workshop or elsewhere; the
  only guard is `MAX_WORKSHOP_JOBS` (10), a queue-depth cap, not a
  semantic duplicate check.
- **No validation step of any kind**, which is the whole point (this is the
  route that sidesteps the Manager/Office requirement, per the file's own
  header: "a player can queue a one-off job directly at a workshop by
  clicking it... Manager orders are a QUEUE that needs a Manager to
  approve; a direct job at a workshop is not in that queue and never was").

### A3. Reachability and asymmetric coverage

Neither route can build a workshop, dig, place a farm plot, or place a zone
(`research/2026-09-18-work-orders.md` §4: "not manager-orderable at all,
needs a designation or a direct build instead"); direct jobs share this
limit (`df-overseer-workjob.lua` also requires an existing, already-built
workshop, verified in `resolve_workshop`). At the DF-engine level both
routes converge on the same primitive: a `df.job` attached to a workshop.
**What differs is this project's own tool coverage, not engine capability**:
`orders.create` (manager-order route) has 12 job kinds wired
(`blocks/mechanisms/barrels/brew_drink/bucket/bed/door/table/chair/splint/
crutch/soap`); `workjob.queue` (direct route) has 3
(`blocks/mechanisms/brew_drink`), and its own header names the missing
generality directly: "structured for a later job to be a new table entry,"
not yet generalised. `Working.md` START HERE explicitly lists `workjob` as
one of the tools that does not yet meet `CLAUDE.md`'s "tools must be
generalisable" rule, alongside `workshop` and `orders.create`.

---

## B. Priority and ordering

**At least three distinct DF/DFHack priority mechanisms exist, confirmed
separately, not one concept wearing different names:**

1. **Dig designation priority, 1-7.** Already known to this repo
   (`decisions/DECISIONS.md` 2026-09-12 row 222): `quickfort`'s `#dig`
   blueprints accept `-p 1-7`. Digging only.

2. **Manager order list position.** `manager_order` has **no priority
   field at all**, confirmed by a full struct field read
   (`decisions/DECISIONS.md` 2026-09-12, same row). Ordering among queued
   orders is purely position in the `world.manager_orders.all` vector.
   **Web-sourced**, DFHack's `orders` plugin docs
   ([orders](https://docs.dfhack.org/en/latest/docs/tools/orders.html),
   fetched this session): `orders sort` reorders the list by *frequency
   class only* (one-time first, then yearly, seasonally, monthly, daily)
   specifically so repeating orders "don't prevent one-time orders from
   ever being completed" — this is a scheduling-fairness sort, not an
   urgency/importance ranking, and it is a separate command this repo's
   `df-overseer-orders.lua` does not currently wrap.

3. **A per-job priority integer, native to `df.job` itself.** This is the
   mechanism the brief's "check whether there are more" instruction was
   looking for, and it is not one this repo's own docs currently name.
   **Web-sourced, moderate-high confidence** (DFHack docs,
   [do-job-now](https://docs.dfhack.org/en/latest/docs/tools/do-job-now.html)
   and a recent PR merging it into `prioritize.lua`, fetched this session):
   "the 'do job now' flag gives the job it's applied to a 10,000,000
   priority boost." Applying it to a selected *work order* boosts every
   job **currently active** from that order, but not future ones —
   meaning this field lives on the individual `df.job`, not on the
   `manager_order` that spawned it. This is a genuinely separate axis
   from list position (#2): it governs which of several already-spawned,
   competing jobs a workshop or worker attends to first, not which order
   the Manager validates first. **Neither `df-overseer-orders.lua` nor
   `df-overseer-workjob.lua` reads or writes this field today** — a real
   gap this session did not find named anywhere else in the repo.

**Workshop "profiles" and restrictions: the repo's implicit assumption is
stale, and the current mechanism is different and unwrapped.** **Web-sourced**
(DF wiki Manager page, fetched this session): "Workshop Profiles" (an older
feature restricting which labors a workshop's jobs could draw on) were
**removed** in current versions. What exists now is a plain per-workshop
toggle, "General work orders allowed" (0/1), which stops the *Manager*
specifically from assigning tasks to that workshop — used because "when
several workshops can fulfill the same job, the manager will distribute the
jobs amongst all those workshops," which can fragment dedicated production.
This toggle is **not readable or writable by any tool in this repo**;
`workshop_exists_count` (`df-overseer-orders.lua`) only counts matching
workshops, it does not check whether any of them has orders disabled. It
also **does not affect the direct-job route at all**: `workjob.queue`
targets one named workshop explicitly, so the Manager's distribution
behaviour (and this toggle) is structurally irrelevant to it — this is a
genuine asymmetry between the routes worth stating plainly: the direct route
sidesteps this whole failure class by construction, not by mitigation.

**Worker selection among competing jobs, low confidence, web-sourced only:**
a Steam Community thread (fetched via search this session, not independently
corroborated by a second source) claims "job selection prioritizes more
highly-skilled dwarves." This is a single secondary-source claim, not
cross-checked against DFHack source or the wiki proper, and is reported here
only because the brief asked how a workshop picks among available work; it
should not be treated as more than a weak prior.

---

## C. Conflicts and failure modes

**Two sources asking for the same product.** This repo's own write-authority
design already limits the blast radius: `agents/overseer/tools.yaml` grants
both `orders.create` and `workjob.queue` to the Overseer only
(`sole_writer: overseer`, `agents/ROSTER.yaml`), so no two *roles* can race
each other into double-queuing today. But nothing stops the **same** Overseer
from queuing both a manager order and a direct job for the same product
(e.g. blocks), and the two systems are structurally separate: a
`manager_order` lives in `world.manager_orders.all`, a direct job lives only
in `world.jobs.list`/the workshop's own queue, and (per
`research/2026-09-18-work-orders.md`'s own explicit, checked-negative
finding) **no field was found linking a spawned `df.job` back to the
`manager_order` that created it**. That means even a careful observer
reading both `orders.list` and `stuckjobs.find` cannot currently tell, from
job attributes alone, whether a given in-flight `ConstructBlocks` job came
from the order queue or from a direct call — a real attribution gap, not
just a coordination gap.

**Competition for workshop, materials or hauling capacity.** Both routes
ultimately reserve materials through the same `job_item` mechanism and
compete for the same stockpiles and haulers; running both concurrently
against the same material pool doubles contention risk with nothing in this
project (or, per the sources below, in vanilla DF) arbitrating between them
automatically.

**Job cancellation spam, causes (web-sourced, several convergent Steam
Community threads, fetched this session, moderate confidence — practitioner
consensus, not official documentation):** the recurring pattern is a job
whose conditions were momentarily true, so it started, then the requisite
item became unavailable (hauled away, sitting mid-transfer in a bin, or
consumed by a *different* job racing for the same material) before the job
actually executed; the order/job re-attempts and cancels repeatedly if the
underlying shortage persists. **DFHack's own mitigation for the order
route**, web-sourced from its docs: `orders recheck` forces a
`manager_order`'s status from `Active` back to `Checking` so conditions are
re-evaluated rather than blindly retried. **The direct-job route has no
equivalent mechanism at all** — a stuck `workjob.queue` job has no recheck,
no condition to re-evaluate; it simply sits until a worker and material
happen to align, or until someone cancels it by hand (this repo has no
`workjob` cancel tool either, a gap the brief did not ask about but is worth
naming: `df-overseer-workjob.lua` has `list`/`queue`, no `cancel`).

**An order that can never be satisfied.** No source checked this session,
repo or web, claims DF ever flags this to the player. `orders recheck`
(above) is a tool-side workaround for *transient* unsatisfiability, not a
detector for *permanent* unsatisfiability (e.g. a condition referencing a
material the embark simply does not have). This matches
`research/2026-09-18-work-orders.md`'s own finding: an order with an
unmeetable condition just sits with `amount_left == amount_total` forever,
`is_active` false, no error, no announcement.

**The silent-failure mode this fort has already hit, install-verified, the
sharpest finding in this report.** The 2026-09-21 supervised unpause found
**zero announcements of any kind mentioning manager, office, or work order**
across a 3,900-tick window in which three orders sat unstarted. This is not
"a subtle signal that's easy to miss" — there is no signal. Any grading or
observability design that assumes the game will eventually complain is
wrong for this specific, already-observed failure mode.

---

## D. Observability

**The repo's own open assumption (`docs/AGENT-LOOP.md` §7 and
`learning/live_signals.py`'s own comment) is genuinely unverified, and this
session's own wiki checks could not settle it either.** The claim is: DF
removes a completed (or cancelled) order from `world.manager_orders.all`,
backing the `order."ID".exists` signal's `op="not_exists"` grading. Three
independent checks this session, none conclusive:

- **Code**: `create_orders`/`cancel_order` (this project's own tool,
  re-read this session) never observed a real completion; `cancel_order`'s
  own `erase(idx)` mechanism is explicitly documented in its own header as
  "inferred by convention... NOT independently proven by a real removal."
- **`learning/live_signals.py`'s own docstring** (re-read this session,
  line ~107): "This project has not independently watched a real order
  complete and vanish live itself," stated as an open gap, not a settled
  fact, by the code that actually depends on the assumption.
- **The DF wiki, checked twice this session**
  ([Work order](https://dwarffortresswiki.org/index.php/Work_order) and
  [Work orders](https://dwarffortresswiki.org/index.php/Work_orders), both
  fetched fresh): neither page describes post-completion list behaviour at
  all. This is a genuine gap in the wiki itself, not a source this session
  failed to find the right page in.

**Confidence: unverified, and it stays unverified until a real order is
watched through a full completion**, exactly the test
`research/2026-09-18-work-orders.md` §8 already proposed and never ran.
`docs/AGENT-LOOP.md` §7 is right to flag that the first live grading of a
`work_order` prediction is also the first real test of this assumption —
worth restating plainly: **if that first grading records a miss, it cannot
yet distinguish "the order never ran" from "the order ran and the
not-exists check itself is wrong,"** which is a second, compounding
uncertainty on top of the one already named in `docs/AGENT-LOOP.md` (failed
execution starting the grading window regardless).

**What can already be read, and where the tooling gap sits:**

- `orders.list` exposes `amount_left`/`amount_total`/`manager_appointed` per
  order (`df-overseer-orders.lua`). It does **not** expose
  `status.validated`/`status.active`, even though `create_orders` shows
  those fields exist on the struct (`research/2026-09-18-work-orders.md`
  §6, source-read, not yet built). This is a cheap, well-scoped, currently
  missing read: it would let an observer distinguish "queued, not yet
  validated" from "validated, waiting on a workshop" from "active,
  in-progress" without an unpause.
- `df-overseer-stuckjobs.lua`'s `get_stuck_jobs` walks the live
  `df.global.world.jobs.list` directly, so it sees an in-flight job from
  **either** route (both land in the same list once spawned). This makes
  it the single existing general-purpose tool that can watch either route's
  progress, but — per the attribution gap in C — it cannot say which route
  a given job came from.
- `JOB_COMPLETED` (`df-overseer-diff.lua`'s `eventful.onJobCompleted`) fires
  for jobs from either route too, with the same attribution gap; it also
  currently discards everything except a name string
  (`research/2026-09-18-work-orders.md` §6 already names extending it to
  capture `job_type`/`reaction_name`/`mat_type` as small, well-scoped work,
  not yet done).
- **A read that would have to be built, not found anywhere in this
  project's tools or in the web sources checked this session**: whether a
  spawned `df.job` carries any struct-level link back to the
  `manager_order` that created it. `research/2026-09-18-work-orders.md`
  looked and found nothing; this session did not find anything either in
  the DFHack docs it checked. If such a field exists, it would resolve
  both the attribution gap in C and materially strengthen D; if it
  genuinely does not exist, `job_type`/`reaction_name`/workshop matching
  (the current fallback) is the ceiling of what is achievable.

---

## E. Recommendation

This is my own judgment from A-D, not a restatement of a source.

**1. The Quartermaster should keep proposing `work_order` for both routes
under one type, as `agents/quartermaster/role.md` already does — do not
split it into two proposal types.** The role's own text already requires
reading both `orders.list` and `workjob.list` before proposing and stating
"which route your proposal means and why" in the rationale. Splitting into
`work_order_manager`/`work_order_direct` would double the bookkeeping
without adding safety, because the actual mutation authority sits entirely
with the Overseer either way (`sole_writer: overseer`); the type split
would not change who checks what before acting.

**2. Do not gate the Quartermaster's existence on an Office/Manager
combination being ready.** `agents/ROSTER.yaml` already enabled it
2026-09-22 for reasons that hold up under this research: food, drink, work
orders and farms are where this fort needs decisions now, and the direct-job
route gives the Quartermaster (via its proposals) a real, working lever
regardless of Office status. Gating the *role* on the Office would remove
the Quartermaster's only currently-reliable production lever for no safety
gain, since the role never acts directly in any case. The user's own framing
in the brief (office-led and non-office jobs both used; Quartermaster
enabled regardless) is the correct call given A1's finding that the office
requirement is real, install-verified, and currently unmet, with no
confirmed timeline for when it will be.

**3. What SHOULD be gated is trust in the manager-order route specifically,
not the role.** Until an Office is built, assigned to the Manager, and a
queued order is **actually watched running to completion once**, the
Overseer should treat any `work_order` proposal naming the manager-order
route as unproven on this fort, and should prefer the direct-job route for
anything the direct-job tool vocabulary already covers (currently
blocks/mechanisms/brew_drink). This is not a new rule; it is what
`agents/quartermaster/role.md`'s own "Confidence and gotchas" section
already asks the Quartermaster to say in its rationale — this recommendation
is that the Overseer's ruling should weight it accordingly, and that the
first successful (or failed) manager-order completion should be recorded as
a gotcha outcome (`gotchas.write`) either way, since both roles already hold
that tool.

**4. Two concrete, cheap, code-level checks are missing and worth building
before either route sees repeated real use, because both are exactly the
"code can catch this, a model shouldn't have to" case the brief asks about
in D:**

- **A duplicate-production check spanning both routes.** Before the
  Overseer accepts (or itself issues) a `work_order` for a given
  job/reaction, scan both `orders.list` (existing manager orders for the
  same `job_type`/`reaction`) and `stuckjobs.find` (existing live jobs of
  the same `job_type` at any workshop, which — per D — already sees jobs
  from either route even though it can't attribute origin) for something
  already in flight. This directly targets C's first finding (double
  production) and does not require solving the harder attribution-by-origin
  problem first: knowing "a ConstructBlocks job or order already exists" is
  enough to flag a likely duplicate even without knowing which route
  created it.
- **A "proven on this fort" gate for the manager-order route.** A simple
  boolean, set once `orders.list` shows an order's `amount_left` has
  actually decreased across a recheck boundary with a matching workshop
  confirmed built (the exact signal `research/2026-09-18-work-orders.md` §5
  already names as the cleanest available progress proof). Until that gate
  is true, treat every manager-order proposal as carrying the same
  structural risk this fort has already hit once.

**5. Smaller, lower-priority gaps worth naming for whoever builds next:**
surfacing `order.status.validated`/`.active` in `list_orders()` (cheap,
fields already identified, not yet read); adding `job.repeat` support and
a `cancel` verb to `df-overseer-workjob.lua` (both currently absent);
wrapping `orders sort`/`orders recheck` (DFHack-native mitigations this
project does not yet expose at all); and one more targeted source read for
a `df.job`-to-`manager_order` link field, since two sessions now (this one
and 2026-09-18's) have looked and found nothing, which is worth treating as
a real, load-bearing negative rather than quietly re-checking a third time
without new information.

---

## What could not be verified

- **Whether building and assigning an Office actually makes queued manager
  orders run.** The leading, install-consistent hypothesis (A1); not yet
  tested, since no Office has been built. This is the single biggest open
  question this report leaves behind, and the next supervised test
  (`Working.md` START HERE item 2) is what would close it.
- **Whether DF removes a completed or cancelled manager order from
  `world.manager_orders.all`** (D). Checked three ways this session (this
  project's own code, this project's own prior research, two fresh wiki
  fetches); none settled it. This is the `docs/AGENT-LOOP.md` §7 assumption
  and it remains open.
- **Whether a spawned `df.job` carries any field linking it back to its
  originating `manager_order`.** Looked for twice now (2026-09-18 and this
  session) with no source found either way; treated here as a real negative
  worth acting on (fallback attribution by job_type/workshop matching) but
  not proven to be structurally absent from the engine.
- **The manager-experience-on-validation and worker-skill-priority claims**
  (A1, B) are single-source web claims (one wiki page, one Steam Community
  thread respectively), not cross-checked against a second source or this
  install's own code, and are flagged at moderate and low confidence
  respectively.
- **Whether the wiki's 20-citizen validation threshold describes something
  materially different from the `required_office` field read live this
  session**, or is simply an imprecise restatement of it. This session's
  best read (A1) is that they are two separable claims, but this is
  inference from the position struct's own field name and description text,
  not a confirmation from DF's own (closed-source) validation logic.
- **The "General work orders allowed" per-workshop toggle's actual struct
  location.** Confirmed to exist by the DF wiki (B) but not looked for in
  this install's own building struct this session; whether it is
  DFHack-readable at all is unknown.
- No new live DFHack call was made this session (read-only brief); every
  install-specific claim above is a re-read of prior live findings already
  on record in this repo, not a fresh check.

## Sources

Repo (read in full or in cited sections this session):
`scripts/dfhack/df-overseer-orders.lua`, `df-overseer-workjob.lua`,
`df-overseer-stuckjobs.lua`, `docs/AGENT-LOOP.md`,
`agents/quartermaster/role.md`, `agents/quartermaster/tools.yaml`,
`agents/overseer/tools.yaml`, `agents/ROSTER.yaml`,
`decisions/DECISIONS.md` (2026-09-12 rows 210-229),
`research/2026-09-18-work-orders.md`,
`research/2026-09-16-opening-priority-ladder.md`,
`handoffs/2026-09-21-nobles-appoint.md`, `learning/live_signals.py`,
`Working.md`.

Web (fetched this session, untrusted data about this install, cited for the
claim made, not treated as fact about `53.16-r1.1` unless separately
verified against this install's own source above):
[DF2014:Manager](https://dwarffortresswiki.org/index.php/DF2014:Manager),
[Manager](https://dwarffortresswiki.org/index.php/Manager),
[Work order](https://dwarffortresswiki.org/index.php/Work_order),
[Work orders](https://dwarffortresswiki.org/index.php/Work_orders),
[DFHack orders plugin docs](https://docs.dfhack.org/en/latest/docs/tools/orders.html),
[DFHack do-job-now docs](https://docs.dfhack.org/en/latest/docs/tools/do-job-now.html),
[DFHack/scripts PR #1615](https://github.com/DFHack/scripts/pull/1615) (prioritize.lua absorbing do-job-now),
Steam Community threads on work-order cancellation spam (searched, several
convergent threads, no single thread singled out as authoritative),
Steam Community thread on job/labor priority (searched, single thread, low
confidence as noted in B).
