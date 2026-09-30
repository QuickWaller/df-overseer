local bp = require('plugins.buildingplan')
local t, s, c = df.building_type.Construction, df.construction_type.Wall, -1
print('construction_type.Wall =', s, ' reverse:', df.construction_type[s])
print('0:243 toString =', dfhack.matinfo.decode(0,243):toString(), ' 0:182 =', dfhack.matinfo.decode(0,182):toString())
local function enabled(idx)
  local n, list = 0, {}
  for name, p in pairs(bp.getMaterialFilter(t, s, c, idx)) do if p.enabled == "true" then n = n + 1; if #list < 5 then list[#list+1] = name end end end
  return n, table.concat(list, ', ')
end
local before_n = enabled(0)
local total = 0; for _ in pairs(bp.getMaterialFilter(t, s, c, 0)) do total = total + 1 end
print('before: enabled', before_n, 'of', total)
bp.setMaterialFilter(t, s, c, 0, {'WOOD', 'material_0_243'})
print('after our names: enabled', enabled(0))
bp.setMaterialFilter(t, s, c, 0, {dfhack.matinfo.decode(0,243):toString()})
print('after real name:', enabled(0))
bp.setMaterialFilter(t, s, c, 0, {})
print('restored: enabled', enabled(0), 'of', total)
