# Stream: doc drift pass after the queue, the rebuild and the first ruling

**Written** 2026-09-16. **Status:** dispatched. **User go-ahead:** "put a
sonnet on updating docs". Execution by a Sonnet executor.

## Why

Four days of live work landed since most of the docs were written: the MCP
server and queue went live on VM 103, VM 106 went dark and was rebuilt,
incident capture shipped, and the Overseer made its first ruling as a second
openclaw agent. Several documents still describe the world before that.
Known-stale examples, not an exhaustive list:

- `agents/ROSTER.yaml` header: "STATUS 2026-09-12: nothing here is running
  yet. The MCP server these allowlists reference does not exist."
- `dfmcp/README.md` around its status lines (one says nothing it produces was
  installed or started anywhere).
- `docs/AGENT-ARCHITECTURE.md`: deployment topology and §14's open list,
  written as design. Two agents now run for real on VM 106, the queue is
  live, and one ruling exists.
- `agents/overseer/model.yaml`: names `anthropic/claude-opus-5`. The first
  ruling ran on `deepseek/deepseek-v4-pro` for budget, a deliberate, recorded
  deviation. The file should say so without changing the design default.
- `ROADMAP.md` Now bucket: the ruling item is done; the fort being paused is
  the blocker for the next two.
- `CLAUDE.md`'s status block: partly updated already; check every line.

## Ground truth

Read these first and treat them as the source of truth. Where a doc and these
disagree, the doc is wrong:

- `Working.md`, `decisions/DECISIONS.md` rows dated 2026-09-14 to 2026-09-16.
- `handoffs/2026-09-15-queue-live-deploy.md`,
  `handoffs/2026-09-15-vm106-rebuild.md`,
  `handoffs/2026-09-15-incident-capture.md`,
  `handoffs/2026-09-15-overseer-first-ruling.md` (Result **and** orchestrator
  review sections in each).
- `evals/live/2026-09-15-architect-third-charter/`,
  `evals/live/2026-09-15-overseer-first-ruling/`.
- `research/2026-09-15-openclaw-secret-storage.md`.

Facts worth stating plainly wherever they belong, because they are easy to
get wrong:
- The live fort is **paused** at tick 12274877 under the user's standing
  rule, so no prediction can come due and nothing executes until it runs.
- The first ruling is **one sample on a cheap model**: charter-clean, but it
  judged an unattributable prediction sound. Not evidence of good arbitration.
- openclaw-side tool scoping is defence in depth; the dfmcp token-to-role map
  is the boundary (`docs/AGENT-ARCHITECTURE.md` principle 8).

## What to do

1. **Audit, then fix.** Walk `CLAUDE.md`, `ROADMAP.md`, `docs/*.md`,
   `dfmcp/README.md`, `dfqueue/README.md`, `agents/**` (including
   `ROSTER.yaml`, each `role.md`, `tools.yaml`, `model.yaml`) and
   `scripts/README.md` if present. For each, list what is stale and fix it in
   place. Keep each file's voice and structure; no rewrites.
