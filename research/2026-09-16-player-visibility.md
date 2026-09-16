# Player Visibility: What a Vanilla DF v50 Fortress-Mode Player Can Know

Date: 2026-09-16
Scope: the factual foundation for the user's policy that df-overseer's agents
may only know what a vanilla Dwarf Fortress player (no DFHack) could have
learned through the game's own UI, given unlimited patience, at some point in
this fort's life. This report establishes what is and is not visible, and
which struct/API fields encode that boundary, on the installed build
(DF v0.53.16 linux64 ITCH, DFHack 53.16-r1.1, confirmed live against VM 103
this session — `dfhack.getDFVersion()`/`dfhack.getDFHackVersion()`). It does
**not** change any tool; that is the follow-up executor's job.

Method: primary sources first. Struct/enum claims are read directly from a
fresh shallow clone of `DFHack/df-structures` (`master`, cloned this session
into scratch, not committed here) and cross-checked live against VM 103 via
read-only `dfhack-run lua` calls (fort confirmed paused throughout,
`dfhack.world.ReadPauseState()==true`; no probe files left on the guest, no
write calls made). DFHack's own C++ (`Units.cpp`, `Maps.cpp`,
`plugins/reveal.cpp`) was fetched from GitHub and read directly, not
recalled. Where only a fetched-and-summarized web page or wiki article
backs a claim, it is marked `[C-Wiki]`/`[WebSearch]` and treated as lower
confidence than a direct struct/source read (`[C-XML]`/`[live]`).

---

## Bottom line

**The visibility boundary in DF v50 fortress mode is gated by a small,
concrete set of fields, not a fuzzy notion of "map knowledge":**

| Domain | Gating field | Kind |
|---|---|---|
| Terrain, any tile | `tile_designation.hidden` (a plain bool on this build, **not** nested under `.bits` in Lua — see live trap below) | per-tile |
| Whether a player has been *told* | `dfhack.maps.isTileVisible(x,y,z)` = `not designation.hidden`; confirmed live identical | derived, same field |
| Caverns/chasms/magma pools/pipes/underworld ("map features") | `feature_init.flags.Discovered` and, more precisely, `.Announced` (`feature_init_flags` enum: `AddSavage`, `AddEvil`, `AddGood`, `Discovered`, `Announced`, `AnnouncedFully`) | per-feature |
| The announcement that actually informs the player of a feature/mineral find | `announcement_type.FEATURE_DISCOVERY` / `.STRUCK_MINERAL` / `.STRUCK_ECONOMIC_MINERAL` / `.STRUCK_DEEP_METAL` / `.CAVE_COLLAPSE` (all `alert_type = UNDERGROUND`), confirmed present in the live enum this session | announcement |
| Mineral/gem veins specifically | `block_square_event_mineralst.flags.discovered` (a `mineral_event_flag` bitfield: `discovered`/`cluster`/`vein`/`cluster_small`/`cluster_one`), scoped by the event's own `tile_bitmask` footprint | per-vein-segment |
| Units (sneaking/ambush/off-map) | `dfhack.units.isHidden(unit)` — **not** `isVisible`, whose own doc says "doesn't account for sneaking." Read from source: `isHidden` = tile-hidden (`!isVisible`, i.e. `designation.hidden`) **OR** (`hidden_in_ambush` AND not `isFortControlled`), with adventure-mode and caged special cases | per-unit, composite |
| Items | `item.flags.hidden` (`INTERFACE_INVISIBLE`, comment just "Hidden item" — thin, not deeply verified) plus whatever tile it sits on | per-item + per-tile |

**The single hardest grey zone, stated plainly:** `df-overseer-threat.lua`
exists specifically to catch ambushes and sneaking creatures because
`INVASION` and `unit-status hostile` both proved unreliable for exactly that
case (`decisions/DECISIONS.md` 2026-09-11/12). But "a unit is ambushing or
sneaking" is *precisely* what `isHidden(unit)` says a vanilla player cannot
see. The tool's entire safety rationale and the new visibility policy are in
direct, structural tension: there is no DFHack primitive that gives ambush
coverage without omniscience, because the game's own fairness mechanic for
ambushes *is* hiding them from the player. The only genuinely vanilla-legal
signal for "something is wrong" without revealing *what* is the `ambush`/
`night_attack`/`undead_or_ghost` announcement-report families
`df-overseer-diff.lua` already tags (ids 53–66, 95, 322, 136–138, 139, 150) —
DF does sometimes announce that something happened without necessarily
revealing the actor. This is a design decision for the executor/user, not
something this report resolves; it is named here so it isn't quietly
papered over.

---

## Cross-domain: how competitive game-AI already drew this line

Restated domain-neutrally: an automated agent playing an imperfect-information
game through an API that can trivially expose perfect information.
StarCraft: Brood War's bot ecosystem hit this problem first and at scale.

