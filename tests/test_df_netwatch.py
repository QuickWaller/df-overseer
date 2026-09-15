"""Unit tests for the guest-side netwatch script's pure logic.

scripts/guest-capture/df_netwatch.py is pushed byte-for-byte to a guest by
`provision_vm.py setup-capture` (handoffs/2026-09-15-incident-capture.md) and
runs there once a minute with no test harness available. Its
subprocess/filesystem-touching parts (main(), write_dump(), rotate_dumps())
are exercised only by a live run, recorded in that handoff's Result section
and docs/RUNBOOK-DARK-GUEST.md. What IS testable locally -- and is exactly
what the handoff's "Tests" item asks for -- is the edge-trigger decision
logic and the small parsers around it, all pure functions taking plain
values and returning plain values.

Addresses in this file are RFC 5737 documentation addresses (192.0.2.0/24),
per docs/TRAPS.md's "fake address used as a positive control is still an
address" rule -- never this project's real gateway or guest addresses.
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "guest-capture"))

import df_netwatch  # noqa: E402


# --- parse_default_gateway -------------------------------------------------

def test_parse_default_gateway_normal_line():
    output = "default via 192.0.2.1 dev eth0 proto dhcp metric 100\n"
    assert df_netwatch.parse_default_gateway(output) == "192.0.2.1"


def test_parse_default_gateway_multiple_routes_picks_default():
    output = (
        "192.0.2.0/24 dev eth0 proto kernel scope link src 192.0.2.50\n"
        "default via 192.0.2.1 dev eth0 proto dhcp metric 100\n"
    )
    assert df_netwatch.parse_default_gateway(output) == "192.0.2.1"


def test_parse_default_gateway_empty_output():
    assert df_netwatch.parse_default_gateway("") is None


def test_parse_default_gateway_no_default_route():
    output = "192.0.2.0/24 dev eth0 proto kernel scope link src 192.0.2.50\n"
    assert df_netwatch.parse_default_gateway(output) is None


def test_parse_default_gateway_none_input():
    assert df_netwatch.parse_default_gateway(None) is None


# --- parse_route_get ---------------------------------------------------

def test_parse_route_get_normal_line():
    output = "192.0.2.1 dev eth0 src 192.0.2.50 uid 0 \n    cache\n"
    src, dev = df_netwatch.parse_route_get(output)
    assert src == "192.0.2.50"
    assert dev == "eth0"


def test_parse_route_get_missing_fields():
    assert df_netwatch.parse_route_get("") == (None, None)
    assert df_netwatch.parse_route_get(None) == (None, None)


# --- decide_transition: the actual edge-trigger contract -------------------

def test_decide_transition_up_to_down_is_edge_down():
    assert df_netwatch.decide_transition("up", False) == "edge_down"


def test_decide_transition_down_to_up_is_edge_up():
    assert df_netwatch.decide_transition("down", True) == "edge_up"


def test_decide_transition_steady_up_is_none():
    assert df_netwatch.decide_transition("up", True) == "none"


def test_decide_transition_steady_down_is_none():
    """The whole point: sixty consecutive down minutes must not re-fire --
    only the first failed ping after a success writes a dump."""
    assert df_netwatch.decide_transition("down", False) == "none"


# --- select_dumps_to_delete (rotation cap) ----------------------------------

def test_select_dumps_to_delete_under_cap_deletes_nothing():
    names = ["dump-20260915T000000Z.txt", "dump-20260915T000100Z.txt"]
    assert df_netwatch.select_dumps_to_delete(names, keep=200) == []


def test_select_dumps_to_delete_over_cap_deletes_oldest():
    names = [
        "dump-20260915T000300Z.txt",
        "dump-20260915T000100Z.txt",
        "dump-20260915T000200Z.txt",
    ]
    # keep=2 -> delete exactly the oldest one
    deleted = df_netwatch.select_dumps_to_delete(names, keep=2)
    assert deleted == ["dump-20260915T000100Z.txt"]


def test_select_dumps_to_delete_exact_cap_deletes_nothing():
    names = ["dump-20260915T000100Z.txt", "dump-20260915T000200Z.txt"]
    assert df_netwatch.select_dumps_to_delete(names, keep=2) == []


# --- format_recovery_line ---------------------------------------------------

def test_format_recovery_line_contains_gateway_and_duration():
    line = df_netwatch.format_recovery_line("20260915T003600Z", "192.0.2.1", 90)
    assert "192.0.2.1" in line
    assert "90" in line
    assert "recovered" in line
