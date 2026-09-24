# Handoff: n8n testing, version control, and node choice for tool workflows

Date: 2026-09-25. **Researcher. Read-only. No VM, no install, no deploy.**

## Why

The user is considering reimplementing df-overseer's MCP tools as n8n
workflows exposed through MCP Server Triggers (one trigger per role, the
allowlist visible as which tool workflows attach to it), with the Lua leaves
unchanged and called via `dfhack-run`. Before any pilot, they want three
things researched: how to test n8n workflows effectively, how to version
control them (this repo is public), and which nodes to use. **Their design
preference is explicit: minimise large blocks of code; control statements
(branches, loops, error paths) should be nodes, not Code-node logic.**

Read `CLAUDE.md`, `research/2026-09-25-n8n-fit.md` (do not repeat it),
`dfmcp/README.md` and enough of `dfmcp/` to know what a tool does today
(argument schema, role allowlist check, the `dfhack-run` or RPC call,
output cleanup such as the CP437 text fix, failed reads reported as unknown,
logging), and `agents/ROSTER.yaml` plus one role's `tools.yaml`.

The dispatch prompt names the user's other n8n project, a private work repo.
Read its workflow test and sync material for patterns. **Never name it, its
company, vendors, clients, workflows, files, hosts or credentials in anything
committed here.** Describe patterns only.

## The questions

1. **Testing.** What works in practice for n8n workflows: n8n's own features
   (pinned data, manual and partial executions, the evaluation or test-run
   features in current versions), CLI execution for CI, unit-style testing
   of a sub-workflow with fixed inputs, contract tests at the MCP trigger,
   mocking `dfhack-run` so tests run with no game, and regression tests that
   replay recorded real outputs. What does the user's other project do, and
   what does it find lacking? Propose a concrete test layout for one tool
   workflow, and say how it would run in this repo's CI alongside the
   existing pytest suites.
2. **Version control.** Git-backed workflow storage: n8n's own source
   control feature (and its licence tier), export/import via the CLI, the
   other project's sync approach (stable ids, stripping volatile fields,
   diffing), credential and secret separation for a public repo, reviewing a
   workflow diff in a PR, and environments (dev and live). Recommend one
   approach and say why.
3. **Node choice, with the user's preference as a hard constraint.** For a
   tool workflow of the shape "MCP trigger, validate arguments, call
   `dfhack-run`, parse JSON, handle failure, return": which native nodes do
   each step (If, Switch, Filter, Merge, Loop Over Items, Execute Workflow and
   sub-workflows, Error Trigger, Stop and Error, Set/Edit Fields, Execute
   Command, SSH, HTTP Request, the MCP Server Trigger and tool nodes). Where
   is a Code node genuinely unavoidable, and how small can it be kept? How
   are shared concerns (output cleanup, logging, the unknown-versus-false
   rule) factored into reusable sub-workflows instead of copied?
4. **Current facts that gate the pilot**, from n8n's own docs and changelog,
   stated with version numbers: whether Execute Command is disabled by
   default in current releases and how it is enabled; MCP Server Trigger
   authentication options (bearer or header auth, one per trigger?); how a
   tool workflow's input schema is declared so an MCP client sees typed
   arguments; whether one tool workflow can attach to several triggers.
5. **Worked sketch.** Describe, node by node in words, one real read tool
   (for example `zone list`) and one real write tool (for example `zone
   place`) as n8n workflows under the constraint above, including the tests
   each would have.

## What to produce

`research/2026-09-25-n8n-testing-vc-nodes.md`: a bottom line first, then the
answers, the worked sketch, and "What could not be verified". Mark claims as
n8n docs (with version), the user's other project (pattern only), or this
repo's source.

## Rules

- `git merge --ff-only main` first; this brief is committed on main.
- You own that research file and this doc's Result section only. Not
  `Working.md`, `decisions/`, `memory/`, `handoffs/INDEX.md`. Nothing in the
  other repo; never read any secrets or .env file there.
- **Before committing, grep your output for the other repo's name, its
  company, and any workflow or file name you read there. Zero hits.**
- No em dashes in prose. **No attribution lines in any commit message.**
- Commit after each milestone. Stop and report on any permission refusal.

## Done means

A testing approach and a version-control approach the user can adopt, a node
map that keeps logic in nodes rather than code, the gating facts settled with
versions, and the two worked sketches.

## Result

Done. `research/2026-09-25-n8n-testing-vc-nodes.md` written and committed
(`66b5f0d`, branch `worktree-agent-a9e407a5179bd48ae`).

