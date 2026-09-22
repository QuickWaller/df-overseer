"""A persistent-connection client for DFHack's RPC socket. This runs this
repo's `df-overseer-*` console commands and returns their printed output --
the second of the MCP server's two missing halves (the other is the
transport itself: no MCP SDK, no HTTP server, no session handling live here,
matching mcp/tools.py and mcp/auth.py's own scope).

**The wire protocol is not re-derived here.** Every framing decision below
is transcribed from `research/2026-09-12-dfhack-rpc-client.md`, written
against the exact installed version (DFHack 53.16-r1.1) by reading its
source at the pinned tag. That report is the citation for every magic
number in this file; this docstring only restates what a reader of this
module specifically needs, not the evidence.

## Why hand-rolled, not `protobuf`

Only five flat proto2 messages are involved, none needing more than a
varint tag, a length-delimited string, or one level of embedded message.
The one existing third-party Python client
(`McArcady/dfhack-client-python`) is unmaintained since 2021, unlicensed,
requires a `protoc` build toolchain and a sibling DFHack source checkout
just to generate its stubs, and has a real header-parsing bug (reads the
`size` field as a 3-byte slice, silently dropping its top byte for any
message at or above 16MiB) -- research doc §4. Hand-rolling ~150 lines
against a settled spec beats depending on that.

## Handshake

Client sends `char[8] magic="DFHack?\\n"` + `int32 version=1` (12 bytes,
little-endian); server replies the same shape with `"DFHack!\\n"` on
success. **A rejection is not a distinct message** -- a bad magic/version
makes the server return without replying at all, so a rejected handshake
and a crashed server and a firewall drop are indistinguishable to the
client: all three show up here as `DFHackConnectionError` from a failed
read of the reply header (research doc §1).

## Framing

Every message after the handshake is `header = int16 id, int16
padding(unused), int32 size` (8 bytes, little-endian, struct format
`<hxxi`), followed by exactly `size` bytes of protobuf-encoded payload --
**except `RPC_REPLY_FAIL`, whose `size` field directly holds the
`command_result` (`CR_*`) code and is followed by no payload at all**
(research doc §2). Reserved reply ids: `RPC_REPLY_RESULT=-1`,
`RPC_REPLY_FAIL=-2`, `RPC_REPLY_TEXT=-3`, `RPC_REQUEST_QUIT=-4`.

## What this module does not do

- **No `BindMethod`.** `RunCommand` is a hardcoded id (1) on every
  connection; this repo's tools never call anything else, so no bind round
  trip is needed (research doc §3).
- **No output sanitising.** Colour is a separate, independent field
  (`CoreTextFragment.color`) that this module never reads; the `text`
  field is never routed through anything resembling DFHack's own ANSI
  renderer, so it is clean JSON as written by the calling Lua script's
  `print()` (research doc §5). `docs/TRAPS.md`'s escape-sequence trap is
  about `dfhack-run`'s own rendering and does not apply to a client built
  this way.
- **No heartbeat/keepalive.** None exists on the wire (research doc §7);
  dead-connection detection here is purely "did the last read or write
  fail", backed by a client-side socket timeout, since DFHack provides no
  protocol-level ping to rely on instead.

## Concurrency: why this module has a pool, not just one connection

**A single connection carries at most one in-flight request.** The
server's per-connection thread reads a request, replies, and only then
reads the next one on that same socket (research doc §6) -- pipelining
several requests onto one socket before reading their replies gains
nothing, since the server drains and answers them one at a time regardless
of how they arrived. Batching a cycle's reads so their `CoreSuspender`
acquisitions land in the same window (`docs/AGENT-ARCHITECTURE.md` §14
item 5's third bullet) is therefore a property of **how many connections
are open**, not of how many requests are in flight on one of them, since
each accepted connection gets its own OS thread on the server side.
`DFHackConnectionPool` exists for exactly this: an explicit, configurable
number of persistent connections, each individually reused across calls
(so the per-call connect/handshake cost is still paid once, not per
call), with `run_many` firing a batch of independent calls across the
pool concurrently.

Pool size is a cap on how much of a cycle's reads can land in one suspend
window, not a knob with a universally correct value -- it belongs in
config (the `size` constructor argument), not hardcoded, since the right
number depends on how many reads a calling cycle actually wants to batch
at once.

## Reconnection

No server-side session survives a dead socket or a DFHack restart --
every reconnect is a fresh TCP connect plus a fresh handshake (research
doc §7). A pooled connection that fails mid-request is marked closed and
is transparently reconnected the next time something tries to acquire it,
so **a DFHack restart does not permanently poison the pool**: calls made
while DFHack is down keep failing with `DFHackConnectionError` (there is
nothing else they can do), but the pool self-heals as soon as DFHack is
back up, with no explicit "reset the pool" call needed.
"""

