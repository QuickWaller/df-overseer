# Water delivery to an incapacitated dwarf, and hospital supply reservation

Desk research only. No SSH, no DFHack, no fort read. Every claim below is
either a directly-read primary source (quoted or exact-fetched) or is marked
otherwise. Namespace is stated on every wiki claim per the project's own
namespace-trap history. Nothing here may be promoted past `prior` in
`doctrine/seed.yaml`, per that file's header rule (no live-read or game-data
source describing 53.16 backs a `verified` water/hospital entry yet, this
research doc included).

## Bottom line

The doctrine entry `bucket-par-and-labor-redundancy` is right about the part
it treats as solid (par level, redundancy, existence-vs-availability) and
wrong or unsupported about the specific mechanism it offers as an open
question. In detail:

1. **`FEED_WATER_WOUNDED` does not exist as a DFHack/engine token.** The real
   label, in both DFHack's own struct definitions and every wiki namespace
   checked, is **`FEED_WATER_CIVILIANS`**. This is a naming problem, not a
   mechanics problem, but it is load-bearing: if the fort's own live read
   queried a field called `FEED_WATER_WOUNDED`, it was querying something
   that is not a real `unit_labor` enum member, and the "0 of 15" figure
   needs to be re-taken against the correct field before anyone treats it as
   informative. This **contradicts** how `docs/PRODUCTION-MODEL.md` §13 and
   the doctrine entry both name the labor, and is the single most useful
   correction in this brief.

2. **The hospital-zone-reservation explanation for the bucket cancellation is
   very likely wrong, on two independent grounds**, and the doctrine entry's
   framing of it as "DF's own answer" should be softened to "one candidate,
   probably not the operative one here":
   - Nothing in this repo's own records (`Working.md`, `decisions/DECISIONS.md`,
     `memory/`, `scripts/dfhack/df-overseer-zone.lua`) shows Uniboslan ever
     having a hospital zone. The fort's only recorded zone is the
     `WaterSource` zone at z168. The zone tool this project has only knows
     how to place `civzone_type.WaterSource`, not a hospital location.
   - Independent of whether a hospital zone exists: DFHack's own
     `df.job.xml` categorizes `GiveWater` under job type **`LifeSupport`**,
     a different category from the eight `Medicine`-type jobs
     (`DiagnosePatient`, `Surgery`, `Suture`, `SetBone`, `DressWound`,
     `CleanPatient`, `ImmobilizeBreak`, `PlaceInTraction`) that the wiki's
     hospital-reservation passage is actually describing. The wiki's own
     text about hospital containers reserving supplies is about "medical
     use" for doctors, and explicitly says containers only *earmark*
     supplies while "doctors can and will use supplies from anywhere" absent
     a container. It never claims the reservation is an exclusive lock, and
     it is not obviously about `GiveWater` at all.
   - The unit that needed water (the sleeping miner, `unconscious=2, pain=0,
     wounds=0`) was not a hospital patient in any sense this repo has
     recorded. Hospital reservation, even if it worked exactly as recalled,
     would have nothing to reserve *against* here.

3. **What the sources actually support for the cancellation** is closer to
   what `docs/PRODUCTION-MODEL.md` §9 already calls a "lossy hint": distance,
   reachability, or a race with another `GiveWater`/hauling job are the
   causes the wiki, a Bay12 bug report, and forum reports converge on, none
   of them specific to hospitals. This is **prior**, not confirmed, and the
   brief's own live-trace suggestion (§3 below) is the way to settle it.

4. **The doctrine's par-level and redundancy guidance is unaffected by any
   of the above** and stands on its own reasoning (insurance-band goods,
   existence-vs-availability, the three deductions). Nothing found here
   argues against holding 2+ buckets or enabling the labor on more than one
   dwarf; it only argues against citing hospital reservation as the
   explanation for why a job failed once.

---

## 1. What actually delivers water to an incapacitated dwarf

**Job**: `GiveWater` (engine/original name `GIVE_WATER`). Confirmed directly
from DFHack's own structure definitions:
`https://github.com/DFHack/df-structures/blob/master/df.job.xml` (master
branch, fetched 2026-09-18, full text read, not summarized):

