for _,u in ipairs(dfhack.units.getCitizens()) do
  local pick=false
  for _,ii in ipairs(u.inventory) do if ii.item:getType()==df.item_type.WEAPON and ii.item.subtype.id=='ITEM_WEAPON_PICK' then pick=true end end
  local mine=u.status.labors[df.unit_labor.MINE]
  local j=u.job.current_job and df.job_type[u.job.current_job.job_type] or 'none'
  if pick or mine then print(dfhack.units.getReadableName(u), 'pick='..tostring(pick),'MINE='..tostring(mine),'job='..j) end
end
local n=0 for _,i in ipairs(df.global.world.items.other.WEAPON) do if i.subtype.id=='ITEM_WEAPON_PICK' then n=n+1 print('pick item',i.id,'inv',i.flags.in_inventory,'job',i.flags.in_job,'forbid',i.flags.forbid) end end
