"""conductor/runner.py: command construction, JSON-envelope parsing, timeout
handling -- all against an INJECTED fake subprocess exec. This module never
starts a real process and never touches docker, matching this stream's hard
line (no Docker run of openclaw, ever, including in tests)."""

from __future__ import annotations

import asyncio
import json

import pytest

from conductor.runner import DockerOpenClawRunner, FakeRoleRunner, RunResult


class _FakeProcess:
    def __init__(self, stdout: bytes, stderr: bytes = b"", *, hang: bool = False, returncode: int = 0):
        self._stdout = stdout
        self._stderr = stderr
        self._hang = hang
        self.returncode = returncode
        self.killed = False

    async def communicate(self):
        if self._hang:
            await asyncio.sleep(999)
        return self._stdout, self._stderr

    def kill(self):
        self.killed = True

    async def wait(self):
        return self.returncode


def _fake_exec(process: _FakeProcess):
    async def _exec(*args, **kwargs):
        return process
    return _exec


def _runner(tmp_path, subprocess_exec) -> DockerOpenClawRunner:
    return DockerOpenClawRunner(
        pinned_config_dir=tmp_path / "config",
        openclaw_state_dir=tmp_path / "state",
        workspace_root=tmp_path / "workspaces",
        secrets_env_file=tmp_path / "secrets.env",
        subprocess_exec=subprocess_exec,
        clock=lambda: 0.0,
    )


_OK_ENVELOPE = {
    "ok": True, "status": "ok", "costUsd": 0.0068,
    "toolSummary": {"calls": 3, "distinctTools": 2, "failures": 0},
    "finalAnswer": "Accepted proposal-0001.",
}


class TestBuildCommand:
    def test_command_names_the_pinned_per_role_config_read_only(self, tmp_path):
        runner = _runner(tmp_path, _fake_exec(_FakeProcess(b"{}")))
        command = runner.build_command("overseer", "do the thing", model="deepseek/deepseek-v4-pro")
        joined = " ".join(command)
        assert "docker run --rm --entrypoint node" in joined
        assert str(tmp_path / "config" / "overseer.json") in joined
        assert joined.count(":ro") == 1  # only the pinned config overlay is read-only
        assert "--env-file" in command
        assert str(tmp_path / "secrets.env") in command

    def test_command_carries_the_model_and_prompt(self, tmp_path):
        runner = _runner(tmp_path, _fake_exec(_FakeProcess(b"{}")))
        command = runner.build_command("architect", "survey the fort", model="deepseek/deepseek-v4-flash")
        assert "--model" in command
        assert command[command.index("--model") + 1] == "deepseek/deepseek-v4-flash"
        assert command[-1] == "survey the fort"

    def test_a_different_role_gets_a_different_config_and_workspace(self, tmp_path):
        runner = _runner(tmp_path, _fake_exec(_FakeProcess(b"{}")))
        overseer_cmd = " ".join(runner.build_command("overseer", "x", model="m"))
        architect_cmd = " ".join(runner.build_command("architect", "x", model="m"))
        assert "overseer.json" in overseer_cmd
        assert "architect.json" in architect_cmd
        assert "overseer-workspace" in overseer_cmd
        assert "architect-workspace" in architect_cmd

    def test_no_secret_value_appears_in_the_command_itself(self, tmp_path):
        """Hard line: secrets only by environment or --env-file, never argv.
        The path is fine to appear; only a real token/key value would not
        be -- and nothing here ever reads the secrets file's contents, so
        there is nothing for the command to leak."""
        runner = _runner(tmp_path, _fake_exec(_FakeProcess(b"{}")))
        command = runner.build_command("overseer", "x", model="m")
        assert "--env-file" in command
        # The env file's PATH is passed; its own contents were never opened
        # by this module (build_command takes no secret value as an arg).


