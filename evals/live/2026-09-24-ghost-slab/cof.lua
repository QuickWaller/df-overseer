local last=tonumber(({...})[1]) or 0
local l=df.global.world.jobs.list.next local n=0
while l and n<3000 do local j=l.item local t=df.job_type[j.job_type]
 if t=='ConstructCoffin' or t=='ConstructBlocks' or t=='InterCorpse' or t=='PlaceItemInTomb' or t=='StoreItemInBuilding' and false then
  local w=dfhack.job.getWorker(j) print('JOB',t,j.id,'worker',w and w.id or 'none','timer',j.completion_timer,'working',tostring(j.flags.working)) end
 if t=='InterCorpse' or t=='ConstructBuilding' then local w=dfhack.job.getWorker(j) print('JOB',t,j.id,'worker',w and w.id or 'none') end
 l=l.next n=n+1 end
local ci=0 for _,i in ipairs(df.global.world.items.other.COFFIN) do ci=ci+1 print('COFFINITEM',i.id,'inbld',tostring(dfhack.items.getHolderBuilding(i)~=nil),'ongr',tostring(i.flags.on_ground)) end
print('COFFINITEMS',ci)
for _,b in ipairs(df.global.world.buildings.all) do if df.building_type[b:getType()]=='Coffin' then print('COFFINBLD',b.id,'stage',b.construction_stage,'exists',tostring(b.flags.exists),'contained',#b.contained_items) end end
local c=df.item.find(2804)
if c then local hb=dfhack.items.getHolderBuilding(c) print('CORPSE',c.id,'ongr',tostring(c.flags.on_ground),'inbld',tostring(hb~=nil),'inv',tostring(c.flags.in_inventory),'injob',tostring(c.flags.in_job),'hidden',tostring(c.flags.hidden)) else print('CORPSE gone') end
local g=df.unit.find(454) if g then print('GHOST',tostring(g.flags3.ghostly),'type',g.ghost_info and g.ghost_info.type,'active',tostring(not g.flags1.inactive)) else print('GHOST gone') end
local r=df.global.world.status.reports
for i=#r-1,math.max(0,#r-40),-1 do local x=r[i] if x.id>last then local t=x.text:lower() if t:find('ghost') or t:find('haunt') or t:find('bur') or t:find('coffin') or t:find('tomb') or t:find('cancel') or t:find('spirit') then print('REPORT',x.id,dfhack.df2utf(x.text)) end end end
local best=999
for _,u in ipairs(df.global.world.units.active) do
 if dfhack.units.isAlive(u) and not dfhack.units.isCitizen(u) and (u.flags1.inactive==false) then
  local rn=df.creature_raw.find(u.race).creature_id
  if rn:find('KEA') then for _,d in ipairs(dfhack.units.getCitizens()) do if d.pos.z==u.pos.z then local dd=math.max(math.abs(d.pos.x-u.pos.x),math.abs(d.pos.y-u.pos.y)) if dd<best then best=dd end end end end end end
print('KEASAMEZ',best)
