# Real-Time, Independent Free-Look Viewer — Architecture Options

Date: 2026-09-10
Author: this session's own reasoning during a live design conversation with the
user, not a `researcher` subagent pass — **confidence is medium-to-low
throughout** and explicitly flagged per-claim below. This is a record of the
current shape of an idea and its open questions, not a verified spec. Treat it
as the thing to read before re-deriving this design, not as settled ground to
build from directly.

Supersedes, for this specific use case, the narrower question
`research/2026-09-10-stonesense-headless-rendering.md` answered — that
document's findings are not wrong and remain relevant background (see §3), but
it was scoped to a periodic-screenshot, pan-and-z-level viewer. This document
covers a harder requirement the user raised afterward: **real-time**, and each
public viewer independently **looks around freely (an FPS-style free camera)**,
not just pans a 2D image and switches which z-level's image is shown.

---

## 1. The requirement, as stated

- Real-time, not a periodic refresh (contrast with the screenshot-per-z-level
  design in the Stonesense doc, which was explicitly *not* real-time — a
  30-60s refresh cadence).
- Each public internet visitor gets independent free-look: their own camera,
  moving continuously through the space, not a shared camera and not a
  discrete "pick a z-level, then pan/zoom a static image" interaction.

## 2. Why the prior candidates don't satisfy this

- **Shared VNC** (the live feed already running): one camera for every
  viewer. Already established, not re-argued here.
- **Periodic screenshot / Stonesense** (`research/2026-09-10-stonesense-headless-rendering.md`):
  satisfies independent pan and independent z-level choice, but not
  real-time free camera movement — Stonesense has a fixed isometric
  projection and no live control API at all (confirmed in that doc, §3: no
  CLI, no Lua API, no RPC). It cannot be driven into "smoothly fly the
  camera wherever this one visitor wants, continuously." **[C]**, inherited
  from the prior doc's own confirmed findings.
- **Server-side per-viewer 3D render, streamed as video** (the "naive" way to
  give free-look): doesn't scale. Free-look means every viewer needs a
  genuinely distinct rendered frame (different camera = different pixels),
  so this is N independent render+encode jobs for N viewers. This project's
  VM is 4 vCPU / 4096 MB, single-core-clock-bound, already running the fort
  itself (`docs/PURPOSE.md` operating parameters) — it cannot absorb even a
  handful of concurrent independent 3D renders, let alone an open-ended
  public audience. This is also a strictly worse version of a scaling
  problem this project already hit and deliberately avoided for the
  *shared*-camera case: `decisions/DECISIONS.md` 2026-09-09 records that
  `websockify` bandwidth/CPU scale with concurrent viewers even when
  everyone shares one camera; independent free-look removes even the
  "share one render" mitigation. **[I]**, reasoned from this project's own
  known VM spec and already-recorded scaling finding, not independently
  load-tested.

## 3. Proposed architecture: client-rendered 3D from a live structured-data feed

**[proposed, low-to-medium confidence, not tested]**

