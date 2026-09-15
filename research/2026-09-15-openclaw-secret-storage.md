# openclaw secret storage on VM 106: can the keys be non-plaintext?

**Written** 2026-09-15. Read-only research: no `config set`, no `secrets
store` writes, no `models auth`/`secrets configure`, no model call, no
gateway start, no change under `/opt/openclaw`. All commands ran as
`sudo -n docker run --rm ...` (the ambient config needed `sudo` for the
Docker socket on VM 106; plain `docker run` returned "permission denied ...
docker.sock" for this session's SSH user, a fact worth recording since no
prior handoff needed to state it) against `ghcr.io/openclaw/openclaw:latest`
(OpenClaw 2026.9.4, `3a9d69d` -- unchanged from every prior stream). The one
command that touched real state (`secrets audit`, `secrets store list`,
`models list`) used a **read-only** bind mount of `/opt/openclaw/config`.
Not one command in this session wrote to that mount, set a config value, or
placed a credential. Guest address resolved once via
`provision_vm.resolve_guest_ip`, used only to open the SSH connection,
never printed or written to any file.

**Methodology note on line numbers.** `openclaw config schema` is 55,932
lines across every command invocation in this session (deterministic in
size), but a fresh, ephemeral container's plugin-registration order is not
guaranteed stable run to run (the schema embeds one large repeated block
per installed plugin), so **a line number is only safe to cite against the
exact dump it was taken from.** Every line number below comes from one
single dump (the "single-dump" pass, its own commands shown together) and
should not be assumed to match a different `config schema` invocation,
including a prior handoff's. Where precision matters more than a citeable
line, this report also gives the JSON path (`properties.auth.properties....`),
which is stable regardless of dump ordering.

## Bottom line

**Two different real answers, and they matter for different secrets.**

