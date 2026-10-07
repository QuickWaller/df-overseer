# A per-role agent notebook, and how we would know it works

Date: 2026-10-07. Design only: nothing built, nothing deployed, no VM touched,
no database opened. Every number from live data below is quoted from the
three research files of today, not re-measured.

Inputs read: `research/2026-10-07-persistent-sessions.md` (section 6 proposes the
notebook), `research/2026-10-07-wake-audit.md`, `research/2026-10-07-cross-run-cache.md`,
`docs/MEMORY-ARCHITECTURE.md`, `docs/AGENT-LOOP.md`, `conductor/briefing.py`,
`conductor/runner.py`, `conductor/cycle.py` (prompt assembly), `dfqueue/runs.py`,
`dfqueue/plan.py`, `dfqueue/schema.py` and `dfqueue/store.py` (record kinds,
coordinate pattern, `near_duplicate_reason`, `_find_duplicate_proposal`),
`dfqueue/lessons.py`, `dfmcp/gotchas_store.py`, `dfmcp/plan_tools.py`,
`handoffs/2026-10-07-wake-cleanup.md`, `research/2026-10-07-planner-design.md`
(briefing slices), and the register rows dated 2026-10-07.

The user's condition (2026-10-07): "if we go for the notebook, make me confident it's
effective and have measurable methods of improvement." Agents stay one-shot.

## 0. Summary

- **What it is.** Each role has one small notebook of at most eleven entries in four
  kinds (`watching`, `next`, `learned`, `avoid`). It holds intent and lessons, never
  fort facts. It is stored as a new append-only queue record kind, `notebook`, one
  version per write, in the same shape as `fort_plan`. The role edits it with one
  tool, `notebook.write`, using add, drop and renew operations. The server stamps
  role, tick and run, and refuses coordinates, any digit outside a record id, a
  `learned`/`avoid` entry with no evidence, and an Overseer entry that restates a
  defer. The conductor gets the rendered notebook from a conductor-only
  `notebook.render`. The server re-checks each entry's premise against live facts at
  that point, so the briefing shows each entry with its age and any flags, in a
  block labelled unverified, after the stable prefix and before the ask.
- **How we would know.** The first step is a read-only metrics script,
  `python -m dfqueue.wake_metrics`, which can be built before the notebook. It computes
  the baseline from the queue and runs databases: repeat proposals (using the server's own
  near-duplicate rule), repeat defers with nothing changed, duplicate-flagged or
  duplicate-rejected proposals, rounds per wake, redundant re-reads, pass rate, cost
  and tokens. It also computes four notebook-quality measures. Next comes a one-week
  **shadow** phase: roles write notes, nobody is shown them, and quality is measured
  without any risk. Then a **block-randomised within-role A/B**: each wake of the
  Architect, Quartermaster and Overseer is randomly assigned to see or not see its
  notebook, and both arms write. The success thresholds, the kill rule and the stop
  date are pre-registered in an `evals/live/` README committed before the A/B starts.
- **Honest sizing.** The cheap signal is rounds per wake, which is roughly 60 wakes
  per arm for a 15% effect. Repeat proposals are the rare event the user cares about,
  and roughly 100 to 200 wakes per arm are needed to see them halve. At today's
  hand-run cadence (21 runs in 1.7 days) that is three to six weeks. It is much faster
  once the conductor runs as its service. "Inconclusive" is a permitted verdict, and
  the recommended default on an inconclusive result is to remove the notebook.
- **Cost.** About $0.0015 per wake (2 to 3% of the $0.05 mean). It pays for itself
  if it saves 0.3 rounds per wake. Prompt-cache impact is nil by construction.

## 1. The notebook

### 1.1 What it is for, and what it must not become

The persistent-sessions study found what a one-shot run lacks: "what was I in
the middle of, and what did I learn that the queue does not record". The wake audit
showed the cost of not having it: nine Quartermaster runs about one fact (drink is 0),
six Quartermaster work orders rejected, four of them in that window as duplicates or
infeasible, and two proposals deferred three times each with nothing changed. Most of
that is wake design, and the wake cleanup (`handoffs/2026-10-07-wake-cleanup.md`) fixes
the wake side. The notebook addresses what remains: a role woken legitimately that
re-derives the same plan, re-files the same answer, or retries a refused approach,
because it cannot remember.

What it must not become is the stale persistent session by another name. The
Laban et al. failure (`research/2026-10-07-persistent-sessions.md` section 4) is the
risk: an early wrong belief, carried forward and over-trusted. Every rule below is
there to keep the notebook to intent and evidence-backed lessons, with fort facts
re-read live.

### 1.2 One slot per role, edited by operations, capped

**Recommended: one current notebook per role, edited by per-entry operations (add,
drop, renew), under hard per-kind caps. Each write appends a full new version.** This
is neither "overwrite each run" nor "append without bound".

- *Overwrite each run* (the persistent-sessions sketch) is simplest, but it breaks the
  A/B in section 3. A wake that is not shown its notebook would overwrite it blind and
  wipe the continuity the other arm is testing. It also loses an entry whenever a role
  forgets to restate it.
- *Append with a cap* grows to the cap and stays there, and it needs an eviction rule
  anyway.
- *Operations under caps* let a role that cannot see its notebook still add, while
  only a role that can see it drops or renews. The server composes each new version
  from the active one plus the operations, as `dfqueue/plan.py compose` does for the
  plan. Over the cap, the oldest entry of that kind is evicted and the eviction is
  reported. A write is never refused for being full, so a role is never stuck.

### 1.3 Entry kinds

