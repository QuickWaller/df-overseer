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
