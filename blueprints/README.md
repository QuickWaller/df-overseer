# Blueprints

`quickfort` blueprint source files (`.csv`, `#dig`/`#place`/`#build` modes),
the "Blueprint library" scope item from `docs/PURPOSE.md`. Chosen over raw
DFHack designation writes deliberately: design commitment #4 says the model
picks a named template and an anchor, never generated coordinates, and
`quickfort` (a mature, stock DFHack tool) is the real mechanism for that —
see `decisions/DECISIONS.md` 2026-09-10 ("Played Uniboslan forward for
real").

**Status: eleven starter files, hand-authored, not yet templated for
reuse.** The first four were built and applied once each, live, against
Uniboslan's actual first room; the three added
`handoffs/2026-09-16-farm-and-still-tools.md` (farm plot, still, kitchen)
were deployed and build-tested live by
`handoffs/2026-09-17-farm-tools-deploy.md` (dry runs only; no real build
exercised yet). The four added
`handoffs/2026-09-17-water-and-industry-tools.md` (well, mason, mechanic,
carpenter) are hand-authored the same way, from `#build` symbols read
directly from this install's own
`hack/scripts/internal/quickfort/build.lua`, but **not yet deployed or
build-tested live** — see that handoff's report for what was and wasn't
exercised.

| File | Mode | Purpose |
|---|---|---|
| `starter-entrance-1x1.csv` | `#dig` | One downstair tile from the surface |
| `starter-connector-1x1.csv` | `#dig` | One upstair tile linking the entrance to the room below — required; a plain floor dig directly beneath a stair never becomes a job, see the durable traps in `Working.md`/`working-archive/` |
| `starter-room-5x5.csv` | `#dig` | The room itself |
| `starter-stockpile-5x5.csv` | `#place` | A matching general stockpile over the dug room |
| `starter-farmplot-5x5.csv` | `#build` | A 5x5 farm plot (`p` symbol), zero-material, filled full-footprint like the stockpile above — for `df-overseer-farm.lua`'s `build` command |
| `starter-still-3x3.csv` | `#build` | A 3x3 Still workshop (`wl` symbol) — for `df-overseer-workshop.lua`'s `build` command, `KIND=still` |
| `starter-kitchen-3x3.csv` | `#build` | A 3x3 Kitchen workshop (`wz` symbol) — same tool, `KIND=kitchen` |
| `starter-well-1x1.csv` | `#build` | One Well tile (`l` symbol) — for `df-overseer-well.lua`'s `build` command |
| `starter-mason-3x3.csv` | `#build` | A 3x3 Mason's Workshop (`wm` symbol) — `df-overseer-workshop.lua`, `KIND=mason` |
| `starter-mechanic-3x3.csv` | `#build` | A 3x3 Mechanic's Workshop (`wt` symbol) — same tool, `KIND=mechanic` |
| `starter-carpenter-3x3.csv` | `#build` | A 3x3 Carpenter's Workshop (`wc` symbol) — same tool, `KIND=carpenter` |

**No static file for `zone.place`.** Unlike every other `build`/`dig`
tool here, `df-overseer-zone.lua`'s water-source zone is not a rectangle a
caller can specify in advance — pond sizes and shapes vary (4 to 31+
tiles this session, `research/2026-09-17-pool-reachability.md`). Its real
(non-dry-run) path generates a throwaway `#zone` blueprint CSV in code,
shaped to the chosen water body's own tile membership, writes it into this
directory on the guest, runs it, then deletes it — see that file's own
header for the exact mechanism and what was/wasn't verified live.

**Deploy path**: plain `scp` into the guest's `dfhack-config/blueprints/`
(quickfort's own player-blueprint directory), not through
`install_df.py`'s script-deploy mechanism — these are quickfort data
files, not DFHack Lua scripts. Applied headlessly via
`quickfort run <file> -c x,y,z`, which needs no interactive map cursor.
Confirmed live this session (read-only `ls`): the guest's
`dfhack-config/blueprints/` today holds only the original four files —
the three new ones must be `scp`'d there (matching the existing four's
own flat layout, no subdirectory) before any `farm.build`/`workshop.build`
call naming them can do anything but fail on a missing file. This stream
did not deploy them (no deploy, per every handoff in this project) — the
tools' own `BLUEPRINT_FILE` argument is a bare filename resolved by
quickfort itself, the same established idiom `openarea.build`/
`diggable.dig` already use, so no code depends on where in this repo the
file physically lives.

**Not yet handled here**: grass-covered surface tiles can't take a
downstair designation (confirmed live, `quickfort` reports 0 tiles
designated with no error) — any anchor point picked automatically rather
than by hand needs to check the actual tile type first, or scan for a
non-grass tile within the target footprint. None of these files do that
check themselves yet; the entrance's coordinates were hand-picked after
manually confirming the tile type this time.

---

## Template library (`templates/`): versioned, generic, tileable cells

Added `handoffs/2026-09-24-bedroom-template.md`, data and documentation
only. **This is a second, deliberately separate tier from the starter
files above and the two are not interchangeable.** A starter file above is
a single-purpose, already-anchored footprint consumed directly by one
tool's `BLUEPRINT_FILE` argument (a farm plot, a specific workshop kind).
A template in `templates/` is a **reusable design artefact**: generic (no
fort coordinates, no landmark names, nothing that identifies Uniboslan),
versioned, and meant to be tiled — placed more than once, adjacent to
copies of itself — by a generator this stream does not build. Read
`docs/PURPOSE.md` design commitment #1 before adding a second template:
the line between an acceptable small generic pattern and a forbidden map
of this fort is real and is what keeps this whole tier legal to publish.

### Why a second tier instead of extending the starter format

The starter files above solve "place this one fixed thing here." The
Architect's actual recurring problem, per
`handoffs/2026-09-24-bedroom-template.md`, is "design this room" done
from scratch on every run. A reusable design needs to say things a
one-off anchored footprint never has to: which of its own edges are its
own, and which it shares with a neighbour when copies of it are tiled
side by side (**seams**), because a self-contained wall ring around every
copy would build a double wall at every shared edge — real waste, real
tile-count, and the kind of thing `research/2026-09-24-room-layout-best
-practices.md` rule 13 asks a checker to weigh. Neither the seam
declaration nor the entrance declaration below has any equivalent in the
starter-file format, hence the new directory rather than a new column.

### One template, two files, per id

Each template is one **id** (`bedroom-cell`, kebab-case, stable — never
renamed once a generator or an agent references it) with two files in
`templates/`, both named `<id>-v<revision>.<ext>`:

- **`<id>-v<revision>.yaml`**: the metadata. Follows the spirit of
  `doctrine/seed.yaml`'s own header (stable id, a revision number, honest
  sourcing with `kind`/`ref`/`describes`/`read`/`accessed`, never a single
  unsourced blob) rather than inventing a second provenance convention.
  Required fields:
  - `id`, `revision`, `kind` (the room/zone kind it declares, e.g.
    `bedroom`), `status` (`designed` — authored and internally consistent,
    not yet applied to any fort; `applied-live` — stamped onto a real fort
    at least once; `verified-live` — stamped and its declared contract,
    room value, zone footprint, etc., confirmed against live game state
    afterward. A template stays `designed` until an executor actually runs
    it against Uniboslan and reports back, per this project's own
    verify-the-verification rule).
  - `generic: true` and a human check that it holds: grep the `.yaml` and
    the `.csv` for anything that looks like a coordinate pair or a name
    this fort has used, before either file is committed.
  - `dimensions`: `footprint` (including any wall ring) and `interior`
    (usable floor), both `{width, depth}`.
  - `edges`: one entry per side (`north`/`south`/`east`/`west` are
    orientation labels for the grid as drawn in the `.csv`, not compass
    directions in the fort — quickfort blueprints carry no compass at
    all). Each edge declares:
    - `role`: `own` (this cell's wall, never shared), `seam` (shared with
      an identical neighbour cell tiled against this edge; whichever cell
      is placed first owns the designation, the second must not re
      -designate it), or `entrance` (faces a corridor or open area, not
      another copy of this cell; carries an `entrance` sub-block instead
      of being a plain wall).
    - `shared`: boolean, redundant with `role` but explicit, since "is
      this edge shared" is the one fact a tiling generator must get right
      or it doubles a wall.
  - `walls`: `intent` (always `finished` for this tier so far — the
    project has not yet needed a second wall intent), `material`
    (`unspecified` — a template never names one), and a `resolution` note
    explaining how the accompanying `.csv` chose to resolve the intent
    concretely (see "Resolving the wall intent" below).
  - `requires`: a list of furniture/zone requirements the template's own
    room-kind needs to be valid (a bed, for a bedroom) —
    `research/2026-09-23-room-and-zone-requirements.md` is the source for
    what a given kind actually requires; a template must not invent a
    requirement that research doc does not list.
  - `does_not_include`: what was deliberately left out and why (a door,
    engraving, extra furniture) — an omission is a design decision, not a
    gap, and gets recorded the same way an inclusion does.
  - `quickfort_blueprints`: one entry per `#`-mode blueprint inside the
    `.csv`, its `label`, `mode`, an `order` number (blueprints sharing an
    order number have no dependency on each other and may be applied
    together, e.g. via a `#meta` bundle; a blueprint with a higher order
    number depends on every lower-order one finishing first, not just
    being applied), and a `depends_on` where the ordering reason is not
    obvious from the number alone.
  - `sources`: same provenance shape as `doctrine/seed.yaml` — a template
    that cites the quickfort guide must say it read the install's own copy
    (`kind: live-read`, the file path, `describes` the install's DF/DFHack
    version), not memory; a template that cites layout convention must
    point at the research doc and, ideally, which numbered rule.
