-- Placement access gate: pure logic (stage C3, register 2026-10-08, D2 and D7).
--
-- WHAT IS CHECKED, honestly. This is the ENTRANCE-CELL check, not a check of
-- the planned circulation graph. A new room's entrance cells are the portal
-- tiles of its footprint (read from the template's own #dig cells by
-- df-overseer-blueprint.lua). For each portal this looks at the portal tile
-- and the tile(s) just outside the footprint, and asks which existing room
-- footprints (zones with their wall ring, blueprint sites, room reservations)
-- those tiles fall inside. Then two rules, both from room-kinds data
-- (df-overseer-roomkinds.lua, generated from blueprints/room-kinds.yaml):
--
--   private_pass_through  (D7)  an entrance may not open into a PRIVATE room:
--       the new room would be reached only through it. Applies to every new
--       kind, private or not.
--   access                (D2)  the new kind's access rule: `corridor` means
--       the entrance must open onto a tile inside no room's footprint;
--       `opens_onto` also allows rooms of the listed kinds; `any` allows all.
--
-- NOT checked here: a true planned-state reachability search (existing
-- walkable tiles plus this blueprint's pending digs), a second route into a
-- room, and an EXISTING room's entrances being walled in by the new footprint
-- (a footprint overlap is already refused by the reservations ledger).
-- Dead ends and single routes stay report-only, in circulation.graph.
--
-- Pure: takes plain tables, reads no game state, never returns a coordinate.
-- Reqscript only; no CLI.
--
--   placement = { kind = "bedroom", z = 5, portals = { { x=, y=, outward = { {x=, y=}, ... } } } }
--   others    = { { name = "Bedroom #24", kind = "bedroom" | nil, z = 5, x1=, y1=, x2=, y2= } }
--     (others' rectangles already include the room's wall ring; kind nil = an
--      unclassified footprint, treated as a non-private room)

local roomkinds = reqscript('df-overseer-roomkinds')

local function label(kind_id)
  return (tostring(kind_id):gsub("_", " "))
end

local function inside(o, z, x, y)
  return o.z == z and x >= o.x1 and x <= o.x2 and y >= o.y1 and y <= o.y2
end

-- Returns { verdict = "clear" | "refused" | "unclassified", checked_kind,
--   access, rooms_considered, portals_checked, refusals = { {rule, text, room} } }.
-- "unclassified" = the placement's kind is not in the room-kind data, so no
-- rule applies (a corridor template, say); it is reported, not guessed at.
function check_entrances(placement, others)
  local k = roomkinds.kind(placement.kind)
  local out = {
    checked_kind = placement.kind, rooms_considered = #(others or {}),
    portals_checked = #(placement.portals or {}), refusals = {},
  }
  if not k then
    out.verdict = "unclassified"
    return out
  end
  out.access = k.access.mode
  out.implemented = "entrance cells only (not the planned circulation graph)"
  local seen = {}
  local new_name = "the new " .. label(placement.kind)
  for _, portal in ipairs(placement.portals or {}) do
    local tiles = { { x = portal.x, y = portal.y } }
    for _, t in ipairs(portal.outward or {}) do tiles[#tiles + 1] = t end
    for _, o in ipairs(others or {}) do
      local hit = false
      for _, t in ipairs(tiles) do
        if inside(o, placement.z, t.x, t.y) then hit = true break end
      end
      if hit then
        local okind = o.kind
        local oprivate = okind ~= nil and roomkinds.is_private(okind)
        local rule, text
        if oprivate then
          rule = "private_pass_through"
          text = string.format(
            "%s entrance would open into %s, a private room, so %s could only be reached through it "
              .. "(rule: a room may not be reached through a private room)",
            new_name, o.name, new_name)
        elseif k.access.mode == "corridor" then
          rule = "access"
          text = string.format(
            "%s entrance would open into %s, but a %s must open onto a corridor (kind access rule: corridor)",
            new_name, o.name, label(placement.kind))
        elseif k.access.mode == "opens_onto" then
          local allowed = false
          for _, ak in ipairs(k.access.kinds) do if ak == okind then allowed = true end end
          if not allowed then
            rule = "access"
            text = string.format(
              "%s entrance would open into %s, but a %s may open only onto a corridor or a room of kind %s "
                .. "(kind access rule: opens_onto)",
              new_name, o.name, label(placement.kind), table.concat(k.access.kinds, ", "))
          end
        end
        if rule and not seen[o.name .. "|" .. rule] then
          seen[o.name .. "|" .. rule] = true
          out.refusals[#out.refusals + 1] = { rule = rule, text = text, room = o.name }
        end
      end
    end
  end
  out.verdict = (#out.refusals > 0) and "refused" or "clear"
  return out
end

-- One sentence for a refused verdict (all refusals joined), or nil when clear.
function refusal_text(verdict)
  if not verdict or verdict.verdict ~= "refused" then return nil end
  local parts = {}
  for _, r in ipairs(verdict.refusals) do parts[#parts + 1] = r.text end
  return table.concat(parts, "; ") .. ". Pick another RANK, RADIUS or landmark so the entrance opens onto a corridor"
end
