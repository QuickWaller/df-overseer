# Working archive: week of 2026-09-14

Moved wholesale from `Working.md` on 2026-09-15 under the archive-cadence rule (the file was 893 lines, over the ~400 threshold, and most of this section reported itself finished). Not edited, summarised or trimmed. Items still open were carried forward into `Working.md`'s current-state section.

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
     - **Its underground search was meaningless, and that is now fixed.**
       `diggable.find` took an absolute z (the map runs 0-185, landmarks sit
       at 168-169), so the architect's z 0 to -4 silently returned `[]`.
     - **DONE and DEPLOYED 2026-09-14:**
       - `openarea.find/build`, `diggable.find/dig` and `chokepoints.find`
         take an optional `LEVEL` relative to the landmark;
       - an off-map level is a named error;
       - MCP arguments carry descriptions;
       - live-verified on VM 103 at the DFHack and MCP levels, where level -1
         finds 5 dig candidates.

       `handoffs/2026-09-14-relative-level-args.md`.
     - **DONE and DEPLOYED 2026-09-14 (`0557415`):** a script's exact
       `{"error": "<msg>"}` output now reaches MCP clients as
       `isError: true`.
       - Live-verified from VM 106: off-map level and unknown landmark give
         `isError: true`; a normal `level: -1` call is still a result.
       - Venv suite 125 to 127. The new test fails against the old
         `server.py`.
     - **DONE 2026-09-14: architect charter run #2.**
       `evals/live/2026-09-14-architect-second-charter/`. Same model,
       charter (hash-identical) and prompt; $0.0037, 1 turn, 14 calls, 3 of
       them `isError`.
       - **The interface fix worked:** it named the 5 SOIL pockets one level
         down and reasoned about the stair linking the two levels.
       - **But the proposal regressed.** There is no `<proposal>` record at
         all: no prediction, no cost, no `public_rationale`. And its one
         proposal, a door or trap at the vertical chokepoint, is
         defensibility, which `role.md` says to flag for the Overseer rather
         than propose.
       - This is one sample per run, so it can't be pinned on the interface
         change.
       - Per-call arguments were unrecoverable, because neither
         openclaw's headless `exec` nor the server logs them.
     - **DONE 2026-09-14 (`2472cdf`): `dfmcp` logs every `tools/call`** as
       one JSON line to journald: role, tool, arguments, `is_error`, error,
       session and request ids, duration.
       Read back with `journalctl -u dfmcp-server.service -o cat | grep '"event": "tools/call"'`.
     - **USER WANTS: a scrolling feed on the right of the live stream**
       showing proposals and Overseer rulings (not agent-to-agent chat; the
       user chose this 2026-09-14, see the register). Build order:
       1. **DONE 2026-09-14 (local code, not an MCP tool yet): `dfqueue/`.**
          - Record kinds `proposal`, `pass` and `ruling`, validated at write
            time with every error listed; refused records write nothing.
          - Type vocabulary keyed by role, a coordinate filter, and a
            `public_view` allowlist.
          - 61 tests; the ambient suite goes 127 to 188 (1 skipped).
          - `handoffs/2026-09-14-proposal-queue.md`.

          **Blocker, now decided (2026-09-15):** `learning/predictions/`
          only accepts end-of-fort ledger signals, so no architect proposal
          can pass today. The user chose to add **live-state signals** (each
          measured by an existing read tool and graded by calling it when due)
          that build up into a ledger, stored in **SQLite on VM 103** with
          dfmcp as the single writer. JSONL exports stay git-tracked for the
          report; the fort ledger stays JSONL.

          **DONE 2026-09-15 (local code):** `learning/live_signals.py` (6
          signals), `dfqueue/` on SQLite with a grader. Run #1's proposal now
          passes with a live signal. Checked against real VM 103 JSON (see
          the register). Ambient suite is 229 passed, 1 skipped.

          **NEXT:** wire it into dfmcp as a `propose` / `pass` / `ruling`
          tool for the roles, pass the current game tick at write time, run
          the grader on a schedule, then build the feed publisher and page.
          All of that touches VM 103, so it needs a go-ahead.

          Also, `check_after_ticks` is passed as `check_at_year` purely to run
          the type check. That row is validation-only and never persisted
          (verified: no `register` call in `dfqueue`).
       2. a publisher of §8's allowlisted fields only, with a kill switch.
          **No delay for now**, the user's call on 2026-09-14;
       3. the stream page, noVNC left and feed right. **Going public needs
          its own go-ahead.**

       Nothing produces a feed today: no queue, no Overseer, one-shot
       architect runs only.
     - Only after step 1: spend on more architect samples per run.
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


## Moved wholesale from Working.md on 2026-09-17 (doc-drift pass, archive-cadence rule: file was 505 lines, over the ~400 threshold)

Every item still open in this section was carried forward into Working.md's new HANDOVER 2026-09-17 section. Not edited, summarised or trimmed.

## HANDOVER 2026-09-16 (read this first after a /clear)

**The fort is in trouble and paused, which is the safe state.** The user
dismissed the popup and re-paused on 2026-09-16; **the orchestrator then
verified it live, read-only**: `pause_state` genuinely true, focus
`dwarfmode/Default` (no dialog up), year 30, `cur_year_tick` 213622,
`frame_counter` 79020, 15 citizens. (Food at that reading was miscounted as 0;
the corrected figure is below.)
About 140 ticks passed between the earlier reading and the pause, nothing more.
The earlier "frozen behind a popup at tick 12309480" state is resolved; the
count below stands. Verified live from inside:

- **fort-owned drink 0; fort-owned food 24 units (5 items: 10 fish, 9 plant,
  5 meat), for 15 dwarves.** Deployed `df-overseer-stocks food-drink` returns
  exactly this, matching the user's own screen reading.
  **Corrected three times on 2026-09-16.** The first count said 234 food and 50 drink and included the
  caravan's goods. The second filtered on `not flags.foreign` and said 0 and 0.
  Both are wrong: **`flags.foreign` is an origin flag, not an ownership flag**,
  true for the fort's own embark supplies too, so it erases the starting
  stores. `flags.trader` is the real fort-vs-caravan test, verified live and
  independently by two sessions (a strict subset of `foreign`: 565 foreign, 292
  trader, zero trader-but-not-foreign, cross-checked through `UNIT_HOLDER` →
  `isMerchant()`). The third error: the first stocks tool counted item
  entities, not stack units, and reported 5 where the fort has 24; the user
  caught that one from the screen too. → `docs/TRAPS.md`.
  The user spotted the original error from the screen before the orchestrator
  did.
- 15 citizens, 59 fort-owned seeds (34 plump helmet; the earlier 119 included
  foreign ones), **zero farm plots, zero stills, zero workshops of any
  kind, no trade depot**. A caravan and the outpost liaison are waiting and
  cannot unload without a depot.
- The fort produces nothing. Stores are not the problem; production is.

**The gap that matters: our agents cannot fix any of this.** The whole write
surface is dig, open-area build, landmark build and labor set. There is no tool
to build a workshop, farm plot, trade depot or typed stockpile, none to create
manager work orders, and none to trade. `proposal-0001` (accepted by the
Overseer 2026-09-16) could not be executed even with the execution tools
switched on.

