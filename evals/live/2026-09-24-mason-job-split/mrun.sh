#!/bin/bash
# remote: runto.sh TARGET_ABS_TICK LASTREPORT ; polls fast, self-checks, pauses at target
cd /opt/df/game
C="./dfhack-run df-overseer-clock"
tick() { ./dfhack-run lua 'print(df.global.cur_year*403200+df.global.cur_year_tick)' | tr -d '\r[0m' | grep -o '[0-9]*' | tail -1; }
bad() {
  echo "$1" | grep -q 'PICK.*OK' || { echo ALERT-PICK; return 0; }
  echo "$1" | grep -q REPORTBAD && { echo ALERT-REPORT; return 0; }
  echo "$1" | grep -q '^ORDERJOB' && { echo EVENT-ORDERJOB; return 0; }
  echo "$1" | grep -q '^REPORT' && { echo EVENT-REPORT-TEXT; return 0; }
  echo "$1" | grep -E '^ORDER' | grep -q 'active.true' && { echo EVENT-ORDER-ACTIVE; return 0; }
  echo "$1" | grep -E '^ORDER' | grep -v 'left.1.\/.1\|left.8.\/.8' | grep -q . && { echo EVENT-ORDER-CHANGED; return 0; }
  k=$(echo "$1" | grep KEASAMEZ | awk '{print $2}'); [ "${k:-999}" -le 8 ] && { echo ALERT-KEA-NEAR; return 0; }
  n=$(echo "$1" | grep 'CAT0' | awk '{print $2}'); [ "${n:-0}" -gt 3 ] && { echo ALERT-CAT0-COUNT; return 0; }
  echo "$1" | grep 'CAT0' | awk '{print $3}' | tr ',' '\n' | grep -v -E '^(345|455|)$' | grep -q . && { echo ALERT-CAT0-NEWID; return 0; }
  echo "$1" | grep -q '"alive": 22' || { echo ALERT-DEATH; return 0; }
  echo "$1" | grep -q '"dead_total": 1,' || { echo ALERT-DEATH; return 0; }
  return 1
}
chk() { ./dfhack-run lua -f /tmp/chk.lua $LAST; ./dfhack-run df-overseer-vitals summary; ./dfhack-run lua -f /tmp/ordscan.lua $LAST; }
LAST=$2
o=$(chk); a=$(bad "$o") && { echo "$a"; echo "$o"; exit 2; }
r=$($C resume); echo "$r" | grep -q '"ok": true' || { echo "resume refused: $r"; exit 3; }
while true; do
  sleep 1
  t=$(tick); [ "${t:-0}" -ge "$1" ] && break
  s=$($C status)
  echo "$s" | grep -q tripwire && { echo ALERT-tripwire; break; }
  echo "$s" | grep -q '"advisory"' && ! echo "$s" | grep -q BIRD_KEA && { echo ALERT-advisory; break; }
  echo "$s" | grep -q '"paused": true' && { echo self-paused; break; }
  o=$(chk); a=$(bad "$o") && { echo "$a"; break; }
done
$C pause | tr -d '\n\t'; echo
echo "final tick $(tick)"
chk | grep -E 'PICK|CATS|CAT0|REPORTBAD|alive|dead_total"|worst|ORDER|JOBS|MGR|REPORT|KEA'
