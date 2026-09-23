# Does a zone room have to be enclosed, and how is a higher room value reached

Date: 2026-09-24. Read-only research, answering
`handoffs/2026-09-24-room-enclosure-and-value.md`. No VM changes, no live
writes, no unpause, no deploy, no new live queries against Uniboslan beyond
what yesterday's pass (`research/2026-09-23-room-and-zone-requirements.md`)
already ran; this pass is a web-and-doctrine investigation, not a new live
session. No raw coordinate appears anywhere below.

## Verdict, up front

**Enclosure is not a game requirement for a zone-defined room to count or to
have a nonzero value. This is now corroborated by a second, independent
wiki page and by informal player testing in the current (post-v50, zone-based)
mechanic, not just the one Office page yesterday's pass relied on.** Whether
enclosure changes the *magnitude* of the value, as opposed to gating its
existence, is genuinely contested between two wiki-adjacent sources: one
current-namespace page claims a percentage penalty for perimeter gaps, but
that page carries the wiki's own caveat that it "was migrated from DF2014...
and may be inaccurate for the current version of DF (v53.16)," and its own
body text is written for the old furniture-defined room mechanic (per-item
placement advice, weapon traps, levers stacking mechanisms), which
`research/2026-09-23-room-and-zone-requirements.md` Q1 already established
"no longer exists in v53.16." A separate, informal source (a Steam
Community discussion where a player reports directly testing enclosure by
poking holes in walls and moving walls to the room's interior) found no
value difference at all, and states plainly: "rooms are zones now and don't
care about doors." No install data or DFHack API can adjudicate this either
way (repeating yesterday's Q3/Q6 finding: no numeric room value is exposed
anywhere on this install).

**Confidence: `prior`, not `verified`, on every part of this. The user's
belief that enclosure is a requirement is not supported by anything read
this session, but the honest state is "the best-supported reading of
contested, version-lagging wiki and informal-player sources," not proof.**
A layout checker should not encode enclosure as a value gate or a value
multiplier; if it wants to gain confidence beyond "prior," the only route is
a live test this project has not run (see "What would settle it").

---

## Q1. Is enclosure required for the zone to count or have value at all

**No, on every source checked, and this now has two independent sources
saying so instead of one.**

- **Office** (dwarffortresswiki.org, banner "v53.16", fetched again this
  session): "does not (necessarily) have to be a separate enclosed space
  separated from other areas by walls and a door." Same page yesterday's
  pass cited; re-fetched and re-quoted in fuller context this session,
  which adds that the page explains overlapping room designations reduce
  value (a different mechanic, see Q3), not that enclosure itself is
  required.
- **A Steam Community discussion** ("Does enclosing rooms impact value?",
  `steamcommunity.com/app/975370/discussions/0/5828254882201086677/`,
  fetched this session): the original poster reports directly testing this
  in the current version by starting from a fully enclosed room and poking
  holes in the walls, and separately by building interior (non-perimeter)
  walls instead of perimeter walls, observing no value difference either
  way. The most-upvoted reply: "rooms are zones now and don't care about
  doors. It's just the value of whatever's in the green area you paint."
  This is a `forum` source under doctrine's schema (informal player
  testing, no developer statement, no version banner in the formal sense a
  wiki page carries), weighted accordingly: it corroborates the wiki
  reading and offers a mechanical reason consistent with Q1 of yesterday's
  pass (rooms are zones, valued by contents, not by a walled-room scan),
  but it is not install data and is not being treated as more than a prior.
