# Watching the Fortress Live: Capturing `df-colony-01`'s Framebuffer and Getting It to willsmith.nz

Date: 2026-09-08
Scope: how to let the user watch VM 103's Xvfb display (`:99`) via a website they already host (`willsmith.nz`), once a fort exists. Covers capture mechanism, relay architecture given the VM's LAN-only stance, and a bandwidth/CPU reality check.
Status: **research/design only.** Nothing was installed, started, or configured on VM 103. Everything below is either (a) read from this repo's own docs and decision register, (b) read from the DFHack docs actually installed at `C:\Program Files (x86)\Steam\steamapps\common\DFHack\hack\docs\docs\tools\` on the local Windows machine, (c) confirmed by read-only SSH (`ssh -i .../df_overseer_ed25519 df@<df-vm-ip>`, no install/start/config commands run) against the live VM, or (d) explicitly flagged as an estimate/inference where nothing live could be checked.

---

## 1. The answer, up front

**Recommendation: periodic-screenshot push, not video, and not VNC, for the public-site leg.** Concretely: a systemd timer on VM 103 runs `import -display :99 -window root` (ImageMagick) or `ffmpeg -f x11grab ... -frames:v 1` every 10–30 seconds, POSTs the PNG outbound over HTTPS to an ingest endpoint on willsmith.nz, and the site polls for the latest image. No inbound port is ever opened on the VM or the router. This reaffirms the shape of the 2026-08-25 decision-register row ("periodic screenshot + live dashboard, not 24/7 video") rather than overturning it — see §2 for why the user's "watch the stream, real time" framing doesn't actually require video once the numbers are worked through, and why the row's `proposed` status can now move toward `accepted` on cost/complexity grounds, though it's still the user's call.

**None of the three candidate capture tools — `x11vnc`, `ffmpeg`, ImageMagick's `import`/`xwd` — are installed on VM 103.** Confirmed live 2026-09-08:

```
$ which x11vnc ffmpeg import xwd Xvfb
/usr/bin/Xvfb
$ dpkg -l | grep -iE 'x11vnc|ffmpeg|imagemagick|xvfb'
ii  xvfb   2:21.1.12-1ubuntu1.6   amd64   Virtual Framebuffer 'fake' X server
```

All three are available from the standard Ubuntu 24.04 (`noble`) `universe` repo already configured on the box, confirmed via `apt-cache policy` (read-only, installs nothing):

```
x11vnc: Candidate 0.9.16-10        (noble/universe)
ffmpeg: Candidate 7:6.1.1-3ubuntu5 (noble/universe)
imagemagick: Candidate 8:6.9.12.98+dfsg1-5.2build2 (noble/universe)
```

So this is a genuinely greenfield build: nothing to reconcile with an existing capture setup, and no package-availability risk.

**DFHack's `spectate` tool is real, available in this build, and relevant — but not as a capture mechanism.** It is an in-game camera director, not a screen-recorder. Read from the installed docs (`hack/docs/docs/tools/spectate.txt` and `tools/gui/spectate.txt`, both `Tags: fort | inspection | interface`, no `unavailable` tag): `spectate` locks DF's own camera to follow whichever dwarf/animal/hostile it judges interesting, switching targets automatically (`follow-seconds`, default 10s), with a preference system (`prefer-conflict`, `prefer-new-arrivals`, `prefer-nicknamed`) and optional on-screen tooltips (name, job, mood) via its `spectate.tooltip` overlay. It has no relationship to VNC, `ffmpeg`, or file output — it just moves what the SDL renderer draws into the Xvfb framebuffer. **The practical implication: `spectate` and a capture tool are complementary, not alternatives.** Without `spectate` enabled, a periodic screenshot is as likely to land on an empty stretch of empty stone as on anything happening; with it enabled (`enable spectate` via `dfhack-run`), the camera actively hunts for action before every capture. Worth enabling regardless of which capture mechanism is chosen — it's the cheapest lever for making any given screenshot or frame worth looking at, and it's a one-line `dfhack-run` call, not a build item.

---

## 2. Reopening the 2026-08-25 decision, honestly