| Kind | Holds | Required fields | Optional structure | Example (coordinate- and digit-free) |
|---|---|---|---|---|
| `watching` | A signal I am waiting to see move, and why it matters | `text` | `until` (a live-signal condition, same grammar as a proposal's prediction), `about` (record id or plan target) | "whether the brew order clears now that a barrel route exists", until `drink_per_citizen >= 1` |
| `next` | The first step I intend on my next wake | `text` | `tool` (an id in my allowlist), `about` | "check the Still's linked piles before any new drink order", tool `stockpile.links` |
| `learned` | A lesson the queue does not record, outside tool behaviour | `text`, `because` (an existing record, ruling, gotcha or run id) | `assumes` (a live-signal premise) | "the Overseer rejects a second brew order while one is open; amend instead", because `ruling-0021` |
| `avoid` | An approach tried, and why it failed | `text`, `because` | `tool`, `assumes` | "direct brew jobs while no barrel is free", because `proposal-0020`, assumes `empty_barrels < 1` |

Kinds per role are policy data (`notebook.kinds_by_role`). The recommended start is all
four for the Architect, Quartermaster and Planner, and `watching`, `learned` and `avoid`
for the Overseer. The Overseer has no `next`, because a ruling turn's next step is set
by what is pending. The Consultant is left out: it answers single asks, and has no
repeat problem in the data.

### 1.4 Never fort facts: what the server refuses

These are server refusals, not charter prose. Each refusal comes with repair text, and
each is a one-line test.

1. **No digits in `text` outside record and catalogue ids.** Allowed tokens are
   `proposal-0017`, `ruling-0025`, `ask-12`, `run-0023`, gotcha ids and doctrine ids,
   matched by one id pattern. Everything else with a digit is refused, with the repair
   text: "name the signal to re-read, not its value; put a threshold in `until` or
   `assumes`". This one mechanical rule removes stock levels, counts, ticks, positions
   and coordinates in one go. It is cruder than a fact detector and that is the point:
   it cannot be argued with. A number written in words ("two beds") gets through, so it
   is measured by the spot-check in 2.3.
2. **The coordinate pattern** (`schema._find_coordinate`) still runs first, so the
   refusal message says "coordinate" when it is one (design commitment 1).
3. **Caps.** `text` is at most 200 characters. Per kind: `watching` 3, `next` 2,
   `learned` 3, `avoid` 3, so at most 11 entries. Each write is at most 6 add operations
   and the payload at most 6 KB. The rendered block is at most 3,000 characters (about
   800 tokens).
4. **References must resolve.** `about` and `because` must name an existing queue
   record, gotcha, run or active plan target. `tool` must be in the writer's own
   `agents/<role>/tools.yaml`. `until` and `assumes` must be a valid live signal
   (`learning.live_signals`, the vocabulary predictions already use).
5. **Evidence for lessons.** `learned` and `avoid` need a `because`, and a `renew` of
   either needs a `because` newer than the entry's. A lesson cannot keep itself alive by
   being re-asserted. This is the main mechanical guard against self-reinforcing
   beliefs (section 5).
6. **No duplicating the queue.** An Overseer entry whose `about` is a proposal whose
   latest ruling is `defer` is refused: "your defer reason already says what would
   change your mind, and it is shown with the proposal". An entry restating an open
   proposal's own summary is refused by the near-duplicate rule, applied to text.

**Flagged, not refused:** a `learned` entry whose text names a tool id is stored with
the flag `tool_lesson`, and the write's reply says "tool behaviour belongs in
`gotchas.write`, which every role reading that tool sees". Such an entry is
legitimately ambiguous (a strategy about a tool, or a fact about the tool), so a refusal
would teach the role to write around it.

Why refuse here when the Planner's plan accepts and flags (register, Planner open
question 1)? A flagged plan entry is inert, while a flagged notebook entry is still
shown to a model. The harm is in the showing.

### 1.5 Tick stamps and expiry

The server stamps every entry with `written_tick` (from the same
`queue_tools._stamp_cycle_snapshot` that `plan.write` uses), `written_run` (the run id
from `conductor.report`'s start), and `tools_hash` (a hash of the writer's
`tools.yaml` at that moment).

An entry expires on **whichever comes first**: its own-wake count or its game ticks.
Wakes are counted as well because ticks freeze under the operator hold (wake audit,
finding 4). The defaults are policy data:

| Kind | Own wakes | Game ticks | Renewable |
|---|---|---|---|
| `next` | 2 | 16,800 (14 game days) | yes, freely |
| `watching` | 5 | 100,800 (one season) | yes, freely |
| `learned` | 12 | 201,600 (two seasons) | only with a newer `because` |
| `avoid` | 12 | 201,600 | only with a newer `because` |

At render time the server also drops or flags the following:
- **dropped**: expired; `about` names a proposal ruled final, or a project closed;
  `until` already true (the thing watched for has happened, shown once as "met", then
  dropped).
- **flagged** (shown with the flag): `assumes` false now (`premise_false`); `tools_hash`
  differs from the current allowlist (`tools_changed`, which matters for `avoid`
  entries about a tool since fixed); the entry was written before the latest charter
  deploy for that role (`charter_changed`).

Each drop is written into the next version's composition with a reason (`expired`,
`closed`, `met`). The record of why entries left is therefore complete and auditable.
The role drops entries itself with a reason code: `done`, `obsolete` or `wrong`. These
codes are measurement inputs (section 2.3).

### 1.6 Where it sits in the prompt

The cache facts first (`research/2026-10-07-cross-run-cache.md`, and `conductor/cycle.py`
lines 867 to 881). The system prompt (openclaw's own, then the charter as `SOUL.md`,
then the tool schemas) is the cross-run cacheable prefix. The briefing is the final
positional argument. Within the briefing, the first volatile byte comes early: for
advisors the briefing is `json.dumps(dict)`, with `game_tick` as its second key, and for
the Overseer the header line carries the tick. Anything in the briefing therefore cannot
affect cross-run cache hits, and within a run the whole first message is cached from
round 2 on.

Placement:

- **Advisors** (JSON briefing): a `notebook` key, last in the dict. The order is the
  Planner's season-stable `plan` slice first (Planner design, section 5.1), then
  `role`, `game_tick`, wake, vitals, diff, queue, alerts, the wake cleanup's `notes`,
  and then `notebook`. If an `ask` key is ever added, `notebook` goes immediately
  before it.
- **Overseer** (text ruling briefing, `build_ruling_briefing`): a block after `OTHER
  OPEN ITEMS` and the wake cleanup's `NOTES` block, and immediately before the ask line.

Rendered form, fixed shape:

```
YOUR NOTEBOOK (you wrote these on earlier wakes. Hypotheses, not facts:
re-read anything you rely on. Drop what is done or wrong with notebook.write.)
- [watching qm-note-0004, 2 wakes ago] whether the brew order clears now that a
  barrel route exists. Until drink_per_citizen >= 1 (now: not met).
- [avoid qm-note-0002, 6 wakes ago, because proposal-0020] direct brew jobs while
  no barrel is free. Premise empty_barrels < 1: NO LONGER HOLDS (read now).
- [next qm-note-0005, 1 wake ago] check the Still's linked piles before any new
  drink order (tool stockpile.links).
```

The "now" and "read now" values are server reads at render time. They are live
facts, not the notebook's own, which is the only way a fort number reaches this block.

**It never goes in the charter or the system prompt.** Doing so would make every
write a cache invalidation of the whole prefix. The charter gets one fixed paragraph
describing the notebook. That paragraph is a single deploy-time charter change, batched
with another deploy so the prefix is invalidated once.

### 1.7 How the role writes it

**Recommended: a dedicated tool, `notebook.write`, called in the same round as the
role's final queue write.** DeepSeek through openclaw issues parallel calls, so this
costs no extra round in the normal case.

```
notebook.write {
  add:   [{kind, text, about?, tool?, until?, assumes?, because?}],   # at most 6
  drop:  [{id, reason: done|obsolete|wrong}],
  renew: [{id, because?}]                                            # because required for learned/avoid
}
-> {version, added: [ids], merged: [{text_index, into}], dropped: [ids],
    evicted: [ids], refused: [{index, problem, repair}], counts_by_kind}
```

- The reply never echoes another entry's text. A wake not shown its notebook learns
  nothing of it from writing (this keeps the A/B arms clean).
- An add that near-duplicates an existing entry of the same kind is merged, not added.
  The match uses the server's `_normalise_words` plus a Jaccard threshold, the same
  helper as `near_duplicate_reason`. A merge refreshes the age of `watching` and
  `next`, and refreshes `learned` and `avoid` only with a newer `because`. A wake
  writing blind therefore cannot fill the notebook with copies.
- A refused operation does not fail the others. The refusals come back with repair text.
- **Rejected alternative: a `notebook` field on `queue.pass` or on the run end.** On
  `queue.pass` it would capture nothing on the wakes that end in a proposal, which are
  the wakes that repeat. A field on every terminal write type spreads one concern
  across five schemas. On the run end, the conductor would have to parse the final
  answer, which is model prose and exactly what "server refusals over charter prose"
  rules out.
- **Rejected alternative: openclaw's workspace `MEMORY.md`.** `agent exec` does not
  load workspace bootstrap files, the file is not auditable, and it is not on the
  Board (persistent-sessions, section 6).

No role gets a `notebook.read`. The conductor shows the notebook, so a role never
spends a round on it, and no role reads another's. `notebook.render` is conductor-only,
by allowlist.

### 1.8 Storage

**Recommended: a new queue record kind, `notebook`, in `dfqueue/schema.py`, append-only,
one record per write. It holds the full composed entry set plus the operations that
produced it.** Fields: `role` (from the credential), `version`, `supersedes` (the
active version's id, checked as `fort_plan` checks it), `entries`, `ops` (added, merged,
dropped with reasons, renewed, evicted), `cycle`, `snapshot`, and `run_id`.

| Option | Verdict |
|---|---|
| New queue record kind | **Chosen.** Append-only, so every version is audited and diffable; joinable to the run by `records_in_window` like every other record; validated at write time by the same schema code; one store per fort, so a notebook dies with its fort, as the memory architecture's dossier row says it should |
| Queue `meta` key | Mutable, no history: the stale-belief audit (2.3) needs to know what an entry said when it was shown |
| Runs DB | It is mutable telemetry pruned at 500 rows (`dfqueue/runs.py KEEP_ROWS`): notebook history would be deleted |
| The gotcha store | Wrong scope: gotchas are per tool, shared by every role reading that tool, and promoted toward doctrine; notebook entries are per role and short-lived. The two are kept apart by the `tool_lesson` flag (1.4) |
| openclaw state dir | Not ours, not auditable, not loaded by `exec` |

Growth: at most 6 KB per version and one version per wake. At a few hundred wakes a
month that is a few megabytes, which is nothing.

Two columns on the runs table, written by `conductor.report`'s `start` phase:
`notebook_arm` (`on`, `off`, `shadow` or null) and `notebook_shown` (JSON: the entry
ids, kinds and render flags the server returned, whether or not they were shown, capped
at 2 KB). Both are what the metrics in section 2 join on. They live in the runs DB
because they are per-run telemetry. The notebook itself is not.

### 1.9 Visibility on the Board

- **Per run:** a run that wrote a `notebook` record gets a collapsed NOTEBOOK panel in
  its turn: added, dropped (with reasons), evicted, and merged. It is built like the
  LESSON panel (`dfqueue/lessons.py`). The run's thread list excludes `notebook`
  records, which are run-level, not threads.
- **Operator page:** each role's current notebook, with age, flags and the arm of the
  latest wake. Next to it is the experiment panel (section 3.6).
- **Public projection:** entries pass the same `find_unsafe_pattern` filter as lessons
  and transcripts. A failing entry shows as withheld and is never edited (consistent
  with the 2026-10-07 transcripts ruling). Collapsed by default.

### 1.10 Interaction with the plan and the notes channel (no duplication)

Three stores feed a briefing, each with one owner and one job:

| Block | Written by | Holds | Expires when |
|---|---|---|---|
| Plan slice (`fort_plan`) | the Planner, server-validated | what the fort needs: targets, districts, flows | a new version |
| Notes (wake cleanup, `LaneState.notes`) | the conductor, from conditions | facts about the fort now: a deferred proposal, a stuck job, an answered ask | the condition clears, or `ttl_cycles`/`max_shows` |
| Notebook (`notebook`) | the role itself | the role's intent and evidence-backed lessons | expiry, closure, `until` met |

The rules that keep them apart, all enforced in code:

1. **Facts are notes, never notebook entries.** This follows from the digit rule
   (1.4.1). A `watching` entry whose `until` signal is the `fact` of a live conductor
   note is not rendered separately: the conductor appends "(you are watching this:
   qm-note-0004)" to the note line, so one fact gives one line.
2. **The plan holds targets, the notebook may only point at them.** An entry may carry
   `about: target:<id>`, and the digit rule stops it restating a target's numbers. The
   Planner's own notebook is for what is in progress between seasonal reviews; the
   season interval still governs `plan.write`.