2. **Mark verified vs proposed** (CLAUDE.md's rule). Anything now live should
   say so with a date; anything still design should keep saying it is design.
   Do not promote something to "live" that you cannot point at evidence for.
3. **New traps** into `docs/TRAPS.md` (append only), from this week's streams:
   multi-agent openclaw configs need `agents.ownership: "explicit"` and
   `agents.defaults.systemAgent.agentId`; a pinned config's `_note` key is
   rejected by the live schema; an externally-linked openclaw plugin is lost
   when the VM is rebuilt; a `models.providers.<id>.apiKey` SecretRef resolves
   but is shadowed by an existing plaintext auth profile (`REF_SHADOWED`).
4. **Report drift you did not fix**, with the file and why, rather than
   guessing. Contradictions between two docs are a finding, not yours to
   settle by picking one.

## Hard lines

- **Docs only. No code, no tests, no config, no VM, no model call.** If a fix
  needs a code change, report it instead.
- No addresses, hostnames, tokens or key material anywhere (the repo is
  public). Cite VMIDs.
- Do not write `Working.md`, `decisions/DECISIONS.md` or `memory/`: the
  orchestrator owns those. Do not push.
- No em dashes in prose.
- Ambient `python -m pytest` must still pass (276 passed, 1 skipped) since you
  are touching no code; run it once at the end as a guard.

## Touched surfaces

`CLAUDE.md`, `ROADMAP.md`, `docs/*.md`, `dfmcp/README.md`, `dfqueue/README.md`,
`agents/**`, this doc, its `handoffs/INDEX.md` row.

## Report

Per file: what was stale, what you changed, and what you left alone and why.
Then the new traps added, and the drift you could not settle.

## Result, 2026-09-16

**Status: done.** Merged local `main` twice (once at dispatch to pick up this
doc, once mid-stream to pick up the orchestrator's own "fort unpaused, frame
cap is 100 not 5, real save location" record) rather than diverging from it.
Docs only, no code/config/tests/VM/model call touched. Ambient
`python -m pytest` run twice (before and after folding in the orchestrator's
update): **276 passed, 1 skipped** both times.

### Per file

**`CLAUDE.md`.** Stale: status date 2026-09-15; the `dfqueue/` bullet said
"nothing has ruled on it"; the Agents bullet described only one-shot
architect calls. Changed: date to 2026-09-16; `dfqueue/` bullet now records
`ruling-0001` (accepted, 2026-09-16), the pause window (kept paused at tick
12274877 until 2026-09-15 23:03 UTC, then unpaused and left running
unattended with no Sentry), and that `proposal-0001`'s 1200-tick prediction
window elapsed within about a minute at the real `FPS_CAP` (100, not 5) --
so grading it now would record a latency miss, not a verdict on the
proposal; Agents bullet now names both architect and overseer as one-shot
callers. Left alone: everything else was already accurate.

**`ROADMAP.md`.** Stale: the Now bucket's numbered next-steps list had "the
Overseer rules on it" as still open, and a grader-schedule item with no pause
annotation. Changed: step 2 marked DONE 2026-09-16 with the ruling detail;
step 3 annotated with the pause-then-unpause-then-window-elapsed finding;
`Last reviewed` header bumped to a 17th, targeted pass. Left alone: the deep
history below the Now bucket (2026-09-08 through 2026-09-11 entries,
Next/Later/Explicitly-not-doing) -- out of this week's scope, no drift found
there on inspection.

**`docs/AGENT-ARCHITECTURE.md`.** Stale: the file-level status block still
said the queue was "not started"; §13 called the transport "MCP over HTTP on
the tailnet" when it is actually LAN-bound with Tailscale deferred (bearer
tokens the only guard); §14 and two other sections state `FPS_CAP:5`, which
cost/latency reasoning rests on, when the live fort actually runs at 100.
Changed: appended a dated status paragraph (queue live, two agents have
called the fort, one ruling, the pause/unpause/window-elapsed finding);
corrected the tailnet claim to LAN; added a new "Still open" finding in §14
recording the real `FPS_CAP` and flagged the three affected passages (§2, §6,
§14) inline **without rewriting the reasoning that depends on the wrong
number** -- per the orchestrator's explicit instruction, correcting the
number is this stream's job, revisiting the conclusions it feeds is not.
Left alone: §14's other "Still open" items (breach poller, hostile detector)
-- still accurate, unchanged.

**`docs/PURPOSE.md`.** Stale: a parenthetical said the MCP seam "has not yet
met a live DFHack" (it has, repeatedly, since 2026-09-14, and is deployed as
a durable service). Changed: corrected that parenthetical; added a dated
finding under the `FPS_CAP` table noting the live fort actually runs at the
table's own default row (100), not the 5 the surrounding paragraph reasons
from -- not re-derived. Left alone: the save-path claim
(`~/.local/share/Bay 12 Games/Dwarf Fortress/save/`) was already correct and
matches the orchestrator's live-verified fact exactly, so nothing to fix
there; the "still-unbuilt MCP seam" phrase inside preserved historical
reasoning a few lines up is immediately superseded by the doc's own next
paragraph, per this repo's convention of not rewriting history in place.

