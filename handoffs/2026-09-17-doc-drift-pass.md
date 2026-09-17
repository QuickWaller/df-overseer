# Handoff: documentation pass, end of 2026-09-17

**Dispatched** 2026-09-17 by the orchestrating session. **Agent:** `executor`,
Sonnet. **User go-ahead:** "lets put a sonnet on updating docs now"
(2026-09-17). **Peer check-in:** no other session on this repo or home-lab.

## Why

Today moved the fort and the toolset a long way and the durable docs lag. The
orchestrating session is near its context budget, so this stream owns the
write-up.

**This stream is the sole writer of `Working.md`, `decisions/DECISIONS.md`,
`ROADMAP.md`, `CLAUDE.md`, `memory/` and `doctrine/` until it finishes** (the
normal handoff rule reserving those for the orchestrator is lifted for this
one stream, because nothing else is running). Do not touch `research/` or any
other stream's handoff doc except to add an index row.

## What happened today (your source list, all already written down)

Read these first, in this order, and take facts from them rather than
re-deriving:

1. `decisions/DECISIONS.md`, all rows dated 2026-09-17. They are the spine.
2. `handoffs/` Results for: `2026-09-17-farm-tools-deploy.md`,
   `2026-09-17-water-source-zone-test.md`,
   `2026-09-17-water-and-industry-tools.md`,
   `2026-09-17-farm-still-first-build.md`,
   `2026-09-17-water-industry-tools-deploy.md`.
3. `research/2026-09-17-founders-not-drinking.md`,
   `research/2026-09-17-pool-reachability.md` (**its CORRECTION note at the
   top overrides the body**), `research/2026-09-17-seed-ratios.md`.
4. `doctrine/seed.yaml` and `docs/TRAPS.md` (both already updated today).

The shape of the day, so nothing important gets lost:

- The fort could not drink because each pond is a sunken basin of 6-7/7 water
  one level below the surface. A `WaterSource` zone **on the water** fixed it;
  dwarves went down and drank, one with no helper at all.
- Farm and still tools were deployed; then the **farm plot was built for real
  and sown to plump helmet in all four seasons**. The still is designated but
  its job is suspended, and the fort owns only 3 logs (the boulders and blocks
  belong to the caravan).
- Zones, tree felling, work orders, well and three more workshops were built,
  merged and deployed. Role tool lists: 19 / 32 / 4.
- Seed economics were researched, with a figures table ready for a database.
- Game knowledge moved out of the register into `doctrine/seed.yaml`, and a
  `ROADMAP.md` item exists for a game-figures database with calculators.

## Do

1. **`Working.md`.** Make "START HERE" true as of tonight: what is done, what
   is in flight (nothing is running when you start), and the next concrete
   steps, which are: clear the still's suspended job; fix
   `df-overseer-farm.lua`'s two live bugs (crop wiped when the plot finishes
   building, and the nonexistent `dfhack.buildings.setName` hidden by an
   unchecked `pcall`); teach `df-overseer-diggable.lua` to propose a dig two
   levels down so the fort can reach stone (today it returns nothing at z167,
   which blocks blocks, mechanisms and the well); then a longer supervised run
   for planting and the still. Remove anything now false (the fort has drink;
   the farm tools are deployed; the founders-not-drinking investigation is
   answered). **Apply the archive-cadence rule** in `CLAUDE.md`: the file is
   already about 480 lines, so move finished sections wholesale into
   `working-archive/Working_archive-2026-09-14.md` (or the right week file),
   leaving one-line pointers. Do not summarise or delete them.
2. **`ROADMAP.md`.** Update the Now bucket: the production gap is partly
   closed. One line per item, pointers not narration. Bump
   `**Last reviewed:**` with a one-sentence note of what this pass changed.
   Check whether the existing "game figures database and calculators" Next
   item and the wiki-lookup item still read correctly.
3. **`CLAUDE.md`.** The status block was updated mid-day and is now behind
   again (it says the fort still owes food, with no farm plot). Keep it short:
   what the fort is, where it stands tonight, what to read first. Mention that
   `doctrine/` exists and what it is for.
