"""Unit tests for `doctrine.validate` against small inline fixtures, plus a
check that the real `doctrine/seed.yaml` validates clean.

Follows `dfqueue/tests/test_schema.py`'s pattern: a builder returns a
minimal entry (and source) that validates clean, and each negative test
breaks exactly one thing and asserts on the specific error it should
produce, not just "errors is non-empty".
"""

from __future__ import annotations

from doctrine.validate import DEFAULT_PATH, validate


def _source(**overrides) -> dict:
    source = {
        "kind": "live-read",
        "ref": "plotinfo.kitchen, some fort",
        "describes": "53.16",
        "read": "opened",
    }
    source.update(overrides)
    return source


def _entry(**overrides) -> dict:
    entry = {
        "id": "test-entry",
        "scope": "universal",
        "status": "prior",
        "topics": ["food"],
        "sources": [_source()],
        "statement": "A statement.",
    }
    entry.update(overrides)
    return entry


def _errors_mentioning(errors: list[str], substring: str) -> list[str]:
    return [e for e in errors if substring in e]


# ---- the real file ------------------------------------------------------


def test_real_seed_yaml_validates_clean():
    assert validate(DEFAULT_PATH) == []


# ---- a valid fixture entry validates clean, as a sanity check on the -----
# ---- builders themselves -------------------------------------------------


def test_valid_entry_validates_clean():
    assert validate([_entry()]) == []


# ---- the verified rule ----------------------------------------------------


def test_verified_with_only_wiki_sources_is_refused():
    entry = _entry(
        status="verified",
        sources=[_source(kind="wiki", describes="unknown", read="unrecorded")],
    )
    errors = validate([entry])
    assert _errors_mentioning(errors, "status is 'verified'")


def test_verified_live_read_describing_unknown_is_refused():
    entry = _entry(
        status="verified",
        sources=[_source(kind="live-read", describes="unknown")],
    )
    errors = validate([entry])
    assert _errors_mentioning(errors, "status is 'verified'")


def test_verified_live_read_describing_install_version_passes():
    entry = _entry(
        status="verified",
        sources=[_source(kind="live-read", describes="53.16")],
    )
    assert validate([entry]) == []


def test_verified_game_data_describing_install_version_passes():
    entry = _entry(
        status="verified",
        sources=[_source(kind="game-data", describes="53.16")],
    )
    assert validate([entry]) == []


# ---- field-level checks ---------------------------------------------------


def test_bad_topic_is_refused():
    entry = _entry(topics=["gardening"])
    errors = validate([entry])
    assert _errors_mentioning(errors, "test-entry.topics: 'gardening' is not one of")


def test_material_topic_is_accepted():
    # Added 2026-09-18 alongside the material-policy doctrine entries
    # (bands, buckets, migration headroom, wear, durability): none of the
    # older topics fit a goods-management policy that isn't about one
    # specific consumable, so this is a deliberate vocabulary addition, not
    # a loosened check.
    entry = _entry(topics=["material"])
    assert validate([entry]) == []


def test_bad_read_value_is_refused():
    entry = _entry(sources=[_source(read="skimmed")])
    errors = validate([entry])
    assert _errors_mentioning(errors, "sources[0].read: 'skimmed' is not one of")


def test_missing_sources_is_refused():
    entry = _entry()
    del entry["sources"]
    errors = validate([entry])
    assert _errors_mentioning(errors, "test-entry.sources: required field is missing")


def test_duplicate_id_is_refused():
    entry_a = _entry(id="dup-id")
    entry_b = _entry(id="dup-id")
    errors = validate([entry_a, entry_b])
    assert _errors_mentioning(errors, "duplicate id 'dup-id'")


def test_unknown_top_level_key_is_refused():
    entry = _entry(extra_field="not part of the schema")
    errors = validate([entry])
    assert _errors_mentioning(errors, "test-entry.extra_field: unknown field")


def test_unknown_source_key_is_refused():
    entry = _entry(sources=[_source(extra="not part of the schema")])
    errors = validate([entry])
    assert _errors_mentioning(errors, "sources[0].extra: unknown field")
