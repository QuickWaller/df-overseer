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
  systemd, world generated, **still no fort**. A candidate embark site was
  found this session ("Match found!") but nobody has clicked through to
  actually embark yet — that's the real next DF-side milestone.
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
- **DF's look is currently the safe, working default**: classic curses
  ASCII rendering (`USE_CLASSIC_ASCII:YES`, default `curses_640x300.png`
  font). The nicer square-tile font attempt was tried, found to still be
  "just ASCII" in the way that matters to the user, and superseded by the
  investigation below — currently reverted to plain default while the
  real fix is researched.

### Open thread, with a queued task for next session: get the built-in modern (Steam-style) graphics working, without a third-party pack

**What's confirmed, in order of how it was found:**
1. `USE_CLASSIC_ASCII:NO` unlocks a genuinely different, modern UI —
   smooth anti-aliased text, full-width colored buttons — confirmed via a
   direct screenshot of the title screen (no map dependency), and the
   user independently confirmed it looks good live. This is real,
   legitimate DF Classic 0.53.16 functionality, not a hack or a
   third-party mod.
2. In that same mode, the world/embark map viewport renders **completely
   empty** — confirmed twice, with two very differently-shaped font files
   (a 256×256 square font, and `curses_640x300.png` at its *actual* pixel
   size of 128×192, which a wiki page says is the exact spec
   `USE_CLASSIC_ASCII:NO` needs for "custom tiles" to render). Both gave
   the identical empty-map result. Confirmed via `dfhack.screen.readTile`
   buffer stats (0 non-blank tiles in the viewport both times), not just
   a visual impression.
3. Ruling out font dimensions as the map's specific problem (two
   different shapes, same failure) points at a different, unconfirmed
   hypothesis: the world/embark map is very likely rendered through a
   categorically separate system from menu text — real per-tile terrain
   sprites (`raw/graphics` tile-page + creature/inorganic graphics tags)
   — and this build's `raw/graphics` folder is confirmed empty. That's a
   plausible explanation, **not yet verified against DF's actual source,
   a changelog, or any primary documentation** — it's this session's best
   guess, not a settled finding.

**What the user wants, stated directly, worth quoting the intent
precisely**: they don't like the ASCII look, they want the modern
Steam-style graphics working, and they explicitly do **not** want to reach
for a third-party community graphics pack as the first move — that's the
bigger, riskier fallback, not the default plan. They suspect this is a
**fixable bug or missing-file issue**, not a fundamental limitation of the
free Classic build.

**Queued task for next session, to be handed to a Sonnet researcher
(cheap, background — matches this project's established pattern from
earlier in this same session for the Alpine cloud-init investigation)**:
investigate whether DF Classic 0.53.16's built-in/official modern graphics
(the ones bundled with or shipped alongside the Steam/premium release) can
be obtained and made to work in this free Classic distribution, *without*
resorting to a third-party community pack. Concretely, the research should
answer:
- Does Bay12 distribute an official graphics/tileset asset bundle for
  Classic separately from the base game download (e.g. an optional
  download on itch.io/Bay12's own site), distinct from what
  `scripts/install_df.py` currently fetches (`DF_URL`, pinned to
  `df_53_16_linux.tar.bz2`)?
- Is the empty `raw/graphics` folder actually the blocker, or is there a
  missing init.txt/config setting instead (a real primary-source check of
  DF's own source or official documentation, not forum folklore — this
  session's own web searches surfaced some inconsistent/unverified
  community claims already, flagged as such in the archived detail)?
- If an official asset bundle exists: exact download URL, checksum
  (matching this project's own pinning discipline — see `DF_SHA256`/
  `DFHACK_SHA256` in `scripts/install_df.py` for the existing pattern),
  and what installing it actually involves (which files go where, whether
  it's compatible with the exact pinned DFHack 53.16-r1.1 build).
- If no official bundle exists and this really is a hard limitation of
  the free Classic build: say so plainly, and only then is a third-party
  pack the next real option — but that's explicitly the fallback, not the
  default plan.

Current live state to resume from: VM 103's `prefs/init.txt` has
`FONT`/`FULLFONT:curses_640x300.png`, `USE_CLASSIC_ASCII:YES` (the safe
default, matching `scripts/install_df.py`'s checked-in `INIT_SETTINGS`,
which is *not* carrying the square-font change — that was fully reverted
this session, see the archive for the exact history of tries).

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
- **Actually embark** — a candidate site was found ("Match found!") but
  nobody has embarked. The real first-fort milestone.

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
