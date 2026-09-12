"""Guard: no private IPv4 address or `.internal` hostname in a tracked file.

CLAUDE.md states twice that this public repo must never contain a real
hostname, address or subnet -- infrastructure specifics belong in
gitignored `infra/local.*`, with committed `infra/local.example.*`
counterparts. That rule depended on every session remembering it and
drifted anyway: roughly a dozen tracked files ended up with real private
IPv4 addresses or `.internal` hostnames in their prose, including
CLAUDE.md itself (see `Working.md`'s "this public repo leaks internal
addresses" entry and `decisions/DECISIONS.md` 2026-09-12).

This is a test, not a pre-commit hook, on purpose: hooks live in
`.git/hooks` (or need `core.hooksPath` pointed at a tracked directory) and
are not installed automatically on every clone, so they are not actually
shared through git. A test in the suite that already runs is.

Placed at top level (`tests/`) rather than under `mcp/tests/` because this
guard scans the whole repository, not `mcp/`'s own code -- it has no
relationship to what `mcp/tests/` is testing.
"""

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# working-archive/ is a historical record of past sessions' own words.
# Rewriting it would falsify what those sessions actually said and saw at
# the time (see CLAUDE.md's archive-cadence rule: "move sections wholesale,
# never summarize or delete"). Excluded from this guard by design, not by
# oversight -- it is known to still contain real addresses and real
# `.internal` hostnames, on purpose.
EXCLUDED_DIR_PREFIXES = ("working-archive/",)

# Any dotted quad; validity/privacy is checked separately below so this
# doesn't have to be a fully correct IPv4 regex on its own.
_IPV4_RE = re.compile(r"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b")

# Real hostnames this repo has actually leaked all have at least two
# hyphenated labels before `.internal` (`df-colony-01.internal`,
# `df-colony-relay-01.internal`, `srv-01.internal`, ...). Requiring that
# shape -- rather than matching bare `.internal` -- deliberately excludes
# incidental prose collisions that are not hostnames at all: a Python
# `"%s.internal" % name` format string (`scripts/install_df.py`) and a
# `json.internal` C++ module reference (`decisions/DECISIONS.md`) both
# matched a naive `\w+\.internal` regex during this guard's own design and
# had to be ruled out by hand -- this narrower pattern rules them out
# mechanically instead.
_INTERNAL_HOSTNAME_RE = re.compile(
    r"\b[a-z0-9]+(?:-[a-z0-9]+)+\.internal\b", re.IGNORECASE
)


def _octet_ok(octet):
    return octet.isdigit() and len(octet) <= 3 and 0 <= int(octet) <= 255


def is_private_rfc1918(a, b, c, d):
    """True if a.b.c.d is a valid IPv4 literal inside an RFC 1918 range.

    Deliberately does NOT flag 127.0.0.0/8 (loopback) or other reserved
    ranges: loopback addresses are identical on every machine and reveal
    nothing about this project's actual network, and several legitimate,
    already-reviewed docs (docs/PURPOSE.md, research files, scripts/*.py)
    cite `127.0.0.1` as a generic DFHack-RPC/x11vnc loopback example. Only
    RFC 1918 (the private-use ranges an attacker could use to place this
    repo on a real LAN) counts as a leak for this guard.
    """
    if not all(_octet_ok(o) for o in (a, b, c, d)):
        return False
    a_i, b_i = int(a), int(b)
    if a_i == 10:
        return True
    if a_i == 172 and 16 <= b_i <= 31:
        return True
    if a_i == 192 and b_i == 168:
        return True
    return False


# Small, explicit allowlist. Keys are paths relative to the repo root, as
# `git ls-files` reports them (forward slashes). Each entry silences every
# hit in that whole file -- keep entries here rare, and only when the
# comment names a real constraint, not convenience.
ALLOWLISTED_FILES = {
    # This repo's own placeholder convention for generic examples in a
    # committed `.example` file: an RFC 1918 address used only to show the
    # CIDR shape a real value must have, never a real host.
    "infra/local.example.env": (
        "RFC1918 address used only as a generic .example template value"
    ),
    # Confirmed during the 2026-09-12 redaction pass: this is a different,
    # fictional subnet from the real VM/relay addresses found elsewhere in
    # this repo (192.168.2.201, 192.168.2.202), not a real host example
    # that needed replacing.
    "scripts/provision_vm.py": (
        "deliberately fictional example address, not a real host"
    ),
    # Owned by the user (CLAUDE.md's Rules section: "Do not modify
    # Working.md, ROADMAP.md or decisions/DECISIONS.md"); editing either
    # is gated to the user, not to this repo's automated cleanup. Both
    # still contain the real VM/relay addresses and a real `.internal`
    # hostname as of 2026-09-12 -- a known, open gap tracked in
    # Working.md's "this public repo leaks internal addresses" entry, not
    # silently accepted here.
    "ROADMAP.md": "owned by the user; leak tracked as open in Working.md",
    "decisions/DECISIONS.md": (
        "owned by the user; leak tracked as open in Working.md"
    ),
}


