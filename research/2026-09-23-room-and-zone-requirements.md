# What does each room and zone actually require

Date: 2026-09-23. Read-only research, answering
`handoffs/2026-09-23-room-and-zone-requirements.md`. No VM changes, no live
writes, no unpause, no deploy. The fort stayed paused throughout (confirmed
`clock status` before and after every live read below); every live command
was a single bounded read (one struct field walk over a small, fixed-size
vector, or one direct id lookup), never an unbounded map scan. Sources: this
install's own live struct data (VM 103, DFHack 53.16-r1.1, via
`scripts/vm-ssh.sh df` and `dfhack-run lua`), this repo's own
`scripts/dfhack/df-overseer-zone.lua`, `df-overseer-nobles.lua` and
`df-overseer-building.lua` (all read in full), DFHack's own shipped docs
(`hack/docs/docs/tools/preserve-rooms.txt`), and four Dwarf Fortress Wiki
pages fetched this session and explicitly labelled by their own version
banner. No raw coordinate appears anywhere below (`docs/PURPOSE.md` design
commitment #1); site comparisons are stated as relative facts (inside/outside
a zone's own footprint), not as numbers.

## Bottom line

**What a room needs is a value, not a kind of furniture, and this fort's two
Office zones almost certainly have a value of zero right now for a
geometric reason nobody had checked: the one Chair this fort has ever built
sits outside both zones' own footprints.** Read live this session,
`dfhack.buildings.getRoomDescription` (the only room-value-adjacent function
DFHack exposes at all) returns an empty string for zone 10, zone 11, and the
Chair building itself, even now, with the Chair fully constructed
(`flags.exists: true`). A direct read of all four buildings' own boundary
fields shows the Chair's tile is not contained by either zone's rectangle:
it sits one row outside zone 10's edge, and it is not inside zone 11's
rectangle either. **This settles, for the first time on this fort, that
"outdoors" is very unlikely to be the actual blocker** (a v53.16-banner wiki
page states plainly that an office "does not necessarily need to be
enclosed", and the geometry problem alone is sufficient to explain a value
of zero regardless of indoor/outdoor status). It does not yet prove indoor
status is irrelevant to this specific install's value calculation, because
no site has ever produced a nonzero read to compare against; see "What could
not be verified". **The room requirement itself is install-verified and is
the single most useful table this stream can hand back**: a live read of
every position's own struct fields gives every noble and administrative
role's required office/bedroom/dining/tomb value in one table (Q4, below),
including four fields (`required_boxes`, `required_cabinets`,
`required_racks`, `required_stands`) that exist on the position struct and
are read by no tool in this repo today.

---

## Q1. What defines a room at all

**A room in this DF version is a Zone, not furniture, and this is now
verified two ways: the install's own quickfort data, and the wiki's own
version banner saying the older mechanic is gone.**

- **Install data (verified, `game-data`, describes 53.16).**
  `df-overseer-zone.lua`'s own header (read in full) documents that
  quickfort keeps `Bedroom`, `Office`, `DiningHall` and `Tomb` as ordinary
  entries in its `civzone_type` table (`zone_db_raw`, reached through Lua
  upvalues, 18 kinds total on this install, confirmed live this session by
  running the deployed `list-kinds` command: `AnimalTraining`,
  `ArcheryRange`, `Barracks`, `Bedroom`, `ClayCollection`, `DiningHall`,
  `Dormitory`, `Dump`, `Dungeon`, `FishingArea`, `MeetingHall`, `Office`,
  `Pen`, `PlantGathering`, `Pond`, `SandCollection`, `Tomb`, `WaterSource`).
  These four are placed and painted exactly like every other zone kind,
  through the `z` (Zones) interface quickfort's `#zone` mode drives, not
  through a separate furniture-room screen.
- **Every building does still carry a `room` field** (verified live this
  session: `df.building_civzonest._fields` lists `room`, and a direct read of
  zone 10, zone 11 and the Chair (building id 9) each showed a populated
  `building.T_room` struct with `extents`, `x`, `y`, `width`, `height`). This
  is the base `df.building` extent struct used by the classic pre-v50
  furniture-room mechanic. It still exists on the struct, is still populated
  for a Zone's own rectangle (a zone's `room.x/y/width/height` match its own
  footprint, confirmed live against zone 10 and zone 11), but is not what a
  vanilla player uses to create a Bedroom/Office/DiningHall/Tomb in this
  version: that is the Zone.
