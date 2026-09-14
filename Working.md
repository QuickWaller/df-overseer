# Working

What's currently in progress. Remove an item once it's done, tabled, or
shelved, don't mark it paused. Any session should read this and know what's
actually going on right now.


## Agent architecture design phase — started 2026-09-12

The design/research phase the handover below anticipated, which then produced
working code.

**Current state, end of 2026-09-12: the design is written and revised against
six research briefs, and the MCP server is built.** `agents/` holds the roster;
`dfmcp/` is six modules and 136 tests (121 without the pinned SDK, where the
transport's own tests skip themselves by design). Two safety detectors exist,
one live-verified working and one inconclusive.

**Still not started:** the Sentry, Triage, the queue, snapshots and playbooks.

**The limit that matters more than any of the above: nothing in `dfmcp/` has
met a real DFHack, a bound socket, or a real agent host.** Every test runs
against a fake server built from the same wire spec, so a divergence between
the VM's actual binary and the source the research read would pass all 136.
Read item 2 below before trusting the number.

### START HERE next session, in priority order

Everything below this block is detail and reasoning. This is the brief.

1. **DONE 2026-09-12: openclaw's VM exists.** `df-colony-openclaw-01`, **vmid
   106**, <openclaw-vm-ip>/24 static, 2048 MB ceiling / 1024 MB balloon, 4 cores,
   onboot enabled, linked clone of template 102 on SRV-01. Verified by SSH, not
   just by the API's "running": correct hostname and correct address from inside
   the guest. `OPENCLAW_VMID` recorded in `.env`, placeholder added to
   `infra/local.example.env`. **The upstream obligation is discharged**: full
   details sent to the live `home-lab-03` session for the
   `inventory/hosts/SRV-01.yaml` `guests:` entry. Nothing else owed. **It found
   a real bug on the way in, see the section below: `clone` would have given it
   the running fort's address.**
2. **DONE 2026-09-12: THE MCP SERVER EXISTS. The one hard blocker is cleared.**
   `dfmcp/` is six modules and **136 tests** (121 in an environment without the
   pinned SDK, where the transport's own tests skip themselves by design).
   Built in four parallel Sonnet streams against two research briefs, in one
   session.

   **What the next session needs to know, in one paragraph.** Run the suite
   from the repo root. To get all 136 you need the pinned SDK in a venv:
   `python -m venv --system-site-packages .venv-dfmcp` then
   `pip install -r dfmcp/requirements.txt` (**never install it into the shared
   environment**, there is a verified `fastmcp<2.0` conflict on this machine).
   Without it you get 121 passed and 1 skipped, which is correct, not a
   failure: `dfmcp/tests/test_server.py` guards its own import, because a bare
   collection error would take the other 121 from passing to not running at
   all.

   **UPDATED 2026-09-14: the server HAS now met reality, and reality found a
   real bug.** Live smoke test on VM 103 (loopback bind, throwaway tokens,
   torn down after, fort untouched): the real SDK over a bound socket, 401
   opacity, per-role `tools/list`, the advisor refusal before DFHack, and the
   RPC client plus pool against real DFHack all held. **But calling
   `landmarks__list` failed**: real scripts print bare JSON arrays, and
   `server.py` put them into `structuredContent`, which the SDK rejects as a
   protocol error. The fake DFHack's payload was an object, a shape no real
   script prints, which is how 136 tests missed it. Also `requirements.txt`
   lacked `pyyaml`. **Both fixed and merged (`f37502c`, 138 tests in the
   venv)**: non-object JSON is now wrapped as `{"result": ...}`. **Re-run live
   on VM 103 the same day: all six checks plus an empty-array case passed**,
   so the fix is live-verified, not merely merged. `landmarks__list` returns
   `{"result": [...]}` with the real fort's landmarks and the text block still
   byte-identical raw JSON; 4 concurrent reads all clean.

   **The last seam, openclaw calling it, split in two on 2026-09-14 after
   recon found openclaw is not installed anywhere.** VM 106 is a bare Ubuntu
   clone: no docker, no node, no openclaw, empty `/opt` (verified read-only
   twice, once by the orchestrator). The workstation scaffold at
   `../openclaw` is config-only, pulls `ghcr.io/openclaw/openclaw:latest`,
   and its `agent.yaml` schema has **no `mcp` key at all**, so the
   `mcp.servers`/`agents.entries` shape in
   `research/2026-09-12-openclaw-mcp-auth.md` is unconfirmed against anything
   that runs. Full recon: `research/2026-09-14-openclaw-mcp-wiring.md`.
   - **DONE 2026-09-14: the server half.** `dfmcp-server.service` is active
     and **enabled** on VM 103 as `df`, from `/opt/df/dfmcp-smoke` (promoted
     in place, sha256-identical to `main`), **bound to the LAN address**
     (user's call: simple now, Tailscale another day, so **bearer tokens are
     the only guard**), tokens in a mode-600 `.env`, survives restart.
     **VM 106 has called it for real, with curl alone**: initialize, the
     architect's 9 read-only tools, `landmarks__list` returning live fort
     JSON, bogus token 401. Re-verified by the orchestrator. Reversal steps:
     `handoffs/2026-09-14-dfmcp-deploy.md`.
   - **DONE 2026-09-14: the client half's knowledge step.**
     `handoffs/2026-09-14-openclaw-install.md` (Result plus Orchestrator
     correction sections).
     - OpenClaw 2026.9.4 (`3a9d69d`) is pulled on VM 106 and was run only as
       throwaway CLI containers. Nothing listens and nothing is running, so no
       `services.yaml` entry is owed for VM 106 yet.
     - The research brief's `mcp.servers` schema is **confirmed against the
       real binary's `config schema`**: `url`, `transport:
       streamable-http`, `headers.Authorization`, `toolFilter`, and
       per-agent `agents.entries.<id>.tools.allow/deny`.
     - `${VAR}` substitution in headers works live.
     - A `df-overseer` entry with a placeholder token reached VM 103 and got
       401.
     - `/opt/openclaw/config/openclaw.json` holds that entry with an
       unresolved `${DF_MCP_TOKEN_PLACEHOLDER}` reference, and is kept for
       the next step.
     - **Scaffold gap:** `../openclaw`'s compose uses `OPENCLAW_CONFIG_DIR`
       and `OPENCLAW_AUTH_PROFILE_SECRET_DIR`, which the image never reads.
       Use `OPENCLAW_STATE_DIR`, or config is silently lost when the container
       is recreated.
     - Reversal: `docker rmi ghcr.io/openclaw/openclaw:latest; sudo rm -rf
       /opt/openclaw`.
   - **DONE 2026-09-14: an agent has called the fort.**
     `handoffs/2026-09-14-openclaw-first-agent-call.md`.
     - `openclaw agent exec` on VM 106, model `deepseek/deepseek-v4-flash`,
       architect token, called `df-overseer__landmarks__list` once and
       answered correctly. It cost $0.0032, and 4 of its 5 attempts failed
       locally for free.
     - Verified by the orchestrator:
       - every MCP 200 since 09:30 on VM 103 came from VM 106;
       - `dfhack-run df-overseer-landmarks list` on VM 103 gives the same 4
         landmarks;
       - the probe shows the 9 read-only tools from
         `agents/architect/tools.yaml`.
     - **State left on VM 106:**
       - `/opt/openclaw/secrets/openclaw_secrets.env` (0600) holds the
         architect token and the DeepSeek key;
       - **the DeepSeek key is also plaintext in
         `/opt/openclaw/config/state/openclaw.sqlite`** (openclaw's
         `models auth paste-api-key`, needed because an env var alone gave
         `Unknown model`);
       - the architect token is in the env file only;
       - the `@openclaw/deepseek-provider` plugin is installed.
       Nothing listens.
     - Reversal: `sudo rm -rf /opt/openclaw` removes both secrets.
   - **DONE 2026-09-14: first architect charter run.**
     `evals/live/2026-09-14-architect-first-charter/` (README has the
     charter check), `handoffs/2026-09-14-openclaw-architect-charter-run.md`.
     - `role.md` was delivered as openclaw's `SOUL.md` bootstrap file. Tools
       were restricted to `df-overseer__*` via a pinned config overlay.
     - DeepSeek v4-flash made 26 read calls and produced **one well-formed
       `workshop_siting` proposal**: the 5x5 open ground 5 tiles S of the
       Embark Site. It used no raw coordinates, gave a falsifiable prediction
       and a cost, flagged the SE stair chokepoint for the Overseer, and
       declined a blind dig. It cost $0.0043.
     - Orchestrator checks:
       - every non-empty `.env` secret and address was scanned against the
         new files, with a positive control;
       - the two VM 106 secrets were compared by hash;
       - nothing listens on VM 106.
     - **Open, unverified: its underground search may have been meaningless.**
       It called `diggable.find` with z = 0, -1 ... -4 and found nothing,
       yet this fort had 41 tiles dug on 2026-09-11.
       `df-overseer-diggable.lua`'s header says z defaults to the landmark's
       own z, which implies an absolute DF z-level. Negative values would
       then be off-map. If true, the tool gives a coordinate-free caller **no
       way to say "one level down"**, a design gap against commitment #1.
       Next step: check what z the script receives and returns for a
       negative value, then consider a relative `levels_below` argument.
     - **Part A found no headless way to un-plaintext the key.**
       `auth.profiles.<id>` has no key or SecretRef field in the config
       schema, and `secrets configure`, the command that advertises SecretRef
       mapping, requires an interactive TTY. The user could try it by hand
       over `ssh -t`.
   - **NEXT (needs the user's call):**
     - whether the DeepSeek key stays on VM 106;
     - trying `openclaw secrets configure` interactively to get it out of
       plaintext;
     - then a durable gateway, from a fixed scaffold (`OPENCLAW_STATE_DIR`)
       or the CLI recipe, which would owe a home-lab `services.yaml` entry;
     - then an agent with a real charter (`agents/*/role.md`) instead of a
       one-shot question.
   - **OWED once the unit is enabled**: a `home-lab` `inventory/services.yaml`
     entry for the new service on VM 103. No live `home-lab` session existed
     when this was dispatched, so it is recorded here as open, per
     `CLAUDE.md`'s upstream-obligations rule.
   VM 103 got `python3.12-venv` (user go-ahead); `install_df.py` now installs
   it. Full table: `handoffs/2026-09-14-mcp-live-smoke-test.md`.
   **openclaw has still not called it**: that is the next reality gap.

   Superseded 2026-09-14, kept for the reasoning: **NOTHING HAS MET REALITY.**
   No live DFHack, no bound socket, no openclaw
   client. Every test runs against a fake DFHack server written from the same
   wire spec, which means a place where the VM's actual binary diverges from
   the source the research read would pass every test here. **The single
   highest-value next action is the live smoke test**, and the exact commands
   are in `handoffs/2026-09-12-mcp-transport.md`'s closing note. It touches
   VM 103, which runs the live fort, so it needs the user's go-ahead and a
   heads-up to a live `home-lab` session first.

   **Verified in the orchestrator session rather than taken on an agent's
   report**: the design's central claim, that an advisor calling a write tool
   is refused with the reason string intact and the call never reaches DFHack,
   run through a real SDK client. Also re-verified by hand: the DFHack wire
   protocol's design-forking property, and the package-name collision below.

   Superseded detail follows, kept because the reasoning is the reusable part.

   **Build the MCP server. IN PROGRESS 2026-09-12, three parallel streams.**
   It is the one hard blocker: nothing else can progress without it, and every
   design requirement it must satisfy is already settled and written down
   (server-side allowlist enforcement, one token per role, one persistent DFHack
   RPC connection rather than shelling out per call, batch a cycle's reads into
   one suspend window). **Four of the five modules are done and tested**
   (`registry.py`, `roles.py`, `tools.py`, `auth.py`, `dfhack_client.py`);
   **only the transport is missing**, and it is now unblocked.

   **RENAMED 2026-09-12: the package is `dfmcp/`, not `mcp/`.** It had to be.
   The Python MCP SDK is also imported as `mcp`, and a local `mcp/` directory
   shadows it for anything running with the repo root on `sys.path`, which is
   every test run and would have been the server itself. `import mcp.server`
   resolved to *us*, so the transport could not have imported its own SDK.
   Caught before the transport stream was dispatched rather than inside it.
   Earlier `decisions/DECISIONS.md` rows and the dated `research/` briefs still
   say `mcp/`; they are historical and were deliberately left alone.

   **Split on where the unknowns are**, which is the only reason three things
   can run at once:
   - **Research, DFHack RPC wire protocol: BACK, and it corrected the design
     doc** → `research/2026-09-12-dfhack-rpc-client.md`. Build against it
     rather than re-deriving. Four things settled. **(1) A connection carries
     one request at a time**, so the server needs a small **pool** of
     persistent connections; `docs/AGENT-ARCHITECTURE.md` §14 item 5 said "one
     persistent connection" and is now corrected in place, along with §6.
     Persistence was always the latency win and survives; only the count was
     wrong. **(2) Hand-roll the wire protocol**, no `protobuf` dependency: the
     messages are flat, `BindMethod` is not even needed since `RunCommand` is a
     hardcoded id, and the one existing Python client is unmaintained,
     unlicensed and mis-frames replies over 16MiB. **(3) JSON comes back
     clean**, one fragment per `print`, colour in a separate field, so no
     sanitising and `docs/TRAPS.md`'s escape-sequence trap turns out to be
     about `dfhack-run`'s own rendering rather than the wire. **(4) The socket
     is unauthenticated and loopback by default**, confirming §13's premise.
     **Verified here, not taken on the agent's word**: the design-forking claim
     (1), plus the handshake, header layout and method ids, were re-checked
     against the *installed* build's own protocol docs at
     `hack/docs/docs/dev/Remote.txt`, whose "Conversation flow" section shows
     the same strictly sequential request/text/result cycle.
   - **Build, transport-independent half: DONE and merged, 45 tests to 86** →
     `handoffs/2026-09-12-mcp-tool-schema.md`. `dfmcp/tools.py` (registry plus
     roster to MCP tool definitions, and a validated call back to the exact
     DFHack argv) and `dfmcp/auth.py` (bearer token to role, `compare_digest`
     against every configured token, never logs a token). `dfmcp/` is now four
     modules and still opens no socket. **Its session ended mid-run**, the
     second stream to die that way in one day; both deliverables were already
     committed to its branch and survived, and only the final doc pass was
     lost and finished by hand. **Check the branch before assuming a dead
     stream lost work.**
   - **Research, MCP server stack: BACK** →
     `research/2026-09-12-mcp-server-stack.md`. **The crux answered yes**,
     per-caller `tools/list` works, but **only at the low-level `Server` API**:
     the high-level wrapper's `list_tools()` takes no arguments and returns one
     static list for everyone. So build on the low-level API, on streamable
     HTTP, with `TokenVerifier` mapping bearer token to role, and return an
     allowlist denial as a tool result carrying `isError` rather than a
     protocol-level error, which the client raises in its own calling code
     instead of showing the model. **One blocking unknown, and it is on the
     client side**: whether openclaw can send a **static bearer header** at
     all, or requires a real OAuth handshake. The locked design is a static
     per-role token, so if openclaw cannot send one, either the token scheme or
     the client config has to change. **Settle that before building the
     transport.**
   - **CLOSED 2026-09-12, same day it was raised** →
     `research/2026-09-12-openclaw-mcp-auth.md`. **A static per-role bearer
     token works**, as a per-server header map whose value can come from an
     environment variable rather than a config file, which this public repo
     needs. **The one-token-per-role scheme survives**: the same URL declared
     once per role, each entry with its own token, because entries are keyed by
     name not by URL. Denial reasons returned as an `isError` tool result do
     reach the model as readable text, so the reason strings `Roster.check`
     already produces are not wasted. **So the transport is unblocked and gets
     built exactly as the stack brief planned.** Honest limit: both sides were
     read, neither was run against the other; the settling experiment is a
     dummy verifier plus a throwaway agent, named in the brief.
     **It also corrected §14 item 1**, which named a harness-specific key as
     one of three per-agent scoping mechanisms. The general one is the
     per-agent `tools.allow/deny` list. Conclusion unchanged, mechanism
     different, and it matters only because that layer is defence in depth: the
     wrong key would look correct and silently leave the enforced boundary as
     the only one.

   **`handoffs/` now exists** (`aba202b`), the template convention this repo had
   never needed until now. One deliberate departure from `.claude/agents/executor.md`'s
   default, recorded in `handoffs/INDEX.md`: **executors do not write
   `Working.md`, `decisions/DECISIONS.md` or `memory/`.** The orchestrator
   session owns the register, so concurrent agents cannot conflict on this file
   and it keeps one voice. They report findings; the register row is written
   here.
3. **Then one supervised end-to-end cycle**: the Overseer making a single real
   decision through the seam. **This is the first thing that would advance the
   project's actual thesis**, as opposed to its foundations. Nothing today did.
4. **Fix the `set_labor`/`autolabor` race.** Small, and it is a single-writer
   violation live in production right now.
5. **The breach question**, opportunistically: wait for rain or an animal
   fording water rather than deliberately flooding the fort.

**Do not start by writing more design.** Today produced a great deal of it and
the ratio is already uncomfortable: a 14-section architecture over a tool surface
that is 18-of-25 read-only. The architecture doc is a target, not a plan.

**CORRECTED 2026-09-12, user caught this:** an earlier version of this brief
said openclaw's VM needed the `home-lab` session before it could be provisioned.
**Wrong. Provisioning is entirely this repo's own.** `scripts/provision_vm.py
clone` exists, the pool-scoped token holds `VM.Clone`, and `.env` carries
`PVE_NODE`, `PVE_POOL`, `DF_TEMPLATE_VMID` and `DF_VMID`. That is the whole point
of the sandbox pool. Two separate things had been conflated:
- **Provisioning: ours, and unblocked right now.** The IP allocation that *was* a
  genuine prerequisite is already done and written on home-lab's side.
- **Recording it: theirs, and only AFTER the fact.** What is owed is the
  `guests:` entry in `inventory/hosts/SRV-01.yaml` with the real VMID, plus
  `inventory/services.yaml` if a service moves. A post-hoc record, not a gate.

**DONE 2026-09-12, and the deferral discharged exactly as intended**: the VMID
went to a live `home-lab` session the moment the VM existed, rather than being
carried by a handover. Kept here only because the reasoning above is what made
the distinction between provisioning (ours) and recording (theirs) clear.

**One thing still needing the user rather than a session:** nothing. The
address-leak cleanup and its `CLAUDE.md` edits were authorised 2026-09-12 and
delegated.

### Done this session

- **[`docs/AGENT-ARCHITECTURE.md`](docs/AGENT-ARCHITECTURE.md) written**, the
  full design: 8 principles, 5 components (2 of them code with no model in
  them), a 6-role roster, the communication protocol, the information
  architecture, graded urgency, write authority, reliability, recording and
  learning, modularity, explicit non-goals, and open questions. It is a design
  artifact and says so at the top.
- **Extensive new rows in `decisions/DECISIONS.md`, all dated 2026-09-12**
  (`grep -c '^| 2026-09-12 |'` for the live count; a hand-maintained number
  here drifted three times in one session, so it is deliberately not restated). The doc is the design; the rows
  are why each call was made, including the ones that were later corrected.
- **`ROADMAP.md` updated**: two new Now items (the architecture, and the MCP
  server as the standing blocker), and three stale items corrected where the
  design closed them.
- **`agents/` scaffolding built**, the first non-document artifact of this phase:
  `ROSTER.yaml` (the single file you edit to change the roster), a `README.md`
  stating the file contract, full three-file sets (`role.md`, `tools.yaml`,
  `model.yaml`) for the three enabled roles, and charters for the three
  disabled ones. **Tool allowlists reference real `TOOLS.yaml` ids**, each
  tagged `exists` or `planned`, so the file cannot silently imply a capability
  this project lacks. The disabled roles deliberately have **no** `tools.yaml`
  or `model.yaml`, for the same reason, and each charter names exactly what
  blocks it plus the traps for whoever builds it.

### The shape that was settled, in one paragraph

One actor (**Overseer**, sole writer, strongest model). Read-only
**specialists** (Architect, Quartermaster, Marshal, Consultant, Chronicler)
that may call exactly one write tool, `propose`. Two code components: a
**Sentry** (reflexes, graded escalation, status publishing) and **Triage**
(diff plus thresholds each heartbeat, so a quiet cycle costs zero tokens).
Latency is answered by **playbooks executed as code**, not by more actors.
Communication is one append-only queue that is channel, audit log and
write-ahead log at once; writes are tool calls with typed fields, reads render
as XML; no peer-to-peer chat in v1. One snapshot per cycle, per-role
projections, three information tiers. Confidence is **tool-stated for facts**
(`MECHANICAL`/`DERIVED`/`HEURISTIC`) and **measured from graded predictions**
for proposals; self-reported confidence is never a decision input.

### Research: all four briefs back, all folded into the doc and register

1. `research/2026-09-12-write-conflict-matrix.md` — **back**, findings below.
2. `research/2026-09-12-openclaw-primitives.md` — **back.** The design's
   biggest risk cleared: **per-agent models and per-agent tool scoping are real
   features**, so principle 8 is enforceable and §11 stands. But four
   constraints landed: **no hard spend cap in the host** (budget enforcement is
   ours plus provider-side caps), **fan-out is lane-serialised** at roughly 30s
   per target so waking five specialists may cost minutes, **the only external
   push wake is an authenticated HTTP hooks endpoint** (that is how the Sentry
   reaches the Overseer), and **host crash recovery does not cover external
   side effects**, which makes the write-ahead queue the actual recovery
   mechanism. Also **corrected a 2026-08-25 register claim**: openclaw's
   exponential retry backoff does not hold for heartbeat. Recorded as
   reported-by-brief, not independently confirmed here.
3. `research/2026-09-12-multi-agent-architecture-prior-art.md` — **back.**
   No-peer-chat **survived review** on convergent multi-source evidence, with
   one doctrine-backed v2 relaxation identified (read-only cross-advisor
   visibility without authority). Produced the best reframe of the session:
   **this is a blackboard system and we had rebuilt only a third of one**; the
   missing piece is an **explicit advisor scheduler**, now named inside Triage.
   Calibration method settled: Brier plus a coarse reliability diagram now,
   track-record weighting next, reference-class forecasting explicitly
   deferred.
4. `research/2026-09-12-dfhack-capability-checks.md` — **back. All six settled
   from source** at the matching version tag (53.16-r1.1), five with high
   confidence. Frame cap: **yes**, but it slows agent tool calls too, because
   DFHack's suspend window is tick-gated, so the throttle tier is a latency
   trap and pausing may actually beat it (unmeasured). Overlay: **yes** and
   headlessly drivable. **`dfhack-run` concurrency: safe, unordered,
   tick-gated**, which **kills the throughput argument for partitioning write
   authority** and also source-confirms the root cause of the previously
   unexplained 45-80s command delay. Priorities: 1-7 for digs, **list position
   for work orders** (no priority field exists). Wake vocabulary: **five of
   nine real; `breach` has no signal at all, and `hostile_detected` only fires
   on registered invasions**. `dfhack.persistent`: no internal locking, 7
   integer slots per entry, whole-file rewrite per save.

### Findings already in from the write-conflict audit

- **`set_labor` already races `autolabor` on ordinary citizens.** Verified at
  source (`df-overseer-labor.lua` writes `unit.status.labors[code]` directly,
  no coordination), not taken on the subagent's word. autolabor exempts only
  military-duty and burrow-restricted units, so the exemption is real but
  narrow. `ROADMAP.md`'s parenthetical claiming autolabor "doesn't
  blanket-override the manual primitives" was an overstatement and is
  corrected in place. **This is a single-writer violation that exists in
  production today**, before any roster is built. **Fix not yet designed.**
- **The Quartermaster and Chronicler roles have essentially no tool surface.**
  Neither manager work orders nor stockpile settings (filters, thresholds,
  links) have any tool in this repo, and DFHack's `stocks`/`workflow` are
  tagged `unavailable` on this install, so the "work orders plus stockpile
  settings is a disjoint write domain" hypothesis is **untestable rather than
  confirmed**. No tool writes a chronicle entry anywhere.
- **18 of 25 existing subcommands are pure reads**; only 7 mutate (3 via
  `quickfort -c`, 1 direct labor write, 3 via the UI input path). The three
  quickfort mutators are cleanly sliceable and mutually disjoint by
  construction; the three UI-path writers are the least sliceable of all,
  since their mutation target is whatever screen happens to be focused.
- **Two read-only tools share one unpartitioned `_G` table** across all
  callers: a shared-resource hazard for concurrent *readers*, even under a
  single writer.

### Next concrete step

**All four briefs are in and fully folded into `docs/AGENT-ARCHITECTURE.md`,
`decisions/DECISIONS.md` (25 rows today) and `memory/dfhack-environment.md`.
The design is no longer the blocker: the tool surface is.** Three things gate
any build, in this order.

1. **SUPERSEDED 2026-09-12: the MCP server exists** (`dfmcp/`, six modules,
   136 tests), and it was built with per-role identity and scoping designed in
   from the start, exactly as this item demanded. Both requirements below are
   enforced in code. Kept because the requirements are what the build was held
   to, and because the reasoning for the topology has not changed.

   **The MCP server still does not exist**, and it needs per-role identity and
   scoping designed in from the start. **Topology decided 2026-09-12 (user
   confirmed both halves): openclaw gets its own new VM on SRV-01; the MCP
   server and the Sentry stay on VM 103 with DF**, because DFHack's RPC socket
   is unauthenticated and must not cross the network. MCP over HTTP on the
   tailnet, never public. **Two requirements recorded before the server exists,
   deliberately**: the allowlist is enforced **server-side** (openclaw's own
   per-agent scoping is defence in depth, not the boundary, since client-side
   enforcement is not enforcement), and **role identity is a credential, one
   token per role**, never a self-declared header, or the Architect could
   assert it is the Overseer and obtain write tools. → `docs/AGENT-ARCHITECTURE.md`
   §13.

   **DONE, all of it:** the transport-independent half described below landed,
   and so did the three modules that did not exist when this was written.

   **IN PROGRESS:** the transport-independent half is being built now in an
   isolated worktree: `dfmcp/registry.py` (loads `TOOLS.yaml`, canonical tool ids,
   preserves each tool's own verified/unverified status) and `dfmcp/roles.py`
   (resolves `ROSTER.yaml` plus per-role allowlists, with **hard load-time
   errors**, notably that any role other than `sole_writer` holding a mutating
   tool fails to load). Includes rewriting the three `tools.yaml` files from raw
   signature strings to canonical ids.
2. **DECIDED: v1 enables three roles, Overseer plus Architect plus Consultant**
   (user's call 2026-09-12, over this session's narrower recommendation of
   Overseer alone). These are the three whose tools exist. Quartermaster,
   Marshal and Chronicler keep charters and directories but stay disabled, so
   enabling one is a config change. **Consequence to carry forward: the
   advisor scheduler is load-bearing from day one**, not at some future scale,
   because with three agents the host's ~30s-per-target send serialisation
   shows up immediately.

3. **UPDATED: both safety detectors are now built and landed, and neither has
   ever been run.** `scripts/dfhack/df-overseer-threat.lua` (`scan`) and
   `scripts/dfhack/df-overseer-breach.lua` (`check`), plus their `TOOLS.yaml`
   entries, both tagged `live_deployed: false` / `verified: unverified`.
   Reviewed here rather than accepted on report: coordinate discipline is
   correct and both carry the `--@module = true` guard.
   **THE THING TO KNOW: the breach detector may be inert.** Every observed use
   of `block.flags.update_liquid` in the installed build's shipped scripts
   *sets* it and nothing reads it, so whether DF's own simulation raises it
   during natural liquid movement is unverified. Its cheap stage-1 trigger
   depends on that flag. **Until settled live, treat flood response as covered
   by nothing, exactly as before the detector existed**, because a detector
   that never fires invites the same false confidence `unit-status hostile`
   already cost this project. Also corrected along the way:
   `df.global.world.flows` does not exist, and this session had repeated that
   error into the design doc and a role charter; all corrected, with a §10
   correction appended to the research brief.
   **LIVE VERIFICATION DONE 2026-09-12** (user granted VM authority; fort
   saved and backed up first, health identical before and after, 15 citizens,
   0 wounds, re-paused and confirmed).
   **Threat detector: VERIFIED WORKING on both motivating failures.** `scan`
   returned a fox and a weasel, both admitted purely by shared walkable group
   with no danger flag; and the two `DEMON_4` units that DO have
   `isDanger`/`isGreatDanger` set were correctly absent, confirmed by direct
   raw query rather than by trusting the scan's silence (walkable group 0,
   109-115 tiles from any landmark). Reachability gates admission, flags do
   not. Both documented failures corrected in one tool.
   **Breach detector: INCONCLUSIVE, so treat flood response as still covered
   by nothing.** `update_liquid` was set on zero of 26,784 blocks on all 11
   polls including through an 85s unpaused window, but the map's water is
   fully settled (`flow_size=7`), so this cannot distinguish "DF never sets
   it" from "DF sets it only on change, and nothing changed". The limits
   (no breach, no dig, no magma) deliberately forbade creating the one
   condition that would settle it. Stage-1 cost measured and cheap: ~0.057s
   CPU for the full block scan. Future route that respects the limits: an
   opportunistic test during rain or an animal fording water.
   **One real bug found and fixed**: `designation.liquid_type` is a Lua
   boolean, not the `df.tile_liquid` enum, so the magma comparison was always
   false and severity could never reach `critical`. Fixed with a deliberate
   dual check, because this install's own `spawn-liquid.lua` hedges the same
   field both ways.

   Superseded text, kept for the reasoning: **two safety detectors did not
   exist and were required work, not polish.**
   **A breach poller**: no DFHack event or announcement type exists for water
   or magma breach at all (a checked negative), so **flood response is
   currently covered by nothing**, and breach is among the fastest
   fort-killers. **A real hostile detector**: `onInvasion` fires only for
   registered invasions, not ambushes, thieves, or wildlife turning
   aggressive, which is the *event layer* having the same blind spot as the
   already-known-unreliable polling signal. Until both exist, the Marshal has
   no trustworthy trigger to write playbooks against.

Also now more urgent than it looked: the **`set_labor`/`autolabor` race**, since
it is the only labor write that exists and two of the four unbuilt roles will
want it.

**Live checks.** The `Core::Update`-while-paused question is **settled, from
source and confirmed live, 2026-09-12: pausing does not stall tool calls.** Ten
round trips against the paused fort all landed between 0.66s and 1.28s, no
stall, tick counter correctly static, fort verified paused before and after and
never unpaused. **Then the user corrected the conclusion drawn from it**, and the
correction is the durable part: the unit is **game time elapsed per decision**,
not wall-clock latency. Game time per cycle is roughly **`f·T + k` ticks** (`f`
frame cap, `T` thinking seconds, `k` tool calls), so lowering `f` shrinks the
thinking term linearly down to a `k`-tick floor. **Throttling does buy thinking
time**; the wall-clock price is paid by the human watching, not the fort. Pause
is the only lever reaching zero. **Choose on cycle shape, not urgency**:
think-heavy cycles throttle well, call-heavy cycles should pause instead. And a
free optimisation nobody had spotted: all suspenders pending at once are
serviced in **one** window, so `k` concurrent calls cost ~1 tick versus ~`k`
sequential, which is a game-time argument for the single-snapshot read pass on
top of the consistency one.
→ `research/2026-09-12-dfhack-capability-checks.md` §9,
`docs/AGENT-ARCHITECTURE.md` §6. **Two remain deliberately unrun, user's call to defer**: whether the
frame cap survives loading a different save in one process (needs a save load on
the live fort, and this project has already lost one fort's save, so not done
casually), and whether an overlay widget renders in the headless Xvfb/VNC
pipeline (only matters if the status banner goes inside the game rather than
beside the stream, and the outside-the-game route is recommended precisely
because it cannot perturb the fort).

### CLOSED 2026-09-12: home-lab obligation for openclaw's VM, both halves

**Fully discharged, and confirmed written on their side.** The IP was
pre-allocated before assignment (the prerequisite half), and the real VMID plus
name, address, host, memory, clone lineage and purpose were sent to
`home-lab-03` for the `guests:` entry the moment the VM existed (the post-hoc
half). They have since confirmed **VM 106 is in `SRV-01.yaml`'s `guests:` block
and `.203` is marked built in `ips.yaml`**, both carrying `confidence: inferred`
with a `second-hand-from` block pointing at this repo's SSH verification rather
than their own observation, which is their rule for facts they have not seen
directly and is the correct handling of anything we tell them.

**ONE STANDING OBLIGATION, not yet due.** `inventory/services.yaml` needs an
entry **once openclaw is actually running something**, which it is not yet: a
provisioned VM is not a service. Agreed explicitly with `home-lab-03`, who will
add it when told. **So whoever brings openclaw up is the one who owes that
message.** This is the only thing still outstanding upstream, and it is
deliberately recorded here because it will come due in a later session than the
one that agreed it. **The address in `.env`
was confirmed to match `ips.yaml` exactly before anything was created.** The
history below is kept because the ordering it establishes is the reusable part.

Original section follows.

**Not yet triggered, deliberately raised early.** The decided topology needs
**one new VM on SRV-01** for `openclaw`. Nothing is created yet, so nothing in
`home-lab/inventory/` is currently wrong, but per this repo's upstream
obligation the IP must be allocated through `home-lab/inventory/ips.yaml`
**before** it is assigned. Skipping that step is exactly how a DF VM's address
came to be in use for a week while registered nowhere (`CLAUDE.md` names the
specific case; deliberately not repeated here, see the redaction note below).

**Routed 2026-09-12 to the live `home-lab-03` session** (this repo is not
authorised to edit home-lab). **Answered:** SRV-01 has comfortable headroom for
one more small guest (checked live: several GB RAM free, moderate load), and its
read is that this need not wait on SRV-02's stability since the two hosts are
unrelated here. **Address: user's call is to stay in the existing 200+ block
rather than reuse the freed `.157`.**

**CLEARED and ALLOCATED 2026-09-12.** The user confirmed directly to
`home-lab-03`, which has written the pre-allocation into `inventory/ips.yaml`
(committed there, not pushed). The address is recorded **only** in this repo's
gitignored `.env` as `OPENCLAW_VM_IP`, per the never-in-a-tracked-file rule; a
commented empty placeholder was added to the tracked
`infra/local.example.env`.

**Mechanism, and it is now a general pattern rather than a one-off:** the
address is static via `ipconfig0` at clone time, **not** a MAC-keyed DHCP
reservation, because df-automation's sandbox VMs do not hold a constant MAC
across rebuilds, so the reservation mechanism home-lab's registry otherwise uses
would not survive one. home-lab has recorded that as the standing pattern for
df-automation-provisioned sandboxes.

**Still owed to home-lab when the VM exists:** the real VMID, so they can add
the `guests:` entry to `inventory/hosts/SRV-01.yaml`. Nothing else outstanding.

Two notes from the episode: the gate was cleared by the user speaking in the
other session, not by this one pushing, which is the correct shape (see the
coordination note below); and the registry turned out to be *ahead* of the
router on the freed address, not behind it, contrary to this session's initial
assumption. **Still owed when the
VM actually exists:** the `guests:` entry in `inventory/hosts/SRV-01.yaml` with
the real VMID and address, and `inventory/services.yaml` if a service moves.
**Recorded here as open so it survives this session ending.**

Target host is SRV-01 deliberately: SRV-02 was crashing roughly every 2.5 hours
as of 2026-09-12, root cause open, and a power-brick swap was confirmed not to
be the fix.

### DONE 2026-09-12: `clone` would have handed openclaw the running fort's address

Found by reading `cmd_clone` before running it, which is the only reason it was
found at all. `guest_address()` read **`DF_VM_IP` and nothing else**, and the
`clone` subcommand had no address flag, so provisioning openclaw's VM would have
configured it with **VM 103's address**: a collision against the live fort, from
a command that would have logged success. **Confirmed against the real host
before fixing**, not argued from the code: `DF_VM_IP` resolved to a pool holder
of `103`, `OPENCLAW_VM_IP` to `None`.

The hardcoding was correct when written, with one guest in the pool. It became
wrong the moment a second address was allocated, and nothing connected the two
facts. **This is the shape to watch for in the rest of this repo**: single-guest
assumptions baked in when the pool had one guest. `DF_VMID` defaulting is worth
a look on the same grounds.

**Fixed** in `scripts/provision_vm.py` (`d587ea1`): `guest_address(env, var)`
plus `clone --ip-var`, a `pool_address_holder()` check that refuses **before**
the clone API call so a rejection cannot strand a half-built VM, and `DF_GW`/
`DF_DNS` deliberately left unparameterised because a gateway and a resolver are
properties of the subnet, not of a guest. Guard's stated limit, in the code: it
sees only our own pool, so `home-lab/inventory/ips.yaml` remains the authority
for anything outside it and this does not reduce that.

**One process lesson worth more than the bug.** Verifying that `.env` and
home-lab's registry agreed, a hand-rolled parser reported a first-octet
mismatch. It was wrong: it did not strip the single quotes `pve.load_env`
strips. Re-running through the **real code path** showed exact agreement. The
check that nearly raised a false alarm about another repo's registry was itself
the broken thing, which is `CLAUDE.md`'s "verify the verification" rule biting
in the direction of a false positive rather than a false all-clear.

### DONE 2026-09-12: the address leak is closed, with a test that keeps it closed

`CLAUDE.md` states twice that hostnames, addresses and subnets must never be
committed here. Tracked files broke it, including `CLAUDE.md` itself. Now fixed.

**Corrected on the way in:** there were **3** distinct real addresses, not the
"roughly four" this section previously claimed, and one of them appeared only in
a single research file. Loopback (`127.0.0.1`) appears dozens of times and is
correctly **not** a leak: it is identical on every machine and reveals nothing.

**What changed.** `CLAUDE.md`'s own leaked address redacted, and its `docs/`
bullet now lists all five docs rather than two. Five real-address occurrences
across four `research/` files redacted to this repo's `<placeholder>`
convention, no facts altered. **Two script help strings that used the REAL relay
address as their example** replaced with RFC 5737 documentation addresses; an
earlier note here wrongly cleared all the `scripts/*.py` hits as harmless, and
two of three were genuine. `ROADMAP.md` and `decisions/DECISIONS.md` redacted
too (15 literals), which had been deferred and would otherwise have left a
permanent hole in the guard below.

**The guard: `tests/test_no_leaked_addresses.py`, a test rather than a git
hook**, because hooks are per-clone and are not shared through git while a test
runs in the suite that already exists. 45 tests pass. **Verified by injecting a
real violation and watching it fail**, naming file, line and value, then
reverting; the agent's own verification of this had been compromised (see below),
so it was redone here.

**Two instructive failures worth keeping:**
- **The detector passed while untracked and failed the moment it was
  committed**, because it scans `git ls-files`. Its own unit-test fixtures
  necessarily contain matching strings.
- It also **flagged itself for containing the real addresses** in its comments
  and fixtures. A leak-detector holding the leaked values defeats its own
  purpose. Fixed by making every value in that file synthetic and excluding the
  file from its own scan, with the tradeoff stated in the code: because it is
  not scanned, a real value pasted there would not be caught, so keep it
  synthetic by convention.

**Deliberately still holding real addresses: `working-archive/`.** It is a
historical record and rewriting it would falsify it. Excluded from the guard's
scope with a comment saying why.

**Not fixed and not fixable: git history.** These files were already pushed, so
nothing above removes anything from history. That was a deliberate fix-forward,
on the proportionate reading that RFC1918 addresses behind a tailnet are low
value, and the reason to act was that the rule is deliberate and the drift kept
growing, including from this session.

### Peer coordination notes

- At the time of the live pause check there was **no peer session** (the
  `home-lab` session present at this session's start had ended), so the
  pre-VM-work heads-up this repo's rules call for had no recipient. Recorded
  rather than skipped silently.
- A new peer, `home-lab-03`, appeared shortly after and **was** given the
  heads-up. It confirmed VM 103 quiet and quorum healthy, and it **deferred an
  outlet-swap test that would have power-cycled SRV-01** (and therefore VM 103
  and the live fort) specifically to avoid disrupting this work. It will give
  lead time before any future attempt, which this session asked for so the fort
  can be quicksaved first. DF ignores SIGTERM, so an abrupt host power loss
  means no save.
- No home-lab inventory obligation arises from any work actually done today:
  nothing was created, deleted, resized or re-addressed.

**Ruled out already, so nobody re-derives it:** one agent per squad (DF combat
resolves faster than an agent round trip, and the threat sensor is verified
unreliable); multiple general writers (no transaction boundary in DF); an
efficiency-analysis agent and a safety-veto agent (both are code);
self-reported confidence as a decision input; publishing raw agent thinking.

**Not yet asked for:** this session's work is committed locally as `500d8ce`
and **not pushed**, which is the only unpushed commit on `main` (the
handover below claimed five; that claim was stale and is corrected there).
Publishing the reasoning stream (§8) is designed but explicitly needs its own
go-ahead, separately.

## HANDOVER — archived

The 2026-09-12 session-end handover moved wholesale to
[`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md)
(file was past the ~400-line threshold). Its durable-traps list now lives
permanently at [`docs/TRAPS.md`](docs/TRAPS.md) — **read it there, and add new
traps there rather than here.** Current state is the section above.

## Archived

- Sections through 2026-09-10 (fifth handover) — provisioning build,
  perception eval, fort ledger, systemd units, title-screen bootstrap,
  live-viewing/relay/tunnel, the tileset investigation, Site Finder
  resolution, the embark-flow saga through both forts founded, and the
  seed-landmark bootstrap — all moved wholesale to
  [`working-archive/Working_archive-2026-09-07.md`](working-archive/Working_archive-2026-09-07.md)
  as each was superseded or reported itself finished.
- 2026-09-09: the 2026-09-08 (evening) handover moved wholesale to the
  same archive file.
- 2026-09-09 (end of session): this session's full handover (title-screen
  bootstrap resolution, the entire live-viewing/relay/tunnel build, the
  tileset investigation, and the Site Finder "Begin" resolution) moved
  wholesale to the same archive file — exceeded the ~400-line threshold,
  not superseded. The handover above is the tight current-state summary;
  the archive has the full detail.
- 2026-09-10: the 2026-09-09 (end of session) handover moved wholesale to
  the same archive file, superseded by this session's own handover above
  (Cloudflare Tunnel completion, the graphics-completeness fix, and the
  live embark-flow attempt).
- 2026-09-10 (second handover today): that session's own handover moved
  wholesale to the same archive file, superseded by this session's handover
  above (the click-registration mystery resolved, the real embark mechanism
  found, and the new "Confirm" crash).
- 2026-09-10 (third handover today): that session's own handover moved
  wholesale to the same archive file, superseded by this session's handover
  above — **the first fort was founded**, and the "Confirm" crash resolved
  empirically via gdb.
- 2026-09-10 (fourth handover today): that session's own handover moved
  wholesale to the same archive file, superseded by this session's handover
  above — the `find_mm_*`/`warn_mm_*` coordinate-frame bug found, and
  `xdotool` real-input fix for headless map/hover interaction discovered
  and validated.
- 2026-09-10 (fifth handover today): that session's own handover moved
  wholesale to the same archive file, superseded by the handover at the top
  of this file — the text-only sweep built and run, a Windows-specific SSH
  command-line truncation bug found and fixed in `provision_vm.ssh_guest`/
  `install_df.remote()`, and a strong second-site candidate found
  (`sx=128 sy=84 ex=131 ey=87`), left uncommitted for the user's call.
- 2026-09-10 (end of session): that handover's full continuation (the
  candidate embarked, Artobcatten's save lost as a result, the
  perception-layer branch split, the quorum-blocked snapshot worked
  around with a file backup, and Uniboslan's first room and stockpile dug)
  moved wholesale to the same archive file — exceeded the ~400-line
  threshold, not superseded by new work. The handover at the top of this
  file is the compacted current-state summary; the embark-screen-specific
  durable traps it used to carry were dropped rather than re-copied
  forward, since they're already the permanent living content of
  `docs/DF-UI-AUTOMATION.md`, not duplicated here.
- 2026-09-11: the 2026-09-11 VM-outage/quorum-incident writeup plus the
  entire 2026-09-10 end-of-session handover (VNC control channel, labor
  management/`autolabor`, the kea-combat finding, the quicksave root-cause,
  the perception-branch audit, both autonomous-play experiments, and the
  `find_diggable_area`/reachability corrections) moved wholesale to the
  same archive file — exceeded the ~400-line threshold by a wide margin,
  not superseded by new work. The handover at the top of this file is the
  compacted current-state summary, written deliberately thorough for a
  `/clear`; the archive has the full decision-by-decision detail.
- 2026-09-11 (documentation consistency pass): three fully-self-reporting
  ### threads moved wholesale to the same archive file: the compliance
  eval harness build (done for the session), mechanical prediction grading
  (built, selftested), and the full find_diggable_area/dig_diggable_area
  saga (built, live-verified, live-tested, the quickfort `-c` top-left-vs-
  center bug found and fixed, re-confirmed working end to end). None were
  gated on a human; item 10 in "What actually got built today" above now
  carries the compacted find_diggable_area/dig summary, and
  `decisions/DECISIONS.md`'s 2026-09-11 rows carry the full trail for all
  three.
- 2026-09-12: the entire 2026-09-11 end-of-session handover (the
  branch-merge question, the "what got built" list through item 12, and
  the peer-sessions/next-steps section) moved wholesale to the same
  archive file — the branch-merge question it spent most of its length on
  is resolved (merged, above), so it's fully superseded, not just over
  the line-count threshold. The handover at the top of this file is the
  new compacted current state.
- 2026-09-12 (session end, ahead of a `/clear`): this session's own content
  (the tool manifest build, both coordinate-leak fixes through deploy and
  live-verification, and the quorum correction) moved wholesale to the same
  archive file — it reports itself fully finished, nothing left gated on a
  human except the already-deferred design-commitment-#1 wording entry,
  carried forward unchanged. The handover at the top of this file is the
  fresh compacted current state, including two corrections the archived
  version's own text no longer reflects: both coordinate leaks are now
  fixed/deployed/verified (the archived text still frames them as open in
  a couple of places), and the driving-brain choice (`openclaw`) and
  live-view-ingest shelving are both folded in as settled state rather than
  same-session news.
