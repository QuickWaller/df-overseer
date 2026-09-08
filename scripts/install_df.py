"""Install Dwarf Fortress Classic + DFHack on a df-overseer VM, over SSH.

    python scripts/install_df.py install [--vmid N] [--force]
    python scripts/install_df.py verify  [--vmid N]
    python scripts/install_df.py start   [--vmid N]
    python scripts/install_df.py stop    [--vmid N] [--save]
    python scripts/install_df.py gen     [--world-id 7] [--preset "POCKET ISLAND"]
    python scripts/install_df.py saves   [--vmid N]
    python scripts/install_df.py backup  [--vmid N] [--out backups]
    python scripts/install_df.py systemd [--vmid N] [--start]

VM 104 was built by hand on 2026-08-27 and the only record of it is prose
(infra/local.df-vm-install.md). This turns that prose into something re-runnable,
so the fortress VM is rebuildable rather than precious -- which is the
precondition for opening the box it runs on.

Every command is idempotent: re-running 'install' on a finished VM re-checks
each step and changes nothing.

Add --dry-run to any command to print the remote script instead of running it.
Nothing host-specific is hardcoded -- it all comes from .env (gitignored).
"""

import argparse
import base64
import os
import random
import subprocess
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pve import PVE, PVEError, log  # noqa: E402
from provision_vm import ssh_guest  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Bay 12 Classic, not Steam: no Steam client on a headless VM, and Classic is
# the build DFHack's Linux release is cut against. The URL is version-pinned
# rather than a 'current' redirect -- a silent DF bump would desync DFHack,
# which only loads against the exact version it was built for.
DF_VERSION = "0.53.16"
DF_URL = "https://www.bay12games.com/dwarves/df_53_16_linux.tar.bz2"
DFHACK_VERSION = "53.16-r1.1"
DFHACK_URL = ("https://github.com/DFHack/dfhack/releases/download/"
              "%s/dfhack-%s-Linux-64bit.tar.bz2" % (DFHACK_VERSION, DFHACK_VERSION))
# Enforced, not just recorded. Until 2026-09-08 the fetch step computed a
# sha256 and echoed it into a log line without comparing it to anything, so
# `bzip2 -t` was the only real check: that catches a truncated download or an
# HTML error page, and proves nothing about *which* archive arrived. Bay12
# serves DF over plain releases with no signature, so the hash is the only pin
# there is. Values measured on the 2026-08-28 install and recorded in
# infra/local.df-vm-install.md.
DF_SHA256 = "2f9c0134b2465cccb705b8d3e322cdff07df7374ffbfafffe8f982f2ef7e7e7d"
DFHACK_SHA256 = "87e041a3e9d260fd9295170182a90eb27ea3c92f05471e4e65259b32f7cb0204"
# What `dfhack.getDFVersion()` returns on a correct install. The 'ITCH' build
# tag is how Classic identifies itself; a Steam build would say otherwise, and
# would not match this DFHack.
DF_VERSION_STRING = "v0.53.16 linux64 ITCH"

DF_ROOT = "/opt/df"
GAME_DIR = "/opt/df/game"
DIST_DIR = "/opt/df/dist"
LOG_DIR = "/opt/df/log"

# Beyond a bare Ubuntu cloud image. DF v50+ is SDL and has no text mode, so
# even headless it needs a real graphics stack -- Xvfb supplies the display and
# the agent never looks at it. Verified against `ldd ./dwarfort` on 2026-08-27:
# with these present nothing is missing except libfmod.so.13, which ships in
# the game root and resolves through the launcher's LD_LIBRARY_PATH.
PACKAGES = [
    "xvfb", "x11-utils",
    "libsdl2-2.0-0", "libsdl2-image-2.0-0", "libsdl2-ttf-2.0-0",
    "libsdl2-mixer-2.0-0",
    "libgl1-mesa-dri", "libglu1-mesa",
    "libopenal1", "libncursesw6", "libgtk-3-0",
    "bzip2", "curl", "tar",
]

# Xvfb display and geometry. 1280x800 for the framebuffer, 1280x720 for the
# game window inside it, which is what init.txt is set to below.
DISPLAY_NUM = ":99"
FB_GEOMETRY = "1280x800x24"

# prefs/init.txt overrides applied to a copy of data/init/init_default.txt.
# SOUND:NO because the VM has no audio device; 2D because there is no GPU.
INIT_SETTINGS = [
    ("SOUND", "NO"),
    ("WINDOWED", "YES"),
    ("WINDOWEDX", "1280"),
    ("WINDOWEDY", "720"),
    ("PRINT_MODE", "2D"),
]

SWAP_SIZE = "4G"
SWAPPINESS = 10

# Preset names are compiled into the binary, not read from any file.
WORLD_PRESETS = [
    "POCKET ISLAND", "POCKET REGION", "SMALLER REGION", "SMALL REGION",
    "SMALL ISLAND", "MEDIUM REGION", "MEDIUM ISLAND", "LARGE REGION",
    "LARGE ISLAND", "CREATE WORLD NOW",
]
DEFAULT_PRESET = "POCKET ISLAND"


# --- transport -----------------------------------------------------------

def remote(env, ip, script, label="remote", timeout=600, check=True,
           sudo=False, dry_run=False):
    """Run a multi-line bash script in the guest.

    The script is base64'd onto the command line rather than quoted into it.
    Two shells parse an ssh command string (the local one building argv, the
    remote login shell), and these scripts contain quotes, '$', backslashes and
    a path with spaces in it -- 'Bay 12 Games'. Encoding sidesteps both passes
    entirely; base64's alphabet has nothing either shell reacts to.

    'set -euo pipefail' is prepended so a step that fails halfway stops there
    instead of reporting the exit status of whatever ran last.
    """
    body = "set -euo pipefail\n" + script
    if dry_run:
        log("--- %s (dry run, not executed) ---" % label)
        log(body)
        log("--- end %s ---" % label)
        return None
    payload = base64.b64encode(body.encode("utf-8")).decode("ascii")
    shell = "sudo -H bash -s" if sudo else "bash -s"
    proc = ssh_guest(env, ip, "echo %s | base64 -d | %s" % (payload, shell),
                     timeout=timeout, check=False)
    if check and proc.returncode != 0:
        raise PVEError("%s failed (exit %s):\n%s"
                       % (label, proc.returncode,
                          (proc.stdout + proc.stderr).strip()))
    return proc


