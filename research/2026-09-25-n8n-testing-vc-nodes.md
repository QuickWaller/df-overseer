# n8n testing, version control, and node choice for tool workflows

Date: 2026-09-25. Researcher, read-only. Answers
`handoffs/2026-09-25-n8n-testing-vc-nodes.md`. Builds on, does not repeat,
`research/2026-09-25-n8n-fit.md`.

## Bottom line

**A pilot is workable under the user's hard constraint (control flow in
nodes, not in Code blocks), but three gating facts have to be settled with
the actual installed version before anything is built**, because n8n's own
docs are thin or silent on exactly the questions that matter most here:
whether Execute Command can be turned on at all on the target host, what
authenticates a caller at the MCP Server Trigger, and whether one tool
workflow's logic can serve more than one role's trigger without being
copy-pasted. The two worked sketches below (§5) show the shape holds up:
every step in `dfmcp`'s tool pipeline (validate args, run `dfhack-run`,
parse JSON, apply the unknown-vs-false rule, log) maps to a native node, and
the one place a Code node is genuinely earned is small and single-purpose
(argument shape validation against a dynamic schema), never the control
flow around it.

**Testing**: use n8n's own CLI batch-execute-and-compare machinery
(`n8n execute-batch --snapshot`/`--compare`) as the workflow-level regression
layer, seeded with `Code`-node fixtures (not `pinData`, which the CLI
ignores) that mock `dfhack-run`'s output so tests need no live game; add a
thin static-shape check (a thing like a per-workflow schema/contract
assertion) run by the existing `pytest` suite with no Docker and no n8n,
mirroring how the other project's `vitest` layer checks workflow JSON
directly; keep manual/pinned-data runs in the n8n UI as the fast local loop,
never as the CI gate, since pinning is UI-only and silently ignored by both
CLI paths.

**Version control**: git as source of truth, one-directional (git to n8n),
same shape the other project already built and hardened through five real
bugs. Adopt the same disciplines: a stable hand-chosen `id` per workflow
file, a field-stripping diff that strips only top-level volatile keys,
import one file at a time (a real n8n 2.x bug, not a workaround for
something imagined), and a deploy step that re-reads n8n afterward to prove
the import actually landed, because `import:workflow`'s exit code and
console output do not.

## 1. Testing

Sources: n8n docs (fetched 2026-09-25, current docs site, no version pinned
on most pages) **[n8n docs]**; `dfmcp/` source **[this repo]**; the other
project's `docs/n8n-sync.md`, `docs/n8n-integration-depth.md`,
`scripts/test-n8n.sh`, and one workflow's `.test.ts` file, read for pattern
only **[other project, pattern]**.

### What n8n itself offers

- **Manual execution and pinned data.** Standard UI feature: run a workflow
  node-by-node or in full from the editor, and pin a node's output so
  downstream nodes replay it without re-calling anything live. **[n8n docs
  + other project, pattern]**: this is real and useful for interactive
  development, but the other project checked it against the installed CLI
  (`n8n execute`, `execute-batch`) by running a workflow with pinned
  fixtures and watching 146 live rows flow through instead of the 2 pinned
  items, `pinData` is **UI-execution-path-only**. The other project cites
  the CLI's own source (`dist/commands/execute.js`, `execute-batch.js`:
  zero references to `pinData`) against the UI's `workflow-runner.js`
  (four references) as the mechanism. **This repo did not re-derive that
  from source itself** (the other repo's `node_modules`/`dist` were not
  read here, only the doc describing the finding), so it is reported as
  **[other project, pattern]**, one level short of this pass's own primary-
  source read, but it is exactly the kind of "checked the installed
  version, not assumed from docs" finding this project's own evidence
  standard asks for, and it is corroborated by n8n's docs never claiming
  pinned data is CLI-visible anywhere this pass found.
- **The Evaluation node / Evaluation Trigger.** n8n docs
  (`docs.n8n.io/build/integrate-ai/test-and-improve-ai-workflows/...`)
  describe a dedicated evaluation feature: "a crucial technique for
  checking that your AI workflow is reliable," built for comparing model
  outputs, catching regressions in LLM-produced content, and scoring
  against metrics **[n8n docs, `understand-why-to-test.md`,
  `run-quick-evaluations.md`, `use-metrics-to-measure-quality.md`]**. **Not
  the right tool here.** Every tool workflow this project would build is
  deterministic (validate args, shell out, parse JSON) with no model call
  in the loop; the evaluation feature's entire design is about scoring
  non-deterministic LLM output, a problem this project's tool workflows do
  not have. **Not independently verified**: whether it requires a paid
  license tier, the fetched pages say nothing about plan gating either
  way, so this is a real gap rather than a confirmed "free" answer.
- **CLI `execute` / `execute-batch` with snapshot/compare.** n8n's own docs
  (`deploy/host-n8n/configure-n8n/use-the-command-line.md`) confirm
  `n8n execute --id <ID>` as a documented command **[n8n docs]**. **The
  `execute-batch` command, and its `--snapshot`/`--compare`/
  `--githubWorkflow`/`--retries`/`--concurrency`/`--skipList` flags, do not
  appear anywhere in n8n's own published docs** that this pass's sitemap
  search and page fetches found, this is a real docs-vs-reality gap,
  flagged per this project's own evidence standard rather than silently
  assumed to be documented. The evidence for `execute-batch`'s existence
  and exact flag set is entirely **[other project, pattern]**: it was found
  by testing the real installed CLI (version 2.40.5) and used in production
  there (`scripts/test-n8n.sh`, `npm run test:n8n`). **Prefer the tested
  reality over the docs' silence**, consistent with "where docs and code
  disagree, prefer the code", but note this repo's researcher did not
  independently run the command against a live n8n instance; this is
  secondhand confirmation of a primary-source finding, not a fresh
  primary-source read.
