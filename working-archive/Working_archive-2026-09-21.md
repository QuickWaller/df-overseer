# Working archive, week of 2026-09-21

Sections moved out of `Working.md` under its archive-cadence rule. Moved wholesale,
never summarised or edited.

## Archived 2026-09-21 (evening): HANDOVER 2026-09-21, first half

The section as it stood when `Working.md` reached 522 lines: the 2026-09-20 fort
figures, the 2026-09-20 deploy note, and the START HERE list with the status
paragraphs that accumulated on 2026-09-21 (the building-tool streams, the
reaction finding, the nobles test, the zone and optional-args streams and the
deploy) and the long item 6 on DFHack coverage of the openclaw minimum bar. The
durable DFHack facts in that item are also in `memory/dfhack-environment.md`.

## HANDOVER 2026-09-21 (read this first after a /clear)

The 2026-09-19 handover, the two 2026-09-18 live-fort sections and the
2026-09-19 "Done today" list moved wholesale to
[`working-archive/Working_archive-2026-09-14.md`](working-archive/Working_archive-2026-09-14.md)
on 2026-09-21 (the file had reached 586 lines). Their fort figures were
overtaken (rollback to tick 213622, "cannot drink", "the fort drinks", the
first-death entry), but the rollback account, the walkability contradiction and
the well-route reasoning live only there.

**Authority.** Unchanged from 2026-09-19: the user granted full authority to
push, change the VM and act on the fort, and asked not to be asked per action
("this is all dev experiments not production"). Standing exception:
genuinely unrecoverable loss (the fort save, the VM itself) still stops and
reports. Two standing rules from the rollback are in `docs/TRAPS.md`: never
run an unbounded query against a live DFHack process, and quicksave
immediately before any live fort action.

### The fort, as last recorded (2026-09-20; not re-read this session)

Uniboslan, year 31, **paused at tick 103055**, 100 FPS when running (not 10).
**22 alive, 1 dead** (unit 454 starved at year 31 tick 15143, the first death).
The **well is built** (id 8), from blocks and a mechanism the fort made itself
through `df-overseer-workjob`; one drink was caught 1 tile from it. Most
drinking still comes from an **unlocated** source (73 thirst resets across all
23 citizens in 42 game days with no well and no brewed drink). A 4x4 plump
helmet farm was rebuilt and 429 wild plants were marked for gathering; the
last recorded hunger read (tick 29445) had **no citizen above 75,000**, but
the fort has run about 73,000 ticks since and hunger was not re-read in the
sources checked. Autosave (in-game `repeat`, every 7 game days) and the
sampler (one record per game day) run only while unpaused.

**Read hunger, thirst, deaths and stock together before calling it healthy**
(register 2026-09-19: a thirst-only all-clear cost a citizen).

### Deployed and live-verified (VM 103, 2026-09-20)

Batch deploy done (`handoffs/2026-09-19-deploy-batch.md`, including its
follow-up): **role tool lists architect 25, overseer 45, consultant 11.**
Six-deduction `stocks.availability` (a live `BOULDER` read returned 7 total, 3
in buildings, 4 available), `doctrine.get` (consultant only), six `series.*`
tools (overseer, consultant), `workjob` registrations, and the doctrine file.
The series tools were blocked by the server's `ProtectSystem=strict` (WAL
needs to write beside the database); one `ReadWritePaths=/var/lib/dfseries`
line fixed it, and `dfseries/` was redeployed and hash-checked twice. Live tool
ids are double-underscored (`series__resets`), not dotted. Revert backups:
`/opt/df/deploy-backup-2026-09-20-{wal,dfseries}/`. `dfseries-import.timer`
(60 s) is enabled and boot-persistent.

**Suite, measured 2026-09-21:** ambient `python -m pytest` **552 passed / 1
skipped**; `dfmcp/tests` in `.venv-dfmcp` **271 passed**.

### START HERE, in priority order

