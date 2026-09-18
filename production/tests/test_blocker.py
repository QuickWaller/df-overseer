"""The AND-OR blocker walk (`production/blocker.py`), tested against
hand-built graphs rather than `extract.py`'s fixtures. The well scenario
(blocks, bucket, chain-or-rope, mechanism, blocks expanding into competing
stone/wood routes) does not exist anywhere in `production/tests/fixtures/`
-- those fixtures are a narrow, audit-quoted subset built for the
extraction stream (brewing, glazing, one carpentry reaction, one smelter
reaction; see `PROVENANCE.md`) and were never meant to cover the well.
Building a synthetic graph here, by hand, with the same row shapes
`extract.py`/`store.py` use, is squarely "a pure function over a snapshot
plus the stored graph" (handoff, "Interface"): the walk does not care
whether its rows came from the extractor or from a test.

None of these node/class/process ids are real DF raw tokens; they are
illustrative fixtures for exercising the traversal, exactly the same
status `reaction_dyes.txt` and `reaction_adv_carpenter.txt` already carry
in the extractor's own fixture set (see PROVENANCE.md: "ILLUSTRATIVE").
"""

from __future__ import annotations

import pytest

from production import blocker, schema


# ---- small builders, to keep the graphs below readable -----------------------


def _node(node_id: str, kind: str = schema.KIND_ITEM_TYPE, status: str = schema.VERIFIED_RAWS) -> dict:
    return {
        "id": node_id, "kind": kind, "display_name": node_id,
        "durability": None, "status": status, "source_ref": "test fixture",
    }


def _class(node_id: str, cls: str) -> dict:
    return {
        "node_id": node_id, "class": cls, "mechanism": schema.MECH_ITEM_TYPE_ONLY,
        "source_ref": "test fixture",
    }


def _process(process_id: str, workshop_node: str | None = None) -> dict:
    return {
        "id": process_id, "workshop_node": workshop_node, "labor": None,
        "is_hardcoded": 0, "source_ref": "test fixture",
    }


def _reagent(process_id: str, class_name: str, quantity: int = 1) -> dict:
    return {
        "process_id": process_id, "direction": schema.REAGENT, "node_id": class_name,
        "quantity": quantity, "unit": None, "unit_source": schema.UNIT_SOURCE_ABSENT,
        "consumption": schema.CONSUMED, "probability": 100, "container_class": None,
        "status": schema.VERIFIED_RAWS, "source_ref": "test fixture",
    }


def _product(process_id: str, node_id: str, quantity: int = 1) -> dict:
    return {
        "process_id": process_id, "direction": schema.PRODUCT, "node_id": node_id,
        "quantity": quantity, "unit": schema.UNIT_UNITS, "unit_source": schema.UNIT_SOURCE_PRODUCT_DIMENSION,
        "consumption": None, "probability": 100, "container_class": None,
        "status": schema.VERIFIED_RAWS, "source_ref": "test fixture",
    }


def _stock(available: int, status: str = schema.MEASURED) -> dict:
    return {"available": available, "status": status}


# ---- the well: the motivating example ----------------------------------------
#
# BUILD_WELL needs blocks, a bucket, a chain-or-rope, and a mechanism (all
# AND). Blocks have two competing producing routes, stone (needs a
# mason's workshop and a boulder, of which there are none) and wood (needs
# a carpenter's workshop and a log, of which there are plenty) -- the OR
# that must resolve live. Chain-or-rope is modelled as one class with two
# members, satisfied straight from stock. Mechanisms need a boulder too,
# and boulders have no producer in this fixture at all (nothing mines):
# that is the fixture's one true dead end, several levels down.


