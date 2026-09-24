# df-ai as prior art for fort planning

Date: 2026-09-24. Read-only research, answering
`handoffs/2026-09-24-df-ai-fort-planner.md`. Source: BenLubar/df-ai, cloned
to a scratch directory outside any worktree, `develop` branch (the repo's
default and only actively-referenced branch), HEAD at commit
`701ea36e0673c0b28572613a64287da585bbdfa3` ("update for r7", 2022-10-10).
Nothing from the clone is committed to this repo. No coordinate, grid or map
appears below, per `docs/PURPOSE.md` commitment 1.

## Verdict

**df-ai plans by placing one fixed, hand-authored fortress template as a
whole at embark, fitting it to terrain by randomized retry against hard
geometric constraints, not by search, scoring or reasoning about the
specific map** [read in source]. There is exactly one shipped plan file
(`plans/generic01.json`) built from thirty room templates (`rooms/templates/`,
four orientation variants each). The planner tries a room at a location
(a random surface point, a random spot near the start room, or a random
existing "connector" tile matching the room's tag), checks it against a
fixed list of geometric predicates (in bounds, not underwater, on/under the
right material, no building in the way, not directly under a cavern), and
if it fails, tries again — up to `max_failures` room-placement failures in a
row, and up to `max_retries` restarts of the whole plan, before giving up
and abandoning the fort entirely. **There is no site search, no scoring
between candidate sites, and no fallback to a smaller or different plan
shape**: the "plan" is a single shuffle-and-retry loop over one fixed
template graph. Growth is not re-planning; the whole plan, including its
generous upper bounds (e.g. up to 300 bedrooms), is laid out once at
embark as unbuilt placeholders, and population growth only decides *when*
an already-planned placeholder gets dug, never adds new plan structure.
The project's last commit predates Dwarf Fortress's v50 (Steam/Premium)
release by about two months and targets DF `0.47.05`; it almost certainly
does not run on this project's v50+/53.x Classic install as-is. The most
directly transferable idea is the **room template as a small, oriented,
reusable geometry-plus-furniture-plus-exits unit with a validity predicate**,
which does not require showing a model a map; the least transferable is the
**terrain-fitting method itself** (blind randomized retry against a fixed
geometric checklist), which is exactly the kind of reasoning this project's
own agents cannot do the way df-ai's hand-coded C++ does, because df-ai's
"search" is really coordinate arithmetic a human wrote, not something an
LLM could be asked to reproduce without seeing coordinates.

## Q1. The plan as data

[read in source, `701ea36`]

- **Room template** (`schemas/room-template.json`, `rooms/templates/*/{north,south,east,west}.json`):
  an object with `f` (furniture list) and `r` (room list, minItems 1).
  Each template ships four files, one per orientation, so the same room
  shape can be placed rotated to fit an approach direction without new
  authoring; e.g. `generic01_bedroom/north.json` places a bed at
  `(0,0,0)`, a cabinet and chest flagged `ignore` (present for footprint
  but not required), a door at `(-1,0,0)`, and a `bedroom` room spanning
  `min [1,0,0]` to `max [3,0,0]` referencing furniture indices via
  `layout: [0,1,2,3]`.
- **Furniture entry** (`schemas/room-instance.json#/definitions/furniture`):
  `type` (a `layout_type` enum), `construction`/`dig` designation enums,
  relative `x`/`y`/`z`, `ignore` (present but not required),  `makeroom`
  (this furniture piece defines the room boundary), `internal`,
  `stairs_special` (resolved to Up/Down/UpDown based on what's dug above
  and below it, see Q5), and `target` (links a door, say, to the room it
  serves).
- **Room entry**: `type` plus one kind-specific `*_type` enum
  (`corridor_type`, `farm_type`, `stockpile_type`, `workshop_type`,
  `furnace_type`, `nobleroom_type`, `outpost_type`, `location_type`,
  `cistern_type`), `min`/`max` bounding box, `exits` (named connection
  points other templates can attach to), `accesspath` (which other rooms
  in this template it connects through), `layout` (furniture indices it
  owns), `level` (a stacking hint), `queue` (placement priority), `outdoor`,
  `single_biome`, `require_walls`/`require_floor`/`require_grass`/
  `require_stone`, `remove_if_unused`, `build_when_accessible`. Every field
  is data, not code: there is no per-room-kind branch in the placement
  algorithm that reads this schema (kind is data selecting a template, per
  `docs/AGENT-ARCHITECTURE.md`'s generalisability principle, though df-ai
  itself never states that principle; it just happens to fall out of the
  design).
- **Plan** (`schemas/plan.json`, `plans/generic01.json`, the only one
  shipped): `start` (which template is the fortress entrance), `padding_x`/
  `padding_y` (space reserved around the entrance for the body of the
  fort), `tags` (named groups of template names, e.g.
  `generic01_generic` groups nine templates including bedrooms, corridors,
  workshops), `outdoor` (templates placed at random surface points instead
  of attached to the graph), `count_as` (one template instance counts as N
  of another kind, e.g. a `generic01_dormitory` counts as 39 bedrooms plus
  4 `bedrooms`), `limits` (min/max instance counts per template *type*,
  read from the actual file: `"generic01_bedroom": [120, 300]`,
  `"generic01_corridor": [5, 300]`, `"generic01_cage_trap": [20, 100]`),
  `instance_limits` (per-orientation-variant bounds), `priorities` (an
  ordered task list consumed at runtime, see Q5), `stock_goals`,
  `military_limit`. `max_retries` (default 25, whole-plan restarts) and
  `max_failures` (default 100, `generic01.json` overrides to 300,
  consecutive room-placement failures before giving up on the current
  attempt) are both plan-level knobs, confirming retry is the sole
  adaptation mechanism (Q2).
- **Not present**: any numeric scoring field, weight, or cost function
  anywhere in either schema. Placement is pass/fail, not ranked.

## Q2. Fitting a plan to terrain (most important question)

[read in source, `plan_setup_blueprint.cpp`, `plan_setup.cpp`, `701ea36`]

**Mechanism: randomized placement attempt, hard pass/fail geometric
validation, retry on failure, no search and no adaptation of the template
itself.** Three placement strategies, chosen by which phase of `build()` is
running (`plan_setup_blueprint.cpp:170-204`):

1. `try_add_room_start`: the very first room (the fortress entrance) is
   placed at one **uniformly random** x/y position within the map, offset
   by `padding_x`/`padding_y`, then validated.
2. `try_add_room_outdoor`: surface-only rooms (farms, the trade depot,
   pastures) are placed at another uniformly random x/y, snapped to the
   actual surface z-level (`Plan::surface_tile_at`, which walks down
   through map blocks skipping open/tree tiles), then validated.
3. `try_add_room_connect`: every other room is attached to a randomly
   chosen existing "connector" tile whose tag matches the room's own type
   (`room_connect`, a list of exit points accumulated as prior rooms are
   placed), then validated at that computed position.

Validation (`PlanSetup::can_add_room`, `plan_setup_blueprint.cpp:396-583`)
is a fixed checklist, not a scored fit: in map bounds; for outdoor rooms,
every tile must be open sky down to the surface (not underground, not
inside a building), plus optional grass-percentage and single-biome checks;
for underground rooms, every dig-designated tile must not be "directly
above a cavern" (checked by inspecting the 8 neighbours one z-level below
for open/non-wall material), no adjacent tile may have standing water
(`flow_size`, POOL/RIVER/BROOK material), and if `require_stone` is set the
surrounding shell must be STONE/MINERAL/FEATURE material, not soil. A
farmplot additionally rejects a spot if the tile below is frozen. **There
is no aquifer-specific check anywhere in the placement code** (confirmed by
`grep -rn aquifer` across all `.cpp`/`.h`: the only three hits are embark
*site selection* options `AquiferLight`/`AquiferHeavy` in `config.cpp`, and
a comment about wooden blocks for aquifer pumps in `stocks_queue.cpp`).
**df-ai's actual aquifer strategy is choosing an embark site without one (or
one it's configured to accept), not planning around one once digging
starts.** Ore veins, caverns and the surface are handled separately from
room placement: vein digging (`Plan::list_map_veins`/`dig_vein`) and cavern
outposts (`Plan::setup_blueprint_caverns`) run as their own post-plan
passes after `build_from_blueprint()` succeeds, using the same
spiral/BFS-style tile search (`AI::spiral_search`,
`Plan::find_typed_corridor`) rather than the room-placement retry loop.

