# Manager appointment: game-made versus tool-made, 2026-10-08

Question: why did `nobles.appoint` (unit 345, MANAGER) read as consistent from `nobles verify` and
show a green Study icon, yet the Work Orders screen said "must assign a manager for work orders",
while a manager appointed through the Nobles screen (unit 347) works.

## Phase A: read-only dump (live Uniboslan, all reads through `dfhack-run lua -f`)

Fort state at read time: tick 353715, paused (`pause_state` true, tick static over 5 s). Nothing was
written. Ids: fortress entity 36 (SiteGovernment), civ entity 12, histfigs 331 (unit 345, the old
manager) and 333 (unit 347, the new manager, also EXPEDITION_LEADER).

### Which entity holds MANAGER

Only the fortress entity 36 defines the MANAGER position (id 10, own-vector index 6). The civ entity 12
has no MANAGER position. So the tool writing to entity 36 was correct; a wrong-entity write is ruled
out. The game's appointment of 347 also wrote entity 36, assignment id 6.

### The assignment (entity 36, assignment idx/id 6, position 10), game-made as it stands now

`histfig=333 histfig2=333 position_vector_idx=6 squad_id=-1 st_id=-1 ab_id=-1 flags.active=true`

Every vacant assignment of entity 36 has `position_vector_idx = -1`; every held one has it set to the
position's index in `positions.own` (MANAGER 6, EXPEDITION_LEADER 4, matching the index of the position
in the own vector). In the civ entity every assignment carries it (0, 1, 4, 5, 8 = own index), and a
vacated civ assignment keeps `position_vector_idx` and keeps the previous holder in `histfig2` with
`histfig=-1` (idx 0: hf -1, hf2 35; idx 2: hf -1, hf2 33; idx 4: hf -1, hf2 185).

`appoint` never wrote `position_vector_idx`. It is the game's cached index of the position profile.

### The holder's link, game-made (hf 333) versus tool-made

| field of `histfig_entity_link_positionst` | game-made (hf 333, assignment 6) | what `appoint` wrote |
|---|---|---|
| entity_id | 36 | 36 |
| assignment_id | 6 | 6 |
| assignment_vector_idx | 6 | 6 |
| link_strength | 100 | 100 |
| start_year | 31 | 31 |
| **entity_vector_idx** | **36** (the entity's index in `world.entities.all`, verified `entities.all[36].id == 36`) | **-1 (unset)** |

df-structures names `entity_vector_idx` `entity_cached_index` (`refers-to world.entities.all[$]`,
`init-value -1`) and `assignment_vector_idx` `position_profile_cached_index`. Every `positionst` link
anywhere on the fort has a real `entity_vector_idx` (hf 323: 12, hf 353: 12, hf 333: 36 twice).
Only `former_positionst` links carry -1 (all of them, including the game's own removal of 345's link),
so -1 is right for a former link and wrong for a live one.

### History events

Game appointing 347: event 1650 `ADD_HF_ENTITY_LINK`, civ=36, histfig=333, link_type=10 (POSITION),
position_id=10, appointer_hfid=-1, promise_to_hfid=-1. Game removing 345: event 1649
`REMOVE_HF_ENTITY_LINK`, civ=36, histfig=331, link_type=10, position_id=10 (so the game itself
acknowledged 345's link when it removed it). Unit 345 has NO add event for the position, only the
membership event 1504 (link_type 0, year 30): the `minimal` version of `appoint` writes none.
Unit 347 has the add events 1607 (EXPEDITION_LEADER, position 8) and 1650 (MANAGER).

### Unit 345 after the game's change

`entity_links`: memberst 12, memberst 36, then TWO identical `former_positionst` (assignment 6,
entity 36, start 31, end 31, entity_vector_idx -1). The duplicate is odd (one from the game's removal,
one from an earlier unappoint of ours, probably) and harmless to the manager check but shows
`unappoint` is not idempotent-clean.

### Unit-level fields that could cache a position

Compared 345 and 347 side by side: flags1/2/3/4, mood (-1 both), civ_id 12, population_id 10,
relationship_ids, military squad -1, current job none. No difference that could carry a position;
only `histfig.flags.never_cull` is true on 347 (probably the expedition leader's), and professions
differ (345 Stonecrafter, 347 profession 1). `dfhack.units.getNoblePositions` reads only histfig
`entity_links` of type `positionst`, then `historical_entity.find(entity_id)` and
`binsearch_in_vector` of assignments/positions by id (DFHack `library/modules/Units.cpp`, read from
upstream). It never reads any cached index, so it, and therefore our `verify`, cannot see a missing
cached index. That is why `verify` kept calling the appointment consistent.

### plotinfo

`plotinfo.nobles` (`plotinfo_positionst`): `manager_cooldown 573`, `bookkeeper_cooldown 0`,
`bookkeeper_precision 0`, `flags 0`; `plotinfo.manager_timer 2`. Neither names a unit; they are
cooldowns, not a cached holder. No plotinfo field holds the manager's id.

### DFHack's own appointers

`hack/scripts/make-monarch.lua` (the model for `appoint`): sets `assignment.histfig`, erases the old
holder's link, inserts a `positionst` link with `entity_id`, `link_strength`, `assignment_id`,
`assignment_vector_idx` (from `ipairs`, which is 1-based: an off-by-one bug in that script) and
`start_year`. It never sets `entity_vector_idx`, `histfig2`, `position_vector_idx`, or an event, and
acts on the civ entity. It works for a monarch because nothing the monarch does needs those caches;
a manager's Work Orders screen evidently does. `internal/emigration/unit-link-utils.lua` is the
removal side (former link plus remove event). No DFHack script or `gui/` tool appoints a fortress
position the way the Nobles screen does.

## Diagnosis

Differences between a game-made and a tool-made MANAGER appointment, ranked:

1. `assignment.position_vector_idx` left at -1 (the game sets it to the position's index in
   `positions.own`).
2. The holder link's `entity_vector_idx` left at -1 (the game sets it to the entity's index in
   `world.entities.all`).
3. No `ADD_HF_ENTITY_LINK` (POSITION) history event.

I believe the cause is 1 and/or 2: both are cached indexes the game uses to resolve the position
and entity without a search, and a Work Orders check that looks up "who is the manager" through them
would find nothing, while getNoblePositions (which searches by id) finds the holder fine. The event
(3) is bookkeeping for the history screens and the unit's biography; I think it is unlikely to
matter. **Confidence: about 70% that the missing cached indexes are the cause; I cannot split 1 from
2 without a live write, and the fix writes both plus the event so it matches the game fully.**
The read cannot prove it: the proof is Phase C (unappoint/appoint through the fixed tool, then the
Work Orders screen and a job appearing). The wiki-only theory of the room-value check is irrelevant
(the Study icon was green).

Unverified: that the Work Orders screen reads these caches (closed source; inferred from the
evidence above), and what 345's assignment looked like before the user changed it (already
overwritten).

## Phase B and C

Appended below as they complete.
