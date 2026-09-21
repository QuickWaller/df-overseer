# Handoff: doc drift pass after the 2026-09-21 tool batch went live

Date: 2026-09-21. **Documentation and manifest-flag stream** (worktree, Sonnet).
Offline: no VM, no live game. Follows the pattern of
`handoffs/2026-09-17-doc-drift-pass.md`; read it and its Result first.

Read `CLAUDE.md` (the rules, especially "If the docs and the actual repo state
disagree, flag it"), `handoffs/INDEX.md` (rows from 2026-09-21), the register rows
of 2026-09-21 in `decisions/DECISIONS.md`, and the deploy report at the end of
`handoffs/2026-09-21-deploy-building-batch.md`, then this.

## What changed since the docs were last touched (facts, all from the register or
the handoff reports; do not re-derive)

1. **Deployed and live on VM 103, 2026-09-21:** the generic `building` tool
   (`list-kinds`, `find`, `build`; dry runs only, no never-built kind built for
   real), `labor enabled-counts`, `gotchas.get`/`gotchas.write` with a static
   confidence file and `tool_guidance` enrichment, the labor graph and join
   (`production/labors.py`, deployed database), `nobles` (`list`, `verify`,
   `appoint`, `unappoint`), and the generalised `zone` tool (18 kinds, optional
   owner). Role tool lists are now **architect 34, overseer 57, consultant 14**
   (were 25/45/11). Ambient suite **891 passed / 3 skipped**, `.venv-dfmcp` **537
   passed**. A fix to the labor join's result shapes is merged but **not yet
   redeployed** (`dfmcp/labor_join.py`, `dfmcp/tool_guidance.py`).
2. **Fort:** paused at year 31, tick 106974, 22 alive, MANAGER appointed (unit 345),
   no Office, queued manager orders still do not run.
3. **Findings that belong in docs:** DFHack's material filters for standard buildings
   are its own tables, not the game's; the Mason's Workshop labor is STONECUTTER
   and STONE_CARVER, never MASON; 145 reactions (`MAKE_ENT<n> <PART>`) exist only in
   the world save, not in any raw file; DFHack's `workshops.getJobs` builds a
   workshop's job list including reaction jobs with reagents converted to job
   items, and a job has a `repeat` flag; the Manager position has
   `required_office` 1 and the fort has no zones; quickfort knows 18 zone kinds.

## Deliverables

1. **`scripts/dfhack/TOOLS.yaml`: make the manifest tell the truth about deployment.**
   Every command of the building, labor `enabled-counts`, nobles and zone tools
   still says `live_deployed: false` (or an "offline / not yet deployed" note) though
   the deploy report shows them live and verified. Set `live_deployed: true` and
   update the `verified` string only where the deploy report or the live tests
   actually verified it (say which, in the string); leave `false` where nothing
   verified it (for example `zone place` real path, `build` real path, the
   `with_event` nobles versions). Do not change behaviour, signatures or notes
   about behaviour.
2. **`agents/*/tools.yaml` and `agents/*/role.md`**: remove or correct "Not yet
   deployed" notes for the ids now live; check each new id's note reads correctly;
   confirm the confidence-legend pointer in each `role.md` reads well. Do not change
   which tools a role holds.
3. **`docs/BUILDING-TOOL.md`**: it is a design note written before any of this was
   built. Mark what is now built and deployed, tick off the open questions the
   builds answered (labor source, material filters, W and H, the ConstructBlocks
   disagreement, hosting), fix the contracts section to what was implemented
   (C1 shapes as the Lua really returns them, C2 `labors_for_kind`, C3 enrichment
   as the sibling `tool_guidance` key), and end with what is still open. Keep the
   design history; add a status block at the top, do not rewrite it.
4. **`docs/TRAPS.md`**: add entries (each with the date, the symptom, the cause, and
   what to do) for: (a) `quicksave` rotates slot directories, so a
   "current/world.sav mtime changed" check can pass for the wrong reason: read every
   slot's `world.sav` mtime and the fort's `cur_savegame.save_dir`;
   (b) `dfhack-run lua -f` does not provide `dfhack_flags`, so a module-style script
   needs a small wrapper; (c) DFHack's `ipairs` over a game vector starts at 0, so
   copying an index from `ipairs` into a 0-based field is correct, and a guess that
   it is off by one is wrong; (d) on this Windows workstation `core.autocrlf` means a
   working-copy sha256 will not match deployed bytes, hash `git -c core.autocrlf=false
   show HEAD:path`; (e) long shell heredocs containing quotes have been rejected at
   parse time in this harness, so write files with the editor tool and run a script;
   (f) subagent worktrees are created from `origin/main` and carry their own copy of
   `.claude/settings.json`, so an unpushed commit or uncommitted setting never reaches
   them, and the first instruction to such an agent should be `git merge --ff-only`;
   (g) auto mode's classifier reads its own `autoMode` configuration only from user or
   managed settings, project `permissions.allow` rules do not override it and broad
   ones are dropped, and a list without `"$defaults"` replaces the defaults (see the
   register row of 2026-09-21); (h) `DF_VM_IP` in `.env` carries a CIDR suffix; strip it
   before ssh; (i) raws are not the whole reaction list (the 145 generated reactions
   live only in the save). Check `docs/TRAPS.md` for existing entries that already say
   any of these and extend instead of duplicating; also check the entry about hunger and
   thirst counters against `scripts/dfhack/df-overseer-sampler.lua` (which reads
   `counters2`) and flag any contradiction.
