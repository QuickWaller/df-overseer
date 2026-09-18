# Handoff: close the two worst lever gaps (bucket order, stockpile read)

Date: 2026-09-18. Stream 1 of 3 from the production-model design pass.
**Read `docs/PRODUCTION-MODEL.md` first**, especially §13 (the lever
catalogue), §12 (water) and §8 (stockpile occupancy). That file is the spec;
this handoff is scope and sequence only.

## Why this stream exists

The design produces ten named diagnoses and only four of them have a tool
that can act on the fix. This stream converts two of the six dead ones into
live ones. One of them is not theoretical: **a citizen of Uniboslan is
unconscious right now, the fort owns no bucket, and a "Give water" job was
cancelled for want of one** (announcement id 104, tick 214135). No existing
tool can make a bucket.

## Deliverable 1: `orders.create` learns more jobs

`scripts/dfhack/df-overseer-orders.lua` currently accepts
`blocks/mechanisms/barrels/brew_drink` only. Add at minimum **`bucket`**, and
while you are in there add the other jobs this fort plausibly needs soon:
`bed`, `door`, `table`, `chair`, `splint`, `crutch`, `soap`. Use your
judgement on the exact set; justify what you add and what you leave out in
the handoff write-up.

- Follow the file's own existing pattern for job construction. Do not invent a
  second mechanism alongside it.
- `DRY_RUN` defaults to `true`, as every write tool here does. Keep that.
- The `manager_appointed` field is reported on every call and is not enforced
  as a refusal. Leave that behaviour alone; it is a deliberate decision
  (`decisions/DECISIONS.md`).
- Verify each new job actually constructs a valid `manager_order` on the live
  install via **dry run**, and report what the dry run returned per job. A job
  name that silently produces a malformed order is the failure mode to catch.

## Deliverable 2: a stockpile read tool

New file `scripts/dfhack/df-overseer-stockpile.lua`, read-only, two commands:

**`stockpile list`** — every stockpile with: its id, a landmark-relative name,
**occupied tiles over total tiles** (see below), and what it accepts at a
coarse level.

**`stockpile links ID`** — the give/take links for one stockpile or workshop,
from `building_stockpilest.links.{give,take}_{to,from}_{pile,workshop}` and
`building.profile.links`. The live audit confirmed these are exact and that
Uniboslan's two stockpiles are entirely unlinked (all four vectors 0).

**Report occupied tiles over total tiles, NOT percentage of capacity.**
Per-tile capacity depends on what container sits there, and that figure is not
established anywhere (see `research/2026-09-18-production-figures.md`).
Claiming "% full" with an unknown denominator is exactly the false precision
this project forbids. If you cannot read tile occupancy exactly, say so and
report what you *can* read, rather than substituting an estimate.

This is one of the very few **leading** indicators in the whole design: a
stockpile at 80% and rising predicts a backed-up workshop before it happens.
That is why it is worth a tool of its own.

## Rules that apply to both

- **`knowledge_scope` is mandatory** in `TOOLS.yaml` for every command
  (`player_visible` / `player_derivable`; `omniscient` is refused at load
  time). Stockpile contents and links are player-visible. Do not report
  anything from a hidden tile: reuse `df-overseer-stocks.lua`'s
  `is_on_hidden_tile` check rather than reinventing it.
- **Never return a coordinate.** Landmark names, ids and counts only. This is
  the project's hardest commitment (`docs/PURPOSE.md` #1).
- Register both in `scripts/dfhack/TOOLS.yaml` and add allowlist entries:
  `stockpile.*` reads to architect, overseer and quartermaster; the new
  `orders.create` jobs need no new allowlist entry, but update the existing
  entry's note. Update the pinned role counts in `dfmcp/tests/test_roles.py`
  if they change.
- Deploy to VM 103 when the code is verified: `git -c core.autocrlf=false
  archive` (this workstation's `autocrlf=true` otherwise ships CRLF and breaks
  hash checks). Restart `dfmcp-server.service` and confirm the new commands
  resolve live.
- **The fort must stay paused.** Check `dfhack.world.ReadPauseState()` before
  and after and report both. Dry runs only: **do not create a real order, do
  not build anything, do not unpause.** The live fort action is a separate
  stream that runs after yours.
