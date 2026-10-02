"""Offline tests for scripts/deploy.py and scripts/deploy_common.py.

No real ssh, no real git push: FakeRunner stands in for every host touch,
and git assertions run against this worktree's own real history (read-only
git plumbing only -- ls-tree, show, rev-parse, merge-base --is-ancestor --
never a push, a branch change, or a write).
"""
from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import pytest  # noqa: E402

import deploy_common as dc  # noqa: E402
import deploy as deploy_mod  # noqa: E402


# ---------------------------------------------------------------------------
# manifest loading
# ---------------------------------------------------------------------------


def write_manifest(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "manifest.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def test_real_manifest_loads_and_has_known_targets():
    targets = dc.load_manifest()
    assert "vm103-dfmcp" in targets
    assert "vm103-dfhack-scripts" in targets
    assert targets["vm103-dfmcp"].host == "df"


def test_real_manifest_high_risk_restarts_have_a_why():
    targets = dc.load_manifest()
    for target in targets.values():
        for entry in target.restart:
            if entry.is_high_risk:
                assert entry.why.strip(), f"{target.name}/{entry.service} has no 'why' for its high risk"


def test_load_manifest_rejects_bad_host(tmp_path):
    path = write_manifest(tmp_path, """
        targets:
          bad:
            host: not-a-real-host
            destination_root: /tmp/x
            paths: []
    """)
    with pytest.raises(dc.ManifestError):
        dc.load_manifest(path)


def test_load_manifest_rejects_bad_risk(tmp_path):
    path = write_manifest(tmp_path, """
        targets:
          t:
            host: df
            destination_root: /tmp/x
            paths: []
            restart:
              - {service: foo.service, risk: medium}
    """)
    with pytest.raises(dc.ManifestError):
        dc.load_manifest(path)


def test_destination_root_resolves_env_placeholder():
    target = dc.Target(name="t", host="openclaw", destination_root_raw="${SOME_ROOT}", paths=["x/"])
    assert target.destination_root({"SOME_ROOT": "/opt/thing"}) == "/opt/thing"


def test_destination_root_missing_env_var_raises():
    target = dc.Target(name="t", host="openclaw", destination_root_raw="${MISSING}", paths=["x/"])
    with pytest.raises(dc.ManifestError):
        target.destination_root({})


def test_destination_root_literal_path_passes_through():
    target = dc.Target(name="t", host="df", destination_root_raw="/opt/df/dfmcp-smoke", paths=["x/"])
    assert target.destination_root({}) == "/opt/df/dfmcp-smoke"


# ---------------------------------------------------------------------------
# git plumbing (read-only against this real worktree)
# ---------------------------------------------------------------------------


def test_is_tree_clean_reflects_real_status():
    # Whatever the state is, it must match git status --porcelain directly,
    # not assert a fixed value (this worktree is mid-stream and legitimately
    # has commits of its own).
    import subprocess
    porcelain = subprocess.run(
        ["git", "status", "--porcelain"], cwd=dc.REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout
    assert dc.is_tree_clean() == (porcelain.strip() == "")


def test_list_files_at_commit_expands_directory():
    head = dc.current_commit()
    files = dc.list_files_at_commit(head, ["agents/"])
    assert "agents/ROSTER.yaml" in files
    assert "agents/overseer/role.md" in files


def test_apply_excludes_drops_tests_and_pycache():
    files = ["dfseries/schema.py", "dfseries/tests/test_schema.py", "dfseries/__pycache__/schema.cpython.pyc"]
    kept = dc.apply_excludes(files, ["**/tests/", "**/__pycache__/"])
    assert kept == ["dfseries/schema.py"]


def test_apply_excludes_drops_sqlite_glob():
    files = ["dfqueue/store.py", "dfqueue/Uniboslan.sqlite3"]
    kept = dc.apply_excludes(files, ["dfqueue/*.sqlite3"])
    assert kept == ["dfqueue/store.py"]


def test_target_files_matches_real_manifest_target():
    targets = dc.load_manifest()
    head = dc.current_commit()
    files = dc.target_files(targets["vm103-dfmcp"], head)
    assert any(f == "agents/ROSTER.yaml" for f in files)
    assert all("/tests/" not in f for f in files)
    assert all(not f.endswith(".sqlite3") for f in files)


def test_sha256_at_commit_matches_known_file():
    import hashlib
    head = dc.current_commit()
    digest = dc.sha256_at_commit(head, "agents/ROSTER.yaml")
    import subprocess
    raw = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "show", f"{head}:agents/ROSTER.yaml"],
        cwd=dc.REPO_ROOT, capture_output=True, check=True,
    ).stdout
    assert digest == hashlib.sha256(raw).hexdigest()


