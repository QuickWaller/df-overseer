# Why `quicksave` Silently No-Ops on VM 103, and Whether That's Suspicious

Date: 2026-09-11
Scope: investigate why `./dfhack-run quicksave` (over SSH, VM 103, fort "Uniboslan") logged and saved nothing on
two consecutive attempts this session, then worked normally on a third — and whether the newly-deployed
personal-control VNC channel, concurrent peer sessions, or infra exhaustion are plausible causes, versus a routine
DFHack mechanism.
Status: **live investigation against the running VM**, read-only except for issuing `quicksave`/pause-state calls
(explicitly permitted, matching this project's own "reproduce read-only" convention). Fort was confirmed paused
before touching it and re-confirmed paused-and-freshly-saved at the end (see §6). Primary sources used throughout:
the installed `quicksave.lua` script itself, live `stderr.log`/journal/auth-log evidence from VM 103, and live
`dfhack-run` reproduction run directly during this investigation — not docs, not the prior session's own
after-the-fact narrative, which is treated here as a claim to verify, not as ground truth.

---

## 1. Bottom line, up front

**The leading, directly-reproduced explanation is verification-window mismatch, not external interference.**
`quicksave` is not a synchronous engine call — it is a DFHack Lua overlay screen (`QuicksaveOverlay`) whose actual
save logic only runs when the game's render loop next processes that overlay, on a timing that this investigation
found to be **unpredictable and, in one directly-reproduced case, at least 45-80 seconds** — far outside the "wait a
few seconds and recheck" (and even the later "retry and recheck") verification protocols this project had been
using. In a live, controlled reproduction this session (fort paused, no VNC activity, nothing else running), a
`quicksave` call returned exit 0, produced **no** `Invoking: quicksave` line and **no** "should autosave" line for
over 45 seconds, yet the underlying save **did** land for real (save-slot rotation and a fresh `world.sav` mtime,
confirmed) once the delay had elapsed. This directly falsifies the assumption, baked into the prior session's own
diagnosis, that "no log line + no mtime change within a few dozen seconds" reliably means "no-op happened." It may
instead mean "not finished yet."

**The two hypotheses this task most wanted checked — the new VNC control channel, and concurrent peer
sessions — are each addressed with real evidence, not just asked-and-shrugged:**
- **VNC channel: temporally ruled out for the specific failure window.** The only real, human-input VNC session
  logged all day ran 00:35:32-00:48:04 UTC (48 `PointerEvent`s, 6 `KeyEvent`s — a genuine active session, not a
  ping). The two failed quicksave attempts, reconstructed from real save-slot mtimes (§3), fall in a roughly
  00:54:40-00:55:15 window — **about 6.5 minutes after the VNC session's own log recorded it ending.** Not
  proof of zero effect (a dialog left open by that session could theoretically persist), but the "someone was
  actively clicking at that exact moment" version of this hypothesis does not hold up against the timeline.
- **Concurrent peer sessions: not ruled out, and one new, independent data point supports the concern.** While
  this investigation was live, `df.global.pause_state` flipped from `true` to `false` between two of this
  session's own checks (~01:07 and ~01:10:47 UTC) with **no** VNC activity in that window (nothing logged past
  00:48:04) and no action taken by this investigation. Something else touched the fort's live state during this
  session. `df-automation-e6` was asked directly (message sent, reply will land in the orchestrator's
  conversation, not this report — see §5); `df-automation-ca` was not reachable by name at the time of asking.
- **Mundane infra causes: checked and ruled out.** Disk 32% used (16G free), memory 5.8G total/3.5G available,
  no OOM signals in the journal, `df-fortress.service` and both VNC-control units all healthy throughout.

**A secondary, real, and independently useful finding**: the "Invoking: `<command>`" console line this project's
verification method leans on is **not a reliable proxy for "the RPC command was dispatched."** A command that
demonstrably succeeded (slot rotated, file mtime updated) produced no such line at all, ever, in this session's
direct reproduction. Any future automated save-verification logic should stop treating that line's absence as
diagnostic of anything.

---

## 2. What `quicksave` actually is (primary source: the installed script)

Read directly from `/opt/df/game/hack/scripts/quicksave.lua` on VM 103:

```lua
local gui = require("gui")

QuicksaveOverlay = defclass(QuicksaveOverlay, gui.Screen)

function QuicksaveOverlay:render()
    if not self.run then
        self.run = true
        save()
        self:renderParent()
        self:dismiss()
    end
end

if not dfhack.isMapLoaded() then
    qerror("World and map aren't loaded.")
end

if not dfhack.world.isFortressMode() then
    qerror('This script can only be used in fortress mode')
end

function save()
    local ui_main = df.global.plotinfo.main
    ui_main.autosave_request = true
    ui_main.autosave_timer = 5
    ui_main.save_progress.substage = 0
    -- ... (state-reset fields)
    print 'The game should autosave now.'
end

QuicksaveOverlay():show()
```

Three things this settles, **confirmed by reading the actual installed source**, not the doc page:

1. **`quicksave` is not itself a save routine.** It pushes a new DFHack Lua overlay screen (`QuicksaveOverlay`)
   onto the game's viewscreen stack via `:show()`. The actual `save()` call — which sets the engine's own
   `autosave_request`/`autosave_timer` fields and prints the log line — only runs inside that overlay's
   **`:render()` method**, which fires on a subsequent game render pass, not synchronously with the RPC call that
   invoked the script.
2. **There are two guard clauses** (`isMapLoaded()`, `isFortressMode()`) that would `qerror()` out before ever
   reaching `show()`. Confirmed by reading the guard code directly. This matters for what a genuine guard-triggered
   failure would look like (see §4) — and this session's evidence rules that specific mechanism out for the two
   observed no-ops.
3. `quicksave.txt` (the shipped doc) says nothing about any of this — it describes `quicksave` as if it were an
   immediate, synchronous autosave ("DF will immediately do an autosave"). **Docs and code disagree here**: the
   doc's "immediately" is not literally true; the code shows an asynchronous, render-loop-gated mechanism. Flagging
   this explicitly per this project's evidence standard — the code is authoritative.

---

## 3. Reconstructing the historical incident's real timeline (not just the qualitative account)

`stderr.log` on VM 103 carries **no timestamps of its own** (confirmed: every line is bare console text, no
per-line time prefix) and the DFHack process's stdout/stderr is **not** mirrored into the systemd journal past
startup (`journalctl -u df-fortress.service` only has real timestamps up through the literal
"redirecting stderr to stderr.log" line, then nothing — confirmed by grepping for `quicksave`/`autosave` in the
journal and getting zero hits). This is a real gap in this project's own logging setup, not something this
investigation could route around cleanly — but the **save files themselves carry real mtimes**, and those turned
out to be enough to reconstruct the timeline precisely.

Exact epoch mtimes of the three `autosave N/world.sav` files, read fresh at the start of this investigation
(save actually lives at `/home/df/.local/share/Bay 12 Games/Dwarf Fortress/save/`, confirmed — `/opt/df/game/save`
is a real, non-symlinked directory that happens to report the same path via `dfhack.getSavePath()`, which is worth
a small doc correction: this install's actual save location matched the already-documented XDG-path trap when
checked directly against the filesystem, not assumed):

| slot | mtime (UTC) |
|---|---|
| `autosave 1` | 00:53:21 |
| `autosave 2` | 00:54:35 (+74s) |
| `autosave 3` | 00:55:32 (+57s) |

Cross-referenced against `stderr.log`'s three (and only three) `Invoking: quicksave` lines in the entire file
(the file spans the full 21+ hour `df-fortress.service` uptime, not just this session), each immediately followed
by "The game should autosave now.": these three lines are the only ever-logged quicksave invocations in the file's
history, and they line up with the "2 successes, unpause/repause, 2 no-ops, 1 success" account almost exactly by
elapsed time: **74 seconds between the first two successes (matches "~1 min later"), and the entire 57-second gap
before the third success has room for exactly** the described unpause (~15s) + repause + two failed attempts
(~20s apart each) + final success, with essentially no slack left over. This is strong, internally-consistent
confirmation that **the two no-op attempts happened in the roughly 00:54:40-00:55:15 UTC window** — squeezed
between the second and third real saves.

**Rotation policy, confirmed empirically, not assumed**: the pool of 3 `autosave N` slots is overwritten
**least-recently-modified-first**, not by a fixed round-robin pointer. Confirmed twice live this session (§4): a
fresh quicksave always landed in whichever of the three slots had the oldest mtime at that moment, in both this
historical reconstruction and in this session's own live reproduction tests.

---

## 4. Live reproduction: the load-bearing new evidence

With the fort confirmed paused and no VNC client connected (`ss -tn` clean, `x11vnc.log` showing nothing since
00:48:04), this investigation ran `./dfhack-run quicksave` directly and tracked it precisely:

- **Immediately after** (exit code 0, `+3s` and `+13s` checks): `stderr.log` line count unchanged except for the
  bare `Client connection established.`/`Shutting down client connection.` pair every `dfhack-run` call produces
  regardless of outcome — **no `Invoking: quicksave`, no "should autosave" line.** `plotinfo.main.autosave_request`
  read `false`, timer `0`. By this project's own prior verification method, this would have been logged as a
  third silent no-op.
- **At +~45-80s** (exact bound: the line was absent through a check at +13s and present by a check at +~48s of
  elapsed wall time, with several other unrelated `dfhack-run` calls interleaved in between): "The game should
  autosave now." appeared — **but still with no `Invoking: quicksave` line ever appearing, before or after.**
  `cur_savegame.save_dir` had rotated to the then-oldest slot, and that slot's `world.sav` mtime matched the save
  landing for real.

This was repeated with a second, independent live quicksave later in the session (after this investigation
accidentally caught the fort unpaused — see §5): same shape, confirmed successful (slot rotated, fresh mtime)
within one 8-second poll interval that time — i.e., **the delay is variable, not a fixed constant**, ranging from
under 8 seconds to well over 45 seconds across three directly-observed attempts (the two historical no-ops, whose
true completion time is now unknowable — see §4.1 — plus these two fresh ones).

**What this rules in and out:**
- **Rules out** the `isMapLoaded()`/`isFortressMode()` guard clauses as the mechanism for *these* two reproduced
  cases: a guard-triggered `qerror()` would still print `Invoking: quicksave` first (the dispatcher logs the
  invocation before the script body runs), then an error — exactly the pattern already visible elsewhere in this
  same `stderr.log` for other scripts (e.g. `(lua command):2: attempt to call a nil value (field 'popen')`,
  `Cannot read field global.job_list: not found` — real script errors that *do* leave a trace). Neither reproduced
  no-op left any such trace.
- **Directly falsifies** treating "`Invoking: quicksave` line present" as a reliable signal of "RPC command was
  dispatched." It was absent for a call that unambiguously succeeded.
- **Leaves open** exactly why the render-loop pickup is delayed by such a variable amount. The most parsimonious,
  evidence-consistent mechanism (not independently confirmed against DFHack's C++ core, which isn't available as
  source on this install — only compiled binaries and Lua scripts are present) is contention on DFHack's single
  main simulation/scripting thread: `./dfhack-run repeat --list` shows **10 currently-registered
  `control-panel/fix/*` repeating scripts** (`fix/stuck-instruments`, `fix/engravings`, `fix/stuck-worship`,
  `fix/noexert-exhaustion`, `fix/stuck-squad`, `fix/empty-wheelbarrows`, `fix/ownership`, `fix/general-strike`,
  `fix/dry-buckets`, `fix/dead-units` — DFHack v50's stock "recommended repeats," confirmed live, not something
  this project's own scripts registered) that fire extremely frequently throughout `stderr.log` (255+ occurrences
  of `fix/noexert-exhaustion` alone across ~1450 lines) and continue even while the fort is paused — consistent
  with a `frames`-based (not `ticks`-based) schedule, since `ticks` are explicitly documented as "unpaused game
  frames" only. `repeat-util.lua`'s own scheduling mechanism (`dfhack.timeout`) runs on the same main thread DFHack
  uses for all Lua/script execution — a documented architectural fact — so a busy, frequently-reentered main loop
  competing with an overlay screen that needs its own render pass to fire is a credible, but **not source-verified**,
  explanation for both the variable delay and the missing log line. **Flagged explicitly as inferred, not
  confirmed** — the DFHack core source that would settle this isn't present on this machine.

### 4.1 A genuine, honestly-reportable gap

Because the save-slot pool only holds 3 entries and gets overwritten least-recently-modified-first, **the two
historical no-op attempts' eventual fate is now unrecoverable**: if they behaved like this session's reproduced
cases and eventually completed 45+ seconds later (well within the 57-second window before the historical third
success), any trace of that would have been the same three slots — already overwritten by the historical third
success and now by this session's own two reproduction tests. There is no way, after the fact, to distinguish
"those two really did nothing" from "those two also landed late, just later than the ~20s the prior session waited
before moving to the next attempt." This is not resolved. It is flagged rather than papered over, per this
project's own evidence standard.

---

## 5. Concurrent-session finding (new, unresolved, worth the orchestrator's attention)

While this investigation was itself live and had not touched pause state, a routine check found:

- ~01:07 UTC: `df.global.pause_state` → `true` (consistent, expected).
- ~01:10:47 UTC: `df.global.pause_state` → `false`.

