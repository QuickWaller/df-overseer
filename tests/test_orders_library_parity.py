"""handoffs/2026-10-07-valid-manager-orders.md: orders.create must issue the
same material fields DFHack's own order library does, and orders.list must
flag an order that has none.

The fixtures in tests/fixtures/dfhack_orders/ are DFHack's shipped order
library (hack/data/orders/*.json, 228 orders), copied byte for byte from the
live install on 2026-10-07. The tool's ORDER_MATERIAL_POLICY table is checked
against them: nothing in the library is left without a policy, every default
is a value the library itself uses for that job, and a job the library
issues bare takes no default.

What a lupa fake world cannot prove: that the game then works an order built
this way (that is the supervised live repair in the handoff's Result), or the
real workorder.lua's struct writes.

Skipped when lupa is not installed.
"""

import json
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

from test_orders_conditions_lua_logic import World  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "dfhack_orders"
INFERRED = {"MakeBarrel"}  # policy entries not derived from the library


def library():
    out = []
    for f in sorted(FIXTURES.glob("*.json")):
        out.extend(json.loads(f.read_text(encoding="utf-8")))
    return out


LIB = library()
JOBS = sorted({o["job"] for o in LIB})
CATS = sorted({c for o in LIB for c in o.get("material_category", [])})


@pytest.fixture
def w():
    world = World()
    names = ", ".join(f'"{j}"' for j in JOBS + sorted(INFERRED))
    cats = ", ".join(f'"{c}"' for c in CATS)
    world.run(
        "local function enum(ns) local e = {NONE = -1, [-1] = 'NONE'};"
        " for i, n in ipairs(ns) do e[n] = i - 1; e[i - 1] = n end; return e end;"
        f"df.job_type = enum({{{names}}});"
        f"MATERIAL_CATEGORY_FLAGS = {{{cats}}}"
    )
    for code in sorted({o["reaction"] for o in LIB if "reaction" in o}):
        world.run(f"add_reaction('{code}')")
    return world


def policy(w):
    p = w.g["ORDER_MATERIAL_POLICY"]
    return {str(k): {str(kk): (list(v[kk].values()) if hasattr(v[kk], "values") else v[kk]) for kk in v} for k, v in p.items()}


def create(w, job, material="", categories=(), frequency=""):
    return w.call(
        "create_order", job, "1", frequency, material, ",".join(categories),
        "", "", "", "", "true",
    )


def test_every_library_order_round_trips_its_material_fields(w):
    checked = skipped = 0
    for o in LIB:
        if "item_subtype" in o:
            skipped += 1  # the tool has no ITEM_SUBTYPE argument
            continue
        job = o["reaction"] if "reaction" in o else o["job"]
        r = create(w, job, o.get("material", ""), o.get("material_category", []), o["frequency"])
        assert "error" not in r, (job, r)
        q = r["would_queue"]
        assert q["job"] == o["job"]
        assert q.get("reaction") == o.get("reaction")
        assert q.get("material") == o.get("material")
        assert q.get("material_category") == o.get("material_category")
        assert q["frequency"] == o["frequency"]
        assert r["material_defaulted"] is False
        checked += 1
    assert checked > 100 and skipped > 0


def test_every_library_job_has_a_policy_entry(w):
    missing = [j for j in JOBS if j not in policy(w)]
    assert missing == []


def test_each_policy_entry_agrees_with_the_library(w):
    p = policy(w)
    for job, entry in p.items():
        if job in INFERRED:
            continue
        mine = [o for o in LIB if o["job"] == job]
        assert mine, f"{job} is in the policy but not in the library"
        mats = {o.get("material") for o in mine}
        cats = {tuple(o.get("material_category", [])) for o in mine}
        if "material" in entry:
            assert entry["material"] in mats, job
        elif "category" in entry:
            assert tuple(entry["category"]) in cats, job
        elif entry.get("none"):
            assert mats == {None} and cats == {()}, job
        else:
            assert entry.get("requires") is True, job
            assert len(mats | cats) > 1, f"{job} has one variant, give it a default"


def test_a_defaulted_order_matches_the_library_order_for_that_job(w):
    p = policy(w)
    for job, entry in p.items():
        if "material" not in entry and "category" not in entry:
            continue
        r = create(w, job)
        assert "error" not in r, (job, r)
        q = r["would_queue"]
        assert r["material_defaulted"] is True
        assert q.get("material") == entry.get("material")
        assert q.get("material_category") == entry.get("category")
        if job in INFERRED:
            continue
        assert any(
            o["job"] == job
            and o.get("material") == q.get("material")
            and o.get("material_category") == q.get("material_category")
            for o in LIB
        ), job


def test_a_job_that_needs_a_choice_is_refused_without_one(w):
    p = policy(w)
    for job in [j for j, e in p.items() if e.get("requires")]:
        r = create(w, job)
        assert "needs a material" in r["error"], job
        assert create(w, job, "INORGANIC:IRON").get("error") is None
        assert create(w, job, "", ["wood"]).get("error") is None


def test_a_job_not_in_the_policy_is_refused_without_a_material(w):
    w.run("df.job_type = {NONE = -1, [-1] = 'NONE', MakeThing = 0, [0] = 'MakeThing'}")
    assert "needs a material" in create(w, "MakeThing")["error"]


def test_reactions_and_none_jobs_stay_bare(w):
    r = create(w, "BREW_DRINK_FROM_PLANT")
    q = r["would_queue"]
    assert q.get("material") is None and q.get("material_category") is None
    assert r["material_defaulted"] is False
    r = create(w, "MakeCharcoal")
    assert r["would_queue"].get("material") is None


def test_the_five_live_jobs_default_as_the_library_does(w):
    w.run("add_reaction('BREW_DRINK_FROM_PLANT')")
    assert create(w, "ConstructBlocks")["would_queue"]["material"] == "INORGANIC"
    assert create(w, "ConstructMechanisms")["would_queue"]["material"] == "INORGANIC"
    assert create(w, "ConstructThrone")["would_queue"]["material"] == "INORGANIC"
    assert create(w, "MakeBarrel")["would_queue"]["material_category"] == ["wood"]


def test_a_real_create_reads_back_a_set_material_and_is_not_invalid(w):
    r = w.call("create_order", "ConstructBlocks", "1", "", "", "", "", "", "", "", "false")
    assert r["create_ok"] is True
    assert r["order"]["invalid_material"] is False
    assert r["order"]["material"]
    rb = w.call("create_order", "MakeBarrel", "2", "Daily", "", "", "", "", "", "", "false")
    assert rb["order"]["material_category"] == ["wood"]
    assert rb["order"]["invalid_material"] is False


def test_list_flags_an_item_order_with_no_material(w):
    w.run("add_order(0, 'ConstructBlocks'); add_order(1, 'MakeBucket')")
    w.run("add_order(2, 'CustomReaction', {reaction = 'BREW_DRINK_FROM_PLANT'})")
    w.run("add_order(3, 'ConstructThrone', {mat_type = 0, mat_index = -1})")
    rows = {o["id"]: o for o in w.call("list_orders")["orders"]}
    assert rows[0]["invalid_material"] is True
    assert "ConstructBlocks" in rows[0]["invalid_material_reason"]
    assert rows[1]["invalid_material"] is True
    assert rows[2]["invalid_material"] is False
    assert rows[3]["invalid_material"] is False
