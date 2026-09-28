# Handoff: what actually marks a mineral as ore/gem worth recovering, ground-truthed against this world's own raws

Date: 2026-09-28. **Researcher, Sonnet. Read-only against VM 103's raw files and the live game via `dfhack-run lua`. No mutation, no deploy.**

## Context

`scripts/dfhack/df-overseer-construction.lua`/`surface.lua` (built earlier
today, `handoffs/2026-09-28-ore-vein-recovery-and-construction-tool.md`)
classify a vein tile as `ore_or_gem` only when the decoded inorganic
material's `.inorganic.economic_uses` is non-empty. Live-tested against the
Manager's Office's known hematite vein (tile 103,101,167, inorganic index 182,
confirmed by `dfhack.matinfo.decode(0, 182):toString()` returning
`"hematite"`): **`economic_uses` reads empty, and `.inorganic.metal_ore` also
reads empty (0 entries)**, for a material everyone (the user, the 2026-09-24
register entry) already knows is iron ore. So the current classification is
provably wrong for the exact case that motivated it, and possibly for others.

The orchestrator's own quick hypothesis (drop the "economic" sub-classification
entirely, just use `MINERAL` vs `STONE` material class, since that's the
distinction the user already used to spot this by eye and the one
`surface.material` already computes correctly) is **a hypothesis to test, not
an accepted answer** -- the user asked for this to actually be researched.

## The question

What is the real, ground-truth signal (in this fort's own raws, and in
DFHack's runtime API) for "this vein is ore or a gem worth mining out before
smoothing/walling," as distinct from ordinary stone?

1. **Read the actual raw text file for this world's hematite entry.** DF
   raws are plain text with literal tags (e.g. `[METAL_ORE:IRON:100]`,
   `[ENVIRONMENT:...]`, `[IS_STONE]`). Find this save's raw files on VM 103
   (likely under the save directory's own `raw/` copy, not just the vanilla
   install's `raw/objects/` -- a world can have generated/altered raws) via
   `scripts/vm-ssh.sh df '...'`, and read hematite's actual tag list directly.
   This settles, unambiguously, whether the vanilla concept this fort's world
   actually uses tags hematite as ore at all, and under what tag name.
2. **Trace that tag to a live-readable DFHack field.** Once you know the real
   on-disk tag (from step 1), find where DFHack's Lua API exposes it at
   runtime (read DFHack's own source -- a scratch clone outside the worktree,
   same pattern as prior research streams here -- for `inorganic_raw`'s real
   struct fields and how `[METAL_ORE:...]`/similar tags map onto them; the
   orchestrator tried `.inorganic.metal_ore` from general knowledge and it
   read empty, so either that's the wrong field, the wrong access pattern, or
   the tag genuinely isn't set for this specific material and vanilla DF
   marks ore a different way entirely -- find out which).
3. **Evaluate the orchestrator's MINERAL-vs-STONE hypothesis on its merits.**
   Does `material_class == MINERAL` reliably mean "vein material, not ordinary
   layer stone" in general (check a few other known minerals/ordinary stone
   tiles on this fort, not just the one hematite case), or does it have false
   positives/negatives DF-side that the "economic"/ore sub-classification was
   trying to filter out? State plainly whether it's a good proxy, a good
   fallback, or wrong.

## What to produce

A findings report (your own file under `research/2026-09-28-ore-detection.md`)
stating: the real tag(s) DF raws use for ore/gem-worthiness, the correct live
DFHack field/access pattern to read it (with an exact code snippet, checked
where possible), whether `economic_uses`/`metal_ore` were simply read wrong or
are answering a different question entirely, and a clear recommendation for
what `surface.vein-material`'s `ore_or_gem` classification should actually
check. If ground truth turns out to be genuinely ambiguous or the tag isn't
present for this specific world, say so plainly.

## Rules

- `git merge --ff-only main` first; this brief is committed on main.
- Read-only: raw file reads and `dfhack-run lua` calls that only print/read
  are fine; no write, no dig, no build, no service restart.
- Do NOT touch `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md`, or the construction/surface Lua files themselves (a
  follow-up fix stream will apply your finding once it's settled).
- No em dashes in prose. No attribution lines in commit messages.
- Commit your research file when done. Stop and report on any permission
  refusal.
- Fill in this handoff's own Result section with the headline finding in
  under 200 words, pointing at the full report for detail.

## Result

(pending)
