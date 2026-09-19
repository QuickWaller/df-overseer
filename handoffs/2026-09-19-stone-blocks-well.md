# Handoff: mine free stone, make blocks and a mechanism, build the well

Date: 2026-09-19. **Live stream. Owns VM 103 and the fort.** The user has
granted full authority; the fort is expendable.

Read `CLAUDE.md`, all of `docs/TRAPS.md`, the write-ups in
`handoffs/2026-09-19-well-and-harvest.md`, `2026-09-19-well-finish.md`,
`2026-09-19-feed-the-fort.md` and `2026-09-19-workshop-add-job.md`, then the
last three rows of `decisions/DECISIONS.md`, then this.

## Where things are

Paused at **year 31, tick 40916**. 22 alive, 1 dead (starved), nobody above
about 40,000 hunger. Stair dug to stone at z167/z166. Mason's workshop
("Stoneworker's Workshop"), mechanic's workshop ("Mechanic's Workshop"),
still, and a 4x4 farm plot (plump helmet) exist.

**There are zero free boulders.** The three mined earlier are all
`in_building`, the building material of the three workshops. **The deployed
`stocks.availability` still counts them as available** (a fix is being built
in parallel and is not deployed): **do not trust its BOULDER figure; check
`flags.in_building` yourself** with a bounded read of
`df.global.world.items.other.BOULDER`.

**The workshop job tool works** (`df-overseer-workjob.lua`, deployed): a real
`queue blocks "Stoneworker's Workshop" false` created one job, a dwarf took it,
and it cancelled only because no free boulder existed.

## Deliverable

1. **Mine a small amount of free stone**, enough for at least 1 block and 1
   mechanism with margin (a few boulders), using the existing dig tools near
   the dug stair. Confirm free boulders exist by the `in_building` check.
2. **Queue one blocks job and one mechanisms job** with `df-overseer-workjob`,
   **dry run first**, and run the fort until BLOCKS and TRAPPARTS (mechanism)
   each reach at least 1.
3. **Build the well** with `well.build` at the site `well find` returns.
4. **Prove a dwarf drank from it**: a `thirst_timer` reset after the well
   exists, from the sampler's history
   (`python3 -m dfseries.cli resets /var/lib/dfseries/uniboslan.series.sqlite3
   unit:<id> thirst_timer`, from `/opt/df/dfmcp-smoke`; `python3`, not
   `python`, on this VM). The fort already drinks from an unlocated source, so
   **a reset alone does not prove the well**: say what evidence ties a drink to
   the well (for example a well-drinking job or announcement), or say you
   cannot tell.

**Do not brew in this stream**: `workjob queue brew_drink` refuses on the
container reagent by design, and fixing that is separate work.

## Rules that will bite

- **Never set `validated` on anything, and never queue manager orders.**
- **Never run an unbounded query against the live DFHack process.** Bounded
  vectors only, never a tile scan.
- **Quicksave before the first unpause, confirmed by slot mtime.**
- **Supervised unpauses with a detached remote watchdog, in bounded chunks**,
  checking hunger, thirst and the dead count between them.
- **Stop and report at once if a citizen dies**, with tick, unit, hunger and
  thirst.
- `"Stoneworker's Workshop"` contains an apostrophe: pass it through a script
  file on the VM, not inline shell quoting. The MCP layer refuses it outright.
- Do not alter or cancel the `overseer-autosave` or sampler repeats. Do not
  resume a long-suspended job without expecting it to run to its failure.
- If a permission classifier refuses anything, **stop and report it**.
- SSH as `df`. `DF_VM_IP` carries a CIDR suffix to strip. Read secrets by key.
  **Never write an IP address, hostname or port into any committed file.**

## Write as you go

Commit on `main` (not worktree-isolated; own files only, `git status` first)
and append to this file's write-up at every milestone, **always the moment you
unpause and the moment you re-pause, with the tick**. Do **not** write
`Working.md`, `decisions/DECISIONS.md`, `memory/` or `handoffs/INDEX.md`. No em
dashes in prose.

## Touched surfaces

VM 103 and the fort, and this handoff doc. No repo source changes.

## Done means

Free stone exists and is proven free; a block and a mechanism were made by
workjob-queued jobs; the well exists; drinking from it is evidenced or
honestly marked unknown; no citizen has died (or any death is reported at
once); the fort is paused again; stock before and after is recorded.
