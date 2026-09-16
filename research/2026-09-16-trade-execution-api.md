# Can an agent complete a trade without a human on the trade screen? A follow-up to §3 of the food-and-drink research

Date: 2026-09-16. Follow-up to `research/2026-09-16-food-and-drink-logistics.md`
§3, which concluded "no struct-level API found, only the trade viewscreen" and
left it as an open question. This report re-opens that question, reads the
actual DFHack scripts and struct layout shipped on VM 103 (not just the doc
index), and queries the live, paused fort directly and read-only. No write,
no unpause beyond what was already true when this session began, no
interaction with the frozen popup, no touch of any viewscreen.

## Bottom line

**No struct-level function exists anywhere in this DFHack build that completes
a trade transaction — that part of the prior research's conclusion holds and
is now confirmed by reading the actual source, not just the doc index.** But
the picture underneath is much richer than "only the viewscreen": DFHack
exposes real, present, callable primitives for *staging* goods
(`dfhack.items.markForTrade`), for *selecting* which goods are on offer (a
live, writable struct field, `df.global.game.main_interface.trade.goodflag[i][j].selected`),
and for manipulating the caravan itself (extend its stay, calm it down,
force it to leave) entirely without any viewscreen. The one step nothing in
this build exposes as code is the final "confirm trade" action, which is
compiled into the closed-source DF engine and reachable only by feeding an
input event to the active screen — mechanically identical to the
`gui.simulateInput`/`screen:feed()` path this repo has deliberately fenced off
for steady-state play. **So the honest answer is "yes, but only by walking up
to the line this repo already drew around UI automation, and the last
centimeter of that line is unavoidable"** — not "no, it's impossible," and not
"yes, cleanly."

## 0. Correction to the prior research: the screen it named does not exist here

`research/2026-09-16-food-and-drink-logistics.md` §3 named
`viewscreen_tradegoodsst` as "the ordinary player interaction" screen for
trade. **Checked live against this install and found not to exist**:

```
$ dfhack-run lua "print(df.viewscreen_tradegoodsst)"
nil
```

