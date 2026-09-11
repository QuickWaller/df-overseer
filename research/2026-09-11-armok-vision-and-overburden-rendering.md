# Armok Vision as Prior Art, and the Overburden/Occlusion Problem

Date: 2026-09-11
Scope: two open questions carried over from `research/2026-09-10-live-freelook-viewer-architecture.md` (§3's RFR
live-update/schema gap, and §4's "Armok Vision, not researched this session" flag) and from the user's direct
question, "can you strip away the ground and only show tunnels and constructions, have people worked that out?" —
(A) read Armok Vision's actual source to determine how it queries `RemoteFortressReader` (RFR) and how it solves
occlusion of overburden terrain; (B) read Stonesense's actual `CHOP_WALL`/`CHOP_WALLS` code path precisely, since
its existence (but not its behavior) was confirmed in `research/2026-09-10-stonesense-headless-rendering.md`; (C) a
light survey of how comparable games/tools handle the same problem.
Status: **desk research only**, per the task's explicit instruction — no SSH access to VM 103, no live infra
touched, no code changes. Everything below is read directly from primary sources: the `RosaryMala/armok-vision`
GitHub repository (source, issues, LICENSE, README — fetched via `gh api`/GitHub contents API, not summarized from
search results except where explicitly marked as such), the `JapaMala/RemoteClientDF-Net` submodule, the
`DFHack/dfhack` repository at the exact pinned tag `53.16-r1.1` this project runs (`plugins/remotefortressreader/remotefortressreader.cpp`),
and the `DFHack/stonesense` repository (continuing directly from the prior Stonesense research pass's already-open
files). Source preferred over docs/marketing wherever they could be compared, per this repo's evidence standard;
every such comparison is named explicitly below.

---

## 1. Bottom line, up front

**Armok Vision is real, working, primary prior art for almost this entire design — and it is abandoned, not
active.** Its own source code answers the two biggest open questions from the freelook architecture doc with much
higher confidence than that doc could reach alone:

1. **RFR's "live update" model is neither pure push nor a naive full-snapshot poll — it is client-driven polling of
   a server-side, hash-computed *delta*.** Read directly from `plugins/remotefortressreader/remotefortressreader.cpp`
   at DFHack's exact `53.16-r1.1` tag (this project's pinned version): `GetBlockList` maintains a persistent
   position-keyed hash table (`std::map<DFCoord, uint16_t> hashes`, Fletcher-16 checksums) and only sends a map
   block's tile/designation/spatter/building data if that specific sub-component's hash changed since the last
   call — not on every call, regardless of how the client invokes it. Armok Vision's client (`DFConnection.cs`)
   simply calls `GetBlockList` on a repeating background-thread timer (`blockUpdate = 500` — no explicit unit
   confirmed, ms is the reasoned default given observed ~2 Hz cadence) against a bounding box centered on the
   camera. **This directly answers the prior doc's open question**: RFR supports genuine incremental content at the
   RPC-payload level, but the *transport* is still request/response polling initiated by the client, never a
   server-push subscription. **[C]**, read directly from the DFHack source at the exact pinned version, cross-checked
   against Armok Vision's own client usage of the same call.
2. **The overburden/occlusion problem is solved by a working, shipped, dynamic camera-relative z-band visibility
   system**, not a hack or an open question in Armok Vision's own history — `GameMap.cs`'s `GetVisibility(z)`
   classifies every loaded map chunk into `None`/`Shadows`/`Walls`/`All` purely as a function of `z - PosZ` (the
   live camera's tracked Z level, updated every frame `MapPositionUpdater` moves), re-evaluated continuously as the
   camera moves. This is exactly the "dynamic, camera-relative culling" the user asked about, real and running, not
   proposed. **[C]**, read directly from the shipped source.

**Stonesense's `CHOP_WALLS` (the actual keybind name — not `CHOP_WALL`; see §5's correction) is a real, working,
but narrow mechanism: it only affects the single topmost currently-loaded z-level's wall sprites, and in three of
its four modes only chops a wall where a creature or building is actually behind it.** It does not "strip away the
ground" through a fort's full depth on its own — that job is already done by `SEGMENTSIZE_Z` (which layers get
loaded at all, per the prior Stonesense doc). `CHOP_WALLS` solves a different, narrower, genuinely complementary
problem: whether the walls of the one layer you *are* looking at themselves block your view of what's on it. **[C]**,
read directly from `Tile.cpp` and `SegmentProcessing.cpp`.

**Licensing is materially cleaner for Armok Vision than for Stonesense.** Armok Vision's repository-wide `LICENSE`
is plain MIT with no carve-out for bundled art, unlike Stonesense's split code/art licensing
(`research/2026-09-10-stonesense-headless-rendering.md` §6). **[C]**, read directly from the `LICENSE` file; **[I]**
on whether every individual community-contributed `StreamingAssets` file has clean upstream provenance, since that
was not itemized asset-by-asset.

**Performance is the loudest warning in this whole report.** Real, primary-source user reports on Armok Vision's own
issue tracker put DF/DFHack's own process CPU usage at **40-50%, up from 5-7% before Armok Vision connected** —
this is the *cost paid by the thing being polled*, the closest available real-world analog to what this project's
already-loaded DFHack process would pay for a live RFR feed, and it is a serious data point against the "broadcast
once, cheaply" assumption in `research/2026-09-10-live-freelook-viewer-architecture.md` §3. **[C]** for the reported
numbers existing on the tracker; **[I]** for how directly they transfer to this project's different hardware/fort
size/query pattern.

---

## 2. Armok Vision: identity, maintenance status, and license

**Canonical repository**: `RosaryMala/armok-vision` (formerly `JapaMala/armok-vision` — the README's own links still
point to the old `JapaMala` org name in places, e.g. the issues link in the "Bugs" section, confirming the rename
happened after that prose was written and was not fully swept). Confirmed canonical by: highest star count (331)
and fork count (30) of every fork checked via `gh api repos/RosaryMala/armok-vision/forks`; every one of those 30
forks' `pushed_at` timestamp is **equal to or earlier than** the upstream's own last push, meaning no fork has
carried the project further than upstream itself — there is no more-current fork to prefer. **[C]**, read directly
from the GitHub API, not inferred from star count alone.