- **The wiki's own "Room" page, fetched this session, carries the version
  banner: "This page refers to a Dwarf Fortress feature that no longer
  exists in v53.16."** It states plainly: "A room was an area defined from
  an object that specified the purpose of the room" (the old mechanic) and
  that as of v50.01 "you instead specify activity zones that may or may not
  have objects inside them." This is a wiki source (`prior`, not
  `verified`, per doctrine's own rule), but it directly corroborates the
  install data above rather than contradicting it, and it is the version
  banner itself making the claim, not an editor's aside.
- **Every other zone kind (the other 14) is a plain rectangle with no owner
  and no room-value concept**: `ZONE_POLICY`'s default entry has
  `owner = false, position_field = nil`, and only `Bedroom`, `Office`,
  `DiningHall` and `Tomb` override it. `WaterSource` is the one kind with an
  entirely different finder (a connected water body, not a rectangle the
  caller sizes).

**What this means for this repo's own tools, concretely, as the handoff
asked**: `df-overseer-zone.lua` sits on the correct side of this mechanism
already (it places Zones, and the four room kinds are handled by data in its
`ZONE_POLICY` table). `df-overseer-building.lua` places furniture (the
Chair), which is a separate object from the zone; nothing in either tool
currently checks whether a placed piece of room-relevant furniture actually
falls inside a room-kind zone's own footprint. That gap is exactly what
happened live on this fort (see "The office question", below).

---

## Q2. Per kind, what does it require

The four room-value kinds, what furniture the wiki (v53.16-banner pages,
`prior`, not independently confirmed against this install's own room-value
output since no site here has ever read a nonzero value) says each wants,
and what this project's own tools currently check:

