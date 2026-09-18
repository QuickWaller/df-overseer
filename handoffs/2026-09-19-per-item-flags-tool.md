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
