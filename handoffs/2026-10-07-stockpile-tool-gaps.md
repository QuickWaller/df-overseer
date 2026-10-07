# Handoff: stockpile tool gaps for the Logistics role

Date: 2026-10-07. **Executor, Sonnet, worktree. Offline; no deploys, no live
VM.** First: `git merge --ff-only main`.

## Why

User's call 2026-10-07: a Logistics role owns stockpiles and links.
`research/2026-10-07-planner-design.md` revision 2 section 6.6 lists what
its tools lack; `research/2026-10-07-stockpile-logistics.md` has the game
facts (a workshop with links uses only its linked piles; orders obey that).

## Scope (design 6.6 items 1 to 6; not 7, 8 or 9)

1. Links-only: read on `stockpile.list`/`links`, write through a settings
   verb. Read the real field from the DFHack/df structures; never hard-code
   its default. If the field name cannot be confirmed from the local DFHack
   source or docs, say so and mark it unverified.
2. Container counts (max bins, barrels, wheelbarrows), read and write.
3. Finer material filters than the 17 categories (which stone, which wood),
   read and write, through the game's own material lists.
4. `stockpile.health` (read): per linked workshop, input classes with no
   non-empty linked source, whether each is available fort-wide
   (`stocks.availability`-style), whether its output link accepts its
   products. `stockpile.plan-feed WORKSHOP_KIND|ID` (read, dry-run spec):
   piles, classes, sizes, links, containers, from a **per-workshop-kind
   input/output table as data** (derived from game data where possible).
5. `stockpile.link` warns in dry run on the single-class trap (a workshop
   linked for some but not all of its input classes, including containers
   and fuel).
6. A pile removal verb, dry run by default.

Every write verb DRY_RUN by default and marked `live_deployed: false,
verified: unverified` in TOOLS.yaml; coordinate-free outputs; no armok.
Do not add the tools to any role allowlist (stage L does that). Tests on
the lupa fake world for each verb.

## Rules

Touched surfaces: `scripts/dfhack/df-overseer-stockpile.lua`, a new data
file for the per-kind table if needed, `scripts/dfhack/TOOLS.yaml`
(stockpile section only), tests, this handoff. Public repo: no hostnames,
IPs or tokens. No em dashes. No attribution lines. Commit after each
milestone. Do not write Working.md, DECISIONS.md, memory or INDEX.md. Full
ambient `python -m pytest` (lupa on PYTHONPATH) and `dfmcp/tests` in
`.venv-dfmcp` green.

## Result

Done offline, 2026-10-07. Everything below is UNVERIFIED LIVE; every new
write verb is DRY_RUN by default, `live_deployed: false`, `verified: unverified`,
and none is on any role allowlist.

**What was built** (`scripts/dfhack/df-overseer-stockpile.lua`, new data file
`scripts/dfhack/df-overseer-stockpile-kinds.lua`, TOOLS.yaml stockpile section):

1. Links-only: `list` and `links` report `links_only`; `stockpile.settings`
   writes it. **The field name `use_links_only` is recalled, not confirmed**:
   no df-structures or DFHack source exists in this repo or offline here, and
   the research note itself says "recalled, not read". Every read is pcall'd
   and reads null if absent, a write to an absent field is refused (never
   blind), no default is hard-coded, polarity is unconfirmed.
2. Container counts: `containers` {max_barrels, max_bins, max_wheelbarrows}
   on `list`/`links`; written by `stockpile.settings ID [LINKS_ONLY]
   [MAX_BINS] [MAX_BARRELS] [MAX_WHEELBARROWS] [DRY_RUN]` ("keep" or omitted
   leaves a field). Same recalled-names caveat.
3. Finer material filters: `stockpile.materials ID CATEGORY` (read) and
   `stockpile.set-materials ID CATEGORY MATERIALS [DRY_RUN]` (replace
   semantics, `all`/`none`, unknown names refused before any write). Lists
   come from the game's own raws vectors (stone: inorganics with IS_STONE;
   wood: plants with TREE) through one `MATERIAL_FILTERS` data entry per
   category, so another category is one entry. The `settings.<cat>.mats`
   layout and the include test are recalled and unverified.
