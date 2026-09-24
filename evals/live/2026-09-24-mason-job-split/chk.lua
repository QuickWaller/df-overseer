-- args: last_report_id
local last=tonumber(({...})[1]) or 0
local ok=false local holder='none'
local it=df.item.find(118)
if it then local h=dfhack.items.getHolderUnit(it) if h then holder=h.id ok=(h.id==192 and it.flags.in_inventory) end end
print('PICK',ok and 'OK' or 'BAD',holder)
local cnt={} local c0={} for _,u in ipairs(dfhack.units.getCitizens()) do local c=dfhack.units.getStressCategory(u) cnt[c]=(cnt[c] or 0)+1 if c==0 then table.insert(c0,u.id) end end
local s='' for c=0,6 do s=s..(cnt[c] or 0)..' ' end print('CATS',s) print('CAT0',#c0,table.concat(c0,','))
local r=df.global.world.status.reports local mx=0
for i=#r-1,math.max(0,#r-60),-1 do local x=r[i] if x.id>mx then mx=x.id end
 if x.id>last then local t=x.text:lower() if t:find('tantrum') or t:find('berserk') or t:find('insane') or t:find('melancholy') or t:find('attack') or t:find('killed') or t:find('hurt') or t:find('has died') or t:find('struck down') then if not (x.id==411) then print('REPORTBAD',x.id,dfhack.df2utf(x.text)) end end end end
print('MAXREPORT',mx)
