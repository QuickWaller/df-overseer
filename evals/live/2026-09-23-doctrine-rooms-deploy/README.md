# Live run: deploy the room doctrine so the Architect can read what an office requires

Date: 2026-09-23. Orchestrating session, user go-ahead: "you may".

Prerequisite for the Architect's first real proposal. The doctrine installed on
VM 103 dated from 2026-09-19 and contained nothing about rooms, so an Architect
run before this deploy would have been proposing an office with no knowledge of
what an office requires, which is the exact failure being corrected.

## Why both files had to go together

`dfmcp/doctrine_tools.py` imports `TOPICS` from `doctrine/validate.py` and uses
it both as `doctrine.get`'s own schema enum and for validation. Shipping
`seed.yaml` with its new `rooms` topic while leaving the old `validate.py` in
place would have failed validation on every new entry, which that module treats
as a hard, loud failure, and `rooms` would not have been a queryable value.
A partial deploy here breaks the tool outright rather than degrading.

## What was deployed

| File | sha256 (first 16) | Installed to |
|---|---|---|
| `doctrine/seed.yaml` | `11d5264c5c4c26fe` | the dfmcp install |
| `doctrine/validate.py` | `fe8ff5846fc462ea` | the dfmcp install |

Committed bytes hashed at source, on arrival in `/tmp`, and at the installed
path. All three readings matched for both. Previous copies backed up first to a
dated directory with timestamps preserved.

## Checks, in order

1. **Validated in place after install**: `python3 -m doctrine.validate` against
   the installed file returned `ok`, using the installed validator.
2. **Parsed the installed file directly**: 35 entries total, **7 carrying the
   `rooms` topic**, statuses `prior` and `verified`, and the installed
   `validate.TOPICS` contains `rooms`.
3. **MCP server restarted**, clean start, application startup complete, no
   `RoleValidationError`.
4. **Called `doctrine.get` as the `architect` role** against the installed
   file: `<doctrine_topic name="rooms" returned="7" omitted_refuted="0">`,
   leading with `rooms-are-zones-not-furniture`.
5. **Fort untouched.** This deploy is MCP-side reference data and does not
   reach the game. The fort stayed paused at `abs_tick 12611557` throughout,
   the same tick as the confirmed `autosave 2` quicksave taken earlier today.

## A measurement error worth recording

The first run of check 4 reported **0 entries** and looked like a failed
deploy. The deploy was fine; the check was wrong. It scraped the output for an
`<id>` tag, and the tool emits `<doctrine_entry id="...">`. The file had
already been shown correct by check 2, which is what made the contradiction
visible rather than believable. Verify the verification: a check that cannot
distinguish "the tool returned nothing" from "I parsed the output wrongly" is
not evidence either way.