- **`<id>-v<revision>.csv`**: the actual quickfort blueprint, in
  quickfort's own multi-blueprint-per-file format (one `#mode label(...)`
  line starts each blueprint; `quickfort-user-guide.txt`'s own "Packaging
  a set of blueprints" section, read on this install, is the source for
  that convention, not a `.csv`-per-mode split). Grid orientation (which
  row/column is which edge) is documented in a leading `#notes` block
  inside the file itself, because the `.yaml`'s `edges` section describes
  the *contract*, not the *coordinates within this specific grid* — a
  reader should not have to cross-reference the two files to know which
  row is the entrance.

### Declaring the entrance edge

An `entrance` edge's sub-block gives `width` (tiles), `position` (where
along that edge, e.g. `middle`), and `feature`: `none` (an open gap, no
door — see "On not adding a door" below) or `door` (only if a template
ever needs one, with a `justification` field required alongside it,
because "player habit" is not a justification this repo accepts for a
door, per the research below).

### Resolving the wall intent

A template declares every wall tile's intent as `finished`, never a
material. **What "finished" means concretely at apply time is two
different quickfort mechanisms, chosen per tile, not one**:

- **Smooth** (`#dig` mode, symbol `"s"`) when the tile is already standing
  natural rock (the ordinary case for a wall left behind when a room is
  carved out of the mountain).
