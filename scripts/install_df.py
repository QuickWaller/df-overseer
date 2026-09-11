"""Install Dwarf Fortress Classic + DFHack on a df-overseer VM, over SSH.

    python scripts/install_df.py install  [--vmid N] [--force]
    python scripts/install_df.py verify   [--vmid N]
    python scripts/install_df.py graphics [--source PATH]
    python scripts/install_df.py start   [--vmid N]
    python scripts/install_df.py stop    [--vmid N] [--save]
    python scripts/install_df.py gen     [--world-id 7] [--preset "POCKET ISLAND"]
    python scripts/install_df.py saves   [--vmid N]
    python scripts/install_df.py backup  [--vmid N] [--out backups]
    python scripts/install_df.py systemd [--vmid N] [--start]
    python scripts/install_df.py stream  [--interval 15] [--ingest-url URL]
    python scripts/install_df.py vnc     [--port 5900] [--password PW]
    python scripts/install_df.py webvnc  [--port 6080] [--vnc-port 5900]
    python scripts/install_df.py vnc-tunnel --relay-ip IP [--relay-user relay] [--vnc-port 5900]

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
import secrets
import shlex
import subprocess
import sys
import tarfile
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
    # Moved here from the template bake on 2026-09-08. The bake existed only
    # to install this package before the guest agent could be asked for the
    # VM's address; now the address is assigned at clone time instead, so
    # nothing needs the agent to exist before this install runs, and the
    # package can simply travel with the rest of the guest install.
    "qemu-guest-agent",
]

# Xvfb display and geometry. 1280x800 for the framebuffer, 1280x720 for the
# game window inside it, which is what init.txt is set to below.
DISPLAY_NUM = ":99"
FB_GEOMETRY = "1280x800x24"

STREAM_DIR = "/opt/df/stream"
VNC_DIR = "/opt/df/vnc"
VNC_PORT = 5900
NOVNC_PORT = 6080

# The authenticated personal-control channel (real mouse/keyboard, not
# view-only) is a second, separate instance of everything below -- its own
# port, its own systemd service, its own tunnel keypair -- never a mode
# switch on the existing public/LAN view-only path. See cmd_vnc's --control
# handling. Auth for this one is Cloudflare Access alone (gated at the edge,
# before any byte reaches the relay), not a second in-app password -- see
# provision_relay.py's cmd_webvnc --control, which binds loopback-only so
# Access is the only way in at all, not merely the intended one.
VNC_CONTROL_PORT = 5901
NOVNC_CONTROL_PORT = 6081

# prefs/init.txt overrides applied to a copy of data/init/init_default.txt.
# SOUND:NO because the VM has no audio device; 2D because there is no GPU.
#
# FONT/FULLFONT:curses_square_16x16.png -- nicer bitmap font for the VNC
# viewer, isolated and verified safe 2026-09-09.
#
# USE_CLASSIC_ASCII:NO -- re-added 2026-09-09 (second attempt), after being
# deliberately left out of this list the first time that same day. The first
# attempt's diagnosis was half right: flipping this to NO does switch the
# map's rendering path to expect real per-tile graphics data, and the map
# came back solid black because this build's graphics modules
# (data/vanilla/vanilla_*_graphics/, vanilla_world_map -- the actual v50+
# mod-module location; there is no raw/graphics folder at all in this DF
# version, an earlier session's shorthand for the same thing) genuinely had
# no PNG/graphics_*.txt content, confirmed on VM 103 directly: `find
# data/vanilla/vanilla_*_graphics -type f` returned only info.txt in each,
# and research/2026-09-09-df-modern-graphics.md independently confirmed this
# is a deliberate Classic/Premium content split, not a bug. What changed:
# the user's own legitimately-purchased Steam copy (confirmed local install,
# DF 53.15) has real content in those same module folders -- 583 PNGs across
# the eight modules in GRAPHICS_MODULES below -- and `install_df.py graphics`
# transplants it onto this install via scp, never through this public repo's
# git tree (the asset files are proprietary Kitfox-commissioned art and must
# never be committed). With that data present, USE_CLASSIC_ASCII:NO is safe:
# confirmed by a live screenshot and non-blank dfhack.screen.readTile buffer
# on the Site Finder screen. → decisions/DECISIONS.md 2026-09-09 rows.
INIT_SETTINGS = [
    ("SOUND", "NO"),
    ("WINDOWED", "YES"),
    ("WINDOWEDX", "1280"),
    ("WINDOWEDY", "720"),
    ("PRINT_MODE", "2D"),
    ("FONT", "curses_square_16x16.png"),
    ("FULLFONT", "curses_square_16x16.png"),
    ("USE_CLASSIC_ASCII", "NO"),
]

# The eight v50+ mod-module directories under data/vanilla/ that carry real
# tile-page graphics content on a Premium/Steam install and ship as empty
# info.txt-only stubs on free Classic (confirmed on VM 103 2026-09-09, and
# independently by research/2026-09-09-df-modern-graphics.md). Names, not
# paths: cmd_graphics resolves them against both a local source install and
# GAME_DIR/data/vanilla on the guest. All eight are already unconditionally
# part of every worldgen's mod list (confirmed via VM 103's own
# gen_modlist.txt from its existing world, generated with no mod-selection UI
# ever touched) -- vanilla_* modules are not opt-in, so no mod-selection
# screen automation is needed at all, just populating the folders these
# already-active empty modules point at.
GRAPHICS_MODULES = [
    "vanilla_buildings_graphics",
    "vanilla_creatures_graphics",
    "vanilla_creatures_extinct_graphics",
    "vanilla_descriptors_graphics",
    "vanilla_interactions_graphics",
    "vanilla_items_graphics",
    "vanilla_plants_graphics",
    "vanilla_world_map",
    # Found 2026-09-10, missed in the original 8: no "_graphics" suffix, so it
    # didn't match this list's own naming pattern. Unlike the others, free
    # Classic's copy is not a pure empty stub -- it already has
    # graphics_classic.txt (matches Steam's byte-for-byte) but is missing
    # graphics_interface.txt (236 KB) and every one of ~70 images entirely,
    # including interface_bits_embark.png -- confirmed the cause of a
    # user-reported missing UI panel on the embark/site-selection screen
    # (plain black background behind info text/dialogs, should show a
    # bordered panel). cp -a's overwrite-in-place behavior handles the
    # partial-module case fine: existing matching files are untouched,
    # missing ones are added.
    "vanilla_interface",
    # Found in the same 2026-09-10 pass, via a full recursive manifest diff
    # of every file under data/vanilla (not just spot-checks) after the user
    # asked "what else is missing" -- this module was ~95 files short, the
    # single largest gap found: walls, floors, water/liquids, ramps, blood,
    # fire, snow -- the core terrain tile graphics used throughout actual
    # fortress-mode play, not just the embark screen. Would have surfaced as
    # a much worse blank-terrain problem once a fort was founded, not caught
    # by any of this session's embark-screen-focused verification.
    "vanilla_environment",
]

# data/art files present on the Premium/Steam install but not free Classic's
# copy, found 2026-09-10 comparing directory listings directly (VM 103 had
# 15 of 27 files) while investigating a user-reported missing UI panel on the
# embark screen. These are splash/logo/title-art assets (Bay12, Kitfox, FMOD
# branding, title-screen backgrounds) -- distinct from GRAPHICS_MODULES, which
# are empty *stubs* free Classic ships intentionally; these are simply absent,
# consistent with Premium bundling extra Steam-release branding free Classic
# never needed. `border.png` (the one file this project suspected might be the
# missing panel) was checked first and is NOT missing -- present on both,
# byte-identical size -- so whatever panel is or isn't missing, it is not this
# list's doing. Included anyway for completeness now that the transplant is
# already being done; not confirmed to fix any visual gap.
ART_FILES = [
    "bay12.png",
    "bay12_small.png",
    "bay12_tiny.png",
    "df_logo.png",
    "fmod.png",
    "pixel_kf.png",
    "pixel_kf_small.png",
    "pixel_kf_tiny.png",
    "title_adv.png",
    "title_background.png",
    "title_siege.png",
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
    # payload goes over stdin, not embedded in the command string: found
    # 2026-09-10 that this ssh.exe truncates a long command line to ~8182
    # chars when spawned by a native Win32 parent (Python) instead of a
    # POSIX one (bash) -- see ssh_guest's input_data docstring.
    proc = ssh_guest(env, ip, "base64 -d | %s" % shell,
                     timeout=timeout, check=False, input_data=payload)
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


def scp_to(env, ip, local_path, remote_path):
    """Push one local file into the guest -- the mirror of scp_from.

    Used only for the graphics transplant (cmd_graphics): the source asset
    tarball is binary and built from the caller's own local Steam/Premium
    install, so it must go straight over scp, never through remote()'s
    base64-a-bash-script path (that path is for *scripts*, not payloads) and
    never through this repo's git tree.
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
        local_path,
        "%s@%s:%s" % (env.get("DF_CIUSER", "df"), ip, remote_path),
    ]
    proc = subprocess.run(argv, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=600)
    if proc.returncode != 0:
        raise PVEError("scp failed (%s): %s"
                       % (proc.returncode, (proc.stderr or proc.stdout).strip()))


