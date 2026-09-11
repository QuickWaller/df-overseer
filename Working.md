# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.

## RESOLVED 2026-09-11: VM 103 outage from cluster quorum loss, fort back up

**Fully resolved.** User SSH'd into SRV-01 directly and ran `pvecm expected
1` (the same non-persistent override used in the 2026-09-02 incident,
confirmed via `pvecm status`: Quorate went No → Yes). `provision_vm.py
start --vmid 103` then succeeded. `install_df.py verify` came back all
PASS (dwarfort running, RPC listening). The fort itself needed one more
step beyond the VM being up: `df-fortress.service` starts DFHack but
lands at the **title screen**, not an auto-loaded fort — clicked "Continue
active game" via `df-overseer-ui.lua`; the tool's own success-check
reported FAIL (a known, pre-existing flaw — text-disappearing isn't a
reliable signal here) but the actual screen type confirmed it worked:
`viewscreen_titlest` → `viewscreen_loadgamest` → `viewscreen_dwarfmodest`.
Final state confirmed directly, not assumed: Uniboslan/Ragwind, Year 30,
Mid-Summer, population 7 intact, `pause_state=true`, active slot
`autosave 2` — exactly the paused state it was left in before the
shutdown. User also separately confirmed the public noVNC feed is working
again (it had looked broken mid-incident, most likely just showing the
idle title screen through the Xvfb-restart window, not an actual fault in
the VNC/tunnel/relay chain itself — `curl` of both the public and admin
hostnames returned their expected codes, 200 and 302, throughout).

**Caution worth carrying forward, from home-lab-29**: the quorum override
is temporary and non-persistent — `corosync.conf` on disk still says
`expected: 2`, so it reverts whenever SRV-01 reboots or SRV-02 actually
rejoins the ring. If SRV-02 comes back while the override is still active,
there's a known small risk of the two nodes disagreeing (a `cfs-lock` hang
happened once before from exactly this). Not something to act on from
here, just context if an oddly-quorum-shaped error shows up again later
today.

**Update, same session**: asked the user directly; chose to retry now
while quorum holds rather than wait. Second cycle: `shutdown` → `set-cpu`
(confirmed by read-back: `cpu=x86-64-v2-AES`) → `start` → `verify` (all
PASS) → "Continue active game" (same false-negative success-check as
before, confirmed via screen type instead) → `viewscreen_dwarfmodest`.
**Fully verified identical state to before this whole incident started**:
same 7 citizen IDs (192-198), same professions, same slot `autosave 2`,
Year 30/Mid-Summer, `pause_state=true`. `decisions/DECISIONS.md`
2026-08-28's `cpu: host` → `x86-64-v2-AES` item is now genuinely done, not
just built — closes that ROADMAP.md "Next" item for real.

<details>
<summary>Original incident writeup (kept for the full trail)</summary>

**Read this first if you're picking up this repo.** Uniboslan, the one
live fort, is currently **not running** — the VM itself is powered off and
cannot be started back up. No data was lost: DF was stopped cleanly first
(quicksave confirmed on disk via the new poll-based `systemd-stop.sh`
before SIGTERM, see below), so this is downtime, not an incident on the
fort's save.

**What happened**: attempting to apply the accepted-but-unapplied
`set-cpu` change (`decisions/DECISIONS.md` 2026-08-28) required a cold
stop/start of VM 103 to take effect. Shut it down cleanly via the new
`provision_vm.py shutdown` (ACPI, confirmed stopped). The `set-cpu` PUT
itself then failed (`500 unable to open file ... Permission denied`), and
**starting VM 103 back up also failed**: `POST .../status/start -> 500
"cluster not ready - no quorum?"`. User confirmed live: **SRV-02 is down**.
home-lab-29 (sibling session) confirms this is a known structural gap, not
a new fault — the `citadel` cluster (SRV-01+SRV-02) has never had a
QDevice (the NAS that would have hosted one was lost at auction; the Pi
3B+ fallback was never built), so any time either node drops, the cluster
goes fully inquorate and **all** `pve-guests`/`pveum`/VM start-stop blocks
indefinitely — not just snapshots, which is the only manifestation this
repo had previously documented. SRV-02 has also been separately unstable
since 2026-09-01 (home-lab's own instability tracking).

**New fact worth keeping**: quorum loss blocking VM power operations
(start/stop), not just snapshots and config writes, was not previously
confirmed in this repo — it is now, by direct API failure.

**Not this repo's to fix** — home-lab owns quorum/QDevice infra, and
every prior recovery on this cluster (the 2026-09-02 `pvecm expected 1`
override, and the most recent provisioning session) was done by the user
directly at a root shell on the host, deliberately never via an agent
SSH/API path. **Waiting on the user or home-lab to restore quorum; do
not attempt `pvecm expected 1` or any other override from an agent
session.** Once quorum is confirmed back: retry `provision_vm.py start
--vmid 103`, confirm `status/current` is `running`, confirm DF/DFHack
come back up cleanly (`install_df.py verify`), then decide whether to
still pursue `set-cpu` (built, `decisions/DECISIONS.md` 2026-08-28 row,
see "set-cpu" section below) or leave `cpu: host` alone for now given how
disruptive this attempt turned out to be.

**Real, useful thing found along the way**: while preparing this,
re-read `systemd-stop.sh` (the live `ExecStop`) and `install_df.py`'s
manual `stop --save`, and found both still had the stale flat `sleep 5`
between quicksave and SIGTERM that predates the 2026-09-11 quicksave-
timing finding (45-80s+ observed) — a real latent risk of SIGTERM'ing
`dwarfort` mid-write on the one live, irreplaceable fort. Fixed both to
poll the active slot's `world.sav` mtime for up to 90s instead (commit
`1d5ed74`). **Verified working live, for real**, stopping VM 103 for this
attempt: journal shows `quicksave confirmed on disk (slot: autosave 2)`
at +10s, then the TERM-wait loop ran its full 30s before a SIGKILL was
needed — DF genuinely still ignores SIGTERM, confirmed again, and the fix
caught it correctly rather than cutting in early.

**Also flagged, not mine to resolve**: `df-automation-da` pushed a batch
of commits to `origin/main` (`eb5f017..da73ca4`, fast-forward, no
conflicts) without asking first — this repo's rule treats `git push` as
needing explicit go-ahead each time, and that wasn't checked. Nothing
destructive (fast-forward only), told the user directly rather than
silently treating it as fine.

**Correction from `df-automation-da`, not a silent edit**: the user was
asked directly in that session ("Want me to push it...?") and said "yeah"
before that push ran — go-ahead was real, not skipped. `df-automation-e6`
had no way to see that (a peer session can only observe the resulting git
history, not another session's own conversation), so the concern wasn't
unreasonable to raise. But it does point at a real gap worth keeping,
separate from whether that specific push was approved: **a shared working
tree means whoever pushes, pushes everyone's locally-committed-but-unpushed
work, not just their own** — that push carried 5 of `df-automation-e6`'s
own commits (set-cpu, script-install, the sleep fix) alongside 2 of
`df-automation-da`'s. The user approving "push it" for one session's commit
doesn't obviously also mean "and publish this other session's separate work
too" — even though it's the same user, each session's own work arguably
wants its own explicit go-ahead before going out, not a free ride on
whoever pushes next. Worth folding into `CLAUDE.md`'s new peer-check-in
rule: before pushing, check `git log origin/main..HEAD` for commits that
aren't yours, and flag them specifically, not just ask about your own.

</details>

## HANDOVER - 2026-09-10 (end of session)

The entire prior handover (text-only sweep, second fort founded,
Artobcatten's save lost, the perception-layer branch split, the quorum-
blocked snapshot, and Uniboslan's first room+stockpile) is archived
wholesale — [`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md).
Compacted here, not superseded: exceeded the ~400-line threshold, and
most of its embark-screen-automation detail already lives permanently in
`docs/DF-UI-AUTOMATION.md`, so it didn't need to stay duplicated here too.
The state below is the tight current summary; the archive has the full
narrative, decision-by-decision.