- **BWAPI's `Flag::CompleteMapInformation`** is the exact analog of what this
  project must *not* do. Its own doc (`[C-XML-equivalent, fetched from
  bwapi.github.io]`): *"Enable to get information about all units on the map,
  not just the visible units."* Off by default; a bot has to opt in.
- **Tournament enforcement, `[WebSearch]`, moderate confidence (raw rules
  page fetch came back empty, so this rests on a search-engine summary, not
  a directly read page):** SSCAIT and the Torch Up ruleset both prohibit
  bots from enabling it. The load-bearing design point is *where* enforcement
  lives: a **Tournament Module** (server-side, in the game/referee layer)
  polices this, not bot-author self-restraint. BWAPI's default behavior is
  itself fog-of-war-respecting — "information on units that have gone back
  into the fog of war is denied to the AI" — so a compliant bot doing nothing
  special is already correct; only an explicit opt-in flag breaks it.
- **The genuinely useful nuance for this project, `[I]` inference from the
  BWTA/BWEM terrain-analyzer issue thread turned up in search:** BWAPI
  separates **static geometry** (walkability, ground height, choke points —
  computed once from the map file, safe to know in full from turn one and
  used by terrain analyzers) from **dynamic fog-of-war state** (units, what's
  currently visible). Only the second is the cheating surface;
  `CompleteMapInformation` is about units, not terrain. This maps directly
  onto DF's own split: **dug-out map topology and a player's own buildings
  are "static" in this sense once revealed** (`find_open_area`/
  `find_diggable_area`/landmarks reading tile shape and material are fine
  *if* gated to revealed tiles — the walkability graph itself is not the
  cheat), while **live unit state and un-revealed terrain are the genuinely
  dynamic, hideable layer.**

