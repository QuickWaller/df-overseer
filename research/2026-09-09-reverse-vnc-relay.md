# Getting Live VNC to willsmith.nz Without Opening VM 103 to the Internet

Date: 2026-09-09
Scope: whether/how to chain x11vnc's reverse-connect ("connect out") mode through a small public relay VM to noVNC/websockify, as the public-facing leg of live-viewing `df-colony-01` (VM 103) — the harder option the user chose over the already-half-built periodic-screenshot push (`cmd_stream` in `scripts/install_df.py`). Follows `research/2026-09-08-live-viewing.md`'s structure and honesty conventions: verified vs. estimated vs. proposed, explicit gaps, a plain recommendation.

Status: **research/design only.** Nothing was provisioned, installed, or configured on any host. Sources are (a) x11vnc's own documentation and source, read directly (man page mirrors of the actual text, and the actual Perl source of the repeater script it ships), (b) the noVNC/websockify projects' own docs and issue tracker, read directly, (c) this repo's own already-running code (`scripts/install_df.py`'s `cmd_vnc`/`cmd_webvnc`, read in full before proposing anything), and (d) general VPS/sysadmin knowledge for cost and hardening figures, explicitly flagged as estimates where no primary source pins a number.

---

## 1. The answer, up front

**Recommend the reverse SSH tunnel, not the VNC-repeater chain, if the repeater approach's harder video option is pursued at all.** Both satisfy the hard constraint (VM 103 only ever dials out, the relay is the only public-facing thing, the result is genuinely live video not stills). The repeater chain needs three cooperating pieces with a genuine, currently-unresolved integration question at the middle joint (§4); the SSH tunnel needs one well-trodden protocol (SSH port forwarding) that this project's own tooling already leans on for everything else, and turns the existing, already-working `df-vnc.service`/`df-webvnc.service` into the relay-side story with **no changes to x11vnc's configuration at all** — the tunnel is purely additive.

Concretely: a `systemd` unit on VM 103 runs `ssh -N -R 127.0.0.1:5900:127.0.0.1:5900 relay-user@relay-host`, giving the relay a `localhost:5900` that is transparently VM 103's `x11vnc`. `websockify`/`novnc` on the relay point at `localhost:5900` exactly as `cmd_webvnc` already points them at `localhost:5900` on VM 103 today — same command, same tool, different host. Nothing new to learn on the RFB side; the only new surface is one restricted SSH key and one hardened relay.

Whether this is worth building at all versus the already-half-built screenshot push is a separate, harder question, addressed honestly in §8.

---

## 2. x11vnc's reverse-connect mechanics, verified against primary sources

