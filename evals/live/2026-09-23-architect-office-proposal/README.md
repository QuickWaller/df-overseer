# Live run: the Architect's first real decision, and what it caught that we did not

Date: 2026-09-23. User go-ahead: "awesome! do it", with two explicit
conditions: **do not tell it why the previous office failed**, and build what
it proposes.

**Runner:** the conductor's own `DockerOpenClawRunner`, so the charter
(`SOUL.md`) handling matched every previous real run. **Model:**
`deepseek/deepseek-v4-pro` (the user's call, "go pro not flash"; all three
2026-09-14/15 runs used flash). Fort **paused throughout**; the Architect is
read-only and holds no write verb.

## Result

`proposal-0002`, written to the live queue at tick 12611557, the **second
proposal any role has ever written for real** and the first since 2026-09-15.
9 tool calls, 0 failures, 309.6 seconds, **$0.025**.

Summary as written: "Designate a 3x3 Office zone anchored on the existing
shale Throne chair near the Well and assign it to the Manager (position
MANAGER), so the manager can validate and dispatch work orders."

## What it got right, unprompted

It derived the mechanism this project spent two days missing, from its own
reading of the fort, having been told only the symptom:

> "CRITICAL DETAIL the finder does not enforce: the 3x3 office zone must
> contain the chair. `zone.find` for Office only returns empty rectangles (it
> rejects occupied tiles, which is where the chair sits); a bare empty office
> would have no chair to work at and a room value of 0, failing the manager's
> required_office=1."

It reached this **without reading the room doctrine deployed for it hours
earlier**: `doctrine.get` is in its allowlist and it never called it. The
route it actually took was `zone.list-kinds`'s own metadata
(`room_value_field=required_office`, `owner_capable`) plus `nobles.list` and
`nobles.verify` on MANAGER. The tool manifest taught it the rule, not the
doctrine.

It also identified a real tool defect in passing, quoted above: `zone.find`
cannot propose a site containing furniture, so any room sited from its output
is reliably valueless. That is the mechanism by which this fort acquired two
empty offices, and no human here had noticed it.

## What it got wrong, and why that is our fault

The proposal states "there is no Office zone anywhere". **Two exist**, ids 10
and 11, both Office, both owned, confirmed immediately afterwards by dropping
to raw Lua over `world.buildings.all`.

It concluded "none" from `landmarks.list`, which does not list zones, because
that was the closest tool it had. **Nothing in this project can enumerate
existing zones**: `zone` offers `list-kinds` (what kinds may be placed),
`find` (candidate empty areas), `check-owner` and `place`. Every role is
structurally blind to the fort's own rooms, so "unknown is never zero" arrived
from the tooling side rather than the reasoning side. Fix dispatched the same
day: `handoffs/2026-09-23-zone-inventory-and-validity.md`.

Its prediction is also weak, and for a reason already on record:
`fort.landmarks.count >= 13`, a proxy that could pass or fail for reasons
unrelated to whether the Manager got a working office. There is no closed
signal for "this position's requirement is met"
(`research/2026-09-23-proposals-and-checks.md` §2).

## On timing, because the first attempt looked like a failure

The first run was killed at the conductor's default 600s ceiling reporting
zero tool calls and zero cost, which looked like a hang. Those fields are
simply unmeasured on a timeout: the process is killed before any JSON is
parsed. The MCP journal showed it had been working the whole time.

Measured, rather than assumed:

- A trivial one-turn run, same model and config and container start, and the
  same 8,312 tokens of tool definitions: **10 seconds** end to end.
- Tool calls themselves cost **1 to 66 ms** each.
- Gaps between tool-call bursts in the real run: **4m21s**, then 33s.

So the fixed overhead is 10s and the rest is the model. The MCP log only sees
tool calls, so consecutive assistant turns that call nothing are invisible
from the fort's side and a single "gap" may be several turns. The successful
run did 9 calls in 309.6s.

**Two consequences beyond today.** `conductor/policy.yaml` carries
`expected_thinking_seconds: 90`, and the clock's "closing in" rule is computed
from it; observed here is several times that, and the figure predates any pro
run. And the runner discards stderr on timeout, so a killed run cannot say
where its time went, which is the same silent-degradation shape as the
game-tick bug found earlier the same day.

## Verification

- Proposal read directly from `/var/lib/dfmcp/Uniboslan.sqlite3`
  (`records`, newest row): `id=proposal-0002`, `kind=proposal`,
  `role=architect`, `cycle=12611557`, `type=room_siting`. Not taken from the
  model's own account of itself.
- Zone contradiction checked against `world.buildings.all` rather than any
  tool that had already been shown unreliable for this question.
- Fort paused before, during and after; no write verb exists in the
  architect's allowlist and none appears in the run's tool summary.
