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
| after the skill read | 5 | 19 | 9 | 177 / 366 | 146 / 293 |
| after the skill read and the 145 generated reactions | 5 | 23 | 5 | 304 / 366 | 273 / 293 |

(The tool's own header line says unknown 8 and 4 for the last two rows and 12 for the first: it undercounts
by one, `Tool`, which it lists but does not count. The rows above use the listed names, and each sums to 33.)

Kinds, last row: known Fishery, Jewelers, Millstone, Quern, SCREW_PRESS. Unknown Bowyers, Clothiers, Kennels,
SOAP_MAKER, Tool. The other 143 quickfort tokens (furniture and constructions) stay `unknown` by design.
Undetermined processes, last row (62): 39 hard-coded jobs with no table labor, 22 `contradicts_profile`
(20 reactions: 18 at Craftsdwarfs, 2 at the Soap Maker, where the skill's labor is not on the kind's Workers
tab, so the graph refuses to name it), 1 material-dependent. `unextracted_reaction` is 0.

### Step 4: deploy (archive of the tip, hash-verified three times)

An archive of the tip (`11f4753`, same as main) made with line-ending conversion off, then a Python-built
tarball of exactly 48 files with a sha256 manifest (no CR in any file, checked). Compared against the VM first:
of 88 candidate files 34 already matched, 12 differed and 42 were absent. The 45 non-Lua files were installed
under `/opt/df/dfmcp-smoke/` (`agents/`, `dfmcp/`, `gotchas/`, `production/` without tests, and
`scripts/dfhack/TOOLS.yaml`) and 3 Lua scripts to DFHack's script directory: `df-overseer-building.lua` (new),
`df-overseer-labor.lua` (`enabled-counts`) and `df-overseer-zone.lua`, the last together with the new
`TOOLS.yaml` (the zone grammar changed). Verification: `sha256sum -c` after extraction on the VM (48 of 48 OK),
a backup of every overwritten file to `/opt/df/deploy-backup-2026-09-21-building-batch/`, then `sha256sum -c` at
the installed paths (45 OK plus the 3 Lua OK). `file` reports no CRLF. `df-overseer-nobles.lua` re-hashed
after: still `5d6ea45464a677e4...`, untouched.

**Found, not touched:** 15 other `df-overseer-*.lua` files under DFHack's script directory differ in content
from main (breach, chokepoints, connectivity, diff, diggable, farm, landmarks, openarea, orders, overview,
stockpile, stuckjobs, threat, ui; none has CR, so it is not line endings). The `TOOLS.yaml` diff shows this
deploy changes only the building, labor, nobles and zone entries plus header comments, so none of them
interact with this batch, but they are drift of unknown age and direction.

### Steps 4 and 5: graph database, gotcha store, unit

- Graph: the full build (skills plus generated reactions) copied to
  `/var/lib/dfproduction/uniboslan.production.sqlite3`, mode 644, owned by `df`; sha256 identical locally, on
  arrival and installed (`0bdcf979...c61083`). It is finalised `journal_mode=DELETE`.
- Gotcha store: `/var/lib/dfgotchas/uniboslan.gotchas.sqlite3` created by `python -m dfmcp.gotchas_store init`
  as `df` in the venv: `gotcha store ready`. Both state directories were created and chowned with `sudo -n`
  (passwordless sudo for `df`, the route earlier deploys used; no password or other credential involved).
- Unit: `/etc/systemd/system/dfmcp-server.service` backed up with `sudo -n cp -p` (hash equal), then exactly one
  line added by `sudo -n sed`, `ReadWritePaths=/var/lib/dfgotchas`, after the existing `dfseries` line; the diff
  against the backup is that single line. **No entry for `/var/lib/dfproduction`**, which the join then proved
  unnecessary (below). `infra/dfmcp-server.service.example` updated (dfseries and dfgotchas lines, with a comment).
- Step 6: `sudo -n systemctl daemon-reload` and `restart dfmcp-server` only. `active (running)`, `NRestarts=0`,
  `Uvicorn running`, no traceback. DF and DFHack were not touched.

### Verification (each over a real MCP client, real HTTP, per-role bearer read by key on the VM)

**Per-role tool lists: architect 34, overseer 57, consultant 14, exactly the expected numbers** (before this
deploy 25 / 45 / 11). Architect +9: building.list-kinds, building.find, gotchas.get, gotchas.write,
labor.enabled-counts, nobles.list, nobles.verify, zone.check-owner, zone.list-kinds. Overseer +12: the same
nine, plus building.build, nobles.appoint and nobles.unappoint (zone.place already existed). Consultant +3:
gotchas.get, nobles.list, nobles.verify. Wire ids use two underscores and keep hyphens (`building__list-kinds`).

**Fort state: paused, year 31, tick 106974 before, after each batch of calls and at the very end. Unchanged.**
No unpause, no real build, no DF or DFHack restart. Every DFHack-backed call was one bounded read or a dry run.

