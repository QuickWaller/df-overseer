# Switching crop choice to DFHack `autofarm` (2026-10-09)

Research for the register row of 2026-10-09 ("switch farming to autofarm"). Read-only: installed plugin
files and docs on VM 103, the upstream plugin source at tag `53.16-r1` (the install is `53.16-r1.1`, not
diffed), and read-only live probes of the running fort. Nothing was enabled, set or run (`autofarm runonce`,
`enable`, `threshold` and `default` all write and were not called). The offline wiki mirror was not consulted.

Confidence tags: **[src]** read from upstream source `plugins/autofarm.cpp` @ `53.16-r1`; **[install]** read
on the install itself (docs, raws, files); **[live]** read from the running fort today; **[inferred]**.

## Answer first

1. **Autofarm only ever writes the CURRENT season's slot of each built plot, and only from stock counts.**
   It cannot be told "plant plump helmet"; it plants whichever eligible crops have stock below threshold, and
   it fallows (sets the slot to -1) a plot when no eligible crop is below threshold. At one plot it is a
   thin, mostly-redundant layer over what we do today, so **the switch buys nothing until there are two or
   more plots, and at default settings it would immediately pull our only plot off plump helmet.**
2. **Do not enable it with defaults.** Live today (spring, tick 2795): the one plot (id 7, underground,
   plump helmet all four seasons) holds plump helmet stock 52, which is at or above the default threshold of
   50, so plump helmet would be ineligible, and sweet pod, quarry bush and dimple cup (0 stock each, seeds
   in hand, spring-plantable) would be eligible. Autofarm would flip the plot to sweet pod (lowest raw
   index among the eligible) on its first cycle. Only plump helmet is edible raw among the six underground
   crops [install]. A default-threshold enable is a food regression.
3. **Required threshold data for a safe switch at the current fort:** plump helmet threshold set high enough
   to stay eligible whenever the fort should be farming, every other seed-bearing crop set to **0**
   (`count < 0` is never true, so it is never planted). With that, autofarm behaves exactly like today at one
   plot, and starts to do real work (even split across eligible crops, season gating) only when the user
   adds plots or raises a second crop's threshold. The numeric value for plump helmet is a **user decision**:
   the doctrine entry on cover targets (`cover-target-not-yet-settable`) forbids inventing one, and
   resupply lead time is still not computable on this install. 
4. **Retire `farm.set-crop` from every agent surface in the same change** (only the Overseer holds it as a
   direct write; the Quartermaster holds it through `crop_plan` proposals the conductor executes). Plan in
   section 3.

## 1. What autofarm does on this install

### Commands and config [install, src]

