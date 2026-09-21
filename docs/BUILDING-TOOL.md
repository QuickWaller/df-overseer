# The generic building tool (design note)

**Status, 2026-09-21: proposed, nothing built.** Written for review before any
handoff is dispatched. Prompted by the user's rule that every tool must be
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

## Proposed shape (unbuilt)

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
  source only.
- **Kind tokens must survive the MCP layer.** The server refuses an
  apostrophe today (`Stoneworker's Workshop`), so tokens are the table's own
  keys or enum names (for example `Masons`), never display labels.

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
2. **Does every kind actually build live?** Only five workshops have ever
   been built by our tools. The user's answer, 2026-09-21: **do not sweep now,
   it costs too much time and money.** Each kind's confidence level is set by
   us when it is added (the level is static), and every kind starts at
   **medium**.
3. **Material filters: decided 2026-09-21, leave to the research pass, and
   factor the result into the graph.** `dfhack.buildings.getFiltersByType`
   looks like the game's own answer to "what does this kind need" to build.
   Unchecked. The user wants the result in the graph: `docs/PRODUCTION-MODEL.md`
   already treats installation as a process (item and labour in, building
   out), so build materials become that process's input flows. My suggested
   split, not yet agreed: whatever is a flow (materials, containers) goes in
   the graph; only what is not a flow (such as the kitchen's seed protection
   setting) stays in the per-kind data file.
4. **What a kind needs to be useful: decided 2026-09-21.** A brief research
   pass by a Sonnet subagent over **all** workshop and furnace kinds, output
   filling the per-kind data file with provenance. Not yet dispatched.
5. **How much the tool checks versus reports: decided 2026-09-21, option
   (b).** It stays report-only and adds a plain `gaps` list to the result
   (for example "no barrels, nobody with the BREWER labor"). It does not
   refuse to build, so "build now, barrels later" still works.
6. **What happens to `workshop`, `well` and `farm`: decided 2026-09-21, keep
   them as custom wrappers over the generic tool.** More wrappers are built
   as needed. They exist for per-kind extras (the well's water-depth check,
   the farm's crop setting, the kitchen's seed protection) and convenient
   names; the placement itself goes through the generic tool, not a second
   copy of it.

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
   the result. To mark an outcome without a third tool, I suggest
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

## Next step

After review, two streams with disjoint files. **Offline:** a table reader,
blueprint generator and requirements file, tested against a fixture of the
real table. **Live, after the offline stream:** one real build of a kind our
tools have never built (a craftsdwarf's workshop, for example). No sweep of
every kind, per the user. **The acceptance test is the rule itself: adding the
next kind must need a data entry and no new code.**
