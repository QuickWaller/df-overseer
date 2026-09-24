for _,u in ipairs(dfhack.units.getCitizens()) do local j=u.job.current_job
 if u.id and (u.job.current_job and (df.job_type[j.job_type]=='Dig' or df.job_type[j.job_type]=='SmoothWall' or df.job_type[j.job_type]=='Sleep') ) then print(dfhack.units.getReadableName(u), df.job_type[j.job_type]) end end
