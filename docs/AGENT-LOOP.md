# The agent loop (MVP)

How the fort runs unattended: what wakes an agent, what the game clock does
while one thinks, and who carries out a decision.

> **Status: design, 2026-09-22. Nothing here is built.** Written in a design
> conversation with the user, whose goal is "design the agent loop, fill in
> the gaps, let the fort run": an MVP that runs, to be improved from what it
> does. Each decision is marked **agreed** (the user's call) or **default**
> (the orchestrator's gap-fill, standing until the user overrides it).
> Companion to `docs/AGENT-ARCHITECTURE.md`, which this narrows to a first
> buildable slice rather than replaces.

---

## 1. Shape

**Agreed, 2026-09-22:** the 2026-09-19 open question ("dispatcher plus queue,
or openclaw-native?") is answered **dispatcher plus queue**. A code
**conductor** wakes each role as an independent one-shot `agent exec` run with
fresh context; roles talk only through `dfqueue`. openclaw's Gateway, its
heartbeat and cron triggers, and `sessions_send`/`sessions_spawn` are not used.
Reasons: `research/2026-09-18-openclaw-capabilities.md` §3 (the queue is the
typed channel and the audit log, the native send lane is serialised, no
Gateway has ever run here), and every live run so far already works this way.

One cycle:

1. **Read.** The conductor reads vitals, the diff since each role last woke,
   and the queue.
2. **Grade.** Predictions now due are graded by code (`dfqueue/grade.py`).
3. **Triage.** Code rules decide who, if anyone, to wake, and set the clock
   policy for the cycle (§2). A quiet cycle wakes nobody and costs nothing.
4. **Advise.** Woken advisors propose or pass.
5. **Decide and act.** The Overseer, woken only if the queue holds something
   for it, rules and carries out what it accepted.
6. **Save** before any action on the fort (the existing quicksave rule,
   `docs/TRAPS.md`).

The fort keeps running between and during cycles, at the speed §2 sets.

## 2. The game clock

The fort runs at **100 FPS**, not the 5 several design docs assumed
(`docs/PURPOSE.md`, finding 2026-09-15), so a 60-second agent turn at full
speed is about 6,000 ticks, roughly five game days. That is what let
`proposal-0001`'s prediction window elapse before anything could act on it.

`docs/AGENT-ARCHITECTURE.md` §6 already chose **throttling, not pausing**,
as the ordinary way to buy thinking time ("a frequently frozen fortress is a
failure, not a safe default"), with game time per cycle about `f·T + k` ticks.
This section makes that concrete.

**Agreed, 2026-09-22: the clock speed while an agent thinks is set by why it
was woken, not by the fact that it is thinking.** Choosing where the next
workshop goes can take minutes at full speed with nothing lost; deciding what
to do about thirst nearing critical cannot.

Three levels, each a config value:

| Level | Setting | Starting value |
|---|---|---|
| Full speed | `base_fps` | 100 |
| Slowed | `think_fps` | 10 |
| Paused | n/a | fort stopped |

**Agreed: `base_fps` is a setting, not a constant.** The user may lower full
speed later if the fort moves too fast to watch or to steer (at 100 a game
year is about 1.1 real hours; at 20, about 5.6). Every rule below is written
in **ticks**, so it holds whatever `base_fps` is set to.

**Policy per wake reason** (fallback table, held as data, not code branches):

| Wake reason | Clock while thinking |
|---|---|
| Routine review (every N game days), prediction graded, season change, migrant wave | full speed |
| Learning, court, doctrine, chronicle (later roles) | full speed, always |
| Stuck job, stock below target | full speed, unless closing in (below) |
| Vital nearing its threshold, caravan present, hostile seen but not yet able to reach the fort | slowed |
| Tripwire: a death, a critical vital, a hostile that can reach the fort | paused |

**Closing in, computed where code can** (agreed direction): slow the fort
only when the ticks until a consequence are fewer than a few multiples of the
expected thinking time, measured in ticks at the current `base_fps`. Code
already derives the inputs (thirst and hunger against their critical values,
food and drink cover days, a caravan's departure). The table is the fallback
for wake reasons with no computable deadline. The multiple is a config value.

**The most urgent live reason wins.** If a reason that slows the fort arrives
during a full-speed cycle, the conductor slows it then, and restores
`base_fps` once nothing urgent is being deliberated.

**Starting and stopping the fort belong to code, never to a model.** The
Overseer's charter line "never unpause without being asked to" is unchanged.

**The frame cap does not survive a game process restart**
(`docs/AGENT-ARCHITECTURE.md` §6), so the conductor re-asserts it.

## 3. Safety: tripwires inside the game

**Default.** Tripwires run **inside the game loop**, in a DFHack script
registered the way `overseer-autosave` is, not over SSH: on 2026-09-19 a
wedged command pipe took the remote watchdog's own pause call with it
(`docs/TRAPS.md`). On a tripwire the script pauses the fort and records why;
the conductor sees the pause and wakes the Overseer. So if the conductor or
openclaw dies, the fort keeps running at whatever speed it was set to and
still pauses itself on a death, a critical vital or a reachable hostile.

Tripwires, v1: a citizen death; hunger or thirst past a critical threshold;
a hostile `threat.scan` admits (reachability, not the danger flag); a new
announcement of an alert class. **Built 2026-09-22 (not deployed): the first
three**; the announcement tripwire was not in that stream's brief and is
still owed. Defaults hunger 75,000 and thirst 50,000 ticks, from DFHack's
`full-heal.lua` (`research/2026-09-16-food-clock-and-farm-lead-time.md`).
`fort.quicksave` fires and reports the predicted slot, with a separate
confirm call, because waiting inside Lua would hold the suspend lock the save
itself needs. **Not covered: flooding**, since the breach
detector is inconclusive (`ROADMAP.md`).

## 4. Build items

All **default** unless marked.

| # | Piece | Where | Notes |
|---|---|---|---|
| 1 | In-game clock and tripwire script | VM 103 | Sets the frame cap on request; pauses on a tripwire and records the reason |
| 2 | A `conductor` role in dfmcp | `dfmcp/` | New token held only by code, never by an agent: `clock.set-speed`, `pause`, `resume`, `status`, `arm`, `disarm`, `clear`, `fort.quicksave`, `vitals.summary` (built 2026-09-22, not deployed) |
| 3 | The conductor service | VM 106, systemd | Python. Runs the cycle, triage, the clock policy; launches `docker run --rm ... agent exec` as the 2026-09-16 run did; archives each run's JSON, tool calls and `costUsd` under `runtime/` for the public report |
| 4 | Queue: an execution record and a grading schedule | `dfqueue/` | `queue.executed` references the ruling and the call ids. **A prediction's window starts at execution, not at writing.** The grader runs every cycle |
| 5 | Enable the Quartermaster | `agents/` | Food, drink, work orders, farms and workjobs are where this fort actually needs decisions; the Architect covers only placement. Needs a proposal-type vocabulary (`dfqueue/schema.py` has only the Architect's three) and a real allowlist |
| 6 | Per-cycle briefing | conductor | Tier 0 figures only (vitals, cover days, stuck jobs, the role's diff, queue state), placed in the prompt. Nothing that grows with the fort |
| 7 | `ask` / `answer` and fact-check records | `dfqueue/` | Any advisor may ask the Consultant (register 2026-09-15); the Overseer may route a proposal for fact-checking (2026-09-17). One ask, one answer, no threads |
| 8 | Consultant retrieval, local | `dfmcp/`, VM 103 | **Agreed.** `knowledge.wiki_lookup` over a local wiki snapshot (register 2026-09-15: capped section excerpts, not the open web), and a read-only search-and-read tool over DFHack's own installed scripts, docs and Lua on VM 103 (exact to 53.16, which the wiki cannot promise) |
| 9 | Consultant retrieval, web (forums) | `dfmcp/` | **Agreed, user's call 2026-09-22: needed for the MVP.** Read-only search and fetch. Everything fetched is **untrusted data, never instructions**, and can support only a `prior`, never `verified`. **Search backend: Brave Search API** (user's call 2026-09-22; the user supplies the key). Runs inside dfmcp, so the per-role allowlist and the call log cover it. The Consultant is guided, not fenced, by `agents/consultant/sites.yaml`: the major DF sites, what each is for, and its version caveat |

**Roster, agreed 2026-09-22:** Overseer, Architect, **Quartermaster** and
**Consultant**. The Consultant is woken only when an `ask` or a fact-check is
open; within a cycle the order is advisors, then Consultant, then Overseer, and
a proposal sent for fact-checking is ruled on the next cycle.

**Triage rules, v1:** wake advisors on a vital crossing a threshold, a stuck
job, a prediction falling due or graded, a migrant or caravan event, or at
least every 7 game days; wake the Overseer only when the queue holds
something for it. All thresholds are config.

**Models:** DeepSeek for every role, as in every live run. No spend-cap work
(user's standing call); each run's `costUsd` is logged and summed per day.

**Alerts:** a status JSON and journald lines. Telegram and the public feed
later.

## 5. Deliberately left out of the MVP

Each can be added without changing the loop's shape: the full per-step
write-ahead log (a quicksave before acting plus the call journal stand in),
playbooks and Sentry reflexes, the Consultant inside the loop, `amend`, the
court and the learning role, the public feed.

**Known risk, accepted:** most write tools have never done a real build
(`Working.md`, "Where the MVP stands"). Early cycles will surface tool
failures. That is intended; it produces the evidence the confidence levels
and gotchas are for.

## 6. Objectives: a default flow with deviations (in design)

Every wake reason above is reactive; nothing yet says what the fort is trying
to achieve. **Agreed direction, 2026-09-22 (user):**

- **The Overseer keeps the agenda** and changes it through queue proposals,
  so every change is audited. How those proposals are ruled is open, pending
  the wider proposals design.
- **It starts preseeded** from forum and guide research, and grows and is
  polished over time. **The seed waits until this design settles.**
- **Two lifetimes** (orchestrator's suggestion, not yet confirmed): a
  **progression template** that survives across forts and is what gets
  polished, and a per-fort **agenda** instantiated from it, which dies with
  the fort.
- **An ordered graph with a default flow and deviations** (user's proposal):
  the site decides not only *what* to do but *when*. Nodes are objectives
  (`done_when`, prerequisites, `because`, sources); default-flow edges give
  the standard progression; **deviation rules** (`when` a site or state fact
  holds, insert, skip, move earlier or later, with `because` and sources)
  adapt it. "Fishing needs a river, lake or ocean" is a visible rule with its
  reason, whether or not it fired.
- **Both code and the Overseer decide applicability** (user: "A and B"):
  code evaluates rules against a closed vocabulary of site and state facts,
  from a site-profile read tool, reporting `unknown` rather than guessing;
  the Overseer may deviate where no rule foresaw it, recorded as a
  **variance** with its reason and evidence.
- **Viewable logic:** every objective carries its history (what changed, who
  proposed it, the ruling, the evidence), returned by `agenda.get(id)`.
- **Prompt size:** a prompt shows the top few open objectives in full plus a
  one-line index of the rest; never the whole graph.

Prior art being read before the schema is fixed: clinical pathways with
variance tracking, and RTS build orders adapting to scouting
(`research/2026-09-22-objective-graph-prior-art.md`, dispatched).

## 7. Open

**From the build streams, 2026-09-22 (all merged locally, none deployed):**

- **A failed execution still starts the grading window**, so a later miss
  cannot yet tell "the proposal was wrong" from "carrying it out failed".
  Needed before any role's hit rate is trusted; it is also the attribution
  split `docs/PRODUCTION-MODEL.md` §3 describes.
- **Only the first execution arms the window.** Manager orders on this fort
  have queued without ever running, so a `work_order` window may start long
  before its effect can land.
- **`order."ID".exists`** assumes DF removes a completed order from its list;
  documented, never witnessed here. Its first live grading is also the first
  check of that assumption.
- **Deploy trap:** the queue migration keeps old rows on their write-time
  deadlines. On VM 103 that includes `proposal-0001`, left ungraded on
  purpose (register 2026-09-16); the first grading cycle would record it as
  a latency miss. Decide before the conductor first runs the grader.
- **Owed:** the announcement tripwire (§3); a wiki snapshot; the VM 103
  DFHack source path check; the Brave key into VM 103's service environment.


- Web retrieval (item 9): the Brave key, owed by the user; Brave's current
  pricing and limits are unchecked.
- The Quartermaster's proposal-type vocabulary (item 5).
- Where the conductor runs (VM 106 is the default, since it launches the
  containers there).
- Cycle wall-clock time, and so the right `think_fps`, is unmeasured
  (`docs/AGENT-ARCHITECTURE.md` §14 item 8). Instrument it from the first run.
