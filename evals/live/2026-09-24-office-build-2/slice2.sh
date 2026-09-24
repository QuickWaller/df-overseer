#!/bin/bash
# usage: slice2.sh TICKS. Acknowledged: tripwire report 411 (ghost), kea advisories.
cd /c/website-projects/df-automation
V="bash scripts/vm-ssh.sh df"
C='cd /opt/df/game && ./dfhack-run df-overseer-clock'
gt() { echo "$1" | grep -o "\"$2\": [a-z0-9]*" | head -1 | grep -o '[a-z0-9]*$'; }
pre=$($V 'cd /opt/df/game && ./dfhack-run lua -f /tmp/pre.lua' | tr -d '\r'); echo "$pre" | grep -q 'PICK.*OK' || { echo "PICK-BAD before slice"; echo "$pre"; exit 2; }
base=$(echo "$pre" | grep STRESS)
s=$($V "$C status"); start=$(gt "$s" abs_tick); echo "start $start"
$V "$C resume" | tr -d '\n\t'; echo
for i in $(seq 1 80); do
  sleep 3
  s=$($V "$C status"); t=$(gt "$s" abs_tick)
  if echo "$s" | grep -q tripwire && ! echo "$s" | grep -q '"report_id": 411'; then echo ALERT-tripwire; break; fi
  if echo "$s" | grep -q '"advisory"' && ! echo "$s" | grep -q 'BIRD_KEA'; then echo ALERT-advisory; break; fi
  p=$($V 'cd /opt/df/game && ./dfhack-run lua -f /tmp/pre.lua' | tr -d '\r'); echo "$p" | grep -q 'PICK.*OK' || { echo ALERT-PICK; break; }
  [ "$(gt "$s" paused)" = true ] && { echo self-paused; break; }
  [ $((t-start)) -ge $1 ] && break
done
$V "$C pause" | tr -d '\n\t'; echo
$V "$C status; cd /opt/df/game; ./dfhack-run df-overseer-vitals summary; ./dfhack-run lua -f /tmp/pre.lua" | tr -d '\r' | grep -E 'abs_tick|paused|alive|dead_total"|worst|report_id|PICK|STRESS'
echo "BASE $base"
$V 'cd /opt/df/game && ./dfhack-run lua -f /tmp/jobs-census.lua' | tr -d '\r'
$V 'cd /opt/df/game && ./dfhack-run df-overseer-blueprint status site-2' | grep -E '"(pending_dig_designations|still_solid|smoothable|shell_done|finish_required_met)"'
