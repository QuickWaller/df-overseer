# DFHack Capability Checks for the Multi-Agent Architecture

Date: 2026-09-12
Scope: settle six DFHack capabilities `docs/AGENT-ARCHITECTURE.md` (2026-09-12) rests on but nobody had verified —
runtime frame-rate control (§6, throttle), in-game overlay (§8, public reasoning stream), `dfhack-run` concurrency
(§7/§13, write-authority partitioning), quickfort/manager-order priority (§4's `suggested_priority` field and §7's
Quartermaster carve-out), `eventful` coverage for the closed wake-event vocabulary (§4), and `dfhack.persistent`
under concurrent writes (§7, "shared mutable state behind the landmark system").
Status: **desk research only, as instructed.** No DFHack command was executed against VM 103 or any live DF
process; no SSH session was opened. Everything below comes from (a) the local Windows Steam install
(`C:\Program Files (x86)\Steam\steamapps\common\DFHack`, confirmed **DFHack 53.16-r1.1** per
`memory/dfhack-environment.md`, matching the VM's own documented version — the VM was not independently
re-checked this session, see §7 below), and (b) two fresh, version-pinned clones read directly, not from memory or
GitHub's code search (which the 2026-09-10 site-finder research already found unreliable for this org's repos):
`github.com/DFHack/dfhack` checked out at tag `53.16-r1.1` (commit `b638b59d`), and its pinned `library/xml`
submodule (`github.com/DFHack/df-structures`, commit `1dd01aad`, "Changelog for 53.16-r1") — both exact-version
matches to the installed build, not "current master." Where a live check would be the only way to close a
remaining gap, that is stated plainly with the exact command, per this task's constraint, and not executed.

---

## 0. Answers, up front

| # | Question | Answer | Confidence |
|---|---|---|---|
| 1 | Runtime FPS cap | **Yes.** `df.global.enabler.fps` (sim/"computational" cap) and `df.global.enabler.gfps` (render cap) are plain runtime fields; `setfps <n>` sets the former directly. Persists in-process across map load (nothing resets it); does **not** survive a DFHack process restart. | High (source-confirmed); persistence claim is inference from absence of reset code |
| 2 | In-game overlay | **Yes**, the `overlay` framework (present, not tagged `unavailable`). A Lua widget's `render`/`overlay_onupdate` runs on the game's own render pass regardless of human input — the same mechanism that makes `quicksave` asynchronous. Mechanically headless-drivable; never live-tested in this project's own Xvfb/VNC pipeline. | High on the mechanism; untested in this project's specific pipeline |
| 3 | `dfhack-run` concurrency | **Safe, not racy, but not FIFO either.** Every command-issuing thread (each `dfhack-run` connection is its own OS thread) must acquire `Core::CoreSuspendMutex` — a `std::recursive_timed_mutex` — before touching game state; DF's own sim thread cooperatively yields it once per tick via `CoreWakeup.wait()`. Concurrent writers are mechanically possible and memory-safe. They are **serialized, unordered/unfair, and this exact mechanism is the confirmed cause of the already-documented quicksave 45-80s delay.** | High — read the actual synchronization primitive, exact version match |
| 4 | Priorities | quickfort: **yes**, `-p`/`--priority <1-7>` on `#dig` blueprints, confirmed in the shipped doc. Manager work orders: **no numeric priority field exists** (confirmed via the `manager_order` struct). Priority is realized purely as **position in `world.manager_orders.all`**, an ordered vector; `orders sort` reorders it by frequency, and the `workorder` script's `create_orders()` (a reusable Lua module) programmatically creates orders and appends them, confirmed from its own source. | High, direct struct/source read |
| 5 | Event coverage | Of the 8 wake events asked about: **job completion** — real, dedicated event (`onJobCompleted`). **Cave-in, migrant wave, caravan arrival, season change** — real signal via the generic `onReport` event filtered by `announcement_type` (`CAVE_COLLAPSE`, `MIGRANT_ARRIVAL`, `CARAVAN_ARRIVAL`, `SEASON_{SPRING,SUMMER,AUTUMN,WINTER,WET,DRY}`), all confirmed enabled-by-default in the live install's own `announcements.txt`. **Unit badly wounded** — a real event (`onUnitAttack`) hands back a `df.unit_wound*` directly, but "badly" is caller logic, not the event's own judgment. **Hostile appearance** — only a narrow real signal (`onInvasion`, fires only for actual siege/invasion-flagged events); does **not** cover ambushes, thieves, or ordinary hostile wildlife, consistent with this project's own prior finding that `unit-status hostile` missed a kea attack. **Water/magma breach** — **no signal of any kind found**, event or announcement; must be polled. | High for what exists; the water/magma breach negative and the invasion-is-narrow findings are the two that most change the design |
| 6 | `dfhack.persistent` | **No dedicated internal lock — safety is entirely borrowed from the same `CoreSuspender` convention as everything else** (every mutating call is individually wrapped in its own fresh suspend). Real hard limit: **exactly 7 integer slots per entry** (`NumInts = 7`, compile-time constant) plus one string value of no source-enforced length limit. Real performance-shape finding: `Persistence::Internal::save()` rewrites **the entire JSON file for a given entity bucket from scratch on every save**, not incrementally — O(entries in that bucket) per save, not O(changed entries). | High, direct source read |