**`docs/MEMORY-ARCHITECTURE.md`.** Stale: a sample-size estimate ("~3 forts
per month") built on `FPS_CAP:5`. Changed: added a dated finding noting the
live cap is 100, so the estimate is a design-time figure at a cap that was
never actually applied, not a measurement -- not re-derived.

**`dfmcp/README.md`.** Stale, and the sharpest drift found: the header
claimed "not deployed anywhere: nothing in this package has met a real
DFHack or a real MCP client outside this repo's own test suite," and the
"What remains unproven" section's four bullets (never met real DFHack, never
run under uvicorn/bound a socket, never reached by openclaw, systemd unit
never installed) were all resolved between 2026-09-14 and 2026-09-15 but
still read as open. The "What this package deliberately does not do"
section repeated the same "never deployed" claim for `server.py`. Changed:
rewrote the header to state it is deployed, live-verified, and called by
openclaw; struck through each of the four unproven bullets with a dated
RESOLVED note and evidence, keeping one genuinely-still-open item (deploy
byte-identity depends on the deploy method -- CRLF trap -- and no
many-concurrent-agent load test exists); corrected the "deliberately does
not do" section's TLS/tailnet claim (it binds LAN directly, no TLS, no
tailnet) and its deployment claim. Left alone: the rest of this very long,
module-by-module README (canonical id scheme, `roles.py`/`tools.py`/
`auth.py`/`dfhack_client.py`/`queue_tools.py` sections) -- read in full,
verified accurate against `decisions/DECISIONS.md`, no drift found.

**`dfqueue/README.md`.** Stale: the header said "Local code and tests only:
no MCP tool ... not built here," and a later section said "Phase A only:
local code and tests, not deployed. Nothing in `dfqueue/` runs on VM 103
yet." Both predate Phase B's live deploy. Changed: both updated to record
the live deploy, the architect's real proposal, the Overseer's ruling, and
the pause/unpause/window-elapsed finding. Left alone: "What is deliberately
not here yet" (grader schedule, publisher, feed page, `plan` record kind) --
still accurate, unchanged.

**`agents/ROSTER.yaml`.** Stale: header said "STATUS 2026-09-12: nothing
here is running yet. The MCP server these allowlists reference does not
exist." Also stale: the `marshal` role's `blocked_on` field cited "no
trustworthy threat signal ... a purpose-built detector is required work
first" -- that detector (`threat.scan`) was built and live-verified
2026-09-12, before this file was last touched, so the premise was already
wrong independent of this week's work. Changed: rewrote the header to state
the MCP server is live and which two roles have actually called it;
corrected `marshal`'s `blocked_on` to say the detector exists and the real
blocker is the missing write tools.

**`agents/README.md`.** Same stale "Status 2026-09-12 ... nothing here is
running" claim as `ROSTER.yaml`. Corrected the same way.

**`agents/overseer/model.yaml`.** Stale by omission: names
`anthropic/claude-opus-5` with no note that the one real ruling ran on
`deepseek/deepseek-v4-pro` for budget. Added a dated note recording the
deviation without changing the design default, per the brief's instruction.

**`agents/architect/model.yaml`.** Same class of drift, not named in the
brief's examples but found by the same audit: names
`anthropic/claude-sonnet-5`, but all three real charter runs used
`deepseek/deepseek-v4-flash`. Added the same kind of dated note.

