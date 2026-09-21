"""`dfmcp.confidence`: the static confidence file and its loader."""

from __future__ import annotations

import pytest
import yaml

from dfmcp import confidence as c
from dfmcp.registry import load_registry


def test_the_real_file_loads_and_defaults_everything_to_medium():
    cfg = c.load_confidence()
    reg = load_registry()
    cfg.validate_against(reg.ids())
    for tool_id in reg.ids():
        got = cfg.lookup(tool_id)
        assert got.level == "medium" and got.source == "default"
        assert got.note == c.DEFAULT_NOTES["medium"]
    assert cfg.lookup("building.build", "Masons").level == "medium"


def test_level_and_kind_resolution():
    cfg = c.parse_confidence(yaml.safe_load("""
default: medium
tools:
  building.build:
    level: low
    kinds:
      Masons: full
      Still: {level: medium, note: "brew needs barrels"}
  building.find: full
"""))
    assert cfg.lookup("building.build").level == "low"
    assert cfg.lookup("building.build", "Masons") == c.Confidence("full", c.DEFAULT_NOTES["full"], "kind")
    assert cfg.lookup("building.build", "Still").note == "brew needs barrels"
    # A kind with no entry inherits the tool's level.
    assert cfg.lookup("building.build", "Kennel") == c.Confidence("low", c.DEFAULT_NOTES["low"], "tool")
    assert cfg.lookup("building.find", "Kennel").level == "full"
    assert cfg.lookup("something.else").source == "default"


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("default: high\ntools: {}", "not one of"),
        ("tools: {}", "'default' is required"),
        ("default: medium\ntools:\n  a.b: excellent", "not one of"),
        ("default: medium\ntools:\n  a.b:\n    kinds:\n      X: perfect", "not one of"),
        ("default: medium\nlevels: {}", "unknown top-level"),
        ("default: medium\ntools:\n  a.b: {level: full, bogus: 1}", "unknown key"),
        ("default: medium\ntools: [a]", "must be a mapping"),
        ("default: medium\ntools:\n  a.b: {level: full, kinds: [X]}", "kinds must be a mapping"),
        ("- just\n- a list", "mapping at the top level"),
    ],
)
def test_loader_refuses_bad_files(text, fragment):
    with pytest.raises(c.ConfidenceError, match=fragment):
        c.parse_confidence(yaml.safe_load(text))


def test_an_unknown_tool_id_is_refused_against_the_registry():
    cfg = c.parse_confidence({"default": "medium", "tools": {"nonsense.tool": "full"}})
    with pytest.raises(c.ConfidenceError, match="nonsense.tool"):
        cfg.validate_against(["building.build"])


def test_missing_and_invalid_yaml_files_are_errors(tmp_path):
    with pytest.raises(c.ConfidenceError, match="not found"):
        c.load_confidence(tmp_path / "nope.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("default: [unclosed", encoding="utf-8")
    with pytest.raises(c.ConfidenceError, match="not valid YAML"):
        c.load_confidence(bad)


def test_the_shared_legend_says_what_the_design_requires():
    from pathlib import Path

    text = (Path(c.REPO_ROOT) / "agents" / "CONFIDENCE-LEGEND.md").read_text(encoding="utf-8")
    lowered = text.lower()
    # Both meanings of confidence, both named levels, the proposed-gotcha rule.
    assert "works" in lowered and "intuitive" in lowered
    assert "**full**" in text and "**medium**" in text
    assert "proposed" in lowered and "did_not_work" in text and "worked" in text
    assert "gotchas.get" in text and "gotchas.write" in text
    assert "—" not in text and "–" not in text  # no em or en dashes
    assert len(text.split()) < 450  # short enough to include in every role prompt
