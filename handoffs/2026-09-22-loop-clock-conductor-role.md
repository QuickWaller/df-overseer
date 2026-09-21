# Stream: game clock, tripwires and the `conductor` role (agent loop MVP, items 1-2)

**Written** 2026-09-22. **Status:** dispatched. **User go-ahead:** given
2026-09-22 ("go put a sonnet on those"). Offline only: **no VM, no deploy, no
model call.** Sonnet executor, worktree-isolated.

## Why

`docs/AGENT-LOOP.md` is the design; read it first, in full, especially §2
(the clock) and §3 (tripwires). In short: code, not a model, controls the game
clock. The fort runs at `base_fps` (100), is slowed to `think_fps` (10) while
an agent deliberates something time-sensitive, and pauses itself inside the
game on a tripwire. This stream builds the game-side half and the MCP role
the conductor service (a later stream) will hold.

## First

`git merge --ff-only main` in your worktree: worktrees are created from
`origin/main`, and local `main` is ahead of it with the design doc.

## Read first

`docs/AGENT-LOOP.md`; `docs/AGENT-ARCHITECTURE.md` §6 (throttling, the
`f·T + k` arithmetic, `df.global.enabler.fps`); `docs/TRAPS.md` (in
particular: the wedged command pipe that took the SSH watchdog down, no
unbounded queries against a live process, quicksave rotation and confirming
by slot mtime); `memory/dfhack-environment.md`; the `overseer-autosave`
`repeat` row in `decisions/DECISIONS.md` 2026-09-19 (in-game registration
that survives restart via `onMapLoad.init`); `scripts/dfhack/df-overseer-sampler.lua`
(the nearest existing in-game periodic script, and where vitals are read);
`scripts/dfhack/TOOLS.yaml`; `dfmcp/roles.py`, `dfmcp/auth.py`,
`agents/ROSTER.yaml`.

## What to build

1. **`scripts/dfhack/df-overseer-clock.lua`**, one tool with subcommands:
   - `set-speed FPS`: set the simulation frame cap (`df.global.enabler.fps`);
     refuse values outside a sane range; return the old and new value.
   - `pause` / `resume`: set pause state. `resume` must refuse while a
     tripwire is latched (below) unless explicitly cleared.
   - `status`: paused or not, current fps, current tick, latched tripwire (if
     any, with reason and tick), whether the watcher is armed.
   - `arm` / `disarm`: the in-game **tripwire watcher**, a periodic check
     scheduled with DFHack's in-game timers (ticks, not wall clock), cheap and
     bounded. On a trip it pauses the game and latches `{reason, tick,
     detail}` where `status` can read it. Tripwires, v1: a citizen death since
     arming; any citizen's hunger or thirst past a critical threshold; a
     hostile admitted by the same reachability logic as
     `df-overseer-threat.lua` (reuse via `reqscript`, do not copy; if that is
     too expensive per check, run it at a lower cadence and say so). Thresholds
     are arguments with defaults, not constants in code. **Source the
     hunger/thirst critical values** from DFHack/df-structures or game data and
     say where each came from; if you cannot source one, make it a required
     argument rather than guess.
   - `clear`: clear a latched tripwire (the conductor does this after the
     Overseer has handled it).
   Perception-layer rules hold: no raw coordinates in output.
2. **`fort.quicksave`**, a tool that runs `quicksave` and reports the slot
   written, confirmed by the slot's mtime changing (the rotation trap). It may
   live in the same script or its own; your call, justified.
3. **`vitals.summary`**: Tier 0 figures only (alive, dead since a tick, worst
   hunger and thirst with their thresholds, count of citizens past a warning
   level). Reuse the sampler's reads rather than writing new ones. O(1) in fort
   size in its output.
4. **Manifest entries** in `TOOLS.yaml` for each, following existing
   entries' fields; `live_deployed: false`, `verified` stating what was
   actually checked (offline) and nothing more.
