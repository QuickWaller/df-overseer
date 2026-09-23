# Attention system deployed to VM 103, 2026-09-23

**Status: deployed and live-verified. Fort stayed paused throughout, same
tick before and after.** User go-ahead 2026-09-23, "yep deploy", for this
deploy only. Built from `handoffs/2026-09-23-attention-tiers-ingame.md` and
`handoffs/2026-09-23-landmark-reachability.md`, both offline streams merged
to `main` (`d7cc3a9`) on top of the already-deployed order/job-attribution
batch (`ba3150b`, `evals/live/2026-09-23-order-job-attribution/README.md`).

## What was deployed

Thirteen files, built from committed bytes (`git -c core.autocrlf=false
archive HEAD -- <paths>`), the full diff between `ba3150b` (last deploy) and
this stream's `HEAD` restricted to the deploy-relevant paths:

Lua, to `/opt/df/game/hack/scripts/`:
- `scripts/dfhack/df-overseer-reachability.lua` (new -- shared tri-state
  reachability helper)
- `scripts/dfhack/df-overseer-landmarks.lua` (rewired onto the helper)
- `scripts/dfhack/df-overseer-connectivity.lua` (rewired onto the helper)
- `scripts/dfhack/df-overseer-threat.lua` (rewired onto the helper, plus the
  new tier classification)
- `scripts/dfhack/df-overseer-clock.lua` (three-tier tripwire, the fifth
  "announcement" tripwire)
- `scripts/dfhack/df-overseer-diff.lua` (theft visibility, the
  `announcement_slow` event)
- `scripts/dfhack/df-overseer-ledger.lua` (new -- observation ledger)
- `scripts/dfhack/df-overseer-announcement-levels.lua` (new -- generated
  from `research/data/2026-09-23-announcement-severity.yaml`)

Config, to `/opt/df/dfmcp-smoke/`:
- `scripts/dfhack/TOOLS.yaml`
- `agents/architect/tools.yaml`
- `agents/overseer/tools.yaml`
- `agents/quartermaster/tools.yaml`
- `agents/conductor/tools.yaml`

No `dfmcp/*.py` file changed in this batch (`git diff --stat ba3150b..HEAD
-- dfmcp/` empty), so no native-code redeploy was needed beyond the
`TOOLS.yaml`/`tools.yaml` reload on restart. `conductor/` (the Python
package) was explicitly not deployed: this task's own instruction lists only
the Lua/TOOLS.yaml/tools.yaml batch, `conductor.service` was never started,
and the sibling stalled-order-poller stream's Python changes are a separate,
later decision.

## Fort state, before and after

Read via `df-overseer-clock status` and `df-overseer-vitals summary`, both
bounded and read-only:

**Before:** paused, year 31, cur_year_tick 107874, abs_tick 12607074, alive
22, dead_total 1, worst_hunger "fine", worst_thirst "thirsty". A kea 68 tiles
away was latched as the clock's own tripwire, reason `hostile_reachable`
(the exact overreaction this batch fixes -- left untouched by the deploy
itself, since the fort was never resumed).

**After** (restart, install, and every live check complete): identical --
paused, year 31, cur_year_tick 107874, abs_tick 12607074, alive 22,
dead_total 1, worst_hunger "fine", worst_thirst "thirsty". The stale
tripwire latch is still showing (nothing clears a `clock.status` latch
without an unpause or an explicit `clock.clear`, neither of which happened).
No tick moved, no death occurred, `fps` read 100.0 both times.

## Quicksave

Taken before any file was touched. Slot confirmed from
`cur_savegame.save_dir`, per `docs/TRAPS.md`'s warning that
`dfhack.filesystem.mtime` is broken on this install: prior slot
`autosave 2`, `fort.quicksave` issued, polled (spaced, not tight-looped)
until confirmed landed in `autosave 3` (`confirmed: true`).

## Hash verification (twice)

