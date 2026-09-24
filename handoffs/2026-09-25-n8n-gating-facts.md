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