def test_is_ancestor_of_origin_main_true_for_origin_main_itself():
    # origin/main is trivially its own ancestor.
    out = dc.git("rev-parse", "origin/main")
    assert dc.is_ancestor_of_origin_main(out) is True


def test_commits_behind_returns_none_for_non_ancestor(monkeypatch):
    monkeypatch.setattr(dc, "is_ancestor_of_origin_main", lambda commit, cwd=dc.REPO_ROOT: False)
    assert dc.commits_behind_origin_main("deadbeef") is None


# ---------------------------------------------------------------------------
# FakeRunner
# ---------------------------------------------------------------------------


def test_fake_runner_records_calls_and_returns_configured_response():
    runner = dc.FakeRunner({("df", "echo hi"): "hi\n"})
    out = runner.run("df", "echo hi")
    assert out == "hi\n"
    assert runner.calls == [("df", "echo hi", None)]


def test_fake_runner_raises_for_unconfigured_call():
    runner = dc.FakeRunner({})
    with pytest.raises(dc.SSHError):
        runner.run("df", "echo hi")


# ---------------------------------------------------------------------------
# deploy.py: planning and the gates
# ---------------------------------------------------------------------------


def _sample_target(**overrides) -> dc.Target:
    base = dict(
        name="sample",
        host="df",
        destination_root_raw="/opt/sample",
        paths=["agents/ROSTER.yaml"],
        exclude=[],
        leave_alone=[],
        restart=[dc.RestartEntry(service="low.service", risk="low", why="ok")],
        post_deploy=[],
    )
    base.update(overrides)
    return dc.Target(**base)


def test_plan_for_target_lists_files_and_stamp():
    target = _sample_target()
    head = dc.current_commit()
    plan = deploy_mod.plan_for_target(target, head, {})
    assert plan["files"] == ["agents/ROSTER.yaml"]
    assert plan["destination_root"] == "/opt/sample"
    assert f"commit={head}" in plan["stamp_contents"]
    assert plan["low_risk_restarts"] == ["low.service"]
    assert plan["high_risk_restarts"] == []


def test_plan_for_target_separates_high_risk_restart():
    target = _sample_target(restart=[
        dc.RestartEntry(service="low.service", risk="low", why="ok"),
        dc.RestartEntry(service="risky.service", risk="high", why="read the doc first"),
    ])
    head = dc.current_commit()
    plan = deploy_mod.plan_for_target(target, head, {})
    assert plan["low_risk_restarts"] == ["low.service"]
    assert plan["high_risk_restarts"] == ["risky.service"]


def test_deploy_target_dry_run_never_calls_runner():
    target = _sample_target()
    head = dc.current_commit()
    runner = dc.FakeRunner({})
    result = deploy_mod.deploy_target(target, head, {}, runner, dry_run=True, yes=False)
    assert result["dry_run"] is True
    assert runner.calls == []


def test_deploy_target_without_yes_is_skipped_not_executed():
    target = _sample_target()
    head = dc.current_commit()
    runner = dc.FakeRunner({})
    result = deploy_mod.deploy_target(target, head, {}, runner, dry_run=False, yes=False)
    assert result["skipped"] == "no --yes"
    assert runner.calls == []


