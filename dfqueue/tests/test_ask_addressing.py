"""Asks addressed to a named role (handoffs/2026-10-07-ask-addressing.md).

The real roster has one answerer (the consultant). Roles that do not exist
yet (logistics, planner) are exercised through a fixture roster, never by
editing agents/ROSTER.yaml.
"""
from __future__ import annotations

import pytest

from dfqueue import schema, store
from dfqueue.tests._helpers import make_answer, make_ask

_REAL_ROSTER = schema._load_roster


@pytest.fixture
def logistics_roster(monkeypatch):
    """The real roster plus an enabled, answering `logistics` role."""
    real = _REAL_ROSTER()
    roster = {
        **real,
        "roles": {
            **real["roles"],
            "logistics": {"enabled": True, "dir": "logistics", "kind": "advisor", "answerer": True},
        },
    }
    monkeypatch.setattr(schema, "_load_roster", lambda: roster)
    return roster


def _db(tmp_path):
    return tmp_path / "queue.sqlite3"


def _errs(errors, text):
    return [e for e in errors if text in e]


GOOD_SPEC = [
    {"purpose": "feeder", "classes": ["stone"], "tiles": 9, "adjacent_to": "workshop", "links_only": True},
    {"purpose": "output", "classes": ["furniture"], "tiles": 6, "adjacent_to": "workshop"},
    {"purpose": "reuse", "pile": "Stockpile #2", "note": "existing wood source is close enough"},
]


# ---- roster data ------------------------------------------------------------


def test_only_the_consultant_is_an_answerer_in_the_real_roster():
    assert schema.answer_roles() == frozenset({"consultant"})


def test_the_fixture_roster_adds_an_answerer(logistics_roster):
    assert schema.answer_roles() == frozenset({"consultant", "logistics"})


# ---- the default path is unchanged ------------------------------------------


def test_an_ask_with_no_to_is_the_consultants(tmp_path):
    path = _db(tmp_path)
    ask = store.append(make_ask(), path)
    assert "to" not in ask
    assert schema.ask_addressee(ask) == "consultant"
    assert [a["id"] for a in store.open_asks(path, to="consultant")] == [ask["id"]]
    answer = store.append(make_answer(ask_id=ask["id"]), path)
    assert answer["role"] == "consultant"


def test_an_explicit_to_consultant_validates():
    assert schema.validate(make_ask(to="consultant")) == []


# ---- refusals on the ask ----------------------------------------------------


def test_to_must_be_an_answerer_role():
    errors = schema.validate(make_ask(to="overseer"))
    assert _errs(errors, "record.to: 'overseer' is not an answerer role")


def test_to_a_role_not_in_the_roster_is_refused():
    assert _errs(schema.validate(make_ask(to="logistics")), "record.to:")


def test_to_must_be_a_string():
    assert _errs(schema.validate(make_ask(to=7)), "record.to:")


def test_a_role_may_not_ask_itself(logistics_roster, monkeypatch):
    monkeypatch.setattr(schema, "ASK_ROLES", (*schema.ASK_ROLES, "logistics"))
    errors = schema.validate(make_ask(role="logistics", to="logistics"))
    assert _errs(errors, "may not ask itself")


def test_an_ask_to_a_fixture_answerer_validates(logistics_roster):
    assert schema.validate(make_ask(to="logistics")) == []


# ---- answer authority follows the addressee ---------------------------------


def test_only_the_addressee_may_answer(tmp_path, logistics_roster):
    path = _db(tmp_path)
    ask = store.append(make_ask(to="logistics"), path)
    with pytest.raises(store.QueueError, match="addressed to 'logistics'"):
        store.append(make_answer(ask_id=ask["id"], role="consultant"), path)
    answer = store.append(make_answer(ask_id=ask["id"], role="logistics"), path)
    assert answer["role"] == "logistics"


def test_the_logistics_role_cannot_answer_a_default_ask(tmp_path, logistics_roster):
    path = _db(tmp_path)
    ask = store.append(make_ask(), path)
    with pytest.raises(store.QueueError, match="addressed to 'consultant'"):
        store.append(make_answer(ask_id=ask["id"], role="logistics"), path)


def test_a_non_answerer_may_not_answer_at_all():
    errors = schema.validate(make_answer(role="architect"))
    assert _errs(errors, "may write an answer")


