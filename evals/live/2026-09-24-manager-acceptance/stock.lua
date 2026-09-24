-- read-only bounded stock counts relevant to the orders
local function cnt(vec,pred) local n,f=0,0 for _,it in ipairs(vec) do local fl=it.flags if not (fl.garbage_collect or fl.removed or fl.trader or fl.hostile) then if pred(it) then n=n+1 end end end return n end
local o=df.global.world.items.other
local function free(it) return not it.flags.forbid and not it.flags.in_job and not it.flags.dump end
print('BOULDER total',#o.BOULDER,'free',cnt(o.BOULDER,free))
print('BLOCKS total',#o.BLOCKS,'free',cnt(o.BLOCKS,free))
print('TRAPPARTS total',#o.TRAPPARTS,'free',cnt(o.TRAPPARTS,free))
print('BARREL total',#o.BARREL,'free',cnt(o.BARREL,free))
print('PLANT total',#o.PLANT,'free',cnt(o.PLANT,free))
print('DRINK total',#o.DRINK)
print('BAR/other n/a')
-- workshops
for _,b in ipairs(df.global.world.buildings.other.WORKSHOP_ANY) do print('WS',b.id,df.workshop_type[b.type],'stage',b:getBuildStage(),'/',b:getMaxBuildStage(),'jobs',#b.jobs) end
-- mason/mechanic/still labor: workers with the labors
local labs={'MASONRY','MECHANIC','BREWING','STONE_CRAFT'}
for _,lb in ipairs(labs) do local k=0 for _,u in ipairs(dfhack.units.getCitizens()) do if u.status.labors[df.unit_labor[lb]] then k=k+1 end end print('LABOR',lb,k) end