def _tracked_files():
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def _scannable_files():
    for rel in _tracked_files():
        if rel.startswith(EXCLUDED_DIR_PREFIXES):
            continue
        if rel in ALLOWLISTED_FILES:
            continue
        yield rel


def _read_text(rel):
    path = REPO_ROOT / rel
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
        # Binary or otherwise unreadable-as-text (e.g. a .jsonl data file
        # with non-UTF8 bytes, or an entry git tracks as a symlink) --
        # nothing this guard can usefully scan as prose.
        return None


def _find_violations():
    violations = []
    for rel in _scannable_files():
        text = _read_text(rel)
        if text is None:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for m in _IPV4_RE.finditer(line):
                if is_private_rfc1918(*m.groups()):
                    violations.append((rel, lineno, m.group(0)))
            for m in _INTERNAL_HOSTNAME_RE.finditer(line):
                violations.append((rel, lineno, m.group(0)))
    return violations


def test_no_private_ipv4_or_internal_hostname_in_tracked_files():
    violations = _find_violations()
    if not violations:
        return
    detail = "\n".join(
        f"  {rel}:{lineno}: {value}" for rel, lineno, value in violations
    )
    pytest.fail(
        "Found what looks like a private IPv4 address or a `.internal` "
        "hostname in a tracked file. CLAUDE.md's rule: infrastructure "
        "specifics (Proxmox host, Coolify, IPs, hostnames, tokens) must "
        "never be committed here -- put the real value in gitignored "
        "infra/local.* instead (see infra/local.example.env for the "
        "committed template), and use this repo's placeholder convention "
        "in prose instead of the literal (e.g. <df-vm-ip>, <relay-vm-ip>, "
        "<pve-host>). If a hit here is genuinely legitimate (an RFC 5737 "
        "documentation address, or an RFC1918 address used only "
        "generically in a `.example` file), add it to ALLOWLISTED_FILES "
        "in tests/test_no_leaked_addresses.py with a comment explaining "
        "why -- don't just delete the failure.\n\n"
        f"{detail}"
    )


# --------------------------------------------------------------------------
# Tests for the guard's own classifier, so a change to it that silently
# stops catching real cases fails loudly here rather than only by someone
# noticing a leak got through.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "quad,expected",
    [
        (("10", "0", "0", "1"), True),
        (("172", "16", "0", "1"), True),
        (("172", "31", "255", "254"), True),
        (("172", "15", "0", "1"), False),  # just outside the RFC1918 range
        (("172", "32", "0", "1"), False),  # just outside the RFC1918 range
        (("192", "168", "2", "201"), True),  # this repo's real leaked VM IP
        (("192", "168", "2", "202"), True),  # this repo's real leaked relay IP
        (("192", "0", "2", "202"), False),  # RFC5737 doc address, not private
        (("127", "0", "0", "1"), False),  # loopback, deliberately not flagged
        (("8", "8", "8", "8"), False),  # public
        (("6", "9", "12", "98"), False),  # looks like an IP, is a version number
        (("999", "0", "0", "1"), False),  # not a valid octet at all
    ],
)
def test_is_private_rfc1918_classifies_known_cases(quad, expected):
    assert is_private_rfc1918(*quad) is expected


@pytest.mark.parametrize(
    "text,should_match",
    [
        ("VM 103 (`df-colony-01.internal`) is running.", True),
        ("Relay is `df-colony-relay-01.internal` per the router.", True),
        ("node `srv-01.internal` in the pool", True),
        ('fqdn = "%s.internal" % name', False),  # format string, not a hostname
        ("delegates to a C++ json.internal module", False),  # module name
        ("nothing internal here at all", False),  # no dot-internal token
    ],
)
def test_internal_hostname_regex_matches_real_shapes_only(text, should_match):
    assert bool(_INTERNAL_HOSTNAME_RE.search(text)) is should_match