| Kind | Defining furniture (wiki, `prior`) | Enclosed/indoors required? (wiki) | This tool's own site checks (install, `verified`) | Owner-capable (install, `verified`) |
|---|---|---|---|---|
| **Bedroom** | A bed. Page quote: "an activity zone that probably should contain a bed"; three tiles fit "a bed, a cabinet, and a chest" | Not stated as mandatory; the page discusses doors only for large auto-designated bedrooms | 3x3 default footprint, `prefer_indoors: true` (this project's own choice, not a game rule), tile must be revealed, unoccupied, no liquid, walkable, not already zoned the same kind | Yes (`preserve-rooms`, role or unit) |
| **Office / Study** | "A throne or chair"; the wiki adds a table next to the chair is recommended (not required) to avoid an unrelated "no table" complaint, and says a "meager office" can be "a 1-tile-diameter area designated from a single chair" | Page states explicitly: does **not** necessarily need to be enclosed | Same 3x3 default, `prefer_indoors: true` (project preference) | Yes |
| **Dining Hall** | A table, each with its own orthogonally adjacent chair ("dwarves will receive negative thoughts from eating... without both a chair *and* orthogonally adjacent table to themselves") | Not stated as mandatory | 4x4 default, `prefer_indoors: true` (project preference) | Yes |
| **Tomb** | Not stated as mandatory by the fetched page; a "crypt" is described as many coffins each with their own Tomb zone, one dwarf per tomb zone | Not stated | 1x2 default, `prefer_indoors: false` | Yes |

Every other zone kind (`MeetingHall`, `Dormitory`, `Barracks`,
`FishingArea`, `SandCollection`, `ClayCollection`, `PlantGathering`, `Pen`,
`Pond`, `AnimalTraining`, `ArcheryRange`, `Dump`, `Dungeon`, `WaterSource`)
has no position field asking for a value from it and is a plain rectangle
(or, for `WaterSource`, a connected water body) with no owner. Six of them
(`FishingArea`, `SandCollection`, `ClayCollection`, `PlantGathering`, `Pen`,
`Pond`) carry a terrain caveat in `ZONE_POLICY` that this project's own tool
does not check.

**What "counts" toward a room's value is not exposed by the game's data or
by DFHack at all.** Confirmed live this session:
`dfhack.buildings.getRoomDescription` is the *only* function in the
`dfhack.buildings` Lua module whose name contains "room", "quality" or
"value" (a full key scan of the module found nothing else). There is no
`getRoomValue`, no numeric accessor, nothing. The quality word itself
(Meager, Modest, ...) is computed inside DF's own closed-source binary; an
older, differently-versioned wiki page (`DF2014:Room`, cited by
`df-overseer-zone.lua`'s own `ROOM_VALUE_EXTERNAL` constant before this
session, written for 0.47) describes the formula as floor-plus-walls
(smoothing and engraving add value) plus the value of contained furniture,
but that page is now explicitly marked obsolete for this version by its own
current-namespace successor (Q1, above), so its formula detail should be
treated as folklore about an earlier, related system, not confirmed
current behaviour.

---

## Q3. How room value is computed, and what it is used for

**Not computable from anything this install exposes; only the quality word
is readable, through one function, and this session got an empty result
from every object it tried.**

- **The quality-tier table exists and is now confirmed on a v53.16-banner
  page** (fetched this session, `Bedroom`; the parallel `Dining_room` page
  gives the identical seven numbers): Meager 0, Modest 100, [named tier]
  250, Decent 500, Fine 1000, Great 1500, Grand 2500, Royal 10000. This
  matches, almost tile-for-tile, the required-value numbers this session
  read live from the position struct (Q4): `SHERIFF` 100 (Modest),
  `CAPTAIN_OF_THE_GUARD`/`DUNGEON_MASTER` 250, `MAYOR` 500 (Decent). That
  convergence between an independently-fetched wiki table and this
  install's own live struct numbers is the strongest indirect evidence this
  session has that the tier table is real and current, even though the tier
  table itself is only wiki-sourced (`prior`).
- **`MANAGER` and `BOOKKEEPER` both require exactly 1.** Per the tier table,
  1 is inside the Meager band (0 up to just under 100), so in practice this
  means "any value greater than zero, however small" — consistent with the
  Office wiki page's own claim that a bare single chair can suffice for
  this class of role.
- **Live-read this session, the sharpest finding in this report**: with the
  fort's Chair fully built (`flags.exists: true`, per
  `evals/live/2026-09-23-chair-completion-run/README.md`), a direct read of
  `dfhack.buildings.getRoomDescription` against zone 10, zone 11 **and the
  Chair building itself** returned an empty string for all three (command
  and full output below). Empty is what this function also returned before
  the Chair existed (`evals/live/2026-09-23-office-and-first-real-build/README.md`'s
  `room_description: null` reads, which is the same "no quality word" state
  reported through a different tool). **The Chair's completion changed
  nothing about either zone's reported room quality.**
  ```
  dfhack-run lua "local z10 = df.building.find(10); local z11 = df.building.find(11);
    local ok10,d10 = pcall(dfhack.buildings.getRoomDescription, z10);
    local ok11,d11 = pcall(dfhack.buildings.getRoomDescription, z11);
    print('z10='..tostring(ok10)..'|'..tostring(d10));
    print('z11='..tostring(ok11)..'|'..tostring(d11));
    local c9 = df.building.find(9);
    local okc,dc = pcall(dfhack.buildings.getRoomDescription, c9);
    print('chair9='..tostring(okc)..'|'..tostring(dc))"
  -- z10=true|
  -- z11=true|
  -- chair9=true|
  ```
