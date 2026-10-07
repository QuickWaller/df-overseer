# The fort roadmap and the role that keeps it

Date: 2026-10-08. Design only. Opus design pass for the orchestrator. No VM
touched, no fort read, no code changed. Brief: the user's calls of
2026-10-08 (register row "A fort roadmap, owned by its own agent, sets the
Planner's numbers; slices go to other roles; the Overseer becomes the
reviewer of proposals"). A red team comes before anything is built.

Provenance tags used throughout:

- **[verified]** read this session in repo code, data or a register row, at
  the cited path.
- **[prior]** a current DF wiki page (main namespace, which documents the
  current release) or a community source, read this session with the
  revision id given; describes game behaviour this project has not measured.
- **[summary]** only a search engine's summary was seen, not the page.
- **[recalled]** the author's own knowledge, not fetched this session.
- **[inferred]** follows from verified pieces; nobody has watched it happen.
- **[proposed]** this design's choice.

---

## 0. The answer, up front

1. **The roadmap is fort-agnostic data: an ordered list of stages, each
   entered on measured milestones (population, years since embark, created
   wealth, first threat), each carrying targets in the plan's own want shape
   `{per_alive, plus, min, max}`, an ordered list of priorities, and
   per-role expectations.** Every entry carries a rationale, sources in
   doctrine's provenance format, and a confidence of `prior` (community or
   project guess) or `measured` (this project's outcomes back it), plus an
   evidence block that **code** computes, never the author. [proposed]
2. **It lives in a cross-fort store on the MCP server, not in a fort's
   queue database**, seeded from a committed repo file, versioned
   append-only, and exported back to the repo so the public record keeps
   every version. Generic by rule: no coordinates, landmark names or fort
   names, and only fort-agnostic signal families. [proposed]
3. **The Planner applies it, "comply or explain".** Each plan target names
   the roadmap entry it comes from; where the Planner's want differs, code
   computes the deviation and the Planner gives a one-line reason. The
   Planner keeps full say over its own plan (user, 2026-10-08); the roadmap
   is a default, never a constraint. The default plan file stops being a
   second source of numbers: version 1 of a plan is the current stage's
   roadmap targets. [proposed]
4. **Per-role slices are computed by code** and pushed in briefings: the
   Planner gets the current stage's targets and the next stage's entry
   conditions; the Overseer gets the stage's priorities as a **review
   lens**; the Quartermaster gets stock and industry expectations; the
   Architect gets **nothing by default**, because the plan already carries
   the roadmap to it, and a second copy would be slice waste. Logistics
   later. Measured by slice miss and slice waste on entry ids. [proposed]
5. **The new role: the Elder** (name is a user decision, section 10). It
   owns the roadmap and nothing in the fort. It wakes on slow,
   evidence-shaped signals the Planner never sees: a stage completed, a
   deviation pattern repeating, a past roadmap change's grade falling due,
   a fort ending, user guidance on progression. It proposes
   `roadmap_change` records with a prediction; **the Overseer reviews them**
   (accept, reject, defer, amend); the server applies an accepted change
   mechanically through the validator; code grades it at a horizon counted
   in stage occurrences, not ticks. [proposed]
6. **Splitting test, honestly applied:** the Elder and the Planner are two
   roles (different wakes, different tools, different reasoning: one
   generalises across forts, one fits this fort). **The Elder and the
   learning role floated on 2026-09-17 are one role**: same evidence reads,
   same wake shape, same judgment ("is this generic rule wrong, given
   outcomes?"); the roadmap is simply the learning role's first artifact,
   and doctrine revisions join it in a later stage if the user agrees. **The
   Chronicler stays separate**: its charter forbids influencing the fort,
   and the Elder exists to influence it. [proposed]
7. **Guards against one fort's noise:** a deviation stays local to the fort
   until it repeats; a generic change from a single fort is allowed only on
   a hoop-test failure (a death or crisis with the entry's target met) or
   user guidance; numeric changes are step-limited per version; one roadmap
   version per game year per fort, at most three entries per change; an
   oscillation detector; and every applied change in the user digest.
   [proposed]
8. **Seeding v1 from community sources finds two real disagreements with
   today's default plan**: the wiki's quickstart recommends a dormitory of
   3 to 4 beds early, not a bedroom per citizen, and the wiki's dining room
   page puts tables and chairs at **one fifth** of the population, against
   the default plan's one per citizen [prior, revids in section 5]. The
   stage boundaries themselves come from game mechanics the wiki documents
   (moods and the first titles at 20, a mayor at 50, sieges and megabeasts
   at 80) and **can be verified from this install's raws and difficulty
   settings**, which is a concrete first live check. No community source
   publishes a staged, per-capita progression table; that part is ours.
9. **Measured** by time from stage entry to each stage target met, stalls,
   crises and deaths per stage, unexplained and repeated deviations, the
   graded hit rate of roadmap changes, and how often a later version walks
   an entry back. Honest limit: with one fort at a time, every
   "improvement" is correlational and slow; the design says so rather than
   promising an A/B it cannot run.
10. **Stages R0 to R5**, each with a live check; R0 and R1 need no new role.
    Ten user decisions, one per line, with a recommendation (section 10).

Two drifts found while reading, for the orchestrator (not fixed here, this
is a design-only task): `agents/planner/role.md` still says "Not enabled
yet", while `agents/ROSTER.yaml` has `enabled: true` and `Working.md`
records the Planner live with plan v1 filed on 2026-10-08 [verified]; and
the word "roadmap" already names the repo's own `ROADMAP.md`, which
`docs/AGENT-ARCHITECTURE.md` §10 says vents and friction "feed" [verified],
so code must never use the bare word (section 1.6).

---

## 1. The roadmap as data

### 1.1 What it is, domain-neutrally

A **generic, staged reference standard that each instance adopts with local
amendments, and whose amendments feed the next edition.** Several fields
own that problem; their shared lessons shape the schema.

| Field | Their artefact | What transfers | Tag |
|---|---|---|---|
| Building codes | A model code (the ICC's I-Codes) revised on a fixed cycle: anyone submits a code change proposal, a committee hears proponents and opponents and votes, public comment follows, a final action hearing decides; jurisdictions then adopt it with local amendments | Proposals from anyone, one reviewer body, a fixed revision cadence, local amendment is normal and expected | [summary] NFSA "Understanding the Model Code Development Process"; NAMBA "Understanding the ICC Model Building Code Development Process" |
| Corporate governance | "Comply or explain" (the UK Corporate Governance Code): a company may depart from a provision if it explains why | The Planner's deviations: allowed, but explained, and the explanations are the regulator's evidence on whether a provision is wrong | [recalled] |
| Clinical guidelines | Living guidelines (WHO's for COVID-19 were the visible case) graded with GRADE certainty levels; recommendations update as evidence accrues, each carrying its certainty | Per-entry confidence separate from the recommendation; "low certainty" is stated, not hidden; updates are triggered by evidence, not by calendar alone | [recalled] |
| Park and facility planning | Fixed national per-capita standards (the old "acres per 1,000 residents") gave way to locally benchmarked levels of service | A per-capita number is a starting prior; a population-only rule ignores local conditions; keep the generic number but expect local variance | [recalled] |
| Product roadmaps | Now / Next / Later, outcome-based roadmaps (this repo's own `ROADMAP.md` uses the buckets) | Stages carry outcomes and priorities, not tasks; dates are soft, triggers are the real gate | [verified: `ROADMAP.md` convention in `CLAUDE.md`] |
| Capacity planning | Order-up-to and reorder bands, headroom (N+1, N+2) planned ahead of growth | The want shape already is this (`{per_alive, plus, min, max}`, reorder gap): `plus` is headroom for the next migrant wave | [verified: `dfqueue/plan.py` `want_units`] |
| Curriculum design | Staged curricula with entry criteria per stage (mastery, not seat time); "backward design" from outcomes | Stage entry on a measured milestone, not on elapsed time alone; each stage states what it is for | [recalled] |
| Runbooks and post-incident review | Blameless postmortems produce action items that change the runbook | A crisis is the strongest single piece of evidence, and it changes the generic artefact through a reviewed change, not by the responder editing it mid-incident | [recalled] |
| RTS build orders | Bots pre-select a build order and rarely switch; experts switch between orders whose relationships they know | Stages are a small, pre-enumerated set; the Planner chooses within known options, it does not improvise a new progression per fort | [verified: `research/2026-09-16-opening-priority-ladder.md` §1.1, itself moderate confidence] |
| Learning policies from outcomes | Conservative policy updates (trust-region and clipped updates in reinforcement learning); off-policy evaluation from logs is weak without a behaviour model | Bound each change's size; do not claim a counterfactual from one run (register 2026-09-18 already rejected seeded reruns) | [recalled] |

The strongest single lesson, repeated in the ladder research and here:
**every field that does this keeps authoring the generic standard separate
from applying it to one case** (the ICC committee is not the city building
department; the guideline panel is not the treating doctor). That is the
argument for the Elder being a role apart from the Planner (section 3.6).

### 1.2 Schema

Field names are the proposal; the shape is the decision.

```yaml
kind: fort_roadmap
version: 4                        # server-assigned, integer, append-only
supersedes: 3
change_id: roadmap_change-0007    # the accepted proposal that produced it (null for v1)
ruling_id: ruling-0123            # the Overseer's accept or amend (null for v1)
reason: "Dining seats at one per citizen stalled in two stages; one fifth matches the wiki and our measured queueing"
game_version: "53.16"             # the install the roadmap is tuned for; a change of DF version flags every measured entry for re-check

stages:                           # ORDER IS PROGRESSION
  - id: founding
    summary: "Shelter, drink, food, workshops; survive to the first migrant waves"
    enter_when: {always: true}    # the first stage
    regress_when: null
    priorities:                   # ORDER IS PRIORITY; ids from a closed vocabulary (1.4)
      - {id: drink_secure, note: "Drink before food: a dwarf dies of thirst first"}
      - {id: food_secure}
      - {id: shelter_and_storage}
      - {id: core_workshops}
      - {id: sleeping_space}
    targets:                      # same shape the Planner files (agents/planner/role.md step 5)
      - id: beds_dormitory
        signal: 'zones."Dormitory".furniture."Bed"'
        want: {plus: 4, max: 6}
        reorder_gap: 1
        owner: architect
        confidence: prior
        sources: [{kind: wiki, ref: "Quickstart guide, Bedrooms", revid: 320477, describes: "v50+", read: opened, accessed: 2026-10-08}]
        rationale: "A dormitory of 3 to 4 beds serves a young fort; individual rooms come later"
    expectations:                 # per-role lines, each with its own id, confidence and sources
      quartermaster:
        - {id: drink_cover, text: "Drink and prepared meals around ten per citizen is plenty", confidence: prior, sources: [...]}
      overseer:
        - {id: no_wealth_before_defence, text: "Defer wealth-making work (gold, engraving) until a militia exists", confidence: prior, sources: [...]}
  - id: hamlet
    enter_when: {any: [{signal: alive, gte: 20}]}
    ...

evidence:                         # COMPUTED by code at read time, never authored; see 6.1
  # per entry id: {forts_used, stage_occurrences, met_count, median_days_to_met,
  #                stalled_count, deviations: {up, down, unexplained}, crises_with_target_met,
  #                graded_changes: {hit, miss}}
```

Notes on the shape:

- **Targets reuse the plan's target shape exactly** (signal, want, one of
  `reorder` or `reorder_gap`, owner, `max_in_flight`, note), so the Planner
  copies an entry into its plan with no translation and the same
  `dfqueue/plan.py` checks apply. [verified: shape in `dfqueue/plan.py`
  `want_mapping_problems`, `check_target`; proposed: reuse]
- **Expectations are lines, not structure**, for roles whose own numbers
  live elsewhere (the Quartermaster's `stock_target`, the Overseer's
  rulings). A line has an id so slice measurement works (2.4). Where an
  expectation is really a number a role should apply (a cover-day level),
  it should become a target with a signal instead, once a signal exists.
- **Provenance per entry uses doctrine's source format** (`kind`, `ref`,
  `describes`, `read`, `accessed`, and the wiki citation fields), so
  `doctrine/wiki_check.py` can flag a roadmap entry whose cited wiki
  revision moved, with no new checker. [verified: field list in
  `doctrine/seed.yaml` header and `doctrine/validate.py`; proposed: reuse]
- **Confidence is `prior | measured | refuted`**, not doctrine's `verified`.
  A roadmap number is policy, not a game fact; nothing in the game data can
  "verify" that 0.2 chairs per citizen is right. `measured` means this
  project's outcomes support it (rule in 3.5). `refuted` entries are kept,
  like doctrine's, so the mistake is not remade.
- **A stage's game-fact boundary cites doctrine**, it does not restate it:
  "sieges begin at 80" becomes a doctrine entry (verifiable from game data,
  section 5.3), and the `town` stage's `enter_when` cites that doctrine id.

### 1.3 Milestone triggers

`enter_when` is a small closed grammar over **fort-agnostic** signals:
`{any: [...]}` or `{all: [...]}` of `{signal, gte | lte}`, `{milestone:
KIND}` (a ledger milestone has happened), or `{always: true}`.

| Trigger family | Signal | Exists today? |
|---|---|---|
| Population | `alive` (vitals) | yes [verified: plan `per: alive`, `vitals.summary`] |
| Years since embark | game tick minus embark tick | tick yes; **embark tick needs recording once per fort** [inferred: no embark-tick field found] |
| Created and exported wealth | the fort's wealth figures | **no read exists** (no "wealth" in `scripts/dfhack/TOOLS.yaml` or `learning/live_signals.py`) [verified]; a small read is a gap for R1 |
| Threats | `{milestone: first_siege}` and the other ledger kinds | the vocabulary exists in `learning/ledger/schema.py` `MILESTONE_KIND` (`first_migrant_wave`, `first_siege`, `caverns_breached`, `monarch_arrived`, ...) [verified]; nothing writes milestones during a live fort yet (`learning/ledger/forts.jsonl` is empty) [verified] |
| Settings | the fort's population cap and difficulty | **no read**; matters because the game's own thresholds move with difficulty settings [prior: Siege and Immigration pages] |

**Stage computation is code** (`roadmap.status`): the current stage is the
**last stage, in order, whose `enter_when` has ever held** in this fort
(monotone, with the high-water mark stored), so a population dip from 21 to
19 after a death does not flap the fort back to `founding`. A stage may
declare `regress_when` (for example, alive below half the stage's entry
level for a whole season) for real collapse; code holds hysteresis, the
model never decides which stage the fort is in. An unresolvable trigger
(the wealth read before it exists) is **flagged inert**, in line with the
Planner's option (b) (register 2026-10-07), and the stage is reached by its
other branch if it has one; the `town` stage carries population as a
second branch for exactly this reason.

### 1.4 Priorities: a closed vocabulary

Priority ids come from a closed list (data, `fort_roadmap/priorities.yaml`)
so that rulings can cite them and slice measurement can count them. Starting
list, from the seed survey: `drink_secure`, `food_secure`,
`shelter_and_storage`, `core_workshops`, `sleeping_space`, `dining`,
`hygiene_and_burial` (refuse, tombs), `administration` (offices, nobles'
rooms), `health` (hospital, well), `defence` (militia, entrance),
`trade`, `moods_ready` (a workshop of each kind a mood may need),
`religion_and_leisure` (temple, tavern, library), `industry_metal`,
`caverns`. Adding one is a data line. A priority is never an action; the
Overseer weighs proposals against it, and the Overseer's own season goal
(register 2026-10-01) picks among them.

### 1.5 Versioning and where it lives

| Option | Pros | Cons |
|---|---|---|
| A. Repo file only; changes land by a human commit | git history, public by default, reviewed | an accepted change waits for a person; the Elder's loop stops whenever nobody is at the desk |
| B. Fort queue database (`<fort>.sqlite3`) | one store, existing records | **dies with the fort**; the roadmap is cross-fort by definition |
| **C. Cross-fort store on the MCP server, seeded from the repo, exported back (recommended)** | applies without a human, survives forts, the public copy still exists | one more store; a repo-vs-server drift to manage |

Option C in detail [proposed]:

- **Store:** `roadmap.sqlite3` beside the fort stores on VM 103, append-only
  `fort_roadmap` versions (full documents), plus an `applied` log. Same
  write discipline as `dfmcp/gotchas_store.py`: refuses to run on a missing
  or wrong-schema file, created by an explicit `init`, `BEGIN IMMEDIATE`
  for ids [verified pattern: that module's docstring].
- **Seed:** `fort_roadmap/seed-v1.yaml` in the repo, loaded as version 1 by
  `init`. After that the repo file is **never edited by hand**; every later
  version arrives from the store.
- **Export:** each applied version is written as
  `fort_roadmap/versions/v<N>.yaml` into the stream publisher's output and
  picked up by the orchestrator's next session, which commits it; the
  daily drift check (`df-overseer-drift-check`, `Working.md`) gains one
  line: "server roadmap version ahead of repo". Which side is stale is then
  obvious and never ambiguous (memory `drift-resolution-case-by-case`).
- **Fort record:** every `fort_plan` version stamps the `roadmap_version`
  it read, so a plan, its deviations and its outcomes always join to the
  exact roadmap that was in force.
- **Game version:** a roadmap version names the DF version it was tuned on;
  a different install flags every `measured` entry as "measured on another
  version", the same trap doctrine's `describes` field exists for.

### 1.6 Generic by rule, and naming

- **Refused at filing, always** (the only refusals; everything else is a
  flag, matching the Planner's option b): a coordinate (the existing
  `_COORDINATE_PATTERN`), a landmark or `anchor` field, a signal family
  that names a fort entity (`landmark`, `site`, orders by id), and any
  string matching a known fort or site name. This is the public-repo and
  no-map commitment, the same as `blueprints/templates` ("no fort
  coordinates, no landmark names", `CLAUDE.md`) [verified rule].
- **Kinds validated, flagged not refused:** zone and building kind tokens
  checked against `zone.list-kinds` and `building.list-kinds`, as plan
  targets are [verified: `dfqueue/plan.py` `check_signal`].
- **Naming.** Record kind `fort_roadmap`, directory `fort_roadmap/`, tools
  `roadmap.*`, and in prose always "fort roadmap". The bare word "roadmap"
  in code or charters would collide with the repo's `ROADMAP.md`, which
  `docs/AGENT-ARCHITECTURE.md` §10 already routes vents into; the Planner
  design made the same call for `fort_plan` versus the Overseer's plan
  (F-22) [verified].

---

## 2. Per-role slices, served by code

### 2.1 What each role gets

| Role | Slice (pushed in the briefing) | Pull | Why |
|---|---|---|---|
| **Planner** | Current stage id and summary; that stage's targets with confidence and evidence counts; the next stage's `enter_when` with the current values ("alive 22, next stage at 50"); the deviations its active plan carries, each with its recorded reason | `roadmap.read` (any stage, any version, one entry's evidence) | It applies the roadmap; it wakes about four times a game year, so the pushed slice replaces several reads per wake (the dossier design's argument for the Planner, `research/2026-10-07-fort-dossier-and-crafting-search.md` §5.4) |
| **Overseer** | The **review lens**: current stage, its priorities in order, and the Overseer expectation lines; at most about 8 lines | none (its tool list is being cut toward ruling-only, register 2026-10-07 and 2026-10-06) | It rules; it needs to know what matters now, not the numbers |
| **Quartermaster** | Stock and industry expectations for the current stage (cover levels, which industries a stage expects running) and any roadmap targets it owns as input owner | `roadmap.read`, from R2 | Its decisions are what to make and how much to keep |
| **Architect** | **none by default** | none | The roadmap reaches it through the plan's targets and shortfall wakes; a direct copy duplicates the plan line it already gets. Revisit only if slice miss shows it reading the roadmap (it cannot: no pull tool) or asking about it |
| **Logistics** (later) | Flows a stage expects (from P3 flows), when P3 lands | later | |
| **Consultant** | none | `roadmap.read` on an ask about progression | It answers questions; a roadmap question is a lookup |
| **Elder** | the whole roadmap version line plus the evidence digest of its wake (section 3.3) | `roadmap.read`, evidence reads | It owns it |
| **Chronicler** (parked) | stage transitions as events | | It narrates "the fort became a village" |

Slices are computed by a `roadmap.slice(role)` function in the server and
placed by the conductor's briefing builder at the **season-stable head** of
the briefing (stage changes are rare), numbers last, the same placement the
Planner design gives the plan slice (2.5 there, F-21) [verified pattern].

### 2.2 The Overseer as reviewer

The user's "the overseer takes on a reviewing proposal type role" has two
readings, and the design supports both [proposed]:

1. **It reviews roadmap changes** (section 3.4): `roadmap_change` is a
   proposal the Overseer accepts, rejects, defers or amends, exactly like
   the doctrine revision path agreed on 2026-09-17.
2. **Its identity settles as the reviewer of every proposal**, which the
   conductor redesign is already moving toward (proposers pick exact
   actions, the Overseer only rules, the conductor executes; register
   2026-10-05). The roadmap gives that reviewer a **lens**: the stage
   priorities. Rulings gain an optional `roadmap_refs` field (priority ids
   the ruling weighed). That one field makes the lens measurable (2.4) and
   gives the Elder evidence on whether a stage's priorities are the ones
   rulings actually use.

Which reading the user meant is decision 3 in section 10; nothing in the
design changes between them except the scope of the Overseer charter edit.

### 2.3 Push versus pull per role

Push for the Planner, Overseer and Quartermaster; none for the Architect;
pull only where a role already holds or is given `roadmap.read`. This
follows the dossier design's per-role reasoning, and **its red team's
warning applies unchanged**: at our wake rate an arm comparison cannot
decide anything for a role woken a few times a year (dossier red team
finding 13; notebook red team, "about 80 per arm per stratum") [verified].
So the Planner's and Overseer's defaults stand on argument plus slice
waste, and push versus pull is not A/B tested for them.

### 2.4 Slice miss and slice waste on entry ids

The dossier red team found matching display names in reasoning text
unworkable ("Still", "Well", "Bed" are English words; transcripts are
clipped) and asked for matching on structured ids only (finding 12)
[verified]. The roadmap is built for that: every target, expectation and
priority has an id.

- **Shown ids per wake** are written by the conductor on the run row
  (`slice_ids`, ids only, publishable), as that red team asked.
- **Slice waste** per role and section: over a window of W wakes (start 10,
  the M1 window in `dfqueue/wake_metrics.py`), the share of shown ids never
  cited in a structured field: a plan target's `roadmap_ref`, a ruling's
  `roadmap_refs`, a proposal's `serves` or `cited`. A section with zero
  citations in the window is proposed for removal from that role's slice
  (a reviewed data change).
- **Slice miss**: a `roadmap.read` call naming an entry or stage that was
  in the role's slice (a **covered read**: the rendering failed) or that
  should have been (a **miss**: the slice lacked it). For the Overseer,
  which has no pull: a defer whose reason names a priority id.
- Added to `wake_metrics` as additive keys, no schema bump, the same way
  the dossier design adds its keys [verified: "additions are not breaking"
  in the `wake_metrics/1` header].

---

## 3. The new role: the Elder

### 3.1 Why "Elder"

Dwarf civilisations keep long memory across settlements, and the project's
own plan is succession forts in a persistent world (register 2026-08-25,
"the world persists; fortresses are mortal") [verified]. The role is the
one that carries experience from one fort to the next. Alternatives if the
user prefers a functional name: `curator`, `strategist` (avoided: the
architecture document already calls the Quartermaster's layer "strategy",
§4) [verified]. Code id `elder`.

### 3.2 Charter outline (for `agents/elder/role.md`)

**Kind:** advisor. **Owns the fort roadmap. Never acts on the fort, never
writes the roadmap directly.**

Owns:

- **The fort roadmap's content**: stages, triggers, targets, priorities,
  expectations, rationale and sources.
- **Proposing changes** to it, each with a reason, the evidence it rests
  on, and a prediction of what the change improves.
- **Answering roadmap questions** from other roles (`queue.ask` addressed
  to it; it is an `answerer` in the roster, as the Consultant is).
- From stage R5, if the user agrees: **patterns across doctrine misses and
  doctrine revision proposals** (the 2026-09-17 learning role), and the
  required discussion partner for other roles' doctrinal and learning
  revisions.

Does NOT own:

- **Any fort's plan.** The Planner applies the roadmap and may deviate. The
  Elder never writes a `fort_plan` and never files action proposals.
- **Whether its change is applied.** The Overseer reviews; code applies.
- **Game facts.** A threshold the game sets is doctrine; the Elder cites
  it, and proposes a doctrine change only through the doctrine path.
- **Tool knowledge.** Gotchas belong to the tools.
- **The story.** The Chronicler's.

Refusals: never cite a fort's coordinates, landmarks or names; never
change an entry on one fort's evidence unless the evidence is a hoop
failure or user guidance (3.5); never move a number further than the step
limit in one change; never propose with an empty prediction.

### 3.3 Wake signals (none of them the Planner's)

| Wake reason | When (code) | What the briefing carries |
|---|---|---|
| `roadmap_stage_review` | the fort's stage high-water mark advances (a stage **completed**), or the fort ends | the **stage outcome digest** for the stage just left (6.1) |
| `roadmap_deviation_pattern` | the same entry deviated in the same direction in K plan versions (start 3) across stages or forts, or one unexplained deviation persists a whole stage | the entry, each deviation with the Planner's reason and outcome |
| `roadmap_grade_due` | a past `roadmap_change`'s horizon arrived and code graded it a miss or unclear (a hit is recorded, nobody wakes, the existing grade-wake rule) | the change, its prediction, the measured outcome |
| `roadmap_hoop_failure` | a crisis (a death by thirst, hunger, or a siege death) while the relevant stage target read **met** | the target, its value, the crisis record |
| `ruling_on_own` | a ruling on its own change | existing mechanism |
| `answer_ready`, `ask` | an answer to its ask, or an ask addressed to it | existing |
| `roadmap_guidance` | the user's guidance tagged progression (Telegram or `GUIDANCE.md`, per `docs/MEMORY-ARCHITECTURE.md` "Human input") | the guidance text |

Not woken by: season changes, shortfalls, migrant waves, routine timers
(the user's retirement of the Architect's timer wake applies in spirit:
a timer invites a role to look for work, register 2026-10-07) [verified].
Every wake reason is edge-triggered and on the shared renotify backoff
(`renotify_max_wakes: 3`, `conductor/policy.yaml`) [verified].

Expected rate [inferred]: a fort moving through four stages in a few game
years gives four stage reviews, plus a handful of pattern and grade wakes:
on the order of two to six wakes per game year. At the Planner design's
cost figures (a review of 8 rounds or fewer is about $0.05 to $0.10,
§11 there) [verified], the role costs well under a dollar a game year.

### 3.4 How a change is proposed, reviewed, applied and graded

1. **Propose.** `roadmap.propose` (a queue proposal of type
   `roadmap_change`) carries `base_version`, a `set` of only the entries it
   changes (stage id plus entry id, the whole new entry), `reason`,
   `evidence` (ids from its digest: plan versions, grades, crisis records,
   deviation ids; at least one), `prediction` and `dry_run`. Filing-only
   checks run first (1.6); a dry run returns every flag and the step-limit
   verdict at once, the Planner's pattern [verified: `plan.write` dry run].
2. **Fact-check, when the change rests on a received source.** The
   Overseer may route it to the Consultant with `queue.ask` and a
   `proposal_id` before ruling; the existing mechanism [verified:
   `agents/overseer/role.md` "Fact-checking before ruling"].
3. **Review.** The Overseer accepts, rejects, defers or amends, with
   `roadmap_refs` naming the entries. An amendment returns to the Elder
   once, then the Overseer's ruling is final and flagged to the user: the
   doctrine amendment rule of 2026-09-17, applied unchanged [verified:
   `docs/AGENT-ARCHITECTURE.md` §4 "amend"].
4. **Apply.** On accept (or a final amend), **the server applies it in the
   same transaction as the ruling**: compose the new version from
   `base_version` plus the accepted `set`, run the validator, store, stamp
   `change_id` and `ruling_id`. A stale `base_version` (another change
   applied first) voids the ruling's application and returns it to the
   Elder. No agent holds a roadmap write tool. This is the doctrine rule
   "applied by a mechanical step that runs the validator, never by an agent
   editing text" (register 2026-09-17) [verified], and it makes
   `roadmap_change` a new action class in `dfqueue/action_tools.yaml`
   beside `routed`, `unrouted` and `ruling_only`: **`applied_on_ruling`**,
   excluded from the unexecuted list [proposed; the class pattern verified
   from the Planner design F-9].
5. **Digest.** Every applied change goes in the user digest (Board and
   Telegram), until graded changes show the Overseer reviews them well;
   doctrine's rule [verified: `docs/MEMORY-ARCHITECTURE.md`].
6. **Grade.** A change's prediction names an outcome measure from 6.1
   (for example "`dining_seats` met within 40 game days of stage entry, and
   no stall") and a **horizon in stage occurrences** ("the next two times
   any fort is in stage `village`"), because a tick horizon means nothing
   for a generic standard; code grades it when the horizon completes.
   Grades are `hit`, `miss`, `unclear` (confounded: the target was never
   tried, the fort died first), the last a valid verdict as the retrospective
   court row requires (register 2026-09-18) [verified]. Later, the court
   may review roadmap changes in batches; nothing here depends on it.

### 3.5 Guarding against one fort's noise

The risk is real: with one fort at a time, almost every observation is
N=1. `docs/MEMORY-ARCHITECTURE.md` names mis-scoping as "the main failure
mode" and rejects vote counters in favour of diagnosticity and stated error
rates [verified]. The design applies that, scaled to what one fort can give:

- **Local first.** A Planner deviation changes only that fort's plan. It
  becomes generic evidence only when it **repeats**: the same entry, the
  same direction, in K plan versions spanning at least two stages, or in
  two forts. Until then it is a "local amendment" in the ICC sense.
- **One-fort exceptions are hoop tests only.** A generic change from a
  single fort is allowed when the evidence is diagnostic in Van Evera's
  sense (the ledger's `DIAGNOSTICITY` vocabulary [verified:
  `learning/ledger/schema.py`]): a citizen died of thirst while the drink
  target read met is a hoop failure for that target, not a straw in the
  wind. The proposal must name the diagnosticity class; code checks that a
  `hoop` claim cites a crisis record with the target met at that tick.
  User guidance is the other exception.
- **Step limit.** A numeric change moves a value at most 50% of its
  current value or 1 unit (whichever is larger) per version; a hoop
  failure doubles the limit. Trust-region thinking: big moves on thin
  evidence are how a single dramatic fort rewrites the standard.
- **`measured` needs repetition.** An entry becomes `measured` only when
  code finds it met without stall or crisis in at least two stage
  occurrences, or, for a changed entry, when its change was graded `hit`.
  Code sets the field; the Elder cannot.
- **Rate limits** (policy data, start values): at most one applied roadmap
  version per game year **per fort**, plus hoop and guidance exceptions; at
  most three entries per change; at most two open `roadmap_change`
  proposals; a rejected change's entries locked for one stage occurrence.
- **Oscillation detector**: an entry moved up then down (or back) across
  three versions is flagged to the digest and the user, the Planner
  design's detector reused [verified: Planner design 3.3].
- **The embarrassment check**: count entries walked back per year. Zero
  across many forts is a warning sign, not a clean record
  (`docs/MEMORY-ARCHITECTURE.md` "Measurement") [verified].

### 3.6 The splitting test, applied honestly

The register's test (own wake signal, own tools, little shared reasoning;
used for Logistics and for zoning, register 2026-10-07 and 2026-10-08)
[verified]:

**Elder versus Planner: split.**

| Test | Planner | Elder | Verdict |
|---|---|---|---|
| Wake signal | bootstrap, season review, stalled target, plan-change ruling | stage completed, deviation pattern, grade due, hoop failure, guidance | disjoint |
| Tools | `plan.read`, `plan.write`, live fort reads (zones, vitals, nobles, sites) | `roadmap.read`, `roadmap.propose`, evidence reads (plan history, grades, series aggregates, ledger), no live fort reads beyond vitals | overlap only in `roadmap.read`, `queue.*` |
| Reasoning | fit this fort now | generalise across forts from outcomes | different, and **opposed in incentive**: a Planner that also owned the generic standard would set the standard to whatever it just did |

The last row is the decisive one, and it is the ladder research's
"authoring and execution institutionally separate" finding [verified:
`research/2026-09-16-opening-priority-ladder.md` bottom line].

**Elder versus the 2026-09-17 learning role: one role.**

| Test | Roadmap owner | Learning role (doctrine patterns) | Verdict |
|---|---|---|---|
| Wake signal | stage completed, deviation pattern, grade due | graded misses against cited doctrine, disputed entries | same shape: slow, outcome-triggered, edge-triggered; would share most wakes once roadmap entries cite doctrine |
| Tools | evidence reads, revision proposal | evidence reads, revision proposal, `queue.ask` to the Consultant | near identical |
| Reasoning | "is this generic number wrong, given outcomes?" | "is this generic rule wrong, given outcomes?" | the same judgment, scope, priors-versus-measured, diagnosticity |

Splitting them would fail all three tests. The honest counter-argument:
doctrine revisions add a second artefact and could grow the charter past
the compliance budget (perfect responses collapse well past a few dozen
simultaneous rules, `docs/AGENT-ARCHITECTURE.md` §10) [verified]. The
answer is staging, not splitting: the roadmap first (R3), doctrine duties
added at R5 only if the user agrees, with a split reconsidered if its
charter or tool count grows past the Planner's (13 tools [verified:
`Working.md` "Planner 13 tools"]).

**Elder versus Chronicler: split, not negotiable.** The Chronicler's charter
says it "must never be in a position where the story it wants to tell could
influence what the fort does" [verified: `agents/chronicler/role.md`]; the
Elder exists to influence it. They share inputs (stage transitions, fort
ends, crises), which is fine: shared reads, separate roles. The register's
2026-09-17 learning row already said "Not the chronicler" [verified].

**Elder versus code: an agent is earned, narrowly.** Principle 1 says an
agent exists only where there is judgment under uncertainty [verified].
Computing stages, deviations, evidence counts, grades and step limits is
code here. What is left (whether a pattern is a wrong standard or a local
quirk, what the new number should be, what to predict) is judgment. Until
evidence exists, there is little for the Elder to judge, which is why R0
to R2 run with no role at all (section 7); the orchestrator's earlier
"data now, agent later" recommendation survives as **build order**, while
the user's choice of an owning agent is the end state.

### 3.7 Tools: 9 at R3

| Tool | Kind | Exists? |
|---|---|---|
| `roadmap.read` | read: a version, a stage, an entry with its computed evidence, the last 8 version lines | new |
| `roadmap.evidence` | read: the digest for a stage occurrence, a deviation history, a change's grade | new (code-built, 6.1) |
| `plan.read` | read: any fort's plan history (deviations and reasons) | exists [verified: Planner tools] |
| `series.timelines` / `series.get` | read: vitals and stock history around a crisis | exist [verified: register 2026-09-19] |
| `doctrine.get` | read: the doctrine a roadmap entry cites | exists (Consultant only today) |
| `queue.propose` (type `roadmap_change`), `queue.pass`, `queue.ask`, `queue.my_filings` | write: proposal, pass, ask; read own | exist |

No fort-mutating tool, no plan write, no roadmap write. The allowlist is the
boundary (principle 8) [verified].

---

## 4. Relationships

### 4.1 With the Planner: comply or explain

- **Plan v1 of a fort is the current stage's roadmap targets**, replacing
  `plans/default-v1.yaml` as the base [proposed]. That file becomes a
  generated view of roadmap stage `founding` (or is deleted), so there is
  one source of default numbers, not two. Uniboslan already has plan v1
  filed from the default (`fort_plan-0001`, `Working.md` 2026-10-08)
  [verified]; its v2 adopts the roadmap.
- **Each plan target carries `roadmap_ref: {entry, version}`** (optional; a
  target with no ref is a fort-local target, allowed). Code compares the
  plan's want with the roadmap entry's and records a **deviation**
  (`up`, `down`, `shape`) in `plan.write`'s reply; a deviation without a
  `deviation_reason` is **flagged, not inert** (the target still runs), and
  shows as "unexplained" in the next digest [proposed]. This honours "the
  Planner can chop and change itself however": nothing is refused.
- **Stage entry is a new Planner wake reason**, `roadmap_stage_entered`,
  and a revision that only **adopts the new stage's roadmap entries
  unchanged** is exempt from the one-version-per-season rule, a
  code-checkable exemption like the fix-only exemption the user already
  accepted [verified: `fix_only` in `dfqueue/plan.py`, register 2026-10-07
  question 1]. A revision that adopts and also deviates waits for the
  season or a `plan_change`, as now.
- **The Planner suggests changes through its reasons**, not proposals. The
  2026-09-17 rule that any role may propose a doctrinal or learning
  revision "but must discuss it with the learning role first" [verified]
  is satisfied naturally: a deviation reason is the discussion record, and
  the Elder decides whether to generalise it.

### 4.2 With doctrine

| | Doctrine | Fort roadmap |
|---|---|---|
| Holds | what is true of the game, and stage-independent rules ("never cook seeds") and material-policy bands | how much the fort should have, by stage, and what matters most now |
| Status words | `prior / verified / refuted` (verified needs a 53.16 game-data or live read) | `prior / measured / refuted` (measured needs this project's outcomes) |
| Changes through | queue revision, Overseer, mechanical apply | the same |
| Read by | the Consultant (`doctrine.get`) | the Planner, Overseer, Quartermaster via slices, the Elder |

Boundary rule: **if the game decides it, it is doctrine; if we decide it,
it is roadmap.** "Sieges begin at population 80" is doctrine (and
verifiable from the install, 5.3); "have a militia of five before 80" is
roadmap. A roadmap entry resting on a game fact cites the doctrine id.
**One live overlap to settle:** stock cover levels. Doctrine holds
"material policy targets: par levels, cover days" (register 2026-09-18)
[verified], and the Quartermaster holds `STOCK_TARGET` alerts in
`conductor/policy.yaml` [verified]. Recommendation: stage-independent
bands stay in doctrine; **stage-varying** expectations (cover that should
grow as the fort grows) go in the roadmap's Quartermaster lines. Decision
6 in section 10.

### 4.3 With gotchas

None in content. Gotchas are tool behaviour, per tool, per fort database,
proposed and outcome-tracked by the roles that hit them [verified:
`dfmcp/gotchas_store.py` docstring]. The roadmap borrows only the pattern
(append-only store, explicit `init`, fails loudly). If the Elder ever
believes a stall was a tool fault, that is a vent or a gotcha, routed to
`ROADMAP.md` maintenance, never a roadmap change
(`docs/AGENT-ARCHITECTURE.md` §10 "Vent and friction") [verified].

### 4.4 With the opening ladder and the season goal

- The 2026-09-16 ladder research proposed `playbooks/opening-ladder.yaml`
  (not built) [verified]. The roadmap's `founding` stage priorities are
  that ladder, generalised to all stages; the ladder file should not be
  built separately. Its "branches where genuine method choice exists"
  (three ways to found a farm) stay where the research put them: methods,
  inside a stage, chosen by the role that acts.
- The Overseer's season goal (register 2026-10-01, not built) chooses
  among the stage's priorities; its scored result per season is evidence
  for the Elder's stage digest.

---

## 5. Seeding v1

### 5.1 What the community actually publishes

Read this session through the wiki's own API, raw wikitext, main namespace
(the current release). Each **[prior]**; revid and timestamp as served on
2026-10-08. Note: the consultant's offline mirror holds edits back one
week, so it would serve older revisions of Siege and Ambush (both edited
2026-10-07) than the ones cited here [verified revids; mirror rule from
`CLAUDE.md`].

| Fact | Source (page, revid) |
|---|---|
| Two hard-coded migrant waves in the first two seasons, 1 to 10 each; none in the first winter; later waves depend on created wealth reported by the outgoing dwarven caravan; the population cap setting stops immigration | Immigration, 320124 |
| Strange moods need at least 20 dwarves | Immigration, 320124; Strange mood, 320207 |
| Fortress titles: Hamlet at population 20 (created wealth 5,000, exported 500), Village 50 (25,000, 2,500), Town 80 (100,000, 10,000; sieges of 10 regulars), City 110, Metropolis 140; Hamlet and Village see ambushes only; hard difficulty roughly halves triggers | Siege, 321023 |
| Sieges begin once population reaches 80 (undead excepted) | Siege, 321023 |
| A mayor is elected at population 50, replacing the expedition leader; then captain of the guard and dungeon master become available | Noble, 320809; Mayor, 315414 |
| Baron: population 20, created wealth 100,000, exported 10,000; has room requirements (decent quarters, dining room, office, tomb) | Noble, 320809; Baron, 320589 |
| Most megabeasts need created wealth 100,000, exported 10,000 and population 80; forgotten beasts need 50,000 created wealth and a discovered cavern | Megabeast, 317133 |
| A dormitory is the best short-term sleeping solution; 3 or 4 beds suffice for one, since only a fraction sleep at once; individual bedrooms can come later | Quickstart guide, 320477, "Bedrooms" |
| Tables and chairs for **one fifth** of the population, planning ahead for immigrants | Dining room, 312062 |
| Ten times the number of drinks and meals as dwarves "is more than enough" | Quickstart guide, 320477, "Brewing and Cooking" |
| Each dwarf consumes about 7 units of food and drink per season; a young fort cannot use farm tiles fully | Farming, 319185 |
| Militia: at least 5 spare dwarves; "you especially will want soldiers before you reach a population of 80" | Quickstart guide, 320477, "Military" |
| Do not make wealth (gold, smoothing, engraving) before a militia is equipped: wealth draws ambushes | Quickstart guide, 320477, "Wealth and Invasion" |
| "Almost always eventually": coffins and tombs, hospital, well, clothing, temple, jail, civilian alerts; "as population grows": smoothing, more industries, caverns with a defended entrance, tavern, library, guilds | Quickstart guide, 320477, "What Next?" |
| Guilds petition for a guildhall at 10 members of a profession; temples at 10 members of a religion, satisfied at value 2,000 | Guildhall, 316008; Temple, 315872 |

Community sources beyond the wiki, honestly:

- A rough first-year order (food, drink, depot, trade goods; dig shelter;
  seal the fort; stock for the spring wave) appears across Steam and forum
  threads [summary only: search results for Steam community discussions
  3716062978730149177 and 3716062978741754507; pages not opened]. The
  older wiki checklist "What should I build first" (40d namespace, an
  old version) gives the same rough order "in some sort of rough order"
  [prior, old version, revid not recorded].
- **Nobody publishes a staged, per-capita progression table.** The wiki
  gives ordered advice for a minimal fortress and an unordered "what next"
  list; per-capita numbers exist only for dining (one fifth) and stock
  ("ten times"); bedrooms per dwarf is a matter of preference ("largely a
  matter of personal preference", Quickstart guide). Searches for forum or
  reddit milestone guides returned no such table [summary]. **The staged
  shape is this project's synthesis**, and the v1 file must say so in
  each entry's sources (`kind: research`, this document).

### 5.2 Seed v1, stage by stage

Each number is **prior**; "project" marks a number from this project's own
default or user calls, not the community.

| Stage | Enter when | Priorities (ordered) | Targets (want shape) | Expectations |
|---|---|---|---|---|
| `founding` | always | drink_secure, food_secure, shelter_and_storage, core_workshops, sleeping_space | dormitory beds `{plus: 4, max: 6}` (wiki); dining seats `{per_alive: 0.2, min: 2}` (wiki one fifth); farm plots: **no target** until a farm-tile signal exists | Quartermaster: drink and meals toward ten per citizen (wiki); Overseer: no wealth-making work before a militia (wiki) |
| `hamlet` | alive 20 or more (the game's title and mood threshold) | sleeping_space, dining, moods_ready, administration, hygiene_and_burial, health | bedrooms `{per_alive: 1.0}` reorder gap 2 (**project**: the user's own default, plan v1, against the wiki's "later"); dining seats `{per_alive: 0.2, min: 4}`; offices per `nobles.requirements` (existing tool, per position, three honest states) | Quartermaster: coffins on hand, beds buffered by a standing order (the unsupplied stream's shape); Overseer: moods start now, so a workshop of each kind a mood may name should exist |
| `village` | alive 50 or more | defence, administration, religion_and_leisure, dining, health | bedrooms as hamlet with `plus: 2` headroom (**project**: register 2026-10-08 example); dining `{per_alive: 0.2}`; mayor's rooms per `nobles.requirements` | Overseer: militia of at least 5 before population 80 (wiki); temple and guildhall petitions arrive at 10 members (wiki) |
| `town` | alive 80 or more, **or** a `first_siege` milestone | defence, caverns, industry_metal, trade | defence targets **inert** (owner `marshal`, which is disabled with no write tools [verified: `agents/ROSTER.yaml`]) | Overseer: sieges and megabeasts are now possible (doctrine-cited) |
| `city` and later | not seeded | | | "No evidence; not seeded" is the honest entry |

Two disagreements to put to the user rather than settle here (decision 7):

1. **Dining seats.** The default plan has one chair per citizen with reorder
   0.7 (`plans/default-v1.yaml`) [verified]; the wiki says one fifth
   [prior]. The wiki's rule is about how many eat at once; a bad thought
   for eating without a table is a per-meal event, so one fifth plus
   headroom is probably enough. Recommendation: the wiki number, `measured`
   only after a stage shows no "ate without a table" thoughts, a read that
   does not exist yet (the Planner design lists citizen thoughts as a gap,
   §3.1 there) [verified gap].
2. **Bedrooms at founding.** The wiki prefers a dormitory early; the
   project's default is a bedroom per citizen from the start, and the live
   fort's stall was exactly a bedroom it could not furnish (no bed item;
   `evals/live/2026-10-07-stuck-bed`) [verified]. Recommendation: dormitory
   in `founding`, bedrooms from `hamlet`, which Uniboslan (22 alive
   [verified, CLAUDE.md status]) is already in.

### 5.3 Verify the boundaries from this install, not the wiki

Stage triggers are game mechanics, so they can become `verified` doctrine
with a `game-data` source describing 53.16, the doctrine validator's rule
[verified: `doctrine/validate.py` `VERIFYING_KINDS`]:

- Noble positions' `REQUIRES_POPULATION` and `LAND_HOLDER` triggers in the
  install's entity raws (the Noble page says Baron, Count and Duke read
  their numbers from the land-holder difficulty settings, not the raws)
  [prior].
- The fort's difficulty and population-cap settings (siege and title
  triggers move with difficulty, per the Siege page) [prior].

This is R0's live check (section 7). **Not done here**: no VM access in
this task.

---

## 6. Measurement

### 6.1 The stage outcome digest (code-built)

Per stage occurrence (one fort's time in one stage), computed from records
that exist or are named gaps:

| Measure | Source | Status |
|---|---|---|
| Game days in stage; reached next stage or fort ended | stage high-water mark with tick stamps | new, small |
| Per target: days from stage entry to met, stalls, max shortfall | `plan.status` history per version | proposed in the Planner design (`plan.status`), history needs keeping |
| Per target: deviation direction, reason, and whether the deviated value was met | `fort_plan` versions with `roadmap_ref` | new field |
| Crises: deaths by cause, thirst and hunger crossings, tripwires | vitals, `dfseries`, tripwire log | exist [verified: `dfseries`, tripwire] |
| Serving proposals per target: filed, accepted, rejected, done | `serves` plus queue | exists (Planner design) |
| Rulings citing each priority | `roadmap_refs` on rulings | new field |
| Wake cost per role in the stage | `wake_metrics` by role and window | exists [verified] |
| Citizen thoughts (no bed, no table) | none | **gap**, as in the Planner design |
| Created and exported wealth | none | **gap** |

The digest is ids and numbers, publishable by construction, like
`wake_metrics/1` [verified pattern].

### 6.2 How we would know the roadmap improved

- **Primary, per entry:** median days from stage entry to met, and stalls
  per stage occurrence, compared between roadmap versions. Lower is better
  only together with **no rise in crises**, since a target set to zero is
  met instantly.
- **Fit:** deviation rate per entry, split into explained and unexplained;
  a falling deviation rate means the standard fits the forts it serves.
  Watch for a Planner that simply stops deviating (copying is not fit):
  check deviations against outcomes, not alone.
- **Change quality:** the graded hit rate of `roadmap_change` proposals,
  per the track-record principle (`docs/AGENT-ARCHITECTURE.md` §10) and a
  Brier score on any stated probability [verified principle].
- **Health of the standard:** share of entries `measured` versus `prior`;
  entries walked back per year (the embarrassment check); entries never
  cited in a slice window (waste).
- **Cost:** Elder wakes and cost per game year; Planner rounds per review
  before and after the slice (the slice should cut orientation reads).

**Baselines.** Uniboslan before the roadmap: the bedroom stall of
2026-10-05 to 2026-10-07, the starvation death of 2026-09-19 and the thirst
crisis of 2026-09-19 [verified: register rows] are the pre-roadmap record
for its founding and hamlet stages. Plan v1 (the unmodified default) is
version-zero behaviour.

**What this cannot show, stated plainly:** one fort at a time, no seeded
reruns (register 2026-09-18) [verified], stages visited once per fort. Any
claim that a roadmap version "improved outcomes" is correlational across
forts with different worlds and embarks, and will stay qualitative for many
forts. The ledger's covariates and partial pooling
(`docs/MEMORY-ARCHITECTURE.md` "Cross-fortress learning") are the right
long-run home; nothing here pretends to be an experiment.

---

## 7. Stages to build

Each stage has a live check; R0 to R2 need no new agent.

### R0. Seed data and verification (offline plus one read-only live check)

`fort_roadmap/seed-v1.yaml` (section 5.2), `fort_roadmap/priorities.yaml`,
a validator (shape, closed vocabularies, the refusal list in 1.6, flags for
kinds and signals, the step limit as a pure function), tests. Doctrine
entries for the game-fact thresholds. **Live check:** one read-only read of
VM 103's entity raws and difficulty settings confirming or correcting 20 /
50 / 80; the doctrine entries flip to `verified` or get corrected.

### R1. Store, stage computation and the Planner slice

`roadmap.sqlite3` with `init` and seed import; `roadmap.read`; conductor-only
`roadmap.status` (current stage, high-water mark, next stage's conditions
with current values, flagged triggers); embark tick recorded; the
`roadmap_ref` and deviation computation in `plan.write`'s reply; the
`roadmap_stage_entered` Planner wake and the adopt-only exemption; the
Planner's slice; `plans/default-v1.yaml` replaced by the roadmap's
founding stage. Deploy `vm103-dfmcp` and `vm106-conductor`, both (the
Planner red team's F-5 lesson) [verified]. **Live check:** a `--once`
Planner cycle under the operator hold shows the `hamlet` slice for
Uniboslan; plan v2 (season permitting, or a `plan_change`) records each
target's `roadmap_ref` and any deviation with its reason on the Board.

### R2. Overseer and Quartermaster slices, and measurement

The review-lens slice and `roadmap_refs` on `queue.rule`; Quartermaster
expectation lines; `slice_ids` on run rows; slice waste and covered reads
in `wake_metrics`. Overseer charter: one paragraph on the lens. **Live
check:** the next real cycle's Overseer briefing shows the lens; after ten
wakes, the waste report lists cited and uncited ids.

### R3. The Elder

`agents/elder/` (role.md, tools.yaml with the 9 tools, model.yaml), roster
line (`answerer: true`), token and pinned openclaw config, rotation row,
`docs/STATE.md` counts; the `roadmap_change` type in the `applied_on_ruling`
class; the server apply step with the validator; the stage outcome digest;
the wake reasons in 3.3 with backoff; the user digest line. **Live check,
offline first:** on a scratch queue, a synthetic stage completion produces
a digest, the real Elder (one-shot openclaw) proposes or passes, the real
Overseer rules, the server applies v2, the Planner's next slice shows v2.
Then once on the live fort when Uniboslan leaves `hamlet`.

### R4. Grading and the anti-noise machinery

Horizon grading by stage occurrence; the hoop-failure wake with its check;
the `measured` promotion rule; rate limits; the oscillation detector; the
export to the repo and the drift-check line. **Live check:** a synthetic
graded miss wakes the Elder once and never twice.

### R5. Doctrine revisions join the Elder (only if the user agrees)

The 2026-09-17 learning role's duties: tallying misses against cited
doctrine, the discussion record other roles must cite for a doctrinal
revision, and doctrine revision proposals through the same review and apply
path. **Live check:** a doctrinal revision filed by another role without a
discussion record is refused by the queue.

---

## 8. Risks

- **A standard nobody needed.** If the Planner copies the roadmap and
  nothing ever deviates or fails, the Elder has nothing to do. That is a
  fine outcome for R0 to R2 and a reason R3 waits for evidence.
- **One dramatic fort rewrites the standard.** The guards in 3.5; the
  hoop-test exception is the sharpest edge, so its check is code, not the
  Elder's claim.
- **The Overseer rubber-stamps.** One ruling on doctrine exists on record;
  there is no evidence yet that the Overseer reviews generic changes well.
  The user digest stays until graded changes say otherwise.
- **Signals that read wrong.** A stage reached on a bad `alive` read, or a
  furnished count that undercounts, propagates into every fort. Stage
  computation keeps the high-water mark with its evidence so a wrong
  advance is visible and reversible by a correction record.
- **The compliance budget.** Slices are a handful of lines per role by
  design; the roadmap as a whole never goes into any prompt but the
  Elder's, and its own charter stays small until R5.
- **Version drift.** A different DF version may move the thresholds; the
  `game_version` field and the doctrine citations flag it.

---

## 9. Not verified

- **Game thresholds on this install** (20, 50, 80, and the wealth figures):
  wiki only; the install's raws and difficulty settings were not read (no
  VM access in this task). R0's live check.
- **Whether title thresholds need population and wealth together or
  either**: the Siege page's table lists both without saying; the prose
  says sieges begin at population 80. Unresolved.
- **The wiki dining and dormitory guidance on 53.16 specifically**: main
  namespace pages describe the current release, not pinned to 53.16.
- **Cross-domain claims** (ICC cycle: search summaries only; comply or
  explain, GRADE and living guidelines, park standards, trust-region
  updates, curriculum design: recalled, not fetched this session).
- **Community milestone guides beyond the wiki**: only search summaries
  were seen; no forum or reddit page was opened, and none of the summaries
  showed a staged per-capita table.
- **The cost and wake-rate estimates** for the Elder: inferred from the
  Planner design's figures, not measured.
- **A wealth read**: assumed buildable from the game's fortress wealth
  figures; no DFHack source was read for it here.

---

## 10. User decisions, one per line, with a recommendation

1. **Role name**: Elder, curator or something else? Recommend **Elder**.
2. **Elder and the 2026-09-17 learning role: one role or two?** Recommend **one**, doctrine duties added at R5.
3. **"The overseer takes on a reviewing proposal type role": reviewer of roadmap changes only, or the Overseer's whole identity as reviewer?** Recommend **both**: it reviews roadmap changes now, and its charter moves to reviewer-of-proposals as the execution redesign already intends.
4. **Where the roadmap lives**: cross-fort server store exported to the repo, or repo only with human commits? Recommend the **server store**, exported and drift-checked.
5. **Build the role now, or data and slices first?** Recommend **R0 to R2 first, R3 when the first stage completes** (the role has nothing to judge before then).
6. **Stage-varying stock expectations: roadmap or doctrine?** Recommend **roadmap** for stage-varying levels, doctrine keeps stage-independent bands.
7. **Seed numbers where the wiki and our default disagree**: dining at one fifth, a dormitory at founding? Recommend **yes to both**, bedrooms per citizen from `hamlet`.
8. **Planner deviations without a reason: flag or refuse?** Recommend **flag** (consistent with your option b for plans).
9. **One-fort exception: may a hoop failure (a death with the target met) change the generic roadmap from one fort?** Recommend **yes**, with the code check and the doubled step limit only.
10. **Applied roadmap changes in your digest until graded changes show good review?** Recommend **yes**, as doctrine.
