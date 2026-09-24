local l=df.global.world.jobs.list.next while l do local j=l.item if df.job_type[j.job_type]=='ConstructThrone' then local w=dfhack.job.getWorker(j) print('throne job',j.id,'worker',w and dfhack.units.getReadableName(w) or 'none') end l=l.next end
local n=0 for _,i in ipairs(df.global.world.items.other.CHAIR) do n=n+1 end print('CHAIR items',n)
