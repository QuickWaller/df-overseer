# Handoff: public agent transcripts (collapsed tab) and full proposal details

Date: 2026-10-07. **Executor, Sonnet, worktree. Offline; no deploys.**
First: `git merge --ff-only main`.

## Why

User's call 2026-10-07: show each agent run's full transcript on the Board,
on a separate tab, collapsed by default like the tools-used view; and show
the full proposal (not just its one-line `public_rationale`), collapsed in
its thread. Both pass the same public safety filter as everything else
(`dfqueue/feed.py` `_UNSAFE_PATTERNS`, `_safe_public_text`); never route
around a refusal: a withheld span is shown as withheld.

Known gap (`research/2026-10-07-cross-run-cache.md`): no per-turn transcript
is stored today. openclaw's state DBs hold no session transcripts; the
conductor archives only `run-<role>.json` envelopes
(`conductor/archive.py`, `conductor/runner.py`).

## Scope

1. **Capture.** Find where the full turn sequence is available at run time
   (openclaw's JSON output the runner parses, its session files, or a
   per-run flag that keeps them; read `conductor/runner.py` and what openclaw
   returns). Archive per run: each round's tool calls (name, arguments),
   tool results (truncated to a cap, policy data), reasoning text if the
   provider returns it, and per-round usage (this also closes the cache
   study's "no per-turn data" gap). Size caps and retention as data. If
   capture needs an openclaw setting you cannot confirm offline, implement
   against the documented shape, mark it unverified, and list the live
   check.
2. **Publish.** The publisher (`dfqueue/live.py` or wherever run data
   reaches the site) carries each run's transcript to the Board through the
   safety filter, public and operator variants as for other text.
3. **Board.** `web/stream/app.js`/`style.css`: a Transcript tab per run (next
   to the Turns tab), each run collapsed by default, tool calls collapsed
   inside it like the tools-used view; and in each proposal's thread a
   collapsed "Full proposal" block: summary, rationale, preconditions,
   prediction, the step (tool and arguments, coordinate-free as filed),
   cited facts. Markdown rendering via the existing safe renderer (DOM only,
   never innerHTML). Bump the asset version. Follow
   `memory`-recorded UI preferences: one screen, inner panes scroll, tabs
   over long lists, dark only.
4. Tests: capture shape, caps, filter applied to every new public field, a
   withheld span shown as withheld, Board rendering tests if the repo has
   them.

## Rules

Touched surfaces: `conductor/runner.py`, `conductor/archive.py`,
`conductor/policy.yaml` only for transcript caps (another stream edits
policy.yaml: add a separate top-level block only), `dfqueue/feed.py`,
`dfqueue/live.py`, `web/stream/`, tests, this handoff. Public repo: no
hostnames, IPs or tokens; transcripts must never carry them (the filter
plus a test). No em dashes. No attribution lines. Commit after each
milestone. Do not write Working.md, DECISIONS.md, memory or INDEX.md. Full
ambient `python -m pytest` (lupa on PYTHONPATH) and `dfmcp/tests` in
`.venv-dfmcp` green.

## Result (executor, 2026-10-07)

Built offline, not deployed. Branch `worktree-agent-a736de380a947392f`.

**Capture.** openclaw's `--state-dir` retention already exists for thinking (`conductor/runner.py`, `thinking_state_root`), and its `transcript_events` rows hold the whole message sequence, so no new openclaw setting is needed: `read_transcript` reads the same retained dir `read_thinking` does. `build_transcript` makes `{rounds: [{n, reasoning, text, calls: [{id, name, args, result, error}], usage}], omitted_rounds}`; `RunResult.transcript` carries it, so `run-<role>.json` in the cycle archive has it (and per-round usage, which closes the cache study's per-turn gap). Caps are data in the new top-level `transcript:` block of `conductor/policy.yaml` (read by the runner directly; `conductor/policy.py` is untouched): max_rounds 60, call args 600 chars, result 800, round text 2000, total 60000 JSON chars (whole later rounds dropped and counted, never cut mid-JSON).

