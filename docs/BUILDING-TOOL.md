# The generic building tool (design note)

## Status, 2026-09-22: built and deployed, dry runs only

This note was written as a design before anything existed; the design history
below is kept as written, and this block says what became of it. Every claim
here was checked against a handoff report (named beside it), not against
another doc's summary.

**Built and live on VM 103 since 2026-09-21**
(`handoffs/2026-09-21-deploy-building-batch.md`, 48 files hash-verified):

- `scripts/dfhack/df-overseer-building.lua`: `list-kinds`, `find`, `build`
  over 175 kinds read at run time from quickfort's own table
  (`handoffs/2026-09-21-building-tool-lua.md`), and `enabled-counts` in
  `df-overseer-labor.lua`.
- `dfmcp/`: the gotcha store and `gotchas.get`/`gotchas.write`, the static
  confidence file and shared legend, the `tool_guidance` enrichment, and the
  labor join (`dfmcp/labor_join.py`) that adds operating labors from the graph
  (`handoffs/2026-09-21-building-tool-server.md`).
- `production/labors.py` and `production/labor_ingest.py`: the graph side of
  the labor question, and a built graph database deployed beside the server
  (`handoffs/2026-09-21-graph-labor-for-jobs.md`).
- Siblings the same day: the generalised `zone` tool (18 zone kinds, optional
  owner) and the `nobles` tool.
- Role tool lists after the deploy: architect 34, overseer 57, consultant 14.

**Verified live after the deploy:** per-role tool lists, `building.list-kinds`,
`building.find` and `building.build` as dry runs for workshops, furnaces,
furniture and a farm plot, error cases, `tool_guidance` on object, array and
error results, the labor join against the real graph (Masons come back
`partial` with STONECUTTER and STONE_CARVER; a kind the graph does not know
comes back `labors: null` with a reason), and `labor.enabled-counts`.

**Never run:** the real (`DRY_RUN` false) build path for any kind. No building
has been built by this tool. The first real build of a never-built kind needs
its own supervised stream and the user's go-ahead.