# ---- pending lists only asks addressed to the answerer ----------------------


def test_open_asks_filters_by_addressee(tmp_path, logistics_roster):
    path = _db(tmp_path)
    a = store.append(make_ask(question="Question for the consultant, distinct."), path)
    b = store.append(make_ask(to="logistics", question="Where should the feeder pile go?"), path)
    assert [r["id"] for r in store.open_asks(path, to="consultant")] == [a["id"]]
    assert [r["id"] for r in store.open_asks(path, to="logistics")] == [b["id"]]
    assert [r["id"] for r in store.open_asks(path)] == [a["id"], b["id"]]
    assert [r["id"] for r in store.open_asks(path, limit=1)] == [a["id"]]


# ---- pile_spec ---------------------------------------------------------------


def test_a_valid_pile_spec_validates_and_is_stored(tmp_path, logistics_roster):
    path = _db(tmp_path)
    ask = store.append(make_ask(to="logistics"), path)
    answer = store.append(make_answer(ask_id=ask["id"], role="logistics", pile_spec=GOOD_SPEC), path)
    assert answer["pile_spec"] == GOOD_SPEC


def _spec_errors(spec):
    return schema.validate(make_answer(pile_spec=spec))


@pytest.mark.parametrize("spec", [[], "stone", {"purpose": "x"}])
def test_pile_spec_must_be_a_non_empty_list(spec):
    assert _errs(_spec_errors(spec), "record.pile_spec")


def test_pile_spec_is_bounded():
    entry = {"purpose": "output", "classes": ["stone"], "tiles": 4}
    assert _errs(_spec_errors([entry] * 9), "at most")


@pytest.mark.parametrize("key", ["x", "y", "z", "pos", "position", "at", "tile"])
def test_pile_spec_refuses_positional_keys(key):
    entry = {"purpose": "output", "classes": ["stone"], "tiles": 4, key: 12}
    assert _errs(_spec_errors([entry]), f"pile_spec.0.{key}: not a field")


def test_pile_spec_refuses_a_coordinate_in_text():
    entry = {"purpose": "output", "classes": ["stone"], "tiles": 4, "adjacent_to": "workshop at (12, 40, 8)"}
    assert _errs(_spec_errors([entry]), "raw-coordinate")
    reuse = {"purpose": "reuse", "pile": "the pile at (12, 40, 8)"}
    assert _errs(_spec_errors([reuse]), "raw-coordinate")


def test_pile_spec_classes_come_from_the_category_list():
    entry = {"purpose": "output", "classes": ["stone", "gold"], "tiles": 4}
    assert _errs(_spec_errors([entry]), "'gold' is not a stockpile category")
    assert _errs(_spec_errors([{"purpose": "output", "tiles": 4}]), "classes: required")
    assert _errs(_spec_errors([{"purpose": "output", "classes": [], "tiles": 4}]), "classes: required")


@pytest.mark.parametrize("tiles", [0, -1, 962, 2.5, "9", True, None])
def test_pile_spec_tiles_stay_within_the_place_cap(tiles):
    entry = {"purpose": "output", "classes": ["stone"], "tiles": tiles}
    assert _errs(_spec_errors([entry]), "tiles:")


def test_pile_spec_tiles_cap_edges_are_accepted():
    for tiles in (1, 961):
        assert _spec_errors([{"purpose": "output", "classes": ["stone"], "tiles": tiles}]) == []


def test_pile_spec_links_only_must_be_a_bool():
    entry = {"purpose": "feeder", "classes": ["stone"], "tiles": 4, "links_only": "yes"}
    assert _errs(_spec_errors([entry]), "links_only")


def test_a_reuse_entry_needs_a_pile_and_takes_no_new_pile_fields():
    assert _errs(_spec_errors([{"purpose": "reuse"}]), "pile: required")
    entry = {"purpose": "reuse", "pile": "Stockpile #2", "tiles": 4}
    assert _errs(_spec_errors([entry]), "tiles: not a field of a reuse entry")


def test_a_new_pile_entry_refuses_a_pile_name_field():
    entry = {"purpose": "output", "classes": ["stone"], "tiles": 4, "pile": "Stockpile #2"}
    assert _errs(_spec_errors([entry]), "pile: not a field of a new-pile entry")


def test_pile_spec_is_optional():
    assert schema.validate(make_answer()) == []
