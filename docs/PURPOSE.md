# df-overseer

> Working draft, 2026-08-25. Consolidates the research in `research/`.
> Not yet implemented — nothing below has been tested against a running game
> except where explicitly marked *verified*.

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
| 24/7 video (OBS → Owncast/Twitch) | Continuous encode on a ProDesk already running DF | Low |
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
before. `FPS_CAP` and `G_FPS_CAP` are separate (`prefs/init.txt` lines 22–23):
cap simulation low, leave rendering at 50, and the world crawls while the
interface stays smooth.

| FPS_CAP | Real time / game year | Game years in 30 days |
|---|---|---|
| 100 (default) | 1.1 h | ~640 |
| 20 | 5.6 h | ~128 |
| 5 | 22 h | ~32 |

At `FPS_CAP:5`, a 60-second model turn is ~¼ game day — so the loop can be
**non-blocking**; no pausing to think.

**VM:** 2–4 vCPU (DF is single-threaded except line-of-sight; extra cores do
nothing, single-core clock is everything), 8 GB RAM (runtime is ~1–2 GB for a
small world; headroom is for the worldgen spike), 40 GB disk. Saves are
15–19 MB, so season-granularity snapshots for a month cost ~2 GB.

**Anti-decay suite** — all present in the install, enable via
`gui/control-panel` → Automation → Autostart: `deteriorate` (corpses, clothes,
food), `autobutcher`, `combine`, `logistics`, `cleanowned`, `clean`, `tailor`,
`suspendmanager`. `timestream` is a *pacing* fix ("dwarves feel zippy at low
FPS"), not a compute fix — it does not stop per-tick cost growing.

**Embark-time decisions outweigh every runtime fix:** 2×2 embark, small world,
short history, population cap, seal the caverns, break line-of-sight with
walls not doors. A blueprint library encodes this discipline for free.

**Pin DF and DFHack to update-on-launch-only.** A month is long enough that a
Steam patch lands mid-run and breaks memory offsets.

## Build order

1. **Perception eval harness.** Hand-written briefings, questions with known
   answers, measure comprehension. No running game, no agent needed. Tests the
   project's biggest risk in an afternoon.
2. `check_reachable` / `get_connectivity_report` — copies `warn-stranded.lua`'s
   working algorithm. Highest-confidence real code.
3. Landmark system on burrows + exits-first representation.
4. `get_overview` / context tiering with **deterministic JSON** (sort keys —
   Lua table order is not guaranteed, and a reshuffle silently busts the
   prefix cache every turn).
5. `get_diff_since` via `eventful`.
6. `find_open_area` (built terrain), hard radius cap from day one.
7. `find_chokepoints`, then `rank_candidate_sites`.
8. `get_stuck_jobs` — least-verified primitive; test in isolation.
9. `find_open_area` (cavern terrain) — genuinely hard, deliberately last.

## Open questions

- Which display to test first: game view (VNC → Pi → monitor, zero build) or
  chronicle (ESP32 + e-ink ambient panel).
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
- Repo has not yet adopted `claude-code-managed-repo-template` conventions.