(High confidence — direct negative-existence check against the running
process, not a doc read.) This is not a mistake specific to that report; it
is stale pre-v50 community knowledge, exactly the trap
`memory/dfhack-environment.md` already warns about generally ("the v50
transition invalidated a lot of older community knowledge"). DF's v50 rewrite
folded fort-mode trade into the unified `main_interface` system rather than a
dedicated pushed viewscreen. The correct live object is
`df.global.game.main_interface.trade`, confirmed to exist and be readable
(§2 below). Nothing else in the prior report's §3 conclusion is contradicted
by this finding — if anything it strengthens it: the *type it named* is gone,
but the *fact* (no completion API) is still true of the real, current
location.

## 1. The full DFHack tool surface around caravans and trade

All five checked directly against **VM 103's actual installed files** over a
read-only SSH session (`/opt/df/game/hack/...`), not the local Windows
install or the doc index alone. Availability confirmed by the same method
`memory/dfhack-environment.md` itself establishes: grep for
`Tags:.*unavailable` in the shipped doc.

```
$ grep -l 'Tags:.*unavailable' hack/docs/docs/tools/{caravan,diplomacy,force,logistics,forceequip,workflow,stocks,zone}.txt
workflow.txt
stocks.txt
zone.txt
```

**`caravan`, `diplomacy`, `force`, `logistics`, `forceequip` are all confirmed
present and NOT tagged unavailable on VM 103** (verified live, high
confidence — this is a direct check on the exact install this fort runs on,
not the Windows workstation copy). `workflow`, `stocks`, `zone` are confirmed
unavailable here too, consistent with `memory/dfhack-environment.md`'s
existing list. **None of `caravan`/`diplomacy`/`force`/`logistics` were named
in that file's available list before this report** — worth folding back in
by whoever next edits `memory/` (this report does not edit it, per this
task's constraint).

Backed by compiled plugin files (not just script presence): only
`forceequip.plug.so` and `logistics.plug.so` exist under `hack/plugins/`.
`caravan`, `force`, `diplomacy` are **pure Lua scripts**
(`hack/scripts/caravan.lua`, `force.lua`, `diplomacy.lua`, plus
`hack/scripts/internal/caravan/{common,movegoods,pedestal,predicates,trade,tradeagreement}.lua`),
confirmed by direct file listing. This matters only insofar as it means their
logic is fully readable Lua, not opaque compiled code — which is exactly why
this report can be this specific.

### `caravan` (172 lines, read in full)

| subcommand | what it actually does | mechanism | headless? |
|---|---|---|---|
| `caravan list` | Prints each caravan's id, race/entity, `trade_state`, days remaining, and any of `casualty`/`hardship`/`seized`/`offended` flags set | Iterates `df.global.plotinfo.caravans`, reads `car.trade_state`, `car.time_remaining`, `car.flags` directly | Yes — pure read |
| `caravan extend [days] [ids]` | `car.time_remaining = car.time_remaining + (days*120); bring_back(car)` — adds dwell time and, if the caravan isn't already `AtDepot`, sets it back to `Approaching` | Direct struct write to `caravan_state.time_remaining` and `.trade_state` | **Yes — a real, confirmed, headless write.** No cap found in the source on how many times or how far this can extend. |
| `caravan happy [ids]` | `car.flags.whole = 0; bring_back(car)` — zeroes every flag (casualty/hardship/seized/offended/tribute/etc.) and un-sticks the caravan | Direct write to the caravan's bitfield | Yes |
| `caravan leave [ids]` | Sets `car.trade_state = Leaving` for the targeted caravans; if no caravan still needs a broker, clears `depot.trade_flags.trader_requested` and removes any `TradeAtDepot` job on every trade depot | Direct struct writes plus `dfhack.job.removeJob` | Yes |
| `caravan unload` | Reconnects pack animals whose drag relationship desynced (a known bug workaround), by writing `unit.relationship_ids[Dragger/Draggee]` directly | Direct struct write | Yes |
| overlays (`movegoods`, `movegoods_hider`, `assigntrade`, `trade`, `tradebanner`, `tradeethics`, `tradeagreement`, `displayitemselector`) | Enhanced **selection UI** layered on the vanilla screens — searchable/sortable item lists, bin-expand shortcuts, ethics filtering, a "select all" gesture | `OVERLAY_WIDGETS` registered against specific `viewscreens` (e.g. `dwarfmode/Diplomacy/Requests` for `tradeagreement`) | **No — these exist to make the human's clicking faster, not to replace clicking.** Confirmed by reading `trade.lua`/`movegoods.lua` directly: every one of them is a `widgets.Window`/`overlay.OverlayWidget` subclass whose whole job is rendering and `onInput` handling for a person. |

(All of the above: **verified by direct source read on VM 103**, high
confidence, not inferred from the doc.)

One directly useful, previously-unrecorded fact for this project's actual
situation (Uniboslan has a caravan and no depot yet, per
`decisions/DECISIONS.md` 2026-09-16): **`caravan extend` is a real, available,
headless way to keep the current caravan from giving up and leaving while a
depot gets built**, with no confirmed ceiling on how far. This is new,
concrete, and actionable — see §6.

### `diplomacy` (108 lines, read in full)

War/peace between whole civilizations (`diplomacy all war`, `diplomacy
<civ_id> peace`), reading/writing `historical_entity` relationship state.
**Confirmed present, headless, but has nothing to do with the caravan trade
transaction or the liaison meeting** — it is entity-level foreign policy, a
different concept from the `main_interface.diplomacy` liaison-meeting screen
below despite the name collision. Flagged so a future reader does not
conflate the two.

### `force` (58 lines, read in full)

`force Caravan [civ_id]`, `force Diplomat [civ_id]`, `force Migrants`, `force
Megabeast`, `force Wildlife [all]`. Triggers the underlying vanilla
event-spawn logic directly; the doc's own caveat, read verbatim: "you can only
trigger one caravan per civ at the same time, and DF may choose to ignore
events that are triggered too frequently." **Confirmed present, headless.**
Relevant here only as the tool that could deliberately summon a caravan for a
future live test of anything in this report, not as part of the trade
transaction itself.

### `logistics` (confirmed available; doc read in full, not the Lua source this pass)

Already covered by the prior research and re-confirmed here: `logistics add
melt trade -s <stockpile>` marks a **named, already-linked stockpile's**
contents for trading whenever a caravan is approaching or at the depot. Its
own doc is explicit that it "does not execute trades itself." **New in this
pass**: this is not the only, or even the most direct, item-marking
primitive — see `dfhack.items.markForTrade` in §2, which works on a single
item with no stockpile-link prerequisite at all.

## 2. The struct and Lua API level

This is where this report goes materially further than the prior pass, which
found only `dfhack.items.isRequestedTradeGood` and generic viewscreen access.
Both static source reads (grep against the shipped `Lua API.txt` and the
caravan scripts) and **live queries against the actual paused fort** are used
below; each claim says which.

### `dfhack.items.*` trade predicates and actions — confirmed present, doc read directly (`hack/docs/docs/dev/Lua API.txt`)

- **`dfhack.items.markForTrade(item, depot)`** — *"Marks the given item for
  trade at the given depot."* **This was not found by the prior pass and is
  the single most load-bearing new fact in this report.** It is a real,
  present, documented function, and it is exactly the mechanism
  `internal/caravan/movegoods.lua:763` uses to implement the vanilla "move
  goods to depot" action (`dfhack.items.markForTrade(item, depot)`, read
  directly at that line). It operates on **any single item**, with no
  stockpile-link prerequisite — a strictly more direct staging primitive than
  `logistics add trade`.
- **`dfhack.items.canTrade(item)`**, **`canTradeWithContents(item)`**,
  **`canTradeAnyWithContents(item)`** — tradeability predicates (whether an
  item, or a container's contents, is eligible at all).
- **`dfhack.items.isRequestedTradeGood(item[, caravan_state])`** — already
  found by the prior pass; re-confirmed, a valuation helper only.
- **`dfhack.items.getValue(item[, caravan_state])`** — computes an item's
  value, adjusted by civ properties and trade agreements if a
  `caravan_state` is passed.

**None of these four "action" functions commits a transaction.**
`markForTrade` only brings an item to the depot (the equivalent of the
vanilla "move goods" screen); it does not sell it, and doing this for a
merchant's item does not buy it either. Confirmed by reading its one call
site, which is inside the *move-to-depot* flow, not anywhere near a
"complete" action.

### `df.global.plotinfo.caravans` / `caravan_state` — confirmed present and read live

```
$ dfhack-run lua "local c=df.global.plotinfo.caravans; print(#c)
   for i,car in ipairs(c) do print(i, car.trade_state, car.time_remaining) end"
1
0  1  3133
```

Live, right now, on Uniboslan: **one caravan, `trade_state=1` ("Approaching"),
`time_remaining=3133`.** `caravan.lua`'s own conversion (`math.floor(car.time_remaining
/ 120)`, confirmed by reading the source) makes that **≈26 days of game time
remaining** before this caravan gives up. `T_trade_state` is a five-value
enum, read live in full: `0=None, 1=Approaching, 2=AtDepot, 3=Leaving,
4=Stuck`. The caravan is stuck at `Approaching` and can never reach `AtDepot`
because Uniboslan has no trade depot (`#df.global.world.buildings.other.TRADE_DEPOT
== 0`, confirmed live) — consistent with the wiki's "merchants cannot path to
a depot that doesn't exist, so they leave without trading."

**This directly settles the previously-open dwell-time question** (flagged
"genuinely unknown" in the prior report's §3 and its Not-verified list): the
mechanism is a plain readable/writable countdown field,
`caravan_state.time_remaining`, in units of 1/120 day, extendable without
limit via `caravan extend`. The **≈26 days** figure is this specific
caravan's live value on this fort today, not a universal constant — no
default or per-caravan-type value was found documented anywhere in the
shipped Lua, since caravans are spawned by the closed-source engine itself,
not by any DFHack script. Confidence: **high on the mechanism and the field
semantics** (direct source read of the conversion plus a live value);
**moderate on generalizing "~26 days" to every caravan** (one live sample).

The caravan's flags bitfield, read live in full: `check_cleanup, casualty,
hardship, communicate, seized, offended, UNUSED_07, greatly_offended,
tribute`, plus 23 unnamed bits. **`tribute` and `communicate` are new facts
this pass adds** — neither was named by the prior research, and both are
directly relevant to §4 below.

### `df.global.game.main_interface.trade` — confirmed present and read live, the actual v50 location

```
$ dfhack-run lua "local t=df.global.game.main_interface.trade
   for k,v in pairs(t) do print(k) end"
open  choosing_merchant  merlist  scroll_position_merlist  scrolling_merlist
title  talker  fortname  place  st  bld  mer  civ  stillunloading  havetalker
merchant_trader  fortress_trader  good  goodflag  good_amount  i_height
master_type_a_type  master_type_a_subtype  master_type_a_expanded
current_type_a_type  current_type_a_subtype  current_type_a_expanded
current_type_a_on  current_type_a_flag  scroll_position_item  scrolling_item
item_filter  entering_item_filter  talkline  buildlists  handle_appraisal
counter_offer  counter_offer_item  scroll_position_counter_offer
scrolling_counter_offer  entering_amount  amount_str  big_announce
scroll_position_big_announce  scrolling_big_announce
```

This is a **live, direct, full field enumeration off the running fort**, high
confidence — not a doc guess. Right now, with no depot and no active trade
session, `open=false`, `bld/merchant_trader/fortress_trader/talker` are all
`nil` (nothing populated because no trade session exists to populate them
into), and `#t.good == 2` (a two-list structure, almost certainly [fort's
tradeable goods, merchant's goods], not independently confirmed which index
is which).

