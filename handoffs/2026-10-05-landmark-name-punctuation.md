# Handoff: workshops with an apostrophe in their name cannot be addressed

Date: 2026-10-05. **Executor, Sonnet, worktree. Offline build; read-only on
hosts; no deploys.**

## Why

Live, 2026-10-05 08:30 to 08:40 UTC: the Quartermaster proposed direct barrel
jobs at the Carpenter's Workshop (only two empty barrels; brewing stalls
without more). The Overseer rejected both (ruling-0016, ruling-0017) because
no tool could address the workshop. The MCP server refuses the apostrophe as a
shell metacharacter (`dfmcp/tools.py` around line 873, `_SHELL_METACHAR_RE`),
and the model's fallback "Carpenters Workshop" was refused by the game script
as an unknown workshop. Every landmark whose name has an apostrophe (Carpenter's,
Stoneworker's, Mechanic's Workshop, and any future one) is unreachable by name
through every tool that takes a landmark name.

## What to build (generic, every tool, every name)

- Landmark name matching tolerant of punctuation, case and spacing: one shared
  normaliser used wherever a tool resolves a landmark name (find it: the
  landmark helper in `scripts/dfhack/`, and any Python-side resolution). An
  ambiguous normalised match is refused with the candidates listed, never
  guessed.
- Decide whether the apostrophe can be allowed through the server at all: RPC
  RunCommand passes arguments as a list, not a shell, so check what
  `_SHELL_METACHAR_RE` actually protects against and whether DFHack's own
  argument handling is affected by a quote. Keep the refusal if it is needed;
  the normaliser makes the apostrophe unnecessary either way.
- The refusal text for a forbidden character should say what to do (for
  example, "omit the apostrophe; names match ignoring punctuation").
- Optional, only if trivial and generic: a building-id argument where tools
  already resolve to a building.

## Tasks (commit after each)

1. Plan in the Result section: where names are resolved today, every tool
   affected.
2. Build, with tests (Lua-logic tests run with `lupa`, see CLAUDE.md).
3. Result: built, tests, deploy targets (expect vm103-dfhack-scripts and
   vm103-dfmcp), live check (`workjob.list-jobs` with "Carpenters Workshop"
   resolves).

## Rules

- First step: `git merge --ff-only main`. Commit plan early and after each
  milestone.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md`, `docs/CONDUCTOR-EXECUTION*.md`.
- Touched surfaces: `scripts/dfhack/` (the landmark resolution helper and
  callers only), `dfmcp/tools.py` (argument check and its message only), tests,
  this handoff. Not `dfmcp/queue_tools.py`, `dfqueue/`, `conductor/` (another
  stream is building there).
- No armok powers. Public repo: no hostnames, IPs or tokens. No em dashes. No
  attribution lines in commits. Do not touch the live fort.
- Full ambient `python -m pytest` (with `lupa`) and `dfmcp/tests` green.

## Result

Plan and built (executor, offline).

Where names are resolved today: (1) `df-overseer-landmarks.lua`
`get_landmark_centroid` and `get_landmark` (exact `==`), used through
`landmarks_mod.get_landmark_centroid(near)` by building, chokepoints,
connectivity (both endpoints), diggable (x2), farm, harvest (x2), openarea,
stockpile, trees (x2), well, workshop, zone (x3) and landmarks' own
`build_at_landmark` and `get`; (2) `df-overseer-workjob.lua`
`resolve_building_generic` (exact `getName` match) used by `list_workshop_jobs`
and `queue_job`. Python side: `dfmcp/tools.py` `_SHELL_METACHAR_RE`.

Built:
- `df-overseer-textutil.lua`: `normalize_name` (lowercase, drop all non
  alphanumerics) and `match_name(query, names)`: exact match first, else
  normalised; more than one DISTINCT normalised candidate is refused with the
  candidates listed; identical duplicate names are not ambiguous (first wins,
  as before).
- `df-overseer-landmarks.lua`: `get_landmark` and `get_landmark_centroid` use
  it, so every near-landmark tool above inherits it with no edits;
  `get_landmark_centroid` returns a 4th value, the reason, on failure;
  `build_at_landmark` and `landmarks get` surface an ambiguity with
  candidates. The other callers read only x, y, z, so an ambiguous name there
  still reads "landmark not found" (ambiguity needs two distinct names that
  differ only in punctuation or case, so it is rare); left unedited to keep
  the touched surfaces small.
- `df-overseer-workjob.lua`: `resolve_building_generic` uses it (workjob.list,
  list-jobs, queue).
- `dfmcp/tools.py`: the apostrophe is no longer refused. Why it is safe:
  `dfmcp/dfhack_client.py` sends RunCommand as a protobuf message whose
  `arguments` is a `repeated string`, a list that no shell and no DFHack
  tokenizer re-parses, so `'` is a literal character inside one argument.
  Still refused: `; & | backtick $ ( ) < > backslash double-quote` and
  newlines (conservative, in case a transport ever shells out). The refusal
  text now says to remove the character and that names match ignoring case,
  spacing and punctuation. Not proven live: that DFHack hands an apostrophe
  argument to the script untouched; that is the live check below.
- Building-id argument (optional): not done, not trivial across tools.

Tests: new `tests/test_landmark_name_matching_lua_logic.py` (9, real textutil
and real workjob resolution under lupa); `tests/test_workjob_wildcard_lua_logic.py`
stub now loads the real textutil; `dfmcp/tests/test_workjob_tool.py` apostrophe
test inverted (passes through) plus a double-quote refusal-message test.
Ambient `python -m pytest` (lupa present): 2765 passed, 3 skipped.
`dfmcp/tests` in `.venv-dfmcp`: 800 passed. Landmark centroid resolution
itself has no direct lupa test (the footprint stub overrides it); it is
covered through the shared matcher tests.

Deploy targets: vm103-dfhack-scripts (textutil, landmarks, workjob; all three
together, since workjob and landmarks now call `textutil.match_name`) and
vm103-dfmcp (`dfmcp/tools.py`, then restart `dfmcp-server`). Live check:
`workjob.list-jobs` with "Carpenters Workshop" resolves and returns the job
list; also `workjob.list-jobs` with "Carpenter's Workshop" passes the server
(proves the apostrophe reaches the script intact).