def guest_ip(pve, vmid):
    """Where to SSH. DF_VM_IP wins; otherwise ask the guest agent.

    DF_VM_IP is the address the VM was assigned at clone time (see
    provision_vm.guest_address()), so this is the normal path now, not an
    override of one. The guest-agent lookup below is kept as a fallback for
    when DF_VM_IP is not set, and as a cross-check against it, not as the
    primary way of finding the VM.

    A tailnet address is ranked last: this host reaches the VM over a subnet
    route to its LAN address, so the 100.64/10 address the VM reports is not
    necessarily one we can open a connection to.
    """
    override = pve.env.get("DF_VM_IP")
    if override:
        # DF_VM_IP is CIDR, because provision_vm.guest_address() feeds the same
        # value straight into cloud-init's ipconfig0, which requires a prefix.
        # ssh does not want one. One variable, one meaning, each consumer takes
        # the part it needs; splitting this into two settings would put the
        # same address in .env twice and let them drift.
        ip = override.split("/")[0]
        log("guest ip %s (DF_VM_IP)" % ip)
        return ip
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


def _append_env_var(key, value):
    """Append KEY='value' to the repo-root .env, guaranteeing a fresh line.

    2026-09-09 incident: a bare open(path, 'a').write(...) landed directly on
    the end of the previous line when the file had no trailing newline,
    silently merging two values (DF_VNC_PASSWORD onto ANTHROPIC_API_KEY) into
    one unparseable line. Checking for and inserting a leading '\\n' when
    needed is the actual fix, not a defensive nicety.
    """
    env_path = os.path.join(REPO_ROOT, ".env")
    with open(env_path, "rb") as fh:
        data = fh.read()
    prefix = "" if (not data or data.endswith(b"\n")) else "\n"
    with open(env_path, "a", encoding="utf-8") as fh:
        fh.write("%s%s='%s'\n" % (prefix, key, value))


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
# Xvfb refuses to start if /tmp/.X%(displaynum)s-lock (or the matching
# .X11-unix socket) already exists, and does not distinguish "a live server
# is using this" from "the last one died without cleaning up" -- it just
# checks for the file. Restart=on-failure below turns any unclean death
# (OOM kill, host crash, `kill -9`) into an infinite crash loop against its
# own stale lock, found 2026-09-08 after 47 restarts: 38s apart, "Server is
# already active for display %(displaynum)s" every time, and it cascades --
# df-fortress.service requires this unit so it cycled too, even though
# nothing about the fortress side was at fault. The leading '-' tells
# systemd not to fail the start if the files are already gone.
ExecStartPre=-/bin/rm -f /tmp/.X%(displaynum)s-lock /tmp/.X11-unix/X%(displaynum)s
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
#
# Found 2026-09-11 (decisions/DECISIONS.md same date, the quicksave no-op
# root-cause): quicksave is not synchronous -- it queues on a later,
# unpredictable game render pass, 45-80s+ observed, no fixed delay. This
# script's own flat 'sleep 5' predates that finding and could SIGTERM
# dwarfort mid-write on a live fort. Fixed to poll the active save slot's
# world.sav mtime (re-reading cur_savegame.save_dir fresh each time, since
# quicksave rotates slots forward) for up to 90s instead of trusting a fixed
# delay or stderr.log's "should autosave" line, neither reliable evidence.
STOP_SH = '''#!/bin/bash
''' + SAVE_PATH_SH + DFHACK_LUA_SH + '''
cd %(game)s
if ! pgrep -x dwarfort >/dev/null 2>&1; then
  exit 0
fi
./dfhack-run quicksave > %(logdir)s/systemd-stop.out 2>&1 || true
slot_before="$(dfhack_lua "print(df.global.world.cur_savegame.save_dir)")"
mtime_before=0
if [ -n "$slot_before" ] && [ -f "$SAVE_DIR/$slot_before/world.sav" ]; then
  mtime_before=$(stat -c %%Y "$SAVE_DIR/$slot_before/world.sav" 2>/dev/null || echo 0)
fi
landed=0
deadline=$(( $(date +%%s) + 90 ))
while [ "$(date +%%s)" -lt "$deadline" ]; do
  sleep 3
  slot_now="$(dfhack_lua "print(df.global.world.cur_savegame.save_dir)")"
  if [ -n "$slot_now" ] && [ -f "$SAVE_DIR/$slot_now/world.sav" ]; then
    mtime_now=$(stat -c %%Y "$SAVE_DIR/$slot_now/world.sav" 2>/dev/null || echo 0)
    if [ "$slot_now" != "$slot_before" ] || [ "$mtime_now" -gt "$mtime_before" ]; then
      landed=1
      break
    fi
  fi
done
if [ "$landed" = "1" ]; then
  echo "quicksave confirmed on disk (slot: ${slot_now:-$slot_before})"
else
  echo "quicksave NOT confirmed within 90s -- stopping anyway, ExecStop must not hang forever"
fi
pkill -TERM -x dwarfort || true
for _ in $(seq 1 30); do
  pgrep -x dwarfort >/dev/null 2>&1 || exit 0
  sleep 1
done
pkill -KILL -x dwarfort || true
sleep 2
exit 0
'''