The field that matters most: **`goodflag[list_idx][item_idx].selected`**,
confirmed by reading `internal/caravan/trade.lua:35` directly
(`trade.goodflag[data.list_idx][data.item_idx].selected`) — this is the exact
boolean DFHack's own enhanced trade window reads to decide whether to draw a
checkmark, and it is a **plain struct field**, writable the same way this
repo already writes `unit.status.labors[code]` or `car.flags.whole`
(`memory/dfhack-environment.md`'s own documented pattern). **Setting
`trade.goodflag[i][j].selected = true/false` directly, with no viewscreen
interaction at all, is therefore a real, mechanically available way to choose
which items are on the table for a trade**, once a trade session is actually
open (`trade.open == true`, which requires a depot, a caravan at it, and an
assigned trader/broker).

`counter_offer`/`counter_offer_item`/`entering_amount`/`amount_str` are the
negotiation/haggling fields; `big_announce` (plus its own scroll state) is
the post-action result banner (e.g. the "the merchants seem pleased"-class
message) — its presence implies completing a trade produces a further
on-screen announcement, adding a step to any full automation of the flow,
not just a single keypress.

**What is not present anywhere in this struct, or anywhere in the Lua API
doc: a function or field that commits the exchange.** A comment at
`internal/caravan/trade.lua:512`, read directly — *`"trade" or "offer"
buttons may have been clicked and we need to reset the cache`* — confirms
these are genuine vanilla, engine-rendered, clickable buttons that DFHack's
own code only reacts to after the fact. DFHack never drives them itself
anywhere in this codebase (checked: no `dfhack.items.markForTrade`-style
"execute" counterpart exists, and no script sets `trade.open = false` as a
completion action — the closest write found, `caravan.lua`'s `leave`
command, forcibly ends a caravan's visit, not a specific trade).

### `df.global.game.main_interface.diplomacy` — the liaison meeting, a separate struct

Read live in full (`open`, `actor`, `target`, `actor_unid/target_unid`, a
`diplomacy_interface_flag` bitfield, `taking_requests`, `dipev`, etc.). **No
DFHack script anywhere touches this struct at all** (checked: zero grep hits
across `hack/scripts/`), confirming the liaison meeting has received zero
DFHack automation attention, unlike trade. `viewscreen_topicmeetingst` and
`viewscreen_topicmeeting_takerequestsst` — the pre-v50 names a search would
turn up — **both checked live and confirmed absent** (`nil`), same v50-fold
pattern as the trade screen. **Trade agreements are administered here, not
in the trade UI**: `internal/caravan/tradeagreement.lua`'s own overlay is
scoped to `viewscreens='dwarfmode/Diplomacy/Requests'` (read directly,
line 13), meaning "what goods the liaison wants next year" is negotiated
during the liaison meeting, structurally separate from the caravan
trade-goods exchange covered above. This corrects an implicit conflation risk
in the original brief's list ("trade agreements" and "the liaison meeting"
are the same screen, not two separate things).

### The depot building itself — type confirmed, no live instance to inspect

```
$ dfhack-run lua "print(#df.global.world.buildings.other.TRADE_DEPOT); print(df.building_tradedepotst)"
0
<type: building_tradedepotst>
```

`building_tradedepotst` exists as a type (confirmed live), but Uniboslan has
zero depots built, so no live instance's fields could be enumerated this
session. The one confirmed field, from reading `caravan.lua`'s `leave`
command directly, is **`depot.trade_flags.trader_requested`** (a boolean,
written directly, no viewscreen). Whether the depot struct exposes anything
else relevant (e.g., a direct pointer to the currently-assigned broker) is
**not verified** — this needs either a live depot to inspect or a
df-structures XML this session did not have access to (VM 103 ships only the
compiled DFHack build, no XML; see Not-verified below).

## 3. The programmatic-viewscreen question — the one that actually matters

**Mechanically, yes: `gui.simulateInput`/`screen:feed()` can drive the
active `main_interface`-hosted screen with no X11/xdotool input at all.**
This is DFHack's own standard mechanism (`hack/lua/gui.lua:58`,
`simulateInput`, read directly: it translates a string key name via
`df.interface_key[name]` and queues it as if a person had pressed it). What
this report can say specifically about what completing a trade this way
would actually require:

1. **A depot, a caravan at it (`trade_state == AtDepot`), and an assigned
   broker/trader** — all vanilla prerequisites, none skippable at the struct
   level (no field flips a caravan straight to a completed trade without a
   depot existing and being reachable).
2. **Opening the trade session** — `trade.open` becomes `true` when the
   vanilla "Trade" option is chosen at the depot; whether this itself can be
   set directly by a script or only arises from an engine-internal reaction
   to a `HOTKEY_BUILDING_TRADEDEPOT`-class input was **not confirmed** this
   session (would need a live depot and an active caravan to test safely,
   which this fort does not currently have).
3. **Selecting items** — confirmed mechanically real and struct-level:
   `dfhack.items.markForTrade(item, depot)` to stage fort goods at the
   depot, then `trade.goodflag[i][j].selected = true` for whichever items
   (fort's and merchant's) are meant to change hands. **This half requires no
   reading of rendered screen content at all** — it is driven entirely by
   iterating `df.global.world.items` and the caravan's own item list
   (`trade.good`), which are ordinary data structures, not pixels or text.
4. **Committing the trade** — **this is the one step this research could
   not find any struct-level equivalent for, anywhere in this build.** The
   action is dispatched by the closed-source DF engine in response to some
   input event on the vanilla "Trade"/"Offer" buttons (confirmed real,
   clickable, engine-rendered widgets by the `trade.lua:512` comment cited
   above). **No dedicated named keybinding was found for this**: the only
   `*BARTER_TRADE*`-named bind in `data/init/interface.txt` is
   `A_BARTER_TRADE`, and the `A_` prefix is confirmed (by its neighboring
   binds — `A_THROW`, `A_SHOOT`, `A_TRAVEL`, etc., all clearly adventure-mode)
   to be **adventure-mode NPC bartering, unrelated to fortress-mode depot
   trade.** Live-checked and confirmed absent from `df.interface_key`
   (`nil`). Generic contextual "custom" keys do exist as real enum values
   (`df.interface_key.CUSTOM_T = 141`, confirmed live) and DF's v50 UI is
   known to bind many on-screen buttons to these rather than to named
   binds — but **which exact key or mouse coordinate the vanilla "Trade"
   button in `main_interface.trade` responds to was not determined by static
   reading**, and this report did not test it live (that would require an
   actual depot, an actual caravan at it, and actually triggering the
   screen — none of which this task's constraints permit). **This is a real,
   named gap, not a paper-over**: the general mechanism (feed a completing
   input to the active screen after struct-level selection) is confirmed
   real and available; the *exact* input is unconfirmed.

**The policy question, stated without deciding it.** This repo's own rule
(`docs/AGENT-ARCHITECTURE.md` §7, "What is sliceable and what is not") names
the UI-automation path — `df-overseer-ui.lua` and `xdotool` — as "never
sliceable," restricted to one-time embark bootstrap, precisely because it
"depends on one keyboard, one mouse, one focused screen, one cursor." A
`gui.simulateInput`/`screen:feed()` call issued from a DFHack Lua script run
via `dfhack-run` is **not that mechanism** — it needs no X11, no xdotool, no
window focus, and would not corrupt concurrent input the way real
keyboard/mouse driving would (`dfhack-run` calls are already confirmed
serialized-safe against each other, per `research/2026-09-12-dfhack-capability-checks.md`
§3). But it **is** feeding a synthetic input event into an active viewscreen
to trigger vanilla UI logic, which is the same *category* of action `docs/PURPOSE.md`
design commitment #1 ("the model is never shown a map... every spatial fact
is computed in code and asserted in text") and commitment #6 ("the human view
and the model view are different artifacts") were written to keep at arm's
length, even though the specific harm those commitments target — a rendered
map defeating a transformer's spatial reasoning — is not present here at all.
**The genuinely load-bearing distinction, which this report surfaces rather
than resolves:**

- If the completing action is **a fixed key sequence chosen entirely by
  code** once struct-level reads have confirmed the trade is set up
  correctly (depot exists, caravan `AtDepot`, `goodflag` selections made,
  `open == true`) — the model never has to look at the screen, and the
  "input" is closer to `caravan.lua`'s own struct writes than to
  `df-overseer-ui.lua`'s embark-time clicking, which does depend on reading
  buffer content to know what's on screen.
- If completing the trade instead requires **reading the screen's own
  rendered item lists or button positions** to decide what to do — because,
  say, the exact set of selectable rows depends on scroll position or a
  dynamic layout that can't be derived purely from `trade.good`/`goodflag`
  — that is materially closer to the barred thing, and this report found no
  evidence either way on which case applies, since it never opened a live
  trade session to check.

This repo's rule-makers, not this report, should decide which side of that
line a `depot.execute-trade`-class tool would fall on. What this report adds
beyond the prior pass is that the fixed-key-sequence version is at least
*plausible* given how much of the selection state (`goodflag`, `markForTrade`)
is genuinely struct-level and code-derivable — the prior pass's framing
("the same UI-automation mechanism this repo already built for embark") may
have overstated how much of the flow needs screen-reading, since most of it
does not.

## 4. The alternatives to trading

- **Offer/tribute.** The caravan's own `tribute` flag (confirmed live, §2)
  demonstrates the engine tracks a tribute state per caravan, but **no
  DFHack script anywhere sets, reads meaningfully, or exposes a way to
  trigger it** (checked: zero references to `.tribute` outside the bare flag
  name listing in `caravan.lua`'s `INTERESTING_FLAGS` table, which only
  reports `casualty`/`hardship`/`seized`/`offended` for `caravan list`
  — `tribute` is not even in that reported set, despite existing as a flag).
  Whatever triggers it (almost certainly the vanilla "give without
  requesting anything back" option at the depot) is unexamined by this
  research beyond confirming the flag's existence. **Not verified**: how to
  set it, or what it does mechanically beyond being a flag.
- **The liaison meeting.** A real, separate struct
  (`main_interface.diplomacy`), confirmed populated by a real outpost
  liaison currently present on Uniboslan (`unit id=64`, `flags1.diplomat ==
  true`, name "Shorast Idvâsh 'Rockheats'", confirmed live). **Whether it
  must be handled at all, or whether ignoring the liaison has any
  consequence beyond a missed trade-agreement negotiation, was not settled**
  — no DFHack script touches this screen, and this research did not find a
  wiki-sourced or source-level statement of what happens if a liaison's
  meeting request is never answered. Flagged as unresolved rather than
  guessed at.
- **Seizing merchant goods.** Confirmed as a real vanilla mechanic with real
  diplomatic cost, from two angles: `caravan.txt`'s own doc, read directly
  ("Make the active caravans willing to trade again **after seizing goods,
  annoying merchants**, etc."), and the caravan's own flags
  (`seized`/`offended`/`greatly_offended`, confirmed live, §2) which persist
  until explicitly cleared by `caravan happy`. This is direct evidence that
  seizing has a lasting negative effect on that caravan's (and implicitly
  that civilization's) disposition, not a one-time freebie — consistent
  with, but more specific than, general DF-wiki framing of seizure as
  diplomatically costly. **Not independently verified**: the exact
  entity-relationship mechanism (e.g., whether repeated seizure eventually
  triggers war, an entity-level `diplomacy` state change, or reduced future
  caravan frequency) — this report did not trace that far.
- **Ignoring the caravan entirely.** Settled with a live number, per §2:
  the caravan's `time_remaining` counts down (currently **≈26 days** on
  Uniboslan) and, per the `T_trade_state` enum, transitions through
  `Approaching → AtDepot → Leaving` (or `Stuck`, for the pack-animal bug
  `caravan unload` fixes) with **no flag observed being set purely for
  giving up and leaving** — `seized`/`offended`/`casualty`/`hardship` are all
  about active mistreatment, not passive neglect. So the honest read is:
  **ignoring a caravan costs the missed trade opportunity and nothing else
  that this research could find** — no flag, no relationship penalty. This
  is a real, live, direct answer to the prior report's open question, not an
  inference from the wiki (which gave only arrival cadence, not dwell time).

## 5. What this implies for the tool list

**Trade completion is not reachable by any confirmed struct-level API, full
stop — the same conclusion the prior report reached, now on firmer
ground.** Whether it is reachable via a fixed `simulateInput` key sequence
is a real, live possibility this report could not fully close (the exact key
is unconfirmed) and, even if closed, runs into the policy question in §3 this
report deliberately does not resolve.

Given that, **`depot.build` and `depot.stage-goods` are still worth
building, and arguably more worth it than the prior report's framing
suggested**, for reasons independent of whether trade-completion is ever
built:

1. **`depot.build`** is unconditionally necessary infrastructure — without a
   depot, the caravan cannot even reach `AtDepot`, confirmed live on this
   exact fort right now (`trade_state == Approaching`, stuck there). It has
   value even under a "human completes the trade" model.
2. **`depot.stage-goods`** should be re-scoped, given this report's find:
   wrap `dfhack.items.markForTrade(item, depot)` directly (per-item, no
   stockpile-link prerequisite) as the primary mechanism, with `logistics
   add trade -s <stockpile>` as a secondary/standing-policy option for goods
   that are already stockpiled. This is a strictly more useful tool than the
   prior report's version, which only knew about `logistics`.
3. **A new, cheap, high-value tool this report did not see proposed before:
   `caravan.extend`**, wrapping the confirmed-available, confirmed-headless
   `caravan extend <days>` command. Given Uniboslan's exact live state (a
   caravan already `Approaching` with no depot to path to, ≈26 days left),
   this is the single most directly actionable finding in this report: it
   buys time for a depot to get built, with zero UI automation, zero policy
   ambiguity, and a mechanism this report verified end-to-end from source.
4. **`depot.execute-trade` remains unnameable as a tool with a confirmed
   mechanism**, exactly as the prior report concluded, but for a more
   precise reason now: not "no struct API exists at all" (a great deal does)
   but "the one remaining step is gated behind the closed-source engine's
   own input dispatch, and this repo's own rules make deploying a script
   that feeds that input a policy call, not a research one." Naming a tool
   here would still misrepresent what this research can back.

## Not verified — summary

- **The exact input (key or mouse position) that triggers the vanilla
  "Trade"/"Offer" confirm action on `main_interface.trade`.** Static reading
  found the buttons are real and clickable (`trade.lua:512`'s own comment)
  but found no named keybind for fort-mode depot trade in
  `data/init/interface.txt` (only the irrelevant adventure-mode
  `A_BARTER_TRADE`), and this report did not open a live trade session to
  test it, per this task's constraints.
- **Whether opening a trade session (`trade.open` becoming `true`) can be
  triggered by a struct write rather than only by an engine reaction to a
  vanilla input** — not tested, no depot exists on this fort to test it
  against.
- **What, if anything, `depot.trade_flags` exposes beyond
  `trader_requested`** — no live depot instance existed on Uniboslan to
  enumerate the struct fully; this report has only the one field confirmed
  by a script's own use of it.
- **How to trigger the `tribute` flag, or what giving tribute actually does
  mechanically** — the flag's existence is confirmed live; nothing sets or
  reads it meaningfully anywhere in the shipped Lua.
- **What happens if the liaison's meeting request is never answered** — no
  source found, wiki or DFHack, that states a consequence either way.
- **Whether seizing goods produces any effect beyond the per-caravan flags
  observed** (entity-level relationship change, reduced future caravan
  frequency) — not traced past the flag level.
- **Which index of `main_interface.trade.good`/`goodflag` (0 or 1)
  corresponds to the fort's own goods versus the merchant's** — the
  structure (`#good == 2`) is confirmed live; which side is which was not
  determined.
- **df-structures XML was not available on VM 103** (only the compiled
  build ships), so struct definitions in this report come from live
  `pairs()` enumeration and direct script reads, not an authoritative XML
  schema the way `research/2026-09-12-dfhack-capability-checks.md` had
  access to via a separately-cloned pinned repository. That prior report's
  method (clone `df-structures` at the matching tag) would be the way to
  close every "not verified" item above about exact field types/sizes,
  without needing a live depot at all — flagged as the concrete next step
  if this question needs to go further.

## Sources

Primary, this session, all against VM 103's live, paused install and its
actual DFHack build (version `53.16-r1.1` per `memory/dfhack-environment.md`,
not independently re-checked this session but not contradicted by anything
found):

- `hack/scripts/caravan.lua` (read in full, 172 lines)
- `hack/scripts/force.lua`, `hack/scripts/diplomacy.lua` (read in full)
- `hack/scripts/internal/caravan/movegoods.lua`, `trade.lua`,
  `tradeagreement.lua` (read substantially, specific line numbers cited
  inline)
- `hack/docs/docs/tools/caravan.txt`, `diplomacy.txt`, `force.txt`,
  `logistics.txt` (read in full)
- `hack/docs/docs/dev/Lua API.txt` (grepped for `trade`/`barter`/`caravan`/
  `depot`/`commit`/`accept`/`offer`)
- `data/init/interface.txt` (grepped for `TRADE`, `DEPOT`, `CARAVAN`, and the
  full adventure-mode `A_*` bind block)
- Live `dfhack-run lua` queries (all read-only; no write, no pause-state
  change, no viewscreen interaction): `df.viewscreen_tradegoodsst`,
  `df.global.plotinfo.caravans`, `df.caravan_state.T_trade_state`,
  `df.global.game.main_interface.trade`, `df.global.game.main_interface.diplomacy`,
  `df.global.world.buildings.other.TRADE_DEPOT`, `df.building_tradedepotst`,
  `df.interface_key.{BARTER_TRADE,CUSTOM_T,CUSTOM_SHIFT_T,SELECT}`,
  `dfhack.world.{ReadPauseState,ReadCurrentTick}`, unit id 64's
  `flags1.diplomat` and readable name.

Repo files read: `research/2026-09-16-food-and-drink-logistics.md`,
`memory/dfhack-environment.md`, `docs/AGENT-ARCHITECTURE.md` (§4, §7),
`docs/PURPOSE.md` (design commitments), `decisions/DECISIONS.md`
(2026-09-16 row and earlier trade/caravan-adjacent rows),
`research/2026-09-12-dfhack-capability-checks.md` (method precedent for
live, read-only `dfhack-run` queries against a paused fort).
