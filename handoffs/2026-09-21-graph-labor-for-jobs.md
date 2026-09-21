# Handoff: the production graph learns which labor operates each workshop

Date: 2026-09-21. **WRITTEN for review, not dispatched; waits on the Lua
stream's data dump.** Offline build stream, no VM.

Read `CLAUDE.md`, `docs/BUILDING-TOOL.md` (decisions and contract C2),
`docs/PRODUCTION-MODEL.md` sections 3 and 4, then `production/schema.py`,
`production/extract.py` and `production/store.py`, then this.

## Why this stream exists

The user decided operating labor comes from the graph: a workshop's labors are
the labors of the processes it hosts (`production_process.workshop_node` and
`.labor`). Reactions carry their workshop and labor in the raws, but
**hardcoded job types** (`is_hardcoded=1`) do not, and those are where the
gaps and the STONECUTTER-versus-MASON disagreement are. The Lua stream
produces a bounded dump from the live game (job type to skill to labor, and
which jobs each workshop hosts); this stream ingests it.

## Deliverables

1. **Ingest the dump** (path given in the dispatch prompt; it stays out of the
   repo) into `production_process` rows for hardcoded jobs, with
   `workshop_node` and `labor` where known and **null with a stated reason
   where not**. Add whatever `source_ref` scheme is needed. Commit a
   **fixture** of a small, hand-verified subset only.
2. **`production/labors.py`** (new): `labors_for_kind(db_path, kind_token)`
   exactly per **contract C2**. `known` only when every process the kind hosts
   has a determined labor; `partial` if some are null; `unknown` if the kind is
   absent or nothing is determined, each with a reason.
3. **Reconcile the mason's workshop**: report what the data says about
   ConstructBlocks and the workshop's other jobs, and the effect on the
   answer.
4. **A coverage table** in the write-up: kinds by status, and how many
   hardcoded jobs have a null labor and why. An honest table matters more than
   green tests.

## Rules that bite here

- Nothing may be presented as verified that came from a guess. An unresolvable
  labor stays null; never fill with a default.
- Extraction is idempotent and must not erase observations (see the fix in
  `production.store`).
- Do not touch `dfmcp/**`, `scripts/dfhack/**`, `gotchas/**` or
  `docs/BUILDING-TOOL.md`. Do not write `Working.md`,
  `decisions/DECISIONS.md`, `memory/` or `handoffs/INDEX.md`. **Commit after
  each milestone.** No em dashes.

## Touched surfaces

`production/**` and this doc.

## Done means

`labors_for_kind` matches C2 on real dump data, the fixture tests pass, the
coverage table is written, the suite passes (**552 passed / 1 skipped**,
report before and after), and the mason's-workshop question has an answer or
an honest "unresolved, and why".

---

## Report (executor, 2026-09-21)

**Status: done, with the graph honest about what it does not know.** Built
`production/labors.py` (contract C2) and `production/labor_ingest.py` (the dump
to graph step), changed the extractor so it stops writing a skill token into a
labor column, and added 63 tests plus a fixture. Nothing outside
`production/**` and this doc was touched. Commits are on the worktree branch;
the orchestrator merges.

### The finding that shaped the build: `labor` never held a labor

`extract.py` wrote `[SKILL:...]` into `production_process.labor`. A skill is not
a labor (BREWING is not BREWER, CARPENTRY is not CARPENTER, MASONRY is not
MASON) and the raws carry no translation. A reader taking that column at its
word would have returned skill names as operating labors, the silent-wrong
shape this repo keeps shipping. Fixed at the source: the extractor now leaves
`labor` NULL and records the skill as a `skill` attribute; the ingest fills
`labor` only from the game's own tables and records how in a `labor_basis`
attribute. `docs/PRODUCTION-MODEL.md` still says the labor comes from
`[SKILL:...]` (orchestrator to correct; I did not touch it). A database
extracted before this change is **refused** by the ingest with "re-run
extraction", not silently misread.

### What was built

- `labors_for_kind(db_path, kind_token)`, C2 exactly, plus additive keys
  (`profile_labors`, `unexplained_profile_labors`, `undetermined_process_count`,
  and `reason` / `candidate_labor` on an undetermined process). The C2 consumer
  ignores extra keys.
