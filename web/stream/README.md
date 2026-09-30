# The stream page (slice S0: local only)

Design: `research/2026-10-01-stream-page-design.md`. This directory is the
whole "everything that can be built and seen locally with no live access"
slice (design section 8, `handoffs/2026-10-01-stream-page-s0.md`). Plain
HTML, CSS and JavaScript, no build step, no framework, no external
requests. `dfqueue/feed.py` is the data layer this page reads; read that
module's docstring and its `GAPS` list before trusting any field the page
does not show — most of what design sections 3.3 and 6 describe (a real
`seq` column, `run_id`, step labels, the season goal, hold codes, the
"right now" line's real source) is not built yet, by this slice's own
scope, and the page says so in the small note at the bottom of the layout
rather than pretending otherwise.

## Open it locally

1. Export some real past queue data into this directory's `data/` folder:

   ```
   python scripts/export_stream_feed.py \
       --records evals/live/2026-09-15-overseer-first-ruling/queue-export/records.jsonl \
       --out-dir web/stream/data
   ```

   Any `queue-export/records.jsonl` under `evals/live/` works (there are
   currently two: `2026-09-15-architect-third-charter` and
   `2026-09-15-overseer-first-ruling`). Or point `--db` at a real
   `dfqueue/<fort>.sqlite3` file if you have one locally — the script opens
   it strictly read-only and never migrates or creates it.

2. Serve this directory over HTTP (opening `index.html` directly as a
   `file://` URL will fail: browsers refuse `fetch()` of local JSON from a
   `file://` page). From `web/stream/`:

   ```
   python -m http.server 8934
   ```

3. Open <http://127.0.0.1:8934/index.html> for the public page, or
   <http://127.0.0.1:8934/operator.html> for the operator page (which reads
   `data/operator/` instead and has a "Showing: Operator / Public preview"
   toggle — design section 5's move of the mockup's Public/Operator switch
   off the public page entirely).

Re-run the export script and refresh the page to see a different export;
the page polls its own `head.json` every 5 seconds while the tab is
visible, so it also picks up a re-export live without a manual refresh.

## What is real here and what is a placeholder

- **Real**: the item stream (proposals, rulings, executed steps, asks,
  answers, passes, escalations, amends, abandons — everything already in
  the queue schema), the public-text allowlist per kind, the withhold net
  for URL/address/path/token-shaped text, reply quotes and thread
  resolution, the project-to-thread map, verdict badges, segmenting into
  200-item immutable files, and the read-only export from a real
  `records.jsonl`.
- **Placeholder**: the video frame (design's live view is not embedded —
  no relay, no noVNC locally), the status strip and "right now" line
  (`feed.status` does not exist yet — design section 3.1), the season goal
  card (no goal exists), step labels and per-step progress on the Projects
  tab (design section 3.3 item 6, slice S4), the Season/chronicle tab
  (slice S7), and history scrolling past the single open segment (design
  section 4.4's segment-fetching logic is not implemented client-side yet —
  a real fort's queue is far larger than the two-record test exports this
  slice ships with, so this was not yet exercised against real segment
  files).

## Known gaps in this slice, beyond `dfqueue/feed.py`'s own `GAPS` list

- No JS test suite for `app.js` — `dfqueue/tests/test_feed.py` covers the
  data layer thoroughly (that is where the safety-relevant logic lives:
  the allowlist and the withhold net); the rendering layer is exercised
  manually per the steps above, not automated. A future slice could add a
  headless-browser smoke test if that seems worth the dependency.
- No closed-segment or season-file fetching client-side (see above).
- No focus-trapping project drawer — the Projects tab lists cards but does
  not open the mockup's full drawer with a step timeline and its own
  conversation thread; that needs step labels and target counts
  (`dfqueue.store.project_status`, not available to a read-only-records
  reader — see `dfqueue/feed.py`'s own `GAPS`).
- No dark/light theme switch (the design says the video frame stays dark
  regardless; the chrome could follow `prefers-color-scheme`, not wired up
  here).
- Accessibility: role names are always shown as text (never colour alone),
  and new items announce politely via `aria-live="polite"` on the messages
  list, but this has not been tested with a real screen reader.
