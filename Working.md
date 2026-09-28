# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.

## Current state, 2026-09-28 (read this first)

**Ore-vein recovery tool built, wrong twice, now live-verified correct** (`decisions/DECISIONS.md` 2026-09-24, `handoffs/2026-09-28-ore-vein-recovery-and-construction-tool.md`, `research/2026-09-28-ore-detection.md`). New `surface.vein-material ZONE_ID` (read) and `construction.mine-vein`/`construction.build` (mutate, overseer-only) built to recover the Manager's Office's 5 hematite ring tiles smoothed over instead of mined 2026-09-24. **The offline-built classification was wrong, and wrong again, in exactly the way today's earlier `Working.md` entry warned about (lupa fake worlds not matching the real API):** first cut used `economic_uses` (not even a valid field path; answers "which reactions use this," not ore-worthiness); the orchestrator's own "just use MINERAL vs STONE" fallback was **researched and rejected on the merits** (live-tested: microcline and kaolinite are both MINERAL-class and both non-ore, so that fallback flags every vein tile). Ground truth from the raw text file (`inorganic_stone_mineral.txt`, `[METAL_ORE:IRON:100]`) plus DFHack's own `isOre()`/`isGem()` (the same calls its `prospector` plugin uses) is correct. Fixing it live took **two more rounds**: `tile_bitmask:get(x,y)` doesn't exist (real shape: `tile_bitmask.bits[y%16]`, bit `x%16` within that row, row/bit orientation confirmed by testing both ways live); then `df.global.world.raws.inorganics[idx]` direct indexing also errors live (real path: `dfhack.matinfo.decode(0, idx).inorganic`). **Final live check on zone 13, all 5 known tiles: `HEMATITE`, `ore_or_gem`, `economic: true`; all 11 others `not_mineral`; zero unknowns, zero read failures.** Offline lupa stub corrected to match the real shapes (was testing a self-consistent fiction before). 1930 tests pass.