**When a room will not fit**: the failure is counted, not diagnosed or
adapted around. `place_rooms` (`plan_setup_blueprint.cpp:206-244`) loops:
shuffle the available blueprint list, try each until one succeeds or
`plan.max_failures` consecutive failures accumulate, then stop that phase.
If the *first* phase (the entrance) never places anything, the whole
attempt is abandoned immediately (`build()`, `plan_setup_blueprint.cpp:178`).
At the top level, `build_from_blueprint` (`plan_setup.cpp:154-190`) tries
each shuffled plan template up to `plan.max_retries` times, fully clearing
and re-randomizing on each retry; only one plan template (`generic01`)
ships, so in practice this is "retry the same fixed layout with new random
numbers up to 25 times." **If every retry of every plan fails, `PlanSetup::Run`
logs "Failed to build blueprint." and calls `AI::abandon(out)`
(`plan_setup.cpp:64-67`) — the fort is abandoned outright.** There is no
degraded-plan fallback, no partial-plan acceptance beyond
`have_minimum_requirements` (a plan that placed *some* rooms but fewer than
a template's declared `limits` minimum is also treated as failed,
`plan_setup_blueprint.cpp:697-770`).

## Q3. Districts or relationships

[read in source, `plan_setup_blueprint.cpp`, `plans/generic01.json`, `701ea36`]

