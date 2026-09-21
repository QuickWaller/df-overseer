# extra_reactions fixture provenance

Read on 2026-09-21, read-only, from the install on the game VM, into an
out-of-tree scratchpad, then copied here **verbatim**. Nothing was rewritten or
invented. These files are deliberately in a subdirectory so that
`extract.discover_reaction_files(FIXTURES_DIR)` (which globs the flat directory)
keeps returning exactly the four reconstructed vanilla fixtures beside it.

**What these are not.** They are not the 145 reactions the game lists that the
extractor never read. Those (all named `MAKE_ENT<n> <INSTRUMENT PART>`, for six
entity ids) are **not in any raw text file on the install**: they are generated
when the world is created and exist only in the world save and in the running
game. See `handoffs/2026-09-21-extract-remaining-reactions.md`. What follows is
the closest real text there is, in the same shape.

| file | source on the install | what was kept |
|---|---|---|
| `reaction_instrument_example.txt` | `data/vanilla/examples and notes/reaction_instrument_example.txt` | the whole file, 4 reactions. The game's own worked example of the instrument reactions (drum body, drum head, assembled drum, wind instrument) whose world-generated counterparts are the 145: `TOOL` reagents that carry an item subtype, `INSTRUMENT` and `TOOL` products with material taken from a reagent, `IMPROVEMENT`, `PRODUCT_TOKEN`, `USE_BODY_COMPONENT`, `UNROTTEN`, `DESCRIPTION`, `BUILDING:CRAFTSMAN:NONE`. |
| `reaction_steam_engine.txt` | DFHack's `hack/raw/reaction_steam_engine.txt` (shipped with DFHack, installed into the game's raws) | the whole file, 1 reaction: two `[BUILDING]` lines, a `[FUEL]` before any reagent, free prose between tokens, two tokens on one line. |
| `reaction_spatter.txt` | DFHack's `hack/raw/reaction_spatter.txt` | lines 1 to 55, the first 2 of 7 reactions (`SPATTER_ADD_OBJECT_LIQUID`, adventure-mode only with no building, and `SPATTER_ADD_WEAPON_EXTRACT`). The other 5 are the same shape and were dropped whole. |

Values the tests pin were each read off these files: the instrument example has
4 `[REACTION]` blocks; `MAKE EXAMPLE DRUM` takes reagents
`TOOL:EXAMPLE DRUM BODY` and `TOOL:EXAMPLE DRUM HEAD` and has two `IMPROVEMENT`
lines; `STOKE_BOILER` lists `STEAM_ENGINE` then `MAGMA_STEAM_ENGINE` and carries
`PRODUCT_DIMENSION:2000`; `SPATTER_ADD_OBJECT_LIQUID` has `ADVENTURE_MODE_ENABLED`
and no `BUILDING`.

Licensing note: the instrument example is Bay 12 Games' own shipped data, the
other two are DFHack's (zlib licence). All three are small and are kept only so
the parser is tested against real syntax rather than syntax this repo made up,
the same reason the earlier `reaction_*.txt` fixtures cite the audit's quotes.
