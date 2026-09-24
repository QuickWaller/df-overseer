# Deploy pending fixes and place the Tomb zone over the ghost's coffin (2026-09-24)

## Context

`evals/live/2026-09-24-ghost-slab/` has the full history. A ghost (Kadol
Zulbanurdim, unit 454, a Forlorn haunt, not dangerous) needs burial. A coffin
is already built and standing (building 14), outside every existing zone. DF
requires a Tomb zone painted directly over a built Coffin before it can
receive a body (`zone list-kinds Tomb` -> `furniture_kinds = ["Coffin"]`,
DFHack's own `burial` script docs confirm the overlap requirement). `zone
place` could not do this until today: it lacked the `AROUND_FURNITURE`
exemption `zone find` already had, so it rejected the coffin's own tile as
occupied. That's fixed, offline, in `scripts/dfhack/df-overseer-zone.lua`
(commit `15d0bf1`), alongside an unrelated fix in `df-overseer-blueprint.lua`
(`jobs_claimed_by_a_worker`, commit `92c628a`). Neither is deployed yet.

**Explicit user ruling, this session:** the coffin's site (2 tiles north of
the Stoneworker's Workshop, chosen by a haul-distance heuristic that doesn't
even apply to a one-time furniture placement) is a poor choice, but this
fort is experimental and the user does not care. **Do not re-site or move
the coffin. Place the Tomb zone on top of it, wherever it is.**

## Your job

1. **Check in.** `ListAgents`, message any df-automation peer session if one
   shows up. None expected (checked from the orchestrator immediately before
   this dispatch).

2. **Deploy the two pending fixes** to VM 103 via `scripts/vm-ssh.sh df`.
   Follow this repo's established pattern exactly (see
   `handoffs/2026-09-17-farm-tools-deploy.md` for the full shape if you want
   a worked example):
   - Files: `scripts/dfhack/df-overseer-zone.lua`,
     `scripts/dfhack/df-overseer-blueprint.lua` to
     `/opt/df/game/hack/scripts/`; `scripts/dfhack/TOOLS.yaml` to the
     `dfmcp-server` install's tree (find the live path on the VM first,
     don't assume).
   - Build with `git -c core.autocrlf=false archive` (this workstation's
     autocrlf otherwise ships CRLF and breaks hash checks).
   - Back up whatever you're overwriting to
     `/opt/df/deploy-backup-2026-09-24-tomb` first.
   - sha256-verify each deployed file against the local commit
     (`git -c core.autocrlf=false show HEAD:path`), not the working copy.
   - Restart only `dfmcp-server`. Do not touch `df-fortress`/`df-xvfb`.
   - Confirm role tool counts unchanged in shape (overseer's list should now
     include the `AROUND_FURNITURE` arg on `place`; don't expect the count
     itself to move, this is an argument add not a new tool).

3. **Quicksave before any live fort action.** Read `cur_savegame.save_dir`
   before, fire quicksave, confirm it changed after (never mtime).

4. **Dry run first.** `zone place Tomb ... AROUND_FURNITURE=true` targeted at
   building 14's location (use `zone find Tomb "shale Coffin" 3 true` or
   equivalent, read-only, to confirm the coffin is visible to the
   furniture-aware search before attempting placement -- the README for this
   eval already showed this working read-only earlier today). Confirm the
   dry-run result reports `contains_qualifying_furniture: true` and the
   chosen site's tile set actually includes building 14's tile. If it
   doesn't, stop and report rather than force it.

5. **Real placement.** Same call, dry run off. Confirm the zone was created
   and `zone contents`/`zone list` shows it owning the coffin.

6. **Bounded unpause to observe burial**, same shape as the prior stage runs
   in this eval directory (bounded tick budget, poll safety slices, stop on
   tripwire or budget, whichever first -- 6000 ticks is a reasonable budget
   matching the prior stage's actual observed cost). Watch for: the corpse
   (item 2804) getting hauled and moved into the coffin/building 14, and
   `unit-info-viewer`'s `ghost_info` for unit 454 changing away from
   Forlorn/active. Do not change any labor, do not assign the coffin to a
   unit unless that turns out to be required for burial to proceed (check
   docs/read before doing it, don't guess).

7. **Write up** in `evals/live/2026-09-24-ghost-slab/` (extend the existing
   README, add new slice/output files following its existing naming), same
   rigor as the file's earlier stages: what was checked, what ticks/tools
   were run, safety slices, and an honest conclusion on whether burial
   actually happened and whether the ghost's haunt status changed.

## What you do NOT own

Per this repo's handoff convention: do **not** write `Working.md`,
`decisions/DECISIONS.md`, or anything in `memory/`. Commit your own code and
eval-directory changes as you go (this stream owns no repo code files besides
what's already deployed offline; if you find you need to touch a `.lua` file
live, stop and report rather than diverging from what's already reviewed and
committed). Report back what you did, what you found, and anything you'd
flag for the orchestrator to decide.
