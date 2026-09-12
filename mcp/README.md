# `mcp/`

The permission seam: what a role is allowed to call. Not the MCP server
itself, not a transport, not an RPC client. Those are out of scope here and
come later, per `docs/AGENT-ARCHITECTURE.md` §13 item 5 ("the MCP server
itself does not exist... the seam needs per-role scoping designed in from
the start").

This package answers exactly one question, mechanically and at load time:
**given a role and a tool id, is the call allowed, and why or why not.**

## The four modules

| Module | Job |
|---|---|
| `registry.py` | Loads `scripts/dfhack/TOOLS.yaml` into an in-memory table of tools, keyed by a canonical id. Fails loudly on structural problems (a bad command signature, two commands colliding on one id). |
| `roles.py` | Loads `agents/ROSTER.yaml` plus each enabled role's `tools.yaml`, resolves both against the registry, and exposes `Roster.check(role, tool_id)`. All of the strict validation lives here, because a role's permission set is the actual security boundary (`docs/AGENT-ARCHITECTURE.md` principle 8: "a role is defined by its tool allowlist"). |
| `tools.py` | Turns a registry + roster + role into actual MCP tool definitions (`name`/`description`/`inputSchema`), and turns a validated call's arguments back into the exact DFHack argv. Transport-independent: no MCP SDK import, no notion of HTTP. |
| `auth.py` | Maps a bearer token to a role, from a gitignored `.env`-shaped file. The credential half of the trust boundary in `docs/AGENT-ARCHITECTURE.md` §13: role identity must be a credential, not a claim. |

None of the four opens a socket, an SSH connection, or a DFHack RPC call.
All are pure functions of files already in this repo (YAML, or a gitignored
`.env`), which is what makes them fully unit-testable with no VM.

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

## What this package deliberately does not do

- **No server, no transport, no RPC client.** Nothing here calls
  `dfhack-run`, opens a socket, or knows what SSH is. That is explicitly
  out of scope per the task brief and belongs to whatever builds the actual
  MCP seam on top of this.
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
  import, no HTTP, no session handling, no DFHack RPC client, no socket, no
  SSH, no VM, and no change to which tools any role has (`tool_definitions`
  only ever narrows via `Roster.check`, never widens). `auth.py` mints no
  tokens and rotates none -- they are pasted into `.env` by hand, the same
  way `PVE_TOKEN_SECRET` already is.

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
