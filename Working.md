# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.

## Open: rotate leaked keys (2026-09-17)

A session ran `cat .env | grep -v SECRET` while looking up the VM 103 SSH
user, breaking the "read secrets by the key you need" rule — it printed
`ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, `CLOUDFLARE_TUNNEL_TOKEN`, and
`CLOUDFLARE_TUNNEL_TOKEN_ADMIN` into the session transcript in full. User's
call: rotate later, not urgent, but don't lose the item. → decisions/DECISIONS.md
2026-09-17.

## In design: the agent loop MVP (2026-09-22)

The user's goal: "design the agent loop, fill in the gaps, let the fort run",
an MVP to improve from what it does. Design lives in `docs/AGENT-LOOP.md`
(register 2026-09-22). **Agreed:** dispatcher plus queue (one-shot
`agent exec` runs woken by a code conductor); clock speed set per wake reason
(full, slowed, paused), from ticks-to-consequence where computable;
`base_fps` a setting the user may lower later. **Defaults not yet confirmed:**
the six build items in its §4 (in-game clock and tripwire script, a
`conductor` dfmcp role, the conductor service on VM 106, an execution record
with prediction windows starting at execution, enabling the Quartermaster, a
Tier 0 briefing). Nothing built.

**Since then, same day:** the roster (Overseer, Architect, Quartermaster,
Consultant), Consultant retrieval (local wiki, DFHack source, Brave web
search, `agents/consultant/sites.yaml`) and the objectives direction (an
Overseer-kept graph with a default flow and deviations, §6) were agreed. Three
offline build streams are dispatched (`handoffs/2026-09-22-loop-*.md`) and one
researcher on objective-graph prior art. **At merge, owed by the orchestrator:**
flip `quartermaster` to enabled in `ROSTER.yaml`; add the README and
`infra/local.example.env` lines the streams report; re-run both suites.

**Design input agreed 2026-09-24: fortress layout, and the user's call that
the checker must score layouts that do not yet exist.** Raised by the user
while looking ahead to fifty bedrooms. Agreed shape: a traffic hierarchy of
hallways by class and width, doors treated as special tiles that furniture may
not block, rooms required to be internally walkable, and wall reuse across
adjacent rooms. Two findings already in hand. DF has a real per-tile
`tile_designation.traffic` enum (High/Normal/Low/Restricted) that is a genuine
pathfinding cost multiplier, and the flood research found **0 of 6,856,704
tiles** carry a non-default value on this fort, so the mechanism exists and is
untouched. And positions demand sharply different room values, read live:
`MANAGER`/`BOOKKEEPER` 1, `SHERIFF` 100, `CAPTAIN_OF_THE_GUARD` and
`DUNGEON_MASTER` 250, `MAYOR` 500, so smoothing and engraving are the value
lever rather than decoration.

**Shelved 2026-09-24: the fort plan, districts as burrows, reservations and the
representative council.** The user's call: good design, possibly overcomplicated for now,
filed as an option for later. Moved whole to `working-archive/Working_archive-2026-09-22.md`.
Register rows stand (the constitution; and the finding that district-as-burrow is this
project's own extension, with burrow completeness as its hard constraint).

**The room pipeline, from the user's own play sequence (2026-09-24).** Five
ordered stages: (1) decide the floor plan and mine it out, (2) mine every ore
and gem the dig uncovered, (3) smooth stone into finished wall, or replace
soil with a constructed wall where smoothing is impossible, veins having
already been removed so a wall can stand there, (4) place furniture, (5) paint
the zones.

**This dissolves the material-knowledge problem** rather than solving it: no
need to know a tile's material before digging, because stage 3 handles either
outcome. It therefore supersedes the "plan, then verify" framing below for the
material question specifically, while the act/sense rule it rests on still
stands.

**Stage 5 being last is an invariant this project has already violated.** Both
Office zones were painted *before* any furniture existed, which is exactly why
`getRoomDescription` read empty for two days. Paint the zone after the
furniture and the read-back is meaningful on the first try. The ordering is
itself a rule, and nobody noticed there was an order to get wrong.

**Each stage boundary is a checkable postcondition**, which is the same shape
as the parked proposals-and-checks question arriving from another direction:
every designated tile dug, every revealed vein mined, every wall smoothed or
constructed, furniture placed, zone painted and reading non-empty. A stage
that has not met its gate blocks the next.

**Tool coverage, checked 2026-09-24: four of the five stages are covered and
the gap is stage 3.** Dig and vein mining are `diggable.dig`'s designation
family; constructed walls appear reachable through the generic `building`
tool, which already maps `df.building_type.Construction` to
`df.construction_type`; furniture is the `building` tool (proven, it built the
Chair); zones are `zone.place`. **Smoothing and engraving have no tool at all,
zero matches in `scripts/dfhack/TOOLS.yaml`**, and they are the stage that
sets a room's value ceiling: furniture alone may reach MANAGER's 1, but
MAYOR's 500 is unlikely to be reachable without them. They are designations
rather than buildings, so the natural home is beside `diggable.dig`, not in
the `building` tool.

**Build-cost correction from the user, 2026-09-24, and the constraint it
exposes.** Digging a room in rock gives you its walls for free: the undug
stone is the wall, so build cost is tiles excavated plus a door plus
furniture, with constructed walls needed only where the natural material will
not do (soil, or ore that should be mined rather than left standing). This
reframes wall reuse: between two rock rooms the shared wall is a tile nobody
digs, so reuse avoids **wasted undug tiles** rather than saving construction
labour, and it is a property of the dig plan rather than of any build order.

**The consequence nobody had stated: a room's value ceiling is set by the
material it is dug into.** Smoothing and engraving are the levers that reach
high room values (MAYOR needs 500 against MANAGER's 1), engraving requires a
smoothed surface, and soil cannot be smoothed. So a room dug in soil can never
be engraved and can never hold a high-value noble. **Needs verification**
before encoding, specifically whether soil truly cannot be smoothed in 53.16.

**And the act/sense rule makes this a post-dig property, not a siting input.**
`df-overseer-diggable.lua` was omniscient until the 2026-09-16 knowledge-scope
fix and its act/sense refinement: an agent may designate a dig into unrevealed
ground, because every player does, but may not know an unrevealed tile's
material first. So "site high-value rooms in stone" cannot simply be planned.
Agreed direction: **plan, then verify.** The planner proposes, the dig
reveals, and a check afterwards reports whether the room can be smoothed and
engraved, which decides whether it can ever hold a high-value noble. Material
reads themselves need no new primitive: `diggable` already reports STONE,
SOIL, FEATURE, MINERAL, LAVA_STONE and FROZEN_LIQUID per tile.

**Two corrections the user made to the orchestrator's proposal, both
accepted.** Wall reuse is a **metric, not an invariant**: "every shared wall
must be exactly one tile thick" would reject a layout that shares half a wall
and still wins, which is common when adjacent rooms differ in size, so it is
measured (shared wall length over total) and ranked, never enforced. And the
checker must be able to **score or create a layout that does not exist yet**,
not only audit what is already placed, which is the larger build: it needs a
model of the map rather than a read of it, and it is what lets the Architect
compare options before a single dig order is issued.

**Open, and blocking the invariant set:** whether a zone-defined room must be
enclosed is a game requirement or only a design preference. Yesterday's
research concluded from a current-namespace wiki page that an office need not
be enclosed; the user believes it is required. Dispatched:
`handoffs/2026-09-24-room-enclosure-and-value.md`. Recorded because a checker
is about to encode whichever answer is true, and this project has twice
mistaken a preference for a rule (`prefer_indoors`, the wiki's 20-citizen
Manager).

**Division of labour that falls out of the no-map commitment:** the model
picks policy (how many rooms, which traffic class, which layout family) and a
deterministic tool does the geometry. Parameterised layout families (spine
with rooms either side, double-loaded corridor, courtyard block) are preferred
over general rectangle packing, because shared walls then fall out of the
family rather than out of a search nobody can reason about. Two objectives,
build cost and movement cost, genuinely conflict, so the tool should return a
small ranked set with both costs stated rather than a single answer.

**Design input agreed 2026-09-23, for the agent design conversation: how
knowledge reaches a role.** Found empirically, not theorised: the Architect
derived the office rule from `zone.list-kinds`'s own metadata and **never
called `doctrine.get`**, which it holds. Agreed framing: knowledge belonging
to one action goes on that action (an office zone needs a chair inside it
belongs on `zone.place`); knowledge spanning actions, or about when and
whether rather than how, stays doctrine (a rule about seasons attaches to no
single tool). The learning rule that falls out: when a role gets something
wrong, attach the fact to the tool it had in its hands at the time.
**Agreed constraint on going further:** tool definitions already cost 8,312
tokens before a single call, paid on every run whether relevant or not, so
pushing everything into manifests grows the bill with the number of tools
rather than with the task. Doctrine is retrieved on demand, which is cheaper
and ignorable, and those are the same property. Also noted: making
`doctrine.get` mandatory buys compliance, not comprehension. **Not decided**,
and the user's own framing is that this is "the layer in between" and may
itself be code and part of the learning process, which makes it the same
layer as the parked proposals-and-checks question rather than a separate one.
**Cheap way to settle it, designed but not built:** `agents/architect/model.yaml`
already says this role is the easiest to evaluate properly because it is
read-only and idempotent, `selection.status: not built`. Three arms, same
fort and prompt, about three cents each: manifest only (already run,
`proposal-0002`), manifest plus a pointer to doctrine, and doctrine injected
into the charter.

**Held by the user, part of the framework design, not yet started:** how
proposals work end to end: (1) the Overseer proposing to itself, with no
second check; (2) which checks each kind of change needs (tactical,
strategy, agenda, template, doctrine); (3) which revisions count as learning.
**Design input agreed for that conversation (2026-09-22):** one shared
"revisioned knowledge" pattern for doctrine, the agenda template, gotchas,
playbooks and the wiki snapshot: stable entry ids, a revision number,
citations of `entry@rev` (the court judges against what was actually read),
a change log with reasons, and a cited-by index that flags, never edits,
dependents when an entry changes. Not in the MVP; keep entry ids stable
until then.

**All three streams merged locally 2026-09-22** (`375d1f9`, `c0bdd6a`,
`5edd1e4`), each checked against its code, the Quartermaster enabled, owed
lines applied. Suites after the last merge: ambient **1035 passed / 3
skipped**, `.venv-dfmcp` **604 passed**. Nothing deployed, nothing pushed.
Design flags and deploy traps from the streams are in `docs/AGENT-LOOP.md`
§7 (notably `proposal-0001` would grade as a latency miss on first run).

**Conductor built and merged 2026-09-22**, then a pre-deploy fix stream
(the Consultant wake via `queue.overview`, refusals reaching clients as
`isError`, `queue.escalate` as the only escalation route, requirements file).
Suites: ambient **1202 passed / 3 skipped**, `.venv-dfmcp` **623 passed**.
Known gap, explained: no "hostile seen but unreachable" signal. History was
rewritten by home-lab-8e the same day to strip Claude credit; local `main`
is credit-free, 68+ ahead of `origin/main`, fast-forward.

**DEPLOYED 2026-09-22, fort kept paused** (`handoffs/2026-09-22-loop-mvp-deploy.md`,
`evals/live/2026-09-22-loop-mvp-deploy/`), orchestrator re-checked on both VMs:
VM 103 paused, year 31, tick 106974, 100 FPS, `dfmcp-server` active,
`proposal-0001` voided, 30-page wiki snapshot at `/var/lib/dfwiki/`; VM 106
conductor unit **disabled and inactive**, four pinned openclaw configs, no
containers. Role tool counts: overseer 60, architect 35, consultant 21,
quartermaster 21, conductor 13. Dry run: it would wake the quartermaster on
`vital_nearing_threshold` and slow the clock to 10. Two live bugs fixed in
the deploy (the conductor's MCP client against the real SDK, a missing
`diff.since` grant).

**Owed before the first real start.**

1. **Text encoding: DONE 2026-09-22**
   (`handoffs/2026-09-22-loop-game-text-encoding.md`). Shared
   `df-overseer-textutil.lua` helper over `dfhack.df2utf`, a CP437 backstop in
   `dfmcp/dfhack_client.py` that logs which tool needed it, redeployed; the
   unseeded conductor dry run is clean; orchestrator re-checked the fort
   paused at tick 106974 and the backstop firing in the journal.
2. **Stale listeners and the quicksave slot: DONE 2026-09-22**
   (`handoffs/2026-09-22-loop-diff-reregister-quicksave-slot.md`). `diff.lua`
   re-registers its eventful listeners on a version bump, so a deploy takes
   effect with no DF restart; the 1210 legacy log entries were converted once
   and marked, next id 1211 intact; `fort.quicksave` reports the slot from
   `cur_savegame.save_dir`. That executor stalled after its last live check,
   so the orchestrator wrote the Result and re-checked VM 103 itself; suites
   1229/3 and 630. **New trap:** `dfhack.filesystem.mtime` is broken on this
   install, so no Lua script can confirm a save by mtime (`docs/TRAPS.md`).
   **Owed, needs game time:** that a genuinely new event logs UTF-8.
3. **Docker access: DONE 2026-09-22**
   (`handoffs/2026-09-22-loop-conductor-docker-access.md`).
   `SupplementaryGroups=docker` on the installed unit only, the `df`
   account's own groups unchanged, re-checked by the orchestrator.
4. **Awaiting the user:** the tripwire live tests (need a brief supervised
   unpause) and a short supervised first cycle. The first run should also
   check owed item 2's UTF-8 event.

**Research in, 2026-09-23: work orders versus direct jobs**
(`research/2026-09-23-work-orders-vs-direct-jobs.md`, the user asked for the
difference, priorities and conflicts). Both routes end in the same `df.job`;
the asymmetry is capability against reliability. Orders alone give conditions,
repeat and ordering, need a Manager with an Office (install-verified on the
MANAGER position: `required_office=1`, `requires_population=0`, so not the
wiki's 20-citizen story) and give **no signal at all** when they silently do
not run: the 2026-09-21 unpause saw zero announcements across 3,900 ticks
with three orders stuck. Direct jobs are the only route that has actually
produced on this fort, but have no conditions, no repeat, no duplicate
detection, a 3-kind vocabulary against 12, and no cancel or recheck. **No
field links a spawned job back to the order that made it**, so we cannot
currently tell which route produced a given job. Researcher's recommendation:
keep one `work_order` proposal type covering both; do not gate the
Quartermaster on an Office, gate trust in the manager route until one order
is watched completing; build a duplicate-production check across both lists
and a "proven on this fort" flag. **Still unverified:** whether DF removes a
completed order from the list, which the `order."ID".exists` grading signal
assumes.

**Correction and tools built, 2026-09-23**
(`handoffs/2026-09-23-order-job-attribution-and-checks.md`, merged, **not
deployed**). The research's claim that nothing links a job to the order that
made it is **wrong**: `df.job` has `order_id`, live-introspected on VM 103,
and DFHack's own `do-job-now.lua:106` matches on it. Both research files now
carry dated corrections. Built offline: order status in `orders.list`
(`validated`, `active`, `finished_year`, `frequency`, `max_workshops`, read
defensively), one shared `job_origin()` used by every live job reader, a new
`orders.check-duplicate` read tool over both routes, `workjob.cancel`
(Overseer only, explicitly denied to the advisors), and an optional repeat
flag on `workjob.queue`. Suites 1266/3 and 652. The repeat flag name
`job.flags['repeat']` is now **confirmed on this install** (orchestrator:
`lever.lua:65` and `gui/workflow.lua:93,102` under `/opt/df/game/hack`), which
the stream could only take from upstream source. Still unconfirmed:
`order_id`'s no-order sentinel (no order has ever spawned a job here) and
`frequency`'s enum type name (raw value always reported). **Deploy is owed
and needs the user's go-ahead**; the exact procedure and the first-run write
verb commands are in the handoff's Result.

**Deployed 2026-09-23** (`evals/live/2026-09-23-order-job-attribution/`),
orchestrator re-checked: fort paused at tick 106974, `dfmcp-server` active,
installed `orders.lua` hash-matches committed bytes. The three orders now read
`validated=true, active=false, finished_year=-1, frequency_raw=0`;
`orders.check-duplicate blocks` correctly flags order id 0 as in flight;
`stuckjobs.find` is empty, so no live job has shown a populated origin field
yet. Tool counts: overseer 62, architect 36, quartermaster 22, consultant 21,
conductor 13. The deploy agent printed the VM address and hostname once each
before building its scrubbing helper; neither reached a tracked file.

**In flight, 2026-09-23: the first unattended run**
(`handoffs/2026-09-23-office-and-first-real-build.md`). The user gave a
go-ahead while not watching, so the bounds replace supervision: quicksave
before every window, tripwires armed, 2000-tick windows, 10 windows maximum,
hard stop on a death, a tripwire, a hostile, a stalled tick, tool errors, any
dwarf reaching dehydrated or thirst worsening twice in a row. Starting vitals:
22 alive, 1 dead, worst hunger fine, worst thirst thirsty (one warning). Goal:
the first real build of a never-built kind (furniture), an Office zone over
it, assigned to the Manager (unit 345), then whether the three orders go
active and spawn a job carrying their `order_id`. Also records what room value
required, and whether a finished order leaves `world.manager_orders.all`
(`docs/AGENT-LOOP.md` §7).

**First unattended run, 2026-09-23: partial, tripwire-stopped**
(`evals/live/2026-09-23-office-and-first-real-build/`). One 900-tick window of
the ten allowed. **The first real build of a never-built kind happened**: a
Chair, dry run and real run identical, read back as existing, and now held
suspended by buildingplan because the fort owns no Chair item (`stocks
CHAIR=0`), so a new manager order (id 3, ConstructThrone) was created to
supply one. Two Office zones exist (10 unowned, 11 owned by the Manager, unit
345, read back twice); no indoor 3x3 site was available near a workshop or the
Well, so both are outdoors. **The tripwire fired for the first time for real**,
`hostile_reachable` on a kea 68 tiles away sharing the citizens' walkable
group, and paused the fort itself, as designed. The run stopped there per its
own hard line. Orchestrator re-checked: paused at tick 107874, 22 alive, 1
dead, hunger fine, thirst thirsty (warning), 2 zones, orders 0/1/2 still
`validated=true, active=false`, order 3 `validated=false`. Restore point
`autosave 2`. **Still open:** whether a bare outdoor owned office carries
enough room value for `required_office=1`; 900 ticks cannot separate "needs
more time" from "needs more room value". **Decision owed by the user:** does
harmless wildlife count as `hostile_reachable`? A kea will stop every window
otherwise. Note the interaction: the in-flight reachability stream
(`handoffs/2026-09-23-landmark-reachability.md`) changes the very rule this
tripwire uses. Two more address or hostname prints by that executor, neither
reaching a tracked file; the shared ssh helper is now clearly overdue.

**Reachability fixed, 2026-09-23, merged, NOT deployed**
(`handoffs/2026-09-23-landmark-reachability.md`). New shared
`df-overseer-reachability.lua`: resolve a landmark to a standable tile (itself,
else its 8-neighbour ring), compare walkable groups, and report
reachable/unreachable/**unknown** instead of a bare false. Wired into
landmarks, connectivity and threat; the old boolean fields were removed after
grepping for dependents, so `landmarks.list/get` and `connectivity.check*` now
return a different shape and are marked unverified in TOOLS.yaml until
deployed. Suites 1281/3 and 652. **Threat behaviour changes**: a unit standing
on a ramp read as group 0 and could be missed entirely, so the scan becomes
strictly more permissive, never less. **Not migrated**: nine other scripts call
`getWalkableGroup` directly and carry the same ramp blind spot (breach,
harvest, trees, openarea, diggable, chokepoints, building, zone, stocks).

**Wildlife research in, 2026-09-23**
(`research/2026-09-23-wildlife-threat-classes.md`). Verified from this
install's own raws: a kea carries only the curious-beast tags, no
LARGE_PREDATOR, no BUILDINGDESTROYER, and is not an invader, so **it should
never pause the fort at any distance**. That overturns
`df-overseer-clock.lua`'s current rule, which pauses on any reachable
candidate. Recommended three tiers: record only, slowed with an Overseer wake,
and pause for a large predator, a building destroyer or a confirmed invader
that has actually reached the citizens' network. For the standing observation
ledger the researcher recommends a small keyed store (race plus outcome, not
per unit) that aggregates in place, decays presence-only rows, graduates theft
or kill rows to the register, and **never calls pause or wake**; the existing
per-role diff cursor is the wrong home because it truncates at 20 events with
no aggregation. Confirmed gap: `CREATURE_STEALS_OBJECT` is not in
`df-overseer-diff.lua`'s report categories, so thefts are currently invisible.
Could not verify: any tick timing for how fast a threat develops, so the pause
tier deliberately does not depend on a tick budget.

**In flight:** the full announcement vocabulary, 357 types read live and saved
at `research/data/2026-09-23-announcement-types.tsv`, being classified into
pause/slow/notice/log only/ignore with a machine-readable YAML
(`research/BRIEF-2026-09-23-announcement-severity.md`).

**Announcement taxonomy in, 2026-09-23**
(`research/2026-09-23-announcement-severity.md`, data at
`research/data/2026-09-23-announcement-severity.yaml`). All 357 types levelled,
orchestrator validated the file: 357 entries, exact match with the live list,
no gaps or extras. Counts: pause 25, slow 23, notice 139, log only 93, ignore
77; confidence verified 74, likely 259, unverified 24, per entry. Joined by
name against DFHack's `df-structures` `alert_type` attribute (all 357 matched
with identical ids). Recommended: a fifth, separate tripwire firing on the 25
pause ids as a literal table, the 23 slow ids routed through
`conductor/triage.py`'s existing wake machinery, and the other 170 never
reaching the tripwire at all. **DF's own vocabulary already splits the kea
case**: `AMBUSH_MISCHIEVOUS` is a distinct id from `AMBUSH_SNATCHER` and
`AMBUSH_AMBUSHER`. **Finding to act on:** the death tripwire listens to the
raw `UNIT_DEATH` event, which `research/2026-09-16-player-visibility.md` tags
omniscient; `CITIZEN_DEATH`/`PET_DEATH` are the player-visible channel, so
re-point or dual-arm it. **The channel's hard limit:** a stalled manager order
produces no announcement of any kind, because the layer only reports things
that happen. That needs a poller in `conductor/triage.py`, the same shape as
`stuck_job`, and no refinement of this classification can close it.

**Attention system built and deployed 2026-09-23**
(`handoffs/2026-09-23-attention-tiers-ingame.md`,
`handoffs/2026-09-23-stalled-order-poller.md`,
`evals/live/2026-09-23-attention-deploy/`). Three tiers replace pause on any
reachable creature; a fifth tripwire on the 25 pause-level announcements,
generated from the severity YAML with a drift check; theft and the other crime
announcements added to the report categories; an observation ledger keyed by
race that aggregates in place and whose write path is proven by a test over the
real file to be unable to pause or wake; a stalled versus blocked order poller
in `conductor/order_watch.py` with thresholds in policy (1200 ticks, reasoned
not measured); the 23 slow-level ids routed as wakes. The two halves agreed
their event shape without talking: the in-game stream read the merged conductor
code and emitted exactly what it assumed. Suites 1342/3 and 652. Deployed and
re-checked: tool counts overseer 63, architect 37, quartermaster 23, consultant
21, conductor 15, each delta explained; **the Well now reads reachable**, the
regression that started this; fort paused at tick 107874 throughout. The
research's claim that the death tripwire used an omniscient event was **wrong**
and the executor said so: it already compared citizen rosters, and pet deaths
are now covered too.

**Bug found live by the mandatory check, fix in flight**
(`handoffs/2026-09-23-creature-tag-fields-fix.md`). All six creature tag reads
in `class_flags` were at the wrong level and partly misspelled:
`creature.flags.X` raises on this install, the tags live on
`creature.caste[unit.caste].flags`, the spelling is `CURIOUS_BEAST_ITEM` not
`CURIOUSBEAST_ITEM`, and building destroyer is `caste.misc.buildingdestroyer`,
an integer, not a flag. Verified twice against live kea unit 513, once by the
deploy agent and once independently. Every read is pcall-guarded, so all six
silently returned false: the kea still landed in `record_only` by luck, but the
**slow tier could never fire for a thieving creature**, the exact case the
design was built for. Three layers of offline tests passed; only a live
creature caught it. **Fixed, redeployed and live-verified 2026-09-23** (orchestrator, one file,
committed bytes hash-matched at the installed path, quicksave confirmed in
`autosave 2` first, backup at `/opt/df/deploy-backup-2026-09-23-tagfix/`):
`threat.scan` now reads kea unit 513 as `is_curiousbeast_item: true` and
`is_curiousbeast_eater: true` with `read_failures: []`, tier `record_only` at
68 tiles and not closing, and the moose as `is_benign: true`. Before the fix
every one of those read false. Fort paused at tick 107874, 100 FPS,
`dfmcp-server` active. **Still owed:** a live check that a deliberately broken
field name actually surfaces in `read_failures`, which only a failing read can
prove.

**Tooling:** `scripts/vm-ssh.sh` (committed, orchestrator-tested) is now the
only sanctioned way for a stream to reach a VM: it reads the address by key,
never echoes it, and masks address-shaped output. Four agents had leaked one by
writing the same wrapper from scratch.

**Design, paused mid-question 2026-09-22.** "The Overseer proposing to
itself" is really two paths, since it holds no `queue.propose`: its own
agenda edits, and its direct write actions outside any proposal. Proposed
answer (not agreed): code checks (graph validity, applicability); a cited
doctrine or wiki revision for any game-rule claim, with a Consultant
fact-check only when uncited or when a default step is skipped or deleted;
and a record written before any self-originated action. The user was asked
which path they meant; their answer is the next step.

**Home-lab inventory:** home-lab-8e wrote both `inventory/services.yaml` lines
(the conductor unit on VM 106, openclaw's four roles) on 2026-09-22, validated
but **left uncommitted** in `../home-lab` beside other in-flight changes, for
the user or whoever commits there next.

**Earlier plan, now done:** one deploy stream for everything, running the clock stream's nine live
checks and voiding `proposal-0001`. **The user authorised the deploy to place
the MCP role tokens itself (2026-09-22: "you can do the tokens yourself"),**
including the new quartermaster, consultant and conductor tokens on VM 106.
Rules still hold: read by key name only, never printed or tracked. If the
auto-mode classifier refuses the secret-store write again (it did on
2026-09-15), stop and tell the user; never route it through another session.

## In discussion: designing the learning loop (2026-09-17)

**Not designed yet, by the user's own assessment.** No code; do not start
building from this section. The design is being settled one question at a time
with the user.

**Agreed so far** (→ `decisions/DECISIONS.md` 2026-09-17):
- Doctrine sources carry per-source provenance; `verified` needs a 53.16 live
  or game-data source; a pytest validator enforces it (built).
- `get_doctrine`, read-only, with a topic index (agreed; **built 2026-09-19** as `doctrine.get`, consultant only, **deployed and live-verified 2026-09-20**).
- Doctrine revisions are proposals; the Overseer can accept, reject, defer,
  **amend**, or hand the proposal to another role for querying first.
  Amendments apply directly for tactical and strategy proposals and return to
  the proposer once for doctrine. Research alone can only yield `prior`.
  Applied doctrine changes go in a user digest for now.
- The quartermaster probably becomes necessary, owning strategy from
  inventory and production trends.
- Every proposal must list the doctrine entries it relied on. An empty list
  is valid ("relied on none"); a missing field is not. A miss puts the cited
  entries under suspicion, which is what links grading to revision.
- **A grader limited to code and a closed signal list is too narrow** (user,
  2026-09-17). Candidate under discussion: plain-language predictions written
  before acting, facts gathered by code, and a small jury of different model
  families that sees only the prediction and the facts. Not decided.
- **A retrospective court, not a gatekeeper** (user, 2026-09-17/18): a
  prosecutor and a defence argue whether past proposals succeeded, at
  per-proposal review horizons, batched into sessions. Code grades what a
  signal settles; the court handles what it cannot; "unclear" must be an
  allowed verdict. Adversarial review of a proposal *before* execution was
  judged overkill. Open: who sets the horizons, who judges, what a verdict
  attaches to, and what wakes a session (no scheduler exists).
- **openclaw has no multi-agent primitive worth using** (research
  2026-09-18, not independently confirmed in source: the local checkout is
  scaffolding only). It has native session send/spawn, but the inter-agent
  lane is reported as one concurrent operation, and cron, heartbeat and
  webhook triggers all need a Gateway this project has never run. Hooks
  exist for session and command lifecycle, **not** tool calls, so
  `dfmcp/roles.py` stays the only real safety boundary. No spend cap of
  any kind. Recommendation: keep the dispatcher-plus-queue design, with
  independent one-shot `agent exec` runs. **Pending the user's decision.**
- **Work orders can carry standing policy** (research 2026-09-18): shipped
  conditioned orders exist, `JOB_COMPLETED` needs a one-line extension to
  measure production, and the manager-appointment question needs one
  supervised unpause to settle. None of this fort's current blockers is an
  order problem.
- **Tools carry a confidence level, and their gotchas are learned material**
  (user, 2026-09-21): full means use it, medium means read the description and
  gotchas closely and monitor for success. Part of this loop; each tool keeps
  gotcha, vent and unexplained-error lists; results carry the level and short
  condition-titled gotchas only; agents propose gotchas via the queue; the
  level is static, with no mechanism to raise it (user, 2026-09-21); vent is
  a complaint channel for an agent to say a tool does not fit its need. → `docs/BUILDING-TOOL.md`.
- **The Overseer hands proposals to the consultant for fact-checking** (the
  "wiki nerd and researcher" role) before ruling.
- **A new learning role, separate from but related to the consultant**, name
  TBD: its job is identifying patterns (for example across graded misses
  against cited doctrine) and proposing doctrine revisions. It is both a
  helper and a proposer, callable by other roles and able to call them
  (for example the consultant, to check a source). Not the chronicler, whose
  charter forbids influencing what the fort does. Mechanical parts stay code:
  grading, tallying misses, flagging an entry disputed, applying changes.
  Agents cannot call each other today (one-shot runs, queue as the only
  channel), so the calling mechanism is undesigned.
- **Other roles may propose doctrine revisions too, but must discuss them
  with the learning role first.** Enforced by the queue: such a proposal
  must reference the discussion record, which carries the learning role's
  view to the Overseer. **Scope: doctrinal and learning revisions only**, not
  every revision (tactical and strategy amendments never need it).

**Built today vs missing, checked against code:** predictions are recorded
and there are two graders (`dfqueue/grade.py`, `learning/predictions/`), but
neither has graded a real proposal. There is no evidence model, no doctrine
revision type (the reader, `doctrine.get`, is live), no chronicle and no
scheduler. The fort's history is now stored and readable (`dfseries`, the
`series.*` tools), but nothing consumes it for grading yet.

**Two of this section's open questions were answered by the production-model
work on 2026-09-18, not by this conversation.** Recorded here because they
were listed as open and no longer are:

- **"Who sets the review horizons"** for the retrospective court. **Material
  class does.** A decision about a consumed good (food, drink) is reviewable
  in days, a keep-on-hand par level in weeks, an insurance level only after
  the threat fires, a reserve floor never, because the whole point of a floor
  is that nothing happens. So the horizon is a property of what the proposal
  was about, derived from the band, rather than a number the proposer picks or
  the court negotiates. → `docs/PRODUCTION-MODEL.md` §10.
- **How an outcome gets attributed** when a proposal misses. The
  four-quadrant rule gives the court a mechanism it did not have: build the
  expectation from Q1 and Q3 (raws and exact reads), and the gap is a
  **residual, reported as unattributed** rather than explained. That splits a
  miss three ways cleanly: the plan was not executed, the plan executed and
  the figures behind it were wrong, or the plan executed on sound figures and
  the objective itself was the wrong choice. Only the third is a
  decision-quality question, and only the third is worth an adversarial
  sitting. → `docs/PRODUCTION-MODEL.md` §3.

**Also relevant, and uncomfortable:** the lever catalogue found that only
four of ten named diagnoses have a tool that can act on them. A court that
reviews proposals the fort could never have executed is grading the wrong
thing, so the catalogue is a prerequisite for the court rather than a
side-quest. → `docs/PRODUCTION-MODEL.md` §13.

**Still open:** exactly which revisions count as "learning" (playbook
thresholds? evidence rules?); the learning role's name; how roles call each
other (referral to the consultant, calls to and from the learning role); how
the learning role decides a run of misses is a pattern without an arbitrary
threshold (research 2026-08-25 already rejected one); the background
ground-truth audit idea (below, under HANDOVER); what `ROADMAP.md` should say
about the learning loop specifically, deliberately not written until the
design settles.

**Next concrete step:** continue the design conversation with the user from
"which revisions count as learning revisions".

## Archived: production model designed, audited, four streams dispatched (2026-09-18)

Moved to `working-archive/Working_archive-2026-09-14.md` on 2026-09-19: every
stream it dispatched finished. Design lives in `docs/PRODUCTION-MODEL.md`.

## The visual ledger (artifact)

**https://claude.ai/artifact/NK1FMkcA1ev9Wvcas6SBpD** (published 2026-09-19).
The fort's state, the production model's build status, the four quadrants, the
lever table, the four deductions, and a two-route diagram of the well versus
brew chains. **It exists to keep measured facts visibly separate from asserted
ones**, and carries the "things this project got wrong" list deliberately.

The **earlier** artifact (`CQZHQDLRB7hRHWLqYrfmY5`) was published under a
different account and **can no longer be updated from this session**. Do not
try; publish to the URL above instead. Republishing the same scratchpad file
path keeps that URL.


## Archived: live fort state and the 2026-09-19 handover (2026-09-21)

Moved to `working-archive/Working_archive-2026-09-14.md` on 2026-09-21: both
2026-09-18 live-fort sections ("cannot drink", tick 227160/235668) and the whole
HANDOVER 2026-09-19, superseded by the section below. Fort figures in them are
historical.

## Current state, 2026-09-15: archived

Moved wholesale to [`working-archive/Working_archive-2026-09-14.md`](working-archive/Working_archive-2026-09-14.md) on 2026-09-18, superseded by
HANDOVER 2026-09-19 and the production-model work above.

## THE LOOP CLOSED, 2026-09-23 (read this first)

**Blocking the first real conductor cycle, found 2026-09-23 after the clock
deploy:** the conductor cannot read the game tick and fails silently doing it.
A foreground `--dry-run --once` on VM 106 planned to wake nobody while four
manager orders sat stalled, and `status.json` read `"game_tick": null`.
`_game_tick` imports `dfqueue`, which the conductor deliberately does not
depend on, and swallows the `ModuleNotFoundError`. A null tick disables the
routine review (never due) and the stalled-order poller (returns empty before
reading an order), so two of the conductor's wake reasons have never worked in
production. Fix dispatched offline: `handoffs/2026-09-23-conductor-game-tick.md`.
**The first real cycle is on hold until this lands**, because a cycle run now
would be a conductor with half its triage switched off.

**Also in flight:** `handoffs/2026-09-23-room-and-zone-requirements.md`, a
read-only researcher on what each room and zone actually requires, read from
the install's own data rather than the wiki, with doctrine entries as its
output. The office question is its explicit target.

**A tool queued a job, the fort ran it, and a building that was waiting on the
item finished.** Job 2249 (`ConstructThrone`, direct job, `order_id: -1`) made
a Chair; building id 9 claimed it and completed at year 31 tick 112205.
Verified independently after the run: `exists=true, jobs=0`, job 2249 gone
from the live list, one CHAIR item `in_building`. Three windows of a permitted
ten, 4483 ticks, no death, thirst improved from "thirsty" to "fine". Every
earlier milestone either dry-ran or left something waiting.
-> `evals/live/2026-09-23-chair-completion-run/README.md`.

**Three findings from the run, in order of how much they change things:**

1. **The office question now points away from the office.** In the first real
   fort time the manager orders have ever had, nothing moved: ids 0/1/2 stayed
   `validated: true, active: false` and id 3 stayed `validated: false` even
   after the Chair it was meant to supply had been built by the other route.
   "They just needed fort time" is now weak. Room value or an unidentified
   requirement is more likely. Nothing varied the office, so it is not proven.
2. **The `slow` tier fired for real and never cleared.** A kea tripped
   `theft_tag_close_range`, correctly stayed at `slow`, and never escalated.
   That is the first live proof the tier the creature-tag bug had disabled now
   works. But nothing clears a `slow` advisory when its creature wanders off,
   so **the fort is currently left at 10 FPS, not 100**, and every unattended
   run would end throttled. `docs/AGENT-LOOP.md` §3 has no clearing rule and
   needs one. The fort is paused, so this costs nothing until it resumes; the
   advisory was deliberately left latched rather than cleared, so the evidence
   is intact for whoever writes that rule.
3. **A classifier refusal keyed on a word, not a code path.** `workjob cancel`
   with its default dry run was refused twice as irreversible deletion, though
   the dry path provably never deletes. The run worked around it with reads
   only, deployed nothing, and routed nothing through another session.

**Owed now:** correcting `df-overseer-breach.lua`'s header and the `ROADMAP.md`
line on the next Lua deploy; the user's open ruling on burrow confinement.

**Both streams dispatched after the push at `c58b9c7` are DONE and merged,
local only, nothing deployed and nothing pushed.**

- **The `slow`-tier clearing rule is built and tested, not deployed**
  (`handoffs/2026-09-23-slow-tier-clearing.md`). `base_fps` is now an explicit
  `clock.arm` argument, default 100, persisted to its own state file, so the
  restore target is a value someone chose rather than one read off the fort at
  the moment of the drop. The threat scan clears the advisory and restores FPS
  as soon as a scan finds nothing at `slow` or worse, at the same cadence that
  sets it, with no hysteresis; `clock.clear` now clears the advisory too and
  reports `had_latch` and `had_advisory` separately. Suites re-run in the main
  checkout: ambient **1371 passed / 3 skipped**, `dfmcp/tests` **652**.
  **Deployed and live-verified the same day** (`evals/live/2026-09-23-clock-clearing-deploy/`):
  the fort read `fps: 10.0` with the kea advisory still latched, `clock clear`
  returned `had_advisory: true`, and an independent status read came back
  `fps: 100.0` with no advisory and `base_fps: 100`. Re-armed, MCP server
  restarted clean, fort unmoved at `abs_tick 12611557` and still paused.
  **One check still owed:** an advisory clearing *by itself* as a candidate
  recedes needs the fort to run, and its reproducer is now consumed, so it
  belongs to the next unattended run.
- **The proposals-and-checks evidence pass is merged**
  (`research/2026-09-23-proposals-and-checks.md`). Its verdict: this project
  already built two classical check shapes without naming either, a one-shot
  postcondition (`dfqueue`'s `prediction`, the design-by-contract shape) and a
  continuous invariant (the tripwire and vitals layer), so `proposal-0001`'s
  void was an anchoring bug rather than a flaw in the record. One claim was
  corrected on merge: it counted ten signals in `learning/live_signals.py`
  where `SIGNAL_KINDS` holds twelve. It ends with five decisions phrased as
  choices, which is where the parked design conversation should start.

**Also found, and now a register row:** a subagent worktree cannot see a
handoff brief that has not been committed yet, and its branch predates any
dispatch commits, so merging one wholesale reverts the orchestrator's own
work. Both branches this round would have deleted the sibling's brief. Commit
briefs before dispatching; take only a stream's owned files on merge.

## Both 2026-09-23 evening streams are DONE and merged (state below is history)

**Outcomes, merged to main, not pushed and not deployed:**

- **`workjob` is generalised.** The job vocabulary now comes from DFHack's own
  `workshops.getJobs`; the three-entry table is gone, the three old tokens
  survive as aliases, `list-jobs` is new, and `COUNT` was appended fifth so no
  existing caller shifts. Coverage measured live: **28 of 33** workshop and
  furnace kinds offer at least one job, the five that do not are named. The
  stream left one failing pinned test in `dfmcp/tests` (the arg signature);
  the orchestrator fixed it and granted `workjob.list-jobs` read-only to
  overseer, architect and quartermaster, without which the generalisation is
  unreachable. Ambient **1362 passed / 3 skipped**.
- **Flood relevance answered.** The footprint sets the tier, not the poll
  scope: traffic is 0 of 6,856,704 tiles non-Normal and burrows are 0, so a
  scope filter would have watched nothing. Dig designations (36 tiles) are the
  only populated element and the only predictive one. **And the breach
  detector is not dead after all**: its `update_liquid` gate fires on 3
  blocks, agreeing exactly with DFHack's own `flows` tool, re-verified
  independently by the orchestrator. `df-overseer-breach.lua`'s own header and
  the `ROADMAP.md` line still say the opposite.

**Owed, in order:** (1) correct that breach header and the ROADMAP line on the
next Lua-deploying stream, rather than drifting the installed hash for a
comment; (2) deploy the generalised `workjob` (needs a go-ahead) and wire
`list-jobs`/`COUNT` argument descriptions into `dfmcp/tools.py` if that layer
needs them; (3) the supervised real-queue test the stream wrote out, which
would make the actual Chair item the fort's built Chair is still waiting on,
through the direct-job route instead of the stalled manager order; (4) the
user's open decision on whether an agent may confine a citizen to a burrow.

## History: the two streams as dispatched 2026-09-23, evening

Both worktree-isolated, neither touching the other's files. Docs pass and the
register/memory rows for the week are merged and **pushed** (`ba708e7`); the
push batch was checked for sibling-session commits and held only this
session's own.

1. **Generalise `workjob`** ([`handoffs/2026-09-21-workjob-generalise.md`](handoffs/2026-09-21-workjob-generalise.md),
   written 2026-09-21, dispatched today on the user's call). The repo's known
   standing violation of the generalisability rule: three job tokens against
   `orders.create`'s twelve, which is why the fort's first Chair had to be
   ordered through `orders.create`. Target is the game's own vocabulary via
   DFHack's `workshops.getJobs`, not a bigger hand-maintained table. Owns
   `df-overseer-workjob.lua`, `TOOLS.yaml` and its manifest tests. Live on
   VM 103 but **read-only, dry runs only, no real job, fort stays paused**.
2. **Flood relevance research** ([`handoffs/2026-09-23-flood-relevance-traffic-burrows.md`](handoffs/2026-09-23-flood-relevance-traffic-burrows.md)).
   `df-overseer-breach.lua` covers nothing: its `update_liquid` gate read
   zero of 26,784 blocks over 11 polls, which cannot distinguish "DF never
   sets it" from "nothing changed". Tests the user's hypothesis that traffic
   designations and burrows are both the relevance filter and the response
   (reroute, confine), and pay for themselves on hauling logistics alone.
   Read-only, no code, owns only its research file and its own Result.

**Design steer sent to stream 2 mid-run, worth keeping if the stream agrees
with it:** the footprint should set the **tier, not the poll scope**. A pure
occupancy filter fails exactly where flooding starts, because a breach
happens in a tile seconds old that belongs to no zone, burrow or route. So
keep a cheap global rising-liquid check and let the footprint decide
loudness: burrow or hauling route is pause, the **active dig frontier** is
slow, an unvisited cavern is ledger-only. Corridors and stairwells sit in no
zone, burrows are optional and often absent, and traffic defaults to
"normal" everywhere, so zones plus burrows alone would under-cover; but
workshops and stockpiles are fine, being real objects with known tiles.

**Next after these two, in the user's own priority order:** an unattended
fort window (answers whether an outdoor unfurnished Office carries enough
room value for `required_office: 1`, and would witness an order's full life
for the first time), and then the parked proposals/checks design
conversation, which the user has said should fold into higher-level design
now that the tool picture is clear.

## HANDOVER 2026-09-21, evening (read this first after a /clear)

The first half of the earlier 2026-09-21 handover (the 2026-09-20 fort figures, the
2026-09-20 deploy note, and the START HERE list with its accumulated status
paragraphs and the long "design gaps" item) moved wholesale to
[`working-archive/Working_archive-2026-09-21.md`](working-archive/Working_archive-2026-09-21.md)
on 2026-09-21 (the file had reached 522 lines). Nothing was summarised there; what
is still true from it is restated below.

**Authority.** The user granted full authority to push, change the VM and act on
the fort ("this is all dev experiments not production"), and asked not to be asked
per action. **Two things changed today:** (1) `CLAUDE.md` still says a push needs
the user's go-ahead each time, and the user's own settings allow `git push` without
a prompt, so **ask before pushing** (a push was made without asking on 2026-09-21
and is recorded as a slip); (2) live VM work is best done in manual mode or with the
`autoMode` block now in the user's settings (below). Standing exception: genuinely
unrecoverable loss (the fort save, the VM itself) stops and reports. Two standing
rules from the rollback are in `docs/TRAPS.md`: never run an unbounded query against
a live DFHack process, and quicksave immediately before any live fort action.

### The fort, re-read live 2026-09-21

Uniboslan, year 31, **paused at tick 106974**, 22 alive and 1 dead (unit 454
starved at tick 15143), 100 FPS when running. At the last poll worst hunger was
39,984 and worst thirst 25,093 (nowhere near critical). **The well is built** (id
8). **MANAGER is held by unit 345** (Tun Konosamem, a Stonecrafter), appointed by
the new `nobles` tool. The fort has **no zones at all, so no Office**, and the three
queued manager orders (ConstructBlocks x1, ConstructMechanisms x1,
`BREW_DRINK_FROM_PLANT` x8, all hand-validated on 2026-09-19) **did not start in a
3,900-tick window**. The user confirmed from play that the Manager needs an office.
Two quicksaves exist from today (`autosave 3` before the appointment, `autosave 2`
after it, 09:25:04Z). Autosave and the sampler run only while unpaused.

**Read hunger, thirst, deaths and stock together before calling it healthy**
(register 2026-09-19).

### Live on VM 103 (deployed 2026-09-21, hash-verified)

Role tool lists **architect 34, overseer 57, consultant 14** (were 25/45/11): the
generic `building` tool (`list-kinds`, `find`, `build`; **dry runs only**),
`labor enabled-counts`, `gotchas.get`/`gotchas.write` (static confidence file,
`tool_guidance` enrichment), the labor graph and join (graph at
`/var/lib/dfproduction/`, **5 known / 23 partial / 5 unknown of 33 kinds**),
`nobles` (`list`, `verify`, `appoint`, `unappoint`) and the generalised `zone` tool
(18 zone kinds, optional owner). New state: `/var/lib/dfgotchas` and one
`ReadWritePaths=/var/lib/dfgotchas` line; backups in
`/opt/df/deploy-backup-2026-09-21-building-batch/`. **Merged, not yet redeployed:**
the labor join's real-shape fix (`dfmcp/labor_join.py`, `dfmcp/tool_guidance.py`).
Fourteen tracked scripts on the VM differ from main by one trailing blank line (the
known artifact); `df-overseer-embark.lua` is on the VM and untracked. **Suite,
measured 2026-09-21:** ambient **891 passed / 3 skipped**; `dfmcp/tests` in
`.venv-dfmcp` **537 passed**.

### Where the MVP stands (the user's minimum bar for openclaw, 2026-09-21)

Build workshops, rooms and furniture, assess dwarves, grow food, build wells.
**Wells: done.** **Workshops:** tool deployed, never built for real (no never-built
kind has been built; reachability of a site is not checked). **Rooms:** the zone tool
is built and deployed; a real placement, the owner assignment and its read-back have
never run; what makes an Office meet a room value is not exposed by the game.
**Furniture:** about 14 kinds dry-run; no way to place furniture inside a given room,
nothing assigns a bed or room to a dwarf. **Assess dwarves:** not designed (what it
feeds into is unanswered). **Grow food:** farm plot tools exist; the fort is fed by
wild gathering; the end-to-end run and the `growdur` unit are unsettled. **Also
missing:** stockpile creation and configuration; a way to run the game forward
safely and watch the vitals continuously; defence; the chronicler; and, biggest, the
agent loop itself (no agent runs as a service, nothing executes an accepted proposal
or grades on a schedule, openclaw is not designed). Order proposed by the orchestrator
(not yet confirmed by the user): prove the tools do real things first, then design
assessment and the food chain, then the loop.

### How the work ran today (process, so it is not re-learned)

Handoff, executor in a worktree, merge, **re-run both suites myself**, record. Two
findings came out "premise wrong" (the 145 reactions are in no raw file; a first
"nothing exists in DFHack" claim was overstated), so live reads beat offline
assumptions. **Worktree agents are created from `origin/main`**, not local HEAD, and
carry their own copy of `.claude/settings.json`: tell every dispatched agent to
`git merge --ff-only main` first. **Auto mode's classifier** refuses live dev-VM work
by its default rules ("Production Deploy", "Remote Shell Writes", "Modify Shared
Resources"); an `autoMode` block (environment, allow, soft_deny, each starting with
`"$defaults"`) was added to the user's `~/.claude/settings.json` on 2026-09-21 and
`claude auto-mode config` shows it merged; its effect is partly evidenced (a live
deploy dispatch and ssh reads went through in auto mode, three specific commands were
still refused). A backup of the previous file is in that session's scratchpad. **Write
scripts with the editor tool**: long shell heredocs containing quotes were rejected at
parse time repeatedly. **Hash committed bytes** (`git -c core.autocrlf=false show
HEAD:path`), not the working copy.

### START HERE, in priority order

**Sequencing rule:** one stream at a time on VM 103 or the fort. Two offline streams
may run together only with strictly disjoint file ownership. Push before dispatching
if the agent must see a commit, or tell it to fast-forward to local `main`.

1. **Redeploy `dfmcp` (labor join shapes) and check it live**: ship
   `dfmcp/labor_join.py` and `dfmcp/tool_guidance.py`, restart `dfmcp-server`, then
   call `building.find` for the Well over the live server and confirm the gap
   `needs 1 of TRAPPARTS, 0 available` reaches the agent. Asked of the user, not yet
   answered.
2. **The Office and Manager test.** Quicksave (confirm by every slot's mtime), place
   an Office with the zone tool (owner `MANAGER`; no fully indoor 3x3 site exists near
   the embark landmark at level 0, so it would be open-air, effect unknown), furnish it
   with the building tool (desk and chair; nothing places furniture inside a zone
   yet), read the room description, then one supervised unpause with the watchdog to
   see whether the queued orders run. Needs the user's go-ahead.
3. **The first real supervised build of a never-built kind** with the building tool
   (a Craftsdwarf's workshop, say): read-back, whether `buildingplan` picks up the
   materials (its state in the running game is unknown).
4. **Generalise `workjob`** (`handoffs/2026-09-21-workjob-generalise.md`, written, not
   dispatched): DFHack's `workshops.getJobs` builds a workshop's job list including
   reaction jobs, and a job has a `repeat` flag (a standing order with no manager).
5. **Design what is undesigned:** assessing dwarves, growing food end to end (re-read
   and trim `handoffs/2026-09-18-supervised-run-and-measure.md`: it is unrun and still
   the way to settle `growdur`, one real job duration with skill, claim state over an
   interval, and `item.age` against the pruned announcement buffer), stockpile
   creation and configuration, game-clock control, defence.
6. **Older open items still true:** a drink that does not depend on luck (brewing:
   `workjob` refuses the container reagent by design; the unlocated water source;
   fishing and hunting); the MCP apostrophe fix (the server refuses `Stoneworker's
   Workshop`); z167 stone (the rollback lost the stair; check before anyone plans on
   it); the `mason` labor in `df-overseer-workshop.lua` is wrong for block work
   (STONECUTTER); two unguarded `items.other.*` patterns crash loudly (hardening).
7. **The harness:** the user wants an overhaul of the auto versus manual setup. The
   `autoMode` fix is applied and partly evidenced; decide with the user whether a
   two-lane policy (offline work in auto mode, live VM work in manual) is still
   wanted.

**Parked ideas and settled rules (2026-09-21):** an **investigator** role (read-only
commands plus reading DFHack's source and docs, both on VM 103; not designed, and raw
`lua` is not read-only); **Dwarf Therapist** as an observation and cross-check tool
for the user (a GUI with no API, so agents cannot call it) and prior art for scoring
dwarves. **No armok capabilities** (`CLAUDE.md`, `docs/ARMOK-RULINGS.md`): the ban is
on powers a player lacks and on hidden information; the classification is
`research/2026-09-21-dfhack-tool-classification.*` and the review is
`research/2026-09-21-armok-review.md`. **Every tool must be generalisable**
(`CLAUDE.md`); `zone`, `building` and `nobles` follow it, `workjob`, `workshop` and
`orders.create` do not yet.

### Open, waiting on the user

- **The loop architecture: UNTABLED 2026-09-22, in design with the user**, see
  "In design: the agent loop MVP" below.
- **Key rotation** for four exposed secrets, deferred by the user ("ill rotate
  them another day"). See the section at the top of this file.

### Owed to home-lab (noted 2026-09-19, user-directed; not writable from here)

This repo may not edit `../home-lab`; route these to a session there or to the
user. Anything sent must carry the command actually run against the live
system, per `CLAUDE.md`'s upstream obligations.

- **`inventory/services.yaml`: add `dfseries-import` on VM 103**
  (`df-colony-01`), beside the existing `dfmcp-server` entry. A systemd
  oneshot service plus a 60s timer, **enabled 2026-09-19 on the user's
  go-ahead, so boot-persistent**. Code at `/opt/df/dfmcp-smoke/dfseries/`,
  database at `/var/lib/dfseries/uniboslan.series.sqlite3`, reads the sampler's
  JSONL under `/opt/df/game/dfhack-config/timeseries/`. Verify with
  `systemctl is-enabled dfseries-import.timer` and `systemctl is-active
  dfseries-import.timer` on VM 103. Full suggested entry in
  `handoffs/2026-09-19-dfseries-auto-import.md`, "What home-lab needs to know".
- **No IP changes**: nothing today allocated or changed an address, so
  `inventory/ips.yaml` is untouched.

### LAN addresses already public in git history (noted 2026-09-19, user-directed)

**Found 2026-09-19** while checking a new write-up for leaks: 
`working-archive/Working_archive-2026-09-07.md` has carried VM 103's and the
relay VM's LAN addresses, plus a VNC port and a noVNC URL, **on GitHub for
weeks**, against this repo's own rule. RFC1918 private addresses, so reachable
only from the home LAN or via the relay: low severity, but a real breach of
the rule, and the kind of detail a public repo exists not to hold.

- **Not yet decided by the user**, deliberately. Two options:
  1. **Redact from here on**: replace them in the current file with
     `<df-vm-ip>`-style placeholders. Cheap and safe, but the addresses remain
     readable in history forever.
  2. **Rewrite history** (`git filter-repo` over those strings, then a force
     push). Actually removes them, but rewrites every commit hash after the
     first occurrence, breaks every existing clone and worktree, and cannot be
     undone once pushed. Needs the user's explicit go-ahead, and every other
     session on this repo stopped first.
- **A guard already exists, and this note wrongly proposed one.**
  `tests/test_no_leaked_addresses.py` (commit `994e8a5`, 2026-09-12) fails the
  suite on any private IPv4 or `.internal` hostname in a tracked file. It
  **deliberately excludes `working-archive/`** as a historical record, which is
  exactly why the 09-07 archive's addresses never tripped it. So the real
  decision is whether that exclusion should stay. It caught this very note on
  2026-09-19, when an earlier draft quoted the illustrative example address
  from `infra/local.example.env` literally; those example values are already
  allowlisted in the `.example` file and `scripts/provision_vm.py`, and are not
  real addresses.

### Background, not urgent

- **Deferred by the user 2026-09-19: trigger import on each sample, not a 60s
  clock.** The 60s timer is correct (records carry their own `abs_tick`; import
  timing only affects freshness) but it lags up to a minute at 100 FPS and
  fires uselessly while paused. The better trigger is a systemd `.path` unit
  fired by the sampler's writes. Catch: a directory watch sees new files, not
  appends, and the file name changes per timeline, so the sampler would touch
  a fixed marker file (`.last_sample`) after each write. Keep the timer as a
  slow fallback. **Not** a DFHack-side hook: that would put external work back
  on the game loop.

- Two unguarded `items.other.*` access patterns (`trees.lua`'s
  `count_fort_owned_axes`, four in `stocks.lua`) **crash loudly** rather than
  silently zeroing. Loud failure is the acceptable end of that spectrum, so
  this is hardening, not a bug.
- The `PlantSeeds` measurement discrepancy: the queue drained 25 to 13 with no
  seed-stock change and no plants appearing, while the user reports the farm is
  genuinely being sown. That is a fault in **our reading**, not the fort.

## HANDOVER — archived

The 2026-09-12 session-end handover moved wholesale to
[`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md)
(file was past the ~400-line threshold). Its durable-traps list now lives
permanently at [`docs/TRAPS.md`](docs/TRAPS.md) — **read it there, and add new
traps there rather than here.** Current state is the section above.

