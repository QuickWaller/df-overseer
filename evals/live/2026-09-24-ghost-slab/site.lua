for _,b in ipairs(df.global.world.buildings.all) do
  local t=df.building_type[b:getType()]
  if t=='Civzone' or (b.name and b.name:find('Stoneworker')) or t=='Workshop' then
    local name = b.name or (b.getName and b:getName()) or ''
    print(t, b.id, 'x',b.x1,b.x2,'y',b.y1,b.y2,'z',b.z, 'ok', pcall(function() return b:getName() end) and b:getName() or name)
  end
end
