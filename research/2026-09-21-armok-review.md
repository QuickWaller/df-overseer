# Review of the 99 `armok`-tagged DFHack tools: is any of them usable?

Date 2026-09-21. Research stream from `handoffs/2026-09-21-armok-review.md`.
**Advice for the user, who decides each exception.** Nothing here was run: no VM,
no live game. Everything below is read from DFHack's own tool docs (copied to a
scratchpad from the install) plus this repo's docs and decisions. Where the docs
were unclear it says so; the closing section lists what would settle each doubt.

Judged against the project's commitments: agents know only what a vanilla player
could know, and "acting on hidden tiles is allowed, sensing them is not"
(`decisions/DECISIONS.md` 2026-09-16); no rendered map is ever shown to a model
(`docs/PURPOSE.md` commitment 1); the run must stay a fair account of what an
agent did (the public report); tools must be generalisable (`CLAUDE.md`).

## 1. Answer up front

**Counts by verdict (99 tools):** 88 keep-banned, 7 candidate-exception,
4 needs-user-ruling. The 88 are not close calls: they write, spawn, heal,
teleport, reveal, or finish work instantly. The exceptions are narrow and all rest
on a handful of read-only forms.

**Shortlist, by name and exact scope:**

| Tool | Verdict | Allowed scope | Role |
|---|---|---|---|
| lever | candidate | `list`, `show`, `pull` (no `--instant`, no `--priority`) | overseer; architect reads |
| prospector | candidate | fort-time `prospect [--show ...]`, never `all` or `hell`; pending a source check | architect, overseer, consultant |
| locate-ore | candidate | default mode (discovered veins), never `--all`; pending a source check | overseer; architect reads |
| diplomacy | candidate | no-argument read only | overseer, later quartermaster |
| justice | candidate | `list` only, never `pardon` | overseer, later marshal |
| assign-preferences | candidate, low priority | `--show` only | overseer |
| pref-adjust | candidate, low priority | `list`, `show` only | overseer |
| caravan | ruling | `list` (days-remaining withheld) and `unload` if bug repairs are allowed; never `extend`, `happy`, `leave` | overseer, later quartermaster |
| showmood | ruling | no arguments, if the vanilla UI already shows a mood's needs | overseer |
| cleaners | ruling | `clean map` by the harness on a schedule, not an agent | none (harness) |
| clear-smoke | ruling | same, harness only | none (harness) |

**Two things to weigh before granting any of these.** First, every candidate is a
pure read (plus `lever pull` and `locate-ore` designating, both ordinary player
actions), and each read could be rebuilt as our own tool, which the rule does not
cover, so an exception only buys use of the shipped script. Second, several
judgements depend on "the vanilla UI shows the same", which I could not check
from documentation; section 6 says what settles each. Useful and should stay
banned: `dig-now`, `build-now`, `teleport`, `full-heal`, `remove-stress`,
`createitem`, `caravan extend` (section 4).

## 2. All 99 tools

Breaks legend: **HI** hidden-information, **GP** grants-power, **ST**
skips-cost-or-time, **CS** changes-the-story, **none** breaks nothing.
Verdicts: **KB** keep-banned, **CAND** candidate-exception, **RULE**
needs-user-ruling. "Scope" is filled only for CAND and RULE; every KB row is
banned whole, including any harmless subcommand (those are listed in section 5).
None of our own `scripts/dfhack/*.lua` tools invokes any of these 99: the only
matches are comments and common English words (checked by grep, 2026-09-21).