**Transport (surfaces beyond the handoff's list, necessary).** The publisher on VM 103 only sees the run store, so the transcript rides the existing path: `conductor/cycle.py` adds a compact-JSON `transcript` to the `conductor.report` end call, `dfmcp/conductor_tools.py` accepts it, `dfqueue/runs.py` stores it in a new `transcript` column (auto-migrated like `thinking`; an over-70000-char one is stored NULL, never truncated).

**Publish.** `dfqueue/live.py`: `PUBLIC_TRANSCRIPTS` switch, newest `TRANSCRIPT_RUNS_PUBLIC` (8) runs only, `TRANSCRIPT_PUBLIC_MAX_CHARS` (40000). Reasoning and text are filtered paragraph by paragraph, tool results line by line (an unsafe span becomes the withheld marker), call arguments as one string (`args_withheld: true`), a tool name that is not a plain identifier becomes `tool` with `name_withheld`, usage keeps numbers only. Operator `runs.json` carries the raw transcript. `dfqueue/feed.py`: `proposal_detail` adds a `detail` block (summary, rationale, preconditions, prediction, step tool/args/label, cited facts) to every proposal item, each field through `find_unsafe_pattern`, an unsafe one `null` and named in `withheld`; the operator item has it unfiltered. `detail` added to `PUBLIC_ITEM_FIELDS`. The old test asserting a proposal's rationale never appears publicly was rewritten to the new rule (only inside the filtered `detail`).

**Board.** `web/stream/app.js`: `detailRows`/`fullProposalEl` (collapsed "Full proposal" in a proposal's receipt and post) and `transcriptEl` plus the agent panel's new Transcript tab (next to Turns): each run collapsed, each round's reasoning and every tool call collapsed again, inner pane scrolls (60vh), withheld spans shown as "(withheld)", Markdown through the existing DOM renderer, text only via `el(..., {text})`. `style.css` additions; assets bumped to `?v=63` in `index.html` and `operator.html`.

**Tests.** `conductor/tests/test_transcript.py`, additions to `test_report.py`, `dfmcp/tests/test_conductor_tools.py`, `dfqueue/tests/test_feed.py`, `tests/test_stream_publisher_runs.py`, new `dfqueue/tests/test_site_js_transcripts.py` (node). Full ambient suite with lupa: 3335 passed, 3 skipped, 0 failed after fixing a private-IP literal my tests had introduced (`tests/test_no_leaked_addresses.py` caught it; test inputs now use 203.0.113.x). `dfmcp/tests` in `.venv-dfmcp`: 937 passed.

**Deploy targets, order.** (1) `vm103-dfmcp` (`conductor_tools.py`, `runs.py`; the column migrates on first connect) before (2) `vm106-conductor` (runner, cycle, policy.yaml: otherwise `conductor.report` would reject the unknown `transcript` argument), (3) `vm103-stream-publisher` (`live.py`, `feed.py`), (4) relay web (`web/stream/`). No config change on VM 106 beyond the existing `CONDUCTOR_THINKING_STATE_DIR` that thinking already needs; the transcript is captured only when that is set.

**Live checks needed.** UNVERIFIED: the tool-call block and `toolResult` message shapes inside `transcript_events` (only thinking and text blocks are proven, `handoffs/2026-10-05-agent-thinking.md`). `build_transcript` reads `toolCall`/`tool_use`/`toolUse` blocks (`arguments`/`input`/`args`) and `toolResult`/`tool` messages matched by `toolCallId`; after one real run, open `run-<role>.json` and confirm `rounds[].calls` is non-empty with results and that `usage` per round is present (key names `input/output/cacheRead/cacheWrite/reasoningTokens/total|totalTokens`). If a shape differs, only `build_transcript` needs adjusting. Then check the Transcript tab and a proposal's Full proposal in a headless browser.

**Design questions.** (a) `runs.json` is polled; carrying 8 transcripts of up to 40 KB makes it up to ~320 KB. A separate lazily fetched per-run file would be cleaner if that is too heavy. (b) Tool results are whole model-adjacent text from game tools; line-level filtering may withhold many lines (24+ char unbroken runs trip the token pattern); judge after a real run whether the filter is too coarse. (c) `scripts/preview_stream_live.py` does not yet build a demo transcript or detail.
