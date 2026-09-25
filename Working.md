# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.

## Current state, 2026-09-25 (read this first)

**Live and settled since 2026-09-24.** The office is built, furnished, owned by the Manager, and the game itself accepts it (the room-value proxy's false negative on `getRoomDescription` is fixed). The ghost has been laid to rest: a Tomb zone over its coffin (the coffin's known-suboptimal site is now load-bearing), confirmed by direct struct reads and the game's own report text. Manager orders still never dispatch a job; **the user's ruling is to set this aside** rather than keep chasing it. Full detail in `working-archive/Working_archive-2026-09-25.md` and `evals/live/2026-09-24-ghost-slab/`.

**The Consultant now answers from the full offline wiki mirror, live-verified.** A 2026-09-25 switch-over attempt was blocked (the S4 reader code had been merged but never deployed, so the server tried `json.load` on the SQLite file; rolled back cleanly, `handoffs/2026-09-25-wiki-switchover.md`). This also explained the day's 27-vs-28 consultant tool-count mismatch. The reader deploy that followed actually switched it over (`handoffs/2026-09-25-wiki-reader-deploy.md`): `wiki_reader.py`, `wiki_search`, a loader `UnicodeDecodeError` fix with a test, a `PYTHONPATH=/opt/df/wikimirror` gap found and fixed, env pointed at the SQLite mirror. Real consultant calls (Tomb revid 315152, Office revid 314166, both `fresh`; `wiki_search` 8 results) and orchestrator re-verification on the VM confirm it. Tool counts now stable at **overseer 79, architect 49, consultant 28, quartermaster 24, conductor 15**. **Still needs its own step:** the refresh timers (S8): until built, the mirror only refreshes by hand and the reader reports `stale` after 24 hours, plus a small follow-up for four gaps S6 found in S1's `store.py`; S7 (changes tool, doctrine flags) is not yet dispatched.

**The districting design session's prior-art research is complete; the session itself is next when the user is available.** Two passes: df-ai (`research/2026-09-24-df-ai-fort-planner.md`: templates, tags and pass/fail gates transfer, random-retry placement does not) and Systematic Layout Planning / architectural adjacency / land-use zoning (`research/2026-09-25-district-layout-prior-art.md`: SLP's qualitative closeness chart is the field's answer to missing flow data; no colony game surveyed solves adjacency; LLMs do better with relational graphs than coordinates but formal composition is weak, so tools must state relations rather than leave composition to the model). Proposal for the session: a kind-by-kind closeness table with a reason per cell, plus per-district contained landmarks and tool-computed relation facts. **Two agenda inputs from the user, 2026-09-25, not decided:** (1) blueprints must mark their entrances/exits, handle rotation, and be modular and connecting: candidate connector properties: type (corridor/door/open/vertical), district tag, width and traffic class, required/optional, door policy per kind, seams, rotation derived by the tool rather than stored per direction, vertical stacking, reserved growth space; (2) **observability is a design requirement**: every inter-agent message carries sender, recipient, type and a one-line rationale, joinable to the tool calls it caused, so the agent activity feed (`ROADMAP.md` Later) can show who talked to whom. The site-ranking redesign (`ranked_rects`, decided 2026-09-24 to need a real design pass rather than a patch) folds into this same session.

