# Stream: the Overseer's first ruling, as a second openclaw agent on VM 106

**Written** 2026-09-15. **Status:** dispatched. **User go-ahead:** given
2026-09-15 ("okay go for it", then, after the per-agent scoping and secret
storage discussion, "great agreed go for it"). Execution by a Sonnet executor
(user's standing preference).

## Why

`proposal-0001` (architect run #3) has sat unruled since 2026-09-15. A ruling
is the first test of the project's thesis: specialists propose, one actor
decides. Decided with the user 2026-09-15:
- **Host:** the Overseer is a second agent in the **same** openclaw instance on
  VM 106, with its own workspace. The 2026-09-14 "no overseer token on VM 106"
  line was a precaution for a DeepSeek test, not an architecture decision; it
  is lifted for this stream.
- **Scoping, both layers:** openclaw's per-agent `tools.allow` decides which
  tools each agent sees; dfmcp still maps each token to a role, because the
  queue stamps authorship from the credential and refuses `queue.propose`
  from the Overseer and `queue.rule` from the architect. So two MCP server
  entries, one per token, same URL.
- **Keys not in plaintext** where openclaw allows it; see "Secret storage".
- **Model: DeepSeek, not Opus, for now** (user's call 2026-09-15, budget).
  `agents/overseer/model.yaml` still names `anthropic/claude-opus-5` as the
  design default; this run is a recorded deviation, not a change to that file.
  No Anthropic key goes onto VM 106.

## Read first

- `agents/overseer/role.md`, `agents/overseer/tools.yaml`,
  `agents/overseer/model.yaml`.
- `evals/live/2026-09-15-architect-third-charter/README.md` and its
  `pinned-config.json` (the run mechanism: pinned config overlay, workspace
  `SOUL.md`, `agent exec`; strip `_note` before mounting).
- `handoffs/2026-09-14-openclaw-first-agent-call.md` (how a token reaches
  VM 106 by key, never the whole `.env`) and
  `handoffs/2026-09-15-vm106-rebuild.md` (VM 106 was rebuilt; no MCP token is
  on it now).
- `research/2026-09-15-openclaw-secret-storage.md`.

## Secret storage

From `research/2026-09-15-openclaw-secret-storage.md` (orchestrator checked
its schema and CLI excerpts). Honest limit: on one VM, "secret" means out of
config and state and readable only by the openclaw user and root, not
encrypted. The target is **`openclaw secrets audit` reporting zero plaintext
findings** at the end.

- **Both MCP tokens:** the existing, proven mechanism. Values in the env file
  under `/opt/openclaw/secrets/` (mode 600, owner `df`, dir 700), referenced
  as `${DF_MCP_TOKEN_ARCHITECT}` / `${DF_MCP_TOKEN_OVERSEER}` in each server's
  `headers`. `headers` accepts no SecretRef object, so this is the only way.
- **DeepSeek key, try first:** move it to that same env file (by key from
  this workstation's `.env`, over stdin) and set
  `models.providers.deepseek.apiKey` to an env SecretRef
  (`openclaw config set models.providers.deepseek.apiKey --ref-provider
  default --ref-source env --ref-id DEEPSEEK_API_KEY`, or the equivalent in the
  pinned config). **Untested**: the research could not show the plugin-provided
  deepseek provider reads this path at runtime. Prove it at $0 if openclaw
  offers a way (models status / provider resolution without a call); otherwise
  prove it with the paid run itself, which fails pre-network with
  `Unknown model` or an auth error if the ref is not honoured.
- **Only once the ref is proven,** remove the plaintext `deepseek:manual` auth
  profile key and re-run `secrets audit`: zero plaintext expected.
- **Fallback if the ref is not honoured:** `openclaw secrets store set
  DEEPSEEK_API_KEY --kind secret --value-file -` over stdin, and wire the
  provider to it with a `store` SecretRef. If neither works, leave the
  plaintext profile as it is today, say so, and still do the run.

## What to do

1. **Tokens onto VM 106**, each read by key on VM 103
   (`grep -E '^MCP_ROLE_TOKEN_ARCHITECT='`, `...OVERSEER=`) and written
   straight into VM 106's secret store as specified above. Never the
   consultant token. Never through this workstation's disk. The overseer and
   consultant tokens were rotated earlier today; use the live values.
2. **Model for the overseer:** `deepseek/deepseek-v4-pro` (the non-flash chat
   model, per the research's prior verified catalog listing). If it is not
   resolvable on this install, use `deepseek/deepseek-v4-flash` and say so.
   The same DeepSeek credential serves both agents.
3. **Config.** Two MCP server entries at the same URL: `df-architect`
   (architect token) and `df-overseer` (overseer token). Two agents:
   - `architect`: workspace as run #3, `deepseek/deepseek-v4-flash`,
     `tools.allow` = `df-architect__*` only;
   - `overseer`: its own workspace, the DeepSeek model from step 2,
     `tools.allow` = the overseer's **read** tools plus
     `df-overseer__queue__pending` and `df-overseer__queue__rule`, nothing
     else. **No fort-mutating tool is allowed in this run** (`openarea.build`,
     `diggable.dig`, `landmarks.build`, `labor.set-labor` all excluded).
4. **Probe, $0.** `openclaw mcp probe` for each server: architect 11 tools,
   overseer 16. Then confirm, without a model call if openclaw offers a way
   (a tools listing per agent), that each agent sees only its allowed tools.
   If there is no $0 way, say so.
5. **Charter.** `SOUL.md` in the overseer workspace = `agents/overseer/role.md`
   verbatim, plus an appended "Your tools this cycle" section listing exactly
   the allowed tools and stating that execution tools are withheld this cycle.
   Save it as `charter-bootstrap.md` in the output directory.
6. **The run.** One `agent exec` for the overseer agent. Prompt:
   *"Read the pending proposals with queue.pending. For each, check its
   preconditions and prediction against the live fort with your read tools,
   then rule on it with queue.rule: accept, reject or defer, with your
   reasons. Do not act on an accepted proposal this cycle; execution tools
   are withheld. Reason only in named landmarks, directions and distances."*
   **At most 2 agent turns; stop at $0.10 total.**
7. **Verify from the queue, not the model.** Read `proposal-0001`'s ruling
   row in `/var/lib/dfmcp/Uniboslan.sqlite3` on VM 103 (venv `sqlite3`
   module), the run's `tools/call` journal lines (role must be `overseer`),
   and any refused calls with their reasons. Also re-run `mcp probe` for the
   architect entry to confirm it still works after the config change.

## Output

`evals/live/2026-09-15-overseer-first-ruling/`: `README.md` (procedure, the
ruling and its reasons, a charter check against `role.md`: did it re-derive
the architect's analysis, reinterpret the proposal, act, or use a
coordinate), `run.json`, `charter-bootstrap.md`, `pinned-config.json` (URL
redacted, no `_note` needed), `queue-export/`, `tool-calls.jsonl`. **Scan
every new file for tokens, keys and addresses with a positive control**
before committing.

## Hard lines

- **No fort-mutating tool call.** No change on VM 103 at all beyond reads.
- No consultant token and no Anthropic key on VM 106. No key or token in argv, in a tracked file,
  in the report, or on this workstation's disk.
- Read secrets by key, never whole files.
- Nothing left listening on VM 106; `docker run --rm` only.
- If probes in step 4 fail, stop before the paid run and report.
- No em dashes. Do not write `Working.md`, `decisions/` or `memory/`. Do not
  push.

## Touched surfaces

VM 106 `/opt/openclaw/` (config, secrets, workspaces); VM 103 read-only;
`evals/live/2026-09-15-overseer-first-ruling/` (new); this doc; its
`handoffs/INDEX.md` row.

## Report

Model id used and why. Secret storage as built (where each secret lives, what is still plaintext
and why), probe results, per-agent tool visibility, the ruling as recorded in
the queue, refusals, cost, and the charter check.