3. **Defers are the queue's.** See the Overseer refusal in 1.4.6. The wake cleanup's
   defer note and the ruling's own reason already carry this.
4. **Rulings, answers and verdicts are the queue's.** `about` points at them, and the
   briefing (`DECIDED, DO NOT REDO`, the answer note from cleanup item 8) shows them.
5. **Tool behaviour is the gotcha store's** (the `tool_lesson` flag).

## 2. Metrics

### 2.1 Data available today (and what is missing)

- **Queue DB** (`records`): every proposal (`type`, `summary`, `rationale`,
  `prediction`, `cited`, `duplicate_of`, `serves`), ruling (`decision`, `proposal_id`,
  `reason`), pass, ask, answer, close and project, each with `ts`, `role` and `cycle`.
  Complete since the queue began.
- **Runs DB** (`runs`): one row per role run since 2026-10-05 (run-0001), with
  `wake_reason`, `status`, `duration_s`, `cost_usd`, `records_json` (the records the
  run wrote, resolved by role and window), and from 2026-10-07 a `transcript` (rounds,
  calls with clipped args and results, per-round `usage`). The persistent-sessions study
  confirmed that only run-0022 and run-0023 carry a transcript at the time of writing.
- **Missing.** Turn counts and token usage for runs before 2026-10-07 exist only in the
  conductor's archived `run-<role>.json` envelopes on the agent VM. The briefing text
  sent to a role is archived there as well, not in any database. The metrics script
  takes an optional `--archive` directory for these, read from a copy, and every
  metric says which source it came from. Redundant re-reads cannot be computed before
  transcripts existed.

### 2.2 Wake and waste metrics (precise definitions)

Unit: a **wake** is one `runs` row with a non-null `ended_at`. An *advisor wake* is a
row whose role is `architect`, `quartermaster` or `planner`; an *Overseer wake* is a row
whose role is `overseer`. Times are server `ts`. All metrics are per wake, per role,
and per arm where one exists.

**M1. Repeat proposal.** For proposals `a` and `b`, `equiv(a, b)` holds when:
```
a.role == b.role and a.type == b.type
and not (set(a.serves) & set(b.serves))             # parallel plan work is allowed (store.py)
and schema.near_duplicate_reason(b, a) is not None   # the server's own rule, reused
```
A proposal `b` is a **repeat** if some earlier `a` with `equiv(a, b)` was written within
the previous 7 days of wall time, and at `b.ts` that `a` was pending, deferred,
rejected, or accepted with its project not closed `completed`. A need that recurs after
completed work is legitimate and is not counted. Each `b` counts once. Repeats are
broken down by the status of `a`: `open` (pending or deferred), `after_reject` and
`after_accept`. **M1-wide** (sensitivity only, not pre-registered) also counts `a` and
`b` of the same role and type with the same `prediction.signal` and `op`, which catches
paraphrases that the text rule misses. The primary metric uses the text rule because it
is what the server, and so the Overseer, already calls a duplicate.

**M2. Repeat defer with nothing changed.** A ruling `r2` with decision `defer` on
proposal `P` is a repeat defer if the previous ruling on `P`, `r1`, is also `defer`, and
nothing changed between `r1.ts` and `r2.ts`. "Changed" means any of the following:
- a queue record whose `proposal_id` is `P` (an ask, amend, close or executed record);
- an answer to an ask about `P`;
- a deploy-epoch boundary (2.5);
- (sensitivity only, needs `--archive`) a `Cites ... now` value for `P` that differs
  between the two archived ruling briefings.

This matches the wake cleanup's notion of "changed" (new citation, new answer). After
the cleanup lands, M2 should be near zero in both arms. It is kept as a guard: a
notebook must not bring it back.

**M3. Duplicate-flagged or duplicate-rejected.** A proposal is counted if
`duplicate_of` is not null, or if a final `reject` on it has a reason matching
`/duplicat|already (queued|pending|open|accepted|ordered)/i`. M3 overlaps M1 by design:
M3 is what the system already noticed, and M1 is the full count.

**Primary waste count per wake, R.**
`R = |{proposals in the run that are M1 repeats or M3}| + |{M2 repeat defers in the run}|`.
Each record counts once. R is the primary metric for the user's problem.

**M4. Rounds per wake.** `len(transcript.rounds) + transcript.omitted_rounds`
(`build_transcript`). Before transcripts, `assistantTurns` from the archive.
Timed-out runs are included and flagged. Runs with no transcript and no envelope are
excluded and counted.

**M5. Redundant re-reads within a wake.** In one transcript, call `j` is a redundant
re-read if there is an earlier call `i` that satisfies all of:
- `name_i == name_j`;
- the canonical args are equal (parse the clipped args JSON and dump it with
  `sort_keys=True`; if parsing fails, compare the clipped strings);
- the name is in the role's `read:` section of `agents/<role>/tools.yaml`;
- `call_i.error` is false;
- no call `k` with `i < k < j` has a name in the role's `write:` section.

