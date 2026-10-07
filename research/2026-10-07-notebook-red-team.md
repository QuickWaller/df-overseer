# Notebook design: red-team review

Date: 2026-10-07. Reviewer: independent Opus pass, not the author of
`research/2026-10-07-notebook-design.md` (commit `cab94cb`). Review only: no code
changed, no VM touched, no database opened, nothing deployed. Every live number is
quoted from the design, `research/2026-10-07-wake-audit.md` or
`research/2026-10-07-persistent-sessions.md`; the arithmetic below is mine and is
shown so it can be checked.

The user's bar: "make me confident it's effective and have measurable methods of
improvement". This review attacks chiefly the evaluation, because that is what the
bar is about.

## 0. Verdict

**N0 (the metrics script): go, with the changes in section 3. N1 onward: not yet.**

The notebook itself is a reasonable, well-guarded design. The evaluation, as
written, cannot deliver the confidence the user asked for:

- the A/B compares "shown" against "written but not shown", so no arm is the
  no-notebook world the keep/remove decision is about, and both cost guards are
  blind to the writing overhead (finding 1);
- the primary the user cares about (repeat proposals, R) is clustered in
  episodes and its post-cleanup rate is unknown, so it is very unlikely to be
  testable at our wake rate (finding 2);
- the secondary primary (rounds) has a pass threshold that a true 15% effect
  meets only about half the time (finding 3);
- the guards are phrased as non-inferiority proofs that cannot be proven at
  these sample sizes, so "all guards must hold" makes "keep" close to
  impossible regardless of the truth (finding 4);
- the repeat metric M1 has never been checked against a known positive
  (finding 5).

There is also a cheaper intervention the design does not consider, which goes
straight at the cause of repeat proposals: advisors are never shown their own
past proposals or the rulings on them (finding 6). It needs no model writes,
cannot go stale, and can be tested with the same N0 script and arm machinery.
**Recommended order: N0, then the wake cleanup, then a go/no-go gate on
post-cleanup data, then an A/B of a server-derived "your recent filings" block,
and only then a reduced notebook (`next` and `watching` only) if a measured
residual remains.**

## 1. Findings

Severity: **Critical** (the evaluation cannot answer its question as written),
**High** (a wrong answer or a broken deploy is likely), **Medium** (a measurable
bias or a cost misstatement), **Low** (a definitional fix).

### 1. Critical: no arm is "no notebook"; the cost guards cannot see the write cost

**Evidence.** Design 3.2 (lines 547 to 551): both arms share "the same tools, the
same write behaviour and the same render call", and both arms write (3.1 table,
line 515). G1 (line 627) and K4 (line 664) are `on`/`off` cost ratios. The writing
overhead (the `notebook.write` call, its reasoning, and any extra round it forces)
is paid in **both** arms, so it cancels out of every on/off comparison. The design
itself says the parallel-call assumption is unverified and that an extra round on
most wakes is possible (lines 776 to 779).

**Why it matters.** The decision at the end is "notebook on for all wakes" versus
"removed entirely". The A/B estimates only the effect of *showing* a notebook to a
role that is already *writing* one. The cost of writing, and any behavioural effect
of being told to keep a notebook (the charter paragraph, a reflective end-of-run
call), is never contrasted with anything. A notebook could pass every A/B test while
adding a round to every wake.

**Fix.**
- Measure the write overhead directly, against a no-notebook baseline: rounds,
  cost and wall clock per wake in the post-cleanup N0 baseline (no notebook code
  deployed) versus the shadow phase, within role and wake reason. This is a
  before/after comparison, so it is confounded with time; keep it short
  (adjacent windows) and say so.