# TimeoutStopSec covers ExecStop's own worst case (up to 90s quicksave poll,
# the 30s TERM wait, and the 2s KILL settle -- comfortable margin under 180s)
# now that a real fort's quicksave timing is known (45-80s+ observed,
# decisions/DECISIONS.md 2026-09-11).
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
        "stop_sh": STOP_SH % {"game": GAME_DIR, "logdir": LOG_DIR, "user": user},
        "xvfb_unit": XVFB_UNIT % {"user": user, "display": DISPLAY_NUM,
                                  "displaynum": DISPLAY_NUM.lstrip(":"),
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

def step_hostname(env, ip, name, args):
    """Set the guest's OS hostname to <Proxmox VM name>.internal.

    The two fields deliberately differ: Proxmox's own name field stays bare
    (matches subnet-router-01, and cloud-init already sets it that way at
    first boot from the VM's name), while '.internal' is home-lab's DNS
    convention for the FQDN, applied here explicitly since it's the guest's
    own hostname/etc/hosts, not something DNS can supply on its own. See
    decisions/DECISIONS.md 2026-09-08, the row correcting the earlier
    misread that put '.internal' in the Proxmox name field instead.
    """
    log("[1/6] hostname")
    fqdn = "%s.internal" % name
    script = '''
if [ "$(hostname)" = "%(fqdn)s" ]; then
  echo "hostname already %(fqdn)s"
else
  hostnamectl set-hostname %(fqdn)s
  sed -i "s/^127\\.0\\.1\\.1.*/127.0.1.1\\t%(fqdn)s\\t%(short)s/" /etc/hosts
  echo "hostname set to %(fqdn)s"
fi
hostname
''' % {"fqdn": fqdn, "short": name}
    proc = remote(env, ip, script, "hostname", timeout=60, sudo=True,
                  dry_run=args.dry_run)
    if proc:
        for line in proc.stdout.strip().splitlines():
            log("  " + line)


def step_packages(env, ip, args):
    log("[2/6] packages")
    # Automatic upgrades are turned off before anything is installed, and this
    # is the same call the register already made once: DF Classic replaced the
    # Steam build because an auto-update mid-fort shifts memory offsets and
    # silently breaks DFHack. An unattended glibc or SDL2 upgrade under a
    # running fort is that hazard one layer down, and a fort is meant to run
    # unattended for a month.
    #
    # The containment is that this VM is LAN-only and cheap to rebuild, which
    # is the whole point of the project. The intended pattern is to pin the
    # box for the duration of a fort and rebuild between forts, rather than to
    # let libraries move under a live one. Written as apt config rather than
    # by masking the unit, because config survives the package being updated.
    script = '''
export DEBIAN_FRONTEND=noninteractive
cat > /etc/apt/apt.conf.d/99-df-overseer-no-auto-upgrade <<'CONF'
// Set by scripts/install_df.py. See decisions/DECISIONS.md 2026-09-08.
// A fort runs unattended for a month; libraries must not move underneath it.
APT::Periodic::Update-Package-Lists "0";
APT::Periodic::Unattended-Upgrade "0";
CONF
echo "automatic upgrades disabled"
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
    log("[3/6] swapfile (%s, swappiness %d)" % (SWAP_SIZE, SWAPPINESS))
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
    log("[4/6] fetching tarballs into %s" % DIST_DIR)
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
    log("[5/6] extracting into %s%s"
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
    log("[6/6] prefs/init.txt")
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
    # Same "no API call under dry-run" contract as target() above.
    name = ("<dry-run>" if args.dry_run
            else pve.get(pve.vm_path(vmid, "/config")).get("name", "df-overseer"))
    step_hostname(pve.env, ip, name, args)
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
    # Same fix as systemd-stop.sh (decisions/DECISIONS.md 2026-09-11): quicksave
    # is async, 45-80s+ observed, so a flat sleep before SIGTERM could kill
    # dwarfort mid-write. Poll the active slot's world.sav mtime instead.
    tail_script = '''
cd %(game)s
if ! pgrep -x dwarfort >/dev/null 2>&1; then
  echo "dwarfort is not running"
  exit 0
fi
if [ "%(save)s" = "1" ]; then
  echo "quicksave: $(./dfhack-run quicksave 2>&1 | tail -n1)"
  slot_before="$(dfhack_lua "print(df.global.world.cur_savegame.save_dir)")"
  mtime_before=0
  if [ -n "$slot_before" ] && [ -f "$SAVE_DIR/$slot_before/world.sav" ]; then
    mtime_before=$(stat -c %%Y "$SAVE_DIR/$slot_before/world.sav" 2>/dev/null || echo 0)
  fi
  landed=0
  deadline=$(( $(date +%%s) + 90 ))
  while [ "$(date +%%s)" -lt "$deadline" ]; do
    sleep 3
    slot_now="$(dfhack_lua "print(df.global.world.cur_savegame.save_dir)")"
    if [ -n "$slot_now" ] && [ -f "$SAVE_DIR/$slot_now/world.sav" ]; then
      mtime_now=$(stat -c %%Y "$SAVE_DIR/$slot_now/world.sav" 2>/dev/null || echo 0)
      if [ "$slot_now" != "$slot_before" ] || [ "$mtime_now" -gt "$mtime_before" ]; then
        landed=1
        break
      fi
    fi
  done
  if [ "$landed" = "1" ]; then
    echo "quicksave confirmed on disk (slot: ${slot_now:-$slot_before})"
  else
    echo "quicksave NOT confirmed within 90s -- stopping anyway"
  fi
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
    script = save_path_sh(pve.env) + dfhack_lua_sh() + tail_script
    proc = remote(pve.env, ip, script, "stop", timeout=240,
                  dry_run=args.dry_run)
    if proc:
        for line in proc.stdout.strip().splitlines():
            log("  " + line)


# --- graphics --------------------------------------------------------------

def cmd_graphics(pve, args):
    """Transplant official Steam/Premium tile graphics onto this Classic install.

    Source is a LOCAL directory (the caller's own legitimately-purchased
    Steam/Premium DF install root, e.g. the default Steam library path), never
    a URL: this is personal-use asset data with no redistribution license,
    not something to fetch or pin like DF_URL/DFHACK_URL above. It never
    enters this repo's working tree or git history -- the eight module
    folders in GRAPHICS_MODULES, plus the ART_FILES splash/title assets, are
    tarred up in a temp file, scp'd straight to the guest, extracted into a
    /tmp staging dir, and copied into GAME_DIR/data/vanilla/<module>/ (over
    the existing info.txt-only stubs) and GAME_DIR/data/art/ respectively.
    See scripts/install_df.py's INIT_SETTINGS comment, ART_FILES's own
    comment, and decisions/DECISIONS.md 2026-09-09 for the full reasoning.

    Deliberately does NOT touch prefs/init.txt or trigger worldgen -- run
    'install' (to apply the now-updated INIT_SETTINGS incl. USE_CLASSIC_ASCII)
    and 'gen' separately. Keeping this to one job (get the bytes onto the VM,
    correctly) matches every other step_* function above.
    """
    vmid, ip = target(pve, args)
    source = args.source or pve.env.get("DF_GRAPHICS_SOURCE")
    if not source:
        raise PVEError(
            "no --source given and DF_GRAPHICS_SOURCE not set in .env -- point"
            " it at the root of a local Steam/Premium Dwarf Fortress install"
            " (the directory containing 'data/vanilla'), e.g. .env:\n"
            "  DF_GRAPHICS_SOURCE=C:/Program Files (x86)/Steam/steamapps/"
            "common/Dwarf Fortress")
    vanilla_src = os.path.join(source, "data", "vanilla")
    if not os.path.isdir(vanilla_src):
        raise PVEError("%s has no data/vanilla -- is --source the DF install"
                       " root (the folder with 'dwarfort'/'Dwarf Fortress.exe'"
                       " in it), not a subfolder of it?" % source)

    missing = [m for m in GRAPHICS_MODULES
              if not os.path.isdir(os.path.join(vanilla_src, m))]
    if missing:
        raise PVEError("source install is missing graphics module(s): %s\n"
                       "  This does not look like a Premium/Steam install --"
                       " free Classic ships these as empty stubs, and this"
                       " command is meant to copy FROM the paid one."
                       % ", ".join(missing))

    art_src = os.path.join(source, "data", "art")
    missing_art = [f for f in ART_FILES
                  if not os.path.isfile(os.path.join(art_src, f))]
    if missing_art:
        raise PVEError("source install is missing data/art file(s): %s"
                       % ", ".join(missing_art))

    manifest = []
    total_bytes = 0
    for module in GRAPHICS_MODULES:
        mdir = os.path.join(vanilla_src, module)
        n_files = 0
        n_png = 0
        size = 0
        for root, _dirs, files in os.walk(mdir):
            for fn in files:
                n_files += 1
                if fn.lower().endswith(".png"):
                    n_png += 1
                size += os.path.getsize(os.path.join(root, fn))
        manifest.append((module, n_files, n_png, size))
        total_bytes += size
    log("source: %s" % source)
    for module, n_files, n_png, size in manifest:
        log("  %-32s %4d files (%3d png), %.1f KB"
            % (module, n_files, n_png, size / 1024.0))
    art_size = sum(os.path.getsize(os.path.join(art_src, f)) for f in ART_FILES)
    log("  %-32s %4d files, %.1f KB" % ("data/art (splash/title assets)",
                                        len(ART_FILES), art_size / 1024.0))
    log("total: %.1f MB across %d modules + data/art"
        % ((total_bytes + art_size) / 1024.0 / 1024.0, len(GRAPHICS_MODULES)))

    if args.dry_run:
        log("--- graphics (dry run, not sent) ---")
        log("would tar the %d module dirs above plus %d data/art file(s), scp"
            " to VM %s, and copy each module into %s/data/vanilla/<module>/"
            " (overwriting the existing info.txt-only stub) and the art files"
            " into %s/data/art/, leaving everything else untouched"
            % (len(GRAPHICS_MODULES), len(ART_FILES), vmid, GAME_DIR, GAME_DIR))
        log("--- end graphics ---")
        return

    fd, tmp_path = tempfile.mkstemp(prefix="df-graphics-", suffix=".tar.gz")
    os.close(fd)
    try:
        log("building local tarball (never written into this repo)")
        with tarfile.open(tmp_path, "w:gz") as tf:
            for module in GRAPHICS_MODULES:
                tf.add(os.path.join(vanilla_src, module), arcname=module)
            for fn in ART_FILES:
                tf.add(os.path.join(art_src, fn), arcname="_art/" + fn)
        tar_size = os.path.getsize(tmp_path)
        log("tarball: %.1f MB, pushing to VM %s" % (tar_size / 1024.0 / 1024.0, vmid))

        remote_tmp = "/tmp/df-graphics-transfer.tar.gz"
        scp_to(pve.env, ip, tmp_path, remote_tmp)
        log("  scp complete")
    finally:
        os.remove(tmp_path)

    script = '''
GAME=%(game)s
STAGE=/tmp/df-graphics-stage
rm -rf "$STAGE"
mkdir -p "$STAGE"
tar -xzf %(remote_tmp)s -C "$STAGE"
for m in %(modules)s; do
  if [ ! -d "$STAGE/$m" ]; then
    echo "MISSING in transfer: $m"
    exit 1
  fi
  dest="$GAME/data/vanilla/$m"
  if [ ! -d "$dest" ]; then
    echo "MISSING on guest (not a known vanilla module?): $dest"
    exit 1
  fi
  cp -a "$STAGE/$m/." "$dest/"
  n_files=$(find "$dest" -type f | wc -l)
  n_png=$(find "$dest" -iname '*.png' | wc -l)
  echo "  $m: now $n_files files ($n_png png) in $dest"
done
if [ -d "$STAGE/_art" ]; then
  cp -a "$STAGE/_art/." "$GAME/data/art/"
  echo "  data/art: copied $(find "$STAGE/_art" -type f | wc -l) file(s) into $GAME/data/art"
fi
rm -rf "$STAGE" %(remote_tmp)s
echo "graphics install complete"
''' % {"game": GAME_DIR, "remote_tmp": remote_tmp,
       "modules": " ".join(GRAPHICS_MODULES)}
    proc = remote(pve.env, ip, script, "graphics install", timeout=180,
                  dry_run=False)
    for line in proc.stdout.strip().splitlines():
        log(line if line.startswith("  ") else "  " + line)
    log("graphics data landed on VM %s. Next: 'install_df.py install' to"
        " apply USE_CLASSIC_ASCII:NO, then 'gen' a fresh world, then 'verify'"
        " with a screenshot." % vmid)


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


def cmd_lua(pve, args):
    """Run one dfhack-run lua expression against the live DF process.

    dfhack_lua_sh()'s helper is for single-value verify checks (tail -n1);
    live embark-testing needs full multi-line output -- a pairs() field dump
    or a viewscreen type name -- so this prints everything, ANSI-stripped.
    The code is heredoc'd with a quoted delimiter so it reaches dfhack-run
    byte-for-byte: no shell expansion of '$', quotes or '%' in the Lua itself.
    """
    vmid, ip = target(pve, args)
    script = (
        "cd %s\n" % GAME_DIR +
        "./dfhack-run lua \"$(cat <<'DF_LUA_EOF'\n"
        + args.code + "\n"
        "DF_LUA_EOF\n"
        ")\" 2>&1 | sed -e 's/\\x1b\\[[0-9;]*m//g' -e 's/\\r$//'\n"
    )
    proc = remote(pve.env, ip, script, "lua", timeout=args.timeout,
                 check=False, dry_run=args.dry_run)
    if args.dry_run:
        return
    out = (proc.stdout or "").strip()
    for line in out.splitlines():
        log("  " + line)
    if proc.returncode != 0:
        raise PVEError("lua command exited %s" % proc.returncode)


def cmd_run(pve, args):
    """Call one already-deployed named dfhack script directly, e.g.
    'df-overseer-openarea find 5 5 169 "Embark Site"', without hand-rolling
    an ssh command or going through cmd_lua's raw-Lua path.

    This is the gap between cmd_lua (arbitrary Lua, full raw access) and
    the single-purpose subcommands like ui-install/script-install: a way to
    invoke a named tool's own CLI exactly as documented in its file header
    or docs/DF-UI-AUTOMATION.md, with each argument passed through shell-safe
    (a landmark name like "Embark Site" needs its own quoting preserved, not
    word-split by the remote shell). Read-only or mutating is up to the
    script being called; this wrapper does not know or care which.
    """
    vmid, ip = target(pve, args)
    quoted = " ".join(shlex.quote(a) for a in [args.script_name] + args.script_args)
    script = (
        "cd %s\n" % GAME_DIR +
        "./dfhack-run %s 2>&1 | sed -e 's/\\x1b\\[[0-9;]*m//g' -e 's/\\r$//'\n"
        % quoted
    )
    proc = remote(pve.env, ip, script, "run", timeout=args.timeout,
                 check=False, dry_run=args.dry_run)
    if args.dry_run:
        return
    out = (proc.stdout or "").strip()
    for line in out.splitlines():
        log("  " + line)
    if proc.returncode != 0:
        raise PVEError("run command exited %s" % proc.returncode)


DFHACK_SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "dfhack")