### State at a glance

- **Uniboslan, "Ragwind," is the one active fort.** The first fort,
  Artobcatten, is gone — its save was overwritten founding Uniboslan, no
  backup existed, confirmed unrecoverable. `decisions/DECISIONS.md`
  2026-09-10 has the full incident.
- **Uniboslan has real structure now**: a 5x5 room dug and a matching
  stockpile placed via `quickfort` blueprints (`blueprints/`, four
  files — the first entries in the "Blueprint library" scope item), all
  7 citizens alive and behaving normally. **Paused and quicksaved**
  (confirmed via mtime + file size, not just exit code) as the session
  ended — pause the colony when not actively driving it, per the user's
  own instruction.
- **`check_reachable`/`get_connectivity_report` and an experimental seed
  landmark exist, but deliberately live on their own branch**,
  `perception-layer-experiments` (not `main`) — user's explicit call to
  keep them experimental rather than merge. The live VM has both scripts
  deployed regardless of which branch is checked out locally.
- **A real Windows-specific SSH bug was found and fixed**:
  `provision_vm.ssh_guest` gained `input_data` (pipes a payload over
  stdin) because Git's MSYS-linked `ssh.exe` silently truncates a
  command-line argument to ~8182 characters when spawned by Python's
  `subprocess` rather than bash. `install_df.remote()`/`provision_relay.py`
  both use the fix.
- **A Proxmox snapshot is currently blocked by cluster quorum** (SRV-02
  down, no QDevice — home-lab's to fix, not this repo's).
  `install_df.py backup` is a verified working substitute (pulls the save
  over SSH, no Proxmox API involved) — used and confirmed to actually
  contain Uniboslan's save data before relying on it.

### Next: the real landmark system, and the rest

1. **Build order item 3's real scope (burrow/building enumeration +
   adjacency graph) now has something real to work against** — the
   stockpile is a genuine `building` object, the first non-seed landmark
   candidate. Still needs to happen on `perception-layer-experiments`,
   not `main`, and is still unstarted beyond the seed landmark.
2. **Not done this session, still open from an earlier handover**: the
   `find_mm_*` Y-axis transform mystery (cheap, read-only, not blocking).

### Durable traps, still true (additions marked NEW)

Embark-screen automation mechanics (coordinate frames, `xdotool`
calibration, dead input paths, dialog handling, the click tool's known
flaws) are the permanent, living content of `docs/DF-UI-AUTOMATION.md` —
not duplicated here. This list is everything else: infra, project-wide
gotchas, and fresh findings without another doc home yet.

- **VM 103 is running DF unattended with no network isolation boundary.**
  home-lab's `memory/tailscale-architecture.md` assigns `df-fortress`/
  `df-colony-01` to `tag:ai-sandbox` — "unattended, possibly LLM-driven,
  lowest trust that isn't internet-facing" — but `runbooks/tailscale-topology.md`
  Phase 5 (the actual hard gate) is still unchecked. **Not this repo's to
  fix** — host-level Tailscale/ACL work, forbidden to any agent by
  home-lab's own rule.
