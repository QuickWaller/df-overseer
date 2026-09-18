# Handoff: build the well, and harvest a lot of plants

Date: 2026-09-19. **Live stream. Owns VM 103 and the fort.** User-directed.
The fort is expendable and the user has granted full authority; you need no
human go-ahead to unpause, designate or build.

Read `CLAUDE.md`, then `docs/TRAPS.md` (**all of it, especially the last two
entries**), then `Working.md`'s HANDOVER 2026-09-19, then
`handoffs/2026-09-18-well-unblock.md` including its write-up (the incident
and the wood-mechanism finding), then `doctrine/seed.yaml`'s
`brewing-chain-from-raws`, `plump-helmet-is-brewable` and
`brew-before-plants-run-out`, then this.

## Where the fort is

Paused at tick **283992** (year 30), **23 citizens, 0 dead**. Owns 3 logs, 0
boulders, 15 empty barrels, buckets and chains, a built still. The first farm
plot and the `WaterSource` zone were **lost in the 2026-09-19 rollback**.
Runs at **100 FPS** (not 10, whatever older docs say), so a game day is about
12 real seconds.

Two in-game repeats run and **must not be altered or cancelled**:
`overseer-autosave` (quicksave every 7 game days) and the time-series sampler
(one record per game day). Your run will be recorded by the sampler; that is a
feature, and the imported history on the VM is a good way to check progress.

## Goal 1: a working well

Settled already, so do not re-derive: the well needs **BLOCKS and a
mechanism (TRAPPARTS)**, which on this install need **stone** (no reaction
makes a mechanism from wood; `stockflow.lua` offers mechanisms only under rock
and metal). The fort has 0 boulders; stone is at z167 behind an orphaned,
half-designated stair. The user's direction: **mine a little and cut blocks.**

The chain: dig down to stone (the merged `dig-stair` tool, which ranks out
occupied spots) → mine enough stone for blocks plus one mechanism → a
**mason's workshop** (blocks) and a **mechanic's workshop** (mechanism) via
`workshop.build` → manager orders via `orders.create` (it knows `blocks` and
`mechanisms`) → the well via `well.build` at the site `well find` returns.
Check labours (mining, masonry, mechanics) before assuming anyone will take
the jobs; `autolabor` is on, and hand-setting a labour takes it off autolabor
fort-wide permanently, so prefer letting autolabor allocate.

**Done for the well means dwarves drink from it**: a thirst reset recorded for
a citizen after the well is built, readable from the sampler's history
(`dfseries` on the VM can answer `resets` for `thirst_timer`). A well that
exists but nobody uses is not done.

## Goal 2: harvest a lot of wild plants

The user wants **a bunch of wild plants harvested**: **gathering wild plants**
(the herbalism labour), not farming. The user clarified this explicitly, so
do not build a farm plot as part of this stream. Find the real route on this install
rather than assuming one: whether DFHack or an existing
`df-overseer-*` tool can designate plant gathering, and which labour does it
here. If no tool exists, that is a **lever gap worth recording**, and a
bounded one-off action is acceptable for this stream.

**Then brew.** Doctrine `brew-before-plants-run-out` (from the user) and
`brewing-chain-from-raws` (5 drinks and a seed back per plant, container any
empty `FOOD_STORAGE`, and the fort owns 15 barrels): queue brewing on the still
for what is gathered, so the plants become drink before they rot. Prefer
brewable plants when choosing what to gather.

## Rules that will bite

- **Never run an unbounded query against the live DFHack process.** On
  2026-09-19 one wedged the command pipe, took the watchdog's pause call with
  it, and forced a kill that rolled the fort back 22,000 ticks. **Finding
  shrubs or trees by scanning map tiles is exactly that kind of query.** Use
  the bounded vectors (`df.global.world.plants` and its sub-vectors), never a
  tile sweep.
- **Quicksave before the first unpause and confirm it by slot mtime.**
- **Supervised unpauses with a remote watchdog**, detached from the SSH
  session, as the sampler stream did. Run in bounded chunks and check progress
  between them rather than one long unattended run.
- **No coordinates in any committed output.** Tools strip them by design.
- SSH as `df`, not root. `DF_VM_IP` carries a CIDR suffix to strip. Read
  secrets by key, never `cat .env`. **Never write an IP address, hostname or
  port into any committed file.**
- If a permission classifier refuses an action, **stop and report it**. Do not
  route around it.

## Write as you go

Streams die on session limits routinely. Commit on `main` (you are not
worktree-isolated; commit only your own files, `git status` first) and append
to this file's write-up **at every milestone**, and **always the moment you
unpause and the moment you re-pause, with the tick**, so a cut-off never
leaves the fort's state unknown.

Do **not** write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
`handoffs/INDEX.md`. No em dashes in prose.

## Touched surfaces

VM 103 and the fort, this handoff doc, and a new `scripts/dfhack/` tool **only
if** plant gathering genuinely needs one (say so first in the write-up; do not
touch existing tool files).

## Done means

The well exists and a dwarf has been recorded drinking from it; a substantial
batch of plants has been gathered and brewing is queued or done; the fort is
paused again; and the write-up records the stock before and after (stone,
blocks, mechanisms, plants, drink), every unpause window with its ticks, and
any lever gap found.