def cmd_script_install(pve, args):
    """Deploy any scripts/dfhack/<name>.lua onto the guest's own
    hack/scripts/ directory, so './dfhack-run <name> ...' is callable
    directly instead of hand-writing a fresh Lua script over SSH, or
    scp'ing one ad hoc, for every new piece of automation.

    Generalizes what was cmd_ui_install (one hardcoded file) now that a
    second script, df-overseer-labor.lua, exists and had only ever been
    deployed by hand via plain scp -- see Working.md 2026-09-11. Same
    tested remote()-over-stdin mechanism, just parameterized by name.
    """
    vmid, ip = target(pve, args)
    local_path = os.path.join(DFHACK_SCRIPTS_DIR, args.name + ".lua")
    if not os.path.isfile(local_path):
        raise PVEError("no such script: %s" % local_path)
    with open(local_path, "r", encoding="utf-8") as f:
        lua_source = f.read()
    remote_name = args.name + ".lua"
    # Built by concatenation, not %-formatting, because the Lua source itself
    # is full of %d/%s directives (string.format calls) that a % on the
    # combined string would try to consume as Python format args.
    script = (
        "mkdir -p " + GAME_DIR + "/hack/scripts\n"
        "cat > " + GAME_DIR + "/hack/scripts/" + remote_name
        + " <<'DF_SCRIPT_INSTALL_EOF'\n"
        + lua_source +
        "\nDF_SCRIPT_INSTALL_EOF\n"
        "echo installed\n"
    )
    proc = remote(pve.env, ip, script, "script-install", timeout=30,
                  dry_run=args.dry_run)
    if args.dry_run:
        return
    log("  " + proc.stdout.strip())
    log("%s deployed on VM %s -- try: ./dfhack-run %s ..."
        % (remote_name, vmid, args.name))