Checked against the actual x11vnc man page text (mirrored verbatim at manpages.ubuntu.com for the `noble` release this project targets, and cross-checked against mankier's copy — both quote identical option text, so this is the real documentation, not paraphrase):

**Plain reverse connect:**
```
-connect string
```
> "For use with 'vncviewer -listen' reverse connections. If string has the form 'host' or 'host:port' the connection is made once at startup."

Multiple targets can be comma-separated (`host1,host2` or `host1:0,host2:5678`); `-shared` is typically needed if more than one viewer is meant to be connected at once. What must be listening on the other end for this plain form: an ordinary VNC **viewer** running in `-listen` mode (e.g. `vncviewer -listen`, or a purpose-built listener) — not a repeater, not a normal VNC server socket. This is the classic "server calls the viewer" NAT-traversal pattern the option was built for.

**Repeater-style reverse connect**, confirmed real and confirmed exact syntax (not assumed from general VNC lore):
```
-connect repeater=ID:1234+host:port
-connect repeater=23.45.67.89::5501+host:port
```
An SSVNC-notation alternate form is also documented: `-connect repeater://host:port+ID:1234`. The man page's own framing: "Some services provide an intermediate 'vnc repeater'... that acts as a proxy/gateway. Modes like these require an initial string to be sent for the reverse connection before the VNC protocol is started." A generic `pre=`/`preNNN=` form also exists for repeaters that expect an arbitrary fixed string rather than the UltraVNC `ID:` convention specifically. What must be listening on the other end for this form: a **repeater** — a service that accepts this "server, register under ID X" handshake on one port and separately accepts "viewer, connect me to ID X" on another port, per §3.

**Confidence: high.** This is the documented option text itself, cross-checked across two independent mirrors that agree verbatim, not a paraphrase or a forum post.

---

## 3. Is there a real, maintained, Linux VNC repeater compatible with this?

**Yes, one exists and is compatible at the protocol level — but it is not actively maintained, and it is not `apt`-installable.**

`LibVNC/x11vnc` (the actively-maintained fork that succeeded the original author's project — the same upstream this project already fetches `x11vnc` from) ships a reference repeater implementation in its own tree: `misc/ultravnc_repeater.pl`, a self-contained Perl script. Read directly from the repository:

- **What it does, confirmed from the actual source**: listens on two TCP ports (default 5900 for viewers, 5500 for servers). A connecting VNC server (x11vnc, in reverse-connect mode) sends `ID:<string>` to register. A connecting viewer sends either `ID:<string>` to request that specific server, or a raw `host:port` for a plain relay. Once a server and a viewer with matching IDs are both present, the repeater stitches their two sockets into what the code treats as **"a plain, transparent TCP pipe"** for the RFB protocol from that point on — confirming that once bridged, a generic VNC-protocol consumer on the viewer side sees an ordinary RFB stream, not repeater-specific framing.
- **Authorship and license, from the file's own header**: Karl J. Runge, 2009-2010, GPLv2.
- **Maintenance status, confirmed from GitHub's own commit history for this specific file**: five commits total, the most recent dated **2010-09-10**. It has not been touched in roughly sixteen years. It rides along inside an otherwise-active repository (LibVNC/x11vnc has had activity within the last year per its releases page) purely as a `misc/` convenience script, not as a maintained component with its own release cycle, tests, or security review. That distinction matters: "shipped by an active project" and "actively maintained" are different claims, and this report is not conflating them.
- **Packaging**: no `apt`-installable package for this or any equivalent VNC repeater was found in Debian/Ubuntu's standard repositories (checked via search rather than a live `apt-cache policy` against a real box, since no relay VM exists yet — flagged as not independently confirmed against a live `apt-cache`, unlike this project's usual standard of checking before committing to a tool). The practical build step would be: `apt install perl` (already present on any Ubuntu box) plus copying one ungoverned, sixteen-year-old script onto the relay and running it as a service — not a package with security updates, changelogs, or upstream issue triage behind it.
- **Independent reimplementations**: none found that are both (a) confirmed compatible with x11vnc's exact `repeater=ID:` wire format and (b) more actively maintained than the above. General-purpose reverse-tunnel tools exist and are actively maintained (`frp`, Go, and `rathole`, Rust — both real, both alive, `rathole`'s last tagged release October 2023) but neither speaks the UltraVNC repeater ID-handshake protocol; they are TCP/UDP tunnels in the same spirit as SSH port-forwarding, not repeaters. Their existence is more evidence *for* §5's SSH-tunnel-shaped approach (that category of tool is well-populated and actively maintained) than for the repeater approach specifically.

**Confidence: high on what the script does and when it was last touched** (read the actual source and the actual commit log). **Medium on "no apt package exists"** — based on search rather than a live `apt-cache policy`, which this project's own convention (cited in the task brief, and visible in `cmd_vnc`/`cmd_webvnc`'s package-check scripts) would normally run against the real target box before concluding this.

---

## 4. Does websockify/noVNC just work against a repeater? A genuinely unresolved question, not a clean yes or no

This is the joint the whole repeater chain hinges on, and the honest answer is **partially documented, practically unverified.**

**The favorable half**: noVNC's own client (`RFB.js`, the code that runs in the browser) ships a `repeaterID` connection parameter, documented in noVNC's `docs/EMBEDDING.md`:

> "repeaterID - The repeater ID to use if a VNC repeater is detected."

This means the *ID handshake* (`ID:1234`) is meant to be sent by noVNC's own RFB implementation over the WebSocket, not by websockify — and websockify, which is a dumb byte-relaying WebSocket-to-TCP bridge with no protocol awareness, would simply forward those bytes through to whatever TCP target it's pointed at. In principle this means: point `websockify` at the repeater's viewer-facing port as its raw TCP target, put `?repeaterID=1234` on the noVNC URL, and the ID handshake happens inside the WebSocket payload before RFB proper begins — no protocol-aware code needed in websockify itself.