5. **The `conductor` role.** `agents/conductor/` (charter, `tools.yaml`) and
   a `ROSTER.yaml` entry. It is **code, never an agent**: its token is held by
   the conductor service only. Its allowlist: the clock tool, `fort.quicksave`,
   `vitals.summary`, and read tools the briefing will need (`overview.get`,
   `queue.pending` if role scoping allows). **`dfmcp/roles.py` currently
   refuses any mutating tool to a role other than `sole_writer`.** Clock
   control mutates game state but is not a fort decision, so add a narrow,
   explicit, tested exception (for example a `clock` class of tool granted
   only to a role of a new `kind: system`), never a general loosening. The
   Overseer must **not** gain `resume`: its charter says never unpause. Token
   variable `MCP_ROLE_TOKEN_CONDUCTOR` (the existing scheme in `dfmcp/auth.py`).
6. **Tests** for everything testable offline: manifest resolution, the
   role-scoping exception (conductor may, overseer may not resume, advisors
   may not touch the clock), argument validation. Lua logic you cannot run
   offline: say so plainly, and write down the exact live checks the deploy
   stream should run.

## Touched surfaces (yours only)

`scripts/dfhack/df-overseer-clock.lua` (new; any other new
`scripts/dfhack/df-overseer-*.lua` you justify), `scripts/dfhack/TOOLS.yaml`,
`agents/conductor/` (new), `agents/ROSTER.yaml`, `dfmcp/roles.py`,
`dfmcp/auth.py` (only if needed), `dfmcp/tests/test_roles.py`, other new test
files you add, `infra/local.example.env`, this doc, its `handoffs/INDEX.md` row.

**Not yours** (other streams own them): `dfqueue/`, `dfmcp/queue_tools.py`,
`dfmcp/server.py`, `dfmcp/registry.py`, any `agents/*/` directory other than
`agents/conductor/`, `dfmcp/README.md` (put the README lines you would add in
your report instead).

## Hard lines

- No VM, no SSH, no deploy, no model call. No push.
- Do not write `Working.md`, `decisions/` or `memory/`.
- No em dashes in prose.
- **Commit after each milestone**, and extend this doc's Result section as you
  go; rate-limit deaths are routine and the next agent must be able to resume.

## Done when

Both suites pass (`python -m pytest` ambient; `dfmcp/tests` in
`.venv-dfmcp`) with the counts reported against the baseline (891 passed / 3
skipped; 537), and the Result section lists: what was built, what was verified
offline and how, what needs a live check (as exact commands), and the README
lines to add.

## Result

**DONE 2026-09-22, merged locally, not deployed.** Offline build, no VM, no
SSH, no deploy, no model call, no push. Commits on
`worktree-agent-a4324fee78b0ecbd5`:
`3441e28` "Game clock, quicksave, vitals tools and the conductor role".

### What was built

1. **`scripts/dfhack/df-overseer-clock.lua`** (new): `set-speed FPS`,
   `pause`, `resume`, `status`, `arm [HUNGER_CRITICAL THIRST_CRITICAL
   CHECK_INTERVAL_TICKS THREAT_CHECK_EVERY_N]`, `disarm`, `clear`.
   - `set-speed` writes `df.global.enabler.fps` and `fps_per_gfps` exactly
     as `hack/scripts/setfps.lua` does (read directly from the local
     Windows DFHack install, `C:\Program Files (x86)\Steam\...\DFHack`).
     Refuses outside `[1, 1000]` (my own sanity ceiling, not researched).
   - `pause`/`resume` use `dfhack.world.SetPauseState`/`ReadPauseState`
     (confirmed present, `hack/docs/docs/dev/Lua API.txt`). `resume`
     refuses with the latch detail while a tripwire is latched; no override
     argument exists, only `clear` then `resume`.
   - The tripwire watcher is registered via `repeat-util.lua`'s own
     `scheduleEvery`/`cancel`/`isScheduled` (required directly, the same
     mechanism `overseer-autosave`/`overseer-sampler` use through the
     `repeat` CLI wrapper), not the `repeat` command wrapper, so the check
     closure can capture `arm`'s own local config without a state file.
     Tripwires v1, exactly the handoff's three (not the design doc's
     fourth, see "Flags" below): a citizen death since the last check (a
     rolling `getCitizens(true)` id-set diff), hunger/thirst past critical
     (see sourcing below), and a hostile `df-overseer-threat.lua`'s
     `find_threats` admits by reachability, reqscript'd and run only every
     `THREAT_CHECK_EVERY_N`-th check (default 10) since it is the heavier
     read. On a trip: `SetPauseState(true)` plus a latch `{reason, tick,
     detail}` written to `dfhack-config/overseer-clock/tripwire_latch.json`
     via `json.encode_file`/`decode_file` (confirmed present in the
     bundled `hack/lua/json.lua`).
   - **Why a file, not a Lua global, for the latch**: read
     `hack/lua/dfhack.lua`'s `run_script_with_env` directly. DFHack caches
     one `env` table per script PATH across separate `dfhack-run`
     invocations (`scripts[file].env` persists; only the top-level chunk
     re-runs), so a bare global WOULD survive across CLI calls within one
     process, but would also wrongly survive a world unload/reload the way
     `df-overseer-sampler.lua`'s own header already warns about for exactly
     this reason. `arm` always clears the latch file first, so a fresh arm
     is a clean start; the scheduled check closure itself dies for free on
     world unload since `repeat-util.lua`'s own `onStateChange` handler
     clears its `repeating` table on `SC_WORLD_UNLOADED`.
   - **Why pausing needs no "already latched, stop checking" logic**: the
     watcher is scheduled in ticks, and ticks freeze while paused, so a trip
     naturally stops the schedule from firing again. If something bypasses
     `resume`'s guard (a human unpausing via the UI/VNC), ticks resume, the
     watcher fires again, and re-pauses if the condition still holds --
     documented as a deliberate defense in depth, not an oversight.
