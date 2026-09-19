"""The live snapshot assembler (`production/snapshot.py`), tested against
hand-built tool-shaped fixtures -- the same approach `test_blocker.py` and
`test_cover.py` already take, and for the same reason: `snapshot.py` walks
whatever tool output the caller hands it, not a real DFHack connection (no
VM, no SSH, no DFHack this stream -- `handoffs/2026-09-19-snapshot-
assembler.md`).

The well-chain scenario below is deliberately minimal, not a copy of
`test_blocker.py`'s own well fixture: this stream is not proving the
production graph (a parallel stream owns `extract.py`), it is proving that
`snapshot.py` turns real recorded tool output (`Working.md`, "The fort
cannot drink, and the pond cannot be dug to": BUCKET 3, CHAIN 3, BLOCKS 0,
TRAPPARTS 0, logs 3, boulders 0) into a `stock` mapping `blocker.find_blocker`
reads correctly. None of the node ids below are real DF raw tokens beyond
the four DF *type* keys (`BLOCKS`/`BUCKET`/`CHAIN`/`TRAPPARTS`/`BOULDER`/
`WOOD`), which are exactly what `df-overseer-well.lua`'s and
`df-overseer-workshop.lua`'s own `fort_owned` dicts key on.
"""

from __future__ import annotations

import pytest

from production import blocker, cover, schema, snapshot

# ---- small builders -----------------------------------------------------------


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


# ---- test 1: the four deductions survive translation (blocker path) -----------


def test_stock_from_items_nets_in_job_end_to_end():
    """An item flagged `in_job` does not count toward available, all the way
    from tool-shaped input through `stock_from_items` to the number
    `blocker.find_blocker` would read."""
    raw_items = [
        {"df_type": "BUCKET", "in_job": False, "owned": False, "forbid": False, "trader": False},
        {"df_type": "BUCKET", "in_job": True, "owned": False, "forbid": False, "trader": False},  # claimed
        {"df_type": "BUCKET", "in_job": False, "owned": False, "forbid": False, "trader": False},
    ]
    node_id_map = {"BUCKET": "ITEM:BUCKET"}

    stock = snapshot.stock_from_items(raw_items, node_id_map)

    assert stock == {"ITEM:BUCKET": {"available": 2, "status": schema.MEASURED}}


def test_stock_from_items_nets_all_six_flags_independently():
    raw_items = [
        {"df_type": "X"},               # clean
        {"df_type": "X", "in_job": True},
        {"df_type": "X", "owned": True},
        {"df_type": "X", "forbid": True},
        {"df_type": "X", "trader": True},
        {"df_type": "X", "in_building": True},
        {"df_type": "X", "construction": True},
    ]
    node_id_map = {"X": "ITEM:X"}

    stock = snapshot.stock_from_items(raw_items, node_id_map)

    assert stock["ITEM:X"]["available"] == 1
    assert stock["ITEM:X"]["status"] == schema.MEASURED


def test_stock_from_items_nets_in_building_the_fort_own_incident():
    """The real case, 2026-09-19: three shale boulders, all `in_building`
    (the still, the mason's and the mechanic's workshop). `available` must
    read 0, not the false 3 `stocks.availability` reported before this
    stream."""
    raw_items = [
        {"df_type": "BOULDER", "in_building": True},
        {"df_type": "BOULDER", "in_building": True},
        {"df_type": "BOULDER", "in_building": True},
    ]
    node_id_map = {"BOULDER": "MATERIAL:BOULDER"}

    stock = snapshot.stock_from_items(raw_items, node_id_map)

    assert stock["MATERIAL:BOULDER"]["available"] == 0


def test_translate_items_reads_nested_flags_dict_too():
    """A future tool might emit `item.flags.in_job`-shaped nesting rather
    than a flattened key; either is accepted (module docstring)."""
    raw_items = [
        {"df_type": "BUCKET", "flags": {"in_job": True}},
        {"df_type": "BUCKET", "flags": {}},
    ]
    node_id_map = {"BUCKET": "ITEM:BUCKET"}

    stock = snapshot.stock_from_items(raw_items, node_id_map)

    assert stock == {"ITEM:BUCKET": {"available": 1, "status": schema.MEASURED}}