**`agents/architect/tools.yaml`, `agents/overseer/tools.yaml`,
`agents/consultant/tools.yaml`.** Stale, found by the audit rather than
named in the brief: all three headers still referenced `mcp/registry.py`,
`mcp/README.md` and `mcp/roles.py` -- the package was renamed `mcp/` ->
`dfmcp/` on 2026-09-12 specifically because a local `mcp/` directory shadows
the MCP SDK, and that day's documentation sweep
(`decisions/DECISIONS.md` 2026-09-12, "six files corrected") missed these
three. Changed: all three headers now say `dfmcp/`. Also in
`agents/overseer/tools.yaml`: the `threat.scan` entry said "Never run
against a live fort as of writing," which was true when written but is now
false -- it was live-verified the same day (`decisions/DECISIONS.md`
2026-09-12, "Threat detector LIVE-VERIFIED"). Corrected with the real
verification detail.

**`agents/marshal/role.md`.** Same stale premise as `ROSTER.yaml`'s
`blocked_on`: "There is no trustworthy hostile signal at either layer, and
building one is required work before this role means anything." Corrected:
`threat.scan` exists and is live-verified; the real blocker is the missing
write tools for military posture, squads and burrows.

**Audited and left alone, no drift found:** `docs/DF-UI-AUTOMATION.md`,
`docs/PROXMOX-SETUP.md`, `docs/RUNBOOK-DARK-GUEST.md` (created 2026-09-15,
already current), `agents/architect/role.md`, `agents/overseer/role.md`
(except the `tools.yaml` fix above), `agents/consultant/role.md`,
`agents/quartermaster/role.md`, `agents/chronicler/role.md`. No
`scripts/README.md` exists.

### New traps added to `docs/TRAPS.md` (append only)

A new "Added 2026-09-15/16, from the queue live deploy and the Overseer's
first ruling" section, exactly the four named in the brief: multi-agent
openclaw configs need `agents.ownership: "explicit"`; `agent exec` in a
multi-agent config separately needs `agents.defaults.systemAgent.agentId`,
undetected by `config validate` alone; a pinned config's `_note` key is
rejected by the live schema; an externally-linked openclaw plugin
(`@openclaw/deepseek-provider`) is lost across a VM rebuild and needs
re-linking; and a `models.providers.<id>.apiKey` SecretRef can resolve
cleanly in a secrets audit while still being shadowed, unconditionally, by
an existing plaintext auth profile (`REF_SHADOWED`).

### Drift not settled, reported rather than picked

- **`agents/overseer/role.md`'s "Command latency is bounded below by the
  simulation tick ... commands have been observed taking 45-80 seconds"** and
  `docs/AGENT-ARCHITECTURE.md` §14 item 5's attribution of that same 45-80s
  figure partly to tick-gating both predate the `FPS_CAP` correction. The
  45-80s figure itself is an independent live observation, not derived from
  `FPS_CAP:5`, so it is not obviously wrong -- but the tick-wait *share* of
  that explanation (previously reasoned as ~200ms at cap 5) would be ~10ms at
  the real cap of 100, which changes which term the explanation says
  dominates. Not touched here: per the orchestrator's instruction, correcting
  the `FPS_CAP` number was this stream's job, not re-deriving what depends on
  it, and this specific passage is reasoning rather than a bare restated
  number, so it did not fit the narrow inline-correction pattern used
  elsewhere. Flagged for the orchestrator's call.
- **No genuine two-doc contradiction was found** that this stream judged not
  its place to settle -- the drift found was uniformly "doc says X, register/
  live-fact says not-X," not two docs disagreeing with each other.

### Live facts folded in mid-stream

The orchestrator sent three verified-live facts partway through (fort
unpaused 2026-09-15 23:03 UTC; `FPS_CAP` is 100 not 5; saves are under the
`df` user's XDG data dir, not the game directory) and, separately, committed
its own `Working.md`/`decisions/DECISIONS.md` record of the same plus the
finding that `proposal-0001`'s prediction window elapsed unexecuted once the
fort resumed. Both were merged into this branch (two merges from `main`, see
commits below) and folded into every doc this stream touched that described
the pause or cited `FPS_CAP:5`, rather than left half-corrected.

### Commits on this branch (`worktree-agent-ac8f4ce560b6658d4`)

Fourteen commits, one per logical chunk (`wip:` prefix) plus two merges from
`main`; see `git log` for the full list. No push.