| Tool | What it does | Breaks | Verdict | Scope |
|---|---|---|---|---|
| adaptation | Shows or sets a unit's cave adaptation level (0 to 800000). | GP (set); HI probable (show, docs do not say the UI shows the number) | KB | |
| add-thought | Injects an emotion or thought into a unit. | GP, CS | KB | |
| aquifer | Lists aquifer tiles per z-level; adds, drains or converts aquifers. | HI (list covers undug rock), GP | KB | |
| armoks-blessing | Sets every dwarf's stats, personality and (optionally) skills to ideal or legendary. | GP, CS | KB | |
| assign-attributes | Sets a unit's physical and mental attribute tiers. | GP, CS | KB | |
| assign-beliefs | Sets a unit's beliefs and values. | GP, CS | KB | |
| assign-facets | Sets a unit's personality facets. | GP, CS | KB | |
| assign-goals | Sets or clears a unit's life goals. | GP, CS | KB | |
| assign-preferences | Sets a unit's likes and dislikes; `--show` prints the current ones. | GP (set); none (`--show`) | CAND | `--show` only, never `--reset` or any `--like*`/`--hate*`. Role: overseer. Low priority, see section 3 |
| assign-skills | Sets or clears a unit's skills up to Legendary+5. | GP, CS | KB | |
| autodump | Teleports items marked for dump to a cursor tile, or destroys them, instantly. | ST, GP | KB | |
| bodyswap | Takes control of any visible unit (adventure mode). | GP; moot in fort mode | KB | |
| brainwash | Rewrites a dwarf's personality to ideal, baseline, stepford or wrecked. | GP, CS | KB | |
| build-now | Instantly completes all unsuspended building jobs. | ST, CS | KB | |
| caravan | Lists caravans; extends stay, makes them happy, makes them leave, fixes unloading. | ST, GP (extend, happy, leave); none (`list`); bug workaround (`unload`) | RULE | `list` looks fair, `unload` is a bug-repair question. See section 3 |
| catsplosion | Makes animals (or any race) pregnant at once. | GP, ST | KB | |
| changeitem | Changes an item's material, quality or subtype. | GP | KB | |
| changelayer | Rewrites the material of a whole geology layer across regions. | GP, CS, HI (must probe first) | KB | |
| changevein | Rewrites a mineral vein's material. | GP | KB | |
| cleaners | `clean` removes spatter from map, items, units, plants; `spotclean` one tile. | ST (instant washing); alters world | RULE | `clean map` only (mud and snow left alone), run by the harness, not an agent. See section 3 |
| clear-smoke | Removes all smoke from the map. | ST; alters world | RULE | Harness-run FPS maintenance only. See section 3 |
| clear-webs | Removes all webs and frees webbed units. | GP, ST | KB | |
| colonies | Lists, places or converts vermin colonies and hives. | GP (place, convert); `list` unclear | KB | |
| combat-harden | Sets a unit's combat-hardened value (how little corpses bother them). | GP, CS | KB | |
| createitem | Creates any item of any material at a unit's feet. | GP, CS | KB | |
| cursecheck | Counts or details cursed creatures (vampires with fake identities, ghosts) map-wide. | HI | KB | |
| deramp | Instantly removes ramps designated for removal, and floating ramps left by cave-ins. | ST | KB | |
| dig-now | Instantly completes dig designations, generating boulders and ore. | ST, CS | KB | |
| diplomacy | Lists war or peace with contacted civilizations; sets relations. | GP, CS (set); none (no-argument list, probable) | CAND | No-argument form only, never `all <REL>` or `<CIV_ID> <REL>`. Role: overseer, later quartermaster |
| elevate-mental | Sets a dwarf's mental attributes to maximum (or 0 to 5000). | GP | KB | |
| elevate-physical | Sets a dwarf's physical attributes to maximum (or 0 to 5000). | GP | KB | |
| embark-anyone | Adds any civilization, dead or non-dwarven, to the embark origin list. | GP, CS (embark time) | KB | |
| embark-skills | Sets starting skills to Proficient or Legendary and sets remaining skill points. | GP, CS (embark time) | KB | |
| exterminate | Lists targets on the map; kills units by race, undead or one at a time, many methods. | GP; HI (`list` enumerates the whole map, docs do not say hidden units are excluded) | KB | |
| extinguish | Puts out fires on tiles, units, items, buildings, or the whole map. | GP, ST | KB | |
| fastdwarf | Citizens move and work at maximum speed, optionally teleporting to jobs. | GP, ST, CS | KB | |
| feature | Lists map features by index; marks features discovered or undiscovered (e.g. magma, cavern layers). | HI (`list`), GP (show, hide, magma) | KB | |
| fillneeds | Makes a unit (or all) focused and unstressed. | GP, CS | KB | |
| firestarter | Sets items, tiles or inventories on fire. | GP | KB | |
| flashstep | Teleports the adventurer to the mouse cursor. | GP; moot in fort mode | KB | |
| force | Triggers caravan, migrants, diplomat, megabeast or wildlife events. | GP, CS | KB | |
| full-heal | Fully heals a unit, optionally resurrecting the dead, for one, citizens, civ or all. | GP, CS | KB | |
| geld | Gelds or un-gelds an animal at once. | ST (vanilla gelding is a designated medical job, probably; not confirmed here), GP (un-geld) | KB | |
| ghostly | Toggles an adventurer's ghost status. | GP; moot in fort mode | KB | |
| gui/adv-finder | Real-time tracker for historical figures and artifacts, with coordinates (adventure mode). | HI | KB | |
| gui/aquifer | Interactive editor and highlighter for aquifers. | HI, GP | KB | |
| gui/autodump | Interactive teleport or destroy of items, with undo for destroy. | ST, GP | KB | |
| gui/create-item | Interactive item creator, including unrestricted materials. | GP, CS | KB | |
| gui/embark-anywhere | Bypasses embark-site warnings (inaccessible, ocean, tower sites). | GP, CS | KB | |
| gui/family-affairs | Inspects and edits romantic relationships; produces pregnancies. | GP, CS (edit); inspect part not separable | KB | |
| gui/gm-editor | Browses and edits any game data structure; has a read-only toggle. | HI (reads any struct incl. hidden), GP | KB | |
| gui/gm-unit | Editor for a unit's attributes. | GP, HI | KB | |
| gui/liquids | Paints water, magma, river sources; no undo. | GP | KB | |
| gui/reveal | Reveals the whole map while open; `--aquifers-only` shows aquifer markers only. | HI | KB | |
| gui/sandbox | Spawns units, trees, items with arbitrary skills and allegiance. | GP, CS | KB | |
| gui/teleport | Teleports selected units; can select hidden ambushers. | GP, HI | KB | |
| gui/tiletypes | Paints tile shape, material and flags (including the hidden flag). | GP, HI (can unhide tiles) | KB | |
| hfs-pit | Digs a pit straight to the underworld from the cursor. | GP, ST, CS | KB | |
| justice | Lists convicts serving sentences; pardons a convict. | GP (pardon); none (`list`, probable) | CAND | `justice` / `justice list` only, never `pardon`. Role: overseer, later marshal |
| lair | Marks the map as a monster lair so items do not scatter on abandon or reclaim. | GP, CS | KB | |
| launch | Flying-suplex a foe (adventure mode). | GP; moot in fort mode | KB | |
| lever | Lists and shows levers; queues a pull job (optionally high priority) or pulls instantly. | ST (`--instant`); none (list, show, plain pull) | CAND | `list`, `show`, `pull` without `--instant`. Role: overseer to pull, architect for reads |
| light-aquifers-only | Turns heavy aquifers light (world-wide pre-embark, active map post-embark). | GP, CS | KB | |
| liquids | Places magma, water or obsidian; river sources. | GP | KB | |
| locate-ore | Lists metal ores and designates one tile of a chosen ore for digging; `--all` includes undiscovered veins. | HI (`--all`); none (default, discovered veins only, per the doc) | CAND | Default mode only, never `--all`. Depends on a source check, see section 3. Role: overseer to designate, architect for the list |
| machine-toggle | Two overlays: edit a built pressure plate's ranges, toggle a gear assembly without a lever. The script itself does nothing. | ST (mild), needs a human at the screen | KB | |
| make-legendary | Makes a dwarf legendary in one skill, a class, or all. | GP, CS | KB | |
| make-monarch | Crowns a unit as monarch. | GP, CS | KB | |
| makeown | Converts any sentient unit into a citizen; also repairs Bug 10921 (workers arrive as Merchants). | GP, CS | KB | |
| migrants-now | Triggers a migrant wave at once. | GP, CS | KB | |
| plant | Lists shrub and sapling IDs; creates, ages or removes plants. | GP, ST | KB | |
| points | Sets embark points to any number. | GP, CS (embark time) | KB | |
| pref-adjust | Shows preferences (`show`); replaces one or all dwarves' preferences with ideal, goth or none. | GP (set); none (`list`, `show`) | CAND | `list` and `show` only, never `one`, `all`, `goth*`, `clear*`. Role: overseer. Low priority, see section 3 |
| prospector | `prospect` summarises resources (layers, ores, gems, veins, trees, liquids, features); default scans visible tiles only, `all` and `hell` scan as if revealed. | HI (`all`, `hell`); none (default, per the doc) | CAND | Fort-time `prospect` and `prospect --show ...` with no `all` or `hell`; not the pre-embark estimate. Depends on a source check, see section 3. Role: architect, overseer, consultant |
| putontable | Moves ground items onto a table in one step. | ST, GP | KB | |
| regrass | Regrows surface grass and cavern moss, up to maximum grazing. | GP, ST | KB | |
| rejuvenate | Resets a unit's age (one, adults, or all incl. children). | GP, CS | KB | |
| remove-stress | Removes some or all stress from one or all dwarves. | GP, CS | KB | |
| remove-wear | Sets item wear to zero for all items or given ids. | GP, ST | KB | |
| resize-armor | Resizes armor or clothing for any race. | GP | KB | |
| resurrect-adv | Revives a dead adventurer. | GP; moot in fort mode | KB | |
| reveal-adv-map | Reveals or hides the adventure-mode world map. | HI; moot in fort mode | KB | |
| reveal-hidden-sites | Reveals every undiscovered site in the world. | HI | KB | |
| reveal-hidden-units | Exposes all sneaking or ambushing units. | HI (directly contradicts the isHidden rule in `research/2026-09-16-player-visibility.md`) | KB | |
| reveal | Reveals the whole map (`reveal`, `revtoggle`), reverts it (`unreveal`, `revflood`, `revforget`). | HI, and it flips `designation.hidden`, the flag our knowledge gate reads | KB | |
| set-orientation | Views (`--view`) or sets a unit's romantic orientation. | GP (set); HI probable (`--view`, not confirmed shown in the UI) | KB | |
| set-timeskip-duration | Changes the length of the pre-game "Updating World" timeskip. | GP, CS (embark time) | KB | |
| showmood | Prints the items a unit in a strange mood needs. | none if the vanilla UI already shows the same needs (docs do not say) | RULE | `showmood` (no arguments) only. Role: overseer. See section 3 |
| source | Registers infinite water or magma sources or drains; lists registered ones. | GP | KB | |
| startdwarf | Sets the number of starting dwarves (up to 32767). | GP, CS (embark time) | KB | |
| strangemood | Triggers a strange mood, optionally forced to a type and skill. | GP, CS | KB | |
| superdwarf | Gives units instant actions and no rest; lists them. | GP, ST | KB | |
| tame | Reads (`--read`) or sets a unit's training level; 7 is fully tame, 8 reverts to wild. | GP (set); none (`--read`, probable) | KB | |
| teleport | Teleports any unit, friendly or hostile, anywhere. | GP, ST | KB | |
| tiletypes | Paints tile shape, material and flags onto the map by brush and filter. | GP, HI (can unhide tiles) | KB | |
| tubefill | Refills mined-out adamantine spires with fresh adamantine. | GP, CS | KB | |
| ungeld | Restores an animal's ability to reproduce. | GP | KB | |
| unretire-anyone | Lets you play as any living (or dead) historical figure in adventure mode. | GP, CS; moot in fort mode | KB | |
| weather | Prints a map of local weather; sets weather to clear, rain or snow. | GP (set); shows a grid map (breaks commitment 1 if relayed) | KB | |