Committed-bytes hashes (`git archive` extraction, cross-checked against
`git show HEAD:<path> | sha256sum` for two spot-check files) matched a
`sha256sum` manifest built from the archive's own extracted bytes, for all
13 files. On the VM, `sha256sum -c` against that manifest passed all 13
(`OK`) immediately after extraction into `/tmp`, and passed again after
installing into both live roots (`sha256sum -c` against the same manifest
re-pointed at the installed paths -- all 13 `OK`). `file` on the three new
Lua files and `TOOLS.yaml` reported ASCII/UTF-8 text with no CRLF.

| file | sha256 (committed bytes) |
|---|---|
| `agents/architect/tools.yaml` | `10c879ecf28ff6cae18e01e1aa32bd1cfe7ea1da15b6dcef8456a383d683b452` |
| `agents/conductor/tools.yaml` | `84c1423efcc0b7ab9ae201e157f27465a2af50328e4940031a45a928dd1965cb` |
| `agents/overseer/tools.yaml` | `0b4ef119acf40767c0187f48fa00736dd3d8101fd194eb2ff965db5dc5d83a58` |
| `agents/quartermaster/tools.yaml` | `3a149549592d05443b1c3904ce2836729f98f8cb142ae5016f7ac25b067cc32c` |
| `scripts/dfhack/TOOLS.yaml` | `acd23e1a7f0e07d205e217d247277dd7c49f6dc73bced8f9e94052e3e4815b87` |
| `scripts/dfhack/df-overseer-announcement-levels.lua` | `5e1917244f083800de5832f41446af2ff71f7d68473fc384aaa7845776e00c04` |
| `scripts/dfhack/df-overseer-clock.lua` | `35fb80cf65443add388eb05d43239952ad6fc049d53e80d7fd98b46e9724ac80` |
| `scripts/dfhack/df-overseer-connectivity.lua` | `372fffb318beb9ea89899274daa2d965cb20e69a192c12eb0e3cdcef910b57f6` |
| `scripts/dfhack/df-overseer-diff.lua` | `214385fb63d1cb20e8c3031acc1685f703f6ec7d1c0c8a27ea171c1b113f22ba` |
| `scripts/dfhack/df-overseer-landmarks.lua` | `c35bf36299b54d21452496e63db93e255ea9522d16b760b0480d593c3abdfb17` |
| `scripts/dfhack/df-overseer-ledger.lua` | `ad139b55df12b0792a6aa1476bea10ca861065e9e0d26bc14f4517f8b5434e35` |
| `scripts/dfhack/df-overseer-reachability.lua` | `9fcb18802e1c8b28f333d550dcf76445f95421140f286cc077ec88d72dc81dad` |
| `scripts/dfhack/df-overseer-threat.lua` | `9eb0e41a4659d6d59f3870c2ba70f4951548a4ce69c57cc69fc79643d0ae45d2` |

