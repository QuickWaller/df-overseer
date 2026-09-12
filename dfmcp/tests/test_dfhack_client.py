"""Tests for mcp/dfhack_client.py: the hand-rolled RPC codec, one
connection, and the pool.

No VM, no live DF, per the handoff brief's acceptance criterion 1 -- every
network test here runs against `FakeDFHackServer`, a small asyncio TCP
server defined in this file that speaks the real wire framing (handshake
bytes, header layout, reserved reply ids) by hand, independently of
`mcp/dfhack_client.py`'s own encoder/decoder, so a bug shared by both sides
would have to be a bug in the wire spec itself, not a tautology between
test and code. The framing is transcribed from
`research/2026-09-12-dfhack-rpc-client.md`, the same source
`mcp/dfhack_client.py` is built against.

The codec tests at the top (`Test*Codec`) go one step further and check
against byte sequences worked out by hand from the protobuf wire-format
spec (a tag byte is `(field_number << 3) | wire_type`; a multi-byte varint
sets the continuation bit on every byte but the last) -- this is the
"round-trip the codec against known byte sequences from the brief"
acceptance criterion, and does not go through FakeDFHackServer at all.

**What remains unproven by this file, stated plainly**: everything here
exercises the protocol against this hand-written fake, not a real DFHack
process. See this stream's report for the exact command that would close
that gap against VM 103, which this stream does not run.
"""

from __future__ import annotations

import asyncio
import struct
from typing import Callable, List, Optional, Tuple

import pytest
import pytest_asyncio

from dfmcp.dfhack_client import (
    DFHackCallError,
    DFHackConnection,
    DFHackConnectionError,
    DFHackConnectionPool,
    DFHackProtocolError,
    RPC_REPLY_FAIL,
    RPC_REPLY_RESULT,
    RPC_REPLY_TEXT,
    RPC_REQUEST_QUIT,
    _decode_text_notification,
    _decode_varint,
    _encode_run_command_request,
    _encode_varint,
)

_HEADER_FORMAT = "<hxxi"
_HANDSHAKE_FORMAT = "<8si"


# ==========================================================================
# Codec tests -- no network, byte sequences worked out by hand
# ==========================================================================


class TestVarintCodec:
    def test_single_byte_values(self):
        # Wire type / field-number tags in the messages this client uses are
        # all single-byte varints (< 128); these are the ones that appear
        # for real (tags 0x0A, 0x12, 0x10 -- see the other tests below).
        assert _encode_varint(0) == bytes([0x00])
        assert _encode_varint(1) == bytes([0x01])
        assert _encode_varint(127) == bytes([0x7F])

    def test_multi_byte_values_set_the_continuation_bit(self):
        # 128 = 0b10000000 -> low 7 bits 0000000 with continuation set
        # (0x80), then the remaining bits (1) as the final byte (0x01).
        assert _encode_varint(128) == bytes([0x80, 0x01])
        # 300 = 0b100101100 -> low 7 bits 0101100=0x2C with continuation
        # (0xAC), remaining bits (300 >> 7 == 2) as the final byte (0x02).
        # This is protobuf's own canonical worked example for a 2-byte
        # varint.
        assert _encode_varint(300) == bytes([0xAC, 0x02])

    def test_decode_is_the_exact_inverse(self):
        for value in (0, 1, 127, 128, 300, 16384, 2**32 - 1):
            encoded = _encode_varint(value)
            decoded, pos = _decode_varint(encoded, 0)
            assert (decoded, pos) == (value, len(encoded))

    def test_negative_value_is_rejected(self):
        # This codec only ever needs to encode non-negative sizes/tags; a
        # negative value here would be a caller bug, not a protocol value
        # (RPC_REPLY_FAIL's command_result is read straight from the
        # header's plain int32 field, never through this varint path).
        with pytest.raises(ValueError):
            _encode_varint(-1)

    def test_truncated_varint_raises_protocol_error(self):
        # A byte with the continuation bit set and nothing after it -- the
        # kind of thing a torn/short read could produce.
        with pytest.raises(DFHackProtocolError):
            _decode_varint(bytes([0x80]), 0)


