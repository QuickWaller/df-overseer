"""Session transport: one Gateway turn at a time, mapped onto `RunResult`.

Spec: `research/2026-10-09-gateway-sessions-v1.md` sections 4, 5.4, 7.3 and 15;
facts from the live S0 (`evals/live/2026-10-09-gateway-s0/README.md`) and its
captured envelopes (`conductor/tests/fixtures/gateway/`). Nothing here starts,
stops or restarts the Gateway, and nothing here touches a VM: the real
transport is exercised in tests only through an injected fake
`subprocess_exec`.

INTERFACE (what stream 3, `sessions.py` / `news.py` / `cycle.py`, builds on)
===========================================================================

    runner = SessionRunner(GatewayTransport(...))        # or FakeTransport()

    result: RunResult = await runner.run_turn(
        role, session_key, message, model=..., budget_seconds=<what is left>,
    )
    transcript = await runner.transcript(session_key)     # dict | None, never raises
    await runner.abort(session_key)                       # kill the client container

* `run_turn` is ONE short client container: `agent --session-key <key>
  --model <m> --json --timeout <floor(budget)> --message-file`. It returns the
  same `RunResult` the one-shot runner returns (`cycle.py`, the archive and
  `_overseer_called_escalate` read it unchanged), plus `session_key` and
  `run_id` on the result. It never raises.
* Budget (spec 5.4): `budget_seconds` is what is left of the role's wake
  budget. Under `MIN_TURN_SECONDS` (60) the turn is NOT launched and the result
  has `status == "no_budget"` (`ok` False, nothing spent): the caller carries
  the remaining items. The outer kill is `timeout + OUTER_KILL_GRACE_SECONDS`.
* Statuses a caller must tell apart (all `ok` False except "ok"):
  `no_budget` (not launched), `launch_failed` (not launched: docker missing),
  `timeout` (outer kill fired; client container killed; the Gateway stops the
  run when its client dies, S0), `transport_lost` (the connection dropped; the
  Gateway MAY STILL FINISH THE TURN, so NEVER resend the same item this wake,
  spec 4.4 and 7.3: read the goal state, carry the rest), `gateway_auth`,
  `no_output`, `bad_json`, and whatever non-"ok" `status` the Gateway itself
  reports (`error`, `aborted`, `in_flight` ...). `RunResult.timed_out` is True
  only for `timeout`. `is_ambiguous(result)` is True for `timeout` and
  `transport_lost`: the turn may have acted.
* Abort is killing the client container, NOT `sessions.abort`/`chat.abort`:
  S0 showed those are refused (`unauthorized`) for the shared-token client.
  `GatewayTransport.abort(session_key)` does `docker kill <client name>`;
  `run_turn` does the same itself on the outer timeout.
* Every failed or unparseable run keeps its raw stdout, stderr and exit code in
  `RunResult.raw` (`conductor.runner.retain_raw`). An ok run's `raw` is the
  envelope minus `meta.systemPromptReport` (about 15 KB of 18 KB, S0).
* Health and fallback (spec 7.3), both pure or near-pure: `probe_startupz(url)`
  returns a `GatewayHealth`; `decide_route(health, role_mode=..., lost_mid_wake=...)`
  returns a `RouteDecision` whose `route` is `"gateway"`, `"oneshot"` (Gateway
  not started: that role runs today's one-shot exec this wake, once-per-outage
  alert) or `"carry"` (lost mid-wake: no fallback in the same wake). No retry loop.
* The transcript is read once, at close, through `gateway call chat.history`
  and cut to the last turn (from the last `user` message) by default;
  `history_to_transcript` adapts it to `conductor.runner.build_transcript`.

Transport protocol: `run_turn(TurnRequest) -> TransportReply`,
`chat_history(session_key) -> dict | None`, `abort(session_key) -> None`.
`TransportReply` is raw process facts only; interpretation lives in the one
mapping function `map_gateway_reply`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol

from conductor.runner import (
    DOCKER_KILL_WAIT_SECONDS,
    OUTER_KILL_GRACE_SECONDS,
    RunResult,
    _final_answer,
    build_transcript,
    load_transcript_caps,
    resolve_image,
    retain_raw,
    usage_from,
)

LOG = logging.getLogger("conductor.session_runner")

#: Spec 5.4: fewer than this many seconds left means no turn is started.
MIN_TURN_SECONDS = 60.0

#: Spec 7.3: the unauthenticated readiness probe, 2 s.
STARTUP_PROBE_TIMEOUT_SECONDS = 2.0

#: Mount points inside the client container.
CLIENT_STATE_MOUNT = "/home/node/.openclaw"
CLIENT_CONFIG_MOUNT = "/home/node/.openclaw/openclaw.json"
MESSAGE_MOUNT = "/msg"

#: Statuses where the turn may have acted and may still be running.
AMBIGUOUS_STATUSES = ("timeout", "transport_lost")

_TRANSPORT_LOST_MARKERS = (
    "gateway closed",
    "may still be running this turn",
    "connection closed",
    "econnrefused",
    "econnreset",
    "abnormal closure",
)
_AUTH_MARKERS = ("unauthorized", "token mismatch", "gateway_credentials_required", "auth_token")


# ---- transport protocol -------------------------------------------------

@dataclass(frozen=True)
class TurnRequest:
    role: str
    session_key: str
    message: str
    model: str
    #: Whole seconds handed to `agent --timeout` (the run's own deadline).
    timeout_seconds: int


@dataclass(frozen=True)
class TransportReply:
    """What one client invocation did, uninterpreted."""

    returncode: Optional[int] = None
    stdout: bytes = b""
    stderr: bytes = b""
    #: The conductor-side outer kill fired.
    timed_out: bool = False
    #: The client could not be launched at all (docker missing, ...).
    launch_error: Optional[str] = None
    wall_clock_seconds: float = 0.0


class Transport(Protocol):
    async def run_turn(self, request: TurnRequest) -> TransportReply: ...

    async def chat_history(self, session_key: str) -> Optional[dict]: ...

    async def abort(self, session_key: str) -> None: ...


def is_ambiguous(result: RunResult) -> bool:
    """True when the turn may have acted (or still be running): never resend."""
    return result.status in AMBIGUOUS_STATUSES


# ---- envelope mapping ---------------------------------------------------

def _num(v: Any) -> Optional[float]:
    return None if isinstance(v, bool) or not isinstance(v, (int, float)) else v


def _slim_envelope(envelope: dict) -> dict:
    """The envelope without `result.meta.systemPromptReport` (about 15 KB of
    18 KB in S0, S0 open item 2): everything else is kept."""
    result = envelope.get("result")
    meta = result.get("meta") if isinstance(result, dict) else None
    if not isinstance(meta, dict) or "systemPromptReport" not in meta:
        return envelope
    slim_meta = {k: v for k, v in meta.items() if k != "systemPromptReport"}
    return {**envelope, "result": {**result, "meta": slim_meta}}


def _gateway_final_answer(envelope: dict) -> Optional[str]:
    result = envelope.get("result")
    if isinstance(result, dict):
        text = _final_answer(result)  # payloads[].text
        if text:
            return text
        meta = result.get("meta")
        if isinstance(meta, dict):
            for key in ("finalAssistantVisibleText", "finalAssistantRawText"):
                v = meta.get(key)
                if isinstance(v, str) and v:
                    return v
    return None


def _gateway_tool_summary(meta: dict) -> Dict[str, Any]:
    summary = meta.get("toolSummary")
    if not isinstance(summary, dict):
        return {}
    out = dict(summary)
    tools = out.get("tools")
    if isinstance(tools, list) and "distinctTools" not in out:
        out["distinctTools"] = len(set(map(str, tools)))
    return out


def _gateway_cost(agent_meta: dict) -> Optional[float]:
    """`costUsd`, else `usage.cost.total`; None (unknown) when neither is a number."""
    cost = _num(agent_meta.get("costUsd"))
    if cost is None:
        usage = agent_meta.get("usage")
        inner = usage.get("cost") if isinstance(usage, dict) else None
        cost = _num(inner.get("total")) if isinstance(inner, dict) else None
    return None if cost is None else float(cost)


def map_gateway_envelope(
    role: str, envelope: dict, wall_clock_seconds: float, *,
    stdout: Any = b"", stderr: Any = b"", exit_code: Optional[int] = None,
    session_key: Optional[str] = None,
) -> RunResult:
    """The Gateway `agent --json` reply `{runId, status, summary, result:{payloads,
    meta}}` -> the one-shot `RunResult` shape. Run stats are on
    `result.meta.agentMeta`, the tool summary on `result.meta.toolSummary`
    (spec 4.2). `ok` is `status == "ok"` and the run was not aborted. A run
    that is not ok keeps its raw stdout and stderr."""
    result = envelope.get("result") if isinstance(envelope.get("result"), dict) else {}
    meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
    agent_meta = meta.get("agentMeta") if isinstance(meta.get("agentMeta"), dict) else {}
    status = str(envelope.get("status", "unknown"))
    aborted = bool(meta.get("aborted", False))
    ok = status == "ok" and not aborted
    turns = _num(agent_meta.get("assistantTurns"))
    slim = _slim_envelope(envelope)
    error = None
    if not ok:
        summary = envelope.get("summary")
        error = (summary if isinstance(summary, str) and summary else None) or (
            "run aborted" if aborted else f"gateway status {status}")
    mapped = RunResult(
        role=role,
        ok=ok,
        status=status if not (aborted and status == "ok") else "aborted",
        cost_usd=_gateway_cost(agent_meta),
        wall_clock_seconds=wall_clock_seconds,
        timed_out=False,
        tool_summary=_gateway_tool_summary(meta),
        final_answer=_gateway_final_answer(envelope),
        raw=slim if ok else retain_raw(stdout, stderr, exit_code, envelope=slim),
        error=error,
        usage=usage_from(agent_meta),
        assistant_turns=int(turns) if turns is not None and turns >= 0 else None,
    )
    return replace(
        mapped, session_key=session_key,
        run_id=envelope["runId"] if isinstance(envelope.get("runId"), str) else None,
    )


def map_gateway_reply(
    role: str, session_key: str, reply: TransportReply, *, grace_seconds: float = OUTER_KILL_GRACE_SECONDS,
    timeout_seconds: float = 0.0,
) -> RunResult:
    """Every outcome of one client invocation -> a `RunResult`. Never raises."""
    def failed(status: str, error: str, *, timed_out: bool = False) -> RunResult:
        return RunResult(
            role=role, ok=False, status=status, cost_usd=None,
            wall_clock_seconds=reply.wall_clock_seconds, timed_out=timed_out,
            tool_summary={}, final_answer=None,
            raw=retain_raw(reply.stdout, reply.stderr, reply.returncode),
            error=error, session_key=session_key,
        )

    if reply.launch_error:
        return failed("launch_failed", reply.launch_error)
    if reply.timed_out:
        return failed(
            "timeout", f"timed out after {timeout_seconds + grace_seconds}s (cost unknown)",
            timed_out=True,
        )
    text = reply.stdout.decode("utf-8", errors="replace").strip()
    err = reply.stderr.decode("utf-8", errors="replace")
    lowered = err.lower()
    if not text:
        if any(m in lowered for m in _TRANSPORT_LOST_MARKERS):
            return failed(
                "transport_lost",
                "gateway connection lost; the turn may still be running (do not resend)",
            )
        if any(m in lowered for m in _AUTH_MARKERS):
            return failed("gateway_auth", "gateway refused the token")
        return failed("no_output", "agent --json printed nothing")
    try:
        envelope = json.loads(text)
    except json.JSONDecodeError:
        if any(m in (text + lowered).lower() for m in _AUTH_MARKERS):
            return failed("gateway_auth", "gateway refused the token")
        return failed("bad_json", "agent --json did not print valid JSON")
    if not isinstance(envelope, dict):
        return failed("bad_json", "agent --json did not print a JSON object")
    # A structured error object from the client (`{"ok": false, "error": {...}}`).
    if "status" not in envelope and isinstance(envelope.get("error"), dict):
        code = str(envelope["error"].get("message") or envelope["error"].get("code") or "error")
        status = "gateway_auth" if any(m in code.lower() for m in _AUTH_MARKERS) else "error"
        return replace(failed(status, code), raw=retain_raw(reply.stdout, reply.stderr, reply.returncode, envelope=envelope))
    return map_gateway_envelope(
        role, envelope, reply.wall_clock_seconds, stdout=reply.stdout, stderr=reply.stderr,
        exit_code=reply.returncode, session_key=session_key,
    )


# ---- chat.history -> transcript -----------------------------------------

def history_to_transcript(
    history: Any, caps: Optional[Dict[str, int]] = None, *, last_turn_only: bool = True,
) -> Optional[dict]:
    """`chat.history`'s `{messages: [...]}` -> `build_transcript`'s dict. Its
    messages are bare (`{role, content, ...}`), `build_transcript` wants
    `{"message": ...}` events, so they are wrapped. `last_turn_only` cuts at the
    last `user` message (one item per turn, spec 4.3). None when empty."""
    messages = history.get("messages") if isinstance(history, dict) else None
    if not isinstance(messages, list):
        return None
    msgs = [m for m in messages if isinstance(m, dict)]
    if last_turn_only:
        for i in range(len(msgs) - 1, -1, -1):
            if msgs[i].get("role") == "user":
                msgs = msgs[i:]
                break
    return build_transcript([{"message": m} for m in msgs], caps)


# ---- health probe and fallback decision ---------------------------------

@dataclass(frozen=True)
class GatewayHealth:
    #: "started" (usable), "starting" (up but not admitting), "down".
    state: str
    detail: str = ""

    @property
    def usable(self) -> bool:
        return self.state == "started"


def parse_startupz(http_status: Optional[int], body: str) -> GatewayHealth:
    """`/startupz`: 200 with `status: "started"` means usable, anything else not."""
    if http_status is None:
        return GatewayHealth("down", body or "no response")
    try:
        doc = json.loads(body) if body else {}
    except ValueError:
        doc = {}
    status = doc.get("status") if isinstance(doc, dict) else None
    if http_status == 200 and status == "started":
        return GatewayHealth("started")
    if http_status == 200 or http_status == 503:
        return GatewayHealth("starting", f"http {http_status} status {status!r}")
    return GatewayHealth("down", f"http {http_status}")


def probe_startupz(
    url: str, timeout_seconds: float = STARTUP_PROBE_TIMEOUT_SECONDS,
    *, opener: Optional[Callable[..., Any]] = None,
) -> GatewayHealth:
    """GET `url` (e.g. `http://127.0.0.1:<port>/startupz`) from Python directly,
    no container, no auth. Never raises. `opener` is the test seam."""
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(url, timeout=timeout_seconds) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return parse_startupz(getattr(resp, "status", 200), body)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            body = ""
        return parse_startupz(exc.code, body)
    except Exception as exc:  # noqa: BLE001 -- refused, timeout, DNS: all "down"
        return GatewayHealth("down", f"{type(exc).__name__}: {exc}")


async def probe_startupz_async(url: str, timeout_seconds: float = STARTUP_PROBE_TIMEOUT_SECONDS) -> GatewayHealth:
    return await asyncio.to_thread(probe_startupz, url, timeout_seconds)


@dataclass(frozen=True)
class RouteDecision:
    #: "gateway", "oneshot" or "carry".
    route: str
    reason: str
    #: True when this decision means the Gateway is down and the conductor
    #: should raise "Gateway down, roles on one-shot" (once per outage; the
    #: caller owns the once-per-outage and renotify bookkeeping).
    alert: bool = False


def decide_route(
    health: GatewayHealth, *, role_mode: str = "session", lost_mid_wake: bool = False,
) -> RouteDecision:
    """Spec 7.3, pure. `role_mode` is the role's configured mode (`session` or
    `oneshot`). A role configured one-shot always runs one-shot. Gateway not
    started at wake open: one-shot this wake. Lost mid-wake (a transport error
    or the probe now failing): "carry" the role's remaining items, never a
    fallback run in the same wake, because the Gateway may still finish the
    in-flight turn."""
    if role_mode == "oneshot":
        return RouteDecision("oneshot", "role is configured one-shot")
    if lost_mid_wake:
        return RouteDecision("carry", "gateway lost mid-wake; the in-flight turn may still finish", alert=True)
    if health.usable:
        return RouteDecision("gateway", "gateway started")
    return RouteDecision("oneshot", f"gateway not started ({health.state}: {health.detail})".rstrip(": ()"), alert=True)


# ---- the Gateway transport ----------------------------------------------

SubprocessExec = Callable[..., Awaitable[Any]]


class GatewayTransport:
    """One short `docker run --rm --network host ... openclaw.mjs agent ...` per
    turn, the token only from the env file (never argv). Each call gets its own
    empty client state dir under `client_state_root`, removed after. The
    message goes in a file under `message_root`, mounted read-only, because
    `--message-file` avoids argv limits (spec 4.1)."""

    def __init__(
        self, *, secrets_env_file: Path, client_config: Path, client_state_root: Path,
        message_root: Path, image: Optional[str] = None,
        subprocess_exec: SubprocessExec = asyncio.create_subprocess_exec,
        clock: Callable[[], float] = time.monotonic,
        outer_kill_grace_seconds: float = OUTER_KILL_GRACE_SECONDS,
        history_timeout_seconds: float = 30.0,
    ):
        self.secrets_env_file = Path(secrets_env_file)
        self.client_config = Path(client_config)
        self.client_state_root = Path(client_state_root)
        self.message_root = Path(message_root)
        self.image = image or resolve_image()
        self._exec = subprocess_exec
        self._clock = clock
        self._grace = outer_kill_grace_seconds
        self._history_timeout = history_timeout_seconds
        self._inflight: Dict[str, str] = {}  # session_key -> client container name

    def _base(self, name: str, state_dir: Path, *, message_dir: Optional[Path] = None) -> List[str]:
        mounts = [
            "-v", f"{state_dir}:{CLIENT_STATE_MOUNT}",
            "-v", f"{self.client_config}:{CLIENT_CONFIG_MOUNT}:ro",
        ]
        if message_dir is not None:
            mounts += ["-v", f"{message_dir}:{MESSAGE_MOUNT}:ro"]
        return [
            "docker", "run", "--rm", "--name", name, "--network", "host",
            "--entrypoint", "node", "--env-file", str(self.secrets_env_file),
            *mounts, self.image, "openclaw.mjs",
        ]

    def build_turn_command(
        self, request: TurnRequest, *, name: str, state_dir: Path, message_dir: Path,
        message_file: str,
    ) -> List[str]:
        return [
            *self._base(name, state_dir, message_dir=message_dir),
            "agent", "--session-key", request.session_key, "--model", request.model, "--json",
            "--timeout", str(int(request.timeout_seconds)),
            "--message-file", f"{MESSAGE_MOUNT}/{message_file}",
        ]

    def build_history_command(self, session_key: str, *, name: str, state_dir: Path) -> List[str]:
        return [
            *self._base(name, state_dir),
            "gateway", "call", "chat.history",
            "--params", json.dumps({"sessionKey": session_key}, separators=(",", ":")),
            "--json",
        ]

    async def _kill_container(self, name: str) -> None:
        """`docker kill <name>`, best effort, bounded. This IS the abort."""
        try:
            proc = await self._exec(
                "docker", "kill", name, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=DOCKER_KILL_WAIT_SECONDS)
        except Exception:  # noqa: BLE001
            pass

    async def abort(self, session_key: str) -> None:
        name = self._inflight.get(session_key)
        if name:
            await self._kill_container(name)

    async def run_turn(self, request: TurnRequest) -> TransportReply:
        started = self._clock()
        tag = uuid.uuid4().hex[:12]
        name = f"conductor-gw-{request.role}-{tag}"
        state_dir = self.client_state_root / name
        message_dir = self.message_root / name
        try:
            state_dir.mkdir(parents=True, exist_ok=True)
            message_dir.mkdir(parents=True, exist_ok=True)
            (message_dir / "message.txt").write_text(request.message, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            self._cleanup(state_dir, message_dir)
            return TransportReply(launch_error=f"{type(exc).__name__}: {exc}")
        command = self.build_turn_command(
            request, name=name, state_dir=state_dir, message_dir=message_dir, message_file="message.txt",
        )
        self._inflight[request.session_key] = name
        try:
            try:
                proc = await self._exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            except Exception as exc:  # noqa: BLE001
                return TransportReply(
                    launch_error=f"{type(exc).__name__}: {exc}", wall_clock_seconds=self._clock() - started,
                )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=request.timeout_seconds + self._grace,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                # Killing the `docker run` client does not stop the container:
                # kill it by name. The Gateway stops the run when its client dies (S0).
                await self._kill_container(name)
                return TransportReply(timed_out=True, wall_clock_seconds=self._clock() - started)
            except asyncio.CancelledError:
                await self._kill_container(name)
                raise
            return TransportReply(
                returncode=proc.returncode, stdout=stdout or b"", stderr=stderr or b"",
                wall_clock_seconds=self._clock() - started,
            )
        finally:
            self._inflight.pop(request.session_key, None)
            self._cleanup(state_dir, message_dir)

    async def chat_history(self, session_key: str) -> Optional[dict]:
        name = f"conductor-gwh-{uuid.uuid4().hex[:12]}"
        state_dir = self.client_state_root / name
        try:
            state_dir.mkdir(parents=True, exist_ok=True)
            proc = await self._exec(
                *self.build_history_command(session_key, name=name, state_dir=state_dir),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=self._history_timeout)
            doc = json.loads(stdout.decode("utf-8", errors="replace"))
            return doc if isinstance(doc, dict) else None
        except asyncio.TimeoutError:
            await self._kill_container(name)
            return None
        except Exception as exc:  # noqa: BLE001 -- observability, never fails a run
            LOG.warning("session runner: chat.history failed for %s: %s", session_key, exc)
            return None
        finally:
            shutil.rmtree(state_dir, ignore_errors=True)

    @staticmethod
    def _cleanup(*dirs: Path) -> None:
        for d in dirs:
            shutil.rmtree(d, ignore_errors=True)


# ---- the fake transport (tests) -----------------------------------------

class FakeTransport:
    """Scripted transport: no subprocess, no network. `replies[session_key]` is
    a list of `TransportReply` consumed in order (the last one repeats); a
    session with none gets an ok reply built from `default_envelope`. Every
    request, abort and history read is recorded."""

    def __init__(
        self, replies: Optional[Dict[str, List[TransportReply]]] = None,
        histories: Optional[Dict[str, dict]] = None, default_envelope: Optional[dict] = None,
    ):
        self.replies = {k: list(v) for k, v in (replies or {}).items()}
        self.histories = dict(histories or {})
        self.default_envelope = default_envelope
        self.requests: List[TurnRequest] = []
        self.aborts: List[str] = []
        self.history_reads: List[str] = []

    async def run_turn(self, request: TurnRequest) -> TransportReply:
        self.requests.append(request)
        queue = self.replies.get(request.session_key)
        if queue:
            return queue.pop(0) if len(queue) > 1 else queue[0]
        envelope = self.default_envelope or {
            "runId": "fake-run", "status": "ok", "summary": "completed",
            "result": {"payloads": [{"text": "(fake transport reply)"}], "meta": {
                "toolSummary": {"calls": 0, "tools": [], "failures": 0}, "agentMeta": {"assistantTurns": 1},
            }},
        }
        return TransportReply(returncode=0, stdout=json.dumps(envelope).encode())

    async def chat_history(self, session_key: str) -> Optional[dict]:
        self.history_reads.append(session_key)
        return self.histories.get(session_key)

    async def abort(self, session_key: str) -> None:
        self.aborts.append(session_key)


# ---- the runner ----------------------------------------------------------

class SessionRunner:
    """Budget handling plus mapping over any `Transport`."""

    def __init__(
        self, transport: Transport, *, min_turn_seconds: float = MIN_TURN_SECONDS,
        grace_seconds: float = OUTER_KILL_GRACE_SECONDS,
        transcript_caps: Optional[Dict[str, int]] = None,
    ):
        self.transport = transport
        self.min_turn_seconds = min_turn_seconds
        self._grace = grace_seconds
        self.transcript_caps = transcript_caps or load_transcript_caps()

    async def run_turn(
        self, role: str, session_key: str, message: str, *, model: str, budget_seconds: float,
    ) -> RunResult:
        if budget_seconds < self.min_turn_seconds:
            return RunResult(
                role=role, ok=False, status="no_budget", cost_usd=0.0, wall_clock_seconds=0.0,
                timed_out=False, tool_summary={}, final_answer=None, raw={},
                error=f"{budget_seconds:.0f}s left, under the {self.min_turn_seconds:.0f}s floor",
                session_key=session_key,
            )
        timeout = int(budget_seconds)
        try:
            reply = await self.transport.run_turn(TurnRequest(role, session_key, message, model, timeout))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 -- a transport bug is a failed run, not a crash
            reply = TransportReply(launch_error=f"{type(exc).__name__}: {exc}")
        return map_gateway_reply(role, session_key, reply, grace_seconds=self._grace, timeout_seconds=timeout)

    async def transcript(self, session_key: str, *, last_turn_only: bool = True) -> Optional[dict]:
        try:
            history = await self.transport.chat_history(session_key)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("session runner: history read failed for %s: %s", session_key, exc)
            return None
        return history_to_transcript(history, self.transcript_caps, last_turn_only=last_turn_only)

    async def abort(self, session_key: str) -> None:
        try:
            await self.transport.abort(session_key)
        except Exception:  # noqa: BLE001
            pass