- **Mechanically, this fits the already-verified finding that rooms are
  zones, not furniture-defined spaces** (`rooms-are-zones-not-furniture`,
  `verified`, install data): a system that values "whatever is painted
  inside the zone's rectangle" has no structural reason to also scan the
  rectangle's perimeter for gaps, whereas the pre-v50 furniture-defined room
  mechanic (walls literally *were* how the room's extent was found) had
  every reason to care about the perimeter. That the source claiming a
  perimeter penalty is explicitly flagged as migrated, possibly-stale
  DF2014 content (next section) is the clean explanation for why these two
  sources appear to disagree without actually needing DF's own value
  formula to arbitrate.

## Q2. What would "enclosed" even mean mechanically, if it meant anything

Not tested and not needed for the Q1 verdict, but recorded for the checker's
benefit if this is ever revisited: neither wiki page defines "enclosed"
precisely enough to encode. The stale "How do I increase the value of a
room" page's own wording is "fully enclosed by walls and/or doors," which
would imply a door counts as closing a gap (not a breach) and that any open
tile on the perimeter is a "gap." No source addresses diagonal gaps,
whether a floor/roof above/below the zone matters independently of the four
side walls, or whether a zone whose painted rectangle extends past the
walls that happen to surround it behaves differently from one that stops
exactly at them. **This project should not manufacture an answer to
questions no source addresses**; if enclosure is ever re-investigated, this
is the specific gap a live test would need to close, not this pass.

## Q3. Does enclosure change value even if not required for existence

**Contested, and the contest itself is the finding.**

- **For it:** the "How do I increase the value of a room" page (fetched
  twice this session, both the current-namespace and the explicit
  `DF2014:` namespaced version, which read identically on this point):
  "Make sure the room is fully enclosed by walls and/or doors -- gaps in
  the perimeter reduce the value of certain features of the room by a
  percentage -- see [a Bay12 forums thread] for details." No percentage is
  given on the page itself; the cited external thread
  (`bay12forums.com/smf/index.php?topic=124938`) was not fetched this
  session (a forum thread behind a search-engine summary only would not
  raise this past `prior` regardless; time was better spent confirming the
  page's own currency, below).
- **Against it, and this is the load-bearing fact:** the same page carries
  the wiki's own migration caveat, read directly this session: **"This
  article was migrated from DF2014... and may be inaccurate for the current
  version of DF (v53.16)."** Its body text is written for the pre-v50
  mechanic throughout: individually stacking furniture pieces, weapon traps
  holding "11 high-value items," levers "stacking theoretically unlimited
  numbers of mechanisms," floor bars needing only "the furniture hauling
  skill." This is exactly the mechanic Q1 of yesterday's pass already found
  gone in 53.16 (`rooms-are-zones-not-furniture`, `verified`): the
  furniture-defined room, not the zone. A page self-flagged as possibly
  describing a retired mechanic, whose surrounding advice is written for
  that retired mechanic, is weak support for a specific claim within it,
  even though the page is filed under the current version number.
- **Against it, informally:** the Steam thread's direct test (Q1) found no
  effect from enclosure at all, for or against, which is the more direct
  kind of evidence (an actual behavioural comparison in the current
  version) than a page-level caveat, even though it is only one player's
  informal report.

**Net: this project should not treat enclosure as a value lever, cheap or
otherwise, until a live test on this install says differently.** Encoding a
"prefer enclosed" bonus in a value estimate would be encoding the weaker,
version-flagged side of a genuine disagreement.

## Q4. The levers that do raise value, and their relative cost

All of the following are `prior` only, drawn from the same
migration-flagged "How do I increase the value of a room" page (fetched in
full this session) as Q3's disputed enclosure claim. Doctrine's rule from
yesterday's pass applies again: this is folklore about a related mechanic
that may not describe 53.16's actual formula, reported here as the best
available account, not confirmed current behaviour. Ordered roughly cheap
to expensive in dig/labour terms, per the page's own framing:

| Lever | What the page says | Cost framing |
|---|---|---|
| Low-quality furniture volume | "Adding more furniture - even low-quality furniture - can raise the room value, if you use enough of it. Fill the room with whatever leftovers are available" | Cheapest: uses stockpile leftovers, no skill requirement implied |
| Floor bars | "Building floor bars only requires the furniture hauling skill, and can produce a modest increase in room value" | Cheap: one low skill, modest payoff |
| Smoothing | "Smoothing and engraving the walls and floors"; "smoothing enhances the value of walls more than that of floors" | Cheap in materials (no material consumed), needs a miner/engraver's dig-detail labour |
| Engraving | Same sentence as smoothing, with the added note that engravers must work "from *inside* the room" | Slightly more expensive: a higher skill than plain smoothing, plus the labour-routing constraint of working from inside |
| Room size | "Increase the size of the room - doubling the amount of floorspace nearly doubles the base value" | Cheap to declare (repaint a bigger zone), expensive to fill: a bigger zone needs proportionally more furniture/smoothing to reach the same per-tile quality, so this is a lever on the *base* component only |
| High-quality/masterwork furniture | "masterwork furniture is worth more than twice as much as the next highest level" | Expensive: needs a skilled craftsdwarf and typically better material |
| Statues | "Statues have the highest base value of 'normal' furniture" | Expensive: stone/skill investment for one of the highest-value single pieces |
| Weapon traps | "weapon traps allow you to stack 11 high-value items into one convenient tile" | Expensive in weapon count, but a genuine density trick: many high-value items on one tile |
| Levers with stacked mechanisms | "Adding levers allow stacking theoretically unlimited numbers of mechanisms" | Cheap per mechanism (mechanisms are simple to make), but the page frames this as a min-maxing trick, not a normal furnishing choice |
| Artifact furniture | "a single legendary piece of furniture can greatly increase the value of a room" | Not obtainable on demand: artifacts are claimed by a mood, not built to order |

**What this means for the practical question ("smallest office for each
position"):** `MANAGER`/`BOOKKEEPER` (`required_office: 1`) need only clear
the Meager band's floor of a positive value, which the Office wiki page and
yesterday's Q3 finding both suggest a single chair can do (a "meager office"
described as "a 1-tile-diameter area designated from a single chair").
`SHERIFF` (100, Modest) plausibly needs one or two mid-quality furniture
pieces or a smoothed floor plus a chair; `CAPTAIN_OF_THE_GUARD` and
`DUNGEON_MASTER` (250) and `MAYOR` (500, Decent) are large enough numbers
that the page's own framing (doubling floorspace nearly doubles the base
value; masterwork furniture is worth "more than twice" the next tier) points
toward smoothing plus a handful of higher-quality furniture pieces rather
than volume alone, since 500 sits well above the Meager/Modest bands. **None
of this can be turned into an actual tile count or furniture list**: no
source gives the base per-tile floor/wall value, no source gives absolute
furniture values by material and quality in this version, and DFHack
exposes no way to read a candidate value before building it (Q6, repeating
yesterday). This question remains "cannot be computed without the value
formula," exactly as the brief allowed for.

## Q5. Is value the only gate a position applies

**No. Population is a second, independently sufficient gate, already found
and install-verified yesterday, and this pass did not find a third.**

- Yesterday's Q4 table (install-verified, re-cited here rather than
  re-read live, since the brief's rules prefer install data already on
  record over a fresh live query): `CAPTAIN_OF_THE_GUARD`, `MAYOR` and
  `DUNGEON_MASTER` each carry `requires_population: 50` alongside their
  value requirement, and all three currently read `HAS_MET_POP_REQ: false`
  on this fort. This is a gate a room's value cannot satisfy on its own,
  confirmed directly on the struct, not inferred from the wiki.