4. `stockpile.health` (read) and `stockpile.plan-feed WORKSHOP_KIND|ID` (read
   spec, builds nothing), both over the per-kind table in
   per-kind classes **derived at runtime from the game's own data**
   (coordinator ruling 2026-10-07, revising the first cut, which was a hand
   table): `dfhack.workshops.getJobs` per kind (the source workjob.list-jobs
   reads) gives each job's reagent specs; reaction products come from
   `raws.reactions.reactions`. A workshop runs one job at a time, so a class
   needed by only some of a kind's jobs is `partial` (reported as optional,
   "1 of 2 jobs"), and only a class every job needs is a trap when unlinked.
   Hand data lives in `df-overseer-stockpile-kinds.lua`, each part marked:
   item type to stockpile category (the game exposes no such table),
   tag-matched reagent flags (food_storage means a container), fuel overlays
   (optional unless magma-fed), products of built-in jobs, feeder sizes, and
   the old whole-kind table kept as a FLAGGED FALLBACK (`kind_source =
   "fallback_table"` plus `derive_error`) when getJobs fails for a kind. An
   item type with no category is listed in `unmapped`, never guessed. Results
   are cached per process. Spec field shapes are those workjob.lua reads
   live; reaction product `item_type` and the category table are recalled.
   Health asks `stocks.get_availability` only for a failing class that names an
   items.other key.
5. `stockpile.link` now returns `warnings` (dry run and real alike, never a
   refusal): `single_class_trap`, `optional_class_unlinked`,
   `pile_feeds_no_input_class`, `output_pile_rejects_products`,
   `unknown_workshop_kind`. Furnaces are accepted as link targets (also
   unverified live).
6. `stockpile.remove ID [DRY_RUN]`: reports items left lying, links dropped,
   and workshops that would lose their last feeder or an input class; the
   real run calls `dfhack.buildings.deconstruct` and reads back whether the
   pile is gone.

**Touched outside the declared surfaces:** `dfqueue/action_tools.yaml`: the
`stockpiles` routing group's `tools:` list gained `stockpile.settings`,
`stockpile.set-materials`, `stockpile.remove`, because
`test_every_mutating_tool_is_routed_on_the_overseer_the_conductor_or_retired`
fails otherwise. `routed: false` is unchanged and this is not a role
allowlist. Also extended `tests/lua_stubs/dfhack_stockpile_world.lua` and
`tests/test_stockpile_writing_lua_logic.py` (harness helpers). Stage L still
owns the allowlists, `stockpile.unlink` in the group, and cutover.

**Tests:** new `tests/test_stockpile_gaps_lua_logic.py` (44 tests, fake world).
Ambient `python -m pytest` (lupa present): 3258 passed, 3 skipped.
`.venv-dfmcp` `dfmcp/tests`: 930 passed.

**Live verification plan** (throwaway pile on the paused fort, each step a
dry run first, read-back compared to the dry-run prediction):
- First, read-only: `stockpile.list` on the two existing piles; confirm
  `links_only` and `containers` are non-null. Null means the field names are
  wrong: inspect the building struct's real field names and fix the Lua
  constants before anything else. Check polarity by toggling the flag in the
  game UI and re-reading.
- `settings`: on a throwaway pile set MAX_BINS 0, read back via `list`;
  toggle LINKS_ONLY and confirm the in-game screen agrees.
- `materials`/`set-materials`: read a stone pile, compare the list to the
  in-game stone list; set two stones, confirm in-game; then `none`/`all`.
- `link`: link a throwaway pile to the Still (a Workshop) and read the
  warnings against the real input classes; then a Furnace (smelter) to
  confirm furnaces resolve and `df.furnace_type` names match the table keys.
  Confirm `df.workshop_type[bld.type]` returns the names used as table keys.
- `health` and `plan-feed`: run on the Still with a partial link; compare to
  what the game actually does when the job runs.
- `remove`: on the throwaway pile only; confirm the building is gone and the
  other ends' link vectors are clean (`links` on the former target).

**Design questions, answered by the coordinator 2026-10-07:** (a) derive the
per-kind table from game data: done, see item 4 above; (b) `stockpile.unlink`
joins the routing group in stage L; (c) the read-only `stockpile.list` live
check comes first. Live check to add for item 4: compare
`stockpile.plan-feed Still` `kind_source`, `unmapped` and classes against the
in-game "add job" menu for a Still and a Smelter.


**Update 2026-10-07, after the live read-only check.** `stockpile.list` returned
neither field, so the recalled names were wrong. Coordinator's live struct read
(pile 1): links-only is `bld.stockpile_flag.use_links_only` (bitfield, false),
containers are `bld.storage.max_barrels/max_bins/max_wheelbarrows` (25/25/0),
and `bld.settings.<stone|wood>.mats` is vector<char> (311/225), so the layout
was right but values are 0/1 chars. Lua reads and writes now use those paths
(table `FIELD_PATHS`), the material read goes through `as_bool` (Lua's 0 is
truthy) and writes 1/0; fake world and tests follow; marked `verified: live
read 2026-10-07` in the code and TOOLS.yaml. Writes remain unverified, as does
the raws-index assumption for the material vectors.
