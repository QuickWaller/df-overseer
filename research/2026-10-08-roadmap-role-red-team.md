# Red team: the fort roadmap and the Elder role

Date: 2026-10-08. Read-only red team of
`research/2026-10-08-roadmap-role-design.md` (the "design" below). No VM
touched, no code changed. Two wiki pages were re-read through the wiki's API
to check the seed numbers.

Tags: **[verified]** read this session in repo code, data, a register row or
a live wiki page (revid given); **[recalled]** the reviewer's own knowledge,
not fetched; **[inferred]** follows from verified pieces, not observed.

---

## 0. Verdict, up front

**Direction holds; the design is about three times larger than the evidence it
will ever get.** Fort-agnostic roadmap data that the Planner applies with
comply-or-explain is right, small, and meets the user's core ask ("not
something I want it constructing brand new for every fort"). The learning
half (stage-occurrence grading, `measured` promotion, oscillation detection,
step and rate limits, slice-waste metrics, a cross-fort store with export and
drift checks, a new action class) is machinery for a sample that does not
exist and will not exist on any horizon the project plans for. Build the data
and the Planner half now; build the Elder as a rare, fort-end reviewer whose
changes ride existing mechanisms; let utilisation sampling, not outcome
grading, be the thing that actually learns numbers.

**Blockers (4):**

- **B1.** Outcome grading cannot reach significance in this project's
  lifetime; the learning loop as designed produces only "unclear" or noise
  (finding 1).
- **B2.** The hoop-failure exception points the wrong way: a death with the
  target met is evidence the number was not the cause, and this fort's own
  thirst history shows the misfire it would produce (finding 2).
- **B3.** The seed's Quartermaster line ("drink and meals toward ten per
  citizen") contradicts verified doctrine that forbids inventing a cover
  target anywhere, and decision 6 would make the roadmap a third source for
  stock numbers (finding 3).
- **B4.** Two of the four trigger families cannot be evaluated during a fort:
  ledger milestones are written once per fort into an append-once store, and
  no wealth read exists; the `town` stage is reachable only by population and
  its targets are all inert (finding 5).

**Smallest version worth building first** (section 3): the seed file with
three stages and targets only; stage computed by code from `alive` with a
stored high-water mark, cross-checked against the game's own
population-requirement flags; the Planner's slice, `roadmap_ref` and the
code-computed deviation flag; `plans/default-v1.yaml` retired. The Elder
comes next as a one-shot role woken at fort end, by a user request or by an
ask, filing a `ruling_only` proposal the Overseer rules on, applied by the same
mechanical validator-and-commit step doctrine needs anyway. No new store, no
new action class.

**Decision changes:** disagree with 4, 6 and 9; amend 3, 5 and 7; agree with
1, 2, 8 and 10; add two decisions (when changes take effect; where stage
thresholds come from). Section 4.

---

## 1. Findings

### Finding 1 (blocker). Outcome grading is statistically meaningless at this project's scale

**Evidence.**

- The project's own expected horizon is about twenty forts:
  `learning/ledger/store.py` docstring ("At N~20 rows") and
  `docs/MEMORY-ARCHITECTURE.md` "Measurement" ("across twenty forts")
  [verified].