def _well_graph():
    nodes = [
        _node("BUILDING:WELL", kind=schema.KIND_BUILDING),
        _node("BUILDING:MASONS_WORKSHOP", kind=schema.KIND_BUILDING),
        _node("BUILDING:CARPENTERS_WORKSHOP", kind=schema.KIND_BUILDING),
        _node("ITEM:BLOCKS:GRANITE"),
        _node("ITEM:BLOCKS:OAK"),
        _node("ITEM:BUCKET"),
        _node("ITEM:CHAIN"),
        _node("ITEM:ROPE"),
        _node("ITEM:MECHANISM"),
        _node("MATERIAL:BOULDER", kind=schema.KIND_MATERIAL),
        _node("MATERIAL:LOG", kind=schema.KIND_MATERIAL),
    ]
    classes = [
        _class("ITEM:BLOCKS:GRANITE", "BLOCKS"),
        _class("ITEM:BLOCKS:OAK", "BLOCKS"),
        _class("ITEM:BUCKET", "BUCKET"),
        _class("ITEM:CHAIN", "BINDING"),
        _class("ITEM:ROPE", "BINDING"),
        _class("ITEM:MECHANISM", "MECHANISM"),
        _class("MATERIAL:BOULDER", "BOULDER"),
        _class("MATERIAL:LOG", "LOG"),
    ]
    processes = [
        _process("BUILD_WELL"),
        _process("MAKE_BLOCKS_FROM_BOULDER", workshop_node="BUILDING:MASONS_WORKSHOP"),
        _process("MAKE_BLOCKS_FROM_LOG", workshop_node="BUILDING:CARPENTERS_WORKSHOP"),
        _process("MAKE_BUCKET", workshop_node="BUILDING:CARPENTERS_WORKSHOP"),
        _process("MAKE_MECHANISM", workshop_node="BUILDING:MASONS_WORKSHOP"),
    ]
    flows = [
        _reagent("BUILD_WELL", "BLOCKS", 1),
        _reagent("BUILD_WELL", "BUCKET", 1),
        _reagent("BUILD_WELL", "BINDING", 1),
        _reagent("BUILD_WELL", "MECHANISM", 1),
        _product("BUILD_WELL", "BUILDING:WELL", 1),

        _reagent("MAKE_BLOCKS_FROM_BOULDER", "BOULDER", 1),
        _product("MAKE_BLOCKS_FROM_BOULDER", "ITEM:BLOCKS:GRANITE", 4),

        _reagent("MAKE_BLOCKS_FROM_LOG", "LOG", 1),
        _product("MAKE_BLOCKS_FROM_LOG", "ITEM:BLOCKS:OAK", 4),

        _reagent("MAKE_BUCKET", "LOG", 1),
        _product("MAKE_BUCKET", "ITEM:BUCKET", 1),

        _reagent("MAKE_MECHANISM", "BOULDER", 1),
        _product("MAKE_MECHANISM", "ITEM:MECHANISM", 1),
    ]
    return blocker.build_graph(nodes, classes, processes, flows)


def _well_stock(*, boulders: int = 0) -> dict:
    return {
        "MATERIAL:LOG": _stock(5),
        "ITEM:CHAIN": _stock(1),
        "ITEM:ROPE": _stock(0),
        "BUILDING:MASONS_WORKSHOP": _stock(1),
        "BUILDING:CARPENTERS_WORKSHOP": _stock(1),
        "MATERIAL:BOULDER": _stock(boulders),
    }


def test_well_blocked_on_boulder_for_the_mechanism_with_quantity_and_path():
    graph = _well_graph()
    stock = _well_stock(boulders=0)

    result = blocker.find_blocker("BUILDING:WELL", graph, stock)

    assert result.blocked is True
    assert result.blocker is not None
    # Blocks resolved live via the wood route (see the OR-semantics test
    # below); bucket and binding resolved too. The true dead end is the
    # boulder the mechanism needs -- named, not "mechanism" or "well".
    assert result.blocker.target == "BOULDER"
    assert result.blocker.is_class is True
    assert result.blocker.quantity_needed == 1
    assert result.blocker.quantity_available == 0
    assert result.blocker.quantity_short == 1
    # The path shows the descent: well -> its process -> the mechanism
    # target -> the mechanism's own process -> the boulder that killed it.
    assert result.blocker.path == (
        "BUILDING:WELL", "BUILD_WELL", "MECHANISM", "MAKE_MECHANISM", "BOULDER",
    )
    # No coordinate anywhere in the report.
    for step in result.blocker.path:
        assert not any(c.isdigit() for c in step), f"{step!r} looks coordinate-shaped"