**The mine-vein/build mutation itself is now done, live, on zone 13 (the Manager's Office).** `construction.mine-vein 13` designated the 3 hematite ring tiles not already mined by the dwarf the user had spotted digging; a supervised unpause window let the miner finish them; `construction.build 13 wall` then walled all 5 (default material WOOD, correctly non-economic). Dry-run first each time, real second. Zone 13's ring reads `open_tiles_found: 5`, all 5 buildings designated, no refusals on the mined tiles. **All 5 wall buildings (18-22) are still stage 0 (designated, no material consumed) — nothing is actually built yet.**

**The user asked, correctly: does the mined ore need to be hauled to a stockpile before its tile gets walled over?** Checked live: zero hematite items exist anywhere near the office (confirmed two independent ways — a material-only scan of every item on the map, and the `df-overseer-stocks availability BOULDER` tool's own count, both agreeing on the fort's 12-boulder total with none from this dig). Not a bug and not something already hauled off or built into something: the DF wiki confirms **ore vein tiles have only a 33% chance per tile of dropping ore when mined** (100% for gem clusters, 25% for ordinary stone) — with 4 tiles mined, roughly a 1-in-5 chance of zero ore is unremarkable. `economic_stone[182]` (hematite's fort-wide stone-collection toggle) reads `1`/enabled, ruling that out as a cause. Also checked and ruled out: DF has no separate "ore" item type (`df.item_type` has `BOULDER` and `ROUGH` for cut gems only; "ore" is just the display name for a boulder made of an ore material), so the scans were not missing it on a naming technicality. **The generalized requirement stands regardless of this particular case coming up empty**: a wall/build step must never proceed while an un-hauled ore item sits on its target tile; haul-to-stockpile belongs as its own step between mine and build, not assumed away. Folded into the job-dependency-graph design below as a candidate guard.

**Along the way: a genuine stuck-viewscreen popup (`FORT_POSITION_SUCCESSION`, "Rith Auburngate has assumed the position of expedition leader") self-paused the first window at t=61s with no tripwire latch and did not clear on one resume-and-verify — the exact 2026-09-16 pattern.** `df-overseer-ui click "Okay"` reported "still present after 3 attempts (unverified)" against it (its buffer-scan does not see this dialog's text at all, confirmed by a full `dump`), so its own verification step is a false negative here — **but the click itself did land**: resuming afterward advanced the tick fine. Do not trust this tool's self-reported failure for announcement-style popups without independently checking via `clock resume` + tick comparison; its "verified" claim only means "the same text vanished from the scanned buffer," which never happens for a popup the buffer-scan can't see in the first place. A second, full 600s window then ran clean end to end: no self-pause, no tripwire, 22 alive throughout, 0 warnings, hunger/thirst fine.

**Deploy of the two 2026-09-28 fixes hit a real live bug, found and fixed before touching the fort.** All 9 files (dfqueue's 6, dfmcp/queue_tools.py, TOOLS.yaml, the building tool) deployed and sha256-verified against committed bytes, `dfmcp-server` restarted clean. A live sanity check then crashed: `kind_previously_built`'s `for i = 1, #buildings do buildings[i] end` treated `df.global.world.buildings.all` (a real DFHack vector, 0-indexed) as a 1-indexed Lua table, reading one tile out of bounds on the last iteration — "index out of bounds" on every real call. **The offline `lupa`-based test suite (14 tests, all passing) never caught it**, because its fake DFHack world evidently models vectors as ordinary 1-indexed Lua tables, silently matching the buggy loop instead of exposing the real API's indexing. Fixed to the same `ipairs(buildings)` idiom every other file in this codebase already uses; redeployed via `git -c core.autocrlf=false archive` (the first deploy of this file went out via a raw scp of the working tree, which is CRLF on this workstation — caught by re-checking against committed bytes before it caused a real problem, redone correctly). Live-verified after: `kind_previously_built: true` and a correct non-economic material breakdown (`chosen_material: "WOOD"`) on a real dry-run call, fort untouched throughout (paused, tick 198236). 1910 ambient (3 skipped) tests still pass. **Open follow-up: the offline lupa fake world's vector indexing should be audited/fixed so it actually matches DFHack's real 0-indexed vectors, or this class of bug will keep passing offline and only surface live.**

**Supervised unpause, 2026-09-28 (10 FPS, 600s wall, tick 192334 to 198236, tripwire armed on defaults, restore trap):** both `MakeBarrel` jobs progressed and at least one completed — `workjob.list-jobs Still` now reads `free_candidate_count: 1` for the brew reaction's container reagent (was 0), so **brewing is now genuinely unblocked**; drink stock is still 0 (nobody has queued a brew job yet, that needs the next real cycle or an orchestrator call). The bedroom-cell dig, tree felling and farm planting all progressed (`Dig`, `FellTree`, `SmoothWall`, `PlantSeeds`, `HarvestPlants` jobs all seen); 3 `Dig` jobs remain stuck with no worker assigned (miners tied up elsewhere), no stuck `FellTree` any more. All 22 alive, 0 warnings, worst hunger/thirst "fine" throughout. Re-paused, independently re-read.

Uniboslan is paused, 22 alive and 1 dead, `dfmcp-server` active. Role tool lists (read plus write): **overseer 79, architect 49, consultant 28, quartermaster 24, conductor 15**. The office is built, furnished, owned by the Manager and accepted by the game; the ghost is laid to rest; Manager work orders still never dispatch (user's ruling: set aside). The Consultant now answers from the full offline wiki mirror, live-verified. The conductor was redeployed live to VM 106 with its `game_tick` fix confirmed, and five real (non-dry-run) conductor cycles have now run against the live fort (2026-09-25 through 2026-09-28): the Overseer has rejected stale/duplicate proposals and accepted and executed real work (a down-stair dig, the first bedroom cell's dig shell, a Carpenter's Workshop siting), with several tool and process gaps found and fixed along the way (the workjob container-reagent gap, positional-argument ergonomics, the Overseer's timeout, cursor and re-wake bugs, a proposal-level duplicate check). The Well and tripwire are live-verified end to end: dwarves drink at the Well despite 0 drink stock, and the tripwire pauses a running fort within one tick and refuses resume until cleared. A 2026-09-28 drift audit found and fixed six VM-stale doc/role files (the Consultant's `sites.yaml` had been running pre-wiki-mirror guidance for six days) and two real `MakeBarrel` jobs were queued as the actual fix for the drink-supply block. Full narrative: [`working-archive/Working_archive-2026-09-28.md`](working-archive/Working_archive-2026-09-28.md), `evals/live/2026-09-25-first-real-conductor-cycle/README.md`, `decisions/DECISIONS.md` 2026-09-25 and 2026-09-28 rows.

**Still open:**
- The districting design session (gated on the user): prior-art research is complete (df-ai, `research/2026-09-24-df-ai-fort-planner.md`; Systematic Layout Planning/adjacency/zoning, `research/2026-09-25-district-layout-prior-art.md`), proposal on the table is a kind-by-kind closeness table with per-cell reasons plus per-district contained landmarks and tool-computed relation facts. Three agenda inputs from the user not yet decided: blueprint connector properties (entrances/exits, rotation, modularity, seams); observability (every inter-agent message with sender/recipient/type/rationale, joinable to its tool calls); and (2026-09-28) **modeling a room's own build order as a dependency graph, not a fixed stage list** — the same relational thinking as room-to-room adjacency, one level down. Motivated live: the 2026-09-24 ore-vein-smoothed-into-a-wall gap (`decisions/DECISIONS.md` 2026-09-24, fix dispatched 2026-09-28 in `handoffs/2026-09-28-ore-vein-recovery-and-construction-tool.md`) is a case of a fixed ordered stage list ("smooth" comes after "mine ore") having no way to structurally gate one step on another actually completing, versus a graph's explicit prerequisite edges. **Node-completion state should be tracked explicitly, not derived live** (user's call, 2026-09-28, overriding the orchestrator's first instinct): once a vein is mined the tile is just open floor, so nothing live-readable proves step 2 ran; some node states are intent, not a physical fact (furniture deliberately deferred vs abandoned mid-work looks identical on a tile scan). Reuse the queue's own `executed-000X` record shape rather than inventing a new one; use live reads to reconcile/catch drift against the tracked record, not as the primary source of truth. **Widened by the user 2026-09-28, live**: not just room-build stages, every small job should be trackable as a module of a larger job, with explicit dependency edges (a wall-build job depending on a mine-vein job completing, not just a room's fixed stage list). Concrete case that motivated the widening: after zone 13's mine-vein/build fix, a wider live scan (a one-off `dfhack-run lua` sweep, not a tool) found the hematite vein continues well past the office's single ring — 26 still-unmined ore wall tiles nearby, 5 already exposed — and one of the 5 wall buildings just designated (building 22, at 102,104) sits directly next to unmined ore at (101,104). Its build job (id 2705) was suspended by hand (`job.flags.suspend = true`) as a stopgap; there is no code path today that would have caught or done this automatically, because nothing records "this wall job depends on that patch of vein being fully cleared first." The site-ranking redesign (`ranked_rects`) folds into this same session.
  - **A full design for this landed 2026-09-28**: `research/2026-09-28-job-dependency-graph.md` (commit `b0d3072`, Opus researcher, `handoffs/2026-09-28-job-dependency-graph-design.md`), reviewed and not yet acted on. Recommendation: proposal -> **project** (new record, the missing `plan` record `docs/AGENT-ARCHITECTURE.md` §9 already flags) -> **step** (one tool call over a target set) -> DF jobs as evidence only, never graph nodes. Three edge kinds: `requires` (hard, tracked explicitly per the user's ruling), **guards** (world-state predicates modelled on DFHack's own `suspendmanager`, e.g. `keeps_access`: would this construction cut off reachable, unmined economic ore), `prefer_after` (soft). Corrects two things: a mined vein tile is *not* indistinguishable from floor (the floor keeps the vein material, confirmed live — what's actually unrecoverable is who/when/why); and a wider scan must never count hidden tiles (armok rule) — the "26 unmined tiles" figure included hidden ones and should not have. **Recommended build order, cheapest first**: (1) `keeps_access` as a plain tool-layer refusal in `construction.build`/`blueprint apply` — alone would have stopped building 22, and also catches a related live bug the design found: `construction.build` currently treats every open ring tile as buildable, which would wall a room's own doorway; (2) project/step records in `dfqueue`; (3) a reconciler in the conductor; (4) dependency steps in blueprint templates. **A haul-before-seal guard (2026-09-28, from the boulder-yield check above) is a second concrete candidate for the same guard vocabulary.** Two things flagged as live risks, not yet acted on: enabling `suspendmanager` (confirmed off) or running `unsuspend` would silently release job 2705's hand-hold; and whether a dwarf can mine a wall from a diagonal neighbour is unverified, which decides whether building 21 (not just 22) is also exposed.
- The wiki refresh timers (S8) and S7 (changes tool, doctrine flags) are not yet dispatched; the mirror only refreshes by hand and the reader reports `stale` after 24 hours. Small S1 remainder: `refresh.py` still uses raw SQL for redirects and doesn't call `cancel_held`, and `Store.get_archived_revision` is not added.
- The first bedroom cell's dig shell is designated (site-3, 12 tiles) but nothing else is installed yet: furniture, zone, owner assignment.
- Two small fixes from 2026-09-28 are done, merged, **deployed to VM 103 and live-verified** (see above): `building.build`/`find` defaulting to non-economic material, and the queue's near-duplicate-proposal flag on `queue.propose`. **`building.build`'s "non-economic" check is now known to use the same wrong field the ore-detection research disproved for `surface.vein-material`**: `economic_uses` is a real, readable field (confirmed live), but it means "reactions registered against this material," not ore-worthiness (`research/2026-09-28-ore-detection.md`) — the same class of mistake, not yet fixed here. Follow-up owed: swap `building.build`/`find`'s material filter to `isOre()`/`isGem()` the same way `surface.vein-material` was fixed.
- **A wider live scan around zone 13 (2026-09-28, ad hoc, not yet a tool) found the hematite vein continues well past the office's single ring**: 26 still-unmined ore wall tiles nearby (5 already exposed/visible), well beyond the 5 tiles the mine-vein/build fix handled. One of the 5 new wall buildings (id 22, at 102,104) sits directly next to unmined ore at (101,104); its build job (id 2705) was suspended by hand as a stopgap so it doesn't seal that ore off, needs reactivating once that patch is mined. The other unmined tiles further out are untouched, no plan yet for whether/how to recover them — likely wants a proper `surface.vein-material`-style scan over a wider radius rather than another one-off script, and ties into the job-dependency-graph idea above (a wall job should refuse/warn if it borders unmined ore, not require a human to notice via a manual scan).
- **A fort can self-pause on a vanilla event outside the announcement-level/tripwire system** (2026-09-28, `FORT_POSITION_SUCCESSION`/noble succession the concrete case; `docs/TRAPS.md` new section, `handoffs/2026-09-28-noble-succession-popup-research.md`). Confirmed a clean `pause_state` flip this once (resume advanced the tick, re-paused cleanly) — but that test ran after the user had already clicked through whatever the game showed on VNC, so it's unproven whether a fresh, unattended occurrence needs a human click, same shape as the 2026-09-16 stuck-viewscreen case. `scripts/supervised-unpause.sh` (new, replaces the ad-hoc per-session heredoc this was rewritten from five times) handles both safely: one resume-and-verify-tick attempt on an untripwired pause, then stop and ask a human if the tick doesn't move. **Must never move into `conductor.service`** — the unattended loop has no VNC fallback.
- The tiling generator for `bedroom-cell-v1`; the burrow confinement ruling; leaked key rotation (below).
- A real supervised conductor run beyond the five ad-hoc cycles above, and the districting session, both wait on the user.

**Archived this pass:** most of the "Current state, 2026-09-25" section (the wiki mirror switch-over and reader deploy, the districting prior-art completing, the full conductor redeploy/fix-cycle/first-real-cycle narrative through the 2026-09-28 fifth cycle, the drift audit, and the well/tripwire live-verification) moved wholesale to [`working-archive/Working_archive-2026-09-28.md`](working-archive/Working_archive-2026-09-28.md); it reported itself finished or superseded throughout. Everything still open is carried into the tight list above.

## Open: rotate leaked keys (2026-09-17)

A session ran `cat .env | grep -v SECRET` while looking up the VM 103 SSH
user, breaking the "read secrets by the key you need" rule — it printed
`ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, `CLOUDFLARE_TUNNEL_TOKEN`, and
`CLOUDFLARE_TUNNEL_TOKEN_ADMIN` into the session transcript in full. User's
call: rotate later, not urgent, but don't lose the item. → decisions/DECISIONS.md
2026-09-17.

## Archived

- Sections through 2026-09-10 (fifth handover) — provisioning build,
  perception eval, fort ledger, systemd units, title-screen bootstrap,
  live-viewing/relay/tunnel, the tileset investigation, Site Finder
  resolution, the embark-flow saga through both forts founded, and the
  seed-landmark bootstrap — all moved wholesale to
  [`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md)
  as each was superseded or reported itself finished.
- 2026-09-09: the 2026-09-08 (evening) handover moved wholesale to the
  same archive file.
- 2026-09-09 (end of session): this session's full handover (title-screen
  bootstrap resolution, the entire live-viewing/relay/tunnel build, the
  tileset investigation, and the Site Finder "Begin" resolution) moved
  wholesale to the same archive file — exceeded the ~400-line threshold,
  not superseded. The handover above is the tight current-state summary;
  the archive has the full detail.
- 2026-09-10: the 2026-09-09 (end of session) handover moved wholesale to
  the same archive file, superseded by this session's own handover above
  (Cloudflare Tunnel completion, the graphics-completeness fix, and the
  live embark-flow attempt).
- 2026-09-10 (second handover today): that session's own handover moved
  wholesale to the same archive file, superseded by this session's handover
  above (the click-registration mystery resolved, the real embark mechanism
  found, and the new "Confirm" crash).
- 2026-09-10 (third handover today): that session's own handover moved
  wholesale to the same archive file, superseded by this session's handover
  above — **the first fort was founded**, and the "Confirm" crash resolved
  empirically via gdb.
- 2026-09-10 (fourth handover today): that session's own handover moved
  wholesale to the same archive file, superseded by this session's handover
  above — the `find_mm_*`/`warn_mm_*` coordinate-frame bug found, and
  `xdotool` real-input fix for headless map/hover interaction discovered
  and validated.
- 2026-09-10 (fifth handover today): that session's own handover moved
  wholesale to the same archive file, superseded by the handover at the top
  of this file — the text-only sweep built and run, a Windows-specific SSH
  command-line truncation bug found and fixed in `provision_vm.ssh_guest`/
  `install_df.remote()`, and a strong second-site candidate found
  (`sx=128 sy=84 ex=131 ey=87`), left uncommitted for the user's call.
- 2026-09-10 (end of session): that handover's full continuation (the
  candidate embarked, Artobcatten's save lost as a result, the
  perception-layer branch split, the quorum-blocked snapshot worked
  around with a file backup, and Uniboslan's first room and stockpile dug)
  moved wholesale to the same archive file — exceeded the ~400-line
  threshold, not superseded by new work. The handover at the top of this
  file is the compacted current-state summary; the embark-screen-specific
  durable traps it used to carry were dropped rather than re-copied
  forward, since they're already the permanent living content of
  `docs/DF-UI-AUTOMATION.md`, not duplicated here.
- 2026-09-11: the 2026-09-11 VM-outage/quorum-incident writeup plus the
  entire 2026-09-10 end-of-session handover (VNC control channel, labor
  management/`autolabor`, the kea-combat finding, the quicksave root-cause,
  the perception-branch audit, both autonomous-play experiments, and the
  `find_diggable_area`/reachability corrections) moved wholesale to the
  same archive file — exceeded the ~400-line threshold by a wide margin,
  not superseded by new work. The handover at the top of this file is the
  compacted current-state summary, written deliberately thorough for a
  `/clear`; the archive has the full decision-by-decision detail.
- 2026-09-11 (documentation consistency pass): three fully-self-reporting
  ### threads moved wholesale to the same archive file: the compliance
  eval harness build (done for the session), mechanical prediction grading
  (built, selftested), and the full find_diggable_area/dig_diggable_area
  saga (built, live-verified, live-tested, the quickfort `-c` top-left-vs-
  center bug found and fixed, re-confirmed working end to end). None were
  gated on a human; item 10 in "What actually got built today" above now
  carries the compacted find_diggable_area/dig summary, and
  `decisions/DECISIONS.md`'s 2026-09-11 rows carry the full trail for all
  three.
- 2026-09-12: the entire 2026-09-11 end-of-session handover (the
  branch-merge question, the "what got built" list through item 12, and
  the peer-sessions/next-steps section) moved wholesale to the same
  archive file — the branch-merge question it spent most of its length on
  is resolved (merged, above), so it's fully superseded, not just over
  the line-count threshold. The handover at the top of this file is the
  new compacted current state.
- 2026-09-12 (session end, ahead of a `/clear`): this session's own content
  (the tool manifest build, both coordinate-leak fixes through deploy and
  live-verification, and the quorum correction) moved wholesale to the same
  archive file — it reports itself fully finished, nothing left gated on a
  human except the already-deferred design-commitment-#1 wording entry,
  carried forward unchanged. The handover at the top of this file is the
  fresh compacted current state, including two corrections the archived
  version's own text no longer reflects: both coordinate leaks are now
  fixed/deployed/verified (the archived text still frames them as open in
  a couple of places), and the driving-brain choice (`openclaw`) and
  live-view-ingest shelving are both folded in as settled state rather than
  same-session news.
- 2026-09-15: the whole 2026-09-12 to 09-14 section (the agent architecture design phase, the MCP server build and live smoke test, the durable deploy, openclaw install and first agent calls, both architect charter runs, the relative-LEVEL, isError and call-log fixes, and the dfqueue and live-signals builds) moved wholesale to
  [`working-archive/Working_archive-2026-09-14.md`](working-archive/Working_archive-2026-09-14.md).
  The file was 893 lines. Every still-open item was carried into the current-state section at the top.
- 2026-09-19: the whole HANDOVER 2026-09-17 section moved wholesale to the 2026-09-14 archive file. Its fort figures (tick 227008, "drink is solved") had been disproven by measurement and its stream list overtaken, but the fishing reversal, the stair background and the ground-truth idea live only there. Every still-open item was carried into HANDOVER 2026-09-19.
- 2026-09-17: the whole HANDOVER 2026-09-16 section (the production-gap discovery, the stocks/labor-race fix, the knowledge-scope audit, and the day-one farm-and-water work) moved wholesale to the same 2026-09-14 archive file, since the file exceeded the ~400-line threshold. Every still-open item was carried into HANDOVER 2026-09-17 at the top; nothing was summarised or dropped.
- 2026-09-21: the 2026-09-18 live-fort sections ("cannot drink") and the whole HANDOVER 2026-09-19 (rollback, walkability contradiction, the deploy and sampler updates, the old START HERE list and "Done today") moved wholesale to the 2026-09-14 archive file; the file was 586 lines. Open items were carried into HANDOVER 2026-09-21.
- 2026-09-24: everything from "In design: the agent loop MVP" through "HANDOVER — archived" (the agent-loop MVP design phase and its later additions, the learning-loop discussion, the 2026-09-23 loop-closed handover and its streams, and the 2026-09-21 handover) moved wholesale to [`working-archive/Working_archive-2026-09-24.md`](working-archive/Working_archive-2026-09-24.md); the file was 1091 lines. None of the moved content was still-open work. Everything still open (the office, the ghost, the wiki mirror, deploy backlog, ore, design thoughts) is in the current-state section at the top, freshly written rather than carried forward line by line, since almost none of the old text was still accurate.
- 2026-09-25: the whole "Current state, 2026-09-24 evening" section moved wholesale to [`working-archive/Working_archive-2026-09-25.md`](working-archive/Working_archive-2026-09-25.md): the office, the ghost, and the manager-order question report themselves finished or set aside, and the wiki mirror and districting items are directly superseded by the same day's and 2026-09-25's own later work (the switch-over rollback and reader deploy, the districting prior-art pass completing). Everything still open is in the current-state section at the top, freshly written.
- 2026-09-28: most of the "Current state, 2026-09-25" section moved wholesale to [`working-archive/Working_archive-2026-09-28.md`](working-archive/Working_archive-2026-09-28.md) (the wiki mirror switch-over/reader deploy, the districting prior-art completing, the full conductor redeploy and five-cycle first-real-run narrative through 2026-09-28, the drift audit, and the well/tripwire live-verification): it reported itself finished or superseded throughout, and `decisions/DECISIONS.md` gained matching 2026-09-25/28 rows that had been missing. Everything still open is carried forward in the current-state section at the top, freshly written and tightened per the archive-cadence rule (the old section had grown into one dense paragraph).
