# Handoff: deploy today's tool work and live-verify it

Date: 2026-09-19. **Live stream. Needs VM 103.** Do not start while
`handoffs/2026-09-19-well-unblock.md` is still running: only one stream touches
the fort at a time.

Read `CLAUDE.md` (including the deploy trap in its status block), then
`handoffs/2026-09-19-per-item-flags-tool.md` and
`handoffs/2026-09-19-silent-zero-fix.md`, both including their write-ups, then
this.

## Update 2026-09-19, read this before starting

**A partial deploy already happened.** The well stream ran
`install_df.py ui-install` (20 scripts) mid-run, which carried the
**`dig-stair` occupancy fix live for the first time**. So item 3 below is
done.

**What that deploy almost certainly did NOT carry**, because both merged
after it ran: **`stocks.availability`** and the **silent-zero fixes**.
**Verify which is actually on the VM before deploying again** rather than
assuming either way; a file-hash or a grep for `checked_flag` on the deployed
`df-overseer-stocks.lua` settles it in one command.

Also note the fort was **rolled back to tick 213622** by an incident during
that stream (see `docs/TRAPS.md`, the DFHack concurrency entry). **Quicksave
before anything, and verify it wrote.**

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

## Outcome, 2026-09-19

**Fort confirmed paused before touching anything**: year 30, tick 272606,
`dfhack.world.ReadPauseState() == true` (bounded `dfhack-run lua` reads of
`cur_year`/`cur_year_tick`/pause state only, matching the state the
orchestrator reported minutes earlier from its own quicksave). Re-read
identically at the end, after every deploy and every live check below:
still year 30, tick 272606, still paused. **No unpause was needed or run.**

### What was already on the VM vs what this stream deployed

