-- df-overseer-blueprint-parse.lua
--@module = true
--
-- handoffs/2026-09-30-reservation-gaps.md item 3: df-overseer-landmarks.lua's
-- build_at_landmark only ever checked its own anchor tile against a
-- reservation, because it never learned the blueprint's footprint size. The
-- fix reuses df-overseer-blueprint.lua's own quickfort-CSV parsing --
-- "no second CSV parser" -- but that file cannot be reqscript'd directly
-- from df-overseer-landmarks.lua: df-overseer-blueprint.lua's OWN header
-- already documents reqscripting df-overseer-landmarks.lua itself (for
-- near-landmark siting), so landmarks -> blueprint would close a two-way
-- reqscript cycle, exactly what df-overseer-reservations.lua's own header
-- warns against ("correctness would depend on which file's own top-level
-- execution had gotten further").
--
-- This file is the extracted, dependency-free leaf: the pure text/CSV
-- parsing df-overseer-blueprint.lua's own `load_blueprint` used to do
-- locally, moved here verbatim (no game API, no reqscript of its own) so
-- BOTH df-overseer-blueprint.lua and df-overseer-landmarks.lua can
-- reqscript it without depending on each other. df-overseer-blueprint.lua's
-- own exported `load_blueprint` is now a one-line delegator to this file's
-- copy -- there is exactly one parser, just relocated.
--
-- Two entry points, because df-overseer-blueprint.lua's TEMPLATE argument
-- and df-overseer-landmarks.lua's BLUEPRINT_FILE argument name a file two
-- different ways:
--   load_blueprint(name) -- a bare template NAME: tries
--     templates/NAME.csv then NAME.csv under dfhack-config/blueprints/,
--     exactly as df-overseer-blueprint.lua's TEMPLATE argument always has.
--   load_blueprint_file(path) -- an exact, already-deployed relative path
--     (df-overseer-landmarks.lua's own BLUEPRINT_FILE, passed to quickfort's
--     own `run` verbatim since 2026-09-11 -- it is not looked up through the
--     templates/-or-bare convention above, so it needs its own entry point,
--     not a guess at which convention it follows).
-- Both return the same shape: {qname =, sections =, w =, h =, room =} or
-- nil, err.

local function valid_name(s)
  return type(s) == 'string' and #s > 0 and #s <= 80 and s:match('^[%w_%-]+$') ~= nil
end

local function read_file(path)
  local f, err = io.open(path, 'r')
  if not f then return nil, tostring(err) end
  local text = f:read('*a')
  f:close()
  return text
end

local BLUEPRINT_DIR = 'dfhack-config/blueprints/'

-- Returns quickfort_name, text or nil, err.
local function locate_blueprint(name)
  if not valid_name(name) then
    return nil, "blueprint name must be a bare identifier (letters, digits, _ or -), got a value that is not"
  end
  local tried = {}
  for _, rel in ipairs({'templates/' .. name .. '.csv', name .. '.csv'}) do
    local text = read_file(BLUEPRINT_DIR .. rel)
    if text then return rel, text end
    tried[#tried + 1] = rel
  end
  return nil, "no blueprint '" .. name .. "' on the guest (looked for " ..
    table.concat(tried, " and ") .. " under dfhack-config/blueprints/); deploy the .csv first"
end

-- Section modes this parser understands the cells of. Others are skipped
-- for geometry (notes, aliases) -- df-overseer-blueprint.lua's own
-- supported_modes refuses those where it matters; this leaf only computes
-- footprint, so it stays silent about them.
local GRID_MODES = {dig = true, build = true, place = true, zone = true, meta = true}
local VALID_MODES = {dig = true, build = true, place = true, zone = true,
  burrow = true, meta = true, notes = true, ignore = true, aliases = true}

-- Parses quickfort's multi-section .csv into sections. Only what a caller
-- needs: each section's mode, label, modeline flags, and its non-empty
-- cells as {x, y, text}, 1-based, with (1,1) the blueprint's top-left cell.
-- Rules mirrored from quickfort (parse.lua modeline grammar): a line
-- beginning `#` followed by a valid mode word starts a section; in a grid
-- row a cell beginning `#` starts a comment and ends the row; a cell of a
-- single backtick is quickfort's "ignore this cell". Blank lines count as
-- rows. Moved verbatim from df-overseer-blueprint.lua -- see header.
function parse_sections(text)
  local sections, cur = {}, nil
  local unnamed = 0
  for raw in (text .. "\n"):gmatch("([^\n]*)\n") do
    local line = raw:gsub("\r$", "")
    local mode = line:match("^#(%a+)")
    if line:match("^#%s*[<>]") then
      -- quickfort's level-change line (`#>` down, `#<` up, optionally with a
      -- count). Without this the line falls through to the grid-row branch
      -- below, whose first cell starts with `#` and ends the row: an empty
      -- row, and the levels beyond it silently folded onto the first.
      sections.multi_level = true
    elseif mode and VALID_MODES[mode] then
      unnamed = unnamed + 1
      cur = {
        mode = mode,
        label = line:match("label%(([^)]*)%)") or tostring(unnamed),
        has_start = line:find("start%(") ~= nil,
        has_hidden = line:find("hidden%(") ~= nil,
        cells = {}, row = 0, w = 0, h = 0,
      }
      sections[#sections + 1] = cur
    elseif cur and GRID_MODES[cur.mode] then
      cur.row = cur.row + 1
      local x = 0
      for cell in (line .. ","):gmatch("([^,]*),") do
        x = x + 1
        local t = cell:match("^%s*(.-)%s*$")
        if t:sub(1, 1) == "#" then break end
        if cur.mode == "meta" and t:find("repeat%s*%(") and (t:find("up") or t:find("down")
            or t:find("[<>]")) then
          -- a meta cell that repeats a blueprint up or down levels
          sections.multi_level = true
        end
        if #t > 0 and t ~= "`" then
          cur.cells[#cur.cells + 1] = {x = x, y = cur.row, text = t}
          if x > cur.w then cur.w = x end
          if cur.row > cur.h then cur.h = cur.row end
        end
      end
    end
  end
  return sections
end

-- Given already-parsed `sections`, the overall footprint (w, h) and the
-- first #zone section's own bounding box (room), or nil, err if any section
-- uses start()/hidden() (origin-shifting, unsupported here) or no section
-- has any cells at all. Moved verbatim from df-overseer-blueprint.lua's own
-- load_blueprint -- see header.
function footprint_from_sections(sections)
  if sections.multi_level then
    return nil, "this blueprint changes levels (a `#>` or `#<` line, or a meta that repeats up or down); "
      .. "this verb reads and applies ONE level only and would fold the levels onto one footprint, so it refuses. "
      .. "Join levels with the stair pair tool (diggable dig-stair) and apply each level as its own blueprint"
  end
  local w, h = 0, 0
  local room = nil
  for _, s in ipairs(sections) do
    if s.has_start or s.has_hidden then
      return nil, "section '" .. s.label .. "' uses start() or hidden(), which shift the origin; this verb does not support that"
    end
    if GRID_MODES[s.mode] and s.mode ~= "meta" then
      if s.w > w then w = s.w end
      if s.h > h then h = s.h end
    end
    if s.mode == "zone" and not room and #s.cells > 0 then
      local x1, y1, x2, y2 = 1e9, 1e9, 0, 0
      for _, c in ipairs(s.cells) do
        x1 = math.min(x1, c.x); y1 = math.min(y1, c.y)
        x2 = math.max(x2, c.x); y2 = math.max(y2, c.y)
      end
      room = {x1 = x1, y1 = y1, x2 = x2, y2 = y2}
    end
  end
  if w == 0 or h == 0 then return nil, "blueprint has no cells to apply" end
  return {w = w, h = h, room = room}
end

-- A bare template NAME (df-overseer-blueprint.lua's own TEMPLATE argument
-- convention: templates/NAME.csv, else NAME.csv). Returns {name =, qname =,
-- sections =, w =, h =, room =} or nil, err.
function load_blueprint(name)
  local qname, text = locate_blueprint(name)
  if not qname then return nil, text end
  local sections = parse_sections(text)
  if #sections == 0 then return nil, "no quickfort sections found in " .. qname end
  local fp, err = footprint_from_sections(sections)
  if not fp then return nil, err end
  return {name = name, qname = qname, sections = sections, w = fp.w, h = fp.h, room = fp.room}
end

-- An exact, already-deployed relative path under dfhack-config/blueprints/
-- (df-overseer-landmarks.lua's own BLUEPRINT_FILE, passed to quickfort's own
-- `run` verbatim -- it does not follow the templates/-or-bare NAME
-- convention above, so it is read directly rather than through
-- locate_blueprint). Returns {qname =, sections =, w =, h =, room =} or
-- nil, err.
function load_blueprint_file(path)
  if type(path) ~= 'string' or #path == 0 then
    return nil, "BLUEPRINT_FILE must be a non-empty path"
  end
  local text, err = read_file(BLUEPRINT_DIR .. path)
  if not text then
    return nil, "could not read blueprint '" .. path .. "' under dfhack-config/blueprints/: " .. tostring(err)
  end
  local sections = parse_sections(text)
  if #sections == 0 then return nil, "no quickfort sections found in " .. path end
  local fp, ferr = footprint_from_sections(sections)
  if not fp then return nil, ferr end
  return {qname = path, sections = sections, w = fp.w, h = fp.h, room = fp.room}
end

-- No dfhack_flags.module guard, no CLI section: reqscript-only leaf, same
-- discipline as df-overseer-reservations.lua.