**Maintenance status: abandoned, not merely quiet.** `gh api repos/RosaryMala/armok-vision` reports
`pushed_at: 2023-01-05T05:43:29Z` — the last commit (`3027c785`, "Update to latest unity") is from that date, three
years eight months before this research date (2026-09-11). A web search independently surfaced a Bay12 Forums
thread titled **"Armok Vision Project, on Hiatus."**, corroborating the same conclusion from a second, independent
source. **[C]** for the commit timestamp (primary source, GitHub API); **[I]** for the forum thread's exact content,
since only its title was seen in search results, not the thread body itself — flagged as corroborating, not
independently read. **Practical consequence for this project**: Armok Vision is safe to study as a design reference
(its solved problems stay solved; the code doesn't get worse by sitting still) but is not a live community to ask
questions of, and its own DFHack-plugin dependency (`RemoteFortressReader`) has almost certainly moved on in ways
Armok Vision's client never adapted to — the README's own install instructions warn of exactly this ("you need a
copy of DFHack built after the current version of Armok Vision was released or an updated RemoteFortressReader
plugin"), a self-aware acknowledgment of protocol drift risk that predates this report.

**License: MIT, repo-wide, no carve-out found.** `LICENSE` (fetched and read in full): standard MIT text, copyright
Japa (2014), covering "the Software" without any artwork/asset exception. This is a **materially cleaner** position
than Stonesense's split code/art licensing (`research/2026-09-10-stonesense-headless-rendering.md` §6, where the
Zlib code license explicitly does not extend to bundled sprites). **[C]**, read directly. The README's "Artists"
section does note community members contribute 3D models/textures under `StreamingAssets`, loaded at runtime — the
per-contributor provenance of each individual asset file was not itemized in this pass, so **whether every single
bundled asset is actually MIT-clean, versus merely "the repo's blanket license says MIT and nobody has objected," is
not fully verified** — flagged in §7. This distinction matters less for this project than Stonesense's case, though,
because nothing in this project's design plans to reuse Armok Vision's actual assets — it is being read purely as
a design reference for RFR usage and occlusion technique, not a source of code or art to redistribute.

---

## 3. How Armok Vision queries RFR (task A.1 and A.2)

### 3.1 Transport: client-driven polling, not server push

Read directly from `Assets/Scripts/MapGen/DFConnection.cs` (1462 lines, fetched in full):

- Every RFR call is a bound `RemoteFunction<TInput, TOutput>` (from the `JapaMala/RemoteClientDF-Net` submodule,
  `DFHack/RemoteFunction.cs` — also read in full) — a synchronous, one-shot `TryExecute(input, out output)` call
  over DFHack's binary RPC protocol. There is no subscribe/callback/streaming primitive anywhere in this class; the
  generic itself only exposes `Execute`/`TryExecute`, both single request-response calls. **[C]**.
- The one exception, `blockListCall`, is wrapped as a `TimedRemoteFunction<BlockRequest, BlockList>` via a local
  helper:
  ```csharp
  TimedRemoteFunction<Input, Output> CreateAndBindTimed<Input, Output>(float interval, RemoteClient client, string name, string proto = "")
  {
      RemoteFunction<Input, Output> output = new RemoteFunction<Input, Output>();
      if (output.Bind(client, name, proto))
          return new TimedRemoteFunction<Input, Output>(interval, output);
      else
          return null;
  }
  ...
  blockListCall = CreateAndBindTimed<BlockRequest, BlockList>(GameSettings.Instance.updateTimers.blockUpdate, networkClient, "GetBlockList", "RemoteFortressReader");
  ```
  with `GameSettings.cs`: `public float blockUpdate = 500;`. **`TimedRemoteFunction`'s own class definition could not
  be located anywhere in the `armok-vision` repository, its `RemoteClientDF-Net` submodule, or a targeted GitHub
  code search of the former** — it is very likely a precompiled dependency (a `.dll` under `Assets/Plugins`) rather
  than source present in the repo, and this report could not read its actual throttling logic. **Not verified**:
  whether `500` means milliseconds or some other unit, and the exact throttling behavior (does it skip a call
  entirely if the interval hasn't elapsed, or queue it?). **[I]**, reasoned from the field's name/magnitude and from
  a user-reported cadence in a separate context (Issue #55's "decreases the update speed from 30 times per second
  down to once per second" — a different subsystem, view-tracking, but confirms sub-second polling intervals are
  the project's general idiom).
- The network work itself happens on a background thread — `RunOnAlternateThread` field, and Unity's own `Update()`
  method (read in full, lines 945-956) does nothing but poll a `connectionManager` and drain callback queues; the
  actual `GetBlockList`/`GetViewInfo`/etc. calls happen in `UpdatePlugin()` (line 774), the background thread's loop
  body. **[C]**.
- **Net conclusion for the freelook doc's open question**: RFR is a request/response RPC service, not a
  publish/subscribe one, at the transport level — a from-scratch browser client would need to poll it the same way
  Armok Vision does (on its own timer, from its own bounding box), not expect DFHack to push anything unprompted.
  **[C]**, this is a structural fact about the RPC framework itself (`RemoteFunction`'s interface has no callback
  registration path anywhere), not merely "Armok Vision chose to poll."

### 3.2 The payload is a real, server-computed delta, not a full resend

This is the more important and more subtle finding, and it required going past Armok Vision's own client code into
DFHack's actual plugin implementation — the client-side evidence alone (a `BlockRequest` with `min_x/max_x/min_y/
max_y/min_z/max_z` bounding-box fields, read from `Assets/RemoteClientLocal/RemoteFortressReader.proto`) could be
misread as "just re-requests the whole region every time." Reading `GetBlockList`'s actual server-side C++
implementation resolves this cleanly.

Fetched directly at this project's exact pinned tag,
`https://raw.githubusercontent.com/DFHack/dfhack/53.16-r1.1/plugins/remotefortressreader/remotefortressreader.cpp`
(2988 lines total; the relevant logic is lines 651-762 and 1378 onward):

```cpp
std::map<DFCoord, uint16_t> hashes;

bool IsTiletypeChanged(DFCoord pos)
{
    uint16_t hash;
    df::map_block * block = Maps::getBlock(pos);
    if (block)
        hash = fletcher16((block->tiletype).data(), 16 * 16 * (sizeof(df::enums::tiletype::tiletype)));
    else
        hash = 0;
    if (hashes[pos] != hash)
    {
        hashes[pos] = hash;
        return true;
    }
    return false;
}
```
Parallel functions exist for designations (`waterHashes`), spatter (`spatterHashes`), and buildings/items. Inside
`GetBlockList` itself:
```cpp
bool tileChanged = IsTiletypeChanged(pos);
bool desChanged = IsDesignationChanged(pos);
bool spatterChanged = IsspatterChanged(pos);
...
if (tileChanged || desChanged || spatterChanged || firstBlock || itemsChanged || flows || forceReload)
{
    net_block = out->add_map_blocks();
    ...
}
if (tileChanged || forceReload)
{
    CopyBlock(block, net_block, &MC, pos);
    blocks_sent++;
}
if (desChanged || forceReload)
    CopyDesignation(block, net_block, &MC, pos);
```
i.e., a block's tile geometry is only actually copied into the response **if its Fletcher-16 checksum changed since
the last time this same server-side state was consulted** (or `force_reload`/`firstBlock` override it). There is
also a dedicated `CheckHashes` RPC and a `ResetMapHashes` RPC (the latter's client-side use is visible in
`DFConnection.cs`: called when the embark/map size changes, to force a full resend on a new fort). **[C]**, read
directly and in full at the exact version this project's VM runs — this is as close to a primary-source-confirmed
answer as this report can give.

**Consequence for the freelook design**: a from-scratch browser-based feed does not need to invent a diffing
mechanism of its own — `GetBlockList` already only sends what changed, provided the client keeps calling it against
the same region without an intervening `ResetMapHashes`. The real remaining cost is the **polling cadence and
region size**, not "does every poll re-send the whole map" — that fear from the prior doc is resolved. What is *not*
resolved (see §6) is whether the **query itself** (walking the map and computing hashes, even when nothing changed)
is cheap on the server side, independent of whether anything gets sent back — the CPU-cost evidence in §6 suggests
it is not free.

### 3.3 Message schema for tiles, materials, units

Read directly from `Assets/RemoteClientLocal/RemoteFortressReader.proto` (1121 lines, the actual `.proto` file
Armok Vision compiles against — a materially more complete primary source than this project's own prior finding
that RFR's *documentation* is thin; the **schema itself**, in the wire-format definition, is not thin at all):

- **`MapBlock`** (one 16x16-tile chunk): `tiles` (flat `repeated int32`, one tiletype enum value per tile),
  `materials`/`layer_materials`/`vein_materials`/`base_materials` (each a `repeated MatPair`, i.e. one
  `(mat_type, mat_index)` pair per tile per category — DF's own two-integer material identity scheme, not
  translated to anything higher-level), `magma`/`water` (per-tile fill-level ints), `hidden`/`light`/
  `subterranean`/`outside`/`aquifer` (per-tile bool flags), `buildings` (`repeated BuildingInstance`), `items`
  (`repeated Item`), `tile_dig_designation` and related designation-marker fields, `flows` (`FlowInfo`, presumably
  for magma/water flow animation). **[C]**.
- **`UnitDefinition`**: tile-granular `pos_x/pos_y/pos_z` **plus** sub-tile `subpos_x/subpos_y/subpos_z` (floats,
  for smooth interpolation between tiles rather than snapping) and a `facing` field of type `Coord` (orientation).
  Also carries `race` (`MatPair`), `profession_color`, `is_soldier`, `appearance`, `inventory`
  (`repeated InventoryItem`), and `wounds`. **[C]**, read directly.
- This confirms the freelook doc's assumption that RFR carries enough for a live 3D reconstruction (geometry,
  material identity, unit position *and* orientation, sub-tile interpolation for smooth movement) was correct, but
  it was previously unverified — it is now **[C]** rather than **[I]**.

### 3.4 Region sizing: concrete numbers for the bandwidth question

`Assets/Scripts/IniFileParser/GameSettings.cs`, the `Rendering` settings class, read directly:
```csharp
public int drawRangeSide = 4;   // blocks (16-tile chunks) each direction from camera
public int drawRangeUp = 1;
public int drawRangeDown = 5;
public int maxBlocksToDraw = 460800;
```
and `GameMap.cs`'s `UpdateRequestRegion()` (read in full) constructs the actual `BlockRequest` bounding box directly
from these values, centered on `PosXBlock`/`PosYBlock`/`PosZ` — the camera's own current position, recomputed and
re-requested continuously as the camera moves. **[C]**. This gives the freelook design a concrete starting point for
its own "how much of the map needs to be live per viewer" question (§3 of the prior doc): Armok Vision's own
defaults request roughly a 9x9-block horizontal footprint (4 blocks each side, i.e. ~144x144 tiles) and 7 z-levels
(1 up, 5 down, plus the current level) around a single camera. **This is a per-camera region** — directly relevant
to whether this project's "broadcast one feed to everyone" plan (prior doc §3) is even the right shape, since Armok
Vision's own reference client assumes exactly one camera's worth of live region, not an aggregate of many
independent free cameras. A multi-viewer broadcast design would need to either request the union of all active
viewers' regions (which grows with viewer count and reintroduces the scaling problem the "broadcast once" design was
meant to avoid) or accept that independent free-look viewers might occasionally query outside the pre-fetched region
and see nothing until it's fetched — **not resolved by Armok Vision's own design, since Armok Vision only ever has
one local camera and never faced this problem**. **[I]**, this is this report's own reasoning applied to Armok
Vision's confirmed single-camera behavior, not something Armok Vision's source itself addresses.

---

## 4. How Armok Vision solves the overburden/occlusion problem (task A.3)

**This is the single most directly actionable finding in this report.** Read directly from
`Assets/Scripts/MapGen/GameMap.cs` (1621 lines, fetched in full) and `Assets/Scripts/MapGen/MapBlock/BlockMeshSet.cs`.

### 4.1 The mechanism: a live, camera-relative Z-band, re-evaluated continuously

`GameMap.cs` tracks `PosZ`, the camera's current tile Z-level, updated every time the camera moves:
```csharp
public void UpdateCenter(Vector3 pos)
{
    DFCoord dfPos = UnityToDFCoord(pos);
    PosXTile = dfPos.x;
    PosYTile = dfPos.y;
    PosZ = dfPos.z + 1;
}
```
`UpdateCenter` is called from `MapPositionUpdater.Update()` — a `MonoBehaviour` attached to (per its own comment
and the presence of a `firstPerson` enum field) the camera/player object, computing `transform.TransformPoint(offset)`
every frame. **This confirms the culling is driven by the free camera's own live position, every frame, not a
manually-toggled setting** — exactly the "dynamic camera-relative" behavior the user asked about. **[C]**.

Every loaded map chunk is assigned one of four visibility states based purely on its Z relative to `PosZ`:
```csharp
BlockMeshSet.Visibility GetVisibility(int z)
{
    if (z > PosZ + GameSettings.Instance.rendering.drawRangeUp)
        return BlockMeshSet.Visibility.None;
    else if (z >= PosZ)
    {
        if (firstPerson)
            return BlockMeshSet.Visibility.Walls;
        else if (overheadShadows)
            return BlockMeshSet.Visibility.Shadows;
        else
            return BlockMeshSet.Visibility.None;
    }
    else if (z == PosZ - 1)
        return BlockMeshSet.Visibility.All;
    else if (z >= PosZ - GameSettings.Instance.rendering.drawRangeDown)
        return BlockMeshSet.Visibility.Walls;
    else
        return BlockMeshSet.Visibility.None;
}
```
Reading this plainly, level by level relative to the camera:
- **Above `drawRangeUp` levels over the camera**: not rendered at all (`None`) — this is the hard cutoff that stops
  a fort's open sky/surface or unrelated upper strata from ever being drawn while the camera is deep underground.
- **At or above the camera's own level, within `drawRangeUp`**: in free/god-mode camera, either invisible
  (`None`) or, if `overheadShadows` is enabled, rendered as `Shadows` — meaning the geometry exists and casts a
  shadow onto the level below (giving a visual depth/lighting cue that "there's a ceiling here") **without actually
  drawing the solid geometry that would block the view**. In first-person mode, this band renders as `Walls` (see
  below) instead, since a first-person camera standing at that level needs to actually see the walls immediately
  around it.
- **Exactly one level below the camera (`PosZ - 1`)**: full detail (`All`) — this is "the floor you're currently
  looking at/standing on."
- **Further below, down to `drawRangeDown` levels**: `Walls` only (see `BlockMeshSet.UpdateVisibility`, below) —
  a cutaway effect showing side walls of lower levels without their ceiling/floor caps blocking the view down
  into them.
- **Beyond `drawRangeDown`**: not rendered (`None`).

`BlockMeshSet.cs`'s `UpdateVisibility` (read in full) reveals what `Walls` vs `All` actually changes at the mesh
level — **not different geometry, but different shadow-casting-mode assignment on the same meshes**:
```csharp
public enum Visibility { None, Shadows, Walls, All }

public void UpdateVisibility(Visibility vis)
{
    switch (vis)
    {
        case Visibility.None:
            gameObject.SetActive(false);
            break;
        case Visibility.Shadows:
            gameObject.SetActive(true);
            foreach (var renderer in meshRenderers)
                renderer.Value.shadowCastingMode = ShadowCastingMode.ShadowsOnly;
            collisionBlocks.gameObject.layer = 2;
            break;
        case Visibility.Walls:
            gameObject.SetActive(true);
            foreach (var renderer in meshRenderers)
            {
                if (IsTop(renderer.Key))         // "Top" mesh types: floor/ceiling caps
                    renderer.Value.shadowCastingMode = ShadowCastingMode.ShadowsOnly;  // invisible, shadow only
                else
                    renderer.Value.shadowCastingMode = ShadowCastingMode.On;            // visible normally — side walls
            }
            collisionBlocks.gameObject.layer = 0;
            break;
        case Visibility.All:
            gameObject.SetActive(true);
            foreach (var renderer in meshRenderers)
                renderer.Value.shadowCastingMode = ShadowCastingMode.On;
            collisionBlocks.gameObject.layer = 0;
            break;
    }
}
```
So "`Walls`" specifically means: the block's **top-face mesh** (its floor/ceiling cap — `MeshType.TopTiles`,
`TopStencilTiles`, `TopTransparentTiles`, `TopTerrain`, distinguished from plain side-wall meshes by the `IsTop()`
helper) is switched to `ShadowCastingMode.ShadowsOnly`, i.e. **it still casts a shadow but is never itself drawn** —
while the ordinary side-wall meshes stay fully visible. This is precisely a doll's-house cutaway: solid rock caps
above the region you're looking into are suppressed from view (but keep contributing ambient shadow for depth
perception), while the walls that give the tunnels their shape stay visible. **[C]**, read directly, this is not
inferred — the mechanism is exactly as described, mesh visibility state driven purely by a live Z-delta from the
camera.