def test_translate_items_missing_flags_default_false_not_dropped():
    """An item with no flag keys at all is still counted (absence means
    'not claimed/owned/forbidden/trader-held', the same `item.get(flag)`
    convention `blocker.available_quantity` and `cover.split_stock` use) --
    it must not silently vanish from the total."""
    raw_items = [{"df_type": "BUCKET"}]
    node_id_map = {"BUCKET": "ITEM:BUCKET"}

    stock = snapshot.stock_from_items(raw_items, node_id_map)

    assert stock["ITEM:BUCKET"]["available"] == 1


# ---- test 2: an unnetted flag never reads as a clean zero (or a clean number) --


def test_fort_owned_counts_never_claim_full_netting():
    """`fort_owned_counts_to_stock` is fed today's real tool shape
    (`well.lua`'s `requirements().fort_owned`). Even for a nonzero count,
    the result must never carry `schema.MEASURED` or `schema.VERIFIED_RAWS`
    -- that would claim in_job/owned/forbid/in_building/construction were
    netted when they were not -- and must say, explicitly, which flags are
    missing. `in_building`/`construction` belong in this set for the exact
    reason this stream exists: `workshop.lua`'s own `building_material_
    report` is one of the two integer-count tools that read the fort's
    three shale boulders as "3 available" while all three were built into
    a workshop."""
    fort_owned = {"BUCKET": 3, "CHAIN": 3, "BLOCKS": 0, "TRAPPARTS": 0}
    node_id_map = {
        "BUCKET": "ITEM:BUCKET", "CHAIN": "ITEM:CHAIN",
        "BLOCKS": "ITEM:BLOCKS", "TRAPPARTS": "ITEM:TRAPPARTS",
    }

    stock = snapshot.fort_owned_counts_to_stock(
        fort_owned, node_id_map, source="df-overseer-well requirements"
    )

    for node_id, count in (
        ("ITEM:BUCKET", 3), ("ITEM:CHAIN", 3), ("ITEM:BLOCKS", 0), ("ITEM:TRAPPARTS", 0),
    ):
        entry = stock[node_id]
        # The number is still carried through -- this is not "hide the
        # figure", it is "do not claim more confidence in it than earned".
        assert entry["available"] == count
        assert entry["status"] == schema.UNAVAILABLE
        assert entry["status"] not in (schema.MEASURED, schema.VERIFIED_RAWS, schema.PRIOR)
        assert set(entry["unnetted_flags"]) == {
            "in_job", "owned", "forbid", "in_building", "construction",
        }
        assert "in_job" in entry["reason"] or "owned" in entry["reason"] or "forbid" in entry["reason"]


def test_fort_owned_counts_reason_names_the_source():
    stock = snapshot.fort_owned_counts_to_stock(
        {"BLOCKS": 0}, {"BLOCKS": "ITEM:BLOCKS"}, source="df-overseer-workshop building_material"
    )
    assert "df-overseer-workshop building_material" in stock["ITEM:BLOCKS"]["reason"]


# ---- test 3: the well chain assembles (the test that proves the stream worked) --


