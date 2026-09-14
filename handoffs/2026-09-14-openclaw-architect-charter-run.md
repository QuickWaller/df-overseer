# Stream: get the DeepSeek key out of plaintext, then a first architect charter run

**Written** 2026-09-14. **Status:** dispatched. **User go-ahead:** "u wanna
contnue on?", in reply to a summary that offered exactly these two steps.
Both are on VM 106 only, reversible, and the architect role cannot mutate the
fort.

## Why

`handoffs/2026-09-14-openclaw-first-agent-call.md` proved one agent turn can
read the fort, but left the DeepSeek key **plaintext** in
`/opt/openclaw/config/state/openclaw.sqlite` (`profiles.deepseek:manual.key`),
and the question it asked was a toy. `agents/architect/model.yaml` names this
seat as the place to try cheap models: read-only, zero blast radius, and
"is its advice any good" is the question. This stream fixes the secret, then
asks the architect to do its actual job once.

## Read first

1. `handoffs/2026-09-14-openclaw-first-agent-call.md`, all of it: the exact
   docker invocation, env file, and the `Unknown model` trap.
2. `agents/architect/role.md`, `tools.yaml`, `model.yaml`.
3. `docs/AGENT-ARCHITECTURE.md`, the proposal-record sections (search
   "proposal") and `learning/ledger/schema.py` for the proposal fields and
   the closed `type` vocabulary, if it defines them.
4. `docs/TRAPS.md`, the 2026-09-14 sections.

## Part A: the key out of plaintext

1. Read `openclaw secrets store --help`, `secrets configure --help`, and
   whatever the `config schema` says about auth profile keys accepting a
   secret reference (search the schema for `SecretRef`, `source`, `env`,
   `keyRef` or similar near `auth`/`profiles`). **Quote what you find.**
2. If an auth profile can point at an env var or a store entry instead of a
   literal, switch the `deepseek` profile to that, remove the plaintext
   `deepseek:manual` profile (`models auth logout --provider deepseek` or the
   real equivalent), and prove it: `secrets audit --json` shows
   `plaintextCount: 0`, **and** a byte search of every file under
   `/opt/openclaw/config` for the key value finds nothing. Read the value from
   the env file into a grep pattern file in `/dev/shm`, never argv, and
   delete that file after.
3. **If no reference form works, do not force it.** Leave the working setup
   as it is, record exactly what you tried, and continue to Part B. A clean
   "openclaw 2026.9.4 can only hold this key in plaintext" is a finding.
4. Whatever the outcome, confirm the agent still resolves the model **without
   spending a turn**, if a local check exists (`models status`, a dry run).
   Otherwise the first Part B turn is the check.

## Part B: one architect charter run

1. Give the agent the architect's charter as its instructions: `role.md` in
   full, plus the proposal fields and allowed `type` values from step 3 of
   "Read first". Use openclaw's own mechanism for this (an agent entry with
   a system prompt or instructions file under `/opt/openclaw/config`, per
   the real schema). Pasting the whole charter into the prompt is the
   fallback, and if you use it, say so. Restrict that agent's tools to
   `df-overseer__*` with `agents.entries.<id>.tools.allow`, so no built-in
   shell, file or web tool is available. Confirm the restriction from config
   before running.
2. Task prompt, verbatim: *"Survey the fort with your tools. Then either make
   exactly one proposal in the required format, or say why no proposal is
   warranted this cycle. Reason only in named landmarks, directions and
   distances."*
3. Run it with `agent exec`, the same throwaway `docker run --rm` pattern,
   model `deepseek/deepseek-v4-flash`.
4. **Check the output against the charter**, mechanically where possible:
   - Did it quote any raw coordinate? Search the output for `x`/`y`/`z`
     numeric patterns and bracketed triples.
   - Does the proposal have every required field and a `type` from the
     closed vocabulary?
   - Is its prediction falsifiable?
   - Does it name a cost?
   - If it is a dig proposal, did it deal with reachability?
   - Did it call any tool outside the 9 read tools? It cannot succeed, but an
     attempt is a finding.
5. Save the run output (the `agent exec --json` result and the list of tool
   calls) to `evals/live/2026-09-14-architect-first-charter/`, **with
   addresses and any token-shaped string removed**. This project keeps run
   output for an eventual public report, so the output is a deliverable, not
   debris. Add a short `README.md` there saying what was run, with which
   model, and what the charter check found.

## Budget and hard lines

- **At most 4 model-backed turns across both parts**, failures included.
  Hitting the cap means stop and report.
- Still architect token only on VM 106. No other role token, no Anthropic
  key. Change nothing on VM 103 (reading its journal is fine).
- Secrets: read by key, never `cat` an env file, never a value in argv, config,
  a tracked file or the report.
- No gateway, no channels, no `docker compose up`, nothing left listening.
- No commits in this repo or `../openclaw`. Don't edit `Working.md`,
  `decisions/`, `memory/`, `CLAUDE.md` or other handoff docs. You may add a
  Result section here, your row in `handoffs/INDEX.md`, and the files under
  `evals/live/2026-09-14-architect-first-charter/`.
