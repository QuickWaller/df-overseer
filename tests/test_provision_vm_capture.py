"""Tests for the incident-capture additions to scripts/provision_vm.py
(handoffs/2026-09-15-incident-capture.md): the address parser setup-capture
uses to find a guest, and the forensic attach-and-read plan builder.

Both are pure functions -- no PVE object, no network, no subprocess -- so
they are tested directly without mocking a live cluster. The dry-run
behaviour of `forensic-attach` against VM 106's *real* config was verified
live and is recorded in this handoff's Result section, not here: that check
needs a real PVE token and is not something a portable test suite can do.

Addresses below are RFC 5737 documentation addresses (192.0.2.0/24), per
docs/TRAPS.md -- never this project's real values.
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import provision_vm  # noqa: E402


# --- parse_ipconfig_ip -------------------------------------------------

def test_parse_ipconfig_ip_static_address():
    assert provision_vm.parse_ipconfig_ip("ip=192.0.2.5/24,gw=192.0.2.1") \
        == "192.0.2.5"


def test_parse_ipconfig_ip_dhcp_returns_none():
    assert provision_vm.parse_ipconfig_ip("ip=dhcp") is None


def test_parse_ipconfig_ip_missing_returns_none():
    assert provision_vm.parse_ipconfig_ip("") is None
    assert provision_vm.parse_ipconfig_ip(None) is None


def test_parse_ipconfig_ip_ignores_other_fields_order():
    # gw before ip, extra whitespace -- shouldn't matter.
    assert provision_vm.parse_ipconfig_ip("gw=192.0.2.1, ip=192.0.2.9/24") \
        == "192.0.2.9"


# --- build_forensic_plan ----------------------------------------------

def test_build_forensic_plan_step_count_and_order():
    plan = provision_vm.build_forensic_plan(
        dark_vmid=106, template_vmid=102, temp_vmid=107,
        boot_order="order=scsi0", disk_opts="discard=on,ssd=1")
    assert len(plan) == 8
    methods = [m for m, _, _ in plan]
    assert methods == ["POST", "POST", "PUT", "POST", "PUT", "DELETE",
                       "POST", "PUT"]


def test_build_forensic_plan_references_correct_vmids():
    plan = provision_vm.build_forensic_plan(
        dark_vmid=106, template_vmid=102, temp_vmid=107,
        boot_order="order=scsi0", disk_opts="discard=on,ssd=1")
    paths = [p for _, p, _ in plan]
    assert any("/qemu/106/status/shutdown" == p for p in paths)
    assert any("/qemu/102/clone" == p for p in paths)
    assert paths.count("/qemu/106/config") == 3  # detach, restore, hot-attach
    assert any("/qemu/107/move_disk" == p for p in paths)
    assert "/qemu/107" in paths  # the delete of the temp vm
    assert any("/qemu/106/status/start" == p for p in paths)


def test_build_forensic_plan_never_starts_the_temp_vm():
    """The whole safety property this plan exists for: the temp vmid is
    cloned and later deleted, and no step ever starts it."""
    plan = provision_vm.build_forensic_plan(
        dark_vmid=106, template_vmid=102, temp_vmid=107,
        boot_order="order=scsi0", disk_opts="discard=on,ssd=1")
    assert not any("/qemu/107/status/start" == p for _, p, _ in plan)


def test_build_forensic_plan_hot_attach_is_last_step():
    """TRAPS.md: the old disk must be attached only after the fresh disk's
    first boot, never before -- so the hot-attach step must come after the
    start step, and be the very last step in the plan."""
    plan = provision_vm.build_forensic_plan(
        dark_vmid=106, template_vmid=102, temp_vmid=107,
        boot_order="order=scsi0", disk_opts="discard=on,ssd=1")
    start_index = next(i for i, (_, p, _) in enumerate(plan)
                       if p == "/qemu/106/status/start")
    assert start_index == len(plan) - 2
    last_method, last_path, last_desc = plan[-1]
    assert last_path == "/qemu/106/config"
    assert "hot-attach" in last_desc


def test_build_forensic_plan_restore_step_mentions_boot_and_opts():
    plan = provision_vm.build_forensic_plan(
        dark_vmid=106, template_vmid=102, temp_vmid=107,
        boot_order="order=scsi0", disk_opts="discard=on,ssd=1")
    restore = plan[4]
    assert "order=scsi0" in restore[2]
    assert "discard=on,ssd=1" in restore[2]
