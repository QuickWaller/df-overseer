# Overseer memory architecture

> Draft, 2026-08-25. Companion to `PURPOSE.md`.

The chronicle is not enough on its own. It is narrative — chronological, prose,
written for a reader — which makes it good for "what happened last spring" and
bad for "what's the best z-level for farms in this world." Operational
knowledge, procedures and per-fort working state each have different lifetimes
and access patterns, and collapsing them into one store makes all of them worse.

## Four stores

| Store | Kind | Lifetime | Access | In context? |
|---|---|---|---|---|
| **Chronicle** | Episodic — what happened, as narrative | Forever, across forts | Searched on demand | No |
| **Doctrine** | Semantic — distilled facts and rules | Forever, edited in place | Always loaded | **Yes — cached prefix** |
| **Playbooks** | Procedural — how to do a thing | Forever, improved in use | Retrieved by name | Named list only |
| **Fort dossier** | Working state — landmarks, plans, open problems | Dies with the fort | Always loaded | Yes |

**Doctrine** is the important one and must stay *small*. Deduped, edited in
place rather than appended to, and written as assertions: *"Seal the caverns
before year 3." "Goblins in this world approach from the east." "Never breach
an aquifer without a drainage plan."* Small enough to sit in the DeepSeek
cached prefix at ~$0.003/M means it is effectively free to consult every turn.

**Playbooks** are the Voyager/hermes-agent skill-library pattern: a named,
reusable procedure that gets *rewritten* after each use rather than accumulating
variants. "Handle a goblin siege." "Set up a magma forge."

**Fort dossier** dies with the fort — but is distilled into an epitaph, and any
generalisable lesson is promoted into doctrine before the fort is abandoned.

## Reading through it

Retrieval is tool-based, not context-stuffing:

```
search_chronicle(query, limit)      -- FTS over prose
get_doctrine(topic?)                -- small; often just loaded whole
get_playbook(name)                  -- full text of one procedure
list_playbooks()                    -- names + one-line summaries
recall_similar(situation)           -- "have I faced this before?"
```

Doctrine is always resident. Everything else is fetched on demand and lands in
the volatile tail of the context, per the caching rules in `PURPOSE.md`.

## Learning: outcome tracking, not self-critique

**This is the part to get right, and the obvious approach is the wrong one.**

Asking an LLM to critique its own reasoning produces confident, plausible,
largely uncorrelated-with-truth self-assessment. Do not build that.

Build **outcome tracking** instead, because this domain hands us something rare:
*the game is ground truth.* Every significant decision records a prediction —

```
decision:    dig a second farm level on z-4
expectation: food stores stop falling within 2 seasons
check_at:    year 253, Autumn
signal:      food_stores trend
```

— and a later pass checks it against actual state. The agent is not judging its
own reasoning; it is being judged by the fortress. Failed predictions are the
highest-value learning signal in the system, and they are objective.

The learning loop, in order of frequency:

1. **Prediction check** (per season) — did what I expected happen? A failure
   writes a chronicle entry and, if it generalises, a doctrine edit.
2. **Playbook revision** (on use) — a procedure that didn't work gets rewritten,
   not appended to.
3. **Fort epitaph** (on death) — what killed it, what I'd do differently.
   Highest-value artifact for both reader and agent.
4. **Doctrine review** (rare) — prune contradictions, merge duplicates. Doctrine
   growing without bound is the failure mode to watch for.

## Cross-fortress learning

This is the point of fort mortality. Each dead fort is a data point; the world
and the memory are what accumulate. But three things make naive
"learn from your mistakes" fail here.

### 1. Lessons have scope, and mis-scoping them is the main failure mode

A lesson learned in one world may be universal, may be true only of that world,
or may be true only of that embark. Promoting a world-specific lesson to
universal doctrine will **actively harm** the next fort. Every doctrine entry
therefore carries a scope:

| Scope | True of | Example | Survives |
|---|---|---|---|
| **Universal** | Dwarf Fortress itself | "Seal the caverns before year 3" | Forever |
| **World** | This generated world | "Goblins approach from the east"; "this civ has no iron" | Until a new world |
| **Site** | This embark | "Aquifer at z-3"; "magma at z-42" | Dies with the fort |

Site-scoped facts live in the fort dossier and die with it. World-scoped facts
survive re-embarks within a world. Only universal lessons cross worlds.

**The taxonomy is right; three discrete buckets are the wrong data structure.**
A lesson is rarely purely universal or purely world-local — it is partially
general, and how general is itself something to be estimated. The correct shape
is a **hierarchical (multilevel) model with partial pooling**: evidence from one
world informs the universal estimate in proportion to how consistent it is
across worlds, rather than being sorted irreversibly into one of three boxes by
a judgement call made at write time.

### 2. N=1 is not a lesson — but a vote counter is not the answer

> **Superseded 2026-08-25.** An earlier draft promoted hypotheses on a plain
> evidence counter (`support >= 3`). `research/2026-08-25-learning-architecture.md`
> identified the fatal flaw: **counting corroborations silently assumes credit
> assignment is already solved.** You cannot record "this fort supports the
> single-entrance hypothesis" without already knowing which of ~200 decisions
> caused its death. The counter presupposed the very thing it was meant to help
> with. Kept below is the *problem*; the mechanism is replaced.

A fort dying to a siege does not prove the entrance design was bad. It may have
embarked beside a goblin fortress; it may simply have been year 8. One dramatic
death produces a confident, wrong generalisation, narrated persuasively.

Three fixes replace the counter.

**Weight evidence by diagnosticity, not by count.** Van Evera's process-tracing
tests distinguish evidence that barely discriminates from evidence that settles
a question — a *hoop* test the hypothesis must pass to stay alive, a
*smoking-gun* test that strongly confirms it. One smoking-gun observation is
worth more than five weak corroborations, and a plain counter cannot express
that.

**Stratify by covariate, don't just tally.** The ledger records the
circumstances alongside the outcome, so comparisons condition on them rather
than pooling unlike forts. Bradford Hill's criteria are the standard checklist
for the shape of inference we are attempting: strength, consistency,
temporality, biological-gradient-analogue (dose-response), plausibility.

**Derive the threshold from a stated error rate.** "3" was arbitrary. A
sequential-testing framework fixes an acceptable false-promotion rate and
derives the stopping point from it — Wald's Sequential Probability Ratio Test
is the standard tool and minimises expected sample size for fixed Type I/II
error, which is exactly the constraint at N≈20.

**Attribute at the feature level, never the decision level.** With ~20 forts
you cannot honestly say a particular decision in year 4 killed a fort. You can
compare coarse recorded features across forts. This has a sharp consequence:
**the ledger schema defines what is learnable.** If entrance design is not a
recorded field, no amount of reasoning will ever produce a lesson about it.

### 3. Forts must be comparable — the fort ledger