def _well_graph():
    """A deliberately minimal well: BLOCKS, BUCKET, CHAIN and TRAPPARTS all
    AND-required, no producer modelled for any of them -- this stream is
    not extracting the real production graph (a parallel stream owns
    `extract.py`), only proving the assembler feeds `blocker.find_blocker`
    correctly shaped, correctly netted (or honestly marked unnetted) stock."""
    nodes = [
        _node("BUILDING:WELL", kind=schema.KIND_BUILDING),
        _node("ITEM:BLOCKS"), _node("ITEM:BUCKET"), _node("ITEM:CHAIN"), _node("ITEM:TRAPPARTS"),
    ]
    classes = [
        _class("ITEM:BLOCKS", "BLOCKS"), _class("ITEM:BUCKET", "BUCKET"),
        _class("ITEM:CHAIN", "CHAIN"), _class("ITEM:TRAPPARTS", "TRAPPARTS"),
    ]
    processes = [_process("BUILD_WELL")]
    flows = [
        _reagent("BUILD_WELL", "BLOCKS", 1),
        _reagent("BUILD_WELL", "BUCKET", 1),
        _reagent("BUILD_WELL", "CHAIN", 1),
        _reagent("BUILD_WELL", "TRAPPARTS", 1),
        _product("BUILD_WELL", "BUILDING:WELL", 1),
    ]
    return blocker.build_graph(nodes, classes, processes, flows)


def test_well_chain_assembles_and_blocker_names_blocks_or_trapparts():
    """The real recorded figures, `Working.md` 'The fort cannot drink, and
    the pond cannot be dug to': BUCKET 3, CHAIN 3, BLOCKS 0, TRAPPARTS 0
    (`df-overseer-well find`'s own `requirements` block) plus logs 3,
    boulders 0 (`df-overseer-workshop`'s `building_material_report`,
    merged in to prove two tool readings combine without conflict). The
    well goal must come back blocked on BLOCKS or TRAPPARTS -- not on
    BUCKET or CHAIN (both present), and not reported against the well
    itself."""
    node_id_map = {
        "BLOCKS": "ITEM:BLOCKS", "BUCKET": "ITEM:BUCKET",
        "CHAIN": "ITEM:CHAIN", "TRAPPARTS": "ITEM:TRAPPARTS",
        "BOULDER": "MATERIAL:BOULDER", "WOOD": "MATERIAL:WOOD",
    }
    well_stock = snapshot.fort_owned_counts_to_stock(
        {"BLOCKS": 0, "BUCKET": 3, "CHAIN": 3, "TRAPPARTS": 0},
        node_id_map, source="df-overseer-well requirements",
    )
    workshop_stock = snapshot.fort_owned_counts_to_stock(
        {"BOULDER": 0, "WOOD": 3, "BLOCKS": 0},
        node_id_map, source="df-overseer-workshop building_material_report",
    )

    stock = snapshot.merge_stock(well_stock, workshop_stock)

    graph = _well_graph()
    result = blocker.find_blocker("BUILDING:WELL", graph, stock)

    assert result.blocked is True
    assert result.blocker is not None
    assert result.blocker.target in ("BLOCKS", "TRAPPARTS"), (
        f"expected the walk to stop at BLOCKS or TRAPPARTS, got {result.blocker.target!r}"
    )
    assert result.blocker.is_class is True
    assert result.blocker.quantity_available == 0
    assert result.blocker.quantity_short == 1
    # Bucket and chain must not appear as the reported blocker -- both are
    # present and must not stop the walk.
    assert result.blocker.target not in ("BUCKET", "CHAIN")
    # No coordinate anywhere in the report (project-wide rule).
    for step in result.blocker.path:
        assert not any(c.isdigit() for c in step), f"{step!r} looks coordinate-shaped"
    # The result's own status carries the unnetted warning through, because
    # _weakest propagates the weakest status touched during the walk.
    assert result.status == schema.UNAVAILABLE


def test_well_chain_satisfied_once_blocks_and_trapparts_are_stocked():
    node_id_map = {
        "BLOCKS": "ITEM:BLOCKS", "BUCKET": "ITEM:BUCKET",
        "CHAIN": "ITEM:CHAIN", "TRAPPARTS": "ITEM:TRAPPARTS",
    }
    stock = snapshot.fort_owned_counts_to_stock(
        {"BLOCKS": 2, "BUCKET": 3, "CHAIN": 3, "TRAPPARTS": 1},
        node_id_map, source="df-overseer-well requirements",
    )

    result = blocker.find_blocker("BUILDING:WELL", _well_graph(), stock)

    assert result.blocked is False
    assert result.blocker is None


