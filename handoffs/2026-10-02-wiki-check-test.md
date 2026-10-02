# Handoff: close the loose ends (wiki-check test and repo-side tidy-ups)

Date: 2026-10-02. **Executor, Sonnet, worktree. Offline only: no VM access,
no deploys.** The user wants everything clean before any new experiment or
feature ("close things we've left dangling").

## Tasks, in order (commit after each)

1. **`doctrine/tests/test_wiki_check.py::test_cli_exit_codes` fails every
   day.** Root cause found by two earlier streams: `doctrine/wiki_check.py`'s
   `main` reads the real wall clock instead of the test's injectable clock,
   while the fixture pins `last_full_pull_utc` to `T0` (2026-09-24), so the
   mirror reads `very_stale` once real time passes the threshold. Give
   `main` (and anything it calls that reads "now") an injectable clock with
   the real clock as the default, and pass the test's clock in. Do not
   weaken the staleness rule itself. Add a test that proves the CLI still
   reports `very_stale` for a genuinely old pull, so the fix cannot hide a
   real stale mirror. Then the full ambient suite must be green with zero
   failures: report the count.
2. **CLAUDE.md tool counts point at `docs/STATE.md`.** Replace the
   hand-written per-role tool counts in CLAUDE.md's status block with a
   pointer to `docs/STATE.md`, and update `tests/test_doc_facts.py` so it
   still fails if any doc states a per-role count that disagrees with the
   registry (it must keep catching Working.md or a charter that hand-writes
   a wrong number). Edit only that sentence in CLAUDE.md.
3. **Guide wording.** Some structured guides (`scripts/dfhack/TOOLS.yaml`,
   `guide.arguments[].meaning`) were filled from a shared table and mention
   `NEAR_LANDMARK` for tools whose argument is `SITE` (`blueprint.apply` is
   one). Find every argument meaning that names an argument the command does
   not take, and fix the wording. Byte-preserving round trip as before.
4. **The two largest remaining tool descriptions** are the native
   `gotchas.write` (about 1,450 characters) and `gotchas.get` (about 1,130),
   sent to every role on every request. Shorten each to a summary of two or
   three sentences and move the detail into that tool's own guide text,
   returned when an agent asks `gotchas.get` about `gotchas.write` or
   `gotchas.get`. Per-role tool counts must not change; report before and
   after sizes.