- Refusals: follow CLAUDE.md's rule, disclose any reroute, and never ask
  another session or agent to do it for you.

## Report

Executor shape, plus **"Findings to record"**:
- Part A outcome, with the audit and byte-search evidence;
- the charter-delivery mechanism used;
- the tool-restriction config;
- the tool calls the architect made;
- the proposal (or its reason for none), quoted;
- the charter check, item by item;
- turns used;
- cost;
- anything listening;
- reversal steps.

Mark each claim as verified (with its command) or inferred.

## Result, 2026-09-14

**Status: done.** Both parts complete. Full run artifacts, charter file, and
pinned config (MCP URL redacted) are in
`evals/live/2026-09-14-architect-first-charter/` (`README.md` there has the
full charter-check write-up). Used 2 of the 4 allowed model-backed turns
(1 free local failure, 1 paid success, $0.0042804664). Nothing left
listening on VM 106 (`docker ps -a` empty, `ss -tlnp` baseline-identical,
both **verified**, before and after). Ambient `openclaw.json` confirmed
byte-identical before and after (**verified** by re-reading it) — Part B's
tool/workspace restriction lived only in a pinned overlay file, never the
production config Part A's working DeepSeek setup depends on.

### Part A: the key stays plaintext, and there is no reference form to move it to

**Verified**, not inferred. `openclaw secrets --help` / `secrets store --help`
/ `secrets configure --help` quoted in full during the run.
`secrets configure` (the one command whose own `--help` text advertises
"provider setup + SecretRef mapping + preflight") **requires an interactive
TTY** — confirmed live: `secrets configure --json --plan-out ... --skip-
provider-setup` returned `{"ok": false, "error": {"message": "secrets
configure requires an interactive TTY."}}`, unusable from a headless
`docker run`. `models auth`'s non-interactive subcommands
(`paste-api-key`, `paste-token`) are documented as plaintext-persisting by
design ("Save an API key in an auth profile..."); `add`, `login`,
`setup-token` are TTY-only. Decisive evidence from `openclaw config schema`
itself: the `auth.profiles.<id>` object schema is `"additionalProperties":
false` with only `provider`, `mode`, `email`, `displayName` — **there is no
key/SecretRef field in this JSON path at all**, so no `config set --ref-
source env ...` builder (confirmed elsewhere in the same schema, e.g.
`mcp.servers.*.headers.*`, and used successfully for the architect token)
can reach it; a dry-run attempt (`config set auth.profiles.deepseek:manual.
apiKey --ref-provider default --ref-source env --ref-id DEEPSEEK_API_KEY
--dry-run`) returned `"checks": {"schema": false}`, consistent with the
field not existing. The secret material lives exclusively in
`state/openclaw.sqlite`'s runtime auth-profile store, never in
`openclaw.json`, regardless of which command created it. **Left as-is**, per
the brief's instruction not to force it: `secrets audit --json` baseline
re-confirmed the same single finding as the prior stream,
`plaintextCount: 1`, `profiles.deepseek:manual.key` — unchanged, not worsened,
not fixed. Step 4's local, $0 check: `models status --json` shows
`defaultModel`/`resolvedDefault` both `deepseek/deepseek-v4-flash` and the
provider `"effective": {"kind": "profiles"}` with the stored profile intact —
resolution confirmed working without spending a turn.

**One correction worth recording for future streams**: this container's
config home is `/home/node/.openclaw` (user `node`, `HOME=/home/node`), not
`/root/.config/openclaw`. Mounting the latter (this run's own first attempt)
does not error — it silently gives `openclaw` a fresh, nearly-empty config,
and `secrets audit` reporting `"status": "clean"` with only one scanned file
was the tell. **Verified**: `docker run --rm --entrypoint sh ... -c "whoami;
echo HOME=\$HOME"` → `node` / `/home/node`.

### Part B: charter delivery, tool restriction, and the run

**Charter-delivery mechanism: a workspace bootstrap file, not a prompt-paste
fallback.** `agent exec --help` has no `--instructions`/`--system-prompt`
flag; the config schema's own field descriptions ("Default agent workspace
for bootstrap and memory files... injected into this agent's system prompt")
and `skipOptionalBootstrapFiles`'s documented valid values (`SOUL.md`,
`USER.md`, `IDENTITY.md`) name the real mechanism. Delivered as `SOUL.md`
(role.md's charter plus the proposal-record format and field notes, verbatim
content in `evals/live/.../charter-bootstrap.md`) in a workspace directory
referenced by `agents.entries.main.workspace` in a **pinned config**
(`--config`-equivalent, via a read-only Docker volume overlay onto
`openclaw.json` inside the container, never touching the ambient file on
disk). **Verified**: `config get agents.entries.main --json` against the
pinned overlay returned exactly the configured `workspace` and `tools.allow`
before any run.

