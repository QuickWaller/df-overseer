# Handoff: review the armok-tagged DFHack tools and say which, if any, could be used

Date: 2026-09-21. **Research stream for a `researcher` agent on Sonnet.**
Read-only. No VM, no live game, no commits.

Read `CLAUDE.md` (the "No armok tools" rule and "Tools must be generalisable"),
`docs/PURPOSE.md` (design commitments and what the project is trying to show),
`handoffs/2026-09-16-knowledge-scope-audit.md` and
`research/2026-09-16-player-visibility.md` (the rule that agents know only what
a player could know, and the "acting on hidden tiles is allowed, sensing them is
not" correction), `memory/dfhack-environment.md` ("Availability" section), and
`docs/DFHACK-INVENTORY.md` (the input), then this.

## Why this stream exists

The user ruled **"we don't want armok"**: DFHack tags 99 tools `armok` ("god-like
powers or access to information the game intentionally keeps hidden"), and
agents will not use them by default. The tag is coarse. It also covers tools
that only do what a player could do by hand, or that inspect what a player could
see. The user then asked for a careful pass: **is there any armok tool we
should use anyway?** This is advice for the user, who decides each exception.

Another stream is classifying all 443 tools at the same time and will list
armok tools with fair uses in passing. **This is the deeper look at just the 99
armok tools.** Do not read or write that stream's files
(`research/2026-09-21-dfhack-tool-classification.*`).

## What to decide, per tool

Read the tool's full documentation (path below), not just the summary, and
answer against the project's own commitments, not against general DFHack
lore:

1. **What does it really do?** Two or three plain sentences.
2. **What does it break, if anything?** Choose all that apply:
   - `hidden-information`: shows what a player could not see (against the
     knowledge-scope rule).
   - `grants-power`: creates, heals, teleports, changes skills or stats,
     controls units, alters the world beyond normal play.
   - `skips-cost-or-time`: does instantly what costs a player time, labor or
     materials (for example completing designations at once).
   - `changes-the-story`: the run stops being a fair account of what an agent
     did (the project's public report depends on that).
   - `nothing`: it does only what a player could do by hand, or shows only
     what a player could see, and the armok tag is coarse for this tool.
3. **Subcommands.** Many tools mix harmless and cheating subcommands (for
   example an `inspect` versus a `pull`, or a `list` versus a `set`). Where
   they differ, judge **each subcommand**, because an exception could be
   granted for a subcommand and not the whole tool.
4. **Verdict**, one of: `keep-banned`, `candidate-exception` (a specific use,
   named), or `needs-user-ruling` (a real judgement call the user should make,
   with the question stated in one sentence).
5. **If candidate or ruling: exactly what would be allowed**, which subcommands,
   under what condition (for example "read subcommands only", "embark-time only
   and we are past embark"), and which role would use it. Note if one of our own
   tools already wraps it (`scripts/dfhack/TOOLS.yaml`, and grep
   `scripts/dfhack/*.lua` for the tool's name).

Be strict: a tool is not a candidate because it is useful, only because it does
not break the commitments above. Say plainly when a tool is useful **and**
should stay banned.

## Input

`docs/DFHACK-INVENTORY.md` (the "Available `armok` tools" table lists them).
Full docs for every tool:
`C:/Users/wills/AppData/Local/Temp/claude/c--website-projects-df-automation/5c2ab084-dd15-4491-b563-0228954a198d/scratchpad/dfdocs/tools/<id>.txt`
(ids with a slash are subdirectories). The complete list of armok-tagged tools is
every row whose Tags column contains `armok`, or grep the docs for a `Tags:`
line containing `armok`.

## Output

One new file, `research/2026-09-21-armok-review.md`:

1. A short **answer up front**: how many of the 99 are `keep-banned`,
   `candidate-exception`, `needs-user-ruling`, and the shortlist by name.
2. A **table of all 99**, one row each: tool, what it does (one line), what it
   breaks (from the list above), verdict, and for candidates or rulings the
   exact scope allowed.
3. A section for each **candidate and needs-ruling tool** with the reasoning,
   the subcommand split, and the question for the user.
4. **What you could not tell** from the docs and why, and what would settle it.

Write the table incrementally so a cut-off session leaves finished work on disk.

## Rules

- Nothing is presented as verified. You are reading documentation, not running
  anything. Say where docs are unclear.
- Do not touch any other file. Do not write `Working.md`,
  `decisions/DECISIONS.md`, `memory/` or `handoffs/INDEX.md`. Do not commit.
- No em dashes in prose. No addresses or hostnames.

## Done means

All 99 armok-tagged tools have a row; every candidate or ruling has an exact
scope and a named role; the final message gives the counts, the shortlist and
what is uncertain.
