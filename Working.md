# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.

## Tool manifest built (2026-09-12, post-`/clear` session)

`scripts/dfhack/TOOLS.yaml` built — the one item the take-stock pass below
left outstanding. Per-CLI-subcommand metadata (not per-file): `effect`
(read/mutate), `coordinate_bearing` (false/internal-only/true, each `true`
annotated with why — spec-sanctioned exception, known gap, or out-of-scope
embark tooling), `live_deployed`, `verified` (date or honestly
`unverified`), and a `notes` pointer rather than re-narrated rationale.
Doubles as a first draft of the still-missing MCP tool schema per design
commitment #5.

Auditing every command's `coordinate_bearing` field this way surfaced a
**second, previously undocumented raw-coordinate leak**: `df-overseer-diff`'s
`recent-combat`/`since-report` both print `pos=%d,%d,%d` via their shared
`report_line()` helper, the same design-commitment-#1 violation as the
already-known `df-overseer-labor unit-status` leak, just not written down
anywhere until now. Recorded in the "Durable traps" list below and in
`TOOLS.yaml` itself; not fixed yet, same as the labor leak — flagging, not
silently patching, per this repo's own rule on docs/reality mismatches.

**Both coordinate leaks fixed, deployed, and live-verified.**
`df-overseer-labor.lua`'s `unit-status` and `df-overseer-diff.lua`'s
`recent-combat`/`since-report` all now resolve `near_landmark`/`direction`/
`distance_tiles` via `nearest_landmark` (reqscript'd from
`df-overseer-landmarks.lua`) instead of printing raw `pos=x,y,z`.
`home-lab-29` heads-upped and confirmed no collision (code-only file
overwrite in the guest's `hack/scripts/`, no VM lifecycle/pause/save touch),
then both files deployed via `install_df.py script-install` and
re-verified live against Uniboslan: `unit-status` (15 real citizens),
`recent-combat 5` (the real kea fight, 99 reports in memory), and
`since-report 0` (85 reports, cursor=99) all show `near_landmark=...`
throughout with zero raw `pos=` anywhere. Fort itself confirmed untouched
(same 15 citizens, all idle/healthy). `TOOLS.yaml` updated to
`verified: "2026-09-12"` / `live_deployed: true` for all three commands.

Also: `home-lab-29` (peer session, 20h uptime) corrected this file's carried-
forward quorum note on check-in — `pvecm status` confirmed `Quorate: Yes`,
2/2, checked fresh the morning of 2026-09-12; SRV-02 rejoined the ring
cleanly, the `pvecm expected 1` override on SRV-01 is stale. SRV-02's own
crash-pattern stability (76 reboots/8 days, PSU-connector reseat, held clean
since ~06:09 2026-09-12) is still genuinely open, not this repo's to fix.
Updated in place below rather than left stale.

## HANDOVER - 2026-09-12 (end of session, written for a `/clear`)

The entire prior handover (2026-09-11's end-of-session summary — the branch
audit, both autonomous-play experiments, the diggable-area saga) is archived
wholesale — [`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md).
**The headline: `perception-layer-experiments` is merged into `main` and
pushed. The branch this project spent three weeks deliberately keeping
separate no longer exists.**

### State at a glance, verified fresh, not assumed

- **Uniboslan, "Ragwind," is the one fort, healthy.** `pause_state=true`,
  15 citizens (the original 7 plus a migrant wave), 0 wounded, `alerts: []`,
  no stuck jobs — checked multiple times today across several live
  experiments, always confirmed undisturbed afterward.
- **`main` is merged, clean, and pushed.** `perception-layer-experiments`
  (14 commits) merged into `main` (`f078bf8`), six real conflicts resolved
  deliberately (not auto-accepted — see `decisions/DECISIONS.md`'s
  2026-09-12 row for the full per-file reasoning), then
  `df-overseer-combat.lua` folded into `df-overseer-diff.lua` (`6dd92bb`).
  22 commits pushed to `origin/main`. The branch and its worktree
  (`../df-automation-perception`) are deleted — **a fresh session should
  not look for that worktree, it's gone.**
- **`scripts/dfhack/` now holds 10 files, all live-deployed on VM 103**:
  connectivity, landmarks, overview, diff (now covering combat/threat
  detection too), openarea, chokepoints, stuckjobs, diggable, labor, ui.
  `df-overseer-combat.lua` no longer exists, folded in, not just deleted.
- **`learning/` exists**: `ledger/` and `predictions/` grouped under one
  parent (real code coupling, not just theme), done while `predictions/`
  was still untracked so it cost a `git mv` instead of a rename later.
- **Quorum: resolved, confirmed fresh by `home-lab-29` the morning of
  2026-09-12** (`pvecm status`: `Quorate: Yes`, 2/2 votes, both nodes in
  membership). SRV-02 rejoined the corosync ring cleanly; the `pvecm
  expected 1` override on SRV-01 is stale, not something to route around
  anymore. **Still genuinely open**: SRV-02's underlying stability —
  76 reboots in 8 days, came back after a PSU-connector reseat, crashed a
  few more times that evening, then held clean since ~06:09 2026-09-12. Not
  declared fixed; a PSU brick swap is under consideration if it recurs.
  Don't assume host uptime for anything relying on SRV-02. Not this repo's
  to fix, just current context. VM 103 itself: running, paused, 15
  citizens, 0 injured, untouched since this repo's last session.

### What actually happened today, compressed (full detail: `decisions/DECISIONS.md`'s 2026-09-12 rows)

1. **A Sonnet subagent brought `README.md` up to date** — its Status
   section still said "no game-side code exists yet," badly stale.
2. **An Opus-authored take-stock/architecture pass**, at the user's
   request: inventoried both the `main` and branch codebases, mapped real
   functional milestones (not dates), and argued against splitting the
   Lua tools into perception/action directories (every action tool is
   deliberately fused with its perception counterpart) in favor of a
   small tool manifest instead. **Built this session (see above),
   closing the one item from this pass that was still outstanding.** Its
   other recommendations were acted on: merge the branch (done, above),
   group `learning/` (done, above), fold `combat.lua`/`diff.lua` (done,
   above).
3. **A bounded Haiku-driven autonomous-play experiment**, testing whether
   a cheaper model can navigate the coordinate-free perception/action
   tools at all. It explored correctly, then guessed a Z-level (`z=0`)
   for `openarea build` since no tool exposed a landmark's own level —
   landed on a real but disconnected part of the map and got a silent,
   misleading no-op instead of an error, then mis-self-diagnosed it as
   "probably occupied tiles." **Root cause found and fixed**: both
   `ranked_candidates()` implementations (openarea, diggable) already
   resolved the landmark's real Z internally and were discarding it —
   `z` now defaults to it when omitted, backward-compatible. Deployed and
   live re-verified, read-only. The real finding: a weak model's failure
   mode here wasn't "gives up" (the honest thing a stronger model did on
   the first autonomous-play attempt, 2026-09-11) — it was "guess, then
   confabulate a plausible reason for the resulting no-op."
4. **The user caught an overstated claim and it held up under real
   research, not just an apology.** Relayed a claim that DFHack's `mode`
   being unavailable blocks unattended re-embark/reclaim outright — the
   user didn't believe it, correctly. Live-verified `mode`'s
   unavailability three ways (it's real), then a proper research pass
   found `mode` was never the mechanism either real embark (Artobcatten,
   Uniboslan) actually used — both went through `gui/embark-anywhere.lua`'s
   struct-write technique plus this project's own scripted UI navigation,
   already proven twice. The real gaps are narrower: an unresolved
   Confirm-click race-condition crash, and DF's actual fort-death
   behavior, never observed. `unretire-anyone` confirmed irrelevant
   (adventure mode only). `df-ai` read directly as outside corroboration —
   its death-detection technique is genuinely reusable, but it targets DF
   0.47, predating the v50 embark rewrite, so it says nothing about the
   Confirm-click crash specifically. **User's call: not worth pursuing
   further right now.** `docs/PURPOSE.md` corrected to match either way.
5. **Two more real bugs found live, fixed, and re-verified**, both while
   finishing the merge: `install_df.py`'s new `run` subcommand (call any
   deployed script by name, built this session) exposed that `pve.py`'s
   `log()` crashed outright on DF gamelog text containing a character
   outside Windows' console codepage — fixed to encode with
   `errors='replace'` instead of letting `write()` fail. And two DFHack
   API facts from the original perception-layer build (`getSize()`'s
   `cx,cy` being building-local not absolute; the real burrows path being
   `plotinfo.burrows.list`) were sitting only in a decision row, not in
   `memory/dfhack-environment.md` where they belong — added.

### Durable traps, still true (carried forward; additions marked NEW same as before)

Embark-screen automation mechanics (coordinate frames, `xdotool`
calibration, dead input paths, dialog handling, the click tool's known
flaws) are the permanent, living content of `docs/DF-UI-AUTOMATION.md` —
not duplicated here. This list is everything else: infra, project-wide
gotchas, and fresh findings without another doc home yet.

- NEW: **`ranked_candidates()`-style helpers that resolve a named
  landmark's own coordinate internally must actually use that resolved
  value everywhere, not just to validate the caller's separately-supplied
  one.** Found 2026-09-12 (the Haiku Z-default bug, above): the real
  coordinate was computed and then discarded in favor of a redundant,
  guessable argument. If a function already has the right answer
  internally, don't also ask the caller for it.
- NEW: **DF gamelog/report text is not guaranteed to be safely printable
  through a Windows console's default codepage.** Any tool that relays
  raw DF text (report text, unit/creature names) should encode
  defensively (`errors='replace'`) rather than let a bare `write()` choose
  how to fail mid-output.
- NEW: **`dfhack.buildings.getSize()`'s `cx,cy` are local to the
  building's own box, not absolute map coordinates** — add the building's
  own origin field before using them as a real coordinate.
- NEW: **`df.global.world.burrows.all` does not exist** — the correct
  path is `df.global.plotinfo.burrows.list`.
- NEW: **`df-overseer-diff`'s `recent-combat`/`since-report` used to leak
  raw `pos=x,y,z`** for every combat/threat report (both go through the
  shared `report_line()` helper) — a second, previously undocumented
  instance of the same design-commitment-#1 violation as the
  `df-overseer-labor unit-status` leak below. Found, fixed, deployed, and
  live-verified all the same session (2026-09-12) building `scripts/dfhack/
  TOOLS.yaml`'s coordinate-bearing audit.
- **Directly changing a live fort's pause state
  (`dfhack.world.SetPauseState(false)`) is blocked by Claude Code's own
  auto-mode classifier by default**, not something a bare mid-conversation
  "go ahead" reliably satisfies. Ask right before the call, get an
  explicit answer to that exact question; if still blocked, say so
  plainly rather than routing around it with an equivalent raw struct
  write.
- **`quickfort run <file>` resolves a plain filename relative to
  `dfhack-config/blueprints/`, not the working directory or an absolute
  path.** Write ad-hoc blueprints directly into that directory.
- **`save/current` is transient staging, not itself an addressable
  save** — a quicksave briefly writes there, then DF moves it into the
  real numbered slot (`cur_savegame.save_dir`) within moments.
- **`reqscript`-loading a `df-overseer-*.lua` file requires a
  `--@module = true` directive as a leading comment line**, and a
  module-loaded script's own CLI-dispatch code still runs during that
  load unless guarded (`if dfhack_flags.module then return end`).
- **VM 103 is running DF unattended with no network isolation boundary.**
  home-lab's own structural gap (Tailscale ACL Phase 5 unchecked) — not
  this repo's to fix.
- **DF ignores SIGTERM.** Quicksave before stop is mandatory once a fort
  is live; a bare stop takes the full timeout and ends in SIGKILL.
- **`-gen` fails silently** roughly a quarter of the time. Success is the
  region directory existing, never the exit code.
- **Saves live at the XDG path**, not in the game directory.
- **Never convert a booted VM to a template without sealing it.**
- **The published hostname is exposed.** The user chose not to rename it;
  `willsmith.nz` is deliberate, not a leak.
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **DF replay determinism is unverified. `hypothesis_id` has no registry.**
- **DONE 2026-09-12: the driving-brain choice decided — `openclaw`**, user's
  explicit call, not the originally-planned empirical 30-day survival test.
  `learning/` should still be built to the still-unbuilt MCP seam, not
  hand-shaped around openclaw's own conventions ahead of that seam
  existing — the choice being settled removes the uncertainty about which
  brain it eventually needs to fit, it doesn't change that sequencing.
  → `decisions/DECISIONS.md` 2026-09-12 row.
- **PVE's cloud-init takes only the first label of the VM `name`** —
  `install_df.py`'s `step_hostname` is the only workable route to a
  suffixed guest hostname.
- **`dfhack-run lua -f script.lua ARG1 ARG2` passes arguments via Lua
  varargs (`local x, y = ...`), not a global `arg` table.**
- **DF's save-slot names (`autosave 1/2/3`, `current`) are a shared,
  generic pool, not scoped per fort** — pull an `install_df.py backup`
  first, always, before founding any further fort.
- **A founded fort's own welcome dialog silently blocks all citizen
  activity even when `pause_state` reads `false`.** Always check for an
  undismissed dialog before concluding a fort is stuck.
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
- **VM 103's SSH host key changes across a full Proxmox stop/start
  cycle** — expected, given documented intentional restarts; fix with
  `ssh-keygen -R <ip>` then accept the new key.
- **Every deployed perception-layer tool deliberately strips coordinates
  before returning anything** — by design, matching commitment #1. Don't
  expect a coordinate back from any perception query; an action tool has
  to compute and consume one internally, never return it. **Known
  exceptions, not yet fixed** (both surfaced building `scripts/dfhack/
  TOOLS.yaml`'s coordinate-bearing audit): `df-overseer-labor unit-status`
  leaks raw `pos=x,y,z` for every citizen/threat row; NEW 2026-09-12,
  previously undocumented — `df-overseer-diff`'s `recent-combat`/
  `since-report` also leak raw `pos=x,y,z` (both go through the same
  `report_line()` helper) for every combat/threat report. Neither is in
  scope for a perception/action experiment until addressed.
- **`unit-status hostile` (`dfhack.units.isDanger`/`isInvader`) is not a
  trustworthy fort-defense signal** — proven wrong in both directions the
  same day it was tested. Treat its output as "worth a second look,"
  never as "confirmed safe" or "confirmed hostile" on its own.

### Other open items, carried forward

- **Design commitment #1's absolute wording vs. its actual evidence
  base** — still queued for a `decisions/DECISIONS.md` entry, deliberately
  not written yet (user's call on timing).
- **Live-view ingest (the public screenshot-push leg): explicitly shelved
  for now, user's call 2026-09-12** — not because it's redundant with the
  two working VNC streams (public view-only + authenticated admin), it
  isn't, it's a lighter-weight static-image embed meant to sit alongside
  the "watch live via noVNC" link on the portfolio page, just not a
  priority right now. Once revisited: wire
  `DF_STREAM_INGEST_URL` in `.env`, convert `curl -F` to an S3-compatible
  signed PUT, fill in `IMAGE_BASE` in
  `willsmith-portfolio/public/dwarf-fortress/index.html`, commit, ask
  before pushing/deploying either repo.
- **DONE 2026-09-12: the tool manifest built** (`scripts/dfhack/TOOLS.yaml`),
  see the "Tool manifest built" section above. Per-command (not per-file)
  metadata; doubles as a first draft of the still-missing MCP tool schema.
- **DONE 2026-09-12: `df-overseer-labor unit-status`'s raw coordinate leak
  fixed, deployed, and live-verified** — found 2026-09-11 setting up the
  Haiku experiment; fixed via `nearest_landmark`, same session as the
  manifest. See "Durable traps" above and `TOOLS.yaml` for detail.
- **DONE 2026-09-12: `df-overseer-diff`'s `recent-combat`/`since-report`
  raw coordinate leak fixed, deployed, and live-verified** — found and
  fixed the same session building the tool manifest's coordinate-bearing
  audit.

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