5. **ROADMAP.md review.** Do the lightweight full-review pass CLAUDE.md
   describes: re-scan Now/Next/Later against `Working.md`, the register and
   `handoffs/INDEX.md` for anything quietly finished or stalled, update it,
   bump `**Last reviewed:**`. List anything you moved and why.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`.
- Touched surfaces: `doctrine/wiki_check.py` and its tests, CLAUDE.md (task
  2's sentence only), `tests/test_doc_facts.py`, `scripts/dfhack/TOOLS.yaml`
  (guides only), `dfmcp/gotchas_tools.py` and its tests, `ROADMAP.md`.
- Public repo: no hostnames, IPs or tokens. No em dashes. No attribution
  lines in commits.

## Done when

Ambient suite green with zero failures, `dfmcp/tests` in `.venv-dfmcp`
green, `tests/test_doc_facts.py` green, and a Result section here.

## Result

All 5 tasks done. `git merge --ff-only main` was already up to date at the
start (this worktree already carried `main`'s latest, including the
`tool-descriptions-split` and `structured-tool-guides` streams).

**Task 1 (the daily wiki-check CLI failure).** Root cause confirmed exactly
as the handoff described: `doctrine/wiki_check.py`'s `_open_reader` opened a
path with `Store.open_readonly(store_reader)`, never passing a clock, so
the opened `Store` always used `_utcnow` (the real wall clock) for its
staleness check regardless of what clock the caller injected elsewhere.
`main`, `check_doctrine` and `_open_reader` all gained an optional `clock`
keyword (default: the real clock, unchanged production behaviour), threaded
through to `Store.open_readonly(path, clock=clock)` only when a path is
opened here (an already-open `Store`/reader keeps whatever clock it was
built with). The staleness rule itself is untouched: `test_cli_exit_codes`
now passes the test's own `wall` clock into `wiki_check.main(..., clock=wall)`
so "fresh pull, same moment the fixture pinned `last_full_pull_utc`" reads
fresh regardless of real wall-clock drift. Added
`test_cli_still_reports_very_stale_for_a_genuinely_old_pull`: advances the
*injected* clock itself 30 days past the pull and asserts the CLI still
exits 1 and still says so, proving the fix cannot hide a real stale mirror.

**Task 2 (CLAUDE.md tool counts to docs/STATE.md).** CLAUDE.md's "Role tool
lists" sentence now reads "(read plus write): **see `docs/STATE.md`'s
generated per-role tool counts** (last matched live 2026-10-01, re-measured
offline 2026-10-02)" instead of hand-writing five numbers. Only that
sentence was touched. `tests/test_doc_facts.py` was rewritten so it no
longer *requires* the old sentence shape to exist anywhere (finding none is
now a pass, since STATE.md is the source of truth) -- but it still scans
CLAUDE.md, Working.md, *and now every `agents/*/role.md` charter* for that
exact sentence shape, and still fails on a wrong number if one ever
reappears there. A new `test_claude_md_points_at_state_md_for_tool_counts`
asserts CLAUDE.md's sentence names `docs/STATE.md` and carries no numbers,
so the pointer itself cannot silently regress back to a hand-written count
or quietly vanish.

**Task 3 (NEAR_LANDMARK/SITE guide wording).** Wrote a one-off script
(parsed every command signature in `scripts/dfhack/TOOLS.yaml`, flagged any
`guide.arguments[].meaning` naming a capitalised token absent from that
command's own signature) rather than trusting the two examples named in the
handoff; it found more than just `blueprint.apply`. Fixed, by exact line
number (byte-preserving, no YAML re-serialisation):
- `blueprint.preview`/`apply`/`reserve` (argument is `SITE`, not
  `NEAR_LANDMARK`): their `LEVEL`, `RANK` and `RADIUS_TILES` meanings now say
  `SITE` (9 lines across the 3 commands).
- `zone.list` (argument is `NEAR_LANDMARK_FILTER`): its `RADIUS_TILES`
  meaning now names the filter argument, not the bare word.
- `threat.scan` and `breach.check` (neither takes a landmark argument at
  all -- both are OR'd against *every* named landmark, confirmed by reading
  `df-overseer-breach.lua`'s own comment "within radius_tiles of a named
  landmark"): their `RADIUS_TILES` meanings now say "a landmark" instead of
  implying a `NEAR_LANDMARK` argument that does not exist.
Remaining script hits were checked by hand and are false positives (RES_ID's
meaning uses the plain words THAT/OTHER; OWNER names example noble roles
MANAGER/SHERIFF/BOOKKEEPER; MATERIAL_CHOICE names SHALE as an example value;
LABOR/POSITION_CODE name example labors/positions; THINK_FPS/BASE_FPS
substring-match FPS) -- none of these name an argument the command doesn't
take, they use capitalised words in ordinary prose or as worked examples.

**Task 4 (gotchas.get/gotchas.write's own descriptions).** Measured before:
`_GET_DESCRIPTION` 1,128 chars, `_WRITE_DESCRIPTION` 1,450 chars (both match
the handoff's own ~1,130/~1,450 estimate and the tool-descriptions-split
stream's "Not done" note that flagged these as the next-highest-value
target). Both rewritten to 2-3 plain sentences (324 and 291 chars). The
full operating detail (four lookup modes, the two write modes, every
field's meaning, known traps) moved into `_GET_GUIDE`/`_WRITE_GUIDE`, built
with the exact same `ToolGuide`/`GuideArgument` dataclasses
`dfmcp/registry.py` already uses for TOOLS.yaml-backed tools (imported from
there, no duplicate shape invented). `gotchas_tools.NativeTool` gained an
optional `guide: Optional[ToolGuide] = None` field; `dfmcp/server.py`'s
`tool_guides` map is built generically (`{t.id: t.guide.guide_text() for t
in registry.all() if getattr(t, "guide", None)}`), so no server.py change
was needed at all -- `gotchas.get(tool="gotchas.write")` or
`gotchas.get(tool="gotchas.get")` now answers with the full guide exactly
the way it would for any other tool. Per-role tool counts are unchanged
(verified against the pre-existing pinned
`TestRoleToolCountsUnchanged::test_role_tool_counts_match_pre_handoff_baseline`:
99/53/29/25/16, identical before and after -- adding a `guide` field changes
no tool's existence or visibility). Added
`test_gotchas_get_and_write_carry_their_own_real_guide` (parametrised over
both tools, calls `gotchas.get` the same way a real agent would, with
`tool_guides` built from `NATIVE_TOOLS` the same way `server.py` builds it
from the registry, and checks the rendered `<guide>` element matches) and
`test_gotchas_get_and_write_descriptions_are_short` (both descriptions
under 400 chars, so neither can silently regrow the removed detail).

**Task 5 (ROADMAP.md review).** Read `Working.md`'s "START HERE" and
"Current state, 2026-09-28" sections and `handoffs/INDEX.md`'s recent rows
rather than re-deriving from scratch. Last reviewed was 2026-09-25; a full
week of landings had gone unrecorded, so this was a full pass, not
targeted. Added a new top Now item covering: five real (non-dry-run)
conductor `--once` cycles (2026-09-25 through 2026-09-28) that made real
decisions; manager work orders confirmed working (and generalised over job
type); the job-dependency-graph design plus its first two build items
(`keeps_access`/`item_present` guards, `dfqueue` project/step records); room
reservations; project MCP tools; the goal-tree design and its independent
red team (waiting on the user); "set intent, let the game execute" as the
now-governing direction; the drift-detection system
(`scripts/deploy.py`/`docs/STATE.md`/daily alert); the stream page's merged
slices; and the tool-description split (this handoff's own tasks 3-4
included). Marked the prior 2026-09-25 top item superseded (same convention
every earlier pass uses: move it down, never delete, note what moved). In
the Next bucket, marked "DF wiki lookup" done (superseded by the full
offline wiki mirror, live since 2026-09-24/25) while keeping its still-open
`ask`/`answer` sub-item visible. Keyword-scanned the rest of Next/Later
(wiki, consultant, conductor, manager, reservation, project, goal tree,
tool description, drift, stream page, district, zoning) and found nothing
else quietly finished; that is a search, not a line-by-line read, same
caveat every prior pass states about itself. Bumped "Last reviewed" with
today's date and both suite counts.

**Tests.** `tests/test_doc_facts.py`, `doctrine/tests/test_wiki_check.py`,
`dfmcp/tests/test_gotchas_tools.py` individually: 78 passed. Full ambient
suite (`python -m pytest`, `lupa` already importable without any
`PYTHONPATH` change needed on this machine): **2496 passed, 3 skipped, zero
failures** (grew from the pre-existing 2492/3 baseline by the 4 new tests
added across tasks 1 and 4). `dfmcp/tests` in a freshly built
`.venv-dfmcp` (`python -m venv --system-site-packages .venv-dfmcp`, pinned
`mcp==2.2.0` via `dfmcp/requirements.txt`, per `docs/TRAPS.md`): **768
passed, zero failures** (grew from 764 by the same 2 new gotchas tests).

**Left open, flagged for the orchestrator rather than silently decided:**
- This worktree's `.venv-dfmcp` is new and local to the worktree
  (gitignored, not committed); whoever next needs `.venv-dfmcp` in the main
  checkout or another worktree will need to build it the same way (two
  commands, see above) since venvs are never shared across worktrees.
- Task 4's guide prose and task 3's wording fixes are mine to have drafted;
  neither carries the "least sure" flag the tool-descriptions-split stream
  used for its own harder calls, but a second read of `_GET_GUIDE`/
  `_WRITE_GUIDE`'s wording against `gotchas_store.py`'s real validation
  rules (title shape, duplicate/size limits, per-run cap) would be cheap
  insurance before calling them final.
- Flipped this handoff's own `handoffs/INDEX.md` row to done (below).
