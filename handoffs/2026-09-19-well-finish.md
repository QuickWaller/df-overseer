# Handoff: finish the well and the brews, now that the orders are validated

Date: 2026-09-19. **Live stream. Owns VM 103 and the fort.** Continues
`handoffs/2026-09-19-well-and-harvest.md`; **read its whole write-up first**,
including the still-loss incident.

Read `CLAUDE.md`, then `docs/TRAPS.md` (all of it), then
`handoffs/2026-09-19-well-and-harvest.md`, then this.

## What changed since that stream stopped

Its three manager orders (1 blocks, 1 mechanism, 8 `BREW_DRINK_FROM_PLANT`)
never became jobs. The cause was found by a bounded read: **all three sat at
`status.validated=false`**. DF only turns validated orders into jobs, and
approval needs a Manager, which this fort lacks, or small-fort
auto-validation, which a 23-citizen fort has outgrown.

**The orchestrator set `validated=true` on those three orders, with the
user's explicit approval**, with the fort paused. It is a **one-off, labelled
exception**, because a real player cannot approve an order without a Manager.
**Do not set `validated` on any other order, and do not change
`df-overseer-orders.lua` to do it.** If you need a new order, it will stall the
same way; say so and stop, rather than validating it yourself.

The fort is **paused at tick 356606**. It owns 3 boulders' worth of stone
already mined, a mason's and a mechanic's workshop, the still, 8 gathered wild
plants, and 15 barrels.

## Deliverable

1. **Supervised unpauses until the three orders are fulfilled**: 1 block, 1
   mechanism, and brewed drink. Check `orders.list` and the stocks between
   bounded chunks. If an order is `validated=true` but still never becomes a
   job, **that is a new finding**: report it rather than guessing.
2. **Build the well** with `well.build` at the site `well find` returns, once
   BLOCKS and TRAPPARTS are both at least 1.
3. **Redeploy `dfseries/` to VM 103** from `main`, which you need for step 4:
   the VM runs a version from before the reset fix, which is why the last
   stream found no `resets` command. Same method as before
   (`git -c core.autocrlf=false archive`, hash-verify), same path
   (`/opt/df/dfmcp-smoke/dfseries`). The import timer keeps running; the
   database needs no rebuild (the reset fix changed no schema).
4. **Prove a dwarf drank from the well**: a `thirst_timer` reset after the
   well exists, from the sampler's history:
   `python -m dfseries.cli resets <db> unit:<id> thirst_timer` from
   `/opt/df/dfmcp-smoke`, with the database at
   `/var/lib/dfseries/uniboslan.series.sqlite3`. **Subjects are `unit:<id>`**,
   not `citizen`; `dfseries.cli timelines` and `series` help find ids. A drink
   could be water from the well **or** the new brewed drink, so say which, or
   say you cannot tell.

## Rules that will bite

- **Never run an unbounded query against the live DFHack process.** Bounded
  vectors only.
- **Quicksave before the first unpause, confirmed by slot mtime.**
- Supervised unpauses with a detached remote watchdog, in bounded chunks.
- **Do not resume a long-suspended job** without expecting it to run to its
  failure: that is how the last stream lost the still.
- Do not alter or cancel the `overseer-autosave` or sampler repeats.
- If a permission classifier refuses anything, **stop and report it**.
- SSH as `df`. `DF_VM_IP` carries a CIDR suffix to strip. Read secrets by key.
  **Never write an IP address, hostname or port into any committed file**; a
  test (`tests/test_no_leaked_addresses.py`) will fail the suite if you do.

## Write as you go

Commit on `main` (not worktree-isolated; own files only, `git status` first)
and append to this file's write-up at every milestone, **always the moment you
unpause and the moment you re-pause, with the tick**. Do **not** write
`Working.md`, `decisions/DECISIONS.md`, `memory/` or `handoffs/INDEX.md`. No em
dashes in prose.

## Touched surfaces

VM 103 and the fort, `dfseries/` deployed copy on the VM, and this handoff doc.
No repo source changes.

## Done means

The well exists, a thirst reset is recorded after it was built (with whether
it was water or brewed drink, or honestly unknown), the brews ran or the reason
they did not is stated, the fort is paused again, and stock before and after is
recorded.