### 4.2 This is a genuinely solved, shipped feature, not an aspiration

Unlike Stonesense's `TOGGLE_SINGLE_LAYER` (confirmed broken upstream in the prior research pass, GitHub issue #185)
or `TRACK_MODE:NONE` (issue #225), nothing in Armok Vision's own issue tracker suggests this Z-band visibility
system itself is broken — the one adjacent bug found, **Issue #59, "Some Z-layers are never rendered in FPS mode"**
(open, unresolved, read in full), describes tree canopy layers sometimes failing to reappear when ascending/
descending repeatedly in first-person mode — a real, open bug, but in the *mesh reload/dirty-tracking* pipeline
around this system, not in the visibility-banding logic itself. **[C]** that the bug exists and is open; **[I]**
that it's specifically a reload-timing issue rather than the banding logic, since this report did not trace the
mesh-dirtying code path that would confirm the exact root cause.

### 4.3 Direct applicability to a browser/WebGL client

Because this technique operates entirely on data already available client-side (each viewer's own current camera Z,
and the geometry already streamed to it), **it transfers directly to a browser/Three.js implementation with no
server involvement at all** — each browser can independently decide, per frame, which of its own already-received
chunks to render at full opacity, shadow-only, or not at all, purely as a function of its own camera's Z position.
This is a strong, concrete answer to part of `research/2026-09-10-live-freelook-viewer-architecture.md`'s open
design space: the "each browser renders independently from a shared broadcast feed" architecture and "each viewer's
occlusion state is purely local, camera-driven, cheap" are compatible and mutually reinforcing — Armok Vision proves
the occlusion technique doesn't need server cooperation beyond receiving the raw geometry, which the broadcast
design already provides. **[I]**, reasoned by combining two independently-confirmed facts (the broadcast
architecture's own data flow, and Armok Vision's confirmed client-only occlusion logic) — not tested against an
actual implementation.

---

## 5. Stonesense's `CHOP_WALLS` action, precisely (task B)

**Correction to the prior research pass's action-name list**: the keybind is `CHOP_WALLS` (plural), not `CHOP_WALL`
as listed in `research/2026-09-10-stonesense-headless-rendering.md` §3's "full confirmed action-name list."
Confirmed from `configs/keybinds.txt`, the shipped template: `[CHOP_WALLS:KEY_C]` /
`CHOP_WALLS | cycle through wall sprite chopping options`, and from `Keybinds.cpp`'s action-dispatch table:
`{"CHOP_WALLS", action_chopwall}`. This one-line comment in the keybind template — *"cycle through wall sprite
chopping options"* — is the **only** documentation of this feature found anywhere; it does not appear at all in
`docs/Stonesense.rst` (searched directly, zero matches for "chop" or "truncate"), confirming the prior research
pass's finding that this action's *existence* was documented but its *behavior* was not, and extending that finding
to: **the behavior is undocumented even in the one place the game usually documents its own actions**, not merely
absent from the rendered docs site.

### 5.1 What it actually does — a 5-state cycle, not a boolean toggle

`UserInput.cpp`, read directly:
```cpp
void action_chopwall(uint32_t keymod)
{
    auto& ssConfig = stonesenseState.ssConfig;
    ssConfig.truncate_walls++;
    if (ssConfig.truncate_walls > 4) {
        ssConfig.truncate_walls = 0;
    }
    stonesenseState.timeToReloadSegment = true;
}
```
`truncate_walls` is a `uint8_t` (`GameConfiguration.h`) cycling through five states, 0-4. Its consumption, read
directly from `Tile.cpp`:
```cpp
bool chopThisTile = 0;
if(ssConfig.truncate_walls == 1) {
    chopThisTile = 1;
} else if(ssConfig.truncate_walls == 2 && obscuringCreature == 1) {
    chopThisTile = 1;
} else if(ssConfig.truncate_walls == 3 && (obscuringCreature == 1 || obscuringBuilding == 1)) {
    chopThisTile = 1;
} else if(ssConfig.truncate_walls == 4 && obscuringBuilding == 1) {
    chopThisTile = 1;
}
```
So: **mode 0 = off. Mode 1 = chop unconditionally. Mode 2 = chop only where a creature is obscured. Mode 3 = chop
where a creature or a building is obscured. Mode 4 = chop only where a building is obscured.** This is a genuinely
content-aware mechanism in three of its five states, not a blanket toggle — **[C]**, read directly.

### 5.2 What "obscured" means, and the crucial scope limit

`SegmentProcessing.cpp`'s `arrangeTileBorders`, read directly, computes `obscuringCreature`/`obscuringBuilding` per
wall tile by checking the three tiles in the isometric "front" directions (up-left, up, left) for a unit
(`occ.bits.unit`) or a non-trivial building (excluding civzones, stockpiles, and the special "blackbox" building):
```cpp
if ((dirs[0] && dirs[0]->occ.bits.unit) || (dirs[1] && dirs[1]->occ.bits.unit) || (dirs[7] && dirs[7]->occ.bits.unit))
    b->obscuringCreature = true;
...
if (isObscurableBuilding(dirs[0]) || isObscurableBuilding(dirs[1]) || isObscurableBuilding(dirs[7]))
    b->obscuringBuilding = true;
```
i.e. a wall is "obscuring" if it sits between the isometric camera and a creature or building that the wall would
otherwise visually hide — genuinely dynamic and content-relative for modes 2-4, not merely "is this a natural rock
wall vs. a constructed one" as the task brief speculated might be the distinguishing factor (that distinction does
not appear anywhere in this logic at all — material type is irrelevant to `truncate_walls`). **[C]**.

