# Handoff: refresh the project's state docs after 2026-09-24 and 2026-09-25

Date: 2026-09-25. **Executor. Docs only. No code, no VM, no push.**

**Exception to the usual ownership rule, granted by the orchestrator for this
stream only:** no other stream is running, so you may edit `CLAUDE.md`,
`Working.md`, `ROADMAP.md`, `memory/` (the repo's, not the user's
auto-memory) and `docs/`. You still **must not** edit `decisions/DECISIONS.md`
rows (append nothing; the register keeps one voice), `research/`, `evals/`,
or any handoff other than this one's Result section. The orchestrator
reviews your diff before merging.

## Sources of truth, in order

1. `decisions/DECISIONS.md`, every row dated 2026-09-24 and 2026-09-25.
2. `handoffs/INDEX.md`, the rows dated 2026-09-24 and 2026-09-25.
3. `evals/live/2026-09-24-wiki-mirror-deploy/README.md`.
4. The research files dated 2026-09-24 and 2026-09-25.
5. `git log --since=2026-09-24`.

If a doc disagrees with these, the register wins; if the register looks
wrong, say so in your Result rather than editing it.

## What to update

1. **`CLAUDE.md` status block** (the `> **Status, ...**` blockquote): bring it
   to 2026-09-25. It is loaded into every session, so make it **shorter**,
   not longer: current state in a few bullets, pointers for history. Must
   be right on: live tool counts **overseer 79, architect 49, consultant 28,
   quartermaster 24, conductor 15**; the Consultant answering from the full
   offline wiki mirror on VM 103 (4,450 pages), refresh timers (S8) not
   built so it goes stale without a manual refresh; test counts **ambient
   1845 passed, 3 skipped** (with lupa) and **dfmcp 692**; conductor still
   never run live; the districting prior art complete and the design
   session waiting on the user; the reload ruling. Keep the "Traps before
   running anything" list, updating its test counts. Keep every
   project-specific rule unchanged.
2. **`Working.md`**: rewrite "Current state" as a tight, accurate summary
   (what is live, what is in motion, what is waiting on the user, and the
   still-open list). Apply the archive-cadence rule in `CLAUDE.md`: move
   finished material wholesale into the matching
   `working-archive/Working_archive-<week-start-date>.md` (follow the naming
   the existing archive files use), never summarise or delete it, and leave
   a one-line pointer. Keep the leaked-key rotation section (still open).
3. **`ROADMAP.md`**: do the full review pass its own header describes. Bump
   `**Last reviewed:**` with a one-paragraph note of this pass; move finished
   items (the wiki mirror deploy, the reader switch-over, the Consultant's
   retrieval) to done; make sure Now reflects what is actually next (a real,
   supervised conductor run is the orchestrator's recommendation; do not
   invent new priorities); keep the Later items added 2026-09-25 (visibility
   feed, traces, catalogue, n8n; save-and-reload testing) as they are.
4. **`docs/CONSULTANT-WIKI.md`**: its status header still says offline, not
   deployed. Update it to deployed and live, with what remains (S7, S8, the
   four `store.py` gaps).
5. **`docs/AGENT-ARCHITECTURE.md` §8 and `docs/AGENT-LOOP.md`**: light touch
   only. Add a pointer to the 2026-09-25 observability requirement (every
   inter-agent message has sender, recipient, type, one-line rationale,
   joinable to its tool calls) and the `ROADMAP.md` Later feed item. Do not
   redesign anything.
6. **Repo `memory/`**: record durable environment facts learned 2026-09-24
   and 2026-09-25 in the file whose scope fits (read `memory/MEMORY.md`
   first), for example: VM 103 has a `dfwiki` system user owning
   `/var/lib/dfwiki/` (750), `df` is in its group read-only, `dfmcp-server`'s
   env needs `PYTHONPATH=/opt/df/wikimirror`, VM 103's Python has FTS5, and
   `load-save` is unavailable in 53.16 (check it is not already there).
   Update `memory/MEMORY.md` if a description changes.
7. **Stale claims anywhere in `docs/`**: grep for "27" consultant counts,
   "not yet deployed" about the wiki, "1844", "691", and fix what is now
   wrong.

## Rules

- `git merge --ff-only main` first.
- **This repo is public.** Never write a hostname, address, token, contact
  value, or anything about the user's other projects (their names, company,
  vendors, workflows). Before each commit run
  `python -m pytest -q tests/test_no_leaked_addresses.py` and a grep of your
  changed files for the other project's name, which the orchestrator will
  give you in the prompt, not here. Zero hits.
- No em dashes in prose; commas, colons or full stops. **No attribution
  lines in any commit message.**
- Mark verified versus proposed as the repo does. Do not upgrade a claim's
  certainty while rewording it.
- Commit after each numbered item. Stop and report on any refusal.

## Done means

Every item above done or explicitly skipped with a reason, `CLAUDE.md`'s
status block shorter than before and correct, `Working.md` under the
400-line threshold with nothing deleted (only archived), and a Result
section listing each file changed and any disagreement found between docs
and the register.

## Result
