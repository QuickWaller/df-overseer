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


## Added 2026-09-12, from building the MCP server

- **This repo's package is `dfmcp`, not `mcp`, and it cannot go back.** The
  Python MCP SDK is imported as `mcp`, and a top-level `mcp/` directory in this
  repo wins over site-packages for anything running with the repo root on
  `sys.path`: every `pytest` run from the root, and the server process itself.
  While it was named `mcp/`, `import mcp.server` resolved to **us**, so the
  transport could not have imported its own SDK. Verified both before and after
  the rename by running `import mcp` from the repo root and from elsewhere.
  **If an SDK import ever appears to resolve into this repo, that is this
  collision returning.** Do not fix it with a `sys.path` manipulation; the
  collision is on the top-level name, so moving files does not help either.
- **A test file that imports an optional dependency must guard its own import
  at module scope**, or it takes the entire suite down with it. A bare
  `ImportError` during collection is not one failing file, it is a pytest
  *collection error* that aborts the run: adding `dfmcp/tests/test_server.py`
  unguarded would have turned 121 passing tests into zero run and one error in
  any environment lacking the pinned SDK. **So this repo's ambient baseline is
  deliberately `121 passed, 1 skipped`, and that skip is correct rather than a
  regression.** The full count (136) needs the pin installed.
- **Install `dfmcp/requirements.txt` into a dedicated venv, never the shared
  environment.** A verified conflict already exists on this machine: an
  unrelated `fastmcp` package pins the SDK below the major version this repo
  needs. `python -m venv --system-site-packages .venv-dfmcp` (gitignored).
- **A DFHack RPC connection carries exactly one request at a time.** The
  per-connection server thread is a strict read, process, reply, read-next
  loop, and the protocol's own documented conversation flow agrees. So
  concurrency, including the "batch a cycle's reads into one suspend window"
  optimisation, needs a **pool of connections**, never several requests
  pipelined down one. This corrected a design requirement that had said "one
  persistent connection" (`docs/AGENT-ARCHITECTURE.md` §14 item 5).
- **The `dfhack-run` colour-escape trap above does not apply over RPC.** A
  tool's `print` arrives as one text fragment with colour in a separate
  protobuf field, never embedded in the text, so JSON parses cleanly with no
  sanitising. The escape sequences are `dfhack-run`'s own terminal rendering,
  a property of that client and not of the wire.

## Added 2026-09-14, from the first live MCP smoke test

- **A fake server built from the wire spec verifies the wire, not the
  payloads.** `dfmcp`'s fake DFHack spoke the protocol byte-for-byte, and all
  136 tests passed, but its canned tool output was a JSON object while every
  real find/list script prints a bare array. The server mishandled arrays and
  nothing noticed until real DFHack answered. **Copy fake payloads from real
  script output**, not from what the output "probably looks like".
- **MCP `structuredContent` must be a JSON object on the protocol versions
  clients negotiate today.** A list there is not rejected when the handler
  returns, only when the SDK serialises the result, so it surfaces as an
  opaque protocol error (`-32603 Handler returned an invalid result`), not a
  tool error the model can read. Newer protocol revisions allow any JSON
  value, so the failure depends on the client.
- **`python3 -m venv --help` succeeding proves nothing.** It only parses
  arguments and exits 0 even when `ensurepip` is missing, which Ubuntu 24.04
  cloud images ship without. Only creating a venv proves venv works.
- **A dependency the ambient environment happens to have is invisible to every
  local test run.** `pyyaml` was imported by `dfmcp` and missing from its
  requirements file for the whole build. A clean venv on a fresh host is the
  first place that shows up.
- **This workstation's `ssh.exe` hangs when a remote command backgrounds a
  long-running process**, even with `ssh -n` and
  `setsid nohup ... > log 2>&1 < /dev/null &`. Seen twice on VM 103 while
  starting the MCP server. The remote side was healthy both times, correctly
  detached, serving requests; only the local `ssh` invocation refused to
  return for 120s or more. Do not diagnose it as a server-side failure. Check
  the remote state from a second connection instead.