- **DF ignores SIGTERM.** Quicksave before stop is mandatory once a fort
  is live; a bare stop takes the full timeout and ends in SIGKILL.
  **Load-bearing, not theoretical** — a real fort exists and must be
  quicksaved before any future stop.
- **The manual (`start`/`stop`) and systemd-managed paths must not run at
  once** — `install_df.py stop` does not clean up a manually-started
  Xvfb. See archive for the full incident/fix.
- **`-gen` fails silently** roughly a quarter of the time. Success is the
  region directory existing, never the exit code.
- **Saves live at the XDG path**, not in the game directory.
- **Never convert a booted VM to a template without sealing it.**
- **The published hostname is exposed.** The user chose not to rename it.
- **`willsmith.nz` is deliberate**, not a leak: the intended public face.
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **DF replay determinism is unverified.**
- **`hypothesis_id` has no registry.**
- **`openclaw` vs `hermes-agent` still deferred.**
- **Tarball checksums are pinned and enforced.**
- **PVE's cloud-init takes only the first label of the VM `name`** —
  `install_df.py`'s `step_hostname` (reused for the relay too) is the only
  workable route to a suffixed guest hostname.
- **Hostname convention has one canonical source: home-lab's `CLAUDE.md`,
  Conventions section.** Cite it, do not restate it here.
- **ImageMagick's `import` infers output format from the file extension.**
  Use an explicit `format:` prefix (`png:path`).
- **On a screen with an actual map viewport, never do a blanket
  full-screen `dfhack.screen.readTile` dump.** Scope scans to the specific
  rows/columns a label search actually needs.
- **`code=exited, status=1` in `systemctl status` means the process called
  `exit(1)` itself, not a signal death** — a core dump will never fire for
  it. Distinguish from `code=killed, status=SIGxxx`.
- **`dfhack-run lua -f script.lua ARG1 ARG2` passes arguments via Lua
  varargs (`local x, y = ...`), not a global `arg` table.**
- **Site Finder's "Begin" needs at least one non-N/A criterion set, or it
  silently no-ops forever.**
- **`load-save.lua`'s `sel_menu_line`-on-`viewscreen_titlest` approach
  does not apply to this build.** Tagged `unavailable`, don't re-attempt.
- **A checksum must never pass through an LLM-summarized web fetch** —
  fetch it directly with `curl` and compare byte-for-byte.
- **`.env` appends must check for a trailing newline first** —
  `install_df.py`'s `_append_env_var()` helper does this.
- **A long payload embedded directly in an SSH command string silently
  truncates at ~8182 characters when Git's MSYS-linked `ssh.exe` is
  spawned by a native Win32 process (Python's `subprocess`) rather than a
  POSIX one (bash)** — no error, exit 0, the remote side just runs a
  truncated command. `provision_vm.ssh_guest` now takes `input_data` to
  pipe a payload over stdin instead; never embed an unbounded-size
  payload directly in an SSH command string again — see
  `provision_vm.ssh_guest`'s docstring.
- NEW, **the costly one — read before ever founding another fort while
  one already exists**: **DF's save-slot names (`autosave 1`, `autosave 2`,
  `current`) are a shared generic pool, not scoped per fort.** Founding
  Uniboslan overwrote Artobcatten's save, confirmed via `md5sum` (both
  slots byte-identical afterward). **Before founding any future
  additional fort**: pull an `install_df.py backup` of every existing
  save first.
- NEW: **A founded fort's own "A Dwarven Outpost..." welcome message
  (with an "Okay" button) silently blocks all citizen activity — walking,
  jobs, everything — even though `df.global.pause_state` reads `false`.**
  Citizens sit frozen indefinitely until it's dismissed (`click "Okay"`).
  Always dump the screen and check for this dialog before concluding a
  fort is "stuck" or unpaused-but-not-progressing.
- NEW: **A downward-staircase (`j`) dig designation cannot be placed on a
  grass-covered surface tile** ("light grass"/"dark grass" — confirmed,
  `quickfort` reports "0 tiles designated" with no error). Works
  immediately on other floor types (stone floor, stone pebbles, dirt).
  Check the actual tile type at the target first.
- NEW: **A plain `d` (floor) dig designation directly beneath an
  already-completed, walkable downstair does not get turned into an
  assignable job at all** — the connecting tile between two z-levels
  needs to be a **matching stair type** (`u`, upstair) to link them for
  job-creation purposes; a plain floor immediately below a stair is not
  sufficient even though the stair above it is itself walkable. Confirmed
  live: changing one tile from `d` to `u` created six real jobs from
  zero. Any blueprint spanning z-levels needs its connecting tile to be a
  proper stair, not a floor designation.
- NEW: **The fortress-wide job list is `df.global.world.jobs.list`**, a
  linked-list struct (traverse via `.next`/`.item`, `#`/`ipairs` both
  fail on it), **not `df.global.job_list`** as
  `research/2026-08-25-spatial-perception.md`'s prototype sketch guessed
  (flagged there, §8, as its one unverified primitive) — now verified.
- NEW: **DF Classic's 2D engine (`PRINT_MODE:2D`) does have real zoom** —
  `data/init/interface.txt` defines genuine `ZOOM_IN`/`ZOOM_OUT` binds
  (`[`/`]` keys), confirmed working live via real `xdotool key
  bracketright`/`bracketleft` in fortress mode. Check the actual
  keybinding file before asserting DF lacks a feature.