```
<enum-item name='GiveWater' original-name='GIVE_WATER'>
    <item-attr name='caption' value='Give Water'/>
    <item-attr name='type' value='LifeSupport'/>
    <item-attr name='labor' value='FEED_WATER_CIVILIANS'/>
</enum-item>
```

Confidence: **high**, this is DFHack's own compiled-from-game-memory struct
description, the closest thing to primary source available without a live
read. Caveat: the fetch was against the `master` branch, not a tag pinned to
this install's DFHack 53.16-r1.1. DFHack's structures repo tracks the current
Steam-era engine continuously and this specific labor/job pairing shows no
sign of recent churn (see below), so the risk of drift is low, but it is not
independently pinned the way `doctrine/seed.yaml`'s provenance rule expects
for a `verified` claim.

**Gating labour**: `FEED_WATER_CIVILIANS`, not `FEED_WATER_WOUNDED`.
`FEED_WATER_WOUNDED` does not appear anywhere in `df-structures` (checked
`df.job.xml`, `df.unit.xml`, `df.entity.xml`, `df.d_init.xml`,
`df.occupation.xml`, `df.game_v.xml`; also checked DFHack's own `autolabor`
tool docs, below). It also does not appear on either wiki namespace's
Health_care, Labor, or Bucket pages. It looks like a project-internal
compound of two real, separate things: `FEED_WATER_CIVILIANS` (the labour
that actually gates `GiveWater`/`GiveFood`) and `RECOVER_WOUNDED` (a
different labour, gating the `RecoverWounded`/`BEDCARRY` job that hauls an
injured unit *to* a bed or hospital, before any water job is relevant).

**Wiki namespace check, both read as raw wikitext via the MediaWiki API**
(not the summarized/rendered view, to avoid losing exact wording):

- Current namespace (`https://dwarffortresswiki.org/index.php/Health_care`,
  version banner `{{Quality|Fine}}`, page references a "Hospital information
  v50.03.png" screenshot, i.e. this is the v50/Steam-track page): calls the
  labour **"Feed patients/prisoners"**, lists it as one of "two unskilled
  supporting hauling labors," "Part of the default orderly work detail."
  Exact quote: *"Any dwarves with the feed patients/prisoners labor will
  attempt to give food or a bucket of water to a hungry or thirsty
  patient."*
- `DF2014` namespace (`https://dwarffortresswiki.org/index.php/DF2014:Health_care`,
  describes v0.47.05): **identical wording**, same table, same "Part of the
  default orderly work detail" phrase attached to the same three labours
  (Recovering wounded, Feed patients/prisoners, and implicitly the doctoring
  five).

So on the specific question "did v50 change the labour model here," the
honest answer is **no evidence of a rename or regating**: both namespaces
describe the same labour under the same display name, gating the same kind
of job. The bigger v50 change is the *UI* layer (work details replacing the
old direct labour-toggle screen), not the underlying labour token, and the
current page's own troubleshooting note confirms this is a UI/propagation
issue, not a new gating mechanism: *"Dwarves assigned roles via the hospital
zone will only begin doing them once the labors for all dwarves have been
updated. To quickly achieve this, go to the labor menu and set 'only
selected dwarves mine' to 'no dwarves mine' and then set back... or do
anything else in work details."*

One namespace-hygiene flag worth naming: the `DF2014:Health_care` page's
wikitext *also* uses the phrase "orderly work detail," which is v50-era UI
terminology. That is either the wiki's DF2014 page having been touched up
with v50 language by an editor (contamination across namespaces, the exact
trap this project watches for) or the phrase predates and outlived the UI
it's now associated with. Not resolved here; flagged so nobody treats the
DF2014 page's wording as a clean pre-v50 snapshot without checking its edit
history.

**Confirmed independently, version-matched**: DFHack's own `autolabor`
plugin documentation, fetched from `https://docs.dfhack.org/en/stable/docs/tools/autolabor.html`,
whose page title reads **"autolabor — DFHack 53.16-r1 documentation"**
(matches this install's DFHack 53.16-r1.1 almost exactly), uses
`FEED_WATER_CIVILIANS` as the labour identifier in its own worked example:

> `autolabor FEED_WATER_CIVILIANS haulers` — *"Have haulers feed and water
> wounded dwarves."*

This is about as strong a confirmation as a desk pass can produce without a
live read: the exact DFHack version this fort runs, in its own shipped docs,
uses `FEED_WATER_CIVILIANS` for precisely the concept the doctrine entry
calls `FEED_WATER_WOUNDED`.

**Live read that would settle this for good**: re-run whatever query
produced "0 of 15" and confirm which `df.unit_labor` enum member it actually
read. If it read `FEED_WATER_CIVILIANS` and got a genuine 0, that is a
different and more interesting finding (see §2). If it read a field named
`FEED_WATER_WOUNDED`, that field does not exist in the struct definitions
checked here, and the read's behaviour in that case (error vs. silently
returning false/0) needs to be understood before the number is trusted at
all.

---

## 2. How a `GiveWater` job got taken with the labour reading zero

The brief lists four candidate explanations and asks not to resolve this by
reasoning alone. Here is what each source actually supports:

**a) "The labour does not gate that job in this version."** **Contradicted.**
`df.job.xml` ties `GiveWater` to `FEED_WATER_CIVILIANS` explicitly, as does
DFHack's own autolabor docs for this exact DFHack version. The job is gated;
the candidate that nothing gates it is not supported by anything found.