- Ambient `python -m pytest` is 306 passed / 1 skipped before you start. Run
  `dfmcp/tests` in `.venv-dfmcp` too. Report both counts before and after.
- Read secrets by the key you need: `grep -E '^KEY=' .env`, never `cat .env`.
- If a harness, hook or classifier refuses you, **stop and report it.** Do not
  reword the command to get past it.
- Do **not** write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`. The orchestrating session owns those.
- No em dashes in prose.

## Touched surfaces

`scripts/dfhack/df-overseer-orders.lua`,
`scripts/dfhack/df-overseer-stockpile.lua` (new),
`scripts/dfhack/TOOLS.yaml`, `agents/*/tools.yaml`, `dfmcp/tests/`, VM 103
deploy, this handoff doc.

## Done means

Both tools deployed and live-resolving on VM 103, every new order job dry-run
verified individually, stockpile list and links returning real values for
Uniboslan's two stockpiles, tests green, fort still paused at the tick you
started from, and a write-up at the bottom of this file saying what you
verified and how.

## Result

**Status: done.** Both tools deployed and live-verified on VM 103; fort
untouched throughout, paused on the same tick before and after.

**Correction received mid-stream, from the orchestrator, addressed before
building anything further:** this handoff's own "why" section ("the fort
owns no bucket... unconscious citizen") is wrong. Live, fort paused at tick
227160: 5 buckets exist, 3 fort-owned (ids 81, 149, 150), empty, unforbidden,
unclaimed. The "unconscious citizen" is a sleeping miner
(`unconscious=2, pain=0, wounds=0, job=Sleep`), not an injury -- no medical
emergency. The sharper framing: a metalcrafter DID cancel "Give water: Need
empty bucket" at tick 214135 (real, still the motivating incident), but with
3 owned buckets sitting unclaimed, that is an availability/reachability
failure, not an absence -- exactly what this stream's stockpile-links half
helps diagnose. Recorded in `df-overseer-orders.lua`'s own header comment,
not just here, so the wrong framing does not resurface from the code later.
Deliverable 1 itself is unaffected: `orders.create`'s four-job vocabulary was
a real, independent gap named by `docs/PRODUCTION-MODEL.md` §13's lever
table regardless of the bucket incident.

### Deliverable 1: `orders.create`'s job vocabulary

Added **bucket, bed, door, table, chair, splint, crutch, soap** (8 jobs, on
top of the existing blocks/mechanisms/barrels/brew_drink). Left out
**MAKE_SOAP_FROM_OIL** (soap's other reaction) deliberately -- tallow is a
byproduct this fort's existing butchering already produces; oil needs a
press workflow that does not exist yet, and the handoff's own list did not
ask for a second soap variant. Also considered and left out: `quern`/
`millstone` (Craftsdwarf-adjacent, not named in the handoff and not tied to
a live gap), and the two "Construct*" jobs that are the *hospital-use* side
of splints/crutches (`BringCrutch`/`ApplyCast`, job types 207/208) -- those
apply an already-made item to a patient, a different action from
manufacturing one, and out of scope for a manager work order.

Every job name/id was read live off this install's own `df.job_type` enum,
not guessed: bucket=126 MakeBucket, bed=69 ConstructBed, door=67
ConstructDoor, table=72 ConstructTable, chair=70 ConstructThrone (DF's own
internal name for the chair job/item pair -- no job_type name contains
"Chair" at all on this install), splint=203 ConstructSplint, crutch=204
ConstructCrutch, soap=209 CustomReaction + reaction_name=
MAKE_SOAP_FROM_TALLOW (live-confirmed present in
`world.raws.reactions.reactions`' own `code` field, plus a live-discovered
custom `SOAP_MAKER` workshop in `world.raws.buildings.all`/`.workshops`,
resolved by code at call time in `workshop_exists_count`, not a hardcoded
index).

**WORKSHOP_SUBTYPE confidence, stated honestly per job** (informational
only -- never gates order creation): bed is verified (wood-only in vanilla
DF); soap's Custom/SOAP_MAKER workshop is live-confirmed present.
door/table/chair/bucket default to Carpenters as a single informational
value, though vanilla DF allows building each of stone or metal too -- an
alternate-material build is invisible to this count. splint/crutch's real
workshop could not be found in any live-queryable table (no
`permitted_reaction_id`-style data exists for non-custom workshops on this
install) so Carpenters there is wiki-level domain knowledge, not a live
read.

**Dry-run results, each via `dfhack-run df-overseer-orders create JOB 1`,
fort never mutated:**

| Job | would_queue.job | reaction | workshop_exists |
|---|---|---|---|
| bucket | MakeBucket | - | 0 |
| bed | ConstructBed | - | 0 |
| door | ConstructDoor | - | 0 |
| table | ConstructTable | - | 0 |
| chair | ConstructThrone | - | 0 |
| splint | ConstructSplint | - | 0 |
| crutch | ConstructCrutch | - | 0 |
| soap | CustomReaction | MAKE_SOAP_FROM_TALLOW | 0 |
| brew_drink (regression check) | CustomReaction | BREW_DRINK_FROM_PLANT | **1** (the fort's one Still) |

All 8 new jobs plus the 4 pre-existing ones report `dry_run: true`,
`manager_appointed: false` (unchanged finding: no citizen holds the MANAGER
position). An unknown job name (`nonsense_job`) was correctly refused,
listing all 12 known jobs alphabetically -- proof of a real allowlist, not a
silent no-op, and proof the live code is the new code (the old vocabulary
could not have named 12 jobs). `orders list` read `{manager_appointed:
false, orders: []}` after every dry run -- confirms nothing was actually
queued.

### Deliverable 2: `df-overseer-stockpile.lua` (new)

Two read-only commands, `list` and `links ID`, both `knowledge_scope:
player_visible`.

**`stockpile list`, live values for Uniboslan's two real stockpiles:**

| id | near_landmark | occupied_tiles | total_tiles | accepts |
|---|---|---|---|---|
| 1 | Stockpile #1 (S, 0) | **24** | 25 (exact) | food, furniture, stone, wood, finished_goods, bars_blocks |
| 2 | Stockpile #2 (S, 0) | **7** | 25 (exact) | food, furniture, stone, wood, finished_goods, bars_blocks |

Per the handoff's own instruction, this is **occupied tiles over total
tiles, not a percentage** -- per-tile capacity is unestablished
(`research/2026-09-18-production-figures.md`). `total_tiles` is exact:
walked `dfhack.buildings.containsTile` per tile (not the opaque
`countExtentTiles` int) so each tile also gets the hidden-tile filter;
confirmed to agree with `countExtentTiles(bld, 0)` independently (25 both
ways, both piles). `occupied_tiles` is **not** the raw item count (pile 1
holds 33 items, pile 2 holds 8) -- it is the count of *distinct* (x,y,z)
positions those items resolve to, since a bin or a stack puts several items
on one tile; pile 1's 33 items resolved to exactly 24 distinct tiles, live.
Both piles read 0 hidden tiles (an honest, unsurprising result for the
fort's own built stockpiles, not assumed).

`accepts` reads `building.settings.flags`, confirmed live to be exactly
DF's own 17 top-level stockpile-category toggles (no more, no fewer,
enumerated by string key) -- the "coarse level" the handoff asked for, not
the deep per-subtype filter.

**`stockpile links ID`, live for both piles, the one workshop, and two
refusal cases:**

- id 1 (stockpile), id 2 (stockpile): all four link vectors (`give_to_pile`,
  `take_from_pile`, `give_to_workshop`, `take_from_workshop`) count 0,
  resolved true -- **confirms the live audit's own finding that Uniboslan's
  two stockpiles are entirely unlinked.**
- id 5 (the fort's one Workshop, the Still): resolved `kind: "workshop"` via
  `building.profile.links`, same four-vector empty result.
- id 99999 (nonexistent): refused `"no building with id 99999"`.
- id 4 (the fort's one real FarmPlot, a valid building id of the wrong
  kind): refused `"id 4 is not a stockpile or workshop (FarmPlot)"`.

What a **non-empty** link vector resolves to (a usable building pointer,
per `research/2026-09-18-schema-extraction-live.md` §5's own working
assumption) is **not independently exercised live**, since nothing on this
fort is linked yet -- `resolve_link_target` is written defensively (pcall
throughout) and marks an entry `resolved: false` rather than guessing if
that assumption is ever wrong. Flagged, not silently trusted.

### Registration

`scripts/dfhack/TOOLS.yaml`: new `df-overseer-stockpile.lua` block (both
commands), `orders.create`'s note extended for the 8 new jobs,
`live_deployed`/`verified` fields filled in with real live results for all
5 affected commands (3 in orders.lua, 2 in stockpile.lua).

`agents/architect/tools.yaml` and `agents/overseer/tools.yaml`: both granted
`stockpile.list`/`stockpile.links` as reads. Overseer's `orders.create` note
updated to list the 8 new jobs (per the handoff's own instruction -- no new
allowlist entry needed since `orders.create` was already granted).

`agents/quartermaster/tools.yaml` (**new file**, a judgment call): the
handoff names quartermaster alongside architect/overseer for the
`stockpile.*` grant, but that role has **no** `tools.yaml` today --
`role.md` line 4 says so explicitly: "No `tools.yaml` or `model.yaml` yet,
deliberately: writing an allowlist of tools that do not exist would imply a
capability this project does not have." That reasoning does not block this
grant, since `stockpile.list`/`stockpile.links` now genuinely exist and are
deployed -- so I created a minimal `tools.yaml` (just the two stockpile
reads) rather than skip the handoff's instruction. **`role.md` line 4 is now
stale** (a file outside this stream's touched surfaces) -- flagged here for
the orchestrator to correct, not fixed by me. The role stays `enabled: false`
in `agents/ROSTER.yaml`, untouched by this stream; enabling it is a bigger
decision than one tool grant.

**No pinned role-tool-count test exists** in `dfmcp/tests/test_roles.py` to
update -- grepped the file for one (the only similar precedent I could find
was narrative counts in past handoffs' own Result sections and in
CLAUDE.md's status block, not a code assertion). The handoff's instruction
to update it does not apply; judged as the one thing in the handoff that
doesn't hold up against the actual repo state. The real per-role tool
counts (see Deploy below) are the durable record instead.

### Deploy to VM 103

Read live pre-deploy: fort paused, tick **227160**. Services `dfmcp-server`,
`df-fortress`, `df-xvfb` all active; `df-fortress` `ActiveEnterTimestamp`
2026-09-16 10:44:08 UTC, `df-xvfb` 2026-09-11 02:26:46 UTC (both recorded
before touching anything, to prove afterward they weren't touched). Live
per-role `tools/list` captured over a real MCP client
(`mcp.client.streamable_http.streamable_http_client` +
`mcp.client.session.ClientSession`, run from this workstation directly
against the VM's bound address, role tokens read from
`/opt/df/dfmcp-smoke/.env` by key via `grep`, never printed):
**architect 21, overseer 34, consultant 4** -- exactly CLAUDE.md's own
cited baseline.

**Expected after-state, computed locally** from this branch's `HEAD` via
`load_registry(native_tools=NATIVE_TOOLS)` → `load_roster(reg)` →
`tool_definitions(reg, roster, role)` (the exact function
`dfmcp/server.py`'s `_on_list_tools` calls), `.venv-dfmcp`: **architect 23
(+2: `stockpile__links`, `stockpile__list`), overseer 36 (+2, same two),
consultant 4 (unchanged)**. Confirmed the before-set is a proper subset of
the after-set for architect and overseer (nothing dropped).

**Deployed via `git -c core.autocrlf=false archive HEAD` of the 6 changed
files** (`scripts/dfhack/df-overseer-orders.lua`,
`scripts/dfhack/df-overseer-stockpile.lua`, `scripts/dfhack/TOOLS.yaml`,
`agents/architect/tools.yaml`, `agents/overseer/tools.yaml`,
`agents/quartermaster/tools.yaml`), sha256 manifest built locally from the
archive's own extracted content (not the working tree, to catch any
autocrlf drift), `sha256sum -c` on the VM immediately after extraction (all
6 OK), then re-hashed a second time at each file's final installed path --
both checks matched the manifest exactly for all 6 files. Backed up
everything about to be overwritten to
`/opt/df/deploy-backup-2026-09-18-lever-gap/` first (2 files existed to back
up -- `df-overseer-orders.lua`, `agents/architect/tools.yaml`, plus
overseer's/TOOLS.yaml's prior copies; `df-overseer-stockpile.lua` and
`agents/quartermaster/tools.yaml` were new, nothing to back up). Ownership
`df:df` on every deployed file (both target directories are already
`df:df`, confirmed before touching either -- no `sudo` needed for any file
operation, only for the service restart).

**Restart:** `dfmcp-server` only, via `sudo systemctl restart`. `NRestarts:
0`, `ActiveState: active`, `SubState: running`, journal clean (uvicorn back
up within 1 second of the stop, no errors or tracebacks). `df-fortress`/
`df-xvfb` `ActiveEnterTimestamp` both unchanged from the pre-deploy read --
neither was ever touched.

**Live per-role `tools/list` after restart, same real MCP client -- exact
match to the locally computed expected state, byte for byte:** architect 23,
overseer 36, consultant 4, every name identical to expected (including
`stockpile__list`/`stockpile__links` present on architect and overseer,
absent from consultant as intended; quartermaster does not appear at all,
correctly, since it stays `enabled: false`).

**How the running code was proven to be the new code:** `df-overseer-
stockpile.lua` is a brand-new file with no prior deployed copy under any
name, so no reqscript cache could apply to it by construction. For
`df-overseer-orders.lua` (redeployed, not new): its only `reqscript`
dependency is `workorder.lua`, unchanged this stream, so the cache-
invalidation question doesn't apply -- the direct proof used instead is the
dry-run sweep itself: `create bucket 1` (etc.) resolving correctly, and
`create nonsense_job 1` listing all 12 known jobs in its refusal, is
something the pre-deploy code (4-job vocabulary) could not have produced.

**Cleanup:** all `/tmp` payload files (tarball, manifest, deploy script,
throwaway MCP client) deleted on the VM, checked by directory listing
after -- only pre-existing, unrelated files remain
(`drinktest.log`, `regionpops_full.txt`, systemd private dirs). No
hostnames, addresses or tokens appear in this document or in any file this
stream leaves behind; the LAN bind address and role tokens seen while
building the live MCP client were read into shell/env variables only.

**Fort paused tick before and after -- identical:** `true`, `cur_year_tick`
**227160**, both before this stream touched anything and after every dry
run and read above. This stream never called `SetPauseState` and created no
real manager order.

**Tests, before and after (both suites, unchanged throughout):** ambient
`python -m pytest` **306 passed, 1 skipped**; `dfmcp/tests` under
`.venv-dfmcp` **165 passed**.

**Verified by execution:** all 6 file hashes at final installed paths; per-
role live `tools/list` before and after, exact, over a real MCP protocol
round-trip; `dfmcp-server` health/restart-count/journal; `df-fortress`/
`df-xvfb` untouched (`ActiveEnterTimestamp` unchanged); all 12 order dry
runs plus the unknown-job refusal and the `orders list` post-check; both
stockpile reads against real values, plus the 4 refusal/edge cases above;
fort pause state and tick unchanged before/after.

**Verified only by mechanism (source read, not exercised live):** the real
(non-dry-run) `create_orders` mutation path for any of the 8 new jobs (by
design -- mutation forbidden this stream); `resolve_link_target`'s
assumption about non-empty link vector contents (nothing on this fort is
linked to exercise it against).

**Not done, deliberately:** no real `orders.create`/`cancel` mutation, no
unpause, no `df-fortress` restart, no fix to `agents/quartermaster/role.md`
(outside touched surfaces, flagged above instead). Those are the
orchestrator's or a later stream's to route.

**Touched surfaces, confirmed against what was actually edited:**
`scripts/dfhack/df-overseer-orders.lua`, `scripts/dfhack/df-overseer-
stockpile.lua` (new), `scripts/dfhack/TOOLS.yaml`, `agents/architect/
tools.yaml`, `agents/overseer/tools.yaml`, `agents/quartermaster/
tools.yaml` (new -- within the `agents/*/tools.yaml` glob), VM 103 (the 6
files above plus a service restart), this handoff doc. No file outside this
list was edited.
