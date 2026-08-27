# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.

## 2026-08-27 (evening) - fort ledger built

**The build-order item named three times is done.** `ledger/` holds the schema,
a validating write path, stratification, a coverage report, and a selftest.
`python -m ledger.selftest` passes all checks; `python -m ledger.report` runs.
Six entries in `decisions/DECISIONS.md` 2026-08-27 record the design calls.

**What it is:** JSONL, one row per fort, git-tracked. `forts.jsonl` is empty
and stays that way until the game side exists. That order is deliberate:
section 3.2 of the learning-architecture research warns that retrofitting
covariates onto old rows defeats the purpose, so the fields have to be right
before the first fort rather than after the twentieth.

**Four design calls worth knowing about:**

1. **Orthogonal feature axes**, replacing the design doc's single
   `entrance_design`. You cannot vary one variable when the variable is a
   portmanteau, and build item 8 depends on being able to.
2. **Every field declares a `source`**, and `store.assert_gradeable()` refuses
   to let grading code read `HUMAN` or `AGENT` fields. This makes "never grade
   the agent's account of its own learning" a code-level failure rather than a
   discipline anyone has to remember.
3. **`unrecorded` is dropped by stratification, not pooled**, and the dropped
   count is part of the result so the denominator stays honest.
4. **The vocabulary can record our own failures** (`agent_error`,
   `fps_collapse`, `run_ended_technical`). A schema that cannot record them
   produces a flattering report by construction.

**Standing caveat, and the next real test of this work:** nothing is verified
against DFHack. Every `MECHANICAL` field is a bet that code will be able to
read that value from game state, and `schema.MECHANICAL_PATH_VERIFIED` is
`False` to say so. `defense_depth`, `primary_industry` and `surface_footprint`
are the likeliest to have no clean mechanical reading; if so they get demoted
to `AGENT` and become colour rather than evidence.

**Deliberately not built:** any inference. `report.py` prints coverage and
descriptive survival with denominators visible and says in its own output that
it is not evidence. Hypothesis promotion is the hierarchical Beta-Bernoulli
model (research 3.3, build item 4), which does not exist. Reading a survival
difference off the report and calling it a lesson is exactly the flat-counter
mistake the register rejected on 2026-08-25.

**Housekeeping:** added `.claude/scheduled_tasks.lock` to `.gitignore` (a
machine-local runtime file that was showing up untracked).

**Not pushed.** Local `main` is now several commits ahead of origin. Push is
gated on an explicit go-ahead each time.

## HANDOVER - 2026-08-27 (evening), work paused here

**State at a glance:** the repo's two earliest build items are both done and
both have their evidence written down. The perception bet is measured and
accepted; the fort ledger exists, is tested, and is deliberately empty. The VM
is built, stopped, and has still never been started. Local `main` is **6
commits ahead of origin and unpushed**.

1. **Perception eval: done for this phase.** `exits_v1` ties `coords_v1` at
   99.1%, n=108 per representation, accepted in the register. Total spend
   $1.14 across three live runs. Detail archived to
   [`working-archive/Working_archive-2026-08-24.md`](working-archive/Working_archive-2026-08-24.md).

2. **Fort ledger: built this session.** `ledger/`, JSONL, git-tracked, empty by
   design. `python -m ledger.selftest` passes, including eleven negative checks
   that break each validator rule on purpose. Six decision-register entries
   record the design calls. Full account in the section above this one.

3. **Infrastructure: unchanged.** Template 101 and VM 104 (`df-fortress`) are
   built. The VM is stopped and was not started this session either.