**Research landed and is merged on `main`:**
`research/2026-09-16-food-and-drink-logistics.md`, dispatched because the user
asked for research first, then an agent to build the tools ("it would be good
to learn how to build the tools as we do it"). Its findings, orchestrator
spot-checked against `memory/dfhack-environment.md`:
- **Trade is buildable but not closeable.** A depot can be built (quickfort),
  and `logistics add trade` can stage goods, but no struct-level API was found
  for executing the trade itself, only the trade viewscreen, which this repo
  bars outside embark bootstrap.
- **Gathering needs activity zones, and the `zone` plugin is unavailable on
  this install** (confirmed in `memory/dfhack-environment.md`'s unavailable
  list, alongside `stocks` and `workflow`). No zone tooling exists here.
- **A farm is the sound long-term path and the slowest**: dig, build, a season,
  a harvest, then a still or kitchen linked before anything is edible.
- **The cheapest real win is manager orders**: `workorder` is available and is
  the only route to them; `orders import library/basic` brings a DFHack-authored
  food and drink standing-order set with no new Lua.
- **Biggest missing read tool:** nothing can distinguish fort-owned stores from
  foreign goods, which is exactly the mistake made today.
- **Genuinely unknown on this install:** `seedwatch`, `buildingplan`,
  `autofarm`. Check these before building against them.
- **Unresolved:** how long the caravan waits.

**The user's framing (restated 2026-09-16):** the fort is an experiment and is
expendable, "we can always delete the fort and restart". Rescuing it is worth
trying **because the tools get built along the way**, not because the fort
matters. Nothing here is an emergency; the tool layer is the point.

### START HERE, in priority order

This is the single current priority list. It supersedes the 2026-09-15 list
that used to sit lower in this file, whose item 1 ("execute `proposal-0001`")
assumed a running fort and a write surface that could carry it; neither holds.

1. ~~Merge and review the research branch~~ **DONE 2026-09-16**, on `main`
   (`eb9e83d`, `research/2026-09-16-food-and-drink-logistics.md`).
2. ~~Decide the rescue path~~ **DECIDED 2026-09-16: continue on this fort.**
   The user dismissed the popup, re-paused, and said "I think we should
   continue on this fort for now". Restarting on an embark chosen to exercise
   an opening ladder was raised by the orchestrator and is **deferred, not
   rejected** — worth revisiting once the tools exist, since a mid-game fort
   with a caravan parked outside cannot exercise an opening policy.
3. **The building tools, in the order the user agreed 2026-09-16.** The whole
   list is still workshops, farm plots, trade depot, typed stockpiles and
   manager orders, landmark-relative with no coordinate crossing the boundary
   (`workorder` is available; `orders import library/basic` is the cheapest
   real win with no new Lua). But three things come first, agreed explicitly:
   1. **The fort-owned vs foreign stocks read**, because every other tool and
      every ladder branch is downstream of a question that answers wrong
      today. **Dispatched** (see below).
   2. **Something that runs on a schedule.** Nothing does: no grader schedule,
      no Sentry, agents are one-shot `agent exec`. A ladder is inert without
      a loop that wakes, checks preconditions and acts, and the "timing" half
      of the problem (season, caravan departure, winter freeze) needs a
      clock-aware trigger. **Not yet designed** — the biggest structural gap.
   3. **The `set_labor`/`autolabor` race**, before anything writes labors.
      The ladder's first rung is fishing, which assigns a fisherdwarf labor,
      which is the losing side of that race. **Dispatched** (see below).
4. **A grader schedule**, so live predictions actually grade. Then the rest of
   the feed:
   1. a publisher of `dfqueue.render.public_view` only (allowlist and kill
      switch; **no delay, user's call 2026-09-14**);
   2. the stream page, noVNC left and a scrolling feed right. **Public, so it
      needs its own go-ahead.**

   It shows proposals and rulings, not agent-to-agent chat (user's call; §4
   kept). Note `proposal-0001` is deliberately left ungraded, see the facts
   section below.
5. **Architect quality, with several samples per configuration.** Run #3 fixed
   the dropped record, but n=1 each: its prediction (`fort.landmarks.count gt
   4` in one day) cannot attribute an outcome, it judged "nothing to dig" from
   level 0 only, and run #2's scope slip (a defensibility proposal) is untested
   since. → `evals/live/2026-09-15-architect-third-charter/README.md` review
   section. Same for the Overseer: `ruling-0001` was charter-clean but called
   an unattributable prediction sound and did not notice the fort was stopped.
6. **The `set_labor`/`autolabor` race**, a live single-writer violation that is
   small to fix.
7. **Only then** execute a proposal end to end. `proposal-0001` (accepted
   2026-09-16, `ruling-0001`, `deepseek-v4-pro`, $0.0068) could not be executed
   even with the Overseer's write tools switched on, because no tool builds
   what it asks for. Execution still needs those tools allowed and the user's
   go-ahead.

### Facts established 2026-09-15/16 that contradict older docs

- **The sim frame cap is 100, not 5** (`enabler.fps` 100, graphics 50, about
  100 ticks per wall second). Cost and latency reasoning built on `FPS_CAP:5`
  is wrong by 20x; the doc pass corrected the number and deliberately did not
  rewrite the conclusions. Still open: the 45-80s command-latency explanation
  in `agents/overseer/role.md` and `docs/AGENT-ARCHITECTURE.md` §14 item 5.
- **Saves are at the XDG path**, not the game directory: slots `autosave 1..3`,
  `current`, `region1`, `region2` under the `df` user's data dir. Already in
  TRAPS.md; rediscovered the hard way.
- **`proposal-0001`'s prediction window is blown.** 1200 ticks elapsed within a
  minute of unpausing with nobody acting, because ruling and execution are
  separate supervised steps hours apart. Grading it now records a latency miss,
  not a verdict on the proposal. Left ungraded on purpose.
- The Overseer's first ruling was charter-clean but called an unattributable
  prediction sound, and did not notice the fort was paused. One sample, cheap
  model.

### Live state as of this handover

- **VM 103:** dfmcp-server active, queue DB at `/var/lib/dfmcp`, incident
  capture installed, DF running under the frozen popup. Overseer and consultant
  tokens rotated 2026-09-15; the architect token was not.
- **VM 106:** openclaw with two agents (`architect`, `overseer`), one MCP entry
  and token each in `/opt/openclaw/secrets/openclaw_secrets.env` (mode 600,
  placed by the user, since sessions are refused writes there). Incident
  capture installed. Its old disk is deleted.
- **DeepSeek key is still plaintext** in openclaw's state DB; the env SecretRef
  is configured but shadowed by the `deepseek:manual` auth profile, and
  removing that profile was refused by the classifier. A user-run script could
  do it, like the token placement one
  (`scripts/`-worthy, currently only in a session scratchpad).
- **Classifier refusals seen repeatedly:** writes to secret stores, disk
  detach, and ad-hoc Proxmox config writes. Named `provision_vm.py` subcommands
  were fine. Route these back to the user, never through another agent.

### In flight, dispatched 2026-09-16

All Sonnet, worktree-isolated, committing on their own branches. None of them
touches `Working.md`, the register or `memory/`.

- ~~**`handoffs/2026-09-16-stocks-read-and-labor-race.md`**~~ **DONE and merged
  to `main` 2026-09-16.** `scripts/dfhack/df-overseer-stocks.lua` (new:
  `food-drink`, `seeds`) registered in `TOOLS.yaml` and granted to all three
  enabled roles; four `stocks.*` signals added to `learning/live_signals.py`'s
  closed registry, so a food or drink prediction is writable and gradeable for
  the first time; and the `set_labor`/`autolabor` race fixed by excluding the
  targeted labor from autolabor's management before writing, or **refusing with
  a reason** when it cannot tell. Ambient suite 276→**281 passed, 1 skipped**,
  re-run by the orchestrator; `dfmcp/tests` 152. Fort left paused throughout,
  nothing deployed. Its load-bearing correction is the `flags.foreign` trap
  above. **Still owed: a deploy pass** (orchestrator, needs a go-ahead) to
  place both scripts on VM 103 and exercise `autolabor LABOR disable` live
  once, which moves item 3 from verified-by-mechanism to verified-by-execution.
- ~~**`research/2026-09-16-trade-execution-api.md`**~~ **LANDED and merged to
  `main` 2026-09-16.** The previous pass's negative conclusion survives, but
  the picture underneath is much richer than "only the viewscreen", and it
  corrects a struct-level error the older docs still carry.
  **Orchestrator-verified live, not relayed:** `df.viewscreen_tradegoodsst` is
  **nil in this build** (trade moved into `df.global.game.main_interface.trade`
  with the v50 rewrite), `dfhack.items.markForTrade` exists,
  `main_interface.trade.goodflag` is present, and `caravan`, `diplomacy`,
  `force`, `logistics` and `workorder` all answer `help`. So **staging goods
  and selecting exactly which items change hands are real, code-level,
  zero-screen operations.** The *only* missing step is the final commit: no
  struct-level equivalent exists anywhere in the build, the vanilla button is
  engine-dispatched, and `A_BARTER_TRADE` is adventure-mode bartering,
  confirmed absent from `df.interface_key`. The exact input that fires the
  fortress-mode Trade button is **unknown and untested** (it needs a real depot
  and a caravan at it).
  **The policy question, for the user, not for an agent:** driving that last
  step via `gui.simulateInput`/`screen:feed()` needs no X11, no xdotool and no
  window focus, so it is *not* the `df-overseer-ui`/`xdotool` mechanism §7
  bars, though it is arguably the same category. Undecided on purpose.
  **Two concrete side-findings.** The caravan dwell question the previous pass
  left open is settled: `caravan_state.time_remaining` is in 1/120-day units
  (verified at source, `caravan.lua:68` divides by 120) and Uniboslan's caravan
  reads **3133, about 26 days left** — the orchestrator re-derived this after
  initially doubting the arithmetic, and the researcher was right. And
  **`caravan extend` is a real, available, zero-UI-automation write** with no
  cap found, so the clock on the depot is extendable if we want it.
  Original brief: settle whether an agent
  can complete a trade at all. The user did not accept the previous pass's "no
  struct-level API found" as final. Covers the whole `caravan`/`trade`/
  `logistics`/`force`/`diplomacy` surface, the struct level, and the one that
  actually matters: whether driving the trade viewscreen **from Lua**
  (`screen:feed()`, no X11) counts as the UI automation this repo bars, which
  is a policy question for the user, not the researcher. Also chases the
  unresolved "how long does the caravan wait".
- ~~**`research/2026-09-16-opening-priority-ladder.md`**~~ **LANDED and merged
  to `main` 2026-09-16.** Recommends the ladder as a versioned data file
  (`playbooks/opening-ladder.yaml` — the directory `docs/AGENT-ARCHITECTURE.md`
  §969 already reserves and that does not exist yet): rungs with closed types,
  coordinate-free preconditions, ranked branches where real judgment exists,
  and a prediction in `dfqueue`'s existing grammar. A new `ladder.next` read
  tool evaluates preconditions and returns ranked eligible rungs, the same
  "code narrows, model chooses" shape as `find_open_area`. Adjustment is never
  a silent edit: graded outcomes per rung, threshold revision queued and ruled.
  **Its own stated biggest risk, orchestrator-verified at source:** the
  ladder's most valuable predictions are unwritable today, because
  `learning/live_signals.py`'s closed registry has exactly six signal kinds and
  no `stocks.*` — which is why the stream above exists. **Of 16 branch-facts,
  5 are readable today and 11 are gaps.** Farm methods: only digging to a soil
  layer survives the no-coordinates rule; flooding rock needs hydraulics
  tooling that does not exist, and the water-dump-and-cancel trick is
  zone-gated and structurally close to the barred UI path. Fishing needs no
  workshop to catch and no zone, so a minimal fishing rung may be buildable
  today; fish stocks do deplete permanently. **Not verified:** stagnant vs
  flowing water, checked twice independently and still unestablished.
  Original brief: an
  opening priority order the Overseer can adjust, adapt and learn from, given
  stocks, map and timing (their own opening: fishing, then drinking from open
  water, then farms by flooding rock, the water-dump-and-cancel trick, or
  digging to soil). Cross-domain prior art first, then a **data** format under
  three existing constraints: no coordinates, the model does not edit its own
  memory, and doctrine has a measured size budget. Its most useful output will
  be the **required-reads list** — every fact the ladder must branch on, marked
  readable-today or not, which is the requirements list for the tool stream.

### Farm and water, state 2026-09-17 (evening)

**Terrain and crops (verified):** z169 surface over one SOIL level at z168 over
stone; all six fort seed types are subterranean crops, so the farm is a room
dug into z168. Dwarves need both food and drink (no `NO_EAT`/`NO_DRINK` flag).

- **DRINK IS SOLVED, for now.** Each pond is a basin of 6-7/7 water in ramps at
  z168 with open air above at z169 and undug soil around it: nowhere to stand at
  the water's level, which is why nobody drank unaided. On the user's call, one
  `WaterSource` zone was placed **on the water at z168** (quickfort `#zone` `w`,
  27 tiles, stagnant). One supervised 10 FPS unpause later (tick 217948 to
  222477, re-paused clean, 15 citizens): founders 193/195/197 went **down to
  z168** and are at 2349/2744/635 thirst, 197 with no giver at all (first
  self-serve drinking recorded here); 194/196/198 drank at the very end of the
  window. Register 2026-09-17. **Zone left in place. Not isolated** (no zoneless
  control run), but decisive enough to act on.
- **Two open risks from that fix:** dwarves stand in 6-7/7 water (drowning), and
  the water is stagnant (`NastyWater` thoughts; health effect unverified). A
  well removes both; it is no longer urgent.
- **Farm and still tools: DEPLOYED 2026-09-17** and verified (hashes, per-role
  tool lists 13/18/4 to 15/23/4, dry runs of farm/still/kitchen builds, fort
  untouched). Five older scripts were found stale by one trailing newline and
  corrected. **Not yet run for real:** `farm.build`, `farm.set-crop`,
  `workshop.build`, each needing the user's go-ahead.
- **Seed economics researched** (`research/2026-09-17-seed-ratios.md`, figures
  table ready for a database): brewing gives 5 drinks + exactly 1 seed per
  unrotten plant and needs an empty barrel or pot; cooking gives none; caps are
  200 per crop and 3000 total; seeds do not rot. Break-even: at least 1/Y of a
  harvest must be brewed, Y = plants per tile, so an unskilled unfertilized
  farm (Y about 1) can cook nothing. Doctrine lives in `doctrine/seed.yaml`.
- **Doctrine file started** (`doctrine/seed.yaml`), the tier from
  `docs/MEMORY-ARCHITECTURE.md`: game knowledge no longer goes in the register.
  Nothing reads it yet.
- **Well, verified requirements** (for when it is wanted): buildable on an
  `EMPTY` or `RAMP_TOP` tile that borders floor, so a pond-edge well needs no
  bridge; needs BLOCKS, BUCKET, CHAIN, TRAPPARTS. Fort has 3 buckets, 3 chains,
  3 logs, about 1,593 visible trees, **0 boulders, 0 blocks, 0 mechanisms**, so
  stone must be dug before a well or a mechanism exists.
- **Next concrete step:** land the water and industry tools stream (zones, tree
  felling, mason/mechanic/carpenter, work orders, well), then with the user:
  dig the z168 farm room, build farm plot and still, plant plump helmets.

### Agents know only what a player could know (decided 2026-09-16)

User's call: agent tools limited to `player_visible` and `player_derivable`.
Existence may be known from the embark screen; **location only once
uncovered**. Binds the role allowlists, not developer diagnostics. Full
reasoning in the register.

- ~~**In flight:** research~~ **LANDED and merged 2026-09-16.** Visibility is
  gated by `designation.hidden` (terrain), `dfhack.units.isHidden` (units; 29 of
  75 active units, all 5 demons, orchestrator-verified live), and feature
  `Announced` flags plus discovery announcements (caverns, veins). Hardest grey
  zone: `threat.lua` exists to catch ambushers, exactly what a player cannot see.
- ~~**In flight:** knowledge-scope audit~~ **DONE, merged and DEPLOYED to VM
  103 2026-09-16.** No agent tool is `omniscient`; `dfmcp` refuses to load if
  one is granted. Verified live: role tool lists 16/11/2 before, 18/13/4 after
  (exactly as computed from merged code), `unit-status hostile` demons 5 → 0,
  stocks 24 food / 0 drink. Backup at `/opt/df/deploy-backup-2026-09-16`.
- ~~Owed before unpausing: restart DF~~ **DONE 2026-09-16 10:43-10:44 UTC.**
  Save verified on disk first (`autosave 2`, 10:42:50), backed up, DF
  restarted, reloaded via "Continue active game", identity matched exactly
  (tick 213622, 15 citizens, the day's FISH labor still set), still paused.
  The `diff.since` visibility gate is live. Backups of both saves at
  `/opt/df/deploy-backup-2026-09-16/`.
- Original research brief: `research/2026-09-16-player-visibility.md` (Sonnet
  `researcher`, read-only, worktree-isolated): what a vanilla v50 player can
  see, when it becomes visible, which struct fields gate it, the exact
  embark-screen list, game-AI prior art (BWAPI's `CompleteMapInformation`),
  and a **preliminary** `knowledge_scope` tag for every tool in `TOOLS.yaml`.
- **Next, once it lands:** an executor audit that tags every tool, adds a
  discovery check to `find_diggable_area`, gates hidden-unit reporting in
  `df-overseer-threat.lua`, and **measures** what each change costs.
- **Accepted cost, now real:** the threat scan no longer reports ambushers or
  sneaking units at all. The player-equivalent signal is the ambush
  announcement family already tagged in `diff.since`'s REPORT branch.

### Open, waiting on the user

- **DeepSeek key in plaintext on VM 106** in
  `/opt/openclaw/config/state/openclaw.sqlite`. openclaw 2026.9.4 has no
  headless way to store it as a reference; `openclaw secrets configure` over
  `ssh -t` might. `sudo rm -rf /opt/openclaw` removes both secrets.
- **PVE token rotation**, deferred by the user. It needs a privileged
  identity, and deleting a token drops its ACLs.
- **Tailscale**, deferred. Until then the LAN bind means tokens are the only
  guard.
- **Two deferred live checks:** whether the frame cap survives a save load,
  and whether an overlay renders in the headless pipeline.

### Owed elsewhere

- **`home-lab` `inventory/services.yaml`: the `dfmcp-server.service` entry is
  written, not committed.** home-lab-fe added it 2026-09-15, marked
  `inferred`, and validated it. It is left in that checkout for the user to
  review and commit. VM 106 owes an entry only once openclaw runs as a service
  (nothing listens today).

### Background, not urgent

- **Project SSH never verifies host identity.** `scripts/provision_vm.py` and
  `scripts/install_df.py` use `StrictHostKeyChecking=no` with throwaway
  known_hosts files. VM 103's host keys were regenerated 2026-09-11 when
  cloud-init saw a new instance id during the outage recovery, which is what
  made a stale entry look like a changed host in Phase B. Worth pinning the
  estate's real keys.
- **Deploy with `git -c core.autocrlf=false archive`.** Phase B's deploy is
  CRLF on VM 103 (content correct), so naive sha256 checks against `main`
  fail. Also from Phase B: `dfmcp.auth` reads only `REPO_ROOT/.env`, so a
  throwaway instance needs its own code copy; openclaw's schema now rejects
  `pinned-config.json`'s `_note` key.

- **The breach detector is inconclusive.** Settle it opportunistically (rain,
  or an animal fording water), never by flooding the fort.
- **The `../openclaw` scaffold** reads `OPENCLAW_CONFIG_DIR` and
  `OPENCLAW_AUTH_PROFILE_SECRET_DIR`, which the image ignores; use
  `OPENCLAW_STATE_DIR` before running it durably.

## Moved wholesale from Working.md on 2026-09-17 (fishing paragraphs from HANDOVER 2026-09-17, finished; superseded by the same-day audit)

Not edited. Both paragraphs' conclusions were later reversed: see `doctrine/seed.yaml` `do-not-overfish` and `uniboslan-pool-fish-unknown`.

**Fishing gotchas and community priors: done, 2026-09-17** (light pass, Steam
Community discussions searched rather than deep-fetched, per the user's
"don't go crazy on token usage"). Folded into `doctrine/seed.yaml`:
`do-not-overfish` updated with the two-state exhaustion mechanic (seasonal
reset vs true permanent) and community corroboration that ponds are the
risky, fast-depleting case while rivers are more sustainable; two new
entries, `fishery-needs-two-labors` (Fish Cleaning, not just Fishing, is
needed to turn a catch into food) and `fisherdwarf-stockpile-distance`
(keep the fish stockpile near the water worked, not just near the fort).
**Correction folded in same day:** the wiki's own `Fishing_industry` page
states non-flowing water fish stocks "are now renewable, unlike in the past
(Bug:2780)," and that bug's history shows the general fish fix landed by
the DF2014 version line, a decade before this project's 0.53.16 — so the
"ponds are fragile, one-shot" framing above may itself be player folklore
that outlived the patch. `do-not-overfish` rewritten to carry this conflict
explicitly at low confidence rather than presenting either side as settled.

**Uniboslan's own "may have already fished out its pond" question: resolved,
live-verified.** A read-only DFHack `region-pops` check (fort confirmed
paused before and after) found every surface fish population at this
fort's world region sitting at `quantity == quantity_max` across all eight
species present (FISH_GAR_LONGNOSE, FISH_STURGEON, FISH_CHAR, FISH_PERCH,
FISH_LAMPREY_BROOK, FISH_SALMON, FISH_SHAD, FISH_MOLLY_SAILFIN; 550 to
10,802 individuals each), every one `discovered=false` — meaning not one
fish has ever actually been removed from any of them. This fort's fishing
was never depleted; the one "nothing to catch" message was a miss, not
evidence of exhaustion. Separately confirmed the fort's 10 units of
fort-owned `FISH` (flagged `foreign=true`) are the vanilla default "Play
Now!" embark ration (wiki: 15 units, 3 stacks of 5, one barrel) minus one
eaten stack — not evidence of a past catch. → `doctrine/seed.yaml`
`uniboslan-fishing-untouched`, `decisions/DECISIONS.md` 2026-09-17.

## Current state, 2026-09-15: the agent loop is reaching the fort, and the channel exists

The 2026-09-12 to 09-14 section (the agent architecture design phase, the
MCP server build, its first contact with reality, openclaw's install and the
first agent calls) moved wholesale to
[`working-archive/Working_archive-2026-09-14.md`](working-archive/Working_archive-2026-09-14.md).
Everything below is what is still open.

**Where things stand.**
- **The server:** `dfmcp-server.service` runs on VM 103, LAN-bound, with
  bearer tokens as the only guard until Tailscale. It is live-verified with
  relative `level` args, `isError` for script errors, and a JSON tool-call
  log in journald.
- **The agent host:** openclaw on VM 106 has run the architect three times as
  a one-shot `agent exec` on DeepSeek. VM 106 went dark after run #3 and was
  rebuilt in place 2026-09-15. openclaw is reinstalled and now hosts two agents,
  architect and overseer, with both MCP tokens in place (2026-09-16).
- **Incident capture** (guest agent, persistent journal, per-minute netwatch
  dump on gateway loss) is live on VMs 103 and 106 since 2026-09-15. A new
  clone needs `provision_vm.py setup-capture --vmid N` run by hand. **Why
  VM 106 went dark on 2026-09-14 is still not established**; the capture is
  there to record it if it recurs (`docs/RUNBOOK-DARK-GUEST.md`).
- **The queue is live** (2026-09-15): `queue.propose`/`pass` (architect) and
  `queue.rule`/`pending` (Overseer) on VM 103, DB under `/var/lib/dfmcp`.
  It holds one real record, `proposal-0001` from architect run #3, with a
  pending prediction (`due_game_tick` 12276077), accepted by the Overseer
  2026-09-16. No grader runs on a schedule; its window is blown regardless
  (see the facts section below) and it is left ungraded on purpose. The fort
  has since been unpaused several times for supervised tests (2026-09-17,
  see the HANDOVER below) and is paused again now.
  → register 2026-09-15 rows,
  `handoffs/2026-09-15-queue-live-deploy.md`.
- **Saves:** under the `df` user's XDG data dir on VM 103 (`Bay 12 Games/
  Dwarf Fortress/save`), **not** the game directory: slots `autosave 1..3`,
  `current`, `region1`, `region2`. Two quicksaves wrote `autosave 2` and
  `autosave 3` on 2026-09-15; `quicksave` rotates slots and needs a render
  pass, so it can silently do nothing (memory/fort-operations-and-incidents).
- **Tests:** ambient `python -m pytest` gives 306 passed, 1 skipped;
  `.venv-dfmcp` gives 165 for `dfmcp/tests` (register 2026-09-17 figures).

## In flight: production model designed, audited, and four streams dispatched (2026-09-18)

**Design is settled on paper and nothing is built.** Six register rows dated
2026-09-18 carry the decisions; the diagrams are in an artifact (URL in the
session, not committed). Read `research/2026-09-18-production-graph.md` for
the formalism and `research/2026-09-18-production-figures.md` for the figures
before touching any of it.

**The short version:** a directed hypergraph in plain SQLite, **seven** tables
(`production_node`, `_class`, `material_reaction_product`, `_process`,
`_flow`, `_attribute`, `_observation`). A node is an item type crossed with a
material; processes consume classes and produce specifics, so routes are
generated rather than authored, and the join table plus a two-pass extraction
exist because 42% of product lines inherit their material at job time.
**Four** consumption semantics (consumed, occupied for the job, occupied until
released, modified in place), because a barrel is freed by drinking rather
than by brewing, and the glaze reactions have no product row at all. The
static graph is placeless: move, install and trade are all generated at query
time. Material policy is banded and lives in **doctrine**, not in the graph,
which is what removes the need for a solver cost vector.

**The rule that governs all of it:** four quadrants, and quadrant 4
(happiness effects, interruption behaviour, time lost to needs) never enters a
formula, only appears as an unattributed residual. Demand is exact, supply
capacity is not, so every question is posed from the demand side.

**Both feasibility audits are in** (`research/2026-09-18-schema-extraction-
static.md`, `-live.md`) and the spec is corrected from them. Headlines: node
identity needed a material join table and a two-pass extraction because 42% of
product lines inherit their material; `consumption` needed a fourth value;
the observation key had to become an absolute tick because
`ReadCurrentTick()` resets annually. Nine of twelve live facts are exactly
readable, job claims are a plain flag, and cancellation announcements turned
out to be a lossy hint rather than a shortcut.

**Four build streams dispatched 2026-09-18**, no two sharing a file:
- **Doctrine** — **DONE and merged.** Six `prior` entries, new `material`
  topic, 307 passed / 1 skipped.
- **Lever-gap tools** — `orders.create` learns a `bucket` job and friends;
  new `stockpile list`/`links`. Deploys to VM 103, dry runs only.
- **`production/` package** — seven tables, two-pass extraction, offline.
- **Doc drift pass** — seven new traps from the audits, plus `ROADMAP.md`,
  `AGENT-ARCHITECTURE.md`, `MEMORY-ARCHITECTURE.md`, `CLAUDE.md` status.


**Archived 2026-09-19.** Every stream this section dispatched finished: doctrine, lever-gap tools, the `production/` package and the doc drift pass, plus the blocker walk and the days-of-cover calculator. The design it summarises lives in `docs/PRODUCTION-MODEL.md`; the decisions are in `decisions/DECISIONS.md` dated 2026-09-18.


## HANDOVER 2026-09-17 (read this first after a /clear)

**The 2026-09-16 handover (the production-gap discovery, the stocks/labor-race
fix, the knowledge-scope audit, and the start of the farm-and-water work)
moved wholesale to
[`working-archive/Working_archive-2026-09-14.md`](working-archive/Working_archive-2026-09-14.md).**
Everything below is today's outcome and what's still open.

**Uniboslan drinks and grows food for the first time.** **Stale as of
2026-09-19: it does not drink, and the fort is at tick 235668, not 227008.
Read the section "The fort cannot drink, and the pond cannot be dug to"
earlier in this file first.** Paused, tick
**227008**, year 30, 15 citizens, no deaths, `dwarfmode/Default` focus (no
dialog up), the last state every stream today independently re-verified
live before touching anything. Nothing is running right now.

- **SUPERSEDED 2026-09-19, and the contradiction is unresolved. Read this
  before the bullet below it.** Measurement on 2026-09-19 found delta thirst
  equalled delta tick exactly across all 15 citizens over 6,303 ticks, so
  **nobody drank at all** in that window. See the section "The fort cannot
  drink, and the pond cannot be dug to" earlier in this file. **But the two
  findings cannot both be right as stated**, and an audit
  (`research/2026-09-19-unverified-claims-audit.md`, finding 5) flagged it:
  the bullet below reports three founders demonstrably drinking at z168 and
  three more catching a `NastyWater` thought, which the 2026-09-19 "zero
  walkable neighbours" reading would make impossible. **Leading hypothesis,
  not yet confirmed: the 2026-09-19 reading derived walkability from tile
  *shape*, and the pond is a bowl of submerged RAMP tiles that dwarves may
  well traverse.** The right primitive is probably
  `dfhack.maps.getWalkableGroup`, which `df-overseer-connectivity.lua`
  already uses. **Until this is settled, treat the well plan as resting on a
  measurement that may be wrong.** What survives regardless: nobody drank
  over that window.
- **Drink is solved, in practice.** Every pond is a sunken basin of 6-7/7
  water at z168 with nowhere dry to stand at the water's own level, which is
  why nobody drank unaided (`research/2026-09-17-founders-not-drinking.md`).
  A `WaterSource` zone placed **on the water itself** at z168 (Activity Zone
  #1, still in place) fixed it: one supervised 10 FPS unpause got three
  founders down to z168 and self-serving water (thirst near zero; 197 with no
  caretaker at all, the project's first confirmed self-serve drink), and three
  more picked up a fresh `NastyWater` thought right at the end of the same
  window. **Not proven as the sole cause** (no zoneless control ran), but
  decisive enough that the zone stays. Two open risks: dwarves stand in 6-7/7
  water (deep enough to drown a poor swimmer), and the water is stagnant
  (health effect of the `NastyWater` thought unverified). A well removes both
  and is no longer urgent. → `decisions/DECISIONS.md` 2026-09-17 rows,
  `handoffs/2026-09-17-water-source-zone-test.md`.
  **Correction folded in:** an earlier same-day research pass
  (`research/2026-09-17-pool-reachability.md`) concluded `getWalkableGroup`
  was broken around ramps; its own top-of-file correction note (verified live
  before that doc was committed) found this was wrong: the ramps really are
  underwater, not miscategorised. Read the correction note, not the body, if
  citing that doc.
- **First real food production: the farm plot is built and its crop set.** A 5x5
  `building_farmplotst` at z168 (x100-104, y101-105), `flags.exists=true`,
  all four seasons carry plump helmet (`plant_id=173`), orchestrator-verified
  by direct struct read. **The still is not built.** It is designated at the
  surface (z169, x96-98, y97-99; no free 3x3 floor exists underground once
  the farm plot took the only one). **Material is genuinely thin, not
  clearly ruled out as the blocker**: the build stream's own live read
  claimed 15 wood / 3 boulders / 4 blocks free, but the register's own
  correction (checking `flags.trader`) found the 3 boulders, 4 blocks and 12
  of that wood belong to the caravan, not the fort. Uniboslan actually owns
  **3 logs and nothing else** buildable, which the still's one-generic-item
  requirement can still be met from, but there is no real cushion. Its
  `ConstructBuilding` job (id 366) never got a worker across a full 453s
  unpause (30 samples, every idle citizen instead cycled through
  Drink/Eat/Sleep). `decisions/DECISIONS.md` frames this as the job "reading
  suspended"; the execution stream's own live read only confirms
  "unassigned, never picked up," not a suspend flag specifically; worth
  checking directly before assuming which it is.
  → `research/2026-09-17-farm-still-first-build.md` (handoff Result),
  `decisions/DECISIONS.md` 2026-09-17.
- **Water and industry tools shipped: zones, tree felling, work orders, a
  well builder, and three more workshop kinds.** New: `zone.find/place`,
  `trees.find/fell`, `well.find/build`, `orders.list/create/cancel`;
  `workshop.find/build` extended with mason/mechanic/carpenter plus a
  `building_material` field (verified live: all five workshop kinds accept
  boulder, wood or block interchangeably). Deployed and live-verified
  (hashes, restart, dry runs, and direct proof the new code is running, not a
  stale `reqscript` cache). **Role tool lists: architect 19, overseer 32,
  consultant 4** (up from 13/18/4 this morning). No citizen holds the
  Manager position, so `orders.create`'s effect on a queued order with no
  manager appointed is reported but not enforced, untested against a real
  unpause.
  → `handoffs/2026-09-17-water-and-industry-tools.md`,
  `handoffs/2026-09-17-water-industry-tools-deploy.md`.
- **Seed economics researched; game knowledge now lives in `doctrine/`, not
  here.** Brewing, quarry-bush-bagging and pig-tail papermaking are
  raw-confirmed 100%-guaranteed 1-seed-per-plant returns; cooking returns
  zero, confirmed two ways. Break-even: at least `1/Y` of a harvest (Y =
  plants per tile) must go through a guaranteed-return method, so an
  unskilled, unfertilized farm can cook nothing yet. Figures table ready for
  the game-figures database `ROADMAP.md` now tracks as a Next item.
  `doctrine/seed.yaml` and `docs/TRAPS.md` were both already updated today by
  the streams that found the facts; nothing in this pass contradicted either,
  so neither was touched further.
  → `research/2026-09-17-seed-ratios.md`, `doctrine/seed.yaml`.
- **Stocks tonight** (live-read during the farm-still build, the most recent
  figures anyone has): fort-owned food (raw_edibles) **17 units** (item_count
  4, down from 20 this morning, ordinary consumption from Eat jobs during the
  unpause, nothing deliberate); drink still **0**; prepared_meals **0**;
  seeds **60 total, 35 plump helmet** (the register's own count, one higher
  than the 59/34 an earlier reading gave, not chased).

### START HERE, in priority order

**Authority note, 2026-09-18:** the user granted this session full authority
to push, to change the VM and to act on the fort, explicitly asking not to be
asked per action. Standing exception kept: genuinely unrecoverable loss (the
fort save, the VM itself) still stops and reports. Everything below that was
previously "needs the user's go-ahead" is now simply sequenced work.

**Sequencing rule while streams are live:** only one stream touches VM 103 or
the fort at a time. Two `production/` streams may run together **only** when
their file ownership is strictly disjoint and each handoff names the other's
files as forbidden; the blocker-walk and days-of-cover pair had to be
serialised because both simply claimed `production/**`.

**Five streams are live as of 2026-09-19.** One owns the VM and the fort (the
well); two are offline under `production/` with strictly non-overlapping
files; one owns `doctrine/` and `docs/`; one is read-only and writes a single
research file. Before dispatching another, check it collides with none of
those five surfaces.

**The worktree trap, learned the hard way today:** a worktree agent is cut
from a **commit**, so a handoff written and dispatched in the same breath is
**not in its checkout**. Two streams were dispatched blind before this was
spotted and had to be told to run `git checkout main -- <their handoff>`.
**Commit the handoff before dispatching.**

0. **The well, and with it the fort's water.** Running:
   `handoffs/2026-09-19-well-unblock.md`. Gated on settling from this
   install's own raws whether a mechanism can be made from wood, because that
   one fact chooses between the 3-log route and the stone route. **Done means
   thirst falling across two reads**, not a well existing. This stream owns
   VM 103 until it reports.
0b. **Correct the water doctrine** (running,
   `handoffs/2026-09-19-water-doctrine-correction.md`) and **audit the repo
   for claims presented as measured** (running, read-only,
   `handoffs/2026-09-19-unverified-claims-audit.md`). The first records what
   the pond actually taught us; the second exists because four instances of
   one error class in two weeks is a pattern.
1. **Fill the graph and connect it.** Running, both offline, both
   worktree-isolated:
   `handoffs/2026-09-19-real-corpus-extraction.md` (the extractor has never
   seen real data; 159 real reactions now staged out of tree) and
   `handoffs/2026-09-19-snapshot-assembler.md` (nobody ever wrote the caller,
   so the graph has never been pointed at this fort). The second one's proof
   test is the well chain itself.
2. **Then the supervised run**, written and waiting:
   `handoffs/2026-09-18-supervised-run-and-measure.md`. **Now blocked behind
   the well stream**, because only one stream touches the fort at a time. It
   settles four known unknowns including the `growdur` unit that blocks the
   harvest clock, and the still's job 366 goes with it: the suspension
   question is answered, it is genuinely DF's `susp` flag, verified live.
3. **The stair may be resolved by the well stream, or not.** If the wooden-
   mechanism answer is no, the stone route *is* the stair: remove the orphan
   z167 UpStair designation, designate the merged rank-1 spot, dig it. If the
   answer is yes, the stair stays outstanding as its own item. Read the well
   stream's write-up before picking this up.
4. **`ban-cooking all`: DONE 2026-09-18.** Kitchen exclusions went 110 to
   1279 (1169 types banned). First enforcement `seed-stock-never-falls` has
   ever had. For the record: 110 exclusions already existed and nobody had
   recorded why.
5. **Done since this list was last written**, so do not go looking for them:
   the lever-gap tools (deployed, role lists **23/36/4** verified live per
   role over a real MCP client), the `production/` package, the doctrine
   material-policy entries, the doc drift pass, the blocker walk and the
   days-of-cover calculator. Suite is 364 passed / 1 skipped.

**Background on the stair, for whoever picks item 3 up.** Farm and stair
tools were deployed and live-tested 2026-09-17, tool lists live at 21/34/4,
and `farm.set-crop`'s real write and restore on plot 4 worked, read back
through `farm.list`. **The stair did not.** `dig-stair` returned ok for both
halves, but its rank-1 spot sat under the fort's Stockpile and quickfort
silently skips occupied tiles, so z167 holds an orphan UpStair with no
DownStair above it (verified live, tick 227160, paused). The fix, merged
2026-09-17 and not yet deployed, ranks out candidates with a building on
either tile (verified live: the Stockpile tile no longer ranks first), judges
success by reading the designation back, designates the upper half first and
undoes it if the lower fails, and turns failures into real errors rather than
an ok. → `handoffs/2026-09-17-dig-stair-fix.md` Result.

**Fishing research: done 2026-09-17, and its first conclusions reversed.**
A same-day audit found that the "overfishing may not be a real risk" swing
rested on a wiki line its own cited bug contradicts, and that the
"live-verified untouched" population read most likely read the clipping
river's fish, not the pools'. Current position: flowing water restocks,
still water may not (moderate confidence); whether this fort's pools hold
fish at all is open. The original two paragraphs moved wholesale to
`working-archive/Working_archive-2026-09-14.md`. → `doctrine/seed.yaml`
`do-not-overfish` and `uniboslan-pool-fish-unknown`, `decisions/DECISIONS.md`
2026-09-17.

**Open idea, not started:** the user proposed background ground-truth
audits (like the `region-pops` check above) running at fort start and
periodically, compared against agent beliefs/predictions after the fact,
but never exposed to the agents themselves except via player-derivable
signals — the same shape `dfqueue`'s grader already has for predictions.
Blocked on the same "no scheduler exists" gap already on record
(2026-09-16). Not yet placed in `ROADMAP.md`; ask before starting.

### Founders-not-drinking: answered in practice, not in full

The zone fix (above) resolved the symptom. The deeper "why job-assignment
routed founders as `GiveWater` workers and migrants as patients, when
founders were thirstier" question in
`research/2026-09-17-founders-not-drinking.md` is still open (three ranked
hypotheses, none confirmed) but no longer blocks anything: self-serve
drinking now works. Not worth chasing further unless it recurs.

### Not yet done, carried from the 2026-09-15/16 ladder (lower priority than
the list above)

- **A grader schedule.** Nothing runs on one; no Sentry. `proposal-0001`
  remains ungraded on purpose (its window blew before this was ever fixable).
- **The public feed/stream page and `dfqueue.render.public_view` publisher.**
  Not built; needs its own go-ahead once built (public-facing).
- **Architect and Overseer quality**, still n=1 each. `ruling-0001` was
  charter-clean but judged an unattributable prediction sound.
- **Execute a proposal end to end.** Still blocked on no tool building what
  any proposal so far has asked for.

### Open, waiting on the user

- **DeepSeek key in plaintext on VM 106** in
  `/opt/openclaw/config/state/openclaw.sqlite`. openclaw 2026.9.4 has no
  headless way to store it as a reference; `openclaw secrets configure` over
  `ssh -t` might. `sudo rm -rf /opt/openclaw` removes both secrets.
- **PVE token rotation**, deferred by the user. It needs a privileged
  identity, and deleting a token drops its ACLs.
- **Tailscale**, deferred. Until then the LAN bind means tokens are the only
  guard.
- **Two deferred live checks:** whether the frame cap survives a save load,
  and whether an overlay renders in the headless pipeline.

### Owed elsewhere

- **`home-lab` `inventory/services.yaml`: the `dfmcp-server.service` entry is
  written, not committed.** home-lab-fe added it 2026-09-15, marked
  `inferred`, and validated it. It is left in that checkout for the user to
  review and commit. VM 106 owes an entry only once openclaw runs as a service
  (nothing listens today).

### Background, not urgent

- **Project SSH never verifies host identity.** `scripts/provision_vm.py` and
  `scripts/install_df.py` use `StrictHostKeyChecking=no` with throwaway
  known_hosts files. Worth pinning the estate's real keys eventually.
- **The breach detector is inconclusive.** Settle it opportunistically (rain,
  or an animal fording water), never by flooding the fort.
- **The `../openclaw` scaffold** reads `OPENCLAW_CONFIG_DIR` and
  `OPENCLAW_AUTH_PROFILE_SECRET_DIR`, which the image ignores; use
  `OPENCLAW_STATE_DIR` before running it durably.


**Archived 2026-09-19.** Superseded by `Working.md` HANDOVER 2026-09-19. Its fort figures (tick 227008, "drink is solved") were disproven by measurement; its tool counts and stream list were overtaken. Kept whole because the fishing reversal, the stair background and the ground-truth idea live only here.


**Archived 2026-09-21 from `Working.md`, verbatim below (the file reached 586 lines).** Superseded by HANDOVER 2026-09-21. Fort figures are historical.

## Live fort state, read-only, 2026-09-18 at tick 227160 (paused)

Read directly this session. **This corrects two claims I made earlier today.**

- **The fort owns three usable buckets** (ids 81, 149, 150: empty,
  unforbidden, unclaimed, no holder). Two more are `trader=true`, held by the
  caravan's yak pack animals. There is no bucket shortage.
- **Nobody is injured.** The "1 of 15 unconscious" from the live audit is a
  **sleeping miner**: `pain=0`, `wounds=0`, `current_job=Sleep`.
- **Fort-owned stock**: logs 3, seeds 60, **drink 0, prepared meals 0**, raw
  plants 8, boulders 0. Food is 8 raw plants for 15 citizens.
- **Thirst** is staggered across three bands, worst 23,391 against a roughly
  three-week (~25,200 tick) drink interval, consistent with the `WaterSource`
  zone working. Not in danger.
- **Farm plot 4 exists**, plump helmet set for all four seasons, and **25
  `PlantSeeds` jobs are queued**, 2 claimed. Claim state is uninformative:
  the fort has run 151 ticks since they appeared.
- **The still (workshop 5) is still `exists=false`** with its
  `ConstructBuilding` job 366 **suspended**, and the fort owns 3 logs.
- `autolabor` is **enabled**, so labour counts are its live allocation, not a
  configuration: PLANT 2, BREWER 1, COOK 1, CARPENTER 1, DIAGNOSE 18 on 1,
  SURGERY 19 on 1, RECOVER_WOUNDED 24 on 1, and **`FEED_WATER_CIVILIANS` 23
  on all 15**. Hand-setting a labour takes it off autolabor fort-wide and
  permanently, so that lever is contested. → `docs/PRODUCTION-MODEL.md` §13.
- **Corrected the same day:** an earlier entry here said
  `FEED_WATER_WOUNDED` was enabled on 0. That token does not exist, and the
  probe could not tell a missing field from a real zero. There is **no labour
  gap in the water chain**. `BIND_WOUND` and `DRESS_WOUNDS` are not real
  tokens either.
- **`growdur` for plump helmet is 300** and live `grow_counter` values are in
  the tens of thousands, so they are not the same unit and **the harvest clock
  is not computable until the unit is settled**. One observation of a planted
  crop settles it.

**Parked by the user, deliberately:** trade (a transient hyperedge inserted
when a caravan is present, so it needs nothing now); rooms and
room-dependent furniture requirements; per-stockpile sites (coarse areas
first); the solver itself, pending a sensitivity check that may show we never
needed it; the mixed-integer question (build a rail line or not), which is
the only thing the missing haul-tier figures block.

**The uncomfortable gap:** nothing in this design executes anything. Work
orders carry standing conditions, so the keep-on-hand band is expressible in
DF's own mechanism today, but the rest has no hands. `proposal-0001` was
accepted and never executed; better diagnosis on an unexecuted loop widens
that gap rather than closing it.

**Next concrete step:** read both research reports when they land, fix the
schema on paper where they say it cannot be populated, then decide whether
extraction is worth building before execution exists.


### The fort cannot drink, and the pond cannot be dug to (2026-09-18, tick 235668, paused)

**Supersedes the thirst line above.** Measured exactly across two reads: tick
227160 thirst 23,391; tick 233463 thirst 29,694. **Delta tick 6,303 = delta
thirst 6,303 across all 15 citizens**, so `thirst_timer` increments exactly 1
per tick and **nobody drank at all**. Top thirst is now 31,899. The earlier
"not in danger" reading was wrong: the `WaterSource` zone is active but
unreachable.

**Why.** The pond is a sunken bowl. Decoded tile shapes: z168 is 142 WALL, 26
RAMP, 1 FLOOR, **0 walkable**, with 27 water tiles all at least 3 deep and
**zero water tiles having any walkable neighbour**. z169 above is 134 walkable,
100 FLOOR, 26 RAMP_TOP, 0 wet.

**Digging does not fix it, proven not assumed.** A ramp was first designated at
z168; the user corrected the level, and investigation showed z168 has **0
walkable tiles near the pond**, so no miner could stand there to dig it. It was
cleared and a Channel designated at z169 on a floor tile with 3 walkable
neighbours. One supervised unpause with a remote watchdog: designation dug,
z168 wet went **27 to 28**, z168 walkable stayed **0**. The new tile simply
flooded. The user reached the same conclusion independently: **go for a well.**

**The well's blocker, from `df-overseer-well find 1 "Activity Zone #1" 20`:**
a viable site one tile from the zone, water depth 6, not salt, **stagnant
true** (a well on it gives unhappy thoughts; survivable). Requirements against
fort-owned stock: **BUCKET 3 and CHAIN 3 present, BLOCKS 0 and TRAPPARTS 0
absent.** The fort owns 3 logs and 0 boulders, and stone is at z167 behind the
half-designated stair.

That is a three-deep chain and exactly the shape `production/blocker.py` was
built to report: drink -> WELL -> BLOCKS + TRAPPARTS -> stone -> stair to z167
-> not dug.

**Dispatched, not resolved:** `handoffs/2026-09-18-well-unblock.md`. Its first
task is to settle from this install's own raws whether a mechanism can be made
from wood, because that single fact chooses between the wood route (3 logs) and
the stone route (finish the stair, mine, build mason's and mechanic's). Done
means thirst falling across two reads, not a well existing.

**Also open, unresolved:** the `PlantSeeds` queue drained 25 to 13 with no
seed-stock change and no plants appearing. The user reports the farm is
genuinely half-sown and still being sown, so this is a **measurement
discrepancy in our read**, not a stalled fort. The still's job 366 was

## HANDOVER 2026-09-19 (read this first after a /clear)

The 2026-09-17 handover is archived in
`working-archive/Working_archive-2026-09-14.md`. Its fort figures were
disproven and its stream list overtaken, but the fishing reversal, the stair
background and the ground-truth idea live only there.

**Authority.** The user granted this session full authority to push, to change
the VM and to act on the fort, explicitly asking not to be asked per action,
and restated it on 2026-09-19 ("this is all dev experiments not production").
Standing exception kept: genuinely unrecoverable loss (the fort save, the VM
itself) still stops and reports.

### The fort, and the one thing that is actually wrong

**ROLLED BACK 2026-09-19. Paused at tick 213622, not 235668.** An unbounded
live DFHack query wedged the command pipe and recovery needed `kill -9`, which
discarded roughly **22,000 ticks** back to a three-day-old quicksave. **Lost:
the 2026-09-17 `WaterSource` zone, the first farm plot, and a stair
designation.** Two standing rules came out of it and are now in
`docs/TRAPS.md`: never run an unbounded query against a live DFHack process,
and **quicksave immediately before any live fort action**, because the cost of
an incident is set by the age of the last save.

**Uniboslan does not drink.** Paused at tick **213622**, year 30, 15 citizens,
zero deaths. Fort-owned after the rollback: **drink 0, prepared meals 0**,
**raw plants 2** (was 8), seeds 60, logs 3, boulders 0, and **15 empty
barrels**.

**The route is brewing, not a well.** Settled from the install's own data:
**no reaction anywhere produces `TRAPPARTS` from wood**, and DFHack's
`stockflow.lua` offers `ConstructMechanisms` only under rock and metal, so the
well needs stone the fort does not have. Brewing needs only a still (1 log of
3) and an empty `FOOD_STORAGE` container, and **the fort already owns 15
barrels**, so the container is free. 2 plants brew to up to 10 drinks
(`brewing-chain-from-raws`, `plump-helmet-is-brewable`, both verified).

**The deliverable is not the drink, it is the two thirst reads.** Whether
alcohol satisfies thirst on this install is still only `prior`, on an
unrecorded wiki read.

Measured across two exact reads: **delta tick 6,303 equalled delta thirst
6,303** across all 15 citizens, so `thirst_timer` rises 1 per tick and nobody
drank in that window. Top thirst 31,899.

**The measurement method is now cleared, but the contradiction is still open.**
`getWalkableGroup` was compared against tile shape and the two **agree** at 0
walkable neighbours, sanity-checked first against all 15 citizens' own
known-walkable positions. So the suspicion below was unfounded and the reading
was sound. **What remains unexplained:** the offered explanation (that a
41-tile dig bridged the network and was lost in the rollback) **does not fit
the dates**, because the rollback happened *after* the zero-walkable
measurement was taken. Either something else removed reachability between
2026-09-17 and 2026-09-19, or that dig never reached the water, or the
2026-09-17 drinking happened elsewhere. Left open deliberately.

**The original suspicion, kept for the record:** An audit found that the 2026-09-17 record has three founders
demonstrably drinking at that pond with `NastyWater` thoughts, while the
2026-09-19 reading says zero water tiles have a walkable neighbour, which
would make that impossible. **Leading hypothesis: the 2026-09-19 reading is
mine and is wrong**, because it derived walkability from tile *shape* while
the pond is a bowl of submerged RAMP tiles a dwarf may wade across. The right
primitive is probably `dfhack.maps.getWalkableGroup`, which
`df-overseer-connectivity.lua` already uses.

**Do not act on the well plan until that is settled.** What survives either
way: nobody drank over that window.

**The brew route may be shorter than the well anyway.** Doctrine
(`alcohol-is-not-food`, status `prior`) holds that drink satisfies thirst on
its own, which would make the whole pond question moot. The fort has 8 raw
plants and 3 logs; the still is designated but unbuilt with its job **366**
reported suspended twice.

### Update, 2026-09-19 morning (read before the list below)

**The fort survived and drinks.** Live read at tick **272606**, paused: **23
citizens alive, 0 dead** (eight migrants arrived), a still exists, drink stock
0. All 15 original citizens (ids 192-198 and 344-353) have thirst at or below
28,922 after roughly 59,000 elapsed ticks, which is only possible if each
drank. The newest eight (453-460) sit at 1,737-2,377 in exact steps of 100,
consistent with arrival, so they are not counted as evidence. **What they drank
is unknown and deliberately not being chased** (user, "idrc"): 2 plants brew at
most 10 drinks, which cannot cover it alone.

**Autosave is fixed** (register 2026-09-19): an in-game `repeat` quicksaves
every 7 game days, persisted in `onMapLoad.init`. Registered, **not yet seen
firing**. A manual quicksave was taken at 272606 and confirmed by slot mtime.

**The well stream and the extraction stream both died on a Sonnet session
limit.** The extraction work was preserved on its branch and the stream has
been resumed. Three streams now running: extraction (resumed), deploy and
live-verify (VM 103), and `get_doctrine`.

**User directions:** blocks come from mining plus a mason's workshop;
drinks must be kept ahead of the plants (`brew-before-plants-run-out`); neither
is the current focus. **The loop itself ("nothing runs on its own") is not
being built unilaterally**: its core architecture is pending the user's
decision, per the learning-loop section above.

### Update, 2026-09-19 afternoon: the fort records its own history

The in-game sampler is live (one record per game day, `docs/TIMESERIES.md`),
`dfseries` stores it, and the two were proven end to end on a real 9-game-day
run. The autosave was seen firing for the first time. **The fort is paused at
tick 283992** and **runs at 100 FPS, not 10**, despite several docs. The user
directed the order: **fix the timer-reset bug, then automatic import, then MCP
tooling**, and is away. Reset fix and auto-import are running; the MCP stream is
written and waits on the reset fix.

### RESUME HERE (2026-09-20)

- **Fort**: well built (id 8), fed, farm rebuilt, 22 alive / 1 starved,
  paused at year 31 tick 103055, autosave and sampler running.
- **Deploy batch fully live** (`handoffs/2026-09-19-deploy-batch.md`, incl.
  its 2026-09-20 follow-up). The WAL block is fixed with one
  `ReadWritePaths=/var/lib/dfseries` line in `dfmcp-server.service`, and
  `series.*` was verified live over a real MCP client. `dfseries/` was
  redeployed, hash-checked twice, with hunger `reset_to_zero_verified=True`
  confirmed on the VM; the importer ran clean. Revert backups are in
  `/opt/df/deploy-backup-2026-09-20-{wal,dfseries}/`. Live tool ids are
  double-underscored (`series__resets`), not dotted.
- **Stopped here on the user's instruction.** Next, when resumed: brewing
  (workjob refuses the container reagent by design), an appoint-a-Manager tool,
  fishing/hunting, finding the fort's unlocated water source, the MCP
  apostrophe fix. Loop design is tabled by the user.

### START HERE, in priority order

**Sequencing rule while streams are live:** only one stream touches VM 103 or
the fort at a time. Two `production/` streams may run together **only** when
their file ownership is strictly disjoint and each handoff names the other's
files as forbidden.

**The worktree trap, hit twice now:** a worktree agent is cut from the last
**pushed** commit. Write the handoff, commit, **push**, then dispatch. A local
commit is not enough.

0. **Settle the walkability contradiction, then get the fort drinking**, by
   whichever of brew or well the evidence favours. Running:
   `handoffs/2026-09-19-well-unblock.md`. Done means thirst **falling** across
   two reads, not a well existing.
1. **Deploy the new tools to VM 103 and live-verify them.** Queued behind the
   fort stream. Three things landed undeployed today: `stocks.availability`
   (new), the silent-zero fixes in `trees`/`workshop`/`well`, and the older
   `dig-stair` fix. **`stocks.availability` specifically needs both
   `UNIT_HOLDER` branches exercised** (a known-held item and a known-unheld
   one) before `owned_ref_check.verified_offline` can honestly flip to true.
   Reconcile the `ROADMAP.md` / `CLAUDE.md` tool counts against the real
   post-deploy numbers at the same time.
2. **Fill the graph.** Running:
   `handoffs/2026-09-19-real-corpus-extraction.md`. The extractor had never
   seen real data; 159 real reactions are staged out of tree.
3. **Then the supervised run**, written and waiting:
   `handoffs/2026-09-18-supervised-run-and-measure.md`. Settles four known
   unknowns including the `growdur` unit that blocks the harvest clock.
4. **The stair to z167** stays outstanding unless the fort stream resolves it
   as part of a stone route. Orphan UpStair designation at z167 still present;
   the `dig-stair` fix is merged but undeployed.

### Done today, so do not go looking for it

Six streams merged on 2026-09-19: the snapshot assembler, the water doctrine
correction, the unverified-claims audit, the availability tool, the
silent-zero fix, and (2026-09-18) days-of-cover and the blocker walk. Suite is
**382 passed / 1 skipped**. `production/` is six modules. The visual ledger is
at the artifact URL recorded above.

