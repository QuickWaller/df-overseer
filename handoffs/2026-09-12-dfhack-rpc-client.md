# Stream: DFHack RPC client

**Dispatched** 2026-09-12. **Status:** dispatched.

## Scope

Build `mcp/dfhack_client.py`: a persistent-connection client that runs this
repo's `df-overseer-*` commands over DFHack's RPC socket and returns their
output. This is the second of the MCP server's two missing halves (the other
is the transport, which is blocked on an open question and is not this
stream).

**The protocol is already settled. Do not re-derive it.** Read
`research/2026-09-12-dfhack-rpc-client.md` first: it has the handshake bytes,
the header layout, the method ids, the message field numbers, and the
recommendation. It was written against DFHack 53.16-r1.1, the version the VM
runs, and its load-bearing claims were re-checked against the installed
build's own protocol docs. Build to it.

## What the brief already decided, so you do not have to

- **Hand-roll the wire format.** No `protobuf` dependency, no generated stubs,
  no third-party client (the one that exists is unmaintained, unlicensed, and
  mis-frames replies above 16MiB). A minimal varint plus length-delimited
  codec covers every message involved.
- **`BindMethod` is not needed.** `RunCommand` is a hardcoded id on every
  connection.
- **Output arrives clean.** One `print` becomes one text fragment; colour is a
  separate field and never embedded in the text, so `json.loads` on the
  fragment text is safe with no sanitising. `docs/TRAPS.md`'s escape-sequence
  trap is about `dfhack-run`'s own rendering and does not apply here.

## The one design point that is not just transcription

**A connection carries one request at a time**, so concurrency needs a pool
(`docs/AGENT-ARCHITECTURE.md` §6 and §14 item 5, both corrected 2026-09-12).
Build a small pool with an explicit, configurable size, and make the batched
case a real method: issue N independent reads concurrently so their suspend
requests are pending at the same instant and DFHack services them in one
window, rather than looping them sequentially. Pool size is the cap on that
saving, so it belongs in config, not hardcoded.

Also handle, with tests: a dead socket mid-request, a connection refused
because DF is down, and reconnection (a fresh handshake, no server-side
session to resume). A DF restart must not leave the pool full of dead
sockets that fail every later call.

## Acceptance criteria

1. Unit-testable with **no VM and no live DF**. Test against a fake server
   you write that speaks the real framing — that is the point of a hand-rolled
   codec. Round-trip the codec against known byte sequences from the brief.
2. `pytest` from the repo root passes, count above the current 86. Report both.
3. `tests/test_no_leaked_addresses.py` still passes. **This repo is public**:
   no address or hostname in any tracked file. Loopback is fine and is not a
   leak.
4. `mcp/README.md` gains a section in the voice of the existing ones,
   including the pool rationale and anything you could not verify offline.

## Explicitly out of scope

- **No MCP SDK, no HTTP server, no transport.** That is the next stream and it
  is blocked on an open question.
- **No live verification against VM 103.** VM 103 runs the live fort. Touching
  it needs the user's explicit go-ahead and a heads-up to the live `home-lab`
  session, neither of which you can obtain. Build to the line, then stop and
  report the exact command you would run. Executor rule 2 applies in full.
- **Do not write `Working.md`, `decisions/DECISIONS.md` or `memory/`** (see
  `handoffs/INDEX.md`). Report findings; the orchestrator writes the rows.

## Report

Executor report shape, plus a **"Findings to record"** section. Say plainly
what remains unproven until it runs against a real DFHack, since everything
here is verified against a fake server of your own construction.
