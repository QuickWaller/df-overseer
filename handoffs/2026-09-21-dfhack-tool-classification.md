# Handoff: classify every DFHack tool for this project

Date: 2026-09-21. **Research stream for a `researcher` agent on Sonnet.**
Read-only against the repo apart from the two output files. No VM, no live game.

Read `CLAUDE.md` (especially "Tools must be generalisable" and "No armok
tools"), `docs/PURPOSE.md` design commitments, `docs/AGENT-ARCHITECTURE.md`
section 3 (the roster), `agents/*/role.md` (what each role is for) and
`docs/DFHACK-INVENTORY.md` (the input), then this.

## What this is for

**The classification is research toward the openclaw agent design** (user,
2026-09-21): what DFHack already gives us and what we must build. The summary
must therefore include a **"Coverage against the minimum bar"** section (added
by message during the run): for each of building workshops, rooms and zones,
furniture placement and assignment, assessing dwarves, growing food, wells and
water, stockpiles, appointing a Manager and nobles, confirming completion,
game clock, quicksave and defence, name the DFHack tools that provide it and
say plainly where nothing exists.

The user wants every DFHack tool on this install categorised so the project
knows which will be used, which will not, which are grey areas, who would use
each, whether it reads or writes, and how it fits a category scheme. The
result drives what we build wrappers for and what the future investigator
role may touch. **The project has three enabled roles (overseer, architect,
consultant) and three defined but not yet enabled (quartermaster, marshal,
chronicler).** Roles only ever act through tools served by our MCP server, so
"who would use it" means "which role's tool list should a wrapper of this
appear on, if we built one".

## Input

`docs/DFHACK-INVENTORY.md` lists **443 tools** (338 available, 105 tagged
`unavailable`), each with DFHack's own one-line summary, tags and kind. The
full documentation for every tool, for when the summary is not enough, is at
`C:/Users/wills/AppData/Local/Temp/claude/c--website-projects-df-automation/5c2ab084-dd15-4491-b563-0228954a198d/scratchpad/dfdocs/tools/<id>.txt`
(ids with a slash are subdirectories, for example `gui/quantum.txt`). Read a
full doc only when the summary and tags cannot settle a judgement; most
cannot need it.

## Rules for the classification

1. **Armok (corrected by the user during the run).** The ban is on the
   **capability**, not the tag: powers a player does not have (heal, teleport,
   spawn, skip costs, alter the world) and information the game hides. The
   `armok` tag is only a pointer. Judge each armok-tagged tool on what it does:
   `use: wont`, `wont_reason: armok` only when it grants a power or reveals
   hidden information; otherwise give it a normal verdict and explain in
   `notes` why the tag is coarse for it. Always set `armok: true` from the tag.
   List in the summary the armok-tagged tools the tag wrongly points at.
2. **Unavailable.** Tools tagged `unavailable` get `use: wont`,
   `wont_reason: unavailable`. Still give a description and a broad category;
   skip the fine category and role judgement (`roles: []`).
3. **Use verdicts** (the rest):
   - `will`: a role plausibly wants this in normal play of this project
     (fort survival, building, logistics, labor, defence, reading state).
   - `wont`: not useful to an agent playing this fort headless. Common
     reasons: needs a human at the screen (most `gui/*` tools that are only
     dialogs), developer or debug tooling, adventure-mode or embark-only,
     pure interface tweaks, or cosmetic. Give a specific reason.
   - `grey`: it could help but there is a real question (works only through a
     GUI but has a command mode; overlaps a tool we already built; helps only
     late game; risky to automate; depends on an unresolved design choice).
     **State the question in one sentence.**
4. **Read or write**: `read` (inspects only), `write` (changes game state,
   files or configuration), or `both` (has subcommands of each). If a tool has
   both, list the read subcommands and the write subcommands in
   `rw_detail` when the doc shows them. A tool that only changes a setting or
   turns an automation on is `write`.
5. **Roles**: a list drawn only from `overseer`, `architect`, `consultant`,
   `quartermaster`, `marshal`, `chronicler`. A role is included if a wrapper of
   this tool would sensibly be on that role's tool list. Use each role's
   charter, not its name. `overseer` is the sole writer: a `write` tool
   belongs to `overseer` (and only to advisors as a read side). Empty list for
   every `wont`.
6. **Categories**: one **broad** category from the fixed list below, one
   **fine** category of your own. Keep the fine vocabulary small and
   consistent (aim for well under 80 distinct values, reused), and **define
   each fine category in one line** in the summary file. Broad list:
   `food-and-drink`, `construction`, `stockpiles-and-logistics`,
   `labor-and-jobs`, `work-orders`, `units-and-health`, `military-and-defence`,
   `map-and-digging`, `items-and-materials`, `animals`, `plants-and-farming`,
   `trade-and-diplomacy`, `inspection`, `game-control`, `bugfix`, `interface`,
   `developer`, `cheat`, `other`. If none fit, use `other` and say why in the
   summary.
7. **Description**: two or three plain sentences saying what the tool actually
   does for someone who has never used DFHack, in this project's terms (a
   fort, citizens, stockpiles). **Not** a copy of DFHack's summary. If you
   could not tell from the docs, say so in the description rather than guess.
8. **Overlap with ours**: if we already built a tool that does this (see
   `scripts/dfhack/TOOLS.yaml`), set `overlaps_ours` to that tool's name and,
   in one sentence, say whether it is a replacement, a complement, or the thing
   our tool wraps. Otherwise leave it out.
9. **Generalisability** (the project rule): where several tools do one job for
   different kinds, or one tool takes a kind argument, note it in
   `notes`. Do not invent structure the docs do not show.
10. **Nothing is presented as verified.** You are reading documentation.
    Where the docs are unclear, vague or contradict the tags, say so.

## Output

Two new files, and nothing else:

1. **`research/2026-09-21-dfhack-tool-classification.yaml`**: one entry per
   tool id in the inventory, **all 443, no omissions**, in inventory order.
   Every entry has exactly these keys:

   ```yaml
   - id: quickfort
     description: "..."
     use: will            # will | grey | wont
     use_reason: "..."    # one sentence; required for grey and wont
     wont_reason: null    # armok | unavailable | gui-only | developer | interface | cosmetic | adventure-or-embark | other
     grey_question: null  # required when use is grey
     armok: false         # from the tag
     unavailable: false   # from the tag
     rw: both             # read | write | both
     rw_detail: "..."     # optional
     roles: [overseer, architect]
     category_broad: construction
     category_fine: blueprint-application
     overlaps_ours: null  # or "workshop.build: wraps it"
     notes: null
   ```

   **Write it incrementally**: append after every ~40 tools and commit
   nothing, so that if your session ends the finished part survives on disk.
   Say in your final message how many tools are done.
2. **`research/2026-09-21-dfhack-tool-classification.md`**: a short summary
   (not a re-listing). Counts by use verdict, by broad category and by rw;
   the fine-category vocabulary with one-line definitions; the **grey list**
   with each question; the **armok exceptions list** and any of our scripts
   that call an armok tool (rule 1); the tools that overlap ours and whether
   each is a replacement or complement; anything you could not classify and
   why; and what you would check next.

## Do not

- Do not touch any other file, run any command against the VM, or call the
  live game. Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`. Do not commit.
- No em dashes in prose. No addresses or hostnames anywhere.

## Done means

The YAML has an entry for every one of the 443 tool ids with all keys present
and only allowed values; every `grey` has a question and every `wont` has a
reason; the summary answers each item above; and your final message states the
counts and what is uncertain.