**The unfavorable half**: no primary source found actually confirms this combination working end-to-end. The one concrete data point is a real bug report against noVNC itself (issue #422 on `novnc/noVNC`) where a user pointed websockify directly at an UltraVNC repeater's port and got a protocol-parsing failure — the repeater received bytes it couldn't parse as a valid ID, then tried to reinterpret part of what it received as a host:port and attempted an unrelated connection. That report does not clearly say whether `repeaterID` was actually set on the noVNC side (the launch command quoted only shows `--vnc <ip>:5901`, no `repeaterID` in view), so it may simply document "what happens if you skip the parameter noVNC provides for exactly this," rather than proving the parameter itself is broken. But the issue was closed as an unresolved "question" with no maintainer confirmation that the intended combination actually works, and no other report of anyone getting `x11vnc -connect repeater=... ` → Karl Runge's Perl repeater → websockify → noVNC `repeaterID` working end-to-end was found.

**Net assessment**: the pieces that would be needed exist and appear designed for exactly this scenario, but there is no verified working reference configuration anywhere this report could find, and the one concrete report of someone trying something like it hit a failure that was never resolved publicly. Building this chain today means being the one to prove it works, against a sixteen-year-untouched repeater script and a noVNC parameter with one line of documentation and no worked example. That is a materially different risk profile from "documented, working, off-the-shelf," and should be weighed as such rather than assumed away.

**Confidence: high on what is and isn't documented; explicitly unverified on whether the combination works in practice** — this is exactly the kind of gap this report is supposed to name rather than paper over.

---

## 5. The alternative: reverse SSH tunnel, compared honestly

**Mechanism**: VM 103 runs (as a `systemd` service, same shape as `df-fortress.service`/`df-vnc.service`):
```
ssh -N -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes \
    -R 127.0.0.1:5900:127.0.0.1:5900 \
    -i <dedicated-key> relay-user@relay-host
```
`-R 127.0.0.1:5900:127.0.0.1:5900` asks the relay's `sshd` to listen on the relay's own `127.0.0.1:5900` (loopback only — never the relay's public interface, so nothing new is exposed there) and forward anything that connects to it, back through the SSH session, to `127.0.0.1:5900` on VM 103, where the existing `df-vnc.service`'s `x11vnc` is already listening. `websockify` on the relay then points at `localhost:5900` — the exact same invocation `cmd_webvnc` already runs today, just pointed at a tunneled port instead of a local one.

**Why this sidesteps §3/§4 entirely**: there is no VNC-repeater protocol anywhere in this design. `x11vnc` never needs `-connect`; it keeps running exactly as `cmd_vnc` already configures it (`-rfbauth ... -rfbport 5900 -viewonly -forever -shared -noxdamage`, confirmed by reading `X11VNC_UNIT` in `scripts/install_df.py`). The relay's `websockify` never needs to understand an `ID:` handshake, `repeaterID`, or any VNC-specific reverse-connect framing — from its point of view it is doing precisely what `cmd_webvnc` already does, against `localhost` instead of a LAN IP. SSH's own remote-port-forwarding (`-R`) is what makes "VM 103 dials out, relay never dials in" true; it has been a stable, unglamorous part of the SSH protocol for decades, with no VNC-specific edge cases to discover.

**What's actually new to build**, compared with what's already running:
1. One `systemd` unit on VM 103 running the `ssh -R` command above, with `Restart=on-failure` (same pattern as `X11VNC_UNIT`).
2. One dedicated SSH keypair, used for nothing else, and restricted on the relay side via `authorized_keys`:
   ```
   command="echo restricted",no-pty,no-agent-forwarding,no-X11-forwarding,permitopen="127.0.0.1:5900" ssh-ed25519 AAAA... df-vnc-tunnel
   ```
   `permitopen` is the load-bearing clause: even a fully compromised copy of this key can only ever forward to `127.0.0.1:5900` on the relay — it cannot open a shell, forward X11, or reach any other port. This is standard OpenSSH `authorized_keys` functionality (`man sshd` — `AUTHORIZED_KEYS FILE FORMAT` section), not a third-party feature; not independently re-verified against a live sshd in this pass, but it is core, long-documented OpenSSH behavior with no version-specific ambiguity worth flagging.
3. `websockify`/`novnc` on the relay, `apt`-installed exactly as `cmd_webvnc` already does on VM 103 — this is literally the same package pair this project has already checked availability for and is already running in production on VM 103, just needing the same check repeated against whatever distro the relay runs (almost certainly the same Ubuntu LTS family, in which case the availability finding already carries over).

**Direct comparison:**

| | Repeater chain | Reverse SSH tunnel |
|---|---|---|
| New protocol surface | UltraVNC repeater ID handshake (undocumented interop with noVNC beyond one parameter name) | None — plain SSH port forwarding |
| Changes to already-working `df-vnc.service` | Yes — `x11vnc` needs `-connect repeater=...` added | None — `x11vnc` config untouched |
| Custom/unmaintained code introduced | Yes — a 2010-vintage Perl script with no upstream support | None — `ssh`, already a dependency of this entire project's tooling |
| Verified working end-to-end anywhere found | No | Not benchmarked in this pass, but the mechanism (SSH remote forwarding) has no novel risk requiring end-to-end proof — it is what `-R` has always done |
| New attack surface on the relay | A repeater daemon on 1-2 ports, no auth beyond the ID string itself (anyone who learns/guesses the ID could request that stream — the repeater as documented does not password-gate the pairing) | One restricted SSH key, scoped by `permitopen` to a single loopback port; VNC's own password (already required by `df-vnc.service`) still gates the actual view |
| Reuses existing project idioms | No | Yes — `ssh_guest`/`scp_from` in `provision_vm.py`/`install_df.py` already make SSH the project's standard remote-control transport |

**Confidence: high.** SSH remote port forwarding and `authorized_keys` restriction directives are core, decades-stable OpenSSH behavior, not an edge case needing a live test to trust; the comparison table's factual rows are drawn directly from what was read in §2-§4 plus the actual `X11VNC_UNIT`/`NOVNC_UNIT` code in this repo.

---

## 6. What the relay VM itself minimally needs

**OS/packages**: any current Ubuntu or Debian LTS is sufficient — this project already standardizes on Ubuntu 24.04 LTS for VM 103 (`decisions/DECISIONS.md` 2026-09-08 row on guest OS), and matching that on the relay avoids learning a second distro's quirks for no benefit. Needed packages: `openssh-server` (present by default on any cloud image), `novnc` + `websockify` (already confirmed `apt`-available on `noble/universe` for VM 103's own install — not re-verified against whatever specific image the relay would use, but there is no reason to expect a different result on the same distro family), and a TLS-terminating reverse proxy in front of `websockify` — `nginx` or `caddy`, both standard `apt`/`snap` packages — so the browser-facing side is `https://` rather than exposing `websockify`'s own listener straight to the internet. `certbot` (or Caddy's built-in ACME client) for a Let's Encrypt certificate.

