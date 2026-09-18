# Handoff: make the four exact deductions actually readable

Date: 2026-09-19. **Offline build stream. No VM, no SSH, no deploy.** You write
the Lua and the tests; the orchestrator deploys and live-verifies separately,
because another stream owns VM 103 right now.

Read `CLAUDE.md`, then `docs/PRODUCTION-MODEL.md` §7, then
`handoffs/2026-09-19-snapshot-assembler.md` **including its write-up**, then
`scripts/dfhack/df-overseer-stocks.lua` in full, then this.

## Why this stream exists

The design's central availability rule is that **available stock is not total
stock**, netted by four exact deductions:

| Flag | Meaning |
|---|---|
| `item.flags.in_job` | claimed by a job |
| `item.flags.owned` + a `UNIT_HOLDER` ref | a dwarf owns it |
| `item.flags.forbid` (**not** `forbidden`) | forbidden |
| `flags.trader` | caravan's |

The snapshot assembler stream established, by grepping every committed tool,
that **only `trader` is reachable today.** `df-overseer-stocks.lua`,
`df-overseer-well.lua` and `df-overseer-workshop.lua` all net
`trader`/`garbage_collect`/`removed` and nothing else, and `well.lua`'s
`count_fort_owned` folds straight to an integer, so **no item list survives for
anything to net further even in principle.**

This is not academic. **The fort held three empty, unforbidden, unclaimed
buckets and still logged "Give water: Need empty bucket"** (announcement 104,
tick 214135). Availability failed while totals looked fine. That is the exact
failure a totals-based walk cannot see, demonstrated live before the code to
detect it existed.

`production/snapshot.py` already has the fully-netted code path
(`stock_from_items` / `items_for_cover`), built and tested against fixtures.
**It has nothing real to consume.** This stream is what feeds it.

## Deliverable

A read-only command on `df-overseer-stocks.lua` that returns, per item type,
both the total and the netted count, **plus the per-flag breakdown** so a
caller can see *why* something is unavailable rather than only that it is.

Shape is your call, but it must let `snapshot.py` distinguish these four
cases, because they are four different decisions:

- 3 buckets exist, all claimed by jobs (wait, or raise priority)
- 3 buckets exist, all forbidden (unforbid)
- 3 buckets exist, all dwarf-owned (make more)
- 0 buckets exist (make one)

Add tests alongside the existing `dfmcp/tests/` and `tests/` patterns for tool
schemas and allowlists, matching how the stockpile and orders tools were added
on 2026-09-18.

## Rules that bite here

- **`flags.forbid`, not `flags.forbidden`.** The second does not exist and
  reads as nil, which is falsy, which would silently count every forbidden item
  as available. `docs/TRAPS.md` carries this. **Getting this wrong reproduces
  the exact bug this stream exists to fix**, so assert it rather than trusting
  the spelling.
- **A lookup that can silently miss must report the miss.** If a flag field is
  absent on this DFHack version, the tool must say so explicitly, never emit a
  zero. This project already shipped a probe that printed "0 of 15" for a token
  that does not exist; the corrected probes print `TOKEN_DOES_NOT_EXIST`.
- **`owned` needs both parts.** The assembler's source notes that `flags.owned`
  was checked and found to be **per-dwarf ownership, not fort ownership**. A
  `UNIT_HOLDER` ref is the other half. If you cannot confirm the ref lookup
  offline, **say so and leave it flagged**, rather than shipping a half-check
  that reads as authoritative.
- **No coordinates in any output.** Hard commitment, `docs/PURPOSE.md` #1.
- **Do not deploy, do not touch the VM, do not unpause anything.** Dry-run
  reasoning and tests only. Say plainly in your write-up what still needs live
  verification and what would falsify it.
