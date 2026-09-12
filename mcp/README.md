# `mcp/`

The permission seam: what a role is allowed to call. Not the MCP server
itself, not a transport, not an RPC client. Those are out of scope here and
come later, per `docs/AGENT-ARCHITECTURE.md` §13 item 5 ("the MCP server
itself does not exist... the seam needs per-role scoping designed in from
the start").

This package answers exactly one question, mechanically and at load time:
**given a role and a tool id, is the call allowed, and why or why not.**

## The two modules

| Module | Job |
|---|---|
| `registry.py` | Loads `scripts/dfhack/TOOLS.yaml` into an in-memory table of tools, keyed by a canonical id. Fails loudly on structural problems (a bad command signature, two commands colliding on one id). |
| `roles.py` | Loads `agents/ROSTER.yaml` plus each enabled role's `tools.yaml`, resolves both against the registry, and exposes `Roster.check(role, tool_id)`. All of the strict validation lives here, because a role's permission set is the actual security boundary (`docs/AGENT-ARCHITECTURE.md` principle 8: "a role is defined by its tool allowlist"). |

Neither module opens a socket, an SSH connection, or a DFHack RPC call. Both
are pure functions of the YAML files already in this repo, which is what
makes them fully unit-testable with no VM.

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
`ui.click`, `ui.dump`, `ui.embark-mode`, `ui.leave-embark-mode`, `ui.hover`.

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
