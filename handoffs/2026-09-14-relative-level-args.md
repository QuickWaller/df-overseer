# Stream: replace absolute Z arguments with a level relative to the landmark

**Written** 2026-09-14. **Status:** dispatched. **User go-ahead:** "yes look
into that", for the gap below. This stream is **code and tests only, no
deploy**. Pushing the changed Lua to VM 103 is a separate, gated step.

## The gap, verified live on VM 103 (read-only probe, 2026-09-14)

The first architect charter run
(`evals/live/2026-09-14-architect-first-charter/`) called `diggable.find` with
`z` = 0, -1, -2, -3, -4, got `[]` every time, and concluded there was nothing
to dig underground. **That conclusion was wrong, and the tool caused it.**

- DF z is absolute. Uniboslan's map runs from z 0 to z 185, and the landmarks
  sit at z 168 to 169. `z` = 0 or -1 searches a level nowhere near the fort,
  or off the map, and **returns `[]` silently instead of an error**.
- Called with the landmark's z minus 1, `find_diggable_area(3,3,…)` returns
  **5 candidates** near Embark Site, Stockpile #2 and Wagon.
- At landmark z minus 2 and below it returns 0. No tile there is walkable, so
  v1's "must border the walkable network" filter rejects everything (by
  design, `df-overseer-diggable.lua` header).
- The MCP input schema gives the model `"z": {"type": "integer"}`, **with no
  description at all**. `dfmcp/tools.py` `_input_schema` emits no
  descriptions for any argument.

2026-09-11's fix (Z defaults to the landmark's own z) went halfway. A
coordinate-free caller can use the default, but still cannot say "one level
down" without knowing an absolute coordinate. Design commitment #1
(`docs/PURPOSE.md`) says it must never need one.

## What to do

1. **Lua: optional `Z` becomes `LEVEL`, an integer offset from
   `NEAR_LANDMARK`'s own level** (0 = the landmark's level, -1 = one below,
   1 = one above). Omitted means 0, so behaviour is unchanged for every
   caller that omits it today. Apply this to:
   - `df-overseer-diggable.lua`: `find` and `dig`
   - `df-overseer-openarea.lua`: `find` and `build`
   - `df-overseer-chokepoints.lua`: `find` (its `Z` is currently required;
     make it an optional `LEVEL` in the same position if that keeps the
     argument order parseable, otherwise explain why not)

   Resolve `az + LEVEL` inside the script. Nothing returns or prints the
   resolved absolute z.
2. **A level off the map is an error, not an empty list**: `{"error": "level
   N from <landmark> is outside the map"}`, the same shape the scripts already
   use for "landmark not found". Check with the map size
   (`dfhack.maps.getSize()`), and do not put the absolute value in the
   message.
3. **Update each script's header and usage lines**, plus
   `scripts/dfhack/TOOLS.yaml`'s command keys: `[Z]` becomes `[LEVEL]`.
   `dfmcp` builds tool names and argument names from those usage strings, so
   the MCP argument name becomes `level`. Grep the repo for every other place
   that parses or documents those usage strings: agents' `tools.yaml`,
   `dfmcp/README.md`, tests, `evals/`, `scripts/`, `docs/`.
4. **Argument descriptions in the MCP schema.** Give `_input_schema` a way to
   emit a `description` per argument. Keep it in one table keyed by argument
   token, next to where tokens are already parsed, rather than in each tool's
   YAML. Cover at least `LEVEL` (state the relative meaning, and that levels
   below the dug fort return nothing until something walkable exists there),
   `NEAR_LANDMARK`, `RADIUS_TILES`, `W`, `H`, `RANK` and `BLUEPRINT_FILE`.
   Say plainly that no argument takes a coordinate.
5. **Tests:** update and extend `dfmcp/tests/` for the renamed argument, the
   descriptions, and the positional-optional gap check still working with
   `LEVEL`. Run the suite both ways: the ambient baseline (`121 passed, 1
   skipped` before your change, and say what it is after) and the venv with
   `dfmcp/requirements.txt` installed, if you can build one. Report both
   numbers.