**Tool restriction**: `agents.entries.main.tools.allow: ["df-overseer__*"]`,
in the same pinned config. **Verified from config before running**, per the
brief: `config validate --json` against the overlay returned `"valid":
true` with no schema errors, and `config get agents.entries.main --json`
echoed the restriction back exactly. Note: `agents.defaults.tools` does
**not** exist in the schema (a first attempt using it failed `config
validate` with `"Unrecognized key: \"tools\""`, caught before spending any
turn) — `tools.allow` is an `agents.entries.<id>`-only field, matching the
brief's own naming.

**The tool calls.** From `run.json`'s `toolSummary`: **26 calls across
exactly the 9 allowed tools** — `overview.get`, `landmarks.list`,
`connectivity.report`, `stuckjobs.find`, `diggable.find`, `openarea.find`,
`chokepoints.find`, `connectivity.check`, `landmarks.get` — **0 failures**,
no attempt at anything outside the set. **Cross-checked** against VM 103's
`dfmcp-server.service` journal (read-only): a matching burst of `POST`/`GET`/
`DELETE /mcp`, all `200`/`202`, from VM 106's address, ending in a clean
session-closing `DELETE`, in the same time window.

**The proposal**, quoted in full in `run.json` and
`evals/live/.../README.md`: one `workshop_siting` proposal siting the next
workshop on open ground 5 tiles south of the Embark Site, reasoned entirely
in named landmarks and tile distances, with a falsifiable prediction
(`landmarks.new_workshop.exit_to_Wagon.distance_tiles lte 7`), a named cost
(`350 dwarf_ticks`), and a `public_rationale`. It also explicitly **declined
to propose a blind dig** after `diggable.find` returned zero candidates
across five z-levels and three origin landmarks — the reachability
discipline the charter asks for, applied even though this wasn't a dig
proposal.

**Charter check, item by item** (full detail in
`evals/live/.../README.md`): no raw coordinates (**verified** by grep, zero
matches for `x=`/`y=`/bracketed-triple patterns); all required proposal
fields present; `type` (`workshop_siting`) is one of only two `type` values
this repo's docs name anywhere — **finding**: no full closed vocabulary is
actually enumerated in this repo (`docs/AGENT-ARCHITECTURE.md` says "closed
vocabulary, see below" but never lists one beyond two illustrative
examples), so the charter told the model this directly and to prefer an
existing category, which it did; prediction is falsifiable in form but its
`signal` dotted-path was **not verified** against `learning/ledger`'s actual
field registry (inferred plausible, not checked this run); cost is named;
reachability discipline was honored in spirit (N/A as a dig proposal, but
the model refused to invent one); no tool called outside the 9 reads
(verified both client- and server-side, above).

**Turns and cost**: 2 of 4. Attempt 1 failed **locally, $0**
(`Unknown model: deepseek/deepseek-v4-flash`, ~130ms, no
`provider-transport-fetch` log line) — root cause: the
`@openclaw/deepseek-provider` plugin's registration had not survived into
the model catalog for this fresh container, even though its npm package was
still on disk (`plugins list --json` did not include it at all; `plugins
registry --refresh --json` showed its install record intact but the "not
installed" config warning persisted). Fixed with `openclaw plugins install
@openclaw/deepseek-provider --force --acknowledge-install-policy-warning`
against the **ambient** config (re-links the cached npm package; no new
secret, no ambient-config content change beyond the plugin's own registry
bookkeeping — **verified** by re-reading `openclaw.json` after, identical to
before). Attempt 2 **succeeded**: `costUsd: 0.0042804664`
(11003 input / 9055 output / 73088 cache-read / 5361 reasoning tokens, 8
assistant turns, `provider-transport-fetch` logs show 4 real `200` round
trips to `api.deepseek.com/chat/completions`).

**Reversal steps** (not executed, matching the prior stream's precedent of
leaving state for continuity — the user's go-ahead covered placing/using
these, and Part A found no safer state to move to):
```
# On VM 106, undoes this stream's one durable change (the plugin re-link) and
# everything placed by the prior stream that this one also relied on:
sudo rm -rf /opt/openclaw
docker rmi ghcr.io/openclaw/openclaw:latest   # optional, frees ~4.58GB
```
This stream's own scratch files (`/opt/openclaw/architect-run/`, a
`/tmp/schema.json` config-schema dump, a `/tmp/plugins2.json` listing) were
already deleted before finishing — **verified**: `ls /opt/openclaw/` now
shows only `auth`, `config`, `secrets`, `workspace` (the same four the prior
stream left), and `docker ps -a` / `ss -tlnp` match the pre-run baseline
exactly.

### What was not done, deliberately

- No `openclaw gateway` process was started.
- Part A was not forced past its TTY/schema wall — no attempt to script an
  interactive `secrets configure` session (e.g. via `expect`), which would
  have been forcing a "no" past what the brief allowed.
- No third attempt at `agent exec` once the second succeeded — 2 of 4 used,
  2 left unspent rather than spent on a second demonstration.
- VM 103 was only ever read from (`journalctl`, read-only); no config,
  service, or game state on it was touched.