- **Status rule, stricter than the handoff's literal wording, on purpose.**
  `known` needs the kind to host at least one process, **every** hosted process
  to have a determined labor, **and** the game's own Workers-tab list for the
  kind (S2) to be non-empty and fully explained by the hosted processes. Reason:
  the Lua stream established that job hosting has no complete source (66
  workshop-like jobs attributed to no kind; the forges unfinished in DFHack's
  table), so "every process we know has a labor" would say `known` for an
  incomplete list. An S2 labor that no hosted process explains proves the list
  is incomplete; an empty S2 offers no check, so such a kind is at best
  `partial`. The literal reading is computed alongside
  (`coverage()["literal_known"]`) so the cost is visible: **11 kinds would be
  known under the literal rule, 2 are under the strict one.**
- Determination comes **only** from the game's tables: the job's skill's labor,
  a direct labor on the job, or the skill map (a skill some job references).
  Name matches and the Workers-tab list are recorded as `candidate_labor`, never
  in `labors`. Three further refusals leave a labor NULL with a reason:
  material-dependent (only `skill_metal`/`stone`/`wood` overrides, so which
  applies depends on the item), **contradicts the Workers tab** (the table's
  labor is not among a non-empty S2 for that kind: the job table cannot tell a
  wooden block from a stone one, so `ConstructBlocks` is STONECUTTER at the
  Carpenter's Workshop whose Workers tab is [CARPENTER, TRAPPER]; and
  `CatchLiveLandAnimal` is TRAPPER at the Butcher's Shop, whose tab lacks it),
  and a job type missing from the table.
- The ingest does its **own** job to labor join from the raw fields, and I
  cross-checked it against the dump's pre-joined table: 74 of 74 rows agree
  except the one Butchers row my S2 guard deliberately refuses (the
  Carpenter's `ConstructBlocks` row, the other guarded one, was checked
  directly).
- A kind's node in the graph is derived from the data (the raws' node where the
  reactions the game lists for the kind were extracted), not asserted: `Kiln` and
  `MagmaKiln` share `BUILDING:KILN`, `Smelter` and `MagmaSmelter` share
  `BUILDING:SMELTER`, `Quern` and `Millstone` share `BUILDING:QUERN`. A kind no
  extracted reaction reaches gets a constructed node `BUILDING:KIND:<Token>` (17
  of 33). Kind attributes are `kind:<Token>` subjects: `node`,
  `profile_labors`, `building_class`.
- **Reactions the game lists that the extractor never read** (S3 has 293
  distinct hosted reactions; the extractor's four vanilla files give 148) are
  added as process rows with a NULL labor and reason `unextracted_reaction` (145
  rows). Without them Craftsdwarfs would look as if it hosted 4 processes
  instead of 104.
- Idempotent: every row the ingest writes has a `source_ref` starting `dump:`;
  a re-run deletes exactly those and resets the `labor` it set on extractor rows
  (tested: run twice gives identical tables; a re-run without a fuller skill
  table resets labors it had filled). `production_observation` is untouched
  (tested). It finishes with `journal_mode=DELETE`.

### Coverage table (the real dump, and a real extraction of the install's `vanilla_reactions`, out of tree)

Kinds the graph holds hosted-job data for (33 workshop and furnace kinds):

| status | count | kinds |
|---|---|---|
| known | 2 | Fishery, Jewelers |
| partial | 18 | Ashery, Butchers, Carpenters, Dyers, Farmers, GlassFurnace, Kiln, Kitchen, Loom, MagmaKiln, MagmaSmelter, Masons, Mechanics, Millstone, Quern, Siege, Smelter, WoodFurnace |
| unknown | 13 | Bowyers, Clothiers, Craftsdwarfs, Kennels, Leatherworks, MagmaForge, MagmaGlassFurnace, MetalsmithsForge, SCREW_PRESS, SOAP_MAKER, Still, Tanners, Tool |

Over quickfort's 175 building tokens, the other 143 (furniture, constructions,
tracks, wells, farm plots, trade depot) are all `unknown` with the reason "the
graph has no record of a workshop or furnace kind ...: an absence of data, not
an absence of labor". Under the literal rule (no closure check) the known set
would be Ashery, Dyers, Fishery, Jewelers, Kitchen, Loom, MagmaSmelter,
Mechanics, Siege, Smelter, WoodFurnace (11).