**The scope-limiting finding, and the most important one for this task**: `chopThisTile` is only ever passed as
`true` at the point of actually drawing a tile's sprite, gated by an additional condition found at every call site
(`Tile.cpp` lines 433, 552, 598, 600):
```cpp
spriteobject->assemble_world_offset(x, y, z, 0, this,
    (chopThisTile && int(this->z) == ownerSegment->segState.Position.z + ownerSegment->segState.Size.z - 2));
```
**Wall-chopping only ever applies to the single topmost z-level of the currently-loaded segment** (`Position.z +
Size.z - 2`, i.e. one below the top of whatever vertical window `SEGMENTSIZE_Z` is currently loading) — never to
every level in the loaded stack, and never to anything below the top slice. **[C]**, read directly, confirmed
consistently across all four call sites that reference `chopThisTile`.

### 5.3 Static or dynamic? Complementary or redundant with `SEGMENTSIZE_Z:1`?

**Static-per-mode, but the mode itself is a whole-view toggle, not per-tile-persistent state** — `truncate_walls`
is a single global config value (one of 5 states) applied uniformly whenever `AssembleTile()` runs; there is no
concept of "chop only near the cursor" or "chop only near the camera" the way Armok Vision's `PosZ`-relative bands
work. Where it *is* dynamic is within a mode: modes 2-4 re-evaluate `obscuringCreature`/`obscuringBuilding` per
tile per render (since `arrangeTileBorders` runs as part of normal segment processing, re-triggered by
`stonesenseState.timeToReloadSegment = true` on every mode change and on ordinary reloads) — so a creature walking
under a chop-eligible wall will cause that specific wall to start/stop being chopped as it moves, without needing
the mode to be re-toggled. **[I]** that this per-tile re-evaluation happens on every regular frame/reload rather
than only when the mode is changed — the code confirms the *logic* is content-relative, but this report did not
trace exactly how often `arrangeTileBorders` re-runs during normal (non-mode-change) operation to confirm the
re-evaluation cadence.