The rate is redundant reads divided by read calls. **M5b, orientation reads** (expected
to be the notebook's real effect), is the number of read calls before the run's first
`write:` call.

**M6. Pass rate.** The share of advisor wakes whose `records_json` holds a `pass` and no
`proposal`, `ask` or `fort_plan`. This is descriptive only, and its direction is
ambiguous: a role that remembers it is waiting should pass more on wakes where nothing
changed. M6 is reported alongside the share of passes whose wake reason was a crossed
survival alert (a guard: passing on an alert is bad).

**M7. Cost and tokens per wake.** `cost_usd`, and from the transcript the sums over
rounds of `usage.output`, `reasoningTokens`, `input` and `cacheRead`. Before transcripts,
the envelope's `usage` totals. **M7n, the notebook's own cost**, is the output tokens of
`notebook.write` calls (their args length divided by 4 as a proxy where usage is per
round), plus one round's cost when `notebook.write` was the only call in its round.

**M8. Rounds to first queue write.** The round index of the first `write:` call.

### 2.3 Notebook-quality metrics

These need `notebook_shown` on the runs row. The server renders in **both** arms and
returns the flags, while only the `on` arm is shown the block. That gives a
counterfactual for Q2.

**Q1. Stale at read.**
`stale_shown / shown`, over `on`-arm wakes. An entry is stale if the server flagged it
at render (`premise_false`, `tools_changed`, `charter_changed`), or if the role dropped
it in that same wake with reason `obsolete` or `wrong`. Also reported:
`auto_dropped / (auto_dropped + shown)`, the share the server removed before display
(expired, closed, met). A high value there is the system working, not a failure.

**Q2. `next` follow-through.** A shown `next` entry is **acted on** in that wake if any
of the following holds:
- its `tool` was called;
- a record written in the run references its `about` (`proposal_id`, `ask.proposal_id`,
  `serves` or thread);
- the role dropped it with reason `done`.

The rate is acted divided by shown. The **causal version** is the on-arm rate minus the
off-arm rate of "acted on" for the same rendered-but-unshown entries. This is the cleanest
evidence that showing the notebook changes behaviour. A `next` entry shown three times
and never acted on is counted as dead weight.

**Q3. Contradicted by live facts.**
`premise_false / premise_evaluable`, over shown entries with `assumes` or `until`. Plus
a **manual spot-check**: each week, 20 randomly drawn shown entries are labelled by a
human or an Opus reviewer against the archived briefing and the queue as supported,
contradicted, unverifiable or contains a fort fact. The spot-check covers unstructured
claims and number-in-words leaks. This is the memory architecture's "cross-check
narration against action" rule, kept out of the agent's own grading.

**Q4. Write discipline.** For `notebook.write`: the refused-operation rate by problem
code, adds per wake, merges, evictions, mean age at drop by reason, and the share of
`learned` entries flagged `tool_lesson`.

**Q5. Harm candidates.** On-arm wakes where the reasoning text names a shown entry id
whose flag was `premise_false`, and the wake then wrote a proposal that was rejected.
The count feeds kill rule K3. It is reviewed by hand, never auto-judged.

### 2.4 The baseline script (specified, to build first)

`dfqueue/wake_metrics.py`, run as `python -m dfqueue.wake_metrics`. It sits beside
`dfqueue/lessons.py` and `dfqueue/runs.py` so the publisher on the fort VM can import it
for the Board panel (3.6). It is pure functions plus a thin CLI.

```
python -m dfqueue.wake_metrics \
  --queue Uniboslan.sqlite3 --runs Uniboslan.runs.sqlite3 \
  [--archive <copy of the conductor archive dir>] [--epochs evals/live/<dir>/epochs.yaml] \
  [--since ISO] [--until ISO] [--roles architect,quartermaster,overseer] \
  --out metrics.json [--per-wake per_wake.jsonl]
```

- **Read-only.** Both databases are opened `mode=ro` (`read_runs_readonly`,
  `queue_records_readonly`). It never creates, migrates or writes a store. An absent
  `notebook_arm` column reads as null, so it runs against today's data unchanged.
- **Reuse, no re-implementation:** `schema.near_duplicate_reason` and
  `_normalise_words`, `runs.records_in_window`, and the `tools.yaml` read/write sections
  through the existing roster loader.
- **Output.**
  - `per_wake.jsonl`: one row per wake with every M and Q value, the role, arm, epoch,
    wake reason, and the data source of each field (`transcript`, `archive` or
    `missing`).
  - `metrics.json`: aggregates per role by arm by epoch (count, mean, median, a
    bootstrap 90% interval with 2,000 resamples and a fixed seed), and the
    pre-registered tests (3.4) once `notebook_arm` exists.
- **`epochs.yaml`**: a hand-maintained list of deploy timestamps that touched a role's
  charter, allowlist or wake policy (from `evals/live/` READMEs and the register). An
  epoch is the interval between two of them.
- **Tests** (fixtures, no live data): hand-built queue and runs databases with known
  answers for every metric. Each of these cases has its own test:
  - a repeat after rejection;
  - a parallel `serves` that is not a repeat;
  - a re-need after `completed` that is not a repeat;
  - a defer, defer with an answer in between (not a repeat);
  - redundant reads separated by a write (not redundant);
  - clipped args;
  - a run with no transcript (excluded and counted);
  - an absent column on an old runs database.
- **Side use:** the per-tool call counts it produces are what the register's
  2026-10-07 "cut every role's tools by evidence" row needs. Build them once.

The script comes before any notebook code. Its first output, on the data since
2026-10-05, is the descriptive baseline and goes into the experiment README.

## 3. Experiment design

### 3.1 Phases

| Phase | Mode (`notebook.mode` in policy) | Who writes | Who is shown | Purpose | Length |
|---|---|---|---|---|---|
| B0, historical baseline | absent | nobody | nobody | descriptive numbers on today's data (pre-cleanup), to size the problem | the script's first run |
| B1, post-cleanup baseline and shadow | `shadow` | the roles in the experiment | nobody | baseline after the wake cleanup; notebook quality (Q1, Q3, Q4) with no behavioural risk; the write's cost; a check that the roles can follow the format | 40 wakes of the three roles or 7 days of cycles, whichever is later |
| A/B | `ab` | all of them, both arms | the `on` arm | the causal estimate | until the target N, or the horizon (3.5) |
| After | `on` or `off` | per the verdict | | | |

**Starting condition:** the A/B starts only after the wake cleanup is deployed. The wake
cleanup changes the wake mix and the base rates, and a notebook measured against the
pre-cleanup world would be credited with the cleanup's effect. B1 also answers a
question worth asking before spending weeks: if the off-state repeat count R is below
0.05 per wake after the cleanup, the notebook's main case is gone. In that case the
decision goes back to the user before the A/B (section 6, question 1).

### 3.2 Randomisation unit: per wake, within role (not per role)

**Per role** (for example the Quartermaster gets a notebook and the Architect does not)
is rejected:
- there are three units, so there is no statistics at all;
- the roles' base rates differ several-fold (the Quartermaster produced the drink
  pile-up, the Architect barely proposes), so every difference is confounded with role;
- fort events and deploys hit roles differently, for example the tool cuts start with
  the Architect and Overseer.

