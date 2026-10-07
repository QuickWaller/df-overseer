# Why do the fort agents' round 1 requests miss DeepSeek's prefix cache across runs?

Date: 2026-10-07. Live, on the agent VM, against the real overseer pinned config. No
model call was made, no tool was called, the fort, dfmcp state, conductor state and
`conductor.service` were not touched.

## Verdict

**The request prefix is byte-identical across runs up to the briefing.** Three launches
of the real overseer role, 4 and 2.5 minutes apart, differ first at byte offset 8490 of
the 111,316-byte request body, and the only differences are inside the user message.
The miss is therefore not caused by an unstable system prompt or tool list in this
setup. Two properties of the request are worth knowing, and one finding about the
workspace needs a check (below).

## Method

- The overseer pinned config was copied and only the DeepSeek provider `baseUrl` was
  pointed at a loopback capture server (plus a dummy API key, so the real key never
  left its file). The server recorded each request body and answered a one-word final
  message with no tool calls.
- The state dir (persisted auth and plugins) was a temporary copy, never the real one.
  The role charter was written as `SOUL.md` into a temporary workspace, as the runner
  does. The docker command shape matched `conductor/runner.py` (`--rm`, fixed
  `--hostname <role>`, `--entrypoint node`, state, read-only pinned config, workspace
  and `--state-dir` mounts, `agent exec --json --model ...`), with `--network host`
  added to reach the capture server.
- Three launches, minutes apart, each with a different briefing (tick number). A
  fourth launch without `--state-dir` produced the same system message length and tool
  count.
- The MCP tool list fetch from the dfmcp server (a read) ran normally: 82 tools.

## Evidence

- Body keys, in order: `model, messages, stream, stream_options, tools, tool_choice,
  max_tokens, reasoning_effort, thinking`. Everything except `messages` is equal across
  runs (tools, 104,905 bytes, identical sha; `thinking` enabled, effort high).
- `messages` has two entries. The system message (8,208 chars) is identical across
  runs. It is marked `STABLE` then `DYNAMIC`; the dynamic part holds a `## Temporal
  Context` block (current date, time zone UTC), which changes once a day.
- First differing byte (runs 1 vs 2, 2 vs 3, 1 vs 3): 8490, 8491, 8490. It is inside
  the user message, which starts with a minute-resolution timestamp prefix
  (`[Wed 2026-10-07 02:49 UTC] <briefing>`) and ends with a `Runtime:` line carrying
  `session=agent:overseer:explicit:<uuid>` and `sessionId=<uuid>`, new every run, plus
  `host=overseer`, OS, node version and model.
- Because the serialized body puts `messages` before `tools`, the first diff offset
  looks early, but DeepSeek renders tools into the prompt ahead of the messages, so the
  shared prefix in the model's view is tools plus the system message, about 30k tokens
  here. This is not confirmed from DeepSeek documentation.

## What this means for the earlier miss

1. Same role, same config, same tool list: the stable prefix is identical, so a
   cross-run miss at the start is not an openclaw prefix instability. The throwaway
   agent's hits and the earlier research (`research/2026-10-07-cross-run-cache.md`) are
   consistent with that: misses seen in real runs are more likely cache eviction
   (best effort, "few hours to few days") or a prefix change between deploys (tool list
   or charter edits), neither testable from one capture.
2. Anything cached ends at the user message. The timestamp, briefing and the
   `Runtime:` session ids are always new, so about the last few hundred tokens of
   round 1 are never cacheable. That is expected and small.
3. A tool-list change on the dfmcp side (a new or reordered tool, a schema edit)
   moves the break to the tool section and costs the whole prefix. The list was stable
   across the three launches (sorted by name in the request).
4. The day boundary: the `Temporal Context` date sits in the dynamic part of the system
   message, after the tool block, so a date change should cost only text after it.

## Caveat that needs a follow-up check

In this reproduction the injected workspace files showed as `[MISSING]` at `/app/SOUL.md`
and the working directory as `/app`, i.e. the charter written to the pinned workspace
path was **not** in the system message (system message 8,208 chars, no charter text).
`agents list` confirmed the overseer's workspace as the pinned path. I did not establish
whether the real runs behave the same (they use the same mounts, so likely) or whether
this was an artifact of the reproduction (for example the temporary state dir).
Two consequences: the 8,208 char system message is smaller than a charter-bearing one
would be, and the real overseer prompt (estimated near 59k tokens earlier) is mostly
tools. A real run's own request should be captured once to confirm; the conductor's
archived envelopes do not hold it. Not verified: DeepSeek's prefix unit size or minimum
length (not documented in the sources read), and whether the real service's launches
add anything this method did not.

## Fix

None needed for prefix stability. Cheap hardening: keep the tool list and schemas
byte-stable across deploys, batch charter edits, and run wakes close together. If the
charter is indeed missing from the prompt, that is a separate and larger issue to check
first.

## Cleanup (verified)

Temporary directory (state copy, config copy, key file, workspace, captures, scripts)
removed; no leftover containers (`docker ps -a` empty); capture server stopped, nothing
listening on its port; the real overseer workspace is empty as before. Local scratch
files removed.
