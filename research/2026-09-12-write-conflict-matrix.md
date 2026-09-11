# Write-conflict matrix over the existing DFHack tool surface

Date: 2026-09-12. Read-only source audit, no live-system calls. Scope: every
command in `scripts/dfhack/TOOLS.yaml` and every `scripts/dfhack/df-overseer-*.lua`
file (10 files, confirmed by `Glob scripts/dfhack/df-overseer-*.lua`), plus
`docs/DF-UI-AUTOMATION.md` and `blueprints/` for the UI-input and blueprint
write paths. Every claim below is cited to a file and line from this
session's own read of the installed source, not recalled or inferred from
`TOOLS.yaml`'s prose alone; where `TOOLS.yaml` and the actual `.lua` code
line up, both are cited so the manifest's claims are shown to be checked, not
just trusted.

Goal question: can action authority over the fortress be safely partitioned
between multiple independent writers, or must it stay with one writer?

## Answer, up front

**Mostly yes for tile/building mutation, no for anything touching units, and
the "single writer" framing already has a live counterexample today:
`autolabor` is a second, independent, always-on writer over the exact field
`set_labor` also writes, and it already wins ties silently.** The four
mutating primitives that go through `quickfort -c x,y,z` (`build_at_landmark`,
`build_open_area`, `dig_diggable_area`, and the stockpile-placement case of
the first two) are cleanly disjoint from each other by construction (diggable
vs. walkable tile classes cannot overlap) and from everything else in this
tool surface (they never touch units, jobs, or labors). The one direct
non-quickfort mutation, `set_labor`, collides for real, today, with
`autolabor`'s own global relabeling cycle. The UI-input-path writers
(`click`, `embark-mode`, `leave-embark-mode`) collide with anything else
touching the shared X11 input channel, human or automated, by the project's
own documented rule (`docs/DF-UI-AUTOMATION.md` lines 33-40). Four of the six
planned roles (Quartermaster, Marshal in the write direction, Chronicler,
and Architect's smoothing/workshop-settings slice) have little or no tool
surface to even test for conflict, which is itself the most load-bearing
finding here: the partition question is premature for most of the roster
because there is nothing yet to partition.

## Command inventory

Effect legend: **R** = read, never mutates. **W** = mutates persistent game
state. Write path legend: **API** = direct DFHack Lua/struct write. **QF** =
`quickfort run BLUEPRINT_FILE -c x,y,z`. **UI** = simulated/real input event
against the current viewscreen.

| Script | Command | R/W | Mutates (cite) | Reads to decide (cite) | Write path | Ambient-state dependence |
|---|---|---|---|---|---|---|
| `df-overseer-connectivity.lua` | `report` | R | none | `warn-stranded.lua`'s `getStrandedGroups()` (line 69); `landmarks.nearest_landmark` (85) | n/a | none |
| `df-overseer-connectivity.lua` | `check FROM TO` | R | none | `get_landmark_centroid` (101, 106); `dfhack.maps.canWalkBetween`/`getWalkableGroup` (113-115) | n/a | none |
| `df-overseer-connectivity.lua` | `check-units A B` | R | none | `df.unit.find`, `dfhack.units.getPosition`, `canWalkBetween` (119-132) | n/a | none |
| `df-overseer-landmarks.lua` | `list` | R (see note below) | **latent**: `dfhack.persistent.saveSiteData(GLOBAL_KEY, ...)` (187), only on the fort's first-ever call with no seed persisted | `enumerate_buildings` (133-149), `enumerate_burrows` (151-171), `build_exits`/`canWalkBetween` (207-232) | n/a for the list itself; API for the latent seed write | none, except the seed write only fires once per save (guarded by `#state.landmarks == 0`, line 181) |
| `df-overseer-landmarks.lua` | `get NAME` | R | same latent seed-write path as `list` (calls `list_landmarks` internally, 265) | same as `list` | n/a / API (latent) | same as `list` |
| `df-overseer-landmarks.lua` | `build NAME BLUEPRINT_FILE` | **W** | tile designations / building / stockpile at the named landmark's centroid, via quickfort (327-329) | `get_landmark_centroid` (322) | QF, coordinate is internal-only (see header comment, 85-91) | none beyond needing the landmark to already exist |
| `df-overseer-overview.lua` | `get` (or no args) | R | none directly; transitively triggers the same latent landmark seed-write via `list_landmarks_mod.list_landmarks()` (74) | composes `list_landmarks` + `get_connectivity_report` (74-75) | n/a | none |
| `df-overseer-diff.lua` | `since CURSOR` | R | **process-state side effect on first load only**: registers 4 `eventful` listeners into a shared, unpartitioned `_G` ring buffer (130-202) | drains `_G.__df_overseer_diff_log` (210-218) | n/a | shared, unpartitioned event log: every caller (any agent) reads from the SAME buffer and counter; no per-caller isolation, no trimming (see conclusions) |
| `df-overseer-diff.lua` | `recent-combat [N]` | R | none | `df.global.world.status.reports` (251) | n/a | none (works even while paused, 249-256) |
| `df-overseer-diff.lua` | `since-report REPORT_ID` | R | none | same report store (276) | n/a | none |
| `df-overseer-openarea.lua` | `find W H [Z] NEAR [RADIUS]` | R | none | `is_free` = `getWalkableGroup` + `buildings.findAtTile` (101-109); `ranked_candidates`/`get_landmark_centroid` (155-166) | n/a | none |
| `df-overseer-openarea.lua` | `build W H [Z] NEAR BLUEPRINT [RANK] [RADIUS]` | **W** | tile designations / building / stockpile inside the ranked-candidate box, via quickfort (294-296) | same `ranked_candidates` scan as `find` (253) | QF, coordinate internal-only (271-296) | none, but see conclusions on cross-call race with other box-mutating tools |
| `df-overseer-chokepoints.lua` | `find Z NEAR [RADIUS]` | R | none | `walkable`/`free`/`is_stair_or_ramp` (60-95) | n/a | none. **Note**: `pos_for_action_tools` (134) deliberately returns a raw coordinate, the one documented exception to design commitment #1 (header, 44-49) |
| `df-overseer-diggable.lua` | `find W H [Z] NEAR [RADIUS]` | R | none | `is_diggable` = `getWalkableGroup` + `getTileType` + `tiletype.attrs.shape/material` (121-137) | n/a | none |
| `df-overseer-diggable.lua` | `dig W H [Z] NEAR BLUEPRINT [RANK] [RADIUS]` | **W** | real dig designations on solid, non-walkable tiles inside the ranked-candidate box, via quickfort (361-363) | same `ranked_candidates`/`borders_walkable_network` scan as `find` (321) | QF, coordinate internal-only (341-363) | none, but see conclusions |
| `df-overseer-stuckjobs.lua` | `find [MIN_IDLE_TICKS]` | R | **process-state side effect on first load only**: registers a `JOB_INITIATED` listener into a shared, unpartitioned `_G` table (56-59) | `utils.listpairs(df.global.world.jobs.list)` (67), `dfhack.job.getWorker` (68) | n/a | shared `_G.__df_overseer_job_start_tick` table, same unpartitioned-resource caveat as `diff.lua`'s log |
| `df-overseer-labor.lua` | `unit-status [idle\|injured\|military\|hostile]` | R | none | `unit.job.current_job`, `unit.body.wounds`, `unit.military.squad_id`, `dfhack.units.isDanger/isInvader/isOwnCiv` (119-147) | n/a | none. **Note**: the `hostile` filter is documented-unreliable (missed a real kea attack, flagged harmless demons; `decisions/DECISIONS.md` 2026-09-11) |
| `df-overseer-labor.lua` | `labors UNIT_ID` | R | none | `unit.status.labors[code]` read loop (181-185) | n/a | none |
| `df-overseer-labor.lua` | `set-labor UNIT_ID LABOR_NAME on\|off` | **W** | `unit.status.labors[code] = state` (196), one bit on one named unit | `df.unit_labor[labor_name]` lookup (192) | API, direct struct write | **collides with `autolabor`**, see conclusions |
| `df-overseer-ui.lua` | `type` | R | none | `dfhack.gui.getDFViewscreen(true)._type` (30) | n/a | reports whatever screen is currently focused |
| `df-overseer-ui.lua` | `click TEXT` | **W** | **whatever the matched on-screen button's own handler does** (unbounded, screen-dependent), via `df.global.gps.mouse_x/y` write (72-73) + `gui.simulateInput('_MOUSE_L')` (74) | full-buffer text scan, `dfhack.screen.readTile` (39-52) | UI (simulated input) | **fully ambient**: same call does something different depending on the currently-focused viewscreen and its buffer text; known false-match risk (docs/DF-UI-AUTOMATION.md 78-90) |
| `df-overseer-ui.lua` | `dump` | R | none | `dfhack.screen.readTile` (85-105) | n/a | reports whatever screen is currently focused |
| `df-overseer-ui.lua` | `embark-mode` | **W** | flips `scr.choosing_embark` via a fixed-position click (127-129) | `scr.choosing_embark` (124) | UI (simulated input, fixed screen position not a text scan, 117-121) | requires caller already on `viewscreen_choose_start_sitest` with `zoomed_in=true` (comment, 120-121) |
| `df-overseer-ui.lua` | `leave-embark-mode` | **W** | cancels `choosing_embark` via `gui.simulateInput('LEAVESCREEN')` (142) | `scr.choosing_embark` (141, 144) | UI | only meaningful mid-embark-flow |
| `df-overseer-ui.lua` | `hover` | R (of DFHack state) | none | `scr.neighbor_hover_mm_*` + buffer-scanned criteria rows (166-188) | n/a | **result is meaningless unless a real X11 mouse move happened first, driven externally by `xdotool`, not by this script** (comment, 149-153); only live-updates while `choosing_embark` is true (`docs/DF-UI-AUTOMATION.md` "Built 2026-09-10 (fifth pass)" section, not in this file's own comments) |

Total: 25 CLI subcommands across 10 files. 18 are pure reads (2 of which have
a latent, one-time, self-guarded persistent-data write buried inside them).
7 are real mutations: 3 go through `quickfort` with an internal-only
coordinate, 1 is a direct API bitfield write, and 3 go through the UI/input
path.

## Conclusion 1: cleanly sliceable vs. not

**Cleanly sliceable** (no ambient-UI-state dependence, mutation target fully
determined by the call's own explicit arguments, disjoint by construction
from every other tool's mutation target):

- `build_at_landmark` (`df-overseer-landmarks.lua:321`)
- `build_open_area` (`df-overseer-openarea.lua:251`)
- `dig_diggable_area` (`df-overseer-diggable.lua:319`)
- `set_labor` (`df-overseer-labor.lua:191`), sliceable with respect to
  *this tool surface*, but not with respect to `autolabor` (see Conclusion 2)
- Every read-only command, trivially, since none of them mutate anything

**Not cleanly sliceable:**

- `click`, `embark-mode`, `leave-embark-mode` (`df-overseer-ui.lua`): the
  mutation target is "whatever the currently-focused viewscreen does with
  this input," which is not an argument to the call at all, it is whatever
  state the shared DF process happens to be in. `click`'s own known flaw
  (false-matching earlier occurrences of the target text on the same screen,
  `docs/DF-UI-AUTOMATION.md` lines 78-90) means even a single caller cannot
  always predict what its own call will hit.
- `hover` is a read, but its output is meaningless without externally-driven
  ambient mouse state (`df-overseer-ui.lua:149-153`), so it cannot be
  evaluated as "safe to hand to an independent reader" without also handing
  that reader control of the one shared X11 cursor, which is a write-side
  resource in practice even though `hover` itself never mutates anything.
- `since` (`df-overseer-diff.lua`) and `find` (`df-overseer-stuckjobs.lua`)
  are reads of fort state, but both drain from or write into a single
  process-wide `_G` table shared by literally every caller, with no
  per-caller cursor isolation and no trimming (`drain_since`'s own comment,
  `df-overseer-diff.lua:205-209`, flags trimming as a known future risk).
  Two independent agents polling `since` with their own separately-tracked
  cursors works only if both agents are individually disciplined about
  cursor bookkeeping; the tool itself provides no isolation between them.
- `list`/`get` in `df-overseer-landmarks.lua` (and transitively
  `df-overseer-overview.lua get`, and every other script that reqscripts
  `nearest_landmark`/`get_landmark_centroid`) carry a latent, one-time
  `dfhack.persistent.saveSiteData` write (line 187) the very first time any
  caller asks for landmarks on a fresh fort with no seed yet. It is
  self-guarded (idempotent past the first call) so it is not a live risk in
  a fort that already has a seed, but it means "list is a pure read" is only
  true after that first call has happened once, by whoever happens to call
  it first.

## Conclusion 2: safe concurrent sets vs. concrete collisions

**Safe as a set:** `{build_at_landmark, build_open_area, dig_diggable_area}`.
`build_open_area`/`build_at_landmark` only ever target tiles that are
already walkable (`is_free`, `df-overseer-openarea.lua:101-109`) and
`dig_diggable_area` only ever targets tiles that are explicitly non-walkable
(`is_diggable`, `df-overseer-diggable.lua:121-137`); those two predicates are
mutually exclusive by construction, so the same tile cannot be a valid
candidate for both in the same fort state. This is a real, structural
disjointness, not a policy convention. What it does **not** cover: nothing
in the tool layer reserves a candidate box between the read (`find`/
`ranked_candidates`) and the write (`build`/`dig`) across two *independent*
calls. Each fused resolve-and-act call is atomic with respect to its own
internal read-then-write, but two agents independently calling `build_open_area`
near the same landmark within the same radius could both rank the same
"rank 1" box (the ranking is deterministic given the same `w,h,z,near,radius`,
`df-overseer-openarea.lua:155-193`) and both attempt to build there; the
second call's `quickfort` invocation would either land on now-occupied space
or silently produce a degenerate result, and nothing here detects or
reports that. No locking or reservation mechanism exists anywhere in this
codebase's write path.

**Safe:** any read-only command against any other command, including every
write command, by construction. This includes `unit-status`, `get_stuck_jobs`,
`get_overview`, `find_open_area`, `find_diggable_area`, `find_chokepoints`,
`report`, `check`, `list`, `get NAME`, `labors`, `since`/`recent-combat`/
`since-report`, `type`, `dump`. None of these mutate fort state (see the
inventory's latent-write caveats above for the two narrow exceptions).

**Concrete collision 1, live today:** `set_labor` vs. `autolabor`.
`decisions/DECISIONS.md`'s 2026-09-11 rows confirm `autolabor` is enabled on
the live fort and "confirmed actually assigning jobs, not just reporting
status" (idle count dropped 6 to 1 during a real unpause). `autolabor`'s own
documented behavior, per that same row, "explicitly leaves dwarves on active
military duty or assigned to a burrow untouched," which is the mechanism the
row cites for it not fighting the manual `set-labor` calls that predated it.
The exact same field, `unit.status.labors[code]` (`df-overseer-labor.lua:196`),
is written by both `set_labor` and `autolabor`'s own recalculation cycle. Any
`set_labor` write to a unit that is *not* on military duty or burrow-restricted
is a genuine, unprotected race against `autolabor`'s next cycle, which is
documented to run continuously, not on request. This is not a hypothetical:
it is the current live state of the fort. A Quartermaster or Marshal role
that wants to steer labor toward, say, hauling food or brewing drink for an
ordinary citizen would have that exact write silently reverted by `autolabor`
unless it also restricted that unit to a burrow or military duty first, which
is itself a write this tool surface has no primitive for either (burrows are
read-only landmarks here, see Conclusion 4).

**Concrete collision 2, documented but not yet exercised as a live-fort
action tool:** `click`/`embark-mode`/`leave-embark-mode` vs. anything else
on the shared X11 input channel. `docs/DF-UI-AUTOMATION.md` lines 33-40
state this explicitly and generally: "any use of `xdotool` (or any other
real-X11-input mechanism) against VM 103 must be called out explicitly," and
"there is no separation between 'the AI's simulated hand' and 'a person's
real hand' at the X11 level." Today these three commands are only used for
the embark-bootstrap flow, before any fort exists, and the personal-control
VNC channel (`decisions/DECISIONS.md` 2026-09-11 rows) is a real second
occupant of that same input channel. If any future Marshal/Architect action
tool were built on this same UI-click mechanism (e.g. clicking through a
squad-assignment or stockpile-settings screen, since neither has a
struct-level API used anywhere in this repo yet), it would collide with a
human on the control VNC channel exactly as this doc already warns, and with
any other concurrent agent doing the same thing.

**Not yet a collision because the domain does not exist:** manager work
orders and stockpile settings never appear as a write target anywhere in
this tool surface (see Conclusion 3), so there is nothing to check them
against for conflict yet.

## Conclusion 3: is "work orders + stockpile settings" a disjoint domain?

**Cannot be settled empirically against this repo's actual code, because
neither half of that domain has any tool surface at all.** Read every
`.lua` file in `scripts/dfhack/`: none of them touch a manager work-order
queue (no `df.global.plotinfo.manager_orders` or equivalent appears
anywhere), and none of them touch stockpile *settings* in the sense of item
filters, take/give links, or bin/barrel toggles. The one stockpile-adjacent
write that exists, `build_open_area`/`build_at_landmark` run against
`starter-stockpile-5x5.csv` (a `#place` blueprint, `blueprints/README.md`
lines 14-19), creates the stockpile *building* once; it is a construction
action, structurally identical to placing any other building, not an
ongoing settings-adjustment action. `memory/dfhack-environment.md` lines
71-73 confirm `stocks` and `workflow`, the two stock DFHack tools that would
most naturally cover this domain, are both tagged `unavailable` on this
exact install, so a future build of this domain cannot lean on them either.

What CAN be said from the code that does exist: manager work orders and
stockpile filter/link fields are structurally different DFHack surfaces from
tile designations, buildings, and burrows (the Architect's domain per this
task's roster), so a naive read of "what fields does each touch" suggests
disjointness, the same way `build_open_area` and `dig_diggable_area` are
disjoint by predicate. But this project already has one live counterexample
to trusting that kind of structural-disjointness argument without checking
underneath it: `autolabor` looks like it lives entirely in "labor policy,"
separate from "tile designation," until you notice it writes the exact same
field `set_labor` does. The same shape of hidden coupling is plausible here:
a Quartermaster whose job is "food, drink, work orders, stock thresholds" is
extremely likely to need dwarves actually reassigned toward hauling, cooking,
or brewing labor when a threshold trips, since something has to physically
move or process the goods a work order or stockpile threshold names. The
only labor-writing tool that exists today is `set_labor`, the same one that
already collides with `autolabor`. So: **the tile/building side and the
work-order/stockpile side look disjoint on paper, but the moment either
domain's implementation reaches for labor assignment (which a working
Quartermaster almost certainly will), it inherits the exact `set_labor`/
`autolabor` collision already documented above.** This is a real risk to
flag before building the domain, not an answered question; it would need a
firm rule about which agent (if any) is allowed to touch `unit.status.labors`
before Quartermaster and Architect could be considered truly independent
writers.

## Conclusion 4: tool-surface gaps per planned role

**Overseer (sole actor).** Every command in the inventory above belongs to
Overseer today, since it is the only actor. This is the baseline the other
five roles are gaps *from*.

**Architect (rooms/workshops/smoothing).** Exists: `find_open_area`/
`build_open_area` (built-terrain placement, `df-overseer-openarea.lua`),
`find_diggable_area`/`dig_diggable_area` (excavation,
`df-overseer-diggable.lua`), `find_chokepoints` (door/trap siting, read-only,
`df-overseer-chokepoints.lua`), `build_at_landmark` (landmark-anchored
placement, `df-overseer-landmarks.lua`), and four starter blueprints
(`blueprints/starter-{entrance,connector,room,stockpile}-*.csv`). Entirely
missing: smoothing/engraving (no script anywhere calls quickfort's smoothing
mode or any `dfhack.designations` smoothing field); workshop-type-aware
placement or material-availability checking (the existing `build` commands
take an arbitrary blueprint file, with no workshop-specific logic); any
deconstruction/demolition primitive; `rank_candidate_sites`, explicitly
still blocked per `TOOLS.yaml` lines 361-366 on `resource_summary` data that
does not exist.

**Quartermaster (food, drink, work orders, stock thresholds).** Exists:
effectively nothing purpose-built. `get_stuck_jobs` could incidentally
surface a stalled hauling/cooking job but has no food/drink-specific framing
at all. Entirely missing, bluntly: no manager work-order tool (create,
cancel, or query the production queue) anywhere in `scripts/dfhack/`; no
stockpile-settings tool (filters, thresholds, give/take links, bins/barrels)
anywhere; no food/drink stock-level query at all, despite `prospector` being
confirmed *available* on this install (`memory/dfhack-environment.md` line
67) and never wired into anything here; the only stockpile-touching command
that exists creates a stockpile's physical building once and never manages
it afterward. Quartermaster has essentially zero tool surface today.

**Marshal (military posture, burrows, squads).** Exists: `unit-status
military` (read-only, `unit.military.squad_id ~= -1`) and `unit-status
hostile` (read-only, and empirically proven **unreliable**: missed a real
kea attack entirely while flagging harmless demons as threats,
`decisions/DECISIONS.md` 2026-09-11); burrows appear only as read-only
landmarks via `enumerate_burrows` (`df-overseer-landmarks.lua:151-171`), with
no burrow-creation or burrow-membership write tool anywhere. The
diff/event log (`df-overseer-diff.lua`) is the closest thing to a real
threat-detection primitive and it is read-only reporting, not a posture-setting
action. Entirely missing: any squad-management write (create a squad, assign
a unit, set alert level or station/patrol orders); any burrow-write tool
(burrows are purely read-only landmarks in this codebase). Marshal has
read-only visibility and a documented-unreliable signal, and zero write
tools of its own.

**Consultant (knowledge only).** By its own definition this role needs only
read access, and essentially the entire read-only surface in this inventory
(`report`, `check`, `check-units`, `list`, `get NAME`, `get_overview`,
`find_open_area`, `find_diggable_area`, `find_chokepoints`, `get_stuck_jobs`,
`unit-status`, `labors`, `since`, `recent-combat`, `since-report`, `type`,
`dump`) is already usable as-is, with no gaps specific to this role beyond
the same `unit-status hostile` unreliability every role inherits.

**Chronicler (writes history).** Exists: nothing. There is no
chronicle-writing tool anywhere in `scripts/dfhack/`. `docs/PURPOSE.md`
describes "the chronicle" as a design goal ("markdown in-repo, source of
truth," line 106, 113) but no script, Lua or otherwise, in this repo writes
a chronicle entry anywhere. The closest existing primitive is
`df-overseer-diff.lua`'s `_G` event log, which is explicitly documented as
ephemeral and session-scoped, "not durable across a restart, and nothing in
this design needs it to survive one" (header comment, lines 18-22), the
opposite property a chronicle needs. Chronicler has zero tool surface: no
tailored read for "what's chronicle-worthy," no write path to persist
anything anywhere, not even a stub writing to a markdown file or
`dfhack.persistent`. This is the starkest gap of the six roles.

## Not verified / caveats

- This audit is source-only. No command was executed, no live fort state was
  read, per the task's explicit read-only constraint. Every "verified"/
  "unverified" tag inside `TOOLS.yaml` was carried through as-is (e.g.
  `build_at_landmark` and `check FROM TO` are both marked `unverified` there,
  meaning the collision/sliceability analysis above for those two rests on
  reading their code, not on a confirmed live test of that exact code path).
- The "no locking mechanism exists" claim in Conclusion 2 is a claim about
  the absence of code, not something that can be proven by more reading;
  it is based on an exhaustive read of all 10 files and finding no mutex,
  reservation table, or coordination primitive anywhere in them, plus no
  reference to one in `TOOLS.yaml`'s own notes.
- The `_G` event-log/job-tracking sharing concern (Conclusion 1) is a
  structural reading of the code (single global table, no per-caller
  partition visible in the source) and was not tested against two genuinely
  concurrent `dfhack-run` invocations in this session; the general fact that
  `_G` state persists across separate `dfhack-run` calls within one DF
  process *is* independently verified live per `decisions/DECISIONS.md`
  2026-09-10, just not the specific two-independent-readers-racing scenario.
- Whether `dfhack.persistent.saveSiteData`'s one-time latent write
  (`df-overseer-landmarks.lua:187`) could itself race two simultaneous
  first-ever callers on a brand-new fort was not tested; Uniboslan already
  has a persisted seed, so this path is dormant on the live fort today and
  could not be exercised even if live testing were in scope.
- `docs/MEMORY-ARCHITECTURE.md` was not read for this audit; it was outside
  the requested file set (`TOOLS.yaml`, the `.lua` files,
  `docs/DF-UI-AUTOMATION.md`, `blueprints/`) and is unlikely to change any
  conclusion about the DFHack tool surface itself, but a Chronicler-role
  design pass should read it before building anything, since it may already
  specify the chronicle's intended storage shape.

## Sources

`scripts/dfhack/TOOLS.yaml` (full file). `scripts/dfhack/df-overseer-{connectivity,
landmarks,overview,diff,openarea,chokepoints,diggable,stuckjobs,labor,ui}.lua`
(full files, all 10). `docs/DF-UI-AUTOMATION.md` (full file). `blueprints/README.md`.
`docs/PURPOSE.md` (design commitments and build order). `memory/dfhack-environment.md`
(tool availability, the quickfort top-left-vs-center bug). `decisions/DECISIONS.md`
2026-09-10 through 2026-09-12 rows (autolabor enablement and confirmed job
assignment, the kea/`unit-status hostile` unreliability finding, the
`_G`-state-persists-across-invocations finding, the Stockpile #2 and dig
closed-loop rows).