**Per wake, within role** is chosen. Each wake of a role is assigned `on` or `off` by
**block randomisation**: blocks of 4 per role, two `on` and two `off` in random order,
from a seed committed in the pre-registration. It is drawn by the conductor at wake
time and recorded on the runs row (`notebook_arm`) before the run starts. This method
gives:
- balance at small N, like strict alternation, but without alternation's periodic
  confounds (an `open_ask` re-wake in the same cycle, or an Overseer that always follows
  an advisor, could line up with parity);
- the wake cleanup, fort changes, the Planner landing and tool cuts all fall on both
  arms in the same weeks. Analysis is stratified by role by epoch (3.4), so a deploy in
  the middle of the window cannot masquerade as an effect.

What the two arms share, so the only contrast is reading the notebook:
- the same charter, including the notebook paragraph. The charter is in the cached
  prefix and must not vary by arm, and an arm-specific charter would also break the
  cache;
- the same tools, the same write behaviour and the same render call;
- the `off` briefing carries one neutral line, "Notebook not shown on this wake." The
  charter promises a notebook, and silence would be a confusing cue. The line is fixed
  so it cannot carry information.

**Known contamination, both toward zero.** First, an `on` wake that avoids a repeat
leaves fewer pending items for the next `off` wake, so the effect leaks through the
queue. Second, the notebook an `on` wake sees includes entries written blind by `off`
wakes. Both make the A/B conservative: a measured effect is a lower bound. This is
stated in the report.

The Overseer is randomised as its own stratum. The Planner joins as a stratum once it
is live, but is not in the primary analysis because its wakes are seasonal and few.

### 3.3 Sample sizes, realistic for our wake rate

Observed variability (cross-run-cache table, 17 runs): rounds per wake were Overseer
13, 5, 5, 9, 7 and Quartermaster 9, 9, 7, 7, 7, 8, 14. On a log scale the coefficient of
variation is about 0.35. Waste events: 6 of 15 rulings in the audit window were defers,
4 of them repeats, and the Quartermaster's nine runs mostly concerned one fact. That
puts the pre-cleanup R at roughly 0.3 to 0.5 per wake, and the post-cleanup value is
unknown until B1, plausibly 0.1 to 0.3. These are rough figures, to be replaced by the
script's output.

Wakes needed per arm (one-sided alpha 0.05, power 0.8, normal approximations):

| Outcome | Effect to detect | Base rate | Per arm |
|---|---|---|---|
| Rounds per wake (M4, log scale) | 20% fewer | CV 0.35 | about 30 |
| Rounds per wake | 15% fewer | CV 0.35 | about 60 |
| Waste count R (Poisson rate ratio) | halved (0.5) | 0.4 per wake | about 100 |
| Waste count R | halved | 0.2 per wake | about 190 |
| Waste count R | 30% fewer (0.7) | 0.2 per wake | about 590 (not feasible) |

**Target: 120 wakes per arm pooled over the Architect, Quartermaster and Overseer, with
at least 30 per arm per role (240 wakes in total).** That target detects a 15% cut in
rounds with room to spare. It detects a halving of R only if the post-cleanup R is
around 0.3 or higher; at a lower rate the R verdict will usually be "inconclusive on
repeats", which the decision rule handles.

Calendar time for 240 wakes:

| Cadence | Wakes a day | Days |
|---|---|---|
| Hand-run, as observed (21 runs in 1.7 days) | about 12 | about 20 days of active cycling |
| Hand-run after the cleanup (fewer wakes, assume half) | about 6 | about 40 |
| Service running unattended (never measured) | 25 to 50 | 5 to 10 |

The honest reading: this experiment is cheap in money and expensive in calendar time
unless the conductor runs as its service. A hand-run A/B is still worth starting,
because the rounds result arrives within weeks and the R result follows later.

### 3.4 Pre-registered analysis, thresholds and decision rule

Written into `evals/live/<date>-notebook-ab/README.md` and committed before the first
`ab` wake. The commit hash is the pre-registration timestamp. Seed, block size, roles,
target N, horizon, thresholds and the exact script version (its commit) are all fixed
there. Any later change is a new, dated section and never an edit.

**Tests.**
- Stratified permutation tests (strata: role by epoch; 10,000 within-stratum shuffles of
  the arm labels, fixed seed), one-sided in the hypothesised direction.
- Effect sizes: the rate ratio for R, and the geometric-mean ratio for rounds, each
  with a stratified bootstrap 90% interval.
- Holm correction across the two primaries.
- **No early stopping for success.** Interim looks happen at 1/3 and 2/3 of the target
  N, for the kill rules only.

**Primary outcomes.**
- **P1, waste:** the rate ratio of R, `on` over `off`, is **at most 0.6** with Holm-adjusted
  p < 0.05, *and* the total R events across both arms are **at least 20**. If there are
  fewer than 20 events, P1 is "inconclusive on repeats" (too rare to judge), not a failure.
- **P2, efficiency:** the geometric-mean ratio of rounds per wake, `on` over `off`, is
  **at most 0.85** with Holm-adjusted p < 0.05.

**Guards** (non-inferiority; all must hold for success):
- G1, cost per wake (M7): the upper bound of the 90% interval of the `on`/`off` ratio is
  at most 1.15.
- G2, Overseer accept rate of advisor proposals: `on` is no worse than `off` by more
  than 15 percentage points (90% interval).
- G3, M2 repeat defers: `on` is not above `off` (rate ratio upper bound at most 1.5,
  given few events).
- G4, M6 pass rate on wakes woken by a crossed survival alert: `on` is not higher than
  `off` by more than 15 points.

**Notebook-quality floors** (from shadow and A/B together; they inform keep, change or
remove, separately from the primaries):
- Q1, stale at read: at most 20% of shown entries.
- Q3, premise contradicted: at most 10% of evaluable entries. Spot-check
  "contradicted or contains a fort fact": at most 2 in 20 per week.
- Q4, refused-operation rate after a role's first 20 writes: at most 20%.
- Q2, `next` follow-through: on-arm at least 30%, *and* on minus off at least 15
  points. Below this, the `next` kind is removed even if the notebook stays.

**Decision rule.**
- **Keep (mode `on` for all wakes):** (P1 succeeds) or (P1 inconclusive *and* P2
  succeeds), *and* all guards hold, *and* the quality floors hold. A quality floor
  missed with the primaries met means keep, with the offending kind removed or
  re-specified, and a short confirmatory A/B.
