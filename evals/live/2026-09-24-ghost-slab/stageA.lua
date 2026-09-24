-- read-only stage A survey
local function nm(u) return dfhack.df2utf(dfhack.units.getReadableName(u)) end
local n=0
for _,u in ipairs(df.global.world.units.all) do
  if u.flags3.ghostly then
    n=n+1
    local gi=u.ghost_info
    print('GHOST',u.id,nm(u),'dead',tostring(dfhack.units.isDead(u)),'ghost_info',gi and 'present' or 'nil')
    if gi then
      print('  type',gi.type,'name',({[0]='Murderous','Sadistic','Secretive','Energetic poltergeist','Angry','Violent','Moaning spirit','Howling spirit','Troublesome poltergeist','Restless haunt','Forlorn haunt'})[gi.type])
      pcall(function() print('  state',gi.state) end)
      pcall(function() print('  target',gi.target and gi.target.id, 'flags',gi.flags) end)
      print('  z_rel_to_fort_center', u.pos.z)
    end
  end
end
print('GHOSTCOUNT',n)
-- body
for _,u in ipairs(df.global.world.units.all) do
  if dfhack.df2utf(dfhack.units.getReadableName(u)):find('Kadol Zulbanurdim') then
    print('NAMED',u.id,'ghostly',tostring(u.flags3.ghostly),'dead',tostring(dfhack.units.isDead(u)),'flags2.slaughter',tostring(u.flags2.slaughter),'killed',tostring(u.flags2.killed),'body.missing?',tostring(u.flags3.body_temp_in_range))
    pcall(function() print('  corpse_flags: dead',u.flags1.inactive) end)
    local hfid=u.hist_figure_id print('  hfid',hfid)
  end
end
for _,it in ipairs(df.global.world.items.other.CORPSE) do
  local ok,unit=pcall(function() return df.unit.find(it.unit_id) end)
  if ok and unit and dfhack.df2utf(dfhack.units.getReadableName(unit)):find('Kadol') then
    print('CORPSE item',it.id,'z',it.pos.z,'onground',tostring(it.flags.on_ground),'inbuilding',tostring(dfhack.items.getHolderBuilding(it)~=nil),'forbid',tostring(it.flags.forbid),'dump',tostring(it.flags.dump),'inv',tostring(it.flags.in_inventory))
    local ok2,t=pcall(function() return dfhack.maps.getTileBlock(it.pos) and dfhack.maps.getTileBlock(it.pos).designation[it.pos.x%16][it.pos.y%16].hidden end)
  end
end
-- buildings
local bc={}
for _,b in ipairs(df.global.world.buildings.all) do
  local t=df.building_type[b:getType()]
  if t=='Coffin' or t=='Slab' or t=='Workshop' then bc[t]=(bc[t] or 0)+1 end
end
for k,v in pairs(bc) do print('BLD',k,v) end
-- slab items
local sl=0 for _,it in ipairs(df.global.world.items.other.SLAB) do sl=sl+1 print('SLABITEM',it.id,'engr',#it.general_refs) end print('SLABS',sl)
-- engraver labor
for _,u in ipairs(dfhack.units.getCitizens()) do
  if u.status.labors.ENGRAVER then
    local sk=dfhack.units.getNominalSkill(u,df.job_skill.ENGRAVE_STONE,true)
    local j=u.job.current_job
    print('ENGRAVER',u.id,nm(u),'skill',sk,'job',j and df.job_type[j.job_type] or 'none')
  end
end
local c=0 for _,u in ipairs(dfhack.units.getCitizens()) do c=c+1 end print('CITIZENS',c)
-- job 2419
local l=df.global.world.jobs.list.next
while l do local j=l.item if j.id==2419 then local w=dfhack.job.getWorker(j) print('JOB2419',df.job_type[j.job_type],'worker',w and w.id or 'none','timer',j.completion_timer,'working',tostring(j.flags.working)) end l=l.next end
print('BOULDERS',#df.global.world.items.other.BOULDER)
print('PICK',dfhack.items.getHolderUnit(df.item.find(118)) and dfhack.items.getHolderUnit(df.item.find(118)).id)
local m=0 for _,u in ipairs(dfhack.units.getCitizens()) do if u.status.labors.MASON then m=m+1 end end print('MASONS_ENABLED',m)
print('CORPSE_EXTRA')
local c=df.item.find(2804) print('corpse item','pos z',c.pos.z,'flags.dead?') 
