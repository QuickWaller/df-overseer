# Handoff: settle the three open n8n facts from source (and a local run if cheap)

Date: 2026-09-25. **Researcher. No VM, no install on any project machine.**

Read `research/2026-09-25-n8n-testing-vc-nodes.md` (its gating-facts and
"could not verify" sections) first. The user asked for these three checked.

## The three facts

1. **Can one tool workflow serve several MCP Server Triggers?** Concretely:
   can the same sub-workflow be exposed as a tool on two triggers (one per
   role), and what is duplicated per trigger (a thin tool node only, or the
   logic)? Any constraint on tool names colliding across triggers?
2. **Does the MCP Server Trigger give an MCP client typed arguments** from a
   tool workflow's declared input schema (the "Workflow Input Schema" /
   Execute Workflow Trigger inputs), the same way the AI Agent's tool
   sub-node does? What does the `tools/list` entry actually contain
   (JSON Schema types, required fields, descriptions)?
3. **`n8n execute-batch`**: does it exist in current n8n, which flags
   (`--snapshot`, `--compare`, and others), what they do, and whether it is a
   supported or internal command. Also whether `pinData` is ignored by CLI
   execution.

## Method

Primary source first: clone `n8n-io/n8n` at the current stable release tag
(say which) into a scratch directory outside the worktree and read the code:
the MCP Server Trigger node, the workflow tool node, the CLI commands.
Quote paths and short excerpts. Docs second.

**Optional, only if Docker is already installed and running on this
workstation** (check, do not install it): run the n8n image locally, build a
throwaway trigger plus tool workflow, and call `tools/list` with a real MCP
client to observe facts 1 and 2 directly. Remove the container and its data
after. If Docker is not already there, skip this and say so. Never touch VM
103, VM 106 or any other project machine.

## What to produce

Append a section "Gating facts checked, 2026-09-25" to
`research/2026-09-25-n8n-testing-vc-nodes.md`: each fact answered yes, no or
partly, with how you know (source path at tag, docs, or observed locally),
and what it means for the pilot design (one MCP trigger per role, one
workflow per tool calling `dfmcp-server` over HTTP).

## Rules

- `git merge --ff-only main` first; this brief is committed on main.
- You own that research file's new section and this doc's Result section.
- Nothing from the user's other n8n project is needed; do not read it.
- No em dashes in prose. **No attribution lines in any commit message.**
- Commit after each milestone. Stop and report on any permission refusal.

## Result

Done, 2026-09-25. Cloned `n8n-io/n8n` at the `stable` tag, which resolves to
`n8n@2.40.6`, into a scratch directory outside this worktree, read the
node/CLI source, then deleted the clone (nothing from it committed). Docker
was already running on this workstation, but the only container up is the
user's other n8n project's own instance; per the brief that project is
off-limits, so no local n8n run was done. The source read answered all
three questions directly and a live run was judged not worth the container
spin-up. Full detail, quotes and file:line citations in
`research/2026-09-25-n8n-testing-vc-nodes.md`, new section "Gating facts
checked, 2026-09-25".

Summary of the three facts, each confirmed from source at `n8n@2.40.6`:

1. **One tool workflow on several MCP Server Triggers: yes.** Each
   `McpTrigger` builds its tool list only from its own `ai_tool`
   connections (`McpTrigger.node.ts`, `helpers.ts:getConnectedTools`); the
   re-usable unit is the sub-workflow a `ToolWorkflow` node calls by
   `workflowId`. What duplicates per trigger is the thin `ToolWorkflow` node
   (or its wiring, if one instance fans out to two triggers), never the
   sub-workflow's logic. No cross-trigger tool-name registry exists, so no
   cross-trigger collision risk; a same-canvas, same-trigger name clash is
   not deduplicated by n8n itself.
2. **Typed arguments in `tools/list`: yes.** `McpServer.ts` converts every
   tool's Zod schema to a real draft 2020-12 `inputSchema` via
   `zodToDraft202012`. For `ToolWorkflow`, that schema is built from
   `$fromAI()` placeholders which the node's "Refresh" action populates
   from the sub-workflow's own declared Workflow Input Schema, via the same
   `extractFromAIParameters`/`createZodSchemaFromArgs` pipeline the AI
   Agent's own tool sub-nodes use. So it is the same typed-schema mechanism,
   reached through one relay step, not a separate weaker path.
3. **`execute-batch` exists, is real and current, and `pinData` is
   CLI-ignored by design: yes.** `packages/cli/src/commands/execute-batch.ts`
   is a live `@Command` with exactly the flag set the earlier pass reported
   (`--snapshot`, `--compare`, `--shallow`, `--githubWorkflow`, `--skipList`,
   `--retries`, `--concurrency`, `--ids`, `--output`, `--debug`,
   `--shortOutput`). `workflow-runner.ts`'s `resolvePinData` returns
   `undefined` for any execution mode other than `manual`/`evaluation`, and
   both `execute.ts` and `execute-batch.ts` run with `executionMode: 'cli'`
   so pinned data is excluded by an explicit mode check in the runner
   itself, confirmed first-hand rather than inferred from the CLI files'
   silence.

**For the pilot**: all three findings support the existing design (one tool
workflow's logic reused across role triggers via thin `ToolWorkflow` nodes;
build the sub-workflow's input schema first and let triggers inherit it
typed; use `execute-batch --snapshot`/`--compare` with `Code`-node fixtures,
never `pinData`, as the CLI-driven regression layer). Nothing here changes
the report's bottom line; it removes the three "not independently verified"
flags the previous pass left open.

Branch: `worktree-agent-a9b62f00e3105a5d8`. Commit `e8ffc0b` on that branch
carries this result and the research file's new section.