def scp_from(env, ip, remote_path, local_path):
    """Pull one file out of the guest, with ssh_guest's option set.

    Kept separate from remote() because tar output is binary and ssh_guest
    decodes stdout as text -- piping an archive through it corrupts the
    archive rather than failing, which is the worst way to lose a backup.
    """
    key = os.path.expanduser(env.get("DF_SSH_KEY", ""))
    if not key or not os.path.exists(key):
        raise PVEError("DF_SSH_KEY not found: %s" % key)
    argv = [
        "scp", "-i", key,
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=%s" % os.path.join(
            tempfile.gettempdir(), "df-overseer-throwaway-known-hosts"),
        "-o", "ConnectTimeout=10",
        "-o", "LogLevel=ERROR",
        "%s@%s:%s" % (env.get("DF_CIUSER", "df"), ip, remote_path),
        local_path,
    ]
    # See provision_vm.ssh_guest for why encoding/errors are explicit here.
    proc = subprocess.run(argv, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=600)
    if proc.returncode != 0:
        raise PVEError("scp failed (%s): %s"
                       % (proc.returncode, (proc.stderr or proc.stdout).strip()))


def guest_ip(pve, vmid):
    """Where to SSH. DF_VM_IP wins; otherwise ask the guest agent.

    Asking the agent rather than pinning an address is what lets a rebuilt VM
    be installed onto without editing .env -- though the MAC override in
    DF_MAC_OVERRIDES should mean a rebuild lands back on the same DHCP
    reservation anyway.

    A tailnet address is ranked last: this host reaches the VM over a subnet
    route to its LAN address, so the 100.64/10 address the VM reports is not
    necessarily one we can open a connection to.
    """
    override = pve.env.get("DF_VM_IP")
    if override:
        log("guest ip %s (DF_VM_IP)" % override)
        return override
    try:
        ifaces = pve.get(pve.vm_path(vmid, "/agent/network-get-interfaces"))
    except PVEError as exc:
        raise PVEError(
            "could not ask VM %s where it is: %s\n"
            "  Is the VM running, and does it have the guest agent? Set"
            " DF_VM_IP in .env to skip this lookup." % (vmid, exc))
    addrs = []
    for iface in (ifaces or {}).get("result", []):
        if iface.get("name") == "lo":
            continue
        for addr in iface.get("ip-addresses", []):
            ip = addr.get("ip-address", "")
            if addr.get("ip-address-type") != "ipv4" or ip.startswith("127."):
                continue
            octets = ip.split(".")
            tailnet = octets[0] == "100" and 64 <= int(octets[1]) <= 127
            addrs.append((1 if tailnet else 0, ip))
    if not addrs:
        raise PVEError("guest agent reported no usable ipv4 for VM %s" % vmid)
    addrs.sort()
    ip = addrs[0][1]
    others = ", ".join(a[1] for a in addrs[1:])
    log("guest ip %s (from the guest agent%s)"
        % (ip, ", other candidates: " + others if others else ""))
    return ip


def resolve_vmid(pve, args):
    vmid = getattr(args, "vmid", None) or pve.env.get("DF_VMID")
    if not vmid:
        raise PVEError("no --vmid given and DF_VMID is not set in .env")
    return int(vmid)


def target(pve, args):
    """(vmid, ip) for a command. Under --dry-run, no API call and no live VM."""
    vmid = resolve_vmid(pve, args)
    if args.dry_run:
        return vmid, "<dry-run>"
    return vmid, guest_ip(pve, vmid)


# --- shared shell fragments ----------------------------------------------

# The save path is the single most expensive thing to get wrong here. The
# Linux v50 build writes under XDG, NOT <df>/data/save -- which is the pre-v50
# layout and still what most community writeups say. A backup or snapshot
# script aimed at the game directory copies nothing and reports success.
# Resolved from passwd rather than $HOME so it is still correct under sudo.
SAVE_PATH_SH = '''
DF_USER="%(user)s"
DF_HOME="$(getent passwd "$DF_USER" | cut -d: -f6)"
SAVE_DIR="$DF_HOME/.local/share/Bay 12 Games/Dwarf Fortress/save"
'''


def save_path_sh(env):
    return SAVE_PATH_SH % {"user": env.get("DF_CIUSER", "df")}


XVFB_SH = '''
export DISPLAY=%(display)s
mkdir -p %(logdir)s
if ! xdpyinfo -display %(display)s >/dev/null 2>&1; then
  setsid nohup Xvfb %(display)s -screen 0 %(geometry)s -nolisten tcp \\
    > %(logdir)s/xvfb.out 2>&1 < /dev/null &
  for _ in $(seq 1 30); do
    if xdpyinfo -display %(display)s >/dev/null 2>&1; then break; fi
    sleep 1
  done
  xdpyinfo -display %(display)s >/dev/null 2>&1 \\
    || { echo "Xvfb never came up on %(display)s"; exit 1; }
  echo "Xvfb started on %(display)s"
else
  echo "Xvfb already on %(display)s"
fi
'''


def xvfb_sh():
    return XVFB_SH % {"display": DISPLAY_NUM, "geometry": FB_GEOMETRY,
                      "logdir": LOG_DIR}


# dfhack-run wraps its output in ANSI colour codes even with stdout not a tty,
# and ends with a bare reset sequence on a line of its own. `tail -n1` there
# returns the escape, not the answer -- caught on VM 104 on 2026-08-28, where
# the version check was comparing "\x1b[0m" against the version string and
# would have reported a correct install as wrong. Strip the escapes, drop what
# is then blank, and take the last line left.
DFHACK_LUA_SH = '''
dfhack_lua() {
  ( cd %(game)s && ./dfhack-run lua "$1" 2>&1 ) \\
    | sed -e 's/\\x1b\\[[0-9;]*m//g' -e 's/\\r$//' \\
    | grep -v '^[[:space:]]*$' \\
    | tail -n1 || true
}
'''


