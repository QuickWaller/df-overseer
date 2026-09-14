# 2026-09-14: Wiring openclaw (VM 106) to dfmcp as a durable service (VM 103)

Read-only research pass. SSH used against both VM 103 and VM 106 to read
state only: no file written, no package installed, no service started,
stopped or enabled, no `.env` created or deleted, nothing committed. Every
command below actually ran; output is quoted with addresses replaced by
labels (VM103-LAN-IP, VM106-LAN-IP) per the no-addresses constraint.

Scope: what is needed to run `dfmcp` durably on VM 103 and have openclaw on
VM 106 call it as a real MCP client. Facts and open choices only, no
implementation.

---

## Decisions the user must make

1. **Where dfmcp's durable install lives on VM 103, and as which user.**
   Recommendation: a git checkout (not a hand-copied tree) under `/opt/df/`,
   owned by `df:df`, the same account that already owns `/opt/df/game` and
   runs every `df-*` systemd unit. Alternative: leave the current hand-staged
   `/opt/df/dfmcp-smoke/` in place and just add a systemd unit on top of it.
   Both are one-command-reversible; the git checkout is cleaner going
   forward, the in-place option is zero extra work today. See Q1.

2. **Which address dfmcp binds to.** Three real options exist today: VM 103's
   LAN address (works now, no new dependency, but the LAN has no firewall on
   either VM, so the DFHack-adjacent MCP endpoint would be reachable by
   anything else already on that /24), a tailnet address (does not exist yet
   on either VM: `tailscale` is not installed on VM 103 or VM 106, so this
   requires provisioning Tailscale first, which is a real prerequisite, not
   a config flag), or leaving it on loopback and reaching it through an SSH
   tunnel from VM 106 (no new software, but a tunnel is one more moving part
   that must itself be kept alive as a service). Recommendation: LAN address
   now, because it is the only option that requires no new install, paired
   with the user's own explicit call on whether an unauthenticated-adjacent
   LAN is acceptable for this estate (this is a `home-lab` posture question,
   not a df-automation one — see Q2 and CLAUDE.md's upstream-obligations
   section). Revisit tailnet once Tailscale is otherwise justified for this
   estate.

3. **Whether openclaw gets installed at all before this is tested**, and if
   so, from which artifact. VM 106 today is a bare Ubuntu 24.04.5 clone with
   nothing on it beyond the base image: no docker, no node, no openclaw. The
   only openclaw artifact that exists anywhere reachable from this session is
   a small config-only scaffold repo (`C:\website-projects\openclaw`,
   `QuickWaller/openclaw` on GitHub) that expects Docker Compose and pulls
   `ghcr.io/openclaw/openclaw:latest`. That scaffold's own `config/*/agent.yaml`
   files use a schema (`name`/`role`/`sandbox`/`channels`/`spokes`/`memory`)
   that has **no relationship** to the `mcp.servers`/`agents.entries` schema
   `research/2026-09-12-openclaw-mcp-auth.md` verified against openclaw's
   TypeScript source. See Q3 and the discrepancy called out there: this needs
   resolving (find or write the real `openclaw.json`/config-dir file the
   running gateway actually reads) before any MCP wiring can be attempted,
   let alone tested.

4. **Whether to accept the current token-handling shape** (tokens minted by
   `token_setup.py` into a mode-600 `.env` on VM 103, read by the server at
   startup; the same values would need to reach VM 106's openclaw config as
   `${VAR}` references) or design something more automated. Recommendation:
   accept it for a first proof; it already matches this repo's existing
   `PVE_TOKEN_SECRET`-style convention. See Q4.

---

## Q1. Deploy location and identity on VM 103

**Today's actual state, read live:**