- NEW: **`install_df.py backup` is a genuine, verified substitute safety
  net when a Proxmox snapshot is blocked by cluster quorum issues** — no
  Proxmox API involved at all. Verify the resulting archive actually
  contains the expected save data (`tar -tzf` + grep) rather than
  trusting a nonzero file size alone.
- NEW, **root-caused 2026-09-11, corrects the two entries below**:
  `quicksave` is not a synchronous save call at all — read directly from
  the installed `quicksave.lua`: it pushes a `QuicksaveOverlay` screen
  whose `save()` body only runs inside that overlay's own `:render()`,
  on a later, unpredictable game render pass (confirmed live: 45-80+
  seconds observed in one reproduced case, under 8s in another, no fixed
  delay). **The "should autosave now" log line is not evidence either way**
  — a live reproduction this session produced a call that unambiguously
  succeeded (slot rotated, fresh mtime) with that line completely absent,
  before and after. The two apparent "silent no-ops" below are now judged
  **most likely the same lag, just checked with too short a window** —
  not a confirmed distinct failure mode — though this can't be proven
  after the fact (only 3 save slots exist, overwrite-oldest-first, so any
  late completion would already be overwritten). **Verification protocol
  going forward: poll the active save slot's `world.sav` mtime for up to
  ~90 seconds, never key off `stderr.log`'s "Invoking:"/"should autosave"
  lines.** Full evidence trail: `research/2026-09-11-quicksave-silent-noop.md`.
- ~~NEW: A `quicksave` RPC call can return and log "The game should~~
  ~~autosave now" before the file actually lands on disk~~ — superseded by
  the entry above (the actual delay is far longer and more variable than
  "wait a few seconds" ever accounted for).
- ~~NEW: `quicksave` can silently no-op entirely, not just lag~~ —
  superseded by the entry above; downgraded from confirmed to unresolved,
  likely-just-lag.

### Authenticated personal-control VNC channel — DONE, deployed and confirmed live

**Decided 2026-09-11**: user chose to ship neither the free-look 3D idea nor
the Stonesense-per-minute public viewer for now. Instead: a second,
authenticated VNC channel giving **the user personally** real mouse/keyboard
control of the live game (pan, click, look around, change z-levels) — the
existing public/LAN feed stays exactly as-is, untouched, view-only. Both
public-facing ideas above remain live research threads to return to later,
not abandoned, just not what's being built right now.

