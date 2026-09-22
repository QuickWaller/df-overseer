"""conductor/cursors.py: per-role diff-stream cursors, persisted atomically."""

from __future__ import annotations

import pytest

from conductor.cursors import INITIAL_CURSOR, CursorStore, CursorStoreError


def test_a_never_seen_role_starts_at_the_initial_cursor(tmp_path):
    store = CursorStore(tmp_path / "cursors.json")
    assert store.get("architect") == INITIAL_CURSOR


def test_set_then_get_round_trips(tmp_path):
    store = CursorStore(tmp_path / "cursors.json")
    store.set("architect", 42)
    assert store.get("architect") == 42
    assert store.get("overseer") == INITIAL_CURSOR  # untouched


def test_set_persists_across_a_new_store_instance(tmp_path):
    path = tmp_path / "cursors.json"
    CursorStore(path).set("quartermaster", 7)
    assert CursorStore(path).get("quartermaster") == 7


def test_set_creates_the_parent_directory(tmp_path):
    path = tmp_path / "nested" / "state" / "cursors.json"
    CursorStore(path).set("architect", 1)
    assert path.is_file()


def test_multiple_roles_do_not_clobber_each_other(tmp_path):
    store = CursorStore(tmp_path / "cursors.json")
    store.set("architect", 1)
    store.set("quartermaster", 2)
    store.set("architect", 3)  # overwrite
    assert store.all() == {"architect": 3, "quartermaster": 2}


def test_a_corrupt_file_is_refused_not_silently_treated_as_empty(tmp_path):
    path = tmp_path / "cursors.json"
    path.write_text("not json{{{", encoding="utf-8")
    with pytest.raises(CursorStoreError):
        CursorStore(path).get("architect")


def test_a_non_object_json_file_is_refused(tmp_path):
    path = tmp_path / "cursors.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(CursorStoreError):
        CursorStore(path).load()


def test_a_missing_file_is_treated_as_no_cursors_yet(tmp_path):
    store = CursorStore(tmp_path / "does-not-exist.json")
    assert store.all() == {}


def test_set_does_not_leave_a_stray_temp_file_behind(tmp_path):
    path = tmp_path / "cursors.json"
    CursorStore(path).set("architect", 1)
    leftovers = [p for p in tmp_path.iterdir() if p != path]
    assert leftovers == []
