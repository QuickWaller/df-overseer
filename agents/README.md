# `agents/`

The roster. One directory per role, one file you edit to change who is on it.

**Status 2026-09-12: this describes a roster, it does not yet drive one.** The
MCP server these allowlists reference does not exist, so nothing here is
running. Said plainly so a fresh session does not assume otherwise.

## The contract

| File | Job |
|---|---|
| `ROSTER.yaml` | **The only file you edit to add, remove or swap a role.** Flip `enabled`. |
| `<role>/role.md` | The charter: owns, does NOT own, refusals, escalation, traps specific to that seat. |
| `<role>/tools.yaml` | The allowlist, by id, referencing `scripts/dfhack/TOOLS.yaml`. **This, not the charter, is the enforced boundary.** |
| `<role>/model.yaml` | Model, fallback, cadence, budget ceiling, and which eval suite should be choosing the model. |

Design rationale for all of it: [`docs/AGENT-ARCHITECTURE.md`](../docs/AGENT-ARCHITECTURE.md),
§3 (roster), §11 (modularity). Decisions: `decisions/DECISIONS.md` 2026-09-12.

## Currently enabled

**Overseer, Architect, Consultant.** Three, not six, and the choice was
deliberate: these are the roles whose tools already exist, so each can do real
work rather than write proposals nothing can execute.

Quartermaster, Marshal and Chronicler have charters and directories but no
`tools.yaml` and no `model.yaml`, because writing an allowlist of tools that do
not exist would imply a capability this project does not have. Each charter
states exactly what blocks it and hands its traps to whoever builds it.

## Two rules that are easy to break

**Exactly one role may write to the fortress.** Currently the Overseer. This is
settled rather than provisional: DFHack serialises every write through one
tick-gated mutex, so additional writers buy no throughput at all, only lost
coherence in the plan and the audit trail.

**An advisor's only write is `propose`.** If an advisor wants an action tool,
that is a `vent.md` entry and a friction-log line, not a workaround. The friction
log is how missing tools become roadmap items instead of quiet failures.

## Adding a role

1. Create `agents/<role>/` with the three files above.
2. Add it to `ROSTER.yaml` with `enabled: true`.
3. Give it a read allowlist that is as narrow as the job allows. Narrow reads are
   not only a permission boundary: they keep the prompt small, which is cheaper
   and keeps the role further under the doctrine-compliance cliff.
4. Do not give it write authority. If you genuinely need to, read §7 first and
   then change `sole_writer` deliberately, knowing what it costs.

## Enabling a role costs money

There is **no hard spend cap in openclaw**: only context limits and cost
visibility. Every `budget.ceiling_usd_per_day` in this directory is enforced by
our own Triage gating and provider-side billing caps, not by the host. Treat
those numbers as obligations, not guardrails that hold on their own.
