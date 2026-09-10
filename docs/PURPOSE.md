# df-overseer

> Working draft, 2026-08-25 (VM spec and game install updated 2026-08-27;
> status corrected 2026-09-08, rebuild completed later the same day).
> Consolidates the research in `research/`. Most of the design below has
> still not been tested against a running game; assume it is a proposal
> unless marked *verified*. Two layers under it are scripted, proven, and
> currently standing: the template and VM build (`scripts/provision_vm.py`),
> and the DF Classic plus DFHack install that runs headless and answers RPC
> (`scripts/install_df.py`). An earlier template and VM (built 2026-08-27)
> were deleted 2026-09-01 in an estate rebuild; today's VM, `df-colony-01`,
> is a fresh rebuild from this repo's own scripts, verified end to end
> (`decisions/DECISIONS.md` 2026-09-08 rows). DF itself has not been started
> and no world exists yet, so nothing is running unattended. The Proxmox
> identity they run against is provisioned outside this repo; see
> `infra/README.md`.
> No game-side *code* exists yet: no perception layer, no agent, no toolkit.
>
> **This banner is stale relative to `main`.** This file's status text
> above predates this branch's own most recent commits (build order items
> 2-4 below are marked Done, all verified live against a real, running
> fort). This is `perception-layer-experiments`, deliberately kept off
> `main` (see `Working.md`), so its own copy of this doc was never updated
> to match `main`'s. Check `main`'s copy of this file for the real current
> picture of the whole project; this branch's build order section below is
> accurate for the perception layer specifically.

## Purpose

**df-overseer turns Dwarf Fortress from a game you sit down to play into a
fortress that runs, survives, and tells its own story without you.**

It is built on DFHack in three layers. A **toolkit** of Lua and Python
automations that hold a fortress together against the item, corpse and
population accumulation that normally kills long runs. A **perception and
action interface** that exposes the game as structured state and typed
actions — never as a rendered map — so a language model can make the
decisions a player would. And an **observation layer** that makes the result
worth watching: an ambient display of the fortress going about its business,
and a written chronicle of what it did and why.

The near-term work is the first layer, used by hand: automations that make my
own forts less tedious and more survivable. That same tooling is the
substrate for everything above it, because it is one problem rather than two
— a fort that survives a month unattended is a fort that does not need
babysitting for an evening.

Fortresses are assumed to be **mortal**. Sieges, tantrum spirals and forgotten
beasts end them, and that is the format rather than a failure of it. What
persists is the world and the chronicle: when a fort dies the overseer
reclaims the site or embarks anew, and the history carries forward. The
long-term goal is a fortress living permanently on a screen in the room,
played by a model, generating a history worth reading.

## Design commitments

These are load-bearing. Breaking one invalidates work built on top of it.

1. **The model is never shown a map.** Not ASCII, not a render, not a tile
   grid. Transformers read a 2D grid as a 1D token sequence and cannot
   reliably reconstruct adjacency. Every spatial fact is computed in code and
   asserted in text. See `research/2026-08-25-spatial-perception.md`.
2. **Code does geometry; the model does judgment.** The model does not work
   out whether a room fits — it calls a tool and chooses among ranked,
   labelled candidates.
3. **Named landmarks and relative directions are the primary representation.**
   Coordinates exist as a code-only field. `"Dining Hall → Main Stair, NE, 9
   tiles, via corridor"` is a MUD room's exit list, an idiom LLMs have deep
   priors for.
4. **Blueprints, not generated coordinates.** The model picks a named template
   and an anchor; it never places individual tiles.
5. **The brain lives outside this repo.** This repo exposes DF over MCP.
   Whatever drives it — hermes-agent, openclaw, Claude Code — is a config
   change, not a dependency.
6. **The human view and the model view are different artifacts.** Pretty
   isometric rendering for the room; a structured briefing for the model.
   Never conflate their requirements.

## Scope

| In this repo | Out of this repo |
|---|---|
| DFHack Lua scripts (via `script-paths.txt`) | The agent brain, prompts, model choice |
| Perception service — briefings, landmark graph, tools | API keys, DeepSeek/hermes/openclaw config |
| DF MCP server + `dfhack-run`/RPC bridge | Proxmox host, Coolify, IPs, tenant infra |
| Blueprint library | DF save files (`save/` is gitignored) |
| Viewer / ambient display | |
| Chronicle (markdown, source of truth) | |
| Infra *shape*: VM spec, watchdog, save rotation | |

Public from day one. Infra specifics live in gitignored `infra/local.*` with
committed `infra/local.example.*`. Worldgen params are tracked so others can
reproduce the world; saves are not.

The chronicle is markdown in-repo for now. A live web dashboard published to
willsmith.nz is the intended public face — see *Streaming*, below.