- Do **not** write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`.
- No em dashes in prose.

## Touched surfaces

`scripts/dfhack/df-overseer-stocks.lua`, `scripts/dfhack/TOOLS.yaml`,
`agents/architect/tools.yaml`, `agents/overseer/tools.yaml`, `dfmcp/tests/`,
`tests/`, and this handoff doc.

**Do not touch** anything under `production/`, `doctrine/` or `docs/`: other
streams own those. If `snapshot.py` needs a change to consume your output,
**describe it in your write-up rather than making it.**

## Done means

The command exists, its tests pass, the full suite still passes (**380 passed /
1 skipped** right now, report before and after), the four cases above are
distinguishable from its output, and the write-up states exactly which parts
are verified offline and which need a live run to confirm.

## Write-up

Built `get_availability(TYPE)` (canonical id `stocks.availability`) in
`scripts/dfhack/df-overseer-stocks.lua`, plus the manifest/allowlist/test
changes below. Full suite: **380 passed / 1 skipped before, 382 passed / 1
skipped after** (2 new tests, 0 regressions), `python -m pytest -q` from the
repo root. `dfmcp/tests` alone: 136 passed / 1 skipped (ambient interpreter;
no `.venv-dfmcp` existed in this worktree to run the 165-count comparison
CLAUDE.md's trap note describes -- see "What still needs a live run" below).

### Output shape

`./dfhack-run df-overseer-stocks availability TYPE`, where TYPE is any
`df.global.world.items.other` key -- `BUCKET` (the motivating case),
`DRINK`/`FOOD`/`ANY_EDIBLE_RAW`/`SEEDS` (this file's own existing buckets,
now netted one layer further), `CHAIN`/`BLOCKS`/`TRAPPARTS` (well.lua's other
three well materials), or any other `items.other` key. An unresolved TYPE
returns `{error: "unknown item type: ..."}`, never a silently-empty result
(dfmcp/server.py's exact-shape rule surfaces this as `isError`).

A successful call returns one JSON object:

```
type                    -- the TYPE argument, echoed back
total_units / total_item_count
                        -- fort-owned total (trader/garbage_collect/removed/
                           hidden-tile already netted out, via THIS FILE'S
                           OWN existing, already-verified is_fort_owned --
                           unchanged by this stream). This is the number
                           that "looked fine" in the motivating bug: 3
                           BUCKET items, and the fort still couldn't drink.
available_units / available_item_count
                        -- fully netted: fort-owned AND NOT in_job AND NOT
                           forbid AND NOT owned, and only when all three of
                           those flags were actually readable on that item.
unnetted_units / unnetted_item_count
                        -- fort-owned items where at least one of
                           in_job/forbid/owned could not be read as a real
                           boolean on this DFHack version. Availability for
                           these items is UNKNOWN, never folded into
                           `available`.
in_job_units / in_job_item_count
forbid_units / forbid_item_count
owned_units / owned_item_count
                        -- the per-flag breakdown the handoff asked for --
                           this is what lets a caller distinguish "all
                           claimed by jobs" from "all forbidden" from "all
                           dwarf-owned" instead of one opaque zero.
owned_ref_check         -- { with_unit_holder_ref, without_unit_holder_ref,
                             lookup_errors, verified_offline: false }.
                           ALWAYS verified_offline: false -- see below.
trader_units / trader_item_count
                        -- caravan-owned, the fourth deduction, already
                           implemented via is_fort_owned; reported here too
                           so all four deductions are visible in one place,
                           not just the marginal three.
rotten_units / unreachable_units
                        -- reused unchanged from count_bucket, for parity
                           with food-drink/seeds.
flag_read_errors        -- list of flag names ("in_job"/"forbid"/"owned")
                           that failed to read as a boolean at least once
                           this call. Empty when every read succeeded.