**Sequencing rule:** one stream at a time on VM 103 or the fort. Two offline
streams may run together only with strictly disjoint file ownership. A
worktree agent is cut from the last **pushed** commit: commit and push the
handoff before dispatching.

0. **Read the live fort, all vitals, quicksave first.** Bounded calls only.
   Nothing in the docs says what hunger looks like after 73,000 ticks.
1. **The supervised run**, `handoffs/2026-09-18-supervised-run-and-measure.md`,
   written and never run. Still open from it: the **`growdur` unit** (300 vs
   `grow_counter` in the tens of thousands, which blocks the harvest clock),
   one real job duration with the worker's skill level, whether claim state
   means anything over a running interval, and `item.age` against the pruned
   announcement buffer. The feed and sampler streams overlapped some of its
   ground (hunger's reset-to-zero is now verified), so re-read the handoff and
   trim it before dispatching.
2. **Give the fort a drink that does not depend on luck.** Brewing (`workjob`
   refuses the container reagent by design, so it needs a designed fix), an
   appoint-a-Manager tool (manager orders never become jobs without one),
   finding the unlocated water source, and fishing and hunting.
3. **The MCP apostrophe fix**: the server refuses `Stoneworker's Workshop`, so
   workjob's first run went through the raw CLI.
4. **z167 stone**: the rollback lost the stair, `well-and-harvest` designated
   another, and the well was finally built from free boulders. No source says
   whether the stair was dug. Check before anyone plans on z167.
5. **Make the tools generalisable** (user's rule, 2026-09-21, `CLAUDE.md`).
   Design first, no code yet: a generic `building.find/build` that takes the
   kind and reads footprint, labor and materials from the game's raws,
   generates its own blueprint, and keeps per-kind policy as data; then audit
   the tools that look single-instance (`workshop` has five hard-coded kinds,
   `zone` water source only, `orders.create` a fixed job vocabulary, `workjob`
   blocks and mechanisms). Rooms and furniture are expected to fall out of the
   same base. **Design note written 2026-09-21: `docs/BUILDING-TOOL.md`; four
   handoffs written for the user's review, none dispatched:
   `handoffs/2026-09-21-building-tool-lua.md` (live, read-only),
   `-building-tool-server.md`, `-graph-labor-for-jobs.md` (waits on the Lua
   stream's dump) and `-building-requirements-research.md`; it now also records the confidence-level
   requirement (each tool and kind carries a level that tells the agent how
   carefully to use it; the user chose this over a verification sweep).** It corrects an assumption: the raws do not
   carry standard buildings, but DFHack's quickfort table (about 87 entries,
   workshops, furnaces, furniture, well, farm plot; rooms in `zone.lua`) does,
   with footprints. Operating labor is only partly derivable. This is also the user's stated minimum for openclaw:
   it must be able to build workshops, rooms and furniture, assess dwarves,
   grow food and build wells before agent infrastructure is worth building.

   **Status, later on 2026-09-21: three of the four streams ran and are merged
   locally, all green (698 passed / 3 skipped ambient, 429 / 1 in
   `.venv-dfmcp`), none deployed.** Lua side: `df-overseer-building.lua`, 175
   kinds from quickfort's own table (reached through upvalues), about 40 dry
   runs verified live and read-only with the fort unchanged at tick 103055;
   `labor enabled-counts`; the dump is at
   `<scratchpad>/building-dump/` (out of tree). Server side: `gotchas.get` and
   `gotchas.write`, static confidence levels, `tool_guidance` enrichment, the
   labor join stubbed to C2. Research: `research/2026-09-21-building-requirements.md`
   (32 kinds; DFHack's material filters are its own tables, not the game's;
   the Mason's Workshop labor is STONECUTTER/STONE_CARVER, so the `mason`
   entry in `df-overseer-workshop.lua` is wrong). Allowlists granted (architect
   30, overseer 51, consultant 12 on the merged tree). **Graph-labor stream merged**
   (`production/labors.py`, strict `known` rule: 2 known, 18 partial, 13 unknown of 33 kinds; the extractor no longer writes a skill into `labor`) and the reaction-extraction stream merged (786 passed / 2 skipped ambient, 430 in the venv). **It found the 145 unread reactions are generated at world creation and exist only in the world save, so coverage did not move; reading them needs a live read, folded into the deploy handoff as step 2b.** **Nobles test done in the main session (2026-09-21):** `df-overseer-nobles.lua` deployed; unit 345 is now MANAGER (both-sides verified, unappoint round trip verified); a 3,900-tick supervised unpause showed no order started, and the fort has no Office zone. **Fort: paused, year 31, tick 106974, 22 alive, MANAGER held.** Next: an Office zone assigned to the manager (needs a zone tool that places one; handoff `handoffs/2026-09-21-zone-tool-generalise.md`), then watch again. **The zone stream is merged** (18 zone kinds, optional owner; a live Office dry run validated; the real placement never run; what makes an Office meet the Manager's room value is unknown; role tools now architect 34, overseer 57, consultant 14; the deployed zone script is the OLD one and must be deployed together with the new manifest). **A `workjob` generalisation handoff is written** (`handoffs/2026-09-21-workjob-generalise.md`, not dispatched). **The optional-args stream is merged**: the building tool now takes just a kind (footprint from the game) and `enabled-counts` takes several labors; ambient 818 passed / 2 skipped, venv 475; role tools on the merged tree are architect 32, overseer 55, consultant 14; nothing is deployed. **Open:** the manifest requires W and H
   and one labor per `enabled-counts` call because `dfmcp/tools.py` cannot
   express optional or repeated arguments (the user has not ruled: extend
   `tools.py`, or accept); nothing has really built a never-built kind; deploy
   needs a gotcha-store directory, a `ReadWritePaths` line and the graph DB
   (see the server report in `handoffs/2026-09-21-building-tool-server.md`).
   Next: nobles test (VM 103 is free), deploy with the user's go-ahead, then
   the first supervised real build.

**DEPLOYED 2026-09-21 (supersedes every "not deployed" above):** the building, gotchas, labor-graph, nobles and zone tools are live on VM 103, hash-verified, role tools architect 34, overseer 57, consultant 14, graph 5 known / 23 partial / 5 unknown of 33 kinds, fort untouched at tick 106974 (MANAGER held by unit 345, no Office). Left: (a) the labor-join shapes fix (dispatched; then a dfmcp-only redeploy), (b) an Office placed and assigned to the manager for real, then a supervised unpause to see whether the queued orders run (the zone tool's real placement has never run; what makes an Office count is unknown), (c) the first real build of a never-built kind, (d) the generalised `workjob` (handoff written, not dispatched), (e) the auto vs manual harness: an `autoMode` block is now in the user's settings, effect partly evidenced.

6. **Design gaps against the openclaw minimum bar** (2026-09-21, none
   designed): **assessing dwarves** (what it feeds into is unanswered);
   **rooms**, which need the same wrapper-over-a-generic-tool system as
   buildings (open question, zone kinds live in quickfort's `zone.lua`);
   **furniture in rooms and assigning a bed or room to a dwarf**; **growing
   food end to end** (unknown; `growdur` unsettled, brewing container
   refused by `workjob`); **stockpiles**, which need more work than the
   read-only `stockpile list/links` (user, 2026-09-21). Also not yet
   designed: appointing a Manager, confirming a build completed, and who
   controls the game clock. **The classification is done: `research/2026-09-21-dfhack-tool-classification.yaml`
   and `.md`** (60 will, 46 grey, 337 wont; read/write, likely roles, categories,
   overlap with ours, and a coverage-against-the-minimum-bar table). **Corrected 2026-09-21 (the first version of this claim was too strong,
   from a classification that read summaries only).** No named tool and no documented API
   function for **appointing a Manager or nobles**, **but the mechanism is
   confirmed (checked 2026-09-21):** DFHack's own `make-monarch.lua` does it by
   setting the position assignment's `histfig` and inserting a
   `histfig_entity_link_positionst` into the new holder's `entity_links`, and
   `internal/emigration/unit-link-utils.lua` shows the removal side. A bounded
   read of the paused fort shows the fortress entity (id 36) has 12 assignments
   including `MANAGER` (assignment id 6), `BOOKKEEPER`, `BROKER`, `MAYOR`,
   `CAPTAIN_OF_THE_GUARD`, `SHERIFF`, `MILITIA_COMMANDER` and
   `CHIEF_MEDICAL_DWARF`, **all vacant except the expedition leader.** So the
   gap is a tool we build (a generic `nobles` read and `appoint`/`unappoint`
   taking a position code), **untested**: the monarch script writes no history
   event, the emigration helper does, and whether a manager then validates
   orders is unknown until tried, with a quicksave first. **Handoff written for review, not dispatched:**
   `handoffs/2026-09-21-nobles-appoint.md`.
   **Room and furniture assignment is partly covered:** `Buildings::setOwner` and
   `dfhack.buildings.getOwner` exist in the API, and quickfort `#zone` blueprints
   can assign a zone to a noble role through `preserve-rooms`; no ready tool
   for "give this bed to that dwarf". **Confirming completion** is a tool we
   build over `eventful` and direct reads, not a missing capability. **Assessment:**
   `allneeds` reads needs; skills, stress and injuries are unit fields with no
   ready tool. **Unpause** is one write to `pause_state`, which we already do.
   **Defence:** the `burrow` plugin is available, `Military::removeFromSquad`
   exists, no squad-creation tool found. **A first-pass inventory of every DFHack tool now exists:
   `docs/DFHACK-INVENTORY.md`** (443 documented tools, generated by
   `scripts/dfhack_inventory.py` from the install's own docs; names, tags and
   summaries only, nothing run). Candidate existing tools for these gaps, from
   summaries alone and unverified: `stockpiles`, `logistics`, `gui/quantum`
   (stockpiles); `buildingplan` (materials); `autofarm`, `seedwatch`,
   `autochop`, `getplants`, `autofish` (food and wood); `allneeds`,
   `gui/unit-info-viewer` (dwarf assessment). The
   user's idea: give the consultant or another role an **investigatory**
   function, read-only commands plus inspecting DFHack's source and docs
   (both are on VM 103). Not designed; the safety constraint is that raw
   `lua` is not read-only and an unbounded query once wedged the pipe.
   **Dwarf Therapist idea (user, 2026-09-21):** maintained, supports v50+, but a
   human-facing GUI with no API, so agents cannot call it; useful as an
   observation and cross-check tool for the user and as prior art for how to
   score dwarves (its role ratings). It shows exact numeric attributes, which
   vanilla does not (unverified), so our assessment tool should return what
   the vanilla UI shows. **Settled 2026-09-21: no armok capabilities** (`CLAUDE.md`, register): the
   ban is on powers a player lacks and on hidden information, and the tag is
   only a pointer, so reading what a player can see is fine. **A Sonnet review of all 99 is in
   `research/2026-09-21-armok-review.md`** (88 keep-banned, 7 candidate
   exceptions, 4 needing a ruling; documentation read only); the four
   rulings (`caravan`, `showmood`, `cleaners`, `clear-smoke`) are being
   discussed one at a time.

## Archived 2026-09-21 (evening): superseded bullets from the CLAUDE.md status block

Moved wholesale from `CLAUDE.md`'s status block when it was compacted. Every entry was
already marked superseded or updated by a later one; the register holds the substance.

> - **The well is built (2026-09-19)**, from blocks and a mechanism the fort
>   made itself through `df-overseer-workjob` (one-off workshop jobs, the way
>   a player clicks, since manager orders never run without a Manager). A
>   dwarf was caught drinking 1 tile from it; most drinking still comes from
>   an unlocated source. 22 alive, fort paused at year 31, tick 103055.
> - **First death, 2026-09-19: the fort starved before it was fed.** Unit
>   454 starved at year 31 tick 15143. All 23 citizens had been hungry and 11
>   past 75,000 while this project's reporting counted only drinks; the user's
>   screen caught it. A feeding stream then marked 429 edible wild plants and
>   rebuilt a farm, and **no citizen is above 75,000 hunger now**. 22 alive,
>   fort paused at year 31, tick 29445.
> - **The fort drinks, measured 2026-09-19.** The sampler's history records
>   **73 thirst resets across all 23 citizens in 42 game days**, with no well
>   and no brewed drink, so they drink from a water source not yet located.
>   The bullet below stands as a record of the known pond (still unreachable)
>   but is no longer the fort's state. Fort paused at year 31, tick 4257.
> - **Superseded 2026-09-19, kept for the record: the fort cannot drink.** This corrects the entry below it, written
>   2026-09-17, which said Uniboslan drinks. Measured 2026-09-19 across two
>   exact reads: delta tick 6,303 equalled delta thirst 6,303 across all 15
>   citizens, so `thirst_timer` increments 1 per tick and **nobody drank at
>   all**. The `WaterSource` zone is active but unreachable, because **zero
>   water tiles have any walkable neighbour**, and digging to the water was
>   disproven by digging: a channel at z169 flooded and left z168 walkable at
>   0. The fort needs a **well**, blocked on BLOCKS 0 and TRAPPARTS 0 against
>   3 logs and 0 boulders. → `handoffs/2026-09-19-well-unblock.md`.
> - **Updated 2026-09-21: the production graph is no longer empty**: the
>   real-corpus extraction and the snapshot assembler both merged on
>   2026-09-19 (the suite is now **552 passed / 1 skipped**). Pointing it at the
>   live fort is the supervised run above. The entry below is kept as written.
> - **The production model is built, green and empty.** `production/` is
>   2,182 lines across five modules at **364 passed / 1 skipped**, covering
>   steps 1 to 5 of the spec's build order. Two gaps, both found by audit
>   rather than by failure: the extractor has **never seen real data** (6
>   hand-assembled fixture reactions, not the real 159), and **nobody wrote
>   the caller** that assembles a snapshot for `blocker.py` and `cover.py`,
>   so the graph has never been pointed at this fort. Two streams are on
>   both. → `handoffs/2026-09-19-real-corpus-extraction.md`,
>   `handoffs/2026-09-19-snapshot-assembler.md`.
> - **The production and logistics model is designed in full, nothing
>   built.** `docs/PRODUCTION-MODEL.md` is the build spec: a directed
>   hypergraph in plain SQLite, corrected by two feasibility audits against
>   this install's own raws and live state
>   (`research/2026-09-18-schema-extraction-static.md`,
>   `research/2026-09-18-schema-extraction-live.md`). Consumption has
>   **four** outcomes, not three; 42% of reaction product lines need a
>   material-side join before a concrete item id exists; no job-duration
>   figure exists anywhere on this install, in DFHack's docs, or on the
>   wiki, confirmed a third independent time. → `ROADMAP.md` Now bucket.
> - **Superseded 2026-09-19, kept for the record: "the fort drinks and grows food for the first time."** Uniboslan is
>   paused at tick 227160 (sim at **10 FPS**, deliberate) with 15 citizens, no
>   deaths. Its ponds are sunken basins of 6-7/7 water one level below the
>   surface, which is why no dwarf drank unaided; a `WaterSource` zone placed
>   on the water at z168, plus one supervised unpause, got founders down to
>   the water and self-serving (register 2026-09-17). A first farm plot is
>   built at z168 with plump helmet set for all four seasons, but **nothing is
>   planted yet**. **Still not
>   built:** the still (designated; the fort owns only 3 logs, no worker took
>   the job yet either way). Fort-owned food is 17 units, drink still 0, 60
>   seeds (35 plump helmet). → `Working.md` HANDOVER 2026-09-19 (the 2026-09-17 one is archived).
>
