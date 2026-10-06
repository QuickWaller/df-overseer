"""Repo-wide test isolation for the routing data.

`dfqueue/action_tools.yaml` carries the operator's live `routed` flags, which
change at each cutover. Tests that are not about a particular flag state must
not move with it, so every test runs against a copy with every group unrouted
(and unfrozen); a test that wants a state sets its own through
`monkeypatch.setattr(routing, "ACTION_TOOLS_PATH", ...)`, which wins over this
default. `test_shipped_routing_flags` reads the real file.
"""
import pytest
import yaml

from dfqueue import routing

SHIPPED_ACTION_TOOLS_PATH = routing.ACTION_TOOLS_PATH


@pytest.fixture(autouse=True)
def _unrouted_action_tools(tmp_path_factory, monkeypatch):
    raw = yaml.safe_load(SHIPPED_ACTION_TOOLS_PATH.read_text(encoding="utf-8"))
    for group in raw["groups"].values():
        group["routed"] = False
        group["frozen"] = False
    path = tmp_path_factory.mktemp("routing") / "action_tools.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    monkeypatch.setattr(routing, "ACTION_TOOLS_PATH", path)
