# Stream: doc drift pass after the queue, the rebuild and the first ruling

**Written** 2026-09-16. **Status:** dispatched. **User go-ahead:** "put a
sonnet on updating docs". Execution by a Sonnet executor.

## Why

Four days of live work landed since most of the docs were written: the MCP
server and queue went live on VM 103, VM 106 went dark and was rebuilt,
incident capture shipped, and the Overseer made its first ruling as a second
openclaw agent. Several documents still describe the world before that.
Known-stale examples, not an exhaustive list:

- `agents/ROSTER.yaml` header: "STATUS 2026-09-12: nothing here is running
  yet. The MCP server these allowlists reference does not exist."
- `dfmcp/README.md` around its status lines (one says nothing it produces was
  installed or started anywhere).
- `docs/AGENT-ARCHITECTURE.md`: deployment topology and §14's open list,
  written as design. Two agents now run for real on VM 106, the queue is
  live, and one ruling exists.
- `agents/overseer/model.yaml`: names `anthropic/claude-opus-5`. The first
  ruling ran on `deepseek/deepseek-v4-pro` for budget, a deliberate, recorded
  deviation. The file should say so without changing the design default.
- `ROADMAP.md` Now bucket: the ruling item is done; the fort being paused is
  the blocker for the next two.
- `CLAUDE.md`'s status block: partly updated already; check every line.

## Ground truth

Read these first and treat them as the source of truth. Where a doc and these
disagree, the doc is wrong:

- `Working.md`, `decisions/DECISIONS.md` rows dated 2026-09-14 to 2026-09-16.
- `handoffs/2026-09-15-queue-live-deploy.md`,
  `handoffs/2026-09-15-vm106-rebuild.md`,
  `handoffs/2026-09-15-incident-capture.md`,
  `handoffs/2026-09-15-overseer-first-ruling.md` (Result **and** orchestrator
  review sections in each).
- `evals/live/2026-09-15-architect-third-charter/`,
  `evals/live/2026-09-15-overseer-first-ruling/`.
- `research/2026-09-15-openclaw-secret-storage.md`.

Facts worth stating plainly wherever they belong, because they are easy to
get wrong:
- The live fort is **paused** at tick 12274877 under the user's standing
  rule, so no prediction can come due and nothing executes until it runs.
- The first ruling is **one sample on a cheap model**: charter-clean, but it
  judged an unattributable prediction sound. Not evidence of good arbitration.
- openclaw-side tool scoping is defence in depth; the dfmcp token-to-role map
  is the boundary (`docs/AGENT-ARCHITECTURE.md` principle 8).

## What to do

1. **Audit, then fix.** Walk `CLAUDE.md`, `ROADMAP.md`, `docs/*.md`,
   `dfmcp/README.md`, `dfqueue/README.md`, `agents/**` (including
   `ROSTER.yaml`, each `role.md`, `tools.yaml`, `model.yaml`) and
   `scripts/README.md` if present. For each, list what is stale and fix it in
   place. Keep each file's voice and structure; no rewrites.
2. **Mark verified vs proposed** (CLAUDE.md's rule). Anything now live should
   say so with a date; anything still design should keep saying it is design.
   Do not promote something to "live" that you cannot point at evidence for.
3. **New traps** into `docs/TRAPS.md` (append only), from this week's streams:
   multi-agent openclaw configs need `agents.ownership: "explicit"` and
   `agents.defaults.systemAgent.agentId`; a pinned config's `_note` key is
   rejected by the live schema; an externally-linked openclaw plugin is lost
   when the VM is rebuilt; a `models.providers.<id>.apiKey` SecretRef resolves
   but is shadowed by an existing plaintext auth profile (`REF_SHADOWED`).
4. **Report drift you did not fix**, with the file and why, rather than
   guessing. Contradictions between two docs are a finding, not yours to
   settle by picking one.

## Hard lines

- **Docs only. No code, no tests, no config, no VM, no model call.** If a fix
  needs a code change, report it instead.
- No addresses, hostnames, tokens or key material anywhere (the repo is
  public). Cite VMIDs.
- Do not write `Working.md`, `decisions/DECISIONS.md` or `memory/`: the
  orchestrator owns those. Do not push.
- No em dashes in prose.
- Ambient `python -m pytest` must still pass (276 passed, 1 skipped) since you
  are touching no code; run it once at the end as a guard.

## Touched surfaces

`CLAUDE.md`, `ROADMAP.md`, `docs/*.md`, `dfmcp/README.md`, `dfqueue/README.md`,
`agents/**`, this doc, its `handoffs/INDEX.md` row.

## Report

Per file: what was stale, what you changed, and what you left alone and why.
Then the new traps added, and the drift you could not settle.
