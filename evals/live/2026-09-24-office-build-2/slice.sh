#!/bin/bash
# usage: slice.sh TICKS ; ignores the known informational advisory tick 12614457
cd /c/website-projects/df-automation
V="bash scripts/vm-ssh.sh df"
C='cd /opt/df/game && ./dfhack-run df-overseer-clock'
gt() { echo "$1" | grep -o "\"$2\": [a-z0-9]*" | head -1 | grep -o '[a-z0-9]*$'; }
s=$($V "$C status"); start=$(gt "$s" abs_tick); echo "start $start"
$V "$C resume" | tr -d '\n\t'; echo
for i in $(seq 1 60); do
  sleep 3
  s=$($V "$C status"); t=$(gt "$s" abs_tick)
  if echo "$s" | grep -q tripwire; then echo ALERT-tripwire; break; fi
  if echo "$s" | grep -q '"advisory"' && ! echo "$s" | grep -q '"tick": 12614457'; then echo ALERT-new-advisory; break; fi
  [ "$(gt "$s" paused)" = true ] && { echo self-paused; break; }
  [ $((t-start)) -ge $1 ] && break
done
$V "$C pause" | tr -d '\n\t'; echo
$V "$C status; cd /opt/df/game; ./dfhack-run df-overseer-vitals summary" | grep -E 'abs_tick|paused|alive|dead_total"|worst|tripwire|"tick"|"reason"|"race"|"direction"|distance'
$V 'cd /opt/df/game && ./dfhack-run lua -f /tmp/jobs-census.lua' | tr -d '\r'