**Merged but not yet redeployed:** the fix that makes the labor join read the
building tool's real result shapes (`dfmcp/labor_join.py`,
`dfmcp/tool_guidance.py`; `handoffs/2026-09-21-labor-join-shapes.md`). Until it
is deployed, every `building.find` says its gaps are unknown ("the result
carried no requirements block") and a `building.build` drops the server's gaps
in favour of the tool's own.

**Answered by the builds** (the open-questions section below carries each in
place): operating labor and the ConstructBlocks disagreement, material
filters, the optional `[W H]` and repeated `LABOR...` arguments, and where the
join happens.

**Still open:** listed at the end of this note.

**Original status, kept:** *proposed, nothing built.* Written for review before
any handoff is dispatched. Prompted by the user's rule that every tool must be
generalisable (`CLAUDE.md`, register 2026-09-21): the workshop tool covers five
hard-coded kinds, and the user's minimum bar for openclaw is building
workshops, rooms and furniture, assessing dwarves, growing food and building
wells.

## What was checked on the install (2026-09-21, read-only, fort paused)

Checked over SSH on VM 103. No file was changed; one bounded Lua read ran
against the paused game.

1. **The raws do not carry standard buildings.** My earlier assumption was
   wrong. `data/vanilla/vanilla_buildings/objects/building_custom.txt` is 56
   lines and defines two workshops (Soap Maker, Screw Press). Footprint and
   build data for every other workshop is hard-coded in the game.
2. **DFHack's quickfort has the table instead.** `building_db_raw` in
   `hack/scripts/internal/quickfort/build.lua` holds roughly 87 labelled
   entries (a `label=` grep over the table's line range, not a parsed count).
   Each has a type, a subtype and a footprint. Confirmed present:
   - about 30 workshops and 7 furnaces, plus siege engines;
   - furniture: bed, seat, table, door, cabinet, container, statue, slab,
     armor stand, weapon rack, bookcase, display furniture, and more;
   - well, trade depot, farm plot, roads, kennels, cages, hives;
   - **default footprint 3x3 for every workshop, furnace and siege engine**,
     with overrides (kennels and siege workshop 5x5; quern, millstone and
     screw press 1x1); everything else defaults to 1x1.
   Rooms are in the sibling `zone.lua`: bedroom, dining hall, office,
   dormitory, barracks, meeting area, pen, pit, dungeon, fishing, sand and
   water source.
3. **Operating labor is only partly derivable.** Reading
   `df.job_type.attrs[job].skill` then `df.job_skill.attrs[skill].labor` gave
   real answers for PrepareMeal (COOK), SmeltOre (SMELT) and ButcherAnimal
   (BUTCHER), and NONE for MakeCrafts. Two lookups (BrewDrink, MakeTrapParts)
   errored and the cause was not investigated. **ConstructBlocks maps to
   STONECUTTER, while the workshop tool's table says a mason's workshop uses
   MASON.** Which is right for what the tool needs is unresolved, so the labor
   cannot be assumed derivable.

   **Resolved 2026-09-21.** The two lookup errors were names that do not exist
   in `df.job_type` on this build (brewing is reaction-defined; trap parts is
   `MakeTrapComponent`), not failures. **STONECUTTER is right and MASON is not
   an operating labor of the Mason's Workshop**: three concordant static
   sources (the job's skill is `CUT_STONE`; the game's Workers tab for Masons
   offers STONECUTTER and STONE_CARVER; no job type's skill maps to MASON at
   all, so the game applies MASON in code). Not proven by watching a dwarf make
   blocks. 39 hard-coded jobs, every Masons and Carpenters furniture job among
   them, have no labor in the game's job table, so those labors are not
   derivable from any structure read
   (`handoffs/2026-09-21-building-tool-lua.md`, "The ConstructBlocks
   disagreement"; `handoffs/2026-09-21-graph-labor-for-jobs.md`).

## Proposed shape (as designed; built, see the status block)

- **`building.find KIND ...` and `building.build KIND ...`.** `KIND` is a token
  from quickfort's own table, read at run time rather than copied, so a new
  DFHack version adds kinds for free. Footprint comes from the table's
  min/max, so `W H` become optional for fixed-size kinds and validated for
  variable ones.
- **The blueprint is generated in code** from the footprint and the kind's
  key. The per-kind starter CSVs in `blueprints/` become unnecessary.
- **Site finding stays as it is** (open area, walkability, ring adjacency).
  Per-kind tile rules already exist in the same table (farm needs soil, a
  well needs water) and should be read from it rather than re-implemented.
- **Per-kind policy is data.** Operating labor, container need, named
  requirements and material notes live in a requirements file keyed by kind,
  with provenance and status like `doctrine/seed.yaml`. The still's barrel
  check and the kitchen's seed protection move out of the tool into it.
  **A kind with no entry must report `requirements: unknown`, never an empty
  list**, or this re-creates the silent-zero bug class this repo has already
  shipped five times (register 2026-09-19).
- **Rooms and furniture fall out of the same base.** A room is a zone kind
  plus a list of furniture kinds built with the same tool; zones need the
  matching generalisation of `zone.find/place`, which today places a water
  source only. *Update 2026-09-21: the `zone` tool now takes any of the
  install's 18 zone kinds with an optional owner, deployed the same day
  (`handoffs/2026-09-21-zone-tool-generalise.md`). Furniture placement for a
  room through `building` exists as a tool, but no room has been assembled from
  the two.*
- **Kind tokens must survive the MCP layer.** The server refuses an
  apostrophe today (`Stoneworker's Workshop`), so tokens are the table's own
  keys or enum names (for example `Masons`), never display labels. *As built:
  a token is the subtype enum name (`Masons`, `Still`), the raws code for a
  custom workshop (`SOAP_MAKER`), or the type name (`Bed`, `Well`); direction
  variants become `<Base>_<key>`; no token contains an apostrophe. Landmark
  names that contain one (such as "Mechanic's Workshop") are still refused by
  the MCP layer as `NEAR_LANDMARK` (`handoffs/2026-09-21-building-tool-lua.md`,
  finding 4).*

## Confidence per tool and kind (user's design, 2026-09-21)

**Not checked or built; this is the user's requirement, recorded as given.**
Each tool, and for the generic tool each kind, carries a **confidence** level
(the name is a placeholder). It tells the agent how much care the tool needs:

- **Full:** the agent can just use it.
- **Medium:** the agent reads the description more thoroughly, checks the
  indexed gotchas, re-reads the instructions or thinks again, and monitors for
  success more closely.
- A low or untested level is implied for things never run live (this note's
  suggestion, not the user's): dry-run first, closest monitoring.

**Why it exists:** some tools will not be intuitive to use and will need extra
context that openclaw updates as it goes, but that is not true of every tool.
The level says which ones. The user sees this as **part of the self-learning
loop**: the gotchas attached to a tool are learned material.

**The user's rulings on the design, 2026-09-21:**
- **The level is a static setting, with no mechanism to raise it.** The user
  rejected code-only level setting (too much grey area) and then said no
  mechanism for the level to increase is needed. So there is no promotion,
  ruling or evidence pipeline for it: it is set when a tool or kind is written
  or reviewed, by us, and stays until we edit it. This also removes the
  "agent must never raise its own tool" concern, since nothing can.
- **Every tool keeps three lists**, so nothing learned about it is lost:
  1. **Gotchas**: things worked out and to be kept in mind next time.
  2. **A vent list**: somewhere for an agent to complain, for example that
     this tool is not right for what it wants. Per `docs/AGENT-ARCHITECTURE.md`
     section 10 vent is a hypothesis generator, never evidence, and it feeds
     repo work, not doctrine. It is a complaint channel, so results do not
     need to carry it (my reading; not stated by the user).
  3. **Unexplained errors and mistakes**: kept until worked out, then promoted
     to a gotcha.
- **Agents propose new gotchas through the queue**, as doctrine revisions do.
- **Every tool result carries the confidence level and a short shorthand of
  each gotcha, not its full text.** The title must state the condition, for
  example "placing a workshop in a desert biome: <hazard>", so the agent can
  tell from the title alone whether it applies and whether to expand it. The
  full text is fetched on demand, which needs an expand call (the shape of
  `doctrine.get`, not built).
- **Meaning of the level (user, 2026-09-21):** it is confidence that the tool
  works **and** confidence in how intuitive it is for an agent to use. Agents
  need a short standard explanation of the levels, or the level is noise. Where
  that text lives (role prompt, tool description, or both) is open.
- **Starting level: every kind starts at medium** (user, 2026-09-21).
- The existing `verified` and `live_deployed` fields in `TOOLS.yaml` are the
  natural starting evidence for the level.

*As built (`handoffs/2026-09-21-building-tool-server.md`):* the levels live in
`gotchas/confidence.yaml`, every tool and kind at medium, with a loader that
refuses an unknown level or a tool id not in the registry. A third level, `low`,
exists because this note suggested one; nothing uses it. The shared legend is
`agents/CONFIDENCE-LEGEND.md`, pointed to from each role's `role.md`.

## Open questions, to settle before building

1. **Operating labor: decided 2026-09-21, from the graph.** A workshop's
   operating labors are the labors of the processes it hosts in
   `production_process`, so the tool carries no labor field. The offline
   stream settles which hardcoded jobs each workshop hosts and the
   ConstructBlocks disagreement. **How it reaches the agent: decided 2026-09-21, option (b):** the Lua
   tool returns only live facts and the MCP server joins the labors in from
   the graph before the result reaches the agent, as it already does for the
   queue, doctrine and history. Needs a one-time deploy of the graph's
   reference data to VM 103 (the production database has not been seen there).
   A raw command-line call to the Lua tool will not include the labors.
   **Built and deployed 2026-09-21.** The graph database on VM 103 was built
   from the real raws, a bounded read of the game's skill-to-labor table (149
   skills, 68 with a labor) and the 145 generated reactions
   (`handoffs/2026-09-21-deploy-building-batch.md`). The service opens the
   database read-only under its sandbox with no extra `ReadWritePaths` entry.
   The status rule is stricter than the design: `known` needs every hosted
   process determined and the Workers-tab list fully explained, so on the
   deployed graph 5 of 33 workshop and furnace kinds are `known`, 23 `partial`
   and 5 `unknown`; the other 143 tokens (furniture, constructions) are
   `unknown` by design. **Answer is wider than the note assumed:** Masons come
   back STONECUTTER and STONE_CARVER (the generated reactions add the second),
   never MASON.
2. **Does every kind actually build live?** Only five workshops have ever
   been built by our tools. The user's answer, 2026-09-21: **do not sweep now,
   it costs too much time and money.** Each kind's confidence level is set by
   us when it is added (the level is static), and every kind starts at
   **medium**. *Still true: the real build path has never run for any kind.*
3. **Material filters: decided 2026-09-21, leave to the research pass, and
   factor the result into the graph.** `dfhack.buildings.getFiltersByType`
   looks like the game's own answer to "what does this kind need" to build.
   Unchecked. The user wants the result in the graph: `docs/PRODUCTION-MODEL.md`
   already treats installation as a process (item and labour in, building
   out), so build materials become that process's input flows. My suggested
   split, not yet agreed: whatever is a flow (materials, containers) goes in
   the graph; only what is not a flow (such as the kitchen's seed protection
   setting) stays in the per-kind data file.
   **Answered 2026-09-21 in part.** `dfhack.buildings.getFiltersByType` does
   **not** return the game's own list: it is DFHack's own table
   (`research/2026-09-21-building-requirements.md`), so the tool reports it as
   DFHack's answer, with stock counts by item type (the filters' own flags are
   listed, not applied) and a plain gap list. Whether installation should also
   become a process in the graph, with materials as input flows, is not covered
   by any report read for this update: still open.
4. **What a kind needs to be useful: decided 2026-09-21.** A brief research
   pass by a Sonnet subagent over **all** workshop and furnace kinds, output
   filling the per-kind data file with provenance. **Research done 2026-09-21**
   (`research/2026-09-21-building-requirements.md`, 32 kinds, every field
   flagged verified or prior). Whether it has been turned into the per-kind
   requirements file the design describes is not shown by any report read for
   this update: still open.
5. **How much the tool checks versus reports: decided 2026-09-21, option
   (b).** It stays report-only and adds a plain `gaps` list to the result
   (for example "no barrels, nobody with the BREWER labor"). It does not
   refuse to build, so "build now, barrels later" still works. *Built: `gaps`
   is a list of plain strings in the result.*
6. **What happens to `workshop`, `well` and `farm`: decided 2026-09-21, keep
   them as custom wrappers over the generic tool.** More wrappers are built
   as needed. They exist for per-kind extras (the well's water-depth check,
   the farm's crop setting, the kitchen's seed protection) and convenient
   names; the placement itself goes through the generic tool, not a second
   copy of it. *Not done: `workshop`, `well` and `farm` are unchanged and still
   carry their own placement code; `df-overseer-workshop.lua` still reports a
   plain fort-owned count without the `in_building` deduction
   (`handoffs/2026-09-21-building-tool-lua.md`, finding 5).*

7. **Where the confidence legend lives: decided 2026-09-21.** One short
   legend in the role prompt, from a single shared text file that every role
   prompt includes so it cannot drift. Each result carries the level plus a
   few-word reminder. The user will monitor whether agents use it.
8. **Gotchas: two shared tools, decided 2026-09-21.** `gotchas.get` expands a
   gotcha by tool and id. **`gotchas.write` takes a tool and writes a gotcha,
   choosing the id itself and marking it `proposed`, with metadata** (user's
   spec). Two tools in total, not two per tool, to keep the tool list small;
   this replaces the earlier idea of proposing gotchas through the queue.
   Suggested details, not yet agreed:
   - **One write tool, a `list` field** (gotcha, unexplained error, or vent),
     rather than a tool per list, in keeping with the generalisability rule.
   - **Metadata:** writing role, run, time, tool, optional kind, and a short
     excerpt of the call that prompted it.
   - **Validated at write time**, as `dfqueue` is: the tool must exist, the
     title must be short and state its condition, and near-duplicates and
     oversized bodies are refused so the store cannot bloat.
   - **Storage follows `dfqueue`** (SQLite on VM 103 with a JSONL export);
     accepted entries are committed to the repo.
   **Proposed gotchas do appear in tool results (user, 2026-09-21), as
   experiments.** Each result carries the standing addendum: try a proposed
   gotcha only if its title applies **and** the tool fails without it, then
   mark the outcome. The addendum lives in the shared legend text as well as
   the result. *(As built: see the status block above; both tools deployed
   2026-09-21, the live store was empty at deploy, and the write path was tested
   only against a temporary store.)* To mark an outcome without a third tool, I suggest
   `gotchas.write` given an existing id records an outcome (worked, did not
   work) on it, append-only and never overwriting. The recorded outcomes are
   the evidence for accepting a gotcha and for spotting a bad one.
   **A pile of gotchas is a design signal (user, 2026-09-21).** If a tool's
   gotchas start to add up, consider rebuilding the tool or rewriting its
   description, since a tool that needs many warnings is a badly shaped tool.
   This is repo maintenance policy, not game knowledge, so I would keep it out
   of `doctrine/seed.yaml` and put it in the learning role's charter; it
   should be a trigger for review, with no fixed threshold (research
   2026-08-25 already rejected an arbitrary one for spotting patterns).
   **Open, parked (user, 2026-09-21):** who turns a proposed gotcha, with
   its outcomes, into an accepted one. It will be an agent, but which one
   waits on the overall openclaw design, which is not decided. Until then,
   proposed gotchas simply stay proposed and keep appearing as experiments.

## Contracts between the streams

The streams below build in parallel against these shapes. **Only the
orchestrator edits this section**; an executor who finds a shape wrong reports
it rather than changing it.

**C1. Lua tool output** (`scripts/dfhack/df-overseer-building.lua`), JSON,
live facts only, no labor names and no confidence:
`{"kind": {"token", "label", "type", "subtype"}, "dims": [w, h],
"site": {"rank", "near_landmark", "direction", "distance_tiles"},
"dry_run": bool, "requirements": {"building_material": {...}},
"quickfort_ok", "quickfort_error", "quickfort_stats"}` (the last three only on
a real build). New read in `df-overseer-labor.lua`:
`enabled-counts LABOR [LABOR...]` returning
`{"counts": {"LABOR": n_or_null}, "errors": {"LABOR": "message"}}`. **A
failed lookup is `null` plus an error, never `0`** (silent-zero rule).

**C1 as built** (checked against `scripts/dfhack/df-overseer-building.lua` in
`handoffs/2026-09-21-labor-join-shapes.md`, and the manifest). The signatures in
`TOOLS.yaml` are `find KIND [W H] [LEVEL] NEAR_LANDMARK [RADIUS_TILES]`,
`build KIND [W H] [LEVEL] NEAR_LANDMARK [RANK] [RADIUS_TILES] [DRY_RUN]` and
`enabled-counts LABOR...`; `[W H]` is an all-or-nothing optional group and
`LABOR...` a repeated argument (`handoffs/2026-09-21-optional-and-variadic-args.md`).
- `find` returns a **bare array** of up to five candidates (the server wraps it
  `{"result": [...]}`). Each has `kind {token, key, label, type, subtype}`,
  `dims`, `site {rank, near_landmark, direction, distance_tiles}`, `search`,
  `requirements` and `gaps`. Requirements are computed once per call, so the
  candidates carry identical ones.
- `build` returns one object with `kind`, `dims`, `site`, `dry_run`, `search`,
  `requirements`, `gaps`, `blueprint`, then `validation` on a dry run or
  `quickfort_ok`, `quickfort_error`, `quickfort_stats` and `read_back` on a
  real build (`quickfort_ok` stays reserved for a real build).
- `requirements` is `{building_material: {source, buildingplan_enabled,
  filters[], note?, error?}}`; each filter has `index`, `quantity` (may be
  negative when it depends on the footprint), `flags`, `count_scope`, `need`
  (text), `item_type?`, `stock?`, `available` (int or null) and further
  optional fields. **There is no `accepts`, `fort_owned` or
  `needs_container` field**: those belonged to the old workshop tool's shape.
  `gaps` is a list of plain strings (`needs Q of NEED, N available`, and the
  tool's own wording for size-dependent quantities and uncountable stock).
- `enabled-counts` returns `{"counts": {LABOR: n or null}, "errors": {LABOR:
  message}}` as designed; a name that is not a real labor is `null` plus an
  error, never `0`.

**C2. Graph API** (`production/labors.py`, new):
`labors_for_kind(db_path, kind_token) -> {"kind": str, "labors": [str],
"status": "known" | "partial" | "unknown", "processes": [{"id", "labor" or
null, "source_ref"}], "unknown_reason": str or null}`. `labors` is empty with
status `known` only if the game data says no labor applies; anything the
extractor could not determine is `partial` or `unknown` with a reason.

**C2 as built** (`production/labors.py`,
`handoffs/2026-09-21-graph-labor-for-jobs.md`): `labors_for_kind(db_path,
kind_token)` returns C2's keys plus `profile_labors`,
`unexplained_profile_labors`, `undetermined_process_count`, and `reason` and
`candidate_labor` on an undetermined process. It raises on a graph it cannot
read rather than answering empty. The status rule is stricter than written:
`known` needs at least one hosted process, every hosted process determined, and
the game's Workers-tab list for the kind non-empty and fully explained by them;
a kind with no data is `unknown`. The MCP join then presents `unknown` as
`labors: null` plus a reason, and `partial` keeps the known labors with the
reason, never `[]`.

**C3. Gotcha record and result enrichment** (`dfmcp`):
record `{"id", "tool", "kind" or null, "list": "gotcha" | "unexplained" |
"vent", "title", "body", "status": "proposed" | "accepted" | "rejected",
"created_at", "written_by_role", "run_id", "call_excerpt", "outcomes": [{"at",
"role", "run_id", "result": "worked" | "did_not_work", "note"}]}`. Every
DFHack-backed tool result gains one sibling object,
`{"confidence": "medium", "confidence_note": "<a few words>", "gotchas":
[{"id", "title", "status"}], "gotcha_addendum": "<standing text>"}`, with
`gotchas` present only if the tool has any and the addendum only when a
proposed one is listed. Titles only; full text comes from `gotchas.get`. The
enrichment must survive the array-output trap in `docs/TRAPS.md`.

**C3 as built** (`dfmcp/tool_guidance.py`,
`handoffs/2026-09-21-building-tool-server.md`, items 1, 2 and 10): the sibling
object is a single key, **`tool_guidance`**, holding `confidence`,
`confidence_note`, `gotchas` (each `{id, title, status}` plus `outcomes:
{worked, did_not_work}`), `gotcha_addendum` when a proposed one is listed, and
`gotchas_omitted`, `gotchas_unavailable` and `notes` where they apply. An
array result is wrapped so the enrichment survives, and the same enrichment is
appended as an XML text block after the tool's own first block. Errors are
enriched; roster refusals are not. Gotcha ids are chosen by the store
(`gotcha-0001`, `unexplained-0001`, `vent-0001`), at most 3 new entries and 10
outcomes per run.

## What is still open (2026-09-22)

- **The real build path has never run** for any kind: writing the blueprint,
  `quickfort run` without a dry run, the `read_back`, and whether
  `buildingplan` picks the materials up. A dry run proves the site and the
  blueprint pass quickfort's tile rules, not that the game accepts the job.
- **The labor-join shapes fix is merged and not deployed** (`dfmcp` only, then a
  restart of `dfmcp-server`).
- **Labor blanks:** 39 hard-coded jobs whose labor the game picks in code from
  the item material; 20 generated reactions whose skill's labor is not on their
  kind's Workers tab; five kinds still `unknown` (Bowyers, Clothiers, Kennels,
  SOAP_MAKER, Tool). The generated reactions came from this world's save and
  need the read repeated for a new world.
- **`find` does not prove a site is reachable** from the main area, and stock
  counts are by item type only.
- **The per-kind requirements file** and **installation as a graph process**
  (open questions 3 and 4) are not shown as built.
- **`workshop`, `well` and `farm` are not yet wrappers over the generic tool.**
- **Who promotes a proposed gotcha to accepted** is parked by the user, and
  whether real agents follow the legend and read the appended text blocks is
  untested.

## Next step (as written before building)

After review, two streams with disjoint files. **Offline:** a table reader,
blueprint generator and requirements file, tested against a fixture of the
real table. **Live, after the offline stream:** one real build of a kind our
tools have never built (a craftsdwarf's workshop, for example). No sweep of
every kind, per the user. **The acceptance test is the rule itself: adding the
next kind must need a data entry and no new code.**
