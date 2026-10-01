# Research: DFHack's own fort-health notifications as conductor wake reasons

Date: 2026-10-01. Researcher, Sonnet, read-only, no live access. Sources:
DFHack GitHub source at tag `53.16-r1` (tag object sha
`aeefb3174b9b8c0829cfa6b316a7eef9675b0d84`, pointing at commit
`c80747da32aad3bdd5915c60105136d6558aca39`) and its pinned `scripts`
submodule, read from that commit's own `.gitmodules`/tree entry: commit
`7549711a993e03bef19e90b27427096c1099853e`, the exact same commit the
sibling `research/2026-10-01-unattended-popups.md` already used, so the two
reports are reading the same pinned snapshot. `[C-GitHub API]`, high
confidence (two independent API calls: the tag ref, then the tag object).

Fetched as raw file bytes via `cdn.jsdelivr.net/gh/<owner>/<repo>@<commit>/<path>`
(a CDN mirror that serves the exact pinned GitHub blob unmodified, verified
by its own HTTP 200 and byte count matching what a direct read then showed),
not a live DF install, not the WebFetch tool's own page-to-markdown
summarizer. **Methodology note, worth recording**: the WebFetch tool was
tried first and is unreliable for a file this size (`internal/notify/
notifications.lua` is 777 lines), it silently truncates the fetched page
before handing it to its own summarizing model, and past the truncation
point that model fabricated plausible-looking but wrong line numbers and
duplicated earlier content instead of saying so outright (it did eventually
admit the truncation when asked for lines past ~480). Switching to a direct
`curl` fetch of the CDN raw bytes, then reading the saved file with the
ordinary file-read tool, gave genuine byte-for-byte content with real line
numbers for both files below. Every citation in this report with a line
number is from that direct read, not from WebFetch's summary.

Answers `handoffs/2026-10-01-dfhack-notifications-research.md`.

---

## Short answer