- **`pgrep -f <pattern>` run over SSH matches the wrapper shell running the
  check itself**, so "is it still running?" answers 2 when the answer is
  really 0. Use `ps -eo pid,etimes,cmd | grep "[p]attern"` and look at the
  elapsed time, or check the listening port, which cannot match itself.

## Added 2026-09-14, from the openclaw schema stream

- **A "not found anywhere" search of a bundled app is only as wide as the
  files it read.** `/app/openclaw.mjs` in the openclaw image looks like the
  bundle and is a 22 KB launcher; the code is in thousands of chunk files.
  An executor searched only that file and reported five config variables and
  a `/healthz` route as nonexistent; four of the variables and the route were
  there. Before trusting an absence claim, check the size of what was
  searched and search the whole tree (`grep -rlF <name> /app --include=*.js
  --include=*.mjs`).
- **openclaw `agent exec` says `Unknown model` when the provider key is only
  in the environment**, even though `models status` shows the key detected.
  It is a local, pre-network failure, so it costs nothing but looks like a
  wrong model id. What fixed it was `openclaw models auth paste-api-key
  --provider <p>`, which stores the key plaintext in `state/openclaw.sqlite`.
  Try `openclaw secrets store` before accepting that on a host that matters.
- **`dfhack-run` output starts with an ANSI colour escape** (`\x1b[0m`), so
  piping it straight into a JSON parser fails at char 0. Strip escapes first;
  it is not a broken script.
- **A secret-scan loop that writes its pattern file to `$TMPDIR` checks
  nothing when `$TMPDIR` is unset in Git Bash.** The writes fail, the loop
  keeps going and prints "done". Give every scan a positive control (a string
  you know is present) so a broken scan cannot pass as a clean one.
- **openclaw's config home in the image is `/home/node/.openclaw`**, not
  `/root/.config/openclaw`. Mounting the wrong one does not error: openclaw
  just starts with an empty config, and `secrets audit` reports "clean".

## Added 2026-09-14/15, from the architect runs, the dfmcp fixes and the queue

- **An optional absolute argument with a good default still leaks
  coordinates.** 2026-09-11 made the spatial tools' `Z` default to the
  landmark's own level, so the default was coordinate-free, but asking for
  any other level needed an absolute DF z (the map runs 0-185 and the
  landmarks sit at 168-169). The architect passed 0 to -4, got silent `[]`,
  and concluded there was nothing underground; level -1 actually had 5 dig
  candidates. Fixed with a relative `LEVEL`. An off-map value is now a named
  error rather than an empty list, and every MCP argument has a description.
- **In the mcp 2.x SDK, `CallToolResult` is built with `isError=` but read
  as `result.is_error`.** Reading `result.isError` raises `AttributeError`;
  the tests caught it.
- **`dfhack.world.ReadCurrentTick()` is `df.global.cur_year_tick`** (ticks
  within the current year, reset every year), **not
  `world.frame_counter`**. Verified live 2026-09-15: 178877, 178877 and
  44275 respectively. An executor cited docs saying `frame_counter`; the
  live reading settled it. Absolute tick = year × 403200 + tick.
- **`overview.get` output is nested**: `tier0.fortress`, `tier1.population`,
  `tier1.landmarks`, `tier2.in_game_date`, `tier2.alerts`.
  `landmarks.list` and `stuckjobs.find` print bare arrays. Copy fixtures
  from real output (`dfhack-run ... | sed` to strip the ANSI prefix) rather
  than from the script's name for a field.
- **Executor "byte-for-byte identical" claims need a hash.** Architect run
  #2's config differed from run #1's in a `_note` string despite that claim.
  It was harmless, but only a `sha256sum` or `diff` showed it.
- **A fake address used as a leak-scan positive control is still an address
  in a public repo.** Use RFC 5737 documentation ranges (`192.0.2.x`), so
  future scans can exclude it cleanly.
- **`python3` does not exist on this workstation, and `py -3` is a 3.13
  without pytest.** Use `python` (3.12) for the ambient suite and
  `.venv-dfmcp/Scripts/python` for `dfmcp/tests`.