def dfhack_lua_sh():
    return DFHACK_LUA_SH % {"game": GAME_DIR}


# --- systemd ---------------------------------------------------------------

# Two units rather than one process tree, because Xvfb and dwarfort have
# different failure handling: Xvfb restarting is safe and should happen
# automatically, but dwarfort restarting on its own would silently start a
# fresh process without the save discipline in systemd-stop.sh ever running.
XVFB_UNIT = '''[Unit]
Description=Xvfb virtual display for Dwarf Fortress
After=network.target

[Service]
Type=simple
User=%(user)s
ExecStart=/usr/bin/Xvfb %(display)s -screen 0 %(geometry)s -nolisten tcp
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
'''

# ExecStartPre polls for the display rather than trusting unit ordering:
# systemd considers df-xvfb "started" the instant Xvfb forks, not once it is
# accepting connections, and dwarfort launched against a display that is not
# there yet exits before dfhack-run has anything to talk to.
WAIT_XVFB_SH = '''#!/bin/bash
for _ in $(seq 1 30); do
  DISPLAY=%(display)s xdpyinfo >/dev/null 2>&1 && exit 0
  sleep 1
done
echo "Xvfb never came up on %(display)s" >&2
exit 1
'''

# The load-bearing piece: DF ignores SIGTERM (verified 2026-08-28 -- 'stop'
# always runs the full timeout before SIGKILL is needed), so systemd's default
# kill sequence would lose the fort on every host reboot. ExecStop is this
# script instead of systemd's own kill: it quicksaves unconditionally --
# unlike install_df.py's manual 'stop --save', there is no one at the console
# to decide, and 'once a fort is live, saving before stopping is mandatory' --
# then falls through to the same TERM-then-KILL escalation as cmd_stop.
STOP_SH = '''#!/bin/bash
cd %(game)s
if ! pgrep -x dwarfort >/dev/null 2>&1; then
  exit 0
fi
./dfhack-run quicksave > %(logdir)s/systemd-stop.out 2>&1 || true
sleep 5
pkill -TERM -x dwarfort || true
for _ in $(seq 1 30); do
  pgrep -x dwarfort >/dev/null 2>&1 || exit 0
  sleep 1
done
pkill -KILL -x dwarfort || true
sleep 2
exit 0
'''

# TimeoutStopSec covers ExecStop's own worst case (quicksave, unmeasured on a
# live fort -- no fort has been embarked yet -- plus the 5s settle, the 30s
# TERM wait, and the 2s KILL settle) with margin. Revisit once a real fort's
# quicksave time is known.
DF_UNIT = '''[Unit]
Description=Dwarf Fortress (DFHack), headless
After=df-xvfb.service network.target
Requires=df-xvfb.service

[Service]
Type=simple
User=%(user)s
WorkingDirectory=%(game)s
Environment=DISPLAY=%(display)s
ExecStartPre=%(game)s/systemd-wait-xvfb.sh
ExecStart=%(game)s/dfhack
ExecStop=%(game)s/systemd-stop.sh
TimeoutStopSec=180
Restart=no
# ExecStop does its own kill (quicksave first, DF ignores SIGTERM) rather than
# systemd's built-in one. MainPID is './dfhack', a launcher script that waits
# on dwarfort and re-exits with dwarfort's signal folded into its own exit
# code (bash's wait/$? convention) rather than dying by that signal itself --
# confirmed on VM 104 on 2026-08-30: 'systemctl status' showed
# 'ExecStart=...dfhack (code=exited, status=137)', an EXIT CODE, not a
# signal death, so listing SIGKILL by name here did not help. 137 = 128+9
# (SIGKILL), 143 = 128+15 (SIGTERM), for whichever escalation step actually
# ends it. Without this, 'systemctl is-active' reads 'failed' after every
# clean stop, a false alarm for any future health check reading unit state.
SuccessExitStatus=137 143

[Install]
WantedBy=multi-user.target
'''


def cmd_systemd(pve, args):
    """Install (or update) the df-xvfb and df-fortress units, and enable them.

    Does not start either unit by default: DF may already be running from a
    manual 'start', and systemd starting a second instance would contend for
    the RPC port and the save directory the same way '-gen' does. Pass
    --start to start them now instead of waiting for the next boot.
    """
    vmid, ip = target(pve, args)
    user = pve.env.get("DF_CIUSER", "df")
    log("installing systemd units on VM %s" % vmid)
    helpers = '''
install -d -m755 %(game)s
cat > %(game)s/systemd-wait-xvfb.sh <<'EOF'
%(wait_sh)s
EOF
cat > %(game)s/systemd-stop.sh <<'EOF'
%(stop_sh)s
EOF
chmod +x %(game)s/systemd-wait-xvfb.sh %(game)s/systemd-stop.sh
chown %(user)s:%(user)s %(game)s/systemd-wait-xvfb.sh %(game)s/systemd-stop.sh

cat > /etc/systemd/system/df-xvfb.service <<'EOF'
%(xvfb_unit)s
EOF
cat > /etc/systemd/system/df-fortress.service <<'EOF'
%(df_unit)s
EOF
systemctl daemon-reload
systemctl enable df-xvfb.service df-fortress.service
echo "units installed and enabled"
systemctl is-enabled df-xvfb.service df-fortress.service
''' % {
        "game": GAME_DIR,
        "user": user,
        "wait_sh": WAIT_XVFB_SH % {"display": DISPLAY_NUM},
        "stop_sh": STOP_SH % {"game": GAME_DIR, "logdir": LOG_DIR},
        "xvfb_unit": XVFB_UNIT % {"user": user, "display": DISPLAY_NUM,
                                  "geometry": FB_GEOMETRY},
        "df_unit": DF_UNIT % {"user": user, "game": GAME_DIR,
                              "display": DISPLAY_NUM},
    }
    proc = remote(pve.env, ip, helpers, "systemd install", timeout=120,
                  sudo=True, dry_run=args.dry_run)
    if proc:
        for line in proc.stdout.strip().splitlines():
            log("  " + line)

    if args.start:
        log("starting units now")
        # is-active/is-enabled, not 'systemctl status': status's unit-state
        # bullet is a non-ASCII glyph, and the workstation's subprocess pipe
        # decodes as cp1252, which raised UnicodeDecodeError on that byte
        # rather than the VM -- caught starting these units for the first
        # time on 2026-08-30.
        script = '''
systemctl start df-xvfb.service df-fortress.service
sleep 2
for u in df-xvfb.service df-fortress.service; do
  echo "$u: active=$(systemctl is-active "$u") enabled=$(systemctl is-enabled "$u")"
done
'''
        proc = remote(pve.env, ip, script, "systemd start", timeout=120,
                      sudo=True, check=False, dry_run=args.dry_run)
        if proc:
            for line in proc.stdout.strip().splitlines():
                log("  " + line)
            if proc.returncode != 0:
                raise PVEError("systemd start reported a problem; check the"
                               " lines above and 'journalctl -u df-fortress'"
                               " on the VM")
    else:
        log("units enabled for next boot, not started. Pass --start to start"
            " them now, or 'systemctl start df-fortress' on the VM -- after"
            " stopping any manually-launched instance first (install_df.py"
            " stop), since the two would contend for the RPC port.")


