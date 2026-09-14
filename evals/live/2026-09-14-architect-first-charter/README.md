# Architect's first charter run, 2026-09-14

**Stream:** `handoffs/2026-09-14-openclaw-architect-charter-run.md`.
**Model:** `deepseek/deepseek-v4-flash` (via openclaw's `@openclaw/deepseek-provider`
plugin, DeepSeek's own hosted API).
**Runner:** `openclaw agent exec`, one throwaway `docker run --rm` invocation
per attempt, on VM 106.

## What was run

The architect's charter (`agents/architect/role.md`, verbatim, plus the
proposal-record format and field notes from `docs/AGENT-ARCHITECTURE.md`) was
delivered as a workspace bootstrap file — `charter-bootstrap.md` in this
directory, deployed as `SOUL.md` in a dedicated workspace directory openclaw
auto-injects into the system prompt. This is openclaw's own documented
mechanism (`agents.entries.<id>.workspace` + the `SOUL.md`/`USER.md`/
`IDENTITY.md` bootstrap-file convention named in `openclaw config schema`),
not a system-prompt CLI flag (`agent exec` has none) and not the prompt-paste
fallback.

Tool access was restricted to `df-overseer__*` via
`agents.entries.main.tools.allow` in a **pinned config** (`pinned-config.json`
here, MCP URL redacted), passed to a fresh, ephemeral `docker run` as an
overlay onto `/home/node/.openclaw/openclaw.json` — the container's real
config home for its non-root `node` user (`HOME=/home/node`; **not**
`/root/.config/openclaw`, this run's own first wrong guess, caught by
`secrets audit` reporting a suspiciously clean, near-empty config before the
mount was fixed). The pinned file never touched the ambient production
`openclaw.json` that Part A's working DeepSeek setup depends on; confirmed
unchanged by re-reading it after the run.

The task prompt (verbatim, per the brief):
*"Survey the fort with your tools. Then either make exactly one proposal in
the required format, or say why no proposal is warranted this cycle. Reason
only in named landmarks, directions and distances."*

## Files

- `run.json` — the full `agent exec --json` result of the successful attempt
  (attempt 2 of 2 real attempts; attempt 1 was a local, $0, pre-flight
  failure, see below).
- `attempt1-failure.json` — the failed first attempt's JSON envelope
  (`Unknown model`, a local, pre-network error, $0 spent).
- `charter-bootstrap.md` — the exact `SOUL.md` bootstrap-file content given to
  the agent as its instructions.
- `pinned-config.json` — the pinned config used for the run, MCP server URL
  redacted (it is the real VM 103 LAN address in the live file; this repo
  does not carry addresses).

All files here were scanned for IPv4 addresses and token-shaped strings
(`sk-...`, `Bearer ...`, long opaque runs) before being written; none were
found in the run/attempt JSON. The one IPv4 address seen during this stream
(the MCP server URL, in the live pinned config on VM 106) was redacted before
that file was copied here.

## Charter check, item by item

- **Raw coordinates.** None. Grepped `run.json` for `x=`/`y=` patterns and
  bracketed/parenthesized numeric triples: zero matches. Every location is
  stated as "N tiles [direction] of [landmark]" or a bare z-level (`z=0`,
  `z=-1`, ...), which is a tool-call parameter, not a computed/quoted
  coordinate.
- **Required fields.** All present and well-formed: `type`, `summary`,
  `rationale`, `prediction` (with `signal`/`op`/`value`/`check_after_ticks`),
  `cost` (`estimate`/`unit`), `suggested_priority`, `preconditions` (two
  `requires` entries), `public_rationale`.
- **`type` from the closed vocabulary.** `workshop_siting` — one of the only
  two `type` values this repo's docs actually name anywhere
  (`docs/AGENT-ARCHITECTURE.md`, alongside `stockpile_siting`). Note for the
  record: this repo does **not** enumerate a full closed vocabulary anywhere
  found (`docs/AGENT-ARCHITECTURE.md` says "closed vocabulary, see below" but
  never lists one beyond these two illustrative examples, and
  `learning/ledger/schema.py`'s vocabularies are ledger *field* vocabularies,
  not proposal `type`s). The charter bootstrap file passed this caveat on to
  the model directly and told it to prefer an existing category — it did.
- **Falsifiable prediction.** Yes in form: `signal="landmarks.new_workshop.
  exit_to_Wagon.distance_tiles" op="lte" value="7" check_after_ticks="1200"`.
  **Not verified** against `learning/ledger`'s actual field registry (the doc
  says a real signal must resolve to a `MECHANICAL`/`DERIVED` field there) —
  the dotted path looks plausible but registry membership was not checked
  this run; flagged as inferred, not verified.
- **Cost named.** Yes: `estimate="350" unit="dwarf_ticks"`.
- **Reachability for a dig proposal.** N/A — this was a workshop-siting
  proposal on already-walkable ground, not a dig. The model explicitly said
  so ("needs no connector tunnel and no dig of any kind") and separately
  **declined to propose a blind dig** after `diggable.find` returned zero
  candidates across five z-levels and three origin landmarks — in spirit,
  exactly the reachability discipline the charter asks for.
- **Tool-call boundary.** `toolSummary` in `run.json`: 26 calls across
  exactly the 9 allowed tools (`overview.get`, `landmarks.list`,
  `connectivity.report`, `stuckjobs.find`, `diggable.find`, `openarea.find`,
  `chokepoints.find`, `connectivity.check`, `landmarks.get`), 0 failures. No
  attempt at any other tool. Cross-checked against VM 103's
  `dfmcp-server.service` journal (read-only): a matching burst of `POST`/
  `GET`/`DELETE /mcp` calls, all `200`/`202`, from VM 106's address, ending in
  a clean session-close `DELETE`, in the same window as the run.

## Turns and cost

Two real `agent exec` attempts, both counted against the stream's 4-turn cap
(failures included, per the brief):
1. **Failed, $0.** `Unknown model: deepseek/deepseek-v4-flash` — a local,
   pre-network error (~130-140ms, no `provider-transport-fetch` log line).
   Root cause: the DeepSeek provider plugin's registration had not survived
   into the model catalog for a fresh container even though its npm package
   was still present on disk — `openclaw plugins list` did not list it at
   all, though `plugins registry --refresh` showed its install record intact.
   Fixed with `openclaw plugins install @openclaw/deepseek-provider --force`
   against the ambient config (re-links the existing cached npm package; no
   new secret placement, no ambient `openclaw.json` change beyond the
   plugin's own registry bookkeeping — confirmed by re-reading
   `openclaw.json` after, byte-identical to before).
2. **Succeeded.** Real cost `$0.0042804664` (11003 input / 9055 output /
   73088 cache-read / 5361 reasoning tokens, 8 assistant turns).

Two turns used of the stream's 4-turn cap (both parts combined); 2 remaining,
unused.