Row count check: 99 rows above, verified against the list of armok-tagged docs.

## 3. Candidates and rulings, tool by tool

Method note. A "candidate" here means a subcommand that, on the docs, breaks none
of the commitments and has a plausible role use. It is a judgement from reading
documentation only. Two things apply to every candidate:

1. **What an exception actually buys.** It permits calling the shipped, tagged
   script. Every pure read below could also be rebuilt as our own read tool over
   the same game structures (the trade research already read `caravan list` as a
   plain struct read, `research/2026-09-16-trade-execution-api.md`), and a
   rebuilt read is not an `armok` tool, though it is still bound by the
   knowledge-scope rule. So the user's real question is whether the rule is about
   the tagged script or about the capability. This review assumes the script.
2. **Any wrapper must keep the boundary rules**: no raw coordinates to the model,
   named kinds as arguments (generalisability), and reads pass the knowledge gate.

### 3.1 Candidates

**`lever`** (docs: full read). Really does: lists levers with id, name, state and
links; `show` prints one; `pull` queues an ordinary pull job that a dwarf carries
out ("the same as selecting the lever and triggering a pull job in the UI").
- Breaks: `--instant` skips the job (skips-cost-or-time). The rest breaks nothing.
- Allowed: `lever list`, `lever show [--id N]`, `lever pull [--id N]`. Not
  `--instant`. `--priority` is left out of the scope on purpose: the doc says only
  "queue a job at high priority" and does not say which mechanism, so it is a small
  question for the user (is a job priority bump something a vanilla player can do).