# --- install -------------------------------------------------------------

def step_packages(env, ip, args):
    log("[1/5] packages")
    script = '''
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq %s
echo "packages ok"
''' % " ".join(PACKAGES)
    proc = remote(env, ip, script, "packages", timeout=1800, sudo=True,
                  dry_run=args.dry_run)
    if proc:
        log("  " + proc.stdout.strip().splitlines()[-1])


def step_swap(env, ip, args):
    """A 4 GB swapfile.

    Not because worldgen needs it -- it does not; a whole POCKET ISLAND gen
    peaked at 561 MB RSS and never touched swap. It is a floor under the
    question that is still open: a long-running fort with hundreds of units
    and years of accumulated items, which nobody has measured yet.
    """
    log("[2/5] swapfile (%s, swappiness %d)" % (SWAP_SIZE, SWAPPINESS))
    script = '''
if swapon --show=NAME --noheadings | grep -qx /swapfile; then
  echo "swapfile already active"
else
  if [ ! -f /swapfile ]; then
    fallocate -l %(size)s /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=4096
  fi
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  echo "swapfile created and active"
fi
if ! grep -qE '^/swapfile[[:space:]]' /etc/fstab; then
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "swapfile added to /etc/fstab"
fi
echo 'vm.swappiness=%(swappiness)d' > /etc/sysctl.d/99-df-overseer.conf
sysctl -q vm.swappiness=%(swappiness)d
swapon --show
''' % {"size": SWAP_SIZE, "swappiness": SWAPPINESS}
    proc = remote(env, ip, script, "swapfile", timeout=300, sudo=True,
                  dry_run=args.dry_run)
    if proc:
        for line in proc.stdout.strip().splitlines():
            log("  " + line)


def step_fetch(env, ip, args):
    log("[3/5] fetching tarballs into %s" % DIST_DIR)
    script = '''
install -d -o %(user)s -g %(user)s %(root)s %(dist)s %(logdir)s
cd %(dist)s
fetch() {
  url="$1"; name="$2"; want="$3"
  if [ -s "$name" ]; then
    echo "have $name ($(stat -c%%s "$name") bytes)"
  else
    curl -fsSL --retry 3 -o "$name.part" "$url"
    mv "$name.part" "$name"
    echo "fetched $name ($(stat -c%%s "$name") bytes)"
  fi
  # A truncated download or an HTML error page extracts as garbage rather than
  # failing, so prove it is really a bzip2 archive before anything unpacks it.
  bzip2 -t "$name"
  # Then prove it is the *right* archive. This runs on the cached path too, so
  # a wrong file already sitting in dist/ is caught rather than trusted.
  got=$(sha256sum "$name" | cut -d' ' -f1)
  if [ "$got" != "$want" ]; then
    echo "sha256 mismatch for $name" >&2
    echo "  expected $want" >&2
    echo "  got      $got" >&2
    echo "  refusing to unpack. If this is an intended version bump, update" >&2
    echo "  DF_SHA256/DFHACK_SHA256 in scripts/install_df.py deliberately." >&2
    exit 1
  fi
  echo "  bzip2 -t ok, sha256 pinned and matching: $name"
}
fetch "%(df_url)s" df.tar.bz2 "%(df_sha)s"
fetch "%(dfhack_url)s" dfhack.tar.bz2 "%(dfhack_sha)s"
chown -R %(user)s:%(user)s %(root)s
''' % {"user": env.get("DF_CIUSER", "df"), "root": DF_ROOT, "dist": DIST_DIR,
       "logdir": LOG_DIR, "df_url": DF_URL, "dfhack_url": DFHACK_URL,
       "df_sha": DF_SHA256, "dfhack_sha": DFHACK_SHA256}
    proc = remote(env, ip, script, "fetch", timeout=1800, sudo=True,
                  dry_run=args.dry_run)
    if proc:
        for line in proc.stdout.strip().splitlines():
            log("  " + line)