**Adjacency and "what belongs near what" is implicit in which templates
share a `tags` group and which exit points happen to be free when a room is
attempted, not an explicit rule engine.** `plan.json`'s `tags` (read from
`generic01.json`) group templates by *kind of thing*, e.g.
`generic01_generic` bundles bedrooms, a corridor, workshops (3x3 and 5x5),
jail, infirmary, nobleroom, location and dormitory into one pool;
`generic01_wide` bundles barracks, stockpile and well; `generic01_in_corridor`
is workshop_1x1 alone (small workshops that fit directly off a hallway
tile). `find_available_blueprints_connect` collects every free exit point
across the whole partially-built graph whose declared tag matches any tag
the candidate room belongs to, then **picks one uniformly at random**
(`plan_setup_blueprint.cpp:652-696`, `std::uniform_int_distribution` over
the candidate list). **There is no distance minimisation, no "place this
workshop near that stockpile" objective, and no proximity scoring between
a workshop and any particular stockpile kind anywhere in the placement
code.** The wider `count_as` and `limits`/`instance_limits` machinery
governs *how many* of each kind get built, not *where relative to what*.
Once a workshop and a stockpile both exist, matching them for hauling is
left entirely to Dwarf Fortress's own default stockpile-search behaviour;
`grep`ing the whole source tree for stockpile "give"/"take" link creation
(the mechanic that would let df-ai wire a workshop to a specific stockpile)
found nothing — **not confirmed present anywhere in this codebase**, which
this report flags rather than assumes either way. The closest thing to a
"central spine" idea is the corridor/connector-tag graph itself growing
outward from the single `start` room, but it is grown by random attachment
order, not by any stated floor-band or hub design.

## Q4. Growth

[read in source, `plan_setup.cpp`, `plan_assign.cpp`, `701ea36`]

**The plan does not grow at runtime; it is planned once, at embark, all the
way up to each template's `limits` maximum (e.g. up to 300 bedrooms, up to
300 corridor segments), as unbuilt placeholders (`room_status::plan`).**
`PlanSetup::Run` (`plan_setup.cpp:44-113`) is invoked exactly once, during
world generation/embark setup (its own log line: "Planning complete!"), and
nothing in `ai.cpp`, `population.cpp` or elsewhere re-invokes
`PlanSetup`/`build_from_blueprint` later in a running fort — confirmed by
`grep -n "PlanSetup"` across the tree returning only its one declaration
site and the one usage in `ai.cpp` checking whether that one-time exclusive
event is still running. "Growth" as population increases is entirely a
matter of **which already-planned placeholder gets dug and furnished next**:
`Plan::getbedroom` (`plan_assign.cpp:68-86`) looks first for a room the
citizen already owns, then any finished unassigned bedroom, then any
still-`plan`-status bedroom not already queued to dig, and calls `wantdig`
on it. **If none of the three is found — i.e. the plan's own `limits`
ceiling for that room kind has been exhausted — it logs
`"[ERROR] AI can't getbedroom(%d)"` and does nothing further.** There is no
code path that re-runs planning or extends the template graph to make room
for a citizen beyond what was budgeted at embark. Population growth is
therefore bounded by however generous the shipped plan's `limits` were
guessed to be, not by anything read from the live population at runtime.

