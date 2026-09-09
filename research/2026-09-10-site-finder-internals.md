# Site Finder Internals: `mm` Coordinates, Single-vs-Multi Candidate Tracking, UI Cycling, Savagery Granularity

Date: 2026-09-10
Scope: four specific gaps left open by `research/2026-09-08-embark-automation.md` and a live testing session on `viewscreen_choose_start_sitest` (DF 0.53.16 / DFHack 53.16-r1.1): what `_mm_` field names mean, whether the Site Finder tracks one candidate or many, whether the current DF UI can cycle between matches, and whether Savagery is a per-tile or per-region property.
Status: **desk research only.** No VM was touched, no key was simulated, no live DF process was queried. Everything below comes from (a) a shallow local clone of `github.com/DFHack/df-structures` (`master`, cloned this session) read directly with `Grep`/`Read`, and (b) the Dwarf Fortress Wiki, fetched live. Primary-source findings (struct XML) are marked **[C-XML]**; wiki findings are marked **[C-Wiki]** with the caveat that wiki text is community-authored and can lag or blur mechanics (one fetch in this session did conflate Savagery with the separate Alignment/good-evil axis — see §4); anything not directly stated by either is marked **[I]** for inference and flagged as such.

---

## 1. The answer, up front

1. **`mm` = "min/max."** Confirmed by an explicit DFHack rename table in `df.site.xml`'s `world_site` struct: the original (decompiled/observed) field names `mm_sx/mm_ex/mm_sy/mm_ey/mm_sz/mm_ez` are renamed by DFHack to `rgn_min_x/rgn_max_x/rgn_min_y/rgn_max_y/rgn_min_z/rgn_max_z`, and separately `real_abs_mm_sx/sy/ex/ey` are renamed to `global_min_x/min_y/max_x/max_y`. The same `_s{x,y}`/`_e{x,y}` = start/min, end/max convention recurs in `df.battlefield.xml`. This is about as strong as evidence gets in this codebase without a developer comment spelling the acronym out — it is DFHack's own semantic mapping, not a guess. **[C-XML]**, high confidence.
2. **Coordinate space: "embark tiles," and there appear to be two nested frames using the same naming convention** — a smaller-range one (`int16`, e.g. `find_mm_*`, and `world_site.mm_*` renamed to `rgn_min/max`) and a larger-range "global/absolute" one (`int32`, e.g. `neighbor_hover_mm_*`, `warn_mm_*`, and `world_site.real_abs_mm_*` renamed to `global_min/max`). The `real_abs_mm_sx` field carries the comment `in embark tiles` directly; the smaller `mm_sx` field also carries `in embark tiles` on the world_site struct. This is **[C-XML]** for the unit label and the two-frame pattern; applying that pattern to say `neighbor_hover_mm_*`/`warn_mm_*` on the embark screen are specifically the *global* embark-tile frame (by analogy to `real_abs_mm_*`'s int32 size) and `find_mm_*` is the *local/region* frame (by analogy to `mm_*`'s int16 size) is **[I]**, a strong but unconfirmed inference from type-size matching, not a field-level comment on the viewscreen itself.
3. **The Site Finder tracks a single best candidate, not a set.** `find_cur_best_value`, `find_mm_sx/ex/sy/ey`, and `find_results` are singular fields (not vectors/arrays of results), and the DF Wiki's current Site Finder page states outright: *"The finder will then display the candidate that best fit as many as possible of the selected settings of the desired size."* Singular "the candidate," not a list. **[C-XML + C-Wiki]**, high confidence this answers the crux disagreement: the map's green multi-square highlighting is very likely a separate, independently-computed "does this square currently satisfy the filter" overlay, not the same thing `find_select`/`find_cur_best_value` describes. Corroborating: the same Wiki page independently confirms multiple *display* highlighting: *"If there are multiple sites that match your settings, the site finder will mark all acceptable sites on the Region and World maps."* Both statements are on the same page, describing two different things — one candidate for "current best," many highlighted squares for "still satisfies the filter." This is a **[C-Wiki]**-sourced distinction, and it lines up exactly with this session's negative test results (toggling `biome_highlighted` and writing `find_select` did nothing to the highlight) without needing to guess why.
4. **No "next match" navigation was found in current DF UI documentation.** The Wiki's Site Finder page (tagged current, `v53.16 · v0.47.05`) describes running the search and examining the single best-fit result plus the separately-highlighted acceptable squares, but never mentions a next/previous/cycle key or button. Absence of documentation is not proof of absence, but combined with finding #3 (the finder fundamentally reports one "current best," which is the thing you'd re-run/adjust to change) this is consistent, not contradictory. **[C-Wiki, negative result — explicitly flagged, not proven]**.
5. **Savagery is generated as a continuous per-world-tile numeric field (0–100) with explicit spatial-autocorrelation controls** (`SAVAGERY:<min>:<max>:<x variance>:<y variance>` plus a `SAVAGERY_FREQUENCY` weighting mesh), the same generation mechanism DF uses for elevation/temperature/rainfall/drainage — **[C-Wiki]**, confirmed exact token syntax from the Advanced World Generation page. Separately, and at a *finer* grain, `df-structures`' `world_region_details` struct (`region_midmapst`) stores a documented 17×17 **biome** sub-grid per world tile plus explicit corner/edge interpolation logic for "how biomes cross embark tile edges" — **[C-XML]**, a struct comment, not inferred. Since the Wiki independently states biomes carry a savagery value (*"All biomes also have... a degree of 'savagery'"*), and biome membership is confirmed to vary at embark-tile granularity within a single world tile (not just at named-region boundaries), the most defensible synthesis is: **savagery is inherited from whichever biome a given embark tile resolves to, and biome resolution is confirmed fine-grained (embark-tile-level with interpolation across world-tile boundaries), which supports the "per-tile, with local correlation, not strict biome-boundary uniformity" model** the domain-expert user proposed. What is **not** independently confirmed is whether the numeric savagery scalar itself is stored/recomputed at that same fine grain, as opposed to being a single value per named region that every embark tile in that biome simply inherits unmodified — the Wiki and the struct comments together support the shape of the answer but don't nail the very last step. Flagged **[I]** for that last inferential hop; everything upstream of it is **[C]**.

