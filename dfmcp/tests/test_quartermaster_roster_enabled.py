"""Proves `agents/quartermaster/`'s real, committed `tools.yaml`, `role.md`
and `model.yaml` would load cleanly under `dfmcp.roles` once
`agents/ROSTER.yaml` flips the role's `enabled` flag to `true` --
`handoffs/2026-09-22-loop-queue-quartermaster.md`'s own requirement ("Make
sure `dfmcp/roles.py` validation would pass once it is flipped"), and
explicitly NOT this stream's job to flip (`agents/ROSTER.yaml` is another
stream's file, flipped by the orchestrator at merge).

Builds a synthetic `ROSTER.yaml` enabling `quartermaster` (plus the real
`sole_writer`, `overseer`, since `queue.rule`/`queue.executed` are
`sole_writer_only` and `load_roster` needs a real sole-writer role loaded
to resolve that), pointing at COPIES of the REAL, on-disk `agents/overseer/`
and `agents/quartermaster/` directories -- never synthetic stand-ins -- so
a pass here is a genuine proof about today's actual files, not a tautology
against a fixture built to pass.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from dfqueue import schema as dfqueue_schema

from dfmcp.doctrine_tools import NATIVE_TOOLS as DOCTRINE_NATIVE_TOOLS
from dfmcp.gotchas_tools import NATIVE_TOOLS as GOTCHAS_NATIVE_TOOLS
from dfmcp.queue_tools import NATIVE_TOOLS as QUEUE_NATIVE_TOOLS
from dfmcp.registry import load_registry
from dfmcp.roles import load_roster
from dfmcp.series_tools import NATIVE_TOOLS as SERIES_NATIVE_TOOLS

REPO_AGENTS_DIR = Path(__file__).resolve().parents[2] / "agents"


@pytest.fixture(scope="module")
def registry():
    return load_registry(native_tools={
        **QUEUE_NATIVE_TOOLS, **DOCTRINE_NATIVE_TOOLS, **SERIES_NATIVE_TOOLS,
        **GOTCHAS_NATIVE_TOOLS,
    })


def _agents_dir_with_quartermaster_enabled(tmp_path: Path) -> Path:
    agents = tmp_path / "agents"
    agents.mkdir()

    doc = {
        "schema_version": 1,
        "sole_writer": "overseer",
        "roles": {
            "overseer": {"enabled": True, "dir": "overseer", "kind": "actor"},
            "quartermaster": {"enabled": True, "dir": "quartermaster", "kind": "advisor"},
        },
    }
    (agents / "ROSTER.yaml").write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    # The REAL, committed directories -- copied, not synthesised.
    shutil.copytree(REPO_AGENTS_DIR / "overseer", agents / "overseer")
    shutil.copytree(REPO_AGENTS_DIR / "quartermaster", agents / "quartermaster")

    return agents


def test_quartermaster_loads_cleanly_once_enabled(registry, tmp_path):
    agents = _agents_dir_with_quartermaster_enabled(tmp_path)

    roster = load_roster(registry, agents_dir=agents)

    assert "quartermaster" in roster.roles
    qm = roster.roles["quartermaster"]

    assert {"queue.propose", "queue.pass", "queue.ask"} <= set(qm.write)
    for tool_id in qm.write:
        assert not registry.get(tool_id).mutates, f"quartermaster holds mutating {tool_id}"

    for read_id in ("orders.list", "workjob.list", "farm.list", "stocks.availability"):
        assert qm.allows(read_id), f"quartermaster should hold read {read_id}"

    for denied in ("orders.create", "workjob.queue", "farm.set-crop", "labor.set-labor"):
        assert not qm.allows(denied), f"quartermaster must not hold {denied}"


def test_quartermaster_check_reads_as_granted_not_a_refusal(registry, tmp_path):
    agents = _agents_dir_with_quartermaster_enabled(tmp_path)
    roster = load_roster(registry, agents_dir=agents)

    ok, why = roster.check("quartermaster", "queue.propose")
    assert ok and "granted" in why

    ok, why = roster.check("quartermaster", "orders.create")
    assert not ok


def test_quartermaster_proposal_type_vocabulary_matches_the_schema():
    """Belt and braces, independent of the roster-loading proof above:
    dfqueue.schema.TYPE_VOCAB_BY_ROLE["quartermaster"] (this stream's own
    change) is exactly the MVP's three types named in role.md and
    tools.yaml's own `queue.propose` note."""
    assert dfqueue_schema.TYPE_VOCAB_BY_ROLE["quartermaster"] == (
        dfqueue_schema.WORK_ORDER, dfqueue_schema.CROP_PLAN, dfqueue_schema.STOCK_TARGET,
    )
