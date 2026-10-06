"""The shipped `action_tools.yaml` flags (read from the real file)."""
import yaml

from conftest import SHIPPED_ACTION_TOOLS_PATH


def test_shipped_routing_flags():
    raw = yaml.safe_load(SHIPPED_ACTION_TOOLS_PATH.read_text(encoding="utf-8"))
    groups = raw["groups"]
    assert groups["rooms"]["routed"] is True
    assert groups["rooms"]["frozen"] is False
    for name, group in groups.items():
        if name != "rooms":
            assert group["routed"] is False, name
