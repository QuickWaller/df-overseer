# Fixture provenance

This offline stream had no VM, no SSH, no DFHack and no fort
(`handoffs/2026-09-18-production-package.md`), and no raws mirror exists
anywhere in this repo (checked: `find . -iname '*reaction*'` /
`*plant_standard*` / `*vanilla*` under the repo root, zero hits). The
handoff's two sanctioned options were "a local raws mirror if one exists in
the repo" (it doesn't) or "commit a small, clearly-labelled set of real
fixture files... genuine excerpts... never hand-written approximations."

What "genuine" means here: `research/2026-09-18-schema-extraction-static.md`
already did a real, read-only, line-cited audit of VM 103's actual install
this session did not have access to. Every fixture file below is built from
**that audit's own quotes and verified findings**, not from this stream's
general knowledge of Dwarf Fortress. Each file's header names, line by line,
which content is:

- **QUOTED** — the audit reproduces this exact token/line verbatim, citing
  its own file:line on the real install. These are as genuine as this
  stream can get without VM access.
- **STRUCTURAL** — required DF raw syntax (the `[REACTION:...]` / `[PLANT:
  ...]` / `[REAGENT:...]` grouping, indentation) that no fixture file can
  omit and still parse, but that the audit did not itself need to quote
  because it is the fixed format, not raw-authored content.
- **RECONSTRUCTED** — a token name and its real presence/absence is
  audit-verified (e.g. "GLAZE reactions use `[IMPROVEMENT:...]`" or
  "`PROCESS_PLANT_TO_BAG` is in the inherited-material bucket"), but the
  audit did not quote the complete literal line, so the full line here is
  this stream's construction from the verified facts. Flagged per-line.
- **ILLUSTRATIVE** — a plausible reaction/plant this stream invented to
  exercise a code path the audit describes only in aggregate (e.g. "68
  dye reactions, each `PLANT_MAT:<species>:<part>`" with no single example
  quoted). Never presented as verified; used only where no test in the
  handoff's list depends on its being real.

Where a real DF mechanic is well known (e.g. that `BREW_DRINK_FROM_PLANT`
yields both a drink and a seed) but the exact raw line was not quoted this
session, this stream used the **RECONSTRUCTED** tag and cited the
corroborating research this project already has on record
(`research/2026-09-17-seed-ratios.md`, cited by the audit itself as
settling the brew/seed yield figures), rather than presenting it as a raw
read.

## Per-file breakdown

- **`reaction_other.txt`** — `BREW_DRINK_FROM_PLANT` (barrel/plant reagent
  lines and the DRINK product line are QUOTED, citing
  `reaction_other.txt:269/271-278/273/277` in the audit; the SEEDS product
  line is RECONSTRUCTED per the audit's own citation of
  `research/2026-09-17-seed-ratios.md`), one `GLAZE_*` reaction
  (RECONSTRUCTED: `[NOT_IMPROVED]`/`[PRESERVE_REAGENT]`/no-`[PRODUCT]`
  pattern and the `[IMPROVEMENT:...]` token are audit-verified; the full
  block is this stream's construction), `PROCESS_PLANT_TO_BAG`
  (RECONSTRUCTED: the `HAS_MATERIAL_REACTION_PRODUCT:BAG_ITEM` reagent
  filter is audit-verified by name; the surrounding block is constructed).
- **`reaction_adv_carpenter.txt`** — one carpentry reaction
  (RECONSTRUCTED: "tool in nearly every carpenter reaction
  (`[PRESERVE_REAGENT][HAS_EDGE]`)" and "every piece of furniture/tool made
  from log inherits whatever wood the carpenter used" are audit-verified
  patterns; the specific reaction is illustrative of that pattern).
- **`reaction_smelter.txt`** — the flux boulder reagent line is QUOTED
  verbatim (`reaction_smelter.txt:143` in the audit); the reaction it sits
  in is ILLUSTRATIVE (the audit describes the smelter alloy set, not one
  named reaction).
- **`reaction_dyes.txt`** — ILLUSTRATIVE. The audit gives the aggregate
  pattern (68 entries, each `PLANT_MAT:<species>:<part>`, fixed non-parametric
  material) and a count, never a single literal example line.
- **`plant_standard.txt`** — `GROWDUR`/season-flag values for plump helmet,
  pig tail, cave wheat, sweet pod are QUOTED (audit §7, citing specific
  lines); dimple cup's season flags were not quoted by the audit and are
  RECONSTRUCTED (marked in-file). All five crops' `MATERIAL_REACTION_
  PRODUCT:DRINK_MAT`/`SEED_MAT` *presence* is QUOTED (audit §2, citing
  `plant_standard.txt` lines 13-14/69-71/117-118/164-165/282-283); the
  exact token argument list is RECONSTRUCTED (the audit names the token,
  not its full internal argument syntax). Quarry bush's
  `ITEM_REACTION_PRODUCT:BAG_ITEM` presence is QUOTED (audit §3, citing
  `plant_standard.txt:223`); its full line is RECONSTRUCTED.
- **`material_template_default.txt`** — `[ROTS]` presence on
  `STRUCTURAL_PLANT_TEMPLATE` and confirmed absence from
  `PLANT_ALCOHOL_TEMPLATE`/`PLANT_POWDER_TEMPLATE`/`SEED_TEMPLATE` are all
  QUOTED findings (audit §6); the templates are otherwise abbreviated
  (audit describes them as 60-line and 41-line blocks this stream does not
  reproduce in full).
- **`item_tool.txt`** — `ITEM_TOOL_WHEELBARROW` and `ITEM_TOOL_MINECART`
  are QUOTED verbatim, whole blocks, from the audit §8 (`item_tool.txt`
  lines 213-223 / 200-211 on the real install). `ITEM_TOOL_JUG` and
  `ITEM_TOOL_LARGE_POT` blocks are RECONSTRUCTED: the individual `SIZE`
  (300/5000) and `CONTAINER_CAPACITY` (10000/60000) values are QUOTED from
  the audit's §8 text, assembled into block form here.

## What this means for the coverage table

Counts in the handoff write-up are extraction results **against this small
fixture subset**, not the full 159-reaction vanilla corpus — that full
corpus was never available to this stream. The extraction *logic* (the
two-pass architecture, the consumption derivation, the `token_family`
strictness) is exercised faithfully; the *row counts* are not a claim about
coverage of the real install.