# ---- test 4: unknown node ids are an error, not a silent skip -----------------


def test_fort_owned_counts_unknown_type_raises():
    with pytest.raises(snapshot.UnknownNodeError):
        snapshot.fort_owned_counts_to_stock(
            {"WHATEVER_NEW_TYPE": 5}, {"BLOCKS": "ITEM:BLOCKS"}, source="test"
        )


def test_stock_from_items_unknown_type_raises():
    with pytest.raises(snapshot.UnknownNodeError):
        snapshot.stock_from_items([{"df_type": "MYSTERY"}], {"BUCKET": "ITEM:BUCKET"})


def test_translate_items_unknown_type_error_names_the_key():
    with pytest.raises(snapshot.UnknownNodeError, match="MYSTERY"):
        snapshot.translate_items([{"df_type": "MYSTERY"}], {"BUCKET": "ITEM:BUCKET"})


# ---- merge_stock: conflicts surface, do not get silently resolved -------------


def test_merge_stock_agreeing_sources_combine_cleanly():
    a = {"ITEM:BLOCKS": {"available": 0, "status": schema.UNAVAILABLE}}
    b = {"ITEM:BLOCKS": {"available": 0, "status": schema.UNAVAILABLE}}

    merged = snapshot.merge_stock(a, b)

    assert merged == {"ITEM:BLOCKS": {"available": 0, "status": schema.UNAVAILABLE}}


def test_merge_stock_disagreeing_sources_raise():
    a = {"ITEM:BLOCKS": {"available": 0, "status": schema.UNAVAILABLE}}
    b = {"ITEM:BLOCKS": {"available": 4, "status": schema.UNAVAILABLE}}

    with pytest.raises(snapshot.StockConflictError):
        snapshot.merge_stock(a, b)


def test_merge_stock_disjoint_sources_both_survive():
    a = {"ITEM:BUCKET": {"available": 3, "status": schema.UNAVAILABLE}}
    b = {"ITEM:CHAIN": {"available": 3, "status": schema.UNAVAILABLE}}

    merged = snapshot.merge_stock(a, b)

    assert merged == {**a, **b}


# ---- items_for_cover: the same translation feeds cover.py directly ------------


def test_items_for_cover_integration_nets_and_splits_correctly():
    """End-to-end: tool-shaped raw items -> `items_for_cover` ->
    `cover.split_stock` -- an in_job item is excluded, a rotten perishable
    is reported separately, never folded into `perishable_available`."""
    node_id_map = {"DRINK": "DRINK:PLUMP_HELMET_WINE", "PLANT": "PLANT:MUSHROOM_HELMET_PLUMP"}
    raw_items = [
        {"df_type": "DRINK", "trader": False},
        {"df_type": "DRINK", "in_job": True},           # claimed, excluded
        {"df_type": "PLANT", "rotten": True},
        {"df_type": "PLANT", "rotten": False},
        {"df_type": "PLANT", "trader": True},            # caravan-owned, excluded
    ]
    durability = {
        "DRINK:PLUMP_HELMET_WINE": schema.DURABLE,
        "PLANT:MUSHROOM_HELMET_PLUMP": schema.PERISHABLE,
    }

    items = snapshot.items_for_cover(raw_items, node_id_map)
    split = cover.split_stock(items, durability)

    assert split.durable_available == 1        # one DRINK, the in_job one excluded
    assert split.perishable_available == 1      # one good PLANT
    assert split.perishable_rotten == 1         # one rotten PLANT, reported not hidden
    assert split.total_available == 2           # rotten never folded in


def test_items_for_cover_unknown_type_raises():
    with pytest.raises(snapshot.UnknownNodeError):
        snapshot.items_for_cover([{"df_type": "MYSTERY"}], {"DRINK": "DRINK:X"})