def step_extract(env, ip, args):
    """DF into the game dir, then DFHack over the top of it.

    That is the whole install -- there is no dfhooks folder split like the
    Windows Steam layout, and ./dfhack in the game root is the launcher.

    Each tarball is unpacked into a staging dir and the layout is then
    detected, because 'the archives are flat' is an assumption worth not
    making: if one wraps its contents in a single top-level directory, copying
    the staging dir verbatim buries the game a level down and every path below
    is wrong. Detecting it costs one 'ls' and turns a silent mislayout into a
    log line.
    """
    log("[4/5] extracting into %s%s"
        % (GAME_DIR, " (--force: existing install will be replaced)"
           if args.force else ""))
    script = '''
GAME=%(game)s
DIST=%(dist)s
FORCE=%(force)s

if [ -x "$GAME/dwarfort" ] && [ "$FORCE" != "1" ]; then
  echo "already installed ($GAME/dwarfort exists); pass --force to replace"
  exit 0
fi

unpack() {
  tarball="$1"; label="$2"
  stage="$(mktemp -d)"
  tar -xjf "$DIST/$tarball" -C "$stage"
  n="$(ls -A "$stage" | wc -l)"
  first="$(ls -A "$stage" | head -n1 || true)"
  if [ "$n" = "1" ] && [ -d "$stage/$first" ]; then
    echo "  $label: wrapped in $first/, descending"
    src="$stage/$first"
  else
    echo "  $label: flat archive, $n entries at top level"
    src="$stage"
  fi
  mkdir -p "$GAME"
  cp -a "$src/." "$GAME/"
  rm -rf "$stage"
}

if [ "$FORCE" = "1" ] && [ -d "$GAME" ]; then
  echo "  removing existing $GAME"
  rm -rf "$GAME"
fi
mkdir -p "$GAME"
unpack df.tar.bz2 "DF %(dfver)s"
unpack dfhack.tar.bz2 "DFHack %(dfhackver)s"

# Prove both halves landed. Without this the failure surfaces much later as
# "the launcher is not there", with nothing saying which unpack went wrong.
for f in dwarfort dfhack dfhack-run; do
  [ -e "$GAME/$f" ] || { echo "MISSING after extract: $GAME/$f"; exit 1; }
done
chmod +x "$GAME/dwarfort" "$GAME/dfhack" "$GAME/dfhack-run"
echo "  extracted: dwarfort, dfhack, dfhack-run present"
''' % {"game": GAME_DIR, "dist": DIST_DIR, "force": "1" if args.force else "0",
       "dfver": DF_VERSION, "dfhackver": DFHACK_VERSION}
    proc = remote(env, ip, script, "extract", timeout=900,
                  dry_run=args.dry_run)
    if proc:
        for line in proc.stdout.strip().splitlines():
            log("  " + line)


def step_init(env, ip, args):
    """prefs/init.txt, from init_default.txt with the headless overrides.

    Each setting is applied and then read back. sed exits 0 when its pattern
    matches nothing, so a key renamed between DF versions would otherwise be
    silently skipped and the game would come up asking for sound on a machine
    with no audio device.
    """
    log("[5/5] prefs/init.txt")
    sed_lines = "\n".join(
        "sed -i -E 's/\\[%s:[^]]*\\]/[%s:%s]/' \"$INIT\"" % (key, key, value)
        for key, value in INIT_SETTINGS)
    check_lines = "\n".join("check %s %s" % kv for kv in INIT_SETTINGS)
    script = '''
GAME=%(game)s
INIT="$GAME/prefs/init.txt"
mkdir -p "$GAME/prefs"
if [ ! -f "$INIT" ] || [ "%(force)s" = "1" ]; then
  cp "$GAME/data/init/init_default.txt" "$INIT"
  echo "  init.txt seeded from data/init/init_default.txt"
fi

%(sed)s

fail=0
check() {
  key="$1"; want="$2"
  got="$(grep -oE "\\[$key:[^]]*\\]" "$INIT" | head -n1 || true)"
  if [ "$got" != "[$key:$want]" ]; then
    echo "  NOT SET: expected [$key:$want], found '${got:-nothing}'"
    fail=1
  else
    echo "  $got"
  fi
}
%(check)s
exit $fail
''' % {"game": GAME_DIR, "force": "1" if args.force else "0",
       "sed": sed_lines, "check": check_lines}
    proc = remote(env, ip, script, "init.txt", timeout=120,
                  dry_run=args.dry_run)
    if proc:
        for line in proc.stdout.strip().splitlines():
            log(line if line.startswith("  ") else "  " + line)


def cmd_install(pve, args):
    vmid, ip = target(pve, args)
    log("installing DF %s + DFHack %s on VM %s"
        % (DF_VERSION, DFHACK_VERSION, vmid))
    step_packages(pve.env, ip, args)
    step_swap(pve.env, ip, args)
    step_fetch(pve.env, ip, args)
    step_extract(pve.env, ip, args)
    step_init(pve.env, ip, args)
    if args.dry_run:
        return
    log("install done. Next: install_df.py start, then verify")


# --- run/stop ------------------------------------------------------------

def cmd_start(pve, args):
    """Start Xvfb and the game, and wait for the RPC socket.

    The game is detached twice over: setsid for a new session, nohup against
    SIGHUP, stdin from /dev/null. That last one has a visible consequence --
    with stdin not a tty the DFHack console logs "Console is shutting down
    properly" and exits. The game keeps running and the remote interface is
    unaffected, so that line is expected output, not an error. Control comes
    from ./dfhack-run instead.
    """
    vmid, ip = target(pve, args)
    log("starting Xvfb and DF on VM %s" % vmid)
    script = xvfb_sh() + dfhack_lua_sh() + '''
cd %(game)s
if pgrep -x dwarfort >/dev/null 2>&1; then
  echo "dwarfort already running (pid $(pgrep -x dwarfort | tr '\\n' ' '))"
  exit 0
fi
setsid nohup ./dfhack > %(logdir)s/dfhack.out 2>&1 < /dev/null &
# Readiness is two independent conditions, and both are needed. Testing only
# that dfhack_lua returned *something* does not work: when the game is not up
# yet dfhack-run prints "Could not connect to localhost:5000", which is
# non-empty, so the loop broke on its first pass and the socket check below
# then ran against a game that had been alive for under a second. That is what
# made a perfectly healthy start report a 240s timeout on 2026-08-28. Measured
# on VM 104 the same day: launch to listening socket is about 10 seconds.
deadline=$(( $(date +%%s) + %(wait)d ))
while [ "$(date +%%s)" -lt "$deadline" ]; do
  if ss -ltn 2>/dev/null | grep -qE '127\\.0\\.0\\.1:5000'; then
    ver="$(dfhack_lua "print(dfhack.getDFVersion())")"
    # Non-empty AND not the connect error. Substring removal rather than a
    # grep so an empty $ver cannot make this accidentally true.
    if [ -n "$ver" ] && [ "${ver#*Could not connect}" = "$ver" ]; then
      break
    fi
  fi
  sleep 2
done
ver="$(dfhack_lua "print(dfhack.getDFVersion())")"
echo "version: ${ver:-<no answer yet>}"
# The RPC socket is what the overseer will actually talk to, so its absence is
# the failure that matters: a running dwarfort with no listener looks healthy
# to pgrep and is useless.
if ss -ltn 2>/dev/null | grep -E '127\\.0\\.0\\.1:5000'; then
  :
else
  # Say which of the two happened. A bare "RPC is NOT listening" sends the
  # next session hunting a crash that may not have occurred: the process can
  # be alive and simply not finished starting.
  if pgrep -x dwarfort >/dev/null 2>&1; then
    echo "dwarfort IS running (pid $(pgrep -x dwarfort | tr '\\n' ' ')) but RPC"
    echo "  has not appeared within %(wait)ds. It may still be coming up:"
    echo "  re-run 'verify', or 'start --wait N' with a longer window,"
    echo "  before treating this as a failure."
  else
    echo "dwarfort is NOT running. See %(logdir)s/dfhack.out on the VM."
  fi
  exit 1
fi
''' % {"game": GAME_DIR, "logdir": LOG_DIR, "wait": args.wait}
    proc = remote(pve.env, ip, script, "start", timeout=args.wait + 180,
                  dry_run=args.dry_run)
    if proc:
        for line in proc.stdout.strip().splitlines():
            log("  " + line)
        log("note: this manual instance is not managed by systemd and will"
            " not survive a reboot. For that, use 'install_df.py systemd"
            " --start' instead (stop this one first with 'stop').")


