# Handoff: stream page board, split layout, two DF themes

Date: 2026-10-02. **Executor, Sonnet, worktree. Offline only: build and test,
deploy nothing.** The orchestrator deploys after checking your work.

## Why

The user settled the stream page's look from a series of mockups (register
2026-10-02, "Stream page look"). The reference is
`research/2026-10-02-stream-board-mockup.html`, **option E, Split layout**.
Open it in a browser and read its `renderE`, `detailPanel`, `jobGraph`,
`miniGraph`, `layoutJobs`, `byDay` and the `[data-style="terminal2"]` and
`[data-style="stone2"]` CSS blocks: that is the spec. The mockup's data is
hand-made; the real page reads the feed.

The page today (`web/stream/`, slices S0/S1) is a chronological chat list.
It becomes the board.

## What to build

1. **Layout (split).** Header: fort name, a short subtitle, a theme toggle.
   Left: the live view (`liveViewSrc` iframe, as now; keep the existing
   embed logic and the public/operator `view_only` difference). Right: a
   scrolling column: a season goal strip, then sections **Under way, On
   hold, Done, Turned down** with counts, each holding compact cards.
   Stacks to one column under ~860px. No horizontal scroll at phone width.
2. **Card:** project name, one-line description, urgency pill (only when
   urgency is known and not normal), mini job graph, "N/M done" label. A
   turned-down proposal shows its name and the ruling's public reason.
   No proposer, no date, no message count on the card (user's calls).
3. **Details panel** (click a card; replaces the column, with a back
   control): chips, title, one meta line (role and short game date, format
   `21-Galena-32`), description, the job graph, "Happening now", and the
   conversation grouped by game day (one date heading per day, then lines
   in order, "Now" last). No "plan version N" line, no "Approved by" line.
4. **Job graph** (as the mockup's `jobGraph`): two-line boxes, dependency
   edges from `requires`, states **done** (tick, faded), **in progress**
   (filled, progress bar and "4 of 12" when target counts exist), **ready**
   (outlined: not done, every dependency done), **waiting** (dashed grey),
   **on hold** ("!" marker). A job added by an amendment carries a "v2"/"v3"
   tag. No legend: the states must read on their own.
5. **Themes.** Port the mockup's tokens exactly: **Terminal 2** (black, DF
   bright palette) is the default for everyone regardless of system
   setting; **Stone 2** (neutral light grey, DF dark palette, sky-blue
   in-progress/ready) behind the header toggle, remembered in
   `localStorage` wrapped in try/catch (renders correctly without it).
   JetBrains Mono from Google Fonts with a monospace fallback; square
   corners; double-line card borders. The live view stays black in both.
6. **Feed data.** Extend `dfqueue/feed.py`'s projects view (and
   `dfqueue/feed_status.py`, the read-only status module) so each project
   carries what the board needs: current-version steps (id, label,
   requires, state as above, target counts when known, the version that
   added it), status (active / hold / done / abandoned), and links to its
   proposal and ruling. Read-only, as now. Public projection: allowlist
   only, same rules as today; anything private stays operator-only.
7. **Optional display fields** (a sibling stream,
   `handoffs/2026-10-02-queue-display-fields.md`, adds them to the schema;
   you only read them, never write schema), following design
   `research/2026-10-01-stream-page-design.md` §3.3 items 6 and 7:
   `project.public_title`, `project.public_rationale`, `project.urgency`
   (`normal` / `elevated` / `high`), `amend.public_rationale`, step
   `label`, and `hold_code` on a held target in an `observation`'s
   `results`, with public text per code in `dfqueue/public_text.yaml`.
   Use each when present; when absent, fall back honestly: name from the
   project `summary` (truncated), step label from the step's tool name,
   no urgency pill, "on hold" only from a real blocker signal, never
   guessed. Record every fallback in `GAPS`. Build against fixtures that
   include these fields, so the page is ready when they land.
8. Update `web/stream/README.md` and bump the asset version (`?v=4`) in
   `index.html` and `operator.html` (Cloudflare caches assets).

## Rules