from __future__ import annotations

import asyncio
import logging
import struct
from typing import List, Optional, Sequence, Tuple

_logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Wire constants -- transcribed from research/2026-09-12-dfhack-rpc-client.md
# §1-3. Do not change any of these without re-reading that report; they are
# not tunable, they are the protocol.
# --------------------------------------------------------------------------

_MAGIC_REQUEST = b"DFHack?\n"
_MAGIC_REPLY = b"DFHack!\n"
_PROTOCOL_VERSION = 1
_HANDSHAKE_FORMAT = "<8si"  # char[8] magic, int32 version; no padding needed
_HANDSHAKE_SIZE = struct.calcsize(_HANDSHAKE_FORMAT)

_HEADER_FORMAT = "<hxxi"  # int16 id, 2 bytes unused padding, int32 size
_HEADER_SIZE = struct.calcsize(_HEADER_FORMAT)

RPC_REPLY_RESULT = -1
RPC_REPLY_FAIL = -2
RPC_REPLY_TEXT = -3
RPC_REQUEST_QUIT = -4

METHOD_BIND_METHOD = 0
METHOD_RUN_COMMAND = 1

MAX_MESSAGE_SIZE = 64 * 1024 * 1024  # 64MiB, enforced both directions on the wire

# CoreErrorNotification.ErrorCode, from CoreProtocol.proto at the pinned tag.
# Only used to make a DFHackCallError message readable; the numeric code is
# always what callers should branch on, never this name.
_COMMAND_RESULT_NAMES = {
    0: "CR_OK",
    1: "CR_FAILURE",
    2: "CR_WRONG_USAGE",
    3: "CR_NOT_FOUND",
    -1: "CR_NOT_IMPLEMENTED",
    -2: "CR_WOULD_BREAK",
    -3: "CR_LINK_FAILURE",
}

_DEFAULT_HOST = "127.0.0.1"  # RunCommand is loopback-gated regardless of
# allow_remote (research doc §8) -- a non-default host is this client's own
# business (e.g. an SSH tunnel's local end), never a claim about a remote
# DFHack accepting RunCommand directly.
_DEFAULT_PORT = 5000
_DEFAULT_TIMEOUT = 10.0


class DFHackProtocolError(Exception):
    """The peer sent bytes that do not parse as this protocol -- a reply id
    outside the four reserved values, a length-delimited field's declared
    size running past the buffer, or a handshake reply of the right length
    but wrong content. Distinct from DFHackConnectionError (an I/O failure)
    because this means "we are talking to something, but it is not
    DFHack" rather than "we could not talk to it at all"."""


class DFHackConnectionError(Exception):
    """The socket failed, or the handshake did not complete. Covers
    connection-refused (DFHack is down), a dropped/reset socket mid-request,
    a read/write timeout, and a rejected handshake -- research doc §1 notes
    a rejected handshake is *not* a distinct wire message, so it necessarily
    lands here rather than as a more specific error. A connection that
    raises this is left closed; a pool transparently reconnects on next
    use (see module docstring)."""


