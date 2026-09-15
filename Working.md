# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.


## Current state, 2026-09-15: the agent loop is reaching the fort, and the channel exists

The 2026-09-12 to 09-14 section (the agent architecture design phase, the
MCP server build, its first contact with reality, openclaw's install and the
first agent calls) moved wholesale to
[`working-archive/Working_archive-2026-09-14.md`](working-archive/Working_archive-2026-09-14.md).
Everything below is what is still open.

**Where things stand.**
- **The server:** `dfmcp-server.service` runs on VM 103, LAN-bound, with
  bearer tokens as the only guard until Tailscale. It is live-verified with
  relative `level` args, `isError` for script errors, and a JSON tool-call
  log in journald.
- **The agent host:** openclaw on VM 106 has run the architect three times as
  a one-shot `agent exec` on DeepSeek. VM 106 went dark after run #3 and was
  rebuilt in place 2026-09-15. openclaw is reinstalled; its architect MCP token
  must be relayed again before the next run.
- **Incident capture** (guest agent, persistent journal, per-minute netwatch
  dump on gateway loss) is live on VMs 103 and 106 since 2026-09-15. A new
  clone needs `provision_vm.py setup-capture --vmid N` run by hand.
- **The queue is live** (2026-09-15): `queue.propose`/`pass` (architect) and
  `queue.rule`/`pending` (Overseer) on VM 103, DB under `/var/lib/dfmcp`.
  It holds one real record, `proposal-0001` from architect run #3, with a
  pending prediction (`due_game_tick` 12276077). Nothing has ruled on it and
  no grader runs on a schedule. → register 2026-09-15 rows,
  `handoffs/2026-09-15-queue-live-deploy.md`.
- **Tests:** ambient `python -m pytest` gives 276 passed, 1 skipped;
  `.venv-dfmcp` gives 152 for `dfmcp/tests`.

### START HERE, in priority order

1. **One supervised end-to-end cycle: the Overseer rules on `proposal-0001`.**
   The first test of the project's thesis. Any execution needs the user's
   approval. **Open question first:** where the Overseer runs, since the
   2026-09-14 handoff bars its token from VM 106.
2. **A grader schedule**, so `proposal-0001`'s prediction actually grades (it
   is probably due already). Then the rest of the feed:
   1. a publisher of `dfqueue.render.public_view` only (allowlist and kill
      switch; **no delay, user's call 2026-09-14**);
   2. the stream page, noVNC left and a scrolling feed right. **Public, so
      it needs its own go-ahead.**

   It shows proposals and rulings, not agent-to-agent chat (user's call; §4
   kept).
3. **Architect quality, with several samples per configuration.** Run #3
   fixed the dropped record, but n=1 each: its prediction
   (`fort.landmarks.count gt 4` in one day) cannot attribute an outcome, it
   judged "nothing to dig" from level 0 only, and run #2's scope slip
   (a defensibility proposal) is untested since. →
   `evals/live/2026-09-15-architect-third-charter/README.md` review section.
4. **The `set_labor`/`autolabor` race**, a live single-writer violation that
   is small to fix.
### Open, waiting on the user

- **VM 106's old disk: delete it?** Detached 2026-09-15 to `unused0` (25G on
  the sandbox storage, volume kept) after a reboot with it attached sent the
  guest to emergency mode (TRAPS.md). Its forensic read is done and cannot
  settle the cause, so the orchestrator recommends deleting it. **Why VM 106
  went dark on 2026-09-14 is still not established**; incident capture is now
  live on VMs 103 and 106 to record it if it recurs
  (`docs/RUNBOOK-DARK-GUEST.md`, register 2026-09-15 rows).
- **Overseer and consultant tokens were briefly on VM 106** during Phase B's
  live checks (staged under `/tmp`, deleted and confirmed gone by the
  executor), which the 2026-09-14 handoff bars. The brief's fault. Rotate
  them or not: the user's call.