`hack/plugins/autofarm.plug.so` and `hack/docs/docs/tools/autofarm.txt` are present. Commands (docs match the
source's argument parser, confirmed by reading both):

| Command | Effect | Writes? |
|---|---|---|
| `enable autofarm` / `autofarm enable` / `disable` | Turn the per-cycle scan on or off; persists the flag | yes |
| `autofarm status` (or bare `autofarm`) | Prints Active/Stopped, per-crop `limit N current M` for crops seen last cycle plus any with a set threshold, and `Default: N` | no |
| `autofarm default N` | Default threshold (initial value 50) | yes |
| `autofarm threshold N CROP [CROP...]` | Per-crop threshold; CROP is a plant raw id (upper-cased by the command), must be a plant with the SEED flag, else `CR_WRONG_USAGE` and the whole command stops at the first bad id (earlier ids in the same call stay set) [src] | yes |
| `autofarm runonce` | One pass without enabling; **this writes plot slots** | yes |

Needs a loaded fort (refuses otherwise). No per-plot or per-season config exists. No crop-priority
weighting exists. `getplants -f` lists ids per the docs (not run).

### The algorithm, exactly [src]

Run every 53 world ticks (`frame_counter` diff) while enabled, and immediately on load (the timestamp resets
to 0). Each pass:

1. **Seeds in stock** = SEEDS items minus those flagged dump, forbid, garbage collect, hostile, on fire,
   rotten, trader, in building, construction, artifact. A crop is a candidate only if it has at least one such
   seed (a single seed counts; there is no seed floor).
2. **Plantable now** = has SEED flag, not a tree, and the **current season flag** is set, and, if
   `cur_season_tick + growdur * 10` runs past a season (10080 ticks), the following season's flag must be set
   too, repeated until the harvest lands. This is real season gating our tool does not do.
3. **Stock count** = PLANT items plus PLANT_GROWTH items with that material, same exclusion flags, summed by
   stack size, anywhere in the fort. Items in barrels or stockpiles count; items in a building (a still,
   a workshop) do not; rotten does not; drinks and seeds are not counted.
4. **Eligible crop** = plantable now and `stock < threshold` (per-crop threshold, else default).
5. **Group plots by biome.** A built plot (`flags.exists` only; plots under construction are skipped) is
   `SUBTERRANEAN_WATER` if its centre tile's designation has the `subterranean` bit, otherwise the surface
   region's biome. A crop is eligible for a plot only if the crop's raw carries the matching `BIOME_*` flag.
   So underground plots draw only from underground crops, surface plots only from surface crops. This
   respects underground vs surface automatically (better than our `outside` classification, but note it keys
   on the `subterranean` bit, not on roof status: a roofed room on the surface counts as surface).
6. **Assign** (`set_farms`) per biome group, **current season slot only**: if no crop is eligible, every plot's
   slot is set to -1 (fallow); otherwise it spreads eligible crops over plots as evenly as possible while
   changing as few plots as it can (a plot already on an eligible crop keeps it). Ties go in raw-index
   order (the eligible set is a `std::set<int>`), so with fewer plots than eligible crops, the lowest-index
   crop(s) win and there is no rotation by deficit or by priority.
7. Other seasons' slots are never touched. After a season turns, the next cycle (within 53 ticks of
   running time) rewrites the new current season. Slots of other seasons keep whatever was last written
   (ours today: plump helmet), so **`farm.list` shows four seasons but only the current one is autofarm's
   truth.**