- **Remove:** P1 and P2 both fail to meet their thresholds, or any guard fails.
- **Inconclusive at the horizon** (target N not reached): the recommended default is
  **remove**. The burden of proof is on the notebook, which is what the user's condition
  asks for (section 6, question 2).

### 3.5 Kill rule and horizon

The kill rules are checked at each interim look. K3 and K5 are checked continuously by
the operator page.

- **K1, harm on the primary:** the R rate ratio, `on` over `off`, is at least 1.3, with
  at least 10 `on`-arm R events.
- **K2, wrong beliefs:** Q3 above 25% after at least 20 evaluable premises.
- **K3, acted on a false premise:** two Q5 harm candidates confirmed by hand review.
- **K4, cost:** the `on`/`off` cost-per-wake ratio is above 1.25 after at least 30
  wakes per arm.
- **K5, operator stop:** any death, critical vital or Overseer escalation whose
  transcript cites a notebook entry. Stop and review first, judge after.

A kill sets `notebook.mode: shadow`. That is one policy line, deployed under the
standing deploy authority. Writing continues for diagnosis, nothing is shown, and the
README records the kill and why.

**Horizon:** the target N, or 6 weeks of cycling after the A/B starts, whichever comes
first. At the horizon, whatever exists is analysed and reported; underpowered results
are labelled as such.

### 3.6 What the user sees, and where

- **Board, operator page, "Notebook experiment" panel.** It reads the script's
  `metrics.json`, recomputed by the publisher on its usual cadence, and shows:
  - the phase and mode, and wakes per arm per role against the target;
  - P1 and P2 point estimates with intervals, labelled "interim, not a verdict" until
    the horizon;
  - each guard and kill rule as green, amber or red;
  - the quality floors;
  - each role's current notebook with flags.

  It follows the UI preferences: one screen, tabs by role, minimal text.
- **Board, per run:** the collapsed NOTEBOOK panel (1.9), and the run's arm in the run
  header.
- **`evals/live/<date>-notebook-ab/`:**
  - `README.md`, with the pre-registration, an interim note at each look, and the final
    verdict against the rule in 3.4;
  - `epochs.yaml`;
  - the script's `metrics.json` and `per_wake.jsonl` at each look;
  - the weekly spot-check sheets.

  This is kept for the public report (the reporting-goal memory).
- **The register** gets one row at the start of the A/B (pre-registered, with a
  pointer) and one at the verdict. The orchestrator writes it, not the stream.

## 4. Staged build plan, tests and cost

Each stage is a separate executor stream on a worktree. Executors commit after each
milestone. No stage needs a VM until deploy.

