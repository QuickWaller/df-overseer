local c={} local l=df.global.world.jobs.list.next
local n=0
while l and n<3000 do local j=l.item; local t=df.job_type[j.job_type]; local w=dfhack.job.getWorker(j) and 'W' or 'x'; c[t..w]=(c[t..w] or 0)+1; l=l.next; n=n+1 end
for k,v in pairs(c) do print(k,v) end
