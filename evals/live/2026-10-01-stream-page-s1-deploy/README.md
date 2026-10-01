# Stream page S1 deploy: publisher on VM 103, Caddy on the relay

Date: 2026-10-01. User's go-ahead ("yes for 2"). Runbook:
`web/stream/README.md` "Slice S1", with the deviations below.

## VM 103

- Code deployed (`deploy-vm103.sh 2026-10-01-i`, rev `ac746d2`), plus
  `scripts/stream_publisher.py` installed with a hash check.
  `dfmcp-server` restarted, active; overseer now 99 tools (door, audit).
- Publisher config in its own `/etc/stream-publisher/env` (df, 0640), not the
  MCP server's `.env` (which holds role tokens). Key
  `/etc/stream-publisher/relay_push_ed25519` generated on VM 103, 0600 df.
- `stream-publisher.service` (oneshot, User df, ProtectSystem strict,
  ProtectHome read-only, queue and code read-only) and `.timer` (5 s),
  enabled. Under systemd: `pushed` then `unchanged` on later cycles.

## Relay

- Installed `rsync`, `caddy` (Debian 12: `/usr/bin/rrsync` ships with
  rsync). Account `stream-pub`; `/srv/stream/data/{public,operator}`;
  `authorized_keys` forced command `rrsync /srv/stream/data` with `restrict`.
- **Fix during deploy:** the account first had shell `nologin`; sshd runs
  the forced command through the login shell, so rsync failed with
  "protocol version mismatch". Changed to `/bin/sh`; the forced command
  still blocks everything else.
- Restriction verified from VM 103: push inside allowed; `../` refused;
  absolute `/etc` refused (nothing created); a shell command refused by
  rrsync.
- **Caddy layout differs from the template:** everything outside
  `/stream/` reverse-proxies to the existing noVNC services unchanged, so
  the viewer links keep working after the tunnels move; the page is under
  `/stream/`. Public site `127.0.0.1:8090` serves `web-public` (no
  `operator.html`) and public data only; operator site `127.0.0.1:8091`
  serves both data sides and `operator.html`.
- **Found and fixed:** Caddy first bound all interfaces despite
  `http://127.0.0.1:...` site addresses, exposing the admin viewer proxy
  on the LAN without Access for a few minutes; `bind 127.0.0.1` added,
  verified one listener per port, loopback. The pre-existing public
  view-only websockify (6080) listens beyond loopback, as before; not
  changed.
- Routes on loopback: public 8090 `index` 200, `operator.html` 404,
  operator data 404, noVNC `/` and `vnc.html` 200; operator 8091 all 200.
- First real push: both sides `pushed: true`; relay copies' hashes equal
  VM 103's staged files.

## Waiting on the user

- Repoint each Cloudflare tunnel's public hostname from the noVNC port to
  Caddy (public 6080 to 8090, admin 6081 to 8091), in the Zero Trust
  dashboard; the tunnels are token-run, so ingress lives there.
- Confirm the admin hostname's Access application covers the whole
  hostname, including `/stream/`.
- home-lab obligation: two new services (Caddy on the relay,
  stream-publisher on VM 103) belong in `home-lab/inventory/services.yaml`;
  this repo cannot edit it.
