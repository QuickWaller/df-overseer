# Stream: MCP tool schema + role token auth

**Dispatched** 2026-09-12. **Status:** dispatched.

## Why this stream exists, and why it can run now

The MCP server is the project's one hard blocker (`Working.md` START HERE
item 2). Two parts of it have real unknowns and are being researched in
parallel right now: the DFHack RPC wire protocol, and the MCP server
framework/transport. **This stream is the part with no unknowns**, so it does
not wait on either.

Everything here is a pure function of files already in this repo. Nothing in
this stream opens a socket, SSHes anywhere, or touches VM 103 or VM 106. If
you find yourself wanting to, stop and report instead.

## What already exists, and must not be changed

- `dfmcp/registry.py` — loads `scripts/dfhack/TOOLS.yaml` into `Tool` objects
  under canonical ids (`openarea.build`, `labor.unit-status`, `overview.get`).
  Read its docstring and `dfmcp/README.md` before writing anything.
- `dfmcp/roles.py` — `Roster.check(role, tool_id) -> (allowed, reason)`. The
  enforced permission boundary.
- `dfmcp/README.md` — the canonical id scheme and what this package
  deliberately does not do.
- `agents/ROSTER.yaml` and each enabled role's `tools.yaml`.

**Do not modify any of those files, `TOOLS.yaml`, or any `agents/**` file.**
If one of them is wrong, say so in your report; do not fix it here.

## Deliverable 1: `dfmcp/tools.py`

Turns the registry into MCP tool definitions, and turns a tool call back into
the exact DFHack command line. Transport-independent: it must not import any
MCP SDK, and must not know what HTTP is.

### 1a. MCP tool names

**Canonical ids contain a dot (`openarea.build`) and MCP/Anthropic tool names
generally may not** — the widely-enforced pattern is `^[a-zA-Z0-9_-]{1,128}$`.
So the package needs a name distinct from the id.

Requirements:
- Deterministic, stable, and human-legible in a denial message.
- **Reversible by lookup, not by string surgery.** Build both directions as
  dictionaries at load time (`name -> id` and `id -> name`). Do not implement
  the reverse as a `split`/`replace`: a future script short-name containing
  the separator character would silently map two ids onto one name. Detect a
  name collision at build time and raise, the way `registry.py` already
  raises on an id collision.
- Verify your chosen pattern against the real manifest (every id, all 25),
  not against an assumption.

### 1b. Tool definitions

`tool_definitions(registry, roster, role) -> list[dict]`, returning only the
tools that role may call, checked through `Roster.check` rather than by
re-reading the YAML. The Overseer's list and the Architect's list must differ,
and `docs/AGENT-ARCHITECTURE.md` §5 names the specific asymmetry to assert in
a test: **the Overseer holds `openarea.build`/`diggable.dig` but NOT
`openarea.find`/`diggable.find`/`chokepoints.find`.** That division is
structural, so a test should fail if it ever quietly stops being true.

Each definition carries `name`, `description`, `inputSchema`.