**Update, same day**: deployed for real (peer session `df-automation-e6`,
commit `05aaf01`) and the user completed the one remaining manual step
(Cloudflare Access app for `dwarf-fortress-admin.willsmith.nz`, scoped to
their own email) — **confirmed working by the user directly** ("it works"),
and independently re-verified in this session rather than taken on trust:
both control-channel systemd units on VM 103 (`df-vnc-control.service`,
`df-vnc-control-tunnel.service`) read `active`, and an unauthenticated
`curl` of the admin hostname returns `302` (redirected to the Access gate)
while the public hostname still returns `200`, unaffected. Full detail:
`decisions/DECISIONS.md` 2026-09-11 (the row directly under the original
build decision). **There are now genuinely two live layers on this one
fort**: the pre-existing public view-only feed, and this new authenticated
full-control feed for the user alone — both up simultaneously, confirmed.
**Standing caution, now live rather than hypothetical**: any future
`xdotool`/DFHack-fake-input use against VM 103 shares this exact channel and
can visibly collide with the user actively driving the game through it —
call it out explicitly before running it, per `docs/DF-UI-AUTOMATION.md`'s
rule. **Update, later the same day**: exactly this happened, harmlessly.
A quicksave-investigation subagent found `pause_state` flip to `false` on
its own during a live check, with no cause it had taken — flagged as a real
concern rather than shrugged off, `df-automation-e6` was asked directly.
Answer: the user really was connected via this control channel at that
time and unpaused the fort themselves (exactly what it's for) — not a
mystery agent. Genuinely useful side effect of asking: e6 also found and
fixed a real, separate bug this uncovered — both x11vnc instances
(`df-vnc` since 2026-09-09, `df-vnc-control` since today) were writing to
the same log file, so the *log* looked silent during that window even
though real input was happening; each now has its own log (`65a96fc`).
Nothing else queued on this thread; it's finished.

**Auth design, reasoned through with the user**: Cloudflare Access only (email
OTP at Cloudflare's edge), no second x11vnc password — confirmed safe *only*
after checking that the relay's existing `websockify` binds all interfaces
(no host prefix in its arg), which would have left a LAN-side bypass around
Access. Fix: the control instance's `websockify` binds `127.0.0.1` only, so
Cloudflare Access is structurally the *only* path in, not merely the intended
one — a second in-app password would be pure friction at that point, not real
defense. One sign-in, not two.

**Built this session, dry-run verified, NOT yet run against VM 103 or the
relay**: `scripts/install_df.py`'s `vnc`/`vnc-tunnel` and
`scripts/provision_relay.py`'s `webvnc` all gained a `--control` flag that
installs a completely separate, second instance (own systemd service, own
port, own tunnel keypair) rather than modifying the existing public one —
`df-vnc-control.service` (port 5901, no `-viewonly`, forced `-nopw`),
`df-vnc-control-tunnel.service` (own keypair/authorized_keys line, doesn't
touch the public tunnel's), `df-webvnc-control.service` (port 6081,
`127.0.0.1`-bound). `--control --password`/`--no-password` together is a
hard error (redundant flags would silently do nothing). Confirmed via
`--dry-run` that the existing non-`--control` paths are byte-for-byte
unchanged.

**A standing rule was added while building this**
(`docs/DF-UI-AUTOMATION.md`): any future use of real X11 input (`xdotool`)
against VM 103 must be called out explicitly, not run silently — it shares
the exact channel this new control session uses, and would genuinely collide
with a connected human session once any future agent needs UI-level input the
way past embark automation here has.

**Next, not yet done, needs the user**: (1) actually run the three
`--control` commands against VM 103 and the relay (currently gated on the
user's go-ahead per this project's live-infra rule); (2) a Cloudflare
dashboard step this repo cannot do for itself — a new Public Hostname on the
existing tunnel pointed at `localhost:6081` on the relay, gated by a
Cloudflare Access policy restricted to the user's own email.

### New thread: real-time, per-viewer free-look fortress viewer (idea stage)

Started this session, separate work from the perception-layer branch (no
overlap — coordinated live with the peer session on `perception-layer-experiments`,
`decisions/DECISIONS.md` doesn't have this yet since nothing's been decided,
only researched). The ask moved twice as it was discussed: shared VNC (exists)
→ periodic per-z-level screenshot with independent client-side pan/zoom
(`research/2026-09-10-stonesense-headless-rendering.md`, medium-confidence,
Stonesense-based) → **real-time, independent FPS-style free-look per viewer**
(`research/2026-09-10-live-freelook-viewer-architecture.md`, low-to-medium
confidence, idea stage only). The free-look requirement rules Stonesense out
entirely (fixed isometric camera, no live API) and points toward a
client-rendered-3D-via-live-RemoteFortressReader-feed architecture instead —
closest prior art is Armok Vision. Also reopens the tileset-licensing question
the screenshot approach had sidestepped, since free-look rendering needs real
texture assets on the client, not just server-rendered pixels — three options
laid out in that doc's §5, **user hasn't picked one yet**.

**Update 2026-09-11**: Armok Vision researched
(`research/2026-09-11-armok-vision-and-overburden-rendering.md`). Both open
questions substantially resolved: RFR's `GetBlockList` is a server-side
hash-diffed poll (client polls, but only changed blocks get sent — confirmed
at this project's exact pinned DFHack tag), and Armok Vision's `GetVisibility(z)`
is a real, shipped, camera-relative Z-band occlusion technique (levels above
camera hidden, current level full detail, lower levels walls-only with caps
suppressed) that answers the user's "strip away the ground" question directly
and transfers cleanly to a browser client with no server involvement.
Also corrected Stonesense's action name (`CHOP_WALLS`, not `CHOP_WALL`) and
found it's narrower than hoped — only affects the single topmost loaded
z-level, complementary to `SEGMENTSIZE_Z:1`, not a substitute for it, and not
itself an answer to the free-look design's occlusion question (that's
Armok Vision's mechanism, not Stonesense's). **Real warning surfaced**:
Armok Vision's own issue tracker reports DFHack's CPU going from 5-7% to
40-50% under a single polling client — foreign hardware/fort, doesn't
transfer directly, but is a concrete reason not to assume "broadcast once,
cheaply" is safe. **Gating next step, not yet done**: a cheap live test —
hook any RFR client to Uniboslan for a few minutes and measure DFHack's own
CPU delta — before further design work on either the free-look architecture
or the Stonesense capture job. User is still deciding overall direction
(also considering a simpler two-tier idea: Stonesense screenshots every
minute for the public, plus a separate authenticated full-control channel
for themselves, not yet reconciled with the free-look thread).

### Dwarf/labor management — first slice built and verified live

Picks up the 2026-09-11 gap (`decisions/DECISIONS.md` same date, "found a
real gap: dwarf/labor management has no build-order item"). Built
`scripts/dfhack/df-overseer-labor.lua` this session:
`unit-status [idle|injured|military|hostile]`, `labors UNIT_ID`,
`set-labor UNIT_ID LABOR_NAME on|off`. Every primitive verified live against
Uniboslan (7 citizens, Year 30) before being written, not assumed from docs
— full detail in `decisions/DECISIONS.md`'s newest row. Confirmed live:
`manipulator` genuinely unavailable on this install (checked, not repeated
on trust), `autolabor` genuinely available but not enabled (out of scope
this session), and `dfhack.units.isDanger`'s "hostile" filter is real but
broader than actual sieges — this fort's own live data (4 `DEMON_*` hits, all
deep-cavern z-levels, `invader=false`) demonstrates the caveat concretely.
Deployed via plain `scp` (mirroring the blueprints precedent) rather than
through `install_df.py`, since that file had a concurrent peer session's
uncommitted changes in flight when this started. All of it went over
`dfhack-run lua`/RPC only, deliberately never touching `xdotool` or
simulated input, so it ran safely alongside the user's newly-live
personal-control VNC session (above) with no channel contention.

**Next, not yet done:**
1. ~~A proper `install_df.py` deploy subcommand for this script~~ — **done,
   see below.**
2. `near_landmark` in `unit-status`'s output is a placeholder (`x,y,z` only)
   until the landmark system on `perception-layer-experiments` merges — a
   different session's branch, not touched here.
3. Nothing yet *decides* what labor to assign — this is the mechanics half
   of design commitment #2 only (code does the bitfield read/write); the
   judgment half (an actual policy: who should mine, who's idle too long,
   when to pull someone off hauling) is still unbuilt.
4. ~~Whether to enable `autolabor`~~ — **done, see below.**

### `provision_vm.py set-cpu` built — done, local only, not yet applied to VM 103

Picks up the 2026-08-28 accepted-but-never-applied decision: `cpu: host`
in `provision_vm.py` blocks live migration between the cluster's two
different CPU generations, defeating the point of clustering at all; `DEFAULT_CPU`
is now `x86-64-v2-AES` for future template builds, and a new `set-cpu`
subcommand (mirroring `set-onboot`'s live-PUT-to-/config pattern) can apply
it to an already-built VM. **Deliberately not run against VM 103 this
session** — same reason as `script-install` above (da's subagent had VM
103's state in flux), plus a sharper one of its own: the change only
actually takes effect on the VM's next cold stop/start, and Uniboslan is a
live, running fort — applying it now would be pointless without also
cold-cycling the VM, which is exactly the kind of disruption to avoid
casually. Needs the user's go-ahead before ever actually running `set-cpu`
+ a deliberate stop/start against the live fort, not just code review.

### Generic `install_df.py script-install <name>` subcommand — built, deployed, and verified live

Coordinated with peer session `df-automation-da` first (their subagent had
VM 103's pause/save state in flux investigating combat detection, so the
build itself stayed local-only: code + `--dry-run` checks, no SSH).
Generalizes `cmd_ui_install` (one hardcoded file) into `cmd_script_install`,
which deploys any `scripts/dfhack/<name>.lua` by name — `ui-install` now
survives as a thin alias (`args.name = "df-overseer-ui"`), confirmed
byte-identical output via `--dry-run` before and after. Covers the
`df-overseer-labor.lua` deploy gap (was plain `scp`'d ad hoc) and, per
da's suggestion, whatever script their subagent lands next, without a
third near-identical subcommand.

**Update, same session**: da's subagent finished and da independently
re-verified VM 103 clear (`pause_state=true`, `autosave 1`) before handing
it back. Ran `script-install df-overseer-labor` for real: exit 0, then
verified past the exit code — read the deployed file's length back off the
guest (9130 bytes: the local source is 9129 UTF-8 bytes plus the heredoc's
one trailing newline, exact match) and called
`dfhack.run_command('df-overseer-labor', 'unit-status', 'idle')` live,
which returned all 7 real citizens, all idle (consistent with the fort
still paused — nothing unpaused, no quicksave triggered, pure read RPC).
Genuinely deployed and callable, not just "exit code said so."

### `autolabor` enabled on Uniboslan — verified live, persisted

User's go-ahead. Checked the tool's own doc before touching anything rather
than assuming behavior: enabling it disables the vanilla work-detail system
outright and recalculates labors on its own cycle, and it **explicitly
leaves dwarves on active military duty or assigned to a burrow untouched** —
that's the actual answer to "does it fight manual `set-labor`," found in the
primary source, no live experiment needed. Confirmed genuinely off before
enabling (`autolabor status` returned "plugin is not enabled"), enabled
(`enable autolabor`), and confirmed genuinely on afterward (`autolabor
status` returned real data: "6 IDLE, 1 OTHER") — not just trusting the
"Enabling autolabor" message. World was and remains paused throughout
(`pause_state` checked before and after, unchanged).

The doc states the enabled flag "stays enabled... even if you save and
reload," which implies it's written into the save itself, not just live
in DFHack's process memory — quicksaved afterward to make sure that's
actually true rather than leaving it to chance. Found a new, real,
previously-undocumented behavior doing this: **`quicksave` rotates forward
through the `autosave N` slot pool by one on each call, rather than
overwriting the currently-active slot in place** — confirmed live, two
quicksaves in a row moved `cur_savegame.save_dir` from `autosave 1` →
`autosave 2` → `autosave 3`, each with a fresh mtime matching when it ran.
Distinct from (and less alarming than) the Artobcatten incident: that was
two *different forts* colliding on the same slot pool; this is one fort
rotating forward through its own slots normally, nothing overwritten
unexpectedly, nothing lost. Worth remembering for any future mtime-based
"did my save land" check: check `cur_savegame.save_dir` fresh each time
rather than assuming the slot name from an earlier check is still current.

**Update, same session**: watched it actually work. Unpaused briefly (~15s
real time), re-checked `unit-status`: idle count dropped from 6 to 1
(`autolabor status` agreed: "1 IDLE, 6 OTHER"), citizens' positions had
genuinely moved, and jobs were assigned (`Sleep`, `Drink`) — real simulation,
not a stuck state. One citizen briefly showed `injured=true` (a real
`body.wounds` entry, not a UI artifact) that had fully healed by the next
check moments later, with nothing in `gamelog.txt` for that window — read as
a minor, self-resolving incident (a scrape, not combat), not a threat; no
DEMON_* unit from the earlier `hostile` scan is anywhere near the fort's
z-level regardless. Re-paused and quicksaved afterward, per the "pause when
not actively driving" convention.

**A second real finding surfaced doing the quicksave-to-confirm-persistence
step, not the autolabor question but adjacent to it**: two consecutive
`./dfhack-run quicksave` calls (both while paused, ~15-20s apart) produced
**no** "The game should autosave now" line in `stderr.log` and **no** file
change on disk at all — confirmed by isolating exactly the new `stderr.log`
lines per attempt (line-count diff, not just a tail glance) and `stat`-ing
the active save slot before and after each. A third attempt, no different
in method, worked normally (log line appeared, `autosave 3`'s mtime updated
to match). **`quicksave` can silently no-op**, not just "log success before
the file lands" (the already-documented trap) — this is a stronger claim,
worth downgrading the standing "wait a few seconds and recheck" advice to
"retry and recheck" if a single retry doesn't confirm. Root cause
unidentified; not chased further since it isn't blocking (the autolabor
enable was already durably saved by the first successful quicksave, before
this was even discovered) and `df-fortress.service`'s own `ExecStop`
already quicksaves unconditionally before any real stop regardless.

### First real combat, used as a live test case for `unit-status hostile`

User spotted a kea fighting the fort's dogs live via the viewer and asked
for it to be used as a real experiment rather than staying synthetic. Good
call — it surfaced a real gap, not just confirmed a theoretical one.
Reconstructed from `gamelog.txt`: the kea (unit 321) picked a fight, the
stray dog + stray war dog + citizen 196 (Fisherdwarf) fought it off, the
kea died (confirmed `isDead=true`), one dog took a minor wound (confirmed
`body.wounds`), no dwarf was hurt. `unit-status hostile` was checked both
before and after finding this — in both cases it reported only the same 4
harmless deep-cavern demons, completely blind to a real, fort-relevant
fight that had just happened at the front door. Full detail and the
correction to the original spec: `decisions/DECISIONS.md` 2026-09-11
("First real combat on Uniboslan"), `research/2026-08-25-spatial-perception.md`
§5. **Not fixed** — the right fix is almost certainly `get_diff_since`
(build order item 5, `eventful`-backed), since "something attacked
something" is an event, not a queryable static predicate; a better
`isDanger`-style filter would be solving the wrong shape of problem.

**Update, same day**: dispatched a Sonnet subagent to investigate/prototype
this properly. Result: `scripts/dfhack/df-overseer-combat.lua`, written but
**deliberately not committed** — user's own call, see below. Verified
independently before anything else: exhaustively checked every
`dfhack.units.*` predicate resembling danger/hostile/combat (found one not
previously tried, `isAgitated` — also `false` for the kea, confirming the
gap is real, not an oversight); found and live-verified
`df.global.world.status.reports` as a structured, typed combat-data source
(not `gamelog.txt` text-scraping) that reconstructs the kea fight exactly;
live-verified `eventful`'s `onReport`/`onUnitAttack` hooks actually fire
end-to-end, including isolating (via a deliberate controlled test, not just
one observation) that DFHack's event queue only drains on unpaused ticks
and backfills its whole backlog on first drain. Fort re-confirmed paused
and saved afterward, independently re-checked by this session too.

**The bigger finding, not the combat mechanism itself**: `df-overseer-diff.lua`
already exists on `perception-layer-experiments` (df-automation-ca's
branch, deployed live on VM 103) and is **already an implementation of the
same primitive**, `get_diff_since` — same `eventful`+`_G`-persisted-log+
cursor design, covering `JOB_COMPLETED`/`UNIT_DEATH` instead of
`REPORT`/`UNIT_ATTACK`. ~~Its own header honestly flags that it **never
verified a real eventful callback firing live**~~ — **correction, found
auditing the full branch afterward**: it *was* verified live
(`e627440`, "closing the last honest gap" — same unpause/watch/re-pause/
verify-mtime discipline used all session), the file's own header comment
just never got updated after the fact and is stale, not accurate. This
session's subagent still closes a real, different gap (`REPORT`/`UNIT_ATTACK`
event types diff.lua deliberately left unwired), just not the "never
verified live" one originally believed. Doesn't change the reconciliation
question, but the correct framing is "extend diff.lua's proven design with
more event types," not "diff.lua's core mechanism is unverified." **`df-automation-ca`
was not reachable to coordinate directly** (not connected at the time).
Asked the user how to handle it: **chose to wait for `df-automation-ca`
before reconciling or committing anything** rather than commit unilaterally
and sort it out later. `scripts/dfhack/df-overseer-combat.lua` sits on disk,
deployed to
VM 103's `hack/scripts/`, but **untracked in git** — do not commit it
without checking back on this first.

**Separately, a real documentation-vs-reality gap, per this repo's own
"flag it, don't silently patch" rule**: `perception-layer-experiments` also
has `df-overseer-chokepoints.lua`, `-openarea.lua`, `-overview.lua`,
`-stuckjobs.lua` deployed on VM 103 (all dated 2026-09-10 23:20) —
most of `docs/PURPOSE.md` build order items 2 and 5-8 already exist there.
Working.md/ROADMAP.md still describe that branch as just "connectivity +
a seed landmark." **Update, audited properly this session** (not just
file-listing guesswork): fetched and read the branch's own commit log and
its own `Working.md` directly. Confirmed for real: **all of build order
items 2 through 8 are built, verified live against the real fort, and all
8 commits are pushed to `origin/perception-layer-experiments`** — not just
present as files. Two real bugs caught there worth knowing regardless of
merge status: `dfhack.buildings.getSize()`'s `cx,cy` are local to the
building's own box, not absolute map coordinates; `df.global.world.burrows.all`
doesn't exist, the real path is `df.global.plotinfo.burrows.list`. The
branch's own `Working.md` explicitly leaves "whether/when to merge" as
"still the user's call to make, not assumed" — asked; **user chose not to
merge yet, wants to keep working with what's there and see how far it
goes** (see the autonomous-play entry below). `df-automation-ca` still
wasn't reachable to coordinate directly this session.

### First autonomous-play experiment — a real judgment win, a real tooling gap

User's framing: "let's keep working with it and seeing how far we can take
this... how far can an AI work" — chosen as a genuine bounded experiment,
not a demo. A subagent was given the deployed `perception-layer-experiments`
tools plus today's labor tools and told to make one real construction
decision using only tool output, build it via `quickfort` only, and hard-stop
rather than improvise if it hit a wall. Full detail: `decisions/DECISIONS.md`
2026-09-11 ("First real autonomous-play experiment on Uniboslan").

**What worked**: the decision itself was cleanly tool-derived — `find_open_area`
ranked a real, walkable, non-stranded 5x5 candidate next to "Stockpile #1,"
using `z=169` read from the citizens' own real positions, not guessed.
Design commitments #1/#2 held up on a real case, not just in theory.

**What it found, verified independently against the actual script source,
not just taken on the subagent's word**: `quickfort run -c x,y,z` needs a
literal absolute coordinate, but **every deployed perception tool
deliberately strips coordinates before returning** — `find_open_area`
computes a real `cx,cy` internally and never includes it in what it hands
back; `df-overseer-landmarks.lua` explicitly nils out `x,y,z` before
returning a landmark, even though an internal function
(`get_landmark_centroid`) holds the real value and is never exposed via any
command. This looks like commitment #1's spirit applied without its
mechanical conclusion ever being built: **nothing converts "the model
picked a good, named candidate" into something `quickfort` can actually
anchor to.** Correctly treated as a stop condition — no coordinate was
guessed, nothing on the fort changed, re-verified after the fact (still
paused, same save slot, 0 injured, no repo files touched).

**Next, concrete, not vague**: a `resolve_landmark`/`resolve_candidate`-style
primitive that hands back a real anchor coordinate for a name or a ranked
result — callable only by the mechanical blueprint-anchoring step, never
by the model's own reasoning, keeping commitment #1 intact while actually
closing the loop end to end. Lives on `perception-layer-experiments`, same
branch-ownership question as the `diff.lua`/`combat.lua` overlap above —
not started, not mine to build unilaterally given that's still open.

### Other open items, carried forward

- **Design commitment #1's absolute wording vs. its actual evidence
  base** — still queued for a `decisions/DECISIONS.md` entry, deliberately
  not written yet (user's call on timing).
- **Live-view ingest (the public screenshot-push leg), still waiting on
  the user.** Once Cloudflare R2 credentials arrive: wire
  `DF_STREAM_INGEST_URL` in `.env`, convert `curl -F` to an S3-compatible
  signed PUT, fill in `IMAGE_BASE` in
  `willsmith-portfolio/public/dwarf-fortress/index.html`, commit, ask
  before pushing/deploying either repo.

**Style note:** the user does not want em dashes in prose. Commas, colons,
semicolons or full stops instead. Fine as structural separators.

## Archived

- Sections for the week of 2026-08-24 moved to
  [`working-archive/Working_archive-2026-08-24.md`](working-archive/Working_archive-2026-08-24.md).
- 2026-08-27 through 2026-09-08: provisioning build, host-RAM blocker,
  perception eval, fort ledger, VM-start, provisioning-hardening,
  DF-install-scripting, systemd-unit handovers — all moved wholesale to
  [`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md)
  as each was superseded or reported itself finished.
- 2026-09-09: the 2026-09-08 (evening) handover moved wholesale to the
  same archive file.
- 2026-09-09 (end of session): this session's full handover (title-screen
  bootstrap resolution, the entire live-viewing/relay/tunnel build, the
  tileset investigation, and the Site Finder "Begin" resolution) moved
  wholesale to the same archive file — exceeded the ~400-line threshold,
  not superseded. The handover above is the tight current-state summary;
  the archive has the full detail.
- 2026-09-10: the 2026-09-09 (end of session) handover moved wholesale to
  the same archive file, superseded by this session's own handover above
  (Cloudflare Tunnel completion, the graphics-completeness fix, and the
  live embark-flow attempt).
- 2026-09-10 (second handover today): that session's own handover moved
  wholesale to the same archive file, superseded by this session's handover
  above (the click-registration mystery resolved, the real embark mechanism
  found, and the new "Confirm" crash).
- 2026-09-10 (third handover today): that session's own handover moved
  wholesale to the same archive file, superseded by this session's handover
  above — **the first fort was founded**, and the "Confirm" crash resolved
  empirically via gdb.
- 2026-09-10 (fourth handover today): that session's own handover moved
  wholesale to the same archive file, superseded by this session's handover
  above — the `find_mm_*`/`warn_mm_*` coordinate-frame bug found, and
  `xdotool` real-input fix for headless map/hover interaction discovered
  and validated.
- 2026-09-10 (fifth handover today): that session's own handover moved
  wholesale to the same archive file, superseded by the handover at the top
  of this file — the text-only sweep built and run, a Windows-specific SSH
  command-line truncation bug found and fixed in `provision_vm.ssh_guest`/
  `install_df.remote()`, and a strong second-site candidate found
  (`sx=128 sy=84 ex=131 ey=87`), left uncommitted for the user's call.
- 2026-09-10 (end of session): that handover's full continuation (the
  candidate embarked, Artobcatten's save lost as a result, the
  perception-layer branch split, the quorum-blocked snapshot worked
  around with a file backup, and Uniboslan's first room and stockpile dug)
  moved wholesale to the same archive file — exceeded the ~400-line
  threshold, not superseded by new work. The handover at the top of this
  file is the compacted current-state summary; the embark-screen-specific
  durable traps it used to carry were dropped rather than re-copied
  forward, since they're already the permanent living content of
  `docs/DF-UI-AUTOMATION.md`, not duplicated here.
