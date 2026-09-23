# Handoff: what does each room and zone actually require

Date: 2026-09-23. **Researcher. Read-only.** No code that changes a tool, no
deploy, no fort mutation, no unpause. The fort is paused with a confirmed
quicksave and stays paused.

Read `CLAUDE.md` first, then `doctrine/seed.yaml`'s header (the entry schema
and its provenance rules), `docs/MEMORY-ARCHITECTURE.md` on the doctrine tier,
`evals/live/2026-09-23-office-and-first-real-build/README.md` and
`evals/live/2026-09-23-chair-completion-run/README.md` (the office evidence),
and `research/2026-09-23-work-orders-vs-direct-jobs.md`.

## Why

This project has been guessing at room requirements and paying for it. Two
Office zones were placed for the Manager, one owned, and in the first real
fort time the manager orders have ever had, not one order validated. The
current best explanation is room value or some requirement we have not
identified, but nobody has ever gone and read what the game actually
requires. **This is knowable.** It is in the install's own data and in the
game's own rules, not a matter of opinion, and it should be doctrine rather
than folklore.

The user's framing: what is required for each of the rooms and zones. Answer
that as a general question, not just for the office. The office is the case
that hurts right now, but a tool or an agent needs the whole table.

## The questions

1. **What defines a room at all?** In this version, how does a room come into
   existence: from a piece of furniture that carries a room, from a zone
   painted over an area, or both depending on kind? Be exact about which
   kinds work which way, because the two are different mechanisms and this
   repo's `zone` tool and `building` tool sit on different sides of it.
2. **Per kind, what does it require?** Bedroom, dining room, office or study,
   tomb, and every other kind this install supports. For each: the defining
   furniture if any, whether it must be enclosed or indoors, whether walls,
   doors or floors matter, and what makes it count as assigned or owned.
3. **How is room value computed, and what is it used for?** This is the heart
   of the office question. What contributes: furniture value, quality,
   material, size, contained goods, engraving. Where thresholds exist, name
   them with their source.
4. **What does each noble or administrative position actually demand?** The
   install's own position data is the authority here, not the wiki. It was
   already found that the MANAGER carries `required_office=1` and
   `requires_population=0`, which contradicted the wiki's 20-citizen story.
   Read every position's requirement fields and tabulate them. If a position
   demands a room of a given value, that number is the single most useful
   fact this whole stream could return.
5. **Does "indoors" or "outdoors" change any of it?** Both Office zones this
   fort placed are outdoors, because no fully indoor site was available near
   a workshop or the Well. If outdoors disqualifies a room, or lowers its
   value, that alone would explain the stalled orders. If it does not, say
   so plainly, because it would rule out the explanation this project
   currently leans on.
6. **What is checkable from a tool, today?** For each requirement you find,
   say whether this project could read it through the existing tools in
   `scripts/dfhack/TOOLS.yaml`, or whether it would need something new.
   `zone.getRoomDescription` read `null` on both offices, twice, so be
   concrete about what that means and whether a real room value is reachable
   at all.

## Sources, in order of authority

**The install's own game data outranks everything else.** `doctrine/`'s own
rule is that wiki and forum sources can make a `prior`, never a `verified`
entry: only a live read or game data describing 53.16 can verify. Honour
that. Read the install's raws and DFHack's own structure definitions for
positions, room types and value; there is a local wiki snapshot at the path
recorded in `Working.md` and the register, and DFHack source on the VM, both
already used by the Consultant.

Where the wiki is the only source, mark the entry `prior` and say what would
settle it. Do not quietly upgrade a wiki claim to verified because it sounds
right. The MANAGER contradiction above is exactly why this rule exists.

## What to produce

1. `research/2026-09-23-room-and-zone-requirements.md`, the full findings with
   citations, in the style of the existing research specs, honest about what
   could not be verified.
2. **Doctrine entries** appended to `doctrine/seed.yaml`, one per rule that is
   solid enough to be worth an agent reading. Follow that file's schema
   exactly, including the `sources` provenance fields and the `describes`
   version. Rooms will need a new `topics` value, so you may add it to the
   enum in `doctrine/validate.py` and to its tests. **That is the only code
   you may touch.** Doctrine is game knowledge, never a repo decision, so it
   never goes in the register.

## Rules

- **Read-only against the fort.** Bounded queries only, never an unbounded
  scan against live DFHack, nothing mutated, never unpaused. Reading files
  from the install is preferred over live queries wherever it answers the
  question. Quote the command and its output for anything you read live.
- Use `bash scripts/vm-ssh.sh df '<cmd>'` for every VM command. Do not write
  your own ssh wrapper and do not read an address out of `.env`: four agents
  have leaked a VM address doing exactly that. No address, hostname or token
  in any tracked file, commit message or report.
- `git merge --ff-only main` first.
- `doctrine/tests` and the ambient suite must both pass if you touch
  `validate.py`. Ambient baseline is **1371 passed, 3 skipped**. Use
  `python`, not `py -3`.
- You own the research file, `doctrine/seed.yaml`, `doctrine/validate.py`,
  `doctrine/tests` and this doc's Result section. Nothing else. Not
  `Working.md`, `decisions/DECISIONS.md`, `memory/` or `handoffs/INDEX.md`.
- **Never show or reconstruct a rendered map**, and keep output
  coordinate-free (`docs/PURPOSE.md` design commitment 1). Describing a room
  requirement is fine; drawing a floor plan is not.
- No em dashes in prose. **No attribution lines in any commit message**: no
  Co-Authored-By, no "Generated with Claude Code".
- Stop and report on any permission or classifier refusal. Never route around
  one through another agent or session.

## Done means

A table of room and zone kinds against their requirements, sourced, with the
noble and administrative position requirements read from the install's own
data rather than the wiki. The office question is explicitly addressed: either
the evidence names a requirement the fort's offices fail, or it says the
offices look sufficient and the stall must be explained some other way. Both
outcomes are useful; a hedge is not.

## Result

(to be filled by the stream)