6. **Write the live verification** you would run once this is deployed, but
   do not run it:
   - a `dfhack-run lua` probe like the orchestrator's, covering `LEVEL` 0 and
     -1 on each surface landmark, and an off-map `LEVEL` giving the error;
   - an MCP-level call with `level: -1`.

   Put it in this doc's Result section.

## Hard lines

- **No deploy.** Don't copy anything to VM 103, don't touch
  `dfmcp-server.service`, and don't call a mutating tool. Reading VM 103 is
  fine if you need to check an API name, but the orchestrator has already
  verified the facts above.
- Don't touch `learning/`, `agents/*/role.md` or `evals/live/` output.
- No commits (the orchestrator reviews the diff and commits). Don't edit
  `Working.md`, `decisions/`, `memory/`, `CLAUDE.md` or other handoff docs.
  Add a Result section here and your row in `handoffs/INDEX.md`.
- Public repo: no addresses, tokens or real fort coordinates in anything
  tracked.

## Report

Executor shape, plus:
- every file changed, with a one-line reason each;
- test numbers both ways;
- anything you found that the brief got wrong;
- the exact deploy and live-verify commands for the gated next step.

## Result (2026-09-14): DONE, code and tests only, nothing deployed

STREAM: replace absolute Z arguments with a level relative to the landmark
STATUS: done

### DID

**Lua (`scripts/dfhack/`), each `Z` -> `LEVEL`, an offset relative to
`NEAR_LANDMARK`'s own level (0/omitted = same level, unchanged behaviour for
every existing caller):**

- `df-overseer-openarea.lua` -- `find`/`build` now take `[LEVEL]` in the same
  position `[Z]` held. Added a local `resolve_level(az, level, landmark_name)`
  (adds `az + level`, validates against `dfhack.maps.getSize()`'s third
  return value, `z_count_block` -- confirmed live by this repo's own
  `df-overseer-breach.lua` to bound z as `0` to `z_count_block-1`) and wired
  it into `ranked_candidates`. Header rewritten to explain the LEVEL change
  alongside the existing 2026-09-11 Z-defaulting note, kept rather than
  deleted (the earlier fix is still true and still relevant).
- `df-overseer-diggable.lua` -- identical shape (`find`/`dig`), its own
  duplicated `resolve_level` (matching this file's existing convention of
  duplicating small pure helpers like `parse_quickfort_stats` rather than
  reqscript-ing across files for a few lines).
- `df-overseer-chokepoints.lua` -- the one real judgement call. `find`'s `Z`
  was **required**, with no default at all, unlike the other two -- so this
  was the tool a caller had *zero* coordinate-free way to call. Fixed by
  making `LEVEL` optional in the same first-argument position: the CLI
  parser sniffs `tonumber(args[2])` the same way `openarea`/`diggable`
  already sniff `args[4]`, just one slot earlier since this command has no
  `W H` ahead of it. `find_chokepoints(level, near, radius_tiles)` now
  resolves `az` from the landmark and calls the same `resolve_level`.
- All three: an out-of-map `LEVEL` now returns
  `{"error": "level N from <landmark> is outside the map"}` (`N` is the
  relative LEVEL value, never the resolved absolute z) instead of silently
  scanning a real but nowhere-near-the-fort level and returning `[]` -- the
  exact failure mode that hid this gap in the first architect charter run.

**`scripts/dfhack/TOOLS.yaml`** -- the 5 affected command keys' signatures
changed `[Z]`/`Z` to `[LEVEL]` (`openarea.find`, `openarea.build`,
`diggable.find`, `diggable.dig`, `chokepoints.find`). Left `verified:`
fields untouched: the wrapped scan/build logic these dates verify is
unchanged, only how z gets computed changed, and the brief didn't ask for a
verified-status change -- flagged below under "what the brief got wrong /
worth a call" since I think a fresh live check is still warranted before
calling LEVEL itself verified.

