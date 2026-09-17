# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.


## Current state, 2026-09-15: the agent loop is reaching the fort, and the channel exists

The 2026-09-12 to 09-14 section (the agent architecture design phase, the
MCP server build, its first contact with reality, openclaw's install and the
first agent calls) moved wholesale to
[`working-archive/Working_archive-2026-09-14.md`](working-archive/Working_archive-2026-09-14.md).
Everything below is what is still open.

**Where things stand.**
- **The server:** `dfmcp-server.service` runs on VM 103, LAN-bound, with
  bearer tokens as the only guard until Tailscale. It is live-verified with
  relative `level` args, `isError` for script errors, and a JSON tool-call
  log in journald.
- **The agent host:** openclaw on VM 106 has run the architect three times as
  a one-shot `agent exec` on DeepSeek. VM 106 went dark after run #3 and was
  rebuilt in place 2026-09-15. openclaw is reinstalled and now hosts two agents,
  architect and overseer, with both MCP tokens in place (2026-09-16).
- **Incident capture** (guest agent, persistent journal, per-minute netwatch
  dump on gateway loss) is live on VMs 103 and 106 since 2026-09-15. A new
  clone needs `provision_vm.py setup-capture --vmid N` run by hand. **Why
  VM 106 went dark on 2026-09-14 is still not established**; the capture is
  there to record it if it recurs (`docs/RUNBOOK-DARK-GUEST.md`).
- **The queue is live** (2026-09-15): `queue.propose`/`pass` (architect) and
  `queue.rule`/`pending` (Overseer) on VM 103, DB under `/var/lib/dfmcp`.
  It holds one real record, `proposal-0001` from architect run #3, with a
  pending prediction (`due_game_tick` 12276077), accepted by the Overseer
  2026-09-16. No grader runs on a schedule; its window is blown regardless
  (see the facts section below) and it is left ungraded on purpose. The fort
  has since been unpaused several times for supervised tests (2026-09-17,
  see the HANDOVER below) and is paused again now.
  → register 2026-09-15 rows,
  `handoffs/2026-09-15-queue-live-deploy.md`.