`decisions/DECISIONS.md` row 24 records **"Streaming to the site: periodic screenshot + live dashboard, not 24/7 video"**, status **`proposed`**. Its reasoning: at `FPS_CAP:5`, almost nothing changes in 30 seconds, so a still image conveys the fortress about as well as video at a fraction of the cost, and the site's distinctive value is the chronicle/reasoning beside the image, not the image itself.

The user's new phrasing — "watch the stream," "real time" — is worth taking at face value rather than assumed away. Two things change the calculus from what the 2026-08-25 row considered, and one thing doesn't:

- **What doesn't change:** the underlying claim that a fort's *composition* (what's built, who's where, what's under siege) moves slowly at low `FPS_CAP` is still true and still the dominant factor for whether a viewer feels like they're watching something live.
- **What's worth adding, not previously in the row:** `FPS_CAP` and `G_FPS_CAP` are separate tokens (`docs/PURPOSE.md`, verified against both installs), and this project's design leaves `G_FPS_CAP` at the default 50 — i.e., **rendering stays smooth even while simulation is capped low.** That means individual sprites can still be mid-animation (a dwarf mid-step) in any single captured frame, so a screenshot cadence of 10-30s isn't literally freezing "nothing happening" — it's sampling a scene whose macro state changes slowly but whose micro rendering doesn't. This is an inference from the documented `FPS_CAP`/`G_FPS_CAP` split, not something independently observed by watching the display animate (no capture tool is installed to check this against — flagged as unverified). Practically it argues for a *shorter* interval than 30s (10-15s) rather than for switching to video, since the game's own render loop is already doing the "smoothness" work; sampling more often mostly buys catching more distinct compositions, not smoother motion.
- **What does change: cost of a "real" stream is now cheap enough to name concretely** (§4 below) rather than staying a vague "video is expensive" assumption — turns out the honest number is "a few hundred kbps, continuously," which is not actually expensive on almost any consumer connection in 2026. So the 2026-08-25 row's *cost* argument for screenshots over video is weaker than it reads; the stronger argument for screenshots is the **CPU-contention** one (§4), which the row didn't emphasize but which matters more given `docs/PURPOSE.md`'s own statement that DF is single-threaded and "single-core clock is everything."

**Recommendation given all of this:** keep the periodic-screenshot architecture, but tighten the interval to 10-15s rather than 30s, and treat continuous video (ffmpeg x11grab → RTMP/HLS) explicitly as a documented, buildable *upgrade path* rather than a rejected option — which is what the original row already said ("treat real video as an upgrade if the still image proves too static"). This report doesn't overturn that structure; it gives it a cost basis so the `proposed` status can be evaluated rather than merely asserted. The row should move to `accepted` (or `accepted` with today's date noting the re-examination) once the user signs off, since nothing found here weakens the original reasoning — it strengthens it with actual numbers.

---

## 3. Capturing the Xvfb framebuffer: three real options

### 3a. Periodic screenshot: `import` (ImageMagick) or `xwd`

The simplest mechanism, and the one this report recommends for the MVP. Two sub-options, both apt-installable and confirmed available (§1):

- **ImageMagick's `import`**: `import -display :99 -window root /path/to/shot.png` captures the whole root window of display `:99` straight to PNG, no intermediate format, no extra conversion step. This is the standard, well-documented Linux headless-screenshot idiom and needs no X client library beyond what `import` itself links.
- **`xwd`**: X's own window-dump utility, `xwd -display :99 -root -out shot.xwd`, produces the native XWD raster format — uncompressed, so a second step (`convert shot.xwd shot.png`, also ImageMagick) is needed to get something small and web-servable. Two tools instead of one, no real advantage over `import` here since `import` already wraps the equivalent XGetImage call and writes PNG directly.

**Verdict: `import` alone, no `xwd`.** One package (`imagemagick`), one command, PNG output that's already reasonably compressed and directly usable by a browser `<img>` tag with no server-side conversion step.

### 3b. `x11vnc` — VNC server on the Xvfb display