Checked before touching anything, by grepping the deployed files (not
assuming): `/opt/df/game/hack/scripts/df-overseer-{stocks,trees,workshop,well}.lua`
were all dated 2026-09-18 12:00 (the well-unblock stream's `ui-install`,
carrying only the dig-stair fix). `grep -c checked_flag
df-overseer-stocks.lua` and `grep -c 'unknown labor'
df-overseer-{trees,workshop,well}.lua` both returned 0. Neither
`stocks.availability` nor any of the four silent-zero fixes was live before
this stream. The dfmcp-server's own manifest copies
(`/opt/df/dfmcp-smoke/scripts/dfhack/TOOLS.yaml`,
`/opt/df/dfmcp-smoke/agents/{architect,overseer}/tools.yaml`) were last
touched 2026-09-18 06:31 (the server's own start time) and also had zero
occurrences of `stocks.availability`.

**Deployed**: `df-overseer-{stocks,trees,workshop,well}.lua` to
`/opt/df/game/hack/scripts/`, and `scripts/dfhack/TOOLS.yaml` plus
`agents/{architect,overseer}/tools.yaml` (not `consultant`, per this
stream's own touched-surfaces note) to their `/opt/df/dfmcp-smoke/`
counterparts. Method: `git -c core.autocrlf=false archive HEAD -- <paths>`
locally, a `sha256sum` manifest built from the extracted tarball, `scp` of
the tarball, `sha256sum -c` against that manifest immediately after
extracting on the VM, then copied into place with `chown df:df`, then
**hashed again at the final installed path** and diffed against the same
manifest -- all 7 files matched byte-for-byte, both before and after
install, so CRLF corruption did not happen. The four overwritten `.lua`
files were backed up first to `/opt/df/deploy-backup-2026-09-19/`. SSH used
`~/.ssh/df_overseer_ed25519` as user `df` (root refuses); `DF_VM_IP`'s
`/24` suffix was stripped before connecting. `dfmcp-server` was restarted
(`systemctl restart dfmcp-server`, matching the documented "restart
dfmcp-server only, never df-fortress" precedent) so the new manifests took
effect; DF's own process was never touched or restarted.

A second, single-file redeploy of `df-overseer-stocks.lua` followed later
(see the `verified_offline` section below), using the identical
archive-hash-verify-install-reverify method, after that file's one
permitted source edit was committed.

### `stocks.availability` verification

- **File loads at all**: confirmed by the first live call succeeding with a
  well-formed JSON object rather than a Lua stack trace. What would have
  made this fail: any syntax error would have made `dfhack-run` print a
  parse/load error instead of JSON.
- **Run against `BUCKET`**: `./dfhack-run df-overseer-stocks availability
  BUCKET` returned `total_units=3, available_units=3, in_job_units=0,
  forbid_units=0, owned_units=0, trader_units=0, unnetted_units=0,
  flag_read_errors=[]`. All three fort-owned buckets are, right now,
  genuinely available (none claimed, forbidden or dwarf-owned) -- a
  different live state than the motivating incident's "3 buckets,
  unreachable," which is expected since the fort has moved on 58,000+
  ticks since that incident; the tool correctly reports the *current* live
  state rather than reproducing the old symptom on demand. What would have
  made this fail: any of those counts being wrong relative to a hand check,
  or the call erroring instead of returning a shape.
- **Bad TYPE returns an explicit error**: `availability NOTAREALTYPE` ->
  `{"error": "unknown item type: NOTAREALTYPE (not a df.global.world.items.other
  key on this install)"}`, not an empty object and not a crash. What would
  have made this fail: an empty `{}` or a Lua error with no JSON at all.
- **Both `UNIT_HOLDER` branches exercised.** `BUCKET`'s `owned_units` was 0
  (nothing of that type is currently dwarf-owned), so `get_availability`
  itself never reached `checked_unit_holder_ref` in this run. Rather than
  report the branch untested, a separate bounded read-only probe
  (`dfhack.units.getCitizens()`, one citizen's own `unit.inventory[0].item`,
  and one `items.other.BUCKET[0]`) called the **exact same DFHack primitive
  `checked_unit_holder_ref` wraps**
  (`dfhack.items.getGeneralRef(item, df.general_ref_type.UNIT_HOLDER)`)
  directly against a known-held item and a known-unheld item:
  - held item (a citizen's own inventory item): `pcall_ok=true,
    ref_found=true` -- the `(true, true)` branch.
  - unheld item (an available bucket, independently confirmed
    `flags.owned == false`): `pcall_ok=true, ref_found=false` -- the
    `(true, false)` branch.

  Both branches behave exactly as the function assumes. What would have
  made this fail: either call raising, or the held item coming back with no
  ref, or the unheld item coming back with a ref.

### `verified_offline`: flipped to `true`, deliberately, separately

Because both `UNIT_HOLDER` branches were genuinely exercised against real
held and unheld items (immediately above), `owned_ref_check.verified_offline`
in `scripts/dfhack/df-overseer-stocks.lua` was flipped from `false` to
`true`, in its own commit (`06fa8b5`, on top of the deploy work, nothing
else changed), with the three adjacent comment blocks that described the
old "never verified" state updated to match rather than left stale. That
commit was then deployed as a single-file redeploy (same
archive/hash/verify method as above) and re-run live: `availability BUCKET`
now returns `"owned_ref_check": {"verified_offline": true, ...}` from the
live process, not just from the source file.

### Silent-zero fix verification

**One fix made to fail on purpose, live, and observed reporting the miss.**
`df-overseer-trees.lua`'s `labor_enabled_count` is called with the hardcoded
constant `CUTWOOD_LABOR = "CUTWOOD"` (not a CLI argument), so proving the
failure path needed a temporary edit to the **deployed VM copy only** (never
the git source, never the one permitted source edit above):

1. Control run, correct constant: `./dfhack-run df-overseer-trees find
   "Embark Site"` -> `"citizens_with_labor": 1, "labor": "CUTWOOD"`, no
   error field.
2. Saved the correct deployed file to `/tmp` on the VM, then `sed`-typo'd
   line 74 to `local CUTWOOD_LABOR = "CUTWOOOD_TYPO"` **in the deployed
   file only**.
3. Re-ran the identical command: `"citizens_with_labor_error": "unknown
   labor: CUTWOOOD_TYPO"`, and **`citizens_with_labor` is absent from the
   object entirely** -- not present, not `0`.
4. Immediately restored the saved-good file, re-hashed it
   (`6695098b...dc06`, matching the original deploy manifest exactly), and
   reran once more to confirm the normal output (`citizens_with_labor: 1`)
   came back.

This is the exact distinction the whole stream exists to prove: **before**
this fix, the identical typo would have produced `"citizens_with_labor": 0`
with no error field at all -- indistinguishable from a real zero, character
for character the original `FEED_WATER_WOUNDED` "0 of 15" bug. **After** the
fix, the miss is unmistakable: an explicit `_error` string and the count
field's own absence, never a bare zero standing in for "I couldn't tell."

Only one of the four fixed call sites was live-exercised this way, by
design (the fort stayed paused and untouched otherwise, and repeating the
same temporary-corrupt-and-restore procedure three more times for
`workshop.lua`'s two call sites and `well.lua`'s one would not have proven
anything the first one didn't already prove -- all four share the identical
`set_labor`-derived `ok/value, err` shape per the offline write-up's own
audit). The other three remain verified by code-reading only (per that
write-up), not independently live-tested in this stream.

### Real per-role tool counts

Queried live, not inferred: a real `mcp==2.2.0` `ClientSession` (the same
SDK the server itself uses, run from the VM's own
`/opt/df/dfmcp-smoke/.venv`) connected to the running `dfmcp-server` at
`http://<df-vm-ip>:<mcp-port>/mcp` (address in gitignored `infra/local.*`), authenticated per role with that role's own
bearer token read by key from `/opt/df/dfmcp-smoke/.env`
(`MCP_ROLE_TOKEN_ARCHITECT`/`_OVERSEER`/`_CONSULTANT`, never the whole
file), called `initialize()` then `list_tools()` for each role in turn. No
DFHack round trip is involved in `tools/list`, so this touched nothing on
the fort.

- **architect: 24** (previously 23; `stocks__availability` is the only
  addition, matching this stream's deploy exactly).
- **overseer: 37** (previously 36; same single addition).
- **consultant: 4** (unchanged; this stream's own touched-surfaces note
  says not to touch `agents/consultant/tools.yaml`, and it wasn't).

`CLAUDE.md` and `ROADMAP.md` both still say the pre-deploy counts
(23/36/4) as of this write-up. Reconciling them is explicitly **not** in
this stream's touched surfaces (only VM 103, this handoff doc, and the one
permitted `df-overseer-stocks.lua` edit are), so it is reported here rather
than edited there, for the orchestrator to update.

### Fort state, start to finish

Every read against DFHack in this stream was bounded (one landmark list,
one citizen list, one item vector index or two, one `find` call with a
capped radius, two `tools/list` calls needing no DFHack round trip at all)
-- no full-map sweep was run. Year and tick were read at the very start and
the very end: **year 30, tick 272606, paused, unchanged**, both times.

### A note on shared history

While this stream ran, other sessions committed directly to this same
checkout's `main` (the "real-corpus-extraction" stream and at least one
autosave/docs commit landed between this stream's start and its own
commit). Checked before committing: `git diff --stat` between the
commit this stream started from and the commit it ended up parented on,
scoped to every file this stream touched or deployed, was empty -- none of
those intervening commits touched
`scripts/dfhack/df-overseer-{stocks,trees,workshop,well}.lua`,
`scripts/dfhack/TOOLS.yaml`, `agents/{architect,overseer}/tools.yaml`, or
this handoff doc. This stream's single commit (`06fa8b5`) contains only its
own one-file edit.
