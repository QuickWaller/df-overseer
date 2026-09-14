# Stream: architect charter run #2, now that it can see underground

**Written** 2026-09-14. **Status:** dispatched. **User go-ahead:** "2 then 1".
Item 1 was "re-run the architect now that it can search underground and
compare with the first run".

## Why

Run #1 (`evals/live/2026-09-14-architect-first-charter/`) produced a sound
surface proposal. Its underground reasoning was void, though: `diggable.find`
then took an absolute z, so the model's z 0 to -4 searched off-map and got a
silent `[]`. Two changes have since been deployed and live-verified on
VM 103 (`handoffs/2026-09-14-relative-level-args.md`):

- `openarea.find`, `diggable.find` and `chokepoints.find` take an optional
  **`level` relative to the landmark**, with an argument description. Level -1
  near Embark Site or Wagon returns 5 diggable candidates.
- A script's `{"error": ...}` output now comes back **`isError: true`**.

This run asks the same question with the same model and charter, so the
difference between the two runs is the tool interface.

## Do

1. Reuse run #1's setup exactly. Its handoff doc
   (`handoffs/2026-09-14-openclaw-architect-charter-run.md`) has the pinned
   config overlay, the `SOUL.md` bootstrap mechanism and the docker
   invocation; the committed copies are `charter-bootstrap.md` and
   `pinned-config.json` in run #1's `evals/live/` directory, with the URL
   redacted. **Charter text unchanged. Model `deepseek/deepseek-v4-flash`.
   Same task prompt, verbatim** (quoted in run #1's README). Before running,
   confirm `mcp probe` or the tool list shows `level` on `diggable__find`,
   because if the ambient openclaw config cached old tool schemas this run is
   not a fair comparison.
2. Run `agent exec` once.
3. **Compare with run #1**, item by item:
   - Did it pass `level`, and which values?
   - Did any call return `isError`, and how did the model react?
   - Did it find or name the level -1 dig candidates?
   - Did the proposal change (type, target, prediction, cost)?
   - Did it deal with reachability for any dig: the stair chokepoint SE of
     the Embark Site, and the fact that level -1 is reachable?
   - The same charter checks as run #1: no raw coordinates, required fields,
     a falsifiable prediction, a named cost, only the 9 read tools.
4. Save to `evals/live/2026-09-14-architect-second-charter/`: `run.json`,
   `README.md` (what was run and the comparison table), any failed-attempt
   JSON. Scan for IPv4 addresses and token-shaped strings, include a positive
   control in that scan, and say so.

## Budget and hard lines

- **At most 3 model-backed turns, failures included.**
- Architect token only; change nothing on VM 103 (reading its journal is
  fine); no gateway, channels or compose; nothing left listening on VM 106.
- Secrets by key only, never in argv, files or the report.
- No commits. Don't edit `Working.md`, `decisions/`, `memory/`, `CLAUDE.md`,
  other handoff docs, or run #1's `evals/live/` directory. Add a Result
  section here and your row in `handoffs/INDEX.md`.
- Refusals: follow CLAUDE.md, disclose any reroute, and never route one
  through another agent.

## Report

Executor shape, plus the comparison table, turns used, cost, and anything
listening. Mark each claim as verified (with its command) or inferred.

## Result, 2026-09-14

**Status: done.** Full run artifacts, the comparison table, and everything
below are in `evals/live/2026-09-14-architect-second-charter/` (`README.md`
there has the complete write-up; this section is the summary). Used **1 of
the 3 allowed model-backed turns** — the run succeeded on its first attempt,
real cost `$0.0036646624`. Nothing left listening on VM 106 (`docker ps -a`
empty, `ss -tlnp` baseline-identical, both **verified** before and after).
Ambient `openclaw.json` confirmed byte-identical before and after (**verified**
by diffing it). VM 103 was only ever read from (its `dfmcp-server.service`
journal, read-only) plus one raw MCP `tools/list` probe call — no config,
service, or game state there was touched.

**Step 1 pre-check, verified before spending anything.** `openclaw mcp probe`
doesn't surface argument-level schema, so a raw MCP `tools/list` call was made
directly against VM 103 (architect token, $0, no model call): `diggable__find`
carries an optional `level` argument with the relative-level description
(quoted in full in the README). The interface change this run exists to test
was live and confirmed before the paid call.

**Setup**: reused run #1's `pinned-config.json` and `charter-bootstrap.md`
byte-for-byte (same model, same MCP entry, same `tools.allow` restriction,
same workspace path), delivered via the same read-only Docker volume overlay
onto `/home/node/.openclaw/openclaw.json` that run #1 used. Noted for the
record: this build's `agent exec --help` does advertise a real `--config
<path>` flag that would have made the overlay trick unnecessary — not used
this run, deliberately, to keep the two runs mechanically identical for a fair
comparison.

**The run.** One `agent exec` attempt, succeeded immediately (no `Unknown
model` preflight failure this time — the DeepSeek plugin/auth fix run #1's
Part A made lives on the same host-mounted directory this run's overlay
shares). `toolSummary`: 14 calls across exactly the 9 allowed tools, **3
failures** (`isError`, the new signal this stream exists to test) — VM 103's
access log shows all `200`s in-window, consistent with `isError` riding inside
a normal JSON-RPC response body per `0557415`, not an HTTP failure. Per-call
argument detail (which 3 calls, what `level` values) was **not recoverable**
from any available artifact — checked and ruled out: `agent exec --json`'s
`toolSummary` has no per-call log, openclaw's own session sqlite has zero rows
in every transcript-shaped table for this headless `exec` path (confirmed
live), and VM 103's access log only carries HTTP status, not JSON-RPC bodies.
Flagged as a real gap rather than guessed at; getting it would need either a
second paid run with debug logging (spending budget on verbosity rather than
the comparison) or a server-side logging deploy (out of scope this stream).

**What changed vs. run #1, the headline items** (full item-by-item table in
the README):
- **The interface fix worked.** The architect found and named real
  underground space for the first time — 5 ranked SOIL candidates one level
  below Embark Site, matching the live-verified `LEVEL` deploy check exactly
  — and engaged in real reachability reasoning (naming the single chokepoint
  stair linking the surface to the underground), which run #1 never got to
  exercise because `diggable.find` always returned `[]`.
- **The required XML proposal record was not used at all this run** — a
  real regression, unrelated to the interface change. Grepped `run.json`
  directly: zero occurrences of `<proposal`, `public_rationale`,
  `suggested_priority`, `check_after_ticks`, or `preconditions`. The model
  wrote two markdown sections ("## Survey", "## Proposal") with bolded prose
  fields instead of the machine-parseable record the charter requires. No
  falsifiable `signal`/`op`/`value` prediction, no named cost.
- **A likely charter-scope violation.** The one proposal — a door or trap at
  the fort's single confirmed vertical chokepoint — reads as a defensibility
  measure. `role.md`'s "Does NOT own" section says exactly this ("Anything
  military... if your proposal would affect defensibility, say so in the
  rationale and let the Overseer weigh it; do not propose the military half
  yourself") should be flagged for the Overseer, not proposed outright. The
  model presented it as its one proposal with no such flag. Not certain (a
  door could be read as pure traffic control rather than a military
  measure), but the model's own rationale — "the single decisive control
  point available" — reads as a defensibility argument. Flagged, not
  corrected.
- **Still clean on the two hard commitments both runs share**: zero raw
  coordinates (grepped directly, zero matches — and this run's own text is
  stricter than run #1's, which stated bare `z=0`/`z=-1` values; this run's
  text never states a bare `level=N` at all), and zero tool calls outside the
  9 allowed (`toolSummary.tools` lists exactly the same 9 names).

**Files scanned** for IPv4 addresses and token-shaped strings before being
written, **with a positive control proven to catch a real hit first**
(a synthetic line with a fake IP, a fake `sk-...` key and a fake `Bearer ...`
token — both regexes matched it). Real-file matches were all false positives
on inspection (tool names, an unredacted `sessionId` UUID — not a credential,
same convention run #1's saved `run.json` uses) except the MCP server's own
LAN URL in `pinned-config.json`, redacted before being written here, exactly
as run #1 did.

**Reversal / cleanup**: this run's own scratch files
(`/home/df/architect-run-2/` on VM 106, and
`/opt/openclaw/config/architect-workspace/SOUL.md`) were deleted before
finishing — verified: the workspace directory is empty again and `/home/df/`
shows only the account's default dotfiles. No durable change to VM 106 beyond
what run #1 already left (the pulled image, the persisted DeepSeek
plugin/auth fix, the `df-overseer` MCP entry) — all still reversible per run
#1's own documented reversal steps.

Full detail, the complete comparison table, and the "what could not be
verified" section are in
`evals/live/2026-09-14-architect-second-charter/README.md`.
