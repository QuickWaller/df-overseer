-- df-overseer-autofarm.lua
--@module = true
--
-- Conductor-only: writes the Planner's crop stock levels into DFHack's `autofarm`
-- plugin (register 2026-10-09, "switch farming to autofarm";
-- research/2026-10-09-autofarm-switch.md). Autofarm plants, per built plot, whichever
-- eligible crop has stock below its level; a level is a plant count, 0 means never.
-- No model holds this tool (it is on no allowlist but the conductor's); the Planner
-- owns the numbers as plan targets and the conductor applies them each cycle.
--
-- set DEFAULT [LEVELS]
--   DEFAULT  the plugin's default level (a whole number, 0 or more)
--   LEVELS   optional "TOKEN=N,TOKEN=N": per-crop levels by plant raw token.
-- Runs `autofarm default N`, one `autofarm threshold N TOKEN` per crop, then
-- `enable autofarm`, then reads `autofarm status` back. Idempotent: setting the same
-- numbers again changes nothing. A refusal (bad token, bad number, a plugin that is
-- not installed) comes back as `nil, message` and stops before anything later runs.
-- Writes plugin state (kept in the world save), never a plot slot directly.

local json = require('json')

local function whole_number(s)
  local n = tonumber(s)
  if n == nil or n < 0 or n ~= math.floor(n) or n > 1000000 then
    return nil
  end
  return math.floor(n)
end

local function run(...)
  local out, status = dfhack.run_command_silent(...)
  -- CR_OK is 0; a missing return is treated as a failure, never as success.
  if status ~= nil and status ~= 0 then
    return nil, tostring(out)
  end
  if status == nil and out == nil then
    return nil, "no result from the command"
  end
  return out
end

-- Pure parse of the LEVELS argument: returns a list of {token, level} or nil, message.
function parse_levels(levels)
  local out = {}
  if levels == nil or levels == "" then
    return out
  end
  for item in string.gmatch(levels, "[^,]+") do
    local token, n = string.match(item, "^%s*([A-Z][A-Z0-9_]*)%s*=%s*(%d+)%s*$")
    local level = n and whole_number(n)
    if not token or level == nil then
      return nil, "bad level " .. string.format("%q", item) .. ": expected TOKEN=N, a plant raw token and a whole number"
    end
    out[#out + 1] = {token = token, level = level}
  end
  return out
end

function autofarm_set(default_level, levels)
  local default = whole_number(default_level)
  if default == nil then
    return nil, "DEFAULT must be a whole number, 0 or more"
  end
  local parsed, perr = parse_levels(levels)
  if not parsed then
    return nil, perr
  end
  local _, err = run('autofarm', 'default', tostring(default))
  if err then
    return nil, "autofarm default failed: " .. err
  end
  local applied = {}
  for _, row in ipairs(parsed) do
    local _, e = run('autofarm', 'threshold', tostring(row.level), row.token)
    if e then
      return nil, "autofarm threshold " .. row.token .. " failed: " .. e
    end
    applied[#applied + 1] = {crop = row.token, level = row.level}
  end
  local _, eerr = run('enable', 'autofarm')
  if eerr then
    return nil, "enable autofarm failed: " .. eerr
  end
  local status = run('autofarm', 'status')
  return {ok = true, default = default, crops = applied, enabled = true, status = status}
end

-- Same module-load guard as every other df-overseer-*.lua script.
if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

if cmd == "set" then
  if args[2] == nil then
    print("usage: df-overseer-autofarm set DEFAULT [TOKEN=N,TOKEN=N]")
  else
    local result, err = autofarm_set(args[2], args[3])
    print(json.encode(err and {error = err} or result))
  end
else
  print("usage: df-overseer-autofarm set DEFAULT [TOKEN=N,TOKEN=N]")
end
