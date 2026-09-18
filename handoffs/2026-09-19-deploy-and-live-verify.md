# Handoff: deploy today's tool work and live-verify it

Date: 2026-09-19. **Live stream. Needs VM 103.** Do not start while
`handoffs/2026-09-19-well-unblock.md` is still running: only one stream touches
the fort at a time.

Read `CLAUDE.md` (including the deploy trap in its status block), then
`handoffs/2026-09-19-per-item-flags-tool.md` and
`handoffs/2026-09-19-silent-zero-fix.md`, both including their write-ups, then
this.

## What is undeployed

Three separate pieces of work are merged to `main` and **have never run on the
VM**:

1. **`stocks.availability`** (new command, `df-overseer-stocks.lua`). Nets
   `in_job`, `forbid` and `owned` per item type.
2. **The silent-zero fixes** in `df-overseer-trees.lua`,
   `df-overseer-workshop.lua` and `df-overseer-well.lua`. Four functions now
   return `value_or_nil, err` instead of a bare `0`, and seven call sites were
   changed to thread the error through.
3. **The `dig-stair` fix** from 2026-09-17, merged and never deployed.

Deploy once, from `main`, rather than three times.

## The deploy trap, which has bitten this repo before

**Use `git -c core.autocrlf=false git archive`.** This workstation has
`core.autocrlf=true`, which otherwise ships CRLF line endings and breaks hash
checks. This is in `CLAUDE.md` for a reason.

Also: `DF_VM_IP` in `.env` **carries a CIDR suffix that must be stripped**, and
SSH must be as user **`df`**, not `root` (root refuses with a login banner).
Read secrets by the key you need (`grep -E '^KEY=' .env`), never `cat .env`.

## Live verification, which is the actual point

A deploy that only proves the file copied is worth very little. **Every check
below must be one that could have failed.**

### `stocks.availability`

- **Confirm the file loads at all.** A Lua syntax error is the likeliest
  failure and the offline stream could not rule it out: no Lua interpreter
  existed in that environment, so it fell back to a keyword-balance check and
  said so honestly.
- **Run it against `BUCKET`**, the motivating case. The fort owns buckets and
  has already demonstrated the failure this tool exists to see: **three empty,
  unforbidden, unclaimed buckets present while "Give water: Need empty bucket"
  was logged.**
- **Exercise both `UNIT_HOLDER` branches.** Find an item a dwarf actually owns
  and one nothing holds, and confirm the tool distinguishes them. **Only then**
  may `owned_ref_check.verified_offline` be changed to `true`, and it must be
  changed deliberately, in the source, as a separate reviewable edit. If you
  cannot find a dwarf-held item, **say so and leave the flag false.**
- **Confirm a bad TYPE returns an error**, not an empty result.

### The silent-zero fixes

- **Make one fail on purpose.** The whole claim is that a failed lookup is now
  distinguishable from a real zero, and the only way to know is to feed one a
  name that does not resolve and confirm the output carries an explicit
  `unknown labor: ...` / `unknown item type: ...` rather than a `0`.
  **A fix to this bug class that is not observed failing has not been
  verified**, which is the whole lesson of the incident that caused it.

### Tool counts

Role tool lists were **23/36/4** before today. Re-read them live per role and
reconcile `ROADMAP.md` and `CLAUDE.md` against the real post-deploy numbers.
Those two files have disagreed on tool counts before.

## Rules that bite here

- **The fort is paused and paused is the safe state.** This stream should need
  **no unpause at all**: every check above is read-only. If you think you need
  one, stop and say why.
- **Verify the verification.** For every green result, state what would have
  made it red.
- **A lookup that can silently miss must report the miss.**
- Do **not** write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`.
- No em dashes in prose.

## Touched surfaces

VM 103 (deploy plus read-only tool runs), and this handoff doc. **One source
edit is permitted and only one**: flipping `owned_ref_check.verified_offline`
in `df-overseer-stocks.lua`, and only if you actually exercised both branches.

## Done means

All three pieces are live, `stocks.availability` has been run against a real
item type, **at least one silent-zero fix has been observed reporting a miss
rather than a zero**, the `verified_offline` flag is either honestly flipped or
honestly left alone with the reason stated, the real tool counts are recorded,
and the fort is still paused.
