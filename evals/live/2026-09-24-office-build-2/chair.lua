local s=dfhack.persistent.getSiteData('df-overseer-blueprint_v1',{sites={}}).sites['site-2']
local it=df.item.find(3946)
if it then local h=dfhack.items.getHolderUnit(it) local b=dfhack.items.getHolderBuilding(it)
 print('ITEM3946','forbid',it.flags.forbid,'in_job',it.flags.in_job,'in_bld',it.flags.in_building,'unit',h and h.id or 'none','bld',b and b.id or 'none','on_ground',it.flags.on_ground,'in_stockpile?',dfhack.items.getGeneralRef(it,df.general_ref_type.BUILDING_HOLDER)~=nil)
else print('ITEM3946 missing (consumed?)') end
local z=df.building.find(13)
for _,b in ipairs(df.global.world.buildings.other.CHAIR) do
 local inside=b.x1>=s.x and b.x1<s.x+5 and b.y1>=s.y and b.y1<s.y+5 and b.z==s.z
 local inz= z and b.x1>=z.x1 and b.x1<=z.x2 and b.y1>=z.y1 and b.y1<=z.y2 and b.z==z.z
 print('CHAIRBLD',b.id,'stage',b:getBuildStage(),'/',b:getMaxBuildStage(),'in_footprint',inside,'in_zone13',inz,'contained',#b.contained_items,'jobs',#b.jobs)
end
if z then local ok,d=pcall(dfhack.buildings.getRoomDescription,z,nil) print('ROOMDESC',ok,'['..tostring(d)..']', 'zone13 size',(z.x2-z.x1+1)..'x'..(z.y2-z.y1+1)) end