def test_well_satisfied_once_boulders_are_available():
    graph = _well_graph()
    stock = _well_stock(boulders=10)

    result = blocker.find_blocker("BUILDING:WELL", graph, stock)

    assert result.blocked is False
    assert result.blocker is None


# ---- OR semantics: report the live route, not the first dead branch ----------


def test_or_semantics_reports_the_live_branch_not_the_first_dead_one():
    graph = _well_graph()
    stock = _well_stock(boulders=0)  # stone route dead (no boulder), wood route live

    result = blocker.find_blocker("BLOCKS", graph, stock, is_class=True)

    assert result.blocked is False, (
        "blocks has a dead stone route and a live wood route; the walk must "
        "not stop at the first (dead) branch it tries"
    )
    assert result.route == ("MAKE_BLOCKS_FROM_LOG",)
    # The dead branch it passed over is still visible, with its own reason.
    dead = [b for b in result.branches if b.process_id == "MAKE_BLOCKS_FROM_BOULDER"]
    assert len(dead) == 1
    assert dead[0].completable is False
    assert dead[0].blocker is not None
    assert dead[0].blocker.target == "BOULDER"


def test_or_semantics_blocked_when_every_branch_is_dead():
    graph = _well_graph()
    stock = _well_stock(boulders=0)
    stock["MATERIAL:LOG"] = _stock(0)  # now both routes are dead

    result = blocker.find_blocker("BLOCKS", graph, stock, is_class=True)

    assert result.blocked is True
    assert len(result.branches) == 2
    assert all(not b.completable for b in result.branches)


# ---- a goal already satisfied: "nothing blocks this", not an empty failure ---


def test_goal_already_satisfied_reports_not_blocked():
    graph = blocker.build_graph(nodes=[_node("ITEM:BUCKET")], classes=[], processes=[], flows=[])
    stock = {"ITEM:BUCKET": _stock(3)}

    result = blocker.find_blocker("ITEM:BUCKET", graph, stock, quantity=1)

    assert result.blocked is False
    assert result.blocker is None
    assert result.route == ()  # satisfied straight from stock, no process needed


# ---- a goal blocked by a missing building, not a missing material ------------


def test_missing_workshop_is_the_named_blocker_not_a_footnote():
    nodes = [
        _node("ITEM:BLOCKS:GRANITE"),
        _node("BUILDING:MASONS_WORKSHOP", kind=schema.KIND_BUILDING),
        _node("MATERIAL:BOULDER", kind=schema.KIND_MATERIAL),
    ]
    classes = [_class("MATERIAL:BOULDER", "BOULDER")]
    processes = [_process("MAKE_BLOCKS_FROM_BOULDER", workshop_node="BUILDING:MASONS_WORKSHOP")]
    flows = [
        _reagent("MAKE_BLOCKS_FROM_BOULDER", "BOULDER", 1),
        _product("MAKE_BLOCKS_FROM_BOULDER", "ITEM:BLOCKS:GRANITE", 4),
    ]
    graph = blocker.build_graph(nodes, classes, processes, flows)
    stock = {
        "MATERIAL:BOULDER": _stock(10),           # plenty of stone
        "BUILDING:MASONS_WORKSHOP": _stock(0),    # but no workshop built
    }

    result = blocker.find_blocker("ITEM:BLOCKS:GRANITE", graph, stock, quantity=1)

    assert result.blocked is True
    assert result.blocker.target == "BUILDING:MASONS_WORKSHOP"
    assert result.blocker.is_class is False
    # This must fall out of the same AND machinery as any reagent, not a
    # special case -- there is no building-specific branch in blocker.py at
    # all, which this test is here to keep honest.


# ---- available versus total: the fort's own demonstrated failure mode --------