**`dfmcp/tools.py`**:
- `_INTEGER_ARG_NAMES`: `"Z"` -> `"LEVEL"`.
- New `_ARG_DESCRIPTIONS: Dict[str, str]`, keyed by the raw manifest token
  (`"LEVEL"`, `"NEAR_LANDMARK"`, `"RADIUS_TILES"`, `"W"`, `"H"`, `"RANK"`,
  `"BLUEPRINT_FILE"`), living right next to `_INTEGER_ARG_NAMES` rather than
  in `TOOLS.yaml` (one table shared across every tool, not one field
  per-command). `ArgSpec` grew a `description: Optional[str] = None` field;
  `_parse_arg_token` looks it up by the token text before brackets are
  stripped; `_input_schema` emits a `"description"` key only when one
  exists (never an empty string) -- same honest-gap convention
  `_INTEGER_ARG_NAMES` already uses for type. `LEVEL`'s description states
  the relative meaning (0/-1/1), says plainly it is never an absolute
  coordinate, and states that a level below the dug fort returns nothing
  until something walkable exists there. `NEAR_LANDMARK` and
  `BLUEPRINT_FILE`'s descriptions also say plainly they are never
  coordinates.
- Module docstring updated: the `[Z]` example is now `[LEVEL]`, the
  positional-optional-trap paragraph's example changed from `Z` to `LEVEL`,
  and a new "Argument descriptions" section explains `_ARG_DESCRIPTIONS`.

**`dfmcp/tests/test_tools.py`**: renamed every `"z"`/`Z` reference to
`"level"`/`LEVEL` (arg-spec assertions, `argv_for_call` happy-path and
positional-gap tests, the module docstring's file:line citations, which I
re-checked against the actual current line numbers after editing the Lua
file rather than leaving them stale). Added 6 new tests: LEVEL/NEAR_LANDMARK
description content (states "relative", states "not"+"coordinate", states
-1/1), every documented token has a description on a real tool, the schema
actually carries `"description"` when one exists, an undocumented token
(`UNIT_ID`) gets no `"description"` key at all, and
`chokepoints.find`'s `LEVEL` is confirmed optional+integer (it was
required, with no schema-level default, before this stream).

**`dfmcp/README.md`**: updated the two `[Z]` signature quotes to `[LEVEL]`,
the positional-optional-trap paragraph's example, and added a short
"Argument descriptions" paragraph mirroring `tools.py`'s new docstring
section.

**`scripts/install_df.py`**: found while grepping "scripts/" for usage-string
references (in scope per the brief's step 3) -- `cmd_run`'s docstring and
its `argparse` help text both used `df-overseer-openarea find 5 5 169
"Embark Site"` as the example invocation, `169` being exactly the kind of
absolute-z value this stream eliminates (it would now resolve as `LEVEL=169`
and hit the new out-of-map error). Changed the example to `-1` in both
places, with a one-line parenthetical explaining LEVEL is relative.

### VERIFIED

- **Python, ambient** (`/c/Users/wills/AppData/Local/Programs/Python/Python312/python`,
  chosen because `py -3`/`python3` are not on PATH on this Windows
  workstation and this is the interpreter the existing `.venv-dfmcp` venv
  was itself built from with `--system-site-packages`; it has `mcp 1.27.1`
  importable directly but not `httpx2`, so `dfmcp/tests/test_server.py`
  still skips as one module-level skip, matching the documented mechanism):
  **before my changes, 102 passed, 1 skipped** (not the 121 the brief
  states -- see "what the brief got wrong" below); **after, 108 passed, 1
  skipped** (+6, the new description/chokepoints tests, 0 regressions).
- **Python, venv** (`.venv-dfmcp`, already present in the repo root with
  `mcp==2.2.0`/`pyyaml==6.0.3` installed per `dfmcp/requirements.txt`, built
  `--system-site-packages` from the same Python 3.12): **before, 119
  passed** (not 121+ either); **after, 125 passed** (+6, same delta,
  `test_server.py` fully exercised, 0 regressions).
- Manually exercised `dfmcp.tools.argv_for_call`/`_arg_specs_for_tool`
  against the real loaded registry (not a synthetic one) for all 5 changed
  commands: confirmed `openarea.find/build`, `diggable.find/dig` each now
  expose `level` as an optional integer in the same position `z` held;
  confirmed `chokepoints.find` now exposes `level` as optional (was
  required); confirmed the positional-optional gap check still fires
  correctly for `chokepoints.find` (`radius_tiles` supplied, `level`
  omitted -> `ArgumentError` naming both); confirmed a full-optionals call
  builds `["df-overseer-chokepoints", "find", "-1", "Embark Site", "20"]`
  as expected.
- Read all three edited `.lua` files start to finish after editing (not
  just the diffed hunks) checking brace/`end`/`local` balance and that every
  call site of `ranked_candidates`/`find_chokepoints` was updated
  consistently -- no Lua interpreter is available on this Windows
  workstation (`lua`/`lua5.1`/`luac` all absent from PATH), so this is a
  read-verification only, exactly the limitation the brief flagged
  ("Lua scripts are not unit-tested locally, so read them carefully").
- Confirmed no `[Z]` or `find Z NEAR_LANDMARK` tokens remain anywhere in
  `scripts/dfhack/TOOLS.yaml` (grep, zero matches) or in the three edited
  `.lua` files' CLI-facing usage strings.
- Repo-wide grep for `\[Z\]`/`find Z NEAR_LANDMARK` after all edits: the only
  remaining hits are this handoff doc's own "gap" section (describing the
  historical bug, correctly left as-is), `handoffs/2026-09-12-mcp-tool-schema.md`
  (a closed, dated stream doc), and `research/2026-09-12-write-conflict-matrix.md`
  (a dated research spec) -- none of those are live documentation of current
  tool usage, so left untouched per the hard line against editing other
  handoff docs and this repo's convention that `research/` is a dated,
  historical artifact, not a living reference.
