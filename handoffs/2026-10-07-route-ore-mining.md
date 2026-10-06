# Handoff: route ore mining so the ore-exposed wake can be acted on

Date: 2026-10-07. **Executor, Sonnet, worktree. Offline; no deploys.**
First: `git merge --ff-only main`.

## Why

Live, 2026-10-07, first cycle after the rooms cutover (deploy 2b): the
ore-exposed wake told the Architect "mine with construction.mine-vein-site
site-5", and it passed (pass-0001): the tool is not in the rooms group of
`dfqueue/action_tools.yaml`, so no routed proposal can name it, and it has no
`execution:` data in `scripts/dfhack/TOOLS.yaml`, so the conductor could not
run it. It still sits on the Overseer's allowlist (unrouted). Result: exposed
ore in bedroom walls blocks the finish phase (Architect charter) and nothing
can mine it. User's call 2026-10-05: exposed ore is mined.

## Scope

- `scripts/dfhack/TOOLS.yaml`: `execution:` data for
  `construction.mine-vein-site` (and `construction.mine-vein` if cheap, it is
  already in the rooms group without it), modelled on the three existing
  entries (`blueprint` apply/release/reserve) and docs/CONDUCTOR-EXECUTION.md
  2.3: verdict, dry_run_echo, handle_args (site), preview_fields,
  nothing_applied. Read the Lua return shape in
  `scripts/dfhack/df-overseer-construction.lua` for the field names, do not
  guess them.
- `dfqueue/action_tools.yaml`: add `construction.mine-vein-site` to the rooms
  group (`dig_order` proposals may name it). Remove it from
  `agents/overseer/tools.yaml` (the routed-tool test requires it); overseer
  becomes 81. Update the counts in `docs/STATE.md` and the count tests.
- `agents/architect/role.md` already says to propose the mining first; check
  it names the proposal type (`dig_order`) and the step shape; one line fix
  only if wrong.
- Check the conductor's run_step path can execute it end to end in tests
  (dry run at filing, real run, nothing_applied, observe). Add tests.
- If anything here needs a design call (for example, the tool's return has no
  usable verdict field), stop and write it in the Result rather than invent.

## Rules

Touched surfaces: `scripts/dfhack/TOOLS.yaml`, `dfqueue/action_tools.yaml`,
`agents/overseer/tools.yaml`, `agents/architect/role.md` (one line at most),
`docs/STATE.md`, tests, this handoff. Public repo: no hostnames, IPs or
tokens. No em dashes. No attribution lines. Commit after each milestone. Do
not write Working.md, DECISIONS.md, memory or INDEX.md. Full ambient
`python -m pytest` (lupa on PYTHONPATH) and `dfmcp/tests` in `.venv-dfmcp`
green.

## Result

Done offline on branch worktree-agent-a76783a21022f6c51. No deploys, no live VMs.

- `scripts/dfhack/TOOLS.yaml`: `execution:` for `construction.mine-vein-site`
  (`handle_args: [site_id]`) and `construction.mine-vein` (no handle arg, its
  ZONE_ID is an integer). Both: `verdict: {refused_if_true: [refused, held]}`,
  `dry_run_echo: dry_run`, `preview_fields: [ore_tiles_found, already_open,
  refused, held]`. No `issues_handle`, `progress` or `landed`: a step with no
  handle is done once issued (observe), and nothing resolves an Uncertain call
  by a read. Field names taken from the Lua return in `mine_vein`.
- `dfqueue/action_tools.yaml`: `construction.mine-vein-site` added to the rooms
  group. `construction.mine-vein` had already
  left the Overseer; the site tool is removed from `agents/overseer/tools.yaml`.
  Overseer is 81. Count updated in `docs/STATE.md`,
  `dfmcp/tests/test_gotchas_tools.py`, `dfmcp/tests/test_queue_cited_facts.py`;
  `dfqueue/tests/test_stage2a.py` now uses `construction.build` as its
  "unrouted tool the Overseer keeps" (the old one is routed now).
- `agents/architect/role.md`: the mining line now names the `dig_order`
  proposal and the arg names (`site_id`, `zone_id`).
- Tests: `tests/test_construction_lua_logic.py` runs the declared verdict on
  the REAL Lua output (clean ore passes, unclassifiable tile refuses, reservation-held
  tile refuses, unknown site refuses, echo mismatch invalid). `dfmcp/tests/test_executor_run.py`
  runs a `dig_order` mining step end to end through the conductor (filing dry
  run with preview, real run, no handle, observe done, not re-runnable;
  refusal at filing on held or refused; override arg rejected).
- Results: ambient `python -m pytest` 3198 passed, 3 skipped, 1 failed, the
  known flaky `test_concurrent_raw_appends_without_serialization_can_collide`,
  which passed alone on rerun; `dfmcp/tests` in `.venv-dfmcp` 929 passed.

Design notes for the orchestrator (nothing invented, none blocking):

1. The Lua return has no `ok` field, so there is no positive verdict path; the
   verdict is refusal-only on the `refused` and `held` lists (non-empty list is
   truthy). The reason text shown to the Architect on refusal is the generic
   "refused is set" or "held is set", not the per-tile strings, because the
   `reason` path must be a string and these are lists. A small Lua field
   (e.g. `blocked_reason`) would give a better message.
2. `held` is treated as a refusal. A site's own walls sit inside its own
   reservation, so a mining step without `res_id` (the site's reservation) is
   held on every ring tile and refused at filing. The Architect charter does
   not tell it to pass `res_id`. Probably needs a charter line (or the
   Architect reading the site's reservation from `blueprint.sites`), a
   judgment call left to the orchestrator. `res_id` is accepted as a step arg
   (only `override` is blocked).
3. `nothing_applied` is deliberately undeclared: a real run designates the
   clean tiles even when others are refused, so a refusal cannot prove nothing
   changed; a real-run refusal therefore lands as Uncertain, not a retryable
   failure. Likewise per-tile `results[i].ok == false` on a real run is not
   inspected (the path language cannot walk a list), so a failed designation
   passes silently. A Lua summary flag would close both.
4. `live_deployed: false` / unverified on both tools stands; the first real
   outputs should be recorded and fed back into a fixture.
