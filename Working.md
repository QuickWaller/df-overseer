# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved — don't mark it paused. Any session should read this and know what's
actually going on right now.

## 2026-08-27 (afternoon) — repo pushed public; harness ran live for the first time

**Pushed:** [github.com/QuickWaller/df-overseer](https://github.com/QuickWaller/df-overseer), public, all commits on `main`. `gh` was already authenticated (QuickWaller); no remote existed before this.

**Perception harness ran against a live model for the first time.** User supplied a temporary Anthropic key (expires ~2026-09-03, stored in gitignored `.env`, do not commit or log it; rotate/remove after use). A 20-cell smoke test (`--limit 20`) immediately hit a real bug: every cell failed with the same 400 — `response_schema()`'s `confidence` field carried `minimum`/`maximum` on a `number` type, which the live structured-output validator rejects (the stub-only tests never caught this, exactly the gap the README predicted). Fixed in `harness/grade.py` — dropped the constraint keywords, stated the 0-1 range in the schema `description` instead. Full account in `decisions/DECISIONS.md` 2026-08-27.

**Re-run after the fix: 20/20 succeeded.** 100% accuracy on `coords_v1` (the only representation this particular 20-cell slice covered — `--limit` takes cells in build order, not a stratified sample). Cache reads confirmed non-zero (12/20 requests, 26,738 cached tokens) — the prefix-caching design works. Actual cost: **$0.043** for the successful run (969 input + 26,738 cached-read + 995 output tokens on `claude-opus-5`), essentially free — the pre-fix all-error run cost nothing (400s bill no tokens).

**New project goal, stated by the user:** the eval data and future fortress runs should build toward a public-facing report, not be throwaway. Reversed a repo-state bug that fought this directly: `evals/perception/.gitignore` was silently excluding `results/` from git. Removed it; `evals/perception/results/*.jsonl` is now tracked. See `memory/` for the standing note on this.

**Update, same afternoon — the stratified run happened, and the $5-15 estimate was wrong.** Real per-cell cost is far below the earlier guess (output tokens ran much lower than assumed). Ran a 120-cell stratified slice (`--per-category 1`, all fixtures, all representations — `evals/perception/results/stratified-2026-08-27.jsonl`) for **$0.27 actual**. Result: **first real signal that the core bet holds** — `exits_v1` tied `coords_v1` at 97.4% on the shared question set; see `decisions/DECISIONS.md` 2026-08-27 for the full breakdown, including the `route`-category soft spot and a thin-but-notable calibration difference. Marked `proposed`, not `accepted` — n=1-3/category, small hand-authored fixtures.

**Update, same afternoon — full 342-cell matrix run.** $0.83 actual, zero API errors. Confirms the core bet at real sample size: all three representations 99.1% (n=108 each), `route` rose to 88.9% with more data. **The calibration-separation finding from the 120-cell run did not replicate** — reordered entirely at n=108 (see `decisions/DECISIONS.md` 2026-08-27, both the `accepted` promotion and the retraction entry). Total spend today across all three eval runs: **$1.14**.

**Perception harness status: first build-order item now has real, accepted evidence behind it.** Standing caveats unchanged — still 15-landmark hand-authored fixtures, not the real (lossier) production briefing generator. Re-run against real briefings once `llm-brief.lua` exists. Next build-order item is the **fort ledger schema** (still not started, named three times now).

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

## HANDOVER — 2026-08-27, work paused here

**State at a glance:** repo is public and pushed. Perception eval — the
project's first build-order item — now has full, accepted evidence behind it.
The VM is built and stopped; it has never been started.

1. **Infrastructure** — template 101 and VM 104 (`df-fortress`) are both
   built. The VM is stopped and was not reachable to start this session — see
   below. Nothing else about it changed today.
2. **Perception eval harness — DONE for this phase.** Ran live for the first
   time, hit and fixed a real schema bug, then ran a 120-cell stratified slice
   and the full 342-cell matrix. Core result: `exits_v1` (the actual no-map
   production idiom) ties `coords_v1` (the coordinate control) at 99.1%,
   n=108/representation, **accepted** in the decision register. Total spend
   $1.14 across three live runs. Full account: `decisions/DECISIONS.md`
   2026-08-27 (five entries), and the section above this one in `Working.md`.
3. **Fort ledger schema — still not started.** Named three times now as this
   stream's earliest build item; its schema defines what is learnable. This is
   the next real piece of work.
4. **Repo is now public and pushed:** [github.com/QuickWaller/df-overseer](https://github.com/QuickWaller/df-overseer).
   `gh` was already authenticated (QuickWaller). As of this handover, local
   `main` is a few commits ahead — check `git status` and push if the user
   wants that caught up; push is gated on asking each time regardless.

### What a next session should pick up, in order

**1. Build the fort ledger schema.** Nothing else in the learning design is
checkable without it (`decisions/DECISIONS.md` 2026-08-25: "Fort ledger moved
to earliest build item"). Read `docs/MEMORY-ARCHITECTURE.md` first.

**2. Proxmox VM start — blocked on the same things as before, unchanged:**
memory headroom (VM wants 6144 MB, host had 5.4 GB available at last read;
options are free host RAM, drop the VM to 4 GB while stopped, or wait for the
second node) and the tailnet subnet router being reachable (`tailscale`,
<tailnet-router-ip>, advertising `<lan-subnet>/24` — it dropped out of this
machine's peer list mid-session because a concurrent AgentSecretary agent was
using that Tailscale login elsewhere; transient, not a real outage — just
retry). Resume command: `python scripts/provision_vm.py status` (gates on
`available`, not `free`).

**3. Re-run the perception eval against real briefings once `llm-brief.lua`
exists.** Today's result is on hand-authored, generous 15-landmark fixtures —
the real generator is lossier (3 nearest neighbours only, geometric distance).
That gap is the next validity question, not urgent on its own.

**4. Housekeeping, still carried forward and still untouched:**

- **Proxmox token not rotated** — pasted into an earlier transcript.
  Datacenter → Permissions → API Tokens → `api` → Remove, re-Add, update
  `PVE_TOKEN_SECRET` in `.env`.
- **Temporary Anthropic key in `.env` expires ~2026-09-03** (7 days from
  2026-08-27, user-supplied). Rotate/remove after use; do not commit or log it.
- **Folder is still `df-automation` on disk** while the project is
  `df-overseer`.
- **`openclaw` vs `hermes-agent`** still deferred. New consideration added
  2026-08-27: multi-agent decomposition by spatial task (patrol/military,
  construction/placement, economy as separate specialized agents) — bears on
  the choice because openclaw's multi-agent support is a candidate
  differentiator. Does not resolve it.
- **DF replay determinism unverified**; **our own compliance-vs-doctrine-size
  curve unmeasured** (N=80 threshold is a single unreplicated study).

**Housekeeping this session:** removed `evals/perception/.gitignore`, which
was silently excluding `results/*.jsonl` from git — the user's stated goal is
for experiment data to accumulate toward a public report, so results are now
tracked (`memory/reporting-goal.md`).

Detail on everything before 2026-08-27 (the provisioning build, the storage
and SDN blockers, the RAM-metric and electricity-cost corrections, the
hardware-planning session, and the original harness build) has moved to
[`working-archive/Working_archive-2026-08-24.md`](working-archive/Working_archive-2026-08-24.md)
— it reported itself finished and this file was getting long.

## Archived

- Sections for the week of 2026-08-24 (the design phase, the access-layer
  build, and the host-RAM blocker) moved to
  [`working-archive/Working_archive-2026-08-24.md`](working-archive/Working_archive-2026-08-24.md).
- 2026-08-27: the provisioning-build handover and the 2026-08-26 storage-blocker
  detail (both finished/superseded) moved to the same archive file.
