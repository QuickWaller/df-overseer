# Live run: deploy the `slow`-tier clearing fix, and watch the fort come back off 10 FPS

Date: 2026-09-23. Orchestrating session, user go-ahead: "yeah deploy".
Stream that built it: `handoffs/2026-09-23-slow-tier-clearing.md`.

## What this run proves

The fort was genuinely stuck at 10 FPS. This is the first deploy on this
project that had a live, reproducible bug waiting for it rather than a change
whose effect had to be inferred, so the check is a before and after on the
same fort state rather than a smoke test.

## The bug, read live before touching anything

`clock status` before the deploy:

```
"advisory": { "reason": "hostile_slow", "tick": 12609974,
  "detail": { "race": "BIRD_KEA", "tier": "slow",
              "tier_reasons": [ "theft_tag_close_range" ],
              "near_landmark": "Stockpile #2", "distance_tiles": 0 } },
"armed": true, "fps": 10.0, "paused": true, "abs_tick": 12611557
```

`fps: 10.0` on a paused fort, from a kea that had long since stopped
mattering. The advisory was deliberately left latched at the end of the Chair
completion run so this check would have a real reproducer.

## What was deployed

Two files, hash-checked as **committed bytes** (`git -c core.autocrlf=false
show HEAD:<path>`), again on arrival in `/tmp`, and again at the installed
path. All three readings matched for both.

| File | sha256 (first 16) | Installed to |
|---|---|---|
| `scripts/dfhack/df-overseer-clock.lua` | `29ee59d1e8620843` | the game's DFHack scripts dir |
| `scripts/dfhack/TOOLS.yaml` | `4313d9cc78b8b355` | the dfmcp install |

Both previous copies were backed up first to a dated backup directory with
timestamps preserved.

## Live checks, in the order they were run

1. **Quicksave before any live action**, per the standing rule. Issued, then
   polled once: `confirmed: true`, `current_save_dir` moved `"autosave 1"` to
   `"autosave 2"`. The slot is DF's own `cur_savegame.save_dir`, never mtime
   (`docs/TRAPS.md`).
2. **Backup, ship, install, hash at all three points.** Table above.
3. **`clock clear` against the genuinely latched advisory**, which is the
   check the reproducer existed for, and it is one-shot: clearing consumes it.
   Returned `{"had_advisory": true, "had_latch": false, "ok": true}`. The new
   two-field return distinguishes a real clear from a no-op, which the old
   single `had_latch` could not.
4. **The part that actually matters, read back independently** rather than
   inferred from the return value: `fps: 100.0`, no `advisory` key at all, and
   the new `base_fps: 100` exposed on status. **10 FPS to 100 FPS on the live
   fort.** This also exercised `read_base_fps`'s fallback path, since
   `base_fps.json` did not yet exist at that point: the stream documented that
   path as reachable only before the first-ever arm, and this was exactly that
   state.
5. **Re-armed.** Necessary and easy to miss: deploying a file does not change
   an already-scheduled `repeat-util` callback, so the armed tripwire was still
   running the old closure in memory until this call. Returned the defaults
   unchanged (`check_interval_ticks: 100`, `threat_check_every_n: 10`,
   `think_fps: 10`, `hunger_critical: 75000`, `thirst_critical: 50000`) plus
   `base_fps: 100`. `base_fps.json` was then confirmed on disk reading
   `{"base_fps": 100}`, with the latch and advisory files both 2 bytes, an
   empty object each.
6. **MCP server restarted** so the new `TOOLS.yaml` loads. Clean start,
   `active`, application startup complete, no `RoleValidationError` (the
   server refuses to boot on a grant naming a missing tool, so a clean start
   is real evidence the manifest and the allowlists still agree).
7. **Fort unharmed and unmoved.** `abs_tick 12611557` identical before and
   after, still `paused: true`, 22 alive, 1 dead, `worst_hunger_status` and
   `worst_thirst_status` both `fine`, `warning_count: 0`. Nothing was unpaused
   at any point.

## Still owed, and why it could not be done here

**The natural-clearing check has not been run.** Watching an advisory clear by
itself as a candidate recedes out of range needs the fort to run, which is a
separate mutating action with its own go-ahead, and the reproducer for it is
now consumed: clearing the kea advisory was the only latched one this fort
had. The next unattended run is the natural place for it, and the thing to
watch is an advisory appearing and then disappearing on its own within one
`threat_check_every_n` cycle, with `fps` returning to `base_fps` unprompted.

Also unexercised: whether the default scan cadence is coarse enough that a
creature loitering exactly at the tier boundary does not visibly flap the FPS.
The fix deliberately has no hysteresis, on the argument that the pause tier has
none either. That argument is untested against a real loiterer.
