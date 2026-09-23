# Handoff: what do players actually do with burrows and districts

Date: 2026-09-24. **Researcher. Read-only. Deliberately small.**

**Budget: this is a short, cheap pass.** Target roughly 150 to 250 lines.
Do not run a broad cross-domain prior-art sweep; that was already done in
`research/2026-09-24-room-layout-best-practices.md`, which you should read
rather than repeat. Stop when the questions below are answered, and say
plainly where a question has no good community answer rather than padding.

Read `CLAUDE.md` first, then that layout research file, and
`memory/dfhack-environment.md` on burrows.

## Context you do not need to re-derive

- This project has agreed that **districts map onto burrows**: DF's own named
  regions with dwarves assigned, rather than a parallel model.
- `plotinfo.burrows.list` is the burrow list and **this fort has zero
  burrows**, verified during the flood research.
- DF's per-tile traffic designation (High/Normal/Low/Restricted, real path
  costs) exists and is unused on this fort.
- A district is a **volume, not a z-level**; integrated neighbourhoods are
  preferred over one purpose per floor.

## The questions

1. **What do experienced players actually use burrows for?** Name the real
   uses (civilian alerts, keeping dwarves out of danger, restricting hauling,
   keeping a workforce local to its industry), and say which are routine
   versus emergency-only.
2. **Per-burrow logistics.** How do players keep a district self-sufficient:
   stockpile placement relative to workshops, what gets stored locally versus
   centrally, and where quantum or feeder stockpiles fit if at all.
3. **Imports and exports between districts.** How does material move between
   a mining district and a crafting one in practice: hauling routes, stockpile
   links (give/take), minecarts, or simply proximity. What do players say goes
   wrong at scale.
4. **Sizing.** Any community guidance on how many dwarves per burrow, or how
   large a district should be before it is split.
5. **Failure modes**, stated so a tool could detect them: the classic burrow
   mistakes (dwarves starving inside a burrow with no food, a burrow with no
   access to a well, hauling deadlock, dwarves unable to reach their jobs).
   This is the most useful section.

## Honesty requirements

Keep **player convention** and **game mechanic** strictly apart, as the layout
pass did. Flag anything predating the v50 change, since burrow handling and
zones both changed. Where the only source is a forum post, say so.

## What to produce

`research/2026-09-24-burrow-district-designs.md`, that file only. Short, with
a verdict paragraph, then the answers, then a brief list of candidate rules or
checks tagged `invariant`/`metric` and `game mechanic`/`convention`, matching
the format the layout research already established.

Propose doctrine entries in your Result section rather than writing them; a
sibling stream recently touched `doctrine/seed.yaml` and you do not own it.

## Rules

- Read-only. No VM command is expected to be needed; if you think one is,
  bound it and quote it. Fort stays paused, nothing mutated.
- `git merge --ff-only main` first; this brief is committed on main.
- You own that one research file and this doc's Result section. Not
  `doctrine/**`, `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`.
- Never render or reconstruct a map; keep output coordinate-free.
- No em dashes in prose. **No attribution lines in any commit message.**
- Stop and report on any permission or classifier refusal.

## Done means

The five questions answered or explicitly declared unanswerable, the failure
modes expressed as conditions a tool could check, convention kept apart from
mechanic, and the whole thing short.

## Result

(to be filled by the stream)
