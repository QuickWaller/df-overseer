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
