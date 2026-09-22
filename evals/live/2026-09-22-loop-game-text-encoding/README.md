# Game text reaches the tools as UTF-8, 2026-09-22

**Status: done, with one owed item found live.** Fixed the `diff.since`
CP437 crash at its source in Lua (one shared helper, used at every known
game-text call site across `scripts/dfhack/`), added a Python-side CP437
backstop in `dfmcp/dfhack_client.py`, deployed to VM 103, and proved the
fix end to end: the exact MCP call that crashed the conductor's first
cycle now succeeds, and a real conductor dry-run on VM 106 completed
cleanly from its real, unseeded initial cursor for the first time. Full
narrative, every call site, every test, and the one thing found live and
not fixed: this stream's executor report in
`handoffs/2026-09-22-loop-game-text-encoding.md`'s own Result section; this
file is the durable, standalone record.

## Why

`handoffs/2026-09-22-loop-mvp-deploy.md` found that `diff.since` crashes
(`'utf-8' codec can't decode byte 0x96'`) on a dwarf name holding a CP437
character, reproduced with a direct `dfhack-run` call, no MCP involved. The
conductor's first real cycle reads `diff.since 0` for every role
(`INITIAL_CURSOR = 0`), so this blocked the conductor's first start for
every role, not just one. Root cause: no script under `scripts/dfhack/`
called `dfhack.df2utf` anywhere, so every tool that prints a name, a job, a
building/zone/burrow name, a race, an announcement or a noble title could
hit the same crash the moment a generated name held a non-ASCII CP437
byte -- not one call site's bug.

## What changed

