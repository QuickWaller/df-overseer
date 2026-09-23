#!/usr/bin/env bash
# Run one command on a project VM without ever printing its address.
#
# Why this exists: four separate agent sessions have now leaked a VM address
# or hostname into a transcript while building this same wrapper from scratch,
# usually while debugging quote stripping in their own `.env` read. The rule
# ("never print an IP or hostname", CLAUDE.md) is easy to keep once nobody has
# to write the lookup again.
#
# Usage:
#   scripts/vm-ssh.sh df 'uptime'              # the fort VM   (DF_VM_IP)
#   scripts/vm-ssh.sh openclaw 'systemctl ...' # the agent VM  (OPENCLAW_VM_IP)
#   scripts/vm-ssh.sh df --copy LOCAL REMOTE   # scp a file to the fort VM
#
# The address is read by key from .env (never the whole file), stripped of
# quotes and any CIDR suffix, and kept in a shell variable that is never
# echoed. Every line of output is filtered so an address the remote command
# happens to print (`ss`, `ip`, a journal line) is masked before it reaches a
# transcript. Nothing here is a secret store: it reads one non-secret value.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${DF_ENV_FILE:-$REPO_ROOT/.env}"
KEY_FILE="${DF_SSH_KEY:-$HOME/.ssh/df_overseer_ed25519}"
SSH_USER="${DF_SSH_USER:-df}"

target="${1:-}"
shift || true
case "$target" in
  df)       env_key="DF_VM_IP" ;;
  openclaw) env_key="OPENCLAW_VM_IP" ;;
  *) echo "usage: vm-ssh.sh {df|openclaw} COMMAND | --copy LOCAL REMOTE" >&2; exit 2 ;;
esac

if [ ! -r "$ENV_FILE" ]; then
  echo "vm-ssh: no readable .env at the expected path" >&2
  exit 3
fi

# Read one key only. Strip surrounding quotes of either kind and any /NN suffix.
addr="$(grep -E "^${env_key}=" "$ENV_FILE" | head -n1 | cut -d= -f2- \
  | tr -d "\"'" | tr -d '\r' | sed 's#/.*##' | xargs)"
if [ -z "$addr" ]; then
  echo "vm-ssh: ${env_key} is not set in .env" >&2
  exit 3
fi

# Mask anything address-shaped, plus the guest hostnames, on the way out.
scrub() { sed -E -e 's/[0-9]{1,3}(\.[0-9]{1,3}){3}/<ip>/g' -e "s/df-[a-z0-9-]+/<host>/g"; }

if [ "${1:-}" = "--copy" ]; then
  local_path="${2:?local path}"
  remote_path="${3:?remote path}"
  scp -o BatchMode=yes -i "$KEY_FILE" -- "$local_path" "${SSH_USER}@${addr}:${remote_path}" 2>&1 | scrub
else
  ssh -o BatchMode=yes -i "$KEY_FILE" -- "${SSH_USER}@${addr}" "$@" 2>&1 | scrub
fi