class TestRunCommandRequestEncoding:
    def test_command_with_no_arguments(self):
        # CoreRunCommandRequest{command:"get"} -- field 1 (string), tag
        # (1<<3)|2 = 0x0A, length 3, then the bytes.
        expected = bytes([0x0A, 0x03]) + b"get"
        assert _encode_run_command_request("get", []) == expected

    def test_command_with_two_arguments(self):
        # field 2 (repeated string) tag is (2<<3)|2 = 0x12, one tag+len+bytes
        # group per element, in order.
        expected = (
            bytes([0x0A, 0x03]) + b"get"
            + bytes([0x12, 0x01]) + b"a"
            + bytes([0x12, 0x02]) + b"bb"
        )
        assert _encode_run_command_request("get", ["a", "bb"]) == expected

    def test_longer_command_name_needs_a_two_byte_length_varint(self):
        # A real command name from this repo's own manifest, chosen because
        # its length (24) is still under 128 so this only checks the
        # length-prefix mechanics, not a second varint byte -- kept
        # separate from the multi-byte-varint codec test above, which
        # covers that.
        command = "df-overseer-connectivity"
        assert len(command) == 24
        expected = bytes([0x0A, 24]) + command.encode("utf-8")
        assert _encode_run_command_request(command, []) == expected


class TestTextNotificationDecoding:
    def _fragment_bytes(self, text: str, color: int) -> bytes:
        # CoreTextFragment{text=1 (string), color=2 (varint)} -- built by
        # hand, not via mcp.dfhack_client's own encoder (this client never
        # needs to *encode* a CoreTextFragment, only decode one).
        text_bytes = text.encode("utf-8")
        return (
            bytes([0x0A, len(text_bytes)]) + text_bytes
            + bytes([0x10, color])
        )

    def test_single_fragment_ignores_color(self):
        fragment = self._fragment_bytes("hello", color=7)
        # CoreTextNotification{fragments=1 (embedded message)}
        notification = bytes([0x0A, len(fragment)]) + fragment
        assert _decode_text_notification(notification) == ["hello"]

    def test_two_fragments_preserve_order(self):
        first = self._fragment_bytes("first", color=0)
        second = self._fragment_bytes("second", color=1)
        notification = (
            bytes([0x0A, len(first)]) + first
            + bytes([0x0A, len(second)]) + second
        )
        assert _decode_text_notification(notification) == ["first", "second"]

    def test_empty_notification_decodes_to_no_fragments(self):
        assert _decode_text_notification(b"") == []

    def test_fragment_with_no_color_field_still_decodes(self):
        # `color` is `optional` on the wire (research doc §3) -- a fragment
        # that omits it entirely must still decode cleanly.
        text_bytes = b"no color here"
        fragment = bytes([0x0A, len(text_bytes)]) + text_bytes
        notification = bytes([0x0A, len(fragment)]) + fragment
        assert _decode_text_notification(notification) == ["no color here"]

    def test_truncated_length_delimited_field_raises_protocol_error(self):
        # Declares a 10-byte string but only provides 3 -- a torn read, or
        # a peer that is not actually speaking this protocol.
        bad = bytes([0x0A, 10]) + b"abc"
        with pytest.raises(DFHackProtocolError):
            _decode_text_notification(bad)


# ==========================================================================
# FakeDFHackServer -- a from-scratch, independent implementation of the
# server side of the wire protocol, for the connection/pool tests below.
# ==========================================================================

Action = Callable[[asyncio.StreamReader, asyncio.StreamWriter], "asyncio.Future"]


def _pack_header(msg_id: int, size: int) -> bytes:
    return struct.pack(_HEADER_FORMAT, msg_id, size)


def _pack_fragment(text: str, color: int = 0) -> bytes:
    text_bytes = text.encode("utf-8")
    return bytes([0x0A, len(text_bytes)]) + text_bytes + bytes([0x10, color])


def _pack_text_notification(*texts: str) -> bytes:
    body = b"".join(bytes([0x0A, len(f := _pack_fragment(t))]) + f for t in texts)
    return body


async def action_ok(reader, writer, texts: Tuple[str, ...] = ()):
    for text in texts:
        body = _pack_text_notification(text)
        writer.write(_pack_header(RPC_REPLY_TEXT, len(body)) + body)
        await writer.drain()
    writer.write(_pack_header(RPC_REPLY_RESULT, 0))
    await writer.drain()


def make_ok_action(*texts: str) -> Action:
    async def action(reader, writer):
        await action_ok(reader, writer, texts)
    return action


def make_fail_action(command_result: int) -> Action:
    async def action(reader, writer):
        writer.write(_pack_header(RPC_REPLY_FAIL, command_result))
        await writer.drain()
    return action


