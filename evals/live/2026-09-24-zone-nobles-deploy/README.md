# Live run: deploy the zone inventory, zone validity, furniture-aware siting and the position requirements check

Date: 2026-09-24 (work dated 2026-09-23). User go-ahead: "sweet as go for it".

Seven files, each hashed as committed bytes (`git -c core.autocrlf=false show
HEAD:<path>`), again on arrival in `/tmp`, and again at the installed path.
**All three readings matched for all seven.** Previous copies backed up first
to a dated directory with timestamps preserved.

| File | sha256 (first 16) |
|---|---|
| `scripts/dfhack/df-overseer-nobles.lua` | `cf2264b92540c3b2` |
| `scripts/dfhack/df-overseer-zone.lua` | `1ac023bcf982cf1b` |
| `scripts/dfhack/TOOLS.yaml` | `653bc9fb0c232c81` |
| `dfmcp/tools.py` | `2d3f6a5f4ed9f9a4` |
| `agents/architect/tools.yaml` | `21def7b492d82bd7` |
| `agents/consultant/tools.yaml` | `8c7167bf3bcb27be` |
| `agents/overseer/tools.yaml` | `d21269db4aa76aae` |

No quicksave was taken for this deploy and none was needed: the fort read
`abs_tick 12611557`, identical to the tick at which this morning's
`autosave 2` was confirmed, so no fort time had passed and that save is still
an exact restore point. Nothing here reaches game state; the fort stayed
paused throughout. MCP server restarted clean, no `RoleValidationError`,
which is real evidence the new grants and the new manifest agree.

## Check 1: the acceptance test, now live rather than hand-traced

`nobles requirements MANAGER`:

```
"Office": { "position_field": "required_office", "required": 1,
            "status": "not_met", "zone_ids": [ 11 ],
            "detail": "every owned zone's getRoomDescription read succeeded
            and returned empty; the strongest evidence available that this
            room's value has not cleared the lowest quality tier, not proof
            of an exact number" }
```

Bedroom, DiningHall and all four furniture counts read `not_required` for
this position, correctly. Only zone 11 is listed because zone 10 is unowned
and therefore not the holder's room. **This is the check that would have
caught the office problem on day one.**

## Check 2: the fort can now see its own rooms

`zone list "" "" "" ""` (unfiltered, so the summary path):

```
counts_by_kind: { "Office": 2 }, total_zones: 2, read_failures: []
needs_attention:
  id 10  Office  owner_status unowned  room_value_status not_met
  id 11  Office  owner_status owned (unit 345)  room_value_status not_met
```

Both offices flagged, with the owner state kept separate from the room-value
state. One call now reports what took two days of manual investigation.

## Check 3: furniture-aware siting works, and ranks badly

`zone find Office 1 1 0 "shale Throne" 2 true` returns 5 candidates, and
**rank 2 reads `contains_qualifying_furniture: true` with
`furniture_building_ids: [9]`**, which is the fort's Chair. The flag works and
resolves the right building.

**But the same search at 3x3 returns 5 candidates, all
`contains_qualifying_furniture: false`.** The site containing the Chair is
either not a legal 3x3 window or ranks below the cut. So a caller asking for a
realistic office footprint still gets only furniture-free sites, ranked first,
with the useful one invisible.

**Finding: ranking does not prefer a site that contains qualifying furniture,
and for a kind with a `room_value_field` it should.** For those kinds a site
containing furniture is strictly more useful than one without, because the
furniture is what gives the room its value. The flag correctly informs rather
than refuses, per its brief, but informing only helps if the useful candidate
is visible. Left unfixed, an advisor asking for a 3x3 office is led straight
back to an empty rectangle, which is the exact failure this work exists to
prevent.