**What changes for this project:** the enforcement point should be the tool
layer, server-side, exactly as `docs/AGENT-ARCHITECTURE.md` principle 8
already states ("a role is defined by its tool allowlist... the allowlist is
the actual boundary") — this is the same lesson BWAPI's Tournament Module
teaches, just for a different game. A prompt instruction telling the model
"don't use hidden information" is the un-enforced, un-audited equivalent of
trusting a bot author's self-restraint, which is exactly the failure mode
competitive StarCraft AI had to build a referee module to stop trusting.

---

## 1. Terrain and tiles

**Gating field, `[C-XML + live]`, high confidence:** `tile_designation.hidden`.
Read directly from `Maps::isTileVisible` (`library/modules/Maps.cpp`, fetched
from `DFHack/dfhack` master):

```cpp
bool Maps::isTileVisible(int32_t x, int32_t y, int32_t z) {
    df::map_block *block = getTileBlock(x, y, z);
    if (!block) return false;
    if (block->designation[x % 16][y % 16].bits.hidden) return false;
    return true;
}
```

**Live-verified trap, `[live]`, this session:** on this exact installed
build, the Lua binding of `tile_designation` is **flat**, not nested under
`.bits` — `designation[x][y].hidden` works directly; `.bits.hidden` errors
(`Cannot read field tile_designation.bits: not found`). This is the same
category of trap already recorded for `liquid_type` in `docs/TRAPS.md`
("binds to a plain Lua boolean... not the enum"). Confirmed live against a
real surface tile at "Embark Site" (`hidden=false`, `light=true`,
`outside=true`, `subterranean=false`, `isTileVisible=true`) and a real
undug tile 60 z-levels below it (`hidden=true`, `isTileVisible=false`) —
`isTileVisible` and `not designation.hidden` agreed exactly in both cases,
as the source predicts.

**Reveal mechanism, `[C-Wiki]` moderate-high confidence (Dwarf Fortress
Wiki, "Revealed tile" page, current):**
- "All above ground tiles on the map start out revealed, including tiles
  above the surface." So the whole surface is visible from turn one —
  confirms item 8's framing that surface geometry needs no gating.
- "All subterranean tiles must be revealed by digging into them."
- "All tiles adjacent to a dug tile on the same level will also be revealed,
  including diagonally: you can see what the rock walls adjacent to a
  mined-out tile are made of." This is the specific, quoted mechanic behind
  the user's "existence is not location" rule for minerals — a *neighbor's*
  material becomes knowable the instant you dig next to it, without digging
  it out yourself.
- Stairways: "You can also see the tile immediately below where a downward
  or up/down stairway has been dug... Upward stairways do not reveal the
  level above."
- Cave-ins and DFHack's own `unhideFlood(pos)` (documented in the local
  install's `hack/docs/docs/dev/Lua API.txt`, line ~6578: "Unhides map tiles
  according to visibility rules, starting from the given coordinates... only
  processes adjacent hidden tiles") confirm the reveal is a flood-fill from
  a newly-dug/newly-breached point, matching the adjacency rule above.
- **No re-hide mechanism was found anywhere in the structures or the wiki
  text gathered this session.** Treated as a checked, not exhaustive,
  absence — `hidden → revealed` reads as monotonic across everything read,
  but no source explicitly states "and it never re-hides."
- Windows/line-of-sight-from-above were **not independently verified** this
  session; the wiki text covers digging/adjacency/stairs only. Flagged as
  not verified rather than assumed either way.

**Persistence across a fort's life, `[I]` inference from
`memory/dfhack-environment.md`'s already-recorded fact ("DFHack persistent
site data survives retire/unretire") plus the field being part of ordinary
save-game tile state:** a previously-uncovered area almost certainly stays
revealed across reclaim/unretire, which is exactly what makes the user's "at
some point in this fort's life" framing well-defined rather than needing a
fresh per-session check. Not independently proven by reading save-format
code this session.

---

## 2 & 3. Caverns, underground features, and map features generally

**Gating fields, `[C-XML]`, high confidence**, read directly from
`df.feature.xml`:

```xml
<enum-type type-name='feature_init_flags' original-name='feature_init_flag_type'>
    <enum-item name='NONE' value='-1'/>
    <enum-item name='AddSavage'/> <enum-item name='AddEvil'/> <enum-item name='AddGood'/>
    <enum-item name='Discovered'/>
    <enum-item name='Announced'/>
    <enum-item name='AnnouncedFully' comment='for tube inside vs. outside'/>
</enum-type>
```

`feature_init.flags` is a `df-flagarray` indexed by this enum. So every
cavern layer, chasm, magma pool/pipe, and underworld-from-layer feature
carries its own `Discovered`/`Announced` bits. **`Announced` is the better
predicate for this project's policy than `Discovered`**: it should track
the actual in-game announcement, which is the moment a vanilla player is
actually told, per the wiki: "Upon breaching a feature, an announcement will
be displayed informing the player of the discovery, and a chunk of the new
feature 'within view' of your dwarves will be revealed" and "a good portion
of a cavern is revealed once you breach it, but other parts remain hidden
until your dwarves explore them" `[C-Wiki]`.

**The announcement itself, `[C-XML + live]`, high confidence.** Read from
`df.g_src.basics.xml`'s `announcement_type` enum and confirmed live against
this exact install:

```
FEATURE_DISCOVERY        alert_type=UNDERGROUND    (id 2, live-confirmed)
STRUCK_MINERAL           alert_type=UNDERGROUND    (id 4, live-confirmed)
STRUCK_ECONOMIC_MINERAL  alert_type=UNDERGROUND    (id 5, live-confirmed)
CAVE_COLLAPSE            alert_type=UNDERGROUND    (id 82, live-confirmed)
```

`STRUCK_DEEP_METAL` is present in the enum by name but was not individually
live-read for an id this session. These are real `REPORT`-family events —
exactly the mechanism `df-overseer-diff.lua` already knows how to listen to
(its `REPORT_CATEGORY` table already tags combat/threat announcement ids the
identical way; extending it to these ids is the same pattern, not new
machinery). `df.report.xml`'s own `entity_activity_statistics` struct
(the fort's report/stats object) independently carries per-fort counters
—`discovered_water_features`, `discovered_subterranean_features`,
`discovered_chasm_features`, `discovered_magma_features`,
`discovered_underworld_features`— corroborating that "discovered" is DF's
own internal vocabulary for this exact concept, not a term invented for this
policy.

**A second, striking corroboration, `[C-XML]`:** the same struct's
`excavated_tiles` field (original name `floorspace`) carries the comment
*"unhidden, subterranean, and excluding map features"* — DF's own
developers use "unhidden" and separate it from "map features" in exactly
the two-tier way this report describes (tile-hidden vs. feature-discovered).

**Does the player know caverns *exist* before breaching?** Two different
answers depending on which screen:
- The plain browse/confirm view's `warn_flag` bitfield (`GENERIC`,
  `WATER_TABLE`, `HEAVY_WATER_TABLE`, `SALT_WATER`, `LARGE`, `SMALL`,
  `DEAD_CIV`, `SAVAGE`, `EVIL`, `UNDEAD` — read directly from
  `viewscreen_choose_start_sitest`, `[C-XML]`) has **no** cavern/chasm/
  magma entry at all. Passive browsing tells you nothing about features.
- The **Site Finder**, a fully vanilla, no-DFHack UI tool on the same
  screen, searches `embark_finder_option` (`[C-XML]`, `df.region.xml`),
  which **does** include `UndergroundRiver`, `UndergroundPool`, `MagmaPool`,
  `MagmaPipe`, `Chasm`, `BottomlessPit`, and `OtherFeatures` as filterable
  criteria, alongside `Savagery`, `Spirit`(evil), `AquiferLight`/
  `AquiferHeavy`, `Soil`/`Clay`/`Sand`, `FluxStone`. **This is the concrete
  form of "patience is allowed":** a player who deliberately searches for a
  magma-pipe embark tile learns "this candidate region has one" (existence,
  categorical) without knowing *where within the region* until they dig —
  exactly the user's own distinction. This does not tell a player which
  *specific* candidate is currently under evaluation has which feature
  without running the search, so it is not a standing background fact —
  it requires the same deliberate, patient UI action the policy's own test
  asks for.

---

## 4. Minerals, gems, and stone

**Gating field, `[C-XML]`, high confidence:** `block_square_event_mineralst`
(`df.block.xml`) carries a `mineral_event_flag` bitfield —
`discovered`/`cluster`/`vein`/`cluster_small`(`SMALL_CLUSTER`)/
`cluster_one`(`RARE`) — plus its own `tile_bitmask` (a DFHack-synthesized
16×16-per-block mask, `df.dfhack.xml`: "not in DF, 16x16 bitmask") marking
which tiles the vein/cluster actually occupies. So vein discovery is tracked
**per vein-segment-per-block**, not per individual tile within it — a real,
if modest, granularity gap from the ideal "exactly this tile" model; not
resolved further this session (would need a live comparison of the mask
against `designation.hidden` on a real, partially-dug vein, not attempted,
see Not Verified).

**Corroborating announcement layer, `[C-XML + live]`:** `STRUCK_MINERAL`/
`STRUCK_ECONOMIC_MINERAL`/`STRUCK_DEEP_METAL` (§2/3 above), and
`df.report.xml`'s `found_minerals` field, commented *"Added after 'you have
struck' announcement"* — direct confirmation that the "you have struck X"
message is the actual player-facing trigger, and that a fort's own report
struct already tracks minerals by the same announcement-gated logic this
report recommends for the tool layer.

**Wiki corroboration, `[C-Wiki]`:** "Designating Ores/Gems works only on
revealed tiles" — the vanilla UI itself refuses to let the player interact
with an unrevealed vein, which is the strongest possible confirmation that
this is a real, enforced-in-vanilla boundary, not a courtesy.

**Adjacency allowance, same as §1:** a tile's *material* becomes knowable the
instant a neighbor is dug (the wiki's "you can see what the rock walls
adjacent to a mined-out tile are made of" applies to ordinary stone/soil and
to vein material alike, since both are just `tiletype_material` values on
the tile). So "the wall next to my dug corridor is granite" is fair;
"the material of a tile four tiles into unbroken rock" is not, unless that
specific tile is independently revealed.

---

## 5. Units

**The three predicates and what they actually check, `[C-XML source read]`,
high confidence — read directly from `library/modules/Units.cpp`:**

```cpp
bool Units::isVisible(df::unit *unit) {
    return Maps::isTileVisible(getPosition(unit));
}

bool Units::isHidden(df::unit *unit) {
    if (*df::global::debug_showambush) return false;
    if (*gamemode == game_mode::ADVENTURE) {
        if (unit == World::getAdventurer()) return false;
        else if (unit->flags1.bits.hidden_in_ambush) return true;
    } else if (*gametype == game_type::DWARF_ARENA) return false;
    else if (unit->flags1.bits.hidden_in_ambush && !isFortControlled(unit))
        return true;
    if (unit->flags1.bits.caged) {
        auto spec_ref = getOuterContainerRef(unit);
        if (spec_ref.type == specific_ref_type::UNIT)
            return isHidden(spec_ref.data.unit);
    } else if (*gamemode == game_mode::ADVENTURE || isFortControlled(unit))
        return false;
    return !isVisible(unit);
}
```

**This is the single most important correction to how the current tools
use these predicates.** `isVisible` is *only* `not designation.hidden` at
the unit's tile — the shipped doc's own caveat ("doesn't account for
sneaking") is literally true: a sneaking/ambushing unit standing on a
perfectly revealed tile still reads `isVisible == true`. **`isHidden` is
the composite, correct predicate**: tile-hidden **or** (ambushing **and**
not the player's own fort-controlled unit/pet), with adventure-mode and
caged special cases. A vanilla-visibility filter that used `isVisible`
instead of `not isHidden` would be **wrong in exactly the direction that
matters**: it would happily admit a sneaking goblin standing on open,
revealed ground.

`isFortControlled` (also read from source): excludes berserk/crazed/
opposed-to-life/undead/ghostly units and a `flags1`/`flags2` exclusion set,
returns true for tame units unconditionally, and otherwise falls through to
`isOwnCiv`. This is why `df-overseer-threat.lua`'s use of it (added beyond
`df-overseer-labor.lua`'s older `isOwnCiv`-only check) is the right call —
it is specifically designed, per its own doc text, "based on checks for
units hidden in ambush," i.e. it is aware of exactly this boundary.

`isDanger`/`isInvader`/`isAgitated` (source read, for completeness — these
were already known to this project as unreliable *hostility* signals, but
their exact logic was not previously quoted from source):

```cpp
bool Units::isInvader(df::unit *unit) {
    return (unit->flags1.bits.marauder || unit->flags1.bits.invader_origin ||
            unit->flags1.bits.active_invader) && !isOwnGroup(unit);
}
bool Units::isAgitated(df::unit *unit) {
    return unit->flags4.bits.agitated_wilderness_creature;
}
bool Units::isDanger(df::unit *unit) {
    if (isTame(unit) || isOwnGroup(unit)) return false;
    return isCrazed(unit) || isInvader(unit) || isOpposedToLife(unit) ||
           isAgitated(unit) || unit->flags2.bits.visitor_uninvited ||
           ((isGreatDanger(unit) || isNightCreature(unit)) &&
            !unit->flags2.bits.visitor);
}
```

None of these three read anything about tile visibility or ambush at all —
confirming this project's own prior finding (`decisions/DECISIONS.md`
2026-09-11/12) that they are orthogonal to "can the player see this," not a
weaker version of the same idea. A unit can be `isDanger==true` and
`isHidden==true` simultaneously (a hostile currently ambushing) or
`isDanger==false` and `isHidden==false` (a visible, harmless demon).

**Off-map/arriving units, not independently verified this session:**
whether a unit assigned to an about-to-arrive migrant wave or caravan exists
in `world.units.active` before it is actually on the local map (and if so,
whether `isHidden`/`isVisible` correctly read false/inapplicable for it)
was not tested live. Flagged as a gap, not assumed either way — a scan
tool that iterates `world.units.active` without checking `isActive`/
map-membership first could plausibly pick up a not-yet-arrived unit; DF's
own `isActive` predicate ("non-dead and on the map") is the obvious guard,
already present in the API and not currently exercised in any of this
project's own read of the relevant tools' logic.

---

## 6. Items and buildings

**Gating fields, `[C-XML]`, moderate confidence (thin comments):**
`df.item.xml`'s `item_flags` bitfield has two entries that both sound
relevant and are **not the same thing** — exactly the kind of "flags may not
mean what their names suggest" trap the brief warned about:

```
flag-bit name='removed'  original-name='HIDDEN'              comment='completely invisible and with no position'
flag-bit name='hidden'   original-name='INTERFACE_INVISIBLE'  comment='Hidden item'
```

The first (`removed`, DF's own original name was misleadingly `HIDDEN`) is
about deallocation bookkeeping, not player visibility — DFHack itself
renamed it away from `HIDDEN` for exactly this reason. The second
(`item.flags.hidden`) is the real per-item UI-visibility flag, but its
comment is thin ("Hidden item") and its exact trigger conditions were not
traced further this session (`[I]`, not deeply verified). Practically, an
item's visibility is very likely gated first and mostly by **the tile it
sits on** (`designation.hidden`, §1) — an item lying in an unrevealed area
is not visible for the same reason the ground under it isn't — with
`item.flags.hidden` as a secondary, item-specific gate whose exact use case
(inside a closed container? a secret/plot item?) is unconfirmed.

**Merchant/caravan goods, `[live, this project's own count]` plus
`[C-Wiki]` for the general mechanic:** this session's own register entry
(`decisions/DECISIONS.md` 2026-09-16, "The fort owns no food and no drink")
already establishes live that caravan goods sitting in wagons on the map
carry `item.flags.foreign` and are readable via ordinary DFHack item
iteration well before any trade occurs. In vanilla play the caravan and its
wagons are ordinary units/items on the map — visible the moment they are on
a revealed tile the same as anything else, no special caravan-hiding
mechanic — but the full itemized manifest is realistically only browsed via
the depot's trade screen or an explicit "view items on tile" UI action, not
passively. Not independently source-verified this session beyond the
already-recorded live count; treat the "itemized manifest needs the trade
screen or an explicit look" half as `[I]`, general DF knowledge.

**Buildings** are not independently gated at all beyond the tile they sit
on — a building cannot exist on a tile a vanilla player has never
interacted with, because building requires a designation the vanilla UI
itself refuses to place on hidden terrain (same as the mineral-designation
restriction, §4, `[C-Wiki]` inference by analogy, not separately confirmed
for buildings specifically). The live risk here is entirely on the *tool*
side: DFHack write tools bypass the UI's own placement restrictions, so
nothing stops a tool from placing a building via `quickfort`/direct
struct-write on a tile that has never been revealed — this is exactly the
class of gap the executor's audit needs to close, not something this report
can verify further.

---

## 7. The embark / Site Finder screen — the concrete v53.16 list

Read directly from the live install's `viewscreen_choose_start_sitest`
struct (`df.d_interface.xml`) plus cross-checked against the wiki's current
Embark page. This is the "existence is not location" allowance's exact
boundary, so precision matters — no field here was recalled from memory.

**Passive/confirm-view indicators (`warn_flag` bitfield, `[C-XML]`, always
shown before confirming embark):**
`GENERIC`, `WATER_TABLE`, `HEAVY_WATER_TABLE`, `SALT_WATER`, `LARGE`,
`SMALL`, `DEAD_CIV`, `SAVAGE`, `EVIL`, `UNDEAD`.

**Browse-view text panel (`[C-Wiki]`, current Embark page, moderate-high
confidence — not independently struct-verified field-by-field, since the
actual displayed strings are composed from world-generation data this
session did not trace to a specific struct):**
biome name, region/continent name, temperature classification, tree/
vegetation density, soil presence and depth, clay/sand presence, available
metal ores, flux stone presence, Savagery (benign/neutral/savage), Spirit
alignment (good/normal/evil), aquifer presence **with light vs. heavy
distinguished**.

**Site Finder search criteria (`embark_finder_option` enum, `df.region.xml`,
`[C-XML]`, high confidence, requires the player to deliberately run a
search — the "patience" case):**
`DimensionX`, `DimensionY`, `Savagery`, `Spirit`(evil), `Elevation`,
`Temperature`, `Rain`, `Drainage`, `FluxStone`, `AquiferLight`,
`AquiferHeavy`, `River`, `UndergroundRiver`, `UndergroundPool`,
`MagmaPool`, `MagmaPipe`, `Chasm`, `BottomlessPit`, `OtherFeatures`,
`Soil`, `Clay`, `Sand`.

**What is explicitly *not* on either list, `[C-XML]` checked absence:** no
cavern-layer-count, no mineral/gem identity, no specific vein location. Only
the seven feature-*category* booleans above (river/pool/magma pool/magma
pipe/chasm/pit/other) are searchable — an embark screen search can tell a
player "this region has a chasm somewhere," never where, and never what's
in it.

---

## 8. Fully visible, no spatial hiding

**High confidence, `[C-Wiki]` general knowledge plus this project's own
already-recorded live reads** (`entity_activity_statistics`/`reportst`,
`df.report.xml`, `[C-XML]`, confirms these exist as real per-fort tracked
fields, not just UI text): announcements/gamelog, the stocks screen (exact
counts — patience-allowed by the policy's own wording), unit screens
(skills, thoughts, relationships, health — all about the player's own
citizens, never spatially hidden), job lists, manager orders, the caravan
trade screen once at the depot, noble mandates, the calendar/weather.
`reportst` itself carries population, wealth breakdowns, death/insanity/
execution histories, artifact counts, and `invaders_repelled` as plain
tracked integers — direct struct confirmation that this whole category is
legitimately, unambiguously player-visible aggregate data, matching
`docs/AGENT-ARCHITECTURE.md` §5's existing "what the code layer owes the
models" list (food-days, hauling distance, etc. — this report confirms the
struct-level backing for that category rather than just the design intent).

**Live-confirmed this session:** a poll of `df.global.world.status.
announcements` on the real, paused fort returned 11 entries — weather,
season change, marriage, a liaison arrival, merchants needing the depot, a
migrant wave, a creature stealing an object, combat strike details — all
squarely in this safe category, none feature/terrain-related (consistent
with this young fort having barely dug).

---

## 9. Grey zones, named

- **Caravan's exact remaining days.** No tool in this project currently
  exposes a trade-countdown at all (checked: not present in any read
  tool's fields). Not a live risk today; flag for later if one is added —
  the vanilla UI shows "leaving soon," not a tick count, per general DF
  knowledge `[I]`, not independently struct-verified this session.
- **Exact tile/stock counts.** Explicitly allowed by the policy's own
  wording ("patience is allowed: exact stock counts, counting pools one by
  one"), and corroborated by `reportst`'s own plain integer fields (§8).
- **Knowledge visible once, later re-hidden.** No re-hide mechanism found
  (§1) — checked absence, not exhaustive.
- **Aquifer layer location once dug into.** No special case: once a dwarf
  dug into it, that specific tile's `designation.hidden` is false, same
  mechanism as everything else. The *existence* of an aquifer was already
  legitimately known from embark (§7); only its *exact z-level/extent*
  needed digging, exactly matching the user's own aquifer example.
- **A fort previously played by a human who uncovered things.** `[I]`,
  reasoned from `designation.hidden` being ordinary per-tile save-game
  state plus the already-recorded fact that DFHack persistent site data
  survives retire/unretire: revealed state almost certainly persists too,
  making the "at some point in this fort's life" test well-defined across
  saves and reclaims. Not independently proven by reading save-format code.
- **An announcement that fires without revealing the actor.** New grey
  zone found this session, not in the brief's original list: `CREATURE_
  STEALS_OBJECT` (seen live in this fort's real announcement log, §8) tells
  the player "something was stolen" — a real, vanilla, player-visible fact
  — while the thief itself may still be `isHidden==true` throughout the
  act. Same shape as the `ambush`/`night_attack` report families named in
  the bottom line: DF's announcement layer sometimes tells you an event
  happened without identifying who did it. A tool that reports "a theft was
  announced" is clean; a tool that also resolves and names the still-hidden
  thief in the same call is not.

---

## Preliminary tool classification (`scripts/dfhack/TOOLS.yaml`)

**Preliminary, for the executor to verify and act on — not itself the
audit.** Tag legend: `player_visible` (reads only things a vanilla player
already sees, no gating needed), `player_derivable` (currently low-risk in
how it's used/scoped, but not structurally guarded by a hidden/isHidden
check — could leak on an edge case), `omniscient` (reads or can read
something a vanilla player has no way to know).

| File / command | Tag | Why, and the fields that drive it |
|---|---|---|
| `df-overseer-connectivity.lua` `report` | player_derivable | Groups the player's own living citizens by walkable-group; no hidden-tile read, but a vanilla player has no literal "connectivity report" screen — this is a legitimate derived fact (citizens' own visible positions), not raw memory. High confidence. |
| `df-overseer-connectivity.lua` `check`/`check-units` | player_derivable | Same reasoning, between two named/owned points. High confidence. |
| `df-overseer-landmarks.lua` `list`/`get` | player_visible | Seed (citizen centroid) + the player's own named buildings/burrows — nothing here can be hidden from its owner. High confidence. |
| `df-overseer-landmarks.lua` `build` | player_visible (target), mutate | Builds at an already-known landmark; the concern (§6) is buildings placed on *unrevealed* ground, which this specific command's target set (existing landmarks) doesn't do. High confidence. |
| `df-overseer-overview.lua` `get` | player_visible | Pure composition of the two rows above plus in-game date. High confidence. |
| `df-overseer-diff.lua` `since` — `JOB_COMPLETED` | player_visible | Always the player's own dwarf's job. High confidence. |
| `df-overseer-diff.lua` `since` — `UNIT_DEATH` | omniscient | Fires engine-wide for *any* unit's death, and the file's own comment admits "the kea's own death generated no report at all" — i.e. this raw event is broader than the announcement layer and not gated by visibility at all. Medium-high confidence (reasoned from the file's own honest gap note, not independently live-fired against a hidden death). |
| `df-overseer-diff.lua` `since` — `REPORT` (combat/threat categories) | player_visible | A `REPORT` entry is, by construction, something DF already put in the player's own gamelog/announcement feed. High confidence. |
| `df-overseer-diff.lua` `since` — `UNIT_ATTACK` | player_derivable, leaning omniscient | Structured attacker/defender/wound event; the file itself flags real delivery as unverified and doesn't state whether it's gated by any visibility/report condition. Not independently confirmed either way — flag for the executor to check whether it can fire for two wild animals fighting in an unrevealed area. Low-medium confidence. |
| `df-overseer-diff.lua` `recent-combat`/`since-report` | player_visible | Reads `world.status.reports` directly — literally the gamelog. High confidence. |
| `df-overseer-openarea.lua` `find`/`build` | player_derivable | `is_free` = walkable + no building; no `designation.hidden` check. In practice low risk (radius-capped, anchored near named/dug landmarks, and walkable natural-cavern-floor tiles that are simultaneously hidden are an edge case, not the common one), but not structurally guarded. Medium confidence — reasoned, not exploited live. |
| `df-overseer-diggable.lua` `find`/`dig` | **omniscient** | The task brief's own motivating example, confirmed by direct source read: `is_diggable` checks only `walkable_group==0` + `WALL` shape + natural material, with **no** hidden check anywhere. The returned `material` field is read straight from `tiletype.attrs[tt].material` on tiles that can be arbitrarily far from any revealed ground (only the candidate box's *ring* must border the walkable network, not its interior). A `MINERAL`/`FEATURE`-material result can name an undiscovered vein's material and approximate presence before it is ever revealed. High confidence. |
| `df-overseer-chokepoints.lua` `find` | player_derivable | Same shape as `find_open_area` (walkable-gated), plus a raw-coordinate exception already deliberately spec'd (`pos_for_action_tools`). Not structurally hidden-guarded, same caveat as openarea. Medium confidence. |
| `df-overseer-stuckjobs.lua` `find` | player_visible | Iterates `world.jobs.list` — every entry exists only because the player/fort's own dwarves created it. High confidence. |
| `df-overseer-threat.lua` `scan` | **omniscient** (see bottom line) | Admits by reachability (legitimate), but reports `isHidden` units as informational rather than filtering them, and the tool's own header states its entire purpose is catching ambush/sneaking units `INVASION` and `isDanger` miss — i.e. it is designed to surface exactly what `isHidden(unit)` says a vanilla player cannot see. High confidence this is deliberate and central to the tool, and the single hardest case in this report (see bottom line). |
| `df-overseer-breach.lua` `check` | player_derivable, leaning omniscient on mechanism | Stage 1 scans **every map block**, revealed or not, for `flags.update_liquid`; stage 2 reads `flow_size`/`liquid_type` on any flagged block's tiles regardless of `designation.hidden`. Reported *findings* are gated by adjacency to the citizen network or a landmark radius, which in this tool's actual use case (a slow seep near an already-dug tunnel) likely correlates with revealed-ness — but that correlation isn't the same as checking the field, and a magma-sea rise elsewhere on the map is read (even if not reported) as an internal computation. Medium confidence; recommend an explicit `designation.hidden` check on the finding tile as a cheap, precise fix rather than relying on the reachability proxy. |
| `df-overseer-labor.lua` `unit-status` (idle/injured/military) | player_visible | Filters `getCitizens()` — always the player's own. High confidence. |
| `df-overseer-labor.lua` `unit-status hostile` | **omniscient** | Scans `world.units.active` filtered by `isDanger`/`isOwnCiv` only — **no reachability, no `isHidden`, no `isFortControlled` check at all**. Worse than `threat.lua`: this project's own register (`decisions/DECISIONS.md` 2026-09-11) already recorded this exact command surfacing 4 demons 40 z-levels down behind solid rock. Still `live_deployed: true` today. High confidence, already empirically demonstrated. |
| `df-overseer-labor.lua` `labors`/`set-labor` | player_visible | Per-citizen labor bitfield; no spatial component. High confidence. |
| `df-overseer-ui.lua` `type`/`dump`/`click`/`embark-mode`/`leave-embark-mode` | player_visible (N/A category) | Screen/UI introspection and simulated input, not fort-state reads. High confidence. |
| `df-overseer-ui.lua` `hover` | player_visible | Screen-scrapes the embark screen's own live hover info (biome/aquifer/soil, rectangle corners) — equivalent to a human reading the same on-screen panel, and explicitly pre-fort/out-of-scope for design commitment #1 per `TOOLS.yaml`'s own note. High confidence. |

**Could not classify from source alone:** none outright, but `UNIT_ATTACK`
(above) and `df-overseer-breach.lua`'s exact correlation between "reachable"
and "revealed" are both flagged as needing a live test, not a source read,
to resolve with confidence.

---

## Not verified, and why

- **Windows/skylight/line-of-sight-from-above as a reveal mechanism.** The
  wiki text gathered covers digging/adjacency/stairs only; not checked
  further (would need either more wiki pages or a live probe against a
  constructed window, not attempted — low priority, this fort has none).
- **Whether the underlying `Discovered`/`Announced` flags are actually
  live-read-verified on this exact install.** Confirmed present in
  `announcement_type` (the announcement enum) and in the fort's own
  `report.status.announcements` mechanism live; the `feature_init.flags`
  bits themselves were **not** independently read live against a real
  Uniboslan feature this session (would require navigating
  `world.world_data`'s region/feature-map structures from Lua, not
  attempted — flagged rather than assumed working, per this repo's own
  "mark verified vs proposed" rule).
- **Mineral vein discovery granularity** — whether `block_square_event_
  mineralst.flags.discovered` flips per-vein-segment or tracks something
  finer via the `tile_bitmask`; not live-tested against a real partially-
  dug vein.
- **`item.flags.hidden`'s actual trigger conditions.** Field confirmed to
  exist; what sets/clears it was not traced into item-creation code this
  session.
- **Whether `UNIT_ATTACK` can fire for two wholly unrevealed units fighting
  each other.** Reasoned as plausible from `UNIT_DEATH`'s already-admitted
  gap, not independently confirmed — this project's own file says its real
  delivery is "verified only by mechanism... not a real attack during a
  live test window."
- **Whether caravan goods are visible on the map from the moment the
  caravan enters versus only once it reaches the depot.** Treated as "yes,
  like any unit/item," by analogy and general DF knowledge, not confirmed
  against this fort's own caravan arrival.
- **Off-map/pre-arrival unit visibility semantics** (§5) — not tested live.
- **BWAPI Tournament Module enforcement details** — the raw rules page
  fetch (torchup.org) returned empty content; the claim rests on a
  search-engine summary (`[WebSearch]`), not a directly read primary source.
  SSCAIT's rules page was not independently fetched this session either.
