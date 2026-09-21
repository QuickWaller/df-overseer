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

## Report (executor, 2026-09-21)

**Status: done, offline, committed on the worktree branch, not deployed.**
Nothing here touched a VM, `TOOLS.yaml`, `agents/*/tools.yaml`, `role.md`,
`production/**`, `scripts/dfhack/**` or `docs/BUILDING-TOOL.md`.

### What was built

| File | What |
|---|---|
| `dfmcp/gotchas_store.py` | The store. SQLite, append-only (`entries`, `outcomes`, `status_history`), id chosen by the store (`gotcha-0001`, `unexplained-0001`, `vent-0001`), `BEGIN IMMEDIATE` writes, write-time validation, JSONL export, and an `init` / `export` command line (`python -m dfmcp.gotchas_store`). |
| `dfmcp/gotchas_tools.py` | `gotchas.get` and `gotchas.write` as native tools, served through the one `Roster.check` boundary like `doctrine.get`. |
| `dfmcp/confidence.py` + `gotchas/confidence.yaml` | Static levels, default medium for everything, loader that refuses an unknown level, key or (against the registry) tool id. |
| `agents/CONFIDENCE-LEGEND.md` | The one shared legend (about 400 words). |
| `dfmcp/tool_guidance.py` | Result enrichment (C3). |
| `dfmcp/labor_join.py` | The labor join (C1, C2). |
| `dfmcp/server.py` | One additive hook (`_enriched`), the gotcha dispatch branch, `_run_id`, three config fields, startup checks. The DFHack branch of `_handle_call_tool` was moved verbatim into `_run_dfhack_tool` so every return path is enriched in one place. |
| `dfmcp/README.md`, `gotchas/README.md` | Short sections. |
| tests | `test_gotchas_store`, `test_confidence`, `test_gotchas_tools`, `test_tool_guidance`, `test_labor_join`, `test_gotchas_server` (real MCP client), `gotchas_support.py`. Existing test files only gained `**GOTCHAS_NATIVE_TOOLS` in their registry fixtures (a one-line change each), so they keep loading the real roster once the allowlists gain the new ids. |

**Module layout, and why.** Two flat modules in `dfmcp/`, not `dfqueue/` (a
gotcha is not a proposal: no prediction, ruling or grader, and one schema
version should not carry both) and not a new top-level package (one caller, the
server; promoting it later is a move, not a redesign).

### Decisions and readings of the brief the orchestrator should check

1. **C3 says "one sibling object" without naming a key. I used a single key,
   `tool_guidance`**, holding `confidence`, `confidence_note`, `gotchas`,
   `gotcha_addendum` (plus `gotchas_omitted`, `gotchas_unavailable`, `notes`
   when they apply). A tool's own output can never collide with one key. If the
   design meant the four keys flat at the top level, it is a small change in
   `tool_guidance.enrich`.
2. **The enrichment is also appended as an XML text block after the tool's own
   text block** (and the labor join as an `<operating_context>` block), because
   a client that shows the model only the text content would never see the
   structured sibling. The tool's own first block is byte-identical to before.
3. **Errors are enriched** (a script `{"error": ...}`, an argument error, a
   DFHack failure), **roster denials and unknown tools are not.**
4. **Enrichment is off unless `build_mcp_server(confidence=...)` is given**, so
   every older caller and test is unchanged; `main()` always passes it. Same
   pattern for the labor join (`production_db_path`).
5. **An unreadable store is reported, not hidden.** The result still arrives,
   with `tool_guidance.gotchas_unavailable: <reason>` and no `gotchas` key.
   `gotchas` absent with no `gotchas_unavailable` means "checked, none".
6. **Startup is loud.** `main()` refuses to start on an absent or malformed
   gotcha store or a confidence file naming a tool that is not in the registry.
   The store is created only by the explicit `init` command.
7. **Outcomes are recorded only on `gotcha` entries** (not `unexplained` or
   `vent`), not on `rejected` ones, one per run per entry, at most 10 per run.
   **New entries: at most 3 per run.** These numbers are constants in
   `gotchas_store.py`, judgements not measurements.
