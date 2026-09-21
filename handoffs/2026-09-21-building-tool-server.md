# Handoff: gotcha tools, confidence, result enrichment and the labor join (server side)

Date: 2026-09-21. **WRITTEN for review, not dispatched.** Offline build
stream. No VM, no SSH, no deploy.

Read `CLAUDE.md`, then `docs/BUILDING-TOOL.md` **in full** (decisions, the
gotcha rulings, and contracts C2 and C3), then `dfmcp/doctrine_tools.py` and
`dfmcp/queue_tools.py` in full (native tools, the pattern to follow),
`dfmcp/server.py`'s `_handle_call_tool`, and `docs/TRAPS.md` (the
`structuredContent` trap), then this.

## Why this stream exists

The user's design gives every tool a **confidence level** (a static setting,
default medium), three per-tool lists (gotchas, unexplained errors, vent), and
two shared tools: `gotchas.get` and `gotchas.write`. Every tool result carries
the level and **short, condition-titled** gotchas, proposed ones included as
experiments to try only if they apply and the tool fails without them, with
outcomes marked. Separately, results from the building tool gain the
operating labors of the kind, joined in **by the server** from the production
graph (option (b) in the design note).

## Deliverables

1. **`dfmcp/gotchas_tools.py`** (new): native tools `gotchas.get` and
   `gotchas.write`, served the way `doctrine.get` is, through the one
   `Roster.check` boundary.
   - `gotchas.get`: by tool (and optional kind), by id, or a list of a tool's
     entries, returning full text and status and outcomes. An unknown tool is
     an error, never an empty list.
   - `gotchas.write`: takes a tool, chooses its own id, sets `proposed`, and
     records metadata per **C3**. **Given an existing id it appends an outcome
     and never overwrites.** Validated at write time as `dfqueue` is: the tool
     must exist in the registry, the title must be short and state the
     condition it applies under, near-duplicates and oversized bodies are
     refused, and a per-run write cap applies.
2. **The store**: SQLite following `dfqueue`'s pattern (append-only, JSONL
   export), path configurable, fail loudly if absent or malformed. Choose the
   module layout and say why; keep it out of `dfqueue/`.
3. **`gotchas/confidence.yaml`** (new): tool id (optionally tool and kind) to
   level, **default medium for everything**, plus a loader that refuses an
   unknown level.
4. **`agents/CONFIDENCE-LEGEND.md`** (new): the one shared, short text every
   role prompt will include. It must explain that confidence means both that
   the tool works and that it is intuitive for an agent, what the agent should
   do at full and at medium, and the standing rule for proposed gotchas (try
   only if the title applies and the tool fails without it, then mark the
   outcome). The orchestrator wires the include into each `role.md`.
5. **Result enrichment** per **C3** in `dfmcp/server.py` (a minimal, additive
   hook): confidence and gotcha titles on every DFHack-backed result. Survive
   the array-output trap; **prove it with a test on an array result and on an
   error result.**
6. **The labor join** per **C2**: for the building tool's results, the server
   calls `production.labors.labors_for_kind(db_path, kind)` (built by another
   stream) and adds `operating_labors`, a `gaps` list (unmet labor, missing
   materials, in plain words) and, using the labor `enabled-counts` read, the
   count of citizens with each labor. Until that stream merges, code against
   C2 with a stub and a test that pins the contract. **`unknown` or `partial`
   must reach the agent as unknown**, never as an empty list.

## Rules that bite here

- Do not touch `production/**`, `scripts/dfhack/**`, `agents/*/tools.yaml`,
  `agents/*/role.md` or `docs/BUILDING-TOOL.md`. Report the allowlist lines
  the roles need. Which roles get the write tool is the orchestrator's call;
  recommend and say why.
- **Every qualifier must survive to the agent**, the rule the `series.*` tools
  followed. Unknown is not zero.
- The doctrine, queue and series tools are untouched.
- The path to the graph database and to the gotcha store must be
  configurable, with a written note of what a deploy to VM 103 needs. **Do not
  deploy.**
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`. **Commit after each milestone.** No em dashes.

## Touched surfaces

`dfmcp/gotchas_tools.py` (new), the store module (new), `dfmcp/server.py`,
`dfmcp/registry.py` only if needed, `gotchas/confidence.yaml` (new),
`agents/CONFIDENCE-LEGEND.md` (new), `dfmcp/tests/**` (new files), this doc.

## Done means

Both tools reachable through the real registry and roster, id assignment and
outcome-append tested, validation refusals tested, the enrichment present on
object, array and error results, the labor join pinned to C2 with a stub, the
full suite passing (**552 passed / 1 skipped** ambient, **271** in
`.venv-dfmcp`, report before and after), and the write-up says exactly what a
deploy needs.