**Answering task B's third question directly**: `CHOP_WALLS` and the prior Stonesense doc's proposed
`SEGMENTSIZE_Z:1` per-level walk are **complementary, solving different layers of the same overall problem, not
redundant**:
- `SEGMENTSIZE_Z` controls **which z-levels are loaded and rendered at all** — a hard vertical crop of the data
  itself, independent of any sprite-level chopping.
- `CHOP_WALLS` controls, **only for the single topmost loaded level**, whether that level's own wall sprites
  visually block the view of what's on/behind them (a dwarf standing near a wall, a workshop built against one).

Combined with `SEGMENTSIZE_Z:1` (making the "topmost loaded level" the *only* loaded level, per the prior doc's
proposed per-z-level capture loop), `CHOP_WALLS` mode 1 (unconditional chop) becomes directly useful: it would
remove wall-sprite obstruction *within* that single visible slice, which `SEGMENTSIZE_Z:1` alone does not do
(`SEGMENTSIZE_Z:1` only controls which *z-level* is visible, not whether *that level's own walls* block content
on it). **[I]**, reasoned directly from the confirmed code behavior of both mechanisms — not tested against a
running Stonesense instance, per this report's own desk-research constraint.

### 5.4 A related, unrelated-seeming flag checked and ruled out

`GameConfiguration.h` also declares `hide_outer_tiles` (adjacent to `truncate_walls` in the struct, which is why
this report checked it) — its only use, read directly in `GUI.cpp`, is purely cosmetic: it shrinks the on-screen
debug rectangle drawn by `DrawCurrentLevelOutline()` by two tiles on each side. **It has no effect on tile
rendering, occlusion, or visibility of any kind** — a red herring ruled out by reading its actual (sole) call site,
not merely assumed irrelevant from its name. **[C]**.