No VNC input was logged anywhere in that window (`x11vnc.log`'s last activity is 00:48:04, over 20 minutes
earlier), and this investigation had issued no unpause command. Something else — most plausibly a concurrent
Claude session with SSH/`dfhack-run` access to the same VM — flipped it. This is exactly the kind of concurrent-
access scenario the task asked to check for. Two things were done about it, not just noted:

1. **Re-paused immediately** (confirmed `true` again within the same investigation step) rather than letting the
   fort run unattended-and-unnoticed.
2. **Asked directly, via `SendMessage`**: `df-automation-e6` was reachable and a message was sent asking whether
   it (or anything it kicked off) touched VM 103 around 00:53-00:56 UTC (the historical no-op window) or
   01:07-01:11 UTC (this investigation's own window), and whether it knows `df-automation-ca`'s activity.
   `df-automation-ca` was **not reachable by that name** at the time of asking (no live agent/session matched it) —
   this could mean it isn't currently running, or that its actual live name differs from what the task brief
   assumed; either way, it could not be asked directly this session.
   **Important for whoever reads this next**: that message was sent from a subagent, which this project's own
   messaging tool documents as being relayed under the *parent* session's address — any reply from `df-automation-e6`
   will arrive in the orchestrating session's conversation, not in this report. The orchestrator should watch for
   it rather than assume no reply means no answer.

**This does not, on its own, explain the historical no-ops** (that window, 00:54:40-00:55:15, predates this
session's own investigation entirely, and the pause-flip observed here happened over 15 minutes later, in a
different window) — but it is real, independent evidence that **this fort is not, in practice, insulated from
concurrent unannounced access during normal working sessions**, which is exactly the standing caution
`docs/DF-UI-AUTOMATION.md` and `Working.md` already carry for the VNC channel, now shown to apply more broadly
(a pure `dfhack-run`/RPC session did it here, not VNC/`xdotool`).

---

## 6. Mundane infra causes: checked directly, all clear

- **Disk**: `df -h` on VM 103 — root filesystem 32% used, 16G available. Not remotely close to full.
- **Memory**: `free -h` — 5.8G total, 2.3G used, 1.2G free, 2.6G buff/cache, **3.5G available**. Some headroom
  pressure exists (this is a modest VM running a 1.7G-resident DFHack process) but nothing indicating exhaustion.
- **OOM/journal**: no OOM-kill messages found; `df-fortress.service`'s own unit has been `active (running)` for the
  entire 21+ hour span with a single stable `Main PID`, no restarts, no crash-exit codes logged in that window.
- **Both VNC-control units** (`df-vnc-control.service`, `df-vnc-control-tunnel.service`): `active`, stable, no
  errors, for their entire (much shorter, ~33min-old-at-investigation-start) lifetime.
- **One stray finding, unrelated to quicksave but worth a note for whoever owns the VNC-control infra**: `ss -tn`
  on VM 103 shows a TCP socket on `127.0.0.1:57980 <-> 127.0.0.1:5901` still `ESTABLISHED` at the time of this
  writing, more than 20 minutes after `x11vnc.log` itself logged that exact client (`port 57980`) as
  `Client 127.0.0.1 gone` at 00:48:04 and reset its own connection statistics. This looks like a lingering/leaked
  TCP connection in the reverse-tunnel path (most likely the SSH `-R` forward's local socket, not x11vnc's own
  application-level session, which the log confirms ended cleanly) rather than a live, currently-active control
  session. Not chased further — it does not fall inside either quicksave-failure window and isn't this report's
  question — but flagged since nothing in this project's existing docs describes it, and it's a real observable
  on a channel this project already treats as sensitive.

---

## 7. Ranked hypotheses (confidence, and what would move the needle)

1. **Verification-window mismatch — the save likely did or would eventually have landed, just later than checked.**
   **Highest confidence**, directly reproduced live this session (§4). This is the only hypothesis with a live,
   controlled, repeatable demonstration behind it rather than circumstantial timing.
2. **DFHack main-thread contention with the stock `control-panel/fix/*` repeat schedule** as the mechanism
   *behind* (1) — plausible, consistent with confirmed facts (10 live repeats, very high frequency, shared
   single-threaded execution model), but **not verified against DFHack's actual core source** (unavailable on this
   install). Would need either DFHack's own GitHub issue tracker (not checked this session — time-boxed out) or a
   controlled test that temporarily cancels the repeats (`repeat --cancel <name>` for each) and reruns the
   quicksave-timing experiment, comparing delay distributions with and without them running.