```
$ ls -la /opt/df
drwxr-xr-x 11 df   df   4096 Sep 13 22:23 .
drwxr-xr-x  6 df   df   4096 Sep 13 23:19 dfmcp-smoke
drwxr-xr-x  9 df   df   4096 Sep  9 04:23 game
...
$ ls -la /opt/df/dfmcp-smoke
drwxrwxr-x  5 df df 4096 Sep 13 22:28 .venv
drwxr-xr-x  8 df df 4096 Sep 13 22:22 agents
drwxr-xr-x  4 df df 4096 Sep 13 23:12 dfmcp
drwxr-xr-x  3 df df 4096 Sep 13 22:22 scripts
-rw-rw-r--  1 df df 3392 Sep 13 23:19 server.log
```

`cd /opt/df/dfmcp-smoke && git status` returns `fatal: not a git repository`
— confirmed this is a hand-copied tree, not a checkout of this repo. It
holds `dfmcp/`, `agents/` and `scripts/dfhack/TOOLS.yaml` only (the subset
`dfmcp` actually imports at runtime), not the rest of df-automation. `.env`
from the smoke test is gone (removed at teardown, per the handoff's own
report and confirmed here: `cat .env` returns "No such file or directory").
The staged `dfmcp/requirements.txt` and the `structuredContent` fix in
`dfmcp/server.py` (line 380, `isinstance(parsed, dict)`) both already match
current `main` — the smoke-test stream re-staged after the fix landed, per
commit `9f7fd1d`. **Confidence: verified, read directly.**

Ownership: `/opt/df`, `/opt/df/game` and `/opt/df/dfmcp-smoke` are all
`df:df`. The account is a real login user (`uid=1000`, groups include `sudo`,
`adm`), not a service account — `ssh_guest`'s default `DF_CIUSER=df` is this
same account. **Confidence: verified.**

`df-fortress.service`'s unit file (`systemctl cat`) confirms `User=df`,
`ExecStart=/opt/df/game/dfhack`. Every other `df-*` unit (`df-xvfb`,
`df-vnc`, `df-vnc-control`, `df-webvnc`, `df-stream`) is `active`/`running`
and by the same pattern almost certainly also runs as `df` (not
independently checked for every unit, but the pattern is consistent and
`infra/dfmcp-server.service.example`'s own comment already assumes it).
**Confidence: verified for `df-fortress.service` directly, inferred by
consistent pattern for the others.**

**What `install_df.py` already does that a deploy could follow:** it
installs everything under `/opt/df/` (game root, tarball cache in
`/opt/df/dist/`, logs in `/opt/df/log/`), owned `df:df`, driven entirely from
`.env` with no hardcoded host specifics, and writes systemd units with
`User=df`/`Group=df`, `Restart=on-failure`, and deliberately tuned
`ExecStop`/`TimeoutStopSec` semantics (`infra/local.df-vm-install.md`'s
verified section on DF ignoring SIGTERM). `infra/dfmcp-server.service.example`
already follows this shape (`User=CHANGEME`/`Group=CHANGEME`, a
`WorkingDirectory` and `EnvironmentFile` under the repo, a dedicated venv
`ExecStart`) — it is explicitly unfilled-in and its own header says the
`User=` line is "not independently re-checked; confirm before filling in."
This pass confirms it: **`df` is right.** The MCP server needs nothing
DFHack's RPC socket doesn't already grant `df` (it talks to
`127.0.0.1:5000`, already reachable by that account), it needs to read
`agents/`/`scripts/dfhack/TOOLS.yaml` (already `df`-owned if deployed
alongside the game), and running it as `df` avoids adding a second service
account with its own sudo/group footprint for no isolation benefit — nothing
in `dfmcp/` needs privilege `df` doesn't already have, and nothing `df`
already has (DF process control, saves, VNC) is a capability the MCP server
should be trying to *not* have. **Confidence: verified against the unit
file and the running services; the "would a separate account be better"
argument is this session's own reasoning, not independently sourced.**

**Real options for a durable install, concretely:**

- **A: git checkout at `/opt/df/dfmcp-automation` (or similar), `df`-owned,
  `git pull` to update.** Matches how a human would expect to redeploy a
  fix (the array-result bug fix is already a real example of "a fix landed
  on `main`, now go update the VM"). Needs `git` on the VM (not checked this
  pass — a one-line follow-up) and either a deploy key or making the repo
  reachable some other way, since it's a public GitHub repo pull-only access
  should suffice with no key at all if HTTPS is reachable from VM 103.
- **B: keep the current hand-copied tree, promote it in place.** Zero extra
  work: it already exists, has a working venv, and the fix is already in it.
  Downside: no record of "this checkout is at commit X," and the next fix
  again means hand-copying files rather than `git pull`.
- **C: `scp`/rsync a built tree on each deploy, no git on the VM at all.**
  Matches `install_df.py`'s own pattern for DF/DFHack (tarballs fetched and
  cached, not git). Consistent with existing convention but reintroduces the
  same "no record of what's deployed" gap as B.