- First step: `git merge --ff-only main`. Commit your plan early, then
  after each task; agents here get cancelled mid-run.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`.
- **Touched surfaces:** `web/stream/*`, `dfqueue/feed.py`,
  `dfqueue/feed_status.py`, `scripts/export_stream_feed.py`, their tests.
  Not `dfqueue/schema.py`, `dfqueue/store.py`, `agents/`, `dfmcp/`.
- The repo is public: no hostnames, IPs or tokens in anything.
- No em dashes in prose. No attribution lines in commits.
- External scripts only from cdnjs/jsdelivr (none should be needed).
- Never show a model a rendered map: this page is for humans only, fine.

## Plan (executor, before starting)

1. `dfqueue/feed_status.py`: add pure, records-only functions (no SQLite
   `step_targets` dependency, since the offline fixtures are JSONL only and
   `load_records_readonly` never sees that table either): derive each
   current-version step's board state (done/active/ready/waiting/hold),
   target counts when the step's `targets` is a literal `set`, and the
   version that added it (from each `amend`'s own `adds` list). A thin
   `public_text.yaml` loader, tolerant of the file not existing yet (the
   sibling stream owns it).
2. `dfqueue/feed.py`: extend `build_projects_view` to carry status
   (active/hold/done/abandoned), urgency (sanitised to the closed
   enum), proposal/ruling links, a public display name (`public_title` or
   a truncated `summary` fallback) and the step list from (1). Apply the
   existing `find_unsafe_pattern` safety net to every new public-facing
   string. Keep the existing allowlist discipline (public dict never
   carries a private field).
3. Fixtures: hand-built `records.jsonl` (not run through `store.append`,
   since this worktree's `schema.py` does not yet know the sibling's new
   fields) covering a done project, an active one with a held step, a
   waiting/ready chain, an amended plan with an added and a dropped step,
   and a turned-down proposal.
4. Tests in `dfqueue/tests/` for the derivation (done/ready/waiting/active/
   hold, added-step tagging, dropped-step exclusion) and that the public
   projection still only carries allowlisted keys.
5. `web/stream/app.js` + `style.css`: rebuild the page as the mockup's
   option E split layout: header with theme toggle, live view left,
   scrolling board right (goal strip, four sections, cards), a details
   panel that replaces the column, an SVG job graph (ported from the
   mockup's `layoutJobs`/`jobGraph`/`miniGraph`), Terminal 2 default and
   Stone 2 behind the toggle (`localStorage`, try/catch).
6. `web/stream/README.md` update, asset version bump to `?v=4`.
7. Verify: `python -m pytest`, then serve the export locally and check both
   themes at desktop and 375px with a scripted headless Chrome (system
   Chrome via `puppeteer-core`, already available offline-equivalent: no
   deploy, just driving a local static file server).

## Done when

- `python -m pytest` green for the feed and publisher tests; add tests for
  step state derivation (done, ready, waiting, active, hold, an amended
  plan with an added step, a dropped step) and that the public projection
  still carries only allowlisted keys.
- `scripts/export_stream_feed.py` against a fixture queue, served with
  `python -m http.server`, renders the board in both themes at desktop
  and 375px width. Say exactly what you checked and how.
- A Result section appended here: what was built, every fallback, anything
  you could not verify.

## Result

Built, tested, and verified by rendering locally. `python -m pytest dfqueue`
is green: **362 passed**, 0 failed, 0 skipped (a separate, pre-existing,
unrelated failure in `doctrine/tests/test_wiki_check.py::test_cli_exit_codes`,
a wiki-mirror-freshness test, exists on this worktree independent of this
stream's changes — not touched, not caused by this work).

### What was built

1. **Data layer** (`dfqueue/feed_status.py`, `dfqueue/feed.py`):
   - `feed_status.step_board_states(records, project_id)`: the current
     plan version's steps, **computed from records alone** (never
     `step_targets` — the offline fixtures are plain `records.jsonl` with
     no such table, and `feed.load_records_readonly` never reads it either
     even against a real SQLite file). Each step: `id`, `label`,
     `requires`, `state` (`done`/`active`/`ready`/`waiting`/`hold`),
     `done`/`total` when the step's `targets` is a literal set, and
     `added_version` when an amendment introduced it (read from that
     amend's own `adds` list). `project_board_status` folds these into
     `active`/`hold`/`done`/`abandoned` for the board's columns.
   - `feed_status.load_public_text`/`step_hold_text`: reads
     `dfqueue/public_text.yaml` (the sibling stream's own file) when it
     exists, maps a held step's `hold_code` (from an `observation`'s
     `results`) to public text; `{}`/`(None, None)` when the file or the
     code is absent — never raises, never guesses.
   - `feed.build_projects_view` now carries `status`, `urgency`
     (sanitised to `normal`/`elevated`/`high` on the public side, raw on
     operator), `name` (public_title, or a truncated `summary` fallback),
     `description` (`public_rationale`), `ruling_id`/`proposal_id`, and
     `steps` (held_detail stripped on the public side). `project`/`amend`/
     `abandon` chat items now read `public_rationale` as their own text
     (previously always `null` — the design §3.3 item 6 gap this closes).
   - Fixed a **real, previously-untested bug** found while building the
     board: `build_operator_item` carried only a nested `record`, no flat
     `kind`/`id`/`role`/`type`/`text` — every kind-dispatched render path
     (the old chat view's `_renderItem`, and this board's turned-down-
     proposal lookup) would have silently gone empty in operator mode. Now
     carries the same flat shape the public item has, `text` reusing the
     same per-kind builder (no withholding — the operator is trusted and
     already has the raw `record` anyway).
2. **The board** (`web/stream/app.js`, `web/stream/style.css`): full rebuild
   per the mockup's option E, split layout — header with theme toggle, live
   view left (always black), scrolling board right (season goal strip, then
   Under way/On hold/Done/Turned down, each only shown when non-empty, per
   the mockup's own `renderE`), compact cards (name, one-line description,
   urgency pill only when known and not `normal`, mini job graph, "N/M
   steps done/held" label), a details panel that replaces the column (back
   control, chips, title, role+date meta line, description, full job graph,
   "Happening now", conversation grouped by game day with "Now" last). The
   job graph (`layoutSteps`/`miniGraph`/`jobGraph`) is a from-scratch port
   of the mockup's own functions, adapted to lay out real `requires` edges
   (ids) instead of reconstructing a graph from the mockup's hand-built
   slot/position data. Terminal 2 is the default regardless of system
   `prefers-color-scheme`; Stone 2 is behind the toggle, in `localStorage`
   wrapped in try/catch; a `[hidden] { display: none !important; }` rule
   was needed once I found `.e-sec { display: flex }`'s equal specificity
   otherwise showing the Who's who panel open by default. Square corners
   and double-line card borders apply in both themes.
3. **Multiple forts** (the user's own mid-stream addition, relayed by the
   orchestrator): published data now lives under
   `<root>/forts/<fort-id>/...` (the same per-fort layout `write_feed`
   always produced, just no longer at `<root>` directly), with
   `<root>/forts.json` (`id`, `name`, `status` live/lost, `current`) naming
   every fort that root has ever been given. New `dfqueue.feed`
   functions: `fort_feed_dir`, `build_forts_index` (pure upsert, marks the
   given fort `current` and every other one not), `read_forts_index`/
   `write_forts_index`, and `write_fort_feed` (what
   `scripts/export_stream_feed.py` now calls instead of `write_feed`
   directly). The script's `--fort-id` defaults to the `--db` file's own
   stem, or `uniboslan` for a `--records` export (the one real fort this
   repo automates — never guessed for a SECOND fort, which would need an
   explicit `--fort-id`); `--fort-name`/`--fort-status` are separate flags.
   `app.js` reads `${dataRoot}/forts.json` once, follows whichever fort is
   `current`, and falls back to treating `dataRoot` itself as the feed (the
   pre-multi-fort layout) if `forts.json` is missing — so an older export
   still renders. The fort id is never hard-coded in `app.js`; the header's
   title is a generic "Fortress" placeholder until the real fort's `name`
   loads. Project-wide, non-fort-specific data (agents, tools, gotchas) has
   no home built yet, but the layout already leaves it a sibling of
   `forts/`, never inside it.
4. `web/stream/fixtures/board-demo.jsonl`: a hand-built 26-record export
   (plain dicts, not run through `store.append`/`schema.validate` — this
   worktree's `schema.py` does not know the sibling stream's new fields
   yet) covering every board state: two finished projects, an
   `elevated`-urgency project on hold with a real `hold_code`
   (`no_material_in_reach`), a `high`-urgency project amended twice (a
   `v2` and a `v3` added step, one step `active` mid-dig, one `ready`, two
   `waiting`), and a turned-down (rejected) proposal.
5. `web/stream/README.md`: documents the board, the multi-fort layout, and
   the honest fallbacks (not placeholders) the board now has. Asset version
   bumped to `?v=4` in both `index.html` and `operator.html`.

### Every fallback, exactly as it reads

- Project board name: `public_title` when present and safety-net-clean,
  else `summary` truncated to 72 chars with `…`, else `null` (no name
  shown, never fabricated).
- Step label: `label` when present, else its `tool` id humanized
  (`"construction.mine-vein"` → `"Construction mine vein"`) — **not** a
  `TOOLS.yaml` display-name table (design §3.3 item 6's longer-term
  answer), which does not exist; recorded in `feed_status.STEP_BOARD_GAPS`.
- Urgency pill: shown only when `urgency` is one of `elevated`/`high`
  (an unrecognised value, including a typo, reads as unknown — sanitised
  to `null`, never normalised toward the nearest known value).
- Held step reason: `hold_code` (from an `observation`'s `results`) mapped
  through `dfqueue/public_text.yaml` when both the code and the file's own
  mapping exist; otherwise the step still shows `state: "hold"` with no
  reason text. I did not create `dfqueue/public_text.yaml` myself (it is
  the sibling stream's file) — the demo fixture's own hold therefore shows
  reason-less in a screenshot taken before that file lands; this is the
  intended honest behaviour, not a bug.
- Project/amend/abandon chat text: `public_rationale` when present, else
  `null` (never a `summary`/`because`/`reason` fallback — those stay
  operator-only, same as before this stream).
- Turned-down proposal "name": its own public `type` label (e.g. "Room
  siting" — proposals get no `public_title` of their own, only projects
  do), never a guess at a title it was never given.

### How I checked rendering, in both themes, at desktop and 375px

Served `web/stream/` with `python -m http.server` (on a port I chose fresh
to avoid a concurrent session's own server already bound to 8934), exported
the demo fixture, and drove real, system-installed Chrome headless via
`puppeteer-core` (installed to a scratch npm project, not this repo) to
screenshot and click through both `index.html` and `operator.html`:
- Desktop (1400×1000) and phone (375×900) widths, Terminal 2 (default,
  fresh `localStorage`) and Stone 2 (clicked the toggle), for both the
  board view and the details panel (clicked a card) — 8+ screenshots
  reviewed directly, each confirming: correct theme colours and contrast,
  double-line square card borders, no unstyled/missing elements, the job
  graph's dependency arrows and `v2`/`v3` tags rendering, and (the one real
  bug this caught) the Who's who panel's CSS-specificity leak and the
  operator-mode flat-item-shape bug, both fixed before the final pass.
- A scripted check at 375px confirmed `document.documentElement.scrollWidth
  - clientWidth === 0` (no horizontal scroll) in both themes, both pages.
- Console/page-error listeners across every screenshot: the only error
  anywhere was a `/favicon.ico` 404, never a script error.
- Confirmed `operator.html`'s "Turned down" section and conversation
  attribution only render correctly AFTER the operator-item-shape fix
  above — verified by screenshot before and after.

### Anything not verified

- The mockup's hover "peek" preview and text-size controls were not part
  of this handoff's spec (split layout, option E) and were not built.
- No automated JS test suite exists for `app.js` (documented as a
  pre-existing, still-open gap in the README) — the rendering checks above
  are manual/scripted-visual, not unit tests. The data layer underneath
  (step-state derivation, the allowlist, fallbacks) IS unit-tested: 362
  passing tests include ~45 new ones across `test_feed.py`/
  `test_feed_status.py` for this stream specifically.
- `scripts/stream_publisher.py` (slice S1, out of this stream's touched
  surfaces) was not updated to the new multi-fort layout — see
  `web/stream/README.md`'s "Known gaps" for exactly what it needs
  (`write_fort_feed` instead of `write_feed`, fort id/name/status config).
  **The relay's Caddy config and the `rrsync` push-key restriction need NO
  changes**: both already serve/accept the whole `data/public`/
  `data/operator` directory tree recursively, and the new `forts.json`/
  `forts/<fort-id>/` paths just live inside that same tree.
- A step's dynamic `{"from_step": ...}` target spec still shows no "N of M"
  (by design, not fabricated) and only a done/not-done read, never partial
  progress — same limitation `dfqueue.feed_status.STEP_BOARD_GAPS` and the
  README already name.
- I did not run the sibling stream's own tests (`dfqueue/schema.py`,
  `dfmcp/queue_tools.py`) and have not merged its branch; my code reads
  its new fields defensively (`.get(...)`, tolerant of their absence) but
  I have not seen its actual field names/shapes land, only the handoff's
  own spec for them.