- **Saves:** under the `df` user's XDG data dir on VM 103 (`Bay 12 Games/
  Dwarf Fortress/save`), **not** the game directory: slots `autosave 1..3`,
  `current`, `region1`, `region2`. Two quicksaves wrote `autosave 2` and
  `autosave 3` on 2026-09-15; `quicksave` rotates slots and needs a render
  pass, so it can silently do nothing (memory/fort-operations-and-incidents).
- **Tests:** ambient `python -m pytest` gives 294 passed, 1 skipped;
  `.venv-dfmcp` gives 165 for `dfmcp/tests` (register 2026-09-17 figures).

## HANDOVER 2026-09-17 (read this first after a /clear)

**The 2026-09-16 handover (the production-gap discovery, the stocks/labor-race
fix, the knowledge-scope audit, and the start of the farm-and-water work)
moved wholesale to
[`working-archive/Working_archive-2026-09-14.md`](working-archive/Working_archive-2026-09-14.md).**
Everything below is today's outcome and what's still open.

**Uniboslan drinks and grows food for the first time.** Paused, tick
**227008**, year 30, 15 citizens, no deaths, `dwarfmode/Default` focus (no
dialog up), the last state every stream today independently re-verified
live before touching anything. Nothing is running right now.

- **Drink is solved, in practice.** Every pond is a sunken basin of 6-7/7
  water at z168 with nowhere dry to stand at the water's own level, which is
  why nobody drank unaided (`research/2026-09-17-founders-not-drinking.md`).
  A `WaterSource` zone placed **on the water itself** at z168 (Activity Zone
  #1, still in place) fixed it: one supervised 10 FPS unpause got three
  founders down to z168 and self-serving water (thirst near zero; 197 with no
  caretaker at all, the project's first confirmed self-serve drink), and three
  more picked up a fresh `NastyWater` thought right at the end of the same
  window. **Not proven as the sole cause** (no zoneless control ran), but
  decisive enough that the zone stays. Two open risks: dwarves stand in 6-7/7
  water (deep enough to drown a poor swimmer), and the water is stagnant
  (health effect of the `NastyWater` thought unverified). A well removes both
  and is no longer urgent. → `decisions/DECISIONS.md` 2026-09-17 rows,
  `research/2026-09-17-water-source-zone-test.md`.
  **Correction folded in:** an earlier same-day research pass
  (`research/2026-09-17-pool-reachability.md`) concluded `getWalkableGroup`
  was broken around ramps; its own top-of-file correction note (verified live
  before that doc was committed) found this was wrong: the ramps really are
  underwater, not miscategorised. Read the correction note, not the body, if
  citing that doc.
- **First real food production: the farm plot is built and sown.** A 5x5
  `building_farmplotst` at z168 (x100-104, y101-105), `flags.exists=true`,
  all four seasons carry plump helmet (`plant_id=173`), orchestrator-verified
  by direct struct read. **The still is not built.** It is designated at the
  surface (z169, x96-98, y97-99; no free 3x3 floor exists underground once
  the farm plot took the only one), material is not the blocker (15 wood / 3
  boulders / 4 blocks free and unreserved, up from the 0 boulders/blocks a
  same-day research pass had found earlier, not chased), but its
  `ConstructBuilding` job (id 366) never got a worker across a full 453s
  unpause (30 samples, every idle citizen instead cycled through
  Drink/Eat/Sleep). `decisions/DECISIONS.md` frames this as the job "reading
  suspended"; the execution stream's own live read only confirms
  "unassigned, never picked up," not a suspend flag specifically; worth
  checking directly before assuming which it is.
  → `research/2026-09-17-farm-still-first-build.md` (handoff Result),
  `decisions/DECISIONS.md` 2026-09-17.
- **Water and industry tools shipped: zones, tree felling, work orders, a
  well builder, and three more workshop kinds.** New: `zone.find/place`,
  `trees.find/fell`, `well.find/build`, `orders.list/create/cancel`;
  `workshop.find/build` extended with mason/mechanic/carpenter plus a
  `building_material` field (verified live: all five workshop kinds accept
  boulder, wood or block interchangeably). Deployed and live-verified
  (hashes, restart, dry runs, and direct proof the new code is running, not a
  stale `reqscript` cache). **Role tool lists: architect 19, overseer 32,
  consultant 4** (up from 13/18/4 this morning). No citizen holds the
  Manager position, so `orders.create`'s effect on a queued order with no
  manager appointed is reported but not enforced, untested against a real
  unpause.
  → `handoffs/2026-09-17-water-and-industry-tools.md`,
  `handoffs/2026-09-17-water-industry-tools-deploy.md`.
- **Seed economics researched; game knowledge now lives in `doctrine/`, not
  here.** Brewing, quarry-bush-bagging and pig-tail papermaking are
  raw-confirmed 100%-guaranteed 1-seed-per-plant returns; cooking returns
  zero, confirmed two ways. Break-even: at least `1/Y` of a harvest (Y =
  plants per tile) must go through a guaranteed-return method, so an
  unskilled, unfertilized farm can cook nothing yet. Figures table ready for
  the game-figures database `ROADMAP.md` now tracks as a Next item.
  `doctrine/seed.yaml` and `docs/TRAPS.md` were both already updated today by
  the streams that found the facts; nothing in this pass contradicted either,
  so neither was touched further.
  → `research/2026-09-17-seed-ratios.md`, `doctrine/seed.yaml`.
- **Stocks tonight** (live-read during the farm-still build, the most recent
  figures anyone has): fort-owned food (raw_edibles) **17 units** (item_count
  4, down from 20 this morning, ordinary consumption from Eat jobs during the
  unpause, nothing deliberate); drink still **0**; prepared_meals **0**;
  seeds **60 total, 35 plump helmet** (the register's own count, one higher
  than the 59/34 an earlier reading gave, not chased).

### START HERE, in priority order

1. **Clear the still's stuck/suspended construction job.** Material is
   available; nobody has worked it across a full unpause window. Check
   whether it is actually DF's `suspended` flag or just never assigned a
   worker before deciding how to unstick it.
2. **Fix `df-overseer-farm.lua`'s two live bugs**, both found and worked
   around live today but not fixed in code:
   - a farm plot's `plant_id` write does not survive the plot's own
     construction completing (order matters: build, wait for
     `flags.exists`, *then* set the crop);
   - `build_farm_plot` calls `dfhack.buildings.setName`, which does not
     exist on this install, through an unchecked `pcall`, so it silently
     fails and the tool reports a name that was never actually set.
   → `docs/TRAPS.md`'s two 2026-09-17 entries on this file.
3. **Teach `df-overseer-diggable.lua` to propose a dig two levels down.**
   At z167 (one level under the farm room, where the fort's stone is) it
   returns nothing today, because its ring-adjacency check only looks at
   the *same* z-level and z167 has no walkable network yet: a structural
   gap the tool's own header already names as v1's scope limit. This
   blocks blocks, mechanisms and the well long-term, even though the still
   and well both currently have just enough material on hand without it.
   → `handoffs/2026-09-17-water-and-industry-tools.md` ("Stone access").
4. **Then a longer supervised run** for planting (nothing has sprouted yet;
   the plot only finished construction partway through today's window) and
   the still, once 1-3 are done.

### Founders-not-drinking: answered in practice, not in full

The zone fix (above) resolved the symptom. The deeper "why job-assignment
routed founders as `GiveWater` workers and migrants as patients, when
founders were thirstier" question in
`research/2026-09-17-founders-not-drinking.md` is still open (three ranked
hypotheses, none confirmed) but no longer blocks anything: self-serve
drinking now works. Not worth chasing further unless it recurs.

### Not yet done, carried from the 2026-09-15/16 ladder (lower priority than
the list above)

- **A grader schedule.** Nothing runs on one; no Sentry. `proposal-0001`
  remains ungraded on purpose (its window blew before this was ever fixable).
- **The public feed/stream page and `dfqueue.render.public_view` publisher.**
  Not built; needs its own go-ahead once built (public-facing).
- **Architect and Overseer quality**, still n=1 each. `ruling-0001` was
  charter-clean but judged an unattributable prediction sound.
- **Execute a proposal end to end.** Still blocked on no tool building what
  any proposal so far has asked for.

### Open, waiting on the user

- **DeepSeek key in plaintext on VM 106** in
  `/opt/openclaw/config/state/openclaw.sqlite`. openclaw 2026.9.4 has no
  headless way to store it as a reference; `openclaw secrets configure` over
  `ssh -t` might. `sudo rm -rf /opt/openclaw` removes both secrets.
- **PVE token rotation**, deferred by the user. It needs a privileged
  identity, and deleting a token drops its ACLs.
- **Tailscale**, deferred. Until then the LAN bind means tokens are the only
  guard.
- **Two deferred live checks:** whether the frame cap survives a save load,
  and whether an overlay renders in the headless pipeline.

### Owed elsewhere

- **`home-lab` `inventory/services.yaml`: the `dfmcp-server.service` entry is
  written, not committed.** home-lab-fe added it 2026-09-15, marked
  `inferred`, and validated it. It is left in that checkout for the user to
  review and commit. VM 106 owes an entry only once openclaw runs as a service
  (nothing listens today).

### Background, not urgent

- **Project SSH never verifies host identity.** `scripts/provision_vm.py` and
  `scripts/install_df.py` use `StrictHostKeyChecking=no` with throwaway
  known_hosts files. Worth pinning the estate's real keys eventually.
- **The breach detector is inconclusive.** Settle it opportunistically (rain,
  or an animal fording water), never by flooding the fort.
- **The `../openclaw` scaffold** reads `OPENCLAW_CONFIG_DIR` and
  `OPENCLAW_AUTH_PROFILE_SECRET_DIR`, which the image ignores; use
  `OPENCLAW_STATE_DIR` before running it durably.

## HANDOVER — archived

The 2026-09-12 session-end handover moved wholesale to
[`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md)
(file was past the ~400-line threshold). Its durable-traps list now lives
permanently at [`docs/TRAPS.md`](docs/TRAPS.md) — **read it there, and add new
traps there rather than here.** Current state is the section above.

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
- 2026-09-17: the whole HANDOVER 2026-09-16 section (the production-gap discovery, the stocks/labor-race fix, the knowledge-scope audit, and the day-one farm-and-water work) moved wholesale to the same 2026-09-14 archive file, since the file exceeded the ~400-line threshold. Every still-open item was carried into HANDOVER 2026-09-17 at the top; nothing was summarised or dropped.
