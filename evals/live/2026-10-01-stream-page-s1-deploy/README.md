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

## Tunnels repointed by the user; the front-door change (same day)

- The user repointed both tunnels in the dashboard. The admin connector
  took the change at once; the public connector kept `localhost:6080`
  until `systemctl restart cloudflared` on the relay (it had just
  reconnected and missed the update).
- **White screen, first misdiagnosed.** The page loaded blank. I first
  blamed a Cloudflare cache of an empty `app.js` (`cf-cache-status: HIT`,
  length 0). Wrong cause: Caddy sites were written `http://127.0.0.1:8090`,
  which answer only requests whose Host is 127.0.0.1; tunnel requests carry
  the public hostname, matched no site, and got an empty 200 for every
  path. Every loopback test had passed because curl sent Host 127.0.0.1.
  Fixed to `http://:8090` and `http://:8091` with `bind 127.0.0.1` (still
  one loopback listener per port, verified). The empty answers had been
  cached by Cloudflare for the `.js` and `.css` names, so asset links now
  carry `?v=3` and the page routes send `Cache-Control: no-cache`, data
  `no-store`.
- **The page is the front door** (the user: the addresses were not
  convenient): `/` is the stream page with the live view embedded
  (view-only on the public site, full control on the admin site), `/view`
  redirects to the bare viewer, old `/stream/...` links redirect to `/`,
  everything else passes through to noVNC. Caddy's `redir /path 302`
  read the target as a path matcher; fixed with `redir * /path 302`.
- From outside after the fixes: public `/` 200 (1302 bytes), `app.js?v=3`
  22116 bytes, `style.css?v=3` 9634, `data/public/head.json` 191,
  `/view` 302, `vnc.html` 200, `/operator.html` and
  `/data/operator/head.json` 404 on the public site; admin `/` redirects to
  Cloudflare Access.