---

## 6. Performance and scaling evidence (task A.4)

**No official benchmark exists for Armok Vision, but real, quantified user reports on its own issue tracker are a
better data point than this report expected to find, and they are concerning for this project's design.**

- **Issue #53, "High memory usage with low responsiveness"** (open, read in full with all 12 comments): a user
  reports **7+ GB of Unity-side memory** after enabling first-person mode and walking a small map. A maintainer
  response and further testing (against a user-submitted save file) found: *"loading it and entering FPS mode,
  without walking around or anything, Armok Vision is already using 4GB+ and 100% CPU"*, later improving to
  *"~3 GB [...] CPU usage is now ~35% instead of 200%, except when walking around."* **Crucially, and most directly
  relevant to this project's server-side cost question**: *"dwarfort.exe is using 40-50% CPU now, up from 5-7%
  before AV started."* This is **DF/DFHack's own process cost from being polled by a single Armok Vision client** —
  the closest real analog available to what this project's already-loaded, resource-modest VM 103 (4 vCPU, 4096 MB,
  already running the live fort per `docs/PURPOSE.md`) would pay for a live RFR feed to even one server-side reader,
  before any broadcast-fan-out to browsers is considered at all. **[C]** that these exact numbers were reported on
  the primary-source issue tracker; **[I]** for how directly they transfer, since fort size, DF/DFHack version,
  hardware, and query region size all differ from this project's situation and were not independently reproduced.
- **Issue #55, "Sluggish"** (open, read in full with all 11 comments): corroborates the CPU finding from the
  client-rendering side — one commenter reports *"barely get a few frames per second despite decent hardware...
  the game being paused"*, and a maintainer reply about a separate but related subsystem: *"the latest version
  decreases the update speed from 30 times per second down to once per second"* for view/cursor tracking — a
  direct acknowledgment that the project's own polling cadence had to be throttled down for performance reasons, in
  the maintainers' own words. Another comment: *"If you increase the viewing area, the performance drops
  quickly... My parameters are 5 up, 4 side, and 5 down. In FPS mode, if I descend a ladder more than about 6
  layers below the layer I began on, Armok Vision crawls to a halt, at <1 frame/second."* **[C]** for the quotes
  existing on the tracker; this is user-reported, not independently benchmarked by this report.
- **No documented hardware baseline or fort-size ceiling exists** — none of the issues, the README, or the wiki
  (not deeply explored this pass, see §7) state a supported map size or expected frame rate for a given hardware
  tier. The performance discussion that exists is entirely reactive bug-report material, not a stated design
  target. **This is itself a finding**: there is no authoritative "Armok Vision handles forts up to size X on
  hardware Y" figure to cite — only scattered evidence that it struggles well below what a modest embark would
  produce, on unspecified "decent hardware" that is almost certainly far more capable than this project's 4-vCPU
  VM.

