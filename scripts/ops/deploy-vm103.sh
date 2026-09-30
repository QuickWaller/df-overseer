#!/usr/bin/env bash
# One-shot deploy of repo HEAD to VM 103: changed Lua scripts to the DFHack
# scripts dir, changed runtime files to the MCP server tree. Hash-verified at
# every hop, backups first, validation before restart. Run from repo root.
set -euo pipefail
TAG="${1:?usage: deploy.sh TAG}"
REV=$(git rev-parse --short HEAD)
W=$(mktemp -d)
SS=/opt/df/game/hack/scripts
MT=/opt/df/dfmcp-smoke
BK=/opt/df/deploy-backup-$TAG

# 1. Candidate paths (runtime only, no tests)
{ git ls-files 'scripts/dfhack/*.lua'
  git ls-files dfmcp dfqueue agents doctrine gotchas scripts/dfhack/TOOLS.yaml | grep -v -E '(^|/)tests/|\.lua$'
} > "$W/candidates"

# 2. Local hashes of committed bytes, remote hashes at the install path
while read -r p; do
  case "$p" in scripts/dfhack/*.lua) dst="$SS/$(basename "$p")";; *) dst="$MT/$p";; esac
  printf '%s %s %s\n' "$(git -c core.autocrlf=false show HEAD:"$p" | sha256sum | cut -c1-64)" "$p" "$dst"
done < "$W/candidates" > "$W/local"
awk '{print $3}' "$W/local" > "$W/dsts"
scripts/vm-ssh.sh df --copy "$W/dsts" /tmp/dfo_dsts >/dev/null
scripts/vm-ssh.sh df 'while read d; do if [ -f "$d" ]; then sha256sum "$d" | cut -c1-64; else echo MISSING; fi; done < /tmp/dfo_dsts | base64 -w0' | base64 -d > "$W/remote"
paste -d' ' "$W/local" "$W/remote" | awk '$1!=$4 {print $2, $3, $1}' > "$W/changed"
echo "changed: $(wc -l < "$W/changed")"
[ -s "$W/changed" ] || { echo "nothing to deploy"; exit 0; }

# 3. Archive exactly those paths from HEAD, ship, verify on arrival
awk '{print $1}' "$W/changed" > "$W/paths"
git -c core.autocrlf=false archive --format=tar -o "$W/deploy.tar" HEAD $(cat "$W/paths")
awk '{print $3"  stage/"$1}' "$W/changed" > "$W/manifest"
awk '{print "stage/"$1" "$2}' "$W/changed" > "$W/map"
for f in deploy.tar manifest map; do scripts/vm-ssh.sh df --copy "$W/$f" "/tmp/dfo_$f" >/dev/null; done
scripts/vm-ssh.sh df "set -e; rm -rf /tmp/dfo_deploy; mkdir -p /tmp/dfo_deploy/stage; cd /tmp/dfo_deploy; tar -xf /tmp/dfo_deploy.tar -C stage; sha256sum -c --quiet /tmp/dfo_manifest && echo ARRIVAL_VERIFIED; ! grep -rlI \$'\r' stage >/dev/null && echo NO_CRLF"

# 4. Back up, install, verify at install path
scripts/vm-ssh.sh df "set -e; cd /tmp/dfo_deploy; mkdir -p $BK; sudo $MT/.venv/bin/python -c 'import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); print(\"DB_BACKED_UP\")' /var/lib/dfmcp/Uniboslan.sqlite3 $BK/Uniboslan.sqlite3.pre-deploy
while read s d; do if [ -f \"\$d\" ]; then mkdir -p \"$BK\$(dirname \"\$d\")\"; cp -a \"\$d\" \"$BK\$d\"; fi; mkdir -p \"\$(dirname \"\$d\")\"; install -m 0644 \"\$s\" \"\$d\"; done < /tmp/dfo_map
while read s d; do [ \"\$(sha256sum < \"\$s\")\" = \"\$(sha256sum < \"\$d\")\" ] || { echo INSTALL_MISMATCH; exit 1; }; done < /tmp/dfo_map; echo INSTALL_VERIFIED; echo $REV > $BK/DEPLOYED_REV"
echo "backup: $BK  rev: $REV"
