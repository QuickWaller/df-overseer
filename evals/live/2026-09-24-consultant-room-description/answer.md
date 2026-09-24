## Live state of your fort right now (read this session)

Before the ranked list, here is what the tools actually say about your build, because your description matches the live data almost exactly and it sharpens the diagnosis:

- **Manager is held** by unit 345, `required_office = 1`, not vacant. [verified — `nobles.list`]
- **The Manager owns exactly one Office zone: id 13.** [verified — `nobles.requirements`]
- **Zone 13 is a 3×3, not_enclosed, with 15 wall-shaped ring tiles and exactly 1 gap** (`open_floor_edge`, not a doorway/missing wall). [verified — `surface.enclosure`] — matches your "fifteen wall tiles, one doorless entrance gap."
- **Zone 13's 15 boundary wall tiles are all smooth (fraction 1.0); its 9 floor tiles are all rough_natural (fraction 0.0).** [verified — `surface.finish`] — matches your "walls smoothed, floor unsmoothed."
- **Zone 13's boundary ring is 11 STONE + 5 MINERAL tiles.** [verified — `surface.material`] — matches "carved into solid stone."
- **And the read still comes back empty**: `nobles.requirements MANAGER` → Office `status: not_met`, detail "every owned zone's getRoomDescription read succeeded and returned empty", `zone_ids: [13]`. [verified — `nobles.requirements`]

So your zone's footprint, finish, and material are all exactly as you described and all live-verified. The zone is *not* the problem. The empty read is stable and real.

---

## (1) Why `getRoomDescription` returns empty, ranked

First, what "empty" means: DFHack's own doc for `getRoomDescription(building[, unit])` says it "returns a description including quality modifiers… **Otherwise, returns an empty string**." [verified — install's `Lua API.txt`, and this fort's own `room-value-not-computable-only-quality-word` doctrine entry]. Empty = DF does not currently consider this zone a room of this kind = nothing room-qualifying is being counted toward it. It is *not* "a Meager room with no number shown"; a Meager room would return a non-empty word.

1. **The chair is not actually inside the zone footprint (game mechanic) — leading cause.** This is the exact bug this fort already proved on 2026-09-23: the fort's one chair (building id 9) sat *outside* both office zones' rectangles, and neither zone had ever contained furniture. [verified, site-scoped — `uniboslan-office-furniture-outside-zone-footprint`]. If the chair you're looking at is that same chair, it is outside zone 13. If you built a *new* throne inside zone 13, this cause is ruled out — but then the empty is surprising and you move to #2–#4.
2. **The "chair" isn't a completed chair/throne building (game mechanic).** A *loose* stone throne item sitting on the floor, or a chair still mid-construction, contributes nothing. Only a built, `flags.exists` Chair/Throne building inside the footprint counts. [standard practice]
3. **Zone kind isn't actually Office (game mechanic).** Ruled out here: `nobles.requirements` already resolved zone 13 as an Office and read it empty. [verified]
4. **Owner not set (game mechanic for the *requirement*, but *not* a cause of empty description).** `getRoomDescription` without a unit argument reads the generic room value, not owner-dependent value; the owner only matters for `nobles.requirements`' owned-zone filter. Your owner is confirmed set (both sides) and zone 13 is owned, so this is ruled out as the cause of the empty string — though it would independently cause `not_met` if it were missing. [verified / standard practice]
5. **Recompute/cache timing (artifact) — plausible but low.** See below.

On the caching question specifically: `getRoomDescription` is a native DFHack binding that **forwards to DF's own closed-source value computation**; it does not scan furniture itself, and it's a synchronous read of DF's current state, so a paused game returns whatever DF currently has rather than "nothing because the game hasn't ticked." [verified — `Lua API.txt`; `room-value-not-computable-only-quality-word`]. Two things argue against a timing artifact here: the empty read has been **stable across many reads and sessions** (2026-09-23 doctrine through today's read), and it persisted through an *unpaused* live run when the chair finished building. [verified — doctrine note + today]. What I **cannot** tell you is *when* DF internally recomputes the value — per tick, lazily when a menu/dwarf looks at the room, or cached-until-invalidated; nothing in this install's readable source or docs states it. [unknown]. So I can't give you the schedule, but I can say: if you want to rule out timing entirely, unpause one tick (or open the zone's room screen once) and re-read; I expect no change.

