"""Test support for execute containment: an activation that contains `RULING`, the ruling every
fixture project in the execute tests came from."""

from __future__ import annotations

from conductor.execute import ExecuteState, ExecuteStore, record_activation

RULING = "ruling-0001"


def contained_state(*rulings: str) -> ExecuteState:
    state = ExecuteState()
    record_activation(state, activation_id="act-test", role="overseer", run_id="run-0001",
                      opened_at="2026-10-09T00:00:00+00:00", closed_at="2026-10-09T00:01:00+00:00",
                      records=list(rulings) or [RULING])
    return state


def seed(deps, *rulings: str):
    """Write an Overseer activation into the cycle's execute state file; returns `deps`."""
    ExecuteStore(deps.cursor_store.path.with_name("execute_state.json")).save(contained_state(*rulings))
    return deps