def cmd_stop(pve, args):
    """Stop DF, optionally saving first.

    --save is off by default and deliberately so: quicksave only means anything
    in fortress mode, and calling it elsewhere is a no-op that would make the
    flag read as a guarantee it is not.
    """
    vmid, ip = target(pve, args)
    log("stopping DF on VM %s%s"
        % (vmid, " (quicksave first)" if args.save else ""))
    script = '''
cd %(game)s
if ! pgrep -x dwarfort >/dev/null 2>&1; then
  echo "dwarfort is not running"
  exit 0
fi
if [ "%(save)s" = "1" ]; then
  echo "quicksave: $(./dfhack-run quicksave 2>&1 | tail -n1)"
  sleep 5
fi
pkill -TERM -x dwarfort || true
for _ in $(seq 1 30); do
  pgrep -x dwarfort >/dev/null 2>&1 || { echo "stopped"; exit 0; }
  sleep 1
done
echo "did not exit on SIGTERM after 30s; sending SIGKILL"
pkill -KILL -x dwarfort || true
sleep 2
if pgrep -x dwarfort >/dev/null 2>&1; then echo "still running"; exit 1; fi
echo "stopped (killed)"
''' % {"game": GAME_DIR, "save": "1" if args.save else "0"}
    proc = remote(pve.env, ip, script, "stop", timeout=180,
                  dry_run=args.dry_run)
    if proc:
        for line in proc.stdout.strip().splitlines():
            log("  " + line)


# --- worldgen ------------------------------------------------------------

def cmd_gen(pve, args):
    """Generate a world headlessly, with the silent-failure check.

    './dfhack -gen <id> <seed> "<preset>"' generates and quits without the UI.
    It fails silently about a quarter of the time: two of eight runs on
    2026-08-27 exited 1 having generated the full history into save/current,
    then never renamed it or wrote any export, with nothing in gamelog.txt,
    errorlog.txt, stdout or stderr. So success is decided by the region
    directory existing, never by the exit code, and a failed attempt is
    retried with a fresh seed.

    Exit 134 (SIGABRT) is the one exit code that does mean something: the world
    id already exists. Retrying that with a new seed would fail identically, so
    it aborts instead.
    """
    if args.preset not in WORLD_PRESETS:
        raise PVEError("unknown preset %r. The preset names are compiled into"
                       " the binary; the valid ones are:\n  %s"
                       % (args.preset, "\n  ".join(WORLD_PRESETS)))
    vmid, ip = target(pve, args)
    world_id = args.world_id
    log("generating world %s on VM %s, preset %r, up to %d attempt(s)"
        % (world_id, vmid, args.preset, args.attempts))

    if not args.dry_run:
        running = remote(pve.env, ip, "pgrep -x dwarfort || true",
                         "running check", timeout=60)
        if running.stdout.strip() and not args.allow_running:
            raise PVEError(
                "dwarfort is already running on VM %s. '-gen' starts its own"
                " instance and the two contend for the RPC port and the save"
                " directory.\n  Stop it first (install_df.py stop), or pass"
                " --allow-running." % vmid)

    for attempt in range(1, args.attempts + 1):
        seed = args.seed if args.seed is not None \
            else str(random.randint(1, 2 ** 31 - 1))
        log("attempt %d/%d, seed %s" % (attempt, args.attempts, seed))
        script = xvfb_sh() + save_path_sh(pve.env) + '''
cd %(game)s
export DISPLAY=%(display)s
# save/current is sampled BEFORE the run. It routinely survives from an
# earlier failed gen, so its mere presence afterwards proves nothing -- on VM
# 104 a stale one from 2026-08-27 was still sitting there. Only a current
# whose mtime moved was written by this attempt.
before=""
if [ -d "$SAVE_DIR/current" ]; then before="$(stat -c %%Y "$SAVE_DIR/current")"; fi
rc=0
./dfhack -gen "%(id)s" "%(seed)s" "%(preset)s" \\
  > %(logdir)s/gen-%(id)s.out 2>&1 || rc=$?
echo "exit:$rc"
if [ -d "$SAVE_DIR/region%(id)s" ]; then
  echo "region:present"
  echo "size:$(du -sh "$SAVE_DIR/region%(id)s" | cut -f1)"
else
  echo "region:absent"
  # The signature of the silent failure: a fully generated history left in
  # save/current that was never renamed. Worth distinguishing from "nothing
  # generated at all", which is a different problem with a different fix.
  if [ -d "$SAVE_DIR/current" ]; then
    after="$(stat -c %%Y "$SAVE_DIR/current")"
    if [ "$before" != "$after" ]; then
      echo "orphan:save/current was written by this attempt -- the silent -gen failure"
    else
      echo "orphan:save/current exists but predates this attempt, so it is stale"
      echo "       from an earlier run and says nothing about this one"
    fi
  fi
fi
''' % {"game": GAME_DIR, "display": DISPLAY_NUM, "logdir": LOG_DIR,
       "id": world_id, "seed": seed, "preset": args.preset}
        proc = remote(pve.env, ip, script, "gen", timeout=1800, check=False,
                      dry_run=args.dry_run)
        if args.dry_run:
            return
        out = proc.stdout
        for line in out.strip().splitlines():
            log("  " + line)
        if "exit:134" in out:
            raise PVEError(
                "world id %s already exists (SIGABRT, the documented abort)."
                " Pick another --world-id, or delete the existing region."
                % world_id)
        if "region:present" in out:
            log("world %s generated on attempt %d with seed %s"
                % (world_id, attempt, seed))
            return
        if attempt < args.attempts:
            log("  no region directory: this attempt failed regardless of its"
                " exit code. Retrying with a fresh seed.")
            if args.seed is not None:
                log("  NOTE: --seed is pinned, so the retry reuses it and will"
                    " very likely fail identically.")
    raise PVEError("worldgen did not produce save/region%s after %d attempts."
                   " Check %s/gen-%s.out on the VM."
                   % (world_id, args.attempts, LOG_DIR, world_id))


