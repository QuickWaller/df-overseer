local n=0
for _,b in ipairs(df.global.world.map.map_blocks) do
  for x=0,15 do for y=0,15 do if b.designation[x][y].dig ~= 0 then n=n+1 end end end
end
print('pending_dig_designations', n)
