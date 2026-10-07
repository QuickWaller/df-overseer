"""Every tool call written into conductor/policy.yaml (alert reads and any
other `{tool: ..., args: {...}}` mapping) must use argument names that exist
in that tool's input schema (found live 2026-10-07: upper-case argument names
in a policy read were rejected by the server, which accepts the lower-case
schema names). The check walks the YAML generically, so a new entry anywhere
in the file is covered with no test change."""

from pathlib import Path

import pytest
import yaml

from conductor.policy import DEFAULT_POLICY_PATH
from dfmcp.registry import load_registry
from dfmcp.tools import _input_schema

REGISTRY = load_registry()


def find_calls(node, path="policy"):
    """Yield (path, tool_id, args) for every mapping with `tool` and `args`."""
    if isinstance(node, dict):
        if isinstance(node.get("tool"), str) and isinstance(node.get("args"), dict):
            yield path, node["tool"], node["args"]
        for k, v in node.items():
            yield from find_calls(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from find_calls(v, f"{path}[{i}]")


def arg_problems(tool_id, args, registry=REGISTRY):
    """Why this call's args do not fit the tool's schema, or []."""
    if tool_id not in registry:
        return [f"unknown tool {tool_id!r}"]
    props = _input_schema(registry.get(tool_id)).get("properties", {})
    return [
        f"{tool_id}: argument {name!r} is not in its schema {sorted(props)}"
        for name in args if name not in props
    ]


def _calls():
    data = yaml.safe_load(Path(DEFAULT_POLICY_PATH).read_text(encoding="utf-8"))
    return list(find_calls(data))


def test_policy_has_tool_calls_to_check():
    assert len(_calls()) >= 3


@pytest.mark.parametrize("path,tool_id,args", _calls())
def test_policy_call_args_exist_in_tool_schema(path, tool_id, args):
    assert arg_problems(tool_id, args) == [], path


def test_checker_catches_a_wrong_or_upper_case_arg_name():
    # Proves the check can fail: the real zone.list call with one name broken.
    assert arg_problems("zone.list", {"kind_filter": ""}) == []
    assert arg_problems("zone.list", {"KIND_FILTER": ""})
    assert arg_problems("zone.list", {"kind_filtr": ""})
    assert arg_problems("no.such-tool", {})
