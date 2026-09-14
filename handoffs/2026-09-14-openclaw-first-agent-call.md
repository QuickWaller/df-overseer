# Stream: first real openclaw agent turn calls the fort (DeepSeek)

**Written** 2026-09-14. **Status:** dispatched. **User go-ahead:** "give it
deepseek tokens for testing", given directly after being told this is the
first step that costs money.

## Why

`handoffs/2026-09-14-openclaw-install.md` confirmed openclaw 2026.9.4's real
config schema on VM 106 and left a `df-overseer` MCP entry in
`/opt/openclaw/config/openclaw.json` with an unresolved
`${DF_MCP_TOKEN_PLACEHOLDER}` header. Nothing has yet made a model call. This
stream closes the loop: **one agent turn, DeepSeek model, that calls one
read-only df-overseer tool against the live fort and gets real JSON back.**

## Read first

1. `handoffs/2026-09-14-openclaw-install.md`, all of it, **including the
   Orchestrator correction at the end** (the executor's scaffold claims were
   wrong; the schema claims held).
2. `research/2026-09-12-openclaw-mcp-auth.md` (tool naming
   `<safeServerName>__<toolName>`, `isError` handling, still unverified live).
3. `dfmcp/README.md` (roles, what the architect role may list and call).

## What to do

1. **Look before placing secrets.** Read `openclaw secrets --help`,
   `secrets store --help`, `secrets audit --help` and `models auth --help`.
   Decide between openclaw's own secret store and a mode-600 env file passed
   with `docker run --env-file`, whichever keeps both values **off disk in
   `openclaw.json` and off every command line**. Say which you picked and why.
2. **Move two secrets to VM 106 without ever printing them:**
   `DEEPSEEK_API_KEY` from this workstation's `.env`, and the **architect**
   role token. The live server's copy of the architect token is
   `MCP_ROLE_TOKEN_ARCHITECT` in `/opt/df/dfmcp-smoke/.env` on VM 103;
   check whether the workstation `.env` has a non-empty value first
   (`grep -c '^MCP_ROLE_TOKEN_ARCHITECT=.\+' .env`) and whether it works
   against the server. If it doesn't, copy the VM 103 value with `scp -3`
   (reading a file on VM 103 is fine, changing anything there is not).
   Transfer as files, delete every temporary copy afterwards, and prove it
   with `ls`.
3. **Point the existing `df-overseer` entry at the real token** by
   environment reference, not a literal. Run `openclaw mcp probe` and expect
   success where it previously got 401. Also run `mcp tools` or its
   equivalent and confirm only read-only tools are visible.
4. **Configure DeepSeek** as the model provider, using the cheapest chat model
   openclaw offers for it. Quote the model id you used.
5. **Run one agent turn** asking it to report something only the live fort
   can answer through a read tool, e.g. "Use the df-overseer tools to tell me
   how many named landmarks the fort has, and name two." Use a throwaway
   `docker run --rm` invocation. If `agent` needs a running gateway, start
   one bound to loopback inside the container, and stop it afterwards.
6. **Verify from both ends.** openclaw's side: the tool call name, its
   arguments and a short excerpt of the result. Server side, read-only on VM
   103: `journalctl -u dfmcp-server.service` (or `server.log`) showing the
   call arriving. Then ask the server the same thing directly and compare, so
   a model that invented an answer cannot pass.
7. Run `openclaw secrets audit` and quote its output.

## Budget and hard lines

- **At most 5 model-backed agent turns in total**, including failed ones.
  Hitting the cap means stop and report, not "one more". No loops, no
  schedules, no channels (Telegram, MS365, Cloudflare), no durable gateway,
  no `docker compose up`.
- **Only the architect role token goes on VM 106.** No overseer or consultant
  token. No Anthropic key anywhere.
- **Change nothing on VM 103.** Reading its journal and `.env` by key is fine.
- **Secrets:** read by key (`grep -E '^KEY=' file`), never `cat` an env file.
  Never echo a value, never put one in argv (a literal `-e KEY=value` is in
  `ps` and shell history; `--env-file` or `-e KEY` with the value inherited
  is fine), never write one into `openclaw.json`, never quote one in the
  report. Key names only.
- Public repo: no address, hostname or token in any tracked file or in the
  report.