**Interpretation for this project**: the client-side numbers (Unity's own GPU/mesh-building cost) don't transfer
directly, since this project's design puts client rendering on the visitor's own browser/GPU, not on the server —
that part of Armok Vision's cost profile is explicitly out of scope for this project's server, by design. **But the
DFHack-side CPU cost (40-50% of a core, from one polling client) is exactly the cost category this project's design
would incur on VM 103 itself**, and it is the single most concrete, primary-source-grounded reason to treat
`research/2026-09-10-live-freelook-viewer-architecture.md` §3's "the expensive part happens once regardless of
viewer count" claim as **not yet safe to assume** — "once" still means "continuously, for as long as the feed
runs," and Armok Vision's own experience says that "once" is not free even for a single reader.

---

## 7. What could not be verified

- **`TimedRemoteFunction`'s actual class implementation and the unit of its `interval` parameter** — not found in
  the `armok-vision` repository, its `RemoteClientDF-Net` submodule, or a GitHub code search restricted to the
  former; almost certainly a precompiled binary dependency this report could not read. The 500 = milliseconds
  reading is a reasoned inference (§3.1), not confirmed.
- **Whether the Issue #53/#55 performance numbers reproduce on this project's actual fort size, DF/DFHack version,
  and VM 103's hardware** — explicitly out of scope for a desk-research pass with no SSH access; flagged as the
  clearest "needs a live/empirical test before committing further design effort" item in this report, mirroring the
  same category of gap the prior Stonesense doc flagged for its own renderer.
- **Per-asset licensing provenance for Armok Vision's community-contributed `StreamingAssets` files** — the
  repository's blanket `LICENSE` is MIT with no carve-out, but individual contributor assets were not itemized
  against that claim one by one.
- **The exact re-evaluation cadence of Stonesense's `obscuringCreature`/`obscuringBuilding` flags during normal
  (non-mode-change) operation** — confirmed to be content-relative and re-computed by `arrangeTileBorders`, but the
  precise trigger frequency during ordinary play (versus only on an explicit reload) was not traced end-to-end.
- **Whether `SEGMENTSIZE_Z:1` + `CHOP_WALLS` mode 1, combined, actually produces a clean single-level cutaway
  image in practice** — this report's §5.3 conclusion is reasoned directly from confirmed code behavior in both
  mechanisms, not run against a live fort; it inherits the same "not tested" caveat the prior Stonesense doc already
  carries for its own `SEGMENTSIZE_Z:1` proposal.
- **Bay12 Forums thread content for "Armok Vision Project, on Hiatus."** — only the title was seen via web search;
  the thread itself was not fetched and read, so this report cannot say what the maintainers stated about the
  project's status beyond what the title itself implies.
- **RosaryMala/isoworld** and **Ankoku/df-webfort** (both surfaced during the §8 prior-art search) were checked only
  at the level needed to rule them out as directly relevant (Isoworld renders flat Legends-mode elevation maps, not
  a live 3D fort interior; df-webfort is a browser-served remote-play tool for DF's own 2D text/tile screen via the
  TWBT plugin, not a 3D viewer) — neither was read in the depth this report gave Armok Vision or Stonesense, since
  neither is a close match to the free-look/occlusion questions this task asked about.

---

## 8. Broader prior art: a light pass (task C)

Kept deliberately shallow per the task's own instruction not to over-invest here.

- **RimWorld and Prison Architect** (both checked via web search only, not source): both are genuinely **2D**
  games with a top-down sprite view, not 3D scenes — their "roof" mechanics are a different problem in kind, not
  degree. RimWorld's roof system is a binary "is this tile roofed" structural calculation (distance from
  supporting walls) with a UI overlay toggle, and community complaints exist about roof *rendering* artifacts
  (Steam Workshop mod "Perspective: Eaves") rather than an occlusion problem, since there is no camera to occlude
  anything from in a top-down 2D game. Prison Architect's "Alpha 4" update (per its own wiki, not verified against
  source) reportedly moved from a solid roof-hiding effect to a greyscale/darkened rendering of fog-of-war areas —
  again a 2D visibility/fog mechanic, not 3D occlusion. **Neither is meaningfully comparable to this project's
  actual problem** (a true 3D scene with a movable free camera and solid geometry that can sit between the camera
  and the thing it wants to look at) — **[I]**, based on search-result summaries only, not source-verified, and
  flagged explicitly as such per this report's evidence standard.
- **Oxygen Not Included**: also a 2D side-view game (not 3D); no useful technical detail on any camera/cutaway
  mechanic was found via web search, and this was not pursued further given the low prior probability of relevance
  once its 2D nature was established.
- **Other DF-specific viewers found**: **Isoworld** (`RosaryMala/isoworld`, by the same author as Armok Vision) —
  a Legends-mode elevation/biome map viewer, not a live fortress-interior 3D tool; ruled out as off-topic rather
  than researched in depth. **`mifki/df-webfort`** (and its forks `Ankoku/df-webfort`, `Alloyed/df-webfort`) —
  README read directly: a DFHack plugin plus a `webfort.html` browser page that renders DF's own text/tile screen
  buffer (via the "Text Will Be Text" plugin) remotely in a browser — genuinely browser-based, but a 2D
  screen-mirroring tool, functionally a browser-based version of this project's *existing* shared-VNC approach, not
  independent 3D free-look. Last pushed 2015-05-25 (upstream) — also long abandoned. **[C]** for what the tool is
  (README read in full); not a match for the occlusion question since it never renders 3D geometry to have an
  occlusion problem with.
- **Net finding for task C**: **no additional prior art solving 3D occlusion via dynamic camera-relative culling
  was found beyond Armok Vision itself.** The comparable-games survey mostly surfaced tools solving a different
  (2D, fog-of-war-shaped) version of "hide what you shouldn't see," which doesn't transfer to this project's
  genuinely-3D problem. This narrows rather than broadens the evidence base: Armok Vision's `GetVisibility(z)`
  mechanism (§4) is, as far as this pass could determine, **the only concretely observed real-world implementation
  of the specific technique this project would need**, not one example among several. Whether "nobody else has
  published this particular technique" or "this report's search simply didn't find them" cannot be fully
  distinguished — flagged honestly rather than overstated as an exhaustive survey.

---

## 9. Recommendation

**(1) Is Armok Vision's approach directly informative for a browser/WebGL version of this project's design, and
what would need to change?**