- Role: overseer pulls (the only actor); architect may read the list.
- Question for the user: allow the no-`--instant` forms of `lever`?
- Our own wrapper: none. Grep hits for "lever" in our scripts are about "lever
  gap" (a leverage idea in `handoffs/2026-09-18-lever-gap-tools.md`), not the
  DF lever building. No tool builds or links levers yet, so this only becomes
  useful once one does.

**`diplomacy`** (docs: full read; the trade research read the source, 108 lines).
Really does: with no arguments, prints war or peace with each contacted
civilization; with arguments, sets both sides' stance.
- Breaks: setting relations is grants-power and changes-the-story (`diplomacy all
  war` makes the world declare war). The no-argument read breaks nothing if the
  vanilla civilizations or diplomacy screen shows the same relations. Docs do not
  say whether the UI also shows the both-directions detail the tool prints.
- Allowed: no-argument form only. Role: overseer now, quartermaster when enabled.
- Question: allow the no-argument read?
- Wrapper: none. The trade research notes it is entity-level foreign policy and
  unrelated to the caravan transaction.

**`justice`** (docs: full read). Really does: `justice` / `justice list` lists
convicts serving sentences; `justice pardon` commutes a sentence.
- Breaks: `pardon` is grants-power and changes-the-story (it undoes a justice
  outcome the fort itself decided). The list is what the vanilla justice screen
  shows (my reading, not checked against the game).