## Streaming the fortress

The fortress should be visible on the public site, not just on a screen in the
room. One build serves four surfaces: the Pi on the wall, a phone, willsmith.nz,
and a shareable artifact.

Video and a dashboard are different bets:

| Approach | Bandwidth / CPU | Build cost |
|---|---|---|
| 24/7 video (OBS → Owncast/Twitch) | Continuous encode on a host already running DF | Low |
| **Periodic screenshot + live dashboard** | Near zero | Medium |
| Full custom web renderer (RFR → browser) | Near zero | High |

At `FPS_CAP:5` almost nothing changes in 30 seconds, so a periodic screenshot
conveys the fortress about as well as video does, at a fraction of the cost.
The distinctive part is not the picture anyway — it is the **chronicle and the
overseer's current reasoning** beside it. Nobody else's DF stream can show what
the player is thinking and why.

Start with screenshot + dashboard; treat real video as an upgrade if the still
image proves too static to hold attention.

## Memory and learning

The chronicle is one of four memory stores, not the whole of memory — see
`docs/MEMORY-ARCHITECTURE.md`. Doctrine (small, always-resident, cached) carries operational
rules; playbooks carry procedures; the fort dossier carries working state;
the chronicle carries narrative history.

Learning is **outcome tracking, not self-critique**: decisions record a
prediction and a check date, and the fortress judges them. Human guidance must
be written into doctrine to persist.

## Operating parameters

Verified against DF v53 / DFHack 53.16-r1.1 unless noted.

**FPS cap is the primary dial, not RAM.** One game year is 403,200 ticks.
Uncapped, a month of real time is ~640 game years — absurd, and FPS-dead long
before. `FPS_CAP` and `G_FPS_CAP` are separate tokens in
`prefs/init.txt` (**find them by name, not line number: they sit at lines
22–23 in the local Windows install and 71 and 75 on the VM**): cap simulation
low, leave rendering at 50, and the world crawls while the interface stays
smooth.

| FPS_CAP | Real time / game year | Game years in 30 days |
|---|---|---|
| 100 (default) | 1.1 h | ~640 |
| 20 | 5.6 h | ~128 |
| 5 | 22 h | ~32 |

At `FPS_CAP:5`, a 60-second model turn is ~¼ game day — so the loop can be
**non-blocking**; no pausing to think.

**VM:** 4 vCPU, **4096 MB** RAM with a 2048 MB balloon floor (DF is
single-threaded except line-of-sight, so extra cores do nothing and
single-core clock is everything), 25 GB disk, plus a 4 GB swapfile at
`vm.swappiness=10`. Sized 2026-08-26 against a 15.5 GB host, revised down from
6144 on 2026-08-27 so clones inherit the size the VM actually runs at.

**The worldgen spike was assumed to be the real peak; measured, it is not**
(*verified 2026-08-27*). Sampled every 0.5s across a whole `POCKET ISLAND`
generation: **peak RSS 561 MB**, swap untouched, available memory never below
2.5 GiB. DF sits at ~263 MB at the main menu, and KVM only backs pages the
guest actually touches. **This measures worldgen only** — a long-running fort
with hundreds of units and years of accumulated items is the actual memory
question and is still unmeasured, so 4096 MB is not yet vindicated, merely not
refuted. The swapfile is insurance rather than a fix. **Standing rule: read
`/nodes/<node>/status` live immediately before starting the VM, never size or
start from a number written in a doc — this host's usage moved 13.7 → 4.8 →
9.0 → 10.1 GB inside three days and the other VMs sharing it are outside our
pool and invisible to us. Gate on that endpoint's `available`, not its `free`:
`free` excludes page cache and collapses during any large copy, which on
2026-08-27 read as a 1.7 GB shortage while 5.4 GB was genuinely available.** A freshly generated pocket world saves at ~900 KB
(*measured*); the 15–19 MB figure from the local install is a save with a
played fortress in it, which is the number snapshot budgeting should use, so
season-granularity snapshots for a month cost ~2 GB.