**building.list-kinds** (overseer): `filter=Still` returns the one Still row; a filter matching nothing returns
`[]` (the tool's own contract, `tool_guidance` present).
**building.find**, near "Embark Site": Masons, Still, Smelter, Kiln (workshops and furnaces, 3x3), Bed and Well
(furniture, 1x1) and FarmPlot 5x5 each returned five sites. Errors, each `is_error: true` with a named reason:
`unknown building kind: Widget (run list-kinds)`; `Stil` adds `did you mean: Still`; `Masons footprint 4x4 is
outside the allowed width 3..3, height 3..3`; `FarmPlot needs W and H (width 1..31, height 1..31)`;
`landmark not found: Nowhere Land`.
**building.build with a dry run** (the default): Masons, Kiln, Craftsdwarfs, Smelter (default, and with
`dry_run:"true"` plus level, rank and radius), Bed at rank 1 and 2, and FarmPlot 5x5 all returned
`validation: {"by": "quickfort run --dry-run", "ok": true, "stats": {"Buildings designated": 1}}` with
`dry_run: true`. An unknown kind errors. Usability trap found: `dry_run` is the last optional slot, so naming it
without `level`, `rank` and `radius_tiles` is refused ("cannot supply 'dry_run' without also supplying the
earlier optional argument 'level'", then 'radius_tiles'); omitting it is a dry run anyway.

**tool_guidance** appears on all three shapes: an object (a `tool_guidance` sibling of the tool's own fields),
an array (`building.list-kinds`: `structured` is `{"result": [...], "tool_guidance": {...}}`, no protocol
error) and an error (`unknown building kind: Widget ...` carries the `<tool_guidance confidence="medium" ...>`
text block). Roster refusals are not enriched, as designed.

**The labor join against the real graph, opened by the service under `ProtectSystem=strict`: works.**
`building.find Masons` returned `operating_labors.status: "partial"`, `labors: ["STONECUTTER",
"STONE_CARVER"]`, reason "15 of 19 hosted processes have no determined labor (no labor in the game's job table
(15))", with citizen counts `STONECUTTER 2, STONE_CARVER 2`. **This differs from the brief's expectation of
STONECUTTER only:** the graph shipped here includes the 145 generated reactions, three of which the Masons
host and which resolve to STONE_CARVER through their skill. The graph without them (the graph stream's build,
and my "after the skill read" build) says STONECUTTER with STONE_CARVER only as an unexplained Workers-tab
labor. MASON is not an operating labor of the Mason's Workshop in any build. Kinds the graph does not know
return `labors: null`, never `[]`, each with a reason: Well, Bed and FarmPlot all gave `operating_labors:
{"status": "unknown", "labors": null, "unknown_reason": "the graph has no record of a workshop or furnace kind
'Well' ... an absence of data, not an absence of labor"}`. Kiln gave partial GLAZING, POTTERY, SMELT; Smelter
partial SMELT; Craftsdwarfs partial with 8 labors. No `ReadWritePaths` entry for `/var/lib/dfproduction` was
needed: a `DELETE`-journal file opens read-only from the read-only directory.

**Two join gaps found** (safe, each is reported as unknown and never as an all-clear, but material gaps never
come from the join): (1) `building.find` returns an array of five candidates, each with its own
`requirements` and `gaps`, and the join looks for a top-level `requirements`, so every find says `gaps_unknown:
"the result carried no requirements block"`, and a top-level `gaps: []` sits next to a candidate that says
`needs 1 of TRAPPARTS, 0 available` (Well). (2) For `building.build` (an object) the join says "the
building_material requirement was present but not in a shape the server understands": it does not read the
tool's `filters[]` shape (item 14 of the server report). The tool's own `gaps` is kept and the server's is
dropped with a note (`the tool's own result already has a 'gaps' key; the server's 'gaps' was dropped`), for
example Bed `["needs 1 of BED, 0 available"]`. Smallest fix, in `dfmcp/labor_join.py`: take `requirements` from
the first candidate of an array result, and read `filters[].need` and `.stock` for the gap wording.

**labor.enabled-counts**: `{"MASON": 3, "NOTALABOR": null, "STONECUTTER": 2}` with `errors: {"NOTALABOR":
"unknown labor: NOTALABOR"}`; a bad name is `null` plus an error, not 0. An independent bounded per-unit read of
the citizens' labor bits (22 citizens) gave MASON 3, STONECUTTER 2. The earlier stream read 2 and 1, so labor
assignments changed since (not investigated).

**gotchas.get**, live store, as each role: architect, overseer and consultant all get the empty index
(`<gotcha_index ...>` with no tools, `structured: {"tools": {}}`); `tool=building.build` returns "is a real tool
and has no matching entries"; `tool=nonesuch.tool` is an error ("Refusing rather than returning an empty
list"). **gotchas.write** on a second server instance on another port with a temporary store under `/tmp`
(deleted after; the live store re-read before and after: **entries 0, outcomes 0, status_history 0**): the
architect's new entry got `gotcha-0001`, `proposed`, with role and run id stamped; the same title again was
refused ("its title is identical"), a bare label refused ("title is too short (9 chars, minimum 12)" and "must
state the condition"), an unknown tool refused ("not a tool in this server's registry"); an outcome by id
appended `worked` and the overseer's `gotchas.get` by id showed `outcomes total="1" worked="1"`; the consultant
could read it and was refused the write ("'gotchas.write' is not on consultant's allowlist. Advisors do not
act; propose it instead."); the next `building.list-kinds` result carried `<gotcha id="gotcha-0001"
status="proposed" worked="1" did_not_work="0">` and the standing addendum. The temporary instance was stopped
(port closed, checked).

**Refusals:** the consultant is refused `building.find`, `building.build` and `building.list-kinds`; the
architect is refused `building.build`; the consultant and architect are refused `nobles.appoint`. All with
"'X' is not on <role>'s allowlist. Advisors do not act; propose it instead." **Not the per-tool deny reasons
the brief expected:** neither role's `tools.yaml` has a `deny` entry for `building.*` or `nobles.appoint` (the
consultant's deny list is openarea, diggable, labor, ui), so the generic wording is what is served.

**nobles**: `nobles.list` as consultant and overseer: 12 positions, held: MANAGER by unit 345, EXPEDITION_LEADER
by 198; `nobles.verify MANAGER` as overseer: `consistent: true`, every assignment check true. Read only; nothing
appointed. **zone** (new script and grammar): `zone.list-kinds` lists kinds with owner capability and policy
source; `zone.check-owner Office MANAGER` returns the preserve-rooms mechanism and `holder_unit_ids: [345]`.

### Tests

Ambient `python -m pytest`: **834 passed, 2 skipped** (the merged tree; the briefs' baselines were older, 552 to
786). `dfmcp/tests` in `.venv-dfmcp`: **475 passed**. Both include the leak-guard test; no address, hostname or
token is in any tracked file (grep of the diff for the address prefix: 0).

### Refusals by the permission classifier

One kind, three times: an address computed in a shell variable before the ssh call, an archive command with a
variable in its paths, and a piped file-list command were each refused as "cannot be shown not to be git"
(this is a worktree-isolated agent). Not routed around: the address was read by key in its own plain command and
typed literally into every later `ssh` and `scp` (the user's form), and the archive and manifest were built with
plain commands and scratch Python scripts. A large heredoc that mentioned those commands was refused the same
way and the report was written with the edit tool instead. Nothing else was refused, including `sudo -n` for
the directories, the unit edit and the restart.

### What the docs now say wrongly (for the orchestrator)

- `CLAUDE.md` status block: role counts "architect 25, overseer 45, consultant 11" and the "Current state"
  bullets are stale: now **34 / 57 / 14**. `ROADMAP.md` carries the same counts.
- `CLAUDE.md` and `Working.md`: fort tick 103055 is stale, it is **106974** (the nobles stream's supervised
  unpause), with MANAGER held by unit 345.
- The building, gotchas, labor-join, nobles and zone tools are **live**; `agents/*/tools.yaml` notes such as
  "Not yet deployed" (for example `gotchas.get` in the consultant's) are now stale.
- `handoffs/2026-09-21-graph-labor-for-jobs.md` and this brief expect Masons to say STONECUTTER only: the graph
  on the VM was built with the generated reactions, so it says STONECUTTER plus STONE_CARVER.
- `docs/PRODUCTION-MODEL.md` still says a process's labor comes from `[SKILL:...]` (flagged by the graph stream).

### What remains unknown

- Whether the join's gap wording should read `filters[]` and array candidates (the two gaps above; a `dfmcp` edit).
- The 15 drifted Lua scripts under DFHack's script directory: undeployed changes or hand edits, direction unchecked.
- Whether the generated reactions are stable: they came from this world's save (entities 12 to 22); a new world
  needs the read repeated. The skill table is stable per DFHack version.
- Remaining graph blanks: 39 hard-coded jobs whose labor the game picks in code from the material, 20 generated
  reactions whose skill's labor is not on their kind's Workers tab (`contradicts_profile`: 18 at Craftsdwarfs, 2
  at the Soap Maker), and five kinds still `unknown` (Bowyers, Clothiers, Kennels, SOAP_MAKER, Tool).
- Why the MASON and STONECUTTER counts rose since the nobles stream.
- Whether real agents follow the confidence legend and read the appended text blocks (not testable here).
- Rollback material: `/opt/df/deploy-backup-2026-09-21-building-batch/` holds every overwritten file and the
  original unit.
