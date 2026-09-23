# Handoff: nothing can list the zones that exist, or say which of them are valid

Date: 2026-09-23. **Offline. No VM, no deploy, no fort mutation, no unpause.**
The deploy needs its own go-ahead and the orchestrating session will ask
separately.

Read `CLAUDE.md` first, then `research/2026-09-23-room-and-zone-requirements.md`,
the `rooms` entries in `doctrine/seed.yaml`, `scripts/dfhack/df-overseer-zone.lua`,
and the `nobles.requirements` verb added earlier today in
`scripts/dfhack/df-overseer-nobles.lua` (its three-state met / not_met /
cannot_tell discipline is the pattern to follow, not to reinvent).

## How this was found, which matters for how you fix it

The Architect was given a real task today: give the Manager a working office.
It was deliberately told nothing about why the previous attempt failed. It
worked out the mechanism unaided and correctly, and then stated as fact:

> "there is no Office zone anywhere"

There are two. Ids 10 and 11, both Office, both owned, confirmed by dropping
to raw Lua because **no tool in this project can enumerate existing zones**.
It reached "none" from `landmarks.list`, which does not list zones, because
that is the closest thing it had.

That is not a model failure. `zone` today offers `list-kinds` (what kinds can
be placed), `find` (candidate empty areas), `check-owner` and `place`. Nothing
answers "what zones exist right now", so every role is structurally blind to
the fort's own rooms.

The same run found a second defect, in its own words:

> "`zone.find` for Office only returns empty rectangles (it rejects occupied
> tiles, which is where the chair sits); a bare empty office would have no
> chair to work at and a room value of 0"

A room needs furniture inside its footprint to have any value. `zone.find`
structurally cannot propose such a site, so a room sited from its output is
reliably worthless. That is how this fort ended up with two empty offices.

## What to build

### 1. An inventory of the zones that exist

A read that answers "what zones does this fort have". **Design it for fifty
bedrooms, not for two offices**, because that is where this fort is going and
a tool that returns fifty rows of detail is a tool nobody can use:

- **Filters**, so a caller can ask a narrow question: by kind, by owner
  (including unowned), by validity (below), and by proximity to a named
  landmark. Filters compose.
- **Summarise by default, detail on request.** An unfiltered call should
  return counts per kind plus the entries that need attention, not every
  zone. State your chosen default and defend it.
- **Identity without coordinates.** A caller must be able to refer to one
  specific bedroom out of fifty in a later call, while
  `docs/PURPOSE.md` commitment 1 forbids coordinates. The zone's own id is an
  opaque identifier and is already the precedent (`order."ID".exists`,
  `landmark."NAME"`). Nearest-landmark plus a stable ordinal is the other
  candidate. Pick one, say why, and make it stable across calls.
- **Bounded.** One pass over the civzone list, never a tile scan.

### 2. A validity check over zones

The user's framing: a way to confirm which zones are actually valid. Per zone,
answer whether it is doing its job, in the same three states
`nobles.requirements` uses, with `cannot_tell` never collapsed into a failure:

- A zone of a kind with a `room_value_field` whose `getRoomDescription` reads
  empty is **not valid**: it is a rectangle, not a room. This is the exact
  condition that went unnoticed on this fort for two days.
- An `owner_capable` kind with no owner is worth reporting as its own state,
  distinct from invalid.
- A failed read is `cannot_tell`, with `read_failures` and `dfhack.printerr`,
  per the established discipline.

This wants to work fleet-wide in one call: "which of my rooms are not really
rooms" is the question, and at fifty bedrooms it is the only way anyone will
ever notice.

### 3. Let `find` site a room around furniture that already exists

`zone.find` must be able to propose a footprint that **contains** qualifying
furniture rather than rejecting every occupied tile. Decide the interface: a
mode or flag, or a separate verb, and justify it. Two properties matter:

- For a kind with a `room_value_field`, a site containing no qualifying
  furniture should be reported as such rather than returned as if it were
  fine. The caller may still want it (they may intend to build furniture
  after), so inform, do not refuse.
- Per-kind knowledge of what furniture qualifies belongs in data, not in
  branches. The existing `ZONE_POLICY` table is the natural home.

**Do not hardcode the office case.** A bedroom needs a bed, a dining room a
table, a tomb a coffin. One table, one code path.

## Scope

Yours: `scripts/dfhack/df-overseer-zone.lua`, `scripts/dfhack/TOOLS.yaml`, the
`dfmcp` schema for any new command, read-only grants in `agents/*/tools.yaml`
(a tool in no allowlist is unreachable, principle 8), and tests. No new write
verbs; `zone.place` keeps its current single-writer position.

Not yours: `df-overseer-nobles.lua` (just changed, and its
`nobles.requirements` is the consumer of this work, not part of it),
`conductor/**`, `doctrine/**`, any other `.lua`, and per the `handoffs/` rule
`Working.md`, `decisions/DECISIONS.md`, `memory/` and `handoffs/INDEX.md`.

## Rules

- **Offline only.** The fort is paused with a confirmed quicksave and stays
  that way. The live fort has exactly two zones, both Office, ids 10 and 11,
  both owned, both empty of furniture, with the fort's only Chair outside both
  footprints. That is your worked example; you may not read it live.
- `git merge --ff-only main` first; this brief is committed on main.
- Both suites green with numbers quoted: ambient `python -m pytest` (baseline
  **1398 passed, 3 skipped**) and `dfmcp/tests` in `.venv-dfmcp` (baseline
  **652 passed**). Use `python`, not `py -3`.
- Keep every output coordinate-free and never render or reconstruct a map.
- No em dashes in prose. **No attribution lines in any commit message.**
- Stop and report on any permission or classifier refusal. Never route around
  one through another agent or session.

## Done means

A role can ask what zones exist, narrow that question by kind, owner,
validity and landmark, refer to one specific zone afterwards without a
coordinate, and be told which zones are not really rooms. `zone.find` can
propose a site around furniture that already exists. Every answer scales to
fifty bedrooms without flooding the caller. The Result names the live checks a
deploy should run, starting with this fort's two known-invalid Office zones.

## Result

Built offline, no VM, no deploy, no unpause, as instructed. All three pieces
landed in `scripts/dfhack/df-overseer-zone.lua`:

**1. Inventory (`zone.list KIND_FILTER OWNER_FILTER VALID_FILTER
NEAR_LANDMARK_FILTER [RADIUS_TILES]`).** One bounded pass over the
fortress's own civzone vector (`ACTIVITY_ZONE`, capped at `MAX_ZONE_SCAN`
5000), never a tile scan. Four composable filters, each `""` for "no
filter" (the same sentinel convention `check-owner`'s `OWNER` already
established, so this isn't a new idiom). **Identity is the zone's own id**
(`z.id`), picked over "nearest-landmark plus a stable ordinal" because two
zones can tie on nearest-landmark and direction, and an ordinal would need
its own stable sort key that is itself just id or creation order anyway;
the id is already this project's precedent (`place_zone`'s `read_back.id`,
`order."ID".exists`, `landmark."NAME"`). **Summarises by default, details
on request**: every filter `""` returns `summary: true` with
`counts_by_kind` over the whole inventory plus `needs_attention` (only the
zones whose `room_value_status` reads `not_met`/`cannot_tell` or whose
`owner_status` reads `unowned`/`cannot_tell`); any filter given returns
matching zones' detail rows instead (capped at the existing `MAX_LIST` 500,
`truncated` says so). Chosen over "always list everything" because at
fifty bedrooms an unfiltered dump is a tool nobody can read, and the
"needs attention" subset is exactly what "which of my rooms are not really
rooms" needs without narrowing at all.