---

## 1. Runtime frame-rate control

**Primary source: `hack/scripts/setfps.lua` (installed, matches shipped doc verbatim) and `hack/scripts/gui/settings-manager.lua`.**

`setfps.lua`'s entire body:

```lua
df.global.enabler.fps = capnum
df.global.enabler.fps_per_gfps = df.global.enabler.fps / df.global.enabler.gfps
```

This directly confirms the mechanism `memory/dfhack-environment.md` already documented for `init.txt` (`FPS_CAP` vs
`G_FPS_CAP`) is the same pair of live fields, not a separate concept: `settings-manager.lua`'s own settings table
(read directly) labels them explicitly —

```lua
{id = 'FPS_CAP', type = 'int', desc = 'Computational FPS cap', min = 1,
    in_game = 'df.global.enabler.fps'},
{id = 'G_FPS_CAP', type = 'int', desc = 'Graphical FPS cap', min = 1,
    in_game = 'df.global.enabler.gfps'},
```

and its `commit_edit` handler calls `set_variable(setting.in_game, value)` directly on the live field the instant
you edit it in the in-game control panel — **not** through a write to `init.txt` (that only happens if you
separately open the "init.txt" file-editor screen and hit save; the two are different code paths in the same
tool). So there are two independent, source-confirmed ways to change the sim FPS cap at runtime: the one-shot
`setfps <n>` console/`dfhack-run` command, or `gui/settings-manager`'s live editor. Both write the same field.

**Persistence across save/load**: `df.global.enabler` is a plain engine-global struct, not part of the world/save
data structures (`df::world`, `df::plotinfo`, etc.) — it is unaffiliated with any specific fort or save file. A
repo-wide grep of the cloned DFHack source for `enabler.fps`/`enabler.gfps` found exactly three hits: `setfps.lua`,
`settings-manager.lua`'s editor, and one CI test reader — **nothing else in the shipped DFHack source ever
resets it**, on `SC_WORLD_LOADED`, `SC_MAP_LOADED`, or anywhere else searched. This is not a positive proof (DF's
own closed-source engine could theoretically reset it internally on load, and that code is not available to read),
but it is a real, source-based basis for "very likely persists within the same running process across loading a
different save," downgraded from "confirmed" to **inferred, moderate-high confidence** for exactly that reason. It
does **not** survive a full DFHack/DF process restart, since restart re-reads `prefs/init.txt` from scratch and no
in-memory field survives a process exit.