**Static IP vs. domain**: this is not really an either/or — a workable public relay needs **both**, but obtaining them is normal, not a special requirement. Essentially every commodity VPS product (a small droplet/instance from any mainstream provider) ships with a static public IPv4 for the life of the instance; that's the default, not an add-on to hunt for. What's actually needed on top is one DNS record — an `A` record for a subdomain such as `df.willsmith.nz` pointing at that static IP — which is normal DNS administration on a domain the user already controls (`willsmith.nz`, per `docs/PURPOSE.md`'s own reference to it as the intended public face for streaming). **Not independently verified in this pass**: how DNS for `willsmith.nz` is actually managed today (registrar, whether Cloudflare or similar sits in front of it) — this repo's own tracked files don't establish that (the 2026-09-08 report already flagged the parallel gap for the screenshot-ingest side, and it applies identically here).

**Resource requirements**: this is a lightweight relay, and the primary source for that claim is what it's actually asked to do — hold one SSH session open, and relay one TCP stream's worth of RFB traffic (§7) per concurrent browser viewer through `websockify` and `nginx`. Neither task is CPU- or memory-intensive in the way video *encoding* would be (§3c of the 2026-09-08 report already flagged x264 encoding cost as the one number needing an actual benchmark; nothing here does that kind of work — `websockify`, unlike `ffmpeg`, does not transcode, it relays already-encoded RFB rectangles). A reasonable estimate, **not benchmarked, general knowledge about these specific tools' resource profiles**: the smallest paid tier from any mainstream VPS provider (roughly 1 vCPU / 512MB-1GB RAM) is comfortably sufficient for a handful of concurrent viewers; this is not a number this report can respect as measured, only as a confident engineering estimate given what the software actually does.

**Security hardening specific to a genuinely public-facing box** — a materially different threat model from VM 103, which is worth stating plainly rather than copying VM 103's posture across:
- **SSH**: key-only auth (`PasswordAuthentication no`), no root login (`PermitRootLogin no`), `fail2ban` (or `sshd`'s own rate-limiting) against brute-force scanning, which any box with a public IP and port 22 open receives from the first hour it exists — this is closer to "certain" than "estimated," it's the well-documented baseline reality of any internet-facing sshd.
- **Firewall**: `ufw`/`nftables` allowing only 22 (SSH, for the tunnel) and 443 (HTTPS, for viewers) inbound — nothing else. Note the real operational wrinkle: SSH on the relay generally **cannot** be IP-restricted to "only VM 103," because VM 103's outbound connection leaves from the user's home router's WAN address, which is very likely dynamic (not established in this repo's tracked files whether the home connection has a static IP — flagged as open, matching the spirit of `home-lab`'s own IP-allocation obligations, though that's a home-lab-owned fact this repo shouldn't guess at). The `permitopen`-restricted key (§5) is what actually bounds the blast radius here, since IP-allow-listing isn't reliably available.
- **Unattended upgrades: the opposite stance from VM 103.** Row 120 of `decisions/DECISIONS.md` deliberately disables automatic upgrades on VM 103 because a live fort can't tolerate a library shifting under it for a month. The relay has no equivalent constraint — it runs `sshd`, `nginx`, and `websockify`, none of which hold irreplaceable state — so it should very likely run `unattended-upgrades` normally. Copying VM 103's "pin the box, rebuild between forts" posture onto the relay would be applying the wrong lesson to a box with a completely different risk profile: a public sshd that never gets security patches is a real, ongoing exposure, and the relay has nothing to lose by patching that VM 103 has by not patching.
- **Disposability**: since the relay holds no state of its own (it neither runs the game nor stores saves), it should be treated as cattle, not pet — cheap to rebuild from a small provisioning script in the same spirit as `provision_vm.py`, so a compromised or drifted relay is a rebuild, not an incident to painstakingly clean.

**Confidence**: the SSH/firewall/patching recommendations are standard, well-established sysadmin practice, not something this pass benchmarked against a live box — flagged accordingly, same as the 2026-09-08 report flagged its own unbenchmarked ffmpeg CPU claim.

---

## 7. Bandwidth and cost: live VNC vs. periodic screenshots

**Not measured — no relay or live VNC session exists to test against.** Estimated from the same reasoning the 2026-09-08 report used for its ffmpeg estimate, extended to RFB specifically:

RFB is incremental (only changed rectangles are re-sent), and `x11vnc`'s encoding choice (Tight, by default, over websockify/noVNC) is broadly comparable in bandwidth character to a low-framerate video codec for a mostly-static scene — this is the same "single-core clock is everything, but the scene itself changes slowly" reality the 2026-09-08 report already established for VM 103's `FPS_CAP`. A reasonable estimate for a 1280x720 DF window, at rest most of the time with occasional camera pans/redraws (`spectate` actively moving the view, per that report's own recommendation): **tens of kbps at rest, spiking to perhaps 1-2 Mbps briefly during a full-screen redraw or pan**, averaging out to something in the same "a few hundred kbps sustained" order of magnitude the 2026-09-08 report already used for ffmpeg. At 300 kbps sustained continuously, 24/7, one viewer's month of data is:

```
300 kbit/s ÷ 8 = 37.5 KB/s
37.5 KB/s × 86,400 s/day × 30 days ≈ 92 GB/month
```

This comfortably fits inside even the smallest VPS tiers' bandwidth allowances (commonly 500GB-1TB+/month on budget tiers, multiple TB on mid tiers) — **bandwidth is not the constraint here either**, matching the 2026-09-08 report's conclusion for screenshots and ffmpeg alike.

**The one cost dimension the screenshot approach doesn't share, worth naming plainly**: `websockify` is a per-connection relay, not a broadcast. Each concurrent browser viewer gets its own independent RFB session end to end (VM 103's `x11vnc` → tunnel/repeater → relay's `websockify` → that browser), so the ~92 GB/month figure above scales roughly linearly with concurrent viewers, and so does the CPU cost of `x11vnc` maintaining multiple independent RFB sessions (mitigated somewhat by `-shared`, which lets one framebuffer poll serve several viewers, but each still gets its own encoded stream out). A handful of simultaneous viewers stays trivial; tens to hundreds would not, and would need a genuinely different architecture (an HLS/RTMP-style one-encode-many-viewers pipeline, which is exactly the "real video" upgrade path the 2026-09-08 report already scoped and declined to build yet). The screenshot-push design has no equivalent scaling concern: one static file, served by whatever's already serving the rest of the site, to any number of viewers, at whatever caching layer the site already has.

**Confidence**: the per-connection, non-broadcast nature of `websockify` is a structural fact about how it works (confirmed by what it is — a WebSocket-to-TCP proxy, not a media server with fan-out), not an estimate. The specific kbps figures are estimates, explicitly flagged, same caveat as the 2026-09-08 report's own screenshot-size estimate.

---

## 8. Minimum viable build, if this is pursued

Following this project's stated Now/Next/Later discipline and the 2026-09-08 report's own "smallest working version first" framing:

1. Provision a small relay VM at any mainstream VPS provider (outside the home-lab estate, per the task's own framing — this repo has no tooling for that provisioning and none is proposed here, since it's a different provider's API entirely).
2. On the relay: `apt install openssh-server nginx novnc websockify fail2ban ufw`; `ufw allow 22,443`; disable password auth; get a Let's Encrypt cert for `df.willsmith.nz` (or whatever subdomain); `nginx` reverse-proxies `443` to `websockify`'s port.
3. Generate a dedicated keypair; install the public half in the relay's `authorized_keys` with the `permitopen="127.0.0.1:5900"` restriction from §5.
4. On VM 103: a new `systemd` unit (same authoring pattern as the existing units in `install_df.py`'s `cmd_systemd`) running the `ssh -N -R ...` command from §5, `Requires=df-vnc.service` (the tunnel is pointless without something listening on the port it's forwarding).
5. `websockify` on the relay targets `localhost:5900` — identical invocation to `NOVNC_UNIT` in `install_df.py` today, just against the tunneled port.
6. Point `df.willsmith.nz` at the relay's `vnc.html`, same page `cmd_webvnc` already serves on the LAN, now reachable from anywhere.

**Explicitly not part of this MVP, and not recommended to attempt first**: the repeater chain from §3/§4. If genuine multi-viewer scale is ever needed, the right next step is the video-encode-once, distribute-many upgrade path the 2026-09-08 report already scoped (`ffmpeg x11grab` → HLS/RTMP → a media server), not a repeater — the repeater solves NAT traversal for a single point-to-point VNC session, which the SSH tunnel already solves more simply; it does nothing for the fan-out problem that would actually matter at higher viewer counts.

---

## 9. Confirmed vs. estimated vs. open, summarized

**Confirmed (read from primary sources — x11vnc's actual documented option text across two independent mirrors, the actual Perl source and commit history of `misc/ultravnc_repeater.pl`, noVNC's actual `EMBEDDING.md` text, and this repo's own `scripts/install_df.py`):**
- `x11vnc -connect host:port` and `x11vnc -connect repeater=ID:1234+host:port` are both real, documented options with the exact syntax quoted in §2.
- A working, GPLv2, Linux-runnable UltraVNC-repeater reimplementation exists (`LibVNC/x11vnc`'s `misc/ultravnc_repeater.pl`) and is protocol-compatible with x11vnc's `-connect repeater=` mode — but its own code has not been touched since 2010-09-10.
- noVNC ships a `repeaterID` client parameter documented for exactly this scenario, but the only concrete real-world attempt to use a repeater with noVNC/websockify found in this pass (GitHub `novnc/noVNC` issue #422) ended in an unresolved protocol failure with no maintainer confirmation of a working configuration.
- `X11VNC_UNIT` and `NOVNC_UNIT` in `scripts/install_df.py` today run plain listening `x11vnc` (no `-connect`) and `websockify` against `localhost`, respectively — the reverse-SSH-tunnel design changes neither, it only adds a tunnel in front of the port they already use.

**Estimated, explicitly not measured:**
- RFB bandwidth for this specific scene (tens of kbps to a couple Mbps in bursts, ~300kbps-order sustained average) — no live VNC session was run to check this.
- Relay VM resource sizing (1 vCPU/512MB-1GB class) — reasoned from what `websockify`/`nginx`/`sshd` actually do, not benchmarked.

**Genuinely open, needs the user's input or a live-system check rather than more research:**
- Whether `willsmith.nz`'s DNS is under the user's direct control in a way that makes adding an `A` record for a relay subdomain trivial, or whether something (a registrar panel, Cloudflare, a Coolify-managed zone) sits in the way — the same open question the 2026-09-08 report already flagged for the screenshot-ingest endpoint, unresolved here too.
- Whether the home connection VM 103 sits behind has a static enough WAN IP to matter for any future IP-based hardening of the relay's SSH port (§6) — a home-lab fact this repo shouldn't assert on its own.
- Whether live video via VNC is worth the complexity at all next to the already-half-built, already-cheaper screenshot push — this report can compare the two paths honestly (§7) but the actual go/no-go on "is genuinely live video worth it" is the user's call, and nothing found here should be read as quietly resolving that in either direction.

---

## 10. Recommendation, stated plainly

**If the harder path is pursued: reverse SSH tunnel, not the VNC-repeater chain.** The repeater chain's own documentation and the one real bug report found in this pass both point at the same conclusion — the pieces exist, they were plausibly designed to interoperate, and nobody has demonstrably made them interoperate. Building on top of a sixteen-year-untouched script and a one-line-documented noVNC parameter, with no working reference anywhere, is a real ongoing maintenance and debugging liability for a solo-maintained project, for no capability the SSH tunnel doesn't already provide. The SSH tunnel needs nothing new to be trusted — it's the same transport this project already uses everywhere else, it doesn't touch the already-verified, already-running `df-vnc.service`/`df-webvnc.service` configuration at all, and its one new attack surface (a single SSH key) can be scoped down to almost nothing with a standard, well-documented `authorized_keys` restriction.

**Whether to build either one is the harder question, and this report's honest answer is: probably not yet, and the reasoning is the same reasoning §2 of the 2026-09-08 report already reached for video generally.** The screenshot push is most of the way built already (`cmd_stream`, blocked only on R2 credentials per `Working.md`), needs no new public-facing host, no SSH key to secure, no relay to patch and monitor indefinitely, and per that report's own numbers, isn't meaningfully worse at conveying "the fortress is alive" than continuous video would be, given how slowly a fort's actual composition changes at this project's `FPS_CAP`. A live relay adds a second machine that must be kept patched forever, a second thing that can go down independently of VM 103, and (per §7) a viewer-count-scaling cost the screenshot path doesn't have — real, ongoing costs for a capability (motion, not just freshness) whose value is more about matching the user's stated preference ("watch the stream, real time") than about anything a viewer would concretely lose without it.

**That said — this is explicitly the user's call, already made once** ("the user was offered [the simple option] and explicitly chose the harder one instead"), and this report isn't trying to relitigate it by default. If the decision stands: build the SSH tunnel, not the repeater, for the reasons in §5, and treat the relay as disposable, patched, and minimally-scoped infrastructure per §6 — a genuinely different posture from VM 103's "pin and rebuild between forts" stance, because it's a genuinely different threat model. If the decision is revisited: the screenshot path is sitting most of the way finished already, blocked on nothing architectural, only on R2 credentials.
