# Stream: trim over-long decision register rows and handoff index rows

**Written** 2026-09-15. **Status:** dispatched. **User go-ahead:** given
2026-09-15 ("trim long register rows", "tighten handoffs/INDEX.md").
Local docs only: no VM, no code, no model call.

## Why

`decisions/DECISIONS.md` is about 55,000 words and 45 rows break CLAUDE.md's
own rule: "Entries running past ~300 words get trimmed to a summary plus a
pointer into `memory/`." `handoffs/INDEX.md` rows have grown into paragraphs,
while the detail already lives in each handoff doc. Both files are read at the
start of most sessions, so their size is a real cost.

**The one non-negotiable: nothing is lost.** This is a move, never a delete.

## Repo overrides for this stream only

`handoffs/INDEX.md` says executors never write `decisions/DECISIONS.md` or
`memory/`. **This stream is the explicit exception**, for trimming and moving
existing text only: no new decisions, no status changes, no reinterpretation.
Still do not touch `Working.md`, `CLAUDE.md`, `ROADMAP.md` or any code (the
orchestrator is editing `CLAUDE.md` concurrently).

## What to do

### 1. The register

- Find every row over 300 words (split on whitespace). Rows at or under 300 are
  untouched.
- **Move each long row's full original text, verbatim**, into a `memory/` file
  chosen **by scope, not by date** (CLAUDE.md's memory rule: "a memory file's
  job is its one-line description"). Reuse an existing file when the scope
  fits (`memory/dfhack-environment.md`); otherwise create a small number of
  scoped files, for example embark automation, live viewing and relay, the
  perception tool builds, infra incidents, the compliance eval. Your call on
  the grouping; justify it in the report. Each moved row goes under a heading
  with its date and title, in date order within the file.
- **Replace the row in the register** with: the same date, the same title, the
  same status cell, and a reason cell of **at most about 120 words** that keeps
  the decision and its main reason, ending with a pointer
  (`→ memory/<file>.md#<anchor>` or the heading text). The summary adds no
  claim that isn't in the original.
- Row count and row order in the register stay exactly the same.
- Add one line per new memory file to `memory/MEMORY.md`, matching its format.

### 2. The handoff index

- Cut each row's Status cell to **at most about 40 words**: status, date,
  headline outcome, and anything a reader must know before trusting the stream.
  Leave the Stream, Doc and Touched-surfaces columns as they are.
- Before cutting, check each fact you remove is already in that row's handoff
  doc. **If one isn't** (orchestrator corrections often live only in the index),
  append it verbatim to the doc under a heading `## Index notes (moved
  2026-09-15)` instead of deleting it.

### 3. Prove nothing was lost (required)

Write a small script in your scratchpad (do not commit it) that, against the
`main` commit you started from:
- extracts every original register row over 300 words and asserts its full
  text appears verbatim in `memory/` after your change;
- asserts the register's row count, dates, titles and status cells are
  unchanged, and no row is now over 300 words;
- for the index, asserts every sentence you removed appears in the linked
  handoff doc (normalise whitespace; report any you had to append).

**Verify the verification:** show the script fails if you delete one moved
paragraph from a memory file, then restore it.

## Hard lines

- No em dashes in any prose you write (commas, colons or full stops).
- No addresses, hostnames or tokens anywhere (this repo is public).
- Commit each chunk to your branch as you go.

## Touched surfaces

`decisions/DECISIONS.md`, `memory/` (new files, `memory/MEMORY.md`,
`memory/dfhack-environment.md` only if a row fits its scope),
`handoffs/INDEX.md`, `handoffs/*.md` (append-only index notes), this doc.

## Report

Word counts before and after for both files; the memory files created and
their scope; the verification script's pass output and its forced-failure
output; any row you could not summarise faithfully under 120 words (leave
those longer and list them rather than distorting them).

## Result

(executor fills in)
