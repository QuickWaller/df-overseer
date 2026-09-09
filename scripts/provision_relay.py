"""Build a small Alpine relay VM (for the DF live-view VNC bridge) and clone it.

    python scripts/provision_relay.py status
    python scripts/provision_relay.py fetch-image
    python scripts/provision_relay.py build-template [--vmid N] [--memory 512]
    python scripts/provision_relay.py clone [--name df-colony-relay-01] [--full]
    python scripts/provision_relay.py start [--vmid N] [--force]
    python scripts/provision_relay.py webvnc [--port 6080] [--vnc-port 5900]
    python scripts/provision_relay.py cloudflared [--token TOKEN]

Not a Dwarf Fortress VM. This is the small, disposable relay that bridges
VM 103's VNC feed toward a public Cloudflare Tunnel. LAN infra (the webvnc
chain above) came first, by deliberate agreement -- see Working.md's
2026-09-09 relay thread. The 'cloudflared' subcommand is the public leg:
installs cloudflared from Cloudflare's own apt repo, and, once a dashboard
connector token exists, runs the token-based service install. See
cmd_cloudflared's own docstring below for the install-source verification.
Debian (genericcloud), not Ubuntu: this VM does
one lightweight job (hold an SSH tunnel open, relay RFB bytes through
websockify), so it gets a smaller distro than df-overseer's DF-sized Ubuntu
template rather than reusing it, while staying on the same apt/dpkg ecosystem
(same package names, same install idioms already proven for VM 103). See
decisions/DECISIONS.md 2026-09-09 for why Debian over an LXC container
(isolation: this box is slated to eventually be the one internet-facing thing
in the estate, and LXC shares the host kernel) and over Alpine (Alpine's
`cloud-init` package locks the account password by default, and Alpine's
`openssh` -- built without PAM -- refuses pubkey SSH logins on a locked
account regardless of a correctly-installed key; confirmed against Alpine's
own README.Alpine for the cloud-init package, and the clean fix needs a
custom cloud-init snippet, which Proxmox's API cannot upload and which
placing by hand would need forbidden host SSH access). Debian/Ubuntu's
PAM-enabled openssh has no such interaction.

Reuses pve.py and the generic, non-DF-specific helpers already in
provision_vm.py (read_pubkey, wait_for_status, resize_disk,
destroy_failed_build) rather than duplicating them -- only the parts that are
genuinely relay-specific (image pin, sizing, its own .env keys) live here.

Own env var prefix (RELAY_*), deliberately separate from VM 103's DF_* vars,
so building or rebuilding this guest can never collide with or overwrite VM
103's configuration. Nothing host-specific is hardcoded -- it all comes from
.env (gitignored).
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pve import PVE, PVEError, log  # noqa: E402
from provision_vm import (  # noqa: E402
    read_pubkey, wait_for_status, resize_disk, destroy_failed_build,
)
from install_df import (  # noqa: E402
    remote, NOVNC_UNIT, NOVNC_PORT, VNC_PORT, install_novnc_index,
)

# Pinned to an exact dated build, not 'latest' -- same reasoning as
# provision_vm.CLOUD_IMAGE_SERIAL: a dated URL is only a name, the checksum
# is the actual pin, and PVE verifies it host-side during download-url.
#
# Checked live 2026-09-09 against the real directory listing at
# https://cloud.debian.org/images/cloud/bookworm/20260907-2594/ (via curl,
# not a summarized fetch) and the real SHA512SUMS file at the same path,
# grepped directly for this exact filename -- a checksum must not pass
# through an LLM paraphrasing step, per the 2026-09-09 Alpine-image lesson.
#
# 'genericcloud', not the plain 'generic' image: identical guest, smaller
# kernel driver set (fewer hardware drivers compiled in), matching this
# relay's whole point of being the lightest VM that reliably does the job.
# 'bios', not 'uefi': matches provision_vm.py's existing template, which sets
# no bios/efidisk0 keys (Proxmox's SeaBIOS default) -- Debian's cloud image
# boots hybrid BIOS/UEFI, same as Ubuntu's.
RELAY_DEBIAN_BUILD = "20260907-2594"
RELAY_CLOUD_IMAGE_URL = (
    "https://cloud.debian.org/images/cloud/bookworm/%s/"
    "debian-12-genericcloud-amd64-%s.qcow2"
    % (RELAY_DEBIAN_BUILD, RELAY_DEBIAN_BUILD)
)
RELAY_CLOUD_IMAGE_SHA512 = (
    "2bc4bad1dafce08937f04760d86fb735a35ca862c322a2c0018e86124bbac0d"
    "24fc276047559b11e31b51caf73a5d295e3259a0aef69506af6ec62ae0a71ab81"
)
RELAY_CLOUD_IMAGE = "debian-12-genericcloud-amd64-%s.qcow2" % RELAY_DEBIAN_BUILD
IMAGE_CONTENT = "import"
TEMPLATE_NAME = "relay-debian-12-%s-template" % RELAY_DEBIAN_BUILD
DISK_SIZE = "4G"
BRIDGE = "vmbr0"

# Sized for what this VM actually does -- hold one SSH tunnel open and relay
# already-encoded RFB bytes through websockify, not run DF. See
# research/2026-09-09-reverse-vnc-relay.md 6 ("a lightweight relay... the
# smallest paid tier... is comfortably sufficient").
DEFAULT_MEMORY = 512
DEFAULT_BALLOON = 256
DEFAULT_CORES = 1

# Cloudflare's own current documented "(Recommended)" apt-repo method for any
# Debian-based distro -- checked live 2026-09-09 by fetching
# https://pkg.cloudflare.com/index.html directly (not paraphrased from a
# tutorial): a keyring file under /usr/share/keyrings/ with an inline
# 'signed-by=' apt source line, not the older, now-deprecated apt-key import
# path. There is no tarball checksum to pin here the way DF_SHA256/
# RELAY_CLOUD_IMAGE_SHA512 pin a download -- the trust anchor is the GPG key
# itself, fetched by the relay directly via curl (never through an
# LLM-summarized fetch, same discipline as this project's checksum rule),
# and apt's own signature verification on every subsequent update/install.
CLOUDFLARED_GPG_URL = "https://pkg.cloudflare.com/cloudflare-main.gpg"
CLOUDFLARED_GPG_PATH = "/usr/share/keyrings/cloudflare-main.gpg"
CLOUDFLARED_APT_REPO = "https://pkg.cloudflare.com/cloudflared"


def guest_address(env):
    """(ipconfig0 value, nameserver) for the relay clone, from RELAY_VM_IP.

    Deliberately separate from provision_vm.guest_address(), which reads
    DF_VM_IP -- VM 103's address must never be at risk of being overwritten
    by a relay build or rebuild sharing the same variable.
    """
    cidr = env.get("RELAY_VM_IP")
    if not cidr:
        raise PVEError(
            "RELAY_VM_IP is not set in .env.\n"
            "  A clone needs a static address assigned before it boots.\n"
            "  home-lab allocates this -- see Working.md's relay thread.\n"
            "  e.g. RELAY_VM_IP=192.168.2.202/24"
        )
    if "/" not in cidr:
        raise PVEError("RELAY_VM_IP must include a prefix, e.g. %s/24" % cidr)
    ip = cidr.split("/")[0]
    gw = env.get("RELAY_GW") or ".".join(ip.split(".")[:3] + ["1"])
    dns = env.get("RELAY_DNS") or gw
    return "ip=%s,gw=%s" % (cidr, gw), dns


def cmd_status(pve, args):
    total, used, free, available = pve.node_memory()
    log("host memory: %.1f GiB total, %.1f available (%.1f used, %.1f free)"
        % (total, available, used, free))
    log("next free vmid: %s" % pve.next_vmid())


def cmd_fetch_image(pve, args):
    existing = pve.get(pve.node_path("/storage/%s/content" % pve.storage),
                       params={"content": IMAGE_CONTENT}) or []
    volid = "%s:%s/%s" % (pve.storage, IMAGE_CONTENT, RELAY_CLOUD_IMAGE)
    if any(v["volid"] == volid for v in existing):
        log("already present: %s" % volid)
        return volid
    log("downloading %s -> %s" % (RELAY_CLOUD_IMAGE_URL, volid))
    upid = pve.post(pve.node_path("/storage/%s/download-url" % pve.storage), {
        "content": IMAGE_CONTENT,
        "filename": RELAY_CLOUD_IMAGE,
        "url": RELAY_CLOUD_IMAGE_URL,
        # PVE verifies this itself, during the download, on the host. A
        # mismatch fails the task rather than importing a wrong image.
        "checksum": RELAY_CLOUD_IMAGE_SHA512,
        "checksum-algorithm": "sha512",
    })
    pve.wait_task(upid, "download cloud image", timeout=1800)
    log("done: %s" % volid)
    return volid


def cmd_build_template(pve, args):
    vmid = args.vmid or pve.next_vmid()
    pubkey = read_pubkey(pve.env)
    image = "%s:%s/%s" % (pve.storage, IMAGE_CONTENT, RELAY_CLOUD_IMAGE)

    total, used, free, available = pve.node_memory()
    log("host memory now: %.1f GiB available of %.1f (%.1f used, %.1f free)"
        % (available, total, used, free))

    log("creating VM %s (%s) in pool %s" % (vmid, TEMPLATE_NAME, pve.pool))
    upid = pve.post(pve.node_path("/qemu"), {
        "vmid": vmid,
        "name": TEMPLATE_NAME,
        "pool": pve.pool,
        "ostype": "l26",
        "cores": args.cores,
        "sockets": 1,
        "cpu": "host",
        "memory": args.memory,
        "balloon": args.balloon,
        "agent": "enabled=1",
        "scsihw": "virtio-scsi-single",
        # import-from turns the downloaded cloud image into this VM's disk.
        # qcow2 is mandatory: 'dir' storage cannot snapshot raw.
        "scsi0": "%s:0,import-from=%s,discard=on,ssd=1,format=qcow2" % (
            pve.storage, image),
        "ide2": "%s:cloudinit" % pve.storage,
        "boot": "order=scsi0",
        "net0": "virtio,bridge=%s" % BRIDGE,
        # Cloud images log boot to the serial console; without this a failed
        # cloud-init is invisible.
        "serial0": "socket",
        "vga": "serial0",
        "citype": "nocloud",
        "ciuser": args.ciuser,
        "sshkeys": pubkey,
        "ipconfig0": "ip=dhcp",
    })
    pve.wait_task(upid, "create VM %s" % vmid)
    log("  disk imported from %s" % image)

    # Everything past creation is guarded: a build that dies partway leaves a
    # VM that is neither a usable template nor obviously junk.
    try:
        resize_disk(pve, vmid, size=DISK_SIZE)

        log("converting %s to a template" % vmid)
        upid = pve.post(pve.vm_path(vmid, "/template"))
        pve.wait_task(upid, "template conversion")

        config = pve.get(pve.vm_path(vmid, "/config"))
        log("done. template %s:" % vmid)
        for key in ("name", "template", "memory", "balloon", "cores", "scsi0",
                    "ide2", "net0", "ciuser", "ipconfig0"):
            if key in config:
                log("  %-9s %s" % (key, config[key]))
    except Exception:
        if getattr(args, "keep_failed", False):
            log("build failed -- VM %s left in place (--keep-failed)" % vmid)
        else:
            log("build failed -- tearing down VM %s" % vmid)
            destroy_failed_build(pve, vmid)
        raise

    log("\nrecord RELAY_TEMPLATE_VMID=%s in .env" % vmid)
    return vmid


def cmd_clone(pve, args):
    template_vmid = args.template or pve.env.get("RELAY_TEMPLATE_VMID")
    if not template_vmid:
        raise PVEError("no template vmid: pass --template or set "
                       "RELAY_TEMPLATE_VMID in .env")
    newid = args.vmid or pve.next_vmid()
    log("cloning %s -> %s (%s)" % (template_vmid, newid,
                                   "full" if args.full else "linked"))
    upid = pve.post(pve.vm_path(template_vmid, "/clone"), {
        "newid": newid,
        "name": args.name,
        "pool": pve.pool,
        "full": 1 if args.full else 0,
        "storage": pve.storage if args.full else None,
    })
    pve.wait_task(upid, "clone", timeout=1800)

    # Assign the address now, before the VM is ever started, so it comes up
    # on it directly rather than taking a DHCP lease and switching later.
    ipconfig, dns = guest_address(pve.env)
    log("assigning address: %s, dns %s" % (ipconfig, dns))
    pve.put(pve.vm_path(newid, "/config"),
            {"ipconfig0": ipconfig, "nameserver": dns})

    log("done. record RELAY_VMID=%s in .env" % newid)
    return newid


def cmd_start(pve, args):
    vmid = args.vmid or pve.env.get("RELAY_VMID")
    if not vmid:
        raise PVEError("no vmid: pass --vmid or set RELAY_VMID in .env")
    status = pve.get(pve.vm_path(vmid, "/status/current"))
    if status.get("status") == "running":
        log("vm %s already running" % vmid)
        return
    total, used, free, available = pve.node_memory()
    cfg = pve.get(pve.vm_path(vmid, "/config"))
    needed = int(cfg.get("memory", DEFAULT_MEMORY)) / 1024.0
    if available < needed and not args.force:
        raise PVEError("only %.1f GiB available, vm %s wants %.1f GiB -- "
                       "pass --force to start anyway" % (available, vmid, needed))
    log("starting vm %s" % vmid)
    pve.wait_task(pve.post(pve.vm_path(vmid, "/status/start")), "start")
    wait_for_status(pve, vmid, "running", timeout=120)
    log("running.")


def cmd_webvnc(pve, args):
    """Install websockify + noVNC on the relay, pointed at localhost:<vnc-port>.

    Assumes VM 103's reverse SSH tunnel (install_df.py's 'vnc-tunnel') is
    already forwarding that port from VM 103's x11vnc to the relay's own
    loopback -- this only adds the browser-facing hop, same NOVNC_UNIT
    install_df.py's own 'webvnc' uses on VM 103, reused rather than
    duplicated, just pointed at this host instead.
    """
    ip = (pve.env.get("RELAY_VM_IP") or "").split("/")[0]
    if not ip:
        raise PVEError("RELAY_VM_IP is not set in .env")
    user = pve.env.get("RELAY_CIUSER", "relay")
    port = args.port
    vnc_port = args.vnc_port

    log("installing noVNC + websockify on the relay (browser port %s ->"
        " localhost:%s)" % (port, vnc_port))

    relay_env = dict(pve.env)
    relay_env["DF_CIUSER"] = user

    pkg_script = '''
if ! command -v websockify >/dev/null 2>&1 || [ ! -d /usr/share/novnc ]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq novnc websockify
fi
'''
    remote(relay_env, ip, pkg_script, "install novnc/websockify", timeout=180,
          sudo=True, dry_run=args.dry_run)
    install_novnc_index(relay_env, ip, args.dry_run)

    # No local unit to depend on here: x11vnc is on VM 103, reached only
    # through the reverse SSH tunnel (a different host's systemd unit
    # entirely) -- see NOVNC_UNIT's own comment in install_df.py for why
    # 'Requires=df-vnc.service' would be wrong (and fatal) on this host.
    unit = NOVNC_UNIT % {
        "user": user, "port": port, "vncport": vnc_port,
        "depends": "After=network.target",
    }
    setup_script = '''
cat > /etc/systemd/system/df-webvnc.service <<'EOF'
%(unit)s
EOF

systemctl daemon-reload
systemctl enable --now df-webvnc.service
systemctl is-active df-webvnc.service
''' % {"unit": unit}
    proc = remote(relay_env, ip, setup_script, "webvnc setup", timeout=120,
                  sudo=True, dry_run=args.dry_run)
    if args.dry_run:
        return
    for line in proc.stdout.strip().splitlines():
        log("  " + line)
    log("open http://%s:%s/ in a browser -- auto-redirects to the live feed"
        " (password requirement depends on how VM 103's 'vnc' was run)"
        % (ip, port))


def cmd_cloudflared(pve, args):
    """Install cloudflared from Cloudflare's own apt repo, and, once a
    dashboard connector token exists, run the token-based service install.

    Two independent, idempotent steps, deliberately not gated on each other:
    this can install cloudflared today, with no token yet, and the token
    step can be re-run later (a different day, a rotated token) without
    reinstalling the package.

    Install source, verified live 2026-09-09 by fetching
    https://pkg.cloudflare.com/index.html directly rather than assuming a
    remembered doc or a tutorial's word for it (see CLOUDFLARED_GPG_URL's
    comment for the exact check): Cloudflare's own current "(Recommended)"
    method for any Debian-based distro is a keyring file under
    /usr/share/keyrings/ with an inline 'signed-by=' apt source line --
    confirmed still current, not the deprecated apt-key path some older
    tutorials still show.

    Once installed, 'cloudflared service install <token>' is Cloudflare's
    own documented non-interactive dashboard-token flow (confirmed via
    their Cloudflare One docs and current community usage 2026-09-09): it
    registers cloudflared as a systemd service pointed at the tunnel that
    token identifies -- no 'cloudflared tunnel login', no interactive
    browser auth, nothing this script could get wrong by guessing. The
    token itself is handled exactly like DF_VNC_PASSWORD elsewhere in this
    project: never logged, never echoed into a --dry-run script dump,
    read from --token or CLOUDFLARE_TUNNEL_TOKEN in .env.

    What this does NOT do, and does not need to: run 'cloudflared tunnel
    route dns'. That command belongs to the older CLI-managed ("locally
    managed") tunnel workflow. This project uses the dashboard-managed
    ("remotely managed") token flow instead, where adding a Public Hostname
    in the dashboard's tunnel config auto-creates the DNS CNAME itself, as
    long as the zone is on Cloudflare DNS -- confirmed true for willsmith.nz
    (user-confirmed 2026-09-09). See Working.md for the exact dashboard
    steps this leaves for whoever holds the token.
    """
    ip = (pve.env.get("RELAY_VM_IP") or "").split("/")[0]
    if not ip:
        raise PVEError("RELAY_VM_IP is not set in .env")
    user = pve.env.get("RELAY_CIUSER", "relay")
    relay_env = dict(pve.env)
    relay_env["DF_CIUSER"] = user

    token = args.token or pve.env.get("CLOUDFLARE_TUNNEL_TOKEN")

    log("installing cloudflared on the relay via pkg.cloudflare.com's apt repo")
    install_script = '''
if ! command -v cloudflared >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  mkdir -p /usr/share/keyrings
  curl -fsSL %(gpg_url)s | tee %(gpg_path)s >/dev/null
  echo 'deb [signed-by=%(gpg_path)s] %(repo_url)s any main' \\
    > /etc/apt/sources.list.d/cloudflared.list
  apt-get update -qq
  apt-get install -y -qq cloudflared
fi
cloudflared --version
''' % {
        "gpg_url": CLOUDFLARED_GPG_URL,
        "gpg_path": CLOUDFLARED_GPG_PATH,
        "repo_url": CLOUDFLARED_APT_REPO,
    }
    proc = remote(relay_env, ip, install_script, "install cloudflared",
                  timeout=180, sudo=True, dry_run=args.dry_run)
    if proc:
        for line in proc.stdout.strip().splitlines():
            log("  " + line)

    if not token:
        log("no connector token given (--token / CLOUDFLARE_TUNNEL_TOKEN) --"
            " cloudflared is installed but not yet connected to any tunnel.")
        log("  create a tunnel in the Zero Trust dashboard (Networks -> Tunnels),"
            " copy its connector token, then re-run this with --token or"
            " CLOUDFLARE_TUNNEL_TOKEN in .env.")
        return

    log("connecting cloudflared to the dashboard tunnel (service install)")
    # Never let the real token land in a --dry-run script dump -- remote()
    # logs the whole body under --dry-run, same reasoning as cmd_vnc's
    # script_password placeholder in install_df.py.
    script_token = "<CLOUDFLARE_TUNNEL_TOKEN>" if args.dry_run else token
    service_script = '''
cloudflared service install %(token)s
sleep 2
systemctl is-active cloudflared
''' % {"token": script_token}
    proc = remote(relay_env, ip, service_script, "cloudflared service install",
                  timeout=60, sudo=True, dry_run=args.dry_run)
    if args.dry_run:
        return
    for line in proc.stdout.strip().splitlines():
        log("  " + line)
    log("cloudflared connected. In the dashboard tunnel's Public Hostname tab,"
        " add hostname 'dwarf-fortress.willsmith.nz' -> service"
        " 'http://localhost:6080' -- willsmith.nz is already on Cloudflare"
        " DNS, so this auto-creates the CNAME; no 'tunnel route dns' needed.")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name, **kw):
        return sub.add_parser(name, **kw)

    add("status", help="host memory, next vmid")
    add("fetch-image", help="download the Alpine cloud image into 'import'")

    build = add("build-template", help="cloud image -> VM -> template")
    build.add_argument("--vmid", type=int)
    build.add_argument("--memory", type=int, default=DEFAULT_MEMORY)
    build.add_argument("--balloon", type=int, default=DEFAULT_BALLOON)
    build.add_argument("--cores", type=int, default=DEFAULT_CORES)
    build.add_argument("--ciuser", default="relay")
    build.add_argument("--keep-failed", action="store_true")

    clone = add("clone", help="clone the template into a VM")
    clone.add_argument("--template", type=int)
    clone.add_argument("--vmid", type=int)
    clone.add_argument("--name", default="df-colony-relay-01")
    clone.add_argument("--full", action="store_true")

    start = add("start", help="start a VM, gated on host memory")
    start.add_argument("--vmid", type=int)
    start.add_argument("--force", action="store_true")

    webvnc = add("webvnc", help="install websockify+noVNC pointed at"
                                 " localhost:<vnc-port>")
    webvnc.add_argument("--port", type=int, default=NOVNC_PORT,
                        help="browser-facing port, default %s" % NOVNC_PORT)
    webvnc.add_argument("--vnc-port", type=int, default=VNC_PORT,
                        help="tunneled port to bridge to, default %s" % VNC_PORT)
    webvnc.add_argument("--dry-run", action="store_true",
                        help="print the remote script instead of running it")

    cloudflared = add("cloudflared", help="install cloudflared (Cloudflare's own"
                                            " apt repo) and, once a connector"
                                            " token exists, connect it to a tunnel")
    cloudflared.add_argument("--token", default=None,
                             help="dashboard tunnel connector token; defaults to"
                                  " CLOUDFLARE_TUNNEL_TOKEN in .env. If neither is"
                                  " set, this only installs cloudflared and does"
                                  " not connect it to anything.")
    cloudflared.add_argument("--dry-run", action="store_true",
                             help="print the remote script instead of running it")

    args = parser.parse_args()
    pve = PVE()
    handler = {
        "status": cmd_status,
        "fetch-image": cmd_fetch_image,
        "build-template": cmd_build_template,
        "clone": cmd_clone,
        "start": cmd_start,
        "webvnc": cmd_webvnc,
        "cloudflared": cmd_cloudflared,
    }[args.command]
    try:
        handler(pve, args)
    except PVEError as exc:
        log("FAILED: %s" % exc)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