# --- verify / saves / backup ---------------------------------------------

def cmd_verify(pve, args):
    """Check the install, separating what is true on disk from what is true
    only while the game is running.

    Reported as PASS/FAIL per item rather than one verdict: "the install is
    fine" is not a useful thing to be told when the interesting answer is
    which of a dozen things is not.
    """
    vmid, ip = target(pve, args)
    log("verifying VM %s" % vmid)
    script = save_path_sh(pve.env) + dfhack_lua_sh() + '''
GAME=%(game)s
fail=0
ok()   { echo "  PASS  $1"; }
bad()  { echo "  FAIL  $1"; fail=1; }
info() { echo "  ....  $1"; }

if [ -x "$GAME/dwarfort" ]; then ok "dwarfort present"; else bad "dwarfort missing"; fi
if [ -x "$GAME/dfhack" ]; then ok "dfhack launcher present"; else bad "dfhack missing"; fi
if [ -x "$GAME/dfhack-run" ]; then ok "dfhack-run present"; else bad "dfhack-run missing"; fi
if [ -d "$GAME/hack" ]; then ok "hack/ present (DFHack unpacked over DF)"
else bad "hack/ missing -- DFHack did not land on top of DF"; fi

# libfmod.so.13 is expected to show as missing here: it ships in the game root
# and resolves at runtime through the launcher's LD_LIBRARY_PATH, not through
# the linker's default search path. Anything else missing is real.
missing="$(cd "$GAME" && ldd ./dwarfort 2>/dev/null | grep 'not found' \\
           | grep -v libfmod || true)"
if [ -z "$missing" ]; then ok "no missing shared libraries"
else bad "missing libraries:"; echo "$missing" | sed 's/^/          /'; fi

for kv in %(initpairs)s; do
  key="${kv%%%%=*}"; want="${kv##*=}"
  got="$(grep -oE "\\[$key:[^]]*\\]" "$GAME/prefs/init.txt" 2>/dev/null \\
         | head -n1 || true)"
  if [ "$got" = "[$key:$want]" ]; then ok "init.txt $got"
  else bad "init.txt $key is '${got:-unset}', want [$key:$want]"; fi
done

if swapon --show=NAME --noheadings | grep -qx /swapfile; then ok "swapfile active"
else bad "swapfile not active"; fi
if grep -qE '^/swapfile[[:space:]]' /etc/fstab; then
  ok "swapfile in /etc/fstab (survives reboot)"
else bad "swapfile not in /etc/fstab"; fi

# The XDG save path, checked as a path rather than assumed. This is the trap
# that makes a backup script silently copy nothing.
if [ -d "$SAVE_DIR" ]; then
  ok "save dir exists: $SAVE_DIR"
  info "worlds: $(ls -1 "$SAVE_DIR" 2>/dev/null | tr '\\n' ' ')"
else
  info "no save dir yet at $SAVE_DIR (expected before the first worldgen)"
fi
if [ -d "$GAME/data/save" ]; then
  bad "$GAME/data/save exists -- that is the pre-v50 layout, not the real save path"
else ok "no misleading $GAME/data/save"; fi

if pgrep -x dwarfort >/dev/null 2>&1; then
  ok "dwarfort is running (pid $(pgrep -x dwarfort | tr '\\n' ' '))"
  ver="$(dfhack_lua "print(dfhack.getDFVersion())")"
  if [ "$ver" = "%(dfver)s" ]; then ok "version: $ver"
  else bad "version is '$ver', want '%(dfver)s'"; fi
  if ss -ltn 2>/dev/null | grep -qE '127\\.0\\.0\\.1:5000'; then
    ok "RPC listening on 127.0.0.1:5000"
  else bad "RPC not listening on 127.0.0.1:5000"; fi
  if ss -ltn 2>/dev/null | grep -qE '(^|[^0-9.])0\\.0\\.0\\.0:5000'; then
    bad "RPC is bound to 0.0.0.0 -- exposed off-box"
  else ok "RPC not exposed off-box"; fi
else
  info "dwarfort is not running; version and RPC checks skipped"
  info "run: install_df.py start"
fi

check_unit() {
  # 'systemctl is-enabled' by itself, not piped through grep: under
  # 'set -o pipefail' (this whole script runs with it) 'list-unit-files |
  # grep -q' reported every unit as absent on VM 104 on 2026-08-30, because
  # grep -q exits the instant it matches, SIGPIPEs the still-writing
  # systemctl, and pipefail turns that SIGPIPE into a pipeline failure --
  # even though the match was real. A bare command substitution has no
  # downstream reader to close early, so it has nothing to race.
  name="$1"
  state="$(systemctl is-enabled "$name" 2>/dev/null || true)"
  case "$state" in
    enabled) ok "$name installed and enabled" ;;
    "") info "$name not installed (run: install_df.py systemd)" ;;
    *) bad "$name installed but state is '$state', not enabled -- will not survive a reboot" ;;
  esac
}
check_unit df-xvfb.service
check_unit df-fortress.service
exit $fail
''' % {"game": GAME_DIR, "dfver": DF_VERSION_STRING,
       "initpairs": " ".join("%s=%s" % kv for kv in INIT_SETTINGS)}
    proc = remote(pve.env, ip, script, "verify", timeout=300, check=False,
                  dry_run=args.dry_run)
    if args.dry_run:
        return
    for line in proc.stdout.rstrip().splitlines():
        log(line)
    if proc.stderr.strip():
        log(proc.stderr.strip())
    if proc.returncode != 0:
        raise PVEError("verify found problems (see the FAIL lines above)")
    log("all checks passed")