Every file backed up first (`cp -p`, preserving mode/mtime) under
`/opt/df/deploy-backup-2026-09-23-attention/` (mirrored into
`game-hack-scripts/`, `dfmcp-smoke-scripts-dfhack/`, and one directory per
role under `dfmcp-smoke-agents-*/`), before any file was overwritten. The
three new files (`df-overseer-reachability.lua`, `df-overseer-ledger.lua`,
`df-overseer-announcement-levels.lua`) had nothing to back up -- confirmed
absent at the install path first (`ls` failed with "No such file or
directory" for all three) before writing them.

## dfmcp-server restart

`sudo -n systemctl restart dfmcp-server`; `systemctl status` seconds later
showed `Active: active (running)`, a single main PID, no restart count -- a
clean start with no crash loop. Since the registry and role allowlists load
once at process start, this alone proves the new `TOOLS.yaml` and the four
changed `tools.yaml` files parsed without a Python exception.

## Live checks, all read-only and bounded

### 1. Every role's tool count, over a real MCP client

Real network HTTP (`mcp.client.streamable_http.streamable_http_client`,
`ClientSession`) against the running server, run from
`/opt/df/dfmcp-smoke/.venv` on the VM itself, each role's own bearer token
read by key from `/opt/df/dfmcp-smoke/.env`, never printed. This install's
`mcp` package vendors `httpx` as `httpx2`
(`streamable_http_client(url, http_client=<httpx2.AsyncClient>)`, yields a
2-tuple, matches `docs/TRAPS.md`'s existing note on this SDK).

| role | before this batch | after | delta | explained by |
|---|---|---|---|---|
| overseer | 62 | **63** | +1 | `ledger__read` (`agents/overseer/tools.yaml`) |
| architect | 36 | **37** | +1 | `ledger__read` (`agents/architect/tools.yaml`) |
| consultant | 21 | **21** | 0 | no grant added, matching both offline streams' decision |
| quartermaster | 22 | **23** | +1 | `ledger__read` (`agents/quartermaster/tools.yaml`) |
| conductor | 13 | **15** | +2 | `announcement-levels__slow-ids` and `orders.list` (`agents/conductor/tools.yaml`) |

Every delta was cross-checked directly against `git diff ba3150b..HEAD --
agents/<role>/tools.yaml` before counting, not just inferred from the
number: overseer/architect/quartermaster each gained exactly one `read`
entry (`ledger.read`, the observation ledger read verb from the in-game
attention stream); conductor gained two (`announcement-levels.slow-ids`,
the static id/name/wake/detail table, and `orders.list`, flagged in that
same diff as slightly outside the sibling stalled-order-poller stream's own
declared touched-surfaces but necessary plumbing for
`conductor/order_watch.py`, already reconciled in that stream's own commit
history, not something this deploy introduced). No tool was removed from
any role.

### 2. `landmarks.list` -- the regression this batch fixes

Called live (`overseer` role). The Well's three exits (from "Activity Zone
#1", "Activity Zone #2", and its own exit list) all now read
`"reachability": "reachable"`, with `"to_via": "adjacent"` /
`"from_via": "adjacent"` on the Well side of each pair -- exactly the fix:
the Well's own centroid (a RampTop, unstandable) used to report `walkable:
false` to every neighbour; it now correctly reports reachable via the
neighbour-ring fallback, tagged so a reader can tell "reachable from beside
it" from "reachable at it". No landmark in this fort's current list reported
`unreachable` or `unknown`.

### 3. `connectivity.check` on a known pair

`{"from": "Well", "to": "Still"}` (overseer role) returned:
```
{"status": "reachable", "from_group": 3478, "to_group": 3478,
 "from_via": "adjacent", "to_via": "at"}
```
Tri-state shape confirmed live, matching the landmark-reachability handoff's
own Result section exactly (`resolve_group`/`reachable_between`'s
`from_via`/`to_via` reporting which case applied).

### 4. `threat.scan` -- tier fields present

Returned two live candidates, both correctly `"tier": "record_only"` with
`"tier_reasons": ["no_pause_or_slow_condition_met"]`: the same kea (68
tiles, unit 513) that is currently latched as the clock's stale
`hostile_reachable` tripwire from before this deploy, and a moose (77
tiles, unit 507). Both carry the new `class_flags` object
(`is_large_predator`, `is_buildingdestroyer`, `is_curiousbeast_item`,
`is_curiousbeast_eater`, `is_curiousbeast_guzzler`, `is_benign`,
`is_mischievous`, each `reliability: "MECHANICAL"`) alongside the
pre-existing `flags`/`reachable` objects. **See the critical check below:
this object's values are not trustworthy as reported.**

### 5. `ledger.read` on an empty ledger

`{"rows": []}` (overseer role). Correct: the fort has been paused this
entire deploy, so no tripwire scan has run to write a row.

### 6. Announcement-levels pause-id list loading

`reqscript("df-overseer-announcement-levels")` loads with no error.
Iterated in-process: `PAUSE_REPORT_IDS` has exactly 25 entries,
`SLOW_REPORT_IDS` has exactly 23, matching
`research/data/2026-09-23-announcement-severity.yaml`'s own counts exactly.
Cross-checked over MCP too: `conductor` role's
`announcement-levels__slow-ids` tool returns the 23-entry table with
`id`/`name`/`wake`/`detail` per row (spot-checked: id 59,
`AMBUSH_MISCHIEVOUS`, whose `detail` string explicitly names the kea case
this whole batch was built for).

## CRITICAL CHECK: the six raw creature-tag field names -- WRONG, found live

This is the one thing the in-game handoff's own Result section flagged as
unverifiable offline and asked a live run to settle. It did not pass.

**Live creature used:** unit 513, the same kea already sitting 68 tiles from
the fort (race `BIRD_KEA`), read directly via `dfhack-run lua`, independent
of `df-overseer-threat.lua`'s own code path.

**What `class_flags()` in the deployed `df-overseer-threat.lua` reads:**
`df.global.world.raws.creatures.all[unit.race].flags.<NAME>` for
`LARGE_PREDATOR`, `BUILDINGDESTROYER`, `CURIOUSBEAST_ITEM`,
`CURIOUSBEAST_EATER`, `CURIOUSBEAST_GUZZLER`, `BENIGN`, `MISCHIEVOUS` --
each pcall-guarded, degrading to `false` on any read failure.

**What is actually correct on this install (DFHack 53.16-r1.1), verified
field by field against the live kea:**

- `cr.flags.CURIOUSBEAST_ITEM` (creature-level, the exact call the deployed
  code makes) errors: `Cannot read field BitArray<>.CURIOUSBEAST_ITEM: not
  found`. The creature-level `flags` BitArray (enum `df.creature_raw_flags`,
  120 entries, dumped in full) has no per-tag members at all in this
  version -- only aggregate `HAS_ANY_LARGE_PREDATOR`, `HAS_ANY_CURIOUS_BEAST`,
  `HAS_ANY_BENIGN`, `HAS_ANY_MISCHIEVOUS` (no `HAS_ANY_BUILDINGDESTROYER`
  entry exists at all). The per-caste flags the deployed code wants live one
  level down, on `cr.caste[unit.caste].flags`, not on `cr.flags`.
- Even at the correct caste level, `caste.flags.CURIOUSBEAST_ITEM` (no
  underscore between CURIOUS and BEAST, the deployed spelling) still
  errors `not found`. The real enum (`df.caste_raw_flags`, 179 entries,
  dumped in full) spells it `CURIOUS_BEAST_ITEM` (also
  `CURIOUS_BEAST_EATER`, `CURIOUS_BEAST_GUZZLER`, `CURIOUS_BEAST` itself) --
  an underscore the deployed code omits.
- `LARGE_PREDATOR`, `BENIGN`, `MISCHIEVOUS` are real member names, but only
  on `caste.flags`, never on `cr.flags` -- the deployed code's actual read
  path.
- `BUILDINGDESTROYER` is not a flag bit anywhere in either enum (confirmed:
  zero matches for `BUILD` or `DESTROY` across both the 120-entry
  creature-level and the 179-entry caste-level enum). It is a plain integer
  field, `caste.misc.buildingdestroyer` (0 = not a destroyer, 1 = destroys
  some buildings, 2 = destroys all), found via DFHack's own field
  reflection (`df.caste_raw._fields.misc.type._fields`) after the flag-bit
  search came up empty. Testing a building-destroyer tag as a boolean flag
  read is not a naming typo, it is the wrong kind of field entirely.

**Verified with the corrected paths, same live kea:**
```
caste.flags.LARGE_PREDATOR         = false  (correct, matches deployed output)
caste.flags.CURIOUS_BEAST_ITEM     = true   (deployed code reads false -- WRONG)
caste.flags.BENIGN                 = false  (correct, matches deployed output)
caste.flags.MISCHIEVOUS             = false  (correct, matches deployed output)
caste.misc.buildingdestroyer        = 0      (not a flag bit; deployed code's
                                               BUILDINGDESTROYER read also
                                               happens to land on false)
```

**Net effect, stated precisely, not glossed over:** for this specific kea,
the deployed code's all-six-false read happens to still classify it
`record_only`, matching the intended regression fix (a kea must never pause
the fort) -- but only because none of the tags that are actually true for a
real kea (`CURIOUS_BEAST_ITEM`) are the ones `classify_tier` uses to *gate*
the pause tier. They are, however, exactly the tag the design's **slow**
tier depends on ("a theft-tagged creature closing in" per
`research/2026-09-23-wildlife-threat-classes.md` S:E1). Because
`is_curiousbeast_item` always reads `false` regardless of the truth, a real
kea closing in on the fort will never escalate to `slow` the way the
research and the handoff's own design intend -- it will sit at
`record_only` forever, silently. The pause-vs-record_only boundary this
deploy's headline regression test cares about happens to be safe by
coincidence; the record_only-vs-slow boundary the same tier table is
supposed to enforce is not. **Not fixed here.** This is a live, load-bearing
finding reported plainly per this task's own instruction, not patched
around -- fixing `class_flags()` (caste-level path, corrected `CURIOUS_
BEAST_*` spelling, and a real integer read for `buildingdestroyer` instead
of a flag-bit guess) is follow-on work for a dedicated stream, not folded
into this deploy.

## What was NOT exercised

No write verb was called against the fort: no `clock.resume`, no unpause, no
`workjob`/`orders` mutation, no tripwire deliberately fired, no
`conductor.service` start, no VM 106 touch, no model call. The stale
`hostile_reachable` tripwire latch from before this deploy was read, not
cleared -- clearing it needs `clock.clear` or an unpause, neither in scope.

## Deploy mechanics notes for future streams

- `scripts/vm-ssh.sh` (committed 2026-09-23, this session's first use of it)
  worked as documented: `DF_ENV_FILE=<path to main checkout's .env>` in the
  environment (the worktree carries no `.env`), then `bash scripts/vm-ssh.sh
  df '<command>'` / `--copy LOCAL REMOTE`. No address or hostname was ever
  typed, echoed, or reconstructed by this session; the wrapper's own `sed`
  scrub also masks `df-*`-shaped filenames as a side effect (visible above
  as `<host>.lua` in some raw command echoes), which is over-scrubbing but
  not a leak.
- The worktree-isolation classifier refuses a `git` or multi-clause shell
  command it cannot statically prove stays inside the worktree (`docs/
  TRAPS.md`, 2026-09-22 entry) -- hit twice this run (a combined `git diff`
  one-liner, a bash `until`-loop poll script) and both times the fix was the
  documented one: split into plain separate commands, or write the loop to
  a file with the editor tool and run it by path.
- `fort.quicksave`'s own `"confirm"` mode needs to be called again after
  `"issued"` mode, spaced out (not tight-looped); this run polled it once
  after roughly a minute of other work plus one more explicit call and it
  had already landed.
- This install's `mcp` SDK vendors `httpx` under the name `httpx2`
  (`streamable_http_client`'s own signature types it `httpx2.AsyncClient`);
  a script written against plain `httpx` fails to import until renamed.
- DFHack field reflection for a struct's own field names, once `pairs()`
  over the struct itself yields nothing useful: read `<Type>._fields`
  (a plain Lua table keyed by field name, each value a field-descriptor
  userdata carrying `.type`, whose own `._fields` recurses into a nested
  struct like `caste_raw.T_misc`). This is what found
  `caste.misc.buildingdestroyer` after the flag-bit search came up empty.

No VM address or hostname appears anywhere else in this file.