class DFHackCallError(Exception):
    """RunCommand completed but returned RPC_REPLY_FAIL. Carries the raw
    `command_result` (`CR_*`) code in `.command_result` -- branch on that
    field, not on the message text, which only exists for readability."""

    def __init__(self, command_result: int) -> None:
        self.command_result = command_result
        name = _COMMAND_RESULT_NAMES.get(command_result, "unknown code")
        super().__init__(
            f"DFHack RunCommand failed with command_result={command_result} ({name})"
        )


# --------------------------------------------------------------------------
# Minimal protobuf wire-format codec, scoped to exactly the shapes in
# research doc §3/§4: varint, and length-delimited string/embedded-message.
# Not a general protobuf implementation -- it is a lenient reader (never
# validates a `required` field it doesn't read) and a writer for exactly
# CoreRunCommandRequest's two fields.
# --------------------------------------------------------------------------

_WIRE_TYPE_VARINT = 0
_WIRE_TYPE_LENGTH_DELIMITED = 2


def _encode_varint(value: int) -> bytes:
    if value < 0:
        raise ValueError(f"varint encoding here only supports non-negative values, got {value}")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _decode_varint(data: bytes, pos: int) -> Tuple[int, int]:
    result = 0
    shift = 0
    while True:
        if pos >= len(data):
            raise DFHackProtocolError("varint runs past the end of the message")
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7
        if shift > 63:
            raise DFHackProtocolError("varint longer than 64 bits")


def _encode_tag(field_number: int, wire_type: int) -> bytes:
    return _encode_varint((field_number << 3) | wire_type)


def _encode_length_delimited_field(field_number: int, raw: bytes) -> bytes:
    return _encode_tag(field_number, _WIRE_TYPE_LENGTH_DELIMITED) + _encode_varint(len(raw)) + raw


def _encode_run_command_request(command: str, arguments: Sequence[str]) -> bytes:
    """CoreRunCommandRequest{required string command = 1; repeated string
    arguments = 2;} -- research doc §3, verbatim field numbers."""
    out = bytearray()
    out += _encode_length_delimited_field(1, command.encode("utf-8"))
    for argument in arguments:
        out += _encode_length_delimited_field(2, argument.encode("utf-8"))
    return bytes(out)


def _iter_fields(data: bytes):
    """Yield (field_number, wire_type, value) for every top-level field in
    `data`. `value` is an int for a varint field, raw bytes for a
    length-delimited one. Lenient by design (research doc §4): this never
    needs to reject a message for a missing `required` field it isn't
    going to read anyway, since every message this client decodes is
    trusted local DFHack output, not untrusted input to validate strictly.
    Raises DFHackProtocolError for a wire type this client has no message
    that uses (there is none in CoreTextNotification/EmptyMessage today;
    if DFHack ever adds one, failing loudly here is correct)."""
    pos = 0
    n = len(data)
    while pos < n:
        tag, pos = _decode_varint(data, pos)
        field_number = tag >> 3
        wire_type = tag & 0x7
        if wire_type == _WIRE_TYPE_VARINT:
            value, pos = _decode_varint(data, pos)
            yield field_number, wire_type, value
        elif wire_type == _WIRE_TYPE_LENGTH_DELIMITED:
            length, pos = _decode_varint(data, pos)
            if pos + length > n:
                raise DFHackProtocolError(
                    f"field {field_number}'s declared length {length} runs past the message"
                )
            yield field_number, wire_type, data[pos:pos + length]
            pos += length
        else:
            raise DFHackProtocolError(
                f"field {field_number} uses wire type {wire_type}, which this client "
                "has no message shape that needs -- see module docstring"
            )


