local z
for _,u in ipairs(dfhack.units.getCitizens()) do if u.id and dfhack.units.getReadableName(u):find('Braidoils') then z=u end end
print('unit',z.id,'stress_cat',dfhack.units.getStressCategory(z),'mood',tostring(z.mood))
local j=z.job.current_job
if j then
 print('job id',j.id,'type',df.job_type[j.job_type],'timer',j.completion_timer,'pos_delta',j.pos.x-z.pos.x,j.pos.y-z.pos.y,j.pos.z-z.pos.z)
 print('flags', 'suspend',j.flags.suspend,'repeat',j.flags['repeat'],'do_now',j.flags.do_now,'working',j.flags.working,'bymgr',j.order_id, 'material_category',tostring(j.flags.special))
 print('unit path len',#z.path.path.x,'dest_delta',z.path.dest.x-z.pos.x,z.path.dest.y-z.pos.y,z.path.dest.z-z.pos.z)
 print('tick now',df.global.world.frame_counter,'cur_year_tick',df.global.cur_year_tick)
end
print('counters: sleepiness',z.counters2.sleepiness_timer,'hunger',z.counters2.hunger_timer,'thirst',z.counters2.thirst_timer,'exhaust',z.counters2.exhaustion)
-- dig jobs
local l=df.global.world.jobs.list.next local n=0
while l and n<3000 do local jj=l.item if df.job_type[jj.job_type]=='Dig' then print('DIG id',jj.id,'worker',dfhack.job.getWorker(jj) and dfhack.job.getWorker(jj).id or 'none','suspend',jj.flags.suspend,'delta_from_zuglar',jj.pos.x-z.pos.x,jj.pos.y-z.pos.y,jj.pos.z-z.pos.z) end l=l.next n=n+1 end
-- reports
local r=df.global.world.status.reports local c=0 local hits={}
for i=#r-1,math.max(0,#r-400),-1 do local t=r[i].text:lower() if t:find('cancel') or t:find('reach') or t:find('danger') or t:find('path') or t:find('interrupt') then c=c+1 if c<=15 then table.insert(hits,r[i].text) end end end
print('reports scanned',math.min(400,#r),'matches',c) for _,h in ipairs(hits) do print(' R:',dfhack.df2utf(h)) end
-- his recent history: last events mention name