This report does not recommend one over the others as a hard requirement —
A is this session's preference for exactly the reason `dfmcp/README.md`
already values elsewhere (a checkout is a pure function of a commit, not a
hand-maintained state) — but the user's call, since it's a process
preference, not something dfmcp's design forces either way.

---

## Q2. Networking between the two VMs

**Same /24 subnet: confirmed.** `.env`'s `DF_VM_IP` and `OPENCLAW_VM_IP`
share their first three octets (checked programmatically, not printed).
`ip -br addr` on each host shows one `eth0` with a `/24` LAN address and
nothing else beyond loopback and its link-local address.

**No Tailscale on either host.** `which tailscale` on VM 103 and on VM 106
both return `tailscale: command not found`. There is no tailnet address to
bind to today — this would be new infrastructure, not a config choice.
**Confidence: verified, both hosts.**

**No firewall on either host.** `ufw status` (unprivileged) returns
`Status: inactive` on both VM 103 and VM 106; `sudo -n ufw status` fails
without a password (no passwordless sudo for this account, expected and not
worked around, per the read-only mandate). Read-only conclusion: nothing
observed blocks LAN traffic between the two VMs today, but this pass cannot
rule out a router/hypervisor-level ACL between them — only the guest-level
posture was checked. **Confidence: verified for the guest OS level; not
checked at the Proxmox/network level (would need `home-lab`, and this repo
is not authorised to inspect or edit that repo's declared layer beyond
citing it).**

**Live reachability, tested (not just inferred from being on one subnet):**

```
$ ssh df@VM103 "ping -c 2 -W 2 <VM106-LAN-IP>"
2 packets transmitted, 2 received, 0% packet loss, rtt min/avg/max/mdev = 0.306/0.333/0.361/0.027 ms
$ ssh df@VM103 "timeout 3 bash -c 'echo > /dev/tcp/<VM106-LAN-IP>/22'"
REACHABLE
```

Sub-millisecond RTT, and TCP connect to VM 106's SSH port succeeds from VM
103. This is the strongest evidence in this report: it is a live test, not
an inference from IP proximity. **Confidence: verified, live test run this
session.**

**`dfmcp`'s bind-address requirement, read from source:**

```
dfmcp/server.py:165   bind_host: str
dfmcp/server.py:171-179
    def __post_init__(self) -> None:
        if not self.bind_host or not self.bind_host.strip():
            raise ConfigError(... "Set MCP_SERVER_BIND_HOST.")
        if self.bind_host == "0.0.0.0":
            raise ConfigError("bind_host must not be 0.0.0.0 ...")
```

No default, and the literal string `"0.0.0.0"` is a hard error at startup —
confirmed by reading `ServerConfig.__post_init__` directly, and this is
exactly the behavior `docs/AGENT-ARCHITECTURE.md` §13 and `dfmcp/README.md`
both describe. `MCP_SERVER_BIND_HOST` is the `.env` key. **Confidence:
verified, read directly.**

**Options, with the .env key each would use:**