Processes (366 in all, 129 with a determined labor, 237 without):

| group | total | determined | undetermined | why undetermined |
|---|---|---|---|---|
| hard-coded jobs | 73 | 31 | 42 | 39 no labor in the game's job table; 2 contradict the Workers tab; 1 material-dependent |
| reactions | 293 | 98 | 195 | 145 not extracted from the raws; 50 have a skill absent from the skill table read |

The dump's 74 (kind, job) rows become 73 processes: Smelter and MagmaSmelter
share a node and were merged (the labor was the same). The 39 with no labor
reproduce the Lua stream's count exactly. Of the undetermined processes, 23 (20
reactions, 3 jobs) carry an inferred candidate (skill name equals a labor name
and the labor is in the kind's Workers tab); none is counted as a labor.

**Skills the dump does not map** (50 extracted reactions): BREWING (3),
CARPENTRY (23), GLAZING (4), POTTERY (6), PAPERMAKING (3), PRESSING (3),
BOOKBINDING (3), SOAP_MAKING (2), TANNER (2), WAX_WORKING (1). The dump maps
only the 46 skills that some job references. This is why **Still is `unknown`**
today (all three reactions are BREWING) and Carpenters is `partial` with one
labor (TRAPPER), CARPENTER appearing only in `unexplained_profile_labors`.

### The Mason's Workshop: answered from the data

`labor_ingest.mason_reconciliation` computes it from the dump; the values are in
the ingest report and pinned by a test:

- `ConstructBlocks` is skill CUT_STONE, whose labor is **STONECUTTER**.
- The Mason's Workers tab is [STONECUTTER, STONE_CARVER]; **no kind's tab offers
  MASON**, and no job type's skill maps to MASON. So **MASON is not an operating
  labor of the Mason's Workshop** in this game data, agreeing with
  `research/2026-09-21-building-requirements.md` and the Lua stream's
  `constructblocks_finding.json`. `df-overseer-workshop.lua`'s `mason` entry
  (`labor = "MASON"`) is the wrong labor for block work.
- The workshop's other 15 hard-coded jobs (`ConstructDoor`, `ConstructTable`,
  `ConstructStatue`, `ConstructQuern` and the rest) have skill -1 in the job
  table, so their labor is **not derivable** and stays NULL. S2 hints
  STONE_CARVER; that is an inference, reported only as
  `unexplained_profile_labors: ["STONE_CARVER"]`, never as a labor. Three
  Mason's reactions the game lists (`MAKE_ENT16 INP1_BODY` and two more) are not
  in the extracted raws.
- **Effect on the answer:** `labors_for_kind("Masons")` returns `partial`,
  `labors: ["STONECUTTER"]`, `unexplained_profile_labors: ["STONE_CARVER"]`, with
  the reason "18 of 19 hosted processes have no determined labor (...)". The
  Carpenter's `ConstructBlocks` is refused rather than filed under STONECUTTER.
  Not proven by watching a dwarf make blocks (the one live block job was
  cancelled for lack of boulders); it rests on three concordant static sources.

### Tests

Ambient `python -m pytest`: **before 698 passed / 3 skipped, after 762 passed /
2 skipped** (`production/` 87 to 150). `dfmcp/tests` in `.venv-dfmcp`: **430
passed** (I did not touch `dfmcp/**`). **The previously skipped
`dfmcp/tests/test_labor_join.py::test_the_real_function_matches_the_signature_when_it_exists`
now runs and passes** against the real signature. A further test drives the
server's real `LaborJoin` with the real `labors_for_kind` (not a stub) and pins
that `unknown` arrives as `labors: null`, never `[]`. Checks that could
actually have caught the bug class: an absent database raises and is not
created; reading leaves the file byte-identical; a valid SQLite file that is not
a graph raises; a pre-split graph is refused; both opens failing raises rather
than answering empty.

### What remains unknown, and what to do next