**b) "autolabor assigns dynamically, so a snapshot isn't the whole
story."** **Partially supported, but with a new wrinkle the doctrine entry
doesn't yet have.** The `autolabor` docs (version-matched, 53.16-r1)
describe the *default* allocation rule: *"By default, each labor is assigned
to between 1 and 200 dwarves... The labor is then added to the best
&lt;minimum&gt; dwarves for that labor, then to additional dwarves that
meet any of [idle-and-unassigned, nonzero skill, or (mining/hunting/
woodcutting and already enabled)]."* Under that stated default, any labour
with no custom override should land on **at least 1 dwarf**, not 0, since
the default minimum floor is 1. `FEED_WATER_CIVILIANS` is *not* one of the
jobs the docs list as bundled into the default 33% "haulers" group (that
list is explicitly: hauling jobs, cleaning, pulling levers, **recovering
wounded**, removing constructions, filling ponds — `FEED_WATER_CIVILIANS`
is conspicuously absent from that list, and only gets routed to haulers if
someone runs the example command `autolabor FEED_WATER_CIVILIANS haulers`
by hand). So under a default, unmodified autolabor configuration, a genuine
"0 of 15" reading for `FEED_WATER_CIVILIANS` would itself be an anomaly
against DFHack's own documented floor, not an expected consequence of
autolabor's normal operation. This raises rather than lowers the suspicion
that the "0" is a field-name artifact (§1), though it doesn't rule out a
custom override in this fort's autolabor config, which this research pass
has no way to check.

Also worth carrying into the doctrine entry: the same docs carry a
version-matched, explicit warning that undercuts trust in *any* autolabor
number here: *"The algorithms that autolabor uses to choose labor
assignments have not been updated for version 50 of Dwarf Fortress... it is
entirely possible that the assignments it makes will lead to unforeseen
consequences."* And: *"When it is enabled, autolabor automatically disables
the work detail system. You cannot use autolabor and work details at the
same time."* So if autolabor really is running fort-wide (per CLAUDE.md,
confirmed enabled), the wiki's "part of the default orderly work detail"
default-on framing for `FEED_WATER_CIVILIANS`/"Feed patients/prisoners"
**does not apply** at all right now: vanilla work details are fully
suspended while autolabor is active, so the "everyone starts with this
enabled" baseline the wiki describes is not the fort's actual starting
condition. Autolabor's own algorithm is the only thing setting labour flags
fort-wide, and per its own docs that algorithm is untested against v50.