Verified details, same source: it only reads and writes `building_farmplotst.plant_id`, the same field our tool
writes, so the two genuinely fight, last writer wins, and autofarm rewrites within 53 ticks. [src, plus the
survey's earlier finding]

### Persistence [src, live]

Stored in the **world save** as persistent site data, not in `dfhack-config`: keys `autofarm/enabled`,
`autofarm/default_threshold`, and one `autofarm/threshold/<PLANT_ID>` per set crop (rewritten wholesale on
every `save_state`). `plugin_enable` and every `default` or `threshold` call save immediately; they land in a
save file only when the game next saves (our in-game quicksave repeat is 7 days; the survey already noted the
save-reload window). Loading a save restores enabled, default and thresholds; a threshold naming a plant not
in the raws is ignored with a warning. Same class as the other plugins: **a reload of a save written before
the enable silently drops it, so the intended state belongs in the on-load init file too** (it is idempotent:
`enable` of an enabled plugin and re-setting the same thresholds change nothing). Live today: the persistent
entries `autofarm/enabled` and `autofarm/default_threshold` read **nil** in the loaded save [live], and
`autofarm status` prints "Stopped. Default: 50", so autofarm has never been enabled on this fort.

Ordering inference [inferred]: `plugin_load_site_data` resets thresholds and loads saved ones; the init file
then re-applies ours. Same pattern as the existing `enable suspendmanager` line, which is already relied on.
Not proven for autofarm on a load.

### Known bugs and quirks [src; no upstream issue tracker was checked]

- **Paused game, no passes.** The cycle is driven by `frame_counter`, which only advances with simulation
  ticks [inferred]; the fort is paused most of the time. `runonce` is the only way to force a pass while
  paused. A newly enabled autofarm does nothing until time runs.
- **Mid-season threshold flips can hot-swap a plot** whose crop is not yet planted; crops already planted are
  unaffected, only future planting jobs follow `plant_id`.
- **No seed-aware or yield-aware logic.** Plants are counted wherever they are, including in barrels
  awaiting brewing; brewing consumes plants, so stock drops and it plants more (a feedback it does not
  model).
- **Threshold is a plant count, not a seed count.** Our doctrine seed floor (30 per crop, `seed-stock-never-falls`)
  has no direct autofarm expression. It is a hard floor on seeds; autofarm will plant a crop while a single seed
  exists and will not stop at a floor. The floor remains the job of the brewing/orders policy and of
  `ban-cooking all` (already restored 2026-10-09); autofarm cannot hold it.
- `setThresholds` calls `atoi` with no validation: `autofarm threshold abc X` sets 0.
- The control panel registry lists `autofarm` as an opt-in automation entry and an optional pig-tail
  threshold, neither default-on [install].
- `news.txt` shows only documentation and control-panel entries for autofarm in recent releases. No
  functional bug fix is recorded for it. Absence of evidence only.

### Live read today [live]

Season spring (0), tick 2795. One built plot, id 7, subterranean true, outside false, all four seasons plump
helmet. Seed stock (excerpt): plump helmet 59, sweet pod 5, quarry bush 5, dimple cup 5, pig tail 5, cave
wheat 5, plus many surface crops (lettuce 36, wild carrot 58, kaniwa 18 and more). Plant stock: plump helmet
52, everything else underground 0. Spring flags: pig tail and cave wheat are summer/autumn only (not
plantable now); sweet pod, quarry bush, dimple cup and plump helmet are. Surface crops are irrelevant while
the only plot is underground.

Raws [install, `plant_standard.txt`]: plump helmet is EDIBLE_RAW and EDIBLE_COOKED, brewable, seed-returning.
Sweet pod, cave wheat, pig tail and dimple cup have no raw-edible structural material (they brew, mill or
spin); quarry bush yields leaves and oil. So only plump helmet feeds the fort directly.

## 2. Conflicts and how to retire or narrow them

### What writes crops today [repo]

| Surface | What it does | Holder |
|---|---|---|
| `farm.set-crop ID SEASON CROP` (`scripts/dfhack/df-overseer-farm.lua`, `set_farm_crop`) | Writes `plant_id[season]`, validates seed owned and biome class, reads back | **Overseer** direct write (`agents/overseer/tools.yaml` write block). Architect and Quartermaster list it under `deny` |
| `crop_plan` proposal (QM vocabulary, `dfqueue/schema.py`) | Agent files it, the Overseer rules, the conductor executes `farm.set-crop` | Quartermaster files; `dfqueue/action_tools.yaml` stage `orders` lists `farm.set-crop` and type `crop_plan`; `dfqueue/step_identity.yaml` lists `farm.set-crop: [id, season]`; `conductor/policy.yaml` and `dfqueue/plan_policy.yaml` list `crop_plan` under `stocks` |
| Quartermaster `role.md` and `tools.yaml` | Charter text for `crop_plan`; `farm.list` and `farm.find` read tools | read-only |
| Doctrine | `plump-helmet-use`, `seed-stock-never-falls`, `seed-break-even`, `cooking-plants-costs-seeds` | read by the Consultant only |

The current fort has one plot and plump helmet in all four seasons: **no agent has needed to change a crop**
since 2026-09-17. So retirement costs no behaviour today.

### Retire `farm.set-crop` (single writer)

Recommended, in one change, with the autofarm enable:

1. **Overseer allowlist:** move `farm.set-crop` from the write block to `deny` with reason "autofarm owns crop
   choice; thresholds are data". `docs/STATE.md`'s generated per-role tool counts and any test that counts the
   Overseer's tools need regenerating (the Overseer's write count drops by one; role-count tests were
   measured 2026-10-02).