5. **READMEs and design docs**: `dfmcp/README.md` and `gotchas/README.md` (counts, the
   labor join and its result shapes, the deploy needs); `docs/AGENT-ARCHITECTURE.md`,
   `docs/MEMORY-ARCHITECTURE.md`, `docs/PRODUCTION-MODEL.md` and `docs/TIMESERIES.md`:
   hunt for statements the facts above contradict (tool counts, "nothing deployed",
   "no tool builds workshops", "no manager appointment", labor from `[SKILL]`,
   "the raws hold every reaction") and **fix mechanical ones; list judgement calls in
   your report instead of rewriting a design**. Do not edit `docs/PURPOSE.md`,
   `docs/ARMOK-RULINGS.md` or `docs/DFHACK-INVENTORY.md` (generated).
6. **Dead and duplicate files:** list, do not delete, anything now obsolete
   (for example the dead stand-in building script in `dfmcp/tests/gotchas_support.py`
   the optional-args stream flagged).

## Rules

- You own the files named above and this doc. **Do not touch** `Working.md`,
  `decisions/DECISIONS.md`, `memory/`, `ROADMAP.md`, `CLAUDE.md` or
  `handoffs/INDEX.md` (the orchestrator is editing them in parallel), and change no
  code behaviour.
- Every changed statement must be checked against the primary source (a file, a
  report), never against another doc's summary. Where you cannot check, say so
  instead of writing it. Nothing verified is downgraded and nothing unverified is
  promoted.
- No address, hostname or token in any tracked file. No em dashes in prose. Commit
  after each deliverable and extend this doc's report as you go. Use the Write tool
  for scratch scripts rather than long inline shell heredocs.

## Done means

The manifest's deployment flags match the deploy report, no doc in the list still
says something the facts above contradict (or it is named in the report as a judgement
call), the new traps are recorded, the suites still pass (baseline **891 passed /
3 skipped** ambient, **537 passed** in `.venv-dfmcp`, report before and after), and
the report lists every contradiction found and what was done about it.

---

## Report (executor, 2026-09-22, in progress)

Baseline before any edit, measured in this worktree: ambient `python -m pytest`
**891 passed / 3 skipped**; `.venv-dfmcp` `dfmcp/tests` **537 passed**.

### 1. `scripts/dfhack/TOOLS.yaml` (done)

Flags flipped to `live_deployed: true`, each from a deploy report, never from a
doc summary:

- building `list-kinds`, `find`, `build`; labor `enabled-counts`; zone
  `list-kinds`, `find`, `check-owner`, `place`: all deployed and hash-verified 48 of 48 in
  `handoffs/2026-09-21-deploy-building-batch.md`. `verified` strings extended only
  with what that report ran after the deploy over a real MCP client (building:
  list-kinds, find, dry-run build; enabled-counts: MASON 3, STONECUTTER 2, bad name
  null; zone: list-kinds and check-owner). Zone `find` and `place` say plainly that
  they were deployed but not called after the deploy. `build` and `place` keep
  "real path UNTESTED". The nobles commands were already `true` and correct; the
  `with_event` version is already noted untested. Nothing else changed.
- `labor set-labor`: was `STALE` ("the deployed file still has the OLD racy code").
  The 2026-09-21 deploy overwrote `df-overseer-labor.lua` with main's copy, hash-verified,
  so the note now says it is no longer stale; `verified` stays `unverified` (no call after).
- Beyond the brief, but the same kind of falsehood and each backed by a deploy
  report: workshop `find`/`build` (deployed 2026-09-17), trees `find`/`fell`, well
  `find`/`build` (2026-09-17, water-industry deploy), workjob `list`/`queue` (deployed
  and run live 2026-09-19), stocks `availability` (deployed and run live 2026-09-19)
  were all `false`. Flipped to `true`.

Two commands could not be promoted to `verified`: `stocks availability` and `workjob
queue` were both run live (BUCKET, both UNIT_HOLDER branches; one real blocks job),
but `dfmcp/tests/test_registry.py::test_stocks_availability_is_read_derivable_and_unverified`
and `dfmcp/tests/test_workjob_tool.py::test_workjob_queue_is_not_claimed_verified`
pin `verified` as `unverified` (stale tripwires written for the offline builds). I
left `verified: unverified` with a comment naming the evidence and the test. For the
orchestrator: update the two tests, then set `verified` on both.

Not flipped, and why (contradiction between reports, unresolved offline):
farm (4 commands, still `false`, `verified` says "never deployed"), diggable
`find-stair`/`dig-stair`, threat `scan`, breach `check`, and openarea (`STALE`).
The 2026-09-17 deploy reports say farm, threat, breach, diggable and openarea were
deployed and matched main by hash; the 2026-09-21 deploy report says 15
`df-overseer-*.lua` files under DFHack's script directory (breach, chokepoints,
connectivity, diff, diggable, farm, landmarks, openarea, orders, overview, stockpile,
stuckjobs, threat, ui, and one more it names) differ from main in content, cause and
direction unknown. So "the file is on the VM" is certain for them but "it is main's code"
is not, and I did not promote `false` to `true` or demote to `STALE`. One read-only
`sha256sum` sweep on the VM against `git -c core.autocrlf=false archive` settles it.

Header comment on `live_deployed` updated to stop saying "all 10 files".
Suites after: ambient 891 passed / 3 skipped; `dfmcp/tests` 461 passed / 3 skipped in the
worktree's ambient python (the 537 is the `.venv-dfmcp` figure, re-measured at the end).
