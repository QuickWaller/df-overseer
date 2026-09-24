local ok=false local holder='none'
local it=df.item.find(118)
if it then local inv=dfhack.items.getHolderUnit(it) if inv then holder=inv.id..' '..dfhack.units.getReadableName(inv) ; ok=(inv.id==192 and it.flags.in_inventory) end else holder='item-missing' end
print('PICK',ok and 'OK' or 'BAD',holder)
local cnt={} local mn=99 for _,u in ipairs(dfhack.units.getCitizens()) do local c=dfhack.units.getStressCategory(u) cnt[c]=(cnt[c] or 0)+1 if c<mn then mn=c end end
local s='' for c=0,6 do s=s..c..':'..(cnt[c] or 0)..' ' end print('STRESS',s)
local n=0 for _,u in ipairs(dfhack.units.getCitizens()) do if u.mood>=0 then n=n+1 end end print('MOOD',n)