2. **Quartermaster `crop_plan`:** retire the type. Touch: `dfqueue/schema.py` (`CROP_PLAN`,
   `QUARTERMASTER_TYPES`), `dfqueue/action_tools.yaml` (`orders.types`, `orders.tools`), `dfqueue/step_identity.yaml`,
   `conductor/policy.yaml` and `dfqueue/plan_policy.yaml` (`stocks`), the QM `role.md` bullet and
   `agents/quartermaster/tools.yaml` comments, `dfmcp/tests/test_quartermaster_roster_enabled.py` (it already
   asserts `farm.set-crop` denied), `dfqueue/tests/test_render.py` (one fixture uses it). Add `farm.set-crop` to
   the `retired:` list in `dfqueue/action_tools.yaml` (its definition: mutating tools held by no proposing role
   and no allowlist). This is the larger piece; a cheaper interim is to leave the type in the schema but remove the
   tool from the `orders` stage so a filed `crop_plan` cannot execute, and say so in the role charter. Prefer the full
   retirement: a type nothing can execute invites filing dead proposals.
3. **Keep the Lua `set-crop` verb** in `df-overseer-farm.lua` and `TOOLS.yaml` as an operator/break-glass entry
   (the survey and the register treat tools as ours to keep; deleting it removes the live-verified read-back
   guard for no gain). Mark it "not for agents while autofarm is enabled, it is overwritten within 53 ticks".
4. **`farm.list`** stays as the read tool, but its description should say that only the current season's slot
   reflects autofarm, and that -1 (decoded as no crop, per the file's own unresolved-index handling at about
   line 616) is a normal fallow state. Check that the decoder returns something clean for -1 rather than an
   error: it is documented as "never guessed" for -1, but this was read, not run with a -1 slot [inferred].
5. **`farm.find`** stays; its "fort-owned seeds valid here" report is still useful for siting a plot (the Architect).
6. **Consequence for the seed-floor doctrine:** it cannot be expressed in autofarm. Keep it as a doctrine rule,
   enforce through the brewing orders and `ban-cooking`, and add a doctrine entry that "autofarm plants any crop
   with a seed in stock and stock below threshold; threshold 0 means never".

### Which doctrine rules still matter, and how they map [analysis]

| Rule | Maps to autofarm? | How |
|---|---|---|
| `plump-helmet-use` (food and drink) | Yes, as thresholds | plump helmet is the only raw-edible underground crop: give it the high threshold, others 0 |
| `never-cook-seed-items`, `seed-stock-never-falls`, `cooking-plants-costs-seeds` | No | seed floor is a seed-count rule; autofarm has no seed floor. Stays with `ban-cooking all` (already in the init file) and brewing |
| `brew-only-refuted`, `dwarves-must-drink` | Indirect | food versus drink split is a brewing-order matter; autofarm counts plants, so drink-only crops (cave wheat, pig tail) should stay 0 until a second plot and a need exist |
| seed break-even (1/Y of harvest to brewing) | No | same as above |

### Threshold data

A threshold is one line per crop. Put the lines **in the deployed init file** (it is already the managed,
idempotent, per-load data, deployed through `infra/deploy-manifest.yaml` target `vm103-dfhack-init`), with
the rationale in a doctrine entry that cites the research and the user's value. A separate YAML rendered into
the init file would be more "data" but adds a generator for six lines; not recommended now. The "next
instance costs one data entry" test passes: a new crop is one `autofarm threshold` line, no code.

Proposed shape for the current fort (values for the user, not invented here):

```
enable autofarm
autofarm default 0                      # every crop not named below is never planted
autofarm threshold <USER_VALUE> MUSHROOM_HELMET_PLUMP
```

Setting the **default to 0** is the safest data shape: any crop not explicitly named is ineligible, so a newly
gathered seed type (the fort holds seeds for 18 crops today, mostly surface ones) can never be planted by
accident. Combined with a high plump-helmet threshold, a one-plot fort never leaves plump helmet unless the
fort is genuinely full of them, in which case the plot lies fallow (a real behaviour change from today:
plump helmet is always planted now). If the user prefers "always plant", use a very large threshold. The
number is the user's call, the doctrine's resupply-lead-time rule applies.