- **Server**: a continuous `RemoteFortressReader` (RFR) feed of map geometry,
  materials, and unit/building state. RFR itself is confirmed present and
  functional on this install (`memory/dfhack-environment.md`: *"RemoteFortressReader.plug.dll
  is present, so structured map/unit reads work out of the box"*) — but that
  confirmation was about one-shot structured reads, not about this design's
  specific need for continuous/incremental live updates. **Not verified this
  session**: whether RFR supports an actual live/incremental query pattern
  (subscribe-to-changes, or a cheap diff) versus only repeated full-region
  pulls, and what its exact message schema carries for tile geometry,
  material identity, and unit orientation/pose. `memory/dfhack-environment.md`
  itself flags RFR's own documentation as thin (*"only ~26 lines; the real RPC
  surface was extracted from the plugin DLL with `strings`"*) and its field
  layouts as *"moderate confidence, from a single upstream source"* — so this
  is a real gap, not a minor detail, and should be the first thing checked
  before writing any server code against it.
- **Transport**: whatever the server computes gets **broadcast once** to every
  connected browser (e.g. over WebSocket) — not computed per-viewer. This is
  the one architectural property that makes independent free-look scale on
  modest hardware: the expensive part (reading and packaging world state)
  happens once regardless of viewer count; the expensive part that *does*
  scale per-viewer (turning that data into pixels from one specific camera
  angle) happens on each visitor's own device.
- **Client**: an ordinary WebGL scene (e.g. Three.js) builds and incrementally
  updates a local 3D representation from the broadcast data, and each
  browser runs its own free-look camera against its own local copy of the
  world — standard real-time-3D-client code, not DF-specific.
- **Unverified/unknown**, all **[I]** or worse, none tested: RFR's live-update
  capability and exact schema (above); realistic update-rate/bandwidth cost of
  broadcasting a changing fort's geometry to N browsers over the existing
  Cloudflare Tunnel path; client-side performance of building/updating a
  WebGL scene from that data continuously; how much of the fort needs to be
  streamed at once (the whole revealed map vs. a region around each camera,
  which reintroduces a per-viewer-relative-data question even though
  rendering itself stays client-side).

## 4. Prior art: Armok Vision

**[noted, not researched this session — flagged explicitly as low confidence]**

Armok Vision is an existing open-source project doing, at a high level,
exactly this: a live 3D viewer of a running DF fort, built on RFR. It is
Unity/desktop, not browser-based, so it is not directly reusable, but its
approach to mapping RFR's block/tile/unit data onto a live 3D scene is
almost certainly the fastest way to answer §3's open schema/update-pattern
questions rather than re-deriving them from the DFHack source blind. **This
session has not read Armok Vision's source, docs, or issue tracker at all —
its relevance here is an inference from its stated purpose, not a verified
recommendation.** A proper research pass (same rigor as the Stonesense doc)
should cover: how it queries RFR for live updates, what its data model looks
like for tiles/materials/units, and what performance or scaling notes exist
in its own history.

## 5. The reopened question: client-side visual assets and licensing

Free-look rendering happens on the visitor's own GPU, which means the
visitor's browser needs actual textures/materials to draw the world with —
unlike the screenshot approach, where only rendered pixels ever left the
server and the underlying tileset files never had to reach a client. This
puts a real decision back on the table, **explicitly not resolved by this
document**:

1. **An original/custom visual style**, not the purchased Kitfox Premium
   tileset. Cleanest licensing (nothing to clear at all), but not "the real
   Steam tileset" the user asked about earlier in this thread.
2. **Some other, openly-licensed community DF tileset** built for
   redistribution, distinct from the commercial Premium pack. Not yet
   identified or verified — would need its own research pass on what exists
   and its actual license terms.
3. **Ship the purchased Kitfox tileset itself as client textures.** A real
   change from this project's existing posture — `decisions/DECISIONS.md`
   2026-09-09's graphics-transplant entry rests its legitimacy explicitly on
   "personal-use asset data from a purchase already made... never
   redistributed, and never committed to this (public) repo." Serving those
   texture files to every visitor's browser is redistribution in a way the
   existing VNC/screenshot approach never was (those only ever sent
   *rendered pixels*, never the asset files). **Not something to build
   without the user explicitly deciding to accept that change** — this is a
   judgment call, not a technical one, and it's the user's to make.

## 6. Status and next steps

**Nothing here is built or tested.** This document exists to record the
current shape of the idea and its open questions before further research or
design commits to a direction. Suggested next steps, in rough order of
value-for-cost:

1. A proper research pass on Armok Vision (its RFR query pattern, data model,
   any documented performance ceiling) and on RFR's own live/incremental
   query capability directly (source-level, same rigor as the Stonesense
   doc) — this resolves the biggest unknown in §3 before any server code gets
   written.
2. The user's call on §5's licensing question — this shapes the client asset
   pipeline early enough that it's worth deciding before, not after, building
   the renderer.
3. A rough bandwidth/update-rate budget check: how much of a running fort's
   geometry actually changes per second at `FPS_CAP:5`, and whether that's
   small enough to broadcast live over the existing Cloudflare Tunnel path
   without redesigning the network layer too.

## 7. Relevant to

`research/2026-09-10-stonesense-headless-rendering.md` (the narrower,
periodic-screenshot version of this same overall thread — background, not
superseded as a document, just answering a different question now that the
requirement has changed). `docs/PURPOSE.md`'s *Streaming the fortress* section
and design commitment #6 (human view and model view are different artifacts —
this is squarely human-view-only, no bearing on design commitment #1).
`decisions/DECISIONS.md` 2026-09-09 graphics-transplant row, contrasted
directly in §5. Also relevant to whoever picks up `docs/PURPOSE.md` build
order item 5 (`get_diff_since` via `eventful`) on the perception-layer side —
a live diff/event feed off DFHack is something both that work and this one
might eventually want, worth checking for overlap before either builds one.