def cmd_ui_install(pve, args):
    """Deploy every scripts/dfhack/df-overseer-*.lua file onto the guest's
    own hack/scripts/ directory, so their subcommands are callable directly
    (e.g. './dfhack-run df-overseer-ui click "Fortress"') instead of
    hand-writing a fresh Lua script over SSH for every single action.

    Found 2026-09-10: that one-off-script-per-action pattern is what made
    the whole embark-flow session slow, and re-derived the same
    buffer-scan-and-click/retry technique from scratch each time instead of
    reusing tested code. Plain automation logic, not game data or a secret
    -- checked into this repo like any other script, unlike GRAPHICS_MODULES
    or ART_FILES. Generalized from a single hardcoded file (df-overseer-ui.lua
    only) to every df-overseer-*.lua file in the directory once a second one
    (df-overseer-connectivity.lua) was added, rather than adding a new
    one-off CLI verb per script going forward.

    Reconciled 2026-09-12 merging perception-layer-experiments into main:
    this branch's bulk-deploy-everything implementation is kept as the real
    'ui-install' (its name predates script-install and is already referenced
    throughout docs/ and decisions/, so the name stays even though it now
    deploys every script, not just the UI one) -- main's own independently-
    built version of this function had instead become a thin two-line alias
    for cmd_script_install once that single-file-targeted command existed.
    Both capabilities are real and worth keeping: this one for "redeploy
    everything after touching several files," script-install below for
    "deploy just this one file."
    """
    vmid, ip = target(pve, args)
    names = sorted(
        f for f in os.listdir(DFHACK_SCRIPTS_DIR)
        if f.startswith("df-overseer-") and f.endswith(".lua"))
    if not names:
        raise PVEError("no df-overseer-*.lua files found in %s" % DFHACK_SCRIPTS_DIR)
    parts = ["mkdir -p " + GAME_DIR + "/hack/scripts\n"]
    for name in names:
        with open(os.path.join(DFHACK_SCRIPTS_DIR, name), "r", encoding="utf-8") as f:
            lua_source = f.read()
        # Built by concatenation, not %-formatting, because the Lua source
        # itself is full of %d/%s directives (string.format calls) that a %
        # on the combined string would try to consume as Python format args.
        # Delimiter is per-file (not a fixed 'DF_OVERSEER_UI_EOF') so two
        # scripts in one deploy can't collide if either ever contained the
        # other's delimiter text.
        delim = "DF_OVERSEER_EOF_%s" % name.replace("-", "_").replace(".", "_").upper()
        parts.append(
            "cat > " + GAME_DIR + "/hack/scripts/" + name + " <<'" + delim + "'\n"
            + lua_source +
            "\n" + delim + "\n"
            "echo installed: " + name + "\n"
        )
    proc = remote(pve.env, ip, "".join(parts), "ui-install", timeout=30,
                  dry_run=args.dry_run)
    if args.dry_run:
        return
    for line in proc.stdout.strip().splitlines():
        log("  " + line)
    log("%d df-overseer-*.lua script(s) deployed on VM %s -- try:"
        " ./dfhack-run df-overseer-ui type" % (len(names), vmid))


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


# --- live view -------------------------------------------------------------

# One-shot capture-and-push, run on a timer rather than as a long-lived
# process -- matches research/2026-09-08-live-viewing.md's recommendation:
# outbound push only (no inbound port, ever), periodic rather than a held
# connection. `enable spectate` first so the in-game camera is pointed at
# something happening before each capture, per the same report -- the
# cheapest lever for making a still frame worth looking at.
STREAM_CAPTURE_SH = '''
mkdir -p %(streamdir)s
chown %(user)s:%(user)s %(streamdir)s
cat > %(streamdir)s/capture-push.sh <<'CAPEOF'
#!/bin/bash
set -uo pipefail
DISPLAY=%(display)s import -display %(display)s -window root png:%(streamdir)s/latest.png.tmp \\
  && mv %(streamdir)s/latest.png.tmp %(streamdir)s/latest.png
if [ -n "%(ingest_url)s" ]; then
  curl -fsS --max-time 10 -F "file=@%(streamdir)s/latest.png" "%(ingest_url)s" \\
    >> %(logdir)s/stream-push.log 2>&1 || \\
    echo "$(date -Is) push failed, will retry next tick" >> %(logdir)s/stream-push.log
fi
CAPEOF
chmod +x %(streamdir)s/capture-push.sh
chown %(user)s:%(user)s %(streamdir)s/capture-push.sh

cat > /etc/systemd/system/df-stream.service <<'EOF'
[Unit]
Description=Capture and push a Dwarf Fortress screenshot (one-shot)
After=df-xvfb.service
Requires=df-xvfb.service

[Service]
Type=oneshot
User=%(user)s
ExecStart=%(streamdir)s/capture-push.sh
EOF

cat > /etc/systemd/system/df-stream.timer <<'EOF'
[Unit]
Description=Run df-stream.service on a timer

[Timer]
OnBootSec=30s
OnUnitActiveSec=%(interval)ss

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now df-stream.timer
systemctl is-enabled df-stream.timer
'''


def cmd_stream(pve, args):
    """Set up periodic screenshot capture (and optional push) on the VM.

    Ingest side is deliberately out of scope here -- willsmith.nz is a static
    GitHub Pages site with no backend (research/2026-09-08-live-viewing.md),
    so DF_STREAM_INGEST_URL must point somewhere that can actually receive an
    upload. Left unset, this still sets up local capture to
    %(streamdir)s/latest.png on the VM, useful on its own for a LAN-side
    viewer (docs/PURPOSE.md's 'VNC -> Pi -> monitor' leg) or to confirm
    capture itself works before wiring up a receiving end.
    """
    vmid, ip = target(pve, args)
    ingest_url = args.ingest_url or pve.env.get("DF_STREAM_INGEST_URL", "")
    log("setting up screenshot capture on VM %s, every %ss%s"
        % (vmid, args.interval,
           (" -> %s" % ingest_url) if ingest_url else " (local only, no ingest URL set)"))

    pkg_script = '''
if ! command -v import >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq imagemagick
fi
'''
    remote(pve.env, ip, pkg_script, "install imagemagick", timeout=180,
          sudo=True, dry_run=args.dry_run)

    remote(pve.env, ip, dfhack_lua_sh() + '''
cd %(game)s
dfhack_lua "if not dfhack.isEnabled('spectate') then dfhack.run_command('enable spectate') end"
''' % {"game": GAME_DIR}, "enable spectate", timeout=60, dry_run=args.dry_run)

    script = STREAM_CAPTURE_SH % {
        "streamdir": STREAM_DIR,
        "display": DISPLAY_NUM,
        "ingest_url": ingest_url,
        "logdir": LOG_DIR,
        "user": pve.env.get("DF_CIUSER", "df"),
        "interval": args.interval,
    }
    proc = remote(pve.env, ip, script, "stream setup", timeout=120,
                  sudo=True, dry_run=args.dry_run)
    if args.dry_run:
        return
    for line in proc.stdout.strip().splitlines():
        log("  " + line)
    log("capturing to %s/latest.png on the VM every %ss"
        % (STREAM_DIR, args.interval))
    if not ingest_url:
        log("no DF_STREAM_INGEST_URL set -- capture only, nothing is pushed anywhere yet")


# x11vnc rather than the screenshot pipeline above, for the human-follow-along
# use case: research/2026-09-08-live-viewing.md 3b already recommended it for
# exactly this leg ("the Pi/wall-display x11vnc leg... a separate, LAN-only
# build with none of the relay complexity"). Genuinely live, incremental-update
# RFB, no relay/ingest side to build. View-only on purpose: this build does not
# forward keyboard/mouse input back into the guest. Adding that later is a
# small change (drop -viewonly) once the view-only version is confirmed
# working, not a redesign -- deliberately deferred, not an oversight.
X11VNC_UNIT = '''[Unit]
Description=x11vnc (%(desc)s) for the Dwarf Fortress Xvfb display
After=df-xvfb.service
Requires=df-xvfb.service

[Service]
Type=simple
User=%(user)s
Environment=DISPLAY=%(display)s
ExecStart=/usr/bin/x11vnc -display %(display)s %(authflag)s \\
  -rfbport %(port)s %(viewonlyflag)s -forever -shared -noxdamage \\
  -o %(logdir)s/%(logfile)s
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
'''


