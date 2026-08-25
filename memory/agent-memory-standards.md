# Agent memory management — the state of the art, and where we diverge

Surveyed 2026-08-25, when deciding how to build the overseer's memory layer.
Context for `docs/MEMORY-ARCHITECTURE.md`; the decisions are in
`decisions/DECISIONS.md` (2026-08-25).

## The three framework families

**Letta (formerly MemGPT)** — the canonical reference, and the closest fit to a
long-running agent. OS-style virtual context management: a small **main
context** (always resident, RAM-like) plus an unbounded **archival store**
(disk-like), with the LLM paging between them via tool calls.

**Mem0** — managed extract → consolidate → retrieve loop. v3 (April 2026) does
single-pass ADD-only extraction with cross-memory entity linking. Aimed at
personalisation.

**Zep / Graphiti** — temporal knowledge graphs over dense retrieval, built for
reasoning about *how facts change over time*. Relevant to us in one specific
way: "the caverns are sealed" is a fact with a validity period, and temporal
graphs handle that where flat stores don't. Worth revisiting if doctrine
staleness becomes a problem.

## Anthropic's stack — closest match to our situation

Three complementary pieces, meant to be combined rather than chosen between:

- **Compaction** — summarise a conversation nearing the context limit and
  reinitialise a fresh window from the summary.
- **Context editing** — clear stale tool results client-side; the lightest-touch
  form of compaction.
- **Memory tool** — structured note-taking persisted outside the context window
  and pulled back in later.

Their long-running-agent pattern: an **initializer agent** that sets up the
environment on first run, plus a worker agent making incremental progress each
session **while leaving clear artifacts for the next session**. This is
essentially what `docs/MEMORY-ARCHITECTURE.md` arrived at independently.

Reported result on a 100-turn task: **84% token savings and a 39% performance
improvement**. Note the second number — trimming context made it work *better*,
not merely cheaper. Context bloat is a correctness problem, not just a cost one.

## Where our design sits

| Ours | Standard equivalent |
|---|---|
| Doctrine + fort dossier | Core memory (Letta main context) |
| Chronicle | Archival memory, retrieved |
| Playbooks | Procedural / skill library (Voyager) |
| Fort ledger | **Non-standard** — a structured trial registry |

Broadly Letta's model plus a domain-specific structured store. The ledger has no
real equivalent because most agents are not running repeated experiments.

## The deliberate divergence: the model does not edit its own memory

**Letta's defining feature is the LLM managing its own memory via tool calls. We
do the opposite** — mechanical promotion, code-driven grading, model kept out of
the loop.

This is a conscious departure from standard practice, and the reasoning must
survive: self-managed memory is where unfaithfulness and sycophancy live. The
field considers this live enough that a benchmark exists specifically for
*sycophancy in agent memory*. For a system whose entire output is accumulated
claims about what works, an agent that can quietly rewrite its own evidence is
the exact failure mode to design against.

The cost of the divergence is real: we forfeit a mature framework and build the
paging/retrieval layer ourselves.

## The gap the whole field shares

> These systems share a common assumption: the LLM will honor retrieved memory
> once it is injected into the context.

That is the compliance problem from `docs/MEMORY-ARCHITECTURE.md`, unsolved by
the standard frameworks — they assume it away. Adopting any of them would not
have inherited a fix. This is why measuring our own compliance-vs-doctrine-size
curve is a build-order item rather than an afterthought.

## Practical correction this produced

"Fresh context per turn" was stated too absolutely. Anthropic pairs compaction
*with* memory rather than choosing. A single overseer turn may itself involve
many tool calls — briefing, landmark lookups, site ranking — and that inner loop
grows. **Compaction belongs inside a turn; memory stores carry across turns.**
Both, at different scales.
