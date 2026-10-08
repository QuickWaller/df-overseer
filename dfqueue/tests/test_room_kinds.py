"""Room kind data (blueprints/room-kinds.yaml): validator, template links,
and that the generated Lua module matches the YAML (register 2026-10-08, D1)."""

import copy

import pytest

from dfqueue import room_kinds as rk

REQUIRED_KINDS = {
    "bedroom", "dormitory", "dining_hall", "office", "hospital", "tavern",
    "temple", "library", "barracks", "jail", "tomb", "workshop_room",
}


@pytest.fixture()
def doc():
    return rk.load()


def test_shipped_file_is_valid(doc):
    assert rk.validate(doc) == []


def test_every_required_kind_present(doc):
    assert REQUIRED_KINDS <= set(doc["kinds"])


def test_office_is_corridor_only_and_private(doc):
    o = doc["kinds"]["office"]
    assert o["access"] == "corridor" and o["private"] is True


def test_bedroom_private_corridor_door_default_with_ground(doc):
    b = doc["kinds"]["bedroom"]
    assert b["private"] is True and b["access"] == "corridor"
    assert b["door_policy"] == {"default": "door", "ground": "user_standard"}


def test_every_template_names_a_defined_kind(doc):
    kinds = rk.template_kinds()
    assert kinds and all(k in doc["kinds"] for k in kinds.values())


def test_template_without_kind_is_reported(tmp_path, doc):
    (tmp_path / "x-v1.yaml").write_text("id: x\nrevision: 1\n", encoding="utf-8")
    assert any("has no `kind:`" in p for p in rk.validate(doc, tmp_path))


def test_template_naming_unknown_kind_is_reported(tmp_path, doc):
    (tmp_path / "x-v1.yaml").write_text("id: x\nrevision: 1\nkind: spaceport\n", encoding="utf-8")
    assert any("spaceport" in p for p in rk.validate(doc, tmp_path))


@pytest.mark.parametrize("mutate,needle", [
    (lambda d: d["kinds"]["bedroom"].update(shape_generator="free_draw"), "shape_generator"),
    (lambda d: d["kinds"]["bedroom"].update(access="sideways"), "access"),
    (lambda d: d["kinds"]["bedroom"].update(access={"opens_onto": ["nope"]}), "unknown kind"),
    (lambda d: d["kinds"]["bedroom"]["size"].update(interior_width=[5, 2]), "interior_width"),
    (lambda d: d["kinds"]["bedroom"].update(private="yes"), "private"),
    (lambda d: d["kinds"]["bedroom"].update(door_policy={"default": "door", "ground": None}), "door"),
    (lambda d: d["kinds"]["bedroom"].update(door_policy={"default": "door", "ground": "folklore"}), "door_policy"),
    (lambda d: d["kinds"]["bedroom"]["required_furniture"][0].update(basis="vibes"), "required_furniture"),
    (lambda d: d["kinds"]["bedroom"].update(basis=""), "basis"),
    (lambda d: d["kinds"]["office"].update(zone_kind="Bedroom"), "primary zone"),
    (lambda d: d.update(shape_generators=d["shape_generators"][:5]), "six"),
])
def test_validator_catches(doc, mutate, needle):
    bad = copy.deepcopy(doc)
    mutate(bad)
    assert any(needle in p for p in rk.validate(bad)), rk.validate(bad)


def test_committed_lua_matches_yaml():
    committed = rk.LUA_FILE.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert committed == rk.render_lua(), "run: python -m dfqueue.room_kinds --write-lua"


def test_lua_zone_map_skips_location_kinds(doc):
    data = rk.lua_data(doc)
    assert data["zone_to_kind"]["MeetingHall"] == "meeting_hall"
    assert data["zone_to_kind"]["Bedroom"] == "bedroom"
    assert data["template_kind"]["bedroom-cell"] == "bedroom"