1. **The DeepSeek/Anthropic-style model-provider key has a genuine,
   schema-confirmed non-plaintext path that no prior stream tried:
   `models.providers.<id>.apiKey` accepts a SecretRef object
   (`{source: "env"|"file"|"exec"|"store", provider, id}`), not just a
   literal string.** This is a different JSON path from `auth.profiles.<id>`
   (the one `models auth paste-api-key` writes to, and the one 2026-09-14's
   Part A correctly found has **no** key/SecretRef field at all). **Not
   verified behaviorally this session** (would need `config set` /
   `config validate`, barred by this task's hard lines) -- flagged as the
   single most actionable next experiment, not a confirmed fix.
2. **The two MCP role tokens (architect, overseer) already have a working
   non-plaintext path**, proven live by two prior streams and re-confirmed
   here from the schema: `mcp.servers.<name>.headers.<key>` is typed
   `string|number|boolean` only (no SecretRef object type reaches this
   field), so the real mechanism is a plain header value containing a
   `${ENV_VAR}` token, resolved from the container's environment at read
   time. **This already works with zero plaintext residue** and needs no
   change for a second (overseer) MCP entry -- just a second env-file
   variable and a second `mcp.servers` entry.
3. **`openclaw secrets store`** (the "team-scoped SQLite secret and
   environment store") is a real, separate, non-interactively scriptable
   mechanism (`secrets store set <NAME> --kind secret --value-file -`,
   stdin, never argv) that neither prior stream exercised beyond reading
   `--help`. It is currently **empty** on this install (`secrets store list
   --json` → `[]`, read-only, nothing stored by this session). Whether its
   values are encrypted at rest is **not established either way** by
   anything in the schema or CLI surface (see Q2).
4. `openclaw secrets audit --json` against the real ambient state, run
   fresh this session, reproduces **exactly** 2026-09-14's finding: one
   `PLAINTEXT_FOUND`, `profiles.deepseek:manual.key`, nothing else. The
   architect MCP token still shows zero residue.

## Q1. Can model-provider API keys be configured headlessly as a reference?

**Two distinct JSON paths exist for "the DeepSeek key," and only one of
them accepts a reference.**

**`auth.profiles.<id>`** -- what `openclaw models auth paste-api-key`
writes to -- is schema-locked to four fields, **no key field of any kind**:

```
=== auth.properties (this session's single dump) ===
"profiles": {
  "type": "object",
  "additionalProperties": {
    "type": "object",
    "properties": {
      "provider": { "type": "string" },
      "mode": { "anyOf": [{"const":"api_key"},{"const":"aws-sdk"},
                           {"const":"oauth"},{"const":"token"}] },
      "email": { "type": "string" },
      "displayName": { "type": "string" }
    },
    "required": ["provider", "mode"],
    "additionalProperties": false
  },
  "title": "Auth Profiles"
}
```
Re-confirms 2026-09-14's finding line for line, independently, in a fresh
dump this session. The actual key material for an `auth.profiles` entry
lives exclusively in `state/openclaw.sqlite`'s runtime store, written
plaintext by `paste-api-key`/`login`/etc. There is no config-path escape
hatch for this specific document.

**`models.providers.<id>.apiKey`** -- a different, previously unexplored
path -- genuinely does accept a SecretRef-shaped object:

```
"providers": {
  "additionalProperties": {
    "properties": {
      "baseUrl": { "type": "string", ... },
      "apiKey": {
        "anyOf": [
          { "type": "string" },
          { "oneOf": [
              { "properties": { "source": {"const":"env"},
                                 "provider": {"pattern":"^[a-z][a-z0-9_-]{0,63}$"},
                                 "id": {"pattern":"^[A-Z][A-Z0-9_]{0,127}$"} },
                "required": ["source","provider","id"], "additionalProperties": false },
              { "properties": { "source": {"const":"file"}, "provider": {...}, "id": {"type":"string"} },
                "required": ["source","provider","id"], "additionalProperties": false },
              { "properties": { "source": {"const":"exec"}, ... } },
              { "properties": { "source": {"const":"store"}, ... } }
          ] }
        ]
      }
    }
  }
}
```
(from `properties.models.properties.providers`, this session's dump.) So
`{"source":"env","provider":"deepseek","id":"DEEPSEEK_API_KEY"}` is a
schema-valid value for `models.providers.deepseek.apiKey`, and
`"models"."mode"`'s own description independently corroborates that this
path is real and load-bearing at runtime, not decorative: *"apiKey values
are preserved only when the provider is not SecretRef-managed in current
config/auth-profile context; SecretRef-managed providers refresh apiKey
from current source markers"* -- language that only makes sense if
SecretRef-managed provider entries are something the runtime actually
resolves and refreshes, in the same breath as `auth-profile` context.

The general CLI builder for this shape already exists and is documented in
`openclaw config --help`'s own usage examples (this session):
```
openclaw config set channels.discord.token --ref-provider default \
  --ref-source env --ref-id DISCORD_BOT_TOKEN
```
which is the generic pattern for any SecretRef-typed field -- there is no
reason to expect `models.providers.deepseek.apiKey` to be an exception,
though this was **not tested live** (would require `config set`, barred by
this task's hard lines).

**What this does not settle.** Whether OpenClaw's *runtime credential
resolution* actually consults `models.providers.deepseek.apiKey` for the
`deepseek` id contributed by the `@openclaw/deepseek-provider` **plugin**
(as opposed to a fully custom, user-declared provider entry) is not
established from schema alone. 2026-09-14's own finding that `agent exec`
needed a stored `auth.profiles.deepseek:manual` entry to resolve the model
at all (`Unknown model` before one existed) is circumstantial evidence that
plugin-contributed providers may go through `auth.profiles` in practice
even when `models.providers.<id>.apiKey` is also schema-legal. **This is
the single most valuable live experiment for a future, execution-authorized
stream**: set `models.providers.deepseek.apiKey` to an env SecretRef,
leave `auth.profiles` empty, and see whether `models status`/`agent exec`
resolves the provider without ever touching the plaintext path.

## Q2. `openclaw secrets`: store, audit, configure

All three `--help` texts, quoted from this session (`openclaw secrets --help`):
```
Commands:
  apply       Apply a previously generated secrets plan
  audit       Audit plaintext secrets, unresolved refs, and precedence drift
  configure   Interactive secrets helper (provider setup + SecretRef mapping + preflight)
  reload      Re-resolve secret references and atomically swap runtime snapshot
  store       Manage the team-scoped SQLite secret and environment store
```

**`secrets configure` requires an interactive TTY.** Re-confirmed as
already established 2026-09-14 (`{"ok": false, "error": {"message":
"secrets configure requires an interactive TTY."}}`); not re-run this
session (would need `--json --plan-out ...` execution, and this task is
read-only on that command specifically since it can write a plan). Its own
`--help` (this session) shows `--allow-exec`, `--apply`, `--plan-out
<path>`, `--yes` -- consistent with an interactive wizard that *can* be
scripted for its preflight-plan step, but not proven headless here.

**`secrets store` is a different, lower-level, genuinely non-interactive
family**, not explored by any prior stream beyond its top-line `--help`.
Full subcommand help, this session:
```
secrets store set <NAME>
  --kind <secret|env>     Entry kind (defaults from NAME)
  --value <value>         Literal value (env kind only)
  --value-file <path>     Read value from a file; use - for stdin
  --allow-host <host>     Allow substitution only for this exact host (repeatable)
  --dry-run

secrets store get <NAME>
  Read an env-kind value; secret-kind values are write-only
  --plain / --json

secrets store import
  --from <file>           Dotenv file; use - or omit for stdin
  --kind <secret|env>
  --dry-run / --yes

secrets store list
  --json / --plain
```
Two things worth flagging as real design signal: **`--value` (a literal on
the command line) is refused for `--kind secret`** -- only `--value-file`
(including `-` for stdin) is accepted for secret-kind entries, which is the
CLI itself enforcing "never in argv" for the more sensitive kind. And
**`secrets store get` structurally cannot read back a secret-kind value**
("secret-kind values are write-only") -- an access-control property
enforced by the command surface, independent of whatever is or is not true
about the underlying file.

**Is the store encrypted at rest? Not established, and the evidence leans
no for the file layer.** Nothing in the 55,932-line schema mentions
encryption, ciphers, or a keyring anywhere near `secrets`, `auth`, or
`models` (a full `grep -i encrypt` / `grep -i "sqlcipher|cipher|keyring|
decrypt"` across the whole schema, this session, turned up only Matrix
channel E2E-encryption toggles and TLS client-key passphrase fields --
unrelated). Hands-on: `secrets store list --json` against the real,
read-only-mounted state returned `[]` (store is empty on this install,
nothing was written by this session). No file under `/opt/openclaw` is
separately named for the store (`find -iname '*secret*' -o -iname
'*store*'` found only `/opt/openclaw/secrets/openclaw_secrets.env`, the
existing env-file for the architect token and DeepSeek key), so the store's
backing table most likely lives inside the same `state/openclaw.sqlite`
that already holds the plaintext DeepSeek key. Direct hands-on evidence
against that one file: `file /opt/openclaw/config/state/openclaw.sqlite`
returns a **fully parsed SQLite 3.x header** ("user version 17 ... schema
4 ... UTF-8"), which `file(1)` could not produce against a SQLCipher- or
otherwise page-encrypted database (that would read as high-entropy `data`
to a magic-byte sniffer). So **the file itself is not whole-file
encrypted**; whether individual `secret`-kind row values get encrypted
before being written into that plain file (application-level encryption
rather than file-level) is **not verified either way** -- the store is
empty, and creating an entry to test was explicitly barred by this task's
hard lines ("Do NOT actually store anything").

**Can `secrets configure` or an equivalent run non-interactively?**
`secrets configure` itself: no (TTY-gated, confirmed). Its lower-level
sibling, `secrets store set`/`store import`, is a real non-interactive
equivalent for the actual write step (`--value-file -` over stdin, or a
dotenv file), even though it skips the wizard's own provider-discovery and
preflight UX. Neither this session nor any prior one has run either
under `ssh -t` specifically; nothing in either command's `--help` suggests
a TTY requirement, unlike `configure`'s explicit one.

## Q3. Can `mcp.servers.<name>.headers` use a reference beyond `${ENV}`?

**No.** From `properties.mcp.properties.servers.additionalProperties.
properties.headers`, this session's single dump:
```
"headers": {
  "type": "object",
  "additionalProperties": { "anyOf": [
    {"type": "string"}, {"type": "number"}, {"type": "boolean"}
  ] }
}
```
No `$ref` to `#/$defs/secretRef`, no `oneOf` with an object branch --
unlike `models.providers.<id>.apiKey` or `skills.entries.<id>.apiKey`
(both of which do have that `oneOf` branch, confirmed in the same dump).
This is the same conclusion 2026-09-14 reached from a different dump;
re-confirmed here from a fresh one with the JSON path attached rather than
only a line number, so it is not dump-order-fragile. The `${VAR}`
substitution that already works for the architect token is therefore not a
schema-level SecretRef feature at all -- it is string interpolation applied
generically to string-typed config values, which happens to be enough for
a bearer header. This is unchanged and needs no new work for a second
(overseer) MCP entry: same mechanism, a second variable name.

## Q4. Per-agent tool allow syntax for two differently-named MCP servers on one URL

**Confirmed on two independent grounds: schema shape, and a live prior
run.**

Schema: `mcp.servers` is a plain named map --
`properties.mcp.properties.servers` is `{"type":"object",
"propertyNames":{"type":"string"}, "additionalProperties": {...per-server
object...}}` -- keyed by the name you give at `mcp add <name>`, with **no
uniqueness constraint on `url`** anywhere in the object schema. So
`mcp.servers.df-architect` and `mcp.servers.df-overseer` can both carry
`"url": "http://<fort>:8443/mcp"`, `"transport": "streamable-http"`, and
different `headers.Authorization` values (`${DF_MCP_TOKEN_ARCHITECT}` /
`${DF_MCP_TOKEN_OVERSEER}`) -- this is exactly the CLI's own model: `mcp
add <name> --url ... --header 'Authorization=Bearer ${VAR}'`, where `name`
is a free argument independent of `url`.

`agents.entries.<id>.tools`, from `properties.agents.properties.entries.
additionalProperties.properties.tools`, this session:
```
"allow": { "type": "array", "items": {"type": "string"} },
"alsoAllow": { "type": "array", "items": {"type": "string"} },
"deny": { "type": "array", "items": {"type": "string"} },
"byProvider": {...}, "toolsBySender": {...}, "profile": {enum minimal|coding|messaging|full}
```
The schema alone only says "array of strings" -- it does not itself declare
glob semantics for `allow` the way `mcp.servers.<name>.toolFilter` and the
`mcp add --include/--exclude` flags explicitly do ("Comma-separated MCP
tool names or `*` globs"). **The glob behaviour for `tools.allow`
specifically is confirmed live, not just inferred from a sibling field**:
`evals/live/2026-09-15-architect-third-charter/` (and the two runs before
it) configured exactly `agents.entries.main.tools.allow: ["df-overseer__*"]`
and the architect agent successfully called nine distinct tool names
(`df-overseer__landmarks__list`, `df-overseer__queue__propose`,
`df-overseer__diggable__find`, etc.) -- a literal-string match against one
four-character-longer pattern could not have admitted more than one tool
name, so the `*` suffix demonstrably matched as a glob at call time, over a
real MCP session against the live fort.

So the pattern the orchestrator described --
```
agents.entries.architect.tools.allow: ["df-architect__*"]
agents.entries.overseer.tools.allow:  ["df-overseer__queue__rule", ...]
```
-- is schema-legal (two named server entries, one URL, independent tokens)
and the glob half of it (`"df-architect__*"`) is the same mechanism already
proven live for `df-overseer__*`. The exact-name half
(`"df-overseer__queue__rule"`) is a plain string match, the simpler case,
not separately re-verified this session but not in doubt either -- it is
the same `array of string`, no special-casing anywhere in the schema
between an exact tool id and a glob.

## Q5. `openclaw secrets audit` on the current install, findings only

Run this session, fresh, against the real ambient state (`/opt/openclaw/config`
read-only bind mount), `secrets audit --json`:
```
{
  "version": 1,
  "status": "findings",
  "resolution": {"refsChecked": 0, "skippedExecRefs": 0, "resolvabilityComplete": true},
  "filesScanned": [
    "/home/node/.openclaw/openclaw.json",
    "/home/node/.openclaw/state/openclaw.sqlite"
  ],
  "summary": {"plaintextCount": 1, "unresolvedRefCount": 0, "shadowedRefCount": 0,
              "storeResidueCount": 0, "legacyResidueCount": 0},
  "findings": [
    {
      "code": "PLAINTEXT_FOUND", "severity": "warn",
      "file": "/home/node/.openclaw/state/openclaw.sqlite",
      "jsonPath": "profiles.deepseek:manual.key",
      "message": "Auth profile API key is stored as plaintext.",
      "provider": "deepseek", "profileId": "deepseek:manual"
    }
  ]
}
```
**One finding category: a plaintext provider key in the state DB
(DeepSeek).** Nothing else -- no unresolved ref, no shadowed ref, no store
residue, no legacy residue. The architect MCP token contributes zero
findings (as expected: it never resolves to a literal anywhere on disk).
This is byte-for-byte the same finding category 2026-09-14 reported,
independently re-run this session against the current ambient state --
**the DeepSeek key is still, today, the only plaintext secret on this
host.**

## Bonus: DeepSeek model catalog, no model call

**Not independently re-derived this session, and that failure is itself a
finding worth recording.** `models list --all --provider deepseek --json`
against the read-only-mounted ambient config returned `{"ok": false,
"error": {"message": "Unknown model catalog provider. Use a provider id
from the installed plugins or configured providers."}}`. Root cause,
inferred from 2026-09-14's own account: the `@openclaw/deepseek-provider`
plugin's registration into a running container's model catalog is itself a
runtime install/link step (`openclaw plugins install ... --force`), not
something a static, read-only config mount carries -- a fresh ephemeral
container that never ran that step has no `deepseek` catalog provider to
list from, even though the ambient `openclaw.json` references it. Chasing
this further would mean a plugin-install action, which is a config
mutation and outside this task's read-only scope, so it was not pursued.

**Falling back to the last live-verified catalog listing**
(`handoffs/2026-09-14-openclaw-first-agent-call.md`, real `models refresh`
+ `agent exec`, not repeated this session): two plain DeepSeek chat models
on offer, `deepseek/deepseek-v4-flash` and `deepseek/deepseek-v4-pro`
(Pro is the non-flash chat model), plus `deepseek/deepseek-v4-flash-vision-exp`
(multimodal, not a plain chat model) and a `deepseek/deepseek-flash` alias
(no `v4`, likely legacy). No pricing field exists anywhere in `models
list`'s output surface (checked in that same run), so "Pro is more
expensive than Flash" is a naming-convention inference, not a verified
cost figure, same caveat that stream already recorded.

## Recommendation

Scope per the orchestrator's update: DeepSeek key only (no Anthropic key on
VM 106 -- the Overseer runs DeepSeek too), plus two MCP role tokens
(architect, overseer).

1. **MCP tokens (architect, overseer): no change needed, already correct.**
   Keep the existing pattern -- two `mcp.servers` entries (or one server
   entry reused if the same URL and different role tokens are wanted, per
   Q4) with `headers.Authorization: "Bearer ${DF_MCP_TOKEN_ARCHITECT}"` /
   `"Bearer ${DF_MCP_TOKEN_OVERSEER}"`, both resolved from
   `/opt/openclaw/secrets/openclaw_secrets.env` (mode 600) via `--env-file`
   on every `docker run`. `secrets audit` already shows zero residue for
   this shape. Nothing to build.
2. **DeepSeek key: try the `models.providers.deepseek.apiKey` SecretRef
   path before accepting plaintext again.** This session found a real,
   schema-confirmed field that neither prior stream tried, specifically
   because they only tested `auth.profiles.<id>` (which genuinely has no
   escape hatch). The concrete next step for an execution-authorized
   stream: `openclaw config set models.providers.deepseek.apiKey --ref-provider
   default --ref-source env --ref-id DEEPSEEK_API_KEY` (or the equivalent
   `config patch`), leave `auth.profiles` untouched, then check whether
   `openclaw models status`/`agent exec` resolves the provider without
   spending a turn and whether `secrets audit` then reports zero plaintext
   findings. **If it does not resolve** (plugin-contributed providers may
   simply not consult this path -- unverified either way here), the
   fallback is `secrets store set DEEPSEEK_API_KEY --kind secret
   --value-file -` (stdin, never argv) plus wiring whatever consumes it
   through a `--ref-source store` reference, which is untested end-to-end
   by anyone yet and would need its own small experiment. Either path is
   strictly better than status quo only if it is actually confirmed live --
   until one is, `secrets audit`'s one plaintext finding is a known,
   already-disclosed, non-worsening condition, not a regression to fix
   blind.
3. **Do not reach for `secrets configure`** for either secret: it is
   TTY-gated and this project's whole install pattern is headless
   `docker run --rm`. `secrets store set`/`import` are the real
   non-interactive equivalents if the store path is pursued.
4. **Whatever path is chosen, re-run `secrets audit --json` and diff
   against this report's Q5 baseline** (one finding, `profiles.
   deepseek:manual.key`) as the pass/fail signal, exactly as 2026-09-14's
   Part A already did successfully for the architect token.

## Not verified

- Whether `models.providers.<id>.apiKey` as a SecretRef actually resolves
  at runtime for a plugin-contributed provider id (deepseek), versus only
  for a fully custom provider entry. Schema-confirmed as legal; behaviorally
  untested (barred by hard lines: no `config set`).
- Whether `secrets store`'s `secret`-kind values are encrypted at the row
  level inside the SQLite file. The file itself is plain, unencrypted
  SQLite (confirmed via `file(1)`); the store is empty on this install, so
  no row-level evidence exists either way, and creating one to test was
  explicitly barred.
- Whether `secrets configure` (or `store set`/`store import`) truly runs
  clean under `ssh -t` specifically -- not attempted this session (the
  `-t` case specifically), only a non-TTY `docker run --rm` (which is the
  install's actual real-world invocation shape, so this gap is low-value).
- The DeepSeek model catalog was not re-derived live this session (plugin
  registration issue, see Bonus); the figures given are carried over from
  2026-09-14's live run, not independently re-checked.
- `secrets.egressProxy` (a Gateway-only mechanism that keeps secret values
  as ciphertext "sentinels" even at outbound request time) is schema-real
  and looks like the strongest available secrecy model in this codebase,
  but it requires a running `gateway`, which this task's hard lines and
  this project's whole `agent exec`-only deployment pattern both rule out
  for now. Worth a name-drop for whenever the project reconsiders running
  a gateway.

## Files touched

None under `/opt/openclaw`. This report only. No config, secrets store, or
auth state was created, modified, or removed on VM 106.