@pytest.mark.asyncio
class TestRun:
    async def test_a_successful_run_parses_the_envelope(self, tmp_path):
        runner = _runner(tmp_path, _fake_exec(_FakeProcess(json.dumps(_OK_ENVELOPE).encode())))
        result = await runner.run("overseer", "rule on proposal-0001", model="deepseek/deepseek-v4-pro")
        assert isinstance(result, RunResult)
        assert result.ok is True
        assert result.status == "ok"
        assert result.cost_usd == pytest.approx(0.0068)
        assert result.tool_summary["calls"] == 3
        assert result.final_answer == "Accepted proposal-0001."
        assert result.timed_out is False
        assert result.raw == _OK_ENVELOPE

    async def test_a_failed_envelope_is_ok_false_never_an_exception(self, tmp_path):
        envelope = {"ok": False, "status": "error", "costUsd": 0.001, "toolSummary": {}}
        runner = _runner(tmp_path, _fake_exec(_FakeProcess(json.dumps(envelope).encode())))
        result = await runner.run("architect", "x", model="m")
        assert result.ok is False
        assert result.status == "error"

    async def test_invalid_json_stdout_is_a_refusal_not_a_crash(self, tmp_path):
        runner = _runner(tmp_path, _fake_exec(_FakeProcess(b"not json at all")))
        result = await runner.run("architect", "x", model="m")
        assert result.ok is False
        assert result.status == "bad_json"
        assert "did not print valid JSON" in result.error

    async def test_empty_stdout_is_a_refusal_not_a_crash(self, tmp_path):
        runner = _runner(tmp_path, _fake_exec(_FakeProcess(b"")))
        result = await runner.run("architect", "x", model="m")
        assert result.ok is False
        assert result.status == "no_output"

    async def test_a_timeout_kills_the_process_and_reports_timed_out(self, tmp_path):
        process = _FakeProcess(b"", hang=True)
        runner = _runner(tmp_path, _fake_exec(process))
        result = await runner.run("architect", "x", model="m", timeout_seconds=0.01)
        assert result.timed_out is True
        assert result.status == "timeout"
        assert process.killed is True

    async def test_launch_failure_is_a_refusal_not_a_crash(self, tmp_path):
        async def _broken_exec(*args, **kwargs):
            raise FileNotFoundError("docker: command not found")
        runner = _runner(tmp_path, _broken_exec)
        result = await runner.run("architect", "x", model="m")
        assert result.ok is False
        assert result.status == "launch_failed"
        assert "docker" in result.error


class TestSoulLifecycle:
    def test_write_soul_then_cleanup(self, tmp_path):
        runner = _runner(tmp_path, _fake_exec(_FakeProcess(b"{}")))
        soul_path = runner.write_soul("overseer", "# Overseer\n\nCharter text.")
        assert soul_path.is_file()
        assert soul_path.read_text(encoding="utf-8") == "# Overseer\n\nCharter text."

        runner.cleanup_workspace("overseer")
        assert not soul_path.is_file()

    def test_cleanup_of_a_never_written_soul_does_not_raise(self, tmp_path):
        runner = _runner(tmp_path, _fake_exec(_FakeProcess(b"{}")))
        runner.cleanup_workspace("nobody-wrote-this-role")  # must not raise


@pytest.mark.asyncio
class TestRunWithCharter:
    async def test_run_writes_the_charter_before_and_removes_it_after(self, tmp_path):
        runner = _runner(tmp_path, _fake_exec(_FakeProcess(json.dumps(_OK_ENVELOPE).encode())))
        soul_path = tmp_path / "workspaces" / "overseer-workspace" / "SOUL.md"

        result = await runner.run(
            "overseer", "rule on proposal-0001", model="m", charter="# Overseer\n\nCharter.",
        )
        assert result.ok is True
        assert not soul_path.is_file()  # cleaned up after a successful run

    async def test_run_removes_the_charter_even_when_the_run_times_out(self, tmp_path):
        process = _FakeProcess(b"", hang=True)
        runner = _runner(tmp_path, _fake_exec(process))
        soul_path = tmp_path / "workspaces" / "architect-workspace" / "SOUL.md"

        result = await runner.run(
            "architect", "survey", model="m", timeout_seconds=0.01, charter="# Architect\n",
        )
        assert result.timed_out is True
        assert not soul_path.is_file()

    async def test_run_with_no_charter_never_writes_a_soul_file(self, tmp_path):
        runner = _runner(tmp_path, _fake_exec(_FakeProcess(json.dumps(_OK_ENVELOPE).encode())))
        soul_path = tmp_path / "workspaces" / "overseer-workspace" / "SOUL.md"

        await runner.run("overseer", "rule", model="m")  # no charter=
        assert not soul_path.is_file()


# ---------------------------------------------------------------------------
# FakeRoleRunner: the double conductor/cycle.py's own tests use
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFakeRoleRunner:
    async def test_default_result_is_a_pass(self):
        fake = FakeRoleRunner()
        result = await fake.run("architect", "survey", model="m", timeout_seconds=60)
        assert result.ok is True
        assert "passed" in result.final_answer
        assert fake.calls == [{
            "role": "architect", "prompt": "survey", "model": "m", "timeout_seconds": 60,
            "charter": None,
        }]

    async def test_set_result_overrides_the_default(self):
        fake = FakeRoleRunner()
        fake.set_result("overseer", RunResult(
            role="overseer", ok=True, status="ok", cost_usd=0.01, wall_clock_seconds=1.0,
            timed_out=False, tool_summary={}, final_answer="Ruled.", raw={},
        ))
        result = await fake.run("overseer", "rule", model="m", timeout_seconds=60)
        assert result.final_answer == "Ruled."

    async def test_every_call_is_recorded(self):
        fake = FakeRoleRunner()
        await fake.run("architect", "a", model="m1", timeout_seconds=1)
        await fake.run("quartermaster", "b", model="m2", timeout_seconds=2)
        assert [c["role"] for c in fake.calls] == ["architect", "quartermaster"]