1. **The skill to labor table is the biggest cheap win.** One read-only Lua loop
   over `df.job_skill.attrs[i].labor` (all skills, not only the 46 jobs
   reference) would determine the 50 undetermined reactions and move Still, Kiln,
   Carpenters and Farmers toward `known`. The ingest already takes it: `python -m
   production.labor_ingest DB DUMP_DIR --skill-labors skills.json` with
   `[{"skill": "BREWING", "labor": "BREWER"}, ...]` (labors validated against
   the dump's 94, conflicts refused, the S2 guard applies to it too). An
   untested sketch of the read, for the Lua stream to make real: `for
   i=0,df.job_skill._last_item do local a=df.job_skill.attrs[i];
   print(df.job_skill[i], a.labor >= 0 and df.unit_labor[a.labor] or 'NONE')
   end`.
2. **Extract the 145 reactions the extractor never read.** They are instrument
   and craft reactions (`MAKE_ENT..` and similar) from raw files outside the four
   `DEFAULT_REACTION_FILES`. Until then Craftsdwarfs (104), Metalsmith's and
   Magma Forge (15 each), Leatherworks (6), the glass furnaces (13 each) and 7
   Kiln reactions cannot be resolved.
3. **The 66 workshop-like job types attributed to no kind** are not ingested:
   no kind can be named for them without a guess. The S2 closure check is what
   stops this making a wrong kind `known` (it is also why the Still shows
   HERBALIST as unexplained: jobs like `ExtractFromPlants` are among the
   unattributed).
4. **S2 is not fully trustworthy for the custom workshops.** The dump gives
   SOAP_MAKER and SCREW_PRESS the same [PRESSING, PAPERMAKING]; the requirements
   research already found DFHack wrongly gives the Soap Maker those. Both are
   `unknown` today so no wrong answer is served, but a fuller skill table would
   let the closure check compare SOAP_MAKER against a wrong list.
5. **Server-side follow-ups (not mine to do).** `processes` is 104 items for
   Craftsdwarfs and 70 for Dyers, and `dfmcp.labor_join` passes the list through
   to the agent; the server stream may want to summarise it. It should also
   surface `unexplained_profile_labors` (the STONE_CARVER-shaped hint), which it
   ignores today as an additive key.
6. **Existing raw fixtures disagree with the real raws.** `reaction_*.txt` name
   buildings `CARPENTERS`, `DYERS`, `FARMERS` where the real raws say
   `CARPENTER`, `DYER`, `FARMER`, and use reaction ids the game lacks; my tests
   use a hand-built graph of real ids instead, and
   `fixtures/labor_dump/PROVENANCE.md` says why. The extractor also writes the
   raws path into `source_ref`, so a graph extracted from a scratch directory
   carries that local path (pre-existing; keep such a database out of the repo).

### How `production.labors` opens its database under the server's sandbox (unproven live)

It never uses `store.connect` (which creates the file, sets `journal_mode=WAL`
and runs DDL: all writes). It opens read-only by URI (`mode=ro`); if that raises
(a WAL database in a read-only directory under `ProtectSystem=strict`, the same
"unable to open database file" that broke every `series.*` call until
`ReadWritePaths` was added) it retries with `immutable=1`, which reads the main
file alone. That is safe only for a closed file: the ingest ends with
`journal_mode=DELETE`, so the deployed file has no `-wal` to lose. Any later
extraction flips it back to WAL (via `store.connect`), so re-ingest before
deploying, or deploy with SQLite's `.backup`. **Tested here** on Windows:
read-only open, writes refused, no file created when absent, byte-identical
after reads, and the fallback order (with `sqlite3.connect` monkeypatched to
fail the first open). **Not tested:** a real `ProtectSystem=strict` read-only
directory on the VM. The deploy stream should run `labors_for_kind` once as the
server's own user against the deployed file. The path the server expects is
`/var/lib/dfproduction/uniboslan.production.sqlite3` (`dfmcp/labor_join.py`);
nothing creates that directory or file yet, so until a deploy the server reports
`unknown: the production graph database was not found`, which is the correct
behaviour.

### How to reproduce

```
python -m production.extract            # writes production/uniboslan.sqlite3 (gitignored)
python -m production.labor_ingest production/uniboslan.sqlite3 <building-dump dir>
```
`extract.main` reads the committed reconstructed fixtures; the real coverage
above came from the same code pointed at the real raws, out of tree, as in
`research/2026-09-19-real-corpus-extraction.md`.