4. **`memory/`.** Add what is durable and not derivable from code: the zone
   fix for sunken ponds, the well's real requirements (BLOCKS, BUCKET, CHAIN,
   TRAPPARTS; buildable on EMPTY or RAMP_TOP bordering floor), and the DFHack
   API facts learned today. Follow the memory scope rule: one file's job is its
   one-line description in `memory/MEMORY.md`; split on scope drift, and update
   `MEMORY.md`'s index. Check `memory/dfhack-environment.md` first, since most
   of this belongs there.
5. **`handoffs/INDEX.md`.** Confirm every 2026-09-17 row exists and its status
   is right; add a row for this stream.
6. **`agents/quartermaster/`.** Its `blocked_on` line says there is no tool for
   manager work orders; `df-overseer-orders.lua` now exists and is deployed.
   Correct that line only, nothing else about the role.
7. **`doctrine/seed.yaml`.** Leave the entries alone unless something in the
   sources contradicts one. If you add anything, keep the existing shape
   (scope, status, source) and say why in your Result.

## Constraints

- **Documentation only. No code, no VM access, no deploy, no fort reads.**
- **Do not invent facts.** Every number you write must come from the sources
  above; where they disagree, prefer the later row and say so. If something is
  unverified, keep it marked unverified, especially the wiki-sourced figures in
  the seed research.
- **No em dashes** in prose (house style).
- Repo is public: no hostnames, addresses, tokens, or anything from `.env` or
  `infra/local.*`.
- Suites must still pass if you touch anything they read: ambient **294
  passed, 1 skipped**, `.venv-dfmcp` `dfmcp/tests` **165**. Docs-only changes
  should not move them; run them once at the end and report.
- **Commit** your work in small, clearly-named commits on `main` (this stream
  is the only writer, so a worktree would only add a merge step). **Do not
  push.**

## Touched surfaces

`Working.md`, `working-archive/`, `ROADMAP.md`, `CLAUDE.md`, `memory/`,
`handoffs/INDEX.md`, `agents/quartermaster/role.md` (one line),
`doctrine/seed.yaml` (only if contradicted), this doc.

## Report back

What you changed per file, in one line each. Anything in the sources that
contradicted itself and how you resolved it. Anything you found stale that the
brief did not name. The test counts. Your commit hashes.

## Result

**Status: done.** Documentation only; no code, no VM access, no deploy, no
fort read. Read the source list in the order given, then wrote all six
surfaces named above plus this doc. Six commits on `main`, small and named,
no push.

**Per file:**
- `Working.md`: archived the whole `## HANDOVER 2026-09-16` section wholesale
  (file was 505 lines, over the ~400 threshold) to
  `working-archive/Working_archive-2026-09-14.md`, and wrote a fresh
  `## HANDOVER 2026-09-17` with tonight's true state (drink solved via a
  `WaterSource` zone, farm plot built and sown, still designated but stuck,
  water/industry tools deployed at 19/32/4), a `START HERE` matching the
  brief's four next steps, and every still-open item from the archived
  section carried forward rather than lost. Also fixed two smaller stale
  facts in the untouched top section: the queue bullet's "fort is paused, the
  clock is not moving" (it has been unpaused several times since) and the
  ambient/`.venv-dfmcp` test counts (276/152 to 294/165).
- `working-archive/Working_archive-2026-09-14.md`: received the archived
  section verbatim (exact `sed` extraction, not retyped), with a one-line
  header saying what moved and when.
- `ROADMAP.md`: added an `UPDATED 2026-09-17` note atop the 2026-09-16
  production-gap `Now` item saying it is partly closed (drink, farm plot,
  19/32/4 tools; still/depot/stockpiles/deeper-digging still open), original
  text kept below it per this file's own convention. Bumped `Last reviewed`
  with a one-sentence note; checked the game-figures-database and wiki-lookup
  `Next` items and both still read correctly, untouched.