- Checked `agents/overseer/tools.yaml` and `agents/architect/tools.yaml`:
  both reference tools only by canonical id (`"openarea.find"`,
  `"chokepoints.find"`, etc.), never by argument name, so neither needed a
  change -- confirmed by reading both files in full, not assumed.
- Checked `docs/PURPOSE.md`, `docs/AGENT-ARCHITECTURE.md`,
  `docs/DF-UI-AUTOMATION.md`: none quote the `Z`/`[Z]` argument specifically
  (grep confirmed), so none needed edits.
- Checked `evals/` for usage-string references outside `evals/live/` output:
  the only 3 hits repo-wide are all inside
  `evals/live/2026-09-14-architect-first-charter/`, which the hard lines
  explicitly forbid touching -- left untouched.

### Anything the brief got wrong

- **The stated ambient baseline (`121 passed, 1 skipped`) does not match
  what this stream actually measured before any change**: 102 passed, 1
  skipped ambient, 119 passed in the venv. I re-ran both twice to rule out
  a fluke; the counts were stable. I don't have a way to tell whether the
  brief's number is from a different Python environment, a point in time
  with more tests than exist in the current `main` checkout, or a
  transcription slip -- flagging it rather than silently reporting against
  the wrong baseline. The important number either way is the **delta**:
  +6 tests, 0 regressions, in both environments, which is what I've
  verified directly.