def cmd_vnc(pve, args):
    """Install x11vnc on the Xvfb display: LAN-reachable, view-only, password-gated by default.

    Password-protected by default even though VM 103 has no public IP: the VM
    currently has no network-isolation boundary (Working.md's durable-traps
    section -- no tag:ai-sandbox ACL yet), so a new inbound LAN port gets a
    password as cheap defense-in-depth rather than riding on "LAN-only" alone.
    The password is never logged or printed -- it comes from --password, from
    DF_VNC_PASSWORD in .env, or is freshly generated and appended to .env for
    the caller to read from there.

    --no-password drops that gate entirely (x11vnc's own -nopw flag, not just
    an empty password), decided 2026-09-09 once this feed started being
    deliberately exposed at dwarf-fortress.willsmith.nz: the feed is -viewonly
    (no keyboard/mouse ever reaches the guest, see X11VNC_UNIT's own comment),
    so an unauthenticated connection can only watch, not act -- removing the
    password trades away a defense-in-depth layer against LAN-side snooping,
    not any control-surface risk, and this is the same x11vnc instance the LAN
    path also uses, so this applies there too, not just the public leg.

    --control installs a SEPARATE, second instance (df-vnc-control.service,
    default port VNC_CONTROL_PORT) rather than changing the one above: drops
    -viewonly (real mouse/keyboard reach the game) and forces -nopw
    unconditionally, ignoring --password/--no-password -- this instance's
    auth is Cloudflare Access at the edge (provision_relay.py's cmd_webvnc
    --control), not an x11vnc password, decided 2026-09-11 specifically to
    avoid a redundant second sign-in once Access already gates the only path
    in. The existing view-only df-vnc.service is completely untouched by
    this flag; both can run at once, on different ports.
    """
    vmid, ip = target(pve, args)
    user = pve.env.get("DF_CIUSER", "df")
    control = args.control
    port = args.port if args.port is not None else (
        VNC_CONTROL_PORT if control else VNC_PORT)
    service = "df-vnc-control" if control else "df-vnc"

    if control:
        # Forced, not merely defaulted -- an explicit --password here would
        # silently do nothing, which is worse than refusing it outright.
        if args.password or args.no_password:
            raise PVEError("--control always runs -nopw (auth is Cloudflare"
                            " Access, not an x11vnc password) -- drop"
                            " --password/--no-password")
        no_password = True
        password = None
        generated = False
    elif args.no_password:
        no_password = True
        password = None
        generated = False
    else:
        no_password = False
        password = args.password or pve.env.get("DF_VNC_PASSWORD")
        generated = False
        if not password:
            password = secrets.token_urlsafe(15)
            generated = True

    log("installing x11vnc on VM %s (%s, port %s%s)"
        % (vmid, "CONTROL -- real mouse/keyboard reach the game" if control
                  else "view-only", port,
           ", no password" if no_password else ""))
    if control:
        log("  -- this instance is meant to sit behind Cloudflare Access"
            " only; do not expose port %s directly" % port)

    pkg_script = '''
if ! command -v x11vnc >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq x11vnc
fi
'''
    remote(pve.env, ip, pkg_script, "install x11vnc", timeout=180,
          sudo=True, dry_run=args.dry_run)

    # A placeholder stands in for the password under --dry-run so a printed
    # script (remote()'s dry-run path logs the whole body) never puts the real
    # value on screen or in a saved log.
    script_password = "<DF_VNC_PASSWORD>" if args.dry_run else password
    vncdir = VNC_DIR + ("-control" if control else "")
    authflag = "-nopw" if no_password else "-rfbauth %s/passwd" % vncdir
    unit = X11VNC_UNIT % {
        "user": user, "display": DISPLAY_NUM, "vncdir": vncdir,
        "port": port, "logdir": LOG_DIR, "authflag": authflag,
        "desc": "CONTROL, real input" if control else "view-only",
        "viewonlyflag": "" if control else "-viewonly",
        # Separate log files -- found live 2026-09-11 that both instances
        # pointed at the same x11vnc.log (this key didn't exist before),
        # which made the shared file an unreliable signal for either
        # instance's actual connection activity once both were running.
        "logfile": "x11vnc-control.log" if control else "x11vnc.log",
    }
    passwd_step = "" if no_password else (
        "x11vnc -storepasswd %(password)s %(vncdir)s/passwd\n"
        "chown -R %(user)s:%(user)s %(vncdir)s\n"
        "chmod 600 %(vncdir)s/passwd\n"
    ) % {"vncdir": vncdir, "password": script_password, "user": user}
    setup_script = '''
mkdir -p %(vncdir)s
%(passwd_step)s
cat > /etc/systemd/system/%(service)s.service <<'EOF'
%(unit)s
EOF

systemctl daemon-reload
systemctl enable --now %(service)s.service
systemctl restart %(service)s.service
systemctl is-active %(service)s.service
''' % {"vncdir": vncdir, "passwd_step": passwd_step, "unit": unit,
       "service": service}

    proc = remote(pve.env, ip, setup_script, "vnc setup", timeout=120,
                  sudo=True, dry_run=args.dry_run)
    if args.dry_run:
        return
    for line in proc.stdout.strip().splitlines():
        log("  " + line)

    if generated:
        _append_env_var("DF_VNC_PASSWORD", password)
        log("generated a VNC password, wrote DF_VNC_PASSWORD to .env"
            " (gitignored) -- read it from there, not printed here")
    if control:
        log("x11vnc listening on %s:%s -- CONTROL (real input), NO x11vnc"
            " password -- must stay behind Cloudflare Access" % (ip, port))
    elif no_password:
        log("x11vnc listening on %s:%s -- view-only, NO PASSWORD (public feed)"
            % (ip, port))
    else:
        log("x11vnc listening on %s:%s -- view-only, password required" % (ip, port))


# noVNC + websockify bridge the existing x11vnc server to a plain browser tab,
# for LAN viewing with zero client install. Deliberately NOT the mechanism for
# willsmith.nz: research/2026-09-08-live-viewing.md 4 already worked out that
# a persistent inbound-facing bridge like this is the wrong shape for the
# public internet (it would mean tunnelling/Funnel-ing this same port, making
# VM 103 a public-facing endpoint indefinitely -- a real, separate decision,
# not a small extension of this). The public leg stays the outbound
# screenshot-push design (cmd_stream above), blocked only on R2 credentials.
# %(depends)s is a full [Unit]-section dependency block (After=/Requires=
# lines, or empty), not baked in fixed: on VM 103 the x11vnc server is a
# local sibling unit (df-vnc.service) and this should wait on it, but on the
# relay (provision_relay.py's cmd_webvnc reuses this same template) the
# thing on the other end of localhost:<vncport> is a *tunneled* port from a
# different host entirely -- no local unit exists to depend on, and
# 'Requires=' naming a unit that does not exist on that host would fail this
# service to start, not just warn. websockify's own Restart=on-failure
# already covers "nothing is listening yet" on either host.
# %(bindhost)s is "" (all interfaces -- the existing public/LAN behavior,
# unchanged) or "127.0.0.1:" (loopback only). Every caller must supply it
# explicitly, even as "" -- there is no implicit default, so a new call site
# can't silently inherit the wrong exposure. provision_relay.py's cmd_webvnc
# --control uses "127.0.0.1:" so Cloudflare Access (reached only via
# cloudflared's own loopback-side connection) is the *only* way to this
# port, not merely the intended one -- confirmed 2026-09-11 that the
# no-bindhost form binds all interfaces, which is fine for the existing
# view-only public feed but would have left the control channel reachable
# directly on the relay's LAN, bypassing Access entirely.
NOVNC_UNIT = '''[Unit]
Description=noVNC websocket bridge to the Dwarf Fortress x11vnc server
%(depends)s

[Service]
Type=simple
User=%(user)s
ExecStart=/usr/bin/websockify --web=/usr/share/novnc %(bindhost)s%(port)s localhost:%(vncport)s
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
'''

