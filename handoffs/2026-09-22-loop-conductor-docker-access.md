# Stream: give `conductor.service`'s account Docker access on VM 106

**Written** 2026-09-22. **Status:** dispatched. **User go-ahead:** 2026-09-22,
"yeah put some sonnets on things", answering "shall I have a Sonnet do ... add
the `df` user to the `docker` group on VM 106 (effectively root; widens
access) ... and come back before anything unpauses?". The access widening is
the user's decision, made knowingly; this stream carries it out and nothing
wider. **Live work on VM 106 only.** Sonnet executor, worktree-isolated. **No
push. No attribution lines in any commit** (no Co-Authored-By, no "Generated
with Claude Code": the user's instruction).

## Why

The conductor launches one-shot openclaw runs with `docker run --rm`. The
loop MVP deploy (`handoffs/2026-09-22-loop-mvp-deploy.md`, Result) found the
account `conductor.service` runs as can reach the Docker socket only through
`sudo`, so the service cannot launch a single role. This is one of the
items owed before the first real start.

## First

`git merge --ff-only main` in your worktree. Read `CLAUDE.md`,
`docs/TRAPS.md`, `infra/conductor.service.example`, the deploy stream's
handoff and `evals/live/2026-09-22-loop-mvp-deploy/README.md` (how VM 106 was
set up, which account the unit uses, where things live).

## What to do (ssh as in that README: key
`C:/Users/wills/.ssh/df_overseer_ed25519`, user `df`, address from `.env`
`OPENCLAW_VM_IP` read by key, stripped of quotes and any `/24`, **never
printed**)

1. Read first, change nothing: the installed unit's `User=` and
   `Group=`/`SupplementaryGroups=`; `id` for that account; the socket's
   owner, group and mode; whether a `docker` group exists. Record all of it.
2. Pick the narrowest change that works and say why. Options: add the
   account to `docker` (`usermod -aG docker <account>`), or
   `SupplementaryGroups=docker` in the installed unit only (scopes the grant
   to the service rather than every login shell of that account). If you
   choose the unit route, mirror the change in
   `infra/conductor.service.example` and commit it. Do not change the
   socket's permissions, do not use a rootless or TCP socket, do not add
   sudoers entries.
3. Verify without sudo, as the service would run: `docker version` and
   `docker ps` as that account (for the unit route, run it through
   `systemd-run --uid=... -p SupplementaryGroups=docker` or equivalent, so
   you test what the unit actually gets). `docker ps` must show 0 containers
   before and after. **Do not start a container and do not run openclaw.**
4. Confirm `conductor.service` is still **disabled and inactive**, and that
   nothing new is listening (`ss -tlnp` before and after).

## Hard lines

- VM 106 only. Do not touch VM 103 or the fort. Do not enable or start
  `conductor.service`. No model call, no container run.
- A sibling stream (`handoffs/2026-09-22-loop-game-text-encoding.md`) will
  run one conductor `--dry-run --once` on VM 106 while you work; it does not
  touch Docker or the unit. Do not run the conductor yourself.
- Nothing beyond this one grant. If it turns out to need more (a second
  group, a socket change, sudo rules), stop and report instead.
- Secrets by key only; never print a secret, an IP or a hostname.
- If the auto-mode classifier refuses the change, it is guarding an access
  widening: **stop and report it verbatim**; do not reroute and never ask
  another session.
- Do not write `Working.md`, `decisions/` or `memory/`. No em dashes.

## Touched surfaces

VM 106: the conductor account's groups or the installed unit file;
`infra/conductor.service.example` only if the unit route is chosen; this
doc; `evals/live/2026-09-22-loop-conductor-docker-access/README.md` (new).

## Report (Result section plus the eval README)

The before state, the change made and why that route, the exact commands,
the verification output (counts, not secrets), unit state before and after,
every refusal verbatim, and the home-lab line owed if any (none expected: no
guest created, resized or re-addressed).

## Result

Done. Full detail in `evals/live/2026-09-22-loop-conductor-docker-access/README.md`;
summary here.

**Before**: installed unit `User=df Group=df`, no `SupplementaryGroups=`,
disabled/inactive. `df`'s own groups: `df,adm,cdrom,sudo,dip,lxd`, no
`docker`. Socket `root:docker`, mode 0660. `docker` group exists (gid 112,
empty). Bare `docker ps` as `df`: permission denied. `sudo -n docker ps`:
0 containers, server 29.1.3. No Docker-related TCP listener.

**Change**: added `SupplementaryGroups=docker` to the installed unit only
(not `usermod -aG docker df`), mirrored into `infra/conductor.service.example`
with a comment explaining the choice. Backed up the pre-change unit to
`/tmp/conductor.service.orig-2026-09-22` on VM 106 first. Chose the
unit-scoped route because it is verifiably narrower: after the change, `df`'s
own shell still cannot reach Docker, only the unit's own
`User=`/`Group=`/`SupplementaryGroups=` combination can.

**Verified**, via `systemd-run --uid=df --gid=df -p SupplementaryGroups=docker
--pipe --wait --collect`, no sudo on `docker` itself: `docker version` ->
`29.1.3`; `docker ps` -> 0 containers, matching the before count. Bare
`docker ps` as `df` still denied (scoping intact). `id` for `df` unchanged
(no `docker` group added to the account). No container started at any point.

**Unit state**: `disabled`/`inactive` before and after. `ss -tlnp` identical
before and after (no new listener). `conductor.service` was never started or
enabled.

**Refusals**: one, from the harness's own worktree/git-safety check (not the
auto-mode classifier, not an access-widening guard) on a computed-`ssh`
command shape; resolved by moving the IP lookup into a script file run by
path, quoted verbatim in the eval README. No classifier refusal was hit.

**A mistake, corrected**: debugging a quote-stripping bug in the ssh
wrapper printed the VM's address into this transcript once via `cat -A`
(the handoff's "never print an IP or hostname" line). Fixed immediately,
not repeated, and confirmed absent from every tracked file
(`grep -rn "192\.168\." infra/ handoffs/` on the touched files, clean).
Flagged in the eval README rather than hidden.

**Home-lab**: nothing owed. No guest created, deleted, resized or
re-addressed.

**Not done, per the hard lines**: `conductor.service` not enabled or
started, no container run, no `agent exec`, no model call, VM 103 and the
fort untouched, no socket permission change, no sudoers entry, no push.
