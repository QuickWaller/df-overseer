-- args: last_report_id . read-only. order states, jobs with order_id, worker census, manager-ish reports
local last=tonumber(({...})[1]) or 0
local mo=df.global.world.manager_orders.all
for i=0,#mo-1 do local o=mo[i]
 print('ORDER',o.id,df.job_type[o.job_type],o.reaction_name or '', 'validated',tostring(o.status.validated),'active',tostring(o.status.active),'left',o.amount_left,'/',o.amount_total,'ic',#o.item_conditions,'oc',#o.order_conditions,'ws',o.workshop_id,'maxws',o.max_workshops)
end
local c={} local l=df.global.world.jobs.list.next local n=0
while l and n<3000 do local j=l.item local t=df.job_type[j.job_type]
 local w=dfhack.job.getWorker(j)
 c[t..(w and 'W' or 'x')]=(c[t..(w and 'W' or 'x')] or 0)+1
 if j.order_id and j.order_id>=0 then print('ORDERJOB',t,'order_id',j.order_id,'job',j.id,'worker',w and w.id or 'none',w and dfhack.units.getReadableName(w) or '') end
 l=l.next n=n+1 end
local s='' for k,v in pairs(c) do s=s..k..'='..v..' ' end print('JOBS',s,'total',n)
local m=df.unit.find(345) if m then local j=m.job.current_job print('MGR345',j and df.job_type[j.job_type] or 'nojob', 'stress',dfhack.units.getStressCategory(m)) end
local r=df.global.world.status.reports
for i=#r-1,math.max(0,#r-80),-1 do local x=r[i] if x.id>last then local t=x.text:lower() if t:find('manager') or t:find('mandate') or t:find('order') or t:find('work order') then print('REPORT',x.id,dfhack.df2utf(x.text)) end end end
local best=999
for _,u in ipairs(df.global.world.units.active) do
 if dfhack.units.isAlive(u) and not dfhack.units.isCitizen(u) and (u.flags1.inactive==false) then
  local rn=df.creature_raw.find(u.race).creature_id
  if rn:find('KEA') then
   for _,d in ipairs(dfhack.units.getCitizens()) do if d.pos.z==u.pos.z then local dd=math.max(math.abs(d.pos.x-u.pos.x),math.abs(d.pos.y-u.pos.y)) if dd<best then best=dd end end end
  end end end
print('KEASAMEZ',best)
