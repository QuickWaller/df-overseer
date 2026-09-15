#!/usr/bin/env python3
"""df-overseer netwatch: edge-triggered dump on gateway-ping loss.

Installed by `provision_vm.py setup-capture` on any clone of template 102
(handoffs/2026-09-15-incident-capture.md). Run once a minute by
df-netwatch.timer. Pings the default gateway -- discovered live from `ip
route`, every run, never hardcoded or read from this repo's own config --
and on the FIRST failed ping after a success (an "edge", so one outage
writes one dump, not sixty) captures what the network looked like from
inside the guest at that moment: `ip addr`, `ip route`, `ip neigh` (does the
gateway resolve, and to which MAC), `arping -D` on the guest's own address
(is another host claiming it), `docker network ls`/inspect if Docker is
present, `systemctl --failed`, `df -h`, `free -m`, and the last 15 minutes
of journal. A short summary line also goes to the serial console
(/dev/ttyS0), readable from the Proxmox console when SSH is dead. On
recovery, one line noting the outage duration.

Only stdlib -- this runs as the system python3 on a bare Ubuntu guest, no
venv, per `install install_df.py`'s own note that Ubuntu 24.04 ships
python3 without ensurepip until python3.12-venv is installed (which this
script must not depend on).

Written for testability: the pure decision/parsing functions below
(parse_default_gateway, decide_transition, parse_route_get,
select_dumps_to_delete, format_recovery_line) take plain strings/values and
return plain values, with no subprocess or filesystem access, so
tests/test_df_netwatch.py exercises the actual edge-trigger logic directly
-- see handoffs/2026-09-15-incident-capture.md's "Tests" item. main() is the
only part that touches the network, the filesystem or the serial console,
and is not itself unit tested; docs/RUNBOOK-DARK-GUEST.md is how a live run
is verified.
"""

import datetime
import os
import shutil
import subprocess
import sys

STATE_DIR = "/var/lib/df-netwatch"
DUMP_DIR = "/var/log/netwatch"
STATE_FILE = os.path.join(STATE_DIR, "state")
OUTAGE_START_FILE = os.path.join(STATE_DIR, "outage_started")
LOG_FILE = os.path.join(DUMP_DIR, "netwatch.log")
SERIAL_DEVICE = "/dev/ttyS0"
MAX_DUMPS = 200
PING_TIMEOUT = 2


# --- pure logic (unit tested directly, no subprocess/filesystem) -----------

def parse_default_gateway(ip_route_output):
    """Extract the gateway address from `ip route show default` output.

    Handles the normal case (`default via <gw> dev eth0 proto dhcp ...`) and
    returns None for empty/unexpected output rather than raising -- a guest
    with no default route at all is itself worth a clean "no gateway" log
    line, not a crash.
    """
    for line in (ip_route_output or "").splitlines():
        parts = line.split()
        if parts[:1] == ["default"] and "via" in parts:
            return parts[parts.index("via") + 1]
    return None


def parse_route_get(ip_route_get_output):
    """(src_ip, dev) from `ip route get <gateway>` output, or (None, None).

    Used to find the guest's own source address and outbound interface for
    the arping -D self-check, without hardcoding either.
    """
    src = None
    dev = None
    parts = (ip_route_get_output or "").split()
    if "src" in parts:
        i = parts.index("src")
        if i + 1 < len(parts):
            src = parts[i + 1]
    if "dev" in parts:
        i = parts.index("dev")
        if i + 1 < len(parts):
            dev = parts[i + 1]
    return src, dev


def decide_transition(prev_state, now_up):
    """(prev_state: 'up'|'down', now_up: bool) -> 'edge_down'|'edge_up'|'none'.

    The whole edge-trigger contract in one place: a dump is written only on
    the up->down transition, a recovery line only on down->up, and a
    steady state (up->up or down->down) does nothing. This is what makes a
    60-minute outage produce one dump instead of sixty.
    """
    now_state = "up" if now_up else "down"
    if prev_state == "up" and now_state == "down":
        return "edge_down"
    if prev_state == "down" and now_state == "up":
        return "edge_up"
    return "none"


def select_dumps_to_delete(dump_filenames, keep=MAX_DUMPS):
    """Given dump-* filenames (any order), return the ones to delete to cap
    the directory at `keep`, oldest-name-first. Filenames sort correctly by
    age because they embed a UTC timestamp (dump-YYYYMMDDTHHMMSSZ.txt).
    """
    ordered = sorted(dump_filenames)
    if len(ordered) <= keep:
        return []
    return ordered[: len(ordered) - keep]


def format_recovery_line(ts, gateway, outage_seconds):
    return "%s df-netwatch: gateway %s recovered after ~%ds" % (
        ts, gateway, outage_seconds)


# --- guest-touching helpers --------------------------------------------