**The description is a safety surface, not decoration.** Per
`docs/AGENT-ARCHITECTURE.md` §10, agents inherit stated reliability rather
than inventing it, so the description must carry, from the manifest and
nowhere else:
- what the command does (`Tool.description`, which is the manifest's `notes`),
- whether it mutates,
- **its verification status, stated plainly when it is not verified.**
  `Tool.is_verified` is already deliberately conservative. Never render an
  unverified tool as if it were verified — that is CLAUDE.md's "mark verified
  vs proposed" rule, and this repo has already paid once for a tool trusted
  beyond its evidence (`unit-status hostile`, see `docs/TRAPS.md`).

### 1c. Input schemas

`TOOLS.yaml` carries no argument types, only signature text like
`"build W H [Z] NEAR_LANDMARK BLUEPRINT_FILE [RANK] [RADIUS_TILES]"`.
`Tool.args` already tokenises the part after the verb.

- `[BRACKETED]` means optional; a bare token is required.
- Types are a **documented heuristic**, not knowledge: keep one explicit
  table of integer-valued argument names (`W`, `H`, `Z`, `RANK`,
  `RADIUS_TILES`, and any others the real manifest shows), default everything
  else to string, and say in the module docstring that it is a heuristic and
  where to correct it. Do not guess silently.
- Sweep the whole manifest and report any argument token the table does not
  cover confidently.

### 1d. Turning a call back into argv

`argv_for_call(tool, arguments: dict) -> list[str]`, producing exactly what
the command line needs: the script name without the `.lua` suffix, the
subcommand verb, then positional arguments in signature order.

Ground truth for the shape, from `scripts/dfhack/df-overseer-overview.lua`:
arguments arrive as Lua varargs (`local args = {...}`) and dispatch on
`args[1]`, so `overview.get` is `["df-overseer-overview", "get"]`. Confirm
that pattern against two or three other scripts rather than trusting this
line; `docs/TRAPS.md` records that `dfhack-run lua -f` passes varargs, not an
`arg` table.

**The one real trap here: positional optionals cannot be skipped.** If a
caller supplies `RANK` but omits the earlier optional `Z`, there is no way to
express that on a positional command line. Raise a specific, named error
saying which omitted argument blocks which supplied one. Silently shifting
arguments would land a dig or a build at the wrong coordinates, which is the
exact class of bug this project already paid for twice (the `quickfort -c`
top-left-vs-centre bug, `decisions/DECISIONS.md` 2026-09-11).

Also validate: unknown argument names rejected, missing required arguments
rejected, and no shell metacharacter smuggled through a string argument
(these become arguments to a real command on a live game host).

## Deliverable 2: `dfmcp/auth.py`

Maps a bearer token to a role. `docs/AGENT-ARCHITECTURE.md` §13: **role
identity must be a credential, not a claim** — a self-declared role header
would let the Architect assert it is the Overseer and obtain write tools,
voiding the single-writer design.

- `load_role_tokens(...) -> Mapping[str, str]` (token -> role) from a
  gitignored source. **This repo is public.** Real tokens go in `.env` or an
  `infra/local.*` file only; add a commented placeholder to the tracked
  `infra/local.example.env` following the conventions already in that file.
  `scripts/pve.py`'s `load_env` is the existing precedent for reading `.env`,
  including that it strips surrounding single quotes — reuse or match it
  rather than hand-rolling a parser. (A hand-rolled `.env` parser that did
  not strip quotes produced a false alarm in this repo on 2026-09-12; see
  `Working.md`.)
- `resolve(token) -> role | None`, using `hmac.compare_digest`, never a plain
  `==`, and never a dict lookup keyed directly on the secret if you can avoid
  leaking timing. Compare against every configured token so the work is
  independent of which token matched.
- **Never log, print, or include a token, or any prefix of one, in an error
  message or a return value.** Report lengths and role names only.
- Refuse to load on: two roles sharing a token, a token mapped to a role that
  is not enabled in the roster, an empty or whitespace token, and a token
  below a stated minimum length. All hard errors at load time, matching
  `roles.py`'s existing style.

## Acceptance criteria

1. `pytest` passes from the repo root, and the total count is **higher** than
   the current 45 by the number of tests you added. Report both numbers.
2. New tests live in `dfmcp/tests/test_tools.py` and `dfmcp/tests/test_auth.py`,
   matching the existing `dfmcp/tests/` style.
3. Every validation rule you add has a test that proves it actually raises.
   (`dfmcp/README.md` records that as the existing standard for `roles.py`.)
4. `tests/test_no_leaked_addresses.py` still passes — no address, hostname or
   token value in any tracked file.
5. `dfmcp/README.md` gains a section for the two new modules in the voice of the
   existing ones: what they do, what they deliberately do not do, and the
   limitation in 1c stated honestly rather than hidden.

## Out of scope, deliberately

- No MCP SDK, no HTTP server, no transport, no session handling.
- No DFHack RPC client, no socket, no SSH, no VM.
- No change to which tools any role has.
- **Do not write to `Working.md`, `decisions/DECISIONS.md` or `memory/`.**
  The orchestrator session owns those (see `handoffs/INDEX.md`). Put what
  would have gone there in your report instead: decisions you made and why,
  and anything you found that contradicts a repo doc.

## Report

Use the executor report shape. Add one section: **"Findings to record"** —
anything the orchestrator should put in the decision register, and any doc
you found to be stale or wrong. Be specific; the orchestrator will write the
row from your words.
