# Durable Traps

Hard-won facts about this project's live environment that cost real time to
find. **Reference material, not a work log.** Each entry exists because
something failed in a way that was not obvious, and each is worth reading
before touching the area it describes.

Moved here 2026-09-12 from `Working.md`'s rolling handover, where it had been
carried forward by hand across many sessions. It was reference rather than
work-in-progress, so an archive pass would have buried it; `Working.md`'s
archive-cadence rule is about finished work, and this list is never finished.

Scope note: embark-screen automation mechanics (coordinate frames, `xdotool`
calibration, dead input paths, dialog handling) are deliberately NOT here.
They are the permanent living content of
[`DF-UI-AUTOMATION.md`](DF-UI-AUTOMATION.md). This file is everything else:
infra, platform behaviour, and project-wide gotchas.

Add to this file rather than to `Working.md` when a new one is found.

---

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

---

## Added 2026-09-12, from the detectors' live-verification session

- **`kill-lua` does NOT rescue a DF process stuck in a long-running Lua loop,
  despite what `SF_DONT_SUSPEND` suggests.** A runaway script pegged `dwarfort`
  at 95.6% CPU for over nine minutes and blocked every subsequent `dfhack-run`
  call. `kill-lua` was attempted at 20s and again at 90s; **both hung.** This
  directly contradicts the expectation
  `research/2026-09-12-dfhack-capability-checks.md` §3 drew from reading
  `RemoteTools.cpp`, where `RunCommand` is registered `SF_DONT_SUSPEND`
  specifically so that "this remote server connection could be the last chance
  for recovering from stuck Lua scripts". The escape hatch exists in the source
  and did not work in practice. **Do not rely on it.** Recovery was algorithmic,
  not administrative: fix the script and wait. No VM operation was needed, and
  none should be reached for first.
- **Allocating a closure per iteration is catastrophic at map scale, roughly two
  orders of magnitude.** A `pcall(function() ... end)` wrapped around each of
  ~6.86M tiles took **9+ minutes**; the identical scan with the per-tile closure
  removed took **~25 CPU-seconds**. Any full-map tile sweep must hoist the
  function out of the loop, or avoid `pcall` per tile entirely. Relevant to any
  future whole-map scan, which this project will keep wanting.
- **A full 26,784-block scan reading one flag per block is genuinely cheap:
  ~0.057s CPU, measured.** So block-level sweeps are affordable and tile-level
  sweeps are not, by a factor of hundreds. Design polling around blocks.
- **`designation[x][y].liquid_type` binds to a plain Lua boolean on this build**
  (`false` = Water, `true` = Magma), **not** the `df.tile_liquid` enum integer.
  Comparing it against `df.tile_liquid.Magma` is always false. This install's own
  `modtools/spawn-liquid.lua:11` hedges by testing both forms of the same field,
  so treat the binding as version-unsafe and check both. Cost a real bug in
  `df-overseer-breach.lua`, found only by live verification.
- **`block.flags.update_liquid` appears to mean "this block's liquid just
  changed", not "this block contains liquid".** Zero of 26,784 blocks had it set
  across 11 polls, including through an 85-second unpaused window, on a map that
  demonstrably contains water. The water in question is fully settled
  (`flow_size=7`, topped out). **Unresolved**: whether DF sets it during
  genuinely active liquid movement. Anything built on this flag is unproven
  until that is answered.