## Archived

- Sections through 2026-09-10 (fifth handover) — provisioning build,
  perception eval, fort ledger, systemd units, title-screen bootstrap,
  live-viewing/relay/tunnel, the tileset investigation, Site Finder
  resolution, the embark-flow saga through both forts founded, and the
  seed-landmark bootstrap — all moved wholesale to
  [`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md)
  as each was superseded or reported itself finished.
- 2026-09-09: the 2026-09-08 (evening) handover moved wholesale to the
  same archive file.
- 2026-09-09 (end of session): this session's full handover (title-screen
  bootstrap resolution, the entire live-viewing/relay/tunnel build, the
  tileset investigation, and the Site Finder "Begin" resolution) moved
  wholesale to the same archive file — exceeded the ~400-line threshold,
  not superseded. The handover above is the tight current-state summary;
  the archive has the full detail.
- 2026-09-10: the 2026-09-09 (end of session) handover moved wholesale to
  the same archive file, superseded by this session's own handover above
  (Cloudflare Tunnel completion, the graphics-completeness fix, and the
  live embark-flow attempt).
- 2026-09-10 (second handover today): that session's own handover moved
  wholesale to the same archive file, superseded by this session's handover
  above (the click-registration mystery resolved, the real embark mechanism
  found, and the new "Confirm" crash).
- 2026-09-10 (third handover today): that session's own handover moved
  wholesale to the same archive file, superseded by this session's handover
  above — **the first fort was founded**, and the "Confirm" crash resolved
  empirically via gdb.
- 2026-09-10 (fourth handover today): that session's own handover moved
  wholesale to the same archive file, superseded by this session's handover
  above — the `find_mm_*`/`warn_mm_*` coordinate-frame bug found, and
  `xdotool` real-input fix for headless map/hover interaction discovered
  and validated.
- 2026-09-10 (fifth handover today): that session's own handover moved
  wholesale to the same archive file, superseded by the handover at the top
  of this file — the text-only sweep built and run, a Windows-specific SSH
  command-line truncation bug found and fixed in `provision_vm.ssh_guest`/
  `install_df.remote()`, and a strong second-site candidate found
  (`sx=128 sy=84 ex=131 ey=87`), left uncommitted for the user's call.
- 2026-09-10 (end of session): that handover's full continuation (the
  candidate embarked, Artobcatten's save lost as a result, the
  perception-layer branch split, the quorum-blocked snapshot worked
  around with a file backup, and Uniboslan's first room and stockpile dug)
  moved wholesale to the same archive file — exceeded the ~400-line
  threshold, not superseded by new work. The handover at the top of this
  file is the compacted current-state summary; the embark-screen-specific
  durable traps it used to carry were dropped rather than re-copied
  forward, since they're already the permanent living content of
  `docs/DF-UI-AUTOMATION.md`, not duplicated here.
- 2026-09-11: the 2026-09-11 VM-outage/quorum-incident writeup plus the
  entire 2026-09-10 end-of-session handover (VNC control channel, labor
  management/`autolabor`, the kea-combat finding, the quicksave root-cause,
  the perception-branch audit, both autonomous-play experiments, and the
  `find_diggable_area`/reachability corrections) moved wholesale to the
  same archive file — exceeded the ~400-line threshold by a wide margin,
  not superseded by new work. The handover at the top of this file is the
  compacted current-state summary, written deliberately thorough for a
  `/clear`; the archive has the full decision-by-decision detail.
- 2026-09-11 (documentation consistency pass): three fully-self-reporting
  ### threads moved wholesale to the same archive file: the compliance
  eval harness build (done for the session), mechanical prediction grading
  (built, selftested), and the full find_diggable_area/dig_diggable_area
  saga (built, live-verified, live-tested, the quickfort `-c` top-left-vs-
  center bug found and fixed, re-confirmed working end to end). None were
  gated on a human; item 10 in "What actually got built today" above now
  carries the compacted find_diggable_area/dig summary, and
  `decisions/DECISIONS.md`'s 2026-09-11 rows carry the full trail for all
  three.
- 2026-09-12: the entire 2026-09-11 end-of-session handover (the
  branch-merge question, the "what got built" list through item 12, and
  the peer-sessions/next-steps section) moved wholesale to the same
  archive file — the branch-merge question it spent most of its length on
  is resolved (merged, above), so it's fully superseded, not just over
  the line-count threshold. The handover at the top of this file is the
  new compacted current state.
- 2026-09-12 (session end, ahead of a `/clear`): this session's own content
  (the tool manifest build, both coordinate-leak fixes through deploy and
  live-verification, and the quorum correction) moved wholesale to the same
  archive file — it reports itself fully finished, nothing left gated on a
  human except the already-deferred design-commitment-#1 wording entry,
  carried forward unchanged. The handover at the top of this file is the
  fresh compacted current state, including two corrections the archived
  version's own text no longer reflects: both coordinate leaks are now
  fixed/deployed/verified (the archived text still frames them as open in
  a couple of places), and the driving-brain choice (`openclaw`) and
  live-view-ingest shelving are both folded in as settled state rather than
  same-session news.
- 2026-09-15: the whole 2026-09-12 to 09-14 section (the agent architecture design phase, the MCP server build and live smoke test, the durable deploy, openclaw install and first agent calls, both architect charter runs, the relative-LEVEL, isError and call-log fixes, and the dfqueue and live-signals builds) moved wholesale to
  [`working-archive/Working_archive-2026-09-14.md`](working-archive/Working_archive-2026-09-14.md).
  The file was 893 lines. Every still-open item was carried into the current-state section at the top.
- 2026-09-19: the whole HANDOVER 2026-09-17 section moved wholesale to the 2026-09-14 archive file. Its fort figures (tick 227008, "drink is solved") had been disproven by measurement and its stream list overtaken, but the fishing reversal, the stair background and the ground-truth idea live only there. Every still-open item was carried into HANDOVER 2026-09-19.
- 2026-09-17: the whole HANDOVER 2026-09-16 section (the production-gap discovery, the stocks/labor-race fix, the knowledge-scope audit, and the day-one farm-and-water work) moved wholesale to the same 2026-09-14 archive file, since the file exceeded the ~400-line threshold. Every still-open item was carried into HANDOVER 2026-09-17 at the top; nothing was summarised or dropped.
- 2026-09-21: the 2026-09-18 live-fort sections ("cannot drink") and the whole HANDOVER 2026-09-19 (rollback, walkability contradiction, the deploy and sampler updates, the old START HERE list and "Done today") moved wholesale to the 2026-09-14 archive file; the file was 586 lines. Open items were carried into HANDOVER 2026-09-21.