- No commits in this repo or `../openclaw`. Don't edit `Working.md`,
  `decisions/`, `memory/`, `CLAUDE.md` or other handoff docs. You may add a
  Result section here and your row in `handoffs/INDEX.md`.
- A refusal from the harness: follow `CLAUDE.md`'s rule. A safe reroute on
  this authorised work on our own VMs is fine if disclosed. Never ask another
  session or agent to do it.

## Report

Executor shape, plus **"Findings to record"**:
- where each secret now lives on VM 106, its file mode, and how openclaw
  reads it;
- the `mcp probe` and tool-list results;
- the model id;
- the agent turn: tool called, arguments, result excerpt, and the final
  answer compared against the server's direct answer;
- the server-side log line, with any address redacted;
- the number of model turns used;
- token usage and cost if openclaw reports them;
- the `secrets audit` output;
- anything now listening on VM 106;
- exact reversal steps, including deleting the DeepSeek key from VM 106.

Mark each claim as verified (with its command) or inferred.

## Result, 2026-09-14

**Status: done.** One real DeepSeek-backed agent turn called `df-overseer`'s
architect-role MCP tools live against VM 103 and got real fort JSON back,
compared directly against the server. Used exactly 5 of 5 allowed agent-turn
attempts (4 failed locally before any network call, $0 each; the 5th reached
DeepSeek's API for real and succeeded). No commits anywhere. Nothing left
listening on VM 106 beyond baseline (sshd, DNS stub, containerd loopback);
`docker ps -a` empty throughout — every invocation was `docker run --rm`.

**A refusal, disclosed per CLAUDE.md's rule.** Step 2's own suggested method
(`scp -3` of VM 103's whole `/opt/df/dfmcp-smoke/.env`) was refused by the
harness's auto-mode classifier, reason "Credential Leakage" — correctly so,
since that file also holds the overseer and consultant tokens, which are
barred from VM 106. Rerouted to a narrower, still-authorised method: `ssh`
VM 103 with `grep -E '^MCP_ROLE_TOKEN_ARCHITECT='` (reading one key, the
CLAUDE.md-sanctioned pattern), captured into a local shell variable, written
to a mode-600 scratchpad file, combined with the workstation's own
`DEEPSEEK_API_KEY` into one small file, `scp`'d to VM 106, then the local
copies deleted and proven absent with `ls`. This is an authorised task on our
own VMs, reversible, and not routed through another session or agent — the
line CLAUDE.md actually draws.

### Findings to record

**1. Where each secret lives on VM 106, its mode, and how openclaw reads it.**
- Both real values (architect role token, DeepSeek key) live in exactly one
  file: `/opt/openclaw/secrets/openclaw_secrets.env`, mode `0600`, owned by
  `df`, inside `/opt/openclaw/secrets/` mode `0700`. Verified:
  `ls -la /opt/openclaw/secrets/` → `-rw------- 1 df df 120 ... openclaw_secrets.env`.
- **Architect token**: `openclaw.json`'s `mcp.servers.df-overseer.headers.Authorization`
  holds only `"Bearer ${DF_MCP_TOKEN_ARCHITECT}"` (set via
  `openclaw config set`, never a literal). Every `docker run` passes
  `--env-file /opt/openclaw/secrets/openclaw_secrets.env`, and openclaw's own
  `${VAR}` substitution resolves it at read time. `secrets audit` (below)
  confirms **zero plaintext residue** for this one — it never touches any
  file in resolved form. Verified.
- **DeepSeek key: this did not end up off-disk, and that is a real finding,
  not the original plan.** `DEEPSEEK_API_KEY` in the same env-file was
  sufficient for `openclaw models status` to show the provider as
  auth-detected (`"effective":{"kind":"env"}`), but **not** sufficient for
  `agent exec` to actually place a call — every attempt using only the
  env-file (with or without `--auth-env-only`) failed with `Unknown model`
  in ~130ms, before any network call. What actually unblocked it was
  `openclaw models auth paste-api-key --provider deepseek`, reading the key
  from the env-file via a purely local VM-106-internal pipe
  (`grep ... | docker run -i --rm ... paste-api-key`, value never in argv,
  never printed). That command **persists the key as plaintext** in
  `/opt/openclaw/config/state/openclaw.sqlite`
  (`profiles.deepseek:manual.key`) — confirmed, not inferred, by
  `secrets audit`'s own finding below. Whether this is because `agent exec`'s
  model-catalog-resolution step genuinely requires a stored auth profile to
  recognize a provider/model pair at all (plausible: the failure is a local,
  pre-network validation, not an auth failure), or some other cause, was not
  traced further inside the bundle — flagged as observed, not fully explained.

**Secret placement decision, and why.** Read `secrets --help`,
`secrets store --help`, `secrets audit --help`, `models auth --help` first.
Chose the `--env-file` + `${VAR}` route over `openclaw secrets store`
(the team-scoped SQLite store) because the prior stream had already verified
`${VAR}` substitution live end-to-end, while the SQLite store's own
config-reference syntax (how a stored secret gets named from
`mcp.servers.*.headers` or `models.auth`) is undocumented in anything this
project has verified — exploring it would have cost turns against a tight
budget for uncertain payoff. This worked completely for the architect token.
It did **not** fully work for the DeepSeek key, per the finding above:
`models auth paste-api-key` was needed on top, and that path is SQLite-backed
and plaintext by design, not `${VAR}`-substituted. Recorded honestly rather
than presented as clean.

**2. `mcp probe` and tool-list results.** `openclaw mcp probe df-overseer --json`
(with the env-file supplying the real token): **success**, 9 tools, where the
same probe with the placeholder token (prior stream) got a 401. The 9 tool
names returned —
`chokepoints__find`, `connectivity__check`, `connectivity__report`,
`diggable__find`, `landmarks__get`, `landmarks__list`, `openarea__find`,
`overview__get`, `stuckjobs__find` (each prefixed `df-overseer__` by
openclaw) — **match `agents/architect/tools.yaml`'s `read:` list exactly**,
9 for 9, confirmed by reading that file directly. No mutating tool
(`*.build`, `*.dig`, `*.set-labor`, `ui.*`, etc.) is present. Verified.

**3. Model id.** `deepseek/deepseek-v4-flash`. Two DeepSeek chat models were
on offer once the `@openclaw/deepseek-provider` plugin was installed and
`models refresh` ran: `deepseek/deepseek-v4-flash` and `deepseek/deepseek-v4-pro`
(a third, `deepseek/deepseek-v4-flash-vision-exp`, is multimodal, not a plain
chat model; a fourth, `deepseek/deepseek-flash` — no `v4` — showed up later
under a different alias with `input: "text+image"`, likely a legacy/alias
entry, not used). **"Cheapest" is inferred from naming convention (Flash vs.
Pro), not verified**: `openclaw models list` exposes no pricing field, and
nothing in the CLI's `--help` surface offers one. Not a strong claim, flagged
as such.

**4. The agent turn.** `openclaw agent exec` (the headless, gateway-free,
one-shot embedded-agent primitive — exactly what the budget's "throwaway"
requirement wants), prompt: *"Use the df-overseer tools to tell me how many
named landmarks the fort has, and name two of them."*
- **Tool called**: `df-overseer__landmarks__list`, arguments `{}` (the tool
  takes none). Exactly 1 call, 0 failures (`toolSummary`).
- **Result excerpt** (from the tool's own JSON, matches the direct call
  below): 4 landmarks — Embark Site (kind `seed`), Stockpile #1, Stockpile
  #2, Wagon — each with 3 exits, all `walkable: true`.
- **Final answer**: *"The fort has 4 named landmarks: 1. Embark Site (kind:
  seed)... 2. Stockpile #1... The other two are Stockpile #2 and Wagon."*
- **Compared against the server directly**, called with the exact same
  token, bypassing openclaw entirely: a raw MCP `initialize` +
  `tools/call` (`name: "landmarks__list"`, the server's own unprefixed id)
  over `curl`, from VM 106. Result: the identical 4 landmarks, same exits,
  same distances. **Match — the model did not invent an answer.**
- **Cost/usage** (from `agent exec --json`'s own `usage` block): input
  22224, output 200, cache-read 20864, reasoning 57, total 43288 tokens;
  `costUsd: 0.0032257792`. Two real HTTPS round trips to
  `api.deepseek.com/chat/completions` (`provider-transport-fetch` log lines,
  status 200 both times) — one before the tool call, one after, matching
  `assistantTurns: 2`.

**5. The server-side log line** (VM 103, `journalctl -u dfmcp-server.service`,
read-only, address redacted): a `POST /mcp` / `POST /mcp` (202) / `GET /mcp`
/ `POST /mcp` / `DELETE /mcp` sequence from VM 106's LAN address at the time
of the openclaw run, all `200`/`202`. A second, separate `POST`/`POST`/`POST`
sequence about a minute later is this stream's own direct-comparison curl
calls, also all `200`.

**6. Number of model turns used: 5 of 5 (the cap, reached exactly, then
stopped).** In order: (1) `--model deepseek/deepseek-flash` — `Unknown
model`, ~130ms, no network call, $0. (2) `--model deepseek/deepseek-v4-flash`
— same failure, before `models set`/`models refresh`. (3) same model, after
`models set` — same failure. (4) same model, after a global `models
refresh` (1027 models/44 providers) — same failure, still before the auth
profile existed. (5) same model, after `models auth paste-api-key` — **the
one that worked**, real network calls, real cost. Attempts 1-4 never reached
DeepSeek (no `provider-transport-fetch` log line for any of them), so total
real spend across the stream is the one figure in finding 4 above,
$0.0032257792. Stopped at the cap as instructed rather than using any
further validation turns.

**7. `secrets audit` output** (`openclaw secrets audit --json`, with the
real env-file loaded):
```
{
  "version": 1,
  "status": "findings",
  "resolution": {"refsChecked": 0, "skippedExecRefs": 0, "resolvabilityComplete": true},
  "filesScanned": [
    ".../agents/main/agent/openclaw-agent.sqlite",
    ".../openclaw.json",
    ".../state/openclaw.sqlite"
  ],
  "summary": {"plaintextCount": 1, "unresolvedRefCount": 0, "shadowedRefCount": 0, "storeResidueCount": 0, "legacyResidueCount": 0},
  "findings": [{
    "code": "PLAINTEXT_FOUND", "severity": "warn",
    "file": ".../state/openclaw.sqlite",
    "jsonPath": "profiles.deepseek:manual.key",
    "message": "Auth profile API key is stored as plaintext.",
    "provider": "deepseek", "profileId": "deepseek:manual"
  }]
}
```
Paths shortened here (no host address in either, safe to quote verbatim
otherwise). One finding, exactly matching finding 1's DeepSeek-key caveat
above; nothing for the architect token. Verified — this is the tool's own
report, not a summary of it.

**8. Anything now listening on VM 106.** Nothing beyond baseline. Verified
both before and after this stream's work: `docker ps -a` empty throughout
(every invocation used `--rm`, none used `-d`); `ss -tlnp` shows only `:22`
sshd, the loopback DNS stub resolver, and a loopback containerd socket —
identical to the prior stream's own baseline. No new `home-lab`
`inventory/services.yaml` obligation.

**9. Exact reversal steps, not executed** (the user's go-ahead covered
placing these secrets; left in place deliberately, matching the prior
stream's own precedent of leaving state for continuity):
```
# On VM 106 (removes both the architect token env-file copy AND the
# plaintext-persisted DeepSeek key together — the state sqlite lives under
# the same tree):
sudo rm -rf /opt/openclaw
docker rmi ghcr.io/openclaw/openclaw:latest   # frees ~4.58GB, optional
```
A narrower alternative that keeps the rest of `/opt/openclaw/config` (the
installed plugin, the MCP entry) while specifically purging just the two
secrets: `rm -f /opt/openclaw/secrets/openclaw_secrets.env` (the env-file
copy) plus `openclaw models auth logout --provider deepseek` (removes the
`deepseek:manual` profile from `state/openclaw.sqlite`) — not run, not
independently verified to fully clear the sqlite row versus leaving a
soft-deleted one; `secrets audit` after running it would confirm either way.

### What was not done, deliberately

- No `openclaw gateway` process was ever started (bound to loopback or
  otherwise); `agent exec` needed no gateway, so that contingency in the
  brief's step 5 never came up.
- No second or third model turn beyond the one demonstration, once the cap
  was in sight — 4 of the 5 were spent on diagnosing `Unknown model`, not on
  extra demonstrations.
- The SQLite `secrets store` mechanism was read about but not used (see
  finding 1's placement-decision note) — not ruled out, just not the path
  taken.
- VM 103 was only ever read from (`.env` by key, `journalctl`); no config,
  service, or game state on it was touched.
