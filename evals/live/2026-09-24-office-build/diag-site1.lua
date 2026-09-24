local s=dfhack.persistent.getSiteData('df-overseer-blueprint_v1',{sites={}}).sites['site-1']
for r=0,4 do for c=0,4 do
 local x,y,z=s.x+c,s.y+r,s.z
 local tt=dfhack.maps.getTileType(x,y,z)
 local d=dfhack.maps.getTileFlags(x,y,z)
 local sh=tt and df.tiletype.attrs[tt].shape
 local nb=0
 for _,o in ipairs({{1,0},{-1,0},{0,1},{0,-1}}) do
   local t2=dfhack.maps.getTileType(x+o[1],y+o[2],z)
   if t2 and df.tiletype_shape.attrs[df.tiletype.attrs[t2].shape].walkable then nb=nb+1 end
 end
 print(c,r,'shape',df.tiletype_shape[sh],'hidden',d and d.hidden,'dig',d and df.tile_dig_designation[d.dig],'walkable_nbrs',nb, 'wg', dfhack.maps.getWalkableGroup(xyz2pos(x,y,z)))
end end
