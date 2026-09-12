# DFHack RPC Client for a Persistent-Connection MCP Server

Date: 2026-09-12
Scope: settle `docs/AGENT-ARCHITECTURE.md` §14 item 5's performance requirement
("hold one persistent DFHack RPC connection... batch a cycle's reads into one
suspend window") into a buildable client design, at the exact installed
version, **DFHack 53.16-r1.1**.
Status: read-only. No connection to VM 103/106, no DF process started or
stopped anywhere. Sources: the local Windows Steam DFHack install's shipped
docs (primary, version-exact for this build), a fresh shallow clone of
`github.com/DFHack/dfhack` pinned to tag `53.16-r1.1` (commit `b638b59d`,
matching `research/2026-09-12-dfhack-capability-checks.md`'s own pin, so the
two reports cite the identical source snapshot), and live inspection of the
one candidate third-party Python client found on GitHub.

---

## 0. Answers, up front

| # | Question | Answer | Confidence |
|---|---|---|---|
| 1 | Handshake | `char[8] magic="DFHack?\n"` + `int32 version=1` → server replies `char[8] magic="DFHack!\n"` + `int32 version=1`. A rejection (bad magic or `version` outside 1-255) is **not a distinct error message** — the server just returns from its connection thread without sending any reply and the socket is torn down; the client sees this as a read failure ("could not read handshake header") indistinguishable from any other I/O error. | High — direct source read, both sides |
| 2 | Framing | `header = int16 id, int16 padding(unused), int32 size`, 8 bytes, **all little-endian**. Reserved ids (`DFHackReplyCode`, `RemoteClient.h`): `RPC_REPLY_RESULT=-1`, `RPC_REPLY_FAIL=-2`, `RPC_REPLY_TEXT=-3`, `RPC_REQUEST_QUIT=-4`. `RPC_REPLY_FAIL` repurposes the `size` field to hold the `command_result` (`CR_*`) code directly, not a byte count. Max payload 64MiB (`64*1048576`), enforced both directions. | High — direct source read |
| 3 | Method binding + the exact messages | `BindMethod` is id 0, `RunCommand` is id 1, hardcoded, present on every connection without needing a bind call. For this repo's use case (run a `df-overseer-*` console command, get its printed output), **no `BindMethod` call is needed at all** — go straight to `RunCommand`. Exact messages, field numbers from `library/proto/CoreProtocol.proto` at the pinned tag, below. | High — direct `.proto` read at the exact tag |
| 4 | protobuf dependency vs. hand-rolled | **Hand-roll it.** Only five flat proto2 messages are involved (`CoreRunCommandRequest`, `EmptyMessage`, `CoreTextNotification`, `CoreTextFragment`, and `CoreBindRequest`/`CoreBindReply` only if a future tool needs direct method binding), none has a field type harder than string/int32/enum/repeated-of-those. The one existing third-party Python client (`McArcady/dfhack-client-python`) is not something to depend on: unmaintained since Feb 2021, no license file, requires `protoc` plus a local DFHack source checkout just to generate its stubs, and has a real read-side bug (below) found by direct comparison against the wire spec. | High on the recommendation; the "no maintained library exists" survey is a real, if narrow, GitHub search |
| 5 | Output delivery | A single `print(json.encode(...))` call becomes **one `CoreTextFragment` inside one `CoreTextNotification`/`RPC_REPLY_TEXT` message** (not split by line or size, up to the 64MiB cap), sent before the closing `RPC_REPLY_RESULT`/`EmptyMessage`. **Colour is a separate per-fragment field (`color`, int enum), never embedded in `text`.** The ANSI escape codes `docs/TRAPS.md` observed are `dfhack-run`'s own terminal-rendering of that field — a client that reads `fragments[i].text` and ignores `.color` gets the JSON completely clean, with no escape sequence to strip. | High — traced both the server's buffering code and the two client-side renderers (`dfhack-run`'s `Console::add_text` vs. the raw field) |
| 6 | Concurrency | **No. One connection cannot carry more than one in-flight request.** The per-connection server thread is a strict read→process→reply→read-next loop; it does not read the next request header until it has sent the previous reply. The "every suspender pending at the same moment is serviced in one window" property §6 of the architecture doc relies on requires **multiple concurrent connections** (the server spawns one OS thread per accepted connection), not multiple requests on one socket. This is a real correction to §14 item 5's third bullet, not just a footnote. | High — direct read of `ServerConnection::threadFn`'s loop structure |
| 7 | Reconnect | Detected as a read/write failure (`recv` returning ≤0, or a connect-time refusal) — there is no ping/heartbeat RPC method. Across a DF restart, the listening socket and all accepted sockets go away with the process; reconnecting means redoing the handshake from a fresh TCP connect, which will fail with connection-refused until DFHack is back up. **Nothing needs re-binding for this repo's use case**, because `RunCommand` (id 1) is a hardcoded id on every fresh connection — `BindMethod`-obtained ids are private to the `ServerConnection` object behind one socket and would need re-requesting after reconnect, but this repo's tools never use them. | High for the mechanism; "no heartbeat exists" is a negative finding from reading the full method list, not exhaustively proven absent from every plugin |
| 8 | Unauthenticated + bind interface | **Confirmed, and one detail is stronger than §13 assumed.** No credential of any kind anywhere in the handshake or dispatch path. The listening socket binds `127.0.0.1` unless `dfhack-config/remote-server.json` sets `"allow_remote": true`, in which case it binds all interfaces (`NULL` passed to `Listen`). But `RunCommand` — the one method an MCP server built on this repo's tools would actually call — carries **no** `SF_ALLOW_REMOTE` flag, so it is rejected from any address other than the literal string `"127.0.0.1"` **even if `allow_remote` is turned on**, by a separate per-method IP check in the dispatch loop. So §13's trust-boundary argument holds, and is actually more conservative in practice: misconfiguring `allow_remote` alone would not expose `RunCommand` to the network. | High — direct source read of both the listen-address selection and the per-method IP gate |

---

## 1. Handshake

Primary source: `hack/docs/docs/dev/Remote.txt` (shipped, read in full — this doc
is unusually complete and matches the source exactly, see §9), cross-checked
against `library/RemoteClient.cpp` (`RemoteClient::connect`) and
`library/RemoteServer.cpp` (`ServerConnection::threadFn`'s handshake block) at
the pinned tag.

Client → server, 12 bytes total, all little-endian:

| Type | Name | Value |
|---|---|---|
| `char[8]` | magic | `"DFHack?\n"` |
| `int32` | version | `1` |

Server → client, same shape, on success:

| Type | Name | Value |
|---|---|---|
| `char[8]` | magic | `"DFHack!\n"` |
| `int32` | version | `1` |

Server-side acceptance check, quoted directly (`RemoteServer.cpp`):

```cpp
if (memcmp(header.magic, RPCHandshakeHeader::REQUEST_MAGIC, sizeof(header.magic)) ||
    header.version < 1 || header.version > 255)
{
    out << "In RPC server: invalid handshake header." << endl;
    return;   // <-- no reply sent; function returns, connection object destructs
}
```

**What a rejection looks like, concretely**: nothing distinguishing arrives on
the wire. The server logs to its own stderr (which a remote client never
sees) and returns without sending any bytes; `ServerConnection`'s destructor
then closes the socket. On the client side, `RemoteClient::connect()`'s next
step (`readFullBuffer(socket, &header, sizeof(header))`) gets `Receive()`
returning `<=0`, which is treated as a generic I/O failure
("Could not read handshake header."). **There is no protocol-level "handshake
rejected" message** — a bad magic/version and a server that crashed
mid-handshake and a firewall drop all look identical to the client: the
socket closes before 8 bytes come back. Build the client to treat "handshake
read fails" as "not talking to a compatible DFHack," not as anything more
specific.

The version check accepts `1`-`255` inclusive on the server side, but both
shipped implementations (client and server) only ever write `1`; there is no
version currently in use above `1` to design around.

---

## 2. Framing

Primary source: `library/include/RemoteClient.h` (`RPCMessageHeader`,
`DFHackReplyCode`), corroborated by `hack/docs/docs/dev/Remote.txt`'s own
"Raw message types" table, which matches the header verbatim:

```cpp
enum DFHackReplyCode : int16_t {
    RPC_REPLY_RESULT = -1,
    RPC_REPLY_FAIL   = -2,
    RPC_REPLY_TEXT   = -3,
    RPC_REQUEST_QUIT = -4
};

struct RPCMessageHeader {
    static const int MAX_MESSAGE_SIZE = 64*1048576;   // 64 MiB
    int16_t id;
    int32_t size;
};
```

Layout is 8 bytes: `int16 id`, then 2 bytes of unused padding (explicit in the
doc's table, implicit in the struct via normal C++ alignment of the following
`int32`), then `int32 size`. **All numbers little-endian** (doc says so
explicitly, and it matches the platform DFHack is built for). A Python struct
format for this header is `<hxxi` (2+2+4 = 8 bytes) — verified against the one
existing third-party client's own (correct, for the header it *writes*) framing
code, see §4.

Message flow per call, from the doc, matching `RemoteFunctionBase::execute`
read directly:

1. Client sends `header(method_id, payload_size)` + the request's
   protobuf-encoded bytes.
2. Server sends zero or more `header(RPC_REPLY_TEXT, size)` +
   `CoreTextNotification` bytes.
3. Server sends exactly one of: `header(RPC_REPLY_RESULT, size)` + the
   method's output message bytes, **or** `header(RPC_REPLY_FAIL, command_result)`
   with **no payload at all** — the `size` field of that header directly *is*
   the `command_result` (`CR_OK=0`, `CR_FAILURE=1`, `CR_WRONG_USAGE=2`,
   `CR_NOT_FOUND=3`, `CR_NOT_IMPLEMENTED=-1`, `CR_WOULD_BREAK=-2`,
   `CR_LINK_FAILURE=-3`, from `CoreErrorNotification.ErrorCode` in
   `CoreProtocol.proto`). This is the one place the framing doc's own
   phrasing ("header(RPC_REPLY_FAIL, command_result)") could be misread as "a
   payload follows" — it doesn't; a client must not try to read a body after
   an `RPC_REPLY_FAIL` header.
4. To close, the client sends `header(RPC_REQUEST_QUIT, 0)` and closes the
   socket immediately; the server's read loop checks for this id **before**
   validating `size`, so no payload is expected or sent either way.

---

## 3. Method binding and the exact messages

`hack/docs/docs/dev/Remote.txt`'s built-in-methods table, confirmed against
`library/RemoteTools.cpp`'s `CoreService::CoreService()` constructor (which
registers them in this exact order so they land on these exact ids):

| id | Method | Input | Output |
|---|---|---|---|
| 0 | `BindMethod` | `dfproto.CoreBindRequest` | `dfproto.CoreBindReply` |
| 1 | `RunCommand` | `dfproto.CoreRunCommandRequest` | `dfproto.EmptyMessage` |

Both are present, at these fixed ids, on **every** connection without a bind
call — `BindMethod` exists only to *look up* the id of everything else (e.g.
plugin RPC methods like `RemoteFortressReader`'s). **This repo's use case
(invoke a `df-overseer-*` console command, capture its printed output) needs
only `RunCommand`.** No `BindMethod` round trip is required at all for that
path — a real, previously-unstated simplification.

Exact message definitions, field numbers as written in
`library/proto/CoreProtocol.proto` at the pinned tag (verbatim):

```protobuf
syntax = "proto2";
package dfproto;

message EmptyMessage {}

// RPC RunCommand : CoreRunCommandRequest -> EmptyMessage
message CoreRunCommandRequest {
    required string command = 1;
    repeated string arguments = 2;
}

message CoreTextFragment {
    required string text = 1;
    enum Color { COLOR_BLACK = 0; /* ...16 values total... */ COLOR_WHITE = 15; };
    optional Color color = 2;
}

message CoreTextNotification {
    repeated CoreTextFragment fragments = 1;
}

// RPC BindMethod : CoreBindRequest -> CoreBindReply  (not needed for RunCommand)
message CoreBindRequest {
    required string method = 1;
    required string input_msg = 2;
    required string output_msg = 3;
    optional string plugin = 4;
}
message CoreBindReply {
    required int32 assigned_id = 1;
}
```

So the entire call for "run this command and get its output" is:

1. Send `header(1, len)` + `CoreRunCommandRequest{command: "df-overseer-overview", arguments: ["get"]}`.
2. Read `header(id, size)` in a loop:
   - `id == RPC_REPLY_TEXT` → parse `CoreTextNotification`, collect
     `fragments[i].text` (ignore `.color` for a clean-JSON client), keep
     looping.
   - `id == RPC_REPLY_RESULT` → parse `EmptyMessage` (i.e. do nothing with the
     body — `RunCommand`'s real output is the text stream, not this message),
     call is complete.
   - `id == RPC_REPLY_FAIL` → `size` field is the `CR_*` code, call failed.

`ServerFunctionBase`'s per-method access flag relevant to `RunCommand`:
registered `SF_DONT_SUSPEND` (`RemoteTools.cpp`: `addMethod("RunCommand",
&CoreService::RunCommand, SF_DONT_SUSPEND)`) — the dispatch loop only wraps a
method in `CoreSuspender` automatically when this flag is absent; `RunCommand`
itself skips that outer wrap so `kill-lua` can still get through a stuck Lua
script (per the comment already quoted in
`research/2026-09-12-dfhack-capability-checks.md` §3), but the actual DFHack
Lua/plugin dispatch underneath still acquires its own `CoreSuspender` one level
down (`PluginManager.cpp`, `LuaTools.cpp`) before touching game state — this
report defers entirely to that prior research for the suspend-mechanism
detail and does not re-derive it.

---

## 4. protobuf dependency vs. hand-rolled: the recommendation

**Recommendation: hand-roll it, no `protobuf` PyPI dependency, no generated
stubs.** Estimated at 100-150 lines for handshake, framing, a minimal
protobuf-wire-format encoder/decoder scoped to exactly the message shapes
above, and the request/response loop.

### Why hand-rolling is genuinely small here

All five messages above use only: `required`/`optional`/`repeated` of
`string`, `int32`, and one embedded-message level (`CoreTextNotification`
containing `repeated CoreTextFragment`). Protobuf's wire format for this
subset is three primitives:

- a **varint** tag byte(s), `(field_number << 3) | wire_type`,
- **wire type 0** (varint) for `int32`/enum fields — used only by
  `CoreBindReply.assigned_id` and `CoreTextFragment.color`, neither needed for
  the `RunCommand`-only path,
- **wire type 2** (length-delimited: a varint length, then that many raw
  bytes) for every `string` and for the embedded `CoreTextFragment` messages.

Encoding `CoreRunCommandRequest` and decoding `CoreTextNotification`/
`EmptyMessage` is therefore: one tag+length+bytes per string field, one
tag+length+bytes per repeated element, and one level of the same recursively
for `fragments`. No `oneof`, no maps, no packed-varint arrays, no default-value
subtleties that matter for a non-validating reader (this client only needs to
be a lenient decoder of trusted local output, not a strict proto2
implementation — it never needs to reject a message for a missing `required`
field it isn't going to read anyway).

### Why not the `protobuf` package plus generated stubs

Not forbidden, just the worse trade here specifically:

- The installed DFHack distribution **ships no `.proto` files at all** — they
  only exist in the DFHack source repository, not in either the Windows Steam
  install or (per `memory/dfhack-environment.md`) the VM's install. Using
  generated stubs means vendoring `.proto` files from a separate GitHub
  checkout into this repo (or fetching them at build time), which is more
  moving parts than the message shapes justify.
- `protoc`-generated Python stubs need either the `protobuf` runtime package
  as a hard dependency, or `grpcio-tools`/`protoc` as a build-time tool — real
  weight for three or four flat messages that never change (`CoreProtocol.proto`
  has been stable in this exact form since DFHack's earliest RPC support; this
  session found no versioned changes to cite, only that it exists unmodified
  at the pinned tag).
- The generated-stubs path pays off when the message surface is large or
  changes often (e.g. a client that also wants full `RemoteFortressReader`
  map/unit structures — a much bigger `.proto` with nested types, oneofs, and
  active development). This repo's need is narrower: run a console command,
  read back text. That is exactly the case the task brief anticipated as
  "simple enough to encode and decode by hand."

### Existing library check: `McArcady/dfhack-client-python`

The shipped doc (`Remote.txt`) names "dfhack-client-python for Python (adapted
from Blendwarf)" as a known client library. Found on GitHub:
`github.com/McArcady/dfhack-client-python` (confirmed via GitHub search API,
not from memory — 8 stars, MIT-adjacent-looking code but **no `LICENSE` file in
the repo**, `pushed_at: 2021-02-19`, i.e. **untouched for roughly five years**,
predating this project's DFHack 53.16-r1.1 by several major DF/DFHack
versions).

It does not work as a drop-in dependency:

- **It is not installable.** No PyPI package (`pip index versions dfhack` and
  four other plausible names all returned nothing). Its own `README.md`
  instructions are `cmake . && make`, which shells out to `protoc` against a
  **sibling checkout of the DFHack source tree** (`CMakeLists.txt`:
  `set(PROTO-DIR-CORE "${CMAKE_CURRENT_SOURCE_DIR}/../dfhack/library/proto")`)
  to generate the Python stubs it imports (`py_export.CoreProtocol_pb2`).
  Using it means reproducing exactly the vendoring problem hand-rolling
  avoids, plus a `protoc`/`python3-protobuf` toolchain dependency, for a
  project this doc otherwise keeps deliberately lean.
- **No license file was found in the repo root**, which matters for a public
  repo (`CLAUDE.md`: "this repo is public") considering depending on or
  vendoring someone else's code.
- **It has a real bug in its own header-parsing, found by direct comparison
  against the wire spec**, not by running it: its `get_header()` (used on
  every reply, including the one in the hot `remote()`-decorator call path)
  reads the 4-byte little-endian `size` field as `int.from_bytes(h[4:7],
  sys.byteorder)` — **`h[4:7]` is a 3-byte slice** (indices 4, 5, 6), silently
  dropping the field's true most-significant byte (index 7). This happens to
  read correctly for any message under `2**24` bytes (16,777,216, since the
  dropped byte is `0` for anything that small) but is wrong for a message
  between that and the protocol's own 64MiB cap — a real, load-bearing bug
  a maintained library should not still carry after five years, and a good
  concrete illustration of why "hand-decode 100 lines yourself, from the spec
  you just read" beats "adopt an abandoned 100-line library you now also have
  to audit line-by-line anyway."

**Verdict for this task's framing ("an existing library that works beats both
options")**: no library on PyPI exists at all for this protocol, and the one
GitHub candidate the DFHack docs themselves point to does not meet that bar —
it is unmaintained, unlicensed, requires a heavier build toolchain than the
protocol needs, and has a real correctness bug in exactly the read path this
project would exercise on every call. This clears the way for hand-rolling
without leaving an unexamined "but a library exists" gap.

---

## 5. Output delivery: framing, colour, and the TRAPS.md question

**Source: `library/ColorText.h`/`.cpp` (`color_ostream`, `buffered_color_ostream`),
`library/RemoteServer.cpp` (`ServerConnection::connection_ostream::flush_proxy`),
`library/RemoteClient.cpp` (`color_ostream_proxy::decode`), and
`library/Console-posix.cpp` (`Console::add_text`) — all read directly at the
pinned tag.**

### How one `print()` call becomes wire bytes

DFHack's `color_ostream::print(fmt, args...)` formats the string, then calls
`add_text(cur_color, str)` once. On the **server side**, the connection's
output stream is a `buffered_color_ostream` subclass; its `add_text`
implementation (quoted in full, this is the whole function):

```cpp
void buffered_color_ostream::add_text(color_value color, const std::string &text)
{
    if (text.empty()) return;
    if (buffer.empty()) {
        buffer.push_back(fragment_type(color, text));
    } else {
        auto &back = buffer.back();
        if (back.first != color || std::max(back.second.size(), text.size()) > 128)
            buffer.push_back(fragment_type(color, text));   // new fragment
        else
            buffer.back().second += text;                   // merge into previous
    }
}
```

A single `print(json.encode(...))` call from a `df-overseer-*` script (all of
this repo's tools call `print()` exactly once, per `df-overseer-overview.lua`
and its siblings) becomes **exactly one `fragment_type(color, whole_json_string)`
entry** — the coalescing logic only ever *merges* short same-colour writes or
*appends a new fragment*; it never splits a single `add_text` call's string
across fragments, and there is no line-based or size-based splitting anywhere
in this path below the protocol's 64MiB message cap. All buffered fragments
are flushed together by `ServerConnection::connection_ostream::flush_proxy()`
into **one `CoreTextNotification` message** (`msg.add_fragments()` once per
buffered fragment) sent as **one `RPC_REPLY_TEXT`**, which happens once at the
end of command execution (`stream.flush()` in `threadFn`, right before the
final result/failure is sent) unless the tool prints enough separate calls or
enough total volume to trigger an earlier implicit flush — irrelevant to this
repo's one-`print()`-call tools. **Practical answer: for these tools, expect
one `RPC_REPLY_TEXT` message with one fragment containing the entire JSON
document, not a stream of chunks to reassemble.** A general-purpose client
should still loop reading `RPC_REPLY_TEXT` messages until `RPC_REPLY_RESULT`
arrives (per §3) rather than assuming exactly one, since that is a property of
*this repo's* tools, not a protocol guarantee.

### Size limit

64MiB (`RPCMessageHeader::MAX_MESSAGE_SIZE`), enforced on both the server
send path (`RemoteServer.cpp`: "reply too large" → `CR_LINK_FAILURE` instead of
sending) and the client receive path (`RemoteClient.cpp`: rejects a header
claiming `size` outside `[0, MAX_MESSAGE_SIZE]`). No smaller limit was found
anywhere in the text-fragment path specifically — the coalescing code's `128`
constant is only a merge-vs.-new-fragment heuristic, not a truncation point.
At this project's fort sizes (`memory/dfhack-environment.md`: 15-19MB *saves*,
implying JSON payloads many orders of magnitude smaller), 64MiB is not a
practical constraint.

### Colour: confirmed a separate field, and the TRAPS.md finding fully explained

`CoreTextFragment.color` (§3) is an independent, optional field alongside
`text`. The escape-sequence behaviour `docs/TRAPS.md` records
(`dfhack-run` colours output even when stdout is not a tty, and ends with a
bare escape sequence) is **entirely client-side rendering, not a wire-format
property**: `dfhack-run.cpp` constructs its `RemoteClient` with a `Console`
object as the default output (`RemoteClient client(&out)`), and
`Console::add_text` (`Console-posix.cpp`, quoted above) unconditionally calls
`d->print_text(color, text)`, which is the same code path the interactive
in-game console uses to emit ANSI colour codes — it does this regardless of
whether `dfhack-run`'s own stdout is a real terminal, which is exactly the
"colours even when stdout is not a tty" symptom already documented. **A
from-scratch RPC client that just reads `fragments[i].text` and never routes
it through anything resembling `Console::add_text` gets the JSON completely
clean** — no ANSI codes were ever in the `text` field to begin with; they are
synthesized downstream by `dfhack-run`'s specific renderer. This settles the
question in `docs/TRAPS.md`'s favour on the optimistic side: **JSON parsing on
the server is safe with no sanitising needed**, provided the client is written
against the raw protobuf fields (as this report recommends) rather than by
shelling out to `dfhack-run` and scraping its coloured text output (which is
the trap `docs/TRAPS.md` actually describes and this design entirely avoids by
not using `dfhack-run` as a subprocess at all).

---

## 6. Concurrency: one connection cannot batch a suspend window by itself

**This is the one place this report changes what `docs/AGENT-ARCHITECTURE.md`
§14 item 5 currently claims, and it matters enough to say plainly up front:
holding one persistent connection gets you the latency win (no more
SSH+process-spawn+RPC-connect per call), but it does *not* get you the
"batch a cycle's reads into one suspend window" win described in the same
item's third bullet. That needs a small pool of connections, not one.**

Source: `library/RemoteServer.cpp`, `ServerConnection::threadFn`, read in full
(quoted at length in this repo's own earlier research,
`research/2026-09-12-dfhack-capability-checks.md` §3, for the suspend-mutex
mechanism itself; this section is about the **per-connection message loop**
around that mechanism, which that report did not examine).

The loop body, structurally:

```cpp
while (!in_error) {
    readFullBuffer(socket, &header, sizeof(header));   // 1. block for next request
    // ... quit check, size check ...
    readFullBuffer(socket, buf.get(), header.size);    // 2. block for its payload
    // ... find function, parse input ...
    { CoreSuspender suspend; res = fn->execute(stream); }   // 3. do the work (unless SF_DONT_SUSPEND)
    // ... send RPC_REPLY_TEXT / RPC_REPLY_RESULT / RPC_REPLY_FAIL ...   // 4. block for the reply to leave the socket
}   // only then loop back to step 1 for the *same* connection
```

Every one of the four steps runs on the **same single thread**, in order,
for a given connection. The server does not begin reading a second request
on a connection until it has fully replied to the first. So a client that
writes several `CoreRunCommandRequest` messages back-to-back on **one**
socket without waiting for replies (naive pipelining) gains nothing: the
requests simply queue in the OS receive buffer, and the server's one thread
for that connection still drains and answers them one at a time, so their
`CoreSuspender` acquisitions never overlap in wall-clock time. The
`toolCount`-based "every suspender pending at the same instant" mechanism
(quoted in the capability-checks report) genuinely batches concurrent
suspenders **across threads** — and each accepted connection gets its own
OS thread (`ServerConnection::Accepted`: `std::thread{...}.detach()`, one per
`Accept()`). **Concurrency, in the sense §6 of the architecture doc needs, is
a property of how many connections are open, not of how many requests are
in flight on one of them, because at most one request is ever in flight on
any single connection.**

Practical consequence for the MCP server design: keep the one persistent
connection for the latency-dominant case (simple sequential tool calls,
which is most of them, per the architecture doc's own "think-heavy cycles"
observation), and open a **small additional pool** of persistent connections
— sized to the largest number of reads a single cycle actually wants to
batch, not large — specifically for the moments the design wants to fire a
cycle's worth of reads concurrently and land them in one suspend window. This
is a design detail to carry into the server's implementation, not a reason to
abandon persistence: the pool members are themselves persistent connections,
opened once and reused every cycle, so the per-call SSH/spawn/connect cost
this whole effort is trying to remove is still fully removed either way.

---

## 7. Reconnect

No heartbeat, ping, or keepalive RPC method was found in `CoreService`'s
method list (`RemoteTools.cpp`, the full registration block quoted in §3 of
`research/2026-09-12-dfhack-capability-checks.md` and re-checked here) or
anywhere else in `library/`. Detection is purely at the socket level:

- **Dead-socket detection**: any `readFullBuffer`/`Receive()` call returning
  `<= 0` is treated by both client and server as a link failure
  (`CR_LINK_FAILURE` on the client side; the server just sets `in_error` and
  exits its loop, tearing the connection down). A client should treat any
  I/O error on the socket — not just an explicit close — as "reconnect now,"
  since a hung `dfhack-run`-equivalent read is exactly the
  stuck-Lua-script scenario `docs/TRAPS.md` already documents
  (`kill-lua` failing to rescue a runaway script) — a client-side read/connect
  **timeout** is worth setting explicitly rather than trusting TCP's own
  (often very long or absent) failure detection, though no protocol feature
  provides one; it is purely a client-side socket option (e.g. Python
  `socket.settimeout(...)`).
- **Across a DF restart**: the listening socket and every accepted connection
  belong to the DFHack process; when it exits, the OS tears all of them down.
  A client's existing connection sees a close (or a failed read); a fresh
  `connect()` attempt gets `ECONNREFUSED` until DFHack restarts and its
  `ServerMainImpl` reopens the listening socket on the configured port. There
  is no server-side session or state that survives a restart to reconnect
  *into* — every reconnect is a full fresh handshake.
- **What must be re-bound after reconnecting**: for this repo's specific use
  (calling `RunCommand`, id 1, on every connection) — **nothing.** `RunCommand`
  and `BindMethod` are registered identically, at the same fixed ids, in
  every `ServerConnection`'s constructor (`core_service->finalize(...)` runs
  fresh per connection). Only **`BindMethod`-obtained ids for other methods**
  (e.g. a future direct `RemoteFortressReader` call) are connection-scoped —
  they live in that one `ServerConnection` object's `functions` vector — and
  would need to be requested again with a fresh `BindMethod` call after a
  reconnect. Since nothing in this repo's tool surface uses anything but
  `RunCommand`, this caveat does not currently bite, but it is the correct
  answer if the server ever grows a direct-protobuf tool.

---

## 8. Unauthenticated, and exactly what interface it binds

Source: `library/RemoteServer.cpp`'s `ServerMainImpl` constructor (listen
address selection) and `ServerConnection::threadFn`'s per-method IP check,
both read in full.

**No authentication of any kind** exists anywhere in the handshake or the
`RunCommand`/`BindMethod` dispatch path — no token, no password, no TLS, no
client certificate. This is a straightforward confirmation of what §13
already asserts, not a new finding on its own.

**What is a genuinely sharper finding than §13 states**: the bind address and
the per-method access check are **two independent gates**, and the second one
matters more than the design doc currently gives it credit for.

1. **Listen address** (`ServerMainImpl` constructor, quoted in full above in
   §2's neighbouring source but relevant here):
   ```cpp
   bool allow_remote = configJson.get("allow_remote", "false").asBool();
   // ...
   const char* addr = allow_remote ? NULL : "127.0.0.1";
   socket.Listen(addr, port);
   ```
   Default (`remote-server.json` absent, or `allow_remote` unset/false):
   **binds `127.0.0.1` only.** `memory/dfhack-environment.md` already records
   that `remote-server.json` did not exist before DFHack's first run on the
   local install — first run creates it with `allow_remote` normalized to
   `false` (the same constructor rewrites the file with defaults filled in),
   so the out-of-the-box state is loopback-only, confirmed rather than
   assumed.

2. **Per-method IP check**, in `ServerConnection::threadFn`'s dispatch, read
   directly:
   ```cpp
   if (((fn->flags & SF_ALLOW_REMOTE) != SF_ALLOW_REMOTE) &&
       strcmp(socket->GetClientAddr(), "127.0.0.1") != 0)
   {
       stream.printerr("In call to {}: forbidden host: {}\n", fn->name, socket->GetClientAddr());
   }
   ```
   `RunCommand`'s registration (`RemoteTools.cpp`,
   `addMethod("RunCommand", &CoreService::RunCommand, SF_DONT_SUSPEND)`)
   carries **no `SF_ALLOW_REMOTE` flag**. So even in the hypothetical where
   `allow_remote: true` was set (socket bound to all interfaces), a
   non-loopback caller invoking `RunCommand` is rejected by this second,
   independent check — the string comparison happens per-request, regardless
   of the listen address. `BindMethod` **does** carry `SF_ALLOW_REMOTE`
   (`addMethod("BindMethod", &CoreService::BindMethod, SF_DONT_SUSPEND |
   SF_ALLOW_REMOTE)`), so a remote caller could still look up method ids even
   with `allow_remote` on — it just could not use `RunCommand` itself. Worth
   naming precisely: this is an **IP string comparison**, not cryptographic
   authentication (a host that can already reach the loopback-bound socket —
   e.g. anything running as any user on VM 103 itself — is fully trusted by
   this check), so it does not change §13's core argument that anything
   reaching the socket has full scripting control. It does mean a simple
   *misconfiguration* of `allow_remote` would not, by itself, expose
   `RunCommand` to the network — a narrower, more specific claim than "the
   whole interface would be exposed," worth folding back into §13 if that
   section is revised.

---

## 9. Discrepancies between docs and source, named explicitly

Per this task's standing instruction to prefer source over docs and name any
disagreement as a finding: **none of substance were found.**
`hack/docs/docs/dev/Remote.txt`, read in full, matches the pinned-tag source
on every point checked in this report — the handshake bytes, the header
layout, the reserved ids, the built-in method table, and even the informal
description of `RPC_REPLY_FAIL`'s size-field repurposing. This is worth
recording precisely because it is the exception rather than the rule for this
project (`memory/dfhack-environment.md` already flags `RemoteFortressReader`'s
doc as too thin to trust alone, and the capability-checks research found a
real doc/source mismatch elsewhere in the codebase, §10 of that report). The
core remote-protocol doc is an accurate primary source in its own right here,
not merely a lead to verify — a genuinely different situation from most of
what this project has found about DFHack's documentation elsewhere, and worth
noting so a future session does not over-generalize "never trust DFHack docs"
into re-deriving something this doc already gets right.

---

## 10. What could not be verified, and why

- **Whether the VM's installed DFHack build is byte-for-byte identical to the
  pinned-tag source read here.** As in
  `research/2026-09-12-dfhack-capability-checks.md` §7, this task's
  constraints forbid touching VM 103, so this report relies on
  `memory/dfhack-environment.md`'s documented version match
  (DFHack 53.16-r1.1 on both the local Windows install and the VM) rather than
  an independent re-check of the VM's binary.
- **Live behaviour under an actual dead-socket/DF-restart scenario** — the
  reconnect mechanics in §7 are derived from reading the accept/teardown code
  paths, not from killing a live DFHack process and watching a client's
  `recv()` actually return. No live process was started or stopped for this
  report, per its hard constraints.
- **Whether a genuinely large tool output (many MB) ever gets flushed in more
  than one `RPC_REPLY_TEXT` message in practice** — §5's "one fragment per
  `print()` call" claim is a direct reading of the buffering code, but no
  script in this repo currently prints output anywhere near a size that would
  exercise the coalescing thresholds differently; this is inference from
  code, not a measured large-payload trace.
- **Whether `Console::add_text`'s ANSI rendering is the *only* source of the
  bare trailing escape sequence `docs/TRAPS.md` records**, versus some
  additional terminal-reset code specific to `dfhack-run`'s `Console::init`/
  `shutdown` sequence — this report traced the per-fragment colour-to-ANSI
  path far enough to answer the JSON-cleanliness question with confidence,
  but did not read `Console-posix.cpp`/`Console-windows.cpp` end to end for
  every place an escape sequence could originate.
- **Whether other third-party clients named in the doc** (`RemoteClientDF-Net`
  for C#, `dfhackrpc` for Go, `dfhack-remote` for JS/Rust, `dfhack-client-qt`,
  `dfhack-client-java`) are current or abandoned — out of scope for this
  brief (Python only), not checked.

---

## 11. Relevant to

`docs/AGENT-ARCHITECTURE.md` §14 item 5 directly — this report is the
buildable design the item calls for. Specific points worth folding back in on
a future revision of that section:

- The three bullets under item 5 hold, **except the third**: "batch a cycle's
  reads into one suspend window" needs a small connection pool, not the single
  connection the surrounding text implies. Recommend rewording to "hold a
  small, fixed pool of persistent connections: one for ordinary sequential
  calls, plus enough concurrent ones to cover the largest batch of reads a
  single cycle wants to fire at once."
- §13's trust-boundary argument is confirmed and can be stated more precisely:
  `RunCommand` specifically is loopback-gated by its own IP check independent
  of `allow_remote`, which is a stronger and more specific guarantee than "the
  socket is local by default."
- `memory/dfhack-environment.md`'s "Remote interface" section already has the
  right high-level shape (protobuf over TCP, port 5000, `BindMethod`/
  `RunCommand` at ids 0/1) — this report is the detail underneath it and does
  not contradict anything there, only extends it with field numbers, framing
  bytes, and the concurrency/reconnect/output-delivery mechanics that file
  does not cover.
- `docs/TRAPS.md`'s `dfhack-run` colour-escape entry is fully explained rather
  than merely worked around: it is specific to that one client's rendering
  choice, not a wire-protocol property, so a hand-rolled RPC client sidesteps
  it entirely rather than needing to sanitise anything.
