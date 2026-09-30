# Handoff: labor.quota over autolabor

Date: 2026-10-01. **Executor, Sonnet, worktree. Offline code only, no live
access** (the orchestrator live-verifies after merge).

## Why

The register (2026-09-30, "set intent, let the game execute"): autolabor,
enabled on this fort, is the labour engine; our layer sets its per-labour
targets, and per-dwarf `set-labor` is the exception. The mechanism is
settled in `research/2026-10-01-quartermaster-levers.md` §2 (read it in full
first): autolabor is built and working at 53.16-r1, per-labour min, max and
talent pool are set through its CLI only (`autolabor LABOR MIN MAX POOL`),
with no Lua accessor; v50 work details have no headcount targets.

## Tasks, in order (commit after each)

1. `labor.quota LABOR MIN MAX [POOL] [DRY_RUN]` in
   `scripts/dfhack/df-overseer-labor.lua`: generic over every labour
   (validated against `df.unit_labor`), shells to the autolabor CLI the way
   the research proposes, refuses when autolabor is disabled (reuse the
   file's own `autolabor_enabled()` pattern), `DRY_RUN` default true.
2. `labor.quota-status [LABOR]`: reads autolabor's current settings per
   labour (parse its own text output, as the research says), plus how many
   dwarves currently hold each labour, so a model can see target versus
   actual.
3. The report after a real write reads the setting back from autolabor,
   never an echo.
4. `TOOLS.yaml` entries (mutating one tagged like the others), tests in the
   existing lupa style with a stub that models autolabor's CLI output; say
   plainly what the stub cannot prove.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early, then after
  each task; agents here get cancelled mid-run.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `agents/*/tools.yaml` (say in the Result which role gets which command;
  only the overseer may hold a mutating one).
- No em dashes in prose. No attribution lines in any commit. No armok
  capabilities.
- Tests: ambient `python -m pytest` and `dfmcp/tests` with the main
  checkout's `.venv-dfmcp`; report both counts.
- Stop and report on any permission refusal.

## Touched surfaces

`scripts/dfhack/df-overseer-labor.lua`, `scripts/dfhack/TOOLS.yaml`, tests
and stubs.

## Result

Built offline, no live access (as scoped). All four tasks done.

**1. `labor.quota LABOR MIN MAX [POOL] [DRY_RUN]`**
(`scripts/dfhack/df-overseer-labor.lua`, function `labor_quota`, now
non-local so a lua-logic test can call it directly, same convention
`df-overseer-stockpile.lua`'s own command functions already use).
Validates the labor name through the file's existing `labor_code_for`
round-trip check, validates MIN/MAX/POOL are non-negative integers with
MIN <= MAX, then refuses exactly like `set-labor` when
`plugins.autolabor.isEnabled()` can't be determined, or when it is
confirmed false (this tool IS autolabor's own lever, so shelling to a
disabled plugin makes no sense). DRY_RUN defaults to true: a dry run does
every validation above and reports `{dry_run: true, would_set: {...}}`
without calling the CLI at all. A real write (`DRY_RUN=false`) shells to
`dfhack.run_command_silent('autolabor', LABOR, MIN, MAX, [POOL])`, the
only interface for these numbers per
`research/2026-10-01-quartermaster-levers.md` §2 (no Lua accessor exists
beyond isEnabled/setEnabled). On success the report is always a fresh
read-back through `labor_quota_status`, never an echo of the MIN/MAX/POOL
the caller passed (task 3) -- proven in the tests by a case where the
caller omits POOL and the read-back returns autolabor's own retained pool
value, which an echo could not produce.

**2. `labor.quota-status [LABOR]`**
(function `labor_quota_status`, also non-local). Parses `autolabor
list`'s own text output (research §2's cited `print_labor` format:
"LABOR: minimum N, maximum M, pool P, currently C dwarfs", or "disabled",
or "haulers" -- the only query surface that exists; the research flags a
bare `autolabor LABOR` as unverified as a per-labor query, so this
deliberately parses the full `list` output instead of depending on that
unverified form). For one LABOR, or with none given every labor autolabor
reports on. Each entry carries autolabor's own self-reported
`autolabor_currently` AND an independently-read `actual_enabled_count`
via the file's existing `enabled_counts` per-citizen bitfield scan, so a
model sees target versus actual from two genuinely separate reads, not
one value copied into two fields. A LABOR that is a real `df.unit_labor`
name but that autolabor's own `list` never mentions is an error ("no
autolabor entry for X"), never a default -- same silent-zero discipline
this file's `enabled-counts` already enforces.

**3. Read-back, not echo.** Done as part of task 1 above: `labor_quota`'s
success path calls `labor_quota_status({labor_name})` after the CLI call
and returns THAT result, never the caller's own input values.

**4. TOOLS.yaml and tests.** `scripts/dfhack/TOOLS.yaml` gets
`arg_defaults: {DRY_RUN: "true"}` on the `df-overseer-labor.lua` block
plus two new command entries, `quota` (`effect: mutate`, tagged
`knowledge_scope: player_derivable`, `live_deployed: false`, `verified:
unverified`) and `quota-status` (`effect: read`, same knowledge_scope,
same live/verified state) -- confirmed loadable: `load_registry()` picks
up `labor.quota` (mutates=True) and `labor.quota-status` (mutates=False).
Tests: `tests/lua_stubs/dfhack_labor_quota_world.lua` (a fake DFHack world
that formats a small in-memory autolabor state back out through
`print_labor`'s real text shape, and deliberately makes the stub's
self-reported "currently" count differ from its own fake citizen roster's
real count, to prove the two are read independently) and
`tests/test_labor_quota_lua_logic.py`, 16 cases covering validation, the
autolabor-enabled refusal, the DRY_RUN no-call path, the real write's
read-back (including the pool-default case above), a simulated CLI
failure, and quota-status's automatic/disabled/haulers/unknown-labor/
no-autolabor-entry/no-argument shapes. What this does NOT prove (stated
in both the stub's and the test file's own headers): the real autolabor
plugin's `list`/`status` text format matching this parser byte for byte,
and the real `autolabor LABOR MIN MAX` CLI call actually taking effect --
both require a live call this stream had no access to make.

**Role grants (not written here, per the handoff's own rule -- only the
overseer may hold a mutating labor tool):**
- `labor.quota` (mutate) should go to `agents/overseer/tools.yaml` only,
  the same place `labor.set-labor` already lives, for the same reason
  (`agents/quartermaster/tools.yaml` and `agents/architect/tools.yaml`
  both explicitly deny `labor.set-labor` as "not this role's domain, and
  it races autolabor regardless" -- `labor.quota` is the same domain and
  should get the same deny, added alongside the grant in the same pass so
  the two files don't drift).
- `labor.quota-status` (read) is a reasonable candidate for whichever
  roles already hold `labor.enabled-counts` (currently overseer and
  architect) -- it is the same kind of read (autolabor's own settings
  plus a per-citizen cross-check), not itself the mutating lever. Left as
  a recommendation, not applied.

**Tests, both counts measured this session:**
- Ambient `python -m pytest` (worktree checkout, `lupa` on `PYTHONPATH`):
  **2263 passed, 3 skipped**, in 120.77s. (Higher than CLAUDE.md's cited
  1845-passed baseline because this run's rootdir picked up `dfmcp/tests`
  and `conductor/tests` too, not because of anything this stream added --
  the new file contributes exactly the 16 cases below.)
- `dfmcp/tests` under the main checkout's `.venv-dfmcp`
  (`C:\website-projects\df-automation\.venv-dfmcp\Scripts\python.exe -m
  pytest dfmcp/tests -q`, run from this worktree): **722 passed**, 85.23s
  (higher than CLAUDE.md's cited 692 baseline; registry/roster loading was
  not broken by the new TOOLS.yaml entries -- `test_registry.py`-style
  checks and the full `dfmcp/tests` suite both passed clean).
- The new file alone: `tests/test_labor_quota_lua_logic.py`, **16 passed**
  in 0.15s.

**Commits** (this worktree, branch not merged to main):
1. `e3127be` -- `labor: add quota/quota-status over autolabor's CLI`
2. `ef3a6a2` -- `tests: labor.quota/quota-status lua-logic tests over a
   fake autolabor CLI`
3. (this commit) -- `TOOLS.yaml` entries and this Result section.

**The live test that would confirm it** (per the research's own §4 table
row for `labor.quota`, and this stream's own "not proven" list above):
with the fort paused and a fresh quicksave taken first, pick one
already-common labor (the research suggests `HAUL_ITEM 1 200`, generous
and non-restrictive), call `labor.quota` with `DRY_RUN=true` first and
confirm the `would_set` shape looks right, then call it with
`DRY_RUN=false`, and:
1. confirm the real `autolabor <LABOR> <MIN> <MAX>` call succeeded (no
   DFHack error in the log);
2. call `labor.quota-status LABOR` and confirm `minimum`/`maximum` match
   what was requested, `mode` is `automatic`, and `autolabor_currently`
   plus `actual_enabled_count` are both present and are real numbers (not
   null/error) -- the two-angle cross-check this stream could only
   simulate;
3. wait a few in-game ticks (autolabor's own reassignment cycle) and
   re-run `quota-status` to confirm `actual_enabled_count` moves toward
   the new bound, the same "count moves toward the new bound" check the
   research's own live-test proposal describes;
4. `autolabor LABOR reset` (or set it back to its prior min/max/pool) to
   leave the fort's automation config as found.
This is the first live exercise of this tool; nothing above was run
against a live fort this session.
