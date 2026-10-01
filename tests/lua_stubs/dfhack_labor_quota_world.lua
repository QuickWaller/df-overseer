-- A fake DFHack world for tests/test_labor_quota_lua_logic.py:
-- df-overseer-labor.lua's `quota`/`quota-status` commands, added by
-- handoffs/2026-10-01-labor-quota.md.
--
-- Scope, honestly: this models exactly enough of the real game surface to
-- exercise this project's OWN logic -- df.unit_labor name/code round-trip,
-- the autolabor-enabled refusal, DRY_RUN's validate-without-mutating path,
-- the `autolabor LABOR MIN MAX [POOL]` shell-out, and the
-- parse-`autolabor list`-back-into-a-status-table logic. It does NOT model
-- the real autolabor plugin's own reassignment engine: `run_command_silent`
-- is faked here as "look up/write a small in-memory STATE table and format
-- it back out the way print_labor's real text format does"
-- (research/2026-10-01-quartermaster-levers.md §2 quotes that exact format
-- from source). The stub deliberately makes autolabor's own self-reported
-- "currently N dwarfs" differ from the live per-citizen count this file's
-- own `enabled_counts` reads, so a test can prove the two are reported as
-- genuinely independent numbers, not one echoing the other. A live
-- `autolabor list` call is the only thing that proves the REAL text format
-- matches what this parser expects; see the handoff's Result for the exact
-- live test this stream could not run itself (offline stream, no live
-- access).

local NULL = "\0"

-- ---------------------------------------------------------------------------
-- df.unit_labor: a small enum, code<->name both ways plus _first_item/
-- _last_item, matching the real shape df-overseer-labor.lua's own
-- each_labor_code()/labor_code_for() already depend on (a plain table
-- serving as both directions at once, confirmed live against the real
-- install per this file's own header).
-- ---------------------------------------------------------------------------

local LABOR_NAMES = {"MASON", "BREWER", "HAUL_STONE", "MINE"}
local unit_labor = {_first_item = -1, _last_item = #LABOR_NAMES - 1}
for i, name in ipairs(LABOR_NAMES) do
  unit_labor[i - 1] = name
  unit_labor[name] = i - 1
end

df = {unit_labor = unit_labor}

dfhack_flags = {module = true}

package.loaded["json"] = {encode = function() return "" end}

local AUTOLABOR = {enabled = true}
function AUTOLABOR.isEnabled() return AUTOLABOR.enabled end
function AUTOLABOR.setEnabled(v) AUTOLABOR.enabled = v end

-- Test hook: flips whether autolabor "is enabled" without going through a
-- real plugin load, for the refusal-path tests.
function set_autolabor_enabled(v) AUTOLABOR.enabled = v end

function require(n)
  if n == "plugins.autolabor" then return AUTOLABOR end
  if package.loaded[n] then return package.loaded[n] end
  return {}
end

function reqscript(n)
  return {}
end

CR_OK = 0

-- ---------------------------------------------------------------------------
-- autolabor's own in-memory state, formatted back out through
-- `autolabor list`'s real text shape (research §2, `autolabor.cpp:1057-1069`
-- print_labor): "NAME:  minimum N, maximum M, pool P, currently C dwarfs",
-- or "NAME:  disabled", or "NAME:  haulers".
-- ---------------------------------------------------------------------------

local STATE = {
  MASON = {mode = "automatic", minimum = 1, maximum = 5, pool = 50, currently = 3},
  BREWER = {mode = "disabled"},
  HAUL_STONE = {mode = "haulers"},
  -- MINE deliberately has no entry: autolabor reports on it in `list` at
  -- all, exercising quota-status's "no autolabor entry for LABOR" branch.
}

local function build_list_text()
  local names = {}
  for n in pairs(STATE) do names[#names + 1] = n end
  table.sort(names)
  local lines = {}
  for _, n in ipairs(names) do
    local e = STATE[n]
    if e.mode == "disabled" then
      lines[#lines + 1] = n .. ":           disabled"
    elseif e.mode == "haulers" then
      lines[#lines + 1] = n .. ":           haulers, currently 18 dwarfs"  -- real text, live 2026-10-01
    else
      lines[#lines + 1] = string.format(
        "%s:           minimum %d, maximum %d, pool %d, currently %d dwarfs",
        n, e.minimum, e.maximum, e.pool, e.currently)
    end
  end
  return table.concat(lines, "\n") .. "\n"
end

AUTOLABOR_CALLS = {}

local function autolabor_command(args)
  table.insert(AUTOLABOR_CALLS, args)
  if args[1] == "list" or args[1] == "status" then
    return build_list_text(), CR_OK
  end
  -- LABOR MIN MAX [POOL]
  local name, min_s, max_s, pool_s = args[1], args[2], args[3], args[4]
  -- Sentinel MAX value (a test never has a legitimate reason to request a
  -- maximum of exactly 999) to exercise the "autolabor's CLI itself
  -- returned non-OK" failure branch without needing a second dispatch path.
  if max_s == "999" then
    return "simulated CLI failure", 1
  end
  local prior = STATE[name] or {}
  -- Deliberately NOT the same "currently" the caller might expect from an
  -- echo -- autolabor's own reassignment cycle decides that, not this call,
  -- and the stub keeps whatever was there before (or 0) to prove
  -- labor_quota's read-back is a real second read, not a pass-through of
  -- what was just requested.
  STATE[name] = {
    mode = "automatic",
    minimum = tonumber(min_s),
    maximum = tonumber(max_s),
    -- A real omitted POOL keeps autolabor's own prior/default, never the
    -- caller's nil -- another thing an echo could not reproduce.
    pool = pool_s and tonumber(pool_s) or (prior.pool or 100),
    currently = prior.currently or 0,
  }
  return "", CR_OK
end

-- ---------------------------------------------------------------------------
-- Citizens: a fixed, small roster whose real labor bitfield deliberately
-- disagrees with autolabor's own self-reported "currently" count above
-- (MASON: autolabor says 3, the live roster below has only 2 enabled), so a
-- test can assert quota-status reports both numbers distinctly instead of
-- collapsing them into one.
-- ---------------------------------------------------------------------------

local function make_unit(id, labor_names_on)
  local on = {}
  for _, name in ipairs(labor_names_on) do on[unit_labor[name]] = true end
  return {
    id = id,
    status = {labors = on},
    military = {squad_id = -1},
    job = {current_job = nil},
    body = {wounds = {}},
  }
end

local CITIZENS = {
  make_unit(1, {"MASON"}),
  make_unit(2, {"MASON"}),
  make_unit(3, {}),
}

dfhack = {
  run_command_silent = function(tool, ...)
    if tool ~= "autolabor" then
      return "", CR_OK
    end
    return autolabor_command({...})
  end,
  units = {
    getCitizens = function() return CITIZENS end,
  },
}
