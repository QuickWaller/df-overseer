# Handoff: load transcripts on demand

Date: 2026-10-07. **Executor, Sonnet, worktree. Offline; no deploys.**
First: `git merge --ff-only main`.

## Why

User's call 2026-10-07. `handoffs/2026-10-07-transcripts-and-full-proposals.md`
ships the newest 8 runs' transcripts inside the polled `runs.json` (up to
about 320 KB per poll). Load each transcript only when its run is expanded.

## Scope

- Publisher (`dfqueue/live.py`): write each run's filtered transcript to its
  own file (public and operator variants, as today), named by run id;
  `runs.json` carries only `transcript: {available, size, withheld_count}`
  per run. Keep transcripts for more than the newest 8 if size allows
  (retention as data), and prune old files.
- Relay: the new files are served next to `runs.json` (check how the
  publisher's outputs reach the relay and that the new path is covered by
  both relay-web targets and the caching headers).
- Board (`web/stream/app.js`): fetch the transcript when a run is first
  expanded, show a loading state, cache it for the session, handle a
  missing file. Bump the asset version.
- `scripts/preview_stream_live.py`: a demo transcript and a demo full
  proposal so the Board can be checked locally.
- Tests: runs.json no longer carries transcript bodies; file written and
  filtered; pruning; Board fetch on expand (node tests if present).

## Rules

Touched surfaces: `dfqueue/live.py`, publisher and relay deploy config if
the new path needs it, `web/stream/`, `scripts/preview_stream_live.py`,
tests, this handoff. Public repo: no hostnames, IPs or tokens. No em
dashes. No attribution lines. Commit after each milestone. Do not write
Working.md, DECISIONS.md, memory or INDEX.md. Full ambient `python -m
pytest` (lupa on PYTHONPATH) and `dfmcp/tests` in `.venv-dfmcp` green.

## Result

**Publisher and `dfqueue/live.py`.** `runs.json` no longer carries transcript
bodies. Each run with one has `transcript: {available, size, withheld_count}`
(`size` is the file's bytes, `withheld_count` the "(withheld)" spans in the
public body, 0 for operator). Bodies go to
`forts/<fort_id>/transcripts/<run_id>.json`, one file per run, public (filtered
by `_public_transcript`, ok runs only, 40000-char cap per run) and operator
(raw) variants under their own staging roots, via `live.build_transcripts`
and `stream_publisher._write_transcripts`. Retention is data:
`live.TRANSCRIPT_RUNS_KEPT = 24` (was 8 inline; about 1 MB worst case, none of
it polled). The old `TRANSCRIPT_RUNS_PUBLIC` constant is gone. A run id that is
not a plain file-name token gets no file. Pruning: staging files for runs no
longer kept are unlinked each cycle; because rsync without `--delete` never
removes a remote file, the push also re-pushes just the transcripts directory
with `--delete` (to `<relay path>/forts/<fort_id>/transcripts`) when the cursor
shows a previously pushed file is no longer kept. rrsync allows `--delete`
(the public-off push already uses it). Cursor gains `public_transcripts` and
`operator_transcripts`. Public off clears the staged public transcripts.

**Relay: no config change needed.** Both Caddy sites serve
`/data/public/*` (and operator `/data/operator/*`) with `file_server` and
`Cache-Control: no-store` over the whole tree, so `forts/<id>/transcripts/*.json`
is covered with the right headers; the publisher's rsync already pushes the
whole staging root (the key is restricted to the parent directory). Deploy
targets: publisher (VM 103, `scripts/stream_publisher.py`, `dfqueue/live.py`)
and the two web roots (`web/stream/`: `app.js`, `index.html`, `operator.html`;
assets now `?v=64`). Deploy order: web roots first or together; an old Board
against a new publisher shows an empty Transcript tab, a new Board against an
old publisher shows the same, so neither order breaks the page.

**Board.** `SitePage._loadTranscript` fetches the file on first expand and
caches it in `this.transcripts` for the session (a failure is not cached, so
reopening retries); `_openTranscript` shows "Loading transcript...", then the
transcript, or "This transcript is no longer available." for a missing file.
`_transcriptTabEl` lists runs from `runs.json` metadata only (label: reason,
date, size in KB, withheld count) and never fetches until a row is opened.

**Preview.** `scripts/preview_stream_live.py` writes demo transcript files
(two spans trip the safety check on purpose; the last demo run has none, to
show the missing state) and adds preconditions, a step and cited facts to one
demo proposal in the temp copy of the records, so "Full proposal" shows every
row including a withheld one.

**Tests.** `tests/test_stream_publisher_runs.py` (metadata-only runs.json, file
bodies filtered and operator-raw, retention, per-run cap, pruning locally and on
the relay, no repeat prune), `dfqueue/tests/test_site_js_transcripts.py` (no
fetch before open, loading then body then cached with one fetch, missing file
note and retry), `replaceChildren` added to the node stub. Ambient
`python -m pytest`: 3341 passed, 3 skipped (this run included dfmcp/tests).
`dfmcp/tests` in `.venv-dfmcp`: 937 passed.

**Observation, not changed.** The public "Full proposal" shows the record's
`rationale` (model text, safety-checked), while the public post text uses
`public_rationale`. The demo fixture marks its `rationale` "never public", so
the two may be meant to differ; worth a look by the owner of that stream.