def _decode_dfhack_text(value: bytes, command: Optional[str]) -> str:
    """Decode one text field DFHack sent us.

    Backstop for handoffs/2026-09-22-loop-game-text-encoding.md: DF stores
    game text (procedurally generated names, job/building/zone names,
    announcement text, ...) in CP437, and the Lua side now converts every
    known game-text call site to UTF-8 at the source with `dfhack.df2utf`
    (scripts/dfhack/df-overseer-textutil.lua) before it is ever printed.
    This is the backstop for a call site that is missed (a future tool that
    forgets the helper, or an accessor this audit didn't find): if the
    bytes are not valid UTF-8, decode them as CP437 instead of raising, and
    log at WARNING which command produced it, so the gap is visible and
    fixable rather than silently papered over. Deliberately not
    `errors="replace"` -- that would turn the offending character into
    U+FFFD and lose the name outright; CP437 recovers the actual text (at
    worst, DF's own encoding was not CP437 for this string, in which case
    the recovered text may itself be wrong, but it is never worse than a
    thrown exception that drops the whole tool response)."""
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as exc:
        _logger.warning(
            "dfhack command %r sent text that is not valid UTF-8 (%s); "
            "decoding as CP437 instead of failing -- this means a game-text "
            "call site in scripts/dfhack/ was missed by the df2utf "
            "conversion pass and should be found and fixed",
            command, exc,
        )
        return value.decode("cp437")


def _decode_text_fragment_text(data: bytes, command: Optional[str] = None) -> Optional[str]:
    """CoreTextFragment{required string text = 1; optional Color color =
    2;} -- only `text` is read; `color` is intentionally ignored (research
    doc §5: it is an independent field, never embedded in the text, so
    ignoring it is what makes the result clean JSON with no ANSI to
    strip)."""
    text: Optional[str] = None
    for field_number, wire_type, value in _iter_fields(data):
        if field_number == 1 and wire_type == _WIRE_TYPE_LENGTH_DELIMITED:
            text = _decode_dfhack_text(value, command)
        # field 2 (color) deliberately ignored -- see docstring.
    return text


def _decode_text_notification(data: bytes, command: Optional[str] = None) -> List[str]:
    """CoreTextNotification{repeated CoreTextFragment fragments = 1;} ->
    the text of every fragment, in wire order. For this repo's tools,
    research doc §5 expects exactly one fragment holding an entire
    print()'d JSON document, but this loops over every fragment
    regardless, since that is a property of these specific tools, not a
    protocol guarantee a general client should assume."""
    texts: List[str] = []
    for field_number, wire_type, value in _iter_fields(data):
        if field_number == 1 and wire_type == _WIRE_TYPE_LENGTH_DELIMITED:
            text = _decode_text_fragment_text(value, command)
            if text is not None:
                texts.append(text)
    return texts


# --------------------------------------------------------------------------
# One connection
# --------------------------------------------------------------------------