**Bottom line.** A pilot is workable under the hard constraint (control
flow in nodes, not Code blocks), but three gating facts (whether Execute
Command can be turned on, MCP Server Trigger auth, whether one tool
workflow can serve several triggers) need checking against the actual
installed n8n version before building. The single biggest design call the
research surfaced: have n8n's tool workflows call `dfmcp-server`'s own MCP
HTTP endpoint (as just another authenticated role-scoped client) rather
than reimplementing `dfhack-run` argv construction, JSON parsing and the
CP437 backstop as native n8n nodes, so every bug already fixed in
`dfmcp/` stays fixed once, not twice.

**Testing.** Two layers: (1) static `pytest` checks with no Docker or n8n,
diffing each workflow's declared schema against `dfmcp.tools.tool_definitions`
and checking no mutating node reaches a read-tool workflow or a
non-Overseer trigger; (2) `n8n execute-batch --snapshot`/`--compare`
against test-tagged twin workflows with `Code`-node fixtures standing in
for the HTTP call to `dfmcp`, never `pinData` (confirmed CLI-ignored). A
third, un-gated contract test (a real MCP client against a real running
n8n instance) is named as the one thing neither layer can prove.

**Version control.** Git as sole source of truth, one-directional
(git to n8n), adopting the other project's pattern: a stable hand-chosen
workflow `id`, a field-stripping diff (top-level only, never at node
depth), one-file-at-a-time import (a real n8n 2.x tag-table bug), and a
deploy step that reads n8n back afterward because `import:workflow`'s exit
code proves nothing.

**Gating facts, with versions (n8n docs, fetched 2026-09-25; stable line
2.40.6 per the docs changelog page):**
- Execute Command disabled by default since n8n 2.0; re-enabled only by
  clearing the whole `NODES_EXCLUDE` list (`NODES_EXCLUDE=[]`), no
  narrower per-node toggle documented.
- MCP Server Trigger: three auth options (None, Bearer auth, Header auth),
  one configuration per trigger node, so a per-role trigger design can
  give each role its own credential.
- Typed tool input schema: a "Workflow Input Schema" declared in the
  called sub-workflow, pulled into the calling tool node. Confirmed for
  the AI Agent's Tool Workflow sub-node; not independently confirmed this
  is the same path the MCP Server Trigger uses.
- Whether one tool workflow can attach to several triggers: not stated
  either way in n8n's docs. Architecturally plausible, not verified.
- `execute-batch` and its snapshot/compare flags do not appear in n8n's
  published docs at all; this project's own reliance on it is entirely
  secondhand from the other project's tested-against-2.40.5 findings, not
  independently re-run here.

**Node map.** MCP Server Trigger (one per role) to a typed tool node, `If`/
`Switch` for argument validation and the three-way unknown-vs-false
routing, `HTTP Request` to `dfmcp-server`'s own endpoint (or `Execute
Command`/`SSH` if calling `dfhack-run` directly), `Switch` into `Stop and
Error` on failure, shared `Execute Workflow` sub-workflows for logging and
any other cross-cutting concern. One Code node is genuinely earned (a
small argument-reshaping expression with no branch inside it); the
constraint that mattered was "zero decisions inside a Code node," not
"zero Code nodes."

**Worked sketches.** `zone.list` (read) and `zone.place` (write), each
node-by-node with their static and snapshot-compare tests, in the research
file's §5. The write sketch's most load-bearing test fixture: a real
placement response with `read_back` missing, which must not be silently
treated as success, mirroring this project's own `getRoomDescription`
false-negative history.

**What could not be verified:** multi-trigger reuse of one tool workflow;
whether the MCP-specific schema path matches the AI-Agent-facing one;
whether n8n's evaluation feature needs a paid tier; `execute-batch`'s
exact behaviour on whatever version this project actually installs;
whether `pinData` is ignored on the current release line versus only the
2.40.5 the other project tested; the n8n source-control feature's exact
license gate. All listed in the research file's own section.

**Pre-commit leak grep.** Ran a grep for the other project's name and a vendor/workflow-
name pattern grep (accounting-API and supplier-billing vendor names, host
ids) against the committed research file before committing: zero hits.
Every reference to the other project is in pattern form (an accounting
API, a supplier-billing pull, a workflow test directory) with no name,
host, vendor, or workflow/file identifier carried over.

No permission refusals encountered. No VM commands or installs were run.