## Q5. Execution

[read in source, `room.h`, `plan_task.cpp`, `701ea36`]

Each room has a four-state status enum (`room.h`: `plan`, `dig`, `dug`,
`finished`). The pipeline: a room starts as `plan` (placed in the graph,
nothing designated in-game); `wantdig` promotes it to `dig` (tiles get a
real DF dig designation); once DF's own miners finish, it becomes `dug`;
furniture/building construction against the `layout` furniture list then
brings it to `finished`. `stairs_special` furniture entries are resolved
after the whole graph is built (`PlanSetup::handle_stairs_special`,
`plan_setup_blueprint.cpp:823-877`): a tile is only turned into an
Up/Down/UpDown staircase if a corresponding stair actually exists one
z-level above/below it, computed once from the set of all placed stairs,
not per-template.

**Recovery from a failed step**: `Plan::checkroom` (`plan_task.cpp:349-393`),
run periodically over the room list (`checkroom_idx`, round-robin, a few
rooms per call — this project's own tripwire/observation-ledger pattern is
a distant cousin of this idea), re-applies three self-healing checks on
every non-`plan` room: `fixup_open` (patches missing walls/staircases) and
`r->dig()` re-issue a cancelled dig designation, with the comment
explicitly naming the causes it expects — **"damp stone, cave-in, or
tree"**; for `dug`/`finished` rooms, any furniture piece whose building id
no longer resolves (read: **destroyed by a tantrum**, per the comment "fix
missing walls/staircases" and "tantrumed furniture"/"tantrumed building")
is re-queued via `add_task(task_type::furnish, ...)`, and a missing room
building itself is rebuilt via `construct_room`. There is no distinct
"give up after N retries" ceiling visible in `checkroom` itself (unlike the
plan-level `max_failures`/`max_retries`); it just keeps re-issuing the fix
every sweep. `monitor_room_value` is queued separately when a room's
computed value falls short of `required_value`, a distinct ongoing check
from placement/construction.

## Q6. Known failures (most important alongside Q2)

[read in source, `git log`, `701ea36`, commit hashes as cited]

Read directly from df-ai's own commit history (1599 commits total on
`develop`), not inferred: a `git log --grep` sweep for stuck/infinite-loop
fixes turned up real, named unattended-play failures, several specifically
about layout or construction:

- **`f791f83` "Fix getting stuck on a workshop stockpile during fortress
  construction."** and **`b63524b` "fix garbage pit stockpile job getting
  stuck if a tree was nearby"** — stockpile/workshop placement interacting
  badly with terrain features not fully accounted for at plan time.
- **`b40eaa3` "fix outpost corridor sometimes going too close to rooms"**
  and **`ab2abf1` "Fix outpost corridors not connecting if they moved
  diagonally."** — the BFS-style corridor search (`find_typed_corridor`,
  Q2) failing to produce a usable path in some terrain shapes.
- **`0ddeb5a` "fix staircase corridors missing a staircase"** and
  **`d6a6f06` "fix rooms that were never built somehow"** — plan graph
  entries silently never reaching `finished` status, i.e. exactly the
  "growth/plan ceiling" failure mode named in Q4, but as a bug rather than
  a designed limit.
- **`dac668d` "fix blueprint blacklist not actually working at all"** and
  **`8ddd238` "Fix bugs causing the legacy plan to not be able to
  successfully finish building"** — the plan-completion check itself
  (`have_minimum_requirements`, Q2) was broken for a period, meaning a
  fortress could silently run with an incomplete plan or fail to ever be
  marked done.