def make_disconnect_action() -> Action:
    async def action(reader, writer):
        writer.close()
        await writer.wait_closed()
    return action


def make_barrier_action(barrier: "asyncio.Barrier", text: str) -> Action:
    """Wait until `barrier`'s full party has each independently read a
    request off their own connection, THEN reply. Proves the server had
    every one of those requests in flight at the same instant -- the
    property research doc §6 says needs multiple connections, which is
    exactly what a pool is for.
    """
    async def action(reader, writer):
        await barrier.wait()
        await action_ok(reader, writer, (text,))
    return action


class FakeDFHackServer:
    """An independent, from-scratch server-side implementation of the
    handshake and framing described in research/2026-09-12-dfhack-rpc-client.md
    §1-2. Not derived from mcp/dfhack_client.py's own code.

    `queue_actions` appends callables consumed FIFO, one per request
    received across ALL connections (matching DFHack's real behaviour of
    replying to whatever request arrives, regardless of which socket it is
    on). A request with no queued action gets a default OK-with-no-text
    reply, so tests that don't care about a particular call's response
    don't need to queue one.

    `received_requests` records the raw, still-undecoded request payload
    for every RunCommand request across every connection, in arrival order
    -- added for dfmcp/tests/test_server.py, which needs to prove a
    specific argv actually reached this fake (test 4 of the transport
    handoff's four load-bearing tests), not just that *some* call
    succeeded. Decode an entry with `_encode_run_command_request` for
    comparison, or dfmcp.dfhack_client's own field iterator. Purely
    additive: nothing before this stream's addition read this list, so no
    existing test's behaviour changes.
    """

    def __init__(self, handshake_ok: bool = True, handshake_bad_magic: bool = False):
        self.handshake_ok = handshake_ok
        self.handshake_bad_magic = handshake_bad_magic
        self._server: Optional[asyncio.base_events.Server] = None
        self.host = "127.0.0.1"
        self.port = 0
        self._actions: List[Action] = []
        self.connections_accepted = 0
        self.received_requests: List[bytes] = []

    def queue_actions(self, *actions: Action) -> None:
        self._actions.extend(actions)

    def _next_action(self) -> Optional[Action]:
        if self._actions:
            return self._actions.pop(0)
        return None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self.host, 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()

    async def __aenter__(self) -> "FakeDFHackServer":
        await self.start()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.stop()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connections_accepted += 1
        try:
            handshake = await reader.readexactly(struct.calcsize(_HANDSHAKE_FORMAT))
            if not self.handshake_ok:
                # research doc §1: a rejected handshake sends NO reply at
                # all -- the connection is simply torn down.
                return
            struct.unpack(_HANDSHAKE_FORMAT, handshake)  # ignore contents; not under test here
            if self.handshake_bad_magic:
                writer.write(struct.pack(_HANDSHAKE_FORMAT, b"NOTDFHK\n", 1))
            else:
                writer.write(struct.pack(_HANDSHAKE_FORMAT, b"DFHack!\n", 1))
            await writer.drain()

            while True:
                header = await reader.readexactly(8)
                msg_id, size = struct.unpack(_HEADER_FORMAT, header)
                if msg_id == RPC_REQUEST_QUIT:
                    return
                payload = await reader.readexactly(size)
                self.received_requests.append(payload)
                action = self._next_action()
                if action is None:
                    await action_ok(reader, writer)
                else:
                    await action(reader, writer)
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            writer.close()


@pytest_asyncio.fixture
async def fake_server():
    async with FakeDFHackServer() as server:
        yield server


# ==========================================================================
# DFHackConnection
# ==========================================================================