2. **`scripts/dfhack/df-overseer-fort.lua`** (new): `quicksave [CONFIRM_SLOT
   CONFIRM_PRIOR_MTIME]`. See "Flags" below for the one real design
   deviation this stream is making a deliberate call on.
3. **`scripts/dfhack/df-overseer-vitals.lua`** (new): `summary`. Returns
   `alive`, `dead_total` (+ the same undercount caveat
   `df-overseer-sampler.lua`'s own `fort/deaths` metric carries, copied not
   reqscript'd since that helper is a `local`), `worst_hunger_status`/
   `worst_thirst_status` as a CATEGORY, and `warning_count`. **Never
   returns a raw `hunger_timer`/`thirst_timer` integer** -- see "A
   knowledge-scope catch" below.
4. **`scripts/dfhack/TOOLS.yaml`**: nine new command entries across the
   three scripts, `live_deployed: false`, `verified: unverified`
   throughout, each `knowledge_scope`-tagged and reasoned in its own
   `notes`. Loads cleanly (`load_registry()` resolves all nine canonical
   ids: `clock.set-speed`, `clock.pause`, `clock.resume`, `clock.status`,
   `clock.arm`, `clock.disarm`, `clock.clear`, `fort.quicksave`,
   `vitals.summary`).
5. **`dfmcp/roles.py`**: `SYSTEM_CLASS_TOOL_IDS` (the seven mutating ids,
   `vitals.summary`/`clock.status` are reads and need no exception), a
   fixed explicit set (not a new `Tool` field, since `dfmcp/registry.py` is
   a different stream's file this same day and not in this stream's
   touched surfaces). `_load_role_permissions`'s Rule 2 now checks
   membership in that set FIRST: a role holding one of these seven ids must
   be `kind: system`, full stop, **with no sole_writer exception** -- this
   is what makes "the Overseer must never gain `clock.resume`" a load-time
   guarantee rather than a charter sentence a future `tools.yaml` edit
   could quietly contradict. Everything else about Rule 2 (advisors are
   read-only) is unchanged.
6. **`agents/conductor/`** (new): `role.md`, `tools.yaml` (reads:
   `clock.status`, `vitals.summary`, `overview.get`, `queue.pending`
   [already a native tool, `mutates=False`, `sole_writer_only=False`, no
   new plumbing needed]; writes: all seven `SYSTEM_CLASS_TOOL_IDS`),
   `model.yaml` (documents "no model call ever", since `dfmcp/roles.py`
   only checks the file exists, never its contents, for any `kind`).
7. **`agents/ROSTER.yaml`**: `conductor: enabled: true, dir: conductor,
   kind: system`.
8. **`infra/local.example.env`**: `MCP_ROLE_TOKEN_CONDUCTOR=` placeholder.
   `dfmcp/auth.py` needed **no code change** -- its `MCP_ROLE_TOKEN_<ROLE>`
   convention is already fully generic over any enabled role name, verified
   by reading it in full rather than assumed.
9. **`dfmcp/tests/test_roles.py`**: updated `test_real_roster_loads` (now
   asserts `conductor` is in the roster) and
   `test_no_advisor_holds_a_mutating_tool_by_any_route` (now
   `SYSTEM_CLASS_TOOL_IDS`-aware rather than blindly failing on the new
   role); six new tests: the conductor's exact write set pinned
   (`test_conductor_is_kind_system_and_holds_exactly_the_clock_writes`),
   the Overseer's non-grant pinned directly
   (`test_overseer_holds_no_system_class_tool_despite_being_sole_writer`),
   the advisors' non-grant
   (`test_advisors_hold_no_system_class_tool`), and three loader-level
   cases mirroring Rule 2's own test style: an advisor refused
   (`test_rule_system_class_tool_granted_to_a_non_system_role_refuses_to_load`),
   **the sole_writer refused too**
   (`test_rule_system_class_tool_granted_to_the_sole_writer_also_refuses_to_load`,
   the one test that most directly proves the "no carve-out" property), and
   the positive case
   (`test_rule_system_class_tool_granted_to_a_system_kind_role_loads_fine`).

### Verified offline, and how

- **`load_registry()` against the real, committed `TOOLS.yaml`** parses all
  nine new commands with no `RegistryError`; canonical ids, `effect` and
  `args` printed and checked by hand (`python -c "from dfmcp.registry
  import load_registry; ..."`, output included in this stream's own
  working log, reproducible from the repo alone).
- **`load_roster()` against the real, committed `agents/`** loads with no
  `RoleValidationError`, proving the new `SYSTEM_CLASS_TOOL_IDS` exception
  and the conductor's own `tools.yaml` are internally consistent (every id
  it references exists in the registry; `queue.pending` resolves because
  every test fixture that loads the real roster already merges
  `queue_tools.NATIVE_TOOLS`, checked directly against
  `dfmcp/tests/test_roles.py`, `test_auth.py`, `test_doctrine_tools.py`,
  `test_series_tools.py`, `test_server.py`, `test_tools.py`,
  `test_workjob_tool.py` and `dfmcp/server.py` itself, all six/seven read
  before assuming it).