**c) "The job is a healthcare activity routed differently from ordinary
labours."** **Contradicted, structurally.** `df.job.xml` puts `GiveWater`
in job-type category `LifeSupport`, a separate category from the `Medicine`
category that holds every doctor-labour job (`DiagnosePatient`, `Surgery`,
`Suture`, `SetBone`, `DressWound`, `CleanPatient`, `ImmobilizeBreak`,
`PlaceInTraction`). There is no structural sign that `GiveWater` is treated
as a healthcare/hospital activity by the engine's own job taxonomy; it sits
alongside `GiveFood`, `GiveWaterPet`, `GiveFoodPet` under the same
`LifeSupport` category, i.e. general welfare jobs, not medicine.

**d) "The wiki's labour list is stale."** **Not supported.** Both wiki
namespaces, read as raw wikitext rather than a rendered summary, agree with
each other and with DFHack's own struct definitions and DFHack's own
autolabor docs, on the labour's existence and its display name. Nothing
found suggests staleness here; if anything it's the doctrine entry's own
naming that's out of step with every source checked.

**What the sources cannot settle:** whether the actual metalcrafter who took
and cancelled the job at tick 214135 had `FEED_WATER_CIVILIANS` set at that
moment, whether autolabor assigned it transiently and then reassigned it
away before the next census, or whether the job was picked up through some
other path DFHack occasionally allows (e.g. a burrow override, or a
temporary assignment autolabor made and then walked back within the same
tick window). None of the sources here address per-tick labour churn; that
needs a live trace, which the brief already rules out for this pass.