**Relation to `timestream`** (also listed as "available" in `memory/dfhack-environment.md`): `timestream`'s own
shipped doc, read directly, describes a materially different mechanism — it does not change the FPS cap at all,
it changes how much *simulated game time* advances per real frame ("more happens per step, so DF has to simulate
fewer steps"), with a hard documented ceiling ("cannot advance more than 9 ticks at a time") and an explicit list
of things it does **not** speed up (world-map army movement, liquid movement/evaporation). Its own config is
confirmed to persist via `dfhack.persistent.getSiteData` (read directly in `hack/lua/plugins/timestream.lua`),
i.e. it is fort-scoped persistent state, unlike the plain `enabler.fps` field. **For "buy agent thinking time
without freezing the display," `setfps` is the more direct primitive** — it slows the actual simulation and
rendering rate the viewer sees, which is what §6 of the architecture doc wants ("Throttle... Lower the frame
cap... Thinking time needed, freeze not warranted"). `timestream` solves the opposite problem (a mature fort
feels slow to a human watching it) and is not a substitute.

**Not independently executed**: whether a value set via `setfps` while a save is loaded is still in effect after
that save is closed and a *different* save is loaded in the same running process. Live command that would settle
this cleanly, stated so it can be approved separately: `dfhack-run lua "df.global.enabler.fps=5"`, then
`load-save <other save>` or a fresh embark, then `dfhack-run lua "print(df.global.enabler.fps)"`.

---

## 2. In-game text overlay

**Primary source: `hack/docs/docs/dev/overlay-dev-guide.txt` and `hack/docs/docs/tools/overlay.txt` (both shipped,
read in full), corroborated by `hack/lua/plugins/overlay.lua` and `hack/plugins/overlay.plug.dll` being present.**

The `overlay` plugin's own doc carries no `unavailable` tag (`Tags: dfhack | interface` only) and is absent from
`memory/dfhack-environment.md`'s "Unavailable in 53.16" list — this is a genuinely new addition to that file's
"available" roster, worth folding back in.

The dev guide is explicit and detailed about the mechanism relevant here:

- A widget is a plain Lua class (`defclass(MyWidget, overlay.OverlayWidget)`) registered via a global
  `OVERLAY_WIDGETS = {name = MyWidget}` table. Registration, enabling, and positioning are all driven by ordinary
  DFHack commands (`overlay enable <name>`, or `default_enabled=true` on the widget class) — **nothing in the
  registration or enable path requires a human at the keyboard**, and the doc explicitly frames scripts/plugins as
  the intended author, not a player clicking a UI.
- Rendering happens via `onRenderFrame`/`onRenderBody`, called "when the viewscreen that the widget is associated
  with does its usual input and render processing" — i.e. on the game's own render pass for whichever
  `viewscreens` the widget declares (e.g. `'dwarfmode'` for the fort-mode main map). This is **the same
  render-loop-gated mechanism** `research/2026-09-11-quicksave-silent-noop.md` already found and confirmed live
  for `QuicksaveOverlay` — a DFHack Lua screen/widget's actual body only executes on a subsequent game render
  pass, not synchronously with whatever triggered it. Since that render pass happens continuously as long as the
  associated viewscreen is on top of the stack, **regardless of whether a human is providing input**, an overlay
  attached to `'dwarfmode'` will draw every frame the fort-mode screen is showing, headlessly, by the same logic
  already load-bearing elsewhere in this project. This is inference by direct analogy to an already-verified
  mechanism, not a fresh independent proof, but the analogy is exact (same render-callback architecture).
- Content updates are driven by `overlay_onupdate()`, throttled by `overlay_onupdate_max_freq_seconds` (default 5s,
  settable to 0 for immediate). The worked example in the doc (`MessageWidget`) is literally "displays a message
  at its position... retrieved from the host script or plugin," which is exactly a status-banner use case.
- Performance guardrail, stated in the doc as a real DFHack-wide SLO, not a suggestion: "no more than 10%
  performance impact during unpaused gameplay with all overlays and background tools enabled... a single overlay
  should seek to take up no more than a fraction of 1%."

**Not independently executed**: whether an overlay widget actually appears, legibly, in this project's specific
headless rendering pipeline (Xvfb framebuffer captured for the public VNC/stream feed on VM 103). The mechanism
being real and headless-safe in principle is not the same claim as "it will look right on the existing stream." A
live smoke test (not run here): register a trivial `OVERLAY_WIDGETS` script with a static-text `widgets.Label`,
`viewscreens={'dwarfmode'}`, `default_enabled=true`, deploy it to VM 103's script path, `overlay enable
<name>`, and check a captured stream frame.

---

## 3. Concurrency of `dfhack-run`

**This is the load-bearing one, and it is answered from the actual C++ synchronization primitive, read directly,
at the exact matching version tag.**

**The RPC server is genuinely multi-threaded at the OS level.** `library/RemoteServer.cpp`, read directly:
the server itself runs on a dedicated detached thread (`std::thread{&ServerMainImpl::threadFn, ...}.detach()`,
line 479), and **every accepted client connection spawns its own separate `std::thread`** (line 252). So two
concurrent `dfhack-run` invocations really are two different OS threads, not serialized at the socket-accept
level, contrary to what a naive "single console" mental model might assume.

**`RunCommand` (the RPC method `dfhack-run` actually calls) is registered `SF_DONT_SUSPEND`**, confirmed in
`library/RemoteTools.cpp`:

```cpp
addMethod("RunCommand", &CoreService::RunCommand, SF_DONT_SUSPEND);
```

which matters because the generic RPC dispatch loop (`RemoteServer.cpp`, read directly) wraps *every other*
RPC method automatically in a scoped suspend guard, and skips it only for methods carrying that flag:

```cpp
if (fn->flags & SF_DONT_SUSPEND) {
    res = fn->execute(stream);
} else {
    CoreSuspender suspend;
    res = fn->execute(stream);
}
```

So `RunCommand` itself does not wait to acquire the suspend lock before doing preliminary dispatch work (parsing
the command name, `help`/`tags`/plugin lookup, etc.) — the code comment explains why: *"disable try_autocomplete
... this remote server connection could be the last chance for recovering from stuck Lua scripts,"* i.e. so
`kill-lua` can still be dispatched even if some other script is stuck holding the suspend lock.

**But the actual point where a command touches game state still acquires a suspend, just one level deeper**,
confirmed by reading both real execution paths:

- Plugin commands: `library/PluginManager.cpp`, immediately before calling the command's function —
  `CoreSuspender suspend; cr = cmdIt->function(out, parameters);`
- Lua scripts (the path `dfhack-run somescript.lua` and interactive console commands both use):
  `library/LuaTools.cpp`'s `RunCoreQueryLoop`, which wraps both the initial script body execution and each
  subsequent interactive iteration in its own `CoreSuspender`.

**The actual lock, and how DF's own simulation thread cooperates with it** — `library/include/Core.h`, read in
full, including its own developer comment block (quoted verbatim because it is the clearest primary-source
description of the mechanism available):

> "Other thread request core suspend by atomic incrementation of `Core::toolCount` and then locking
> `Core::CoreSuspendMutex`... `Core::Update()` makes sure that queued tools are run when it calls
> `Core::CoreWakeup::wait`. The wait keeps `Core::CoreSuspendMutex` unlocked and waits until `Core::toolCount`
> is reduced back to zero."

and `library/Core.cpp`'s actual `Core::Update()` (the function DF's own hooked render/simulation loop calls every
tick — comment: "should always be from simulation thread!"):

```cpp
doUpdate(out);
// Let all commands run that require CoreSuspender
CoreWakeup.wait(MainThread::suspend(),
        [this]() -> bool {return this->toolCount.load() == 0;});
```

`CoreSuspendMutex` is a `std::recursive_timed_mutex` held by the simulation thread by default (`Core::Init` locks
it for the thread's whole lifetime); any other thread wanting to touch DF memory safely increments `toolCount` and
blocks on that mutex; the sim thread, once it finishes its own per-tick work, calls `CoreWakeup.wait(...)`, which
releases the mutex and parks the sim thread until every currently-waiting suspender has finished and `toolCount`
is back to zero, then reclaims the lock and proceeds to the next tick.

**What this settles, plainly**:

- **Concurrent `dfhack-run` calls are not racy in the memory-corruption sense.** Every actual touch of game state
  goes through this one mutex, one way or another, regardless of which thread issued it or how many are pending.
- **The mechanism is a lock with a cooperative hand-off, not a FIFO command queue.** There is no queue data
  structure holding pending commands in order; `std::recursive_timed_mutex::lock()` gives no fairness/ordering
  guarantee, so which of several simultaneously-waiting writers gets serviced next is not deterministic or
  priority-orderable from outside.
- **The window for suspension only opens once per simulation tick** (after `doUpdate()` finishes), which is a
  real, direct, source-confirmed explanation — upgraded from "plausible, not source-verified" to **confirmed** —
  for the exact multi-second, highly variable delay `research/2026-09-11-quicksave-silent-noop.md` measured live
  (45-80s in one case) between issuing a command and its effect landing. That investigation flagged the mechanism
  as "the most parsimonious, evidence-consistent... but not independently confirmed" explanation; this session's
  source read confirms it directly. Worth folding back into that report's own confidence framing.
- **For the architecture doc's §7/§13 question ("is `dfhack-run` concurrency even safe")**: yes, mechanically.
  Multiple independent writers issuing commands concurrently will not corrupt fortress state. What they will not
  get is throughput, ordering guarantees, or low latency under contention — each writer's actual work is fully
  serialized against every other writer *and* against the simulation tick itself, and the more of them there are,
  the longer each individually waits its turn (directly consistent with the already-observed variable multi-second
  delays). This answers the "mechanically possible" half of §7's carving question; it does not answer the
  separate throughput question (`research/2026-09-12-write-conflict-matrix.md`'s territory), which needs measured
  cycle times, not source reading.

No live execution was needed to settle this question — the mechanism is definitive from source at the exact
matching version. (The quicksave investigation's own live reproduction already stands as indirect empirical
corroboration of the delay this predicts.)

---

## 4. Priorities

### quickfort dig-designation priority: confirmed present

`hack/docs/docs/tools/quickfort.txt`, read directly:

> `"-p", "--priority <num>"` — Set the priority to the given number (1-7) for tiles designated by the `#dig`
> blueprint that you are applying... If not specified, defaults to `4`.

Scoped explicitly to `#dig` blueprints (not `#build`, `#place`, etc.). This is a real, usable CLI/API surface for
exactly the field the architecture doc's proposal schema names (`<suggested_priority>4</suggested_priority> <!--
DF 1-7 -->`).

### Manager work-order priority: no numeric field — position in an ordered list is the mechanism

Read directly from `df.workquota.xml` (df-structures, pinned commit `1dd01aad`, "Changelog for 53.16-r1" — exact
match), the full `manager_order` struct (DFHack name; engine name `workquotast`):

```xml
<struct-type type-name='manager_order' original-name='workquotast'>
    <int32_t name='id' .../>
    <enum ... name='job_type' .../>  <enum ... name='item_type' .../>  <int16_t name='item_subtype' .../>
    <stl-string name="reaction_name" .../>
    <int16_t name="mat_type" .../>  <int32_t name="mat_index" .../>
    <compound type-name='job_spec_flags' name='specflag'/>  <compound type-name='job_spec_data' name='specdata'/>
    <bitfield type-name='job_material_category' name="material_category"/>
    <compound name='art_spec'>...</compound>
    <int16_t name="amount_left"/>  <int16_t name="amount_total"/>
    <bitfield type-name='manager_order_status' name="status"/>
    <enum type-name='workquota_frequency_type' name="frequency"/>
    <int32_t name="finished_year"/>  <int32_t name="finished_year_tick"/>
    <int32_t name="workshop_id"/>  <int32_t name="max_workshops"/>
    <stl-vector pointer-type='manager_order_condition_item' name="item_conditions"/>
    <stl-vector pointer-type='manager_order_condition_order' name='order_conditions'/>
    <pointer type-name='job_reqst' name='items'/>
</struct-type>
```

There is no field resembling a numeric priority anywhere in this struct. The container,
`workquota_handlerst.all` (exposed to Lua as `world.manager_orders.all`), is a plain **ordered `stl-vector`** —
confirming that in vanilla DF's own manager screen, "priority" is realized as **queue position**, not a value.
This is exactly what the `orders sort` tool (its doc, read directly) manipulates: *"Sorts current manager orders
by repeat frequency so repeating orders don't prevent one-time orders from ever being completed... one-time
orders first, then yearly, seasonally, monthly, and finally, daily."* Reordering the list is the priority
mechanism as DF implements it.

### Programmatic creation and ordering: confirmed, via `workorder.lua`, read directly

`hack/scripts/workorder.lua` is a real, present, reusable Lua module (`--@ module=true`) whose `create_orders()`
function is annotated in its own source as *"creates a df.manager_order from its definition... translated
orders.cpp to Lua"* — i.e. it is DFHack's own blessed reimplementation of the exact struct-construction logic the
game's manager screen itself uses, not an ad hoc workaround. Its actual insertion, read directly:

```lua
local order = df.manager_order:new()
-- ... field population from a JSON/table spec ...
world.manager_orders.all:insert('#', order)
```

`insert('#', order)` appends to the end of the vector (new orders land at the back of the queue by default). The
`orders` tool itself is for managing/importing/exporting/sorting **existing** orders (including a library of
pre-baked order sets); it is `workorder` that creates new ones from a job-type name or JSON spec, and does so as
a plain, callable Lua function (`reqscript('workorder').create_orders(...)`) a specialist tool could call directly
rather than shelling out to the CLI form. Reordering beyond "append at the end" is not exposed as a named
command by either tool, but is mechanically trivial given `world.manager_orders.all` is a plain exposed vector
supporting `:insert(idx, order)`/`:erase(idx)` at arbitrary positions — the same idiom `workorder.lua` itself
already uses for insertion and removal.

**Relevance to §7's Quartermaster carve-out**: the architecture doc already flags "the manager work-order queue, a
single ordered list where order is the semantics" as a crossed dependency. This research confirms that framing
exactly — it is not a metaphor, the underlying DF struct literally has no priority field, only list position, so
any future "set priority" tool would have to be built as list reordering, and two independent writers reordering
that one list concurrently is precisely the kind of shared-ordered-list contention §7 already named as a reason
not to hand out multiple general writers.

---

## 5. Event coverage

**Primary source: `library/include/modules/EventManager.h`'s `EventType` enum, `library/modules/EventManager.cpp`'s
actual trigger conditions for each handler, `plugins/eventful.cpp`'s Lua-facing bindings, and `df.g_src.basics.xml`'s
`announcement_type` enum — all read directly at the matching version — cross-checked against the live install's
own `data/init/announcements.txt` to confirm which announcement categories are actually enabled by default.**

The full, real `EventManager::EventType` enum (`EventManager.h`, verbatim):

```
TICK, JOB_INITIATED, JOB_STARTED, JOB_COMPLETED, UNIT_NEW_ACTIVE, UNIT_DEATH, ITEM_CREATED, BUILDING,
CONSTRUCTION, SYNDROME, INVASION, INVENTORY_CHANGE, REPORT, UNIT_ATTACK, UNLOAD, INTERACTION, EVENT_MAX
```

Every one of these except `TICK` is exposed to Lua as a named `eventful.onXxx` event (confirmed by reading
`plugins/eventful.cpp`'s `DFHACK_PLUGIN_LUA_EVENTS` table directly — `onJobCompleted`, `onUnitNewActive`,
`onUnitDeath`, `onInvasion`, `onReport`, `onUnitAttack`, etc. are all real, present bindings, not aspirational).
`TICK` is excluded from the generic Lua `enableEvent()` registration path by an explicit runtime check
(`evType != EventManager::EventType::TICK`) — it is handled elsewhere (repeat-scheduling), not via this mechanism.

Mapping the eight requested wake signals against what actually fires, per-type trigger condition read directly
from `EventManager.cpp`:

| Wake signal | Real event? | Evidence |
|---|---|---|
| **Job completion** | **Yes, dedicated.** `JOB_COMPLETED` → `onJobCompleted(job)`. | Direct, unambiguous match. |
| **Cave-in** | **Yes, via `REPORT` + type filter.** `announcement_type.CAVE_COLLAPSE` exists (`df.g_src.basics.xml`) and is confirmed **enabled by default** in the live install's own `data/init/announcements.txt`: `[CAVE_COLLAPSE:A_D:D_D:ALERT]`. | `manageReportEvent()` fires `onReport(report_id)` for every new report; consumer filters by `df.report.find(id).type`. |
| **Migrant wave arrival** | **Yes, via `REPORT` + type filter** (best fit for "wave" semantics — one report per wave). `MIGRANT_ARRIVAL`/`MIGRANT_ARRIVAL_NAMED` confirmed present and default-enabled (`[MIGRANT_ARRIVAL:A_D:D_D]`). `UNIT_NEW_ACTIVE` also fires, but per-unit, not per-wave — a consumer using it would have to debounce/batch itself. | Both mechanisms real; `REPORT` is the cleaner match for "wave." |
| **Caravan arrival** | **Yes, via `REPORT` + type filter.** `CARAVAN_ARRIVAL` (and `FIRST_CARAVAN_ARRIVAL`, since v0.50.01) confirmed present and default-enabled: `[CARAVAN_ARRIVAL:A_D:D_D:ALERT]`. | Same mechanism as above. |
| **Season change** | **Yes, via `REPORT` + type filter.** `SEASON_SPRING/SUMMER/AUTUMN/WINTER` (plus `SEASON_WET/DRY` for non-temperate biomes) confirmed present and default-enabled (`[SEASON_SPRING:A_D:D_D]` etc.). | Same mechanism; no dedicated `EventType` of its own. |
| **Unit badly wounded** | **Partial — a real event exists but doesn't itself judge severity.** `UNIT_ATTACK` fires on `COMBAT_STRIKE_DETAILS` reports and hands the Lua callback `(attacker_id, defender_id, wound)` — a real `df.unit_wound*`, not just text. "Badly" is caller logic over that struct's fields (not independently surveyed this session — the wound object's severity/pain fields exist but their exact semantics weren't read). | `manageUnitAttackEvent()`, `getWound()`, read directly. Real signal, needs downstream interpretation. |
| **Hostile appearance** | **Narrow — real, but covers only actual invasions, not "any hostile."** `INVASION` fires strictly when `df::global::plotinfo->invasions.next_id` increments — DF's own siege/invasion-registration mechanic. It does **not** fire for an ambush, a lone thief, a sneaking creature, or ordinary hostile wildlife (a kea, a giant cave spider) turning aggressive. | `manageInvasionEvent()`, read directly. This is independent, source-level corroboration of the project's own prior finding (`decisions/DECISIONS.md` 2026-09-11) that `unit-status hostile` missed a real kea attack — the miss is not just that one polling signal being unreliable, the *event* layer has the same blind spot by construction. |
| **Water or magma breach** | **No signal of any kind found.** No `EventType` matches ("BUILDING"/"CONSTRUCTION" are about buildings/constructions being created or destroyed, not liquid movement). No `announcement_type` item matches either — a targeted grep of the full enum for `FLOOD`, `BREACH`, `MAGMA`, `WATER`, `FLOW`, `DROWN`, `SURGE`, `CHASM` across the entire announcement enum returned nothing beyond `MAGMA_DEFACES_ENGRAVING` (an unrelated cosmetic-damage report) and `NOTHING_TO_CATCH_IN_WATER` (a fishing-failure message). | This is a genuine, checked negative finding, not an unexamined gap — "nobody built this" is the honest conclusion. The closest available polling target, not itself confirmed as sufficient: `df.global.world.flows` (the active-liquid-flow list the `liquids` tool already reads) plus map-block liquid-level/designation-flag scanning. |

**What this changes about the design doc's assumptions, stated plainly**: the closed wake vocabulary in §4
(`hostile_detected`, `breach`, `cave_in`, `unit_critical`, `migrant_wave`, `caravan_arrived`, `job_stalled`,
`stock_below_threshold`, `season_change`) has real DFHack events or default-enabled announcement types behind
five of its nine entries (`cave_in`, `migrant_wave`, `caravan_arrived`, `season_change`, and `unit_critical` via
`onUnitAttack`'s wound data with added severity logic). `breach` has **no signal at all** and needs to be built as
a poller from scratch. `hostile_detected` has a real but narrow event (`onInvasion`) that will silently miss most
of what a person would call "a hostile appeared" — treating `onInvasion` firing as sufficient coverage for
`hostile_detected` would reproduce exactly the false-confidence failure mode `unit-status hostile` already
demonstrated. `job_stalled` and `stock_below_threshold` were not part of this brief's eight signals (they map
to this project's own `get_stuck_jobs`/threshold-polling tools, already built, not to an `eventful` event) and
were not investigated here.

No live execution was needed for the existence claims (source-confirmed at the matching version). The one
genuinely unverified step: whether these announcement types, confirmed *configured* as enabled in
`announcements.txt`, are actually *observed* landing in `world.status.reports` during real play on this install —
inferred with high confidence from the config being present and enabled, not independently watched happen.

---

## 6. `dfhack.persistent`

**Primary source: `library/modules/Persistence.cpp` and `library/include/modules/Persistence.h`, read in full.**

**Concurrency**: a repo-wide grep of `Persistence.cpp` for any mutex, lock, or atomic guard found **none** —
the backing store (`static std::unordered_map<int, std::multimap<std::string, std::shared_ptr<DataEntry>>>
store`) has no synchronization of its own. Every mutating entry point (`addItem`, `getByKey`, `save`, `load`,
`clear`), read directly, wraps itself in its **own freshly-constructed `CoreSuspender`** before touching `store`:

```cpp
PersistentDataItem Persistence::addItem(int entity_id, const std::string &key) {
    ...
    CoreSuspender suspend;
    auto ptr = std::shared_ptr<DataEntry>(new DataEntry(entity_id, key));
    add_entry(entity_id, ptr);
    return PersistentDataItem(ptr);
}
```

So `dfhack.persistent` is safe for concurrent writes **for exactly the same reason, and to exactly the same
extent, as everything else answered in §3**: it has no dedicated locking, and relies entirely on every caller
going through the standard `CoreSuspender` convention that ordinary Lua/`dfhack-run` usage always goes through
anyway. Two scripts calling `dfhack.persistent.getSiteData`/`saveSiteData` concurrently (e.g. two specialists
both touching the landmark system in the same cycle) will not corrupt the map — each one's full read-modify-write
sequence runs while holding the suspend lock, and the next contender only starts after the previous one and the
main thread's own tick have both released it. This is the same serialization-not-parallelism outcome as §3, not
an independent guarantee — if any future code path ever touched `store` without going through a suspend (e.g. a
hypothetical raw C++ plugin call bypassing the Lua/RPC layer), that would be a real, unguarded race, since the
class provides nothing itself.

**Hard limit, confirmed by a compile-time constant**: `Persistence.h`, line 54: `static const size_t NumInts =
7;`. Every persistent entry carries exactly one string value (`str_value`) plus a fixed `std::array<int, 7>`. No
source-enforced limit on the string's length was found in this file — it flows straight into a `Json::Value`
field and out to disk as-is, so its practical ceiling is JSON/file-size and memory, not anything `Persistence.cpp`
itself checks.

**Performance shape, confirmed by reading `Persistence::Internal::save()` directly**: on save, for each entity
bucket (the world bucket plus one bucket per site/fort), the code builds a **fresh JSON array from every live
entry in that bucket** and overwrites `dfhack-<name>.dat` completely:

```cpp
for (auto & entity_store_entry : store) {
    Json::Value json(Json::arrayValue);
    for (auto & entries : entity_store_entry.second)
        json.append(entries.second->toJSON());
    auto file = std::ofstream(getSaveFilePath("current", name));
    file << json;
}
```

This is a real, confirmed cost shape: **every save rewrites the whole file for that bucket, proportional to total
entry count in it, not to what changed since the last save.** At this project's current scale (small worlds,
15-19MB saves per `memory/dfhack-environment.md`) this is not yet a problem, but it is the concrete mechanism by
which a landmark system that grows unboundedly would eventually show up as save-time cost — worth instrumenting
if landmark count grows materially, rather than assuming it stays free.

No live execution was needed for any of this — all three findings (no internal lock, the 7-int limit, the
whole-bucket rewrite) come directly from reading the exact matching source.

---

## 7. What was not verified, and why

- **The VM's DFHack build was not independently re-read this session.** Everything above was checked against the
  local Windows Steam install plus GitHub source pinned to the exact matching tag (`53.16-r1.1`).
  `memory/dfhack-environment.md` already documents the VM as running the same version, and this task's
  constraints direct against executing anything on the live fortress — reading the VM's own installed files over
  SSH would have been permitted (per the task brief) but was judged unnecessary given the version match is
  already documented and this research is about the DFHack *build*, not this install's local configuration.
  Flagged rather than silently assumed: if a future session finds the VM's actual DFHack build differs from what
  `memory/dfhack-environment.md` claims, every finding here should be re-checked against that build specifically.
- **§1, FPS-cap persistence across a save/load within one running process** — inferred from the absence of any
  reset code in the shipped source, not executed. Settling command (not run):
  `dfhack-run lua "df.global.enabler.fps=5"`, load a different save, `dfhack-run lua
  "print(df.global.enabler.fps)"`.
  **This can only be fully settled by live execution; the user should approve that separately if wanted.**
- **§2, overlay rendering in this project's actual headless pipeline** — the mechanism is confirmed real and
  headless-safe in principle (same render-loop architecture already proven for `quicksave`), but nobody has
  watched an overlay widget actually appear in a captured Xvfb/VNC frame on VM 103. Settling command (not run):
  deploy a trivial `OVERLAY_WIDGETS` test script, `overlay enable <name>`, inspect a captured stream frame.
  **This can only be fully settled by live execution; the user should approve that separately if wanted.**
- **§5, whether the confirmed-enabled announcement types actually land in `world.status.reports` during real
  play** — inferred with high confidence from `announcements.txt`'s live config (`A_D:D_D`/`ALERT` flags present
  and not commented out), not independently watched happen on a running fort.
- **§5, exact severity semantics of `df.unit_wound`** (what "badly" should threshold on) — the struct and the
  event delivering it are confirmed real; its field-level content was not surveyed this session, out of scope for
  "does the event exist" but immediately relevant to actually building the `unit_critical` wake trigger.
- **The `manager_order`/`workorder` reordering claim** ("mechanically trivial given a plain vector") was not
  exercised live — `world.manager_orders.all:insert(0, order)` at an arbitrary index was not actually called
  against a running fort, only confirmed as a supported vector operation by the same idiom `workorder.lua` itself
  already uses for `insert('#', ...)`.

---

## 8. Relevant to

`docs/AGENT-ARCHITECTURE.md` §13 ("Still open", item 4) directly, resolving all six named capabilities. Specific
downstream effects worth the next design pass picking up:

- §6 (throttle mechanism): `setfps`/`df.global.enabler.fps` is a real, direct primitive — the Sentry's "Throttle"
  level in the graded-response table can be built now, not left unverified.
- §8 (public reasoning stream): the in-game overlay alternative this section flagged as "would look better" is
  mechanically real, but the section's existing choice to render the stream **outside** the game (status JSON +
  a separate page) is not undermined by this finding — it remains the safer choice per that section's own stated
  reasoning (an in-game write path is a write path into the thing being observed), now informed rather than
  blocked by an open question.
- §4 (wake events) and §7 (write-authority partitioning, the Quartermaster carve-out, `dfhack.persistent` as
  shared mutable state): both get their evidentiary gaps closed by §4-6 of this report; the water/magma-breach
  negative finding and the invasion-is-narrow finding are the two most likely to change what actually gets built,
  since both were implicitly assumed covered.
- `research/2026-09-12-write-conflict-matrix.md`: this report's §3 finding (mechanically safe, but serialized and
  unordered, with the exact mutex/hand-off mechanism now source-confirmed) is the piece that brief needed to move
  from "gated on question 3 of the capability checks" to actually assessable.
- `memory/dfhack-environment.md`: worth a follow-up edit adding `overlay` and `workorder` to the "available and
  load-bearing" list (both confirmed present, neither currently named there), and noting the `manager_order`
  struct has no priority field if this project ever builds a Quartermaster tool around it.
