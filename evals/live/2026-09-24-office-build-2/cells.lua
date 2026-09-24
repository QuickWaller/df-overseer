local s=dfhack.persistent.getSiteData('df-overseer-blueprint_v1',{sites={}}).sites['site-2']
for r=0,4 do local line='' for c=0,4 do
 local x,y,z=s.x+c,s.y+r,s.z
 local tt=dfhack.maps.getTileType(x,y,z) local f=dfhack.maps.getTileFlags(x,y,z)
 local a=df.tiletype.attrs[tt]
 line=line..string.format('[%s/%s/%s/dig=%s] ',df.tiletype_shape[a.shape]:sub(1,5),df.tiletype_special[a.special]:sub(1,6),f.hidden and 'H' or 'v',df.tile_dig_designation[f.dig]:sub(1,4)) end print(r,line) end