# The stock novnc package ships no index.html, so the bare hostname/port
# serves an Apache-style directory listing (app/, core/, vendor/, ...)
# instead of the viewer -- confirmed live on the public dwarf-fortress.
# willsmith.nz URL 2026-09-09. Shared by both this file's cmd_webvnc (VM 103,
# LAN) and provision_relay.py's cmd_webvnc (the relay, public) since it's the
# same fix either way. autoconnect=true is only a good default once the
# password gate is actually off ('vnc --no-password') -- otherwise this
# would hide the prompt behind a connection that just sits there looking
# blank. Lives in /usr/share/novnc (an apt package path, not this repo), so a
# future `apt upgrade` of the novnc package could overwrite it; cheap to
# re-run this than to solve, same "disposable, rebuild it" posture the relay
# already has elsewhere.
NOVNC_INDEX_HTML = '''<!doctype html><meta charset="utf-8">
<title>Dwarf Fortress -- live</title>
<meta http-equiv="refresh" content="0; url=vnc.html?autoconnect=true&resize=scale">
<a href="vnc.html?autoconnect=true&resize=scale">Dwarf Fortress -- live</a>
'''


def install_novnc_index(env, ip, dry_run):
    script = "cat > /usr/share/novnc/index.html <<'EOF'\n%s\nEOF\n" % NOVNC_INDEX_HTML
    remote(env, ip, script, "install novnc index redirect", timeout=30,
           sudo=True, dry_run=dry_run)


def cmd_webvnc(pve, args):
    """Bridge the running x11vnc server to a plain browser tab, no VNC client needed.

    Requires 'vnc' to already be set up (df-vnc.service listening on
    --vnc-port, default VNC_PORT) -- this only adds the browser-facing hop.
    Still LAN-only, still password-gated: websockify just relays bytes to the
    existing x11vnc server, so the browser page prompts for the same
    DF_VNC_PASSWORD, not a second credential to manage.
    """
    vmid, ip = target(pve, args)
    user = pve.env.get("DF_CIUSER", "df")
    port = args.port
    vnc_port = args.vnc_port

    log("installing noVNC + websockify on VM %s (browser port %s -> vnc port %s)"
        % (vmid, port, vnc_port))

    pkg_script = '''
if ! command -v websockify >/dev/null 2>&1 || [ ! -d /usr/share/novnc ]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq novnc websockify
fi
'''
    remote(pve.env, ip, pkg_script, "install novnc/websockify", timeout=180,
          sudo=True, dry_run=args.dry_run)
    install_novnc_index(pve.env, ip, args.dry_run)

    unit = NOVNC_UNIT % {
        "user": user, "port": port, "vncport": vnc_port, "bindhost": "",
        "depends": "After=df-vnc.service\nRequires=df-vnc.service",
    }
    setup_script = '''
cat > /etc/systemd/system/df-webvnc.service <<'EOF'
%(unit)s
EOF

systemctl daemon-reload
systemctl enable --now df-webvnc.service
systemctl is-active df-webvnc.service
''' % {"unit": unit}

    proc = remote(pve.env, ip, setup_script, "webvnc setup", timeout=120,
                  sudo=True, dry_run=args.dry_run)
    if args.dry_run:
        return
    for line in proc.stdout.strip().splitlines():
        log("  " + line)
    log("open http://%s:%s/ in a browser -- auto-redirects to the live feed"
        " (password requirement depends on how 'vnc' was run)" % (ip, port))


# The public-relay leg: VM 103 dials OUT to the relay so it never accepts an
# inbound connection from anywhere, LAN or internet. Recommended over a
# VNC-repeater chain in research/2026-09-09-reverse-vnc-relay.md -- no new
# protocol, x11vnc's own config (X11VNC_UNIT above) is untouched, this is
# pure SSH remote port forwarding. The private key is generated ON VM 103
# and never leaves it; only the public half goes to the relay.
TUNNEL_DIR = "/opt/df/vnc-tunnel"

# 127.0.0.1 on both sides of -R, deliberately: the relay's sshd has
# 'GatewayPorts no' (confirmed live 2026-09-09), so the forwarded listener on
# the relay binds to loopback only -- reachable by the relay's own
# websockify process, not by anything else on the relay's network. The
# restricted authorized_keys entry below (permitopen=) is the second,
# independent layer: even if GatewayPorts were ever flipped, this specific
# key still could not open anything else.
VNC_TUNNEL_UNIT = '''[Unit]
Description=Reverse SSH tunnel: expose %(requires)s's x11vnc to the relay (LAN-internal only)
After=network.target %(requires)s
Requires=%(requires)s

[Service]
Type=simple
User=%(user)s
ExecStart=/usr/bin/ssh -N -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes \\
  -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=%(tunneldir)s/known_hosts \\
  -i %(tunneldir)s/id_ed25519 -R 127.0.0.1:%(vncport)s:127.0.0.1:%(vncport)s \\
  %(relayuser)s@%(relayip)s
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
'''