- **`TOOLS.yaml`'s `verified:` dates for the 5 changed commands are now a
  little stale in spirit**, even though I didn't touch them per the brief's
  literal instructions. The 2026-09-11 dates verified the *scan/build logic*
  against real Z values that happened to work; they never exercised the new
  `LEVEL` offset math or the new out-of-map error path at all (that code
  didn't exist yet). I'd suggest the orchestrator treat `LEVEL` itself as
  unverified until the live check below actually runs, regardless of what
  the manifest's `verified:` field still says.
- **Everything else in the brief matched what I found**: the chokepoints
  positional shift was parseable in the same argument slot as described;
  `dfhack.maps.getSize()`'s third return value bounding z 0 to
  `z_count_block-1` was exactly as `df-overseer-breach.lua`'s own comment
  (independently, already in this repo) says; the positional-optional trap
  test infrastructure needed only renaming, not restructuring.

### DOCS UPDATED

None of `Working.md`/`decisions/DECISIONS.md`/`memory/`/`CLAUDE.md` (per the
hard lines -- orchestrator owns those). This handoff doc's own Result
section (this section) and `handoffs/INDEX.md`'s new row for this stream.

### BLOCKED/HANDBACK

Not blocked. Nothing gated was touched. The gated next step (deploy +
live-verify) is written below for the orchestrator to run.

### NEXT: the gated deploy + live-verify commands (not run by this stream)

**Deploy** (requires explicit go-ahead -- copies files to VM 103 and
restarts a live service; check in with any peer session first per this
repo's standing rule):

```
python scripts/install_df.py script-install df-overseer-openarea.lua
python scripts/install_df.py script-install df-overseer-diggable.lua
python scripts/install_df.py script-install df-overseer-chokepoints.lua
```

(or `ui-install` to redeploy all 10 files at once -- either way, TOOLS.yaml
itself and `dfmcp/` don't need copying to VM 103; VM 103 only runs the
`.lua` files, and `dfmcp-server.service` reads `TOOLS.yaml` from wherever
`dfmcp/` is deployed under `/opt/df/`, which needs its own separate,
already-established redeploy step per `handoffs/2026-09-14-dfmcp-deploy.md`
if this change should reach the live MCP server too.)

**Live-verify, Lua level, direct dfhack-run** (read-only, safe against the
live fort -- `find` never mutates):

```
# LEVEL 0 (default, same level as the landmark) on each current surface
# landmark -- get real names first, don't assume "Embark Site" is still the
# only one:
python scripts/install_df.py run df-overseer-landmarks list

# For each landmark name that comes back (Embark Site, Stockpile #2, Wagon
# etc. as of the last live read -- names may have changed):
python scripts/install_df.py run df-overseer-diggable find 5 5 0 "Embark Site"
python scripts/install_df.py run df-overseer-diggable find 5 5 -1 "Embark Site"
python scripts/install_df.py run df-overseer-openarea find 5 5 0 "Embark Site"
python scripts/install_df.py run df-overseer-openarea find 5 5 -1 "Embark Site"
python scripts/install_df.py run df-overseer-chokepoints find 0 "Embark Site"
python scripts/install_df.py run df-overseer-chokepoints find -1 "Embark Site"

# Expect: LEVEL -1 on diggable.find to reproduce the 5 real candidates the
# gap section above describes (near Embark Site/Stockpile #2/Wagon), not []
# -- this is the actual regression check for the bug that started this
# stream.

# Off-map LEVEL, all three tools, expect the new error shape and NOT a
# silent [] or a Lua traceback:
python scripts/install_df.py run df-overseer-diggable find 5 5 9999 "Embark Site"
python scripts/install_df.py run df-overseer-openarea find 5 5 -9999 "Embark Site"
python scripts/install_df.py run df-overseer-chokepoints find 9999 "Embark Site"
# Expect each to print: {"error":"level 9999 from Embark Site is outside the map"}
# (or -9999) -- and confirm the message contains no absolute z number.
```

**Live-verify, MCP level** (after the separate `dfmcp/` redeploy referenced
above; requires a real architect or overseer role token from VM 103's
`.env`, never printed): a plain `curl` two-step (POST `initialize`, then
POST `tools/call` reusing the returned `Mcp-Session-Id`) is the pattern
`handoffs/2026-09-14-dfmcp-deploy.md` used successfully from VM 106 for
`landmarks__list`; reuse that exact mechanism with `diggable__find` and
`{"w": 5, "h": 5, "level": -1, "near_landmark": "Embark Site"}` as the
`arguments` body. If curl again can't carry the streamable-HTTP session
cleanly for a call with this many arguments, fall back to the SDK-client
approach this repo's own `dfmcp/tests/test_server.py` already proves works
(`mcp.client.streamable_http.streamable_http_client` +
`mcp.client.session.ClientSession`), pointed at VM 103's real address
instead of the in-process fake transport:

```python
import asyncio
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

async def main():
    async with streamable_http_client(
        "http://<VM-103-LAN-address>:<port>/mcp",
        headers={"Authorization": "Bearer <architect-or-overseer-token>"},
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "diggable__find",
                {"w": 5, "h": 5, "level": -1, "near_landmark": "Embark Site"},
            )
            print(result.structuredContent)

asyncio.run(main())
```

Expect a real, non-empty candidate list (mirroring the Lua-level check
above), and separately a call with `"level": 9999` expected to surface the
`{"error": "..."}` shape through `structuredContent` rather than an MCP
protocol-level failure -- worth confirming explicitly, since this stream
never exercised the MCP layer's own error-passthrough path for this
specific new error shape, only `argv_for_call`'s argument validation (which
never sees the Lua-side error at all -- that error comes back from DFHack
at call time, not from `dfmcp` itself).
