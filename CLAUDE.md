# df-overseer

Turning Dwarf Fortress into a fortress that runs, survives, and tells its own
story without you. See **[docs/PURPOSE.md](docs/PURPOSE.md)** for what this is
and why, and **[docs/MEMORY-ARCHITECTURE.md](docs/MEMORY-ARCHITECTURE.md)** for the overseer's memory and
learning architecture.

> **Status, 2026-09-23.** Current work and next steps: `Working.md` ("START
> HERE"). History: `decisions/DECISIONS.md`, `working-archive/`, `evals/live/`.
> Game knowledge (crop and water rules the agents should use) goes in
> `doctrine/seed.yaml`, not the register.
>
> - **Current state, as last verified live 2026-09-23 (the tag-fix redeploy,
>   `evals/live/2026-09-23-attention-deploy/` plus the orchestrator's
>   single-file redeploy that followed it).** Uniboslan is paused at year 31,
>   tick 107874, 22 alive and 1 dead, 100 FPS, `dfmcp-server` active. Role
>   tool lists: **overseer 70, architect 44, quartermaster 24, consultant
>   26, conductor 15** (read plus write lists, measured 2026-09-24 from the
>   roster; figures above this line predate the zone, nobles and surface tools). Since then the zone inventory,
>   `nobles.requirements`, furniture-aware siting and a zone-anchored surface
>   perception layer (enclosure, finish, material, traffic) are deployed. The
>   Architect ran on the office task with no hints and produced a sound
>   proposal (`evals/live/2026-09-24-architect-rematch/`); agents stay
>   propose-only (register 2026-09-24) and the hands, a quickfort-backed
>   template-plus-site verb, are in build. Both offices are still empty and
>   unenclosed; `nobles requirements MANAGER` still reads `not_met`. **Two Office zones exist** (id 10 unowned, id 11
>   owned by the Manager, unit 345, read back twice), both outdoors (no
>   fully indoor 3x3 site was available near a workshop or the Well). **A
>   Chair was built for real**, the first real, non-dry-run build of any
>   kind by the generic `building` tool, and it sits buildingplan-suspended,
>   pending a Chair item; a new manager order (id 3, ConstructThrone) was
>   created to supply one. **Four manager orders exist**: three
>   (`ConstructBlocks`, `ConstructMechanisms`, the brew-drink reaction)
>   `validated: true, active: false`; the new Chair order `validated: false`.
>   None has ever produced a job with a populated `order_id`, so whether the
>   office is enough room value for the Manager, and whether a completed
>   order actually starts a job, are both still open. The conductor is
>   installed on VM 106 (`conductor.service`), **disabled and inactive**; it
>   has run only as a manual dry run, never for real. → `Working.md`, whose
>   own top section is current as of this pass and was not rewritten here
>   (`handoffs/` rule: the orchestrating session owns it).
> - **Recent history, each in full in the register, `Working.md` and
>   `evals/live/`:** the agent loop MVP (clock/tripwire script, a
>   `conductor` dfmcp role, the conductor service, the Quartermaster
>   enabled, Consultant web/wiki/source retrieval) was designed, built and
>   deployed 2026-09-22, with two live bugs found and fixed (the
>   conductor's MCP client against the real SDK; a missing `diff.since`
>   grant) and a CP437 game-text encoding bug found and fixed at its
>   source (`df-overseer-textutil.lua`, a Python-side backstop in
>   `dfmcp/dfhack_client.py`). `df.job.order_id` was found to link a
>   spawned job back to the manager order that made it, correcting an
>   earlier research claim that no such link existed; order-status fields
>   and a duplicate-production check (`orders.check-duplicate`) shipped and
>   were deployed and live-verified 2026-09-23. The first unattended run
>   (900 of a possible 2000-tick window) placed the first two real Office
>   zones and the first real Chair, then stopped itself on its own
>   `hostile_reachable` tripwire (a kea 68 tiles away) exactly as designed.
>   A three-tier attention system (record/slow/pause, replacing "pause on
>   any reachable creature"), a fifth tripwire on 25 pause-level
>   announcements, an observation ledger, and a stalled/blocked order
>   poller were designed from two research passes and deployed the same
>   day. **The mandatory live check on that deploy caught a real bug**: all
>   six creature-tag reads in the tier classifier were at the wrong struct
>   level and partly misspelled, silently returning `false` for every read
>   (pcall-guarded); a kea still landed in the correct tier by luck, but the
>   slow tier, built for a thieving creature closing in, could never have
>   fired. Fixed, redeployed and live-verified the same day against the
>   same live kea.
>
> - **The fort.** VM 103 (`df-colony-01`) runs **Uniboslan, "Ragwind,"** the
>   one fort, on DF Classic plus DFHack under Xvfb, built by
>   `scripts/provision_vm.py` and `scripts/install_df.py`. A first fort,
>   Artobcatten, was lost founding it (register 2026-09-10). It is genuinely
>   paused, the safe state. The user chose to continue on this fort; it is
>   expendable, and rescuing it is worth trying for the tools it forces us to
>   build.
> - **Perception and action.** `scripts/dfhack/` holds the coordinate-free
>   tools: connectivity, landmarks, overview, diff, open-area and diggable
>   find/build, chokepoints, stuck jobs, labor, farm, workshop, zone, trees,
>   well, manager work orders and a direct-job route, the generic
>   `building` tool (now with one real non-dry-run build to its name),
>   `nobles`, a `zone` tool over every zone kind, a shared tri-state
>   reachability helper (fixes a false negative where the Well's own centre
>   tile, a ramp top, read unreachable to every neighbour), an observation
>   ledger, and the in-game clock/tripwire/vitals/quicksave tools the
>   conductor uses, all live on VM 103. **`doctrine/`** holds game knowledge
>   (crop and water rules) the agents should eventually read; only the
>   consultant reads it, through `doctrine.get`, and it is never a repo
>   decision, so it never goes in the register.
> - **`dfmcp/`**, the MCP server: `dfmcp-server.service` on VM 103,
>   LAN-bound, **bearer tokens the only guard until Tailscale**. Per-role
>   allowlists enforced server-side, role from the credential, every call
>   logged to journald.
> - **`dfqueue/`**, the proposal queue: SQLite, validated at write time, live
>   since 2026-09-15. `proposal-0001` (the only proposal a role has ever
>   written for real) was voided during the 2026-09-22 MVP deploy rather
>   than graded, since its 1200-tick prediction window elapses in well
>   under a minute at the fort's real 100 FPS cap: grading it now would
>   record wall-clock latency, not a verdict on the proposal.
> - **Incident capture** on VMs 103 and 106 (guest agent, persistent journal,
>   a netwatch dump on gateway loss), with `docs/RUNBOOK-DARK-GUEST.md`. VM 106
>   went dark on 2026-09-14, cause unknown; it was rebuilt in place.
> - **Agents.** openclaw on VM 106 is configured with four pinned roles
>   (architect, overseer, quartermaster, consultant), each validated and
>   probed live against the real MCP server (tool counts match exactly).
>   Only architect and overseer are confirmed to have actually run a real
>   `agent exec` decision (the architect's proposals, the Overseer's single
>   ruling, `ruling-0001` from 2026-09-16); **unknown** whether quartermaster
>   or consultant has ever run one for real, versus only being probed/
>   validated -- no run record for either was found in the sources this pass
>   read. The conductor has run once, manually, in the foreground, with
>   `--dry-run --once`; it has never run as a live systemd service, and no
>   agent or conductor cycle has ever made a real decision on this fort
>   beyond `ruling-0001`. Everything in `docs/` and `research/` beyond the
>   above is design or proposal unless marked verified.
>
> **Traps before running anything:**
> - Ambient `python -m pytest` gives **1348 passed, 3 skipped** (measured 2026-09-23,
>   `handoffs/2026-09-23-creature-tag-fields-fix.md`); the
>   skips are correct (transport tests guard their pinned SDK import). Run `dfmcp/tests`
>   in `.venv-dfmcp` for all **652** (measured 2026-09-23). `py -3` here is a 3.13 without pytest:
>   use `python`.
> - Packages are `dfmcp` and `dfqueue`, never `mcp` or `queue`: a local
>   directory of either name shadows the MCP SDK or the stdlib module.
> - Deploy with `git -c core.autocrlf=false archive`; this workstation's
>   `core.autocrlf=true` otherwise ships CRLF and breaks hash checks.
> - Subagent worktrees are created from `origin/main`, not local HEAD, and carry their own
>   copy of `.claude/settings.json`: tell a dispatched agent to `git merge --ff-only main`
>   first. Hash **committed** bytes (`git -c core.autocrlf=false show HEAD:path`), not the
>   working copy. Auto mode's classifier refuses live dev-VM work by its defaults and is
>   configured only from the user's settings (`autoMode`), not the repo: see the register,
>   2026-09-21, and `docs/TRAPS.md`.

This repo is managed with Claude Code using a structured memory system,
following the pattern published as
[`claude-code-managed-repo-template`](https://github.com/QuickWaller/claude-code-managed-repo-template)
(MIT) — the conventions below (`Working.md`, `memory/`, `decisions/`, the Rules
section, the `executor`/`researcher` agents) come from that template. Read this
file first in any session.

## Structure

- **`ROADMAP.md`** (root) — the forward-looking, priority-ordered plan: what's
  next and roughly when, in Now/Next/Later buckets plus an "explicitly not
  doing" list. Complements `Working.md` rather than duplicating it —
  `Working.md` is tactical detail on what's in motion right now, `ROADMAP.md`
  is the strategic list it's drawn from. One line per item: what/why plus a
  pointer into `decisions/DECISIONS.md`, `Working.md`, `docs/`, or `research/`
  for the real detail, never a re-narration. **Update triggers:** a Now-bucket
  item starting or finishing, an explicit user priority call, and a
  lightweight full-review pass at least every ~2 weeks regardless (bump
  `**Last reviewed:**`, actually re-scan for anything quietly finished or
  stalled).

- **`Working.md`** (root) — what's currently in progress. If something is
  tabled, shelved, or paused, remove it rather than marking it paused. Any
  session — fresh, resumed, or accidentally concurrent — should read this file
  and know the current state at a glance. When handing off mid-investigation,
  record what's been **ruled out** and the single **next concrete step**, not
  just the goal.
  **Archive-cadence rule:** archive a `##` section into
  `working-archive/Working_archive-<week-start-date>.md` as soon as *either*
  (a) that section reports itself finished — nothing gated on a human or
  another stream — or (b) the file exceeds roughly 400 lines of in-progress
  material. Move sections wholesale, never summarize or delete; leave a
  one-line pointer.

- **`memory/`** — indexed repo memory: context not derivable from the code.
  `memory/MEMORY.md` is the index. Files split by **scope**, not size.

- **`decisions/DECISIONS.md`** — decision register. Every decision worth
  remembering: **date**, **status**, **reason**. Entries running past ~300
  words get trimmed to a summary plus a pointer into `memory/`.

- **`docs/`** — the design artifacts: `PURPOSE.md`, `MEMORY-ARCHITECTURE.md`,
  `DF-UI-AUTOMATION.md`, `TRAPS.md`, `AGENT-ARCHITECTURE.md`.

- **`research/`** — dated research specs produced by `researcher` agents.
  Long, cited, and honest about what could not be verified. Read the relevant
  one before designing in its area rather than re-deriving it.

- **`handoffs/`** — one written brief per dispatched work stream, plus
  `INDEX.md`. Added 2026-09-12, when more than one stream first ran at once.
  **Two rules live there and differ from `.claude/agents/executor.md`'s
  defaults**: executors do **not** write `Working.md`, `decisions/DECISIONS.md`
  or `memory/` (the orchestrating session owns those, so concurrent agents
  cannot conflict on one long file and the register keeps one voice), and two
  streams must never list the same file under "touched surfaces" — if they
  would, they are one stream.

- **`agents/`** — the roster: `ROSTER.yaml` plus one directory per role
  (`role.md` charter, `tools.yaml` allowlist, `model.yaml`). Adding a role is a
  directory and one line. The allowlist, not the charter, is the real boundary
  (`docs/AGENT-ARCHITECTURE.md` principle 8).

- **`dfqueue/`** — the proposal queue (`docs/AGENT-ARCHITECTURE.md` §4):
  proposal, pass and ruling records validated at write time, stored in
  SQLite (`dfqueue/<fort>.sqlite3`, gitignored) with JSONL export, and a
  grader for live-state predictions. **Named `dfqueue` and not `queue`**
  because a local `queue/` would shadow Python's stdlib module, the same
  trap as `dfmcp`.

- **`blueprints/`** — quickfort blueprints. Two tiers: the original
  single-purpose starter files (`starter-*.csv`, one per tool, since
  2026-09-10), and `blueprints/templates/`, the versioned reusable template
  library added 2026-09-24 (`<id>-v<n>.yaml` metadata plus its `.csv`, with
  `doctrine/`-style provenance). A template declares its seam edges so tiling
  copies share walls instead of doubling them, and declares walls as
  `finished` intent rather than naming a material. **Templates are generic by
  rule**: no fort coordinates, no landmark names. A small generic pattern may
  be shown to a model; this fort's own map may not (`docs/PURPOSE.md`
  commitment 1, user's call 2026-09-24).

- **`evals/live/`** — output of real agent runs against the live fort, kept
  for the public report (one directory per run, with a README and a charter
  check).

- **`dfmcp/`** — the MCP server: registry, roles, tool schema, auth, DFHack RPC
  client, transport. **Named `dfmcp` and not `mcp` on purpose**: a local `mcp/`
  directory shadows the MCP SDK for anything running with the repo root on
  `sys.path`. If an import of the SDK ever seems to resolve to this repo, that
  is the collision returning, not something to work around with `sys.path`.

## Upstream obligations

- **`home-lab`** (`../home-lab` — private, permanently; the declared source
  of truth for the physical server estate this repo automates). Cite its IDs
  (`SRV-01`, `DISK-06`, a VMID); **never copy a hostname, address or subnet
  into this repo** — a public repo cannot leak what it does not contain, and
  that separation is the whole reason the IDs exist.

  **Obligation — creating, deleting, resizing or re-addressing a guest here
  makes `home-lab/inventory/` wrong.** In the same turn, not later:
  - allocate the IP through `home-lab/inventory/ips.yaml` *before* assigning
    it — that file is an allocation registry, "consult before assigning,
    update on assignment", and skipping it is how `<df-vm-ip>` came to be
    in use for a week without being registered anywhere;
  - record the guest change in that host's `inventory/hosts/SRV-0x.yaml`
    `guests:` block, and in `inventory/services.yaml` if a service moved.

  **You are not authorised to edit that repo from here, and it will not
  thank you for trying.** home-lab's own rules forbid reconciling drift
  silently in either direction — writing your observations into its declared
  layer is the specific failure it exists to prevent. Follow the
  consulting-another-repo procedure in `## Rules`: if a session is live in
  `../home-lab`, tell it; otherwise record the obligation in `Working.md` as
  open and say so in your summary, so the user can route it. Anything you do
  send is second-hand there and must arrive with the command you actually
  ran against the live system, not just your conclusion.

  Recorded because it was already decided and never written down:
  `home-lab/decisions/DECISIONS.md` 2026-08-27 accepted that consumption is
  "via a sibling checkout plus one line in the consuming repo's `CLAUDE.md`."
  This is that line. Its eleven-day absence is why VM 103's rebuild sat
  unrecorded in home-lab for a week.

## Rules

- Before proposing or researching an approach, check the decision register —
  don't re-suggest something already tried and rejected without saying so.
  It's fine to resurface a rejected approach, but say that it was rejected
  before and why it's worth revisiting.
- Update `Working.md`, memory, and the decision register as changes happen —
  err toward updating more often rather than batching.
- If the docs and the actual repo state disagree, flag it and suggest a memory
  audit rather than silently patching over it.
- **Memory file scope rule**: a memory file's job is its one-line description
  in `MEMORY.md`. Split on scope drift, not line count. Compress resolved
  narrative into a `DECISIONS.md` entry once settled.
- Destructive or hard-to-reverse actions require explicit confirmation
  regardless of `.claude/settings.json`.
- Treat `git push` and any deploy as outward-facing actions needing explicit
  go-ahead **each time**. Committing locally is fine; publishing is gated.
  **This repo's sessions share one working tree**: before pushing, check
  `git log origin/main..HEAD` for commits that aren't yours — go-ahead for
  your own commit doesn't obviously extend to publishing a sibling
  session's separate, unpushed work riding along with it. Flag whose
  commits are in the batch, don't just ask about your own (found
  2026-09-11 — a push correctly approved for one session's commit swept in
  another session's five, without that session's own go-ahead).
- **Verify the verification.** Before reporting an all-clear, confirm the check
  you ran could actually have detected the problem in question. State what was
  verified and how, not just the outcome.
- **A refusal is a signal, not automatically a wall** (user's call,
  2026-09-14, revising a stricter rule written the same day). When the
  harness, a hook or a classifier refuses an action, work out what it was
  guarding. **If the task is already authorised, the action is reversible,
  and it touches only this project's own machines, taking a safe alternative
  route is fine** — then say plainly in your report that you were refused and
  what you did instead. That is what happened when an executor was refused a
  piped cross-VM token relay and used `scp -3`: authorised task, own hosts,
  both copies deleted after. **Two things still stop you**: a refusal
  guarding something irreversible or outward-facing (a push, a deploy, a
  delete, anything leaving the estate, anything that widens your own access),
  and **routing a blocked action through another session or agent**, which
  hides the decision from the user instead of resolving it.
- **Read secrets by the key you need, never the whole file.** Use
  `grep -E '^KEY=' .env`, not `cat .env`. An agent that needs one value has
  no reason to materialise every token in its transcript. Found 2026-09-14:
  an executor read the whole file, which is what forced a rotation pass.
- **On session start (a fresh session, or right after `/clear`), check
  `ListAgents` for other sessions on this repo and message them to check
  in** — what they have in flight, uncommitted changes, which branch, any
  live-infra state — before assuming a clean slate. This repo routinely runs
  several concurrent Claude sessions; asking first is what has actually
  prevented file-collision and duplicate-work incidents (2026-09-11 rows in
  `decisions/DECISIONS.md` — the personal-control VNC channel, the quicksave
  investigation's pause-flip, and the `df-overseer-diff.lua`/
  `df-overseer-combat.lua` overlap were all caught this way, not by luck).
- **Check in again before modifying a VM or any live-prod state** — a
  peer-session heads-up (what you're about to do, expected visible effect,
  e.g. brief downtime) in addition to, not instead of, this file's existing
  explicit-confirmation rule above. A peer's earlier go-ahead for a
  different action does not cover a new one.

## Project-specific rules

- **No armok capabilities** (user's call, 2026-09-21; refined the same day
  from "no armok tools"). The rule is about the capability, and DFHack's
  `armok` tag is only a pointer to check. Banned: powers a player does not
  have (heal, teleport, spawn, skip costs, alter the world) and information
  the game hides. Reading something a player can already see is fine, however
  it is implemented. `docs/DFHACK-INVENTORY.md` lists the tagged tools;
  `docs/ARMOK-RULINGS.md` records the user's ruling on each one discussed.
- **Tools must be generalisable** (user's call, 2026-09-21; applies to every
  tool). A tool that works for one instance is not a tool: a `build workshop`
  tool that only builds stills is a still script. Take the kind, item or job
  as an argument and read what differs per kind (size, labor, materials,
  requirements) from the game's own data; put genuinely per-kind policy in
  data (doctrine or a requirements entry), not in branches in the tool.
  Before building or extending a tool, ask what the next instance would cost
  (the next workshop, crop, zone type or furniture piece) and design so the
  answer is "one data entry, no new code". Known offenders are listed in
  `Working.md` START HERE.
- **Research before designing from scratch.** State the problem in
  domain-neutral terms, ask which other fields already own it, and read those.
  This produced the best material in both research specs so far — see
  `decisions/DECISIONS.md` 2026-08-25.
- **Never design anything that shows the model a rendered map.** Not ASCII,
  not a tile grid, not a screenshot. This is a hard commitment, not a
  preference — see `docs/PURPOSE.md` design commitment #1 and
  `research/2026-08-25-spatial-perception.md`.
- **Mark verified vs proposed.** DFHack tool availability changed
  substantially in the v50 transition; several tools are present as files but
  tagged `unavailable`. Check `memory/dfhack-environment.md` before assuming a
  tool works, and check the local install before assuming API surface exists.
- **This repo is public.** Infrastructure specifics (Proxmox host, Coolify,
  IPs, hostnames, tokens) go in gitignored `infra/local.*` with committed
  `infra/local.example.*` counterparts. Never commit the specifics.
