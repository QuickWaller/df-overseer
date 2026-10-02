# n8n conventions for df-overseer

Date: 2026-09-25. Researcher, read-only. Answers
`handoffs/2026-09-25-n8n-conventions.md`. Builds on
`research/2026-09-25-n8n-fit.md` and
`research/2026-09-25-n8n-testing-vc-nodes.md`.

Labels: **[documented]** = read on docs.n8n.io on 2026-09-25 (the `.md`
versions of the pages, current and unversioned); **[carried]** = taken from the
earlier two research files, which in turn carry a finding from another project
tested on n8n 2.40.5, not re-tested here; **[opinion]** = my recommendation,
no source. No n8n instance was installed or run, and I did not read n8n source
at a tag, so nothing here is confirmed against an installed binary.

## Bottom line

Use a small closed vocabulary, keep almost everything that matters in the
**workflow name and the git path**, and use tags only for the four dimensions
you would actually filter on. Do not put environment, lifecycle or trigger
kind in tags. Treat n8n's execution history as short-lived debugging data and
write your own audit line per run to a store you control: n8n's way of
attaching searchable metadata to executions is not available on an
unregistered Community install.

## Recommended convention set (accept or edit)

| # | Question | Recommended default | Basis |
|---|---|---|---|
| 1 | Workflow name | `<component>.<verb>-<noun>`, lowercase, dot then kebab, e.g. `wikimirror.refresh-pages`, `wikimirror.seed-index`, `consultant.wiki-search` | opinion (mirrors dfmcp tool ids such as `zone.place`) |
| 2 | Sub-workflow used as a tool | `tool.<dfmcp-tool-id>` when it fronts an existing dfmcp tool, `tool.<component>.<verb>-<noun>` otherwise; shared helpers `util.<verb>-<noun>`; error handler `util.error-handler` | opinion |
| 3 | Node names | Verb-noun in sentence case, unique within a workflow, never left as the default ("HTTP Request1"); branch nodes name the states (`Switch: met / not_met / cannot_tell`) | opinion |
| 4 | Credential names | `<service>-<role-or-purpose>-<env>`, no secret or host in the name, e.g. `dfmcp-consultant-live` | documented that names travel in exported JSON and can be sensitive; the scheme is opinion |
| 5 | Tags (4 dimensions only) | `c:<component>` (`c:wikimirror`), `role:<role>` (`role:consultant`), `rw:read` or `rw:write`, `k:job` / `k:tool` / `k:util` / `k:error` | opinion, constraints documented |
| 6 | What is NOT a tag | Environment (separate instances), lifecycle (n8n's published state), trigger kind (visible from node 1), person/owner | opinion |
| 7 | Tag creation | A committed vocabulary file lists every allowed tag; create the tags once before any workflow import; import workflows one at a time | documented (tags global, names unique) plus carried (batch-import tag race) |
| 8 | Folders/projects | Instance folders mirroring the repo path (`wikimirror/`, `tools/`, `util/`); do not depend on Projects | folders travel in packages (documented); Projects need a registered Community license (documented); the split is opinion |
| 9 | One workflow per tool vs shared | One workflow per tool, entered through an `Execute Sub-workflow Trigger` with a declared input schema, attached to the per-role MCP trigger via `Call n8n Workflow Tool`. Shared logic only as `util.*` sub-workflows | node behaviour and publish requirement documented, rest opinion |
| 10 | Control flow | Branching and loops as Switch/If/Loop nodes; Code nodes only for pure data reshaping, a few commented lines; one pretty-printed JSON file per workflow | user rule, opinion |
| 11 | Error handling | One instance-wide `util.error-handler` (Error Trigger first) set as the error workflow on every workflow; it writes the same audit line with `status=error` | mechanics documented, scope opinion |
| 12 | Attribution | Every workflow's last node (and the error handler) writes one JSON audit line: `ts, workflow, role, component, sender, recipient, type, rationale, correlation_id, n8n_execution_id, status`. `role` comes from which MCP trigger/credential was used, never from a caller-supplied field; `correlation_id`, `sender`, `type`, `rationale` are required tool inputs | opinion, fits the repo's observability requirement |
| 13 | Execution retention | Pruning on; `EXECUTIONS_DATA_MAX_AGE=168`, `EXECUTIONS_DATA_PRUNE_MAX_COUNT=5000`, save errors and successes on live, `EXECUTIONS_DATA_SAVE_MANUAL_EXECUTIONS=false` on live and true on dev | defaults documented (336 h, 10000); chosen values opinion |
| 14 | Environments | Two instances (dev, live), same repo files, nothing per-environment in the JSON; secrets typed into each instance by hand; credentials resolved on import by name and type | documented (import matching modes, secrets never exported) |
| 15 | Public-repo hygiene | Committed JSON holds credential IDs and names only; names are role/purpose, never host or address; webhook paths random, not descriptive; scan each file for pasted headers and hosts before commit | documented that IDs and names travel; rest opinion |

## Reasoning per question

### 1. Tagging

Facts **[documented, Tag workflows and How import works]**: tags are global to
the instance; editing or deleting one affects everyone; only instance owners
can delete; names are unique across the instance; on package import tags are
matched by source ID, never by name, with two conflict kinds (rename drift,
name collision) and a `--tag-conflict-policy=rename` mode. Tags are written
before folders and workflows. I found no documented tag count or length limit
and tested none.

I found no primary source documenting how experienced teams tag n8n at scale
(see gaps). What follows is opinion informed by adjacent fields (Airflow tags,
CI labels, IaC resource tags): tags are for **cross-cutting filters you will
actually query**, while identity goes in the name and path. So:

- `c:` component is the filter you want when something misbehaves.
- `role:` mirrors the repo principle that the role's allowlist is the real
  boundary. The real allowlist is which tool workflows hang off which trigger,
  so the tag is a label that can drift; check it in review.
- `rw:read` / `rw:write` is worth tagging because the fit research made
  "read-only, notify, ingest" the hard line. A review or CI check can grep for
  any `rw:write`. Opinion: none should exist until the user decides otherwise.
- `k:` kind separates jobs (scheduled), tools (called) and utilities.

Prefix tags so the flat global namespace cannot collide later and a vocabulary
check is a regex. Not tags: environment (two instances, so always known),
lifecycle (n8n has published state and history), trigger kind. Fewer
dimensions also means fewer chances to hit the collision bug.

**Surviving export to git [documented]:** tags travel in packages and in
workflow JSON as name and ID pairs. **[carried]:** a batch import introducing
a new shared tag crashed on n8n 2.40.5 via the server CLI. Avoidance, cheapest
first: create the whole vocabulary before any import; import one file at a
time; or use the newer package import (from n8n 2.27.0, marked Preview) with
`--tag-conflict-policy=rename`, which the docs say checks everything before
writing. Whether the crash is fixed on the version you install was not tested.

### 2. Naming

Dotted `component.verb-noun` mirrors dfmcp tool ids, so an audit line's
`workflow` field reads like an MCP call in the journal. The `tool.` prefix
sorts tool sub-workflows together and tells a reviewer they are called, not
scheduled. Airflow `dag_id`s, Terraform module names and CI job names converge
on a stable lowercase machine identifier with no owner or version in the name
and the description elsewhere (general knowledge, not fetched **[opinion]**).

Two documented mechanics make names matter: the Error Trigger payload gives
the workflow `id` and `name`, so the name is what shows in alerts; and the tool
description on `Call n8n Workflow Tool` is what an agent reads to decide when
to call it **[documented]**. Renaming a tool workflow later changes what a
model sees, which is the reason to settle names first.

Credential names: exported JSON carries credential names and IDs, and the
docs warn names "could be sensitive" **[documented]**.

### 3. Layout and reuse

- **One workflow per tool.** The earlier research chose one MCP Server Trigger
  per role, with the allowlist visible as which tool nodes attach to it
  **[carried]**. One file per tool keeps diffs and reviews per tool.
- **Sub-workflow entry** via `Execute Sub-workflow Trigger` with a defined
  input schema; the caller refreshes inputs from it **[documented]**. A
  sub-workflow called through `Call n8n Workflow Tool` must be **published**,
  otherwise the call fails at runtime with "Workflow is not active and cannot
  be executed" and the error text is returned to the agent as the tool result
  **[documented]**. Put that in the deploy checklist.
- **Caller policy:** `N8N_WORKFLOW_CALLER_POLICY_DEFAULT_OPTION` (default
  `workflowsFromSameOwner`) can restrict who may call a workflow, but the docs
  say it needs workflow sharing **[documented]**; availability on the planned
  license was not checked.
- **Folders** mirror the repo layout. Package import rewrites sub-workflow IDs,
  credential IDs and the error-workflow setting through an old-to-new ID map,
  but only where a node selects its target from a list, not by expression
  **[documented]**. So never pick a sub-workflow by expression.
- **Projects** are RBAC and need a registered Community license or above
  **[documented]**; skip them.
- **Reviewable in git:** pretty-printed JSON, stable ordering, strip
  instance-local keys before diffing, never strip node-level `id` **[carried]**.
  Keep Code nodes tiny and commented so control flow stays visible in nodes
  **[opinion]**.
- **The built-in source control feature is Business/Enterprise only
  [documented]**, so it is not an option. Git is a repo plus a CLI: the server
  `import:workflow` route the earlier research assumed, or the newer
  `n8n-cli package` commands. **Change from the earlier research:** the docs
  now say n8n recommends the n8n CLI for new work and plans to deprecate the
  server CLI export/import commands (no date). Packages are Preview, API/CLI
  only. Whether to adopt Preview packages is a user call.

### 4. Audit and observability

Domain-neutral restatement: an event log where each event has a principal, a
subject, a type, a reason and a trace id, joinable to lower-level records
(distributed tracing, CI run metadata, DB audit tables). Settled practice
there: the application writes the structured record itself to storage it
owns, keyed by a trace id, and treats platform run history as an ephemeral
debugging aid. Applied **[opinion]**:

- **Native n8n [documented]:** execution ID and URL in the Error Trigger
  payload; custom execution metadata via the Execution Data node or
  `$execution.customData` (key max 50 chars, value max 512), **but only on
  Cloud Pro/Enterprise, self-hosted Enterprise or registered Community**;
  log streaming is **Enterprise only**. An OpenTelemetry tracing page exists
  in the docs sitemap; I did not read it.
- So on an unregistered Community install, attribution must not depend on
  execution metadata or log streaming. Write the audit line yourself (row 12)
  to a store the repo already validates (a `dfqueue`-style SQLite or JSONL),
  including the n8n execution ID so a human can jump to the run while it still
  exists. Registering the free Community license would unlock searchable
  execution metadata; that is a user decision, not assumed.
- **Role identity:** the fit research requires role from a credential, not a
  claim **[carried]**. In n8n: one MCP Server Trigger per role with its own
  bearer credential, and the audit line taking `role` from the trigger, never
  from an input.
- Sender, recipient, type and one-line rationale are unknown to n8n. Make
  them required inputs on every tool workflow so a call fails validation
  without them, and log them verbatim. Scheduled jobs use `sender=n8n`,
  `type=job`.

**Retention [documented defaults]:** pruning on, 336 h max age, 10000 max
count, hard-delete buffer 1 h, save on error and success `all`, save manual
`true`, save progress `false`; per-workflow overrides exist in workflow
settings. Row 13 values are opinion: seven days is enough to debug a failed
refresh and the durable record is the audit line. Wiki refresh runs may hold
large page payloads in execution data; consider not saving success runs for
that workflow only, and check `N8N_EXECUTION_DATA_STORAGE_MODE` (`database`
default) if the database grows (sizing untested).

### 5. Environments and secrets

- No source-control environments on Community **[documented]**, so dev and
  live are two instances fed from the same repo files.
- Credential secrets never travel in exports or packages; the file holds only
  ID, name and type **[documented]**. Package import resolves credentials by
  explicit binding, else `--credential-matching-mode` (`id-only`,
  `name-and-type`, `type-only`), else an empty stub credential that blocks
  publishing until filled **[documented]**. A same-named credential per
  instance plus `name-and-type` matching is the smallest setup. Whether the
  server-CLI JSON import can match by name is unknown to me; by ID it does not
  survive across instances, which favours packages.
- **Public repo:** JSON carries credential IDs and names, webhook paths and
  node parameters. Review each committed file for hostnames, addresses, tokens
  and pasted headers (HTTP Request nodes imported from cURL can carry auth
  headers **[documented]**). Reference the DFHack/MCP host through a
  credential field, not a node parameter. Variables need a license that
  supports them **[documented]**, so do not assume them.

## Adjacent fields consulted

Airflow/Prefect DAG naming, CI job naming, IaC module conventions and
structured-audit-log practice were used from general knowledge, not fetched or
cited in this pass. They support the direction but are not evidence about n8n.

## Could not verify

- **Tag limits:** no documented count or length limit found; nothing tested.
- **Whether the batch-import tag crash still occurs** on the version you will
  install, and whether package import avoids it. The crash is a carried
  finding on 2.40.5 only.
- **n8n packages in practice:** docs read only (Preview, from 2.27.0). Whether
  it works on an unlicensed Community install, and whether its round trip is
  stable enough for clean git diffs, is untested.
- **Folder rules:** nesting limits and availability on unregistered Community.
  The folders docs page was not found.
- **Licensing gates** for caller policy, variables and folders on the planned
  install. The custom execution data and log streaming gates are documented
  and stated above.
- **OpenTelemetry tracing:** page not read.
- **`$execution.id` inside an MCP-called sub-workflow**, and whether the MCP
  Server Trigger exposes any caller identity to the workflow: not checked. If
  it does not, role must come from the per-role trigger design as recommended.
- **Practice survey:** no mature-team write-up on tag taxonomy at scale was
  found in the primary docs. The tagging rows rest on documented constraints
  and adjacent-field reasoning, not observed n8n practice.
- **The other project's conventions** were deliberately not read, per the
  brief; only what the two earlier research files already carry is used.