- **`dfmcp/tests/test_auth.py`** (not edited, not in this stream's
  touched surfaces) still passes: it asserts no fixed role SET, only
  token-resolution behaviour, so adding `conductor` to the real roster
  does not touch its assertions.
- **Full ambient suite**: `python -m pytest -q` -> **897 passed, 3
  skipped** (baseline 891/3; +6, exactly the six new `test_roles.py`
  cases, no regressions elsewhere).
- **`dfmcp/tests` in a freshly created `.venv-dfmcp`**
  (`python -m venv --system-site-packages .venv-dfmcp`, gitignored, did not
  exist in this fresh worktree; `pip install -r dfmcp/requirements.txt`,
  the documented `fastmcp` ambient-conflict warning appeared and is
  harmless per `docs/TRAPS.md`): `./.venv-dfmcp/Scripts/python -m pytest
  dfmcp/tests -q` -> **543 passed** (baseline 537; +6, the same six).
- **Lua was NOT executed or syntax-checked.** No standalone `lua`/`luac`
  binary exists on this workstation (checked: `where lua`/`where luac`
  both empty), and running the real DF+DFHack process locally to exercise
  it was judged out of scope for an offline stream that explicitly cannot
  touch a VM either. Every Lua API call used
  (`dfhack.world.ReadPauseState`/`SetPauseState`,
  `dfhack.filesystem.mtime`/`isdir`/`mkdir_recursive`, `dfhack.getSavePath`,
  `df.global.enabler.fps`/`gfps`/`fps_per_gfps`, `repeat-util`'s
  `scheduleEvery`/`cancel`/`isScheduled`, `json.encode_file`/`decode_file`)
  was confirmed to exist by reading its source or doc directly on the
  local Windows DFHack install (`C:\Program Files (x86)\Steam\steamapps\
  common\DFHack`, version 53.16-r1.1, the same version the VM runs per
  `memory/dfhack-environment.md`), not recalled from memory or assumed
  from the API doc's prose alone.