---

## 2. Method and sources

- `git clone --depth 1 https://github.com/DFHack/df-structures.git` into the session scratchpad, then `Grep`/`Read` directly on the XML — this is the exact repo the task specified, read locally rather than through GitHub's code-search API (which returned **zero** hits for `neighbor_hover_mm`, `find_cur_best_value`, and `T_find_results` as literal search-index queries — GitHub's code search apparently doesn't index this repo's XML data files the way a local grep does; this is worth remembering for any future desk research against this repo — **use a shallow clone, not `gh api search/code`**).
- Dwarf Fortress Wiki pages fetched live this session: `Site_finder`, `Embark`, `Biome`, `Surroundings`, `DF2014:World_generation`, `Advanced_world_generation`. Each fetch is summarized by an intermediate model (the `WebFetch` tool's own processing step), not raw HTML read directly by this research pass — treat quoted passages as high-confidence but not literally byte-verified against the page source.
- No DFHack Discord or Bay12 forum thread specifically discussing Site Finder struct internals (`find_mm`, `neighbor_hover`, or the algorithm's candidate-tracking behavior) turned up in web search. This is reported as a plain **negative finding** — "nobody has written this up," not "it wasn't looked for." Per this project's convention (`CLAUDE.md`, "nobody really does this is a valid finding"), this is stated rather than papered over.

---

## 3. `neighbor_hover_mm_*` / `warn_mm_*` / `find_mm_*`: primary-source field definitions

Read directly from `df.d_interface.xml`, the `viewscreen_choose_start_sitest` class-type block (full struct, lines 6657–6764 of the cloned `master` copy):

```xml
<int32_t name='neighbor_hover_ax'/>
<int32_t name='neighbor_hover_ay'/>
<int32_t name='neighbor_hover_mm_sx'/>
<int32_t name='neighbor_hover_mm_sy'/>
<int32_t name='neighbor_hover_mm_ex'/>
<int32_t name='neighbor_hover_mm_ey'/>
...
<int32_t name='warn_mm_startx'/>
<int32_t name='warn_mm_endx'/>
<int32_t name='warn_mm_starty'/>
<int32_t name='warn_mm_endy'/>
...
<int32_t name="find_cur_best_value"/>
<int32_t name="find_block_x"/>
<int32_t name="find_block_y"/>
<int32_t name="find_block_dx" init-value='-1' comment='to world width / 16'/>
<int32_t name="find_block_dy" comment='to world height / 16'/>
<int32_t name="find_select" refers-to='$$._parent.enabled_options[$]'/>
<static-array type-name='int32_t' name="find_param" index-enum='embark_finder_option'/>
<static-array type-name='bool' name="find_missed_param" index-enum='embark_finder_option'/>

<stl-vector type-name='int16_t' name='find_missed_metal_ore'/>
<stl-vector type-name='int32_t' name='find_param_list'/>
<stl-vector type-name='int16_t' name='find_metal_ore'/>
<stl-vector type-name='int16_t' name='skip_metal_ore'/>

<enum base-type='int16_t' name='find_results'> not a real enum
    <enum-item name='None' value='-1'/>
    <enum-item name='NoResult'/>
    <enum-item name='Partial'/>
    <enum-item name='Suitable'/>
</enum>

<int16_t name='find_ax'/>
<int16_t name='find_ay'/>
<int16_t name='find_mm_sx'/>
<int16_t name='find_mm_ex'/>
<int16_t name='find_mm_sy'/>
<int16_t name='find_mm_ey'/>
```

No inline comment on this screen explains what "mm" stands for or what coordinate frame `neighbor_hover_mm_*`/`warn_mm_*`/`find_mm_*` use directly — the acronym has to be triangulated from other structs using the same naming convention, done in §4 below.

**On `find_select`**: it carries a `refers-to='$$._parent.enabled_options[$]'` annotation — i.e. DFHack's own type-checking metadata claims this field indexes into an `enabled_options` array reachable via this struct's parent. A repo-wide grep for `enabled_options` turns up **no other definition of that name anywhere in df-structures** — it does not exist as a documented field on any struct in this codebase, including `viewscreen` (the direct base class) or any plausible container. This `refers-to` annotation is therefore either pointing at an as-yet-unnamed/unmapped field, or is stale/aspirational metadata. **Not resolvable from primary source this session** — flagged rather than guessed at, since it isn't one of the four priority questions but came up investigating `find_select` directly (the field the live session's toggle test targeted).

---

## 4. What "mm" means: the rename evidence

`df.site.xml`, `world_site` struct (the site's own persisted bounding box, unrelated to the live UI but sharing the exact naming convention):

```xml
<int16_t name="rgn_min_x" original-name='mm_sx' comment='in embark tiles'/>
<int16_t name="rgn_max_x" original-name='mm_ex'/>
<int16_t name="rgn_min_y" original-name='mm_sy'/>
<int16_t name="rgn_max_y" original-name='mm_ey'/>
<int16_t name="rgn_min_z" original-name='mm_sz'/>
<int16_t name="rgn_max_z" original-name='mm_ez'/>

<int32_t name="global_min_x" original-name='real_abs_mm_sx' comment='in embark tiles'/>
<int32_t name="global_min_y" original-name='real_abs_mm_sy'/>
<int32_t name="global_max_x" original-name='real_abs_mm_ex'/>
<int32_t name="global_max_y" original-name='real_abs_mm_ey'/>
```

`df.battlefield.xml` uses the identical `real_abs_mm_sx/sy/ex/ey` names (renamed there to plain `x1/y1/x2/y2`) for a battlefield's bounding rectangle — same convention, third independent struct.

Reading straight across the rename: `mm_s{x,y}` → `*_min_{x,y}`, `mm_e{x,y}` → `*_max_{x,y}`. **`mm` = "min/max"** — a rectangle described by its minimum and maximum corner. This is DFHack's own semantic decoding of the field, done as part of normal struct-mapping work, not this session's speculation. **[C-XML]**.

**Unit**: `real_abs_mm_sx` (the `int32`, "global" variant) is explicitly commented `in embark tiles`, as is the smaller `int16` `mm_sx` variant. Both use the same unit label; they differ in numeric range (world-tile-scale global coordinates need `int32`, whereas a single site's local rectangle fits in `int16`). Applying this directly to the viewscreen: `neighbor_hover_mm_*` and `warn_mm_*` are `int32`, matching the "global" pattern's type size; `find_mm_*` is `int16`, matching the "local/region" pattern's type size. **This type-size correspondence is the strongest available argument for reading `neighbor_hover_mm_*`/`warn_mm_*` as world-absolute embark-tile coordinates and `find_mm_*` as a coordinate local to whatever the finder's current scan block (`find_block_x/y`) is** — but no field on the viewscreen itself carries an explicit "embark tiles" or "global" comment; this final step is **[I]**, not a direct read.

`find_block_dx`/`find_block_dy`'s own comments (`to world width / 16`, `to world height / 16`) are a second, independent unit clue: the Site Finder's scan appears to walk the world in blocks sized as some fraction (`/16`) of total world width/height — i.e., an optimization that divides the whole-world scan into chunks, consistent with `find_ax`/`find_ay` + `find_block_x`/`find_block_y` together describing "where the incremental scan currently is," separate from `find_mm_*`'s "the rectangle of the current best-found candidate." **[C-XML]** for the comment text; **[I]** for the "scan chunking" interpretation of what it's for.

---

## 5. Single candidate vs. multi-square highlight: resolving the crux disagreement

**Struct shape argument** (**[C-XML]**): `find_cur_best_value` is a scalar `int32_t`, not a vector. `find_mm_sx/ex/sy/ey` are four scalar `int16_t` fields, not a vector-of-rectangles. `find_results` is a scalar enum, not a vector of per-candidate statuses. There is no vector-of-candidates anywhere in this struct. Everything the finder algorithm itself tracks live is singular. This directly supports the "single most-recently-found candidate" half of the disagreement — not an inference from naming, a direct read of the type system.

**`find_results`'s own members** (**[C-XML]**, but see caveat): `None(-1)`, `NoResult(0)`, `Partial(1)`, `Suitable(2)`. This reads as a search-progress/outcome state machine — has a search been run at all (`None`), did it fail to find anything (`NoResult`), did it find something that satisfies some but not all filters (`Partial`), or a full match (`Suitable`) — reinforcing that this is state *about the single current best candidate's fit quality*, not a count or list of results. **Caveat, stated plainly by DFHack's own annotation**: the XML tags this enum `not a real enum` — DFHack's own convention for flagging a reconstructed/inferred enum that isn't backed by an actual RTTI/symbol name in the game binary. This is DFHack's own team saying "we guessed this list from behavior," which is a meaningfully lower-confidence source than most of the rest of this struct (which comes from confirmed field layout even where names are guessed). Treat the specific four-member list as **plausible and structurally consistent, but explicitly self-flagged as reconstructed, not decompiled**.

**Wiki corroboration** (**[C-Wiki]**), from the current (`v53.16`-tagged) Site Finder page: *"The finder will then display the candidate that best fit as many as possible of the selected settings of the desired size."* Singular "the candidate." The same page separately says multiple matching sites get marked on the map: *"If there are multiple sites that match your settings, the site finder will mark all acceptable sites on the Region and World maps and allow you to examine them for yourself."* These are two different claims on the same page, not a contradiction: one best-fit candidate is what the search algorithm converges on and reports (matching `find_cur_best_value`/`find_mm_*`/`find_results`), while a broader "does this square satisfy the current filter" pass is what produces the green highlighting seen on the map, independent of which single square the algorithm currently considers "best." **This is the strongest available answer to the crux question** — it's stated on DF's own community-maintained but current-tagged documentation, and it's structurally consistent with everything the XML shows.

**`find_param_list`**: an undocumented `stl-vector<int32_t>`, no comment, no `index-enum` (unlike its sibling `find_param`, which explicitly is indexed by `embark_finder_option`). The live session found it at length 24. `embark_finder_option` (`df.region.xml`) has 22 non-`NONE` members (`DimensionX` through `Sand`, enumerated below) — **22 does not divide evenly against 24, and doesn't match either "one slot per criterion" (22) or an obvious "min+max pair per UI-visible criterion" count** without further assumptions about exactly how many of the 22 criteria are range-type (min/max) versus single-value/boolean-type in the UI. **This is explicitly not resolved** — there is no struct comment on `find_param_list` anywhere in df-structures, and the arithmetic doesn't cleanly confirm the "per-criterion min/max pairs" hypothesis the task asked about. Flagged as **genuinely unknown**, not inferred past the evidence.

Full `embark_finder_option` enum (`df.region.xml`, `original-name='find_site_param_type'`, `bay12: FindSiteParamType`) — **[C-XML]**, confirms the task's ~10-12-criteria description was an undercount of what the type actually supports (the UI likely only exposes a subset):

```
NONE(-1), DimensionX, DimensionY, Savagery, Spirit(EVIL), Elevation, Temperature,
Rain, Drainage(GEO), FluxStone(FLUX), AquiferLight, AquiferHeavy, River(OUTSIDE_RIVER),
UndergroundRiver(FEATURE_RIVER), UndergroundPool(FEATURE_POOL), MagmaPool(FEATURE_M_POOL),
MagmaPipe(FEATURE_M_PIPE), Chasm(FEATURE_CHASM), BottomlessPit(FEATURE_PIT),
OtherFeatures(FEATURE_OTHER), Soil(SOIL), Clay(CLAY), Sand(SAND)
```

---

## 6. Does the current DF UI expose "next match" cycling?

**No affirmative evidence found**; treated as a negative result, explicitly flagged rather than assumed. The current Site Finder wiki page (banner: `v53.16 · v0.47.05`, i.e. tagged as describing the present Steam-era version, with a note that "some content may still need updating" — so treat with slightly reduced confidence on completeness, not on version-correctness) documents:

- invoking the finder (`[Find embark location]` button),
- adjusting criteria (`↑`/`↓` to switch which setting is highlighted, `←`/`→` or numpad `4`/`6` to change its value),
- running the search, and
- the outcome: one best-fit candidate is displayed, and all currently-acceptable squares are separately marked on the Region/World maps.

Nowhere does it describe a next/previous/cycle key or button for stepping between multiple matches. Given finding §5 (the algorithm converges on one candidate, not a set), the absence of a "next match" feature in the documentation is consistent with there being no such feature at all — to get a different match, the implication (not stated outright, but the natural reading given everything above) is you adjust the search rectangle/criteria and re-run, rather than paging through results. **This is inference from the shape of the evidence, not a direct statement** — the Wiki never says "there is no next-match key," it simply never mentions one. Flagged per the task's instruction to say plainly when only an absence was found. The task's caution about older ASCII-era docs describing different behavior was heeded: the fetched page is explicitly version-tagged current (`v53.16`), not one of the `40d:`/`v0.31:`/`v0.34:`/`DF2014:`-prefixed historical pages that also exist on the same wiki for this topic — those were seen in search results but not used as sources here.

---

## 7. Savagery: per-tile or per-region?

Three independent pieces of evidence, read in order of directness:

1. **World generation is a continuous per-world-tile numeric field** (**[C-Wiki]**, Advanced World Generation page, exact token syntax): `[SAVAGERY:<min>:<max>:<x variance>:<y variance>]`, e.g. `[SAVAGERY:1:100:200:200]`, values 0–100, plus `[SAVAGERY_FREQUENCY:<mesh>:<0-20 weight>:...:<80-100 weight>]`. This is the same generation mechanism DF uses for elevation, rainfall, temperature, and drainage — all of which are well-established to be smoothly-varying scalar fields across the world map, not discrete per-named-region flags, with the variance/frequency parameters explicitly controlling spatial autocorrelation (how fast the value changes tile-to-tile). This by itself already argues against "uniform within a named region" as the operative model, since the other fields generated the identical way are known to vary continuously.

2. **Biome membership is confirmed fine-grained at "embark tile" resolution, finer than a world tile**, from a struct comment on `world_region_details`/`region_midmapst` in `df.region_midmap.xml` (**[C-XML]**, a documented comment, not inferred):

   ```
   In order to determine how biomes cross embark tile edges,
   the rectangle framing an embark tile is split into 4 corners,
   and 4 straight edge segments, using ranges measured in tiles...
   After this, each corner and edge segment is assigned the biome
   of one of the adjoining 4 or 2 embark tiles, based on the values
   in these arrays.
   ```

   backed by a `biome` static array documented as `17x17`, with each cell's lower 4 bits indexing "biome 1..9" using a documented 3x3 compass layout (own tile = 5, neighbors 1–4 and 6–9). This confirms biome is not resolved once per world tile and then treated as uniform — it is explicitly interpolated at a finer "embark tile" grid, with different embark tiles inside the *same* world tile capable of drawing from *different* neighboring world tiles' biomes near a boundary.

3. **The Wiki states savagery is a property biomes carry** (**[C-Wiki]**, `Biome` page): *"All biomes also have some kind of 'alignment' -- good, neutral, or evil -- and a degree of 'savagery'."* Separately (and this is the one place a fetch in this session went slightly wrong and needs a correction flagged): an earlier `Embark`-page fetch summary described "a named region... will be either good, normal, or evil" as if it were about savagery — that sentence is actually about **Alignment** (the good/neutral/evil axis), a *different* biome property from Savagery (the calm/wilderness/untamed axis), per the `Biome` page's own wording, which lists them as two separate things in the same sentence. **This is flagged explicitly as a correction of this session's own earlier evidence-gathering, not carried forward as fact** — the "uniform per named region" framing does not have a confirmed savagery-specific source; it may only be true of Alignment, not Savagery, and the two should not be conflated.

**Synthesis**: since (a) savagery is generated as a continuous, spatially-autocorrelated numeric field at the world-tile level, and (b) the biome that determines a location's savagery is itself confirmed to resolve at embark-tile granularity with cross-boundary interpolation, the composite picture supports the domain-expert user's stated belief — per-tile with local correlation, not strict uniformity — better than a strict per-named-region model does. **What remains genuinely unconfirmed**: whether the underlying numeric savagery scalar is itself recomputed/interpolated per embark tile the same way biome membership is, or whether each embark tile simply inherits one flat savagery value from whichever world-tile-level biome it resolves to (in which case the *visual* patchiness would come entirely from biome-boundary interpolation, with savagery itself still effectively a per-biome constant, just applied to a finer patchwork of biome assignments than "one biome per world tile" would suggest). Both readings are consistent with everything found this session; adjudicating between them would require either DF's actual (non-public) source or a live experiment (out of scope for this desk-research pass) — e.g., comparing `find_param`'s Savagery slot behavior against `world_region_details.biome` on a real loaded world.

---

## 8. What could not be verified, and why

- **The exact intended reading of `mm` in developer terms** ("min/max" is the only reading the rename evidence supports, but no DFHack comment or commit message spelling out "this stands for min/max" was found — it is a confident triangulation from three independent structs' rename tables, not a quoted definition).
- **Whether `neighbor_hover_mm_*`/`warn_mm_*` truly use the "global" embark-tile frame and `find_mm_*` the "local" one** — argued from `int32` vs `int16` type-size matching against `world_site`'s two analogous field pairs, but no comment on the viewscreen itself confirms this; a live read of a real in-progress site-finder scan's `find_mm_*` values against `neighbor_hover_mm_*` values for the same visible square (do they differ by a `find_block_x`/`find_block_y`-sized offset?) would settle it and was explicitly out of scope this session (desk research only, no VM).
- **`find_select`'s `refers-to='$$._parent.enabled_options[$]'` annotation** — the referenced `enabled_options` field does not exist anywhere else in df-structures under that name; not resolvable from static analysis alone.
- **`find_param_list`'s actual layout** — no comment, and its live length (24) doesn't cleanly confirm a "min/max pair per UI-visible criterion" theory against the 22-member `embark_finder_option` enum. Reported as unknown rather than forced into a tidy story.
- **Whether DF's current UI has literally zero next-match mechanism**, versus one that exists but isn't documented on the Wiki. Only a documentation gap was found, not a code-level negative proof (DF's own source is not public, so this can't be checked more directly than the Wiki plus the struct's own singular-candidate shape already argued in §5).
- **Whether the savagery scalar itself is recomputed per embark tile or only per world-tile-level biome** (§7's final unresolved hop) — needs either non-public DF source or a live in-game comparison, not desk research.
- **No DFHack Discord/Bay12 forum thread discussing any of this was found** — reported as a plain negative result (see §2), not chased further given the "desk research only" scope for this pass.

---

## 9. Net assessment

Two of the four questions (`mm` = min/max, and the single-candidate-vs-multi-highlight crux) now have strong, primary-source-grounded answers that should be treated as settled for design purposes. The DF-UI-cycling question has a clean negative result (nothing documented) that is consistent with, and reinforced by, the single-candidate finding. The Savagery granularity question has a well-evidenced partial answer — biome is confirmed fine-grained, savagery is a documented biome attribute, but the very last inferential link (does the savagery *number itself* refine at that same grain) is not nailed down by anything short of DF's own non-public source or a live test. All four are meaningfully better understood after this pass than before it; none required abandoning the "state findings honestly, flag what's inferred" discipline to get there.
