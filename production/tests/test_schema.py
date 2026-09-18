"""Unit tests on `production.schema`'s own row validators and DDL, separate
from the full-extraction tests in `test_extract.py`."""

from __future__ import annotations

import sqlite3

from production import schema


def test_create_schema_creates_all_seven_tables(tmp_path):
    conn = sqlite3.connect(tmp_path / "t.sqlite3")
    conn.row_factory = sqlite3.Row
    schema.create_schema(conn)
    tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    expected = {
        "production_node", "production_class", "material_reaction_product",
        "production_process", "production_flow", "production_attribute",
        "production_observation",
    }
    assert expected <= tables
    conn.close()


def test_valid_node_validates_clean():
    row = {
        "id": "DRINK:PLUMP_HELMET_WINE", "kind": schema.KIND_ITEM_TYPE,
        "display_name": "plump helmet wine", "durability": schema.DURABLE,
        "status": schema.VERIFIED_RAWS, "source_ref": "test",
    }
    assert schema.validate_node(row) == []


def test_node_rejects_unknown_kind():
    row = {
        "id": "X", "kind": "not_a_kind", "display_name": "x",
        "status": schema.VERIFIED_RAWS, "source_ref": "test",
    }
    errors = schema.validate_node(row)
    assert any("kind" in e for e in errors)


def test_node_rejects_unknown_status():
    row = {
        "id": "X", "kind": schema.KIND_MATERIAL, "display_name": "x",
        "status": "guessed", "source_ref": "test",
    }
    errors = schema.validate_node(row)
    assert any("status" in e for e in errors)


def test_flow_consumption_only_valid_on_reagent_rows():
    product_row = {
        "process_id": "P", "direction": schema.PRODUCT, "node_id": "X",
        "unit_source": schema.UNIT_SOURCE_ABSENT, "consumption": schema.CONSUMED,
        "status": schema.VERIFIED_RAWS, "source_ref": "test",
    }
    errors = schema.validate_flow(product_row)
    assert any("consumption" in e for e in errors)


def test_flow_rejects_out_of_vocabulary_consumption():
    reagent_row = {
        "process_id": "P", "direction": schema.REAGENT, "node_id": "X",
        "unit_source": schema.UNIT_SOURCE_ABSENT, "consumption": "vanished",
        "status": schema.VERIFIED_RAWS, "source_ref": "test",
    }
    errors = schema.validate_flow(reagent_row)
    assert any("consumption" in e for e in errors)


def test_flow_null_node_id_requires_unavailable_status():
    row = {
        "process_id": "P", "direction": schema.PRODUCT, "node_id": None,
        "unit_source": schema.UNIT_SOURCE_ABSENT, "consumption": None,
        "status": schema.VERIFIED_RAWS, "source_ref": "test",
    }
    errors = schema.validate_flow(row)
    assert any("status" in e for e in errors)


def test_material_reaction_product_rejects_unknown_token_family():
    row = {
        "material_id": "PLANT:PLUMP_HELMET", "token": "DRINK_MAT",
        "result_node": "DRINK:PLUMP_HELMET_WINE", "token_family": "some_other_family",
        "source_ref": "test",
    }
    errors = schema.validate_material_reaction_product(row)
    assert any("token_family" in e for e in errors)


def test_observation_job_duration_requires_skill_level():
    row = {
        "abs_tick": 100, "subject_id": "BREW_DRINK_FROM_PLANT",
        "metric": schema.METRIC_JOB_DURATION, "value": 400.0,
        "status": schema.MEASURED, "source_ref": "test",
    }
    errors = schema.validate_observation(row)
    assert any("skill_level" in e for e in errors)


def test_consumption_values_closed_vocabulary_has_exactly_four():
    # The load-bearing correction: three isn't enough.
    assert len(schema.CONSUMPTION_VALUES) == 4
    assert schema.MODIFIED_IN_PLACE in schema.CONSUMPTION_VALUES
