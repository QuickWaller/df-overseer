# Research: why manager work orders are not dispatching on Uniboslan

Date: 2026-10-01. Researcher (Sonnet), read-only: no code, no live access this
session. Brief: `handoffs/2026-10-01-orders-not-dispatching-research.md`.
Builds on `research/2026-10-01-quartermaster-levers.md` §1 (DFHack-source
answer to "what are `validated`/`active`") without re-deriving it; this
document adds the closed-engine-adjacent structures (`ManageWorkOrders`,
`workshop_profile`) that research did not need and the DF wiki's own account
of the validation step, then proposes read-only live checks ordered by how
likely each is to be the actual cause.

All DFHack citations are against **DFHack tag `53.16-r1`**: `orders.cpp`
fetched fresh this session from `raw.githubusercontent.com/DFHack/dfhack/
53.16-r1/plugins/orders.cpp`; `df.job.xml` and `df.building.xml` fetched from
the pinned `df-structures` submodule commit
`1dd01aad64219afa0578f1328cf15bd0c6006d5a` (the same commit
`research/2026-10-01-quartermaster-levers.md` already pinned and diffed
byte-identical against this session's own fetch of `df.job.xml`, so this is
the second independent read of that file at that commit, not a fresh guess at
version). The DF wiki (`dwarffortresswiki.org`) is used only for the closed
engine's own prose account of the Manager's validation behavior, per the
handoff's instruction, never as a struct-shape source.

## Short answer

**Most likely cause, not yet live-confirmed: Uniboslan may not actually have
a Manager appointed to it right now, despite the register's belief that it
does.** `scripts/dfhack/df-overseer-orders.lua`'s own header (written the
same day as this handoff, `:114-135`) already records a live scan
(`dfhack.units.getNoblePositions` over every unit in `world.units.active`)
that found **zero** citizens on Uniboslan holding the `MANAGER` noble
position; the one filled `MANAGER` assignment it found in
`world.entities.all` resolved, through its histfig's `unit_id`, to no live
unit at all, which is the signature of an assignment belonging to a
different site's government entity, not Uniboslan's own. This sits at direct
odds with the 2026-09-30 user report that "manager work orders work" and
with `CLAUDE.md`'s current-state line built on that report. Both cannot be
true of the same moment; the discrepancy is either (a) genuinely stale, a
Manager who was appointed and later died, left, or lost the position between
2026-09-30 and this write, or (b) the user's report described a different
fort, a different session, or a state that has since regressed. **This is
the single highest-value live check**, because DF's own wiki page for
"Manager" states plainly that once a fort passes 20 citizens (Uniboslan has
22), **no work order runs at all until the Manager validates it**, and every
symptom in the eval (`evals/live/2026-10-01-queue-and-material-deploy/
README.md`) is consistent with "there is currently no one who can validate
anything": the three weeks-old orders are `validated: true, active: false`
(validated once, presumably while a Manager existed, now stalled with
nothing re-checking them), and the brand-new order 4 never even reached
`validated: true` across 2.5 game days, exactly what "no Manager to run the
validation job" predicts.

If a live check finds a Manager genuinely appointed and present on Uniboslan
right now, the next most likely causes, in order, are: the target workshop's
own `workshop_profile` (a real, per-workshop, player-visible setting that can
ban general orders outright, cap how many it will pull, or exclude every
labor/worker DF would otherwise use, §2 below) blocking the specific job;
no citizen currently has the labor the job needs enabled; and only after
those, this repo's own order-creation path differing from a UI-made order in
some field DF needs (weakened as a leading theory, see §4, since the three
weeks-old orders were **not** made by this repo's tooling and are stuck the
same way as the new one).

## 1. What moves an order unvalidated -> validated -> active

**Verified from DFHack source, confirming and extending
`research/2026-10-01-quartermaster-levers.md` §1.** `manager_order_status`
(`df.workquota.xml:59-62`, not re-read this session, cited from the prior
research which already pinned it) is the two-bit `validated`/`active` flag.
`orders.cpp` itself (`:390-391`) reads exactly those two bits for its own
`list` output (`is_validated`, `is_active`) and nowhere else in the file
computes or sets them except on import (`:663-664`, restoring a saved
snapshot verbatim) and `recheck`/`recheck_current` (already covered by the
prior research, clears both to force re-evaluation). **DFHack itself never
performs the validate-or-activate step; it only reads and, via `recheck`,
resets the two bits for the closed engine to redo.**

**New this session, from `df.job.xml` (verified from source).** The actual
job a Manager performs to validate an order is a real, named job type:

```
1160  <enum-item name='ManageWorkOrders' original-name='MANAGE_WORK_ORDERS'>
1161      <item-attr name='caption' value='Manage Work Orders'/>
1162      <item-attr name='skill' value='ORGANIZATION'/>
1163  </enum-item>
```

(`df.job.xml:1160-1163`, pinned commit above). This is the "Manage Work
Orders" job the vanilla UI shows a Manager performing; it has a `skill`
attribute (`ORGANIZATION`) but, unlike most job types in this file, **no
`type` attribute** (contrast `MakePipeSection` two entries earlier, which
carries `type='Manufacture'` and `item='PIPE_SECTION'`), meaning DFHack's own
schema does not classify it as ordinary production; it is administrative.
This is consistent with, and gives a name to, the wiki's own account (§1.1
below) of what a Manager physically does to validate an order, but the job's
own scheduling, how often it fires, whether it requires the Manager to be
physically at the office, and what makes the engine decide to run it are all
in the closed DF engine and not resolvable from this XML alone. **Unverified
beyond the job type's existence and its skill attribute.**

Also new this session, from the same file: once a job **is** dispatched from
a manager order, two fields mark it as such, both **verified from source**:

- `job.order_id` (`df.job.xml:1772`, `int32_t`, `ref-target='manager_order'`,
  `init-value='-1'`): a live job created from a manager order carries the
  order's id here; a job not from a manager order (a direct/hand-built job)
  has `-1`. This is a direct, checkable link from "a job is currently
  running" back to "which order caused it," not previously in this repo's
  own tools per the grep this session ran (`df-overseer-orders.lua` reads
  `order.status`, never `job.order_id`; `df-overseer-stuckjobs.lua` was not
  re-read this session for whether it already surfaces this field).
- `by_manager` (`df.job.xml:1479`, `original-name='QUOTASOURCE'`, a
  `job_flags` bit): set on any job whose origin is a manager order.

Both are readable today with the same pattern `df-overseer-orders.lua`
already uses for other job/order fields (`pcall(function() return
job.order_id end)`), and give a **direct, zero-inference test for "has the
Manager ever actually dispatched anything from this fort's orders, ever,
regardless of which order"**: scan `df.global.world.jobs.list` for any job
with `order_id ~= -1` or `flags.by_manager == true`. If that scan is empty
across the fort's whole history (not just the eval's 2.5-day window), that is
strong, cheap, second-hand-free evidence that the Manager-dispatch path has
never fired even once on this fort, which would corroborate the
no-Manager-appointed theory independently of the noble-position scan.

### 1.1 The DF wiki's own account of validation

**From the wiki, treated as the closed engine's own prose description, never
as a struct source, and flagged where it goes beyond what the fetch actually
returned (the automated fetch summarized rather than quoting verbatim, so
treat wording as paraphrase, not an exact quotation, until an orchestrator
re-reads the page directly).**

- The Manager validates orders "in their office," gains experience from
  validating (not from the order finishing), and needs "ample free time" and
  to not be "called far from the office for timely order validation." This
  is the wiki's account of a real prerequisite this research cannot verify
  structurally: **a Manager who is busy with other duties, or without an
  accessible office, plausibly performs `ManageWorkOrders` slowly or not at
  all.** The office's own good-standing (this repo's `CLAUDE.md` says it is
  "built, furnished and owned by the Manager") only addresses the
  furniture/ownership side of this, not whether the Manager unit is
  currently free.
- **The load-bearing line for this fort specifically:** "once your fortress
  reaches 20 citizens, work orders will not be performed until they are
  validated by the manager." Uniboslan is reported at 22 alive
  (`CLAUDE.md` current-state line). This means Uniboslan is unambiguously
  past the threshold where validation is not optional scaffolding, it is a
  hard gate on every order, matching the eval's own observation that the
  newest order never even reached `validated: true`.
- Multiple conditions on one order are AND'd (all must hold before the order
  begins); this only matters for orders with more than one `item_condition`,
  which none of Uniboslan's four orders currently have per the eval
  (`AtMost:20:BARREL` is the only condition on order 4).
- A documented, unrelated bug: material selection can be lost if the order
  is confirmed before the player finishes picking a material. Not applicable
  here, orders are created by this repo's own tooling, which sets material
  fields before the order object is ever inserted into the live vector
  (`wo.lua`'s `create_orders`, per the prior research), not interactively.
- The wiki text did **not** state, in what this fetch returned, an explicit
  mechanism for what makes `validated` become `active` (workshop pathing,
  worker availability), only that frequency settings gate *when* a
  repeating order's conditions are next checked. **Not verified**: whether
  the wiki has a more explicit account elsewhere (a "Work Order" article
  subsection, a talk-page note) that this single fetch did not surface.

## 2. What keeps a validated order inactive: workshop_profile

**Verified from source, new this session, not covered by
`research/2026-10-01-quartermaster-levers.md`** (that research's scope was
`workorder.lua`/`orders.cpp`/`df.workquota.xml`, not `df.building.xml`).
`df.building.xml:309-319` defines a real, per-workshop struct that vanilla DF
exposes through the workshop's own query menu ("restrict general orders" /
per-labor bans a player can already set):

