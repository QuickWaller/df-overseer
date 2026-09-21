# Handoff: deploy the building tool, gotchas, labor graph and nobles tool, and verify each live

Date: 2026-09-21. **WRITTEN, gated: dispatch only after the nobles stream has merged** (one stream at a time on VM 103,
and the deploy should carry it; the reaction-extraction stream has merged). **Live stream on VM 103. The fort stays
paused; no unpause is needed or permitted. No real building is built.**

Read `CLAUDE.md` (the deploy trap in its status block), `docs/TRAPS.md`, the
method and write-up of `handoffs/2026-09-19-deploy-batch.md` (the way that
worked, including the `ReadWritePaths` precedent for `series.*`), then the
reports of `2026-09-21-building-tool-lua.md`, `-building-tool-server.md` (the
"what a deploy needs" list), `-graph-labor-for-jobs.md`,
`-extract-remaining-reactions.md` and `-nobles-appoint.md`, then this.

## What is merged and not live

1. `scripts/dfhack/df-overseer-building.lua`, the `enabled-counts` addition to
   `df-overseer-labor.lua`, and `df-overseer-nobles.lua` if its stream merged,
   with `scripts/dfhack/TOOLS.yaml`.
2. `dfmcp/` (gotchas store and tools, confidence loader, enrichment, labor
   join, the changed `server.py`), `gotchas/confidence.yaml`,
   `agents/CONFIDENCE-LEGEND.md`, `agents/*/tools.yaml` and `role.md` changes.
3. The `production/` package (the join imports `production.labors`) and a
   built graph database.

Expected role tool counts on the merged tree, before any later grants:
**architect 34, overseer 57, consultant 14** (nobles included: 2 read commands for architect and consultant, 2 read plus 2 write for overseer; the zone tool's `list-kinds` and `check-owner` are 2 more read for architect and overseer). **Deploy `scripts/dfhack/df-overseer-zone.lua` and `TOOLS.yaml` together**: the new manifest changed the zone grammar, so the deployed old zone script and the new manifest do not match. The old script is currently live. The nobles script `df-overseer-nobles.lua` is already on VM 103 (hash-verified 2026-09-21, byte-identical to main's copy); confirm the hash and leave it.

## Steps, in order

1. **Check what is actually on the VM before deploying**; record the fort's
   pause state and tick (last recorded: year 31, tick 103055, or later if the
   nobles stream changed it).
2. **The skill read.** One bounded, read-only Lua loop over
   `df.job_skill.attrs[i].labor` for every skill (about 100 entries; see the
   untested sketch in the graph report, item 1), written to a JSON file
   `[{"skill": ..., "labor": ...}]` **outside the repo**. Quote the output. A
   skill with no labor is written as absent, never as a guess.
2b. **The generated-reaction read.** The extraction stream found that the 145
   `MAKE_ENT<n> <PART>` reactions (instrument pieces; Craftsdwarfs 100, forges 15,
   glass furnaces 13, Kiln 7, Leatherworks 6, Masons 3, Carpenters 1) exist only in
   the world save, not in any raw file. Read them the same way: a bounded,
   read-only loop over `df.global.world.raws.reactions.reactions`, restricted to
   the ids that are not already in the four vanilla files. Start cheap: code, the
   building it is hosted at, and its skill, which is all `labors_for_kind`
   needs; render as raw tokens into one `reaction_generated.txt` outside the
   repo if the fuller read is cheap. An untested sketch is in section 6 of
   `handoffs/2026-09-21-extract-remaining-reactions.md`. Do not commit the
   output (game data, public repo).
3. **Build the graph database** offline from the real raws and the dump:
   extraction, then `python -m production.labor_ingest DB DUMP_DIR
   --skill-labors skills.json` (dump path in the graph report; it ends in
   journal_mode=DELETE). Report the before and after coverage table.
4. **Deploy** with `git -c core.autocrlf=false archive` from `main`, a sha256
   manifest, verify on arrival and at the installed path, back up anything
   overwritten. Place the graph DB where the server expects it
   (`/var/lib/dfproduction/uniboslan.production.sqlite3`, or set
   `MCP_SERVER_PRODUCTION_DB`), owned so the service user can read it.
5. **Create the gotcha store** (the server refuses to start without it): a
   state directory (`/var/lib/dfgotchas` or `MCP_SERVER_GOTCHAS_DB`), then
   `python -m dfmcp.gotchas_store init <path>` as the service user, and add
   `ReadWritePaths=` for it to the unit (the same hardening as `series.*`; the
   unit example is `infra/dfmcp-server.service.example`, update it too). If
   the classifier refuses a unit change or restart, **stop and report**, do
   not route around it.
6. **Restart `dfmcp-server` only.** Never restart DF or DFHack.

## Verification, each one that could fail

- **Per-role tool lists over a real MCP client**: record the counts and
  reconcile them with the expectation above; say what differs.
- **`building.list-kinds`, `building.find` and `building.build` with DRY_RUN**
  as the overseer for at least a workshop, a furnace and one furniture kind;
  errors for an unknown kind. Confirm the dry run changed nothing (pause state
  and tick identical).
- **`tool_guidance`** appears on a DFHack-backed result (object, array, error).
- **The labor join against the real graph**: `building.find` for the Masons
  workshop returns `operating_labors` partial with STONECUTTER and the reason,
  and a kind the graph does not know returns `labors: null` with a reason,
  never `[]`. This is also the first proof that `production.labors` can open
  the database under the service's `ProtectSystem=strict` (a read-only
  directory); if it fails, report the exact error and the smallest fix.
- **`labor.enabled-counts`** for MASON, STONECUTTER and one bad name (null plus
  an error, never 0).
