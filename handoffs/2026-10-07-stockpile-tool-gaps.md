# Handoff: stockpile tool gaps for the Logistics role

Date: 2026-10-07. **Executor, Sonnet, worktree. Offline; no deploys, no live
VM.** First: `git merge --ff-only main`.

## Why

User's call 2026-10-07: a Logistics role owns stockpiles and links.
`research/2026-10-07-planner-design.md` revision 2 section 6.6 lists what
its tools lack; `research/2026-10-07-stockpile-logistics.md` has the game
facts (a workshop with links uses only its linked piles; orders obey that).

## Scope (design 6.6 items 1 to 6; not 7, 8 or 9)

1. Links-only: read on `stockpile.list`/`links`, write through a settings
   verb. Read the real field from the DFHack/df structures; never hard-code
   its default. If the field name cannot be confirmed from the local DFHack
   source or docs, say so and mark it unverified.
2. Container counts (max bins, barrels, wheelbarrows), read and write.
3. Finer material filters than the 17 categories (which stone, which wood),
   read and write, through the game's own material lists.
4. `stockpile.health` (read): per linked workshop, input classes with no
   non-empty linked source, whether each is available fort-wide
   (`stocks.availability`-style), whether its output link accepts its
   products. `stockpile.plan-feed WORKSHOP_KIND|ID` (read, dry-run spec):
   piles, classes, sizes, links, containers, from a **per-workshop-kind
   input/output table as data** (derived from game data where possible).
5. `stockpile.link` warns in dry run on the single-class trap (a workshop
   linked for some but not all of its input classes, including containers
   and fuel).
6. A pile removal verb, dry run by default.

Every write verb DRY_RUN by default and marked `live_deployed: false,
verified: unverified` in TOOLS.yaml; coordinate-free outputs; no armok.
Do not add the tools to any role allowlist (stage L does that). Tests on
the lupa fake world for each verb.

## Rules

Touched surfaces: `scripts/dfhack/df-overseer-stockpile.lua`, a new data
file for the per-kind table if needed, `scripts/dfhack/TOOLS.yaml`
(stockpile section only), tests, this handoff. Public repo: no hostnames,
IPs or tokens. No em dashes. No attribution lines. Commit after each
milestone. Do not write Working.md, DECISIONS.md, memory or INDEX.md. Full
ambient `python -m pytest` (lupa on PYTHONPATH) and `dfmcp/tests` in
`.venv-dfmcp` green.

## Result

(executor fills this in, including a live verification plan per write verb)