- **`import:workflow` deactivates on import.** n8n's own docs confirm this
  directly, independent of the other project: "By default, `import:workflow`
  deactivates every imported workflow" **[n8n docs,
  `use-the-command-line.md`]**, with an escape hatch this repo had not seen
  cited elsewhere: `--activeState=fromJson` preserves the active flag from
  the JSON file, but **only in multi-main or queue mode**, not the plain
  single-instance self-hosted mode either project runs. This corroborates,
  from n8n's own docs rather than only from the other project's testing,
  the "deploy re-arms what was already armed" problem: the safe fix (record
  what was active before import, re-arm exactly that afterward, tell the
  operator to restart) is the one already proven in production
  **[other project, pattern]**, and there is no config flag that makes it
  unnecessary on a single-instance deployment.

### What the other project does, and finds lacking

**[other project, pattern only, no names, hosts, vendors, or workflow
files repeated here]**

- Real workflow-level tests live as committed workflow files under a
  `tests/` subdirectory, each tagged distinctly from production workflows,
  each ending every branch in an explicit "landed" marker node rather than
  an error-stop, so a correct run visibly succeeds rather than merely not
  crashing.
- Every fixture that stands in for a live external call is a `Code` node
  inside the *test* workflow, never `pinData` (see above) and never a real
  credentialed call, a static check independently confirms no live-service
  node exists in a test workflow at all.
- A CLI test script imports the test workflows one file at a time (working
  around the same n8n 2.40.5 shared-tag import bug described in §2),
  captures a snapshot on `--update`, and on a normal run compares against
  the committed snapshot, deciding pass/fail from the reported execution
  counts rather than the process exit code, because `execute-batch`, like
  `import:workflow`, can exit 0 on a run that itself reports failures.
- A **second, independent layer with no Docker and no n8n at all**: a plain
  unit-test-framework file that loads the committed workflow JSON straight
  off disk and asserts static shape facts about it, every HTTP node
  hitting a specific real API uses only a safe method, no write-capable
  node type appears anywhere in the graph, every connection references a
  node that actually exists, parameterised queries only. This is the
  layer that runs in ordinary CI with no external service, and it exists
  because the snapshot-compare layer proves the **branches behave**, not
  that **no node in the graph could misbehave**, a structural guarantee a
  behavioural test cannot give by construction.
- **What it finds lacking**, stated directly in that project's own record:
  no compile-time type guarantees (a test only catches what someone thought
  to write, where a type error cannot compile at all), and execution
  history retention meaning any real payload run through a workflow lives
  in n8n's own database as well as wherever the workflow itself stores it ,
  both flagged as "things to handle," not blockers.

### Proposed test layout for df-overseer, and how it runs in this repo's CI

Two layers, mirroring the other project's two-layer shape but adapted to
this project's actual risk (a wrong DFHack argv, a misread unknown-vs-false
result, a write tool skipping a required guard), not that project's risk
(a wrong ledger amount):