DFHack already computes exactly **19 named fort-health/adventure checks** in
one module, `scripts/internal/notify/notifications.lua` (the `scripts`
submodule, not DFHack's C++ core). **All 19 are self-clearing by
construction, not by any explicit clear-on-resolve logic**: there is no
stored "active" flag anywhere in this system. Each notification is a
closure re-evaluated from scratch every time the list is read, and the
calling code (`gui/notify.lua`'s `overlay_onupdate`) rebuilds its whole
choice list from an empty table each time, keeping only the notifications
whose function currently returns non-nil. The moment the underlying
condition clears, the notification is simply absent from the next read:
there is nothing to "go away," because nothing is latched in the first
place. This answers the user's question directly: yes, every one of these
auto-clears, unconditionally, with no exception.

A script can read the whole set without the UI at all, cheaply, by
`reqscript`-ing the module directly and calling each entry's function:
`gui/notify.lua`'s own overlay does exactly this, just inside a render
loop; nothing about it requires the overlay plugin, a visible screen, or
even that the player has the notification enabled in their own settings.

Of the 16 fort-mode-relevant notifications (3 of the 19 are adventure-mode
only), **all read player-visible or player-derivable facts** by this
project's own existing standard (`CLAUDE.md`'s armok rule and the
precedent already set in `df-overseer-vitals.lua`'s header and
`df-overseer-threat.lua`'s treatment of `isDanger`/`isInvader`), with one
flagged exception, `missing_nemesis`, which reports savegame-corruption
internals no vanilla screen shows (see Q3). Two more (`stuck_squad`,
`auto_train`) are military-only and not yet relevant per the 2026-10-01
"military deferred" decision.

The clearest single payoff is `warn_stranded`: a one-line, already-written,
already-self-clearing check for exactly the condition that caught this
project's own 2026-09-28 incident (two citizens sealed in by the office's
own ring walls), and it is not in `conductor/policy.yaml` today at all.

Proposed: one generic read tool, `df-overseer-notify status`, that iterates
the module's own table and returns every notification's current text
(never branching on which notification it is, so a new DFHack release's
20th notification costs nothing), wired into the conductor's per-cycle read
step next to `vitals.summary`, with a handful of new `policy.yaml` wake
reasons mapped from the table in Q3. Full design in Q4.

---

## Q1: Where the list lives, what exists, and self-clearing behaviour

**Location**, confirmed by direct read: `scripts/internal/notify/
notifications.lua` (the file name is exactly the path the handoff guessed).
`scripts/gui/notify.lua` is the UI layer on top of it (the overlay widget
and the settings screen), not where the notifications are defined. The
`gui/notify.lua` file itself confirms the import at its own line 4:
`local notifications = reqscript('internal/notify/notifications')`.

**The table.** `NOTIFICATIONS_BY_IDX`, `internal/notify/notifications.lua:425-737`,
is a plain Lua array of 19 entries; `NOTIFICATIONS_BY_NAME` (`:739-742`) is
built from it by `name` for lookup. Each entry has: `name`, `desc` (the
text shown in the settings screen), `default` (enabled by default or not),
optionally `critical` (adventure-mode only, see below), and one or more of
`fn` (works in both modes), `dwarf_fn` (fort mode only), `adv_fn`
(adventure mode only). `gui/notify.lua:63-69`'s `get_fn` picks `adv_fn` or
`fn` in adventure mode, `dwarf_fn` or `fn` in fort mode.

**The full list** (name, line range, mode, condition computed, verbatim
from source):

| # | name | lines | mode | what it computes |
|---|---|---|---|---|
| 1 | `missing_nemesis` | 427-492 | both | savegame corruption: a unit's nemesis record vector unsorted, or more nemesis IDs issued than records exist (`#df.global.world.nemesis.all` vs `df.global.nemesis_next_id`) |
| 2 | `stuck_squad` | 494-522 | fort | a squad/army stuck on the world map (`fix/stuck-squad`'s own scan) |
| 3 | `auto_train` | 524-540 | fort | the `autotraining` script enabled but no squad selected |
| 4 | `traders_ready` | 542-582 | fort | a caravan at the depot with no merchant still holding `trader`-flagged goods |
| 5 | `mandates_expiring` | 584-606 | fort | a `Make`-mode mandate within 2500 ticks of its deadline |
| 6 | `petitions_agreed` | 608-620 | fort | an agreed-to guildhall/temple petition not yet built (`list-agreements`) |
| 7 | `moody_status` | 622-650 | fort | the current moody dwarf's state: claiming a workshop, gathering, working, or stuck (no workshop/item found) |
| 8 | `warn_starving` | 652-657 | fort | count of citizens past the dire-need thresholds (see below) |
| 9 | `agitated_count` | 659-664 | fort | count of agitated, uncaged/unchained, non-hidden creatures |
| 10 | `invader_count` | 666-671 | fort | count of active, non-hidden invaders |
| 11 | `hostile_count` | 673-678 | fort | count of active, non-hidden, non-invader, non-fort-controlled, non-agitated units flagged `isDanger` (megabeasts etc.) |
| 12 | `warn_nuisance` | 680-685 | fort | count of thieving/mischievous creatures, excluding anything already counted as invader/hostile/agitated |
| 13 | `warn_stranded` | 687-692 | fort | `warn-stranded.getStrandedGroups()`, groups of citizens cut off from the main group |
| 14 | `wildlife` | 694-699 | fort | summary of visible, non-dangerous wildlife (default off) |
| 15 | `wildlife_adv` | 701-706 | adv only | same, adventure mode |
| 16 | `injured` | 708-713 | fort | count of citizens with `health.flags.needs_healthcare`, plus "no functional hospital" if the site lacks a staffed diagnostician+bone+surgeon hospital |
| 17 | `suffocation_adv` | 715-721 | adv only | a breath/air bar, `critical=true` |
| 18 | `bleeding_adv` | 723-729 | adv only | a blood bar, `critical=true` |
| 19 | `save-reminder` | 731-736 | both | minutes since last save past a configurable threshold (default 15) |

`[C-source]`, high confidence for every row, each is a direct read of the
named lines, not an inference.

**Self-clearing, mechanism-level answer**, confirmed from source, not
inferred: `gui/notify.lua:69-105` (`NotifyOverlay:overlay_onupdate`) does
`local choices = {}` (`:72`) then, for each enabled notification, calls
`get_fn(notification, is_adv)()` (`:77-79`) and only
`table.insert(choices, ...)` (`:81-84`) **if the call returned a truthy
value this time**. There is no prior-state comparison anywhere in this
function or in `internal/notify/notifications.lua`, nothing reads "was
this active last tick." Every one of the 19 entries is a pure, stateless
predicate over current game state (unit flags, counters, vectors, a
persistent-save timer), called fresh on every poll. So "does it clear
itself when the condition clears" is not a per-notification property to
check one by one, it is a structural guarantee of the whole system:
**every one of the 19 clears itself, with no exception**, because nothing
is ever stored as "currently showing." The one piece of state in the whole
file, `Cache_nemesis_all` (`:382-422`), is a performance cache for
`missing_nemesis` alone (recomputed at most every 1200 ticks or on
world/map load/unload, `:391-399`), it caches the expensive scan's
*result*, not whether the notification is "active," and the notification's
own `fn` (`:430-444`) still re-derives its return value from that cached
data fresh every call.

**What "how often" means here**: there is no fixed interval in
`internal/notify/notifications.lua` itself, it only defines functions.
The polling interval is whatever calls `get_fn(...)()`, which in the
shipped UI is `gui/notify.lua`'s overlay, drawn on ordinary frame-render
cadence for the dwarf-mode panel (`DwarfNotifyOverlay`, no
`overlay_onupdate_max_freq_seconds` override at `:126-129`, so it inherits
whatever the overlay plugin's own default is, **not independently
verified this pass**: the overlay plugin itself lives in DFHack's C++ core,
not the scripts submodule, and this task did not locate+read that default
from source; not load-bearing for this project anyway, since the plan below
calls these functions directly from a conductor-triggered script, not
through the live overlay). The adventure-mode panel explicitly sets
`overlay_onupdate_max_freq_seconds=1` (`:158`), i.e. once a game-displayed
second, irrelevant to fort mode.

---

## Q2: Reading the set from a script, without the UI, and its cost

**How**: `reqscript('internal/notify/notifications')` from any DFHack
script context (the exact same primitive this project's own scripts
already use, e.g. `df-overseer-clock.lua`'s and `df-overseer-vitals.lua`'s
own `reqscript` calls, and the module does this to its own siblings:
`internal/notify/notifications.lua:7-10` itself requires
`list-agreements`, `fix/stuck-squad`, `warn-stranded` the same way). Once
required, the module's own two public tables are enough:
`NOTIFICATIONS_BY_IDX` to iterate in display order, `NOTIFICATIONS_BY_NAME`
to look one up by name. For each entry, call `entry.dwarf_fn or entry.fn`
(fort mode) directly, this is **not** going through
`gui/notify.lua`/`get_fn` at all, since that function lives in the UI file
and a read tool has no reason to load the overlay machinery just to reuse
four lines of mode-selection logic; a tool-side equivalent is trivial
(`entry.dwarf_fn or entry.fn`, matching `get_fn`'s fort-mode branch
exactly, `gui/notify.lua:63-69`).

**No overlay, no visible screen, no player toggle required.** The 19
functions read `df.global.world.*`, `df.global.plotinfo.caravans`,
`df.global.nemesis_next_id`, and `dfhack.persistent.getUnsavedSeconds()`:
global game state, not anything screen- or widget-relative. The
`enabled`/`disabled` setting (`notifications.config.data[name].enabled`,
written to `dfhack-config/notify.json`) only gates whether the **player's
own overlay** shows it (`gui/notify.lua:76`); nothing stops a separate
script from calling a "disabled" entry's function directly. Recommend the
read tool ignore that player preference entirely and always evaluate every
entry, the conductor needs ground truth, not the human player's current
UI taste, and the two are allowed to differ (e.g. a player who turned off
`wildlife` because it is noisy on their own screen should not thereby hide
it from the conductor).

**One real side effect worth naming honestly**: merely `reqscript`-ing the
module runs its top-level code, which calls `get_config()`
(`internal/notify/notifications.lua:744-766`) and, the first time (or after
a DFHack/notifications.lua version change), **writes
`dfhack-config/notify.json` to disk** (`:762-764`, `f:write()`), the exact
same file the native settings UI would create. This is not a game-state
mutation (nothing in `df.global` changes, nothing a player's save file
tracks) and matches what simply opening `gui/notify` once by hand would do;
flagged here only so it isn't later mistaken for an unexpected write. On
every subsequent call within the same DFHack process, `reqscript` returns
the cached module table and none of this top-level code re-runs
(`:744-776` only executes once per load), confirmed by `reqscript`'s
documented caching behaviour, not independently tested live this pass
(no VM access).

**Cost, per call, reasoned from the predicates read**: of the 16 fort-mode
entries, 8 do a single O(active units) scan
(`for_agitated_creature`/`for_invader`/`for_hostile`/`for_starving`/
`for_nuisance`/`for_wildlife` all iterate `units.active` once each via the
shared `for_iter` helper, `:22-33`; `for_moody`/`for_injured` iterate
`dfhack.units.getCitizens(true)`, a much smaller list). `missing_nemesis`
is cache-backed and cheap except at most once per 1200 ticks. The rest
(`traders_ready`, `mandates_expiring`, `petitions_agreed`, `stuck_squad`,
`auto_train`, `save-reminder`) iterate small vectors (caravans, mandates,
agreements, armies) or do O(1) persistent reads. On a 22-citizen fort with
whatever wildlife is on the map (this project's fort is small, per
`CLAUDE.md`'s status line), this is at most a few dozen O(n) passes with n
in the low hundreds at the absolute worst, the same order of cost as this
project's own `df-overseer-vitals.lua`, which already does a comparable
per-citizen scan every cycle. **Safe to call once per conductor cycle**;
**not** safe to assume it is cheap enough for a tight per-tick poll loop
without measuring live first (no VM access this pass to measure directly;
flagged in Not Verified).

---

## Q3: Armok status, and mapping to wake reasons / the fixed floor

Checked against `CLAUDE.md`'s rule verbatim: "Banned: powers a player does
not have... and information the game hides. Reading something a player can
already see is fine, however it is implemented," and against this
project's own two closest precedents, both already in the repo:

- `df-overseer-vitals.lua`'s header (`scripts/dfhack/df-overseer-vitals.lua:12-27`):
  the raw `hunger_timer`/`thirst_timer` integers are armok-adjacent
  ("diagnostic-only... not something any vanilla screen shows"), but the
  **derived category** a player's own status-flash icon would show
  (fine/hungry/starving, fine/thirsty/dehydrated) is ruled
  `player_derivable` and fine to expose. **This is exactly the shape of
  DFHack's own `warn_starving`**: `internal/notify/notifications.lua:86-99`
  (`is_in_dire_need`, `for_starving`) also never returns the raw timer, only
  a count of units past the threshold, the same derived-category pattern
  this project already ruled acceptable, independently arrived at.
  **Added finding, not in the original research prompt**: DFHack's own
  thresholds (`hunger_timer > 75000`, `thirst_timer > 50000`,
  `:87-89`) are the *identical* critical values `df-overseer-vitals.lua`
  already uses (`HUNGER_CRITICAL=75000`, `THIRST_CRITICAL=50000`,
  `df-overseer-vitals.lua:59-60`, both files citing the same ultimate
  source, DFHack's `full-heal.lua`'s `is_in_dire_need`), cross-validating
  both. The one gap: DFHack's `is_in_dire_need` also checks
  `sleepiness_timer > 150000` (`:89`), which `df-overseer-vitals.lua`
  currently does not track at all. Worth a small follow-up to close that
  gap in the existing tool, independent of this handoff's own ask.

- `df-overseer-threat.lua`'s header (`scripts/dfhack/df-overseer-threat.lua`,
  lines 9-20 and 122-124): this project already found, live, that
  `dfhack.units.isDanger`/`isInvader` **alone is an unreliable reachability
  signal** ("demons were flagged but unreachable; the kea was reachable but
  unflagged") and built its own `shares_walkable_group`/radius-based
  reachability layer on top specifically to fix that. **DFHack's own
  `invader_count` and `hostile_count` notifications are built on exactly
  the flags this project's own research already proved insufficient for
  "reachable"** (`internal/notify/notifications.lua:61-84`, `for_invader`/
  `for_hostile`, presence and non-hidden only, no reachability check at
  all). **Recommendation, and a correction to a naive reading of the
  handoff**: do not wire `invader_count`/`hostile_count` straight into the
  fixed-floor "a reachable hostile" wake reason, that would silently
  reintroduce the exact false-positive/false-negative pattern
  `df-overseer-threat.lua` was built to fix. Use them only as a cheap
  "something is flagged at all, worth running the real threat tool"
  pre-check, never as the floor's own source of truth.

Per-notification armok read (fort-mode-relevant 16, excluding the 3
adventure-only entries which are out of scope for a fortress-mode
conductor):

| name | armok status | reasoning |
|---|---|---|
| `warn_stranded` | clean | identical in kind to the native "stranded citizens" notification the user already saw live catching the 2026-09-28 incident; player-visible by construction |
| `invader_count`, `hostile_count`, `agitated_count`, `warn_nuisance` | clean | all explicitly filter `not dfhack.units.isHidden(unit)` (`:68, 80, 57, 126`), the authors deliberately excluded anything a player could not see, same intent as this project's own no-armok rule |
| `traders_ready` | clean | reads depot/inventory flags shown in the trade screen |
| `mandates_expiring` | clean | reads the mandates a player sees on the nobles' mandate screen |
| `petitions_agreed` | clean | reads the petitions screen's own backing data |
| `moody_status` | clean | job/path state a player can already see on the unit's own job tooltip |
| `warn_starving` | clean, precedent-matched | see above, same derived-category pattern as `df-overseer-vitals.lua`, independently validated |
| `injured` | clean | `health.flags.needs_healthcare` is what drives the player-visible health-icon state; hospital-staffing check reads noble/occupation assignments, also player-visible |
| `wildlife` | clean, low value | visible-wildlife summary; not useful to the conductor (no hands-off decision hinges on it) |
| `save-reminder` | clean, not even game data | purely a DFHack meta-timer (seconds since last save) |
| `stuck_squad`, `auto_train` | clean but **not yet relevant** | both are military-only; per the 2026-10-01 "military deferred" decision (`decisions/DECISIONS.md`), this project has no squads yet, so these have nothing to report, revisit when squads exist |
| `missing_nemesis` | **flagged, not clean-cut** | reports internal savegame-corruption state (`world.nemesis.all` sortedness, orphaned nemesis IDs) that no vanilla screen shows a player at all. It is a DFHack-native, player-facing diagnostic (shown by DFHack's own standard notify overlay to any player who has it enabled) rather than a hidden developer-only read, which leans toward "fine, it's the same facility a human player already has", but it is also qualitatively different from the project's player_derivable precedent (it is not a category derived from an existing visible icon, it is new information about save-file integrity). **Recommend an explicit ruling before wiring this one in**, the same way `docs/ARMOK-RULINGS.md` records a per-tool decision rather than assuming; everything else in this table is clean enough not to need one. |

**Mapping to `conductor/policy.yaml`'s wake table** (current table read in
full from the live file this pass):

| DFHack notification | proposed wake reason | clock | wakes | floor? |
|---|---|---|---|---|
| `warn_stranded` | `citizens_stranded` (new) | `tripwire` (paused) | `overseer` | **yes, recommend adding to the fixed floor.** This is the exact miss from the 2026-09-28 incident; the existing floor (tripwire, death, reachable hostile, pause-watchdog escalation) has no entry that would have caught two citizens sealed in a room with no immediate death yet. The user's own framing in the handoff's "Why" ("it was the only thing that caught...") argues for floor status, not an Overseer-tunable one. |
| `injured` (no functional hospital clause specifically) | `citizen_needs_healthcare` (new) | `slowed` | `quartermaster` | no, same tier as `stuck_job`/`stock_below_target`, a production/care gap the quartermaster already owns |
| `traders_ready` | refine the existing `caravan_present` reason to use this richer, depot-ready signal instead of (or alongside) its current trigger, **existing `caravan_present` entry's own current trigger condition was not read this pass** (out of scope: it lives in `conductor/cycle.py`, code, not `policy.yaml`'s data) | `slowed` | `quartermaster` | no, already matches an existing non-floor entry |
| `mandates_expiring`, `petitions_agreed` | `deadline_approaching` (new, shared) | `slowed` | `quartermaster` | no |
| `moody_status` | `moody_dwarf_status` (new), ties into the already-researched job-dependency-graph work (`research/2026-09-28-job-dependency-graph.md`) rather than inventing fresh triage logic | `full_speed` if "can't find needed workshop/item" (a real stuck state), else `slowed` | `quartermaster` | no |
| `warn_starving` | cross-check against the conductor's existing vitals-based wake logic before adding a second, possibly-overlapping reason. **Not designed in this pass**, flagged as a design question for whoever builds this, not answered here | n/a | n/a | no |
| `agitated_count`, `hostile_count`, `invader_count` | not a new wake reason; feed as a cheap pre-check into whatever already runs `df-overseer-threat.lua`'s reachability pass, per the correction above | n/a | n/a | **no**, explicitly not the floor's source of truth |
| `save-reminder` | `unsaved_too_long` (new), low priority | `slowed` | `[]` (visible in the digest, nobody woken) | no |
| `missing_nemesis` | hold until the ruling above is made | n/a | n/a | no |
| `stuck_squad`, `auto_train`, `wildlife` | not wired in now | n/a | n/a | no, military-deferred or low-value |

---

## Q4: Proposed tool, conductor change, live test plan

### Tool: `df-overseer-notify status`

Generic over notification type by construction, matching this repo's own
rule (`CLAUDE.md`, "Tools must be generalisable") and the sibling design in
`research/2026-10-01-unattended-popups.md`'s `popup-status`/
`dismiss-popups` pair, this is the same shape, read-only:

```
df-overseer-notify status [--names n1,n2,...]
  -> reqscript('internal/notify/notifications')
     for each entry in NOTIFICATIONS_BY_IDX (optionally filtered by --names):
       skip entries with no dwarf_fn and no fn (adventure-only, fort mode)
       text = (entry.dwarf_fn or entry.fn)()   -- always evaluated,
                                                 -- ignoring the player's
                                                 -- own enabled/disabled
                                                 -- toggle (Q2)
       return {name, active: text ~= nil, text, player_enabled: <config
               value, informational only>}
```

It does not branch on *which* notification it is, the next DFHack release
adding a 20th entry to `NOTIFICATIONS_BY_IDX` costs this tool nothing,
exactly the standard the repo already holds every other tool to. It needs
no new struct knowledge: everything is read through the module's own
already-public Lua functions, not raw `df.global` offsets, so there is
less here to get wrong live than most of this project's other tools.

**Precondition, worth stating plainly**: `internal/notify/
notifications.lua`'s own top-level code reads `df.global.world.buildings`/
`plotinfo.caravans`/`world.units` at module-load time (`:14-16`), so this
only works with a map loaded, never at the title screen. That already
matches every situation this tool would be called in (the conductor only
runs against a loaded fort).

### Conductor change

Wire `df-overseer-notify status` into the conductor's per-cycle read step
(`conductor/cycle.py`), next to the existing `vitals.summary` read (same
precedent `research/2026-10-01-unattended-popups.md` used for where this
class of thing belongs). Add the new `policy.yaml` wake reasons from the Q3
table (`citizens_stranded` to the fixed floor; `citizen_needs_healthcare`,
`deadline_approaching`, `moody_dwarf_status`, `unsaved_too_long` as
ordinary tunable entries). None of this requires `cycle.py` to branch on
notification name beyond reading each returned entry's own `name` to look
up its wake reason in the policy table, the same data-driven pattern
`policy.yaml`'s own header already commits to ("Nothing in
`conductor/cycle.py` branches on a literal wake-reason string").

### Live test plan, cheapest/safest first

1. **Read-only, zero risk**: on VM 103, `dfhack-run lua
   "local n = reqscript('internal/notify/notifications'); print(#n.NOTIFICATIONS_BY_IDX)"`.
   Confirms the module loads and the table resolves at all on the real
   53.16-r1.1 install before anything else is built on it (same
   "read the exact field before trusting it live" discipline
   `docs/TRAPS.md` already asks for).
2. **Read-only, functional**: call `(entry.dwarf_fn or entry.fn)()` for
   `warn_stranded` and `save-reminder` specifically (the two cheapest and
   most certain to have a readable answer right now) and compare against
   what the live fort's own state should produce (currently: no one
   stranded, so `nil`; some number of minutes since last save, non-nil).
   Confirms the fort-mode branch of `get_fn`'s logic reimplemented in the
   new tool matches a known-good answer.
3. **Read-only, over time**: run the new `status` subcommand once per
   conductor cycle for a few real cycles and diff successive outputs
   against the fort's actual known state (no citizens should show
   `warn_stranded` active under normal operation; this gives a negative
   control before the next real incident gives a positive one).
