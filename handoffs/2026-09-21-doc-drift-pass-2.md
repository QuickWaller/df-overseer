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

UPDATE, later in this pass: farm (4 commands), diggable `find-stair`/`dig-stair`, threat
`scan` and breach `check` were then also flipped to `true`, because the file's presence on
VM 103 is proven by direct evidence (farm plot built and crop set for real 2026-09-17; the
stair designated for real 2026-09-18; threat and breach hash-equal to main 2026-09-17), and
`live_deployed` is defined as file presence. Their `verified` strings, and the tests pinning
threat and breach as unverified, are untouched. Only openarea (`STALE`, two commands) was
left alone. The rest of this paragraph is what I first wrote and is kept.

Not flipped at first, and why (contradiction between reports, unresolved offline):
farm (4 commands, still `false`, `verified` says "never deployed"), diggable
`find-stair`/`dig-stair`, threat `scan`, breach `check`, and openarea (`STALE`).
The 2026-09-17 deploy reports say farm, threat, breach, diggable and openarea were
deployed and matched main by hash; the 2026-09-21 deploy report says 15
`df-overseer-*.lua` files under DFHack's script directory (breach, chokepoints,
connectivity, diff, diggable, farm, landmarks, openarea, orders, overview, stockpile,
stuckjobs, threat, ui: the report says 15 and names these 14) differ from main in
content, cause and direction unknown. So "the file is on the VM" is certain for them but "it is main's code"
is not, and I did not promote `false` to `true` or demote to `STALE`. One read-only
`sha256sum` sweep on the VM against `git -c core.autocrlf=false archive` settles it.

Header comment on `live_deployed` updated to stop saying "all 10 files".
Suites after: ambient 891 passed / 3 skipped; `dfmcp/tests` 461 passed / 3 skipped in the
worktree's ambient python (the 537 is the `.venv-dfmcp` figure, re-measured at the end).

### 2. `agents/*` (done)

- `agents/{architect,overseer,consultant}/tools.yaml`: every "Not yet deployed" is gone (0
  left, grep-checked). Each note now says what the deploy reports show: stocks
  (2026-09-16, 2026-09-19, 2026-09-20), farm/workshop/zone/trees/well/orders
  (2026-09-17), workjob (2026-09-19), gotchas/building/labor enabled-counts and the
  generalised zone (2026-09-21). No allowlist entry was added, removed or moved (role
  lists parse to the same ids: architect 32 read, overseer 39 read and 18 write,
  consultant 14 read; the registry tests pass).
- Contradictions inside those notes, corrected against a primary source (a register row
  or a handoff report, cited in the note): `stocks.availability` was described as an
  offline build never run, four deductions, `verified_offline` always false (it is deployed,
  was run live, has six deductions, and `verified_offline` was flipped true 2026-09-19);
  `farm.build`/`farm.set-crop`, `well.build`, `workjob.queue` and `diggable.dig-stair` were
  described as untested live for the real path (register rows of 2026-09-17, 2026-09-19 and
  the well-unblock report show real runs); `orders.create`, `orders.list`, `workjob.*` said no
  Manager exists (unit 345 has held MANAGER since 2026-09-21, orders still do not run);
  `labor.set-labor` said "not yet redeployed, STALE" (the 2026-09-21 deploy redeployed the
  file); `zone.find`/`zone.place` described the old water-only tool.
- `agents/consultant/role.md` and `agents/CONFIDENCE-LEGEND.md`: the legend pointer told every
  role to "record the outcome with `gotchas.write`", but the consultant has no
  `gotchas.write` (refused live in the deploy report). The consultant's paragraph now says so
  and the legend has a one-line exception. The architect and overseer pointers read correctly and
  were left alone.
- `agents/ROSTER.yaml` (quartermaster `blocked_on`) and `agents/quartermaster/tools.yaml` header:
  the first still said manager work orders have no tool (`orders.*` and `workjob` exist), the
  second said role.md still had a stale line (role.md was fixed on 2026-09-17). Both corrected.
  ROSTER.yaml was not named in the brief; it sits under `agents/` and the fix is mechanical.

### 3. `docs/BUILDING-TOOL.md` (done)

