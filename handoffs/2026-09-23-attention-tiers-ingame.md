# Stream: the in-game half of the attention system (tiers, the fifth tripwire, theft, the ledger)

**Written** 2026-09-23. **Status:** dispatched. **User go-ahead:** 2026-09-23,
"agreed", to building the attention system and the stalled-order poller.
**Offline code and tests only. No deploy, no VM, no unpausing.** A sibling
stream (`handoffs/2026-09-23-stalled-order-poller.md`) owns everything under
`conductor/`; you own the in-game side. Sonnet executor, worktree-isolated.
**No push. No attribution lines in any commit.** No em dashes.

## Why

Today's research settled what should stop the fort and what should merely be
written down. Read these first:

- `research/2026-09-23-wildlife-threat-classes.md`: a kea carries only the
  curious-beast tags, no LARGE_PREDATOR, no BUILDINGDESTROYER, and is not an
  invader, so it must never pause the fort at any distance. Recommends three
  tiers and an observation ledger that never pauses or wakes anything.
- `research/2026-09-23-announcement-severity.md` and
  `research/data/2026-09-23-announcement-severity.yaml`: all 357 announcement
  types levelled (pause 25, slow 23, notice 139, log only 93, ignore 77),
  validated by the orchestrator as complete and exact against the live list.
- `evals/live/2026-09-23-office-and-first-real-build/`: the run a kea 68 tiles
  away ended after 900 ticks.

## What to do

1. **Three tiers in `scripts/dfhack/df-overseer-clock.lua`**, replacing "any
   reachable candidate pauses". Follow the researcher's rule as written:
   **pause** for a large predator, a building destroyer, or a confirmed
   invader or marauder that has actually reached the citizens' walkable
   network; **slow** for a theft-tagged creature closing in, or an invader
   visible but not yet reachable, waking the Overseer; **record only** for
   anything else, including a kea. Read the tags per candidate, the same cheap
   reads `df-overseer-threat.lua` already makes. Put the tier table in data,
   not in branches, so the next creature class is one entry.
2. **The fifth tripwire: announcements.** Fire on a newly arrived report whose
   type is one of the 25 `pause` ids, held as a literal table in the same
   shape `df-overseer-diff.lua`'s `REPORT_CATEGORY` already uses, generated
   from the YAML rather than hand-copied, with the generator committed. It is
   a **separate** tripwire, not folded into the hostile one. The 23 `slow` ids
   are not yours to act on: expose them so the sibling conductor stream can
   route them, and record the agreed field shape in your Result.
3. **Theft is currently invisible.** `CREATURE_STEALS_OBJECT` is not in
   `df-overseer-diff.lua`'s report categories, so a kea actually taking
   something never reaches us. Add it, and any sibling ids the YAML marks
   `notice` or higher that the table omits. Say which you added and why.
4. **The observation ledger.** A small store keyed by creature race plus
   outcome, not per unit, aggregating in place: sighting count, last seen
   tick, closest approach, outcome counts. Presence-only rows decay on a
   window; a row recording a theft or a kill graduates to the permanent record
   instead of decaying. **Hard rule: the ledger's write path never pauses and
   never wakes.** It is only ever read. Provide a read verb and grant it to
   the roles that should see it.
5. **The death tripwire listens too widely.** It uses the raw `UNIT_DEATH`
   event, which `research/2026-09-16-player-visibility.md` tags omniscient.
   `CITIZEN_DEATH` and `PET_DEATH` are the player-visible channel. Re-point or
   dual-arm it, and say plainly which you did and what changes.
6. **Player visibility applies to every tier and every ledger row.** A rule
   that reacts to something the player could not see is out, whatever it is
   called. State how you checked.
7. Tests, including: a kea-shaped candidate does not pause; a large predator
   that has reached the citizens does; an unreachable invader slows rather
   than pauses; the ledger aggregates rather than appends; the ledger's write
   path cannot reach a pause or wake call; the generated pause-id table
   matches the YAML. Both suites green: ambient `python -m pytest` (1281
   passed / 3 skipped before you) and `.venv-dfmcp/Scripts/python -m pytest
   dfmcp/tests` (652 before). Report the new counts.

## Hard lines

- **Offline only.** No ssh, no VM, no deploy, no live DFHack call, no
  unpausing. The fort is paused and stays paused.