**2. Validity, per zone.** Reuses `nobles.requirements`' own
met/not_met/cannot_tell discipline (never collapsed into a bare failure),
read here per zone rather than per position: `room_value_status`
(`not_applicable` for a kind with no room-value concept at all, `met` for
a non-empty `getRoomDescription`, `not_met` for a real read that came back
empty -- the exact condition that went unnoticed on this fort for two
days -- `cannot_tell` for a failed read, logged to `read_failures` and
`dfhack.printerr`) is a **separate** field from `owner_status`
(`not_applicable`/`owned`/`unowned`/`cannot_tell`), per the handoff's own
instruction: an owner-capable kind's unowned state is its own fact, not
folded into "invalid", since an owned zone can still read empty and a bare
unowned zone can still read a real quality word. Fleet-wide "which of my
rooms are not really rooms" is one call:
`zone.list "" "" not_met ""` (or, unfiltered, just read `needs_attention`
off a plain `zone.list "" "" "" ""`).

**3. `zone.find`'s new `AROUND_FURNITURE` flag.** Default false (unchanged
behaviour, byte-for-byte, for every existing caller). `true` admits a site
tile occupied by one of the kind's own `ZONE_POLICY.furniture_kinds`
(`Office`:`Chair`, `Bedroom`:`Bed`, `DiningHall`:`Table`, `Tomb`:`Coffin`)
instead of rejecting it as occupied; any other occupied tile is still
rejected exactly as before. A kind with no `furniture_kinds` entry refuses
the flag by name rather than silently ignoring it. Each result then
carries `contains_qualifying_furniture` and `furniture_building_ids`
(never a coordinate) -- informs, never refuses: a site with no qualifying
furniture is still returned, since the caller may want to build furniture
into it later. `furniture_kinds` is a `ZONE_POLICY` data field, read
through `df.building_type` at call time by a single `furniture_type_ids_for`
resolver; no kind or building-kind name appears in the site-search code
itself (`test_furniture_kinds_are_only_on_the_owner_capable_room_kinds`,
`test_around_furniture_refuses_a_kind_with_no_furniture_kinds_entry` pin
this). **`zone.place` is unchanged**: no new argument, `ranked_rects`'s
`furniture_type_ids` parameter stays `nil` for it, so it still rejects
every occupied tile -- per the handoff's scope, this is `find`'s own
capability, not a second write path
(`test_find_and_place_share_ranked_rects_but_only_find_passes_furniture_ids`
pins this too).