**Live read that would settle this**: two things, both cheap. (1) Re-query
`unit.status.labors[df.unit_labor.FEED_WATER_CIVILIANS]` (the confirmed-real
field) across all 15 citizens and compare to the existing "0 of 15" figure
taken under whatever field was actually queried before. (2) If autolabor
logging was enabled at tick 214135 (`debugfilter` at debug/trace for
autolabor's cycle mode), check whether autolabor assigned
`FEED_WATER_CIVILIANS` to the metalcrafter shortly before the job was taken.

---

## 3. Why "Need empty bucket" fired with three empty buckets present

**What the wiki says about bucket selection mechanics for `GiveWater`
specifically: very little, directly.** Both the current and `DF2014`
`Bucket` pages (current fetched in full as raw wikitext; DF2014 checked)
describe what buckets are *for* — *"giving water to thirsty dwarves who are
wounded or busy"* (current page, exact quote) — but neither states the
selection algorithm: no stated distance rule, no stated claim/reservation
rule beyond the general hospital-requisition passage in Health_care (§4),
and no mention of "Need empty bucket" as a phrase at all. This is a real gap
in the wiki as a source, not a gap in this research pass.

**Community reports, weak but converging**, from a Steam Community
discussion thread
(`https://steamcommunity.com/app/975370/discussions/0/3727324132824954154/`,
forum, `read: search-summary` via a fetch-and-summarize tool, not the raw
thread text, so treat as lower confidence than the wiki/structures material
above) about the exact symptom "cancels Give water: Need empty bucket"
despite visible empty buckets:

- One reply frames it as a general DF pattern: cancellation messages report
  "the last failure point in the chain," which is a hint the message text
  is not reliably diagnostic of the actual blocking condition — this
  matches `docs/PRODUCTION-MODEL.md` §9's own stance that cancellation
  announcements are "a lossy hint, not a shortcut."
- The thread's own resolution, in that specific case, was **reachability**:
  the recipient unit had become physically unreachable (walled off in the
  caverns), not a bucket problem at all, even though the message named
  buckets.
- A separate reply claims *"hospitals maintain separate bucket inventories
  and won't draw from external stockpiles"* and that distance to the
  recipient increases cancellation odds. This is an uncorroborated forum
  claim (one reply, no source cited, no version stated) and it directly
  conflicts with the current wiki's own Health_care text (§4 below), which
  says hospital containers only *earmark* supplies and doctors "can and
  will use supplies from anywhere." Flagging this as an open contradiction
  rather than picking a side.

**Bay12 official bug tracker: unreadable.** Both bug reports found by search
(`0007690`, "Dwarfs with 'Give Water' job won't use buckets," and `0008363`,
"Spam flood of Cancel Give Water - No Empty Bucket") returned a database
error on every fetch attempt, the same failure mode already logged in
`doctrine/seed.yaml`'s `do-not-overfish` entry for the Bay12 tracker. Their
existence (titles matched exactly by search) is itself weak evidence that
this is a recognized, recurring community-reported symptom, not a one-off,
but their content could not be read and their version/resolution status is
unknown.

**DFHack's own tooling implies a related, but distinct, bucket failure
mode.** `https://docs.dfhack.org/en/stable/docs/tools/fix/dry-buckets.html`
(DFHack docs, `stable` branch, general, not version-pinned in the fetched
text) documents a fixer for a known cause of buckets silently going
unusable: *"dwarves drop buckets of water on the ground if their water
hauling job is interrupted. These buckets then become unavailable for any
other kind of use."* This is a plausible mechanism for "the fort owns N
buckets by count, but fewer are actually usable" independent of forbidding,
claiming, or hospital reservation, and it matches the project's own
available-vs-total framing in `docs/PRODUCTION-MODEL.md` §7 (which currently
lists four deductions: job-claimed, owned, forbidden, caravan-owned, and
flags trade-depot transfer as a fifth unverified case). **A dropped,
still-holding-water bucket looks like a sixth deduction not yet in that
list**, worth adding once verified: a bucket that reads non-empty (holding
water from an interrupted haul) fails "empty bucket" filtering even though
it is unforbidden, unclaimed, and fort-owned. Whether any of the fort's
three buckets (81, 149, 150) were ever in this state at tick 214135 is
unknown from this pass.

**Not found anywhere**: a stated maximum distance, a stated "must be within
the hospital/burrow" rule, or a stated path-reachability check specific to
`GiveWater`'s bucket selection (as opposed to the *recipient's*
reachability, which is documented). The brief's own hypothesis, that the
project's available-vs-total-stock deduction model predicts exactly this
class of failure, is **supported in shape** (a bucket can exist,
be counted, and still be unusable for reasons item-flag reads don't catch)
but **not pinned to a specific one of the candidate mechanisms** by anything
read here.

**Live read that would settle this**: trace job 372 (or whichever job ID the
cancelled `GiveWater` was) at tick 214135 specifically — which of the three
buckets (if any) it evaluated, what `item.flags` and `item.flags2` each
carried at that moment (forbidden, in_job, non-empty/holding a contaminant,
trader-owned), and the recipient unit's and the metalcrafter's map
coordinates relative to each bucket and to any water source, to check for a
severed path. A second, cheaper check: query `item.flags.dump`,
`item.flags.melt`, and the item's `general_refs` for a `CONTAINS` reference
(the flag `dry-buckets` targets) on the three known bucket IDs right now, to
see whether any of them is silently non-empty.

---

## 4. Hospital zones and supply reservation

**What the current wiki (raw wikitext, `Health_care`, v50/53.16-track)
actually says**, quoted exactly because the exact wording matters here:

> *"The hospital will requisition thread, cloth, splints, crutches, plaster
> powder (for casts), buckets, and soap for medical use. These will be
> stored within the hospital's containers; you may adjust the desired
> quantities."*

> *"Place chests... to store medical supplies reserved for hospital use.
> Once placed, dwarves will start stocking the hospital with medical
> supplies... (Containers are not strictly necessary; doctors can and will
> use supplies from anywhere, but dedicated hospital containers allow you to
> earmark some supplies for medical use — for example, to prevent the
> auto-looming of every last thread.)"*

Read closely, this describes a **stocking/staging behaviour** (dwarves haul
designated supply types into hospital-linked containers, the way a
stockpile-give-link works), not a documented hard claim-lock that would
show up as, say, a special `item.flags` bit preventing a non-medical job
from taking the item. The parenthetical is explicit that the alternative to
using a container is "doctors... use supplies from anywhere," which reads
as containers being an *opt-in convenience*, not the only path to medical
supply. The `DF2014` namespace page carries the identical passage,
word-for-word in the container paragraph, so this is not a v50 change
either; it is the same described behaviour across both namespaces.

**Quantities**: confirmed on both namespaces, identical figures: hospital
container capacity is tracked in different units than stockpile units — "1
stockpile unit of thread = 15000 in the hospital," "1 cloth = 10000," "1
soap = 150," "1 gypsum powder = 150." No conversion figure is given for
buckets specifically; buckets appear to be tracked by item count like
splints and crutches, not by the scaled-unit system used for thread/cloth/
soap/plaster.

**What creates a hospital and what it needs**: designate a Meeting Area
zone, then add the Hospital location to it (current page: *"select the Add
Location button (plus sign) and select Hospital"*). Functionally it needs,
per the same page: beds (patients rest there, can lie on the ground if none
available), at least one table (surgery, "you may perform surgery without
tables; it will be messier"), one or more traction benches (compound
fractures, one patient at a time each), and containers (optional but
recommended, for supply earmarking as above).

**Confirm/correct/report, per the brief's four options**: **correct, with a
scope narrowing.** The mechanism the doctrine entry recalls (a hospital zone
reserves its own supplies) is real and wiki-documented, not invented. What
needs correcting is treating it as the likely explanation for the `GiveWater`
cancellation specifically: (a) it is described as a staging/earmarking
behaviour for `Medicine`-category jobs, not a documented hard lock, (b)
`GiveWater` is structurally a `LifeSupport`-category job per DFHack's own
job-type taxonomy (§1, §3), not a `Medicine`-category one, and (c) nothing
in this repo's own records shows Uniboslan has a hospital zone at all (see
Bottom line), so even the correctly-scoped version of the mechanism has
nothing to reserve against here.

**Live read that would settle this**: `dfhack.buildings` / civzone query for
any `df.abstract_building_hospitalst` (or equivalent v50 hospital location
struct) at Uniboslan, to confirm directly whether a hospital zone exists at
all. If one does, cross-reference its container list against the three
known bucket IDs (81, 149, 150) to see if any sit inside a hospital-linked
container right now.

---

## 5. What a fort minimally needs for a wounded dwarf to be treated at all

From the current wiki `Health_care` page, raw wikitext, with the doctor-
labour table reproduced because the wording is precise about which labours
are skilled vs. supporting:

| Labour | Kind | Role |
|---|---|---|
| Diagnostician | skilled | prescribes which of the other four are needed; **nothing else can start without this** |
| Surgeon | skilled | internal organ damage, excising necrotic tissue, serious muscle/bone injury |
| Bone doctor | skilled | sets simple breaks |
| Suturer | supporting (orderly default) | stops serious bleeding |
| Wound dresser | supporting (orderly default) | finalizes closed wounds |
| Recovering wounded | supporting (orderly default) | hauls the injured unit to the hospital |
| Feed patients/prisoners | supporting (orderly default) | gives food/water to patients/prisoners |

Doctors are appointed to one of four v50-era doctoring occupations
(diagnosis, surgery, bone-setting, or the combined "doctor" role covering
all three) and "operate under the instruction of the chief medical dwarf,"
an appointed noble.

**Minimum to treat anything at all, per the page's own framing**: a hospital
location with at least beds; **at least one diagnostician** (page's exact
words: *"without a diagnosis, patients cannot be treated, if they cannot be
treated, they will occupy the hospital area until they die, performing no
function"*); soap is not strictly required but its absence "increases the
risk of infection, which will most likely kill the patient"; water access
("designated source... safe, nearby and clean, either a well, cistern or
running water") is needed for washing and for suturing/dressing; a traction
bench only if compound fractures are expected; splints or (preferably)
gypsum plaster for simple fractures.

**Newcomer traps explicitly named on the page**, verbatim or close to it,
worth carrying into an insurance-par-level writeup:

- **Occupation-assignment propagation bug**: assigning a doctor occupation
  at the hospital does not take effect until the labor/work-detail screen is
  touched again; the page gives the workaround (toggle a work detail
  assignment to force recomputation).
- **Chief medical dwarf is a single point of failure by design**: nobles
  with meeting responsibilities are deprioritized by autolabor, and per the
  autolabor docs (§2), the chief medical dwarf specifically is *"never"*
  assigned other labors by autolabor. If a fort has no chief medical dwarf,
  the wiki (via the Steam-community search summary cross-checked earlier)
  states this "turns off" the hospital: nobody gets fixed or fed.
- **Save/reload can lose in-flight rescue jobs**: *"'Bring crutch' and
  'Recover Wounded' jobs will be lost [on save/reload], keeping the patient
  away from the hospital, and doctors will NOT go to patients, even if
  burrowed with them, because a diagnose job hasn't been created."* The
  page's own recommended mitigation: keep a non-burrowed dwarf with
  `RECOVER_WOUNDED` enabled at all times, and don't burrow doctors away from
  the hospital during an active injury.
- **A separately-documented bug** (page's own Bugs section): *"Dwarves
  resting in bed may be starving/dehydrated and not being taken care of;
  deconstructing the bed to generate a new Recover Wounded task and force
  them to rest properly fixes this."* This is a live, named workaround for
  exactly the failure class doctrine is worried about (an incapacitated
  dwarf silently not getting food/water), independent of bucket supply.
- **Chairs near surgery tables**: explicitly called out as inviting
  "freeloaders" to block medical procedures.
- **Unit conversion trap for anyone setting hospital stock targets**:
  hospital container capacity is tracked in scaled units (15000 per
  stockpile-unit of thread, 10000 per cloth, 150 per soap, 150 per gypsum
  powder), not raw item counts. A par level written in ordinary item-count
  terms for thread/cloth/soap/plaster will be off by three to four orders of
  magnitude if applied directly to the hospital-information screen's
  numbers. Buckets and splints/crutches do not carry a stated conversion
  factor, suggesting (not confirmed) they are tracked by plain item count
  unlike the scaled goods.
- **Temperature trap, from the `Bucket` page**: below-freezing temperatures
  (e.g. glacier layers) freeze water inside buckets, disabling them
  ("bucket full" message) until the ice is dumped out. Not obviously
  relevant to Uniboslan's swamp-region embark, but worth having on file
  since it's another silent "the bucket exists but can't be used" mode
  alongside the dry-buckets one in §3.

**Live read that would settle par-level sizing precisely**: none of the
above needs a live read to be usable as doctrine text (it's all Q1-shaped,
static rules), but confirming *this fort's actual state* against the list
(is there a chief medical dwarf appointed, is there a diagnostician, does
autolabor have `DIAGNOSE` and the four doctor labours assigned to anyone)
would need a labour/occupation census the same shape as the one already run
for `FEED_WATER_CIVILIANS`/`PLANT`/`BREWER`/etc. in
`docs/PRODUCTION-MODEL.md` §13.

---

## What could not be found

- **The exact field name the live read that produced "0 of 15" actually
  queried.** This is the single biggest unresolved item and it's a
  live-fort question, out of scope for this desk pass by the brief's own
  restriction. Flagged as the first thing to check.
- **Whether Uniboslan currently has a hospital zone at all.** Inferred
  "probably not" from the complete absence of any mention across
  `Working.md`, `decisions/DECISIONS.md`, `memory/`, and the zone tool's
  supported types, but this is an absence-of-evidence inference from repo
  records, not a live query result, and could be wrong if a hospital zone
  was built and simply never written up.
- **A stated distance or path-reachability rule specific to `GiveWater`'s
  bucket selection.** Neither wiki namespace states one. The forum evidence
  is suggestive (reachability of the *recipient* mattered in at least one
  documented case) but doesn't speak to bucket *selection* distance
  specifically.
- **The two Bay12 Mantis bug reports' actual content** (`0007690`, `0008363`).
  Both returned a database error on every fetch attempt, the same failure
  mode already on file in `doctrine/seed.yaml`'s `do-not-overfish` entry. An
  alternate mirror (the way `dwarffortressbugtracker.com` served as a mirror
  for the fishing dev-log bug previously) was searched for but not found
  serving these specific bug IDs.
- **Whether `GiveWater` requires the recipient to be a hospital-tracked
  "patient"** (health-screen entry) versus firing for any unit that reads as
  thirsty/needing regardless of hospital status. The wiki's own wording
  ("thirsty patient," "wounded or busy") is ambiguous on this point and
  nothing in `df.job.xml` settles it, since job-type categorization doesn't
  encode trigger conditions. This matters for whether hospital-adjacent
  mechanics are relevant to ordinary (non-hospitalized) citizens at all, and
  a live read of the sleeping miner's health-screen/patient status at the
  time would settle it directly.
- **Whether any of the fort's three known buckets (81, 149, 150) were ever
  in a "dropped while holding water" state** at or before tick 214135, the
  mechanism DFHack's `fix/dry-buckets` tool targets. Would need a live
  `item.flags`/contained-item check on those specific IDs at that tick, or
  the current state if the condition persists.
- **The unit_labor enum's own source file** in `df-structures` (the file
  actually defining the enum that `df.unit.xml`'s and `df.entity.xml`'s
  `index-enum='unit_labor'` references). Confirmed the job-to-labor mapping
  via `df.job.xml`'s `item-attr name='labor'` values instead, which was
  sufficient to answer the brief's questions, but the canonical enum
  listing (in case a future check needs the full labor list, not just the
  ones tied to specific jobs) was not located in this pass.

## Sources cited

- DFHack/df-structures, `df.job.xml`, GitHub `master` branch, fetched and
  read in full 2026-09-18: https://github.com/DFHack/df-structures/blob/master/df.job.xml
- DFHack/df-structures, `df.unit.xml`, `df.entity.xml`, `df.d_init.xml`,
  `df.occupation.xml`, `df.game_v.xml`, same repo/branch, grepped for
  `unit_labor`/`FEED_WATER`/`RECOVER_WOUNDED`, 2026-09-18.
- DFHack docs, `autolabor`, version banner "DFHack 53.16-r1 documentation":
  https://docs.dfhack.org/en/stable/docs/tools/autolabor.html
- DFHack docs, `fix/dry-buckets`: https://docs.dfhack.org/en/stable/docs/tools/fix/dry-buckets.html
- Dwarf Fortress Wiki, current namespace, `Health_care`, raw wikitext via
  MediaWiki API, version banner `{{Quality|Fine}}` / v50-track imagery:
  https://dwarffortresswiki.org/index.php/Health_care
- Dwarf Fortress Wiki, `DF2014:Health_care`, raw wikitext via MediaWiki API,
  describes v0.47.05: https://dwarffortresswiki.org/index.php/DF2014:Health_care
- Dwarf Fortress Wiki, current namespace, `Bucket`, raw wikitext via
  MediaWiki API: https://dwarffortresswiki.org/index.php/Bucket
- Dwarf Fortress Wiki, `DF2014:Bucket` (checked, found nothing on job
  mechanics): https://dwarffortresswiki.org/index.php/DF2014:Bucket
- Dwarf Fortress Wiki, current namespace, `Labor` (summarized via fetch, not
  raw wikitext): https://dwarffortresswiki.org/index.php/Labor
- Steam Community discussion, "Canceling give water due to (false) lack of
  empty buckets," read via fetch-and-summarize (forum, search-summary grade):
  https://steamcommunity.com/app/975370/discussions/0/3727324132824954154/
- Bay12 Mantis bug tracker, `0007690` and `0008363` — titles matched by
  search, content unreadable (database error on every fetch), same failure
  mode as the tracker's prior appearance in `doctrine/seed.yaml`:
  https://www.bay12games.com/dwarves/mantisbt/view.php?id=7690 ,
  https://www.bay12games.com/dwarves/mantisbt/print_bug_page.php?bug_id=8363
- This repo, checked for existing hospital-zone evidence: `Working.md`,
  `decisions/DECISIONS.md`, `memory/`, `working-archive/`,
  `scripts/dfhack/df-overseer-zone.lua`, `docs/PRODUCTION-MODEL.md` §12/§13,
  `doctrine/seed.yaml` (`bucket-par-and-labor-redundancy`).