`x11vnc -display :99` exposes `:99` as a standard VNC (RFB protocol) server. This is the "VNC → Pi → monitor, zero build" option named in `docs/PURPOSE.md`'s open questions. It's a strong fit for that specific use case — a Raspberry Pi on the same LAN running a VNC client, or a monitor in the room — because:

- It needs no relay: Pi and VM are both on the LAN, one TCP connection, done.
- "Zero build" is accurate: `x11vnc` plus any VNC client is off-the-shelf, no code to write.
- RFB's incremental-update design (only send changed rectangles) is genuinely bandwidth-efficient for a mostly-static scene, more so than either screenshots or video in principle.

**It's a weaker fit for the public-website leg specifically**, for reasons distinct from the local-display case:

- VNC is not natively browser-embeddable. Getting it into a web page needs `noVNC` + `websockify` bridging the RFB protocol to a WebSocket the browser can consume — a second piece of software, run somewhere, that itself needs a persistent connection.
- It's a continuously-open connection, not a periodic push. That's exactly the shape the LAN-only containment stance (§4) is built to avoid: either the VM must accept the persistent connection inbound, or the connection has to be tunneled outbound continuously, which is heavier than "wake up every 15 seconds, POST a PNG, sleep" both operationally and in terms of what's running all the time.
- It doesn't naturally produce an artifact (a file) that a static or lightly-dynamic web page can just serve — it's a live protocol session, which pushes complexity onto the site side that a `<img src="latest.png">` tag doesn't have.

**Verdict:** good, arguably the best answer for the wall-display/Pi leg of `docs/PURPOSE.md`'s open question ("which display to test first"); not recommended for the willsmith.nz leg. These can both be true — the two surfaces don't have to share one mechanism, and PURPOSE.md's own framing ("one build serves four surfaces") is an aspiration, not a constraint this report needs to preserve if the constraints genuinely differ. This resolves that open question partially: pick VNC for the local surface, periodic-screenshot-push for the public one.

### 3c. `ffmpeg` with `x11grab`

`ffmpeg -f x11grab -video_size 1280x800 -i :99 ...` captures the X display as a video source, either to a local file, an HLS segment sequence, or an RTMP push to something that can serve it (a self-hosted Owncast instance being the obvious open-source target, matching `docs/PURPOSE.md`'s streaming table's "24/7 video (OBS → Owncast/Twitch)" row).

This is the real-video path, and it works technically — `x11grab` is a standard, well-supported ffmpeg input device, not an exotic one. The open costs are:

- **Continuous CPU for encoding**, competing with DF's own single-threaded simulation on a host `docs/PURPOSE.md` already characterizes as "single-core clock is everything." This wasn't measured on this VM (ffmpeg isn't installed, and installing/running it was out of scope for a read-only pass) — flagged explicitly as **not verified**, only estimated from general x264 encoding cost knowledge: a low-resolution, low-framerate (1-5fps) encode at a fast preset typically costs low single digits of a percent of one modern core, but "modest" on a modern core is a different claim than "modest against a game that's already trying to use that exact core for its own single-threaded tick loop." This is the concrete thing to benchmark before adopting video, not assume.
- **A server-side piece that doesn't exist yet.** Owncast (or equivalent) is not confirmed running anywhere in this project's tracked infra (checked `infra/README.md`, `infra/local.hardware-plan.md`, `infra/local.proxmox-access.md`, `.env` — no mention of Owncast, RTMP, or a media server). Standing this up is real, non-trivial build work, versus the screenshot path's website-side requirement of "accept a PUT/POST and serve the latest file."
- **Still needs the same outbound-relay treatment as everything else** (§4) — RTMP push is itself an outbound connection from the VM, so it doesn't change the LAN-only story, but it is a *persistent* outbound connection rather than a periodic one, closer in operational shape to VNC than to screenshot-push.

**Verdict:** the correct tool if/when video is adopted as the upgrade path §2 describes, but not part of the MVP. Worth a scoped benchmark (measure actual CPU delta on this exact host, with DF running, before deciding) rather than building the whole media-server side speculatively.

---

## 4. Getting it to the website: the relay question

VM 103 has no public IP and is reached only over the tailnet/LAN (`infra/README.md`; consistent with `decisions/DECISIONS.md` row 120, which states the fortress VM's whole security containment rests on being "LAN-only and cheap to rebuild" — "the project's whole thesis," in the register's own words). Any live-viewing design has to route around that, not through it.

**Two architectural directions, with sharply different cost:**

**A. Push (recommended).** VM 103 initiates an outbound HTTPS connection on its own timer and sends the current screenshot to an ingest point on willsmith.nz. No inbound port is opened on the VM, the router, or anywhere in the path — the VM never accepts a connection from the internet, it only makes one. This is the architecture that requires zero change to the LAN-only stance recorded in row 120, and it's the natural fit for a systemd timer that already exists as a pattern in this repo (`df-fortress.service`/`df-xvfb.service`, `decisions/DECISIONS.md` row 95). Concrete implementations, roughly in order of build simplicity:
  - `curl -F file=@shot.png https://willsmith.nz/df-ingest` against a small upload endpoint (needs one to exist on the site — see the open question below).
  - `rsync`/`scp` over SSH to the web host, if the web host accepts SSH from this key or a dedicated one — simplest possible "ingest," no new server code, just a target directory the site already serves.
  - A PUT to an S3-compatible object store (e.g., a bucket willsmith.nz's frontend reads from directly) with a long-lived or periodically-rotated credential scoped to just that bucket.

**B. Pull.** Something on the public side reaches into the VM to fetch the current frame. This is the wrong direction given the LAN-only stance, for the reason the task brief already names: it requires either (a) opening inbound access on the VM/router, which is a real, direct reversal of row 120's containment model, not a footnote, or (b) the pulling side being tailnet-joined so it can reach `<df-vm-ip>` without a public route — which pushes the question onto **where willsmith.nz is actually hosted**, and that's genuinely unknown from this repo's tracked files (see below). If the site's host isn't already tailnet-enrolled, giving it that enrollment is itself a new, non-trivial exposure decision (a new tailnet identity reaching into the LAN from a public-facing box) that deserves its own decision-register entry if ever pursued, not a quiet default.

**A middle case worth naming explicitly rather than glossing over: Tailscale Funnel (or an equivalent, e.g. Cloudflare Tunnel).** Funnel lets a tailnet device expose an HTTP(S) service to the public internet via an *outbound*-initiated connection to Tailscale's own relay — so, mechanically, no inbound firewall rule is ever added on the LAN or router, which sounds like it inherits Option A's safety property. But the effect is that VM 103 becomes a public-internet-facing HTTP endpoint in its own right, reachable by anyone with the URL, indefinitely, while it's enabled — a materially different exposure than "the VM makes one outbound POST every 15 seconds and otherwise talks to nobody." Whether that distinction matters is a judgment call for the user, not something this report should resolve by default; it's flagged here specifically so it isn't adopted as "basically the same as push" without that call being made on purpose.

**Recommendation: Option A, plain outbound push**, specifically because it's the only one of the three that requires no new standing exposure of any kind and no new judgment call about what "LAN-only" is allowed to mean — it just makes VM 103 into a client of an HTTPS endpoint, the same shape of thing `provision_vm.py`/`install_df.py` already do when they talk to the Proxmox API or fetch a cloud image.

**Open question this report cannot close: what does willsmith.nz actually run today?** `CLAUDE.md`'s file-listing prose and `.gitignore`'s comments both mention "Coolify" in the same breath as Proxmox/IPs as a category of infra specifics that would need to stay out of the public repo — but no `infra/local.*` file, and no key in `.env`, actually names a Coolify instance, a deploy target, or any detail about how willsmith.nz is served. That means **it's not established from this repo's own records whether Coolify (or anything else) is actually running for willsmith.nz today**, nor whether that host is reachable from this project's tailnet. This is the single biggest open question standing between this report and an actual build — not a capture-mechanism question at all, but "where does the ingest endpoint live and what can it run." Worth asking the user directly rather than guessing further; nothing in the checked files resolves it, and guessing wrong here (e.g., building the VM-side push against assumptions about the receiving end) is exactly the kind of rework this report is meant to prevent.

---

## 5. Bandwidth and CPU: an evidence-based reality check

Following this project's own pattern of measuring rather than assuming (the worldgen memory-spike rows, `decisions/DECISIONS.md` 2026-08-27), here's what can and can't be pinned down without actually running a capture tool (none is installed — see §1, this is estimation, clearly flagged, not measurement):

**Screenshot size.** Not independently measured (no capture tool installed to test against the live display). Estimate: a 1280x800 24-bit raw frame is 1,024,000 px x 3 B = ~3.0 MB uncompressed. DF's tile-based rendering (whether the ASCII-styled Classic default or a graphical tileset) is heavy on flat, repeating regions compared to photographic content, which PNG compresses well — a reasonable estimate is **100-400 KB per screenshot**, but this is an estimate range, not a measurement, and should be checked against a real capture before being used to size anything (e.g., before picking an object-storage tier or committing to a specific interval).

**Bandwidth at various intervals**, using the 100-400 KB estimate:

| Interval | Rate (est.) | Data/day (est.) |
|---|---|---|
| 30s | 3-13 KB/s (27-107 kbps) | 288-1152 MB |
| 15s | 7-27 KB/s (53-213 kbps) | 576-2304 MB |
| 10s | 10-40 KB/s (80-320 kbps) | 864-3456 MB |

All of these are trivial against any consumer upload connection in 2026 and against object-storage egress costs at this project's scale — the honest conclusion is that **bandwidth was never actually the constraint**, for either screenshots or, per the ffmpeg discussion in §3c, low-framerate video (a few hundred kbps sustained is the same order of magnitude as the 10-15s screenshot cadence above). This matters for §2: it means the case for screenshots over video rests on CPU contention and build simplicity, not on the bandwidth argument the original 2026-08-25 row leaned on.

**CPU/RAM budget context**, from this project's own established numbers (`decisions/DECISIONS.md` rows 48/65/84, `docs/PURPOSE.md`): worldgen peak RSS was measured at 561 MB against a VM sized 4096 MB/2048 MB balloon floor on a host whose available memory has been observed swinging between roughly 4.8 and 13.7 GB across a few days. **A live check today (2026-09-08) found the guest itself currently reporting 5.8 GiB total memory** (`free -h`: `Mem: total 5.8Gi, used 507Mi, available 5.3Gi`) with DF's `dwarfort` process using 255 MB RSS at 42.5% CPU while sitting at the title/world-loaded state with no fort embarked yet — a different total than the 4096 MB figure recorded in the decision register. This discrepancy is noted but not explained here (possibly a balloon-driver reporting difference, possibly a config change made after the 2026-08-27 sizing rows that isn't reflected in the docs) — **flagged as worth a memory-doc audit**, per this repo's own standing rule ("if the docs and the actual repo state disagree, flag it and suggest a memory audit rather than silently patching over it"), separate from this report's actual scope. For the purposes of this report: there is currently more headroom than the documented 4096 MB figure would suggest, which if anything strengthens the case that a lightweight periodic-screenshot process (a few MB RSS, sub-second CPU burst once per interval) is not a meaningful competitor for resources — the honest open risk is specifically continuous video encoding (§3c), not screenshotting, and that's exactly the item flagged as needing its own benchmark before being adopted.

**A once-per-interval screenshot process, concretely:** `import` runs, captures, writes a file, and exits — it does not hold a core busy the way a continuous ffmpeg encode does. At any interval from 10-30s, its CPU footprint is a fraction of a second of work spread across a window during which DF's own simulation is doing far more continuous work; this is a reasonable inference from how the tool works (a single XGetImage-equivalent call plus PNG compression of one frame), not a live measurement, but it's a qualitatively different claim from ffmpeg's continuous-encode cost and doesn't carry the same "benchmark before adopting" caveat as strongly.

---

## 6. Minimum viable build vs. later refinement

Following this project's stated preference for a working smallest version over a complete one (`ROADMAP.md`'s Now/Next/Later structure; the build-order list in `docs/PURPOSE.md` itself is staged the same way):

**Minimum viable (what to actually build first):**

1. On VM 103: `apt install imagemagick` (confirmed available, §1).
2. A small script — a dozen lines, in the same style as `scripts/install_df.py`'s remote-script pattern — that runs `import -display :99 -window root /some/path/latest.png`, then pushes it out (`curl -F` or `rsync`, per §4's Option A) to willsmith.nz.
3. A systemd timer (or, more simply, a `cron` entry — this doesn't need the save-before-stop care that `df-fortress.service` needed, since there's no state to lose) firing every 10-15 seconds.
4. Optionally, before any of the above: one `dfhack-run` call to `enable spectate` (with `include-animals`/`include-hostiles` left at their sensible defaults) so the camera is actively pointed at something happening before the first screenshot is ever taken. This is the single cheapest quality improvement available and isn't gated on any of the build work above.
5. On willsmith.nz: whatever minimal endpoint or shared directory Option A's chosen sub-mechanism needs (an upload handler, or just a directory the existing site already serves, if `rsync`/`scp` is viable) — **this is the actual open question (§4)**, not a design decision this report can finish without knowing what's already running there.
6. On willsmith.nz: a page with an `<img>` tag pointed at the latest pushed file, refreshed on a timer (cache-busted query string) or via a trivial polling script. No websocket, no server push needed at this cadence.

**Explicitly deferred, as upgrades rather than blockers:**

- Real video (ffmpeg x11grab → RTMP/HLS → Owncast or equivalent) — gated on (a) a CPU-contention benchmark on this exact host with DF actually running, and (b) standing up a media server that doesn't exist in this project's infra today.
- Pairing the image with live chronicle/reasoning text beside it on the page — this is explicitly named in `docs/PURPOSE.md` as the actually-distinctive part of the whole idea ("nobody else's DF stream can show what the player is thinking and why"), but it's gated on the perception/agent layer existing at all, which per `CLAUDE.md`'s current status has no code yet. The screenshot pipeline above doesn't need to wait for that — it can ship and show a bare image well before there's any reasoning to show beside it.
- `noVNC`/websockify bridging for a browser-embedded live VNC session, if the still-image cadence proves genuinely unsatisfying after being tried (§2's stated fallback condition).
- The Pi/wall-display `x11vnc` leg (§3b) — a separate, LAN-only build with none of the relay complexity, worth doing independently and on its own schedule.

---

## 7. Confirmed vs. open, summarized

**Confirmed (checked against primary sources or the live VM, 2026-09-08):**
- None of `x11vnc`/`ffmpeg`/`import`/`xwd` are currently installed on VM 103; all three tool families are available via the box's already-configured `apt` sources.
- `spectate` is a camera-follow/annotation tool, not a capture mechanism — confirmed by reading its actual installed doc text, not inferred from the name.
- VM 103 is LAN-only with no public IP; a push architecture (VM-initiates-outbound) requires no change to that stance, and a pull architecture would.
- DF is currently running on VM 103 (`dwarfort` process live, Xvfb `:99` active) with a world generated but no fort embarked, matching the task brief's stated status.
- No Owncast, media server, or web-ingest endpoint exists anywhere in this project's tracked infra today.
- No record in this repo establishes what willsmith.nz's actual hosting/deploy stack is (Coolify is mentioned only as a category-name placeholder, never as a confirmed live instance).

**Estimated, explicitly not measured:**
- Screenshot file size (100-400 KB range) and the bandwidth table derived from it.
- ffmpeg x11grab's CPU cost on this specific host — flagged as the one number that should be benchmarked before video is adopted, not assumed from general knowledge.

**Genuinely open, needs the user's input rather than more research:**
- What willsmith.nz actually runs today, and therefore what the ingest side of the push architecture should target (§4's closing question) — this is the one thing blocking a concrete first commit, more than any capture-tool decision.
- Whether the 2026-08-25 decision-register row (streaming: screenshot not video) should now be marked `accepted` given this report's numbers, and at what interval (10s, 15s, 30s) — a judgment call this report has narrowed but not made.
- Whether a live discrepancy noticed in passing (VM 103 currently reporting 5.8 GiB total memory against the decision register's documented 4096 MB) needs its own memory-doc audit, per this repo's standing rule for docs/reality disagreements — flagged here, not resolved, since it's outside this report's scope.