def test_deploy_target_real_run_restarts_only_low_risk():
    target = _sample_target(restart=[
        dc.RestartEntry(service="low.service", risk="low", why="ok"),
        dc.RestartEntry(service="risky.service", risk="high", why="read the doc first"),
    ])
    head = dc.current_commit()
    runner = dc.FakeRunner({
        ("df", "mkdir -p /opt/sample"): "",
        ("df", "*"): "",  # catches the tar-xf and cat-stamp calls below
    })
    # Give the tar/stamp/restart calls explicit, exact-match responses too,
    # since FakeRunner's "*" fallback only matches when the exact key misses.
    runner.responses[("df", "tar xf - -C /opt/sample")] = ""
    result = deploy_mod.deploy_target(target, head, {}, runner, dry_run=False, yes=True)
    assert result["deployed"] is True
    restart_calls = [c for c in runner.calls if "systemctl restart" in c[1]]
    assert len(restart_calls) == 1
    assert "low.service" in restart_calls[0][1]
    assert "risky.service" not in str(runner.calls)


def test_main_refuses_without_dry_run_or_yes(capsys):
    rc = deploy_mod.main(["--target", "vm103-dfmcp"])
    assert rc == 2


def test_main_refuses_dirty_tree(monkeypatch):
    monkeypatch.setattr(dc, "is_tree_clean", lambda: False)
    rc = deploy_mod.main(["--target", "vm103-dfmcp", "--dry-run"])
    assert rc == 2


def test_main_refuses_commit_not_on_origin_main(monkeypatch):
    monkeypatch.setattr(dc, "is_tree_clean", lambda: True)
    monkeypatch.setattr(dc, "is_ancestor_of_origin_main", lambda commit, cwd=dc.REPO_ROOT: False)
    rc = deploy_mod.main(["--target", "vm103-dfmcp", "--dry-run"])
    assert rc == 2


def test_main_dry_run_unknown_target(monkeypatch):
    monkeypatch.setattr(dc, "is_tree_clean", lambda: True)
    monkeypatch.setattr(dc, "is_ancestor_of_origin_main", lambda commit, cwd=dc.REPO_ROOT: True)
    rc = deploy_mod.main(["--target", "no-such-target", "--dry-run"])
    assert rc == 2


def test_build_tar_flatten_rewrites_member_names():
    import tarfile
    from io import BytesIO
    head = dc.current_commit()
    tar_bytes = deploy_mod.build_tar(head, ["agents/ROSTER.yaml", "agents/README.md"], flatten=True)
    names = tarfile.open(fileobj=BytesIO(tar_bytes), mode="r:").getnames()
    assert set(names) == {"ROSTER.yaml", "README.md"}


def test_build_tar_without_flatten_keeps_full_path():
    import tarfile
    from io import BytesIO
    head = dc.current_commit()
    tar_bytes = deploy_mod.build_tar(head, ["agents/ROSTER.yaml"], flatten=False)
    names = [n for n in tarfile.open(fileobj=BytesIO(tar_bytes), mode="r:").getnames() if n.endswith(".yaml")]
    assert names == ["agents/ROSTER.yaml"]


def test_target_remote_path_flatten_vs_default():
    flat = dc.Target(name="t", host="relay", destination_root_raw="/x", paths=["a/b.txt"], flatten=True)
    plain = dc.Target(name="t", host="relay", destination_root_raw="/x", paths=["a/b.txt"], flatten=False)
    assert flat.remote_path("web/stream/index.html") == "index.html"
    assert plain.remote_path("web/stream/index.html") == "web/stream/index.html"


def test_main_dry_run_all_targets_succeeds(monkeypatch, capsys):
    monkeypatch.setattr(dc, "is_tree_clean", lambda: True)
    monkeypatch.setattr(dc, "is_ancestor_of_origin_main", lambda commit, cwd=dc.REPO_ROOT: True)
    rc = deploy_mod.main(["--all", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "vm103-dfmcp" in out
    assert "WOULD NOT restart (high risk" in out