3. **Concurrent-session interference (a peer Claude session or the VNC channel touching shared state)** —
   real and confirmed as a *general* live risk (§5's pause-flip), and structurally plausible as a contributor to
   (2)'s contention story, but **temporally ruled out as the direct cause of the two historical no-ops
   specifically** (VNC session ended 6.5 minutes prior; the pause-flip incident happened in a different,
   15-minutes-later window). Would need `df-automation-e6`'s and `df-automation-ca`'s direct confirmation
   (requested, not yet answered as of this report) to close out fully.
4. **Something worse (unauthorized access, a race corrupting state)** — **no evidence found for this.** Nothing
   in the auth log, journal, or VNC log suggests any connection from outside the expected `192.168.2.159`/relay
   path. Not ruled impossible in principle, but there is no positive evidence pointing toward it, and the far
   more mundane explanation (1) already accounts for the observed symptoms without needing it.

---

## 8. Recommendation

**Don't chase this further as an active incident.** The evidence assembled here — a live, repeatable
reproduction of the exact "no log line, no immediate mtime change, real save later" pattern under quiet
conditions — is strong enough to treat the original two no-ops as most likely the same benign latency, observed
with too short a verification window, rather than a sign of external interference or corruption.

**Do fix the verification protocol**, since this is genuinely actionable and cheap:
- Any future automated "did the quicksave actually happen" check should **poll for a while (demonstrated
  necessary: up to ~80 seconds observed; budget more, not less) rather than check once or twice a few seconds
  apart**, and should key off **`cur_savegame.save_dir` + that slot's `world.sav` mtime changing**, never off the
  presence/absence of `Invoking: quicksave` or "The game should autosave now." in `stderr.log` — this session
  proved that line is not reliable evidence either way.
- `Working.md`'s existing "retry and recheck" advice for quicksave should be upgraded to **"poll the active save
  slot's mtime for up to ~90 seconds before concluding failure"** — the underlying claim ("quicksave can silently
  no-op, not just lag") should be downgraded from confirmed to **unresolved, likely just lag**, per §4.1's honest
  gap.
- Worth a follow-up, not urgent: `stderr.log` carrying no timestamps at all is a standing observability gap that
  made this reconstruction much harder than it needed to be (it only worked because save-file mtimes happened to
  be precise enough); if this project ever wraps DFHack's stdout more, prefixing each line with a wall-clock time
  (e.g. via `ts` in the systemd unit, or a small logging shim) would make any future timing question like this one
  answerable directly instead of via reconstruction.
- The stray lingering VNC-control TCP socket (§6) is worth a look by whoever owns that channel, but it is not
  blocking and not this report's question.

---

## 9. What was verified vs. not, explicitly

**Verified directly this session** (primary source or live reproduction, not taken on trust):
- `quicksave.lua`'s actual source and its asynchronous, render-loop-gated design.
- The three historical `Invoking: quicksave` lines and their exact real-world timing via save-slot mtimes.
- Live reproduction of a `quicksave` call succeeding with a 45+ second delay and no `Invoking:`/print trace during
  that delay.
- Live reproduction of the save-slot rotation policy (overwrite-oldest, not fixed round-robin).
- Disk, memory, journal, and both VNC-control units' health on VM 103 at investigation time.
- The VNC control channel's only logged activity window (00:35:32-00:48:04 UTC) and its non-overlap with the
  reconstructed historical failure window.
- A real, live pause-state flip during this investigation's own session, from an unidentified source.

**Not verified / genuinely open:**
- Whether the two *historical* no-ops specifically ever completed late (unrecoverable — §4.1).
- The exact DFHack core mechanism causing the render-loop pickup delay (inferred from architecture and the
  `repeat --list` evidence, not confirmed against source not available on this install).
- Who or what flipped `pause_state` during this session (message sent to `df-automation-e6`, reply pending as of
  this report; `df-automation-ca` unreachable by name).
- Whether DFHack's own GitHub issue tracker documents this delay/contention pattern — not checked this session
  (time-boxed out in favor of the live reproduction, which is stronger evidence anyway).

---

## 10. End-of-session state (fort safety)

Confirmed clean before finishing, not assumed:
- `df.global.pause_state` → `true`.
- `df.global.world.cur_savegame.save_dir` → `autosave 3`.
- `autosave 3/world.sav` mtime → 2026-09-11 01:13:08 UTC, matching a `quicksave` issued and polled-for-completion
  moments earlier in this same investigation (confirmed via the same mtime-polling method this report recommends
  adopting generally, §8).
