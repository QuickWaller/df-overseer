# Handoff: build the farm plot and still for real, plant plump helmets

**Dispatched** 2026-09-17 by the orchestrating session. **Agent:** `executor`,
Sonnet. **User go-ahead:** "go for both i approve" (2026-09-17), for building
the farm plot and still and planting, including the short supervised unpause
needed to make the work happen. **Peer check-in:** no other session on this
repo or home-lab; one sibling executor is building tools locally (no fort
writes) and must be told before you mutate.

## Why

Drink is solved (`WaterSource` zone, register 2026-09-17). **Food is not:** 24
units, no farm plot, no still, no kitchen. The farm and still tools were
deployed today and verified by dry run only. This stream runs them for real,
the first agent-built production in this fort.

Verified today: all six fort seed types are subterranean, so the plot must be
underground; `farm find` reports **1 candidate at z168** (the existing dug
room) with all six crops valid, and 5 surface candidates with none. The fort
holds **59 seeds, 34 plump helmet**; plump helmet grows in all seasons, 25
days, and brewing one plant gives 5 drinks and 1 seed back
(`doctrine/seed.yaml`). Fort has 15 barrels; brewing needs an empty barrel or
pot per job.

## Read first

`CLAUDE.md`, `docs/TRAPS.md`, `doctrine/seed.yaml`,
`handoffs/2026-09-16-farm-and-still-tools.md` and its Result (what each command
does, its dry-run behaviour), `handoffs/2026-09-17-farm-tools-deploy.md` Result
(what is live), `handoffs/2026-09-17-water-source-zone-test.md` Result (the
supervised-unpause envelope you are repeating), `research/2026-09-17-seed-ratios.md`
(§ on planting and yield), `blueprints/README.md`.

## Do

1. **Pre-state, read-only:** paused, tick (expect 222477), FPS 10, 15 citizens,
   zone 3 present, `stocks food-drink` and `stocks seeds`, existing buildings,
   citizens holding PLANT and BREWER labors, barrels, seeds by type. Record it.
2. **Farm plot, for real.** `farm find` near the "Embark Site" landmark, pick
   the z168 candidate, dry-run, then build. Verify live: a `building_farmplotst`
   exists, its footprint, and that it is where the dry run said.
3. **Crop, for real.** `farm set-crop` plump helmet **for all four seasons** on
   that plot (the tool writes `plant_id[season]`; this write has never run
   live). Verify all four seasons read back as plump helmet.
4. **Still, for real.** `workshop find` for a still, prefer a candidate at z168
   near the plot and the stockpile; dry-run, then build. It will need a
   building material and a worker, so expect it to be a **job**, not an instant
   building: report the job created and what it wants.
5. **Labors:** make sure at least two citizens hold the planting labor, and one
   holds brewing, using the deployed `labor set-labor` (which excludes the labor
   from autolabor fort-wide, by design: say which labors you changed). Do not
   touch any other labor.
6. **One supervised unpause**, exactly the earlier envelope: script on the VM
   with `nohup setsid`, `trap` re-pausing on any exit, FPS 10, **450 s ceiling**,
   stop conditions: citizens below 15, any thirst at or above 45,000, focus not
   `dwarfmode`, tick not advancing. **Success stop:** the plot shows planted
   tiles (`building_farmplotst` seeds planted / `job_type.PlantSeeds` completed)
   **and** the still is built. Sample every 15 s: tick, jobs (type, worker,
   building), plot state, still build progress, citizen count, any new report.
7. **After re-pause:** read back plot (crop per season, planted), still
   (built or still a job, what it lacks), seeds by type, food and drink units,
   citizen count and any deaths or drowning reports. **Do not save.**

## Constraints

- **Nothing else changes.** No dig, no other building, no zone, no burrow, no
  trade, no DF restart, no quicksave.
- If a build or write fails, **stop and report**; do not improvise a different
  building or a manual struct write. A designation or building can be cancelled
  or removed afterwards, which is why this is reversible; keep it that way.
- Watch for the two known risks in your samples and stop if either appears: a
  citizen at z168 in deep water going unconscious or missing, and a drop in
  citizen count.
- Never set DFHack globals (`local` only). Multi-line Lua goes in a file run
  with `dfhack-run lua -f`. Keep probes light. Delete `/tmp` files both ends.
- VM access: `.env` keys `DF_VM_IP` (strip any `/24`) and `DF_SSH_KEY`, user
  `df`; those keys only. No hostnames, addresses or tokens in what you write.
- If the harness refuses the unpause, stop and report; do not route around it.
- Do not edit `Working.md`, `decisions/`, `ROADMAP.md`, `CLAUDE.md`, `memory/`,
  `research/`, `doctrine/`. **Do not commit**: append your Result to this doc.

## Touched surfaces

VM 103's fort (one farm plot, one crop assignment, one still, up to three labor
writes, one supervised unpause); this doc.

## Report back

Pre-state and post-state side by side. Each command run, its dry run, its real
result, and the live read that confirms it. The unpause window (ticks, wall
time, why it stopped). Whether anything was planted and whether the still was
built; if not, exactly what the fort is waiting for. Labors changed. Any
deaths, drownings or cancellations. What you verified by execution versus
inferred.