- **The reason, read live and confirmed this session: the Chair is not
  inside either zone's own rectangle.** Both zones and the Chair building
  were read directly (`x1/y1/x2/y2` on each, and the zone's own
  `room.x/y/width/height`, which match). The Chair's single tile falls
  outside zone 10's rectangle by exactly one row on the boundary nearest it,
  and is not inside zone 11's rectangle at all (a different site, on the
  far side, per `evals/live/2026-09-23-office-and-first-real-build/README.md`'s
  own account of why the owned zone was placed at a different location once
  `zone.lua`'s own `already_zoned_same_type` rejection ruled out the
  Chair's immediate neighbourhood for a second Office). No coordinate is
  reproduced here (design commitment #1); the fact itself — outside both
  rectangles — is what matters and is what a boolean containment check
  confirmed for both zones live this session.
- **The Manager's own Office zone (11, the owned one) was never placed over
  any furniture at all.** It is a bare 3x3 patch of ground with an owner
  assigned to it and nothing built inside it. Whatever value an unsmoothed,
  furniture-free outdoor patch carries under the (unverified, obsolete-page)
  floor-plus-walls-plus-furniture formula, it is very unlikely to clear even
  the Meager threshold's "greater than zero" bar the Manager's
  `required_office: 1` needs, independent of whether outdoor status matters
  at all.

**This directly answers the office question the handoff asked for, plainly,
not as a hedge**: **the evidence names a requirement the fort's real,
owned office fails, and it is not the requirement this project had been
suspecting.** It is very unlikely to be "outdoors" (Q5 below); it is that
the owned zone contains no furniture, and the one piece of room-relevant
furniture this fort has ever built sits in the wrong place to help either
zone. Order id 3 (`ConstructThrone`) staying `validated: false` through
every window run so far (`evals/live/2026-09-23-chair-completion-run/README.md`)
is fully explained by this without needing to invoke "not enough real
time" at all, though this report cannot rule out that more time would
*also* be needed on top of a geometry fix, since no corrected office has
ever been tried.

---

## Q4. What each noble or administrative position actually demands

**Read live this session, direct struct field walk, bounded (this
fortress's own `positions.own` vector, 14 entries), fort paused throughout.
This is the single most useful table this stream can return, as the handoff
asked for.**

```
dfhack-run lua "local e=df.global.plotinfo.main.fortress_entity; local o={};
  for i=0,#e.positions.own-1 do local p=e.positions.own[i];
    table.insert(o, p.code..' office='..tostring(p.required_office)..
      ' bedroom='..tostring(p.required_bedroom)..
      ' dining='..tostring(p.required_dining)..
      ' tomb='..tostring(p.required_tomb)..
      ' pop='..tostring(p.requires_population)..
      ' met='..tostring(p.flags.HAS_MET_POP_REQ)) end;
  print(table.concat(o, string.char(10)))"
```

| Position | Office | Bedroom | Dining | Tomb | Population needed | Met? |
|---|---|---|---|---|---|---|
| `MILITIA_COMMANDER` | 0 | 0 | 0 | 0 | 0 | true |
| `MILITIA_CAPTAIN` | 0 | 0 | 0 | 0 | 0 | true |
| `SHERIFF` | 100 | 100 | 100 | 0 | 0 | true |
| `CAPTAIN_OF_THE_GUARD` | 250 | 250 | 250 | 0 | 50 | **false** |
| `EXPEDITION_LEADER` | 0 | 0 | 0 | 0 | 0 | true |
| `MAYOR` | 500 | 500 | 500 | 0 | 50 | **false** |
| `MANAGER` | 1 | 0 | 0 | 0 | 0 | true |
| `CHIEF_MEDICAL_DWARF` | 0 | 0 | 0 | 0 | 0 | true |
| `BROKER` | 0 | 0 | 0 | 0 | 0 | true |
| `BOOKKEEPER` | 1 | 0 | 0 | 0 | 0 | true |
| `CHAMPION` | 0 | 0 | 0 | 0 | 0 | true |
| `HAMMERER` | 0 | 0 | 0 | 0 | 0 | true |
| `DUNGEON_MASTER` | 250 | 250 | 250 | 0 | 50 | **false** |
| `MESSENGER` | 0 | 0 | 0 | 0 | 0 | true |

Confirms and extends the earlier, single-position finding
(`handoffs/2026-09-21-nobles-appoint.md`, `MANAGER`'s
`required_office: 1, requires_population: 0`): that finding generalises.
Every position with a nonzero office/bedroom/dining requirement asks for
the *same* number across all three room kinds at once (`SHERIFF` 100/100/100,
`CAPTAIN_OF_THE_GUARD`/`DUNGEON_MASTER` 250/250/250, `MAYOR` 500/500/500),
and no position in this list requires a Tomb value at all. Four positions
(`CAPTAIN_OF_THE_GUARD`, `MAYOR`, `DUNGEON_MASTER`, and implicitly `SHERIFF`
once its own population figure is checked) gate on a population this fort
has not yet met (50; `SHERIFF` itself reads `pop: 0` so it is not
population-gated, only value-gated), which is a separate, independently
sufficient reason those specific offices could never validate yet even if
their room geometry were perfect.

**A second, previously unread requirement class exists on the same struct
and is read by no tool in this repo today**: `required_boxes`,
`required_cabinets`, `required_racks`, `required_stands`. Read live this
session, same bounded walk, only positions with a nonzero value in any of
the four shown:

```
SHERIFF               boxes=1 cabinets=1 racks=1 stands=1
CAPTAIN_OF_THE_GUARD   boxes=1 cabinets=1 racks=1 stands=1
MAYOR                  boxes=2 cabinets=1 racks=1 stands=1
DUNGEON_MASTER         boxes=1 cabinets=1 racks=1 stands=1
```

These track exactly the same four value-requiring positions (justice- and
leadership-adjacent roles that plausibly need evidence storage or record
furniture), never `MANAGER`/`BOOKKEEPER`. Neither `df-overseer-nobles.lua`
(which reports only `required_office`) nor `df-overseer-zone.lua`'s
`requirements_for` (which reports `required_office`/`_bedroom`/`_dining`/
`_tomb` only) reads these four fields at all: a real, install-confirmed
tool gap, not something this project had previously named anywhere.

---

## Q5. Does indoors/outdoors change any of it

**Most likely not disqualifying by itself, on the evidence available, but
this stream cannot rule it out as a contributing factor, only show it is not
the sole or most likely explanation.**

- The `Office` wiki page (v53.16-banner, fetched this session) states
  plainly that an office "does not necessarily need to be enclosed."
  `Bedroom` and `Dining_room` (same-session fetches, same version banner)
  do not state an indoor requirement either, though `Bedroom` does mention
  using doors "when auto-designating from a large area", which reads as
  practical/privacy advice, not a stated value rule.
- **This project's own `zone.lua`'s `prefer_indoors: true` for these three
  kinds is explicitly labelled in its own header as this project's
  preference, not a game rule**, and both of this fort's real Office zones
  read `indoors: false` because no fully indoor 3x3 site existed near a
  workshop or the Well (`evals/live/2026-09-23-office-and-first-real-build/README.md`).
  Nothing in the struct data, DFHack's API or the fetched wiki pages ties
  indoor status to the `required_office` value check at all.
- **Q3's finding is sufficient on its own to explain a value of zero**,
  independent of indoor status: an empty zone with no furniture inside it
  is very unlikely to clear even the Meager (0-99) band regardless of
  roof cover. This makes "outdoors" a much weaker candidate explanation for
  the stalled order than this project had been leaning on, without fully
  retiring it: **no site on this fort has ever produced a nonzero room
  value to compare against**, so whether an otherwise-identical indoor
  office would score any differently is untested, not disproven. If the
  office is rebuilt so the Chair sits inside the zone's own footprint and
  it still reads empty, that would be the clean test of indoor status
  specifically; this stream did not run it (would mutate the fort).

---

## Q6. What is checkable from a tool, today

| Requirement | Readable today, how | Would need building |
|---|---|---|
| Which positions need a room value, and how much | `df-overseer-nobles.lua list` (office only) or `df-overseer-zone.lua`'s `requirements_for` (office/bedroom/dining/tomb, all four) — **verified live, confirmed again this session** | Nothing; already read by an existing tool for these four fields |
| `required_boxes`/`_cabinets`/`_racks`/`_stands` per position | Not read by any tool in this repo. Confirmed to exist on `df.entity_position` this session (a live field-name scan) | A small, well-scoped addition to `df-overseer-nobles.lua` or `df-overseer-zone.lua`, same pattern as the existing four fields |
| A room's actual numeric value | **Not available at all.** Confirmed this session: `dfhack.buildings` has exactly one function with "room"/"quality"/"value" in its name (`getRoomDescription`), and it returns only a quality-word string (or empty), never a number | Cannot be built from anything this install or DFHack exposes; the value lives inside DF's own closed-source binary |
| A room's quality word (Meager, Modest, ...) | `dfhack.buildings.getRoomDescription(zone)`. Confirmed live this session on three different objects (two zones, one piece of furniture), all returning empty for this fort's current geometry. `df-overseer-zone.lua`'s `place_zone` already calls and reports this on every real placement | Nothing; already wired |
| Whether a piece of furniture sits inside a room-kind zone's own footprint | **Not checked by any tool today.** This session did it with one ad hoc bounded read (each building's own `x1/y1/x2/y2` plus the zone's `room.x/y/width/height`), which is exactly the check that found this fort's Chair sits outside both Office zones | A genuinely new, small, generalisable check: given a zone id and a building id (or a zone id and a building kind to search for within its footprint), report containment. Same shape as `zone.lua`'s own site-eligibility geometry, reusable rather than novel |
| Whether a zone is indoors | `df-overseer-zone.lua`'s own `indoors` field on every rectangle-kind result, from the tile's `outside` flag — **verified live**, already reported on both real Office zones | Nothing; already wired |
| The 4-tier population gate (`requires_population`/`HAS_MET_POP_REQ`) | `df-overseer-nobles.lua`'s `describe()` already reports both fields for every position; `zone.lua`'s `requirements_for` also reports a derived `population_requirement_met` per room-requiring position — **verified live, confirmed again this session (Q4 table)** | Nothing; already wired |

---

## What could not be verified

- **Whether an indoor, furniture-correct Office would read a nonzero
  value.** No such site exists on this fort. This is the clean test that
  would separate "the geometry mistake alone explains it" from "indoors
  also matters," and this stream deliberately did not run it (it would
  mutate the fort, out of scope for a read-only research stream).
- **The exact room-value formula** (floor/wall smoothing, engraving,
  furniture value/material/quality, contained-goods value). The only
  concrete formula text found (an older, DF2014-namespaced wiki page) is now
  explicitly marked obsolete by the current-namespace `Room` page itself, so
  it is reported here as folklore about a related, no-longer-current
  mechanic, not as a description of 53.16's actual formula. Nothing in
  DFHack's own API exposes a computed value at all (Q6), so this cannot be
  settled from this install even in principle without reading the game's
  own (closed-source) binary logic.
- **Whether the specific furniture the wiki names (throne/chair for Office,
  bed for Bedroom, table+chair for Dining Hall) is a hard requirement
  recognised by this version's own engine, or just the conventional way
  players supply value.** The zone system's own mechanics (Q1) place no
  furniture-type check anywhere this project can read; `preserve-rooms`'s
  own docs describe "assignable" zones purely by kind, with no furniture
  condition mentioned. It remains plausible that *any* sufficiently
  valuable furniture inside the footprint would work, not specifically a
  chair for an Office; this was not tested.
- **Tomb requirements for any position.** No position on this fort's own
  positions vector requires a nonzero Tomb value; whether any DF position
  ever does (a monarch's own tomb, perhaps) is unverified from this
  install, since this fort has neither a monarch position instantiated nor
  a way to check one that does not exist here.
- **Whether `required_boxes`/`_cabinets`/`_racks`/`_stands` gate order
  validation the same way `required_office` does**, or are checked/reported
  separately by the game. Their existence and per-position values are
  verified live; their effect is not, since this fort has never had a
  fully-furnished office of any kind to observe against.
- **Whether the wiki's seven-tier value table (Meager 0 through Royal
  10000) is the complete and current set of thresholds**, beyond the
  strong indirect corroboration of three of its numbers (100/250/500)
  matching this install's own live position data exactly. The table itself
  remains a wiki source (`prior`).

## Sources

Install, read live this session (VM 103, DFHack 53.16-r1.1, fort paused
throughout, `scripts/vm-ssh.sh df`, bounded reads only): `df.entity_position`
field-name scan; every position's `required_office`/`_bedroom`/`_dining`/
`_tomb`/`requires_population`/`HAS_MET_POP_REQ`; every position's
`required_boxes`/`_cabinets`/`_racks`/`_stands`; `df.building_civzonest`
field-name scan; zone 10, zone 11 and building 9's own `room` extent struct;
`dfhack.buildings.getRoomDescription` against zone 10, zone 11 and building
9; a `dfhack.buildings` module key scan for room/quality/value-named
functions; `df-overseer-zone.lua list-kinds`'s full 18-kind output.

Repo, read in full this session: `scripts/dfhack/df-overseer-zone.lua`,
`scripts/dfhack/df-overseer-nobles.lua`, `scripts/dfhack/df-overseer-building.lua`
(header), `doctrine/seed.yaml` (header), `docs/MEMORY-ARCHITECTURE.md`,
`evals/live/2026-09-23-office-and-first-real-build/README.md`,
`evals/live/2026-09-23-chair-completion-run/README.md`,
`research/2026-09-23-work-orders-vs-direct-jobs.md`,
`handoffs/2026-09-21-nobles-appoint.md` (cited, not re-read in full),
`/opt/df/game/hack/docs/docs/tools/preserve-rooms.txt` (DFHack's own shipped
docs, read live on VM 103).

Web, fetched this session, each cited by its own version banner (untrusted
data about this install per doctrine's own rule; `prior` only):
[Room](https://dwarffortresswiki.org/index.php/Room) (banner: "no longer
exists in v53.16"), [Office](https://dwarffortresswiki.org/index.php/Office)
(banner: "v53.16 · v0.47.05"),
[Bedroom](https://dwarffortresswiki.org/index.php/Bedroom) (banner:
"v53.16"), [Dining room](https://dwarffortresswiki.org/index.php/Dining_room)
(banner: "v53.16 · v0.47.05"), [Tomb](https://dwarffortresswiki.org/index.php/Tomb)
(banner: "v53.16"). A local wiki snapshot path recorded in `Working.md`
(`/var/lib/dfwiki/` on VM 106) was checked and does not exist on that guest;
the web fetches above were used instead, each individually version-labelled.

## Addendum 2026-09-24: how a zone's owner link works on this install (Q7)

Read from the installed DFHack scripts on the game VM over ssh (read-only), and
from the live struct field lists via `dfhack-run lua` (reads only). The
Buildings C++ source is not installed there, so the behaviour of
`dfhack.buildings.setOwner` itself is inferred from its callers, not read.

- **What links exist.** `building_civzonest` has `assigned_unit_id` (zone to
  unit), `owner_unit_cached_index` and `retained_owner`. The unit has
  `owned_buildings`, a vector of building pointers (unit to zone). No other
  field on the zone, the unit or `entity_position` holds a room link:
  `entity_position` carries only `required_office`, `required_bedroom`,
  `required_dining` and `required_tomb` values. A noble's "room" is therefore
  not a game link at all; it is whichever zone names the holder, plus the
  preserve-rooms plugin's own reservation state.
- **What sets them.** `fix/ownership.lua` finds zones where `getOwner` names a
  unit but the unit's `owned_buildings` lacks the zone, and repairs it with
  `setOwner(zone, nil)` then `setOwner(zone, unit)`: evidence that `setOwner`
  is the call that maintains the unit-side vector, and that the two sides can
  drift apart. `entomb.lua` writes `assigned_unit_id` and inserts into
  `owned_buildings` by hand for a tomb. `emigration/unit-link-utils.lua` frees
  a leaving unit's rooms with `setOwner(bld, nil)` over `owned_buildings`.
  `gui/room-list.lua` lists rooms by `owned_buildings` filtered on
  `v.owner == unit`, so a one-sided link shows as a missing room.
- **Consequence.** `zone assign-owner` and `clear-owner` call `setOwner` only
  and read every link back in both directions, so a one-sided result is
  reported (`one_direction_only`) rather than trusted, and the fix named is the
  game's own `fix/ownership`. The tool never writes a field by hand.
- **What is still unverified live.** That `setOwner` writes both sides for a
  zone that already exists and is currently unowned (the fixture proves the tool
  logic against a fake, not the game); that the Manager's requirement then reads
  `met`; and whether a room with a nonempty quality word is enough for
  `required_office` of 1 (Q6 stays open).