- Yesterday's Q4 also surfaced `required_boxes`/`_cabinets`/`_racks`/
  `_stands`, nonzero for the same four value-requiring positions
  (`SHERIFF`, `CAPTAIN_OF_THE_GUARD`, `DUNGEON_MASTER`, `MAYOR`), read
  directly from the position struct and not currently checked by any tool
  in this repo. Whether these gate order validation independently of room
  value, or are folded into it, was left unverified yesterday and this
  pass found nothing (install, wiki, or forum) that settles it either way.
  It remains a distinct, named open question, not resolved here.
- No source found this session (wiki or forum) describes a location,
  assignment-timing or "distance from other rooms" gate beyond the
  overlap penalty already named in Q3/yesterday's Q3 (two zones' footprints
  overlapping cuts each one's value by 75%, per the same migration-flagged
  page, so `prior` only, but consistent with the Office page's own
  overlap warning, which is current-namespace).
- **This pass did not find a new gate beyond population and the
  furniture-count fields already named yesterday.** That is itself worth
  stating plainly rather than padding: the search for "is there another
  gate" came back empty beyond what was already on record.

---

## What would settle the enclosure question for real

A live test this project has not run and this pass did not run (it would
mutate the fort, out of scope for read-only research): build or identify
two otherwise-matched sites, one with a zone whose furniture sits inside a
fully walled-and-doored perimeter and one with the same furniture in an
open zone of the same size and contents, and compare
`dfhack.buildings.getRoomDescription` on both. Given Q3's finding that the
one page claiming a penalty is self-flagged as possibly stale, the
Steam-thread report that a player already ran approximately this test and
found no difference is suggestive but not a substitute for this project's
own instrumented comparison.