- **VM 103's LAN address**, in `MCP_SERVER_BIND_HOST`. Works today with
  nothing new installed. Trade-off: reachable by anything else on that /24
  (there is no firewall on VM 103 today to narrow this to VM 106
  specifically), and the MCP HTTP endpoint sits adjacent, network-wise, to
  DFHack's own unauthenticated RPC port (though that port itself stays
  bound to loopback regardless — the MCP server does not change DFHack's own
  exposure). This is the option the 2026-09-14 smoke test's design assumed
  would come next (it deliberately used `127.0.0.1` for the test itself,
  precisely to avoid this exposure before a real client existed).
- **VM 103's tailnet address**, in the same `MCP_SERVER_BIND_HOST` key —
  requires installing and configuring Tailscale on both VMs first. Trade-off:
  the strongest of the three (encrypted, identity-scoped, matches
  `docs/AGENT-ARCHITECTURE.md` §13's "MCP over HTTP on the tailnet, never
  publicly exposed" language, and matches how the rest of this estate already
  reaches Proxmox per `infra/local.*` comments), but it is new infrastructure
  this pass found no trace of on either guest, so it is a real prerequisite
  project, not a five-minute step.
- **Loopback only, reached via an SSH tunnel initiated from VM 106** (`ssh -L`
  or `-R`, matching the pattern `df-vnc-tunnel.service` already uses on VM
  103 for the relay). `MCP_SERVER_BIND_HOST` stays `127.0.0.1` on VM 103; VM
  106's openclaw config would then point at *its own* loopback address,
  wherever the tunnel forwards it. No new package on VM 103 beyond `ssh`
  (already present). Trade-off: one more durable process to keep alive (the
  tunnel itself, plus whatever supervises it), and it needs its own systemd
  unit and its own "what if it dies" answer — this project already has one
  documented failure mode for exactly this pattern (`df-vnc-tunnel.service`
  exists because a naive tunnel needed supervision).

This report takes no position on which the user should choose beyond noting
that the LAN option is the only one requiring zero new infrastructure, and
that the live reachability test above already proves the LAN path would work
mechanically today.

---

## Q3. What openclaw on VM 106 actually is right now

**Not installed, not running, not configured, no systemd unit.** Verified
directly:

```
$ ssh df@VM106 "which docker docker-compose"
bash: line 1: docker: command not found
$ ssh df@VM106 "ls -la /opt/openclaw"
ls: cannot access '/opt/openclaw': No such file or directory
$ ssh df@VM106 "which node npm openclaw"
bash: line 1: node: command not found
(npm, openclaw: same)
$ ssh df@VM106 "systemctl list-units --all | grep -i openclaw"
(no output)
$ ssh df@VM106 "cat /etc/os-release"
PRETTY_NAME="Ubuntu 24.04.5 LTS"
$ ssh df@VM106 "uptime -s"
2026-09-12 06:22:23
```

VM 106 is a two-day-old bare Ubuntu clone with nothing beyond the base cloud
image and an SSH key. **Confidence: verified, this session's own live
reads.**

**The only openclaw artifact reachable at all is a local checkout,
`C:\website-projects\openclaw`**, git remote `QuickWaller/openclaw`
(three commits, last one 2026-05-26, well before this project's own MCP
work). It is a **config-only scaffold repo**, not the openclaw application
source: `docker-compose.yml` pulls `ghcr.io/openclaw/openclaw:latest` as an
opaque image, and the repo itself holds only `config/{orchestrator,
personal-assistant,system-ops}/agent.yaml`, a memory directory skeleton, and
a `.env.example`.

**The real config shape in this checkout, quoted in full** (there are only
three files, each short):

```yaml
# config/orchestrator/agent.yaml
name: orchestrator
role: hub
sandbox: false
channels: []
spokes:
  - personal-assistant
  - system-ops
```
```yaml
# config/personal-assistant/agent.yaml
name: personal-assistant
role: spoke
sandbox: false
channels:
  - telegram
tone: friendly, concise, personal
memory:
  private: memory/spokes/personal-assistant
  shared: memory/shared
integrations:
  - microsoft-365
```
```yaml
# config/system-ops/agent.yaml
name: system-ops
role: spoke
sandbox: false  # to be configured — see Block 6
channels: []
tone: terse, precise, technical
memory:
  private: memory/spokes/system-ops
  shared: memory/shared
```