Yes, substantially more than the prior doc's "noted, not researched" flag suggested. Its RFR-polling pattern (§3)
and its Z-band occlusion technique (§4) both transfer conceptually to a from-scratch browser client without needing
Armok Vision's own code, engine, or assets at all — this project would still be writing its own server-side poller
and its own Three.js client, but now with a concrete, source-verified reference for both "how to talk to RFR
sensibly" and "how to hide overburden once you have the geometry," rather than reasoning both out from protocol
documentation alone. What would need to change: everything client-side, obviously (Unity/C#/native GPU access
becomes Three.js/JavaScript/WebGL, per-browser); server-side, this project would still need to write its own
region-tracking/polling loop against `GetBlockList` (no reusable server code exists to take from Armok Vision, since
its "server-side" logic lives entirely inside DFHack's own plugin, already available to any RFR client); and the
occlusion logic (§4.1's `GetVisibility(z)` state machine) is simple enough — a pure function of `z - cameraZ` plus
two settings — that it is more sensible to reimplement directly in the browser client than to try to port or wrap
any of Armok Vision's actual C# code.

**(2) Does `CHOP_WALLS` solve the user's stated want ("strip away the ground, only show tunnels and constructions")
— fully, partially, or not at all?**

**Partially, and only as a component of a larger recipe, not as a standalone answer.** By itself, `CHOP_WALLS`
only affects the single topmost currently-loaded z-level's own wall sprites (§5.2) — it does nothing about the many
levels of rock that would sit *above* whatever level you're looking at in a naive full-map render. That larger job
is `SEGMENTSIZE_Z`'s to do (limiting what's loaded at all), a mechanism the prior Stonesense doc already covered.
`CHOP_WALLS` becomes meaningfully useful specifically once `SEGMENTSIZE_Z:1` is already in play (making the "top
level" the *only* level), at which point mode 1 removes that level's own wall obstruction of what's happening on
it. **This is squarely Stonesense's answer, though — a periodic-screenshot, per-z-level tool, not the real-time
free-look design this document otherwise concerns itself with.** For the free-look/browser design specifically, the
user's want is better answered by Armok Vision's `GetVisibility(z)` mechanism (§4), which is a genuine, continuous,
arbitrary-3D-camera solution to exactly this problem, already proven in a shipped tool — Stonesense's
`CHOP_WALLS` and the free-look design are not the same tool solving the same problem, and this report recommends
treating them as separate, non-competing answers to two different rendering approaches this project has in play
(periodic isometric screenshots vs. real-time free-look), not as alternatives to choose between.

**(3) What's the single next concrete step this project should take given these findings?**

**A live, cheap measurement of RFR's actual polling cost on VM 103 itself**, before any further design work on
either the freelook architecture or a Stonesense capture job. Specifically: connect any RFR client (even a trivial
script calling `GetBlockList` in a loop against a small bounding box) to the already-running Uniboslan fort, and
measure the DFHack process's own CPU delta, the same way `docs/PURPOSE.md` already measured the worldgen memory
spike and the prior Stonesense doc proposed for its own renderer-viability question. Armok Vision's own issue
tracker (§6) gives a real but foreign data point (someone else's fort, someone else's hardware, someone else's DF
version) suggesting this cost is not negligible; this project's entire "broadcast once, cheaply" architecture
(`research/2026-09-10-live-freelook-viewer-architecture.md` §3) rests on that cost being small enough to run
continuously alongside the live fort on a 4 vCPU VM, and that has not yet been checked against this project's own
actual system even once. This is a smaller, cheaper, and more foundational test than anything else this thread has
proposed, and it gates whether the rest of the freelook design is worth continuing to refine at all.

---

## 10. Sources

- `RosaryMala/armok-vision` GitHub repository (read directly via `gh api`/GitHub contents API, `master` branch,
  this research date): `LICENSE`, `README.md`, `Assets/Scripts/MapGen/DFConnection.cs` (full, 1462 lines),
  `Assets/Scripts/MapGen/GameMap.cs` (full, 1621 lines), `Assets/Scripts/MapGen/MapBlock/BlockMeshSet.cs`,
  `Assets/Scripts/CameraScripts/MapPositionUpdater.cs`, `Assets/Scripts/IniFileParser/GameSettings.cs`,
  `Assets/Scripts/MapGen/UserSettings/DrawRangeUp.cs`/`DrawRangeDown.cs`/`DrawRangeSide.cs`,
  `Assets/RemoteClientLocal/RemoteFortressReader.proto` (full, 1121 lines), `Assets/Shaders/Invisibul.shader`
  (checked, ruled out as unrelated — a shadow-caster-only material for a different purpose), `.gitmodules`. Primary
  source, verified directly, highest confidence in this report.
- `RosaryMala/armok-vision` issue tracker (`gh api repos/RosaryMala/armok-vision/issues` and
  `.../issues/{53,55,59}/comments`, read in full): #53 "High memory usage with low responsiveness", #55 "Sluggish",
  #59 "Some Z-layers are never rendered in FPS mode", #48, #52, #57, #60, #66, #67, #80 (titles only, not read in
  full — listed for completeness, not cited above). Primary source.
- `JapaMala/RemoteClientDF-Net` GitHub repository (submodule of armok-vision): `DFHack/RemoteFunction.cs` (full).
  Primary source.
- `DFHack/dfhack` GitHub repository, **exact pinned tag `53.16-r1.1`** (this project's own installed version):
  `plugins/remotefortressreader/remotefortressreader.cpp` (full, 2988 lines) — `GetBlockList`, `IsTiletypeChanged`,
  `IsDesignationChanged`, `CheckHashes`, `ResetMapHashes`. Primary source, version-exact, highest confidence.
- `DFHack/stonesense` GitHub repository (continuing directly from the prior research pass's already-open files,
  re-fetched fresh this session): `UserInput.cpp`, `UserInput.h`, `Tile.cpp`, `SegmentProcessing.cpp`, `GUI.cpp`,
  `GameConfiguration.h`, `Keybinds.cpp`, `configs/keybinds.txt`, `docs/Stonesense.rst` (searched for "chop"/
  "truncate", zero matches — a confirmed docs gap, not an oversight in this report's search). Primary source.
- This project's own already-verified files: `research/2026-09-10-live-freelook-viewer-architecture.md` (the
  document this research directly continues), `research/2026-09-10-stonesense-headless-rendering.md` (source for
  the `CHOP_WALL`/action-name list this report corrects in §5, and for the `SEGMENTSIZE_Z:1` proposal this report's
  §5.3 evaluates against), `docs/PURPOSE.md` (VM spec, measurement-methodology precedent cited in §9's
  recommendation).
- General web search (`WebSearch`), used only for identifying the canonical Armok Vision repository, corroborating
  its abandonment status via an independent forum-thread title, and the light §8 comparable-games pass — every
  claim sourced this way is explicitly marked **[I]** or lower and distinguished from the primary-source-read
  material above, per this report's evidence standard.

---

## 11. Relevant to

`research/2026-09-10-live-freelook-viewer-architecture.md` §3 (RFR live-update/schema question — substantially
answered here) and §4 (the "Armok Vision, not researched" flag this document resolves). Also relevant to
`research/2026-09-10-stonesense-headless-rendering.md` §3 (the action-name correction in §5 above) and §5 (this
report's §5.3 directly evaluates that document's `SEGMENTSIZE_Z:1` proposal against `CHOP_WALLS`'s actual scope).
`docs/PURPOSE.md`'s *Streaming the fortress* section and design commitment #6 (human view vs. model view — this
entire thread, including this document, is human-view-only work, no bearing on design commitment #1's prohibition
on showing the model a rendered map). Whoever next picks up either the freelook architecture or a Stonesense
capture-job build should read §9's recommendation first — it names a single, cheap, concrete live test that gates
further design work on both fronts, not just one.