- **`6e04942` "Fix stocks update (and therefore manager orders) never
  completing if the floor plan does not include a garbage pit. See #31."**
  — a single missing room *kind* in a custom plan cascading into an
  unrelated subsystem (manager orders) never functioning, a sharp
  "everything assumes the fixed plan is complete" failure shape.
- **`0e7bbb2` "plan: avoid infinite loop in move_river"** and
  **`4afc74c` "fix infinite loop if need more minerals"** — terrain-search
  loops (river relocation, vein search) with no termination guarantee in
  some map configurations, later given one.
- **`113448a` "Fix 48 missing bedrooms"**, **`2a67718` "Fix barracks,
  bedrooms, dining rooms, etc. never being created from the furniture,"**
  **`c665fe4`/`76fbde5`** dining-room sizing bugs, **`edc730c`/`e890c9f`**
  bedroom door placement bugs — a cluster of template/orientation-variant
  bugs (the four-orientation-file design in Q1 was itself a source of
  bugs: `0c6225b`/`b137a8a` "Fix north_east bedroom position"/"Fix two
  bedroom templates," `a9057e6` "Fix west_south bedrooms being placed on
  the wrong side of a corridor," all citing issue #59).

**This is second-hand relative to the actual runtime behaviour** (commit
messages describe what was fixed, not a live-observed session), but it is
first-hand relative to df-ai's own project history, which is exactly the
evidentiary bar the brief asked for absent a live install to test against.
No GitHub issue tracker or forum thread was fetched this session (see "What
could not be verified"); the commit log alone was judged sufficient given
its volume and specificity, and reaching further would have meant guessing
at network access this session did not attempt to confirm.

## Q7. Currency

[read in source, `701ea36`, `CHANGELOG.md`]

- **Default/only actively-referenced branch**: `develop`
  (`origin/HEAD -> origin/develop`), HEAD commit `701ea36e0673c0b28572613a64287da585bbdfa3`,
  committed 2022-10-10, message **"update for r7"**.
- **`CHANGELOG.md`**'s most recent dated section header is **`# 0.47.05-r1`**,
  with an undated `# Future` section above it (the unreleased commits since
  r1, ending at r7 per the final commit). `0.47.05` is a pre-v50 (pre-Steam/
  Premium) Dwarf Fortress version.
- **DF's v50 (Steam/Premium) release was December 2022**, roughly two
  months after this repo's last commit; no commit message, branch, tag or
  changelog entry anywhere in this history mentions v50, Steam, or Premium.
  Combined, this is strong (though not perfectly conclusive — see "not
  verified" below) evidence that **df-ai was never updated for the v50+
  engine rewrite and does not run on this project's v50+/53.x Classic
  install without a substantial, unattempted-by-upstream port.**
- The `develop` branch is the one referenced by the README's build
  instructions and the one `origin/HEAD` points to; a `gh-pages` branch
  (documentation) and a `ruby` branch (the pre-C++-port legacy
  implementation, referenced by commit `8603502`'s message "start the
  porting process over with a new plan: this will be a 1:1 port of the
  terrible ruby") also exist but were not explored further, being clearly
  older or non-code.

## What transfers to df-overseer

df-overseer's models must reason about space **without ever being shown a
map** (`docs/PURPOSE.md` commitment 1); df-ai's C++ code, by contrast,
directly manipulates raw tile coordinates throughout (`df::coord`, `x`/`y`/`z`
arithmetic everywhere in `plan_setup_blueprint.cpp`). Every idea below is
filtered through that difference explicitly.

**Survives the constraint:**

- **The room template as a named, reusable, small unit of geometry plus
  furniture plus typed exits, described in relative coordinates local to
  the template, not fortress coordinates.** This is exactly the same shape
  as this project's own `blueprints/templates/` (`<id>-v<n>.yaml` plus
  `.csv`, seam edges declared, walls as `finished` intent not material) —
  df-ai's `rooms/templates/*.json` is independent confirmation that this is
  a sound unit of composition, arrived at separately. A model can be shown
  "here is a bedroom template: one bed, one door, footprint 3x1" as a named
  concept and asked to place instances of it by *relationship* (next to the
  corridor tagged X, within the district tagged Y), never by coordinate.
- **Tags as a way to group templates by role for attachment, decoupled
  from any specific instance.** `plan.json`'s `tags` (`generic01_generic`,
  `generic01_wide`, etc.) is a district-shaped idea already: a named
  category of "things that can go here." This maps cleanly onto the
  districting/burrow design this project already owes a session on
  (`decisions/DECISIONS.md` 2026-09-24 site-ranking entry,
  `research/2026-09-24-burrow-district-designs.md`) — df-ai's tags are a
  coarser, purely-topological version of exactly that idea, with no
  distance metric attached, which is worth inheriting: **a model reasoning
  without coordinates cannot evaluate a distance metric anyway**, so a
  tag/category match ("this workshop wants to be placed via a
  `production`-tagged connector") is a *more* model-appropriate primitive
  than df-ai's own unused-but-possible alternative of a distance score
  would have been.
- **Hard pass/fail geometric predicates as an acceptance gate, kept
  separate from any placement search.** df-ai's `can_add_room` checklist
  (no water nearby, right material, no cavern below, no building in the
  way) is exactly the shape of this project's own `blueprint` verb's
  refusal to dig a plan it can prove will strand (`CLAUDE.md`'s own status
  banner) and the candidate rule tables in
  `research/2026-09-24-room-layout-best-practices.md` (`invariant` rows).
  This is a **verification** role a tool can own deterministically; nothing
  about it requires showing a model a map, since the tool runs the check
  and reports pass/fail/reason back as text, the same shape
  `zone.place`/`blueprint.plan` already use.
- **The self-healing periodic recheck (`checkroom`)** as a pattern: sweep
  placed structure, detect drift from intended state (cancelled dig,
  destroyed furniture, tantrumed building), and re-issue the fix
  automatically. This is close in spirit to this project's own
  tripwire/observation-ledger loop and needs no spatial reasoning to
  reproduce; it is a state-diff check, not a placement decision.
- **Room status as an explicit small state machine (`plan`/`dig`/`dug`/
  `finished`)** is a clean, model-legible vocabulary for reporting
  progress back to an agent in words ("this Office is still in `plan`
  status") without any grid.

**Does not survive the constraint, or transfers only with a substituted
mechanism:**

- **The terrain-fitting method itself: blind randomized retry against a
  fixed checklist.** This is only tractable because df-ai's C++ can iterate
  a random coordinate and test it in microseconds, thousands of times, with
  no cost to being wrong. An LLM agent cannot "try a random tile, see if it
  fails, try another" the way df-ai does — every attempt would be a real
  tool call and a real token cost, and the agent has no coordinate to try
  in the first place under commitment 1. **This is the central reason
  df-ai's core algorithm does not transfer**: its "search" is not a
  reasoning process worth imitating, it is brute-force coordinate
  enumeration a model was never going to be asked to do. What this project
  needs instead (and has already been building, per `CLAUDE.md`'s status
  banner: `zone.place`'s `AROUND_FURNITURE` flag, a shared tri-state
  reachability helper, the `blueprint` verb's own site search) is a tool
  that does df-ai's coordinate arithmetic internally and reports back in
  words ("no valid site found: candidate area overlaps water on its north
  edge"), which is the direction already taken independently of this
  research.
- **Random selection among tag-matching connectors with no distance
  objective (Q3).** Worth naming as a *limit* discovered in df-ai, not
  something to copy: df-ai never actually solves "put the workshop near its
  stockpile" despite superficially looking districted; it is topologically
  connected but not distance-optimised. This project's own
  `research/2026-09-24-room-layout-best-practices.md` Q6 already flagged
  the same real problem (the travel-weighted facility-layout question) as
  unsolved by any source it found; df-ai is now confirmed as *not* the
  missing answer to that question either. Do not treat df-ai's tag system
  as proof that adjacency is solved once tags exist.
- **A single fixed plan with hard population ceilings, silently erroring
  when exhausted (Q4).** This is a genuine anti-pattern this project should
  avoid reproducing: df-ai's own commit history (Q6) shows this exact
  category of bug repeatedly. A districting design for df-overseer should
  make room-count growth an explicit, checkable fact ("this district's
  bedroom capacity is N/limit") rather than a silent cap discovered only
  by a getbedroom-style log error.
- **All-or-nothing plan failure (abandon the fort) with no degraded
  fallback.** Directly contrary to this project's own posture (Uniboslan is
  "expendable, and rescuing it is worth trying for the tools it forces us
  to build," `CLAUDE.md`); df-ai optimises for "never run an incomplete
  fort," this project explicitly wants partial, recoverable, inspectable
  failure. Not a transferable design choice.
- **The C++ struct-level plumbing itself** (raw `df::coord`, direct DFHack
  struct reads for tile material/designation): irrelevant by construction,
  since this project's tools already read the equivalent live state through
  DFHack's Lua/Python API, not by porting df-ai's C++.

## What could not be verified

- **Whether df-ai actually fails to build or run against this project's
  installed DFHack/DF version.** This report's v50+ incompatibility
  conclusion (Q7) rests on commit-date and changelog evidence (the last
  commit predates the v50 release and never mentions it), which is strong
  but indirect; no attempt was made to build or run df-ai against this
  project's DF/DFHack install, and the brief specified no VM/game
  interaction for this stream. If df-ai has an unlisted or fork-maintained
  v50 port, this report would not have found it without a broader search
  than a single clone and `git log`.
- **Live runtime behaviour.** Everything about execution (Q5), recovery,
  and the failure modes in Q6 is read from source and commit messages, not
  from watching a running df-ai fort. No forum thread, GitHub issue, or
  BuildMaster/wiki page was fetched this session; the commit log was judged
  sufficient given its specificity, but a issue-tracker pass could turn up
  additional, more recent failure reports (this repo's `develop` branch
  history running to `701ea36` should already contain any fixes made in
  response to issues filed before that date, but not open/unfixed reports).
- **Whether any workshop-to-stockpile stockpile-link ("give"/"take")
  mechanism exists anywhere in df-ai outside the schema and placement code
  read this session.** A targeted grep found nothing; this is reported as
  a negative finding, not a confirmed absence across the entire ~150-file
  codebase, since not every file was read line by line.
- **The `ruby` branch** (the pre-C++-port legacy implementation) and
  `gh-pages` branch were not explored; if either contains materially
  different planning logic that later informed or diverged from the C++
  port, this report would not reflect it.
- **Forum/community write-ups of real unattended play failures** (the
  brief's own suggested source alongside issues and commit messages):
  none were fetched this session; Q6 relies entirely on the commit log,
  which is read-in-source, stronger evidence than forum anecdote would have
  been, but narrower in scope (only failures upstream chose to fix and
  document in a commit message would appear).

## Sources

Primary, read in source this session, all at commit
`701ea36e0673c0b28572613a64287da585bbdfa3` on `develop`
(github.com/BenLubar/df-ai, cloned to a scratch directory, not committed):
`README.md`, `CHANGELOG.md`, `schemas/room-template.json`,
`schemas/room-instance.json`, `schemas/plan.json`, `rooms/templates/generic01_bedroom/*.json`,
`plans/generic01.json`, `plan_find.cpp` (full), `plan_setup.cpp` (Run,
build_from_blueprint), `plan_setup_blueprint.cpp` (can_add_room,
try_add_room_start/outdoor/outdoor_shared/connect, place_rooms,
find_available_blueprints*, have_minimum_requirements, handle_stairs_special),
`plan_assign.cpp` (getbedroom), `plan_task.cpp` (checkroom), `room.h`
(room_status, room_type enums), `config.cpp` (aquifer embark options),
`ai.cpp` (PlanSetup exclusivity check), `git log` (1599 commits on
`develop`, targeted greps for stuck/infinite-loop/fix-room/fix-plan
messages, cited above by hash), `git branch -a`/`git remote show origin`
(default branch confirmation).

No docs or second-hand sources were used for any claim above; every finding
is read-in-source. This report does not repeat
`research/2026-09-24-room-layout-best-practices.md` or
`research/2026-09-24-burrow-district-designs.md`, both read in full first
per the brief, and cross-references them only where df-ai's evidence
directly bears on a gap either report named.