def _run(argv, timeout=15):
    try:
        return subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - a capture step must never crash the run
        class _Fail:
            returncode = 1
            stdout = ""
            stderr = str(exc)
        return _Fail()


def default_gateway():
    proc = _run(["ip", "route", "show", "default"])
    return parse_default_gateway(proc.stdout)


def ping_ok(gateway):
    if not gateway:
        return False
    proc = _run(["ping", "-c", "1", "-W", str(PING_TIMEOUT), gateway],
               timeout=PING_TIMEOUT + 5)
    return proc.returncode == 0


def read_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as fh:
                value = fh.read().strip()
                return value if value in ("up", "down") else "up"
        except OSError:
            return "up"
    return "up"


def write_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as fh:
        fh.write(state + "\n")


def _serial_line(text):
    try:
        with open(SERIAL_DEVICE, "w", encoding="utf-8") as fh:
            fh.write(text.strip() + "\n")
    except OSError:
        pass  # no console attached (e.g. this VM's serial0 not wired up); not fatal


def _append_log(line):
    os.makedirs(DUMP_DIR, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _section(title, argv_or_none, output):
    output.append("--- %s ---" % title)
    if argv_or_none is not None:
        proc = _run(argv_or_none, timeout=20)
        text = (proc.stdout or "") + (proc.stderr or "")
        output.append(text.strip() or "(no output)")
    return output


def write_dump(ts, gateway):
    os.makedirs(DUMP_DIR, exist_ok=True)
    out = []
    out.append("=== df-netwatch dump %s UTC ===" % ts)
    out.append("gateway: %s" % gateway)
    _section("ip addr", ["ip", "addr"], out)
    _section("ip route", ["ip", "route"], out)
    _section("ip neigh", ["ip", "neigh"], out)

    route_get = _run(["ip", "route", "get", gateway], timeout=10)
    src, dev = parse_route_get(route_get.stdout)
    out.append("--- arping -D (own address, source-of-truth from `ip route get`) ---")
    if src and dev and shutil.which("arping"):
        arping = _run(["arping", "-D", "-c", "3", "-I", dev, src], timeout=15)
        out.append(((arping.stdout or "") + (arping.stderr or "")).strip()
                   or "(no output)")
    else:
        out.append("(skipped: no source address/interface resolved, or arping"
                   " not installed)")

    out.append("--- docker network ls / inspect ---")
    if shutil.which("docker"):
        ls = _run(["docker", "network", "ls"], timeout=15)
        out.append((ls.stdout or "").strip() or "(no output)")
        ids = _run(["docker", "network", "ls", "-q"], timeout=15)
        for net_id in (ids.stdout or "").split():
            inspect = _run(["docker", "network", "inspect", net_id], timeout=15)
            out.append(inspect.stdout or "")
    else:
        out.append("(docker not present)")

    _section("systemctl --failed", ["systemctl", "--failed", "--no-legend"], out)
    _section("df -h", ["df", "-h"], out)
    _section("free -m", ["free", "-m"], out)
    _section("journalctl --since -15min", ["journalctl", "--since", "-15min",
                                          "--no-pager"], out)

    path = os.path.join(DUMP_DIR, "dump-%s.txt" % ts)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    return path


def rotate_dumps():
    try:
        names = [n for n in os.listdir(DUMP_DIR) if n.startswith("dump-")
                 and n.endswith(".txt")]
    except OSError:
        return
    for name in select_dumps_to_delete(names):
        try:
            os.remove(os.path.join(DUMP_DIR, name))
        except OSError:
            pass


def main():
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    gateway = default_gateway()
    if not gateway:
        _append_log("%s df-netwatch: no default gateway in the routing table" % ts)
        return 0

    prev = read_state()
    now_up = ping_ok(gateway)
    action = decide_transition(prev, now_up)

    if action == "edge_down":
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(OUTAGE_START_FILE, "w", encoding="utf-8") as fh:
            fh.write(str(int(datetime.datetime.now(
                datetime.timezone.utc).timestamp())))
        dump_path = write_dump(ts, gateway)
        rotate_dumps()
        write_state("down")
        _serial_line("df-netwatch: gateway %s unreachable, dump written %s"
                     % (gateway, dump_path))
    elif action == "edge_up":
        outage_seconds = 0
        try:
            with open(OUTAGE_START_FILE, encoding="utf-8") as fh:
                started = int(fh.read().strip())
            outage_seconds = int(datetime.datetime.now(
                datetime.timezone.utc).timestamp()) - started
        except (OSError, ValueError):
            pass
        line = format_recovery_line(ts, gateway, outage_seconds)
        _append_log(line)
        _serial_line(line)
        write_state("up")
    else:
        write_state("up" if now_up else "down")
    return 0


if __name__ == "__main__":
    sys.exit(main())