- Add a pre-registered **write-overhead guard**: the share of wakes where
  `notebook.write` was the only call in its round (M7n's extra-round flag) at most
  20%, and the median added wall clock at most one round.
- Restate the keep rule as: the measured benefit of showing (P1 or P2) exceeds the
  measured cost of writing (M7n plus extra rounds), not only "on is not costlier
  than off".

### 2. Critical: R is very unlikely to be testable at our wake rate

**Evidence.**
- Design 3.3 sizes R as Poisson with independent wakes: about 100 per arm at
  0.4 per wake, 190 at 0.2 (I reproduce both: `n = (1.645 + 0.842)^2 x
  (1/l1 + 1/l0) / ln(RR)^2`, 96.5 and 193).
- R events are not independent. The wake audit's main finding is an *episode*:
  nine Quartermaster runs about one fact, drink 0 (audit 1.1), and two proposals
  each deferred three times in a row (audit 1.2). Clustered counts are
  overdispersed; the needed N scales by roughly the mean events per episode. With
  episodes of three to six events, 190 per arm becomes something like 500 to
  1,000 per arm.
- The wake cleanup exists to remove exactly these episodes (coalescing one wake
  per fact, defers as notes, `prediction_graded` to the proposer). The audit
  classes 8 reasons REMOVE and 7 WARNING, so "half the wakes after the cleanup"
  (design 3.3, line 596) is optimistic. The audit itself warns "Rates are not
  rates": the 21 runs in 1.7 days were hand-run cycles under an operator hold
  (audit section 2).
- The event floor (P1 needs at least 20 events in total, line 621) at a
  post-cleanup R of 0.1 over 240 wakes gives about 24 events if nothing changes,
  fewer if the notebook works.

**Why it matters.** The most likely P1 outcome is "inconclusive on repeats", and
the user's actual problem then goes unmeasured while four build streams are spent.

**Fix.**
- **Gate before N1, not after the shadow phase.** The R-below-0.05 check
  (line 521) needs no notebook code: N0 on post-cleanup data computes it. Pre-
  register a power projection from N0's measured rate and its dispersion
  (episodes per fact), and build N1 to N3 only if the projected power for P1 or
  P2 at the horizon is at least 0.5.
- **Use an at-risk denominator.** Count R only on wakes where a repeat is
  possible: the role has a same-type proposal of its own that is open or was
  rejected within the window. This raises the base rate and removes wakes that
  carry no information about repeats.
- **Cluster-aware analysis.** Bootstrap by cycle (or by fact episode where the
  cleanup's `fact` key exists), not by wake; permute arm labels within the actual
  randomisation blocks of 4, which is the real assignment mechanism, rather than
  free shuffles within role-by-epoch strata (line 611).

### 3. High: P2's point threshold makes a true 15% effect a coin flip

**Evidence.** P2 (line 623) needs the geometric-mean ratio "at most 0.85" *and*
p < 0.05. With a true ratio of exactly 0.85, the estimate falls at or below 0.85
half the time, whatever N is. The design's claim that 120 per arm "detects a 15%
cut in rounds with room to spare" (line 586) is true of the significance test, not
of the decision rule. At a true 0.80 and 120 per arm (SE of the log ratio about
0.35 x sqrt(2/120) = 0.045), P(estimate at most 0.85) is about 0.91.

The CV is also not one number. From the design's own rounds (line 568), log-scale
standard deviations are about 0.41 for the Overseer (13, 5, 5, 9, 7) and 0.25 for
the Quartermaster (9, 9, 7, 7, 7, 8, 14). The Overseer stratum needs roughly 80 per
arm, not 60, for a 15% effect.

**Fix.** Pre-register a minimum worthwhile effect (say 10%) as the point threshold
and size for a plausible effect (20%); or decide on the interval (upper 90% bound of
the ratio below 0.95). Add covariate adjustment for wake reason and briefing length
(a CUPED-style regression on pre-run covariates), which costs nothing and reduces
variance, since round counts depend heavily on why a role was woken.

### 4. High: guards phrased as non-inferiority proofs cannot hold at this N

**Evidence.**
- G2 (line 629): "on no worse than off by more than 15 points (90% interval)".
  With about 50 advisor proposals per arm and an accept rate near 0.6, the 90%
  half-width of the difference is 1.645 x sqrt(0.24 x 2/50) = 0.16. The interval
  is wider than the margin, so G2 cannot be shown to hold even with no effect.
- G3 (line 631): after the cleanup the design expects M2 near zero in both arms
  (line 376), so a rate ratio and its upper bound are undefined or unbounded.
- G4 (line 633): pass rate on wakes woken by a crossed survival alert. The audit
  records one `alert_crossed` run (audit section 2 ledger). There will be a
  handful at most.
- The decision rule requires "all guards hold" (line 646). Read literally, keep is
  unreachable; read loosely, the guards are vacuous.

**Fix.** Make guards harm detectors, not proofs: a guard **fails** only when the
evidence shows harm (the lower bound beyond the margin, or a hand-confirmed case),
and is reported as **not evaluable** below a stated minimum count. Review G4 case
by case: every alert-woken wake in the `on` arm is read by hand, which is cheap
because there are few. Drop K1's "10 on-arm events" kill (line 660), which will
rarely be evaluable; K3 and K5 already cover acute harm.

### 5. High: M1 has never been checked against a known positive

**Evidence.**
- M1 reuses `schema.near_duplicate_reason` (`dfqueue/schema.py:542-565`): summary
  word-set Jaccard at least 0.75, or a sequence ratio at least 0.85 on the summary
  or rationale. These thresholds were chosen to flag a duplicate to the Overseer
  (`schema.py:519-536`), that is, for precision. A model that rephrases each wake
  will slip under them. Nobody has run the rule over the 2026-10-05/06 window,
  where the positives are known (the Quartermaster's drink orders, "the same three
  orders each time"; `proposal-0017` and `proposal-0020`).
- M1 adds `a.role == b.role` (design line 352), but the server's rule is
  cross-role (`dfqueue/store.py:427-457` filters by type only; the originating
  case, `proposal-0009` duplicating `proposal-0007`, was across advisors). M3
  (`duplicate_of` not null, line 380) is cross-role. R therefore mixes in
  cross-role duplicates the per-role notebook cannot affect.
- "Accepted with its project not closed `completed`" (line 358): accepted
  proposals of unrouted types have no project (legacy execution,
  `store.close_legacy`), so a legitimate re-order after a fulfilled one counts as
  a repeat for 7 days.
- The 7-day window is wall time. Under a hold the tick freezes; under the service
  7 days is many seasons. Neither matches the role's experience.
- The rationale-ratio path can match two different proposals that share
  boilerplate rationale.

**Fix.** Before pre-registration, hand-label every proposal pair of the same role
and type in the 2026-10-05 onward data as repeat or not, and report M1's precision
and recall against it (and M1-wide's). Pre-register whichever has acceptable recall,
or a hand-labelled primary if neither does. Restrict M3 to same-role
`duplicate_of`. Count an accepted proposal as completed when it has an `executed`
record or a prediction graded true. Use a window in the role's own wakes (say 10)
or game ticks, not wall days.

### 6. High: a simpler intervention goes straight at the cause, and is not considered

**Evidence.** Advisors are never shown their own filings. `build_briefing` gives
them `queue.count` and pending ids only (`conductor/briefing.py:181-187`), drawn
from all roles' pending proposals (`conductor/cycle.py:243-261`). No advisor
allowlist holds a queue read for proposal history or rulings (`agents/quartermaster/tools.yaml`
read section, lines 35 to 179; the Architect has only `queue.project_status`). A
rejected proposal leaves the advisor's view entirely. The Overseer, by contrast,
gets "DECIDED, DO NOT REDO" with the last rulings and reasons
(`briefing.py:308-323`). The wake cleanup's `ruling_on_own` note (audit row 9) shows
a verdict once, for a few cycles.

The design's `learned` and `avoid` kinds must cite an existing record as evidence
(line 129). Those records already exist and the server can show them; the model
does not need to restate them.

**Fix.** Build first a server-derived block, **YOUR RECENT FILINGS**, for advisors:
the role's own proposals in the last N own wakes with type, summary, status
(pending, deferred with reason, accepted, rejected with reason), `duplicate_of`,
and open asks with answers. It is the advisor analogue of DECIDED, DO NOT REDO.
It has no model write, no new record kind, no digit rule, no expiry, and cannot be
stale, because the server builds it from the queue each wake. It targets M1's
`open` and `after_reject` repeats directly. It can be A/B tested with N0, the
same per-wake arm assignment and the same pre-registration, at a fraction of the
build cost (one conductor stream). The notebook then has only a residual to
explain: intent (`next`, `watching`), which a reduced notebook can test.

### 7. High: a new record kind crashes the publisher unless N1 touches the feed

**Evidence.** `dfqueue/feed.py:720-725` (`build_public_item`) and `feed.py:788-791`
(`build_operator_item`) raise `ValueError` on any kind not in `KNOWN_KINDS`, by
design ("a new kind needs its own public/operator rendering added here"). N1's
touched surfaces (design line 710) are `schema.py`, `store.py` and the policy file;
the feed is only in N4 (line 713). The shadow phase deploys N1 to N3 (line 714) and
the first `notebook` record would break the Board feed.

**Fix.** N1 adds `notebook` to `KNOWN_KINDS` with a public renderer that returns
`None` (withheld) and an operator renderer, plus `compute_reply_to`, with a test
that the publisher survives a notebook record. N4 later replaces the withheld
rendering with the filtered one.

### 8. High: a parallel `notebook.write` cannot point at the proposal it accompanies

**Evidence.** Section 1.7 calls `notebook.write` "in the same round as the role's
final queue write" (line 224). The natural `watching` entry ("whether the order I
just filed clears") needs `about` to name that proposal, and `about` must resolve to
an existing record (line 125). In a parallel call the model does not yet know the
new id, and the two calls race for the queue write lock
(`dfmcp/queue_tools.py`, module docstring "writes are serialised"). So either the
entry has no `about`, or the model spends a second round.

There is also a repo precedent that DeepSeek drops trailing duties: an Overseer
told to "stop when each has a ruling" left an accepted brew unexecuted
(`briefing.py:214-218`). An optional end-of-run call is the same shape.

**Fix.** Allow `about: "this_run"`, resolved by the server after the run to the
records the role wrote in the open run (the same `records_in_window` join the runs
store already uses). Add **Q0, write compliance**: the share of wakes with a
successful `notebook.write`, with a shadow gate of at least 80%. Measure the
extra-round rate in shadow (finding 1's guard).

### 9. Medium: the cost of an extra round is understated

**Evidence.** Line 779 says an extra round makes "the cost figure roughly double".
The design's own figure for one round is $0.003 to $0.005 (line 731), against a
notebook cost of $0.001 to $0.0015 (line 729). An extra round on most wakes makes
the total about $0.004 to $0.006 per wake, 8 to 12% of the $0.051 mean, and adds
about 35 seconds of wall clock (Overseer mean 317 s over 5 to 14 rounds, audit
section 2). The audit's own conclusion is that the case for trimming is "wall
clock, rounds and proposal churn, not spend". "Pays for itself at 0.3 rounds saved"
(line 733) becomes about one round saved.

**Fix.** Correct the figure; make the extra-round rate a shadow gate (finding 8).

### 10. Medium: contamination is not all toward zero, and the off arm leaks

**Evidence.**
- The estimand is the effect of showing on one wake inside a mixed history. The
  benefit the notebook claims is cumulative (a `next` written by a sighted wake,
  acted on by the next sighted wake, dropped as `done`). With 50% assignment,
  half the chains are broken. Together with "inconclusive means remove", every
  bias in the design points the same way, toward removal. That may be acceptable
  under the user's bar, but it should be stated, not described as "conservative".
- The off arm's reply carries `merged: [{text_index, into}]`, `evicted: [ids]` and
  `counts_by_kind` (line 234). "Your add merged into qm-note-0004" tells a blind
  wake that it already noted this. It matters if the model calls the tool before
  acting, which models do.
- The de-duplication rule (line 311) appends "(you are watching this:
  qm-note-0004)" to a conductor note. If applied in both arms, the off arm sees
  its notebook.
- Overseer outcomes (M2, G2) depend on the arms of the advisor wakes whose
  proposals it rules on, in the same cycle (`cycle.py:861-880`: advisors are
  briefed and run before the Overseer's ruling prompt is built from
  `queue.pending_brief`).

**Fix.** Off-arm reply: `{version, accepted, refused}` only. Annotations on notes
in the on arm only, with a test. Analyse the Overseer as a secondary stratum with
the advisor arm of each ruled proposal as a covariate, or leave it out of the
primary. Optionally, a switchback design (alternating blocks of wakes per role,
first wake after a switch discarded) estimates the cumulative effect at the cost of
time confounding; marketplace experiments use it for exactly this carryover
problem. At minimum, report the chain-length distribution of on-arm runs.

### 11. Medium: the shadow phase measures less than it claims

**Evidence.**
- The phase table says shadow measures Q1, Q3 and Q4 (line 514). Q1 is defined
  over on-arm shown entries and counts drops "with reason obsolete or wrong"
  in the same wake (line 427), which a blind writer cannot do. Q1 is not
  computable in shadow.
- A blind notebook is never curated: every wake adds, nobody drops or renews, the
  caps fill and evict. Its stale rate and premise-false rate describe a notebook
  that will not exist in the on state.
- Shadow is also used as the "post-cleanup baseline" (line 514), but every shadow
  wake writes, so it is a baseline with the write overhead in it (finding 1).

What shadow does measure, and is worth measuring: whether DeepSeek calls the tool
at all, refusal codes and repair loops, render errors, the write's real token
cost, and the extra-round rate.

**Fix.** Recast shadow as an operational shakedown with explicit pass gates (Q0 at
least 80%, refused-operation rate at most 20% after the first 10 writes, extra-round
rate at most 20%, zero render failures that block a run), at about 20 wakes rather
than 40 wakes or 7 days. Take the baseline from N0 before any notebook code ships.

### 12. Medium: what is stored will undercount exactly the calls the notebook adds

**Evidence.**
- `build_transcript` drops whole *later* rounds until the JSON fits
  `max_total_chars` (60,000; `conductor/runner.py:131-137, 256-261`). The final
  round, where `notebook.write` and the final queue write live, is the first to go
  on a long run. M7n, Q2's "tool was called", M5, M8 and per-round token sums all
  undercount on long runs; M4 is safe because it adds `omitted_rounds`.
- The tool-call block shapes are "UNVERIFIED against a live run"
  (`runner.py:200-205`). If openclaw's call blocks are not in `_CALL_TYPES`, every
  `calls` list is empty and M5, M8 and Q2 silently compute zero.
- Call names in openclaw output are wire-form (`df-overseer__queue__propose`,
  `cycle.py:404-410`); `tools.yaml` holds ids (`queue.propose`). M5's read/write
  classification needs the inverse of `conductor/mcp_client.py:39-43 tool_name`
  plus the server prefix.
- The runs table keeps 500 rows across all roles (`dfqueue/runs.py:40, 201-204`);
  at the service cadence the design projects (25 to 50 wakes a day, line 597),
  rows older than 10 to 20 days are deleted before the verdict.
- `cost_usd` is None for killed runs (`runner.py:360-362`), so G1 and K4 drop
  timeouts, and the Architect has timed out at 607 s twice (audit row 21).
- `wake_reason` keeps the first reason only (audit finding 8) until the cleanup
  lands, so stratifying or adjusting by wake reason needs the cleanup's full list.

**Fix.** N0 asserts, on run-0022 and run-0023, that `calls` are non-empty and map
to allowlist ids, and fails loudly otherwise. Record `notebook.write` presence and
its outcome on the runs row at `end` (from the server's own write log, not the
transcript). Each interim look writes an append-only `per_wake.jsonl` snapshot into
`evals/live/`, so pruning cannot lose experiment rows. Count timeouts by arm as
their own outcome. Exclude `notebook.write` from the "write call" definitions in
M5 and M8, or the first write is the notebook.

### 13. Medium: epochs will be too many and hand-maintained

**Evidence.** Analysis is stratified by role by epoch from a hand-written
`epochs.yaml` (lines 488 to 490). Deploys are frequent and now run under standing
authority (memory `standing-deploy-authority`, 2026-10-05); the register's
"cut every role's tools by evidence" row (design line 501) plans allowlist changes
for the same roles; Planner P1b is in flight (commit `37bc610`, "wip: planner P1b,
cycle wiring") and adds a `plan` slice to every advisor briefing plus `serves`,
which changes M1 by definition (parallel `serves` are excluded, line 353). Many
epochs make small strata; a stratum with one arm contributes nothing.

**Fix.** Stamp `charter_hash`, `tools_hash` and `policy_hash` on each runs row at
`start`, and derive epochs from them, not from memory. Declare a change freeze on
the three roles' charters, allowlists and wake policy for the A/B window, kill
switches and safety fixes excepted. Start the A/B after the Planner's P1 is live, or
pre-declare its arrival as an epoch boundary and report the two halves.

### 14. Medium: the premise machinery covers few real entries

**Evidence.** `until` and `assumes` must be live signals (line 127). The vocabulary
is fifteen kinds (`learning/live_signals.py:223-228`): population, alert and
stuck-job counts, landmark checks, four stock counts, `order.exists`,
`stocks.availability.units`, three zone counts. The design's own examples,
`drink_per_citizen >= 1` and `empty_barrels < 1` (lines 95 to 98, 207 to 209), are
not in it. The example lesson "the Overseer rejects a second brew order while one
is open" has no expressible premise at all. So Q3 and K2, the main stale-belief
measures, cover a minority of entries, and Q5 relies on the model naming an entry
id in reasoning that is clipped to 2,000 characters per round (`runner.py:245`).

**Fix.** Use only real signals in examples and tests, and report premise coverage
(entries with an evaluable premise over all entries) as its own number. Make Q5
mechanical: an on-arm proposal whose text near-duplicates a shown `avoid` entry, or
that relies on an entry flagged `premise_false`, and is then rejected, is a harm
candidate. Hand review stays as confirmation.

### 15. Medium: "inconclusive means remove" is right in principle and ambiguous in wording

**Evidence.** Line 651: "Inconclusive at the horizon (target N not reached)",
remove. Line 621: "inconclusive on repeats" means fewer than 20 events. These are
two different meanings. A significant P2 at the horizon with N short of target reads
as both "inconclusive" and "succeeded".

**Assessment.** Removal on no evidence matches "make me confident it's effective".
But together with findings 2, 3, 4 and 10, the design's prior probability of a
"keep" verdict is low, so the build order matters more than the rule: spend on the
cheap test first (finding 6).

**Fix.** Define the horizon analysis as the pre-registered final look:
significance at the horizon counts whatever N is; "inconclusive" means only "not
significant and not harmful". Keep remove as the default for that case.

### 16. Low: the digit rule blocks some legitimate ids and does not stop number words

**Evidence.** The allowed tokens are record, run, gotcha and doctrine ids matched by
one id pattern (line 112). Blueprint template ids carry digits
(`blueprints/templates/bedroom-cell-v1.yaml`, `office-room-v2.yaml`), and plan target
ids are free strings chosen by the Planner (`dfqueue/plan.py:273-280`). An Architect
lesson naming a template is refused. Number words pass (line 117), and a refusal
whose repair text says "name the signal, not its value" will often teach the model to
spell the number out.

**Fix.** Allow a digit-bearing token when it resolves to a known id (record, run,
gotcha, doctrine, template, plan target, tool), by lookup, not by regex. Refuse
cardinal number words (zero to twenty, hundred, dozen) as well, with the same repair
text, and count both refusal codes in Q4. Tool ids carry no digits today (checked
across `agents/*/tools.yaml`), so they are unaffected.

### 17. Low: metric definitions to tighten

- **Q2** counts "dropped with reason `done`" as acted on (line 438); the off arm
  cannot drop what it cannot see, so the causal on-minus-off difference is
  inflated. Exclude that criterion from the causal version.
- **Q3**'s denominator includes entries with only `until` (line 446); an unmet
  `until` is the normal state, not a contradiction. Use `assumes` only.
- **Q1** counts `tools_changed` and `charter_changed` flags as stale (line 427).
  Every deploy then flags every entry, so Q1 tracks deploy cadence. Report Q1 with
  and without deploy flags; the floor applies to the version without.
- **M2**'s "changed" (lines 368 to 373) omits a changed cited value except with
  `--archive`, but the cleanup re-wakes the Overseer on a deferred proposal
  precisely when a citation changes (`handoffs/2026-10-07-wake-cleanup.md`
  item 1). M2 would count those legitimate re-rulings as repeats. Reuse the
  cleanup's own defer-change test, and record the edge cause on the runs row.
- **M5** treats any later read with equal args as redundant unless a `write:` call
  intervenes. Advisor `write:` sections hold only queue writes
  (`agents/quartermaster/tools.yaml:180-201`), and a running fort changes between
  reads. Restrict M5 to runs where the fort was paused, or report it as an upper
  bound.

### 18. Low: the prompt-cache claims hold

Checked: the advisor briefing is `json.dumps` of a dict whose second key is
`game_tick` (`briefing.py:167-170`, `cycle.py:870`); the Overseer's first line
carries the tick (`briefing.py:295`). A block placed last in either cannot move the
cross-run prefix. Two small corrections: adding `notebook.write` to the allowlists
changes the tool schemas in the system prefix once, alongside the charter paragraph;
and the persistent-sessions study found round 1 reads 0 or 1,408 cached tokens anyway
(persistent-sessions 3.1), so there is little cross-run cache to protect today. Keep
the charter identical across arms for a clean contrast, not for the cache.

## 2. On the specific questions asked

- **Are the metrics computable from what is stored?** Mostly yes; the queue fields
  M1 to M3 use exist (`schema.py:416-436`: `type`, `summary`, `rationale`,
  `prediction`, `cited`, `duplicate_of`, `serves`; rulings carry `decision`,
  `proposal_id`, `reason`), and the runs table carries `records_json`, `cost_usd`
  and `transcript` (`runs.py:44-62`). The gaps are in finding 12: late rounds
  dropped, call shapes unverified, wire names, pruning, killed-run cost, and no
  per-run hashes or arm columns yet.
- **Is M1's equivalence rule sound?** Plausible but unvalidated, inconsistent with
  M3 on role, and wrong for legacy accepted work (finding 5).
- **Can the arms leak?** Yes, through the write reply, the note annotation, the
  queue and the Overseer (finding 10). The queue leak is mostly toward zero; the
  others are fixable.
- **Is the sample size realistic?** For rounds, roughly, at about 80 per arm per
  stratum. For R, no, at our wake rate (finding 2).
- **Thresholds and kill rule?** P2's point threshold and the guards need rework
  (findings 3 and 4); K1 and K4 add little; a write-overhead kill is missing
  (finding 1).
- **Confounders?** Cleanup and Planner both land near the window, deploys are
  frequent; stamp hashes and freeze (finding 13).
- **Inconclusive means remove?** Right default, but wording and build order need
  fixing (finding 15).
- **Does shadow measure anything?** Operational fitness, yes; quality and baseline,
  not as claimed (finding 11).
- **Digit rule?** Blocks template and target ids; does not stop number words
  (finding 16).
- **Prompt cache?** Sound (finding 18).
- **DeepSeek tool-call reliability?** Unverified for this call and pairing, with a
  repo precedent of trailing duties being dropped (finding 8). Measure Q0 in shadow.
- **Cost?** Fine if parallel; 3 to 4 times the stated figure if not (finding 9).
- **Simpler design?** Yes: the server-derived recent-filings block (finding 6).

## 3. Changes required

### Before N0 (metrics script)

1. Assert transcript call parsing on run-0022 and run-0023, and map wire names to
   allowlist ids (finding 12).
2. Hand-label the 2026-10-05 onward proposal pairs and report M1 and M1-wide
   precision and recall; restrict M3 to same role; fix the legacy-accept rule and
   the wall-clock window (finding 5).
3. Reuse the cleanup's defer-change test for M2 once it exists (finding 17).
4. Add the at-risk denominator for R, cluster bootstrap by cycle, and block-wise
   permutation (finding 2).
5. Add dispersion and power projection output: events per episode, projected power
   for P1 and P2 at the horizon given the measured rate (finding 2).
6. Write append-only `per_wake.jsonl` snapshots to `evals/live/` at each run
   (finding 12).

### Gate between N0 and N1

7. After the wake cleanup is live, run N0 on post-cleanup wakes. If projected power
   for both primaries at the horizon is below 0.5, stop and take it back to the user
   (finding 2).
8. Build and A/B the YOUR RECENT FILINGS block first, with the same pre-registration
   discipline (finding 6). Build the notebook only for a measured residual.

### Before N1 (if the notebook proceeds)

9. Reduce v1 to `next` and `watching`; drop `learned` and `avoid` in favour of the
   filings block and gotchas (finding 6). Keep `assumes` only on real signals
   (finding 14).
10. `notebook` in `KNOWN_KINDS` with withheld public rendering, in N1
    (finding 7).
11. `about: "this_run"`; Q0 write compliance; minimal off-arm reply; on-arm-only
    note annotation (findings 8 and 10).
12. Digit rule by id lookup, plus number words (finding 16).
13. Runs row: arm, `notebook.write` outcome, `charter_hash`, `tools_hash`,
    `policy_hash` (findings 12 and 13).
14. Rewrite the pre-registration: P2 threshold or interval rule; guards as harm
    detectors with a "not evaluable" state; a write-overhead guard; horizon
    wording; change freeze; Overseer as a secondary stratum; corrected cost
    (findings 1, 3, 4, 9, 13, 15).
15. Recast shadow as a short shakedown with pass gates (finding 11).

## 4. Not verified

- No database was opened, so M1's actual recall on the known window, R's real
  dispersion and the post-cleanup wake rate are unknown; the sample-size
  corrections above are arithmetic on the design's and audit's numbers.
- Whether real transcripts contain parsed `calls` (finding 12) was not checked; the
  design says parallel calls "are seen in transcripts", which suggests they do.
- The overdispersion factor (three to six events per episode) is inferred from the
  one drink episode and the two triple defers; it may be smaller after the cleanup.
- That the recent-filings block reduces repeats is a hypothesis, which is why it is
  proposed as an A/B, not as a fix.