- **`scripts/dfhack/df-overseer-textutil.lua`** (new): one shared helper,
  `to_utf8`, wrapping `dfhack.df2utf` with a `pcall` guard. `reqscript`'d
  and used at every known game-text accessor found by reading the whole
  `scripts/dfhack/` tree: `dfhack.job.getName`,
  `dfhack.translation.translateName`, `dfhack.units.{getReadableName,
  getVisibleName,getRaceName,getProfessionName}`, `dfhack.buildings.getName`,
  `dfhack.burrows.getName`, and `rep.text` (the raw announcement/report
  string DF's `eventful` plugin hands back). Ten existing files changed to
  use it: `df-overseer-{diff,landmarks,connectivity,farm,labor,nobles,
  overview,stuckjobs,threat,workjob}.lua`. Fixing `df-overseer-landmarks.lua`
  fixes every other tool's `near_landmark` field transitively, since they
  all resolve landmark names through it rather than reading a
  building/burrow name directly.
- **`dfmcp/dfhack_client.py`**: a Python-side backstop
  (`_decode_dfhack_text`) -- if a DFHack text reply is not valid UTF-8,
  decode it as CP437 instead of raising (never `errors="replace"`, which
  would lose the name), and log at `WARNING` naming the DFHack command that
  produced it, so a missed call site is visible and fixable rather than
  silently papered over.
- Tests: a regression test reproducing the exact byte-0x96 crash through
  the real Python client path (`FakeDFHackServer` -> `DFHackConnection.
  run_command`), unit tests for the CP437 fallback and its warning log, and
  a new grep-style static guard, `tests/test_game_text_utf8_helper.py`,
  that fails if a `scripts/dfhack/*.lua` file calls a known game-text
  accessor without wiring in the shared helper.

Ambient suite: **1212 passed, 3 skipped** (was 1202/3, per the mvp-deploy
stream's own baseline). `dfmcp` venv suite: **630 passed** (was 623).

## Deploy to VM 103

Quicksave taken and confirmed first (landed in `autosave 2`, confirmed by
`cur_savegame.save_dir` plus a fresh matching `world.sav` mtime -- **not**
by the `fort.quicksave` tool's own slot prediction, which was wrong this
run; see "Found live, not fixed" below). 12 committed files (the new
helper, the ten changed Lua scripts, `dfmcp/dfhack_client.py`) built with
`git -c core.autocrlf=false archive HEAD`, sha256-manifested from the
archive's own extracted bytes, copied, hash-verified on arrival
(`sha256sum -c`, all `OK`), installed, then hash-verified again at the
installed path -- all 12 match the manifest exactly, both times. The 10
overwritten files backed up first to
`/opt/df/deploy-backup-2026-09-22-encoding/` (`df-overseer-textutil.lua`
is new, needed no backup). `dfmcp-server` restarted, confirmed `active`.

Fort state before, during and after every step of this whole stream:
**paused, year 31, tick 106974, alive 22, dead_total 1** -- unchanged
throughout, including after the VM 106 dry run.

## Live checks

| check | result |
|---|---|
| `dfhack-run df-overseer-diff since 0` (direct, the exact crashing call) | Still fails at this raw level -- expected, see "Found live, not fixed" |
| `diff.since` cursor=0 over real MCP, as conductor | **Succeeds.** Valid structured JSON; `Kûbuk Kûbukoshur` (the dwarf whose CP437 name broke the original bug) reads correctly |
| `dfmcp-server` journal | WARNING logged naming `df-overseer-diff`, exactly as designed |
| Role tool counts over MCP | overseer 60, architect 35, consultant 21, quartermaster 21, conductor 13 -- unchanged from the pre-deploy baseline |
| Sample of every other changed tool (`landmarks list`, `nobles list`, `labor unit-status`, `threat scan`, `stuckjobs find`, `workjob list`, `overview get`, `farm list`, `connectivity report`) | All return clean JSON/text, no crash |

## The conductor dry-run, VM 106, real initial cursor

No cursor file existed before this run (the mvp-deploy stream's manual
seed was genuinely removed, per this stream's own instruction not to
reseed). `conductor.service` stayed disabled/inactive; run by hand,
foreground, once:

```
cycle 1: clock=slowed roles_woken=('quartermaster',) dry_run=True
cycle 1 dry-run plan: {'would_read': ['architect', 'quartermaster',
'consultant', 'overseer'], 'would_wake': ['quartermaster'],
'would_set_clock': 10, 'wakes': [{'reason': 'vital_nearing_threshold',
'detail': 'vital nearing threshold', 'roles': ['quartermaster'],
'clock': 'slowed'}]}
```

This is the first time this command has completed cleanly from a real,
unseeded cursor -- the mvp-deploy stream could only get a clean dry run by
seeding every role's cursor to the fort's real high-water mark (1210),
specifically to route around the crash this stream fixes. No model call,
no real clock change, no quicksave, nothing archived; `cursors.json` still
does not exist afterward (dry-run's own documented no-persistence
behaviour, unrelated to this fix). No conductor process left running
afterward.

## Found live, not fixed: the historical event log is stuck on stale closures

`df-overseer-diff.lua`'s `eventful` listeners register exactly once per DF
process lifetime, guarded by a `_G` flag that was already `true` before
this deploy -- the DF process has been running long enough to accumulate
1210 events, all logged under the **old**, unconverted closures.
Redeploying the `.lua` file to disk does not re-run that one-time
registration (the same family of issue `docs/TRAPS.md` already documents
for `reqscript` module caching, here for `eventful` registration instead),
so:

- **13 of the 1210 already-logged events still hold raw CP437 bytes**
  (found live: the first bad entry is id=19, type `UNIT_ATTACK`). This is
  exactly why the direct, unauthenticated CLI call still fails -- it drains
  these pre-existing corrupted entries, which the redeploy cannot touch.
- **The fix itself was proven correct, live, on the real corrupted
  bytes**: entry id=19's raw `detail` fails `utf8.len` (confirms real
  corruption); calling the new `textutil.to_utf8` on it directly recovers
  `"Kûbuk Kûbukoshur (DWARF, id=193) wounded BIRD_KEA (BIRD_KEA, id=323)
  (wound id=-1)"` cleanly. The helper is right; only the live, already-
  registered closures are stale.
- **Why the MCP path succeeds anyway**: the Python-side backstop catches
  the CP437 bytes these 13 stale entries still produce and recovers them --
  exactly the layered design this stream's handoff asked for. The WARNING
  fired in the server's journal, naming the command, exactly as designed.
- **What would close this**: a DF process restart (not a `dfmcp-server`
  restart -- a different process, doesn't touch DFHack's Lua state) would
  re-run the registration block fresh and clear the stale in-memory ring
  buffer. **Not done here**: out of this stream's authorised scope (only
  `dfmcp-server` restart was listed), DF ignores SIGTERM, and the fort must
  stay undisturbed -- a decision for the user. Every future *new* event
  (after a restart, or on a fresh fort) will be converted correctly at the
  source, per the live proof above.
- **Also found live, unrelated, not this stream's to fix**:
  `df-overseer-fort.lua`'s quicksave slot-prediction heuristic predicted
  the wrong slot this run (`autosave 1`, actual landing `autosave 2`) --
  flagged for whoever next touches that file; worked around here by using
  the authoritative confirmation method instead
  (`cur_savegame.save_dir` plus a fresh matching mtime).

## Owed

1. A DF process restart on VM 103, to clear the 13 stale historical
   events and pick up the fix for the live `eventful` closures -- a
   decision for the user (item 1 above).
2. `df-overseer-fort.lua`'s quicksave slot-prediction bug -- not this
   stream's surface.
3. Everything the mvp-deploy stream already listed as owed (Docker socket
   access for `conductor.service`, the tripwire's live tests, a supervised
   first real cycle) is unchanged and still owed; this stream closes the
   specific `diff.since` encoding blocker on that list, for every future
   event.

No VM address appears in this file (per `CLAUDE.md`'s rule); both were
necessarily used as literal `ssh`/`scp` arguments during the live work
itself, never printed, logged or committed.