### A knowledge-scope catch worth naming explicitly

Re-reading `research/2026-09-16-food-clock-and-farm-lead-time.md` (asked of
this stream by the "Read first" list only indirectly, via
`docs/AGENT-ARCHITECTURE.md`; I read it in full because the tripwire and
`vitals.summary` both touch hunger/thirst) turned up its own bottom line:
**a raw `hunger_timer`/`thirst_timer` integer is "diagnostic-only -- not
something any vanilla screen shows a player"**, only the derived
flash-equivalent category ("Hungry"/"Starving", "Thirsty"/"Dehydrated") is
legitimately player-visible. My first draft of `vitals.summary` would have
returned the raw timer for the worst citizen. Fixed before committing:
both `vitals.summary` and the tripwire's own hunger/thirst latch `detail`
now report only the derived status category, never the tick integer, and
both files' `knowledge_scope` is `player_derivable` (an internal read
producing a safe, bounded, player-legal output) rather than
`player_visible`, with the reasoning written into each file's own header.
Flagging this because it is exactly the kind of mistake that would have
shipped silently without deliberately re-reading a research doc the
handoff only cited in passing.

### Exact live checks the deploy stream should run

None of the nine commands above have been run against a live fort. In
rough dependency order, fort paused throughout, quicksave first per
`docs/TRAPS.md`:

1. `df-overseer-clock status` -- confirm it returns without error and
   `paused`/`fps`/tick fields look sane before touching anything else.