- **DeepSeek key in plaintext on VM 106** in
  `/opt/openclaw/config/state/openclaw.sqlite`. openclaw 2026.9.4 has no
  headless way to store it as a reference; `openclaw secrets configure` over
  `ssh -t` might. `sudo rm -rf /opt/openclaw` removes both secrets.
- **PVE token rotation**, deferred by the user. It needs a privileged
  identity, and deleting a token drops its ACLs.
- **Tailscale**, deferred. Until then the LAN bind means tokens are the only
  guard.
- **Two deferred live checks:** whether the frame cap survives a save load,
  and whether an overlay renders in the headless pipeline.

### Owed elsewhere

- **`home-lab` `inventory/services.yaml`: the `dfmcp-server.service` entry is
  written, not committed.** home-lab-fe added it 2026-09-15, marked
  `inferred`, and validated it. It is left in that checkout for the user to
  review and commit. VM 106 owes an entry only once openclaw runs as a service
  (nothing listens today).

### Background, not urgent

- **Project SSH never verifies host identity.** `scripts/provision_vm.py` and
  `scripts/install_df.py` use `StrictHostKeyChecking=no` with throwaway
  known_hosts files. VM 103's host keys were regenerated 2026-09-11 when
  cloud-init saw a new instance id during the outage recovery, which is what
  made a stale entry look like a changed host in Phase B. Worth pinning the
  estate's real keys.
- **Deploy with `git -c core.autocrlf=false archive`.** Phase B's deploy is
  CRLF on VM 103 (content correct), so naive sha256 checks against `main`
  fail. Also from Phase B: `dfmcp.auth` reads only `REPO_ROOT/.env`, so a
  throwaway instance needs its own code copy; openclaw's schema now rejects
  `pinned-config.json`'s `_note` key.

- **The breach detector is inconclusive.** Settle it opportunistically (rain,
  or an animal fording water), never by flooding the fort.
- **The `../openclaw` scaffold** reads `OPENCLAW_CONFIG_DIR` and
  `OPENCLAW_AUTH_PROFILE_SECRET_DIR`, which the image ignores; use
  `OPENCLAW_STATE_DIR` before running it durably.

## HANDOVER — archived

The 2026-09-12 session-end handover moved wholesale to
[`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md)
(file was past the ~400-line threshold). Its durable-traps list now lives
permanently at [`docs/TRAPS.md`](docs/TRAPS.md) — **read it there, and add new
traps there rather than here.** Current state is the section above.

## Archived

- Sections through 2026-09-10 (fifth handover) — provisioning build,
  perception eval, fort ledger, systemd units, title-screen bootstrap,
  live-viewing/relay/tunnel, the tileset investigation, Site Finder
  resolution, the embark-flow saga through both forts founded, and the
  seed-landmark bootstrap — all moved wholesale to
  [`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md)
  as each was superseded or reported itself finished.
- 2026-09-09: the 2026-09-08 (evening) handover moved wholesale to the
  same archive file.
- 2026-09-09 (end of session): this session's full handover (title-screen
  bootstrap resolution, the entire live-viewing/relay/tunnel build, the
  tileset investigation, and the Site Finder "Begin" resolution) moved
  wholesale to the same archive file — exceeded the ~400-line threshold,
  not superseded. The handover above is the tight current-state summary;
  the archive has the full detail.
- 2026-09-10: the 2026-09-09 (end of session) handover moved wholesale to
  the same archive file, superseded by this session's own handover above
  (Cloudflare Tunnel completion, the graphics-completeness fix, and the
  live embark-flow attempt).
- 2026-09-10 (second handover today): that session's own handover moved
  wholesale to the same archive file, superseded by this session's handover
  above (the click-registration mystery resolved, the real embark mechanism
  found, and the new "Confirm" crash).
- 2026-09-10 (third handover today): that session's own handover moved
  wholesale to the same archive file, superseded by this session's handover
  above — **the first fort was founded**, and the "Confirm" crash resolved
  empirically via gdb.
