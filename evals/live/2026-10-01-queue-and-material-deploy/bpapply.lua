local b = reqscript('df-overseer-building')
local bp = require('plugins.buildingplan')
local t, s, c = df.building_type.Construction, df.construction_type.Wall, -1
local function count()
  local n, tot, hem = 0, 0, false
  for name, p in pairs(bp.getMaterialFilter(t, s, c, 0)) do
    tot = tot + 1
    if p.enabled == 'true' then n = n + 1; if name == 'hematite' or name == 'adamantine' then hem = true end end
  end
  return n, tot, hem
end
print('before', count())
local req = b.building_filters_and_gaps(t, s, c, '', 'Wall')
local recs = req.filters or (req.building_material and req.building_material.filters) or req
local report, restore = b.apply_material_filters(t, s, c, recs)
for _, a in ipairs(report.applied or {}) do
  print('applied index', a.index, 'ok', a.ok, 'enabled_count', a.enabled_count, 'economic_enabled', a.economic_enabled, 'error', a.error)
end
print('during', count())
restore()
print('after restore', count())
