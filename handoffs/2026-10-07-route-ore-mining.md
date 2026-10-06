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

(executor fills this in)