def cmd_saves(pve, args):
    vmid, ip = target(pve, args)
    script = save_path_sh(pve.env) + '''
echo "save dir: $SAVE_DIR"
if [ ! -d "$SAVE_DIR" ]; then echo "  (does not exist yet)"; exit 0; fi
du -sh "$SAVE_DIR"/* 2>/dev/null | sed 's/^/  /' || echo "  (empty)"
'''
    proc = remote(pve.env, ip, script, "saves", timeout=120,
                  dry_run=args.dry_run)
    if proc:
        for line in proc.stdout.rstrip().splitlines():
            log(line)


def cmd_backup(pve, args):
    """Pull the save directory off the VM.

    Archived on the guest and then copied, rather than streamed, so what lands
    locally can be size-checked against what was made. A backup that silently
    produces an empty file is the failure worth an extra step to rule out.
    """
    vmid, ip = target(pve, args)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = "df-saves-%s-%s.tar.gz" % (vmid, stamp)
    remote_tmp = "/tmp/%s" % name
    out_dir = args.out if os.path.isabs(args.out) \
        else os.path.join(REPO_ROOT, args.out)
    script = save_path_sh(pve.env) + '''
if [ ! -d "$SAVE_DIR" ]; then
  echo "no save dir at $SAVE_DIR -- nothing to back up"
  exit 1
fi
if [ -z "$(ls -A "$SAVE_DIR")" ]; then
  echo "save dir is empty -- nothing to back up"
  exit 1
fi
tar -C "$(dirname "$SAVE_DIR")" -czf %(tmp)s "$(basename "$SAVE_DIR")"
echo "archived $(du -sh %(tmp)s | cut -f1) from $SAVE_DIR"
tar -tzf %(tmp)s | wc -l | sed 's/^/entries:/'
''' % {"tmp": remote_tmp}
    proc = remote(pve.env, ip, script, "backup", timeout=900,
                  dry_run=args.dry_run)
    if args.dry_run:
        log("would copy %s -> %s" % (remote_tmp, os.path.join(out_dir, name)))
        return
    for line in proc.stdout.strip().splitlines():
        log("  " + line)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    local = os.path.join(out_dir, name)
    scp_from(pve.env, ip, remote_tmp, local)
    size = os.path.getsize(local)
    remote(pve.env, ip, "rm -f %s" % remote_tmp, "cleanup", timeout=60,
           check=False)
    if size < 1024:
        raise PVEError("backup landed at %s but is only %d bytes -- treat that"
                       " as a failure, not as a small fort" % (local, size))
    log("backup: %s (%.1f KB)" % (local, size / 1024.0))


# --- cli -----------------------------------------------------------------

def main():
    # --vmid and --dry-run are attached to the top-level parser AND to every
    # subparser, so both orderings work. argparse does not do this for you:
    # a top-level-only option must precede the subcommand, which contradicts
    # the usage text above and reads as a broken flag. The SUPPRESS defaults
    # are what makes the pair safe -- without them a subparser's unset default
    # overwrites the value the top-level parser already stored.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dry-run", action="store_true",
                        default=argparse.SUPPRESS,
                        help="print the remote script instead of running it;"
                             " makes no API call and needs no reachable VM")
    common.add_argument("--vmid", type=int, default=argparse.SUPPRESS,
                        help="defaults to DF_VMID in .env")

    parser = argparse.ArgumentParser(
        description=__doc__, parents=[common],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name, **kw):
        return sub.add_parser(name, parents=[common], **kw)

    inst = add("install", help="packages, swap, DF + DFHack, init.txt")
    inst.add_argument("--force", action="store_true",
                      help="replace an existing game dir and re-seed init.txt")

    add("verify", help="check the install, PASS/FAIL per item")
    start = add("start", help="start Xvfb and DF, wait for RPC")
    start.add_argument("--wait", type=int, default=120,
                       help="seconds to wait for the RPC socket."
                            " Measured launch-to-listening on VM 104 is"
                            " ~10s, so the default is a wide margin.")

    stop = add("stop", help="stop DF")
    stop.add_argument("--save", action="store_true",
                      help="quicksave first (fortress mode only)")

    gen = add("gen", help="generate a world headlessly")
    gen.add_argument("--world-id", default="1")
    gen.add_argument("--seed",
                     help="fixed seed; the default is a fresh random one per"
                          " attempt, which is what makes the retry useful")
    gen.add_argument("--preset", default=DEFAULT_PRESET,
                     help="default %r" % DEFAULT_PRESET)
    gen.add_argument("--attempts", type=int, default=3,
                     help="-gen fails silently ~25%% of the time; default 3")
    gen.add_argument("--allow-running", action="store_true",
                     help="generate even though dwarfort is already up")

    add("saves", help="list worlds in the XDG save dir, with sizes")

    backup = add("backup", help="pull the save dir off the VM")
    backup.add_argument("--out", default="backups",
                        help="local directory, default ./backups")

    systemd = add("systemd", help="install and enable the Xvfb + DF units")
    systemd.add_argument("--start", action="store_true",
                         help="also start the units now, instead of only"
                              " enabling them for the next boot")

    args = parser.parse_args()
    # SUPPRESS means an unsupplied flag leaves no attribute at all.
    args.vmid = getattr(args, "vmid", None)
    args.dry_run = getattr(args, "dry_run", False)
    pve = PVE()
    handler = {
        "install": cmd_install,
        "verify": cmd_verify,
        "start": cmd_start,
        "stop": cmd_stop,
        "gen": cmd_gen,
        "saves": cmd_saves,
        "backup": cmd_backup,
        "systemd": cmd_systemd,
    }[args.command]
    try:
        handler(pve, args)
    except PVEError as exc:
        log("FAILED: %s" % exc)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
