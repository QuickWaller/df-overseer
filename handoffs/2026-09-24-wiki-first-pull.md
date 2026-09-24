# Handoff: deploy the wiki mirror to VM 103 and run the first real pull

Date: 2026-09-24. **Executor. Live on VM 103, outward-facing (public DF wiki).
User's go-ahead given this session for the deploy and the first pull.**

Read `CLAUDE.md`, then `docs/CONSULTANT-WIKI.md` (sections 3, 5, 10 and 11
especially), then the S3 and S5 handoffs
(`handoffs/2026-09-24-wiki-s3-full-pull.md`,
`handoffs/2026-09-24-wiki-s5-refresh-changelog.md`).

## Scope

In: getting `wikimirror/` onto VM 103, the `dfwiki` user and
`/var/lib/dfwiki/`, a dry run, **the first real full pull, run by hand and
watched**, then one manual refresh run, and the eval write-up.

Out (do not do): enabling any timer, touching `dfmcp-server` or its
environment (no restart, no `MCP_SERVER_WIKI_SNAPSHOT` switch), `df-fortress`,
`df-xvfb`, the fort itself, S7/S8 code, the four known S1 `store.py` gaps.
Report what the switch-over would need instead.

## Steps, stopping where marked

1. `git merge --ff-only main`. `ListAgents`; message any df-automation peer
   with what you're about to do on VM 103 (none expected).
2. On VM 103 via `scripts/vm-ssh.sh df`, read before you change: Python
   version, **FTS5 present** (design section 10 marks it unknown), free disk,
   whether a `dfwiki` user or `/var/lib/dfwiki/` already exists (the old
   30-page JSON snapshot lives there: back it up, do not delete it), and which
   user `dfmcp-server` runs as.
3. Deploy with `git -c core.autocrlf=false archive` (committed bytes only),
   sha256-check committed against landed bytes. Create the unprivileged
   `dfwiki` user with no access to the fort's saves. Put the environment in a
   root-owned file on the VM, never in the repo.
4. Dry run the pull. Read `wikimirror/__main__.py` for the real CLI; don't
   guess flags.
5. **STOP here and report** if `DFWIKI_UA_CONTACT` has not been given to you
   in your prompt or a follow-up message. It goes only in the VM env file.
   Never commit it, never put it in the eval write-up.
6. The real pull. Watch it. Record request count against the budget (800),
   duration, the section 5.1 promotion checks (page count within 1% of
   enumerated, no null body, integrity check), pages degraded or unlisted,
   and DB size. If it fails, keep the staged file and stop; do not re-run in
   a loop.
7. `wikimirror status`, a few reads straight from the DB proving real content
   (known pages such as `Office` and `Tomb`, with revid and section text),
   then one manual `python -m wikimirror.refresh` run and its result.
8. Write `evals/live/2026-09-24-wiki-mirror-deploy/README.md`: every command
   run and its real output (trimmed), what was verified and how. Run
   `tests/test_no_leaked_addresses.py` over it before committing.

## Rules

- You own `evals/live/2026-09-24-wiki-mirror-deploy/**` and this doc's Result
  section. Not `Working.md`, `decisions/`, `memory/`, `handoffs/INDEX.md`,
  `CLAUDE.md`. Any code bug found: report it, don't fix it in this stream.
- Read secrets by key (`grep -E '^KEY=' .env`), never the whole file.
- No hostname, address or contact value in anything committed.
- No em dashes in prose. **No attribution lines in any commit message.**
- Commit after each milestone. Stop and report on any permission or
  classifier refusal; do not route around one that guards the outward pull.

## Done means

The mirror promoted on VM 103 with the 5.1 checks passing and shown, one
refresh run recorded, nothing else on the VM changed, and a list of what the
`dfmcp-server` switch-over and timers would need.

## Result