1. **Static shape tests, `pytest`, no Docker, no n8n, no VM.** A new
   `dfmcp/tests/test_n8n_workflows.py` (or a `tools_n8n/tests/` directory,
   parallel to `dfmcp/tests/`) loads each committed tool-workflow JSON file
   directly and asserts, per workflow: every node id referenced by
   `connections` exists and vice versa; the workflow's declared
   `inputSchema`/parameter definitions match the same argument names,
   types, and required set `dfmcp/tools.py` already derives for that tool
   id from `TOOLS.yaml` (a drift test, the same class of protection
   `dfmcp/README.md` already describes for the canonical-id scheme); no
   node in a **read**-tool workflow is an Execute Command, SSH, or any node
   whose parameters could mutate fort state (the DFHack tool it calls is
   itself read-only, checked against the registry's own `mutates` flag);
   a **write**-tool workflow contains exactly the `dfhack-run` invocation
   the registry expects and no other Execute Command/SSH node; every
   workflow is tagged and inactive by default, matching the other project's
   "deployed workflows arrive inactive" discipline. This is the layer that
   runs in the existing `python -m pytest` / `.venv-dfmcp` pass, needs no
   n8n instance, and is the layer least likely to be skipped by accident.
2. **Snapshot/compare execution tests, `n8n execute-batch`, needs a running
   n8n (Docker, same as the other project's shape) but no live DFHack and no
   VM 103.** One test-tagged workflow per tool, wired identically to the
   real one except that the node calling `dfhack-run` is replaced with a
   `Code` node returning a fixed, committed fixture string (the exact
   stdout a real `df-overseer-zone.lua list` or `df-overseer-zone.lua
   place` call would print, captured once from a real run and committed as
   the fixture, the same "capture once, treat as read-only, diff on
   change" discipline `docs/n8n-sync.md`-equivalent rules already apply to
   the workflow JSON itself). Covers exactly what the fixture drives: the
   unknown-vs-false rule on a DFHack failure output, the CP437 backstop's
   text on a name field, an `ArgumentError`-shaped rejection on bad input,
   and a role-appropriate refusal path. `--compare` decides pass/fail from
   the reported execution counts, not the process exit code, per the other
   project's own finding that both `import:workflow` and `execute-batch`
   can report success while doing nothing or failing.
3. **CI wiring.** Layer 1 runs in the existing pytest job with no new
   infrastructure. Layer 2 needs an n8n container in CI, which this repo
   does not have today; the honest scoping call is to run layer 2 as a
   separate, explicitly-gated job (or a pre-push hook mirroring the other
   project's, run locally before a workflow-touching commit) rather than
   blocking the existing `pytest`/`dfmcp/tests` suites on standing up
   Docker in CI, consistent with `CLAUDE.md`'s existing "ambient pytest"
   versus "`.venv-dfmcp`, all 691" two-tier pattern already in this repo,
   which already accepts that not every test tier runs in every context.
4. **Contract test at the MCP boundary.** Whether the MCP Server Trigger
   actually presents the workflow's declared schema as typed arguments to
   a real MCP client is not something either the static or the
   snapshot layer proves (both operate on the workflow graph, not on the
   MCP wire protocol). A third, thin check, the same shape
   `dfmcp/tests/test_server.py` already uses today, a real MCP Python SDK
   `ClientSession` against the running instance, is the only way to prove
   this end to end; not proposed as a CI gate given the Docker-and-live-n8n
   cost, but named here as the honest gap between "the workflow looks
   right" and "an MCP client actually sees a typed tool," mirroring exactly
   the gap `dfmcp/README.md` itself already documents between its own
   in-process ASGI tests and the live VM 103 smoke test that caught the
   real `structuredContent` bug.

## 2. Version control

- **n8n's own "source control" feature is Enterprise-licensed**, not
  available on the Community edition this project's own operational shape
  (self-hosted, no license) would run, **not independently re-verified
  against n8n's current docs in this pass** (no page describing the
  git-integration feature's license gate was fetched; this line carries
  forward `research/2026-09-25-n8n-fit.md`'s own finding that n8n has "no
  first-class git integration for community/self-hosted workflow JSON," not
  a fresh read). Treated as settled for this project regardless: even were
  a license available, the honest workflow either way is "build in the UI,
  capture the diff, commit," per both n8n's own docs describing manual
  export/import and the other project's own experience.
- **Adopt the other project's approach, described here only in pattern
  form**: git as sole source of truth, deploy strictly one-directional
  (git overwrites n8n), with a `diff` step treated as the load-bearing
  half, "undetected divergence was the problem; detected divergence is
  just a to-do item." Concretely, for this repo:
  - Every tool workflow file carries a **hand-chosen, never-reused `id`**
    (n8n's importer matches by `id`, not name; an id-less file re-imports
    as a new duplicate on every deploy, found the hard way elsewhere,
    worth avoiding here by rule from the first file rather than
    rediscovering it).
  - A **field-stripping diff/comparison** before any commit or PR review,
    stripping only genuinely instance-local top-level keys
    (`versionId`, `createdAt`, `updatedAt`, `active`, `pinData`,
    `staticData`, `triggerCount`, `shared`, `homeProject`, `scopes`, and
    similar, the exact list needs re-deriving against whatever n8n
    version this project actually installs, not copied verbatim from the
    other project's own list, since that list is itself version-specific
    findings, not documented n8n behaviour), critically, **never at node
    depth**: a node's own internal `id` must survive stripping, a lesson
    the other project paid for once with corrupted captures.
  - **Import one file at a time**, not a directory batch, this is real
    n8n 2.x behaviour (a shared-tag race in the tag table on a batch
    import with a new tag), not a workaround for something imagined, and
    it will reproduce on this project's install if workflow files share a
    role-based tag (`architect`, `overseer`, `read-only`, and so on, the
    natural tagging scheme for a role-scoped MCP allowlist) and are
    imported together for the first time.
  - **Deploy re-arms what was already armed, and verifies the import
    actually landed by reading n8n back afterward**, both are direct
    consequences of two confirmed n8n behaviours (§1's `import:workflow`
    deactivate-on-import default, and the exit-code-lies-about-success
    problem both `import:workflow` and `execute-batch` share), not
    speculative caution.
- **Credentials.** This repo already has the exact discipline the other
  project independently arrived at: secrets never in git, a gitignored
  local file with a committed empty-placeholder counterpart
  (`infra/local.example.*`, `.env` for `dfmcp`'s own bearer tokens). n8n
  workflow JSON references a credential by id and name but never its value
  **[n8n docs, general behaviour, consistent with the other project's own
  finding]**, the practical consequence for this project is the same one
  named there: a credential (here, a `dfmcp` role's bearer token, held by
  n8n as an `HttpHeaderAuth` or `HttpBasicAuth`/bearer credential referring
  to `dfmcp`'s own MCP HTTP endpoint) must be created once per n8n
  instance with a stable name, and re-bound by hand the first time a
  workflow lands on a new instance, not yet a problem with one instance,
  worth writing down now per the other project's own stated reasoning for
  writing it down early.
- **Reviewing a workflow diff in a PR.** The field-stripped, depth-aware
  JSON diff above is directly reviewable in an ordinary PR the same way any
  other JSON config file is; nothing about n8n workflow JSON needs a
  special PR tool once the volatile fields are gone, per the other
  project's own "a diff you trust is the entire point" framing.
- **Environments (dev and live).** Not deeply explored by either source for
  this project's specific case (df-overseer has no dev/live n8n split
  planned yet, unlike the other project's laptop-versus-eventual-server
  split); the transferable piece is simply that credential names must
  match exactly across environments since ids do not, which stays true
  however many environments this project ends up with.
- **Recommendation: adopt the other project's approach as a pattern, build
  or share a small `n8n-sync`-shaped tool rather than reinventing the same
  five bugs (id-less duplicate imports, tag-batch race, silent
  deactivation, `pinData` false lead, exit-code-lies) from scratch.** This
  matches `research/2026-09-25-n8n-fit.md`'s own §4 finding, restated here
  because it is directly the version-control answer, not a side note: "this
  is a case for building a small shared `n8n-sync` tool (or documenting the
  pattern in this repo) rather than rediscovering the same
  six-duplicate-workflow and silent-deactivation bugs here."

## 3. Node choice

The shape asked for: **MCP trigger, validate arguments, call `dfhack-run`,
parse JSON, handle failure, return**, with the hard constraint that control
flow (branches, loops, error paths) is nodes, never Code-node logic.

| Step | Node(s) | Why this node, not Code |
|---|---|---|
| Entry | **MCP Server Trigger** (`n8n-nodes-langchain.mcptrigger`), one per role, matching the brief's "one trigger per role, the allowlist visible as which tool workflows attach to it" design | This *is* the allowlist boundary at the n8n layer, a tool node simply is or is not wired to a given trigger's canvas, which is a structural, at-a-glance fact, exactly the kind of thing this project's own `docs/AGENT-ARCHITECTURE.md` principle 8 ("a role is defined by its tool allowlist") wants visible, not buried in a condition |
| Declare typed args | The tool sub-node's own **Workflow Input Schema** (declared once, in the called sub-workflow, via its own trigger node's schema editor; n8n docs describe pulling these into the calling tool node with a "Refresh" action) **[n8n docs, `n8n-nodes-langchain.toolworkflow`]** | This is n8n's own typed-schema mechanism, not a Code node reinventing JSON Schema by hand; **not independently verified how this specific mechanism is exposed through an MCP Server Trigger specifically**, as opposed to the AI Agent's own Custom Workflow Tool sub-node, see "what could not be verified" |
| Validate arguments against `dfmcp`'s own rules (required/optional/enum/positional-optional trap) | **If** / **Switch**, chained: one condition per rule (`labor.set-labor`'s enum, `zone.place`'s `[W H]` all-or-nothing group, a missing required field) | The rules are already enumerable, `dfmcp/tools.py`'s `argv_for_call` raises one of five named `ArgumentError` cases; each is a single boolean condition, exactly what `If`/`Switch` are for. **One Code node is earned here** (see below), not five |
| Route on validation result / call result / effect (read vs mutate) | **Switch** | A DFHack-shaped result is one of a small closed set: success, `{"error": ...}` (a script-level failure, per `server.py`'s own "a script's own failure report is a tool error too" rule), non-JSON output, or a connection failure, `Switch` on a computed status field, not a chain of `If`s, matches the closed set directly |
| Call `dfhack-run` | **Execute Command** (self-hosted only, and only once explicitly re-enabled, see §4) targeting the exact `dfhack-run <script> <verb> <args...>` invocation `dfmcp/tools.py`'s `argv_for_call` already computes, OR **SSH** if n8n runs off VM 103 and reaches it over the network the way `dfmcp-server` itself is reached today | Matches this project's existing `dfhack-run` invocation shape exactly; `SSH` is the safer placement given `docs/AGENT-ARCHITECTURE.md` §13's existing reasoning that DFHack's RPC socket is local/unauthenticated and nothing should reach it except from VM 103 itself, an n8n instance on another host calling over SSH into a constrained command keeps that boundary intact the same way `dfmcp-server` itself does today, whereas Execute Command implies n8n runs colocated with DFHack |
| Parse JSON | **Set/Edit Fields** with an expression (`JSON.parse($json.stdout)`), or the HTTP-request-family nodes' own automatic JSON parsing if this ends up calling `dfmcp`'s own HTTP endpoint instead of shelling out directly (see the note below) | A single expression in a `Set` node's field, not a Code node, n8n's expression editor is a first-class node-parameter mechanism, not "code" in the sense the constraint is guarding against (it cannot hold a branch or a loop) |
| Failure paths: unreachable DFHack, non-JSON output, a script's own `{"error": ...}` | **Switch** (branch on which failure it is) into **Stop and Error** (a genuinely terminal call, matching `dfmcp`'s `isError=True` wire shape), never an uncaught exception | Matches `server.py`'s own existing "every failure becomes the identical wire shape... never a raised protocol-level error" design directly: `Stop and Error` with a structured message is n8n's equivalent of that rule, and using it explicitly (not letting a node throw and rely on the workflow's default Error Trigger) keeps the failure shape visible in the graph |
| The unknown-vs-false rule | **Switch**, one branch per one of the three states this project already insists on elsewhere (`nobles.requirements`'s "met / not_met / cannot_tell", `docs/TRAPS.md`'s caution against collapsing "could not determine" into "false") | This is exactly the shape a `Switch` is for: three named outcomes, not two, and nothing about it is a loop or an accumulation that would need a Code node |
| Output cleanup (the CP437 backstop) | Already done upstream, inside `df-overseer-textutil.lua`/`dfhack_client.py`'s own Python-side backstop, **not repeated in the n8n graph at all if n8n calls `dfmcp`'s own MCP HTTP endpoint rather than shelling out to `dfhack-run` directly** | This is the strongest argument in this whole map for having n8n call `dfmcp-server`'s existing HTTP endpoint (as "just another MCP client," per `research/2026-09-25-n8n-fit.md` §3) rather than reimplementing `dfhack-run` argv construction and CP437 handling as n8n nodes: every fix already shipped in `dfmcp/`'s Python (the CP437 backstop, the array-vs-dict `structuredContent` fix, the positional-optional trap) is inherited for free, and none of it needs a second implementation to keep in sync. See the note below the table |
| Logging | **A shared sub-workflow**, called via **Execute Workflow**, doing one thing: format and emit a log line matching `dfmcp.calls`' own shape (`event`, `ts`, `role`, `tool`, `tool_id`, `arguments`, `is_error`, `duration_ms`) | Reusable, not copied per tool workflow, exactly what `Execute Workflow` is for, and it keeps the log shape centrally defined the same way `server.py`'s own "one wrapper, every return path goes through it" design already does |
| Shared concerns generally (output cleanup, the unknown-vs-false rule, logging) | **Sub-workflows via Execute Workflow**, one per concern, called from every tool workflow | Matches the brief's own question directly: factor a concern into one sub-workflow, call it from N tool workflows, rather than copying five nodes into every tool workflow and letting them drift, this is n8n's own answer to "don't repeat yourself" and needs no Code node at all |
| Return to the MCP client | The tool sub-workflow's own output (n8n MCP tooling maps a sub-workflow's return value back through the trigger automatically) | No dedicated "return" node needed beyond producing the right final item shape |

### Where a Code node is genuinely unavoidable, and how small

**One place, and it should be kept to the single job of shaping a dynamic
argument-schema check, not any control flow around it.** `dfmcp/tools.py`'s
own argument validation is data-driven (a table of integer-arg names, a
table of arg descriptions, an enum list per token) rather than a fixed set
of fields known in advance, the same heuristic table the module's own
docstring calls "a documented heuristic, not knowledge." Reproducing that
exact heuristic as a chain of native `If`/`Switch` nodes per argument name
would either (a) hard-code the same table twice, in two languages, with no
shared source of truth, reproducing precisely the "which copy actually ran"
failure mode `docs/n8n-sync.md`-equivalent thinking exists to prevent, or
(b) genuinely need a small expression evaluating a lookup against a
JSON-encoded copy of that same table. **The node-count-minimising and
single-source-of-truth-preserving answer is neither**: call `dfmcp`'s own
MCP HTTP endpoint (an **HTTP Request** node, or, more simply, treat n8n as
just another MCP client authenticating with its own role token against the
already-running `dfmcp-server`) and let the existing Python do argument
validation, `dfhack-run` invocation, JSON parsing, CP437 cleanup and the
unknown-vs-false framing exactly as it already does for openclaw today.
**If a Code node is still wanted somewhere**, for instance, to reshape an
MCP tool-call payload into the exact JSON body `dfmcp`'s HTTP endpoint
expects, it should be a single expression-sized transform with no `if`,
`for`, or `while` in it: a literal one-line `return {...}` mapping fields,
never a branch. That is the actual boundary the user's rule draws: **not
"zero Code nodes," but "zero decisions inside a Code node."**

### The load-bearing design choice this map surfaces

Everything above points at one real fork the brief's shape does not settle
on its own: **should the n8n tool workflow reimplement `dfhack-run`
argv-construction and parsing as native n8n nodes, or should it call
`dfmcp-server`'s already-existing, already-tested MCP HTTP endpoint and let
n8n be "just another authenticated MCP client"?** The second option is
strongly favoured by everything this pass read: it is what
`research/2026-09-25-n8n-fit.md` §3 already concluded n8n's role should be
("another MCP-calling client that holds read-only role tokens... the same
shape as openclaw"); it inherits every bug fix already shipped in
`dfmcp/dfhack_client.py` and `server.py` (CP437, the `structuredContent`
array-vs-dict fix, the positional-optional trap, the log line shape) for
free; and it means the "one tool workflow per role, the allowlist visible
as which tool workflows attach to a trigger" design is a second, n8n-side
description of an authorization boundary `dfmcp`'s own `Roster.check`
already enforces server-side, belt and braces, not a new, independently
maintained implementation of the same rules that could drift from the
Python one. **The worked sketches in §5 are written against this reading**,
since the brief's own shape ("call `dfhack-run`") is ambiguous between
"shell out directly" and "call the MCP endpoint that shells out on your
behalf," and the second is the one that does not duplicate logic already
built, tested, and live on VM 103.

## 4. Current facts that gate the pilot, with version numbers

All version numbers below are **[n8n docs, fetched 2026-09-25]** unless
marked otherwise. The docs site itself does not consistently print a
version per page, so where a specific number is quoted it is quoted from
the page's own text, not inferred.

- **Execute Command is disabled by default from n8n 2.0 onward.** n8n's own
  docs for the node state directly: "the node is disabled by default from
  n8n 2.0" **[n8n docs, `n8n-nodes-base.executecommand`]**. It is enabled
  by setting the `NODES_EXCLUDE` environment variable to an empty list
  (`NODES_EXCLUDE=[]`) on a self-hosted instance **[n8n docs,
  `deploy/host-n8n/configure-n8n/security/block-specific-nodes`]**, this
  removes the entire default exclusion list, not just Execute Command
  specifically, which is worth flagging as a real gating fact of its own:
  there is no narrower "just re-enable this one node" toggle documented,
  only "clear the whole exclusion list." **Not verified against this
  project's actual planned n8n version**, the fetched pages did not name
  which n8n release line is current beyond what the changelog fetch
  separately showed (stable 2.40.6, beta 2.41.2 as of the changelog page's
  own content, 2026-09-25); whether "disabled from 2.0" still holds
  unchanged at 2.40.x was not independently re-confirmed on a changelog
  entry, only read off the node's own current doc page.
- **MCP Server Trigger authentication: three options, all in current
  docs, None, Bearer auth, Header auth** **[n8n docs,
  `n8n-nodes-langchain.mcptrigger`]**, confirming and sharpening
  `research/2026-09-25-n8n-fit.md`'s earlier finding that the trigger
  "defaults to no authentication." **One credential configuration per
  trigger node** (each MCP Server Trigger node has its own Authentication
  parameter), so a per-role trigger design (one trigger per role) can give
  each role its own bearer token or header credential, matching this
  project's own "role identity must be a credential, not a claim"
  principle (`dfmcp/README.md`'s description of `auth.py`), **not
  independently verified whether n8n enforces anything about token
  strength, reuse across triggers, or comparison-timing safety** the way
  `dfmcp/auth.py` deliberately does (`hmac.compare_digest` against every
  configured token); n8n's own docs pages fetched here say nothing about
  this, and it was not chased further.
- **Typed tool input schema.** A tool workflow declares a **Workflow Input
  Schema** in its own entry trigger; n8n docs for the related
  `Tool Workflow` node (the AI Agent's own sub-node for calling a
  workflow as a tool, `n8n-nodes-langchain.toolworkflow`) describe pulling
  those input fields into the calling node via a "Refresh" action, and
  describe parameter values as settable by fixed value, expression, or "let
  the AI model define it" (`$fromAI()`) **[n8n docs,
  `n8n-nodes-langchain.toolworkflow`]**. **Not independently verified**
  whether the MCP Server Trigger's own tool-attachment mechanism uses this
  exact same schema path, as opposed to a parallel one specific to MCP ,
  the MCP-specific doc pages fetched in this pass (`mcptrigger`,
  `build/integrate-ai/mcp-servers`) do not describe the schema-to-client
  mapping at all; this is inferred from the AI-Agent-facing tool node's
  docs, which is the closest documented analogue, not a confirmed MCP-path
  statement.
- **Whether one tool workflow can attach to several triggers.** **Not
  settled by n8n's own docs**, none of the pages fetched in this pass
  (the MCP Server Trigger page, the MCP servers integration page, or the
  Tool Workflow sub-node page) states this either way. The only
  documentary hint found is that "By default, this field contains a
  randomly generated MCP URL path, to avoid conflicts with other MCP
  Server Trigger nodes" **[n8n docs, `mcptrigger`]**, which establishes
  that multiple MCP Server Trigger nodes coexisting is an expected,
  supported shape, but says nothing about whether the *same* underlying
  tool sub-workflow (referenced by workflow id) can be wired as a tool
  node under more than one of them. **Architecturally plausible but
  unverified**: since a "Custom n8n Workflow Tool"-style tool node is
  itself just a reference to a workflow id plus a schema, nothing in what
  was read rules out attaching that same reference under two different
  trigger workflows, but this is inference from how the pieces are
  described, not a confirmed behaviour, and it should be checked against
  a real installed instance before the pilot's role-based trigger design
  leans on it.
- **`execute-batch` is not in n8n's own published docs at all**, as noted
  in §1, this is itself a gating fact worth stating plainly: the test
  layout this report recommends depends on a CLI surface n8n does not
  document, only on the other project's own tested-against-the-real-binary
  findings. Before relying on it for this project's CI, the same
  verification step (run `n8n execute-batch --help` against whatever
  version actually gets installed here) should happen fresh, not be
  assumed to carry over unchanged from a different installation.

## 5. Worked sketch

Both sketches assume the "n8n calls `dfmcp-server`'s existing MCP HTTP
endpoint" design from §3's "load-bearing design choice," since that is the
reading that avoids duplicating `dfmcp/`'s already-tested Python logic. Node
names below are descriptive, not literal n8n canvas labels.

### Read tool: `zone.list`

(`dfmcp/README.md`'s own description: "Every zone this fort has, filterable
by kind, owner, validity and landmark; an unfiltered call summarises rather
than flooding the caller." Read-only, `effect: read`, currently `status:
planned` per `agents/architect/tools.yaml`.)

1. **MCP Server Trigger**, the Architect's trigger, Bearer auth, holding
   the Architect's own `dfmcp` role token as an n8n credential (never the
   Overseer's).
2. **Tool node: `zone.list`**, declaring its Workflow Input Schema
   (`kind`, `owner`, `landmark`, all optional strings/enums, matching
   `dfmcp`'s own generated `inputSchema` for this tool id) so the calling
   MCP client sees the same typed arguments it would see calling `dfmcp`
   directly.
3. **Set/Edit Fields**, shape the incoming call into the JSON body
   `dfmcp-server`'s `tools/call` endpoint expects (`name`, `arguments`).
4. **HTTP Request**, `POST` to `dfmcp-server`'s MCP endpoint, Bearer auth
   using the same credential as step 1, `Retry On Fail` left at n8n's
   default (a transient network blip to VM 103 is worth one retry; a
   `Roster.check` denial is not transient and should not be retried).
5. **Switch** on the response shape: `isError == true` (with `error`
   text, a denial, a bad argument, or `dfmcp` itself reporting a DFHack
   failure) versus a clean `structuredContent`.
   - **Error branch → Execute Workflow (shared "log call" sub-workflow)**
     with `is_error: true`, then **Stop and Error** carrying `dfmcp`'s own
     reason string verbatim (never re-worded, this project's own
     `roles.py` already writes denial reasons meant to be shown to the
     caller, and re-wording them in n8n would be exactly the kind of
     "second, drifting copy" this report argues against elsewhere).
   - **Success branch → Execute Workflow (shared "log call" sub-workflow)**
     with `is_error: false`, `result_chars` computed from the response.
6. **Switch** on the zone list's own contents (three-state, not two, per
   §3's unknown-vs-false row): a normal list (possibly empty, an
   unfiltered call legitimately summarising to "no zones of this kind"
   is not an error), versus `structuredContent` missing the expected
   `zones` key entirely (a shape this project would treat as `cannot_tell`,
   never silently coerced to "none exist"), so a caller several hops away
   from the raw JSON cannot lose that distinction.
7. Return the (possibly summarised, per `dfmcp/README.md`'s own design)
   zone list to the calling MCP client.

**Tests for this workflow:**

- **Layer 1 (static, pytest, no n8n).** Assert: the declared Workflow
  Input Schema's `kind`/`owner`/`landmark` fields and types match
  `dfmcp.tools.tool_definitions`'s generated schema for `zone.list` under
  the architect role, exactly (a drift test); no Execute Command, SSH, or
  any node type capable of a direct fort mutation appears anywhere in the
  graph (this is a read tool, nothing here should even have the
  *capability* to shell out); the "log call" sub-workflow is referenced by
  `Execute Workflow`, not copy-pasted, on both the success and error
  branches.
- **Layer 2 (snapshot/compare, `execute-batch`, needs n8n but no VM
  103/no live game).** A test-tagged twin workflow with the `HTTP Request`
  node's target swapped for a `Code` node returning one committed fixture
  per case: a normal multi-zone `structuredContent` (asserting the
  `zones` array passes through unmodified), an empty-list
  `structuredContent` (asserting this is *not* routed to the error branch,
  the empty-vs-cannot-tell distinction this project has already been
  burned by once, per `getRoomDescription`'s own false-negative history in
  `CLAUDE.md`'s status banner), a `{"error": "..."}`-shaped denial fixture
  (asserting it reaches `Stop and Error` with the reason string intact,
  byte-for-byte), and a malformed-JSON fixture (asserting the same error
  path, not an uncaught exception). Snapshots committed, compared on every
  run.
- **Contract test (not gated in CI, named as a real gap per §1 item 4).**
  A real MCP client session against a real running n8n instance, calling
  through the actual MCP Server Trigger, proving the declared schema is
  what a genuine external MCP client actually receives, the one thing
  neither layer above can prove by construction.

### Write tool: `zone.place`

(`dfmcp/README.md`/`TOOLS.yaml`: places one zone of `KIND` at the
`RANK`-th site near a landmark; `DRY_RUN` defaults to true, only an
explicit `false` places for real; `effect: mutate`; currently denied to
every role but the sole writer, per `agents/architect/tools.yaml`'s own
`deny` list, "Advisors do not act. Propose it.")

1. **MCP Server Trigger**, the **Overseer's** trigger only (the sole
   writer, per `agents/ROSTER.yaml`), a structurally separate n8n
   credential/token from every advisor trigger, mirroring
   `dfmcp/roles.py`'s own hard rule that no advisor role may ever be
   granted a `mutates` tool.
2. **Tool node: `zone.place`**, schema `kind`, `landmark`, `rank`,
   optional `w`/`h` (the all-or-nothing group), `owner`, and `dry_run`
   (defaulting `true` in the schema itself, matching `dfmcp`'s own
   default, so an n8n-side caller cannot accidentally omit it into a real
   placement).
3. **If**, `dry_run == false` **AND** the calling context is not itself
   already inside a dry-run test fixture (a literal boolean the shared
   "log call" sub-workflow also reads, so a real placement is distinguishable
   in the log from a preview even before the response comes back) →
   branch into "real placement" logging (a distinct log line/tag,
   matching `docs/n8n-sync.md`-equivalent thinking that a schedule/write
   path deserves visibly different handling than a read path) before
   proceeding; otherwise straight through.
4. **Set/Edit Fields**, shape the call body, same as the read sketch.
5. **HTTP Request**, `POST` to `dfmcp-server`, Bearer auth with the
   Overseer's credential. **`Retry On Fail` explicitly disabled on this
   node**, a genuinely mutating call must never be silently retried by
   n8n's own retry machinery on an ambiguous timeout, since a retried
   `zone.place` could double-place if the first attempt actually landed
   but the response was lost; this is exactly the class of concern
   `docs/AGENT-ARCHITECTURE.md` §13's "DF has no transaction boundary"
   reasoning already flags, applied here to n8n's own error-handling knob
   rather than to a second writer.
6. **Switch** on response shape, same three-way split as the read sketch
   (`isError`, a clean result, or a script-level `{"error": ...}` /
   `quickfort_error` field alongside real data, `server.py`'s own
   documented distinction that an object carrying an error-like field
   *alongside* real data is still an ordinary result, not an error,
   for `dig`/`build`/`zone.place`'s own `quickfort_error`).
7. **Switch** on `dry_run` in the echoed request: a dry-run result routes
   to a "preview" output shape (validation ok/not-ok, tile count, no
   `read_back` field expected); a real placement result routes to a
   branch that specifically checks for the `read_back` field
   (`dfmcp/README.md`'s own description: "a real run reads the zone back
   ... and reports quickfort's own statistics"), **treating a real
   placement response with no `read_back` field as its own distinct
   failure case**, not silently accepted as success, since `TOOLS.yaml`'s
   own notes on this exact tool already describe reading the placement
   back as the actual evidence a write happened, not merely that the call
   returned without error.
8. **Execute Workflow (shared "log call" sub-workflow)** on every branch,
   tagged with the real-vs-dry-run distinction from step 3.
9. Return the result (preview or confirmed placement) to the calling MCP
   client.

**Tests for this workflow:**

- **Layer 1 (static).** All of the read-tool checks, plus: assert the
  workflow's declared schema's `dry_run` field defaults to `true`; assert
  no test-tagged twin of this workflow (see below) has `dry_run` fixed to
  `false` anywhere in a committed fixture, so a CI run can never
  accidentally exercise a real placement; assert the MCP Server Trigger
  this workflow is attached to is the Overseer's trigger and *only* the
  Overseer's, a static graph check that this write tool is not
  reachable from any advisor-role trigger, the n8n-side mirror of
  `dfmcp/roles.py` rule 2's own hard check.
- **Layer 2 (snapshot/compare).** Fixtures for: a dry-run validation
  success (`ok`, tile count, no `read_back`); a dry-run validation
  failure (the soil-cannot-be-smoothed class of refusal `TOOLS.yaml`'s
  own notes describe elsewhere in this project); a real-placement success
  fixture including a populated `read_back` (asserting the workflow's own
  step-7 check passes); and, deliberately, a **real-placement response
  with `read_back` missing** (asserting step 7's guard actually fires
  and this is *not* silently treated as success), this last fixture is
  the single most important one in the whole sketch, because it is
  testing the exact class of gap (a write reported successful without
  independent evidence it actually happened) `CLAUDE.md`'s own status
  banner names as a real bug this project already found once elsewhere
  (`getRoomDescription`'s false negative, the mirror-image failure of the
  same underlying discipline: never trust an absence of a signal as
  positive evidence either way without an independent read).
- **Contract test.** Same shape as the read tool's, with one addition:
  proving that an MCP client authenticated as a non-Overseer role
  genuinely cannot see or call this tool through its own trigger, the
  n8n-side analogue of `dfmcp/tests/test_server.py`'s own "the call never
  reaches the fake DFHack at all" load-bearing test.

## What could not be verified

- **Whether one tool workflow can attach to more than one MCP Server
  Trigger.** Not stated either way in any n8n doc page fetched in this
  pass. Architecturally plausible (a tool node is a reference plus a
  schema, and nothing read here structurally forbids reuse), but this is
  inference, not a confirmed behaviour, check against a real installed
  instance before the pilot's per-role-trigger design depends on it,
  exactly as the brief asked to have settled.
- **Whether the MCP Server Trigger's own schema-to-client mapping uses the
  same "Workflow Input Schema" mechanism documented for the AI Agent's
  Tool Workflow sub-node**, as opposed to a separate, MCP-specific path.
  Inferred from the closest documented analogue, not independently
  confirmed against the MCP-specific doc pages, which say nothing about
  this mapping at all.
- **Whether n8n's evaluation feature (§1) requires a paid license tier.**
  Not stated in the pages fetched; genuinely unknown rather than assumed
  free. Moot for this project's use case regardless, since the feature
  targets LLM-output scoring and this project's tool workflows are
  deterministic.
- **`execute-batch`'s exact behaviour and flag set on whatever n8n version
  this project actually installs.** Entirely carried over from the other
  project's own tested findings against version 2.40.5; not independently
  run against a live instance by this research pass, and not documented by
  n8n at all as far as this pass's docs search found. Re-verify against
  the real installed binary (`n8n execute-batch --help`) before relying on
  it for this project's own CI.
- **Whether `pinData` is genuinely ignored by the CLI on the current n8n
  release line**, as opposed to only the specific version (2.40.5) the
  other project tested. Carried over from that project's own primary-source
  read of `dist/commands/execute.js`; not re-read from this project's own
  install (none exists yet) or from n8n's upstream source directly by this
  pass.
- **The n8n source-control feature's exact license gate.** Carried forward
  from `research/2026-09-25-n8n-fit.md`'s own finding rather than freshly
  re-checked against current docs in this pass.
- **Whether `NODES_EXCLUDE=[]` is the only way to re-enable Execute Command**,
  or whether a narrower per-node allowlist mechanism exists on some n8n
  plan tier. The fetched docs page described only the whole-list-clearing
  approach.

## Pre-commit leak grep

Run before every commit touching this file, per the brief's explicit
requirement: grep for the other project's own name/company and for every
workflow, file, host, or credential name read there. This pass's own check
(described in the Result section of the handoff) found zero hits; the
report above deliberately describes every finding from that project in
pattern form only (an accounting API, a supplier-billing pull, a workflow
test directory, a sync script) and never quotes an actual filename,
vendor, workflow id, or the repository's own name.

## Sources

- n8n docs, fetched 2026-09-25: `n8n-nodes-base.executecommand`,
  `deploy/host-n8n/configure-n8n/security/block-specific-nodes`,
  `n8n-nodes-langchain.mcptrigger`, `n8n-nodes-langchain.toolworkflow`,
  `build/integrate-ai/mcp-servers`, `build/integrate-ai/test-and-improve-
  ai-workflows/understand-why-to-test`, `n8n-nodes-base.evaluationtrigger`,
  `deploy/host-n8n/configure-n8n/use-the-command-line`, the docs sitemap,
  and the docs changelog page (stable 2.40.6 / beta 2.41.2 as read on
  2026-09-25).
- This repo: `CLAUDE.md`, `dfmcp/README.md`, `dfmcp/tools.py`,
  `dfmcp/dfhack_client.py`, `dfmcp/server.py` (via README description),
  `scripts/dfhack/TOOLS.yaml` (zone commands), `agents/ROSTER.yaml`,
  `agents/architect/tools.yaml`, `research/2026-09-25-n8n-fit.md`.
- The user's other private repo (not named here): its `docs/n8n-sync.md`
  and `docs/n8n-integration-depth.md`, its `scripts/test-n8n.sh`, and one
  workflow's `.test.ts` file, read-only, pattern-only, no names, hosts,
  vendors, or workflow/file identifiers carried into this report.