- Allowed: `list` only. Role: overseer now, marshal when enabled.
- Question: allow the read? Low stakes; the same list is a plain struct read.

**`prospector`** (`prospect`; docs: full read). Really does: a summary of layers,
ores, gems, veins, shrubs, trees, liquids and features. By default "only the
visible part of the map is scanned"; the `all` keyword scans "as if it were
revealed"; `hell` adds HFS tube z-ranges. A pre-embark form estimates a chosen
embark rectangle, with the doc's own +/-30% caveat.
- Breaks: `all` and `hell` are hidden-information outright. The default depends
  on whether the doc's "visible" means the same as our `designation.hidden` gate
  (very likely, but unverified; see section 6).
- Allowed: fort-time `prospect` and `prospect --show <sections>`, never `all` or
  `hell`. The pre-embark estimate is left out: the doc does not show it stays
  within "existence from the embark screen", and it estimates amounts.
- Roles: architect, overseer, consultant (all read-only).
- Question: allow the visible-only form, conditional on the source check?
- The memory file lists `prospector` as load-bearing and `docs/TRAPS.md` uses
  `prospect all` as a cross-check on whole-map aggregates. That is developer
  diagnostics, which the knowledge-scope handoff exempts from the role allowlists
  ("The rule binds the role allowlists, not developer diagnostics"). Whether the
  armok rule also exempts developer probes is not written down; see section 6.