Cross-fort questions ("what did forts that survived past year 10 have in
common?") need structured records, not prose. A fifth store: one **fort ledger**
entry per fort, written at death, queryable.

```
fort_id, world_id, embark_biome, embark_size, start_year, end_year,
peak_population, cause_of_death, entrance_design, caverns_sealed(bool),
milestones[], hypotheses_tested[], epitaph_ref
```

The epitaph is the prose; the ledger row is the data. The agent queries the
ledger to form and check hypotheses, and reads epitaphs for context.

**Build this earliest.** It is a trial registry, and nothing else in this
document is checkable without it. Its fields must carry the **covariates**
(world, embark conditions, civ, neighbours) that comparisons need to condition
on — not just the outcome label. Schema design is learning design.

### Sample size is the real constraint

At `FPS_CAP:5` (~32 game years/month), a fort living ~10 game years yields
roughly **3 forts per month**. Six months is ~20 forts. That is a small sample,
and it means learning must be sample-efficient — which is exactly why the
hypothesis/evidence model above is preferred over anything statistical.

Raising the FPS cap buys more forts per month at the cost of watchability. That
trade is worth making deliberately, not by accident.

### The ambitious version: deliberate experimentation

Passive learning waits for variation to occur. The stronger version has the
agent *vary things on purpose*: "I have built entrance design A three times;
this fort will try B." Active experimentation turns 20 forts into 20 designed
trials rather than 20 anecdotes.

**This is v1, not a later ambition** (revised 2026-08-25). Passive learning at
N≈20 is close to unworkable — twenty forts in twenty different worlds are twenty
confounded anecdotes. A one-variable-at-a-time discipline is nearly free once
the ledger exists, and re-embarking in the *same* world holds the largest
confound constant, which is what makes the comparison worth anything.

It is also the most interesting thing to *watch*, and it turns the chronicle
from a diary into a research log.

## Received knowledge: the wiki as a hypothesis source

Twenty forts is a small sample. The community has run millions and written the
conclusions down. The Dwarf Fortress Wiki is one of the best game wikis in
existence and is **dual-licensed MIT + GFDL** (*verified*) — bulk download and
reuse are explicitly permitted, with attribution.

### Get it offline, don't fetch live

The wiki documents an official offline path: WikiTeam's `dumpgenerator.py`
against the wiki's API, with `--exnamespaces` to skip namespaces you don't want.

Pre-ingest rather than live-fetch, for three reasons: a month-long unattended
run should not depend on the network; wiki content changes slowly (on game
updates) while the agent queries constantly; and offline retrieval is faster and
free. Re-dump on DF version bumps.

### The version-namespace trap

The wiki keeps **version namespaces** — `DF2014` is v0.47 content, which is a
different game from v53 in ways that matter (mode switching, `PRINT_MODE`,
adventure mechanics, UI). A v0.47 strategy applied confidently to v53 is a
silent, plausible-sounding failure.

Every retrieved chunk must carry its namespace, and version mismatch must be
surfaced to the model, not hidden. This is the biggest correctness risk in the
whole knowledge layer.

### Two-tier retrieval

- **Curated digest in the cached prefix.** DeepSeek V4's 1M context at
  ~$0.003/M cached input means 50–100K tokens of the most useful wiki content
  can ride in the stable prefix *every turn for almost nothing*. Pick the twenty
  or thirty pages that actually matter: aquifers, sieges, defence design, fort
  layout, industry chains, FPS. This option did not exist before cheap large
  caches.
- **RAG over the full dump** for the long tail.

### The key rule: the wiki produces hypotheses, not doctrine

**Received knowledge and verified knowledge must stay distinct.**

- The wiki is what the community *believes*.
- Doctrine is what this overseer has *confirmed in its own forts*.

A wiki claim therefore enters the same hypothesis pipeline as anything else —
just with a higher starting prior, since community consensus is real evidence.
It enters as a **stated prior strength**, not a magic starting count: how
strongly the community holds it, how consistent the sources are, and which
version namespace it comes from. (An earlier draft said "enters at
`support: 2`"; that was the same arbitrary-arithmetic mistake as the promotion
counter — see §Cross-fortress learning.) It still needs corroboration from this
agent's own play before it becomes doctrine.

This does two useful things. It bootstraps the learning loop instead of
bypassing it — the agent starts community-competent rather than losing three
forts to rediscover "seal the caverns," which means its scarce empirical budget
gets spent on questions the wiki *doesn't* answer. And it lets the agent
**disagree with the wiki** on its own evidence:

> *The wiki holds that two entrances are safer. In three forts I have found the
> opposite; the second entrance was the breach point twice.*

That is a far better read than an agent that simply does what it was told, and
it is the difference between a research log and a walkthrough.

### Attribution

MIT + GFDL dual licensing means MIT terms can be chosen for reuse. If wiki
content is surfaced on the public dashboard or in published chronicles, attribute.

## Compliance: doctrine has a hard size budget

Doctrine staying small is not a style preference. It is close to a measurable
ceiling on how many simultaneous rules a model will actually obey, and it gates
everything else in this document — unfollowed doctrine makes the whole
architecture decorative.

**Instruction-count collapse.** A 2026 controlled study (arXiv:2607.19257)
tested five models — Claude Sonnet 5, Claude Haiku, Gemini Flash and two Qwen
sizes — against system prompts carrying 10 to 160 simultaneous, independently
verifiable rules, across four formats and both system- and user-turn placement,
960 calls per model. Perfect-response rate **collapsed to zero by N=80 rules for
every model, every format, and both placements.**

*Single study; the exact N=80 threshold has no independent replication.* Treat
it as an order-of-magnitude budget, and measure our own
compliance-versus-doctrine-size curve early rather than trusting the number.

**Position matters as much as size.** "Lost in the middle" (Liu et al.) found a
U-shaped curve — content at the very start or very end of context is used far
more reliably than content buried in the middle, with a 30-point-plus accuracy
drop moving a relevant document from first to tenth of twenty, persisting even
in models built for long context. So the cache-ordering rule in `PURPOSE.md` is
**also a correctness requirement**, not only a cost optimisation. Doctrine goes
at the front, possibly duplicated at the very end; never in a middle tier.

**Multi-turn decay — and it changes the loop design.** Microsoft Research and
Salesforce (arXiv:2505.06120) measured roughly **39% accuracy loss** as
conversations extend over many turns. A month-long fortress session is, naively
implemented, one enormous multi-turn conversation.

> **Therefore: the overseer is not a long-running conversation.** Each turn
> assembles a fresh context from memory — doctrine, dossier, retrieved
> chronicle, current briefing — rather than appending to an accumulating
> dialogue. Continuity lives in the memory stores, not in the message history.

## Measurement: how we would know it is learning

Believing the system learns is not evidence that it does. Three rules.

**Never grade the agent's account of its own learning.** Every check — prediction
grading, evidence updates, promotion decisions — is a mechanical read of ledger
and dossier state. A model can produce a compelling account of *why* doctrine
changed its decision without that doctrine having causally influenced anything;
removing the model from the grading loop is the only defence with evidence
behind it.

**Cross-check narration against action.** Where turn-by-turn reasoning cites a
doctrine entry, an automated (non-LLM, or separate cheap-model) auditor checks
whether the action actually matches what that entry prescribes.

**Measure from real run logs, not a flagged test mode.** A compliance eval run
as an obviously-distinct scripted scenario may not describe behaviour during
real unattended play.

And one heuristic worth watching for directly:

> **A system that is genuinely learning should occasionally be embarrassed by
> its own past doctrine.** If doctrine only ever grows across twenty forts, and
> nothing is ever contradicted or walked back, that is a warning sign that
> hypotheses are being confirmed rather than tested — not a clean track record.

**Seeded counterfactual reruns** are proposed as a cheap substitute for a
control arm, exploiting DF's determinism to replay a situation with one decision
changed. *Unverified: whether DF actually replays deterministically from a save
has not been tested, and the whole idea rests on it.*

## Human input

Guidance from a human must land in **doctrine**, not just in a turn's context.
Advice given conversationally and not written down is forgotten on the next
turn — this is the single most likely way the system will feel broken.

Channels, in order of reliability:

- **`GUIDANCE.md` in the repo** — git-tracked, survives everything, works with
  no infrastructure. Read every turn; the agent folds new entries into doctrine
  and marks them applied.
- **Telegram** — conversational, already wired in openclaw. Good for "stop
  digging so deep" in the moment.
- **Dashboard comments** — lowest priority, needs the dashboard first.

Whatever the channel, the same rule holds: the agent must *write it down* into
doctrine and say that it has, or the instruction did not really land.

## Open questions

- Doctrine format: typed markdown files with an index (the
  `claude-code-managed-repo-template` pattern already in use) vs. a single file.
- ~~Where memory physically lives.~~ **Settled 2026-08-25: in this repo**,
  git-tracked, built framework-agnostic and exposed as MCP tools. See
  `memory/agent-memory-standards.md`.
- Whether playbooks and DFHack blueprints should be the same object. A playbook
  that says "build this" and a blueprint that encodes it are closely related.