| Stage | What | Touched surfaces | Tests | Depends on |
|---|---|---|---|---|
| **N0, metrics script** | `dfqueue/wake_metrics.py` and its CLI, as specified in 2.4. First run against read-only copies of the two databases (and optionally the archive) for the B0 baseline | `dfqueue/wake_metrics.py`, `dfqueue/tests/test_wake_metrics.py` | fixture databases with known answers for every M and Q metric (the cases in 2.4); a read-only guarantee (a test opens a database with no runs table and asserts it is not created) | nothing; **build now**, whatever is decided about the notebook |
| **N1, record and store** | the `notebook` kind in `schema.py` (fields, caps, digit rule, coordinate rule, reference checks, evidence rule, Overseer defer refusal, `tool_lesson` flag); `store.py` composition (operations onto the active version, near-duplicate merge, eviction, the `supersedes` check, expiry at compose); policy data `dfqueue/notebook_policy.yaml` (caps, kinds by role, expiry, merge threshold) | `dfqueue/schema.py`, `dfqueue/store.py`, `dfqueue/notebook_policy.yaml`, tests | one test per refusal and its repair text; a digit inside an id is allowed and outside is refused; eviction order; merge refreshes `watching` but not an unevidenced `learned`; expiry by wakes and by ticks, and under a frozen tick; compose is append-only and the old version stays readable | N0 not required |
| **N2, tools** | `notebook.write` (role from credential; tick, snapshot and run stamped; reply never echoes other entries' text); `notebook.render` (conductor-only; evaluates `assumes`/`until` through the fact reader `plan.write` uses, at most 6 reads per render; returns the rendered text plus the entry flags for `notebook_shown`); allowlists for the three roles plus the conductor; `conductor.report` start accepts `notebook_arm` and `notebook_shown`; runs DB migration adds the two columns, as the `thinking` and `transcript` migrations did | `dfmcp/notebook_tools.py`, `dfmcp/conductor_tools.py`, `dfqueue/runs.py`, `agents/*/tools.yaml`, `docs/STATE.md` counts | a role cannot write another role's notebook; render is refused to non-conductor credentials; a premise read failure gives "premise unreadable", never false; old runs databases migrate; full `dfmcp/tests` green | N1 |
| **N3, conductor** | a `notebook:` policy block (`mode: off\|shadow\|ab\|on`, seed, block size, roles); block-randomised arm assignment persisted in lane state so blocks survive restarts; one render call per woken role; the briefing key or block (1.6); the neutral off line; de-duplication against the wake cleanup's notes (1.10.1); one charter paragraph per participating role | `conductor/policy.yaml`, `conductor/policy.py`, `conductor/cycle.py`, `conductor/briefing.py`, `agents/*/role.md` | **cache test:** for the same inputs, the `on` and `off` prompts are byte-identical up to the first volatile byte (`game_tick`), and the charter is identical across arms; the block sequence is balanced in every block of 4 and reproducible from the seed; `mode: off` makes no render call and produces byte-identical prompts to today; a render failure degrades to "notebook unavailable", and the run goes ahead | N2, **and the wake cleanup merged** (both touch `policy.yaml`, `cycle.py`, `briefing.py`; one stream at a time per the handoff rules) |
| **N4, Board** | the per-run NOTEBOOK panel, the operator notebook and experiment panel, and the public projection with the withheld rule | `dfqueue/live.py` or `site_data.py`, the site templates | public projection drops unsafe entries and never edits them; the panel renders "interim" until the horizon; a `metrics.json` missing or older than a day shows as stale | N0, N2 |
| **N5, run it** | deploy N1 to N4 with `mode: shadow` (B1); after B1, write and commit the pre-registration README; switch to `mode: ab`; interim looks; verdict | `evals/live/<date>-notebook-ab/` | | all |

**Build cost.** Five Sonnet executor streams. N0 and N4 are each comparable to the
transcripts-capture stream. N1 plus N2 together are comparable to Planner P1a. N3 is
small but has to wait for the wake cleanup. Opus is needed only for a red team of
this design (the red-team memory) and for the verdict write-up.

**Runtime cost per wake.**
- The rendered block is at most about 800 tokens, uncached on round 1:
  800 x $0.435/M = $0.00035. On later rounds it is cache reads: 800 x 8 x $0.0036/M,
  which is negligible.
- The write is about 300 tokens of arguments plus up to about 500 of reasoning:
  800 x $0.87/M = $0.0007. It is parallel with the final write, so no extra round.
- When it does force an extra round: one cache re-read of a 60 to 100k prompt (about
  $0.0003) plus that round's output.
- Total: about $0.001 to $0.0015 per wake, which is 2 to 3% of the $0.051 mean wake
  (wake audit).
- One avoided round is worth about $0.003 to $0.005 (run-0023: about 3k output tokens
  per round, plus that round's new tool results uncached), so the notebook pays for
  itself at about 0.3 rounds saved per wake.

**Experiment cost.** The wakes would run anyway. The notebook's increment over 240 wakes
is about $0.30. The weekly spot-check is a few minutes of human or Opus time.

## 5. Risks and mitigations

| Risk | Mechanism | Mitigations (mechanical first) | Measured by |
|---|---|---|---|
| **Self-reinforcing wrong beliefs** | A role writes "X does not work", sees it next wake, never tries X, and renews it; the belief outlives the fix that made it false (the Laban lock-in, at notebook scale) | `because` required for `learned` and `avoid`, and renewal only with *newer* evidence (1.4.5); hard expiry in wakes and ticks (1.5); `tools_changed` and `charter_changed` flags; structured `assumes` re-checked live at every render; the "hypotheses, not facts" label; the Overseer still rules on every action against server-refreshed citations, so a wrong belief can waste a wake but cannot act on the fort | Q1, Q3, Q5; K2, K3; mean age at drop |
| **The notebook becomes fort state** | Agents write stock levels and counts, which go stale between wakes | The digit rule; the structured `until` and `assumes` instead of numbers in prose; fort numbers appear only as server reads at render; the weekly spot-check catches numbers written in words | the Q3 spot-check; Q4 refusal codes |
| **Prompt-cache damage** | Notebook content or an arm difference landing before the first volatile byte | Briefing-only placement after `game_tick` (1.6); never in the charter; the arm toggles only briefing bytes; the N3 byte-identity test; the one charter paragraph batched into another deploy | per-round `cacheRead` in transcripts, on and off arms compared (round 1 should not differ) |
| **Noise and small samples** | Few wakes, rare events, many metrics, and the temptation to read an interim number as a verdict | One pre-registered primary per question; Holm; stratified permutation; a minimum event count before P1 can pass; no early success stop; "inconclusive" allowed, defaulting to remove; the operator panel labels interim numbers | the README's analysis log |
| **Confounding** | The wake cleanup, tool cuts, Planner arrival and fort events shift the base rates | Start after the cleanup; within-role randomisation in the same weeks; strata by epoch; `epochs.yaml` | per-epoch tables in `metrics.json` |
| **Contamination between arms** | An effect leaking through the queue, and blind writes | Accepted: it biases toward zero, and is stated in the report | none (bias direction known) |
| **Goodhart** | Fewer repeats achieved by passing on real problems | G4 (passes on survival-alert wakes); G2 (acceptance rate) | G2, G4 |
| **Write overhead** | Refusal loops, or an extra round every wake | Partial success (one bad operation does not fail the others); repair text; the charter says call it alongside the final write; K4 | M7n, Q4 |
| **Duplication with other stores** | Plan, notes, gotchas and rulings restated in the notebook | The rules in 1.10, enforced at write and render | the share of `tool_lesson` flags; Overseer defer refusals |

## 6. Open questions for the user

1. **If the post-cleanup shadow baseline shows almost no repeats (R below 0.05 per
   wake), do we still run the A/B?** *Recommendation: yes, but on rounds per wake
   only, at the smaller 60-per-arm target.* The notebook's remaining case would be
   efficiency, which is cheaper to test, and repeats then stay a guard. If you would
   rather not build a feature whose main problem has been fixed upstream, the
   alternative is to stop after N0 and the shadow phase.
2. **What happens if the result is inconclusive at the horizon?** *Recommendation:
   remove it.* That is the reading of "make me confident it's effective": the notebook
   stays only if it shows a gain.
3. **Should the A/B wait for the conductor to run as its service?** *Recommendation:
   start it hand-run once the wake cleanup is live, and accept a three-to-six-week
   calendar.* The rounds result comes first; waiting for the service would make it
   take days instead, but would add an unrelated change to the same window.
4. **Should notebooks be public on the Board?** *Recommendation: yes, collapsed and
   filtered, as transcripts are* (register, 2026-10-07). They are among the more
   readable artefacts for the public report.

## 7. Not verified

- All live numbers are quoted from today's three research files. None were re-measured,
  because no database was opened. Rounds variance comes from 17 envelopes and two
  transcripts. The post-cleanup waste rate is a guess bracketed in 3.3.
- That openclaw on DeepSeek reliably issues `notebook.write` in parallel with the final
  queue write. Parallel calls are seen in transcripts, but not for this pairing. If it
  does not, M7n will show one extra round on most wakes and the cost figure roughly
  doubles. That is still under K4.
- That the fact reader `plan.write` uses can evaluate every live signal named in an
  `assumes`. Signals it cannot read render as "premise unreadable" and count as not
  evaluable.
- The wake cleanup's final shapes (`notes`, `fact` keys, the answer note) are taken from
  its handoff and the audit's section 5. The de-duplication in 1.10.1 depends on the
  `fact` key existing as specified.
- Sample-size figures use normal approximations, a rounds CV of 0.35 from few runs, and
  Poisson R. A permutation test's real power at these N will differ somewhat.