- Wrapper: none (`df-overseer-overview.lua` notes it does not implement a
  prospect-equivalent resource summary).

**`locate-ore`** (docs: full read). Really does: `locate-ore` lists metal ores;
`locate-ore <type>` finds one tile of that ore, zooms the screen to it and
designates it for digging. "By default, the tool only searches ore veins that your
dwarves have discovered"; `--all` searches undiscovered veins.
- Breaks: `--all` is hidden-information. Default mode is acting on a discovered
  tile, which the 2026-09-16 rule allows; the doc does not say how "discovered" is
  decided (the hidden flag, or a per-vein flag), which is the whole question.
- Allowed: default mode only, never `--all`. Role: overseer designates (it is a
  mutation); architect may read the list.
- Question: allow it, conditional on the script checking `designation.hidden` (or
  equivalent) rather than a coarser flag?
- Caveats: it also moves the game camera, which is harmless headless; it presumably
  prints a tile position, which a wrapper must strip. It takes the ore as an
  argument, so it already meets the generalisability rule.

**`assign-preferences --show`** and **`pref-adjust list|show`** (docs: full read).
Really do: print a unit's likes and dislikes; every other form overwrites them.
- Breaks: the writes are grants-power and changes-the-story (they make a dwarf
  easy to satisfy). The reads show what a vanilla citizen's preferences screen
  shows (my belief about the fort-mode UI, not confirmed here).
- Allowed: `assign-preferences --show` and `pref-adjust list`/`show`, nothing
  else. Role: overseer. **Low priority**: both act on the "selected unit" (a UI
  selection, awkward headless), and the same read is a plain field read; they
  are listed only because they break nothing. Doc quirk: `assign-preferences`'s
  usage line says `assign-goals`, a copy-paste error in the shipped doc.

### 3.2 Needs a ruling

**`caravan`** (docs full read; internals from the trade research's source read on
the VM, relayed and not re-checked). Subcommands:
- `caravan list`: a pure struct read (id, race, trade state, days remaining, and
  casualty, hardship, seized and offended flags). Fair if the game shows the same.
  **Doubt:** the exact days-remaining countdown may be something the vanilla UI
  does not show; the docs do not say.