Status block added at the top (built, deployed, verified live, never run for real,
join-shapes fix merged and not redeployed). Design text kept; additions are marked
"Resolved", "Answered", "As built" or "Update". The ConstructBlocks disagreement, the
BrewDrink/MakeTrapParts lookup errors (names absent from `df.job_type`), the labor source
(graph, joined in the MCP server, deployed), material filters (DFHack's own table, not the
game's), the optional `[W H]` and `LABOR...` arguments and the zone generalisation are ticked
off, each from its handoff report. Contracts C1, C2 and C3 each have an "as built" paragraph
(C1 from the Lua as read in the labor-join-shapes report, C2 the stricter status rule and
additive keys, C3 the single `tool_guidance` key). Ends with a "still open" list; the old
"Next step" is kept under a heading saying it predates the build.
Left open rather than claimed: whether a per-kind requirements file was built (no report
shows it), whether installation became a graph process, and the wrappers `workshop`/`well`/`farm`
(not rebuilt over the generic tool, per the Lua report's finding 5).

### 4. `docs/TRAPS.md` (done)

Nine items. Extended in place, not duplicated: (a) the existing `autosave N` rotation entry
(slot-mtime check for the wrong reason, with what to do), (b) the existing `dfhack_flags`
entry (the nine-line wrapper), (f) the existing "worktree starts from the last pushed
commit" entry (adds `origin/main` and the per-worktree `.claude/settings.json`). New, under
"Added 2026-09-22": (c) DFHack `ipairs` is 0-based, (d) `core.autocrlf` versus deployed
hashes (measured here: 518 CRs in the working copy of `docs/TRAPS.md`, 0 in the committed
blob), (e) refused shell commands, (g) the auto-mode `autoMode` settings, (h) the CIDR
suffix on `DF_VM_IP`, (i) the raws are not the whole reaction list. Each has the date, the
symptom, the cause and what to do, and a source. **One item is weaker than the brief
states it:** the brief says long quoted heredocs are rejected at parse time; the recorded
refusals are the classifier's (variable-built addresses and paths, piped file lists, `git`
forms it cannot bound to the worktree), and a quoted Python heredoc ran fine early in this
pass (later ones naming `git` were refused). The entry says so and treats the parse-time
rejection as intermittent, not a rule.
Hunger and thirst entry checked against `scripts/dfhack/df-overseer-sampler.lua`: the trap
says the timers live in `counters2` (and unconsciousness in `counters`), and the sampler
reads `u.counters2.thirst_timer`, `hunger_timer` and `sleepiness_timer`. **No contradiction.**

### 5. READMEs and design docs (done)

- `dfmcp/README.md`: native-tool paragraph now says `main()` passes the queue, doctrine,
  series and gotchas natives (it said only the queue's; checked against `server.py`); the
  gotchas section gains "live since 2026-09-21" with counts 34/57/14, the deploy needs
  (store `init`, `ReadWritePaths`, graph database and `production/`, the labor script, the
  `journal_mode=DELETE` reason the graph opens read-only), and the merged-not-deployed shapes
  fix with what the deployed join does meanwhile.
- `gotchas/README.md`: deployed 2026-09-21, the store is empty and created by hand, who holds which tool.
- `docs/PRODUCTION-MODEL.md`: status block (built in part, deployed for labors only, original
  status kept); the Q1 row no longer says labour per reaction is "free and exact" (304 of 366
  determined); the "159 reactions" claim and Pass 1 now say the 145 generated reactions are
  outside the raws and unchecked against the consumption rule. The `[SKILL]` claim was already
  corrected on 2026-09-21 (line 126) and needed nothing.
- `docs/AGENT-ARCHITECTURE.md`: one new "UPDATED 2026-09-22" block after the last dated one
  (counts, what acts on the fort, detectors, Manager appointed with no Office) and an inline
  update on section 14 item 7 ("work orders have no tool"). The dated blocks are kept.
- `docs/TIMESERIES.md`: status line (sampler live, `series.*` live).
- `docs/MEMORY-ARCHITECTURE.md`: `get_doctrine` is built and live as `doctrine.get`, consultant only.

### 6. Dead and duplicate files (listed, none deleted)

- `dfmcp/tests/gotchas_support.py`: the `_BUILDING_SCRIPT` stand-in (signatures `[W] [H]`) is
  skipped whenever the real manifest has `df-overseer-building.lua`, which it now does, so it
  is dead. Its `agents/*/tools.yaml` grant loop (`gotchas.get`, `gotchas.write`, `building.find`,
  `building.build`) is also a no-op now that the real allowlists hold those ids. The module
  docstring still says the orchestrator has not yet granted them. Safe to reduce to the
  native-tool registry plus a copy of the real files; two test modules import it.
- `dfmcp/labor_join.py`: the older `accepts` / `fort_owned` / `needs_container` requirements
  shape (around lines 196 to 240) is read only for the old workshop tool's stub shape; the real
  building tool never emits it. Kept on purpose by the shapes stream, so not dead to its tests, but
  dead for real results.
- `docs/BUILDING-TOOL.md`: the old "Next step" text (kept, now headed as history).
- `scripts/dfhack/df-overseer-workshop.lua` and the per-kind starter blueprints in `blueprints/`
  (`starter-still-3x3.csv`, `-kitchen-`, `-mason-`, `-mechanic-`, `-carpenter-`, `-well-`,
  `-farmplot-`): the generic tool needs none of them, but `workshop`, `well` and `farm` still use
  them by decision, so not obsolete yet. They become removable when those three are rebuilt over `building`.
- Out of tree: `df-overseer-embark.lua` on VM 103 has no counterpart in the repo (found 2026-09-17,
  still there per the 2026-09-19 reports), and 15 deployed `df-overseer-*.lua` differ from main
  (2026-09-21 report). Neither is verified from here.

## Judgement calls left for the orchestrator

1. **Flag semantics.** I read `live_deployed` by its header definition (the file is on VM 103), so
   dry-run-only commands (`building.build`, `zone.place`) are `true` and say in `verified` that the
   real path is untested. If you want it to mean "exercised for real", `building.build`,
   `zone.place`, `zone.find`, `trees.fell` and similar would go back to `false`.
2. **Two stale tripwire tests.** `dfmcp/tests/test_registry.py::test_stocks_availability_is_read_derivable_and_unverified`
   and `dfmcp/tests/test_workjob_tool.py::test_workjob_queue_is_not_claimed_verified` pin `verified` as
   `unverified`, though both tools were run live 2026-09-19. Update them, then set `verified` on both.
   Threat and breach are also pinned `unverified`; I left them, since the threat detector's live
   verification predates its knowledge-scope fix and breach has no recorded run.
3. **The 15-script drift** (2026-09-21 deploy report) against the 2026-09-17 reports that say the same
   files matched main. One read-only hash sweep on the VM would settle whether openarea's `STALE` and the
   "differs from main again" sentences I wrote into the threat and breach notes are right.
4. **Register rows to close** (I may not touch the register): the 2026-09-21 row that says the
   building tool "requires W and H ... open" (answered by the optional-group syntax, per the optional-args
   report), and any row that says the labor for Masons is MASON. Also the deploy report's finding that
   `handoffs/2026-09-21-graph-labor-for-jobs.md` and the deploy brief expect Masons to say STONECUTTER only;
   the deployed graph says STONECUTTER and STONE_CARVER.
5. **`docs/MEMORY-ARCHITECTURE.md` says nothing about the gotcha and confidence layer** (a new
   agent-written memory), and **`docs/AGENT-ARCHITECTURE.md` still has section 2 and 3 text written when only three
   roles and no tool surface existed.** I added an update block rather than rewriting either; a real design pass could fold them in.
6. **`agents/ROSTER.yaml`, the consultant's `role.md` and `CONFIDENCE-LEGEND.md`** were edited beyond the letter of
   deliverable 2 (the brief said tools.yaml and role.md; the roster line and the legend exception were the same drift).
7. **Consultant and `gotchas.write`.** The consultant cannot write gotchas (refused live). I made the docs say so; whether
   it should hold `gotchas.write` (the server report argues an advisor may, since it mutates no fort state) is your call.
8. **Manifest notes I left as written** because they describe behaviour, not deployment: for example the `workjob.queue` note
   still opens "Offline build, never run against a live DFHack process", now preceded by an UPDATE line saying that is stale.
9. `docs/BUILDING-TOOL.md` items I could not resolve from any report: whether a per-kind requirements file exists, and
   whether installation became a graph process.

## Test counts

Before: ambient **891 passed / 3 skipped**; `.venv-dfmcp` `dfmcp/tests` **537 passed**. After: ambient
**891 passed / 3 skipped**; `.venv-dfmcp` **537 passed**. Unchanged, as expected for a documentation and manifest-flag
change. The ambient run includes `tests/test_no_leaked_addresses.py`, which scans every tracked file.