## What could not be verified

- **The exact enclosure-penalty percentage**, if the penalty exists at all:
  the only page naming one points to an external Bay12 forums thread
  (`topic=124938`) that was not opened this session.
- **Whether the "How do I increase the value of a room" page's other
  levers (smoothing, engraving, furniture stacking, weapon traps, levers
  with mechanisms) still function as described in the zone-based mechanic**,
  given the same migration caveat that undercuts its enclosure claim. They
  are reported here as the best available account, explicitly `prior`, not
  as confirmed 53.16 behaviour, exactly as yesterday's pass treated the
  formula-adjacent `DF2014:Room` page.
- **Any base per-tile floor/wall value, or absolute furniture values by
  material and quality in 53.16**, meaning "smallest office per position"
  (brief Q5) remains uncomputed, as flagged above.
- **Whether `required_boxes`/`_cabinets`/`_racks`/`_stands` gate order
  validation the same way room value does** (Q5 above; unresolved since
  yesterday, not newly settled this session).
- **The Steam Community thread's reliability**: one informal player report,
  not independently reproduced by this session, not a developer statement,
  and not dated to a specific patch within "the current Steam version." It
  is treated as corroborating, not as proof, consistent with doctrine's
  rule that only install data verifies.

## Sources

Web, fetched this session, each quoted by its own version banner or caveat
where one exists (untrusted data about this install per doctrine's own
rule; `prior`/`forum` only, never `verified`):

- [Office](https://dwarffortresswiki.org/index.php/Office) (banner
  "v53.16"), re-fetched for fuller context around the enclosure sentence.
- [How do I increase the value of a
  room](https://dwarffortresswiki.org/index.php/How_do_I_increase_the_value_of_a_room)
  (filed under the current, unprefixed title, but carrying its own
  in-page caveat: "migrated from DF2014... may be inaccurate for the
  current version of DF (v53.16)"), fetched twice this session for the
  enclosure sentence in context and for the full lever list.
- [DF2014:How do I increase the value of a
  room](https://dwarffortresswiki.org/index.php/DF2014:How_do_I_increase_the_value_of_a_room)
  (explicit `DF2014:`/v0.47.05 namespace), fetched to confirm the two
  pages read identically on the enclosure sentence, i.e. the
  current-namespace page is effectively an uncorrected copy of this one.
- [Does enclosing rooms impact
  value?](https://steamcommunity.com/app/975370/discussions/0/5828254882201086677/)
  (Steam Community discussion, `forum` source, no formal version banner;
  read as current-version player testing based on its own content).

Not fetched this session (named for future reference, not relied on): the
Bay12 forums thread cited by the stale wiki page for the enclosure
percentage (`bay12forums.com/smf/index.php?topic=124938`); the "PSA: If you
are having trouble with room value, you need to separate them" and "How are
people finding exact room values?" Steam threads (surfaced by search, not
opened, since this pass's central question was already answered by the
pages above and time was spent confirming the stale-page finding instead).

Repo, re-cited from yesterday's pass rather than re-read in full this
session (already-established findings this pass builds on, not re-derived):
`research/2026-09-23-room-and-zone-requirements.md` (Q1, Q3, Q4, Q6),
`doctrine/seed.yaml` `rooms` topic entries (`rooms-are-zones-not-furniture`,
`room-value-not-computable-only-quality-word`,
`uniboslan-office-furniture-outside-zone-footprint`,
`room-furniture-must-sit-inside-zone-footprint`,
`room-indoor-status-not-shown-to-matter`,
`noble-position-room-value-and-furniture-requirements`,
`room-value-quality-tier-table`).