2. `df-overseer-clock set-speed 10` then `set-speed 100` -- confirm
   `df.global.enabler.fps` actually changes (read it back independently,
   not just trust the tool's own echoed `new_fps`) and that `fps_per_gfps`
   does not error if `gfps` is ever 0.
3. `df-overseer-clock pause` / `resume` (fort not latched) -- confirm
   `ReadPauseState()` flips both ways and the fort visibly freezes/resumes.
4. `df-overseer-clock arm` with short-ish test thresholds (e.g. a
   `check_interval_ticks` low enough to observe within a supervised
   session) -- confirm `repeat --list` (or `repeatUtil.isScheduled` via
   `status`) shows `overseer-tripwire` registered, and that an UNPAUSED,
   supervised run for a few thousand ticks does NOT spuriously trip (no
   citizen near a critical threshold on Uniboslan today, per the
   2026-09-21 status in `Working.md`) -- a true negative control.
5. **The one condition genuinely testable live without waiting on a real
   crisis**: temporarily arm with a deliberately low `hunger_critical` or
   `thirst_critical` (below some citizen's current live timer value, read
   first) and confirm it trips within one `check_interval_ticks` window:
   fort pauses, `status` shows the latch with the right `reason`/`detail`,
   `resume` refuses citing the latch, `clear` then `resume` succeeds. This
   is the single most important live check in this list, since it
   exercises the exact mechanism `docs/AGENT-LOOP.md` ss3 depends on.
6. **The threat-tripwire path** needs a reachable hostile on the map,
   which may not be available on demand; if none is, say so rather than
   skip silently, and note the gap.
7. `df-overseer-fort quicksave` (no args) -- confirm `predicted_slot` names
   a real `autosave N` directory and `predicted_slot_prior_mtime` matches
   what `dfhack.filesystem.mtime` reports for that slot's `world.sav`
   independently, THEN wait (spaced-out separate calls, per this file's own
   header, never a tight loop) and confirm `quicksave "autosave N" PRIOR`
   eventually reports `confirmed: true` -- this is the path most likely to
   need a fix, since `save_root()`'s path-splitting logic
   (`dfhack.getSavePath()` minus its last segment) is the one piece of this
   stream with no live filesystem to check it against.
8. `df-overseer-vitals summary` -- confirm the shape and that
   `worst_hunger_status`/`worst_thirst_status` match what a player would
   actually see (cross-check one citizen's status icon in-game/VNC against
   the category this tool reports for them).
9. Role/token wiring: once a real `MCP_ROLE_TOKEN_CONDUCTOR` is minted and
   pasted into the VM's `.env`, confirm `dfmcp-server` starts clean and a
   client authenticating with that token gets exactly the conductor's nine
   allowed ids (four reads including `queue.pending`, seven writes) and
   nothing else -- and confirm a client authenticating as `overseer` still
   gets a "not on this role's allowlist" refusal for `clock.resume`.

### README lines owed (dfmcp/README.md is not this stream's file)

- Under whatever section lists roles/kinds: `kind: system` is a new,
  third `RolePermissions.kind` value (existing values were `"actor"` and
  `"advisor"`, per `roles.py`'s own docstring on the field) -- a role of
  this kind is code, never a model, and may hold `SYSTEM_CLASS_TOOL_IDS`
  even though it is not the sole_writer.
- Under the "strict validation rules" list (the doc that Rule 2's test
  names cite, e.g. "Rule 1", "Rule 6"): document the `SYSTEM_CLASS_TOOL_IDS`
  check as its own rule (it sits inside Rule 2's code but is logically
  independent: opposite shape, no sole_writer exception), so a future
  reader of `roles.py` via the README does not miss it the way a diff-only
  read might.
- A one-line mention that `MCP_ROLE_TOKEN_CONDUCTOR` exists and, unlike
  every other role's token, must never be handed to an agent process, only
  to the conductor service itself.

### Flags -- things in the design worth the user's attention

1. **`fort.quicksave` does not confirm inline**, contrary to the handoff's
   literal "reports the slot written, confirmed by the slot's mtime
   changing". This is a deliberate call, not an oversight: this project's
   own already-established facts (`docs/AGENT-ARCHITECTURE.md` ss6's
   suspend-lock finding, plus the up-to-90-second async save latency
   `research/2026-09-11-quicksave-silent-noop.md` measured) combine into a
   real self-deadlock risk if a script busy-waits for the save inside one
   call: the wait would itself hold the exact lock the pending render pass
   needs to fire. I designed around it (fire-and-report-predicted-slot,
   plus a cheap `confirm`-mode call the caller re-issues later, spaced
   out) rather than build the literal blocking version. If this reasoning
   is wrong, or the tradeoff should go the other way, that is a design
   call for the user, not something I felt entitled to silently overrule
   the handoff on without flagging loudly -- which this is.
2. **`docs/AGENT-LOOP.md` ss3 lists four v1 tripwires (death, hunger/thirst,
   hostile, "a new announcement of an alert class"); the handoff's own arm
   bullet lists only three (no announcement-class tripwire).** I built
   exactly the handoff's three, treating the handoff as the narrower,
   authoritative build spec for this stream over the design doc it
   summarizes. Worth reconciling one document into the other; I did not
   edit `docs/AGENT-LOOP.md` since it is not in this stream's touched
   surfaces and no other stream lists it as theirs either, as far as I
   read.
3. **A naming mismatch**: `docs/AGENT-LOOP.md` item 2 writes `clock.set_speed`
   (underscore); the handoff's own build spec (item 1) writes `set-speed`
   (hyphen), and the registry's canonical-id scheme takes the command
   signature's leading verb literally, so the real id is `clock.set-speed`.
   I followed the handoff (the more specific, operative spec) and did not
   edit the design doc. Worth a one-line fix there so a future reader does
   not go looking for a tool that does not exist under that name.
4. **The latch-file staleness gap across a world unload while still armed
   with nobody calling arm/disarm/clear across the boundary** (named in
   this file's own header) is real but judged acceptable for v1: `arm`
   always starts clean, and the deploy/conductor-service stream can close
   it fully later (e.g. an `onStateChange` handler) if it turns out to
   matter in practice.
5. **`vitals.summary`'s "O(1) in fort size"** (the handoff's own phrase) is
   read here as "cheap and bounded, unlike a map sweep", not literally
   population-independent -- a literal O(1) read of "worst hunger across
   all citizens" is not achievable honestly without a pre-aggregated cache
   that does not exist anywhere in this project. Said plainly in the
   TOOLS.yaml notes rather than silently reinterpreted.

### Not done / out of scope for this stream

- No VM contact of any kind; nothing above is `live_deployed: true` or has
  a `verified` date.
- The conductor SERVICE itself (`docs/AGENT-LOOP.md` item 3, Python,
  triage, the cycle loop) is explicitly a later, separate stream.
- Real thresholds for a live fort (Uniboslan's actual citizens' current
  hunger/thirst timers) were not read, since that needs the VM.
