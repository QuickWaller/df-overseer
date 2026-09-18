"""Direct, transport-free tests of `dfmcp.doctrine_tools`, in the same style
as `dfmcp/tests/test_queue_tools.py`: this module imports nothing from `mcp`
(the SDK), only `dfmcp.doctrine_tools` and `doctrine.validate` directly, so
it runs under the ambient environment too, not only `.venv-dfmcp`.

Fixture doctrine data is hand-built rather than reused from the real
`doctrine/seed.yaml`, so these tests do not silently break (or silently stop
proving anything) the day someone adds or edits a real entry -- except for
`test_the_real_doctrine_file_loads_and_validates`, which is a deliberate
smoke test against the real file, since a broken `doctrine/seed.yaml` should
fail loudly in CI, not just at deploy time.

The property under test throughout, per this stream's brief: **status and
sources survive unflattened**, an unknown id or topic is refused rather than
returning an empty list, and a refuted entry is never silently dropped nor
presented as current guidance.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dfmcp import doctrine_tools
from doctrine import validate as doctrine_validate

pytestmark = pytest.mark.asyncio

# --------------------------------------------------------------------------
# Fixture doctrine data
# --------------------------------------------------------------------------

_INSTALL = doctrine_validate.INSTALL_VERSION  # "53.16"

_PRIOR_FOOD = {
    "id": "a-prior-food",
    "scope": "universal",
    "status": "prior",
    "topics": ["food"],
    "sources": [
        {"kind": "user", "ref": "own play", "describes": "unknown", "read": "recalled", "accessed": "2026-09-17"},
    ],
    "statement": "A prior statement about food.",
}

_VERIFIED_FOOD_DRINK = {
    "id": "b-verified-food-drink",
    "scope": "universal",
    "status": "verified",
    "topics": ["food", "drink"],
    "sources": [
        {"kind": "live-read", "ref": "plotinfo.kitchen, testfort", "describes": _INSTALL, "read": "opened", "accessed": "2026-09-17"},
    ],
    "statement": "A verified statement about food and drink.",
}

_REFUTED_DRINK = {
    "id": "c-refuted-drink",
    "scope": "universal",
    "status": "refuted",
    "topics": ["drink"],
    "sources": [
        {"kind": "user", "ref": "own play", "describes": "unknown", "read": "recalled"},
    ],
    "statement": "A refuted statement about drink, kept as a record.",
    "note": "Kept so the mistake is not remade.",
}

_PRIOR_WATER = {
    "id": "d-prior-water",
    "scope": "site",
    "status": "prior",
    "topics": ["water"],
    "sources": [
        {"kind": "wiki", "ref": "some wiki page", "describes": "unknown", "read": "search-summary", "accessed": "2026-09-01"},
    ],
    "statement": "A prior statement about water.",
}

_ALL_FIXTURE_ENTRIES = [_PRIOR_FOOD, _VERIFIED_FOOD_DRINK, _REFUTED_DRINK, _PRIOR_WATER]

# Sanity check the fixture itself is valid against the real validator, so a
# test failure below is never actually a bug in this file's own fixture data.
assert doctrine_validate.validate(_ALL_FIXTURE_ENTRIES) == []


def _write_doctrine(tmp_path: Path, entries) -> Path:
    path = tmp_path / "seed.yaml"
    path.write_text(yaml.safe_dump(entries, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture
def doctrine_path(tmp_path) -> Path:
    return _write_doctrine(tmp_path, _ALL_FIXTURE_ENTRIES)


async def _call(tool_id, role, arguments, *, doctrine_path):
    return await doctrine_tools.call(tool_id, role, arguments, doctrine_path=doctrine_path)


# ==========================================================================
# By id
# ==========================================================================


class TestById:
    async def test_returns_the_entry_with_status_and_sources_unflattened(self, doctrine_path):
        text, structured = await _call(
            doctrine_tools.DOCTRINE_GET, "consultant", {"id": "b-verified-food-drink"},
            doctrine_path=doctrine_path,
        )
        entry = structured["entry"]
        assert entry["id"] == "b-verified-food-drink"
        assert entry["status"] == "verified"
        # Sources survive as a list of full dicts, not a flattened string.
        assert isinstance(entry["sources"], list)
        assert entry["sources"][0] == {
            "kind": "live-read", "ref": "plotinfo.kitchen, testfort",
            "describes": _INSTALL, "read": "opened", "accessed": "2026-09-17",
        }
        assert 'status="verified"' in text
        assert "<source " in text
        assert 'kind="live-read"' in text

    async def test_a_prior_entry_carries_an_explicit_warning_in_the_text_form(self, doctrine_path):
        text, structured = await _call(
            doctrine_tools.DOCTRINE_GET, "consultant", {"id": "a-prior-food"},
            doctrine_path=doctrine_path,
        )
        assert structured["entry"]["status"] == "prior"
        assert "<warning>PRIOR" in text

    async def test_a_refuted_entry_is_returned_not_dropped_and_is_visibly_refuted(self, doctrine_path):
        """The whole point: a by-id lookup never silently drops a refuted
        entry, and it must be unmistakable, not merely a status string
        buried in a larger payload."""
        text, structured = await _call(
            doctrine_tools.DOCTRINE_GET, "consultant", {"id": "c-refuted-drink"},
            doctrine_path=doctrine_path,
        )
        assert structured["entry"]["status"] == "refuted"
        assert 'status="refuted"' in text
        assert "<warning>REFUTED" in text
        assert "do not treat as current guidance" in text.lower()

    async def test_verified_entry_carries_no_warning(self, doctrine_path):
        text, _structured = await _call(
            doctrine_tools.DOCTRINE_GET, "consultant", {"id": "b-verified-food-drink"},
            doctrine_path=doctrine_path,
        )
        assert "<warning>" not in text

    async def test_unknown_id_is_an_error_not_a_miss(self, doctrine_path):
        with pytest.raises(doctrine_tools.DoctrineToolError) as exc:
            await _call(
                doctrine_tools.DOCTRINE_GET, "consultant", {"id": "no-such-id"},
                doctrine_path=doctrine_path,
            )
        assert "no-such-id" in str(exc.value)


# ==========================================================================
# By topic
# ==========================================================================


class TestByTopic:
    async def test_returns_every_entry_filed_under_the_topic(self, doctrine_path):
        _text, structured = await _call(
            doctrine_tools.DOCTRINE_GET, "consultant", {"topic": "food"},
            doctrine_path=doctrine_path,
        )
        ids = {e["id"] for e in structured["entries"]}
        assert ids == {"a-prior-food", "b-verified-food-drink"}
        assert structured["returned_count"] == 2
        assert structured["omitted_refuted_count"] == 0

    async def test_refuted_entries_are_omitted_by_default_and_the_omission_is_stated(self, doctrine_path):
        text, structured = await _call(
            doctrine_tools.DOCTRINE_GET, "consultant", {"topic": "drink"},
            doctrine_path=doctrine_path,
        )
        ids = {e["id"] for e in structured["entries"]}
        assert ids == {"b-verified-food-drink"}
        assert "c-refuted-drink" not in ids
        assert structured["omitted_refuted_count"] == 1
        # The text form must say so, not just leave a number in structured data.
        assert 'omitted_refuted="1"' in text
        assert "1 refuted entry" in text

    async def test_include_refuted_returns_them_still_clearly_labelled(self, doctrine_path):
        text, structured = await _call(
            doctrine_tools.DOCTRINE_GET, "consultant",
            {"topic": "drink", "include_refuted": True}, doctrine_path=doctrine_path,
        )
        ids = {e["id"] for e in structured["entries"]}
        assert ids == {"b-verified-food-drink", "c-refuted-drink"}
        assert structured["omitted_refuted_count"] == 0
        assert 'status="refuted"' in text
        assert "<warning>REFUTED" in text

    async def test_a_topic_with_zero_entries_is_a_valid_empty_result_not_an_error(self, doctrine_path):
        """"health" is a real, closed-vocabulary topic that happens to have
        no fixture entries -- distinct from an unknown topic string, which
        must error instead (see TestByTopic below)."""
        _text, structured = await _call(
            doctrine_tools.DOCTRINE_GET, "consultant", {"topic": "health"},
            doctrine_path=doctrine_path,
        )
        assert structured["entries"] == []
        assert structured["returned_count"] == 0

    async def test_unknown_topic_is_an_error_never_an_empty_list(self, doctrine_path):
        with pytest.raises(doctrine_tools.DoctrineToolError) as exc:
            await _call(
                doctrine_tools.DOCTRINE_GET, "consultant", {"topic": "not-a-real-topic"},
                doctrine_path=doctrine_path,
            )
        assert "not-a-real-topic" in str(exc.value)


# ==========================================================================
# The topic index
# ==========================================================================


class TestTopicIndex:
    async def test_lists_every_closed_topic_including_ones_with_zero_entries(self, doctrine_path):
        _text, structured = await _call(
            doctrine_tools.DOCTRINE_GET, "consultant", {}, doctrine_path=doctrine_path,
        )
        assert set(structured["topics"]) == doctrine_validate.TOPICS
        assert structured["topics"]["food"]["count"] == 2
        assert structured["topics"]["health"]["count"] == 0

    async def test_status_breakdown_is_never_hidden_even_for_refuted(self, doctrine_path):
        _text, structured = await _call(
            doctrine_tools.DOCTRINE_GET, "consultant", {}, doctrine_path=doctrine_path,
        )
        drink = structured["topics"]["drink"]
        assert drink["count"] == 2
        assert drink["by_status"] == {"prior": 0, "verified": 1, "refuted": 1}


# ==========================================================================
# Argument validation
# ==========================================================================


class TestArguments:
    async def test_id_and_topic_together_is_rejected(self, doctrine_path):
        with pytest.raises(doctrine_tools.DoctrineToolError):
            await _call(
                doctrine_tools.DOCTRINE_GET, "consultant",
                {"id": "a-prior-food", "topic": "food"}, doctrine_path=doctrine_path,
            )

    async def test_unexpected_argument_is_rejected(self, doctrine_path):
        with pytest.raises(doctrine_tools.DoctrineToolError) as exc:
            await _call(
                doctrine_tools.DOCTRINE_GET, "consultant",
                {"role": "overseer"}, doctrine_path=doctrine_path,
            )
        assert "role" in str(exc.value)

    async def test_wrong_type_for_id_is_rejected(self, doctrine_path):
        with pytest.raises(doctrine_tools.DoctrineToolError):
            await _call(
                doctrine_tools.DOCTRINE_GET, "consultant", {"id": 123},
                doctrine_path=doctrine_path,
            )


# ==========================================================================
# Loading failures are refusals, never a silent empty result
# ==========================================================================


class TestLoadFailures:
    async def test_missing_doctrine_file_is_refused_loudly(self, tmp_path):
        missing = tmp_path / "does-not-exist.yaml"
        with pytest.raises(doctrine_tools.DoctrineToolError) as exc:
            await _call(
                doctrine_tools.DOCTRINE_GET, "consultant", {}, doctrine_path=missing,
            )
        assert "not found" in str(exc.value)
        assert str(missing) in str(exc.value)

    async def test_invalid_doctrine_file_fails_the_real_validator_loudly(self, tmp_path):
        """A doctrine file that would fail doctrine/validate.py's own
        validate() -- here, a verified entry with no describes-53.16
        source -- must refuse to serve anything, never silently drop the
        bad entry and serve the rest."""
        bad_entry = dict(_VERIFIED_FOOD_DRINK)
        bad_entry["sources"] = [
            {"kind": "wiki", "ref": "some page", "describes": "unknown", "read": "search-summary"},
        ]
        path = _write_doctrine(tmp_path, [bad_entry])
        with pytest.raises(doctrine_tools.DoctrineToolError) as exc:
            await _call(doctrine_tools.DOCTRINE_GET, "consultant", {}, doctrine_path=path)
        assert "validator" in str(exc.value)

    async def test_not_yaml_at_all_is_refused_loudly(self, tmp_path):
        path = tmp_path / "seed.yaml"
        path.write_text("{not: valid: yaml: [", encoding="utf-8")
        with pytest.raises(doctrine_tools.DoctrineToolError):
            await _call(doctrine_tools.DOCTRINE_GET, "consultant", {}, doctrine_path=path)


# ==========================================================================
# JSON-safety: dates must not leak a non-serialisable datetime.date
# ==========================================================================


class TestJsonSafety:
    async def test_an_unquoted_iso_date_in_accessed_is_returned_as_a_string(self, tmp_path):
        """seed.yaml's real `accessed:` lines are usually unquoted ISO
        dates, which PyYAML parses into datetime.date -- not
        JSON-serialisable for MCP structuredContent. `yaml.safe_dump` of a
        plain Python `str` re-quotes it on the way out (PyYAML protects
        against exactly this ambiguity), so the fixture entry needs a real
        `datetime.date` object to reproduce seed.yaml's actual on-disk
        shape (an unquoted scalar) rather than round-tripping a string."""
        import datetime

        entry = {**_PRIOR_FOOD, "sources": [{**_PRIOR_FOOD["sources"][0], "accessed": datetime.date(2026, 9, 17)}]}
        path = _write_doctrine(tmp_path, [entry])

        # Confirm the fixture really does parse accessed as a date object,
        # so this test is proving something real rather than vacuously
        # passing on an already-string value.
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(raw[0]["sources"][0]["accessed"], datetime.date)

        _text, structured = await _call(
            doctrine_tools.DOCTRINE_GET, "consultant", {"id": "a-prior-food"},
            doctrine_path=path,
        )
        accessed = structured["entry"]["sources"][0]["accessed"]
        assert isinstance(accessed, str)
        assert accessed == "2026-09-17"


# ==========================================================================
# The real doctrine/seed.yaml, as a smoke test
# ==========================================================================


class TestRealDoctrineFile:
    async def test_the_real_doctrine_file_loads_and_validates(self):
        """Not a fixture: the actual doctrine/seed.yaml this tool will serve
        in production. Must load without DoctrineToolError -- if this ever
        fails, doctrine/seed.yaml itself has drifted invalid (the
        doctrine/validate.py test suite should already have caught that,
        but this proves the exact path doctrine.get takes, end to end)."""
        _text, structured = await _call(
            doctrine_tools.DOCTRINE_GET, "consultant", {},
            doctrine_path=doctrine_tools.DEFAULT_DOCTRINE_PATH,
        )
        assert sum(t["count"] for t in structured["topics"].values()) > 0

    async def test_default_doctrine_path_points_at_the_real_file(self):
        assert doctrine_tools.DEFAULT_DOCTRINE_PATH.is_file()
        assert doctrine_tools.DEFAULT_DOCTRINE_PATH.name == "seed.yaml"


# ==========================================================================
# Roster wiring: the real registry + roster, per-role grant/withhold
# ==========================================================================


class TestRosterWiring:
    """Proves the deliberate per-role choice recorded in
    agents/*/tools.yaml actually holds, through the real registry/roster
    boundary -- not just that this module's own functions work in
    isolation."""

    @pytest.fixture(scope="class")
    def registry(self):
        from dfmcp.queue_tools import NATIVE_TOOLS as QUEUE_NATIVE_TOOLS
        from dfmcp.registry import load_registry
        from dfmcp.series_tools import NATIVE_TOOLS as SERIES_NATIVE_TOOLS

        # SERIES_NATIVE_TOOLS merged in too, added
        # handoffs/2026-09-19-series-mcp-tools.md: agents/overseer/tools.yaml
        # and agents/consultant/tools.yaml now grant series.* ids, which
        # roles.py rule 1 requires to exist in the registry -- load_roster
        # below would otherwise fail to load the real roster.
        return load_registry(
            native_tools={**QUEUE_NATIVE_TOOLS, **doctrine_tools.NATIVE_TOOLS, **SERIES_NATIVE_TOOLS}
        )

    @pytest.fixture(scope="class")
    def roster(self, registry):
        from dfmcp.roles import load_roster

        return load_roster(registry)

    # `async def` throughout this class, with no actual `await`, solely so
    # the module-level `pytestmark = pytest.mark.asyncio` above does not
    # warn about a sync test carrying an asyncio mark it does not need.

    async def test_consultant_is_granted(self, roster):
        allowed, _reason = roster.check("consultant", doctrine_tools.DOCTRINE_GET)
        assert allowed

    async def test_architect_is_withheld(self, roster):
        allowed, reason = roster.check("architect", doctrine_tools.DOCTRINE_GET)
        assert not allowed
        assert "doctrine" in reason.lower() or "allowlist" in reason.lower()

    async def test_overseer_is_withheld(self, roster):
        allowed, _reason = roster.check("overseer", doctrine_tools.DOCTRINE_GET)
        assert not allowed

    async def test_doctrine_get_does_not_mutate_and_is_not_sole_writer_only(self, registry):
        tool = registry.get(doctrine_tools.DOCTRINE_GET)
        assert tool.mutates is False
        assert tool.sole_writer_only is False

    async def test_doctrine_get_carries_no_knowledge_scope(self, registry):
        """Deliberate, per this module's docstring -- not an omission. A
        missing attribute is what keeps roles.py rule 7 (no role may hold
        an `omniscient` tool) uninterested in this tool, exactly like
        dfmcp.queue_tools's own native tools."""
        tool = registry.get(doctrine_tools.DOCTRINE_GET)
        assert getattr(tool, "knowledge_scope", None) is None