At two or more plots, the user can raise a second crop (for example pig tail for thread) above 0 and autofarm
splits plots; this is the point where the switch pays for itself.

## 3. Minimal build plan

Order matters: the allowlist retirement and the enable must land together, otherwise two writers coexist.

1. **Init file** `infra/dfhack-init/onMapLoad_overseer_plugins.init` exists on main (suspendmanager, autoslab,
   autolabor, ban-cooking). Add the three lines above with a comment citing this report. **It is not on the
   VM yet** [live: `dfhack-config/init/` lists only the host's own `onMapLoad.init`], and the manifest
   comment says the first deploy's writability and the extra file being run are unconfirmed. So the live
   path today is: deploy that file (user's standing deploy authority covers it), confirm DFHack runs it on
   the next map load, and also apply by hand once now so the current session needs no reload.
2. **Order of operations on the live fort (paused, one change at a time):**
   a. `autofarm default 0`, `autofarm threshold <value> MUSHROOM_HELMET_PLUMP` (writes persistent data, no
      effect on plots while disabled).
   b. `autofarm status`: expect Stopped and the thresholds listed.
   c. `autofarm runonce` (writes; the single plot, spring): expect plot 7 spring still plump helmet when
      stock is below the value, or -1 when at or above it. Read back with `farm.list`. This is the
      safe dry-run of the policy, since runonce does not enable.
   d. `enable autofarm`; quicksave (the survey already established plugin state is only durable once a
      save writes it); confirm `autofarm/enabled` reads 1 in the saved persistent data.
3. **Code and data:** allowlist and proposal-type retirement as in section 2; regenerate `docs/STATE.md`
   tool counts; update `scripts/dfhack/TOOLS.yaml` `set-crop` and `list` notes; one new doctrine entry
   ("autofarm: threshold is a plant count; 0 is never; seed floor is not expressible").
4. **Optional read tool, deferred:** a `farm.autofarm-status` read (wrapper over `autofarm status` through
   `dfhack.run_command_silent`, which works from Lua and returned the expected text today [live]) so the
   Quartermaster can see limits and current counts. Not needed to ship. **Do not add an agent threshold
   write tool in v1**: it would re-create the multiple-writer problem at a different layer, and the user's
   decision is "set thresholds once". If the user later wants agent-set thresholds, it is one tool with a
   crop argument and a number, per the generalisation rule.
5. **Live checks after enable [to run]:**
   - Spring to summer rollover (or a forced season check by reading `plant_id` for the new season within a
     minute of running time): confirm the new season's slot is set by autofarm and no agent call is needed.
   - Seed floor unaffected: seed stock of plump helmet does not drop below its start across a harvest.
   - `farm.list` shows -1 handled when the stock exceeds the threshold (set the threshold low once to
     provoke a fallow, then restore; this is a real write, needs the user's say).
   - Reload an older save and confirm the init file re-applies the enable and thresholds.

## Not verified

- **Nothing was run that writes.** `runonce`, `enable`, `default` and `threshold` are all unexecuted; the
  per-season rewrite, the fallow `-1` path and the "keeps current crop when eligible" behaviour are read
  from source, not observed.
- The install is `53.16-r1.1`; source read at `53.16-r1`. Not diffed. The compiled `autofarm.plug.so` was not
  disassembled.
- Whether `frame_counter` advances while the game is paused (affects whether autofarm runs paused): inferred
  that it does not.
- Whether `farm.list` decodes a -1 slot cleanly: read, not run with -1.
- That DFHack runs `onMapLoad_overseer_plugins.init` and that the plugin's load-state ordering lets the init
  thresholds win: unproven for this file; the first-deploy check is still open.
- No upstream issue tracker or changelog beyond the install's `news.txt` was searched for autofarm bugs.
- The offline wiki mirror was not consulted; plant season and biome data came from the install's raws.
- Numeric thresholds: deliberately not proposed (doctrine forbids inventing a cover target).
