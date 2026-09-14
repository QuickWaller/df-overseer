"""Shared record builders for dfqueue tests. Not a test module itself
(pytest only collects `test_*.py`).

Every builder returns a record that passes `schema.validate` unmodified, so
a test only needs to describe what it is breaking, not rebuild a whole valid
record from scratch each time.
"""

from __future__ import annotations


def make_proposal(**overrides) -> dict:
    record = {
        "kind": "proposal",
        "role": "architect",
        "cycle": 1,
        "snapshot": "tick 178877",
        "type": "workshop_siting",
        "summary": "Site the next workshop on the open ground south of the Embark Site.",
        "rationale": (
            "Hauling distance from the wagon is the largest single "
            "contributor to current idle-hauler time, and this patch is "
            "already walkable ground."
        ),
        "prediction": {
            # `fort.population` is a live signal (learning/live_signals.py),
            # so this resolves against `overview.get` and the prediction
            # validates. Live signals, not `learning/ledger` fields, are
            # what a dfqueue proposal predicts against.
            "signal": "fort.population",
            "op": "gte",
            "value": 1,
            "check_after_ticks": 1200,
        },
        "cost": {"estimate": 350, "unit": "dwarf_ticks"},
        "suggested_priority": 3,
        "preconditions": [
            {"landmark": "Embark Site", "state": "exists"},
            {"area": "open_ground_5x5_S_of_Embark_Site_5tiles", "state": "unclaimed"},
        ],
        "public_rationale": (
            "We have a wagon and two stockpiles but nowhere to actually "
            "work, so the next workshop goes on the clear ground just "
            "south of the embark point."
        ),
    }
    record.update(overrides)
    return record


def make_pass(**overrides) -> dict:
    record = {
        "kind": "pass",
        "role": "architect",
        "cycle": 1,
        "snapshot": "tick 178877",
        "reason": (
            "diggable.find returned zero candidates at every probed "
            "z-level and radius; declining rather than proposing a blind dig."
        ),
    }
    record.update(overrides)
    return record


def make_ruling(proposal_id: str = "proposal-0001", **overrides) -> dict:
    record = {
        "kind": "ruling",
        "role": "overseer",
        "cycle": 1,
        "snapshot": "tick 178877",
        "decision": "accept",
        "proposal_id": proposal_id,
        "reason": (
            "Shortest hauling path of the candidates offered, and it does "
            "not touch the stairway to the south-east."
        ),
        "public_rationale": (
            "Approved: shortest walk from the wagon and both stockpiles, "
            "no digging needed."
        ),
    }
    record.update(overrides)
    return record
