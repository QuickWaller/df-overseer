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
  is paused (the popup was dismissed 2026-09-16), so the clock is not moving.
  → register 2026-09-15 rows,
  `handoffs/2026-09-15-queue-live-deploy.md`.
- **Saves:** under the `df` user's XDG data dir on VM 103 (`Bay 12 Games/
  Dwarf Fortress/save`), **not** the game directory: slots `autosave 1..3`,
  `current`, `region1`, `region2`. Two quicksaves wrote `autosave 2` and
  `autosave 3` on 2026-09-15; `quicksave` rotates slots and needs a render
  pass, so it can silently do nothing (memory/fort-operations-and-incidents).
- **Tests:** ambient `python -m pytest` gives 276 passed, 1 skipped;
  `.venv-dfmcp` gives 152 for `dfmcp/tests`.

## HANDOVER 2026-09-16 (read this first after a /clear)

**The fort is in trouble and paused, which is the safe state.** The user
dismissed the popup and re-paused on 2026-09-16; **the orchestrator then
verified it live, read-only**: `pause_state` genuinely true, focus
`dwarfmode/Default` (no dialog up), year 30, `cur_year_tick` 213622,
`frame_counter` 79020, 15 citizens. (Food at that reading was miscounted as 0;
the corrected figure is below.)
About 140 ticks passed between the earlier reading and the pause, nothing more.
The earlier "frozen behind a popup at tick 12309480" state is resolved; the
count below stands. Verified live from inside:

- **fort-owned drink 0; fort-owned food 24 units (5 items: 10 fish, 9 plant,
  5 meat), for 15 dwarves.** Deployed `df-overseer-stocks food-drink` returns
  exactly this, matching the user's own screen reading.
  **Corrected three times on 2026-09-16.** The first count said 234 food and 50 drink and included the
  caravan's goods. The second filtered on `not flags.foreign` and said 0 and 0.
  Both are wrong: **`flags.foreign` is an origin flag, not an ownership flag**,
  true for the fort's own embark supplies too, so it erases the starting
  stores. `flags.trader` is the real fort-vs-caravan test, verified live and
  independently by two sessions (a strict subset of `foreign`: 565 foreign, 292
  trader, zero trader-but-not-foreign, cross-checked through `UNIT_HOLDER` →
  `isMerchant()`). The third error: the first stocks tool counted item
  entities, not stack units, and reported 5 where the fort has 24; the user
  caught that one from the screen too. → `docs/TRAPS.md`.
  The user spotted the original error from the screen before the orchestrator
  did.
- 15 citizens, 59 fort-owned seeds (34 plump helmet; the earlier 119 included
  foreign ones), **zero farm plots, zero stills, zero workshops of any
  kind, no trade depot**. A caravan and the outpost liaison are waiting and
  cannot unload without a depot.
- The fort produces nothing. Stores are not the problem; production is.

**The gap that matters: our agents cannot fix any of this.** The whole write
surface is dig, open-area build, landmark build and labor set. There is no tool
to build a workshop, farm plot, trade depot or typed stockpile, none to create
manager work orders, and none to trade. `proposal-0001` (accepted by the
Overseer 2026-09-16) could not be executed even with the execution tools
switched on.

**Research landed and is merged on `main`:**
`research/2026-09-16-food-and-drink-logistics.md`, dispatched because the user
asked for research first, then an agent to build the tools ("it would be good
to learn how to build the tools as we do it"). Its findings, orchestrator
spot-checked against `memory/dfhack-environment.md`:
- **Trade is buildable but not closeable.** A depot can be built (quickfort),
  and `logistics add trade` can stage goods, but no struct-level API was found
  for executing the trade itself, only the trade viewscreen, which this repo
  bars outside embark bootstrap.
- **Gathering needs activity zones, and the `zone` plugin is unavailable on
  this install** (confirmed in `memory/dfhack-environment.md`'s unavailable
  list, alongside `stocks` and `workflow`). No zone tooling exists here.
- **A farm is the sound long-term path and the slowest**: dig, build, a season,
  a harvest, then a still or kitchen linked before anything is edible.
- **The cheapest real win is manager orders**: `workorder` is available and is
  the only route to them; `orders import library/basic` brings a DFHack-authored
  food and drink standing-order set with no new Lua.
- **Biggest missing read tool:** nothing can distinguish fort-owned stores from
  foreign goods, which is exactly the mistake made today.
- **Genuinely unknown on this install:** `seedwatch`, `buildingplan`,
  `autofarm`. Check these before building against them.
- **Unresolved:** how long the caravan waits.

**The user's framing (restated 2026-09-16):** the fort is an experiment and is
expendable, "we can always delete the fort and restart". Rescuing it is worth
trying **because the tools get built along the way**, not because the fort
matters. Nothing here is an emergency; the tool layer is the point.

### START HERE, in priority order

This is the single current priority list. It supersedes the 2026-09-15 list
that used to sit lower in this file, whose item 1 ("execute `proposal-0001`")
assumed a running fort and a write surface that could carry it; neither holds.

1. ~~Merge and review the research branch~~ **DONE 2026-09-16**, on `main`
   (`eb9e83d`, `research/2026-09-16-food-and-drink-logistics.md`).
2. ~~Decide the rescue path~~ **DECIDED 2026-09-16: continue on this fort.**
   The user dismissed the popup, re-paused, and said "I think we should
   continue on this fort for now". Restarting on an embark chosen to exercise
   an opening ladder was raised by the orchestrator and is **deferred, not
   rejected** — worth revisiting once the tools exist, since a mid-game fort
   with a caravan parked outside cannot exercise an opening policy.
3. **The building tools, in the order the user agreed 2026-09-16.** The whole
   list is still workshops, farm plots, trade depot, typed stockpiles and
   manager orders, landmark-relative with no coordinate crossing the boundary
   (`workorder` is available; `orders import library/basic` is the cheapest
   real win with no new Lua). But three things come first, agreed explicitly:
   1. **The fort-owned vs foreign stocks read**, because every other tool and
      every ladder branch is downstream of a question that answers wrong
      today. **Dispatched** (see below).
   2. **Something that runs on a schedule.** Nothing does: no grader schedule,
      no Sentry, agents are one-shot `agent exec`. A ladder is inert without
      a loop that wakes, checks preconditions and acts, and the "timing" half
      of the problem (season, caravan departure, winter freeze) needs a
      clock-aware trigger. **Not yet designed** — the biggest structural gap.
   3. **The `set_labor`/`autolabor` race**, before anything writes labors.
      The ladder's first rung is fishing, which assigns a fisherdwarf labor,
      which is the losing side of that race. **Dispatched** (see below).
4. **A grader schedule**, so live predictions actually grade. Then the rest of
   the feed:
   1. a publisher of `dfqueue.render.public_view` only (allowlist and kill
      switch; **no delay, user's call 2026-09-14**);
   2. the stream page, noVNC left and a scrolling feed right. **Public, so it
      needs its own go-ahead.**

   It shows proposals and rulings, not agent-to-agent chat (user's call; §4
   kept). Note `proposal-0001` is deliberately left ungraded, see the facts
   section below.
5. **Architect quality, with several samples per configuration.** Run #3 fixed
   the dropped record, but n=1 each: its prediction (`fort.landmarks.count gt
   4` in one day) cannot attribute an outcome, it judged "nothing to dig" from
   level 0 only, and run #2's scope slip (a defensibility proposal) is untested
   since. → `evals/live/2026-09-15-architect-third-charter/README.md` review
   section. Same for the Overseer: `ruling-0001` was charter-clean but called
   an unattributable prediction sound and did not notice the fort was stopped.
6. **The `set_labor`/`autolabor` race**, a live single-writer violation that is
   small to fix.
7. **Only then** execute a proposal end to end. `proposal-0001` (accepted
   2026-09-16, `ruling-0001`, `deepseek-v4-pro`, $0.0068) could not be executed
   even with the Overseer's write tools switched on, because no tool builds
   what it asks for. Execution still needs those tools allowed and the user's
   go-ahead.

### Facts established 2026-09-15/16 that contradict older docs

- **The sim frame cap is 100, not 5** (`enabler.fps` 100, graphics 50, about
  100 ticks per wall second). Cost and latency reasoning built on `FPS_CAP:5`
  is wrong by 20x; the doc pass corrected the number and deliberately did not
  rewrite the conclusions. Still open: the 45-80s command-latency explanation
  in `agents/overseer/role.md` and `docs/AGENT-ARCHITECTURE.md` §14 item 5.
- **Saves are at the XDG path**, not the game directory: slots `autosave 1..3`,
  `current`, `region1`, `region2` under the `df` user's data dir. Already in
  TRAPS.md; rediscovered the hard way.
- **`proposal-0001`'s prediction window is blown.** 1200 ticks elapsed within a
  minute of unpausing with nobody acting, because ruling and execution are
  separate supervised steps hours apart. Grading it now records a latency miss,
  not a verdict on the proposal. Left ungraded on purpose.
- The Overseer's first ruling was charter-clean but called an unattributable
  prediction sound, and did not notice the fort was paused. One sample, cheap
  model.

### Live state as of this handover

- **VM 103:** dfmcp-server active, queue DB at `/var/lib/dfmcp`, incident
  capture installed, DF running under the frozen popup. Overseer and consultant
  tokens rotated 2026-09-15; the architect token was not.
- **VM 106:** openclaw with two agents (`architect`, `overseer`), one MCP entry
  and token each in `/opt/openclaw/secrets/openclaw_secrets.env` (mode 600,
  placed by the user, since sessions are refused writes there). Incident
  capture installed. Its old disk is deleted.
- **DeepSeek key is still plaintext** in openclaw's state DB; the env SecretRef
  is configured but shadowed by the `deepseek:manual` auth profile, and
  removing that profile was refused by the classifier. A user-run script could
  do it, like the token placement one
  (`scripts/`-worthy, currently only in a session scratchpad).
- **Classifier refusals seen repeatedly:** writes to secret stores, disk
  detach, and ad-hoc Proxmox config writes. Named `provision_vm.py` subcommands
  were fine. Route these back to the user, never through another agent.

### In flight, dispatched 2026-09-16

All Sonnet, worktree-isolated, committing on their own branches. None of them
touches `Working.md`, the register or `memory/`.

- ~~**`handoffs/2026-09-16-stocks-read-and-labor-race.md`**~~ **DONE and merged
  to `main` 2026-09-16.** `scripts/dfhack/df-overseer-stocks.lua` (new:
  `food-drink`, `seeds`) registered in `TOOLS.yaml` and granted to all three
  enabled roles; four `stocks.*` signals added to `learning/live_signals.py`'s
  closed registry, so a food or drink prediction is writable and gradeable for
  the first time; and the `set_labor`/`autolabor` race fixed by excluding the
  targeted labor from autolabor's management before writing, or **refusing with
  a reason** when it cannot tell. Ambient suite 276→**281 passed, 1 skipped**,
  re-run by the orchestrator; `dfmcp/tests` 152. Fort left paused throughout,
  nothing deployed. Its load-bearing correction is the `flags.foreign` trap
  above. **Still owed: a deploy pass** (orchestrator, needs a go-ahead) to
  place both scripts on VM 103 and exercise `autolabor LABOR disable` live
  once, which moves item 3 from verified-by-mechanism to verified-by-execution.
- ~~**`research/2026-09-16-trade-execution-api.md`**~~ **LANDED and merged to
  `main` 2026-09-16.** The previous pass's negative conclusion survives, but
  the picture underneath is much richer than "only the viewscreen", and it
  corrects a struct-level error the older docs still carry.
  **Orchestrator-verified live, not relayed:** `df.viewscreen_tradegoodsst` is
  **nil in this build** (trade moved into `df.global.game.main_interface.trade`
  with the v50 rewrite), `dfhack.items.markForTrade` exists,
  `main_interface.trade.goodflag` is present, and `caravan`, `diplomacy`,
  `force`, `logistics` and `workorder` all answer `help`. So **staging goods
  and selecting exactly which items change hands are real, code-level,
  zero-screen operations.** The *only* missing step is the final commit: no
  struct-level equivalent exists anywhere in the build, the vanilla button is
  engine-dispatched, and `A_BARTER_TRADE` is adventure-mode bartering,
  confirmed absent from `df.interface_key`. The exact input that fires the
  fortress-mode Trade button is **unknown and untested** (it needs a real depot
  and a caravan at it).
  **The policy question, for the user, not for an agent:** driving that last
  step via `gui.simulateInput`/`screen:feed()` needs no X11, no xdotool and no
  window focus, so it is *not* the `df-overseer-ui`/`xdotool` mechanism §7
  bars, though it is arguably the same category. Undecided on purpose.
  **Two concrete side-findings.** The caravan dwell question the previous pass
  left open is settled: `caravan_state.time_remaining` is in 1/120-day units
  (verified at source, `caravan.lua:68` divides by 120) and Uniboslan's caravan
  reads **3133, about 26 days left** — the orchestrator re-derived this after
  initially doubting the arithmetic, and the researcher was right. And
  **`caravan extend` is a real, available, zero-UI-automation write** with no
  cap found, so the clock on the depot is extendable if we want it.
  Original brief: settle whether an agent
  can complete a trade at all. The user did not accept the previous pass's "no
  struct-level API found" as final. Covers the whole `caravan`/`trade`/
  `logistics`/`force`/`diplomacy` surface, the struct level, and the one that
  actually matters: whether driving the trade viewscreen **from Lua**
  (`screen:feed()`, no X11) counts as the UI automation this repo bars, which
  is a policy question for the user, not the researcher. Also chases the
  unresolved "how long does the caravan wait".
- ~~**`research/2026-09-16-opening-priority-ladder.md`**~~ **LANDED and merged
  to `main` 2026-09-16.** Recommends the ladder as a versioned data file
  (`playbooks/opening-ladder.yaml` — the directory `docs/AGENT-ARCHITECTURE.md`
  §969 already reserves and that does not exist yet): rungs with closed types,
  coordinate-free preconditions, ranked branches where real judgment exists,
  and a prediction in `dfqueue`'s existing grammar. A new `ladder.next` read
  tool evaluates preconditions and returns ranked eligible rungs, the same
  "code narrows, model chooses" shape as `find_open_area`. Adjustment is never
  a silent edit: graded outcomes per rung, threshold revision queued and ruled.
  **Its own stated biggest risk, orchestrator-verified at source:** the
  ladder's most valuable predictions are unwritable today, because
  `learning/live_signals.py`'s closed registry has exactly six signal kinds and
  no `stocks.*` — which is why the stream above exists. **Of 16 branch-facts,
  5 are readable today and 11 are gaps.** Farm methods: only digging to a soil
  layer survives the no-coordinates rule; flooding rock needs hydraulics
  tooling that does not exist, and the water-dump-and-cancel trick is
  zone-gated and structurally close to the barred UI path. Fishing needs no
  workshop to catch and no zone, so a minimal fishing rung may be buildable
  today; fish stocks do deplete permanently. **Not verified:** stagnant vs
  flowing water, checked twice independently and still unestablished.
  Original brief: an
  opening priority order the Overseer can adjust, adapt and learn from, given
  stocks, map and timing (their own opening: fishing, then drinking from open
  water, then farms by flooding rock, the water-dump-and-cancel trick, or
  digging to soil). Cross-domain prior art first, then a **data** format under
  three existing constraints: no coordinates, the model does not edit its own
  memory, and doctrine has a measured size budget. Its most useful output will
  be the **required-reads list** — every fact the ladder must branch on, marked
  readable-today or not, which is the requirements list for the tool stream.

### Farm and food clock, in flight 2026-09-16

**Verified live first:** all six fort seed types are subterranean crops (none
grows outdoors), and the terrain is **z169 surface over a single SOIL level
at z168 over stone**. So the farm is a room dug into z168: underground,
soil-floored, valid for every crop held. A surface farm would grow nothing.

- **`handoffs/2026-09-16-farm-and-still-tools.md`** (Sonnet executor): correct
  the dig finder to "acting on hidden tiles is allowed, sensing them is not"
  (the audit made it refuse hidden tiles, so it cannot propose the z168 room);
  `farm.find`/`build`/`set-crop`; `workshop.find`/`build` for a still. Dry-run
  modes verified live, no fort mutation; the orchestrator runs real builds.
- ~~Food clock research~~ **LANDED and merged.** Food is not binding (raw
  plump helmets close it); **drink is**, and turns on whether dwarves can
  reach the pools. Verified live: 11/15 dwarves thirsty, worst ~18,400 ticks
  from dire (the install's own notify threshold, 50,000); pool edges are
  ramps under full-depth water with no dry standing tile. Counter-evidence: 4
  dwarves drank ~9,700 ticks ago with no drink stocked. **At 100 FPS the race
  is minutes of wall time.** `setfps` is available and is the lever.
- **Act/sense reading confirmed by the user** ("yeah"): acting on hidden
  tiles is allowed, sensing them is not. Applies to all tools.
- **Waiting on the user:** lower the frame cap and run a short supervised
  unpause to see whether thirsty dwarves drink from the pools. Everything
  (farm urgency, whether water access must be built first) depends on it.

### Agents know only what a player could know (decided 2026-09-16)

User's call: agent tools limited to `player_visible` and `player_derivable`.
Existence may be known from the embark screen; **location only once
uncovered**. Binds the role allowlists, not developer diagnostics. Full
reasoning in the register.

- ~~**In flight:** research~~ **LANDED and merged 2026-09-16.** Visibility is
  gated by `designation.hidden` (terrain), `dfhack.units.isHidden` (units; 29 of
  75 active units, all 5 demons, orchestrator-verified live), and feature
  `Announced` flags plus discovery announcements (caverns, veins). Hardest grey
  zone: `threat.lua` exists to catch ambushers, exactly what a player cannot see.
- ~~**In flight:** knowledge-scope audit~~ **DONE, merged and DEPLOYED to VM
  103 2026-09-16.** No agent tool is `omniscient`; `dfmcp` refuses to load if
  one is granted. Verified live: role tool lists 16/11/2 before, 18/13/4 after
  (exactly as computed from merged code), `unit-status hostile` demons 5 → 0,
  stocks 24 food / 0 drink. Backup at `/opt/df/deploy-backup-2026-09-16`.
- ~~Owed before unpausing: restart DF~~ **DONE 2026-09-16 10:43-10:44 UTC.**
  Save verified on disk first (`autosave 2`, 10:42:50), backed up, DF
  restarted, reloaded via "Continue active game", identity matched exactly
  (tick 213622, 15 citizens, the day's FISH labor still set), still paused.
  The `diff.since` visibility gate is live. Backups of both saves at
  `/opt/df/deploy-backup-2026-09-16/`.
- Original research brief: `research/2026-09-16-player-visibility.md` (Sonnet
  `researcher`, read-only, worktree-isolated): what a vanilla v50 player can
  see, when it becomes visible, which struct fields gate it, the exact
  embark-screen list, game-AI prior art (BWAPI's `CompleteMapInformation`),
  and a **preliminary** `knowledge_scope` tag for every tool in `TOOLS.yaml`.
- **Next, once it lands:** an executor audit that tags every tool, adds a
  discovery check to `find_diggable_area`, gates hidden-unit reporting in
  `df-overseer-threat.lua`, and **measures** what each change costs.
- **Accepted cost, now real:** the threat scan no longer reports ambushers or
  sneaking units at all. The player-equivalent signal is the ambush
  announcement family already tagged in `diff.since`'s REPORT branch.

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
  known_hosts files. VM 103's host keys were regenerated 2026-09-11 when
  cloud-init saw a new instance id during the outage recovery, which is what
  made a stale entry look like a changed host in Phase B. Worth pinning the
  estate's real keys.
- **Deploy with `git -c core.autocrlf=false archive`.** Phase B's deploy is
  CRLF on VM 103 (content correct), so naive sha256 checks against `main`
  fail. Also from Phase B: `dfmcp.auth` reads only `REPO_ROOT/.env`, so a
  throwaway instance needs its own code copy; openclaw's schema now rejects
  `pinned-config.json`'s `_note` key.

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