- **Construct** (`#build` mode, symbol `"Cw"`) when the tile is not
  natural rock at all — most plausibly a seam edge where a neighbour
  template's own dig already removed the material there, so there is
  nothing left to smooth and a wall has to be built from scratch instead.

This project does not yet have the generator that inspects a real tile
and picks between the two per the brief that commissioned this tier
(`handoffs/2026-09-24-bedroom-template.md`: "you are not building that
generator; you are defining the cell and its contract so the generator is
possible"). Until that generator exists, a template's own `.csv` picks
one concrete resolution (documented in its `#notes` block and its
`.yaml`'s `walls.resolution` field) for the common case, and says plainly
which case it assumed, so nobody mistakes "the file that ships" for "the
only correct resolution."

### On not adding a door

`research/2026-09-24-room-layout-best-practices.md` (Q4, candidate rule
11) found the current-version wiki states plainly that a sleeping dwarf
takes no penalty from others travelling through their bedroom — the usual
player reason for a bedroom door does not hold as a game mechanic. A
template in this tier that wants a door anyway must justify it on some
other verified ground (fluid or gas containment, access control against a
named threat) in its `.yaml`'s `entrance.feature: door` block, or leave
the door out. `bedroom-cell-v1` leaves it out.

### Smooth (and, if used, engrave) before build

`quickfort-user-guide.txt`, read on this install
(`scripts/vm-ssh.sh df`, `/opt/df/game/hack/docs/docs/guides/quickfort
-user-guide.txt`), states this directly in its own "Tips and tricks"
section: "After digging out an area, you may wish to smooth and/or
engrave the area before starting the build phase, as dwarves may be
unable to access walls or floors that are behind/under built objects." A
template's `quickfort_blueprints` ordering must put every `#dig`-mode
blueprint (dig, smooth, engrave, in that order if engrave is used) ahead
of the `#build`-mode blueprint that places furniture, and its `.yaml`
should say so in a `note`, not leave the reader to infer it.

### Templates in this tier

| id | revision | kind | status | files |
|---|---|---|---|---|
| `bedroom-cell` | 1 | bedroom | designed | `templates/bedroom-cell-v1.yaml`, `templates/bedroom-cell-v1.csv` |

**Not deployed, not applied, not build-tested.** This tier's files have
never been `scp`'d to the guest's `dfhack-config/blueprints/` and never
run against Uniboslan; `status: designed` in the `.yaml` says so and
should be the first thing a future stream updates once that changes.

### Rationale: `bedroom-cell` v1

**Why this shape.** A 3x3 interior inside a 5x5 footprint, one row deep
off a corridor, with the east and west walls declared as seams and the
north wall as this cell's own. This is the wiki's own **line design**
pattern (`research/2026-09-24-room-layout-best-practices.md` Q1: "Bedroom
alcoves dug directly off an existing access corridor, one row deep, no
separate hallway... very space efficient and very adaptive"), chosen over
the fractal/stairwell-hub families in the same section because it is the
smallest, most self-contained pattern to define a seam contract for — a
line of cells sharing only their east/west walls is the simplest tiling
case that still needs the seam concept at all, which is exactly what this
first template exists to prove out. The research doc's own caveat is kept
rather than hidden: this pattern's known cost is that the corridor itself
becomes the single point of congestion for rooms past the middle of a
long row (Q1, same paragraph); that is a property of *how many cells get
tiled and how long the row runs*, which this single-cell template does not
decide and a future generator will have to weigh, not something this
template can fix by itself.

**Why a 3x3 interior specifically.** No source found by the research pass
gives a minimum or optimal bedroom footprint in tiles (`research/2026-09
-24-room-layout-best-practices.md`, "what could not be verified" does not
list one either, because the question was not in scope for that pass).
3x3 is the smallest square interior that comfortably fits the one
required item (a bed) without the bed occupying the entrance gap's own
approach tile, and it keeps the whole template small and genuinely
generic, per the user's own ruling that a small pattern is the acceptable
side of the line drawn in `docs/PURPOSE.md` commitment #1. A larger
interior is a future revision (`bedroom-cell-v2`, not this file), not a
property this v1 tries to guess at.

**What this optimises for.** Dig cost and the seam contract's own
correctness, in that order — not travel time to a fortress's circulation
hub (`research/2026-09-24-room-layout-best-practices.md` rule 10, a
ranking concern for wherever a *row* of these cells gets placed, not a
property of one cell) and not room value (owned by the sibling
`handoffs/2026-09-24-room-enclosure-and-value.md` stream, not this one).

**What it deliberately does not include, and why:**
- **No door.** See "On not adding a door" above:
  `research/2026-09-24-room-layout-best-practices.md` Q4/rule 11 found the
  current-version wiki states no penalty for a sleeping dwarf from others
  passing through, which removes the usual justification; no other
  verified ground (fluid containment, access control against a named
  threat) applies to an ordinary bedroom, so the entrance stays an open
  gap.
- **No engraving.** Only the wall-finish intent was asked for
  (`handoffs/2026-09-24-bedroom-template.md`); engraving is a real,
  separate quickfort designation (`#dig` mode, symbol `"e"`, must also
  come before the build phase per the same "Tips and tricks" rule) that
  this template does not claim any position on. A later revision that
  wants engraved walls should add it as its own declared intent, not fold
  it silently into "finished."
- **No furniture beyond the one required bed.** `requires: [bed]` is the
  only requirement `research/2026-09-23-room-and-zone-requirements.md`
  states for the bedroom kind; adding a cabinet or container the way the
  quickfort guide's own worked example does would be scope this template
  was not asked to carry, and would make the "one bed, nothing invented"
  contract harder for a generator to reason about.
- **No south-of-corridor (double-loaded) variant.** The line-design
  pattern in Q1 is usually built as rows on both sides of a shared
  corridor; this v1 only defines a single row's cell, with its entrance
  facing one direction. A double-loaded layout is a second template or a
  mirrored placement of this one by the future generator, not something
  v1 needs to encode itself.
