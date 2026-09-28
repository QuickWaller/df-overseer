#!/bin/bash
# Run a bounded, supervised unpause window on the live fort (VM 103), with
# the tripwire armed on defaults and a restore trap that always re-pauses
# and restores 100 FPS on exit, however the window ends.
#
# WHY THIS EXISTS AS ONE TRACKED SCRIPT, NOT A FRESH HEREDOC EACH TIME:
# the orchestrator rewrote this same window logic from scratch five or six
# times in one session (2026-09-25 through 2026-09-28) before this file
# existed. This is the "prefer reusable infra" lesson applied to itself.
#
# WHAT'S NEW HERE VS EARLIER AD-HOC VERSIONS: handling a fort pause that is
# NOT the tripwire. 2026-09-28 found the fort can self-pause on a vanilla,
# non-armok event (FORT_POSITION_SUCCESSION, a noble succession) that the
# announcement-level pause system does NOT control (`level` reads
# not_pause_or_slow for it) and the tripwire never latches for
# (`clock status`'s own `tripwire` key stays absent). See
# handoffs/2026-09-28-noble-succession-popup-research.md and
# decisions/DECISIONS.md 2026-09-16 for the related "undismissed popup" case
# (a different failure shape: pause_state could read false while the game
# was still genuinely frozen behind a modal, requiring a human click on
# VNC). The two cases look identical from `clock status` alone (paused:
# true, no tripwire key), so this script tells them apart THE ONLY SAFE WAY:
# try `resume` once, then verify the tick actually advances. If it does,
# this was the harmless self-pause case -- keep going. If it does not
# (or `clock status` itself disagrees), STOP and report; never assume a
# resume "worked" without checking the tick moved, and never retry the
# resume-and-check more than once per pause (a genuinely stuck viewscreen
# would just eat time in a loop otherwise, and a human should look at it).
#
# THIS LOGIC MUST NEVER MOVE INTO conductor.service. A real tripwire pause
# and this self-pause case are told apart only by the `tripwire` key being
# absent -- that check is load-bearing. This script only ever runs under a
# live, supervised orchestrator session (a human + Claude actively watching
# the run), which is a structurally different trust boundary from the
# autonomous conductor loop; agents/conductor/role.md's "never unpause
# without being asked to" is a charter guarantee for the unattended loop
# and this script does not weaken it.
#
# Usage: scripts/supervised-unpause.sh [FPS] [DURATION_SECONDS] [POLL_SECONDS]
#   FPS              think-speed frame cap during the window (default 10)
#   DURATION_SECONDS total wall-clock budget (default 600)
#   POLL_SECONDS     how often to poll clock status (default 15)
#
# Run this ON the fort VM (via scripts/vm-ssh.sh df --copy, then
# scripts/vm-ssh.sh df 'bash supervised-unpause.sh ...'), not on the
# workstation -- it calls the local dfhack-run binary directly.

set -u

R=/opt/df/game/dfhack-run
FPS="${1:-10}"
DURATION="${2:-600}"
POLL="${3:-15}"

strip() { sed 's/\x1b\[[0-9;]*m//g' | tr -d '\n\t'; }

clock_status() { $R df-overseer-clock status | strip; }
cur_tick() { clock_status | sed -n 's/.*"cur_year_tick": \([0-9]*\).*/\1/p'; }
vitals() { $R df-overseer-vitals summary | strip; }
alive_count() { vitals | sed -n 's/.*"alive": \([0-9]*\).*/\1/p'; }
warning_count() { vitals | sed -n 's/.*"warning_count": \([0-9]*\).*/\1/p'; }

trap '
  echo
  echo "TRAP: pause, clear, re-arm defaults, restore fps 100"
  $R df-overseer-clock pause | strip; echo
  $R df-overseer-clock clear | strip; echo
  $R df-overseer-clock arm | strip; echo
  $R df-overseer-clock set-speed 100 | strip; echo
' EXIT

echo "== before"; clock_status; echo
ALIVE_START=$(alive_count)
echo "alive at window start: ${ALIVE_START:-unknown}"
$R df-overseer-clock set-speed "$FPS" | strip; echo
$R df-overseer-clock resume | strip; echo

END=$((SECONDS + DURATION))
SELF_PAUSE_RETRIED=0

while [ "$SECONDS" -lt "$END" ]; do
  sleep "$POLL"
  C=$(clock_status)
  V=$(vitals)
  echo "t=$SECONDS $C" | cut -c1-260
  echo "$V" | grep -o -E '"alive": [0-9]+|"warning_count": [0-9]+|"worst_[a-z]+_status": "[a-z]+"' | tr '\n' ' '; echo

  ALIVE_NOW=$(echo "$V" | sed -n 's/.*"alive": \([0-9]*\).*/\1/p')
  if [ -n "$ALIVE_START" ] && [ -n "$ALIVE_NOW" ] && [ "$ALIVE_NOW" -lt "$ALIVE_START" ]; then
    echo "STOP: alive count dropped ($ALIVE_START -> $ALIVE_NOW) -- a death, re-pausing"
    break
  fi

  if echo "$C" | grep -q '"paused": true'; then
    if echo "$C" | grep -q '"tripwire"'; then
      echo "STOP: tripwire latched"
      echo "$C"
      break
    fi

    if [ "$SELF_PAUSE_RETRIED" -eq 1 ]; then
      echo "STOP: paused again with no tripwire after already trying one resume-and-verify this window -- do not loop, this needs a human"
      break
    fi

    echo "-- unexplained pause, no tripwire latched: trying one resume-and-verify (2026-09-28 finding)"
    TICK_BEFORE=$(cur_tick)
    $R df-overseer-clock resume | strip; echo
    sleep 5
    TICK_AFTER=$(cur_tick)
    SELF_PAUSE_RETRIED=1

    if [ -n "$TICK_BEFORE" ] && [ -n "$TICK_AFTER" ] && [ "$TICK_AFTER" -gt "$TICK_BEFORE" ]; then
      echo "-- confirmed: tick advanced ($TICK_BEFORE -> $TICK_AFTER), this was a harmless self-pause, continuing"
    else
      echo "STOP: resumed but tick did not advance ($TICK_BEFORE -> $TICK_AFTER) -- this looks like the 2026-09-16 stuck-viewscreen pattern, not the clean flip. Needs a human on VNC, not another automated retry."
      break
    fi
  fi
done

echo "== window over"
