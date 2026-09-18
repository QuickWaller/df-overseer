# Handoff: serve the fort's history to agents over MCP

Date: 2026-09-19. **Offline build stream. No VM, no SSH, no deploy.**

Read `CLAUDE.md`, then `docs/TIMESERIES.md`, then `dfseries/` in full
(including the reset-aware API added by
`handoffs/2026-09-19-dfseries-resets.md`, read its write-up), then
`dfmcp/doctrine_tools.py` **in full**, which is the pattern you follow, then
this.

## The goal

The fort now records its own history (`dfseries`), and it imports on the VM
automatically (`handoffs/2026-09-19-dfseries-auto-import.md`). **No agent can
see any of it.** Build the read-only MCP tools that let one.

## Deliverable

Native tools in a new `dfmcp/series_tools.py`, served **exactly the way
`doctrine_tools.py` is**: hand-written `NativeTool`s with explicit JSON
schemas, merged via `load_registry(native_tools=...)`, enforced through the
one `Roster.check` boundary, routed by `dfmcp/server.py`'s generalised
native-tool branch. **One boundary, not a second permission path.**

The minimum set, each wrapping the `dfseries.trend` function of the same
purpose rather than re-implementing it:

- **the timelines**, marking which is current and which are superseded;
- **a series** for a subject and metric over a tick window;
- **the latest value**;
- **a rate over a window**;
- **reset events** for a resetting timer, and the **fort-level events per
  dwarf-day** aggregate (drinking events, for thirst).

Name the ids to match the registry's conventions (`doctrine.get` is the
precedent) and say what you chose.

## What the output must never lose

The store was built to refuse confident nonsense. **The tools must carry
every qualifier through to the agent, unflattened**, because an agent reading
a bare number is exactly how this project's past errors propagated:

- every rate carries its **sample count, tick span and skipped nulls**;
- every output states the **metric kind it assumed** (level or resetting
  counter) and, for a counter, whether reset times are **exact or
  interval-bounded**;
- an `unavailable` result carries its **reason**, and is never rendered as a
  number;
- a query that reached a **superseded** timeline says so;
- **a `null` reading is never rendered as `0`.**

Write a test for each of those, through the real registry and roster, not just
against the functions.

## Decisions you must make and state

- **Which roles get which tools.** The quartermaster role (if enabled) owns
  inventory and production trends by agreed design; the overseer arbitrates;
  the consultant fact-checks. Read `agents/*/role.md` and choose deliberately,
  per role, with a reason, as the `get_doctrine` stream did.
- **`knowledge_scope`.** This is live fort state read by the game itself, which
  is a different case from doctrine's curated corpus. Read how `roles.py` uses
  the field and choose; `player_derivable` is plausible because every metric is
  something a player can see in-game, but say why.
- **The database path**: configurable, read from the environment like
  `MCP_SERVER_DOCTRINE_PATH`, defaulting to whatever path the auto-import stream
  chose (read its write-up); **fail loudly if the database is absent**, never
  return empty history as though the fort had none.

## Rules

- **Write as you go.** Commit on your branch after each milestone and append
  to this file's write-up each time.
- Read-only: `.mutates` is `False`.
- No coordinates. **Never write an IP address, hostname or port into any
  committed file.**
- Do **not** write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md` or `docs/TIMESERIES.md`. No em dashes in prose.

## Touched surfaces

`dfmcp/series_tools.py` (new), its tests, minimal wiring in `dfmcp/server.py`
and test fixtures that load the registry, `agents/*/tools.yaml`,
`infra/local.example.env` (one new path variable), and this handoff doc.
**Not** `dfseries/`.

## Done means

The tools are reachable through the real registry and roster, every qualifier
above survives to the agent and is tested, the role and scope choices are
stated with reasons, the full suite passes (report before and after), and the
write-up says exactly what a deploy needs.