```

The four cases the handoff named are distinguishable directly from this
shape without any further logic: "0 buckets exist" is `total_units == 0`;
"3 exist, all job-claimed" is `total_units == 3, in_job_units == 3,
available_units == 0`; "3 exist, all forbidden" is the same with
`forbid_units == 3`; "3 exist, all dwarf-owned" is the same with
`owned_units == 3`. A fifth, honest case the four-way framing doesn't name
is also representable and was the point of `unnetted_units`: "3 exist, but
we can't currently tell why none are available" (a flag read failed) --
that must never be silently reported as `available_units == 3`, and isn't.

### What's verified offline vs what needs a live run

**Verified offline (static reasoning plus reuse of already-verified code):**
- `checked_flag`'s honesty property: any read that raises OR returns a
  non-boolean is treated identically as `ok=false`, never as `false`. This
  is the direct fix for the documented trap (docs/TRAPS.md: on this
  install, `item.flags.forbidden` "errors outright" -- confirmed live
  2026-09-18, not re-derived here, just relied on) -- `checked_flag` does
  not assume that failure mode is the only one (a hypothetical silent-nil
  miss is handled identically, per the handoff's own "0 of 15" precedent).
- The `total`/base fort-ownership filter reuses `is_fort_owned` completely
  unchanged, so food-drink's and seeds' own 2026-09-16 live verifications
  are not put at risk by this addition -- confirmed by reading the diff
  (no existing function's body was edited) and by the full suite passing.
- `scripts/dfhack/TOOLS.yaml` parses cleanly and the new command resolves
  to canonical id `stocks.availability` with `args == ["TYPE"]`, `effect:
  read`, `mutates == False` -- confirmed by `dfmcp.registry.load_registry()`
  against the real manifest, and by `dfmcp/tests/test_registry.py`'s new
  `test_stocks_availability_is_read_derivable_and_unverified`.
- Both `agents/architect/tools.yaml` and `agents/overseer/tools.yaml` load
  through `dfmcp.roles.load_roster` and grant `stocks.availability` to both
  roles (matching the existing `stocks.food-drink`/`stocks.seeds`
  precedent, read-only, not touching `agents/consultant/tools.yaml`, which
  is outside this stream's touched surfaces) -- confirmed by the new
  `dfmcp/tests/test_roles.py::test_stocks_availability_follows_the_stocks_food_drink_pairing`.
- A crude keyword-balance check (`function`/`if...then` (excluding
  `elseif`)/`do` vs `end`, 50 vs 50) over the whole file after editing, as a
  cheap syntax sanity net given no Lua interpreter was available in this
  environment (checked: no `lua`/`lua5.1`/`lua5.3`/`luac` on PATH). This is
  NOT a substitute for `dfhack-run` actually loading the file.

**Genuinely unverified, needs a live run, stated plainly rather than
implied fixed:**
- **The whole command has never executed.** No DFHack process, no VM, no
  `dfhack-run` call, this entire stream (per its own no-deploy constraint).
  Whether the file even loads without a syntax error, beyond the crude
  keyword-balance check above, is unconfirmed.
- **`item.flags.in_job` and `item.flags.owned`**, read via the same
  `checked_flag` mechanism as `forbid`, are standard DF item_flags fields
  by long-established convention and this project's own prior sampling
  (this file's own header: `owned` checked live, found false on every
  DRINK/BOULDER/SEED sampled) -- but neither has been read through
  `checked_flag` specifically, on this install, this stream. A live run is
  what confirms `checked_flag`'s failure path is unreachable for these two
  in practice, not just in the one case (`forbid`) docs/TRAPS.md already
  covers.
- **`checked_unit_holder_ref` (the `owned` + `UNIT_HOLDER` half) is the
  weakest part of this tool, and says so in its own output.**
  `dfhack.items.getGeneralRef(item, df.general_ref_type.UNIT_HOLDER)` is
  the same class of call this file's own header already describes using
  live to confirm `flags.trader` against a real merchant unit, but that
  exact call, for UNIT_HOLDER specifically, has never run from any
  COMMITTED code in this repo -- the only precedent is an uncommitted ad
  hoc `dfhack-run lua` probe in a chat session
  (`df-overseer-orders.lua`'s header, tick 227160: "3 fort-owned ...
  unclaimed, no holder"). Per the handoff's own instruction ("if you cannot
  confirm the ref lookup offline, say so and leave it flagged rather than
  shipping a half-check that reads as authoritative"), every result this
  tool produces carries `owned_ref_check.verified_offline: false`
  unconditionally -- that field is hardcoded `false` in the Lua, not
  computed, and can only become `true` by a future live-run write-up
  editing it, never by this file inferring success from a clean pcall. A
  live run should specifically try an item known to be dwarf-held (a worn
  garment, a claimed bed) and confirm `checked_unit_holder_ref` returns
  `(true, true)` for it, and something known unheld (a barrel in a
  stockpile) and confirm `(true, false)` -- both branches, not just the
  "doesn't error" case.
- **The four-case distinguishability claim** (all-job-claimed vs
  all-forbidden vs all-dwarf-owned vs none-exist) is verified as a property
  of the output *shape* (each combination maps to a distinct, non-
  overlapping set of nonzero fields, worked through by hand above), not
  exercised against a fort in any of those four actual states.

### What `production/snapshot.py` would need to consume this (not made --
out of this stream's touched surfaces, per the handoff)

`fort_owned_counts_to_stock` currently expects a `DF_TYPE -> count` dict
(well.lua's/workshop.lua's existing shape) and always marks the result
`unnetted_flags=("in_job","owned","forbid")`. A caller with real
`stocks.availability` output per type could instead build a dict shaped
like `stock_from_items`/`items_for_cover` already expect (item dicts
carrying the four deduction flags) OR, more simply, a new translation
function parallel to `fort_owned_counts_to_stock` that reads this tool's
`available_units`/`total_units`/per-flag fields directly and sets
`status=schema.MEASURED` only when `flag_read_errors` is empty AND
`unnetted_item_count == 0` for that type, falling back to
`status=schema.UNAVAILABLE` with `unnetted_flags` naming exactly which
flags this call couldn't confirm (using `flag_read_errors` and
`owned_ref_check.verified_offline` directly, rather than the current
all-three-always-unnetted default). That keeps `snapshot.py`'s existing
honesty contract (never claim a netting that didn't happen) while letting
it finally report `MEASURED` for a type this tool actually netted cleanly.
