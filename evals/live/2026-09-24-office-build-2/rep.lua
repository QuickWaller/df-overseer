local r=df.global.world.status.reports for i=#r-1,math.max(0,#r-6),-1 do print(r[i].id,df.announcement_type[r[i].type],dfhack.df2utf(r[i].text)) end