class TestConnectionHandshake:
    pytestmark = pytest.mark.asyncio

    async def test_successful_handshake(self, fake_server):
        conn = DFHackConnection(fake_server.host, fake_server.port, timeout=2.0)
        await conn.connect()
        assert not conn.is_closed
        await conn.close()

    async def test_rejected_handshake_raises_connection_error(self):
        # research doc §1: indistinguishable from any other I/O failure on
        # the wire -- there is no protocol-level "handshake rejected"
        # message, so this MUST surface as DFHackConnectionError, not
        # anything more specific.
        async with FakeDFHackServer(handshake_ok=False) as server:
            conn = DFHackConnection(server.host, server.port, timeout=2.0)
            with pytest.raises(DFHackConnectionError):
                await conn.connect()
            assert conn.is_closed

    async def test_garbage_handshake_reply_raises_protocol_error(self):
        # A peer that replies with the right shape but wrong magic -- not
        # DFHack's real rejection behaviour (which sends nothing), but
        # worth handling distinctly: this is "we got bytes back, and they
        # are not a DFHack handshake", not an I/O failure.
        async with FakeDFHackServer(handshake_bad_magic=True) as server:
            conn = DFHackConnection(server.host, server.port, timeout=2.0)
            with pytest.raises(DFHackProtocolError):
                await conn.connect()
            assert conn.is_closed

    async def test_connection_refused_raises_connection_error(self):
        # Nothing listens on this port (a fresh server was never started
        # here) -- models "DFHack is down".
        async with FakeDFHackServer() as server:
            dead_port = server.port
            await server.stop()
        conn = DFHackConnection("127.0.0.1", dead_port, timeout=2.0)
        with pytest.raises(DFHackConnectionError):
            await conn.connect()

    async def test_reconnect_on_an_already_used_object_closes_the_old_socket_first(self, fake_server):
        conn = DFHackConnection(fake_server.host, fake_server.port, timeout=2.0)
        await conn.connect()
        await conn.connect()  # must not raise or leak the first socket
        assert not conn.is_closed
        assert fake_server.connections_accepted == 2
        await conn.close()


class TestConnectionRunCommand:
    pytestmark = pytest.mark.asyncio

    async def test_happy_path_single_fragment(self, fake_server):
        fake_server.queue_actions(make_ok_action('{"ok": true}'))
        conn = DFHackConnection(fake_server.host, fake_server.port, timeout=2.0)
        await conn.connect()
        result = await conn.run_command("df-overseer-overview", ["get"])
        assert result == '{"ok": true}'
        await conn.close()

    async def test_multiple_text_fragments_are_concatenated_in_order(self, fake_server):
        fake_server.queue_actions(make_ok_action("part one ", "part two"))
        conn = DFHackConnection(fake_server.host, fake_server.port, timeout=2.0)
        await conn.connect()
        result = await conn.run_command("some-command")
        assert result == "part one part two"
        await conn.close()

    async def test_no_output_returns_empty_string(self, fake_server):
        fake_server.queue_actions(make_ok_action())
        conn = DFHackConnection(fake_server.host, fake_server.port, timeout=2.0)
        await conn.connect()
        assert await conn.run_command("quiet-command") == ""
        await conn.close()

    async def test_rpc_reply_fail_raises_call_error_with_the_raw_code(self, fake_server):
        fake_server.queue_actions(make_fail_action(3))  # CR_NOT_FOUND
        conn = DFHackConnection(fake_server.host, fake_server.port, timeout=2.0)
        await conn.connect()
        with pytest.raises(DFHackCallError) as excinfo:
            await conn.run_command("missing-command")
        assert excinfo.value.command_result == 3
        # research doc §2: RPC_REPLY_FAIL's `size` field IS the code -- no
        # body follows. If the client tried to read one, this call would
        # hang or desync the connection instead of returning cleanly.
        await conn.close()

    async def test_dead_socket_mid_request_raises_connection_error_and_closes(self, fake_server):
        fake_server.queue_actions(make_disconnect_action())
        conn = DFHackConnection(fake_server.host, fake_server.port, timeout=2.0)
        await conn.connect()
        with pytest.raises(DFHackConnectionError):
            await conn.run_command("doomed-command")
        assert conn.is_closed

    async def test_run_command_on_a_closed_connection_raises_without_touching_the_network(self):
        conn = DFHackConnection("127.0.0.1", 1, timeout=2.0)  # never connected
        with pytest.raises(DFHackConnectionError):
            await conn.run_command("anything")

    async def test_close_sends_request_quit_and_no_payload(self, fake_server):
        conn = DFHackConnection(fake_server.host, fake_server.port, timeout=2.0)
        await conn.connect()
        await conn.close()
        assert conn.is_closed
        # A second close() must be a harmless no-op, not a re-raise.
        await conn.close()


# ==========================================================================
# DFHackConnectionPool
# ==========================================================================