class DFHackConnection:
    """One persistent socket to a DFHack RPC server. Carries at most one
    in-flight `run_command` at a time -- not a self-imposed limit, a hard
    protocol property (research doc §6): call `run_command` concurrently
    from two tasks on the same connection and the second simply waits for
    the lock below, it does not get a second request-in-flight.

    Not meant to be used directly by most callers -- see
    `DFHackConnectionPool`, which is what makes several of these usable
    concurrently. A bare `DFHackConnection` is still complete and
    independently useful for the simple sequential case (open once, reuse
    for many calls), matching the "hold one persistent connection" half of
    the design (research doc §6's own recommendation for the non-batched
    case).
    """

    def __init__(
        self,
        host: str = _DEFAULT_HOST,
        port: int = _DEFAULT_PORT,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._lock = asyncio.Lock()
        self._closed = True

    @property
    def is_closed(self) -> bool:
        return self._closed

    async def connect(self) -> None:
        """Open the TCP connection and complete the handshake. Safe to call
        again on an already-used object (e.g. a pool reconnecting a dead
        connection in place) -- any previous socket is force-closed first."""
        if not self._closed:
            await self._force_close()
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=self._timeout,
            )
        except (OSError, asyncio.TimeoutError) as exc:
            raise DFHackConnectionError(
                f"could not connect to DFHack at {self._host}:{self._port}: {exc}"
            ) from exc
        self._closed = False
        try:
            await self._handshake()
        except Exception:
            await self._force_close()
            raise

    async def _handshake(self) -> None:
        assert self._writer is not None
        self._writer.write(struct.pack(_HANDSHAKE_FORMAT, _MAGIC_REQUEST, _PROTOCOL_VERSION))
        await self._drain()
        try:
            reply = await self._read_exactly(_HANDSHAKE_SIZE)
        except (OSError, asyncio.IncompleteReadError, asyncio.TimeoutError) as exc:
            # research doc §1: a rejected handshake is not a distinct wire
            # message -- this is exactly what "invalid magic/version" looks
            # like on the wire, indistinguishable from any other I/O failure.
            raise DFHackConnectionError(
                "could not read handshake reply (not a compatible DFHack, "
                "or the connection dropped before replying)"
            ) from exc
        magic, version = struct.unpack(_HANDSHAKE_FORMAT, reply)
        if magic != _MAGIC_REPLY or version != _PROTOCOL_VERSION:
            raise DFHackProtocolError(
                f"unexpected handshake reply: magic={magic!r} version={version}"
            )

    async def run_command(self, command: str, arguments: Optional[Sequence[str]] = None) -> str:
        """Run one df-overseer-* console command over RunCommand (method id
        1, no BindMethod needed -- research doc §3) and return its printed
        text output, concatenated in wire order.

        Raises DFHackCallError if DFHack itself reports the command failed
        (RPC_REPLY_FAIL). Raises DFHackConnectionError for any I/O failure;
        after that, this connection is closed and must be reconnected (or
        discarded) before reuse -- it will not repair itself.
        """
        if self._closed or self._writer is None or self._reader is None:
            raise DFHackConnectionError("run_command called on a closed connection")

        arguments = list(arguments or [])
        payload = _encode_run_command_request(command, arguments)
        header = struct.pack(_HEADER_FORMAT, METHOD_RUN_COMMAND, len(payload))

        async with self._lock:
            try:
                self._writer.write(header + payload)
                await self._drain()

                fragments: List[str] = []
                while True:
                    reply_header = await self._read_exactly(_HEADER_SIZE)
                    reply_id, reply_size = struct.unpack(_HEADER_FORMAT, reply_header)

                    if reply_id == RPC_REPLY_TEXT:
                        body = await self._read_exactly(reply_size)
                        fragments.extend(_decode_text_notification(body, command))
                    elif reply_id == RPC_REPLY_RESULT:
                        await self._read_exactly(reply_size)  # EmptyMessage body, discarded
                        return "".join(fragments)
                    elif reply_id == RPC_REPLY_FAIL:
                        # research doc §2: `reply_size` IS the command_result
                        # here, not a byte count -- no body follows, do not
                        # try to read one.
                        raise DFHackCallError(reply_size)
                    else:
                        raise DFHackProtocolError(f"unexpected reply id {reply_id}")
            except (OSError, asyncio.IncompleteReadError, asyncio.TimeoutError) as exc:
                await self._force_close()
                raise DFHackConnectionError(f"connection failed mid-request: {exc}") from exc

    async def close(self) -> None:
        """Send RPC_REQUEST_QUIT and close the socket. Per research doc §2,
        the server expects no payload and sends no reply to this -- the
        client closes immediately after writing it. Safe to call on an
        already-closed connection (a no-op)."""
        if self._closed:
            return
        try:
            assert self._writer is not None
            self._writer.write(struct.pack(_HEADER_FORMAT, RPC_REQUEST_QUIT, 0))
            await self._drain()
        except (OSError, asyncio.TimeoutError):
            pass  # already going away; nothing left to negotiate
        await self._force_close()

    async def _read_exactly(self, n: int) -> bytes:
        assert self._reader is not None
        return await asyncio.wait_for(self._reader.readexactly(n), timeout=self._timeout)

    async def _drain(self) -> None:
        assert self._writer is not None
        await asyncio.wait_for(self._writer.drain(), timeout=self._timeout)

    async def _force_close(self) -> None:
        self._closed = True
        writer, self._writer = self._writer, None
        self._reader = None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass


# --------------------------------------------------------------------------
# A small pool
# --------------------------------------------------------------------------