---

## (2) Smallest thing to try first — and the success signal

**First, read-only, zero-risk:** compare the chair building's center tile against zone 13's rectangle and confirm the chair's tile falls inside it (the rectangle is inclusive of its edges). Concretely in DFHack:

```lua
local z = df.building.find(13)
print(z.room.extents.x, z.room.extents.y, z.room.extents.width, z.room.extents.height)  -- or z.x1/y1/x2/y2
-- then find your Chair/Throne building and check its centerx/centery is inside that rectangle
```

- **Diagnostic success signal:** if the chair's tile is *not* inside, you've found the bug. If it *is* inside and `flags.exists` is true, geometry is ruled out and we escalate to the other causes.
- **Actual "it worked" signal:** once a completed chair/throne is genuinely inside the footprint, `getRoomDescription` returns a **non-empty quality word** (at minimum "Meager Office", likely higher given your 15 smoothed walls), and `nobles.requirements MANAGER` flips Office from `not_met` to `met`. The game's own equivalent: the Manager's Study icon in the Nobles screen goes green. [standard practice]

---

## (3) What reaches the lowest tier — and is one chair enough?

- **Tier thresholds** (current-namespace wiki, corroborated — not independently confirmed — by live position data): Meager, then Modest 100, base name 250, Decent 500, Fine 1000, Great 1500, Grand 2500, Royal 10000. Manager's `required_office = 1` sits in the Meager band: **any positive value clears it.** [recall — `room-value-quality-tier-table`; the 1/100/250/500 numbers match this fort's live raws exactly, which the doctrine records as real support, not proof]
- **Is one chair enough? Yes.** The current-namespace Manager wiki states the office "must at least have a chair," and that building a chair inside turns the Study icon green. A throne counts as a chair. [recall — current wiki; consistent with the live `required_office = 1`]
- **Door?** Not required to make it a room or to reach Meager; a door adds value but isn't the prerequisite. [recall]
- **Table?** Not required; adds value if present. [recall]
- **Floor finish?** Not required at this level; smoothing/engraving the floor adds value *above* the base, but your unsmoothed floor is fine for Meager. [recall]
- **Wall finish?** Smoothing walls adds value (you already did all 15, verified), but it does *not* create a room by itself — value still needs a counted furniture item. [recall]

**Bottom line:** the one and only prerequisite to stop getting an empty string is at least one qualifying piece of furniture actually inside the footprint. A single chair clears Meager on its own.

---

## (4) Is anything in your setup wrong?

- **Zone footprint vs chair position — the open question, and the leading suspect.** Your footprint, finish, and material are all correct and live-verified; yet the read is still empty. Given "a chair alone is enough," that means the chair is almost certainly *not being counted* — either it isn't actually inside the footprint, or it isn't a completed chair building. I **cannot read the chair's tile with my current toolset** (I can read the zone's footprint and boundary, but no tool here returns a furniture building's coordinates), so this is the one thing you must check yourself — it's exactly the check in §2. And note the live contradiction plainly: your description says a chair is inside, but the fort's only known chair was verified *outside* both office zones as of 2026-09-23. If you didn't build a new throne inside zone 13, the chair is still outside. [verified + recall]
- **Owner assignment — fine.** Manager held (unit 345), zone 13 owned by him, both sides confirmed. Not the problem. [verified]
- **Enclosure — fine, and irrelevant here.** Zone 13 reads `not_enclosed` (one open edge), and that is *not* the cause: an office "does not necessarily need to be enclosed" (current-namespace Office wiki), and nothing on this install ties indoor/outdoor status to room value. Your doorless gap is not the bug. [recall — `room-indoor-status-not-shown-to-matter`]
- **Smoothing — fine, but insufficient alone.** Your 15 smoothed walls add value but cannot make a room appear without a counted furniture item. [recall]

**What I plainly do not know:** the exact numeric threshold at which DF first returns a quality word vs. empty (0 vs. 1 — DFHack exposes no number here, so I can't confirm it from this install), and *when* DF recomputes room value internally. Both are stated as such above. The operational conclusion doesn't depend on either: one completed chair inside the footprint is the fix, and the empty→non-empty flip on `getRoomDescription` is your proof it worked.