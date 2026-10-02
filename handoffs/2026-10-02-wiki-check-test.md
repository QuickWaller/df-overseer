# Handoff: close the loose ends (wiki-check test and repo-side tidy-ups)

Date: 2026-10-02. **Executor, Sonnet, worktree. Offline only: no VM access,
no deploys.** The user wants everything clean before any new experiment or
feature ("close things we've left dangling").

## Tasks, in order (commit after each)

1. **`doctrine/tests/test_wiki_check.py::test_cli_exit_codes` fails every
   day.** Root cause found by two earlier streams: `doctrine/wiki_check.py`'s
   `main` reads the real wall clock instead of the test's injectable clock,
   while the fixture pins `last_full_pull_utc` to `T0` (2026-09-24), so the
   mirror reads `very_stale` once real time passes the threshold. Give
   `main` (and anything it calls that reads "now") an injectable clock with
   the real clock as the default, and pass the test's clock in. Do not
   weaken the staleness rule itself. Add a test that proves the CLI still
   reports `very_stale` for a genuinely old pull, so the fix cannot hide a
   real stale mirror. Then the full ambient suite must be green with zero
   failures: report the count.
2. **CLAUDE.md tool counts point at `docs/STATE.md`.** Replace the
   hand-written per-role tool counts in CLAUDE.md's status block with a
   pointer to `docs/STATE.md`, and update `tests/test_doc_facts.py` so it
   still fails if any doc states a per-role count that disagrees with the
   registry (it must keep catching Working.md or a charter that hand-writes
   a wrong number). Edit only that sentence in CLAUDE.md.
3. **Guide wording.** Some structured guides (`scripts/dfhack/TOOLS.yaml`,
   `guide.arguments[].meaning`) were filled from a shared table and mention
   `NEAR_LANDMARK` for tools whose argument is `SITE` (`blueprint.apply` is
   one). Find every argument meaning that names an argument the command does
   not take, and fix the wording. Byte-preserving round trip as before.
4. **The two largest remaining tool descriptions** are the native
   `gotchas.write` (about 1,450 characters) and `gotchas.get` (about 1,130),
   sent to every role on every request. Shorten each to a summary of two or
   three sentences and move the detail into that tool's own guide text,
   returned when an agent asks `gotchas.get` about `gotchas.write` or
   `gotchas.get`. Per-role tool counts must not change; report before and
   after sizes.
5. **ROADMAP.md review.** Do the lightweight full-review pass CLAUDE.md
   describes: re-scan Now/Next/Later against `Working.md`, the register and
   `handoffs/INDEX.md` for anything quietly finished or stalled, update it,
   bump `**Last reviewed:**`. List anything you moved and why.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`.
- Touched surfaces: `doctrine/wiki_check.py` and its tests, CLAUDE.md (task
  2's sentence only), `tests/test_doc_facts.py`, `scripts/dfhack/TOOLS.yaml`
  (guides only), `dfmcp/gotchas_tools.py` and its tests, `ROADMAP.md`.
- Public repo: no hostnames, IPs or tokens. No em dashes. No attribution
  lines in commits.

## Done when

Ambient suite green with zero failures, `dfmcp/tests` in `.venv-dfmcp`
green, `tests/test_doc_facts.py` green, and a Result section here.