- Forts are sequential, one at a time (design 6.2; register 2026-09-18 "Not
  doing: seeded counterfactual reruns") [verified].
- Pace: Uniboslan read tick 209,571 in year 31 on 2026-09-28 and tick 285,626
  on 2026-10-06 (`Working.md`), about 76,000 ticks, roughly a fifth of a game
  year in a week of real time, because the fort runs only in supervised
  windows and the conductor service is disabled [verified]. It reached 20
  alive (the design's `hamlet` entry) before any roadmap existed; it is at 24
  now, with two of the last arrivals births [verified: `Working.md` line 13].
  Its next stage boundary is 50, which needs wealth-driven migration after the
  two hard-coded waves (wiki Immigration, revid 320124) [verified].
- The design's grading unit is a **stage occurrence**, horizon "the next two
  times any fort is in stage `village`" (3.4 step 6), and `measured` needs two
  clean occurrences (3.5) [verified].

**Why it fails.** Two occurrences per arm cannot separate anything. The best
possible result of a rank test comparing two old-version occurrences with two
new-version ones (perfect separation) has a one-sided p of 1/6; three against
three gives 1/20; four against four 1/70 [recalled: exact Mann-Whitney
minimum p = 1/C(2n, n)]. That is with perfect separation and no confounding,
and every occurrence here comes from a different world, embark, civilisation,
difficulty and code version, with deploys landing weekly. Worse, the design
lets changes land at up to one per game year per fort (3.5), so by the time
an entry's horizon completes, other entries have changed underneath it:
attribution is gone before the sample exists. The design admits "correlational
and slow" (0.9, 6.2) but then builds the grading machinery anyway (R4).

The dossier red team made the same finding for push versus pull (finding 13:
"cannot decide anything at our wake rate") and the notebook red team sized a
far commoner event at about 80 per arm [verified]. Stage occurrences are
orders of magnitude rarer than wakes.

**What the honest minimum viable loop is.** Three sources of evidence work at
N=1, and the design under-uses all three:

1. **Measure what the number stands for, inside one fort.** A capacity number
   is a queueing claim: "one fifth of the fort eats at once", "about a tenth
   sleeps at once" (wiki Quickstart, revid 320477, verified below). Peak
   concurrent use can be sampled every cycle within one fort, giving hundreds
   of samples, not two. `labor.unit-status` already reads each unit's
   `current_job` name (`scripts/dfhack/df-overseer-labor.lua:201`)
   [verified]; that sleeping, eating and drinking appear there as job types
   `Sleep`, `Eat`, `Drink` is [recalled], to verify. A code-built
   `utilisation` series (max and 90th percentile concurrent sleepers and
   diners per alive, per season) is the one signal that lets a per-capita
   number learn honestly from one fort.
2. **Explained deviations.** The Planner's one-line reasons are qualitative
   expert evidence, the comply-or-explain regulator's actual input. They need
   no statistics; they need someone to read them at the right time.
3. **Fort-end after-action review.** One structured review per fort (the ICC
   fixed revision cycle the design cites in 1.1 but does not apply), reading
   deviations, crises and utilisation, proposing one batch of changes. The
   new edition takes effect at the next fort, so each fort runs one edition
   and comparisons are at least edition-clean.

**Fix.** Drop stage-occurrence grading, the `measured` promotion rule and the
grade-due wake from the plan (R4 as written). Replace with: utilisation
sampling (code, small); a fort-end Elder wake; a code-built fort digest of
deviations, crises and utilisation; changes applied as an edition for the next
fort (or at the current fort's next stage boundary, decision 11). Keep a
prediction on each change, but grade it at fort end qualitatively, with
"unclear" the expected verdict and said so.

### Finding 2 (blocker). The hoop-failure exception inverts the logic and would misfire on this fort's own history

**Evidence.** Design 3.5: "a citizen died of thirst while the drink target
read met is a hoop failure for that target", allowing a one-fort generic
change with a doubled step limit; decision 9 recommends yes [verified].
Uniboslan's thirst history: founders failed to drink with water present; a
Water Source zone on the pond broke the deadlock; five of eleven thirsty
dwarves drank in a supervised test and the difference was unexplained
(register 2026-09-17, three rows); dwarves later drank at the Well with 0
drink stock (`CLAUDE.md` status) [verified].

**Why it fails.** A target is a necessary-ish condition, not a sufficient one.
If a dwarf dies of thirst while the drink target reads met, the stock level
was by construction not the binding constraint; access, labour, zone
designation or pathing was. In Van Evera's terms the evidence fails a hoop for
"meeting this target prevents thirst deaths", which nobody claimed; it is a
straw in the wind at best for "the number is too low". Raising the drink
number by 100% in response is exactly the wrong fix this fort's history
documents. It is also the sharpest edge in the design's own risk list (8).

**Fix.** A crisis with the target met never changes a **number** from one
fort. It routes to diagnosis (the retrospective court when built, the
orchestrator meanwhile) and may change a **priority order or add a missing
target** (for example "a Water Source zone or Well before the first summer"),
through the user. A one-fort numeric change is allowed only when the crisis
record shows the target's own signal was **below** its reorder level at the
crisis tick and the shortfall was unserved for a stated time (a "the number
was too low to trigger in time" case), which code can check.

### Finding 3 (blocker). The roadmap would be a third, contradictory source for stock numbers

**Evidence.**

- Doctrine `cover-target-not-yet-settable` (`doctrine/seed.yaml:960`):
  "**no cover target is set here, deliberately, and none should be invented
  elsewhere**", because resupply lead time is not computable until the
  growdur unit is settled [verified].
- Doctrine `cover-target-migration-headroom` (`:784`) already sets the
  headroom rule (50% margin, in dwarf-days, population never a formula term)
  [verified]. The roadmap's `plus` and per-stage "cover that should grow as
  the fort grows" (4.2) restate it in a different form, with population as a
  formula term.
- The Planner charter: "The Quartermaster owns orders, crops and stock par
  levels" (`agents/planner/role.md`) [verified]; `conductor/policy.yaml`
  holds the Quartermaster's `stock_target` family [verified]; the goal-tree
  design gives standing goals low and high marks "refined by learning"
  (register 2026-09-30, item 8) [verified].
- Seed 5.2: `founding` Quartermaster line "drink and meals toward ten per
  citizen (wiki)"; decision 6 puts stage-varying stock expectations in the
  roadmap [verified].

**Fix.** The roadmap holds **no stock numbers** in v1. Its boundary rule
("if the game decides it, doctrine; if we decide it, roadmap") is good but
incomplete: add "if a role already owns the number, that role's store". Room
and furniture capacity (beds, dining tables, offices) are the roadmap's;
cover, par and reorder for consumed goods stay doctrine plus the
Quartermaster. When the harvest clock is settled, revisit. Decision 6 changes
to "neither, for now".

### Finding 4 (major). The Overseer is asked to judge generic changes with no evidence and no cross-fort view

**Evidence.**

- The Overseer charter: "Rule on the reasoning. You hold no stock reads: a
  ruling that needs a fact nobody cited is a defer naming that fact", and
  "you never rule on a version" of the fort plan (`agents/overseer/role.md`
  70-85) [verified]. The design gives it no pull tool for the roadmap (2.1).
- The user's Planner authority call (register 2026-10-07, option C) kept the
  Overseer off plan versions; the roadmap is the source of every plan's
  defaults, so the Overseer would rule on the more consequential artefact
  while barred from the less consequential one [verified].
- Track record: "there is one real ruling on record" for doctrine (register
  2026-09-17) [verified]; every role runs the same model (register
  2026-10-01, DeepSeek pro) [verified], so Elder and Overseer errors are
  correlated, and the design's "until graded changes show the Overseer reviews
  them well" (3.4 step 5) can never be satisfied given finding 1.
- The Overseer is fort-scoped by charter (the fort's project manager,
  register 2026-10-01) [verified]; a roadmap change is cross-fort.

**What the Overseer can do well:** check that a proposal's cited evidence
says what the proposal claims (a reasoning check, which is its charter), and
route a source claim to the Consultant (existing fact-check) [verified].

**Fix.** The proposal must cite digest ids (deviation ids, crisis ids,
utilisation rows); the briefing renders each cited id with its value, the
cited-facts pattern the Overseer already rules on. The Overseer rules on
"does the evidence support this change", not "is this the right number". Every
accepted change is held for a user veto window before it applies (the user
digest of decision 10, with teeth), and since edition changes apply at the
next fort or stage boundary anyway (finding 1), the window costs nothing.

### Finding 5 (blocker). Stage triggers lean on reads that cannot exist during a fort

**Evidence.**

- Ledger milestones: `learning/ledger/forts.jsonl` is empty [verified]; the
  ledger is "one row per fort", and `store.append` raises if the `fort_id` is
  already present (`learning/ledger/store.py:86-100`) [verified]. A
  `{milestone: first_siege}` trigger cannot be read mid-fort from this store
  by construction, not just because nothing writes it yet. `migrant_wave` and
  `season_change` events were never emitted and their mappings were deleted
  (`conductor/cycle.py:104-107`) [verified].
- Wealth: no read anywhere (design 1.3, re-checked: no "wealth" in
  `scripts/dfhack/TOOLS.yaml`, `learning/live_signals.py`, `dfmcp/*.py`)
  [verified]. The fortress wealth figures sit in the game's plotinfo task
  structures [recalled, not checked against df-structures].
- Embark tick: not recorded (design 1.3) [verified by the design; not
  re-checked].
- `town` (5.2): entered at alive 80 "or `first_siege`"; its targets are all
  inert (owner `marshal`, disabled) [verified: `agents/ROSTER.yaml`]; military
  is deferred by the user (register 2026-10-01) [verified]. A stage whose
  every target is inert and whose second trigger is unreadable is decoration.

**Hysteresis and migrant waves.** The high-water mark is right and enough;
`regress_when` is not needed because targets are per-capita and shrink with
the fort. Two real problems remain: (a) stage entry coincides with a migrant
wave, so the plan's targets step up at the moment of most load (a hamlet
entry turns a dormitory target into 20 bedrooms at once); the adopt-only
exemption makes that instantaneous. Fine, but the shortfall watch's per-owner
in-flight ceiling (Planner red team F-7) is what keeps it from flooding the
Architect, and the R1 live check should watch for it. (b) `alive` counts
every citizen including babies (`df-overseer-vitals.lua:113-149`,
`getCitizens`) [verified]; two of Uniboslan's 24 are newborns, so per-capita
bedroom targets count babies [inferred: babies do not need a bed of their
own; recalled].

**Fix.** v1 triggers: `alive` only, high-water mark stored, no milestone or
wealth grammar, no `regress_when`. Seed three stages (`founding`, `hamlet`,
`village`); drop `town` and `city` until a threat read and a military role
exist. Where the game itself exposes the threshold, read it: the
`noble-position-room-value-and-furniture-requirements` doctrine entry is
already **verified** from a live read of `requires_population` and
`flags.HAS_MET_POP_REQ` on this fort's positions (MAYOR, CAPTAIN_OF_THE_GUARD,
DUNGEON_MASTER at 50) (`doctrine/seed.yaml:1290`) [verified]. Using the
game's own "population requirement met" flag for `village` follows the
difficulty settings automatically and is the "set intent, let the game
execute" principle applied to triggers. Consider a per-capita basis that
excludes babies (`per_adult`) as a later want-shape key, not now.

### Finding 6 (major). Seed numbers: right sources, two wrong conclusions

**Evidence, re-read live this session.**

- Dining room page: "a good general rule of thumb is to have enough tables and
  chairs to serve one fifth (1/5) of your fortress population ... More never
  hurts, but may never be necessary", and "**one table is only enough for one
  dwarf**" [verified, wiki API, current revision; the API did not return a
  revid on the parse call, the design cites 312062].
- Quickstart guide, revid 320477, "Layout": a dormitory is "often the best
  short-term solution"; "in a fort of 50 dwarves ... around five dwarves will
  be sleeping at a time ... A dormitory therefore rarely requires above ten
  beds"; "Building": "no more than 3 or 4 should be necessary" [verified].
- Siege page, revid 321023: Hamlet 20 / 5,000 / 500, Village 50, Town 80 with
  sieges; "sieges ... once its population reaches 80"; hard difficulty
  "roughly halved" triggers [verified]. Immigration, revid 320124: "adjusting
  the population caps do not adjust population requirements (such as 80 to get
  a king). Such requirements can be modified in the game's advanced difficulty
  settings" [verified].
- Our zone tool: the DiningHall's defining furniture is **Table**
  (`scripts/dfhack/df-overseer-zone.lua:242`); the default plan's
  `dining_seats` counts **Chair** (`plans/default-v1.yaml`) [verified].

**Where the design goes wrong.**

1. **The dormitory is argued from the wrong evidence.** Design 5.2 item 2
   says "the live fort's stall was exactly a bedroom it could not furnish".
   The stall was that no BED item had ever existed and nothing ordered one
   (`evals/live/2026-10-07-stuck-bed/README.md` answer 2) [verified]. A
   dormitory needs the same beds. The dormitory is still the wiki's advice
   and fine as a founding target, but it fixes nothing that happened here, and
   the baseline claim built on it (6.2) should go.
2. **The dormitory number should be per-capita, as the wiki states it**:
   about a tenth sleep at once, so `{per_alive: 0.1, min: 4, max: 10}` rather
   than the flat `{plus: 4, max: 6}`.
3. **Dining counts the wrong furniture.** One table serves one diner; the
   zone's defining furniture is the table. Count `zones."DiningHall".furniture."Table"`
   at `{per_alive: 0.2, min: 2}`, not chairs (chairs per table are a
   furnishing detail for the blueprint). Rename the target `dining_tables`.
4. **"No wealth-making before a militia"** (seed `founding` Overseer line)
   collides with the user's "military deferred" (register 2026-10-01) and
   with the wiki's own mechanics: migration after the first two waves needs
   created wealth (Immigration, revid 320124), the mayor's rooms need room
   value 500 (verified doctrine above), so the expectation would freeze the
   fort below 50 for as long as military stays deferred. The wiki's advice is
   about "too much wealth too fast" [verified, Quickstart]. Drop it, or
   reword as "no wealth-only work (gold, engraving for its own sake) while a
   survival priority is unmet".

**Are 20/50/80 right for v53?** 20 and 50 are right for normal difficulty and
50 is already verified live for this fort's positions; 80 matters only for
sieges and the monarch, which v1 should not seed. Difficulty moves the siege
and title triggers but not the position `requires_population`, which the
Immigration page says is set in advanced difficulty [verified, wiki]; read
the live flag and the question answers itself per fort.

### Finding 7 (major). Over-engineering: cut list for the first version

Each line: what, why it can go, what replaces it.

| Part | Cut? | Reason | Replacement |
|---|---|---|---|
| Cross-fort `roadmap.sqlite3`, export to repo, drift-check line (1.5 C) | **cut** | A handful of changes per fort; the standing deploy grant (memory, 2026-10-05) means an accepted change can be committed and deployed the same day; a second store creates a new drift class the project already pays for elsewhere | Repo file deployed like `plans/` (the manifest already ships `plans/`, `Working.md` 2026-10-08) [verified]; git history is the public record |
| New action class `applied_on_ruling` (3.4 step 4) | **cut** | `ruling_only` already exists for exactly this shape (`dfqueue/action_tools.yaml`, `plan_change`) [verified] | `roadmap_change` as `ruling_only`; a maintainer apply script runs the validator and commits, the same step doctrine revisions need (register 2026-09-17, "applied by a mechanical step") and which is not built for doctrine either: build it once for both |
| Oscillation detector (3.5) | **cut** | At one edition per fort the whole version list fits on a screen | The user digest and `git log` |
| Step limit, rate limits, entry locks (3.5) | **keep one** | The step limit is a pure function and cheap; the rest regulates a rate that cannot occur | Step limit as a validator flag; "at most one open `roadmap_change`" |
| `measured` promotion, computed evidence block, `refuted` (1.2, 3.5) | **cut** | Finding 1 | Every entry `prior` with sources; utilisation rows cited by id when they exist |
| Stage-occurrence grading, `roadmap_grade_due` wake (R4) | **cut** | Finding 1 | Fort-end qualitative review |
| `roadmap_deviation_pattern` wake, K=3 | **cut** | Rare and confounded; reasons are read at fort end anyway | Deviations listed in the fort digest |
| Quartermaster slice (2.1) | **cut** | Finding 3: no stock numbers in the roadmap | none |
| Overseer `roadmap_refs` field and lens measurement (2.2, 2.4) | **cut** | Slice waste needs about 80 wakes per arm (dossier red team 12, 13) [verified]; the Overseer's season goal that would pick among priorities is not built (register 2026-10-01) [verified] | One briefing line: stage id, summary, next stage at N |
| Closed priority vocabulary file (1.4) | **defer** | Nothing consumes priorities yet; plan targets are already in priority order (F-7) [verified: `plans/default-v1.yaml` header] | Stage `summary` text |
| Per-role expectations block (1.2) | **cut** | Prose lines with ids are the "fixed per-role lists" the user rejected for briefings (register 2026-10-05) and add to the compliance budget | none |
| Slice-miss and slice-waste metrics in `wake_metrics` (2.4) | **cut** | Same as the lens; additive keys are cheap but unreadable at our N | none |
| `regress_when` (1.3) | **cut** | Per-capita targets shrink with the fort | High-water mark only |
| Milestone and wealth trigger grammar (1.3) | **cut** | Finding 5 | `alive` plus the game's own flags |
| `roadmap_stage_entered` Planner wake, adopt-only exemption (4.1) | **keep** | Small, code-checkable, and the place the roadmap actually changes behaviour | as designed |
| `game_version` field, doctrine-format sources, coordinate refusal (1.2, 1.6) | **keep** | Cheap and already-proven patterns | as designed |

### Finding 8 (major). Baselines measure plumbing, not standards

**Evidence.** Design 6.2 names the pre-roadmap baseline: the bedroom stall of
2026-10-05 to 10-07, the starvation death and the thirst crisis of
2026-09-19 [verified rows]. The bedroom stall was a missing order (finding 6);
the thirst history was access and zones (finding 2). None was caused by a
wrong number.

**Why it matters.** Any improvement after the roadmap lands will coincide with
derived-input ownership (Planner red team F-1), the stuck-job watch, the
manager fix (register 2026-10-08) and other plumbing. Crediting the roadmap
with them is the post-hoc story `docs/MEMORY-ARCHITECTURE.md` warns about
[verified].

**Fix.** State the baseline as "no roadmap-attributable failure observed" and
measure the roadmap only on what it controls: deviation count and reasons per
entry, and (once built) utilisation against the target ratio. Report the
Planner's rounds and reads per review before and after the slice as the one
effort measure (a paired same-state comparison, dossier red team 13's method,
if anyone wants a number).

### Finding 9 (minor). The cache placement claim does nothing; the cost is small either way

**Evidence.** The live cache study found the shared prefix is the tool list
plus the system message; the user message begins with a minute-resolution
timestamp and the briefing's first line carries the game tick
(`evals/live/2026-10-07-cache-miss-cause/README.md`;
`conductor/briefing.py:307`) [verified]. Placing the slice at "the
season-stable head of the briefing" (2.1) therefore buys no cross-run cache.

**Fix.** Either leave it in the briefing and stop claiming a cache benefit (a
few hundred uncached tokens per wake, negligible), or put the stage block into
the role's system workspace, which breaks the cached prefix once per stage
change (rare). The first is simpler.

### Finding 10 (minor). The Elder can pick predictions it cannot miss

**Evidence.** The proposal's prediction names "an outcome measure from 6.1"
chosen by the Elder (3.4 step 6); `unclear` is a valid grade (3.4); a hit wakes
nobody [verified].

**Why it matters.** Lowering a target and predicting "met within 40 days"
grades a hit by construction; a high `unclear` rate hides misses. The design
names the zero-target trap for its primary metric (6.2) but not for the
Elder's own predictions.

**Fix.** Code fixes the outcome measure by change direction: a lowered number
must predict "no rise in the matching crisis family and utilisation stays
below the new ratio"; a raised one "utilisation above the old ratio was
observed". Report the `unclear` share beside the hit rate.

### Finding 11 (minor). One-role merge with the learning role creates a slow gate

**Evidence.** The 2026-09-17 rows: any role's doctrinal revision "must
reference a discussion record" with the learning role, enforced by the queue
[verified]. The Elder wakes two to six times a game year (3.3) [inferred by
the design].

**Fix.** Agree with one role, but the discussion-record gate needs the Elder
to wake on an `ask` addressed to it (the design has it as an answerer, good)
with a stated answer time; otherwise doctrine revisions queue behind a rarely
awake role. Note it in R5.

### Finding 12 (minor). Small drifts and claims

- `agents/planner/role.md` still says "Not enabled yet" while the roster has
  it enabled [verified]; the design found this too. Fix before any charter
  edit for the roadmap.
- "Planner 13 tools" is from `docs/STATE.md`'s hand-edited note, not a
  regenerated count [verified: `docs/STATE.md:54`].
- `doctrine.get` is described as "Consultant only today"; the Architect's
  `tools.yaml` carries a withheld entry for it [verified: `agents/architect/tools.yaml:446`].
  Harmless, but say "granted to the Consultant only".
- The design says stage boundaries "can be verified from this install" as new
  work; 50 is already verified doctrine (finding 5) [verified].

---

## 2. Checked and found sound

- **Elder versus Planner split.** The incentive argument (a Planner owning the
  standard sets it to whatever it just did) is right and cites the ladder
  research correctly [verified: `research/2026-09-16-opening-priority-ladder.md`].
- **Elder versus Chronicler split.** The Chronicler's charter forbids
  influencing the fort [verified: `agents/chronicler/role.md`].
- **Targets reuse the plan shape exactly.** `want_units`,
  `want_mapping_problems` and `check_signal` in `dfqueue/plan.py` accept the
  roadmap's targets with no translation [verified]; `zones."KIND".furniture."F"`
  works for any kind, including `Dormitory`, which is a known zone kind
  (`learning/live_signals.py:154-164`, `df-overseer-zone.lua:247`) [verified].
- **Comply or explain, flag not refuse.** Consistent with option (b)
  (register 2026-10-07) [verified]; the season guardrail and `fix_only`
  exemption are as the design describes (`dfqueue/plan.py:472-520`)
  [verified]. The adopt-only exemption is the same shape.
- **"Generic by rule" and the naming collision with `ROADMAP.md`.** Right.
- **The design's own honesty** about one-fort-at-a-time limits (0.9, 6.2, 9)
  is good; the problem is that the build stages do not follow from it.

---

## 3. The smallest version worth building first

**V1 (replaces R0 to R2):**

1. `fort_roadmap/seed-v1.yaml`: stages `founding`, `hamlet`, `village`; per
   stage a `summary` and **targets only**, in the plan target shape, each with
   doctrine-format sources and a rationale; `game_version`. Seed targets:
   `founding` dormitory beds `{per_alive: 0.1, min: 4, max: 10}`, dining
   tables `{per_alive: 0.2, min: 2}`; `hamlet` bedrooms `{per_alive: 1.0}`
   reorder gap 2 (marked "project"), dining tables as founding with `min: 4`;
   `village` bedrooms `{per_alive: 1.0, plus: 2}`, dining tables
   `{per_alive: 0.2}`. No stock numbers, no expectations, no priorities file.
2. A validator: plan-shape checks reused, coordinate and fort-name refusal, the
   step limit as a flag.
3. Stage computation in code: `alive` with a stored high-water mark, and a
   cross-check against the game's own `HAS_MET_POP_REQ` for the population-50
   positions (a read that already exists in substance). The R0 live check
   becomes: confirm the flag read on Uniboslan (expected false at 24).
4. Planner: the slice (stage, its targets, next stage at N), `roadmap_ref` on
   targets, deviation computed by code and flagged without a reason, the
   `roadmap_stage_entered` wake with adopt-only exemption;
   `plans/default-v1.yaml` retired in the same commit.
5. Overseer: one briefing line (stage, summary). Nothing else.
6. Utilisation sampling, if the job-name read holds: per cycle, concurrent
   `Sleep` and `Eat` counts per alive, kept as a series. This is the learning
   signal; it costs one existing read per cycle.

**V2, the Elder (replaces R3 to R4):** a one-shot role, woken at fort end, on
an ask addressed to it, or on user guidance tagged progression. It reads a
code-built fort digest (deviations with reasons, crises, utilisation, stage
times) and files at most one `roadmap_change` (`ruling_only`) with cited
digest ids and a prediction whose measure code fixes by direction. The
Overseer rules on whether the evidence supports it; the user gets a veto
window; the shared validator-and-commit apply step writes `seed-v<N+1>`. The
edition applies at the next fort (decision 11). Tools: `roadmap.read`,
`plan.read`, `series.*`, `doctrine.get`, `queue.propose/pass/ask/my_filings`.

This honours each part of the user's intent: numbers come from a roadmap
rather than per fort; it adjusts; its own agent manages it; the Overseer
reviews; other roles get the aspect they use. What it drops is the claim
that it can measure its own improvement statistically, which nothing in this
project can.

---

## 4. The ten decisions, and two missing ones

1. **Name: Elder.** Agree.
2. **Elder and the learning role, one role.** Agree, with finding 11's
   answer-time condition for the doctrine discussion gate at R5.
3. **Overseer: roadmap reviewer and general reviewer.** Amend: the second
   reading is already decided (register 2026-10-05, "the Overseer only
   rules"), so the only new decision is the first. Agree it reviews roadmap
   changes, scoped to "does the cited evidence support the change", with a
   user veto window (finding 4).
4. **Server store, exported and drift-checked.** Disagree. Repo file deployed
   like `plans/`, changes as `ruling_only` proposals applied by a shared
   validator-and-commit step; revisit a server store only if accepted changes
   measurably wait on the commit (finding 7).
5. **R0 to R2 first, R3 when the first stage completes.** Amend: build V1
   (section 3), which is R0 and R1 trimmed and almost none of R2. The Elder's
   trigger is fort end, an ask or user guidance, not a stage completion:
   Uniboslan's next completion is at 50, which may be a long way off (finding
   1).
6. **Stage-varying stock expectations in the roadmap.** Disagree: neither, for
   now; doctrine forbids inventing a cover target until the harvest clock is
   settled (finding 3).
7. **Seed: dining one fifth, dormitory at founding.** Agree with both, amended:
   count tables not chairs; dormitory per-capita at a tenth with a floor of 4;
   do not cite the bed stall as support (finding 6). Drop the
   wealth-before-militia line.
8. **Unexplained deviations flagged, not refused.** Agree.
9. **One-fort hoop exception may change the generic roadmap.** Disagree: a
   crisis with the target met never changes a number from one fort; it routes
   to diagnosis and may change an order or add a target through the user
   (finding 2).
10. **Applied changes in the user digest.** Agree, and make it a veto window,
    not a notice.
11. **New: when does an accepted change take effect?** Recommend: at the next
    fort (an edition per fort), or at the current fort's next stage boundary
    for user guidance. Mid-stage changes confound the only comparison
    available.
12. **New: where do stage thresholds come from?** Recommend: the game's own
    flags where one exists (`HAS_MET_POP_REQ`), `alive` otherwise; never
    milestone or wealth triggers until a live read exists.

---

## 5. Not verified

- That sleeping, eating and drinking show as `current_job` types `Sleep`,
  `Eat`, `Drink` in `labor.unit-status`: recalled from DF's job types, not
  read live (no VM access). The utilisation recommendation depends on it.
- That babies are counted by `getCitizens(true)` and that the game's own
  title population counts them: recalled.
- Exact-test minimum p values: recalled arithmetic (1/C(2n, n)), not
  computed with a library.
- The location of fortress wealth fields in the game's data: recalled, not
  checked against df-structures.
- The Dining room page revid: the API parse call returned the text but no
  revid; the quoted text was read this session.
- Cost and wake-rate figures for the Elder: the design's inference, not
  re-derived.
