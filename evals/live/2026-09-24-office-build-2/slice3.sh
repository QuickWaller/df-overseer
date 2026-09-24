#!/bin/bash
# usage: slice3.sh TICKS LASTREPORT. Auto stops: pick, cat0 >3 or unknown cat0 id, bad reports, death, new tripwire/advisory.
cd /c/website-projects/df-automation
V="bash scripts/vm-ssh.sh df"
C='cd /opt/df/game && ./dfhack-run df-overseer-clock'
gt() { echo "$1" | grep -o "\"$2\": [a-z0-9]*" | head -1 | grep -o '[a-z0-9]*$'; }
chk() { $V "cd /opt/df/game && ./dfhack-run lua -f /tmp/chk.lua $2; ./dfhack-run df-overseer-vitals summary" | tr -d '\r'; }
bad() { # $1 = chk output
  echo "$1" | grep -q 'PICK.*OK' || { echo ALERT-PICK; return 0; }
  echo "$1" | grep -q REPORTBAD && { echo ALERT-REPORT; return 0; }
  n=$(echo "$1" | grep '^.*CAT0' | grep -o 'CAT0	[0-9]*' | grep -o '[0-9]*$'); [ "${n:-0}" -gt 3 ] && { echo ALERT-CAT0-COUNT; return 0; }
  echo "$1" | grep 'CAT0' | grep -E '[,	]' | grep -o '[0-9,]*$' | tr ',' '\n' | grep -v -E '^(345|455)$' | grep -q . && { echo ALERT-CAT0-NEWID; return 0; }
  echo "$1" | grep -q '"alive": 22' || { echo ALERT-DEATH; return 0; }
  echo "$1" | grep -q '"dead_total": 1,' || { echo ALERT-DEATH; return 0; }
  return 1
}
o=$(chk x $2); bad "$o" && { echo "$o"; exit 2; }
s=$($V "$C status"); start=$(gt "$s" abs_tick); echo "start $start"
$V "$C resume" | tr -d '\n\t'; echo
for i in $(seq 1 100); do
  sleep 3
  s=$($V "$C status"); t=$(gt "$s" abs_tick)
  if echo "$s" | grep -q tripwire; then echo ALERT-tripwire; break; fi
  if echo "$s" | grep -q '"advisory"' && ! echo "$s" | grep -q 'BIRD_KEA'; then echo ALERT-advisory; break; fi
  o=$(chk x $2); a=$(bad "$o") && { echo "$a"; break; }
  [ "$(gt "$s" paused)" = true ] && { echo self-paused; break; }
  [ $((t-start)) -ge $1 ] && break
done
$V "$C pause" | tr -d '\n\t'; echo
$V "$C status" | grep -E 'abs_tick|paused'
o=$(chk x $2); echo "$o" | grep -E 'PICK|CATS|CAT0|REPORTBAD|MAXREPORT|alive|dead_total"|worst'
$V 'cd /opt/df/game && ./dfhack-run lua -f /tmp/jobs-census.lua' | tr -d '\r'
$V 'cd /opt/df/game && ./dfhack-run df-overseer-blueprint status site-2' | grep -E '"(pending_dig_designations|still_solid|smoothable|shell_done|finish_required_met)"'
