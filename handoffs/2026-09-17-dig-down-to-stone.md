# Handoff: let the dig tools propose a way down to stone

**Dispatched:** 2026-09-17, by the orchestrating session. **Executor:** Sonnet, worktree-isolated.
**Stream status:** see `handoffs/INDEX.md`.

## Why

Uniboslan can't reach stone, and that blocks a lot:
- **Blocks and mechanisms** can't be made, and so the **well** can't be built. The fort has 0 BLOCKS and 0 TRAPPARTS.
- **The still** has thin material: the fort owns only 3 logs.

The fort lives at z168 (the farm room). Stone is at z167. `df-overseer-diggable find 1 1 -2 "Embark Site"` returns `[]`, because `borders_walkable_network` only checks the ring of tiles on the **same** z-level as the candidate. z167 has no walkable tile yet, so nothing there can ever qualify. The tool's own header already calls this a v1 scope limit. Recorded in `handoffs/2026-09-17-water-and-industry-tools.md`, "Stone access (item 6)", and `Working.md` HANDOVER 2026-09-17 START HERE item 3.

## Goal

The Architect can discover, and the Overseer can designate, a real way from the existing walkable network down to diggable stone one level below. The usual shape is a stair: an up/down or down stair designated on a walkable tile at z168, with the matching up stair directly beneath it at z167, plus room to dig from there.

Read before designing:
- **Boundary-connectivity lesson** (the diggable header, and the register 2026-09-10): a floor dig beneath a stair never became a job because the connecting tile wasn't a matching stair type. The stair pair has to be designated correctly on both levels.
- **The act/sense split** (`docs/AGENT-ARCHITECTURE.md`): finds and lists go on the Architect's read list, and writes go on the Overseer's write list only. This split is pinned by tests.
- **Design commitment #1:** no raw coordinates leave the script. Candidates are named relative to landmarks, as the existing finders already do.

**Prefer extending the existing `diggable.find` / `diggable.dig`** (for example a vertical, stair-down candidate kind) over new tool ids. If a new tool id really is the cleaner design, you may add one. Update `scripts/dfhack/TOOLS.yaml` (with a `knowledge_scope` tag and its justification), `agents/architect/tools.yaml` and/or `agents/overseer/tools.yaml`, and the pinned role tool counts in the tests. State the new counts in your report, because CLAUDE.md quotes them.

## Verification without mutating the fort

- **Read-only checks against the live fort (VM 103) only.** A find must return a real candidate at the embark. A dig dry run must describe exactly which tiles it would designate on each level.
- **No real designation.** The orchestrator runs that later, with the user aware.
- **Leave the fort paused.** Confirm `dfhack.world.ReadPauseState()` is true before your first read and after your last. If it's ever false, stop and report.
- **Test your changed script without replacing the deployed one.** DFHack caches scripts by name, so run your version from a temporary, uniquely named copy in `/tmp` with `dfhack-run lua -f` or an equivalent, and delete it afterwards. Never leave files under DF's script paths.

## Constraints

- **Branch** from current `main` and commit on your worktree branch.
- **Test suites** on `main`: the ambient `python -m pytest` gives **306 passed, 1 skipped**, and `.venv-dfmcp` `dfmcp/tests` gives **165**. `.venv-dfmcp` won't exist in your worktree, so say which interpreter you used.
- **Traps:**
  - `dfhack-run lua -e` silently does nothing on this build; use `-f` with a file.
  - Every output line carries an ANSI prefix.
  - `getWalkableGroup` takes `xyz2pos(x,y,z)`.
  - Never set DFHack globals; use `local` only.
  - Check every `pcall` result.
- **VM access:**
  - Use the `.env` keys `DF_VM_IP` (strip any `/24`) and `DF_SSH_KEY`, user `df`.
  - **Read those keys only**, with `grep -E '^KEY=' .env`. Never `cat` or filter the whole file.
  - No hostnames, addresses or tokens in anything you write.
- **Don't edit** `Working.md`, `decisions/`, `ROADMAP.md`, `CLAUDE.md`, `memory/`, `research/`, `doctrine/`, or `docs/TRAPS.md`. Put any new traps in your report.
- **Don't deploy** to VM 103.

## Touched surfaces

`scripts/dfhack/df-overseer-diggable.lua`, `scripts/dfhack/TOOLS.yaml`, `agents/architect/tools.yaml`, `agents/overseer/tools.yaml`, `dfmcp/tests/` and `tests/` (only as far as tool registration and role counts require), and this doc. **Not** `scripts/dfhack/df-overseer-farm.lua` (another stream owns it today).

## Report

- The design you chose, and the alternatives you rejected.
- What you changed.
- What you verified live, with the command for each check.
- What only a real designation can prove, written as a short test plan.
- Tool-count changes, if any.
- New traps.
- Suite counts and the interpreter you used.
- Your branch name and commit hashes.
