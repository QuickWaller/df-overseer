# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved — don't mark it paused. Any session should read this and know what's
actually going on right now.

## 2026-08-25 — research and design phase, nothing implemented

The project is in design. No code exists yet; `docs/` and `research/` are the
current output.

**Done:**

- `docs/PURPOSE.md` — purpose statement, six design commitments, scope
  (in/out), streaming plan, memory summary, operating parameters (FPS-cap
  maths, VM spec, anti-decay tool suite), 9-step build order, open questions.
- `docs/MEMORY-ARCHITECTURE.md` — four memory stores, retrieval tools, outcome-tracking
  (not self-critique), cross-fortress learning (scope tags, hypothesis
  promotion, fort ledger), the wiki as a hypothesis source, human input.
- `research/2026-08-25-spatial-perception.md` — 694-line spec. Verdict: the
  model is never shown a map; DF pre-computes most of the graph
  (`getWalkableGroup`, buildings, burrows); 10-tool minimal set; site scoring;
  ~440-token worked briefing.
- Repo adopted `claude-code-managed-repo-template` conventions.

- `research/2026-08-25-learning-architecture.md` — ~7,700 words. Attacked the
  memory design as a strawman and found a real flaw: the evidence counter
  presupposed credit assignment. Verdicts reconciled into
  `docs/MEMORY-ARCHITECTURE.md`; eight new/superseding rows in
  `decisions/DECISIONS.md`.

**In flight:** nothing. No agents running.

**Next concrete step:** build the **perception eval harness** — hand-written
briefings, questions with known answers, measure comprehension. No running game
or agent needed, and it tests the project's biggest risk. Build the **fort
ledger schema** alongside it, since schema design determines what is ever
learnable and it is cheap now / painful at twenty rows.

**Two things to verify before they become load-bearing:** whether DF actually
replays deterministically from a save (the seeded-counterfactual measurement
idea rests entirely on it), and our own compliance-versus-doctrine-size curve
(the N=80 instruction-collapse threshold is a single unreplicated study).

**Ruled out / settled** (see `decisions/DECISIONS.md` for reasons): headless
terminal DF (`PRINT_MODE:TEXT` gone since v50); DFPlex for multiplayer (dead
for v50+); simultaneous adventure + fortress in one world (mode locks the
world); the agent brain living in this repo.

**Open, not blocked:** repo/folder still named `df-automation` on disk while
docs say `df-overseer`; not yet a git repo; `openclaw` vs `hermes-agent`
deliberately deferred; which display to build first.
