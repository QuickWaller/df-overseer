# Labor dump fixture provenance

These three files are a **filtered subset** of the building-tool Lua stream's
out-of-tree dump (`handoffs/2026-09-21-building-tool-lua.md`, Deliverable 4),
which was a bounded read-only read of the live game on 2026-09-21. Entries are
copied verbatim; only whole entries were dropped. Nothing was rewritten or
invented.

- `job_types.json`: 21 of 259 job types (those the fixture kinds host, plus a
  few whose skills fill the skill to labor map), and the 31 labor names those
  reference.
- `workshop_hosting.json`: 16 of 33 kinds, each with its S2 Workers-tab labor
  list untouched, its S1 hard-coded jobs filtered to a handful and its S3
  reactions filtered to a few. The dump's pre-joined
  `hardcoded_jobs_with_labors_by_kind` and its 193-name unattributed list are
  dropped (the ingest does its own join).
- `quickfort_kinds.json`: 8 of 175 kinds.

The graph the tests pair with it (`../../labor_helpers.py`) uses **real**
reaction ids, building tokens and skills, taken from a real extraction of this
install's `vanilla_reactions` raws (out of tree, 2026-09-21). It deliberately
does not use `reaction_*.txt` beside this directory: those reconstructed
fixtures name buildings `CARPENTERS`, `DYERS` and `FARMERS` where the real raws
say `CARPENTER`, `DYER` and `FARMER`, and give reactions ids the game does not
have (`MAKE_WOODEN_CHAIR` for the real `MAKE WOODEN CHAIR`), so the dump's
reaction lists could not join to them.

Values the tests pin were each read off the real dump: `ConstructBlocks` is
skill `CUT_STONE` whose labor is STONECUTTER; `ConstructDoor`, `ConstructTable`
and `ConstructQuern` have skill -1; `MakeFlask` has only a `skill_metal`
override; `CollectSand` has a direct labor `HAUL_ITEM`; the Mason's Workshop's
Workers tab is [STONECUTTER, STONE_CARVER]; the Carpenter's is [CARPENTER,
TRAPPER]; the Still's is [BREWER, HERBALIST].