- `caravan extend [days] [ids]`: adds dwell time and pulls a leaving caravan back.
  A vanilla player faces that countdown and loses the caravan. Grants-power, and
  it is precisely the live case (the fort's caravan had no depot to reach). Useful
  and stays banned.
- `caravan happy`: zeroes the consequence flags (seized goods, offence). Grants
  power. `caravan leave`: forces departure, no player equivalent. Both banned.
- `caravan unload`: repairs a known bug where pack animals' drag relationships
  desync so the caravan will not unload (per the trade research's source read).
  The vanilla player's only remedy is waiting or losing the goods.
- Question for the user, one sentence: may agents apply a DFHack repair for a
  game bug that no vanilla action can fix (`caravan unload`; the class also
  includes `deramp`'s floating ramps and `makeown`'s Bug 10921, though those tools
  do far more than repair)? Separately, may `list` be used with days-remaining
  withheld?
- Suggested scope if yes: `list` (days-remaining dropped) and `unload`; never
  `extend`, `happy`, `leave`. Role: overseer, later quartermaster.

**`showmood`** (docs: read; three lines). Really does: prints the items a unit in
an active strange mood needs. Broken commitments: none if the vanilla UI already
tells the player what a moody dwarf is asking for; hidden-information if it does
not. The docs do not say, and I do not know this build's UI.
- Question for the user, who plays the game: does vanilla v50 show a moody
  dwarf's requested materials to the player? If yes, allow `showmood`
  (no arguments). It does not create the items, so it grants nothing.
- Role: overseer. A strange mood left unmet can ruin a dwarf, so the survival
  value is real, but that is not a reason on its own.

**`cleaners`** (`clean`, `spotclean`; docs full read) and **`clear-smoke`**.
Really do: `clean` removes spatter from the map, items, units and plants;
`clear-smoke` removes all smoke. The docs pitch both as FPS relief in an old
fortress ("can significantly reduce FPS lag").
- Breaks: skips-cost-or-time in a small, cosmetic way; alters the world beyond
  normal play. No new power, no hidden information, no change to what an agent
  decided. `clean units` also decontaminates units and hostiles, and `clean items`
  strips poison from weapons: those two are real effects and stay banned.
- The project already wrote these down as load-bearing toolkit
  (`memory/dfhack-environment.md`: "clean/cleaners"; `docs/PURPOSE.md`: a toolkit
  "against the item, corpse and population accumulation that normally kills long
  runs"), which the new blanket rule now contradicts.
- Question for the user, one sentence: does FPS-only cosmetic maintenance run by
  the harness on a schedule, not by any agent, fall outside the "no armok" rule?
- Suggested scope if yes: `clean map` (default, mud and snow left alone) and
  `clear-smoke`, run by the harness. No agent role calls them. Not `autodump`,
  `extinguish` or `deramp`: those move, destroy or erase real game objects.

## 4. Useful and should stay banned

Useful is not a reason. These do exactly the thing a mortal fort is meant to
suffer, and `docs/PURPOSE.md` says mortality "is the format rather than a failure
of it" (sieges, tantrum spirals, forgotten beasts).

- **`dig-now`, `build-now`, `deramp`, `autodump`**: instant labor. A stuck
  construction or a dig backlog is a real recurring problem, and these remove it
  by skipping the labor a player would spend.
- **`teleport`, `gui/teleport`, `fastdwarf`, `superdwarf`**: rescue a stranded
  dwarf, or finish jobs at once. Grants power and changes what the run means.
- **`full-heal`, `resurrect-adv`, `remove-stress`, `fillneeds`, `brainwash`,
  `armoks-blessing`, `elevate-*`, `rejuvenate`, `combat-harden`**: prevent or undo
  the deaths and tantrum spirals the format expects.
- **`createitem`, `gui/create-item`, `changeitem`, `gui/sandbox`,
  `remove-wear`, `resize-armor`, `points`, `embark-skills`, `startdwarf`**: make
  materials, gear or dwarves from nothing. The well shows the intended route: it
  was built from blocks and a mechanism the fort made itself through
  `df-overseer-workjob` (`CLAUDE.md` status banner), which is the run's story.
- **`migrants-now`, `force`, `catsplosion`**: manufacture population and events.
- **`caravan extend|happy|leave`**: see 3.2.
- **`aquifer`, `light-aquifers-only`, `liquids`, `gui/liquids`, `source`,
  `tiletypes`, `gui/tiletypes`, `changelayer`, `changevein`, `tubefill`,
  `hfs-pit`, `regrass`, `plant`**: reshape the world.
- **`reveal`, `gui/reveal`, `reveal-hidden-units`, `reveal-hidden-sites`,
  `feature`, `cursecheck`, `exterminate`, `gui/gm-editor`, `gui/gm-unit`**: show
  what a player cannot see. **A separate hazard:** `reveal`, `tiletypes` and
  `gui/tiletypes` (hidden flag) and `feature` do not only leak, they change
  `designation.hidden` or discovery flags, the very state our knowledge gate
  reads (`research/2026-09-16-player-visibility.md`), so one use would silently
  make every later tool's "hidden" answer wrong.
- **`gui/embark-anywhere`**: lets an embark proceed on sites the game refuses
  outright. `research/2026-09-08-embark-automation.md` read its source as a
  pattern for driving the embark screen (setting a warn flag to reach the "accept
  anyway" panel). Reading a banned tool's source is not using it, and ordinary
  sites need no bypass; the tool itself stays banned.
- **`lair`**: keeps items from scattering when a site is reclaimed. The project
  plans to reclaim after a fort dies, and scatter is a vanilla consequence, so
  this would soften the format. Banned, but it is the softest ban in the list and
  the user may want to look at it (not a ruling I would push).
- **Adventure-mode tools** (`bodyswap`, `flashstep`, `ghostly`, `launch`,
  `resurrect-adv`, `reveal-adv-map`, `unretire-anyone`, `gui/adv-finder`): no
  role plays adventure mode; moot as well as banned.
- **`gui/*` tools in general**: interactive, mouse-driven; an agent could not
  drive them headless anyway, apart from being banned on their own merits.

## 5. Harmless read subcommands inside banned tools (no exception recommended)

These break nothing but have no role use and sit next to writes, so granting an
exception would only widen the surface. Listed to show the mixed tools were
judged subcommand by subcommand.

`tame --read` (training level, probably shown in the animal's screen),
`changeitem info` and `createitem inspect` (an item's material tokens),
`plant list` and `regrass -l` (raw-ID lists), `source list` (only sources this
tool registered), `superdwarf list`, `make-legendary list|classes`,
`armoks-blessing list|classes` (static lists).

Read-looking but **not** clean: `adaptation` (the number may not be shown in the
UI), `set-orientation --view` (same doubt), `colonies` list (docs do not say
hidden colonies are excluded), `exterminate` list and `feature list` (map-wide,
likely hidden-information), `aquifer` list and `gui/reveal --aquifers-only`
(aquifers under undug rock, hidden-information), `weather` (prints a rendered map
of the weather, a commitment-1 problem if relayed as text).

## 6. What I could not tell, and what would settle it

Everything is documentation-only. Nothing was run and no DFHack source was read
for this review (the install is on the VM; the docs are copies of the shipped
`.txt` files).

1. **`prospect` default really skips hidden tiles.** Docs say "only the visible
   part of the map is scanned". Settle by reading the plugin source at the
   installed tag (53.16-r1.1) and by a read-only comparison of `prospect` and
   `prospect all` on the paused fort (counts should differ if it skips hidden
   tiles). Also check that the `features` and `liquids` sections do not name
   undiscovered things.
2. **`locate-ore` "discovered".** Read `locate-ore.lua` to see whether it tests
   `designation.hidden` or a vein-level flag.
3. **`caravan list` fields versus the vanilla UI.** Unknown whether days remaining
   is shown to a player. Settle with the user, or look at the depot and trade
   screens on the fort.
4. **`showmood`, `diplomacy`, `justice list`, preferences, orientation,
   adaptation, training level, gelding.** Each turns on what the vanilla v50 UI
   shows or allows (for gelding, whether a vanilla geld order exists, in which
   case `geld` is only an instant version of it). The user plays the game and
   can likely answer most in a sentence; I could not from docs.
5. **`lever --priority`.** The mechanism is not described.
6. **Does the armok rule cover developer and orchestrator diagnostics?** The
   memory file lists `prospector` as load-bearing and `docs/TRAPS.md` uses
   `prospect all`; the knowledge-scope handoff exempts developer diagnostics from
   role allowlists. The armok decision says "agents do not use", which reads the
   same, but it is not written.
7. **Doc drift in this repo.** `memory/dfhack-environment.md` ("Available and
   load-bearing") names six armok-tagged tools: `prospector`, `clean`/`cleaners`,
   `unretire-anyone`, `bodyswap`, `lair`, `gui/embark-anywhere`. That is now
   inconsistent with the 2026-09-21 rule. A memory audit is the suggested fix; I
   did not touch that file.
8. **Doc versus code.** I found no case where a shipped doc and its code
   disagree, because I read no code here. The only doc defect seen is the
   copy-paste usage line in `assign-preferences`. Statements about `caravan`'s and
   `diplomacy`'s internals come from `research/2026-09-16-trade-execution-api.md`
   (source read on the VM), relayed, not re-verified.
9. **Where the confidence sits.** The 88 keep-banned verdicts are mostly not close
   calls: they write, spawn, heal, teleport, reveal or complete work at once. The
   soft part is the handful of reads (section 3), which rest on "same as the
   vanilla UI", a claim I could not check, and each of which could be replaced
   by our own read tool.
