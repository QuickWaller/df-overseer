# Handoff: the first reusable blueprint, a tileable bedroom cell

Date: 2026-09-24. **Data and documentation only. No tool changes, no
`TOOLS.yaml`, no deploy, no fort mutation.** A sibling stream currently owns
`scripts/dfhack/TOOLS.yaml` and the Lua scripts; do not touch either.

Read `CLAUDE.md` first, then `research/2026-09-24-room-layout-best-practices.md`
(the 13-rule candidate table), `research/2026-09-23-room-and-zone-requirements.md`,
and the install's own quickfort user guide, which is the authority on blueprint
format and is readable through `bash scripts/vm-ssh.sh df` under the game's
`hack/docs/docs/guides/` directory.

## Why, and the user's rulings that scope it

The Architect currently designs every room from scratch on every run. The
agreed first step is to make the reusable design a **first-class artefact**
rather than to add a new role: a versioned blueprint library the Architect can
author and consume.

The user's rulings, which are the constraints here:

- **A small reusable ASCII template is acceptable for the model to see.** The
  line they drew is between a tiny generic room pattern, which carries no
  information about this fort, and the fort's own map, which remains
  forbidden by `docs/PURPOSE.md` commitment 1. Keep every template generic:
  **no fort coordinates, no landmark names, nothing specific to Uniboslan.**
- **Walls must be finished, but not to a specific or consistent type.** The
  template declares the intent "finished", and the build pipeline resolves it
  per tile: smoothed where the material allows, constructed where it does
  not. Mixed types within one room are explicitly fine. The template must not
  name a material.
- **One template only for now: a bedroom.**
- **Bedrooms get spammed, and will share walls and hallways.**

## The design problem that shapes the format

If the template carries a complete wall ring, two copies placed side by side
produce a double wall, which is the waste this project has already agreed to
measure against. So the cell must declare its **seams**: which edges are
shared with an identical neighbour, which edge faces a corridor, and which are
its own. The wall belongs to the seam rather than to either room.

Design the artefact so that a later generator can tile the cell into a block
of N bedrooms off a corridor and get the shared walls right by construction.
You are not building that generator; you are defining the cell and its
contract so the generator is possible.

## What to produce

1. **`blueprints/` (new directory) with a `README.md`** defining the library
   format: how a template declares its dimensions, its seam edges, its
   entrance edge, what it requires (a bed), what it declares as intent rather
   than as material ("finished wall"), and how versions and provenance are
   recorded. Follow the spirit of `doctrine/seed.yaml`'s header: stable ids, a
   revision, and honest sourcing.
2. **One bedroom template**, in whatever form the format above defines, with
   the quickfort blueprint content it corresponds to. State plainly which
   quickfort modes it uses and in what order, using the install's own guide
   rather than memory, and note that the guide requires smoothing and
   engraving **before** the build phase because furniture blocks access to the
   walls behind it.
3. A short **rationale** section: why this cell, why these dimensions, what it
   optimises for, and what it deliberately does not include. Record that a
   door is **not** required for privacy (the layout research found the current
   wiki states a sleeping dwarf takes no penalty from others passing through),
   so if the template has a door, justify it on other grounds or leave it out.

## Rules

- **Generic only.** No fort coordinates, no landmark names, nothing that
  reveals this fort's layout. A template is a pattern, not a map of Uniboslan.
- **Data and docs only.** No `.lua`, no `TOOLS.yaml`, no `dfmcp/**`, no
  `agents/**`, no deploy. A sibling stream holds those files right now.
- Read-only against the VM, and only to read the install's own quickfort
  documentation. Do not touch the fort. Use
  `bash scripts/vm-ssh.sh df '<cmd>'`; do not write your own ssh wrapper and
  do not read an address out of `.env`.
- `git merge --ff-only main` first; this brief is committed on main.
- The ambient suite must still pass: baseline **1413 passed, 3 skipped**.
- No em dashes in prose. **No attribution lines in any commit message.**
- Stop and report on any permission or classifier refusal.

## Done means

A blueprint library exists with a documented format, and contains exactly one
bedroom cell that is generic, declares its seams and entrance, requires a bed,
declares its walls as finished without naming a material, and could be tiled
into a shared-wall block by a later generator. The quickfort modes and their
order are stated from the install's own guide, not from memory.

## Result

(to be filled by the stream)
