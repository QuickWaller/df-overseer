# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.

## HANDOVER - 2026-09-09 (end of session)

The full blow-by-blow of this session (a very long, very productive one) is
archived wholesale, not summarized away —
[`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md),
appended 2026-09-09. Read it if you need to know exactly *how* something
below was found. This handover is the tight, current-state version: what's
true right now, and the one concrete task queued next.

### State at a glance

- **VM 103** (`df-colony-01.internal`, `192.168.2.201`): running DF under
  systemd, real Steam-graphics rendering confirmed working (see below),
  a fresh graphics-enabled world (`region2`) generated with a candidate
  embark site found on it, **still no fort**. Nobody has clicked through
  to actually embark yet — that's the real next DF-side milestone.
- **Relay VM** (`df-colony-relay-01.internal`, vmid 105, `192.168.2.202`,
  Debian 12 bookworm, home-lab's Proxmox pool, `srv-01`): built this
  session, LAN-only, purpose is bridging VM 103's VNC feed toward a future
  public leg.
- **Live LAN viewing is fully built and user-confirmed working end to
  end**: VM 103's `x11vnc` (`df-vnc.service`) → reverse SSH tunnel
  (`df-vnc-tunnel.service`, dedicated `permitopen`-restricted key, VM 103
  dials out, never accepts inbound) → relay's `websockify`/noVNC
  (`df-webvnc.service`) → `http://192.168.2.202:6080/vnc.html`. The user
  opened that URL in a real browser and confirmed it connects and shows
  VM 103's display live.
- **Public leg (Cloudflare Tunnel on the relay) is the one piece not
  built**, deliberately deferred — get LAN infra solid first, agreed
  explicitly, not forgotten.
- **DF's look is now the real, official Steam-style modern graphics,
  confirmed genuinely rendering** — resolved 2026-09-09, see below. Not
  ASCII, not the plain bundled font: actual per-tile sprite art
  transplanted from the user's own purchased Steam copy.

### RESOLVED 2026-09-09: built-in modern (Steam-style) graphics are working on VM 103

**Bottom line**: `research/2026-09-09-df-modern-graphics.md` confirmed
there is no *free* official path — Premium's tileset is proprietary
Kitfox-commissioned art bundled only in the paid build, and free Classic's
`data/vanilla/vanilla_*_graphics`/`vanilla_world_map` module folders ship
as empty `info.txt`-only stubs by design. What actually unblocked this:
the user already owns a legitimate Steam copy locally (confirmed install
at `C:\Program Files (x86)\Steam\steamapps\common\Dwarf Fortress`, version
**53.15**, one patch behind VM 103's pinned 53.16). `install_df.py` gained
a new `graphics` subcommand (`--source PATH`, or `DF_GRAPHICS_SOURCE` in
`.env`) that tars the eight real module folders from that local install,
`scp`s the tarball straight to VM 103, and extracts it over the existing
empty stubs — the asset bytes never touch this repo's git tree, matching
the public-repo/no-committed-binaries convention. Full reasoning,
legitimacy basis, and the version-gap analysis →
`decisions/DECISIONS.md` 2026-09-09 (the graphics-transplant row).

**No mod-selection screen automation was needed.** The task's anticipated
hard problem — DF v50+ graphics modules needing to be opted into a
world's mod list via a UI mod-selection screen before worldgen — turned
out not to apply: VM 103's own `gen_modlist.txt` already listed all eight
`vanilla_*` modules as active with no mod-selection UI ever touched,
confirming they're baked into every worldgen unconditionally, not opt-in
like a Workshop mod. The actual work was pure file-placement (populate
the stub folders DF already reads at render time) plus
`USE_CLASSIC_ASCII:NO` (both already in `scripts/install_df.py`'s
`INIT_SETTINGS`/`GRAPHICS_MODULES`).

**Verified genuinely rendering, not just a setting flipped**: real
screenshots (saved locally at `C:\Users\wills\df-graphics-screenshots\`,
11 files, sequentially numbered) show actual pixel-art sprites — trees,
wave-textured water, mountains, a volcano, sand — on three separate
screens: the world overview, the unzoomed Site Finder panel, and the
zoomed embark-placement map. One honest caveat: `dfhack.screen.readTile`'s
aggregate non-blank-tile count (the exact diagnostic that proved the
original bug) reads back 0 again over the equivalent clean map-only
region in this now-confirmed-working case — that screen's terrain is
drawn via a texture-blit path invisible to `dfhack.screen`'s
character-buffer instrumentation, so that specific check is not a valid
signal either way for this widget; the screenshot is the load-bearing
evidence, not the buffer read.

**This task had been started and interrupted mid-session by an earlier
agent with no final report.** Rather than assume its stopping point, this
session opened by directly inspecting VM 103 (process list, current
viewscreen, `data/vanilla/` module file counts, `prefs/init.txt`) before
doing anything further. That inspection found the interrupted agent had
already correctly finished the graphics transplant, the
`USE_CLASSIC_ASCII:NO` flip, and a full fresh worldgen (`region2`,
discarding the old ASCII-era candidate site per the user's prior
approval) — DF was sitting idle at the title screen, nothing stuck or
mid-write. This session completed the remaining unverified half: the
screenshot confirmation and a fresh Site Finder pass on `region2`.

**Two live follow-up questions from the user (watching via the VNC feed)
were investigated directly, both came back negative**: (1) whether DF's
v50+ button-style menus expose per-screen keyboard hotkeys — checked via
screenshots and `pen.fg` colour dumps on the Site Finder panel, world-map
buttons, and the title menu; no bracketed/underlined/distinctly-coloured
hotkey letter exists anywhere, confirmed via uniform `fg` values, not
just a glance. (2) whether a global keyboard-vs-mouse interface-mode
toggle exists — checked Settings' Video/Game/Keybindings tabs in full
(including scrolling Game to its actual end) and `prefs/init.txt`/
`data/init/d_init_default.txt`; `Keybindings` is a physical-key
**rebinding** screen for named actions already known dead against these
widgets, not a mode switch, and no such toggle exists anywhere. The
existing buffer-scan-and-click mouse automation remains the correct
mechanism. For the Site Finder's search criteria specifically, a direct
struct-field write (`scr.find_param[2] = 0`, the `gui/embark-anywhere.lua`
idiom) proved more robust than hunting for a `+`/`-` button's coordinates,
which don't render as static glyphs on that particular panel.

**Current state**: `region2` (the graphics-enabled world) has a confirmed
candidate embark site (`find_results == 2`, "Match found!", Savagery set
to Calm) — not yet embarked, per instruction. `region1` (the old
ASCII-era world/candidate) still exists on disk, superseded, not deleted.
DF is back under systemd management (`df-fortress.service`/
`df-xvfb.service`, both active) after this session's manual
stop/start/reset cycles — `verify` passes clean.

### Durable traps, still true

- **VM 103 is running DF unattended with no network isolation boundary.**
  home-lab's `memory/tailscale-architecture.md` assigns `df-fortress`/
  `df-colony-01` to `tag:ai-sandbox` — "unattended, possibly LLM-driven,
  lowest trust that isn't internet-facing" — but `runbooks/tailscale-topology.md`
  Phase 5 (the actual hard gate) is still unchecked. **Not this repo's to
  fix** — host-level Tailscale/ACL work, forbidden to any agent by
  home-lab's own rule.
- **DF ignores SIGTERM.** Quicksave before stop is mandatory once a fort
  is live; a bare stop takes the full timeout and ends in SIGKILL.
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
- **`gui.simulateInput`'s generic keys don't work on DF v50+'s native
  button-style menus, and this extends to WASD map-panning too** —
  confirmed dead (pixel-identical before/after screenshots) on
  `choose_start_sitest`'s camera panning specifically, alongside the
  already-known title-screen/region-list menu cases. Mouse clicks
  (buffer-scan for text, compute coordinate, `_MOUSE_L`) are the only
  confirmed-working input method on any of these screens.
- **Site Finder's "Begin" needs at least one non-N/A criterion set, or it
  silently no-ops forever.** Solved this session, see archive for the
  full A/B test.
- **`load-save.lua`'s `sel_menu_line`-on-`viewscreen_titlest` approach
  does not apply to this build.** Tagged `unavailable`, don't re-attempt.
- **A checksum must never pass through an LLM-summarized web fetch** —
  fetch it directly with `curl` and compare byte-for-byte. Learned the
  hard way this session (see `scripts/provision_relay.py`'s comments).
- **`.env` appends must check for a trailing newline first** —
  `install_df.py`'s `_append_env_var()` helper does this; never use a bare
  `open(path, "a")` again (caused a real incident this session: a missing
  trailing newline silently merged `DF_VNC_PASSWORD` onto the end of
  `ANTHROPIC_API_KEY`'s line).

### Other open items, carried forward

- **Design commitment #1's absolute wording vs. its actual evidence
  base** — still queued for a `decisions/DECISIONS.md` entry, deliberately
  not written yet (user's call on timing). This session put a live
  instance of the distinction into practice (screenshots used directly
  for the tileset-debugging work, with the user's explicit go-ahead)
  without writing the formal entry.
- **Live-view ingest (the public screenshot-push leg), still waiting on
  the user.** Once Cloudflare R2 credentials arrive: wire
  `DF_STREAM_INGEST_URL` in `.env`, convert `curl -F` to an S3-compatible
  signed PUT, fill in `IMAGE_BASE` in
  `willsmith-portfolio/public/dwarf-fortress/index.html`, commit, ask
  before pushing/deploying either repo.
- **Cloudflare Tunnel on the relay — installed and verified, blocked only on
  the dashboard connector token.** `scripts/provision_relay.py cloudflared`
  installs `cloudflared` from Cloudflare's own apt repo (verified 2026-09-09
  against `pkg.cloudflare.com`'s own index page, fetched directly: the
  current documented method is a `/usr/share/keyrings/` keyring file plus
  an inline `signed-by=` apt line, not the deprecated `apt-key` path) —
  idempotent, re-run and confirmed skipping reinstall. `cloudflared 2026.8.3`
  is live on the relay (`192.168.2.202`), confirmed by `cloudflared
  --version` over SSH. The subcommand also runs the token-based
  `cloudflared service install <token>` step, but only once a token exists;
  not invoked with any placeholder this session, per the task's own
  constraint. `decisions/DECISIONS.md` 2026-09-09 rows record both this as a
  deliberate simplification over `research/2026-09-09-reverse-vnc-relay.md`
  §6's generic-VPS/nginx/certbot sketch, and the explicit revisit of both
  research docs' screenshot-over-VNC recommendation for the public leg.

  **Exact steps for whoever holds the Cloudflare console access, once the
  tunnel exists:**
  1. In the Zero Trust dashboard: Networks -> Tunnels -> create a tunnel
     (any name, e.g. `df-colony-relay`) -> choose the Debian/generic
     connector option -> copy the connector token shown (a long string, the
     dashboard's non-interactive install flow, not `cloudflared tunnel
     login`).
  2. Put that token in `.env` as `CLOUDFLARE_TUNNEL_TOKEN` (a placeholder
     line already exists there and in `infra/local.example.env`), or pass
     it directly: `python scripts/provision_relay.py cloudflared --token
     <token>`.
  3. Run `python scripts/provision_relay.py cloudflared` (no `--token`
     needed once it's in `.env`). This runs `cloudflared service install
     <token>` on the relay and confirms `systemctl is-active cloudflared`.
  4. Back in the same tunnel's dashboard config, open the **Public
     Hostname** tab and add: hostname `dwarf-fortress.willsmith.nz`,
     service type HTTP, URL `http://localhost:6080`. Since `willsmith.nz`
     is already on Cloudflare DNS, saving this auto-creates the CNAME —
     no `cloudflared tunnel route dns` needed (that command belongs to the
     older CLI-managed tunnel workflow, not this dashboard-token one).
  5. Verify: `https://dwarf-fortress.willsmith.nz` should load the same
     noVNC page `http://192.168.2.202:6080/vnc.html` already serves on the
     LAN, prompting for `DF_VNC_PASSWORD`.
  6. Once confirmed live, fill in the link in
     `willsmith-portfolio/public/dwarf-fortress/index.html` (currently
     present but marked not-yet-live) and update this section again.
- **Actually embark** — a candidate site was found on `region2` (the
  graphics-enabled world, "Match found!") but nobody has embarked. The
  real first-fort milestone.

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