- 2026-09-10 (fourth handover today): that session's own handover moved
  wholesale to the same archive file, superseded by this session's handover
  above — the `find_mm_*`/`warn_mm_*` coordinate-frame bug found, and
  `xdotool` real-input fix for headless map/hover interaction discovered
  and validated.
- 2026-09-10 (fifth handover today): that session's own handover moved
  wholesale to the same archive file, superseded by the handover at the top
  of this file — the text-only sweep built and run, a Windows-specific SSH
  command-line truncation bug found and fixed in `provision_vm.ssh_guest`/
  `install_df.remote()`, and a strong second-site candidate found
  (`sx=128 sy=84 ex=131 ey=87`), left uncommitted for the user's call.
- 2026-09-10 (end of session): that handover's full continuation (the
  candidate embarked, Artobcatten's save lost as a result, the
  perception-layer branch split, the quorum-blocked snapshot worked
  around with a file backup, and Uniboslan's first room and stockpile dug)
  moved wholesale to the same archive file — exceeded the ~400-line
  threshold, not superseded by new work. The handover at the top of this
  file is the compacted current-state summary; the embark-screen-specific
  durable traps it used to carry were dropped rather than re-copied
  forward, since they're already the permanent living content of
  `docs/DF-UI-AUTOMATION.md`, not duplicated here.
- 2026-09-11: the 2026-09-11 VM-outage/quorum-incident writeup plus the
  entire 2026-09-10 end-of-session handover (VNC control channel, labor
  management/`autolabor`, the kea-combat finding, the quicksave root-cause,
  the perception-branch audit, both autonomous-play experiments, and the
  `find_diggable_area`/reachability corrections) moved wholesale to the
  same archive file — exceeded the ~400-line threshold by a wide margin,
  not superseded by new work. The handover at the top of this file is the
  compacted current-state summary, written deliberately thorough for a
  `/clear`; the archive has the full decision-by-decision detail.
- 2026-09-11 (documentation consistency pass): three fully-self-reporting
  ### threads moved wholesale to the same archive file: the compliance
  eval harness build (done for the session), mechanical prediction grading
  (built, selftested), and the full find_diggable_area/dig_diggable_area
  saga (built, live-verified, live-tested, the quickfort `-c` top-left-vs-
  center bug found and fixed, re-confirmed working end to end). None were
  gated on a human; item 10 in "What actually got built today" above now
  carries the compacted find_diggable_area/dig summary, and
  `decisions/DECISIONS.md`'s 2026-09-11 rows carry the full trail for all
  three.
- 2026-09-12: the entire 2026-09-11 end-of-session handover (the
  branch-merge question, the "what got built" list through item 12, and
  the peer-sessions/next-steps section) moved wholesale to the same
  archive file — the branch-merge question it spent most of its length on
  is resolved (merged, above), so it's fully superseded, not just over
  the line-count threshold. The handover at the top of this file is the
  new compacted current state.
- 2026-09-12 (session end, ahead of a `/clear`): this session's own content
  (the tool manifest build, both coordinate-leak fixes through deploy and
  live-verification, and the quorum correction) moved wholesale to the same
  archive file — it reports itself fully finished, nothing left gated on a
  human except the already-deferred design-commitment-#1 wording entry,
  carried forward unchanged. The handover at the top of this file is the
  fresh compacted current state, including two corrections the archived
  version's own text no longer reflects: both coordinate leaks are now
  fixed/deployed/verified (the archived text still frames them as open in
  a couple of places), and the driving-brain choice (`openclaw`) and
  live-view-ingest shelving are both folded in as settled state rather than
  same-session news.
- 2026-09-15: the whole 2026-09-12 to 09-14 section (the agent architecture design phase, the MCP server build and live smoke test, the durable deploy, openclaw install and first agent calls, both architect charter runs, the relative-LEVEL, isError and call-log fixes, and the dfqueue and live-signals builds) moved wholesale to
  [`working-archive/Working_archive-2026-09-14.md`](working-archive/Working_archive-2026-09-14.md).
  The file was 893 lines. Every still-open item was carried into the current-state section at the top.