def test_available_versus_total_gives_different_answers_for_a_job_claimed_item():
    # Three buckets exist, one is claimed by a pending job. Reading total
    # stock says "3, plenty for 2"; reading available stock (after the
    # in_job deduction) says "2 free, exactly enough" -- and if one more
    # is also owned by a dwarf, "1 free, short by 1". This is deliberately
    # the fort's own documented failure (three empty buckets, no water
    # delivered) rewritten as a check on the deduction wiring itself.
    items = [
        {"in_job": False, "owned": False, "forbid": False, "trader": False},
        {"in_job": True, "owned": False, "forbid": False, "trader": False},
        {"in_job": False, "owned": True, "forbid": False, "trader": False},
    ]
    total = len(items)
    available = blocker.available_quantity(items)
    assert total == 3
    assert available == 1  # only the first bucket is truly free

    graph = blocker.build_graph(nodes=[_node("ITEM:BUCKET")], classes=[], processes=[], flows=[])

    result_by_total = blocker.find_blocker(
        "ITEM:BUCKET", graph, {"ITEM:BUCKET": _stock(total)}, quantity=2,
    )
    result_by_available = blocker.find_blocker(
        "ITEM:BUCKET", graph, {"ITEM:BUCKET": _stock(available)}, quantity=2,
    )

    assert result_by_total.blocked is False, "naive total reads 3 >= 2, no problem"
    assert result_by_available.blocked is True, "available reads 1 < 2, genuinely short"
    assert result_by_available.blocker.quantity_short == 1


def test_available_quantity_ignores_forbidden_and_trader_owned_items():
    items = [
        {"forbid": True},
        {"trader": True},
        {},  # one genuinely free item
    ]
    assert blocker.available_quantity(items) == 1


# ---- termination on adversarial input -----------------------------------------


def test_cycle_raises_instead_of_recursing_forever():
    # A -> (needs class CLS_B, satisfied only by B) -> B -> (needs class
    # CLS_A, satisfied only by A): a direct two-node cycle. The static
    # audit found no cycle in the real raw-defined reactions, but the
    # walk must not simply trust that; it has to detect and stop.
    nodes = [_node("A"), _node("B")]
    classes = [_class("A", "CLS_A"), _class("B", "CLS_B")]
    processes = [_process("MAKE_A"), _process("MAKE_B")]
    flows = [
        _reagent("MAKE_A", "CLS_B", 1),
        _product("MAKE_A", "A", 1),
        _reagent("MAKE_B", "CLS_A", 1),
        _product("MAKE_B", "B", 1),
    ]
    graph = blocker.build_graph(nodes, classes, processes, flows)
    stock: dict = {}

    with pytest.raises(blocker.GraphTraversalError):
        blocker.find_blocker("A", graph, stock, quantity=1)


def test_depth_guard_trips_on_a_long_acyclic_chain():
    # Not a cycle -- a straight chain longer than max_depth, to prove the
    # depth guard is a real, independent safety net and not just an
    # artifact of the cycle check.
    n = 5
    nodes = [_node(f"N{i}") for i in range(n)]
    classes = [_class(f"N{i}", f"CLS{i}") for i in range(n)]
    processes = [_process(f"MAKE{i}") for i in range(1, n)]
    flows = []
    for i in range(1, n):
        flows.append(_reagent(f"MAKE{i}", f"CLS{i - 1}", 1))
        flows.append(_product(f"MAKE{i}", f"N{i}", 1))
    graph = blocker.build_graph(nodes, classes, processes, flows)

    with pytest.raises(blocker.GraphTraversalError):
        blocker.find_blocker(f"N{n - 1}", graph, {}, quantity=1, max_depth=2)


# ---- status propagation: a prior fact must not read as raw-verified ----------


def test_blocker_status_reflects_a_prior_node_not_verified_raws():
    nodes = [_node("ITEM:SOAP", status=schema.PRIOR)]
    graph = blocker.build_graph(nodes, [], [], [])
    stock: dict = {}

    result = blocker.find_blocker("ITEM:SOAP", graph, stock, quantity=1)

    assert result.blocked is True
    assert result.blocker.status == schema.PRIOR
