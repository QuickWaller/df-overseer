-- args: last_report_id. read-only. the direct blocks job, orders, order_id jobs, manager job, blocks count
local last=tonumber(({...})[1]) or 0
local mo=df.global.world.manager_orders.all
for i=0,#mo-1 do local o=mo[i] print('ORDER',o.id,'v',tostring(o.status.validated),'a',tostring(o.status.active),'left',o.amount_left,'/',o.amount_total) end
local l=df.global.world.jobs.list.next local n=0 local found=0
while l and n<3000 do local j=l.item local t=df.job_type[j.job_type]
 local w=dfhack.job.getWorker(j)
 if j.order_id and j.order_id>=0 then print('ORDERJOB',t,j.order_id,j.id) end
 if t=='ConstructBlocks' then found=found+1 local hb=dfhack.job.getHolder(j)
  print('MJOB',j.id,'worker',w and w.id or 'none',w and dfhack.units.getReadableName(w) or '','ws',hb and hb.id or 'none','susp',tostring(j.flags.suspend),'working',tostring(j.flags.working),'timer',j.completion_timer,'items',#j.items) end
 l=l.next n=n+1 end
print('MJOBS',found,'total',n)
local m=df.unit.find(345) if m then local j=m.job.current_job print('MGR345',j and df.job_type[j.job_type] or 'nojob') end
local b=0 local bf=0 for _,i in ipairs(df.global.world.items.other.BLOCKS) do b=b+1 end
local bo=0 for _,i in ipairs(df.global.world.items.other.BOULDER) do bo=bo+1 end
print('BLOCKS',b,'BOULDERS',bo)
local r=df.global.world.status.reports
for i=#r-1,math.max(0,#r-40),-1 do local x=r[i] if x.id>last then local t=x.text:lower() if t:find('manager') or t:find('mandate') or t:find('block') or t:find('cancel') then print('REPORT',x.id,dfhack.df2utf(x.text)) end end end
local best=999
for _,u in ipairs(df.global.world.units.active) do
 if dfhack.units.isAlive(u) and not dfhack.units.isCitizen(u) and (u.flags1.inactive==false) then
  local rn=df.creature_raw.find(u.race).creature_id
  if rn:find('KEA') then for _,d in ipairs(dfhack.units.getCitizens()) do if d.pos.z==u.pos.z then local dd=math.max(math.abs(d.pos.x-u.pos.x),math.abs(d.pos.y-u.pos.y)) if dd<best then best=dd end end end end end end
print('KEASAMEZ',best)