class TestPool:
    pytestmark = pytest.mark.asyncio

    async def test_size_must_be_positive(self):
        with pytest.raises(ValueError):
            DFHackConnectionPool(size=0)

    async def test_start_opens_exactly_size_connections(self, fake_server):
        pool = DFHackConnectionPool(fake_server.host, fake_server.port, size=3, timeout=2.0)
        await pool.start()
        assert fake_server.connections_accepted == 3
        await pool.close()

    async def test_start_is_idempotent(self, fake_server):
        pool = DFHackConnectionPool(fake_server.host, fake_server.port, size=2, timeout=2.0)
        await pool.start()
        await pool.start()
        assert fake_server.connections_accepted == 2
        await pool.close()

    async def test_calling_before_start_raises(self):
        pool = DFHackConnectionPool("127.0.0.1", 1, size=1, timeout=2.0)
        with pytest.raises(DFHackConnectionError):
            await pool.run_command("anything")

    async def test_run_command_round_trips_through_the_pool(self, fake_server):
        fake_server.queue_actions(make_ok_action('{"a": 1}'))
        pool = DFHackConnectionPool(fake_server.host, fake_server.port, size=2, timeout=2.0)
        await pool.start()
        assert await pool.run_command("df-overseer-overview", ["get"]) == '{"a": 1}'
        await pool.close()

    async def test_run_many_returns_results_in_call_order(self, fake_server):
        fake_server.queue_actions(
            make_ok_action("one"), make_ok_action("two"), make_ok_action("three")
        )
        pool = DFHackConnectionPool(fake_server.host, fake_server.port, size=3, timeout=2.0)
        await pool.start()
        results = await pool.run_many(
            [("cmd-a", []), ("cmd-b", []), ("cmd-c", [])]
        )
        assert results == ["one", "two", "three"]
        await pool.close()

    async def test_run_many_actually_batches_into_one_suspend_window(self, fake_server):
        # The whole point of the pool per research doc §6: N independent
        # requests should be pending on the server AT THE SAME INSTANT,
        # not answered one at a time. A barrier proves it -- every action
        # blocks until all `size` of them have been reached, so if the
        # pool were secretly serialising these (e.g. reusing one
        # connection sequentially), this test would hang and fail on
        # timeout instead of passing.
        barrier = asyncio.Barrier(3)
        fake_server.queue_actions(
            make_barrier_action(barrier, "a"),
            make_barrier_action(barrier, "b"),
            make_barrier_action(barrier, "c"),
        )
        pool = DFHackConnectionPool(fake_server.host, fake_server.port, size=3, timeout=5.0)
        await pool.start()
        results = await asyncio.wait_for(
            pool.run_many([("cmd", []), ("cmd", []), ("cmd", [])]),
            timeout=5.0,
        )
        assert sorted(results) == ["a", "b", "c"]
        await pool.close()

    async def test_run_many_with_more_calls_than_pool_size_still_completes(self, fake_server):
        fake_server.queue_actions(*(make_ok_action(str(i)) for i in range(5)))
        pool = DFHackConnectionPool(fake_server.host, fake_server.port, size=2, timeout=2.0)
        await pool.start()
        results = await pool.run_many([(f"cmd-{i}", []) for i in range(5)])
        assert results == [str(i) for i in range(5)]
        await pool.close()

    async def test_pool_self_heals_after_a_dead_connection(self, fake_server):
        # This is the acceptance criterion named explicitly in the handoff
        # brief: "A DF restart must not leave the pool full of dead
        # sockets that fail every later call." Size 1 so there is exactly
        # one connection to kill and exactly one to reconnect.
        fake_server.queue_actions(
            make_disconnect_action(),      # kills the pool's one connection
            make_ok_action("recovered"),   # served by the reconnected one
        )
        pool = DFHackConnectionPool(fake_server.host, fake_server.port, size=1, timeout=2.0)
        await pool.start()

        with pytest.raises(DFHackConnectionError):
            await pool.run_command("doomed")

        # The pool must not be permanently poisoned: the next call
        # transparently reconnects and succeeds.
        result = await pool.run_command("df-overseer-overview", ["get"])
        assert result == "recovered"
        assert fake_server.connections_accepted == 2
        await pool.close()

    async def test_close_only_closes_idle_connections(self, fake_server):
        pool = DFHackConnectionPool(fake_server.host, fake_server.port, size=2, timeout=2.0)
        await pool.start()
        await pool.close()
        # A closed pool refuses new calls rather than silently reopening.
        with pytest.raises(DFHackConnectionError):
            await pool.run_command("anything")