- `CLAUDE.md`: rewrote the two stalest status bullets (the fort no longer
  owes food alone with "no farm plot"; role tool lists to 19/32/4; the
  `doctrine/` mention already present, left as-is) and bumped the two test
  counts in the traps block to 294/165.
- `memory/dfhack-environment.md`: added a dated block (`ADDED 2026-09-17`)
  under "Game-side facts": `zone.lua`'s `is_valid_zone_tile` is hidden-only,
  so a zone can sit directly on water; the well's real requirements and
  buildable-tile shape; a cautionary note that an initial live
  `getWalkableGroup`/ramp-miscategorisation claim was itself wrong on a
  closer re-check; the water/drink and manager-work-order `df.job_type`
  enum values; `getFiltersByType`'s generic building-material filter across
  every workshop kind; `getNoblePositions` for checking a Manager
  appointment. `memory/MEMORY.md`'s one-line description for that file still
  covers all of this (verified versions/facts about the environment), so no
  index edit was needed.
- `handoffs/INDEX.md`: confirmed all five 2026-09-17 rows already present and
  accurate against their own Result sections; added a row for this stream.
- `agents/quartermaster/role.md`: corrected only the named line.
  `df-overseer-orders.lua` now exists and is deployed for manager work
  orders; left the stockpile-settings half of the claim (still true, no
  tool) and the rest of the role's rationale and enablement decision
  untouched, per the brief's explicit "nothing else about the role."
- `doctrine/seed.yaml`: read in full, checked against all three research
  docs and the register. **Nothing added or changed.** Every entry (seed
  break-even, cooking-costs-seeds, water-source-zone-for-ponds, etc.) is
  either already `verified` against exactly what today's sources confirm, or
  correctly still `prior`/unverified where the sources themselves say a
  figure is unconfirmed (e.g. milling/thread seed-return counts). No
  contradiction found.

**Contradiction found and resolved (the one real catch this pass made):**
the `farm-still-first-build` handoff's own Result section reports "15 free
wood / 3 free boulders / 4 free blocks" as available material for the still,
and my first draft of `Working.md`/`CLAUDE.md` repeated that figure. Reading
`decisions/DECISIONS.md` row 331 (dated the same day, later in sequence)
against it found the register's own correction: those boulders, blocks and
most of that wood carry `flags.trader` and belong to the caravan, not the
fort. **The fort actually owns 3 logs and nothing else buildable.** Per the
brief's own rule ("where they disagree, prefer the later row and say so"),
fixed both files to the corrected figure in a follow-up commit, and also
corrected a `START HERE` line that had claimed the well "currently has just
enough material" (it does not: 0 of the BLOCKS and TRAPPARTS it needs are
fort-owned).

**Stale facts found that the brief did not name:** the queue bullet's frozen
"clock is not moving" framing in `Working.md`'s untouched top section, and
that section's own pre-today test counts (both listed above, both fixed).

**Test counts, run live at the end, not assumed:** ambient `python -m
pytest` → **294 passed, 1 skipped**; `.venv-dfmcp/Scripts/python.exe -m
pytest dfmcp/tests` → **165 passed**. Both match the figures already written
into the docs above; docs-only changes did not move either number.

**Commits, all on `main`, none pushed:**
- `c8af686` docs: rewrite Working.md START HERE for 2026-09-17
- `305f904` docs: update ROADMAP Now item for the partly-closed production gap
- `28f6aad` docs: refresh CLAUDE.md status block for 2026-09-17
- `841ed6b` docs(memory): record today's DFHack facts
- `717d82c` docs: fix a stale material claim caught cross-checking DECISIONS.md
- `193cda3` docs: add doc-drift-pass index row, fix quartermaster's stale blocked_on line
- (this doc's own Result, committed after) `docs: add Result to the doc-drift-pass handoff`

**Not done, deliberately:** no `decisions/DECISIONS.md` row for this stream
itself (no new decision was made, only documentation corrected; the touched
surfaces list in this doc doesn't name the register either). No em dashes
introduced in any new prose (checked with `git diff | grep —` after every
edit); the pre-existing em dashes in `Working.md`'s untouched archived-list
section are original content, not this stream's.