**Reloading a save is ruled a test-harness power only, never an agent's** (user's ruling, 2026-09-25, `docs/ARMOK-RULINGS.md`): reloading to undo a bad outcome is save-scumming against the no-armok rule. The save-and-reload comparison-testing idea lives in `ROADMAP.md` Later with its real needs (replicates, a reload route since `load-save` is unavailable in 53.16, grading from the queue's existing predictions); first intended use, per the user, is testing architect tools.

**Conductor `--dry-run --once` re-run 2026-09-25 (VM 106, exit 0):** plan was to wake the Overseer for `queue_pending` ("the queue holds something for the Overseer"), clock full_speed. **REDEPLOYED same day (user's go-ahead, peer heads-up sent):** `conductor/` only (it never imports `dfqueue`, the parser is vendored on purpose, and `dfqueue/` was never on VM 106), from `git -c core.autocrlf=false archive HEAD`; **all 16 conductor files sha256-verified on the VM against committed bytes**; old copy backed up in the `df` home dir on VM 106 as `conductor-dfqueue-backup-2026-09-25.tgz` (conductor only). `conductor.service` still disabled and inactive. Re-run `--dry-run --once`: exit 0, **`game_tick` now 12673497, equal to the fort's `abs_tick` at the last tripwire read**, so the fix is confirmed; the plan now wakes **architect, quartermaster (routine review, 7.0 game days since the last one) and overseer (queue_pending)**. So a real run would wake three roles, not one. **The Overseer's pending queue items, read read-only from the queue database on VM 103 (`Uniboslan.sqlite3`): `proposal-0002` and `proposal-0003`, both architect `room_siting`, 2026-09-23, no ruling, predictions `awaiting_execution`.** Both are about giving the Manager a working office (outdoor 3x3 around the shale Throne, and a carved stone office off the farm level). **Both are superseded: the office has since been built, furnished and owned by the Manager and the game accepts it (see above).** A real run would ask the Overseer to rule on stale proposals, and their prediction windows (1000 and 30000 ticks from tick 12611557) have long elapsed, so grading them now would be meaningless, the same reason `proposal-0001` was voided 2026-09-22. **Recommendation, awaiting the user's call: void both (write a void on the predictions) before the first real run, so the run's first wake is not spent on obsolete work.** **Two findings that preceded it (both now: 1 fixed, 2 open):** (1) `game_tick` is still null in `status.json` because **VM 106 runs stale conductor code: `conductor/game_tick.py` and the `game_tick_error` path in `cycle.py` (repo has 7 references, VM has 0) are not deployed**, so the 2026-09-23 game-tick fix never reached the service; redeploy the conductor first (`git -c core.autocrlf=false archive`, hash committed bytes). (2) What is pending in the queue for the Overseer is not yet read; look before a real run wakes it on that item. **FIRST REAL CONDUCTOR CYCLE RAN 2026-09-25, fort paused throughout** (`evals/live/2026-09-25-first-real-conductor-cycle/README.md`). Attempt 1 failed harmlessly (Docker access is unit-scoped, not for a plain SSH shell); attempt 2 via a transient systemd unit mirroring the approved unit worked: Architect and Quartermaster each filed a proposal (about $0.02 each), and the **Overseer rejected both stale proposals citing live reads (charter held), accepted and really executed a down-stair beside the Farm Plot (paused, so not yet dug), and accepted a brew-drink proposal whose execution failed** (`workjob.queue` cannot take a wildcard container reagent). Overseer hit the 600 s role timeout after finishing its work. Six findings in the README (workjob container gap, positional-argument ergonomics, the timeout, the unwoken Consultant ask, the cursor advancing on a failed run, unit-scoped Docker). Fort re-read after: paused tick 174297, 22 alive. **Conductor fixes deployed to VM 106 the same day (16 files hash-verified, backed up); a second real cycle CRASHED before the Consultant ran:** `/opt/openclaw/consultant-workspace` is `root:root` while the other three role workspaces are `df`-owned, so `write_soul` raised PermissionError. Two follow-ups: chown that workspace to the service account (needs the user's go-ahead, a permission change on VM 106) and make `write_soul` failures a recorded `launch_failed` run instead of a service crash (a crash-loop risk under `Restart=on-failure`). Cost recording for a successful run is still unobserved. Fort untouched, paused, tick 174297. **Recommended next step (orchestrator's call): fix the `workjob.queue` container gap and the positional-argument ergonomics, then consider a second cycle; the down-stair only takes effect when the fort next runs.** The conductor has never run live, only a manual `--dry-run --once`; no agent or conductor cycle has ever made a real decision on this fort beyond `ruling-0001`.

**Drink is 0, and unpausing is a dehydration race (read-only vitals check, 2026-09-25).** Paused at year 31 tick 155487, 22 alive and 1 dead, no new deaths, no stuck jobs, worst hunger and thirst "fine" (frozen by the pause), 161 raw edibles, 157 seeds, **0 drink, 0 prepared meals**. Already on the register since 2026-09-16 (survival-clock entry), not new. **The user believes the Well is running (unverified, not checked by the vitals pass)**, which would make water the supply; whether dwarves actually drink from it, and the tripwire's configured thresholds, are unchecked. **Well and tripwire read-only check, 2026-09-25 (agent report, orchestrator has not re-run it):** Well id 8 is built (stage 1 of 1, bucket, chain, trap parts, blocks), sits on a depth-7 water tile, and all 22 citizens are reachable to it; it is **not proven in use** (paused, zero jobs, Still idle, its manager order inactive). Tripwire is armed at 100 FPS; thresholds are source defaults (thirst 50000, hunger 75000, checked every 100 ticks), not read live, and what the conductor passes to arm is unconfirmed. **Supervised unpause run 2026-09-25 (orchestrator-run, inconclusive on the key question):** quicksaved first (`autosave 2` rewritten, mtime stable across 8 polls), set 10 FPS, unpaused for about 300 s wall (year 31 tick 155487 to about 158523, roughly 3,000 ticks), re-paused by exit trap, then re-read: paused, fps back to 100, 22 alive and 1 dead, worst hunger and thirst "fine", 0 warnings, drink still 0, raw edibles 165 to 161 units (some eaten). Nobody crossed "thirsty", so **no drink job at the Well was observed and the question is still open**; the window was too short (worst thirst about 18,100 at the start, "thirsty" is well above that) and the polling returned categories only. A farm plot now shows a `PlantSeeds` job idle 26 ticks. **Second, longer window, same day (15 min wall at 10 FPS, tick 158527 to 167441, about 8,900 ticks, 60 polls of a bounded 22-citizen thirst/job probe):** **dwarves do drink with drink stock at 0.** `Drink` jobs appeared in 13 of 60 polls (up to 2 at once), the thirstiest timer rose from 16,297 to a peak of 21,038 then fell back (max 14,918 at the end) and per-dwarf timers reset to under 400, so the fort is hydrating itself from a water source. All 22 alive, 0 warnings, worst hunger and thirst "fine" throughout, no tripwire, re-paused by exit trap and independently re-read paused at tick 167441, fps 100. **Caveat: the job type does not say where they drank, so this does not prove it was the Well rather than the pool** (the 2026-09-16 research said no pool tile touches the walkable network, which the Well now bypasses, but the source of each drink was not read). PlantSeeds jobs (3 to 6 at once) are running on the new farm plot. **Attributed, third short window (about 9 min wall at 10 FPS):** a dwarf's `Drink` job carried a `BUILDING_WELL_TAG` general ref and its target tile was one tile from the Well, and the dwarf walked to it (distance 9, 7, 3, 1 over four polls). **So the Well is the working water supply, live-verified.** Re-paused by exit trap and independently re-read paused. The Well question is closed. **Tripwire dry fire, same day:** the conductor's `clock.arm` sends no arguments (`conductor/cycle.py`), so it runs on the script defaults, thirst 50000, hunger 75000, check every 100 ticks, base 100 FPS (arm arguments confirmed). Armed with thirst 14000 (below the thirstiest dwarf's timer) it **latched immediately**: `thirst_critical`, unit 196, status "dehydrated", and **`clock.resume` was then refused until `clock.clear`**, a useful property. Restored: cleared, re-armed on defaults, 100 FPS, paused, independently re-read. **Caveat: the fort was already paused when it fired, so a tripwire pausing a running fort mid-run is still unobserved.** **Mid-run trip attempt, same day: inconclusive, it never tripped.** Armed thirst 400 ticks above the thirstiest dwarf (20,216 to 20,616), unpaused at 10 FPS for about 1,500 ticks: no trip, most likely because dwarves drink at the Well at roughly 20 to 21k (the long window peaked at 21,038 and fell back) so the threshold was never reached, not because the watcher failed. Restored to defaults (re-armed 50000/75000), paused, 100 FPS, independently re-read. **Mid-run trip confirmed on the second try, same day:** unpaused at 10 FPS (tick 174296, `paused: false`), then armed with thirst 5000 while running: within one tick the tripwire **paused the running fort** and latched `thirst_critical` (unit 192, "dehydrated"). Restored (paused, cleared, re-armed defaults 50000/75000, 100 FPS) and independently re-read. **The tripwire safety net is now verified end to end**: latch, reason, pause of a running fort, and resume refused until clear. Caveat: it trips on the arm-time check; the periodic 100-tick check firing on its own is still only source-read. **Still to settle:** does a citizen complete a drink job at the Well, does the pool tile stay wet, the real tripwire trigger, and the conductor's arm arguments.

**Still open:** the tiling generator for `bedroom-cell-v1`; burrow confinement ruling; leaked key rotation (below); the site-ranking redesign and the districting design session (above, both gated on the user); the wiki S1 follow-up is done 2026-09-25 (four gaps fixed, 246 tests) except `refresh.py` still uses raw SQL for redirects and does not call `cancel_held`, and `Store.get_archived_revision` is not added; the wiki refresh timers (S8) and S7 (not yet dispatched); the ore/hematite fix (mine the vein the office ring smoothed over, build a constructed wall, deferred by the user); a real supervised conductor run (above).

**Archived this pass:** the whole "Current state, 2026-09-24 evening" section (the office, the ghost, the manager-order question, the wiki mirror's design/build/first pull, and the districting prior-art start) moved wholesale to [`working-archive/Working_archive-2026-09-25.md`](working-archive/Working_archive-2026-09-25.md); nearly all of it reported itself finished or was directly superseded by this same section.

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