**Interface decision (item 3's "mode or flag, or a separate verb").** A
flag on the existing `find`, not a new verb: the site-search geometry
(landmark, radius, level, walkable-group, indoor preference, ranking) is
identical either way, and a separate verb would either duplicate all of it
or become a thin wrapper calling the same `ranked_rects` -- the flag is
the smaller, more honest surface, and it is what let `place` share the
same underlying function untouched.

**Signature plumbing.** `RADIUS_TILES` had to be added to `find`'s own
`skippable` list (it already existed for `[W H]`) so a caller can give
`AROUND_FURNITURE` without also giving `RADIUS_TILES`; the CLI tells them
apart by whether the next word parses as a number
(`parse_radius_and_furniture`), the same heuristic `parse_site_args`
already uses for `LEVEL` vs `W H`. `zone.list`'s four filter tokens are
each their own scoped `_ARG_DESCRIPTIONS` entry in `dfmcp/tools.py`
(`KIND_FILTER`/`OWNER_FILTER`/`VALID_FILTER`/`NEAR_LANDMARK_FILTER`, not
reusing the existing `KIND`/`OWNER`/`NEAR_LANDMARK` keys) because those
existing keys already describe `find`/`place`'s different semantics for
the same scope (`zone`), and the description table is keyed by
scope+token only -- reusing them would have given the filters a
misleading description or silently overwritten `find`/`place`'s own.

**Role allowlists.** `zone.list` added read-only to `agents/architect/
tools.yaml` and `agents/overseer/tools.yaml` (the only two roles that
grant any `zone.*` tool today), `status: planned` matching the existing
`workjob.list-jobs` convention for an offline-built, not-yet-deployed
command that is nonetheless a real allowlist grant once the registry
loads it.

**Tests.** `tests/test_zone_tool_manifest.py` extended: existing tests
updated for the new signatures (`zone.find`'s extra `radius_tiles`/
`around_furniture` args and its now-larger `skippable` set, `zone.list`'s
new argument names and effect/scope), plus nine new tests pinning the
three-state discipline, the empty-string filter sentinel, the
data-only furniture-kind rule, the unchanged `place`/`zone_tile` default
behaviour, and that `zone.list` never leaks a coordinate into a row.
Structural/source-level only, per this file's own existing convention
(the header comment: "The Lua cannot be executed in the test suite, it
needs a DFHack process").

**Both suites green, as required:**
- Ambient `python -m pytest`: **1407 passed, 3 skipped** (baseline 1398
  passed, 3 skipped; the +9 delta is exactly the nine new tests added to
  `tests/test_zone_tool_manifest.py`).
- `dfmcp/tests` in `.venv-dfmcp`: **652 passed** (unchanged from baseline;
  no new dfmcp/tests files were needed since the schema for the new
  arguments is derived automatically from `TOOLS.yaml` by the existing
  sweep tests).

**Live checks the eventual deploy should run, in order:**

1. Deploy `df-overseer-zone.lua` and confirm `zone.list-kinds` still
   returns 18 kinds with the new `furniture_kinds` field present (Office:
   `["Chair"]`, Bedroom: `["Bed"]`, DiningHall: `["Table"]`, Tomb:
   `["Coffin"]`, every other kind `[]`) -- a cheap, non-mutating sanity
   check that the file loaded without a quickfort-upvalue hop breaking.
2. Run `zone.list "" "" "" ""` (fully unfiltered) against Uniboslan and
   confirm `summary: true`, `total_zones: 2`, `counts_by_kind: {"Office":
   2}`, and both known zones (id 10 unowned, id 11 owned by the Manager)
   appear in `needs_attention` with `room_value_status: not_met` -- this
   is the direct, load-bearing test of item 2: it should surface exactly
   the defect `research/2026-09-23-room-and-zone-requirements.md` found by
   hand (the Chair sits outside both zones' own footprints, so both read
   empty). If either zone reads `met` instead, something changed about the
   fort's geometry since that research pass and is worth investigating
   before trusting anything else here.
3. Run `zone.list Office "" not_met ""` and confirm it returns exactly
   those same two zones -- proves the `VALID_FILTER` path independently of
   the unfiltered summary path.
4. Run `zone.list Office owned "" ""` and confirm it returns exactly zone
   11 (unit 345) -- proves `OWNER_FILTER`.
5. Run `zone.find Office 3 3 0 "Well" 20 true` (or near whichever landmark
   is closest to the real Chair) and confirm the result includes a
   candidate with `contains_qualifying_furniture: true` and the Chair's
   own building id in `furniture_building_ids` -- this is the one claim in
   this stream that is genuinely unverifiable offline: whether
   `getWalkableGroup` and the kind's own `is_valid_tile_fn` actually admit
   a tile carrying a Chair the way this stream assumes. If they don't,
   `find` will report `search.rejected.occupied` still counting that tile
   and no candidate will contain it; that would be the first real signal
   about whether the furniture-siting approach itself needs rethinking
   (e.g. a Chair's own tile failing the walkable-group check) rather than
   just being unverified.
6. Only after 1-5: consider whether to place a corrected Office zone (a
   real mutation, its own go-ahead) sited around the existing Chair via
   `AROUND_FURNITURE`, to get this fort's first non-empty room reading --
   the clean test `research/2026-09-23-room-and-zone-requirements.md`
   named but did not run.