class DFHackConnectionPool:
    """A small, fixed-size pool of persistent DFHackConnections.

    Exists because one connection cannot carry more than one in-flight
    request (module docstring, research doc §6): batching N reads into one
    DFHack suspend window needs N connections open at once, each on its
    own OS thread server-side, not N requests pipelined on one socket.
    `size` is the cap on how much of a cycle's reads this pool can land in
    one window -- pass it explicitly rather than relying on a default that
    happens to fit today's tool count.

    A dead connection is not fatal to the pool: `run_command`/`run_many`
    reconnect a closed connection transparently the next time it would be
    used, so a DFHack restart degrades to "every call fails while it's
    down" and then self-heals, rather than "the pool is now permanently
    full of dead sockets" (the failure mode the handoff brief named
    explicitly).
    """

    def __init__(
        self,
        host: str = _DEFAULT_HOST,
        port: int = _DEFAULT_PORT,
        size: int = 4,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        if size < 1:
            raise ValueError(f"pool size must be at least 1, got {size}")
        self._host = host
        self._port = port
        self._size = size
        self._timeout = timeout
        self._available: "asyncio.Queue[DFHackConnection]" = asyncio.Queue()
        self._started = False

    @property
    def size(self) -> int:
        return self._size

    async def start(self) -> None:
        """Open all `size` connections up front. Call once before use.
        Raises DFHackConnectionError (without leaving the pool half-open in
        a way a caller could still use) if any connection fails -- start
        is meant to be an explicit, checkable step, not something that
        succeeds partially and fails mysteriously later."""
        if self._started:
            return
        opened: List[DFHackConnection] = []
        try:
            for _ in range(self._size):
                conn = DFHackConnection(self._host, self._port, timeout=self._timeout)
                await conn.connect()
                opened.append(conn)
        except DFHackConnectionError:
            for conn in opened:
                await conn.close()
            raise
        for conn in opened:
            self._available.put_nowait(conn)
        self._started = True

    async def _acquire(self) -> DFHackConnection:
        conn = await self._available.get()
        if conn.is_closed:
            try:
                await conn.connect()
            except DFHackConnectionError:
                # Put it back closed so the pool's total count never shrinks
                # -- the next acquire (this call's or another's) gets to try
                # again once DFHack is back. See class docstring.
                self._available.put_nowait(conn)
                raise
        return conn

    def _release(self, conn: DFHackConnection) -> None:
        self._available.put_nowait(conn)

    async def run_command(self, command: str, arguments: Optional[Sequence[str]] = None) -> str:
        """Run one command on whichever pooled connection is free next,
        blocking if all `size` are currently busy. Use `run_many` instead
        when several independent calls should be issued in the same
        suspend window."""
        if not self._started:
            raise DFHackConnectionError("pool.start() was not called")
        conn = await self._acquire()
        try:
            return await conn.run_command(command, arguments)
        finally:
            self._release(conn)

    async def run_many(
        self, calls: Sequence[Tuple[str, Sequence[str]]]
    ) -> List[str]:
        """Run several independent (command, arguments) calls concurrently,
        each on its own pooled connection, up to `size` at once -- the
        batched-reads pattern research doc §6 requires a pool for. If more
        calls are given than there are pool slots, the extra calls queue
        for a connection to free up rather than failing; only the first
        `size` of them can actually land in the same suspend window.

        Returns outputs in the same order as `calls`. A single call's
        DFHackCallError/DFHackConnectionError propagates (via
        asyncio.gather's default behaviour) rather than being swallowed --
        a caller that wants partial results on partial failure should
        catch per-call, not rely on this method to do it silently."""
        if not self._started:
            raise DFHackConnectionError("pool.start() was not called")
        return list(
            await asyncio.gather(
                *(self.run_command(command, arguments) for command, arguments in calls)
            )
        )

    async def close(self) -> None:
        """Close every idle connection currently sitting in the pool.
        Anything checked out mid-call at the moment this is called is not
        closed here -- callers should let in-flight calls finish (or
        cancel their own tasks) before calling this, the same way closing
        a normal connection pool elsewhere would work."""
        while not self._available.empty():
            conn = self._available.get_nowait()
            await conn.close()
        self._started = False
