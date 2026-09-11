# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.


## HANDOVER — 2026-09-12 (session end, written for a `/clear`)

The entire prior session's content (tool manifest build, both coordinate-leak
fixes, the quorum correction, and everything else since the last `/clear`) is
archived wholesale —
[`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md).
**User's stated direction for the next session: a design and research phase**,
likely opening with a fresh Opus conversation — nothing further is queued or
assumed beyond that; this handover is deliberately just the state-at-a-glance
a fresh session needs, not a prescribed next task.

### State at a glance, verified fresh, not assumed

- **Uniboslan, "Ragwind," is the one fort, healthy and untouched**: 15
  citizens, all idle/healthy, confirmed by a live `unit-status` call at the
  end of this session (also used to verify the coordinate-leak fix, below).
- **`main` is clean but has 5 unpushed local commits** — `034f555` (tool
  manifest), `809baaa` (leak fixes, code), `8ac539d` (leak fixes, deployed +
  verified), `4108c1f` (live-view ingest shelved), `c5de471` (openclaw brain
  decision). **Not pushed — needs explicit go-ahead, and per this repo's own
  rule, check `git log origin/main..HEAD` again before pushing in case
  another session added commits of its own in the meantime.**
- **`scripts/dfhack/` holds 10 files plus a new manifest, `TOOLS.yaml`,**
  all live-deployed and live-verified on VM 103 as of this session (its own
  per-command `verified` dates are the source of truth, not this paragraph).
- **Both known raw-coordinate leaks are fixed, deployed, and live-verified**:
  `df-overseer-labor unit-status` and `df-overseer-diff recent-combat`/
  `since-report` all now resolve `near_landmark`/`direction`/`distance_tiles`
  instead of printing raw `pos=x,y,z`. No known coordinate leak remains open.
- **Quorum: resolved** (`pvecm status`: `Quorate: Yes`, 2/2, confirmed by
  `home-lab-29` the morning of 2026-09-12). SRV-02's own crash-pattern
  stability (76 reboots/8 days) is still genuinely open — not this repo's to
  fix, just current context if anything relies on host uptime.
- **Live-view ingest (screenshot-push to the portfolio page): explicitly
  shelved, user's call** — not blocked on anything technical (an R2
  bucket/token is still the only missing piece), just not a priority right
  now. Not redundant with the two working VNC streams (public view-only +
  authenticated admin) — it's a lighter-weight static-image embed meant to
  sit alongside a "watch live via noVNC" link, just deprioritized.
- **The driving-brain choice is decided: `openclaw`**, user's explicit call
  (not the originally-planned empirical 30-day survival test), wanting a
  multi-agent architecture — many agents, each a single responsibility, each
  free to run a different model. **Not yet built**: the actual
  multi-agent-by-task decomposition, and the MCP server/tool schema this
  repo's design commitment #5 needs before any brain can actually drive the
  fort (`scripts/dfhack/TOOLS.yaml` is a first draft of that schema, not the
  server). → `decisions/DECISIONS.md` 2026-09-12 rows.

### Durable traps, still true (carried forward from the archived handover, unchanged unless noted)

Embark-screen automation mechanics (coordinate frames, `xdotool` calibration,
dead input paths, dialog handling, the click tool's known flaws) are the
permanent, living content of `docs/DF-UI-AUTOMATION.md` — not duplicated
here. This list is everything else: infra, project-wide gotchas, and fresh
findings without another doc home yet.

- **`ranked_candidates()`-style helpers that resolve a named landmark's own
  coordinate internally must actually use that resolved value everywhere,
  not just to validate the caller's separately-supplied one.** If a function
  already has the right answer internally, don't also ask the caller for it.
- **DF gamelog/report text is not guaranteed to be safely printable through
  a Windows console's default codepage.** Any tool that relays raw DF text
  should encode defensively (`errors='replace'`).
- **`dfhack.buildings.getSize()`'s `cx,cy` are local to the building's own
  box, not absolute map coordinates** — add the building's own origin field
  before using them as a real coordinate.
- **`df.global.world.burrows.all` does not exist** — the correct path is
  `df.global.plotinfo.burrows.list`.
- **UPDATED 2026-09-12: no known raw-coordinate leak remains** in any
  deployed `df-overseer-*.lua` command — both leaks found this session
  (`df-overseer-labor unit-status`, `df-overseer-diff recent-combat`/
  `since-report`) are fixed, deployed, and live-verified. If a future audit
  finds another, it goes here the same way these did.
- **Directly changing a live fort's pause state
  (`dfhack.world.SetPauseState(false)`) is blocked by Claude Code's own
  auto-mode classifier by default**, not something a bare mid-conversation
  "go ahead" reliably satisfies. Ask right before the call, get an explicit
  answer to that exact question; if still blocked, say so plainly rather
  than routing around it with an equivalent raw struct write.
- **`quickfort run <file>` resolves a plain filename relative to
  `dfhack-config/blueprints/`, not the working directory or an absolute
  path.** Write ad-hoc blueprints directly into that directory.
- **`save/current` is transient staging, not itself an addressable save** —
  a quicksave briefly writes there, then DF moves it into the real numbered
  slot (`cur_savegame.save_dir`) within moments.
- **`reqscript`-loading a `df-overseer-*.lua` file requires a
  `--@module = true` directive as a leading comment line**, and a
  module-loaded script's own CLI-dispatch code still runs during that load
  unless guarded (`if dfhack_flags.module then return end`).
- **VM 103 is running DF unattended with no network isolation boundary.**
  home-lab's own structural gap (Tailscale ACL Phase 5 unchecked) — not this
  repo's to fix.
- **DF ignores SIGTERM.** Quicksave before stop is mandatory once a fort is
  live; a bare stop takes the full timeout and ends in SIGKILL.
- **`-gen` fails silently** roughly a quarter of the time. Success is the
  region directory existing, never the exit code.
- **Saves live at the XDG path**, not in the game directory.
- **Never convert a booted VM to a template without sealing it.**
- **The published hostname is exposed.** The user chose not to rename it;
  `willsmith.nz` is deliberate, not a leak.
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **DF replay determinism is unverified. `hypothesis_id` has no registry.**
- **PVE's cloud-init takes only the first label of the VM `name`** —
  `install_df.py`'s `step_hostname` is the only workable route to a suffixed
  guest hostname.
- **`dfhack-run lua -f script.lua ARG1 ARG2` passes arguments via Lua
  varargs (`local x, y = ...`), not a global `arg` table.**
- **DF's save-slot names (`autosave 1/2/3`, `current`) are a shared, generic
  pool, not scoped per fort** — pull an `install_df.py backup` first,
  always, before founding any further fort.
- **A founded fort's own welcome dialog silently blocks all citizen activity
  even when `pause_state` reads `false`.** Always check for an undismissed
  dialog before concluding a fort is stuck.
- **A downstair can't be designated on a grass tile**; a plain floor dig
  beneath a completed stair never becomes a job unless the connecting tile
  is itself a matching stair type — boundary connectivity, not just the
  target tile's state, gates job creation.
- **The fortress-wide job list is `df.global.world.jobs.list`** (linked
  list, `.next`/`.item`), not `df.global.job_list`.
- **`quicksave` is asynchronous and its own log line is not a reliable
  signal in either direction.** Poll the save slot's mtime for up to ~90s.
- **Quicksave rotates forward through the `autosave N` slot pool,
  overwrite-oldest-first** — always re-read `cur_savegame.save_dir` fresh.
- **VM 103's SSH host key changes across a full Proxmox stop/start cycle**
  — expected, given documented intentional restarts; fix with
  `ssh-keygen -R <ip>` then accept the new key.
- **Every deployed perception-layer tool deliberately strips coordinates
  before returning anything** — by design, matching commitment #1. Don't
  expect a coordinate back from any perception query; an action tool has to
  compute and consume one internally, never return it. No known exception
  remains open (see above).
- **`unit-status hostile` (`dfhack.units.isDanger`/`isInvader`) is not a
  trustworthy fort-defense signal** — proven wrong in both directions the
  same day it was tested. Treat its output as "worth a second look," never
  as "confirmed safe" or "confirmed hostile" on its own.

### Other open items, carried forward

- **Design commitment #1's absolute wording vs. its actual evidence base**
  — still queued for a `decisions/DECISIONS.md` entry, deliberately not
  written yet (user's call on timing).
- **Live-view ingest**: shelved, see above. Once revisited: wire
  `DF_STREAM_INGEST_URL` in `.env`, convert `curl -F` to an S3-compatible
  signed PUT, fill in `IMAGE_BASE` in
  `willsmith-portfolio/public/dwarf-fortress/index.html`, commit, ask before
  pushing/deploying either repo.
- **The multi-agent-by-task decomposition and the MCP server/tool schema**
  — both unbuilt, both now the concrete next step toward `openclaw` actually
  driving the fort. Likely subject matter for the user's planned design/
  research phase, not started this session.
- **`infra/local.proxmox-access.md` is stale** — describes VM 104, node
  `proxmox`, pool `df-overseer`, user `df-overseer@pve`, all superseded by
  the live `.env` (VM 103, node `srv-01`, pool `df-overseer-sandbox`).
  Noticed this session, not yet re-recorded.

**Style note:** the user does not want em dashes in prose. Commas, colons,
semicolons or full stops instead. Fine as structural separators.

## Archived

- Sections through 2026-09-10 (fifth handover) — provisioning build,
  perception eval, fort ledger, systemd units, title-screen bootstrap,
  live-viewing/relay/tunnel, the tileset investigation, Site Finder
  resolution, the embark-flow saga through both forts founded, and the
  seed-landmark bootstrap — all moved wholesale to
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
- 2026-09-11: the 2026-09-11 VM-outage/quorum-incident writeup plus the
  entire 2026-09-10 end-of-session handover (VNC control channel, labor
  management/`autolabor`, the kea-combat finding, the quicksave root-cause,
  the perception-branch audit, both autonomous-play experiments, and the
  `find_diggable_area`/reachability corrections) moved wholesale to the
  same archive file — exceeded the ~400-line threshold by a wide margin,
  not superseded by new work. The handover at the top of this file is the
  compacted current-state summary, written deliberately thorough for a
  `/clear`; the archive has the full decision-by-decision detail.
- 2026-09-11 (documentation consistency pass): three fully-self-reporting
  ### threads moved wholesale to the same archive file: the compliance
  eval harness build (done for the session), mechanical prediction grading
  (built, selftested), and the full find_diggable_area/dig_diggable_area
  saga (built, live-verified, live-tested, the quickfort `-c` top-left-vs-
  center bug found and fixed, re-confirmed working end to end). None were
  gated on a human; item 10 in "What actually got built today" above now
  carries the compacted find_diggable_area/dig summary, and
  `decisions/DECISIONS.md`'s 2026-09-11 rows carry the full trail for all
  three.
- 2026-09-12: the entire 2026-09-11 end-of-session handover (the
  branch-merge question, the "what got built" list through item 12, and
  the peer-sessions/next-steps section) moved wholesale to the same
  archive file — the branch-merge question it spent most of its length on
  is resolved (merged, above), so it's fully superseded, not just over
  the line-count threshold. The handover at the top of this file is the
  new compacted current state.
- 2026-09-12 (session end, ahead of a `/clear`): this session's own content
  (the tool manifest build, both coordinate-leak fixes through deploy and
  live-verification, and the quorum correction) moved wholesale to the same
  archive file — it reports itself fully finished, nothing left gated on a
  human except the already-deferred design-commitment-#1 wording entry,
  carried forward unchanged. The handover at the top of this file is the
  fresh compacted current state, including two corrections the archived
  version's own text no longer reflects: both coordinate leaks are now
  fixed/deployed/verified (the archived text still frames them as open in
  a couple of places), and the driving-brain choice (`openclaw`) and
  live-view-ingest shelving are both folded in as settled state rather than
  same-session news.