- **Do not touch `conductor/`**: the sibling stream owns it.
- No model call. No armok capability, nothing a player could not know, no map,
  coordinate-free output.
- Tripwires run on a tick timer: no unbounded scan (`docs/TRAPS.md`).
- Secrets by key only, never printed. Never print an IP or hostname.
- Do not write `Working.md`, `decisions/` or `memory/`.
- Commit as you go and fill in the Result section.

## Touched surfaces

`scripts/dfhack/df-overseer-{clock,diff,threat}.lua`, a new ledger module and
its generator, `TOOLS.yaml`, the matching dfmcp schema and role allowlists,
tests under `tests/` and `dfmcp/tests/`, this doc.

## Result

**Status: done, offline. Nothing deployed, no VM touched, fort untouched
(it isn't running anywhere this stream could reach).** Branch:
`worktree-agent-acaeeebc8ecf17436`, commits `c04c42d`..`HEAD` on top of the
merge of `main` (which pulled in the already-finished sibling conductor
stream, `handoffs/2026-09-23-stalled-order-poller.md`).

### 1. Three tiers (`df-overseer-threat.lua`)

`class_flags(unit)` reads six raw creature tags
(`LARGE_PREDATOR`/`BUILDINGDESTROYER`/`CURIOUSBEAST_ITEM`/`_EATER`/
`_GUZZLER`/`BENIGN`/`MISCHIEVOUS`) via
`df.global.world.raws.creatures.all[unit.race].flags.<NAME>`, pcall-guarded,
false on any read failure. `classify_tier(...)` applies
`research/2026-09-23-wildlife-threat-classes.md` S:E1's rule exactly as
written: pause for `LARGE_PREDATOR`/`BUILDINGDESTROYER`/an invader that has
actually reached the citizen network; slow for a theft-tagged creature
closing in or already close, or an invader visible but not yet reachable;
record_only otherwise (a kea at any distance lands here, the concrete
regression case). The escalation table (`TIER_ESCALATIONS`) is data (two
rows today); the next `LARGE_PREDATOR`-shaped raw class is one more row, not
a branch. `find_threats` now sorts by tier first, score second, so
`df-overseer-clock.lua` can keep reading `results[1]`.

**Named gap, stated plainly, not fixed here:** the exact struct/enum field
names for the six raw-tag reads were **not verified against a live game**
(offline stream, no VM). The pattern (`df.global.world.raws.creatures.all`,
bitfield-as-boolean, no `.bits` in Lua) is standard DFHack idiom and each
read is pcall-wrapped so a wrong name degrades to `false` rather than
crashing the tripwire, but a live check (`:lua =df.global.world.raws.
creatures.all[SOME_KEA.race].flags` against a real kea) is owed before
trusting a live run's tier assignment. Flagged in the .lua file's own header
too, per the project's "mark verified vs proposed" rule.

`DEFAULT_CLOSE_RANGE_TILES = 10` is this stream's own unresearched
placeholder (research doc S:C: no measured tick-to-tile number exists to
derive a real one from), overridable, not tuned against a live fort.

### 2. The fifth tripwire, and the reconciliation with the merged conductor stream

`scripts/gen_announcement_pause_slow.py` (committed) reads
`research/data/2026-09-23-announcement-severity.yaml` and writes
`scripts/dfhack/df-overseer-announcement-levels.lua` (generated,
`--check` mode verifies no drift; `tests/test_announcement_levels_generated.py`
enforces it in CI). `df-overseer-clock.lua`'s new step 4 is a **separate**
tripwire (its own bounded backward scan over `world.status.reports`, own
latch reason `"announcement"`), not folded into step 3, over the 25
generated `PAUSE_REPORT_IDS`.

**Reconciliation, since you flagged the sibling had already merged and
assumed a shape:** confirmed by reading `conductor/cycle.py` on `main` after
merging it in. Its `SLOW_ANNOUNCEMENT_EVENT_TYPE`/
`_classify_slow_announcements` assumed a `diff.since` event
`{"type": "announcement_slow", "announcement_type": <df name>, "tick": <int>,
"wake": [<role>, ...], "detail": <one-clause gloss>}`. **That exact shape is
now real**: `df-overseer-diff.lua`'s `onReport` handler emits it for a
newly-arrived report whose type is in the generated `SLOW_REPORT_IDS`
(23 ids), sourced from `SLOW_REPORT_IDS[id].{name,wake,detail}` -- the
generator now also carries each slow type's own severity-YAML `reason`
string as `detail`, so no second data source was needed. This is
**independent of `REPORT_CATEGORY`** (a slow id may carry no
`REPORT_CATEGORY` tag at all, e.g. most of the 23 aren't in that table), and
**never pauses or changes FPS** from that handler -- it only logs into the
same `diff.since` stream the conductor already drains every cycle with its
own per-role cursor, so no new call is needed on the conductor's side at
all. I did not edit `conductor/` itself. The `announcement-levels.slow-ids`
MCP tool (granted to `conductor` in `agents/conductor/tools.yaml`) still
exists as a secondary, static introspection route (the full table on
demand, independent of any report having fired), not the primary path.

**Field shape actually delivered** (matches what the sibling assumed,
confirmed against its merged code, not just recorded as a plan):
```
{"type": "announcement_slow", "announcement_type": "<df.announcement_type name>",
 "tick": <int>, "wake": ["overseer"|"architect"|"quartermaster", ...],
 "detail": "<the severity YAML's own reason string for that type>"}
```
delivered as one more entry in `diff.since`'s existing `events` array
(alongside the pre-existing `id`/`at_tick`/`encoding_version` bookkeeping
fields every event there already carries).

### 3. Theft visibility (`df-overseer-diff.lua`)

Added `CREATURE_STEALS_OBJECT` (145, the handoff's own named case) plus
every `alert_type: CRIME` sibling the severity YAML marks `notice` or higher
that `REPORT_CATEGORY` omitted (checked every CRIME-tagged id in the YAML,
not just the one named): `MISCHIEF_LEVER`/`PLATE`/`CAGE`/`CHAIN` (75-78, the
vanilla-legal fallback for a `MISCHIEVOUS`-class creature the wildlife
research says this project has no legal way to see directly),
`CITIZEN_SNATCHED` (252, already `pause`-level), `CRIME_WITNESS_HANDOFF`/
`STOLEN`/`ITEM_MOVED`/`ITEM_MISSING` (332-335). `AMBUSH_THIEF`/
`AMBUSH_SNATCHER` were already covered by the existing `"ambush"` tag, not
duplicated. A `"theft"`-category `REPORT` also writes a `"theft"` outcome
into the ledger, honestly under race `"unknown"` -- `df.report` carries no
structured race field, only English text, and attributing a race from that
text was not attempted (no VM to verify against real report text this
stream, and a wrong guess is worse than an honest unknown). Named as a
real, follow-on gap, not glossed over. `REGISTRATION_VERSION` bumped so the
live re-registration guard actually replaces the pre-2026-09-23 listener
closure on next deploy.

### 4. The observation ledger (`df-overseer-ledger.lua`)

Keyed by race (never per-unit), aggregating `sighting_count`,
`first_seen_tick`/`last_seen_tick`, `closest_distance_tiles`, and an
`outcomes` count map in place. `record()` is the only write entry point;
`read_ledger(max_age_ticks)` decays a row **at read time only** (a row whose
`outcomes` holds only `"present"` and is older than the window is left out;
any other outcome never decays). **Field shape of one row:**
```
{race, first_seen_tick, last_seen_tick, sighting_count,
 closest_distance_tiles, outcomes: {present: N, theft: N, ...}}
```
`ledger_closest_distance(race)` is the pure read `threat.lua` uses for the
"closing in" comparison, read strictly **before** the same scan's own
`record()` calls (in `clock.lua`'s step 3), so a scan never sees its own
fresh writes mid-computation.

**Hard rule, verified structurally, not just asserted:**
`tests/test_observation_ledger.py::test_ledger_source_never_references_
pause_or_wake_machinery` and `::test_ledger_never_reqscripts_clock` grep the
real committed `.lua` file's **code** (comments stripped) for
`SetPauseState`/`clock_pause`/`clock_resume`/`clock_arm`/`clock_disarm`/
`repeatUtil.`/`repeat-util`, and for a `reqscript('df-overseer-clock')` line
-- both pass against the actual file, not a port of it. `df-overseer-ledger.lua`
does not even `reqscript` `df-overseer-clock.lua`, so the dependency edge
itself cannot become an accidental pause/wake route later.

**Read verb granted** to `overseer`, `architect` and `quartermaster`
(`ledger.read` in each `agents/*/tools.yaml`), per research doc S:E3(6): a
repeated pattern is fence/trap proposal material for the Architect and
restock material for the Quartermaster, not only an Overseer concern.

### 5. The death tripwire

Checked the **actual code**, not the design doc's paraphrase:
`df-overseer-clock.lua`'s step 1 has never used the raw `UNIT_DEATH`
eventful event (that's `df-overseer-diff.lua`'s separate event log, already
`isHidden`-gated since 2026-09-16). Step 1 is, and always was, a
`dfhack.units.getCitizens()` roster diff -- already scoped to the player's
own fort citizen roster, not the omniscient `world.units.active`-wide event.
**No change made there: there was no omniscience to fix**, and I said so
plainly in the code (a new comment on step 1) rather than silently leaving
the research doc's claim uncorrected. **Dual-arming achieved for free**: the
generated `PAUSE_REPORT_IDS` already contains `CITIZEN_DEATH` (106) and
`PET_DEATH` (107) (both `pause`-level in the severity YAML), so step 4's
announcement tripwire independently pauses on either -- a real,
player-visible, DF-announced corroborating signal, with no separate wiring
needed, and coverage the roster diff structurally cannot have on its own
(`getCitizens()` never lists animals, so `PET_DEATH` was previously
uncovered by any tripwire).

### 6. Player visibility, checked against every tier and every ledger row

- **Tier computation** reads only: static raw tags (a per-species lookup,
  not a map scan, same cost class as the existing `danger_flags()`),
  `dfhack.units.isInvader` (already an existing, already-audited HEURISTIC
  read in this file), and the existing reachability fields
  (`shares_walkable_group_with_citizens`/`within_bounded_distance_of_landmark`/
  `distance_tiles`), all already classified `player_visible`/
  `player_derivable` before this stream. No new field is read from the
  game. `is_mischievous` is read and reported but **never used by
  `classify_tier`** -- deliberately: gating a decision on it would reproduce
  the exact `isHidden` violation `research/2026-09-16-player-visibility.md`
  already ruled out (research doc S:D/E2), so this stream built no rule
  that reaches for it, matching that doc's own instruction.
- **The announcement tripwire (step 4)** reads `world.status.reports` --
  DF's own in-game announcement log, the single most player-visible channel
  this project has (already the basis of `df-overseer-diff.lua`'s
  `REPORT`/`recent-combat`/`since-report`, already tagged `player_visible`).
- **The ledger** stores only race/tick/distance/outcome-name -- every one of
  those was already legally exposed by `find_threats`/the `REPORT` stream
  before this stream touched anything; aggregating them over time adds
  memory, not a new read (research doc S:E3(6), confirmed by re-reading it
  against what `record()` actually stores).
- **How I checked, concretely**: for each new/changed read site, I traced
  it back to either an existing `player_visible`/`player_derivable`
  `TOOLS.yaml` entry already carrying that classification, or DF's own
  documented in-game announcement/raw-tag surface (something a vanilla
  player's raws/game log already show), and said so inline in the code
  comment at that read site, not only here.

### 7. Tests

New files, all offline (Python ports/static source-text checks over the
real `.lua` files, same framing `tests/test_reachability_ring_logic.py`
already established for this repo since no Lua interpreter exists here):
`tests/test_announcement_levels_generated.py` (5),
`tests/test_wildlife_tier_logic.py` (13, including the drift guard),
`tests/test_observation_ledger.py` (10, including the structural
pause/wake guard), `tests/test_clock_tripwire_tiers.py` (10). No
`dfmcp/tests/` files were added -- nothing in `dfmcp/*.py` changed; the
`TOOLS.yaml`/`agents/*/tools.yaml` additions are exercised by the existing
registry/roles tests, all still green.

**Both suites, measured after merging `main` (the sibling stream) and this
stream's full changes:**
- `python -m pytest` (repo root, includes `dfmcp/tests`): **1342 passed, 3
  skipped**.
- `.venv-dfmcp`/ambient `python -m pytest dfmcp/tests`: **573 passed, 3
  skipped** (no `.venv-dfmcp` existed in this worktree; ambient `python`
  already has `pyyaml`/`mcp` installed and ran the full suite cleanly, same
  573/3 both standalone and as part of the 1342/3 root run).

**A discrepancy worth flagging, not silently resolved:** this handoff's own
"before you" baseline stated ambient `python -m pytest` at "1281 passed / 3
skipped" and `dfmcp/tests` at "652 before". I measured ambient at exactly
1281/3 **before** adding any of my own tests (confirming that baseline), but
`dfmcp/tests` alone measured **573/3, not 652/3**, both before and
unaffected by my changes (I added no `dfmcp/tests` files). I could not
reconcile the 652 figure -- possibly a different environment/venv, possibly
a stale prediction -- and did not chase it further, since it does not gate
this stream's own work; flagging it rather than quietly adopting either
number.

### Hard lines, confirmed

Offline throughout: no ssh, no VM, no deploy, no live DFHack call, no
unpausing. `conductor/` (the Python package) was never touched -- only
`agents/conductor/tools.yaml` (the allowlist), which is explicitly not that
directory. No model call anywhere in this stream's own work. No armok
capability, no map, coordinate-free output (nothing new here returns
x/y/z). Tripwires run on the existing tick timer; the new announcement scan
is bounded (breaks at the first already-seen report id, cost proportional
to new reports since the last check, never total history). No secret or
IP/hostname was read or printed. `Working.md`/`decisions/DECISIONS.md`/
`memory/` were not written, per the handoff's own instruction (and per
`handoffs/README`'s "executors do not write those files" rule).

### What I could not verify offline (a punch list for the next live check)

1. The six raw-tag field names (`class_flags` in `df-overseer-threat.lua`)
   against a real kea/troll/gremlin unit.
2. That the `announcement_slow`/pause-latch events actually fire for real
   DF-generated reports (mechanism-verified by source reading only, same
   honesty this project's other eventful-based tripwires already carry).
3. That `df.global.world.raws.creatures.all[unit.race]` resolves for every
   unit this scan will actually see (pcall-guarded to degrade safely if
   not, but the safe-degrade path itself is untested against a live
   process).
4. Whether 10 tiles (`DEFAULT_CLOSE_RANGE_TILES`) and 10,000 ticks
   (`DEFAULT_DECAY_WINDOW_TICKS`) are remotely the right order of
   magnitude on a real fort -- both stated as unresearched placeholders in
   the code, not measured.

### Deploy note, 2026-09-23 (separate session, user go-ahead "yep deploy")

Deployed live to VM 103 alongside the merged landmark-reachability batch.
Full deploy record, hashes, and every live check:
`evals/live/2026-09-23-attention-deploy/README.md`. Fort stayed paused,
same tick before and after (107874).

**Punch-list item 1 above is now answered, and the answer is "no, the
field names are wrong"** -- checked directly against a live kea (unit 513),
independent of this file's own code. All three of `class_flags()`'s
premises miss: `LARGE_PREDATOR`/`BENIGN`/`MISCHIEVOUS` are caste-level
fields (`cr.caste[unit.caste].flags.X`), not creature-level
(`cr.flags.X`, the deployed read path, whose own enum has no per-tag
members at all in this DFHack version, only aggregate `HAS_ANY_X`); the
curious-beast names are missing an underscore (`CURIOUS_BEAST_ITEM`, not
`CURIOUSBEAST_ITEM`); and `BUILDINGDESTROYER` is not a flag bit anywhere,
it is a plain integer (`caste.misc.buildingdestroyer`, 0/1/2). pcall
guards degrade every one of these to `false` silently -- no crash, no
error surfaced to `threat.scan`'s caller. For this specific kea the
degrade-to-false happens to still land it in `record_only` (none of the
tags gating the *pause* tier are the ones affected), but
`CURIOUS_BEAST_ITEM` genuinely reads `true` for a real kea and always
reads `false` through the deployed code, so the *slow* tier ("a
theft-tagged creature closing in") can never fire for the exact creature
class this whole design exists to handle. Full derivation, live values,
and the reflection technique that found `buildingdestroyer` are in the
eval README above. Not fixed in this deploy; a dedicated follow-on stream
owns the correction.