- **`gotchas.get`** live as each of the three roles (the consultant has no
  write). Test `gotchas.write` and its outcome append against a **temporary
  store copy or a second instance, not the live store**: the store is
  append-only and proposed entries are shown to agents, so a test entry must
  not land in it.
- **Refusals**: the consultant is refused the building tools, with the deny
  reasons from its `tools.yaml`; the architect holds no `building.build`.
- **The nobles tool** (if merged): `list` only, read-only. Do not appoint.

## Rules

- **Do not unpause the fort, do not restart DF or DFHack, do not build
  anything for real.** Never run an unbounded query against the live DFHack
  process. Bound the skill loop.
- SSH as `df`, except where a system unit genuinely needs root, and say where.
  Read secrets by key only. No address, hostname or token in any tracked file.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`. **Commit after each milestone** and extend this doc's
  report as you go. No em dashes in prose.

## Done means

Everything above verified with output quoted, the counts reconciled, the graph
join shown working (or its exact failure reported), the fort still paused at
the recorded tick, the ambient and venv suites unchanged, and a list for the
orchestrator of what the docs now say wrongly (role counts in `CLAUDE.md` and
`ROADMAP.md`).

---

## Report (executor, 2026-09-21, in progress)

Worktree tip at start: `11f4753`. Sessions ran as `df` over key-pinned ssh throughout; every VM command was
one plain `ssh`/`scp` with a literal address (a variable-computed address in a `VAR=$(...)` compound was
refused by the permission classifier as "cannot be shown not to be git", so the address was read once by key
in its own command and typed into each later one; nothing routed around, no address in any tracked file).

### Step 1: what was on the VM, and the fort's state before

- `df-overseer-nobles.lua`: sha256 `5d6ea454...c0aab4` on the VM, equal to the value in the brief. Left alone.
- The VM's `/opt/df/game/hack/scripts/` has no `df-overseer-building.lua`; `df-overseer-zone.lua` (17433 bytes,
  2026-09-18) and `df-overseer-labor.lua` (17924 bytes, 2026-09-18) are the old copies.
- `/opt/df/dfmcp-smoke/` has no `production/` and no `gotchas/` directory; `/var/lib/` has `dfmcp` and
  `dfseries` only (no `dfgotchas`, no `dfproduction`).
- `dfmcp-server`: active.
- Fort, read with one bounded `dfhack-run lua` (pause state, year, tick): **paused, year 31, tick 106974**
  (the nobles stream's supervised unpause moved it from 103055).

### Step 2: the skill read (bounded, read-only)

One Lua loop over `df.job_skill._first_item .. _last_item` (-1 to 148, guarded to at most 400) reading
`df.job_skill.attrs[i].labor`, run with `dfhack-run lua -f` from a `/tmp` copy that was removed afterwards.
Result: 149 skill ids scanned, **68 with a labor, 0 read errors**, the other 81 written as absent (labor -1).
Written out of tree to `skills.json` as `[{"skill","labor"}]`. Examples: MASONRY MASON, CUT_STONE STONECUTTER,
CARVE_STONE STONE_CARVER, BREWING BREWER, CARPENTRY CARPENTER, POTTERY POTTERY, PRESSING PRESSING,
CROSSBOW/BOW/SNEAK/RANGED_COMBAT all HUNT. It adds 22 skills to the 46 the dump had (map size 46 to 68).

### Step 2b: the generated-reaction read

`df.global.world.raws.reactions.reactions` has 304 entries; the ones whose code matches `^MAKE_ENT%d+ ` number
**145**, exactly the count the extraction stream predicted. Each reaction carries `raw_strings`, a vector of the
reaction's own raw tokens (`[BUILDING:CRAFTSMAN:NONE]`, `[REAGENT:...]`, `[PRODUCT:...]`, `[SKILL:BONECARVE]`),
so the fuller read was as cheap as the cheap one: one bounded loop (guard 2000 reactions, 200 lines each)
prints `[REACTION:code]` plus those strings. Rendered to one `reaction_generated.txt` (145 reactions, 2,201
lines, out of tree, CP437 decoded). The extractor reads it with no code change. It reports 435 `unparsed`
lines, all "no open reagent/product to attach to", which is exactly 3 per reaction: `[GENERATED]`,
`[SOURCE_ENID]`, `[MAX_MULTIPLIER]` appear before any reagent. They carry no flow or labor.

### Step 3: the graph database, coverage before and after

Built offline from the real vanilla reaction files, the real building dump and (for the last two rows) the
skill table and generated reactions, with the worktree's `production` code. All three files end in
`journal_mode=DELETE` and pass `integrity_check`.

| build | known | partial | unknown | processes determined | reactions determined |
|---|---|---|---|---|---|
| before: dump only (matches the graph stream's 2/18/13, 129/366) | 2 | 18 | 13 | 129 / 366 | 98 / 293 |
| after the skill read | 5 | 19 | 8 | 177 / 366 | 146 / 293 |
| after the skill read and the 145 generated reactions | 5 | 23 | 4 | 304 / 366 | 273 / 293 |

Kinds, last row: known Fishery, Jewelers, Millstone, Quern, SCREW_PRESS. Unknown Bowyers, Clothiers, Kennels,
SOAP_MAKER, Tool. The other 143 quickfort tokens (furniture and constructions) stay `unknown` by design.
Undetermined processes, last row (62): 39 hard-coded jobs with no table labor, 22 `contradicts_profile`
(20 reactions: 18 at Craftsdwarfs, 2 at the Soap Maker, where the skill's labor is not on the kind's Workers
tab, so the graph refuses to name it), 1 material-dependent. `unextracted_reaction` is 0.