4. **Repo is public** at [github.com/QuickWaller/df-overseer](https://github.com/QuickWaller/df-overseer).
   `gh` is authenticated (QuickWaller). **Six local commits are unpushed**,
   including the whole ledger. Push is gated on an explicit go-ahead each time,
   so ask rather than assuming the user still wants it caught up.

### What a next session should pick up, in order

**1. Build the compliance eval harness.** This is
`research/2026-08-25-learning-architecture.md` build item 1, described there as
"cheapest, do first, **before any fort runs**", and it is now the earliest
unbuilt item in that list. It replicates the instruction-count-decay
methodology against our actual doctrine format and actual model: load synthetic
doctrine at increasing rule counts, measure where compliance degrades.

Three reasons it is the right next thing. It needs no game and no agent, so it
is not blocked behind the VM like everything in `docs/PURPOSE.md`'s build order
past item 1. It retires a named standing caveat: the register records the N=80
threshold as "a single unreplicated study" and says to measure our own curve
early, which has not happened. And it can reuse the perception harness's entire
shape (matrix runner, JSONL results under version control, `report.py`, the
prefix-caching prompt layout), so the build is mostly assembly rather than
design.

**2. Then mechanical prediction grading** (research build item 3): a scripted
comparison of a prediction's `signal` field against recorded state at
`check_at`. Cheap, and no prediction-based calibration metric means anything
until it exists.

**3. The ledger's real test is its write path, and it is not built.** Every
`MECHANICAL` field is currently a bet that code will be able to read that value
from game state; `schema.MECHANICAL_PATH_VERIFIED` is `False`. `defense_depth`,
`primary_industry` and `surface_footprint` are the likeliest to have no clean
mechanical reading, in which case they get demoted to `AGENT` and become colour
rather than evidence. This is gated on the perception layer, so it waits, but
it is the thing that will actually validate or break the schema.

**4. Proxmox VM start: blocked on the same two things, unchanged.** Memory
headroom (the VM wants 6144 MB; host had 5.4 GB available at last read; options
are free host RAM, drop the VM to 4 GB while stopped, or wait for the second
node) and the tailnet subnet router being reachable (`tailscale`,
<tailnet-router-ip>, advertising `<lan-subnet>/24`). Resume command:
`python scripts/provision_vm.py status`, which gates on `available`, not
`free`.

**5. Re-run the perception eval against real briefings once `llm-brief.lua`
exists.** Today's result is on hand-authored, generous 15-landmark fixtures;
the real generator is lossier (3 nearest neighbours only, geometric distance).
That gap is the next validity question, not urgent on its own.

**6. Housekeeping, carried forward and still untouched:**

- **Proxmox token not rotated**, pasted into an earlier transcript. Datacenter
  > Permissions > API Tokens > `api` > Remove, re-Add, update `PVE_TOKEN_SECRET`
  in `.env`.
- **Temporary Anthropic key in `.env` expires ~2026-09-03** (user-supplied
  2026-08-27). Rotate or remove after use; do not commit or log it.
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **`openclaw` vs `hermes-agent` still deferred.** The 2026-08-27 addition
  stands: multi-agent decomposition by spatial task bears on the choice because
  openclaw's multi-agent support is a candidate differentiator. Does not
  resolve it.
- **DF replay determinism unverified**, and the seeded-counterfactual rerun
  harness (research build item 7) rests entirely on it.
- **`hypothesis_id` has no registry.** Ledger observations reference
  hypotheses by bare string, and nothing checks the id exists. Belongs with
  research build item 4, but a typo before then silently orphans evidence. See
  `ledger/README.md` open questions.

**Style note for future sessions:** the user does not want em dashes in prose.
Commas, colons, semicolons or full stops instead. They are fine as structural
separators (aligned definition lists, index lines).

## Archived

- Sections for the week of 2026-08-24 (the design phase, the access-layer
  build, and the host-RAM blocker) moved to
  [`working-archive/Working_archive-2026-08-24.md`](working-archive/Working_archive-2026-08-24.md).
- 2026-08-27: the provisioning-build handover and the 2026-08-26 storage-blocker
  detail (both finished/superseded) moved to the same archive file.
- 2026-08-27 (evening): the afternoon perception-eval section (it reported
  itself finished) and the afternoon handover (superseded by the one above)
  moved to the same archive file.