```
309  <bitfield-type type-name='workshop_profile_flag' base-type='uint32_t'>
310      <flag-bit name='block_general_orders' original-name='GENERAL_WORK_ORDER_BAN'/>
311  </bitfield-type>
313  <struct-type type-name='workshop_profile' original-name='workshop_profilest'>
314      <stl-vector type-name='int32_t' name='permitted_workers' .../>
315      <int32_t name='min_level'/>
316      <int32_t name='max_level' init-value='3000'/>
318      <int32_t name='max_general_orders' original-name='maximum_allowed_general_work_orders'/>
319      <bitfield ... name='flags' original-name='flag'/>
320      <static-array name='blocked_labors' original-name='general_work_order_ban_profession' type-name='bool' index-enum='unit_labor'/>
321  </struct-type>
```

(building.xml uses 1-indexed source lines here; block quoted at the file's
own 309-319, `blocked_labors` at 320 immediately after). Every real
workshop-type building embeds one of these (`profile`, found at three
locations in the file for different workshop classes, `:1300, :1592, :1669`,
not individually inspected this session for which workshop kinds carry it,
flagged unverified below). This is a **structural, player-visible, per-
workshop cause for "validated but never active" that is completely
independent of the order or the Manager**: if the workshop kind that would
produce the ordered item (a Carpenter's Workshop for `MakeBarrel`) has
`flags.block_general_orders` set, or `max_general_orders` set to `0`, or
`blocked_labors[CARPENTRY]` true, or a non-empty `permitted_workers` list
that excludes every citizen with the labor enabled, or a `min_level` above
every such citizen's skill, the Manager could validate the order and still
never have anywhere to send it. None of `orders.cpp`, `wo.lua`, or
`df-overseer-orders.lua` reads or writes this struct at all (confirmed by
the earlier grep of `orders.cpp` for `profile`/`workshop`, which returned
only unrelated hits), so **this repo currently has no visibility into
whether any of Uniboslan's workshops are configured this way.** This is a
genuine, previously-undocumented-in-this-repo gap, not a restatement of
anything in the prior research or the register.

**Not verified**: whether this fort's actual Carpenter's Workshop(s) (the
job that would fulfil `MakeBarrel`) have any of these fields set away from
default; no live read was available this session.

## 3. Candidate causes, ranked, with the read-only check for each

Ordered by expected likelihood given the evidence already in hand (the
no-Manager-found comment, the pattern of three old validated-but-inactive
orders plus one never-validated new one, and the wiki's 20-citizen gate),
most likely first.

1. **No Manager is actually appointed on Uniboslan right now**, despite the
   register's belief. Check:
   ```
   dfhack-run lua "
     for _,u in ipairs(df.global.world.units.active) do
       local ok, ps = pcall(dfhack.units.getNoblePositions, u)
       if ok and ps then
         for _,p in ipairs(ps) do
           local ok2, code = pcall(function() return p.position.code end)
           if ok2 and code == 'MANAGER' then
             print(u.id, dfhack.units.getReadableName(u))
           end
         end
       end
     end"
   ```
   (Reproduces exactly `manager_appointed()` in
   `df-overseer-orders.lua:280-293`, but printing identity instead of a
   boolean, and can be run directly as `orders.list`'s own
   `manager_appointed` field via the MCP tool, which already computes this
   on every call, no new code needed: `dfmcp` call `orders.list`, read the
   `manager_appointed` key.) If false or empty, this is very likely the
   whole answer, and the fix is re-appointing a Manager, not a tools change.

2. **No job has ever actually been dispatched from a manager order on this
   fort.** Check, reading the two new fields from §1:
   ```
   dfhack-run lua "
     local n = 0
     for _,j in ipairs(df.global.world.jobs.list) do
       local ok, oid = pcall(function() return j.order_id end)
       if ok and oid and oid ~= -1 then n = n + 1
         print(j.id, oid, df.job_type[j.job_type]) end
     end
     print('manager-sourced jobs currently queued:', n)"
   ```
   A zero count during a supervised unpause (not just at one paused instant)
   corroborates cause 1 independently: it means the dispatch path has never
   fired, not just that it hasn't fired for order 4 specifically.

3. **A workshop-side block** (`workshop_profile`, §2) on whichever workshop
   kind fulfils the job in question. Check, for every building of the
   relevant kind (Carpenter's Workshop, for `MakeBarrel`):
   ```
   dfhack-run lua "
     for _,b in ipairs(df.global.world.buildings.all) do
       if b:getType() == df.building_type.Workshop
         and b.type == df.workshop_type.Carpenters then
         local p = b.profile
         print(b.id, 'block_general_orders=', p.flags.block_general_orders,
           'max_general_orders=', p.max_general_orders,
           'min_level=', p.min_level, 'max_level=', p.max_level,
           'permitted_workers_n=', #p.permitted_workers,
           'CARPENTRY_banned=', p.blocked_labors.CARPENTRY)
       end
     end"
   ```
   (Field/enum names not independently confirmed against this exact
   install's Lua bindings this session, since no live access; read
   conservatively with `pcall` around each field the way this repo's other
   tools already do, and treat a binding error as "not this struct shape
   here," not as a confirmed negative.)

4. **No citizen currently has the relevant labor enabled**, so even a
   validated, active order has no eligible worker. Check via this repo's own
   existing tool, `labor` (per `research/2026-10-01-quartermaster-levers.md`
   §2's `autolabor list`/`enabled-counts` path), for `CARPENTRY` (barrels) or
   whichever labor the stuck order's job type needs.

5. **The 20-citizen validation gate itself, confirmed rather than assumed.**
   Uniboslan's population (22 per `CLAUDE.md`) is already past the wiki's
   stated threshold, so this is not a candidate *cause* by itself, it is
   confirmation that validation is mandatory here and cannot be skipped by
   population size; listed to close off "maybe it's just small-fort laxness"
   as a theory. Check: current population count, already tracked and cheap
   (`nobles`/vitals tooling this repo already runs each cycle).

6. **This repo's own order-creation path differs from a UI-made order in a
   field DF needs.** Weakened as a leading theory by the eval's own evidence
   (orders 0-2 predate `df-overseer-orders.lua`'s 2026-10-01 generalisation
   and are stuck in the identical `validated: true, active: false` shape as
   the new tool-made order 4), but not eliminated, since **all four could
   share one upstream cause unrelated to which tool made them** (i.e., causes
   1-4 above would explain all four identically, which is the simpler
   explanation Occam's-razors this one down the list). If causes 1-4 are all
   ruled out live, the next check would be exporting one of the old orders
   via `orders export`, comparing its full field set (including any DFHack
   does not expose to `create_orders`' JSON shape) against a freshly
   tool-made one for an unexpected structural difference.

## Not verified

- Whether Uniboslan currently has a Manager appointed at all: the strongest
  evidence in hand is `df-overseer-orders.lua`'s own header comment
  (2026-10-01, same day as this handoff), which is a live finding from that
  stream, not independently re-run this session (no live access). This
  research treats that comment as evidence, not as its own confirmation, and
  candidate-check 1 above is exactly how to re-confirm it.
- The wiki fetch for "Manager" and "Work order" was summarized by an
  intermediate model (`WebFetch`'s own processing step), not read verbatim
  by this researcher; wording under §1.1 is paraphrase of that summary, not
  a direct quotation, and should be treated as directionally reliable but
  not citation-grade until an orchestrator re-reads the source pages
  directly if exact wording ever matters.
- Whether `ManageWorkOrders`'s scheduling (how often, whether it requires
  the Manager to be physically at the office building versus just
  "employed and free") is knowable from DFHack source at all; nothing in
  `df.job.xml`, `orders.cpp`, or `wo.lua` schedules or triggers this job
  type, consistent with `research/2026-10-01-quartermaster-levers.md`'s own
  finding that no DFHack source reads or checks a Manager noble position
  anywhere in the order-creation path. This is closed-engine behavior.
- Which specific workshop kinds embed `workshop_profile` (found at three
  struct locations in `df.building.xml`, `:1300, :1592, :1669`); only the
  struct's own field list was read this session, not which of those three
  locations covers a Carpenter's Workshop specifically. The candidate-3
  check above should confirm this live rather than assume it from the
  field name.
- Whether `job.order_id`/`by_manager` are already surfaced by any existing
  tool in this repo (`df-overseer-stuckjobs.lua` was not re-read this
  session for this specific field); if they already are, candidate-check 2
  above may already be one call away rather than needing new Lua.
- Everything in this document is a source-and-wiki read, not a live-fort
  observation, per the handoff's read-only constraint. Every check in §3 is
  a proposal for the orchestrator to run, none was executed this session.