8. **Title rule, mechanically:** one plain line, 12 to 120 characters, no `<`
   or `>`, of the form `<condition>: <hazard>` with the condition at least two
   words. It refuses bare labels and paragraphs; it cannot judge whether a
   condition is a good one. Near-duplicates: same tool and list, any status
   (rejected ones included so a rejected note cannot be re-proposed), title word
   overlap 75 percent or title text similarity 85 percent or body similarity 85
   percent.
9. **`low` is a third level** alongside `full` and `medium`, because the design
   note suggested one for never-run-live tools. It is not the user's wording and
   nothing uses it. Delete it from `confidence.LEVELS` if unwanted.
10. **Each listed gotcha also carries `outcomes: {worked, did_not_work}`** counts
    (additive to C3's `{id, title, status}`), so a bad note is visible without
    an expand call. Results list at most 10 (accepted first) and state how many
    were left out.
11. **`status` changes have a store function (`set_status`, audited) but no
    tool.** Who accepts a gotcha is the parked design question; until then
    proposed ones stay proposed and keep appearing as experiments.
12. **"Run" is the MCP session id** (`run_id = "session-<id>"`; a request with no
    session id shares one bucket). The per-run cap assumes one openclaw
    `agent exec` is one session. If a client reuses a session across runs the cap
    is only stricter.
13. **Where the labor join finds the kind:** the result's own `kind.token` (C1),
    else the call's `kind` argument. The join set is
    `labor_join.LABOR_JOIN_TOOLS = ("building.find", "building.build")`, data
    not a branch; the wrappers can be added when rebuilt over the generic tool.
14. **Gap wording rests on one assumption about C1's `requirements` shape.**
    C1 only says `{"building_material": {...}}`. The joiner reads the shape the
    existing workshop tool already prints (`accepts` plus `fort_owned`, and
    `needs_container` plus `fort_owned_containers`). Anything it does not
    understand, and `requirements: "unknown"`, goes to `gaps_unknown`, never to
    "no gaps". **The Lua stream should confirm its `building_material` shape
    matches**, or the joiner needs one line.
15. **The graph file is checked for existence before the real reader runs.**
    `production.store.connect` creates an empty, schema-valid database at any
    missing path (as `dfqueue.store` does), which would answer "no process" for
    "graph missing". The stub path skips the check.

### Unknown is not zero: what reaches the agent

`operating_labors.status` is `known`, `partial` or `unknown`. `unknown` is
`labors: null` plus a reason and a `gaps_unknown` line, never `[]`; `partial`
keeps the known labors, the reason, and a `gaps_unknown` caveat; only `known`
with `[]` means "no labor applies". A count the Lua read returned as `null` (or
did not return) stays `null` with its error and never becomes the "nobody has the
X labor enabled" gap. An absent graph, an absent `production.labors`, a raising
lookup, a C2 result of the wrong shape and a failed count read are each
`unknown` with the reason. Every one of these is a test.

### Verification and counts

Before: ambient `python -m pytest` **552 passed / 1 skipped**; `.venv-dfmcp`
`dfmcp/tests` **271 passed**.
After: ambient **687 passed / 3 skipped**; `.venv-dfmcp` **429 passed / 1
skipped**. The skips are the original one, `test_labor_join`'s check of the real
`production.labors` signature (skips until that stream merges), and, ambient
only, `test_gotchas_server.py` (needs the mcp 2.x line, like `test_server.py`).
The enrichment on an object, an array and an error result is proved twice: on
the exact shapes the server produces (`test_tool_guidance.py`) and through the
real SDK client, where a bare list in `structuredContent` would have raised a
protocol error (`test_gotchas_server.py`). The whole loop runs over the wire: an
architect writes a proposed gotcha, a later run's result carries its title but
not its body, an outcome is recorded, and the next result shows the count.
Checked that startup wiring works: the real registry with the new natives loads
the real roster, the real `gotchas/confidence.yaml` validates against it, a fresh
store passes `check_store`.

What the tests could not prove: nothing ran against DFHack, a real openclaw
client or VM 103; `mcp-session-id` is present in the in-process transport, but
how openclaw assigns sessions is unchecked.

### Allowlist lines the roles need (orchestrator to apply; I did not touch them)

- `agents/architect/tools.yaml` `read:` gets `gotchas.get` and `gotchas.write`.
- `agents/overseer/tools.yaml` `read:` gets `gotchas.get` and `gotchas.write`.
- `agents/consultant/tools.yaml` `read:` gets `gotchas.get` only.
- (Lua stream) `building.find` to the readers, `building.build` to the overseer's
  `write:`.

**Recommendation on who writes:** the architect and the overseer, the two roles
that have actually run tools and hit their failures. The consultant is an
advisor that has never made a real call, so reading gotchas is enough until it
has; more writers means more noise, and the per-run cap is the only brake. Both
tools have `mutates=False` (they never touch fort state), so an advisor may hold
`gotchas.write` without contradicting "advisors are read-only"; `roles.py` rule 1
requires the ids in the registry, which every test fixture and `main()` now
provide. The orchestrator wires `agents/CONFIDENCE-LEGEND.md` into each
`role.md`.

### What a deploy to VM 103 needs (not done)

1. **Code:** `dfmcp/` (new `gotchas_store.py`, `gotchas_tools.py`, `confidence.py`,
   `tool_guidance.py`, `labor_join.py`; changed `server.py`), `gotchas/confidence.yaml`,
   `agents/CONFIDENCE-LEGEND.md`, and **the `production/` package** (the join
   imports `production.labors` lazily; without it every building result says
   `unknown`). Ship with the repo's usual `autocrlf=false` archive. No new pip
   dependency (`pyyaml` is already pinned).
2. **The gotcha store, created once:** make `/var/lib/dfgotchas` (the default
   path is `/var/lib/dfgotchas/uniboslan.gotchas.sqlite3`, or set
   `MCP_SERVER_GOTCHAS_DB`), owned by the service user, then
   `python -m dfmcp.gotchas_store init <path>` as that user. **The server will
   not start without it.**
3. **systemd:** `ProtectSystem=strict` blocked `series.*` until
   `ReadWritePaths=/var/lib/dfseries` was added (deploy-batch handoff). The same
   applies: add `ReadWritePaths=/var/lib/dfgotchas` to the unit (the example unit
   is `infra/dfmcp-server.service.example`, outside this stream's surfaces).
4. **The production graph:** a built database at
   `/var/lib/dfproduction/uniboslan.production.sqlite3` (or
   `MCP_SERVER_PRODUCTION_DB`). Open risk for the graph stream: `production.store`
   opens in WAL mode and runs `create_schema`, so a reader under
   `ProtectSystem=strict` may need the directory in `ReadWritePaths` too, or a
   read-only open in `labors_for_kind`. The join reports the failure as
   `unknown`, so it will not break a call, but it will silently never work.
5. **The Lua side must be deployed for the counts:** `df-overseer-labor.lua`
   with `enabled-counts`, which the join calls as
   `dfhack-run lua -f df-overseer-labor enabled-counts LABOR...`. Until then the
   counts are `null` with an error and the result says so.
6. **Optional env:** `MCP_SERVER_CONFIDENCE_PATH` (default the in-tree file).
7. Restart `dfmcp-server`; then a smoke test: `gotchas.write` a throwaway entry,
   see its title on the next `landmarks.list`, and confirm the call log carries
   the `session-...` run id.

### Contract notes for the orchestrator

- **C2 is coded against exactly as written** (`labors_for_kind(db_path,
  kind_token)`); one test pins the real function's parameter names once the module
  exists.
- **C3 deviations are listed above (1, 2, 10).** C1 is consumed as written
  (`kind.token`, `requirements`, the `{"counts", "errors"}` read).

### What remains unknown

- Whether openclaw's one-shot `agent exec` is one MCP session (the run cap).
- Whether real agents follow the legend, and whether a text block after the
  tool's own is read by them; the user said they will monitor this.
- The right numbers: caps, title bounds, duplicate thresholds, the 10-title
  listing cap. All are constants with no evidence behind them yet.
- The exact shape of the Lua tool's `requirements.building_material` (item 14).
- How `production.labors` opens its database under the service's sandbox (item 4).
- Who promotes a proposed gotcha to accepted (parked by the user).