4. **Supervised functional test of the floor wake reason**: the next time
   this project deliberately or accidentally reproduces a stranding (e.g.
   a supervised construction test near an access point, matching the
   caution already applied around the office's ring walls), confirm
   `citizens_stranded` fires, wakes the Overseer, and clears itself the
   next cycle once the group rejoins, this is the one claim in this report
   that most needs a real positive-case live run, since the 2026-09-28
   incident was caught by eye, not by this tool (which did not exist yet).
5. **Never skip reachability's own tool**: when wiring `agitated_count`/
   `hostile_count`/`invader_count` in as a pre-check, verify live that a
   genuinely unreachable flagged creature does *not* escalate past the
   pre-check stage, i.e. that `df-overseer-threat.lua`'s own reachability
   pass still gets the final word, per the Q3 correction.

---

## Not verified, and why

- **The overlay's own default poll frequency** (`overlay_onupdate_max_freq_seconds`
  for the fort-mode panel). Lives in DFHack's C++ overlay plugin, not the
  scripts submodule; not located this pass. Not load-bearing for the design
  above, since the proposed tool calls the notification functions directly
  rather than through the overlay's own render loop.
- **Measured, live, per-call cost of `df-overseer-notify status`** on the
  real Uniboslan population. Reasoned from the predicates' own
  O(active units) shape, cross-checked against `df-overseer-vitals.lua`'s
  comparable existing cost, but not timed against the real process (no VM
  access this pass).
- **Whether `reqscript`'s module-caching behaviour holds across the
  conductor's own `agent exec` invocation boundary** (i.e. whether each
  conductor cycle gets a fresh DFHack process, in which case the one-time
  `dfhack-config/notify.json` write happens once per cycle rather than once
  ever). Reasoned from `reqscript`'s documented semantics, not observed
  live.
- **The existing `caravan_present` wake reason's actual trigger condition**
  in `conductor/cycle.py`, needed to say precisely how `traders_ready`
  should refine or replace it. Out of this pass's source-reading scope
  (that logic is in `conductor/`'s own Python, not DFHack's source); flagged
  as a design question for whoever implements Q4 rather than guessed at.
- **A ruling on `missing_nemesis`'s armok status.** Argued both ways above;
  deliberately left as an open question rather than a judgment call this
  report is positioned to make on the user's behalf, consistent with how
  `docs/ARMOK-RULINGS.md` records each such decision individually.