**Anti-decay suite** — all present in the install, enable via
`gui/control-panel` → Automation → Autostart: `deteriorate` (corpses, clothes,
food), `autobutcher`, `combine`, `logistics`, `cleanowned`, `clean`, `tailor`,
`suspendmanager`. `timestream` is a *pacing* fix ("dwarves feel zippy at low
FPS"), not a compute fix — it does not stop per-tick cost growing.

**Embark-time decisions outweigh every runtime fix:** 2×2 embark, small world,
short history, population cap, seal the caverns, break line-of-sight with
walls not doors. A blueprint library encodes this discipline for free.

**The VM runs DF Classic (Bay12), not Steam** — decided 2026-08-26,
*installed and verified 2026-08-27*. Steam auto-updating DF mid-fort shifts
memory offsets and silently breaks DFHack, which was the biggest
month-long-run hazard; dropping Steam on the VM removes it entirely, along
with Steam Guard 2FA in provisioning and the Steam Linux Runtime gotcha. Steam
DF is still played locally. What is now on the VM is **DF v0.53.16 linux64
(build tag `ITCH`) with DFHack 53.16-r1.1**, the same DFHack version as the
local Windows install, so the availability findings in
`memory/dfhack-environment.md` carry over; audited against the Linux install
and they hold. Saves *should* be interchangeable between the two builds, and
that is still the one part of this decision nobody has tested — *verify, don't
assume*.

**DF runs headless under Xvfb** (*verified*). This revisits the 2026-08-25
rejection of headless DF, which was right that no text mode exists and beside
the point: nobody looks at the window, so a virtual framebuffer is enough to
satisfy SDL, and commitment #1 is untouched because the model never sees it.
Control is `dfhack-run` against the RPC server on `127.0.0.1:5000`.

Three lifecycle facts about that process, all *verified 2026-08-28*, and all of
them shape the systemd work:

- **Launch to a listening RPC socket is about 3 to 10 seconds.** The process
  starts immediately; there is no delayed start to wait out.
- **DF ignores SIGTERM.** There is no graceful shutdown: a stop waits the full
  timeout and then needs SIGKILL. So the unit must save through `dfhack-run`
  before stopping and allow a long `TimeoutStopSec`, or every host reboot kills
  the fort outright.
- **`dfhack-run` colours its output even when stdout is not a tty**, ending
  with a bare `[0m` on its own line, and prints
  `Could not connect to localhost:5000` when the game is down. Both bite: a
  health check that reads the last line gets the escape sequence, and one that
  merely tests for non-empty output passes against a dead game.

**Worlds are generated from the command line** (*verified*):
`./dfhack -gen <id> <seed> "<preset>"` runs silently and quits, so world
creation needs no UI driving at all. Preset names are compiled into the
binary. `POCKET ISLAND` is the current default: 17x17, stops at year 30,
~900 KB save in about 12 seconds. **It fails silently in roughly a quarter of
runs**, generating the full history and then never writing an export, with
nothing in any log; detect by the absence of the region directory, never by
exit code. Reproduced again on 2026-08-28 (one of two attempts on one world)
and now handled in `scripts/install_df.py gen`, which retries with a fresh
seed. Note that `save/current` survives a failed run, so its presence
afterwards proves nothing on its own: compare its mtime across the attempt. Embark is the next thing that will need UI driving, and how much of
it is scriptable is unknown.

**Saves live at `~/.local/share/Bay 12 Games/Dwarf Fortress/save/`**
(*verified*), not in the game directory. Anything that rotates, snapshots or
backs up saves must point there; the pre-v50 `<df>/data/save` layout that most
community writeups still describe does not exist on this build, and a script
aimed at it copies nothing and reports success. `scripts/install_df.py`
resolves the path from `getent passwd` (so it is right under sudo too), backs
it up with `backup`, and `verify` fails outright if `<df>/data/save` ever
reappears.

## Build order

0. ~~**Get DF and DFHack running on the VM.**~~ **Done 2026-08-27** — see
   `infra/local.df-vm-install.md`. Not originally on this list, and it blocked every
   item below it. **Scripted 2026-08-28** as `scripts/install_df.py`
   (`install` / `verify` / `start` / `stop` / `gen` / `saves` / `backup`), all
   verified against VM 104, so the install is now reproducible rather than a
   hand-built artifact to protect. Still missing: systemd units, so nothing
   inside the guest survives a reboot — and `onboot` is not set on the VM
   either, so the VM itself does not come back after a host reboot.
1. ~~**Perception eval harness.**~~ **Done 2026-08-27** — `evals/perception/`,
   99.1% across all three representations at n=108 each. Caveat that still
   stands: hand-authored 15-landmark fixtures, not the lossier real generator
   (build item 4 produces that), so item 1 wants re-running once it exists.
2. ~~**`check_reachable` / `get_connectivity_report`.**~~ **Done
   2026-09-10, named-endpoint stopgap resolved same day (separate
   session, `perception-layer-experiments`)** —
   `scripts/dfhack/df-overseer-connectivity.lua`, deployed via
   `install_df.py ui-install`. `get_connectivity_report()` calls
   `warn-stranded.lua`'s own `getStrandedGroups()` directly via `reqscript`
   rather than reimplementing it, confirmed live against a real fort
   (Uniboslan), and now carries `near_landmark`/`direction`/
   `distance_tiles` per stranded group. `check_reachable` (`check FROM
   TO`) resolves landmark names via item 3's `get_landmark_centroid`; the
   original raw-unit-id form is kept separately as `check-units` for
   low-level debugging. JSON output is deterministically key-sorted for
   free — DFHack's `json.encode` delegates to a C++ (jsonxx-derived)
   encoder, confirmed live across repeated fresh processes, not dependent
   on Lua's own table iteration order. → `decisions/DECISIONS.md`
   2026-09-10.
3. ~~**Landmark system on burrows + exits-first representation.**~~ **Done
   2026-09-10 (separate session, `perception-layer-experiments`, not
   `main`)**, after a first bootstrap-only slice earlier the same day
   (the seed "Embark Site" landmark, still kept for continuity).
   `scripts/dfhack/df-overseer-landmarks.lua` now enumerates real
   buildings (`buildings.all`, filtered to named ones) and burrows
   (`plotinfo.burrows.list` — NOT `world.burrows.all`, which does not
   exist, correcting this doc's own §10 prototype sketch), merges them
   with the persisted seed, and computes a nearest-3 exits graph per
   landmark with a live-verified `walkable` flag. Exports
   `get_landmark_centroid`/`nearest_landmark`/`list_landmarks` via
   `reqscript` for item 2 and item 4 to consume. Confirmed live against
   Uniboslan; found two real bugs the research doc's prototype sketch
   would have hit verbatim (`getSize()`'s `cx,cy` are local to the
   building's own box, not absolute) and one wrong prior conclusion (the
   embark wagon *is* a `building` object; the seed-landmark session
   checked the wrong list, `vehicles.all`). → `decisions/DECISIONS.md`
   2026-09-10 rows.
4. ~~**`get_overview` / context tiering with deterministic JSON.**~~ **Done
   2026-09-10 (same session/branch)** —
   `scripts/dfhack/df-overseer-overview.lua`, composing item 2 and item
   3's `reqscript` exports into a tier0 (fortress name) / tier1
   (population, landmarks) / tier2 (in-game date, alerts) shape. Key
   sorting is free (see item 2); array ordering (landmark list, exits) is
   sorted by name explicitly, since engine iteration order isn't. Fixed a
   second real `reqscript` gotcha in the process: a module load runs the
   loaded script's own CLI-dispatch code too unless guarded with
   `dfhack_flags.module`, which was leaking stray "usage: ..." lines
   ahead of the real JSON before the fix. `resource_summary` (needs a
   real prospect-equivalent scan) and event-driven diffing (item 5) are
   deliberately not attempted here. → `decisions/DECISIONS.md`
   2026-09-10 rows.
5. `get_diff_since` via `eventful`.
6. `find_open_area` (built terrain), hard radius cap from day one.
7. `find_chokepoints`, then `rank_candidate_sites`.
8. `get_stuck_jobs` — least-verified primitive; test in isolation.
9. `find_open_area` (cavern terrain) — genuinely hard, deliberately last.

## Open questions

- Which display to test first: game view (VNC → Pi → monitor, zero build) or
  chronicle (ESP32 + e-ink ambient panel). **Partially answered 2026-09-09**:
  game view was built and works — `x11vnc` on VM 103, bridged to a plain
  browser tab via a relay VM (`websockify`/noVNC), verified end to end on
  the LAN. The public/internet leg (Cloudflare Tunnel) and the literal
  physical Pi/monitor form factor are both still open; only "can a human
  watch the game view live" is answered, not "on what hardware." →
  `decisions/DECISIONS.md` 2026-09-09 rows,
  `research/2026-09-09-reverse-vnc-relay.md`.
- Loop shape — trigger (event-driven vs heartbeat vs self-pacing), and whether
  a two-speed strategist/operator split earns its complexity.
- Multi-agent: two agents on one fort is available today over shared RPC.
  Multi-fort round-robin is gated on automating retire/unretire, which DFHack
  53.16 cannot script (`mode` is tagged unavailable).
- **Adventure mode cannot run concurrently with an active fortress** — playing
  any mode locks the world (*verified*). A human visiting the agent's fortress
  as an adventurer works time-sliced (agent retires → play → retire → agent
  unretires) and needs no scripting, since a person can drive the UI. The
  "Save to a new Timeline" fork allows concurrency but the worlds diverge
  permanently. Worth designing for the time-sliced version.
- How much of **embark** is scriptable. `-gen` removed UI driving from
  worldgen; embark is the next thing to need it, and the answer decides
  whether an unattended re-embark after a fort dies is possible at all. Note
  that DFHack 53.16 cannot script mode switching (`mode` is unavailable), so
  this is not a solved problem by assumption.
- **A running fort's memory ceiling.** Worldgen answered a different question
  (above). Nothing is known about a fort at year 5 with 100 dwarves.
