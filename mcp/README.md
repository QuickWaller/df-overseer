# `mcp/`

The permission seam, plus (as of `dfhack_client.py`) the RPC client that
actually talks to DFHack. Still not the MCP server itself and not a
transport: no MCP SDK import anywhere in this package, no HTTP, no session
handling. That is the one remaining missing half, blocked on an open
question (`research/2026-09-12-mcp-server-stack.md`), per
`docs/AGENT-ARCHITECTURE.md` §13 item 5 ("the MCP server itself does not
exist... the seam needs per-role scoping designed in from the start").

Four of the five modules answer exactly one question, mechanically and at
load time: **given a role and a tool id, is the call allowed, and why or why
not.** The fifth, `dfhack_client.py`, answers a different one: **given an
allowed call, how do you actually run it and get its output back**, without
`dfhack-run` or any subprocess in between.

## The five modules

| Module | Job |
|---|---|
| `registry.py` | Loads `scripts/dfhack/TOOLS.yaml` into an in-memory table of tools, keyed by a canonical id. Fails loudly on structural problems (a bad command signature, two commands colliding on one id). |
| `roles.py` | Loads `agents/ROSTER.yaml` plus each enabled role's `tools.yaml`, resolves both against the registry, and exposes `Roster.check(role, tool_id)`. All of the strict validation lives here, because a role's permission set is the actual security boundary (`docs/AGENT-ARCHITECTURE.md` principle 8: "a role is defined by its tool allowlist"). |
| `tools.py` | Turns a registry + roster + role into actual MCP tool definitions (`name`/`description`/`inputSchema`), and turns a validated call's arguments back into the exact DFHack argv. Transport-independent: no MCP SDK import, no notion of HTTP. |
| `auth.py` | Maps a bearer token to a role, from a gitignored `.env`-shaped file. The credential half of the trust boundary in `docs/AGENT-ARCHITECTURE.md` §13: role identity must be a credential, not a claim. |
| `dfhack_client.py` | A persistent-connection client for DFHack's RPC socket: hand-rolled handshake/framing/protobuf-subset codec, a `DFHackConnection`, and a `DFHackConnectionPool` for batching a cycle's reads into one suspend window. The only module in this package that opens a socket. |

`registry.py`, `roles.py`, `tools.py` and `auth.py` are pure functions of
files already in this repo (YAML, or a gitignored `.env`) and open no
socket, SSH connection, or DFHack RPC call -- which is what makes them
fully unit-testable with no VM. `dfhack_client.py` breaks that pattern on
purpose (something has to eventually open the socket), and stays
unit-testable a different way: every test in `mcp/tests/test_dfhack_client.py`
runs against a fake server written for that file, not a live DFHack.

## The canonical id scheme

`TOOLS.yaml` keys commands by their human-readable CLI signature, for
example `df-overseer-openarea.lua` colon `"build W H [Z] NEAR_LANDMARK
BLUEPRINT_FILE [RANK] [RADIUS_TILES]"`. That is a good label for a person
reading the manifest and a bad identifier for code: it embeds argument
names, optional-argument brackets, and punctuation that has no business
being part of an id a role's allowlist references by exact string.

**Scheme:** strip the script's `df-overseer-` prefix and `.lua` suffix to
get a short script name, take the leading verb token of the command
signature (everything up to the first whitespace or `(`, lowercased), and
join the two with a dot.

```
df-overseer-openarea.lua  ->  "build W H [Z] ..."   ->  openarea.build
df-overseer-overview.lua  ->  "get (or no args)"     ->  overview.get
df-overseer-labor.lua     ->  "unit-status [idle|..." -> labor.unit-status
df-overseer-diff.lua      ->  "since-report REPORT_ID" -> diff.since-report
```

Full table produced by the current manifest: `overview.get`, `openarea.find`,
`openarea.build`, `diggable.find`, `diggable.dig`, `labor.unit-status`,
`labor.labors`, `labor.set-labor`, `landmarks.list`, `landmarks.get`,
`landmarks.build`, `connectivity.report`, `connectivity.check`,
`connectivity.check-units`, `stuckjobs.find`, `chokepoints.find`,
`diff.since`, `diff.recent-combat`, `diff.since-report`, `ui.type`,
`ui.click`, `ui.dump`, `ui.embark-mode`, `ui.leave-embark-mode`, `ui.hover`,
`threat.scan`, `breach.check`.

**The last two were missing from this list until 2026-09-12**, when building
`tools.py` swept the manifest and found 27 ids where this paragraph claimed
25. They are the two safety detectors, added to `TOOLS.yaml` after this
README's list was written. Nothing was wrong in the code, which derives every
id from the manifest and has no hand-maintained table; only this prose had
drifted. Worth noting because it is the exact drift the id scheme was designed
to make impossible in code, reappearing in a doc that restates it by hand.

This is the scheme proposed in the task brief, adopted as written. It was
checked against the real manifest rather than assumed:

- **Stable.** The id is a pure function of the script filename and the
  command signature's first token. Renaming an argument, or adding a new
  optional trailing argument, does not change the id.
- **Unambiguous, given collision-checking.** Two different commands in one
  script could in principle share a leading verb (an overload). None do
  today, and `registry.py` treats that as a hard load-time error rather than
  a silent overwrite (see below), so the scheme cannot quietly go wrong.
  If that ever happens for real, the fix belongs in `TOOLS.yaml`'s own
  command text (make the verbs distinct), not in a hand-maintained
  exception table in this package.
- **Derivable without a hand-maintained mapping.** `registry.py` computes
  every id straight from `TOOLS.yaml`. There is no lookup table anywhere
  that a future edit to the manifest could silently drift out of sync with.
- **Readable in a denial message.** `"'consultant' cannot call
  'openarea.build': Advisors do not act. Propose it."` names the domain and
  the action in a way `build_open_area` or a raw signature string would not
  improve on.

**One known limitation, stated rather than hidden.** Taking only the
leading verb discards the rest of the signature, so `openarea.find` and
`openarea.build` are distinguishable only because they happen to start with
different words. If `TOOLS.yaml` ever grew two genuinely different
operations that both start with, say, `get`, in the same script, the
collision check would catch it at load time (this is exactly what "hard
error, not silent overwrite" is for), but the fix is a manifest change, not
something this package can paper over. No real case forced a richer scheme
today, so a richer scheme was not built.

**What was deliberately not adopted:** keeping the full signature as the id
(rejected: unreadable in a denial message, and brittle to argument-text
edits that do not change what the command does), or hashing the signature
(rejected: unreadable, and defeats the point of a human-legible boundary).

## What `registry.py` exposes

`load_registry(path=scripts/dfhack/TOOLS.yaml) -> Registry`. Raises
`RegistryError` for:

- a command signature no verb can be extracted from,
- an `effect` field that is not `read` or `mutate`,
- two commands normalising to the same canonical id (the collision check
  above).

Each `Tool` carries: `id`, `script` (the raw filename), `command` (the raw
signature string, kept verbatim for anyone who needs to reconstruct the CLI
call), `lua_function`, `effect` and the derived `mutates` bool,
`coordinate_bearing`, `live_deployed`, `args` (a light tokenisation of the
signature's trailing arguments), and `verified` plus the derived
`is_verified` bool.

**On "human description":** `TOOLS.yaml` has no dedicated `description`
field. Its `notes` field is the closest analogue, and the manifest's own
header says notes carry "the honest caveats", so `Tool.description`
returns `notes` rather than inventing a second, redundant field that could
drift out of sync with it.

**On verification status:** `Tool.verified` is the manifest's raw string,
untouched, including the literal `"unverified"` and dated strings like
`"2026-09-12 (REPORT only)"` that carry a caveat in parentheses.
`Tool.is_verified` is `False` for anything that is not more than the literal
string `"unverified"`, and `False` for anything missing entirely. That is
the deliberate conservative direction: a missing verified field is treated
as unverified, never as a clean pass, per CLAUDE.md's "mark verified vs
proposed" rule. Nothing in this package upgrades a manifest caveat into a
clean bill of health.

## What `roles.py` exposes

`load_roster(registry, agents_dir=agents/) -> Roster`, and
`Roster.check(role, tool_id) -> (allowed: bool, reason: str)`.

The reason string is meant to be shown to an agent, not a developer: it
reuses the `reason` field already written into the role's `deny` entries
where one exists (`"Advisors do not act. Propose it."`), and falls back to
a generic "not on this role's allowlist" message, phrased for advisors
versus the sole writer, when nothing more specific was written.

### Strict validation, all hard errors at load time

Every one of these raises `RoleValidationError` and has a dedicated test in
`mcp/tests/test_roles.py` proving it actually raises:

1. **An allowlist (`read` or `write`) references a tool id absent from the
   registry.** A typo must never silently grant nothing.
2. **A role other than `ROSTER.yaml`'s `sole_writer` is granted (via `read`
   or `write`) any tool the registry marks `effect: mutate`.** This is
   checked per id against the registry's own `mutates` flag, not merely by
   the presence of a `write:` section, so a mutating tool mistakenly placed
   under `read` is caught too.
3. **An id appears in both an allow list (`read` or `write`) and the `deny`
   list**, wildcard-aware: a role that denies `ui.*` and also allows
   `ui.click` conflicts even though the strings differ.
4. **`ROSTER.yaml` names an enabled role whose directory or `role.md` is
   missing.**
5. **An enabled role's `tools.yaml` or `model.yaml` is absent.**

`planned` entries (`queue: propose`, `sentry: status`, and so on) are
**not** validated against the registry. They name capabilities that do not
exist yet by design (the queue, the sentry endpoint), and checking them
against a manifest of DFHack tools that will never contain them would be a
false hard error, not a real one. They are parsed and preserved (each
carries its own `note`) so a future MCP server has the same forward-looking
list this repo's authors already wrote, but they play no part in
`Roster.check`.

### Wildcard denials

`deny` entries of the shape `df-overseer-ui: *` in the original files
translate to `ui.*`: "deny everything in this script." A deny entry that
names one specific command, like the original `df-overseer-openarea: build
*` (a wildcard over that command's *arguments*, not over other commands in
the script), translates to the exact id `openarea.build`, not to
`openarea.*`. Widening it to the script wildcard would be a real change in
scope (it would also deny `openarea.find`, which the same role's `read`
list explicitly allows, tripping validation rule 3 above for no reason the
original file intended). `Roster` matches a wildcard deny pattern by prefix
(`"ui.*"` matches any id starting with `"ui."`) and an exact pattern by
plain string equality.

## What `tools.py` exposes

`build_tool_names(registry) -> (id_to_name, name_to_id)`. Canonical ids
contain a dot (`openarea.build`); MCP/Anthropic tool names generally may not
(`^[a-zA-Z0-9_-]{1,128}$`), so every id gets a name built once, both
directions, as dictionaries: `id.replace(".", "__")` forward
(`openarea.build` -> `openarea__build`), and a **plain dict lookup, never
string surgery**, in reverse. Raises `ToolSchemaError` if a generated name
falls outside the legal pattern, or if two different ids produce the same
name -- a hard load-time error, matching `registry.py`'s own id-collision
behaviour, not a silent overwrite.

`tool_definitions(registry, roster, role) -> list[dict]`. Exactly the
`{name, description, inputSchema}` tool definitions `role` may call,
filtered through `Roster.check` rather than by re-reading a `tools.yaml`
directly. Per `docs/AGENT-ARCHITECTURE.md` §10 ("agents inherit stated
reliability rather than inventing it"), every description states, from the
manifest and nowhere else: what the command does (`Tool.description`),
whether it mutates, and its verification status -- **stated plainly, in
words, when a tool is not verified**, never upgraded into a clean bill of
health. This is the same discipline `unit-status hostile`
(`docs/TRAPS.md`) was trusted past once already.

`argv_for_call(tool, arguments) -> list[str]`. The exact DFHack argv:
script name minus `.lua`, the verb, then positional arguments in signature
order. Ground truth (`local args = {...}; local cmd = args[1]`, Lua
varargs not an `arg` table, `docs/TRAPS.md`) was confirmed against **all
12** `scripts/dfhack/df-overseer-*.lua` dispatch blocks, not assumed from
one. Raises `ArgumentError` for: an argument name not in the tool's schema,
a missing required argument, a non-numeric or boolean value for an
integer-typed argument, a string value containing a shell metacharacter, an
invalid enum choice, and the positional-optional trap below.

**Input schema types are a documented heuristic, not knowledge.**
`TOOLS.yaml` carries no argument types, only signature text. `tools.py`
keeps one explicit table of integer-valued argument names
(`_INTEGER_ARG_NAMES`), each entry confirmed by reading a real
`tonumber(...)` call in the owning script (see `mcp/tests/test_tools.py`'s
module docstring for the file:line list); everything else defaults to
`"string"`. **Stated honestly, per the task brief: this is a heuristic that
could be wrong for an argument name not yet seen**, and the module
docstring says where to correct it (add the name to the table). Two
argument tokens in the real manifest are not placeholder names at all --
`"on|off"` (`labor.set-labor`) and `"[idle|injured|military|hostile]"`
(`labor.unit-status`) are literal choices, turned into a `string` schema
property with an explicit `enum` and a name synthesised from the choices
themselves, since the manifest gives them no other name. A full sweep of
the current, real manifest found nothing else the heuristic does not
confidently cover.

**The positional-optional trap.** DFHack's CLI is positional, so if a
caller supplies a later optional argument (e.g. `RANK`) while omitting an
earlier one (e.g. `Z`), there is no way to express that without silently
shifting every later argument into the wrong slot -- the exact class of bug
this project has already shipped twice (the `quickfort -c`
top-left-vs-centre bug, `decisions/DECISIONS.md` 2026-09-11).
`argv_for_call` refuses this with a named `ArgumentError` rather than
guessing a shift. The check only concerns optional arguments relative to
each other; a required argument positioned after an optional one (as
`NEAR_LANDMARK` sits after `[Z]` in `openarea.build`) is validated
independently and never participates in the gap.

## What `auth.py` exposes

`load_role_tokens(roster, path=<repo-root>/.env, minimum_length=20) ->
dict[str, str]` (token -> role). Reads a `.env`-shaped file for
`MCP_ROLE_TOKEN_<ROLE>` entries (one per enabled role, upper-cased role
name) and resolves each to a role. Real tokens live only in the gitignored
`.env`; `infra/local.example.env` carries the commented, empty placeholder
per currently-enabled role.

`resolve(token, tokens) -> role | None`. Looks up which role (if any) a
bearer token authenticates as, using `hmac.compare_digest` against **every**
configured token rather than a dict lookup keyed on the secret, so the work
done does not depend on which token (if any) matched.

This is the credential half of `docs/AGENT-ARCHITECTURE.md` §13's trust
boundary: **role identity must be a credential, not a claim.** A
self-declared role header would let the Architect assert it is the
Overseer and obtain write tools, silently voiding the single-writer design
(§7).

**Strict validation, all hard errors at load time** (mirroring `roles.py`'s
own style), each with a dedicated test in `mcp/tests/test_auth.py`:

1. Two roles sharing the same token.
2. A token naming a role that is not enabled on the given roster (a typo,
   or a stale token left behind after a role was disabled).
3. An empty or whitespace-only token.
4. A token shorter than `minimum_length`.

**Never logs, prints, or returns a token value or any prefix of one.**
Every error message names an env var, a role, or a length -- never the
token itself; `mcp/tests/test_auth.py` asserts this directly for the two
rules where a token value would be the obvious thing to quote (the
collision and the too-short cases).

`scripts/pve.py`'s `load_env` is this repo's existing precedent for reading
`.env` (comments and blank lines skipped, split on the first `=`, matching
surrounding quotes stripped from the value -- needed there because the
Proxmox password contains `$E`, which bash would otherwise expand away). A
hand-rolled `.env` parser that skipped that quote-stripping step produced a
false alarm in this repo on 2026-09-12 (`Working.md`). `scripts/` has no
`__init__.py`, so it is not import-able as an ordinary package from `mcp/`;
rather than reach across that boundary with a path hack, `auth.py`
reimplements the same small parsing logic verbatim instead of inventing a
different one. If `load_env` ever changes, `auth.py`'s `_read_dotenv` needs
the same fix by hand -- there is no shared import to keep them in sync.

## What `dfhack_client.py` exposes

The wire protocol behind every call here is not re-derived in this file --
it is transcribed from `research/2026-09-12-dfhack-rpc-client.md`, written
against the exact installed version (DFHack 53.16-r1.1) by reading its
source at the pinned tag. That report is the citation for every magic
number below; this section only restates what a caller of this module
needs, not the evidence.

`DFHackConnection(host="127.0.0.1", port=5000, timeout=10.0)` -- one
persistent socket. `await conn.connect()` does the handshake (`"DFHack?\n"`
+ version 1, twelve bytes, little-endian); `await conn.run_command(command,
arguments=None) -> str` runs one `df-overseer-*` console command over
`RunCommand` (method id 1 -- `BindMethod` is never needed for this repo's
use case, research doc §3) and returns its printed output, concatenated
across every `RPC_REPLY_TEXT` message in wire order. `await conn.close()`
sends `RPC_REQUEST_QUIT` and tears the socket down.

**No output sanitising anywhere in this path.** Colour
(`CoreTextFragment.color`) is a field this client never reads; `text` is
never routed through anything resembling DFHack's own ANSI-rendering
`Console::add_text`, so a `df-overseer-*` script's `print(json.encode(...))`
comes back as clean JSON with nothing to strip. `docs/TRAPS.md`'s
escape-sequence trap is specific to `dfhack-run`'s own rendering choice
(research doc §5) and does not apply to a client that reads the raw
protobuf field instead of shelling out to `dfhack-run`.

**Errors, and what they mean:**

- `DFHackConnectionError` -- an I/O failure: connection refused (DFHack is
  down), a dropped socket mid-request, a read/write timeout, or a rejected
  handshake. Research doc §1 found DFHack's own handshake rejection is not
  a distinct wire message at all -- the server just returns without
  replying -- so a bad handshake and a crashed peer and a firewall drop are
  genuinely indistinguishable on the wire, and all three surface here as
  the same exception. A connection that raises this is left closed; call
  `connect()` again (or let a pool do it, see below) rather than reusing it.
- `DFHackProtocolError` -- the peer replied, but not with something this
  protocol recognises (wrong handshake magic, a reply id outside the four
  reserved values, a length-delimited field whose declared size runs past
  the buffer). Distinct from a connection error on purpose: this means "we
  are talking to something, and it is not DFHack," which is a different
  fact than "we could not talk to it at all."
- `DFHackCallError` -- DFHack itself ran the request and replied
  `RPC_REPLY_FAIL`. Carries the raw `command_result` (`CR_*`) code in
  `.command_result`; per research doc §2, that reply's `size` header field
  directly *is* the code, with no body following it at all -- a client that
  tried to read a body after `RPC_REPLY_FAIL` would hang or desync the
  connection, which is why `run_command` branches on the reply id before
  ever touching a length.

### `DFHackConnectionPool`, and why it exists rather than one connection

**A single connection cannot carry more than one in-flight request.**
Research doc §6 traced this directly in DFHack's own server loop: a
connection's thread reads a request, replies, and only then reads the next
one -- pipelining several `RunCommand` calls onto one socket without
waiting for replies gains nothing, because the server drains and answers
them one at a time regardless of send order. Batching a cycle's reads so
they land in one DFHack suspend window (`docs/AGENT-ARCHITECTURE.md` §14
item 5's third bullet -- corrected 2026-09-12 on this exact point) is
therefore a property of **how many connections are open**, since each
accepted connection gets its own OS thread server-side, not of how many
requests are in flight on any one of them.

`DFHackConnectionPool(host, port, size=4, timeout=10.0)` is a small,
explicitly-sized set of persistent connections. `await pool.start()` opens
all `size` of them up front (and raises `DFHackConnectionError`, closing
anything it did manage to open, if any single one fails -- no half-open
pool). `await pool.run_command(...)` runs one call on whichever pooled
connection is free next. `await pool.run_many([(command, arguments), ...])
-> list[str]` is the batching primitive itself: it fires every call
concurrently (`asyncio.gather` over `size` pooled connections at once,
queuing the rest if more calls are given than the pool has slots) so their
suspend requests are pending at the same instant, in results-match-input
order. **`size` is a cap on how much of a cycle's reads can land in one
window, not a value with a universally correct default** -- it belongs in
whatever config the eventual MCP server reads, sized to the largest batch
of reads a single cycle actually wants to fire, not hardcoded here.

**Self-healing, not just detection.** Per the handoff brief's own
acceptance criterion: "a DF restart must not leave the pool full of dead
sockets that fail every later call." A pooled connection that fails
mid-request is marked closed and put back in the pool exactly as before;
the *next* acquire (`run_command`/`run_many`) sees it is closed and
reconnects it in place before use. Calls made while DFHack is actually
down still fail (there is nothing else they can do), but nothing about a
past failure lingers once DFHack is back up -- there is no separate "reset
the pool" step to remember to call. `mcp/tests/test_dfhack_client.py`'s
`test_pool_self_heals_after_a_dead_connection` is this behaviour end to
end against a fake server that deliberately drops one connection.

**What could not be verified offline, stated plainly (per the handoff
brief):** every test for this module runs against `FakeDFHackServer`, a
from-scratch asyncio TCP server written in `mcp/tests/test_dfhack_client.py`
that speaks the handshake and framing bytes independently of this file's
own encoder/decoder -- not a real DFHack process, and not VM 103, which
this stream was barred from touching. Unverified against the genuine
article: whether the VM's actual DFHack build behaves byte-for-byte as the
pinned-tag source this was built against (research doc §10 flags the same
gap); real dead-socket/DF-restart timing (the fake server's disconnect
action closes cleanly, which is a reasonable model of a `recv()` returning
`<=0` but is not the same event as an actual DF process dying under load);
and whether a real multi-connection batch actually lands inside one
DFHack-side suspend window in practice, as opposed to the fake server's
`asyncio.Barrier`-based proof that the client-side requests are at least
genuinely concurrent on the wire.

## What this package deliberately does not do

- **No MCP server, no transport.** No MCP SDK import, no HTTP, no session
  handling. That is explicitly out of scope per the task brief and belongs
  to whatever builds the actual MCP seam on top of this -- and is blocked
  on an open question (`research/2026-09-12-mcp-server-stack.md`).
- **No mutation of `TOOLS.yaml`, `ROSTER.yaml`, any `role.md`, or any doc.**
  Read-only with respect to everything outside `mcp/` and the three
  `tools.yaml` files this task named for rewriting.
- **No enforcement of `model.yaml`'s budget ceiling, cadence, or fallback
  model.** Those are real fields but a different concern (cost and
  scheduling, not permission), and `docs/AGENT-ARCHITECTURE.md` §11 already
  treats them as a separate file for exactly that reason.
- **No caching, no hot-reload watcher.** `load_registry` and `load_roster`
  are called once and return an immutable-in-practice structure. If a
  server built on this needs to pick up an edited `tools.yaml` without a
  restart, that is its own concern to add.
- **`tools.py` and `auth.py` add no new scope beyond the above.** No MCP SDK
  import, no HTTP, no session handling, no socket, no SSH, no VM, and no
  change to which tools any role has (`tool_definitions` only ever narrows
  via `Roster.check`, never widens). `auth.py` mints no tokens and rotates
  none -- they are pasted into `.env` by hand, the same way
  `PVE_TOKEN_SECRET` already is.
- **`dfhack_client.py` adds no scope beyond what its own section above
  states.** No `BindMethod` (`RunCommand` is a hardcoded id on every
  connection), no output sanitising (colour is a field this client never
  reads, not something stripped from `text`), no heartbeat/keepalive (none
  exists on the wire -- research doc §7 -- so this module does not
  pretend to poll for one), no live verification against VM 103 or any
  real DFHack process.

## Things found while doing this that are worth flagging back

- **`agents/architect/tools.yaml` and `agents/consultant/tools.yaml`'s
  `deny` entries for `labor.set-labor` and `openarea.*`/`diggable.*` are
  denying tools those roles never had in their `read` list to begin with.**
  Harmless (there is nothing to conflict with), and left exactly as
  written per the task's "do not change which tools each role has", but it
  means those specific deny lines are documentation of intent
  ("this role should never get this") rather than a live boundary catching
  anything. Worth knowing if `tools.yaml` ever grows a `read` entry for one
  of those scripts without someone re-checking the matching `deny` line.
- **`agents/overseer/tools.yaml`'s `deny` list has both `ui.*` and
  `ui.embark-mode`.** The second is fully subsumed by the first. Kept as
  two separate entries (not merged) per "preserve every note... deny reason
  verbatim", since the two carry different `reason` text and merging them
  would lose the more specific one.
- **The manifest's `planned` entries use a different namespace than
  everything else** (`queue: propose`, `sentry: status`, `knowledge:
  wiki_lookup`), colon-separated rather than the DFHack-script dotted form.
  Converted to the same dotted style (`queue.propose`, `sentry.status`,
  `knowledge.wiki_lookup`) for consistency in the rewritten `tools.yaml`
  files, but they remain a distinct, unchecked namespace as described
  above. Whoever designs the actual queue/sentry/knowledge surfaces should
  treat these as names already spoken for, not as settled ids.
- **`scripts/dfhack/TOOLS.yaml` gives two positional arguments the same name.**
  `connectivity.check-units UNIT_ID UNIT_ID` is a "from" unit and a "to" unit,
  both written `UNIT_ID`. JSON-Schema property names must be unique, so
  `tools.py` suffixes repeats in signature order (`unit_id_1`, `unit_id_2`)
  from one shared helper, so the schema and the argv builder can never
  disagree about which name means which position. The manifest would be
  clearer if it named them distinctly; not changed here, since this stream was
  barred from editing it.
- **Two argument "names" in the manifest are not names at all, they are
  literal choice lists**: `on|off` in `labor.set-labor` and
  `[idle|injured|military|hostile]` in `labor.unit-status`. They become a
  `string` property with an explicit `enum` and a synthesised name, rather
  than being mistaken for an identifier. Worth knowing before adding another
  command whose signature embeds its choices this way.
- **`scripts/` has no `__init__.py`, so `scripts/pve.py`'s `load_env` is not
  importable from `mcp/`.** `auth.py` reimplements the same small `.env`
  parsing rather than reaching across that boundary with a path hack, which
  means **two copies now exist with no import keeping them in sync.** They
  agree today, including the quote-stripping step whose absence caused a false
  drift alarm on 2026-09-12. If either changes, change both by hand. Recorded
  as a real duplication rather than presented as a clean separation.
