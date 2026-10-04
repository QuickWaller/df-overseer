"""Offline tests for scripts/drift_check.py: every host interaction goes
through a FakeRunner, never a real ssh call."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import pytest  # noqa: E402

import deploy_common as dc  # noqa: E402
import drift_check  # noqa: E402


def _target(**overrides) -> dc.Target:
    base = dict(
        name="sample",
        host="df",
        destination_root_raw="/opt/sample",
        paths=["agents/ROSTER.yaml"],
        exclude=[],
        leave_alone=[],
        restart=[dc.RestartEntry(service="sample.service", risk="low", why="ok")],
        post_deploy=[],
    )
    base.update(overrides)
    return dc.Target(**base)


# ---------------------------------------------------------------------------
# stamp
# ---------------------------------------------------------------------------


def test_read_stamp_parses_key_value_lines():
    runner = dc.FakeRunner({
        ("df", "cat /opt/sample/DEPLOYED_COMMIT 2>/dev/null || true"):
            "commit=abc123\ndeployed_at=2026-10-02T00:00:00Z\nmanifest_sha256=deadbeef\n",
    })
    stamp = drift_check.read_stamp(_target(), "/opt/sample", runner)
    assert stamp == {"commit": "abc123", "deployed_at": "2026-10-02T00:00:00Z", "manifest_sha256": "deadbeef"}


def test_read_stamp_missing_returns_none():
    runner = dc.FakeRunner({("df", "cat /opt/sample/DEPLOYED_COMMIT 2>/dev/null || true"): ""})
    assert drift_check.read_stamp(_target(), "/opt/sample", runner) is None


# ---------------------------------------------------------------------------
# remote_sha256_many
# ---------------------------------------------------------------------------


def test_remote_sha256_many_parses_normal_output():
    files = ["a.txt", "b.txt"]
    sha_a = "1" * 64
    sha_b = "2" * 64
    runner = dc.FakeRunner({
        ("df", f"cd /opt/sample && sha256sum {files[0]} {files[1]} 2>&1 || true"):
            f"{sha_a}  a.txt\n{sha_b}  b.txt\n",
    })
    out = drift_check.remote_sha256_many("df", "/opt/sample", files, runner)
    assert out == {"a.txt": sha_a, "b.txt": sha_b}


def test_remote_sha256_many_handles_missing_file():
    files = ["a.txt", "missing.txt"]
    sha_a = "1" * 64
    runner = dc.FakeRunner({
        ("df", f"cd /opt/sample && sha256sum {files[0]} {files[1]} 2>&1 || true"):
            f"{sha_a}  a.txt\nsha256sum: missing.txt: No such file or directory\n",
    })
    out = drift_check.remote_sha256_many("df", "/opt/sample", files, runner)
    assert out == {"a.txt": sha_a, "missing.txt": None}


def test_remote_sha256_many_respects_flatten_remote_path():
    files = ["web/stream/index.html"]
    sha = "3" * 64
    runner = dc.FakeRunner({
        ("relay", "cd /srv/stream/web-public && sha256sum index.html 2>&1 || true"): f"{sha}  index.html\n",
    })
    out = drift_check.remote_sha256_many(
        "relay", "/srv/stream/web-public", files, runner, remote_path=lambda f: f.rsplit("/", 1)[-1],
    )
    assert out == {"web/stream/index.html": sha}


def test_remote_sha256_many_survives_masked_filenames_by_position():
    # Reproduces the real, live-confirmed case: vm-ssh.sh's scrubber masks
    # any df-[a-z0-9-]+-shaped string, including this project's own
    # df-overseer-*.lua filenames, so the printed name in sha256sum's own
    # output comes back as "<host>.lua" for every one of them. Name-based
    # matching would silently call every one of these "missing"; position
    # must not.
    files = ["scripts/dfhack/df-overseer-ui.lua", "scripts/dfhack/df-overseer-zone.lua"]
    sha_a = "a" * 64
    sha_b = "b" * 64
    runner = dc.FakeRunner({
        ("df", "cd /opt/game/scripts && sha256sum df-overseer-ui.lua df-overseer-zone.lua 2>&1 || true"):
            f"{sha_a}  <host>.lua\n{sha_b}  <host>.lua\n",
    })
    out = drift_check.remote_sha256_many(
        "df", "/opt/game/scripts", files, runner, remote_path=lambda f: f.rsplit("/", 1)[-1],
    )
    assert out == {
        "scripts/dfhack/df-overseer-ui.lua": sha_a,
        "scripts/dfhack/df-overseer-zone.lua": sha_b,
    }


def test_remote_sha256_many_empty_files_returns_empty_without_calling_runner():
    runner = dc.FakeRunner({})
    assert drift_check.remote_sha256_many("df", "/opt/sample", [], runner) == {}
    assert runner.calls == []


# ---------------------------------------------------------------------------
# check_target_files
# ---------------------------------------------------------------------------


def test_check_target_files_clean_when_hashes_match():
    head = dc.current_commit()
    target = _target(paths=["agents/ROSTER.yaml"])
    real_hash = dc.sha256_at_commit(head, "agents/ROSTER.yaml")
    runner = dc.FakeRunner({
        ("df", "cat /opt/sample/DEPLOYED_COMMIT 2>/dev/null || true"): f"commit={head}\n",
        ("df", f"cd /opt/sample && sha256sum agents/ROSTER.yaml 2>&1 || true"): f"{real_hash}  agents/ROSTER.yaml\n",
    })
    result = drift_check.check_target_files(target, {}, runner)
    assert result["clean"] is True
    assert result["drifted_count"] == 0
    assert result["stamp"]["commit"] == head


def test_check_target_files_detects_drift():
    head = dc.current_commit()
    target = _target(paths=["agents/ROSTER.yaml"])
    wrong_hash = "f" * 64
    runner = dc.FakeRunner({
        ("df", "cat /opt/sample/DEPLOYED_COMMIT 2>/dev/null || true"): f"commit={head}\n",
        ("df", f"cd /opt/sample && sha256sum agents/ROSTER.yaml 2>&1 || true"): f"{wrong_hash}  agents/ROSTER.yaml\n",
    })
    result = drift_check.check_target_files(target, {}, runner)
    assert result["clean"] is False
    assert result["drifted_count"] == 1
    assert result["files"][0]["status"] == "differ"


def test_check_target_files_no_stamp_compares_against_origin_main():
    target = _target(paths=["agents/ROSTER.yaml"])
    origin_main_hash = dc.sha256_at_commit("origin/main", "agents/ROSTER.yaml")
    runner = dc.FakeRunner({
        ("df", "cat /opt/sample/DEPLOYED_COMMIT 2>/dev/null || true"): "",
        ("df", "cd /opt/sample && sha256sum agents/ROSTER.yaml 2>&1 || true"):
            f"{origin_main_hash}  agents/ROSTER.yaml\n",
    })
    result = drift_check.check_target_files(target, {}, runner)
    assert result["stamp"] is None
    assert result["compared_against"] == "origin/main"
    assert result["clean"] is True


def test_check_target_files_missing_on_host_counts_as_drift():
    target = _target(paths=["agents/ROSTER.yaml"])
    runner = dc.FakeRunner({
        ("df", "cat /opt/sample/DEPLOYED_COMMIT 2>/dev/null || true"): "",
        ("df", "cd /opt/sample && sha256sum agents/ROSTER.yaml 2>&1 || true"):
            "sha256sum: agents/ROSTER.yaml: No such file or directory\n",
    })
    result = drift_check.check_target_files(target, {}, runner)
    assert result["clean"] is False
    assert result["files"][0]["status"] == "missing_on_host"


# ---------------------------------------------------------------------------
# systemd unit targets: hashing plus untracked unit / drop-in detection
# ---------------------------------------------------------------------------

_LIST_CMD = ("cd /etc/systemd/system && find . -mindepth 1 -maxdepth 2 -type f "
             "| sed 's/-/_/g' | sort || true")


def _unit_target(**overrides) -> dc.Target:
    base = dict(
        name="units", host="df", destination_root_raw="/etc/systemd/system",
        paths=["infra/units/df/"], sudo=True, strip_prefix="infra/units/df/",
        stamp=False, daemon_reload=True, restart=[],
        unmanaged_units=[{"name": "df-vnc-tunnel.service", "why": "address"}],
    )
    base.update(overrides)
    return dc.Target(**base)


def _unit_runner(listing: str, target: dc.Target, *, same_hashes=True):
    files = dc.target_files(target, "HEAD")
    names = [target.remote_path(f) for f in files]
    hashes = {f: dc.sha256_at_commit("HEAD", f) for f in files}
    sha_out = "".join(f"{hashes[f] if same_hashes else 'f' * 64}  {n}\n" for f, n in zip(files, names))
    return dc.FakeRunner({
        ("df", f"cd /etc/systemd/system && sha256sum {' '.join(names)} 2>&1 || true"): sha_out,
        ("df", _LIST_CMD): listing,
    })


def _installed_listing(target: dc.Target, extra=()):
    names = [target.remote_path(f).replace("-", "_") for f in dc.target_files(target, "HEAD")]
    return "".join(f"./{n}\n" for n in [*names, *extra])


def _patch_compare_to_head(monkeypatch):
    # the real comparison commit for an unstamped target is origin/main, which
    # does not carry unpushed unit files; compare against HEAD for these tests
    real = dc.target_files
    monkeypatch.setattr(dc, "target_files", lambda t, commit, cwd=dc.REPO_ROOT: real(t, "HEAD"))
    real_sha = dc.sha256_at_commit
    monkeypatch.setattr(dc, "sha256_at_commit", lambda c, p, cwd=dc.REPO_ROOT: real_sha("HEAD", p))


def test_units_clean_when_hashes_match_and_nothing_extra(monkeypatch):
    _patch_compare_to_head(monkeypatch)
    t = _unit_target()
    listing = _installed_listing(t, extra=["df_vnc_tunnel.service"])  # declared unmanaged
    result = drift_check.check_target_files(t, {}, _unit_runner(listing, t))
    assert result["clean"] is True and result["untracked"] == []
    assert result["stamp"] is None  # never reads a stamp for stamp: false


def test_units_installed_dropin_unknown_to_repo_is_drift(monkeypatch):
    _patch_compare_to_head(monkeypatch)
    t = _unit_target()
    listing = _installed_listing(t, extra=["dfmcp_server.service.d/override.conf"])
    result = drift_check.check_target_files(t, {}, _unit_runner(listing, t))
    assert result["clean"] is False
    assert result["untracked"] == [{"path": "dfmcp_server.service.d/override.conf", "kind": "drop-in"}]


def test_units_installed_unit_unknown_to_repo_is_drift(monkeypatch):
    _patch_compare_to_head(monkeypatch)
    t = _unit_target()
    result = drift_check.check_target_files(t, {}, _unit_runner(_installed_listing(t, extra=["stray.service"]), t))
    assert result["clean"] is False
    assert result["untracked"][0] == {"path": "stray.service", "kind": "unit"}


def test_units_edited_in_place_is_drift(monkeypatch):
    _patch_compare_to_head(monkeypatch)
    t = _unit_target()
    result = drift_check.check_target_files(t, {}, _unit_runner(_installed_listing(t), t, same_hashes=False))
    assert result["clean"] is False and result["drifted_count"] == result["file_count"]


def test_units_unmanaged_directory_name_covers_its_files(monkeypatch):
    _patch_compare_to_head(monkeypatch)
    t = _unit_target(unmanaged_units=[{"name": "sshd-keygen@.service.d", "why": "distro"}])
    listing = _installed_listing(t, extra=["sshd_keygen@.service.d/disable_it.conf"])
    assert drift_check.check_target_files(t, {}, _unit_runner(listing, t))["clean"] is True


def test_units_empty_listing_is_an_error_not_a_false_all_clear(monkeypatch):
    _patch_compare_to_head(monkeypatch)
    t = _unit_target()
    result = drift_check.check_target_files(t, {}, _unit_runner("", t))
    assert result["clean"] is False
    assert result["untracked_error"]


def test_non_unit_target_does_not_list_untracked():
    target = _target(paths=["agents/ROSTER.yaml"])
    real_hash = dc.sha256_at_commit("origin/main", "agents/ROSTER.yaml")
    runner = dc.FakeRunner({
        ("df", "cat /opt/sample/DEPLOYED_COMMIT 2>/dev/null || true"): "",
        ("df", "cd /opt/sample && sha256sum agents/ROSTER.yaml 2>&1 || true"): f"{real_hash}  agents/ROSTER.yaml\n",
    })
    result = drift_check.check_target_files(target, {}, runner)
    assert result["untracked"] == [] and result["untracked_error"] is None


# ---------------------------------------------------------------------------
# offline tool counts
# ---------------------------------------------------------------------------


def test_offline_role_tool_counts_matches_real_roster():
    counts = drift_check.offline_role_tool_counts()
    assert set(counts) == {"overseer", "architect", "consultant", "conductor", "quartermaster"}
    assert all(c > 0 for c in counts.values())


# ---------------------------------------------------------------------------
# check_live_tool_counts
# ---------------------------------------------------------------------------


def test_check_live_tool_counts_probe_absent_is_clean_with_note():
    targets = {"vm103-dfmcp": _target(host="df", destination_root_raw="/opt/df/dfmcp-smoke")}
    runner = dc.FakeRunner({
        ("df", "test -f /opt/df/dfmcp-smoke/scripts/ops/mcpcall.py && echo present || echo absent"): "absent\n",
    })
    result = drift_check.check_live_tool_counts(targets, runner)
    assert result["clean"] is True
    assert result["probe_deployed"] is False
    assert "cross-checked" in result["note"]


def test_check_live_tool_counts_probe_present_clean_when_ids_match():
    """A real `names-all` dump of conductor's exact own tool ids (the
    smallest role, 17 tools) must compare clean -- this exercises the real
    id.replace(".", "__") <-> name_to_id round trip against the real
    registry, not a stubbed-out comparison."""
    conductor_ids = sorted(drift_check.offline_role_tool_ids()["conductor"])
    names_all = "".join(f"conductor\t{tid.replace('.', '__')}\n" for tid in conductor_ids)
    targets = {"vm103-dfmcp": _target(host="df", destination_root_raw="/opt/df/dfmcp-smoke")}
    runner = dc.FakeRunner({
        ("df", "test -f /opt/df/dfmcp-smoke/scripts/ops/mcpcall.py && echo present || echo absent"): "present\n",
        ("df", "cd /opt/df/dfmcp-smoke && .venv/bin/python scripts/ops/mcpcall.py names-all"): names_all,
    })
    result = drift_check.check_live_tool_counts(targets, runner)
    assert result["probe_deployed"] is True
    assert result["clean"] is True
    assert result["live_counts"]["conductor"] == 17


def test_check_live_tool_counts_catches_id_level_mismatch_with_equal_counts():
    """Same COUNT (17) as the real conductor role, but one real id swapped
    for another role's real id ("overview.get" replaced by architect's
    "zone.list") plus one name the current registry does not recognise at
    all -- a count-only check would miss both; this must not."""
    conductor_ids = sorted(drift_check.offline_role_tool_ids()["conductor"])
    assert "overview.get" in conductor_ids
    swapped = [tid for tid in conductor_ids if tid != "overview.get"] + ["zone.list"]
    assert len(swapped) == len(conductor_ids)
    names_all = "".join(f"conductor\t{tid.replace('.', '__')}\n" for tid in swapped)
    names_all += "conductor\tnot-a-real-tool\n"
    targets = {"vm103-dfmcp": _target(host="df", destination_root_raw="/opt/df/dfmcp-smoke")}
    runner = dc.FakeRunner({
        ("df", "test -f /opt/df/dfmcp-smoke/scripts/ops/mcpcall.py && echo present || echo absent"): "present\n",
        ("df", "cd /opt/df/dfmcp-smoke && .venv/bin/python scripts/ops/mcpcall.py names-all"): names_all,
    })
    result = drift_check.check_live_tool_counts(targets, runner)
    assert result["probe_deployed"] is True
    assert result["clean"] is False
    m = result["mismatches"]["conductor"]
    assert m["offline"] == m["live"] == 17  # counts agree; ids still caught the drift
    assert m["missing_live"] == ["overview.get"]
    assert m["extra_live"] == ["zone.list"]
    assert m["unknown_live_names"] == ["not-a-real-tool"]


def test_check_live_tool_counts_role_absent_from_live_output_not_reported():
    """A role the live dump never mentions (e.g. mcpcall.py's own ROLES list
    falling behind the roster) is not itself a mismatch -- distinct from a
    role that IS reported but disagrees."""
    targets = {"vm103-dfmcp": _target(host="df", destination_root_raw="/opt/df/dfmcp-smoke")}
    runner = dc.FakeRunner({
        ("df", "test -f /opt/df/dfmcp-smoke/scripts/ops/mcpcall.py && echo present || echo absent"): "present\n",
        ("df", "cd /opt/df/dfmcp-smoke && .venv/bin/python scripts/ops/mcpcall.py names-all"): "",
    })
    result = drift_check.check_live_tool_counts(targets, runner)
    assert result["probe_deployed"] is True
    assert result["clean"] is True
    assert result["live_counts"] == {}


def test_check_live_tool_counts_no_dfmcp_target():
    result = drift_check.check_live_tool_counts({}, dc.FakeRunner({}))
    assert result["probe_deployed"] is False
    assert result["clean"] is True


# ---------------------------------------------------------------------------
# check_services
# ---------------------------------------------------------------------------


def test_check_services_reports_without_judging():
    targets = {
        "t1": _target(host="df", restart=[dc.RestartEntry(service="a.service", risk="low", why="x")]),
        "t2": _target(host="openclaw", restart=[dc.RestartEntry(service="b.service", risk="high", why="y")]),
    }
    runner = dc.FakeRunner({
        ("df", "systemctl show a.service --property=ActiveState,UnitFileState 2>&1 || true"):
            "ActiveState=active\nUnitFileState=enabled\n",
        ("openclaw", "systemctl show b.service --property=ActiveState,UnitFileState 2>&1 || true"):
            "ActiveState=inactive\nUnitFileState=disabled\n",
    })
    result = drift_check.check_services(targets, runner)
    assert result["a.service"]["active"] == "active"
    assert result["a.service"]["enabled"] == "enabled"
    assert result["b.service"]["active"] == "inactive"
    assert result["b.service"]["enabled"] == "disabled"


# ---------------------------------------------------------------------------
# write_state
# ---------------------------------------------------------------------------


def test_write_state_produces_expected_sections(tmp_path):
    report = {
        "generated_at": "2026-10-02T00:00:00Z",
        "clean": True,
        "files": {
            "sample": {"stamp": {"commit": "a" * 40}, "commits_behind_origin_main": 0,
                       "drifted_count": 0, "file_count": 1},
        },
        "live_tool_counts": {"offline_counts": {"overseer": 10}, "note": None},
        "services": {"a.service": {"host": "df", "risk": "low", "active": "active", "enabled": "enabled"}},
    }
    out_path = tmp_path / "STATE.md"
    drift_check.write_state(report, out_path)
    text = out_path.read_text(encoding="utf-8")
    assert "Deployed commit per target" in text
    assert "overseer" in text
    assert "a.service" in text
    assert "Do not hand-edit" in text


# ---------------------------------------------------------------------------
# main() end to end, FakeRunner injected
# ---------------------------------------------------------------------------


def test_main_single_target_clean_exit_zero(monkeypatch, capsys):
    head = dc.current_commit()
    real_hash = dc.sha256_at_commit(head, "agents/ROSTER.yaml")

    def fake_init():
        return dc.FakeRunner({
            ("df", "cat /opt/df/dfmcp-smoke/DEPLOYED_COMMIT 2>/dev/null || true"): f"commit={head}\n",
            ("df", "test -f /opt/df/dfmcp-smoke/scripts/ops/mcpcall.py && echo present || echo absent"): "absent\n",
            ("relay", "*"): "",
        })

    monkeypatch.setattr(dc, "SSHRunner", fake_init)

    # Build a tiny manifest with exactly one target so the fake only needs
    # to answer for files actually requested.
    tmp_manifest = {
        "vm103-dfmcp": _target(name="vm103-dfmcp", host="df", destination_root_raw="/opt/df/dfmcp-smoke",
                                paths=["agents/ROSTER.yaml"]),
    }
    monkeypatch.setattr(dc, "load_manifest", lambda path=dc.MANIFEST_PATH: tmp_manifest)

    runner = fake_init()
    runner.responses[("df", "cd /opt/df/dfmcp-smoke && sha256sum agents/ROSTER.yaml 2>&1 || true")] = \
        f"{real_hash}  agents/ROSTER.yaml\n"
    monkeypatch.setattr(dc, "SSHRunner", lambda: runner)

    rc = drift_check.main(["--target", "vm103-dfmcp"])
    out = capsys.readouterr().out
    assert "clean" in out
    assert rc == 0


def test_main_unknown_target_exits_two():
    rc = drift_check.main(["--target", "no-such-target"])
    assert rc == 2