def cmd_vnc_tunnel(pve, args):
    """Reverse SSH tunnel from VM 103 to the public relay -- VM 103 dials out.

    Generates a dedicated ed25519 keypair on VM 103 (idempotent -- skips if
    one already exists) used for nothing but this tunnel, distinct from the
    admin key (DF_SSH_KEY) used to manage VM 103 itself. Installs only the
    public half on the relay's authorized_keys, restricted with
    'permitopen=\"127.0.0.1:<port>\",no-pty,no-agent-forwarding,no-X11-forwarding'
    -- per research/2026-09-09-reverse-vnc-relay.md 5, even a fully
    compromised copy of this key can only ever forward to that one loopback
    port on the relay, nothing else: no shell, no other host, no other port.

    --control tunnels the control x11vnc instance (df-vnc-control.service,
    default VNC_CONTROL_PORT) instead, via a completely separate keypair,
    authorized_keys line, and systemd service (df-vnc-control-tunnel) --
    deliberately not reusing the view-only tunnel's key, so nothing about
    this ever touches (or risks breaking) the existing public tunnel.
    """
    vmid, ip = target(pve, args)
    user = pve.env.get("DF_CIUSER", "df")
    control = args.control
    vnc_port = args.vnc_port if args.vnc_port is not None else (
        VNC_CONTROL_PORT if control else VNC_PORT)
    relay_ip = args.relay_ip
    relay_user = args.relay_user
    tunnel_dir = TUNNEL_DIR + ("-control" if control else "")
    service = "df-vnc-control-tunnel" if control else "df-vnc-tunnel"
    requires = "df-vnc-control.service" if control else "df-vnc.service"
    key_comment = service

    log("setting up reverse VNC tunnel%s: VM %s -> %s@%s (port %s)"
        % (" (CONTROL)" if control else "", vmid, relay_user, relay_ip,
           vnc_port))

    keygen_script = '''
mkdir -p %(tunneldir)s
if [ ! -f %(tunneldir)s/id_ed25519 ]; then
  ssh-keygen -t ed25519 -f %(tunneldir)s/id_ed25519 -N '' -C '%(comment)s' -q
fi
chown -R %(user)s:%(user)s %(tunneldir)s
chmod 700 %(tunneldir)s
chmod 600 %(tunneldir)s/id_ed25519
cat %(tunneldir)s/id_ed25519.pub
''' % {"tunneldir": tunnel_dir, "user": user, "comment": key_comment}
    proc = remote(pve.env, ip, keygen_script, "generate tunnel key",
                  timeout=60, sudo=True, dry_run=args.dry_run)
    if args.dry_run:
        return
    pubkey = proc.stdout.strip().splitlines()[-1]
    log("  tunnel public key: %s..." % pubkey[:40])

    # This SSHes to the RELAY, a different host from VM 103 -- reusing
    # remote()/ssh_guest with a copied env whose DF_CIUSER is overridden to
    # the relay's own login user, the same trick provision_relay.py's
    # scripts use, rather than a second copy of the SSH plumbing.
    relay_env = dict(pve.env)
    relay_env["DF_CIUSER"] = relay_user
    authkey_line = ('command="echo restricted",no-pty,no-agent-forwarding,'
                    'no-X11-forwarding,permitopen="127.0.0.1:%s" %s'
                    % (vnc_port, pubkey))
    relay_script = '''
mkdir -p ~/.ssh
chmod 700 ~/.ssh
touch ~/.ssh/authorized_keys
grep -qxF '%(line)s' ~/.ssh/authorized_keys || echo '%(line)s' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
''' % {"line": authkey_line}
    remote(relay_env, relay_ip, relay_script, "install tunnel key on relay",
          timeout=30, dry_run=args.dry_run)
    log("  restricted key installed on relay (permitopen=127.0.0.1:%s only)"
        % vnc_port)

    unit = VNC_TUNNEL_UNIT % {
        "user": user, "tunneldir": tunnel_dir, "vncport": vnc_port,
        "relayuser": relay_user, "relayip": relay_ip, "requires": requires,
    }
    setup_script = '''
cat > /etc/systemd/system/%(service)s.service <<'EOF'
%(unit)s
EOF

systemctl daemon-reload
systemctl enable --now %(service)s.service
sleep 2
systemctl is-active %(service)s.service
''' % {"unit": unit, "service": service}
    proc = remote(pve.env, ip, setup_script, "vnc-tunnel setup", timeout=60,
                  sudo=True, dry_run=args.dry_run)
    for line in proc.stdout.strip().splitlines():
        log("  " + line)
    log("tunnel service started on VM %s -- verify from the relay side"
        " (connect to its own 127.0.0.1:%s)" % (vmid, vnc_port))


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

    graphics = add("graphics", help="transplant official Steam/Premium tile"
                                     " graphics from a local install onto"
                                     " this VM's free Classic install")
    graphics.add_argument("--source", default=None,
                          help="root of a local Steam/Premium DF install"
                               " (the folder containing data/vanilla);"
                               " defaults to DF_GRAPHICS_SOURCE in .env")

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

    lua = add("lua", help="run one dfhack-run lua expression, print raw output")
    lua.add_argument("code",
                     help="Lua code, e.g."
                          " 'print(dfhack.gui.getCurViewscreen()._type)'")
    lua.add_argument("--timeout", type=int, default=60)

    run = add("run", help="call one already-deployed named dfhack script"
                          " directly, e.g. df-overseer-openarea find 5 5 169"
                          " \"Embark Site\" -- see docs/DF-UI-AUTOMATION.md"
                          " or the script's own file header for its CLI")
    run.add_argument("script_name",
                     help="script name without .lua, e.g. df-overseer-openarea")
    run.add_argument("script_args", nargs=argparse.REMAINDER,
                     help="arguments passed through to the script's own CLI")
    run.add_argument("--timeout", type=int, default=60)

    add("ui-install", help="deploy every scripts/dfhack/df-overseer-*.lua"
                            " file onto the guest's hack/scripts/ -- use"
                            " script-install to deploy just one")

    script_install = add("script-install",
                         help="deploy any scripts/dfhack/<name>.lua onto the"
                              " guest's hack/scripts/")
    script_install.add_argument("name",
                                help="script name without .lua, e.g."
                                     " df-overseer-labor")

    add("saves", help="list worlds in the XDG save dir, with sizes")

    backup = add("backup", help="pull the save dir off the VM")
    backup.add_argument("--out", default="backups",
                        help="local directory, default ./backups")

    systemd = add("systemd", help="install and enable the Xvfb + DF units")
    systemd.add_argument("--start", action="store_true",
                         help="also start the units now, instead of only"
                              " enabling them for the next boot")

    stream = add("stream", help="periodic screenshot capture (and optional push)")
    stream.add_argument("--interval", type=int, default=15,
                        help="seconds between captures, default 15")
    stream.add_argument("--ingest-url", default=None,
                        help="where to POST each screenshot; defaults to"
                             " DF_STREAM_INGEST_URL in .env, or local-only"
                             " capture if neither is set")

    vnc = add("vnc", help="LAN-reachable, view-only VNC (x11vnc) on the Xvfb display")
    vnc.add_argument("--port", type=int, default=None,
                     help="VNC port; default %s normally, %s with --control"
                          % (VNC_PORT, VNC_CONTROL_PORT))
    vnc.add_argument("--password", default=None,
                     help="VNC password; defaults to DF_VNC_PASSWORD in .env,"
                          " or a freshly generated one appended there."
                          " Rejected with --control (see cmd_vnc's docstring)")
    vnc.add_argument("--no-password", action="store_true",
                     help="drop the password gate entirely (x11vnc -nopw)."
                          " Feed stays -viewonly regardless -- see cmd_vnc's"
                          " docstring for why this is safe for a public feed."
                          " Rejected with --control (already implied there)")
    vnc.add_argument("--control", action="store_true",
                     help="install a SEPARATE df-vnc-control.service instead:"
                          " drops -viewonly (real mouse/keyboard reach the"
                          " game) and forces -nopw, meant to sit behind"
                          " Cloudflare Access only. Does not touch the"
                          " existing view-only instance -- see cmd_vnc's"
                          " docstring")

    webvnc = add("webvnc", help="bridge the x11vnc server to a plain browser tab"
                                 " via noVNC (no VNC client needed)")
    webvnc.add_argument("--port", type=int, default=NOVNC_PORT,
                        help="browser-facing port, default %s" % NOVNC_PORT)
    webvnc.add_argument("--vnc-port", type=int, default=VNC_PORT,
                        help="existing x11vnc port to bridge to, default %s"
                             % VNC_PORT)

    tunnel = add("vnc-tunnel", help="reverse SSH tunnel from VM 103 to the"
                                     " public relay (VM 103 dials out)")
    tunnel.add_argument("--relay-ip", required=True,
                        help="the relay's LAN IP, e.g. 192.168.2.202")
    tunnel.add_argument("--relay-user", default="relay",
                        help="login user on the relay, default 'relay'")
    tunnel.add_argument("--vnc-port", type=int, default=None,
                        help="port to forward; default %s normally, %s with"
                             " --control" % (VNC_PORT, VNC_CONTROL_PORT))
    tunnel.add_argument("--control", action="store_true",
                        help="tunnel the control x11vnc instance instead,"
                             " via a completely separate keypair/service --"
                             " see cmd_vnc_tunnel's docstring")

    args = parser.parse_args()
    # SUPPRESS means an unsupplied flag leaves no attribute at all.
    args.vmid = getattr(args, "vmid", None)
    args.dry_run = getattr(args, "dry_run", False)
    pve = PVE()
    handler = {
        "install": cmd_install,
        "verify": cmd_verify,
        "graphics": cmd_graphics,
        "start": cmd_start,
        "stop": cmd_stop,
        "gen": cmd_gen,
        "lua": cmd_lua,
        "run": cmd_run,
        "ui-install": cmd_ui_install,
        "script-install": cmd_script_install,
        "saves": cmd_saves,
        "backup": cmd_backup,
        "systemd": cmd_systemd,
        "stream": cmd_stream,
        "vnc": cmd_vnc,
        "webvnc": cmd_webvnc,
        "vnc-tunnel": cmd_vnc_tunnel,
    }[args.command]
    try:
        handler(pve, args)
    except PVEError as exc:
        log("FAILED: %s" % exc)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