**None of these three files contains an `mcp` key, a `tools.allow`/`deny`
key, a `headers` key, or anything resembling
`research/2026-09-12-openclaw-mcp-auth.md`'s quoted schema.** That research
brief verified its schema (`mcp.servers.<name>.headers`,
`agents.entries.<agentId>.tools.allow/deny`, `${VAR}` substitution) against
openclaw's own TypeScript source on GitHub
(`github.com/openclaw/openclaw`, read via the GitHub API) — a different
repository from this scaffold, and a different config shape entirely
(`agents.entries.<id>` vs. this checkout's `config/<name>/agent.yaml` one
file per agent, `mcp.servers` vs. nothing at all here).

**Flagged discrepancy, stated plainly per this project's evidence standard:**
this local checkout's own config schema does not match, and gives no
evidence either way for, the schema the research brief verified from
upstream source. Two explanations are both plausible and this pass could not
adjudicate between them read-only:

1. The scaffold repo (written 2026-05-26, by a different author line
   `tombstonesuplex`, predating this project's MCP work by nearly four
   months) is simply an earlier, thinner config convention than whatever the
   real `ghcr.io/openclaw/openclaw` image at `latest` actually reads from
   `OPENCLAW_CONFIG_DIR` today — i.e., these `agent.yaml` files might not be
   the file the running gateway consumes at all, and the real
   `mcp.servers`/`agents.entries` config might live in a sibling file (an
   `openclaw.json`, per the research brief's own examples) that this scaffold
   never got around to adding.
2. The research brief's schema belongs to a later or different version/build
   of openclaw than whatever `ghcr.io/openclaw/openclaw:latest` currently
   resolves to, and the two could disagree at the point this is actually
   deployed.

**This pass could not resolve which, because doing so would mean either
pulling the actual image (a change to VM 106, barred by this task's
read-only mandate) or fetching upstream source again (out of scope for a
VM-focused pass, and the research brief already did this once). Recorded as
the single largest open unknown in this whole investigation**: nobody has
confirmed that `openclaw.json`'s `mcp.servers` key is really what the
`ghcr.io/openclaw/openclaw:latest` image reads, only that the upstream
TypeScript source (as read on GitHub) implements it. Before wiring anything,
whoever does the deploy should pull the image once, run
`docker compose config`/inspect its actual config-loading behavior, or read
the image's own docs for `OPENCLAW_CONFIG_DIR`'s expected file layout, and
confirm `openclaw.json` (not `agent.yaml`) is the right file — or that
`agent.yaml` per-agent files are additionally merged with a top-level
`openclaw.json` the scaffold simply never wrote.

---

## Q4. Tokens

**Server side, confirmed from source and from the smoke test's own script:**
`dfmcp/auth.py` reads `MCP_ROLE_TOKEN_<ROLE>` (upper-cased role name) from a
`.env`-shaped file at the repo root (`load_role_tokens`, default path
resolves next to wherever `dfmcp/` is deployed). Enabled roles today, per
`agents/ROSTER.yaml`: `overseer`, `architect`, `consultant` — so
`MCP_ROLE_TOKEN_OVERSEER`, `MCP_ROLE_TOKEN_ARCHITECT`,
`MCP_ROLE_TOKEN_CONSULTANT`, matching `infra/local.example.env`'s
placeholders exactly. Minimum token length enforced at load (20 chars
default); never logged, printed, or returned in any error message —
confirmed by `dfmcp/README.md`'s description of the dedicated tests for this,
and independently observed live: the smoke test's own `check12.sh` reads
the token from `.env` into a `curl -K` config file (never a bare CLI arg,
so it never appears in `ps`), deletes the file immediately after use, and
`token_setup.py` prints only token *lengths*, never values.

**On VM 103 today, concretely:** `token_setup.py` (staged at
`/opt/df/dfmcp-smoke/token_setup.py`) generates three `secrets.token_urlsafe(32)`
values into a mode-600 `.env` in the staging dir, alongside
`MCP_SERVER_BIND_HOST`/`PORT`/`DFHACK_HOST`/`DFHACK_PORT`. That `.env` was
deleted at the smoke test's teardown (confirmed: `cat .env` now returns "No
such file or directory") — nothing token-shaped is currently sitting on the
VM. A durable deploy needs this regenerated (or a real, intentionally
long-lived set minted) as part of standing the service up.

**Client side, per `research/2026-09-12-openclaw-mcp-auth.md`'s verified
reading of openclaw's source:** `mcp.servers.<name>.headers` is a plain
string map sent as literal HTTP headers, and its values go through generic
`${VAR_NAME}` substitution at config load
(`src/config/env-substitution.ts`), so `openclaw.json` itself would commit
only `"Authorization": "Bearer ${DF_MCP_TOKEN_OVERSEER}"` — never the literal
value — and the real value would need to reach openclaw's own process
environment (a systemd `EnvironmentFile=`, a `.env` the container loads via
`docker-compose.yml`'s `environment:` block, or Docker secrets). **This half
is unverified against a real openclaw instance** (Q3 above: no openclaw
instance exists to check), so "does `${VAR}` substitution really apply to
whatever schema the real image reads" inherits the same open question as Q3.

**Where a token would risk exposure, concretely, given what's on each VM
today:**

- **World-readable file:** neither `.env` shape observed here (the deleted
  smoke-test one, or `infra/local.example.env`'s placeholders) is
  world-readable; `token_setup.py` explicitly `chmod`s to 0600. The risk is
  a *future* mistake, not something observed live — worth stating as a
  requirement for whoever re-creates the file, not as a finding of an actual
  leak.
- **Process list:** `check12.sh`'s own approach (curl `-K` config file, never
  a bare argv token) is the right pattern and should be the template for any
  future check script. A naive `curl -H "Authorization: Bearer $TOKEN"`
  would leak the token to any other user's `ps aux` on the same VM — VM 103
  has more than one group member (`sudo`, `adm`, `lxd`) so this is not purely
  theoretical, though only one human account (`df`) was observed.
- **Git-tracked file:** `infra/local.example.env` (tracked) carries only
  empty placeholders; the real `.env` is gitignored, confirmed by this
  repo's own `.gitignore` convention already documented in CLAUDE.md and
  `dfmcp/README.md`. openclaw's own config, on VM 106, is a separate concern
  — the scaffold repo's `.env.example` also carries only placeholders and its
  `.gitignore` (not read in full this pass, but its README states
  "Not tracked in git: `.env`...") appears to follow the same convention.
  **Not independently re-verified for the openclaw scaffold's `.gitignore`
  contents this pass.**

---

## Q5. The smallest possible first proof

**Recommendation: an `architect` (advisor) call to a verified, read-only,
zero-argument tool — `overview.get` or `landmarks.list` — from openclaw,
end to end.**

Why `architect` and not `overseer`: it is a read-only role by design (no
`write:` section in `agents/architect/tools.yaml`), so even a
misconfiguration on the openclaw side (a wrong tool name reaching the server,
a role-scoping mistake) cannot reach a mutating tool — the smallest possible
blast radius for the very first external call. `dfmcp/roles.py` enforces
this server-side regardless of what openclaw's own config claims, per
`docs/AGENT-ARCHITECTURE.md` §13's "allowlist enforced by the MCP server, not
by openclaw's config" design.

Why `overview.get` or `landmarks.list` specifically: both are tagged
`status: exists` in the live roster, both were part of the 2026-09-14 smoke
test's own verified set (`landmarks.list` is the exact tool that surfaced
Bug 1, now fixed and confirmed staged), and both take no arguments — nothing
about argument encoding, positional-optional ordering, or the enum/int
schema heuristics in `dfmcp/tools.py` can go wrong on the first call.

**What would count as proof:** a real, non-empty JSON response reaching the
openclaw agent's tool-result content — specifically, for `landmarks.list`, a
JSON array of landmark objects (the exact shape the array-result fix
targets, so this call also re-confirms that fix against a client that is not
the reference Python SDK, closing `dfmcp/README.md`'s own explicitly-named
gap: "Nothing here has been reached by openclaw, or any MCP client other
than the reference Python SDK's own `ClientSession`"). A `tools/list` call
returning the architect's tool set with zero mutating tools present would be
a slightly smaller, even-safer precursor step if an extra layer of caution is
wanted before the first real tool call.

**No mutating tool is involved at any point in this proof**, matching this
task's own constraint and `handoffs/2026-09-14-mcp-live-smoke-test.md`'s
"hard line" against ever calling a mutate tool through a permitted role.

---

## Q6. Risks to the live fort

**What this deployment could plausibly disturb:**

- **Resource contention on VM 103.** The MCP server, once durable, holds a
  small pool of persistent DFHack RPC connections
  (`DFHackConnectionPool`, default size read from `MCP_SERVER_POOL_SIZE`)
  open continuously alongside the game process, Xvfb, two VNC servers, a
  websocket bridge, and two reverse SSH tunnels — all already running on a
  4096 MB VM (per `infra/local.df-vm-install.md`'s sizing note, which itself
  flags that a long-running fortress with hundreds of units is "the real
  memory question and remains unmeasured"). Adding a Python/uvicorn process
  is unlikely to be the thing that tips this over, but this pass did not
  measure current headroom on VM 103 (a `free -h` read was not part of this
  task's checklist and was not run) — worth doing before enabling.
- **A crash-looping or misbehaving MCP service destabilizing sibling units.**
  This project already has a documented precedent for exactly this failure
  shape: a leftover manual Xvfb process once blocked `df-xvfb.service` from
  binding its display, which cascaded into `df-fortress.service` failing via
  a `Requires=` dependency (`infra/local.df-vm-install.md`). A new systemd
  unit that is not carefully scoped (no `Requires=`/`After=` chain to
  `df-fortress.service` beyond what `infra/dfmcp-server.service.example`
  already comments out) should not create a new coupling of this shape —
  the example unit's own commented-out `After=dfhack.service` line is
  deliberately not wired to anything that could fail the fort if the MCP
  server itself crash-loops. Confirm this stays a one-directional dependency
  (MCP depends on DF being up; DF must never depend on MCP) when the real
  unit is written.
- **Exposure surface, if bound to the LAN address (Q2).** Nothing currently
  firewalls VM 103's LAN interface, so an MCP endpoint bound there is
  reachable by anything else already on that /24, not just VM 106. This does
  not expose DFHack's own RPC port directly (it stays loopback-bound
  regardless), but it does expose whatever the MCP server's own tool surface
  allows — for the `overseer` role, that includes real mutating tools
  (`openarea.build`, `diggable.dig`, `landmarks.build`, `labor.set-labor`),
  gated only by that role's token. A leaked or guessed Overseer token on an
  unfirewalled LAN segment is a real write path to the live fort.
- **A genuinely mutating call reaching the fort by mistake during testing.**
  The design's own layered defence (server-side `Roster.check`, then
  openclaw's own `tools.allow/deny` as a second layer, once that config
  question in Q3 is resolved) is real, but Q5's whole point is to prove the
  read path first and defer any call to a role holding write tools until
  read-only proof is solid.

**What would make it safe to reverse:**

- **The MCP server itself is stateless and additive.** It holds no
  persistent state of its own beyond the token `.env` and its own log file;
  stopping the systemd unit and deleting `/opt/df/dfmcp-smoke/`
  (or its durable successor) removes it completely, with **zero** effect on
  DF/DFHack, saves, or any other running service — confirmed by this pass's
  own read of what the smoke test's teardown already proved: server killed,
  port closed, token file deleted, `df-fortress.service` unaffected and still
  `active`. This was independently re-checked by the orchestrator per the
  handoff, not just claimed by the executor that ran it.
- **The systemd unit, if installed, is reversible in the same way any other
  `df-*` unit already is**: `systemctl disable --now`, delete the unit file.
  Nothing in `infra/dfmcp-server.service.example` requests a reboot, a
  package outside a dedicated venv, or any change to `df-fortress.service`'s
  own unit.
- **The riskiest single step is minting durable tokens and putting the
  bind address on the LAN**, both of which are easy to undo (rotate/delete
  tokens, rebind to loopback) but matter while they're live — this is a
  posture choice (Q2) more than an irreversibility risk.
- **Nothing in this deployment touches saves, quicksaves, or DF's own
  process lifecycle.** The one hard line every prior stream touching VM 103
  has held (`handoffs/2026-09-14-mcp-live-smoke-test.md`'s own "hard lines"
  section) continues to apply and this pass found no reason it would need to
  change for a durable install.

---

## What could not be verified, stated plainly

- **Whether `openclaw.json`'s `mcp.servers` schema (verified against
  upstream TypeScript source by `research/2026-09-12-openclaw-mcp-auth.md`)
  is really the file `ghcr.io/openclaw/openclaw:latest` reads from
  `OPENCLAW_CONFIG_DIR`.** The only local openclaw artifact (the scaffold
  repo) uses a visibly different, incompatible-looking schema and predates
  this project's MCP research by four months. This is the single largest
  open item in this report — see Q3.
- **Proxmox/hypervisor-level network policy between VM 103 and VM 106.**
  Guest-level reachability is proven live; anything enforced above the guest
  (a vSwitch ACL, a security group) was not checked, and this repo is not
  authorised to inspect `home-lab`'s declared layer for it.
- **VM 103's current memory/CPU headroom** for adding a durable MCP process
  alongside everything else already running. Not measured this pass.
- **Whether `git` is installed on VM 103**, relevant to deploy option A in
  Q1. Not checked.
- **The openclaw scaffold repo's `.gitignore` contents**, relevant to the
  "git-tracked token" sub-question in Q4. The README states `.env` is not
  tracked; the actual `.gitignore` file was not read in full this pass.
- **Whether a passwordless-sudo path exists on either VM for a future
  deploy step** (e.g. installing `python3.12-venv`, as the smoke test needed)
  — `sudo -n` failed for `ufw status` on both hosts, meaning any future
  install step will need an interactive or otherwise-authorized sudo path,
  not something this pass attempted to work around.

---

## Relevant to

`docs/AGENT-ARCHITECTURE.md` §13 (deployment topology, the two trust-boundary
requirements) and §14 item 5 (closed for the server's existence, still open
for a real client); `dfmcp/README.md`'s own "what remains unproven" list
(specifically "nothing here has been reached by openclaw"); the not-yet-built
openclaw-side `mcp/` config referenced by
`research/2026-09-12-openclaw-mcp-auth.md`'s closing section; and
`handoffs/2026-09-14-mcp-live-smoke-test.md`, whose staged tree and fix this
report confirms is still live and current on VM 103.

---

## Correction, added 2026-09-14 after the deploy stream ran

**This report's "could not be verified" section was wrong about sudo.** It
inferred from a failing `sudo -n ufw status` that `df` has no passwordless
sudo. Checked directly during the deploy: `sudo -n whoami` returns `root` and
`sudo -n -l` reports `(ALL) NOPASSWD: ALL`. The `ufw` call failed for its own
reasons, not a sudo restriction. The orchestrator had already confirmed the
same thing independently before the package install earlier that day.

Everything else in this report held up in practice. Q1's "promote the staged
tree in place" turned out to need no restaging at all: the tree was
sha256-identical to `main` across every file `dfmcp` imports.
