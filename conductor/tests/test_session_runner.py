"""conductor/session_runner.py against the real envelopes captured at Gateway S0
(`conductor/tests/fixtures/gateway/`). No subprocess, no network, no VM."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from conductor.runner import RAW_RETENTION_CHARS, RunResult
from conductor.session_runner import (
    FakeTransport,
    GatewayHealth,
    GatewayTransport,
    SessionRunner,
    TransportReply,
    TurnRequest,
    decide_route,
    history_to_transcript,
    is_ambiguous,
    map_gateway_envelope,
    map_gateway_reply,
    parse_startupz,
    probe_startupz,
)

FIX = Path(__file__).parent / "fixtures" / "gateway"
ENVELOPE = json.loads((FIX / "agent_turn_mcp_tool_call.json").read_text(encoding="utf-8"))
HISTORY = json.loads((FIX / "chat_history_after_tool_call.json").read_text(encoding="utf-8"))
LOSS_STDERR = (FIX / "transport_loss_stderr.txt").read_bytes()
AUTH_STDOUT = (FIX / "auth_wrong_token.txt").read_bytes()
KEY = "agent:consultant:s0-p"


def ok_reply(envelope=ENVELOPE) -> TransportReply:
    return TransportReply(returncode=0, stdout=json.dumps(envelope).encode(), wall_clock_seconds=9.6)


class TestEnvelopeMapping:
    def test_the_captured_mcp_turn_maps_to_a_run_result(self):
        r = map_gateway_reply("consultant", KEY, ok_reply())
        assert isinstance(r, RunResult)
        assert r.ok and r.status == "ok" and not r.timed_out
        assert r.cost_usd == pytest.approx(0.0005703936)
        assert r.assistant_turns == 2
        assert r.usage["input"] == 3356 and r.usage["cacheRead"] == 22912 and r.usage["total"] == 26398
        assert r.tool_summary["calls"] == 1
        assert r.tool_summary["tools"] == ["df-consultant__doctrine__get"]
        assert r.tool_summary["distinctTools"] == 1
        assert r.final_answer.startswith("S0 check: doctrine topic")
        assert r.session_key == KEY and r.run_id == ENVELOPE["runId"]
        assert r.wall_clock_seconds == 9.6

    def test_raw_drops_the_system_prompt_report_and_keeps_the_rest(self):
        r = map_gateway_reply("consultant", KEY, ok_reply())
        assert "systemPromptReport" not in r.raw["result"]["meta"]
        assert "systemPromptReport" in ENVELOPE["result"]["meta"]  # the fixture is untouched
        assert r.raw["result"]["meta"]["toolSummary"]["calls"] == 1
        assert len(json.dumps(r.raw)) < len(json.dumps(ENVELOPE)) // 2

    def test_escalate_detection_sees_the_gateway_tool_names(self):
        # cycle.py reads tool_summary["tools"] the same way for both routes
        r = map_gateway_reply("consultant", KEY, ok_reply())
        assert "df-consultant__doctrine__get" in (r.tool_summary or {}).get("tools", [])

    def test_cost_falls_back_to_usage_cost_total_then_unknown(self):
        env = json.loads(json.dumps(ENVELOPE))
        del env["result"]["meta"]["agentMeta"]["costUsd"]
        assert map_gateway_envelope("c", env, 1.0).cost_usd == pytest.approx(0.0005703936)
        del env["result"]["meta"]["agentMeta"]["usage"]["cost"]
        assert map_gateway_envelope("c", env, 1.0).cost_usd is None  # unknown, never 0

    def test_a_non_ok_status_is_not_ok_and_keeps_raw_stdout(self):
        env = json.loads(json.dumps(ENVELOPE))
        env["status"] = "error"
        env["summary"] = "provider failed"
        reply = TransportReply(returncode=1, stdout=json.dumps(env).encode(), stderr=b"boom")
        r = map_gateway_reply("consultant", KEY, reply)
        assert not r.ok and r.status == "error" and r.error == "provider failed"
        assert r.raw["_stderr"] == "boom" and r.raw["_exit_code"] == 1
        assert json.loads(r.raw["_stdout"])["status"] == "error"
        assert r.raw["runId"] == ENVELOPE["runId"]

    def test_an_aborted_run_is_not_ok(self):
        env = json.loads(json.dumps(ENVELOPE))
        env["result"]["meta"]["aborted"] = True
        r = map_gateway_reply("consultant", KEY, TransportReply(returncode=1, stdout=json.dumps(env).encode()))
        assert not r.ok and r.status == "aborted"

    def test_missing_pieces_are_unknown_not_zero(self):
        r = map_gateway_envelope("c", {"status": "ok"}, 2.0)
        assert r.ok and r.cost_usd is None and r.usage is None
        assert r.assistant_turns is None and r.tool_summary == {} and r.final_answer is None


class TestFailureShapes:
    def test_transport_loss_is_ambiguous_and_keeps_stderr(self):
        r = map_gateway_reply("consultant", KEY, TransportReply(returncode=1, stderr=LOSS_STDERR))
        assert r.status == "transport_lost" and not r.ok and not r.timed_out
        assert is_ambiguous(r)
        assert "may still be running" in r.raw["stderr"]
        assert r.raw["exit_code"] == 1
        assert "do not resend" in r.error

    def test_wrong_token_is_gateway_auth(self):
        r = map_gateway_reply("consultant", KEY, TransportReply(returncode=1, stdout=AUTH_STDOUT))
        assert r.status == "gateway_auth" and not r.ok and not is_ambiguous(r)
        assert "gateway token mismatch" in r.raw["stdout"]

    def test_wrong_token_json_part_alone_is_gateway_auth(self):
        body = AUTH_STDOUT.decode().split("\n", 1)[1].encode()
        r = map_gateway_reply("consultant", KEY, TransportReply(returncode=1, stdout=body))
        assert r.status == "gateway_auth" and "token mismatch" in r.raw["_stdout"]

    def test_empty_stdout_keeps_stderr_for_diagnosis(self):
        r = map_gateway_reply("quartermaster", KEY, TransportReply(returncode=1, stderr=b"weird"))
        assert r.status == "no_output" and r.raw["stderr"] == "weird" and r.raw["exit_code"] == 1

    def test_bad_json_keeps_stdout_and_stderr(self):
        r = map_gateway_reply("c", KEY, TransportReply(returncode=0, stdout=b"<html>", stderr=b"e"))
        assert r.status == "bad_json" and r.raw["stdout"] == "<html>" and r.raw["stderr"] == "e"

    def test_json_that_is_not_an_object_is_bad_json(self):
        assert map_gateway_reply("c", KEY, TransportReply(stdout=b"[1]")).status == "bad_json"

    def test_timeout_is_ambiguous_and_marks_timed_out(self):
        r = map_gateway_reply("c", KEY, TransportReply(timed_out=True), timeout_seconds=100, grace_seconds=60)
        assert r.status == "timeout" and r.timed_out and is_ambiguous(r) and r.cost_usd is None
        assert "160" in r.error

    def test_launch_failure(self):
        r = map_gateway_reply("c", KEY, TransportReply(launch_error="FileNotFoundError: docker"))
        assert r.status == "launch_failed" and not is_ambiguous(r)

    def test_raw_retention_is_capped(self):
        big = b"x" * (RAW_RETENTION_CHARS * 3)
        r = map_gateway_reply("c", KEY, TransportReply(stdout=big + b"{", returncode=0))
        assert len(r.raw["stdout"]) < RAW_RETENTION_CHARS + 100
        assert "left out" in r.raw["stdout"]


class TestHistory:
    def test_the_captured_history_becomes_a_transcript(self):
        t = history_to_transcript(HISTORY)
        assert t["omitted_rounds"] == 0
        assert len(t["rounds"]) == 2
        call = t["rounds"][0]["calls"][0]
        assert call["name"] == "df-consultant__doctrine__get"
        assert "farming" in call["args"]
        assert call["result"] and call["error"] is False  # the toolResult attached by id
        assert t["rounds"][1]["text"].startswith("S0 check")
        assert t["rounds"][0]["reasoning"]

    def test_last_turn_only_cuts_at_the_last_user_message(self):
        extra = {"role": "user", "content": "second item"}
        second = {"role": "assistant", "content": [{"type": "text", "text": "done two"}]}
        hist = {"messages": HISTORY["messages"] + [extra, second]}
        t = history_to_transcript(hist)
        assert [r["text"] for r in t["rounds"]] == ["done two"]
        full = history_to_transcript(hist, last_turn_only=False)
        assert len(full["rounds"]) == 3

    def test_garbage_is_none(self):
        assert history_to_transcript(None) is None
        assert history_to_transcript({"messages": []}) is None


@pytest.mark.asyncio
class TestSessionRunnerWithFake:
    async def test_a_turn_goes_through_with_the_floor_of_the_budget_as_timeout(self):
        ft = FakeTransport(replies={KEY: [ok_reply()]})
        r = await SessionRunner(ft).run_turn("consultant", KEY, "hello", model="m", budget_seconds=299.9)
        assert r.ok
        req = ft.requests[0]
        assert req == TurnRequest("consultant", KEY, "hello", "m", 299)

    async def test_under_the_floor_nothing_is_launched(self):
        ft = FakeTransport()
        r = await SessionRunner(ft).run_turn("overseer", KEY, "x", model="m", budget_seconds=59.0)
        assert r.status == "no_budget" and not r.ok and ft.requests == [] and r.cost_usd == 0.0

    async def test_a_transport_exception_is_a_failed_run(self):
        class Boom(FakeTransport):
            async def run_turn(self, request):
                raise RuntimeError("bug")
        r = await SessionRunner(Boom()).run_turn("c", KEY, "x", model="m", budget_seconds=120)
        assert r.status == "launch_failed" and "bug" in r.error

    async def test_transcript_and_abort_delegate(self):
        ft = FakeTransport(histories={KEY: HISTORY})
        runner = SessionRunner(ft)
        assert len((await runner.transcript(KEY))["rounds"]) == 2
        assert await runner.transcript("other") is None
        await runner.abort(KEY)
        assert ft.aborts == [KEY]


class _Proc:
    def __init__(self, stdout=b"", stderr=b"", returncode=0, hang=False):
        self._o, self._e, self.returncode, self._hang, self.killed = stdout, stderr, returncode, hang, False

    async def communicate(self):
        if self._hang:
            await asyncio.sleep(999)
        return self._o, self._e

    def kill(self):
        self.killed = True

    async def wait(self):
        return self.returncode


def _transport(tmp_path, proc, calls):
    async def fake_exec(*args, **kwargs):
        calls.append(args)
        return _Proc() if args[:2] == ("docker", "kill") else proc
    return GatewayTransport(
        secrets_env_file=tmp_path / "gw.env", client_config=tmp_path / "client.json",
        client_state_root=tmp_path / "state", message_root=tmp_path / "msg",
        image="ghcr.io/openclaw/openclaw@sha256:" + "a" * 64, subprocess_exec=fake_exec,
        outer_kill_grace_seconds=0.0,
    )


@pytest.mark.asyncio
class TestGatewayTransport:
    async def test_the_command_is_one_short_client_container(self, tmp_path):
        calls = []
        t = _transport(tmp_path, _Proc(json.dumps(ENVELOPE).encode()), calls)
        reply = await t.run_turn(TurnRequest("consultant", KEY, "hi", "deepseek/x", 90))
        cmd = list(calls[0])
        assert reply.returncode == 0
        assert cmd[:4] == ["docker", "run", "--rm", "--name"]
        assert cmd[cmd.index("--network") + 1] == "host"
        assert cmd[cmd.index("--entrypoint") + 1] == "node"
        assert cmd[cmd.index("--env-file") + 1] == str(tmp_path / "gw.env")
        assert "openclaw.mjs" in cmd and cmd[cmd.index("openclaw.mjs") + 1] == "agent"
        assert cmd[cmd.index("--session-key") + 1] == KEY
        assert cmd[cmd.index("--model") + 1] == "deepseek/x"
        assert "--json" in cmd and cmd[cmd.index("--timeout") + 1] == "90"
        assert cmd[cmd.index("--message-file") + 1] == "/msg/message.txt"
        assert "@sha256:" in " ".join(cmd)
        assert "hi" not in cmd  # the message is a file, never argv
        assert any(a.endswith(":/msg:ro") for a in cmd)
        assert any(a.endswith("/home/node/.openclaw/openclaw.json:ro") for a in cmd)

    async def test_no_token_value_in_argv_and_dirs_are_cleaned(self, tmp_path):
        calls = []
        t = _transport(tmp_path, _Proc(b"{}"), calls)
        await t.run_turn(TurnRequest("c", KEY, "hi", "m", 90))
        assert not list((tmp_path / "state").iterdir())
        assert not list((tmp_path / "msg").iterdir())
        assert not any("TOKEN" in a.upper() and "=" in a for a in calls[0])

    async def test_timeout_kills_the_client_container_by_name_not_sessions_abort(self, tmp_path):
        calls = []
        proc = _Proc(hang=True)
        t = _transport(tmp_path, proc, calls)
        reply = await t.run_turn(TurnRequest("consultant", KEY, "x", "m", 0))
        assert reply.timed_out and proc.killed
        name = calls[0][calls[0].index("--name") + 1]
        assert name.startswith("conductor-gw-consultant-")
        assert ("docker", "kill", name) in calls
        flat = " ".join(" ".join(c) for c in calls)
        assert "sessions.abort" not in flat and "chat.abort" not in flat

    async def test_abort_kills_the_in_flight_client(self, tmp_path):
        calls = []
        proc = _Proc(hang=True)
        t = _transport(tmp_path, proc, calls)
        task = asyncio.create_task(t.run_turn(TurnRequest("consultant", KEY, "x", "m", 600)))
        await asyncio.sleep(0.05)
        await t.abort(KEY)
        kill = [c for c in calls if c[:2] == ("docker", "kill")]
        assert len(kill) == 1 and kill[0][2].startswith("conductor-gw-consultant-")
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    async def test_launch_failure_is_a_reply_not_an_exception(self, tmp_path):
        async def boom(*a, **k):
            raise FileNotFoundError("docker")
        t = _transport(tmp_path, _Proc(), [])
        t._exec = boom
        reply = await t.run_turn(TurnRequest("c", KEY, "x", "m", 60))
        assert "FileNotFoundError" in reply.launch_error

    async def test_chat_history_uses_gateway_call(self, tmp_path):
        calls = []
        t = _transport(tmp_path, _Proc(json.dumps(HISTORY).encode()), calls)
        doc = await t.chat_history(KEY)
        cmd = list(calls[0])
        i = cmd.index("openclaw.mjs")
        assert cmd[i + 1:i + 4] == ["gateway", "call", "chat.history"]
        assert json.loads(cmd[cmd.index("--params") + 1]) == {"sessionKey": KEY}
        assert doc["sessionKey"] == KEY

    async def test_chat_history_failure_is_none(self, tmp_path):
        t = _transport(tmp_path, _Proc(b"not json"), [])
        assert await t.chat_history(KEY) is None

    async def test_end_to_end_with_the_runner(self, tmp_path):
        t = _transport(tmp_path, _Proc(json.dumps(ENVELOPE).encode()), [])
        r = await SessionRunner(t).run_turn("consultant", KEY, "hi", model="m", budget_seconds=120)
        assert r.ok and r.tool_summary["calls"] == 1


class _Resp:
    def __init__(self, status, body):
        self.status, self._b = status, body

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestHealthAndFallback:
    def test_started_is_usable(self):
        h = parse_startupz(200, '{"ok":true,"status":"started"}')
        assert h.usable and h.state == "started"

    def test_not_started_is_not_usable(self):
        assert parse_startupz(200, '{"ok":false,"status":"starting"}').state == "starting"
        assert parse_startupz(503, "").state == "starting"
        assert parse_startupz(404, "").state == "down"
        assert parse_startupz(None, "refused").state == "down"
        assert parse_startupz(200, "not json").usable is False

    def test_probe_reads_the_url_with_a_timeout(self):
        seen = {}

        def opener(url, timeout):
            seen.update(url=url, timeout=timeout)
            return _Resp(200, b'{"ok":true,"status":"started"}')
        assert probe_startupz("http://127.0.0.1:1/startupz", opener=opener).usable
        assert seen == {"url": "http://127.0.0.1:1/startupz", "timeout": 2.0}

    def test_probe_never_raises(self):
        def opener(url, timeout):
            raise ConnectionRefusedError("no")
        h = probe_startupz("http://127.0.0.1:1/startupz", opener=opener)
        assert h.state == "down" and "ConnectionRefusedError" in h.detail

    def test_started_gateway_routes_to_the_gateway(self):
        d = decide_route(GatewayHealth("started"))
        assert d.route == "gateway" and not d.alert

    def test_gateway_not_started_falls_back_to_oneshot_with_an_alert(self):
        for state in ("down", "starting"):
            d = decide_route(GatewayHealth(state, "x"))
            assert d.route == "oneshot" and d.alert

    def test_lost_mid_wake_carries_never_falls_back(self):
        d = decide_route(GatewayHealth("down"), lost_mid_wake=True)
        assert d.route == "carry"
        assert decide_route(GatewayHealth("started"), lost_mid_wake=True).route == "carry"

    def test_a_oneshot_role_stays_oneshot_without_alert(self):
        d = decide_route(GatewayHealth("down"), role_mode="oneshot")
        assert d.route == "oneshot" and not d.alert
