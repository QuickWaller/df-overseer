local l=df.global.world.jobs.list.next local found=false
while l do local j=l.item if df.job_type[j.job_type]=='ConstructThrone' then found=true local w=dfhack.job.getWorker(j)
 local bld=dfhack.job.getHolder(j)
 local d='n/a' if w and bld then d=math.max(math.abs(w.pos.x-(bld.x1+bld.x2)//2),math.abs(w.pos.y-(bld.y1+bld.y2)//2))..' z'..(w.pos.z-bld.z) end
 print('THRONE job',j.id,'worker',w and w.id..' '..dfhack.units.getReadableName(w) or 'none','dist_to_workshop',d,'suspend',j.flags.suspend,'items',#j.items,'job_items',#j.job_items.elements,'timer',j.completion_timer,'working',j.flags.working) end l=l.next end
if not found then print('THRONE job absent') end
for _,i in ipairs(df.global.world.items.other.CHAIR) do
 local ref='' for _,r in ipairs(i.general_refs) do ref=ref..df.general_ref_type[r:getType()]..' ' end
 print('CHAIR item',i.id,'type',i:getType(),'forbid',i.flags.forbid,'in_bld',i.flags.in_building,'in_job',i.flags.in_job,'refs',ref,'mat',dfhack.matinfo.decode(i):getToken())
 local b=dfhack.items.getHolderBuilding and dfhack.items.getHolderBuilding(i) print('  holder bld',b and b.id or 'none') end
local b=df.building.find(9)
if b then print('BLD9',df.building_type[b:getType()],'stage',b:getBuildStage(),'max',b:getMaxBuildStage(),'contained',#b.contained_items,'jobs',#b.jobs)
 for _,j in ipairs(b.jobs) do print(' job',j.id,df.job_type[j.job_type],'suspend',j.flags.suspend,'jobitems',#j.job_items.elements,'items',#j.items) end
 local ok,bp=pcall(require,'plugins.buildingplan')
 if ok then print(' planned',pcall(bp.isPlannedBuilding,b)); for k=0,3 do local o,s=pcall(bp.getDescString,b,k) print(' desc',k,o,s) end
  local o,f=pcall(bp.getGlobalSettings) end
else print('BLD9 missing') end
