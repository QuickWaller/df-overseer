#!/bin/bash
# usage: win.sh TARGET_TICKS
cd /c/website-projects/df-automation
V="bash scripts/vm-ssh.sh df"
tick() { $V 'cd /opt/df/game && ./dfhack-run df-overseer-clock status' | tr -d '\n\t' ; }
st=$($V 'cd /opt/df/game && ./dfhack-run df-overseer-clock status')
start=$(echo "$st" | grep -o '"abs_tick": [0-9]*' | grep -o '[0-9]*$')
echo "start $start"
$V 'cd /opt/df/game && ./dfhack-run df-overseer-clock resume' | tr -d '\n\t'; echo
for i in $(seq 1 40); do
  sleep 3
  s=$($V 'cd /opt/df/game && ./dfhack-run df-overseer-clock status')
  t=$(echo "$s" | grep -o '"abs_tick": [0-9]*' | grep -o '[0-9]*$')
  p=$(echo "$s" | grep -o '"paused": [a-z]*' | grep -o '[a-z]*$')
  if echo "$s" | grep -q 'tripwire\|advisory'; then echo "ALERT"; echo "$s"; break; fi
  if [ "$p" = "true" ]; then echo "self-paused"; break; fi
  if [ $((t-start)) -ge $1 ]; then break; fi
done
$V 'cd /opt/df/game && ./dfhack-run df-overseer-clock pause' | tr -d '\n\t'; echo
$V 'cd /opt/df/game && ./dfhack-run df-overseer-clock status; ./dfhack-run df-overseer-vitals summary' | grep -E 'abs_tick|paused|alive|dead_total"|worst|tripwire|advisory|reason'
