#!/usr/bin/env bash
# Idle canary for the openclaw Gateway on VM 106 (research/2026-10-09-gateway-sessions-v1.md 9.1, S0).
#
# Proves the Gateway starts no agent turn on its own: since the canary start
# time there must be ZERO model calls, ZERO agent runs, ZERO new sessions and
# ZERO enabled cron jobs. Read-only; run on VM 106 as the df user:
#
#   scripts/ops/gateway_idle_canary.sh start    # record "now" as the canary start (once, after the last restart)
#   scripts/ops/gateway_idle_canary.sh check    # PASS/FAIL report, exit 1 on FAIL
#
# Any conductor-opened or hand-run turn after `start` makes it FAIL by design:
# run no turns during the canary. The matching dfmcp-side check (role tool calls
# in the dfmcp journal since the same instant) is printed as a command at the end
# because dfmcp lives on another host.
set -u
STATE=/var/lib/openclaw-gateway/canary-start
UNIT=openclaw-gateway.service
GWC=/home/df/gwc.sh

case "${1:-check}" in
  start)
    date -u +%Y-%m-%dT%H:%M:%SZ > "$STATE"
    echo "canary started at $(cat "$STATE")"
    exit 0 ;;
  check) ;;
  *) echo "usage: $0 start|check" >&2; exit 2 ;;
esac

[ -r "$STATE" ] || { echo "no canary start recorded; run '$0 start' first" >&2; exit 2; }
START=$(cat "$STATE")
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
fail=0
echo "canary window: $START -> $NOW"

active=$(systemctl is-active "$UNIT")
echo "unit active: $active"; [ "$active" = active ] || fail=1

# The unit must not have restarted since the start (a restart rewrites the start of the window).
since_start=$(journalctl -u "$UNIT" --utc --no-pager --since "${START/T/ }" -o cat 2>/dev/null)
starts=$(printf '%s\n' "$since_start" | grep -ac '\[gateway\] starting\.\.\.')
echo "gateway starts inside window: $starts (expect 0 if started before the window, 1 if the window began at a start)"

model_calls=$(printf '%s\n' "$since_start" | grep -ac 'model-fetch\] start')
agent_runs=$(printf '%s\n' "$since_start" | grep -ac '\[agent/embedded\]\|\[agents/agent-command\] \[agent\] run')
tool_errs=$(printf '%s\n' "$since_start" | grep -aci 'session.stalled')
echo "model calls: $model_calls   agent runs: $agent_runs   stalled-session lines: $tool_errs"
[ "$model_calls" -eq 0 ] || fail=1
[ "$agent_runs" -eq 0 ] || fail=1

# Session store: no session created or updated since the start; no cron job enabled.
if [ -x "$GWC" ]; then
  sess=$("$GWC" gateway call sessions.list --params '{}' --json 2>/dev/null | python3 -c "
import sys, json, datetime
start = datetime.datetime.strptime('$START', '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=datetime.timezone.utc).timestamp() * 1000
try:
    d = json.load(sys.stdin)
except Exception:
    print('unreadable'); sys.exit()
rows = d.get('sessions', [])
new = [s['key'] for s in rows if (s.get('updatedAt') or 0) >= start or s.get('hasActiveRun')]
print(len(rows), len(new))
")
  echo "sessions (total, touched since start): $sess"
  case "$sess" in unreadable) fail=1;; *) [ "${sess##* }" = 0 ] || fail=1;; esac
  jobs=$("$GWC" gateway call cron.list --params '{"includeDisabled":true}' --json 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print('unreadable'); sys.exit()
print(sum(1 for j in d.get('jobs', []) if j.get('enabled')))
")
  echo "enabled cron/heartbeat jobs: $jobs (expect 0)"
  [ "$jobs" = 0 ] || fail=1
else
  echo "client helper $GWC missing: session and cron checks skipped"; fail=1
fi

echo "resident memory:"; /home/df/dk.sh stats --no-stream --format '  {{.MemUsage}} cpu={{.CPUPerc}}' openclaw-gateway 2>/dev/null

echo "dfmcp side, run from the workstation (expect 0 role tool calls since the start):"
echo "  scripts/vm-ssh.sh df 'journalctl -u dfmcp-server.service --utc --no-pager -o cat --since \"${START/T/ }\" | grep -a tools/call | grep -ac role'"

if [ "$fail" -eq 0 ]; then echo "CANARY: PASS"; else echo "CANARY: FAIL"; fi
exit "$fail"
