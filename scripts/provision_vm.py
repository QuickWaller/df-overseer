"""Build the df-overseer VM template from the Ubuntu cloud image, and clone it.

    python scripts/provision_vm.py status
    python scripts/provision_vm.py fetch-image
    python scripts/provision_vm.py build-template [--vmid N] [--memory 6144]
    python scripts/provision_vm.py clone [--name df-fortress] [--full]
                                         [--ip-var DF_VM_IP]
    python scripts/provision_vm.py set-memory --vmid N --memory 6144
    python scripts/provision_vm.py set-onboot [--vmid N] --enable|--disable
    python scripts/provision_vm.py snapshot --name N [--vmid N] [--description D]
    python scripts/provision_vm.py rollback --name N [--vmid N]
    python scripts/provision_vm.py start [--vmid N] [--force]

The template is built from scratch out of a cloud image we downloaded, on
purpose: an earlier VM here was a linked clone of a template outside our pool,
invisible to us and able to take our VM with it if deleted. The template is
never booted: it is created, resized and converted, nothing more, so there is
nothing on it to seal. See guest_address() below for how a clone gets its
address instead of the template ever running.

Nothing host-specific is hardcoded -- it all comes from .env (gitignored).
"""

import argparse
import os
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pve import PVE, PVEError, log  # noqa: E402

# Stored as .qcow2, not .img. Canonical's file *is* qcow2, but it ships with an
# .img extension, and an 'import'-content store rejects that outright:
#   400 {"errors":{"filename":"invalid filename or wrong extension"}}
# download-url lets us name the destination independently of the URL, so the
# rename happens on the way in rather than as a second step on the host.
# Verified by that exact failure, 2026-08-26.
#
# Pinned, not tracking 'current'. Two rebuilds a month apart used to fetch
# different, unverified base images, which made "rebuildable" true and
# "reproducible" false. A dated URL is only a name: the sha256 is the actual
# pin, and PVE verifies it host-side during download-url, so no host shell and
# no check of our own is needed.
#
# Two traps, both confirmed against the published tree on 2026-09-08:
#   1. The filename differs between the daily tree and the releases tree.
#      'releases/noble/release-<serial>/' carries
#      ubuntu-24.04-server-cloudimg-amd64.img and does NOT carry
#      noble-server-cloudimg-amd64.img, so changing only the directory 404s.
#   2. The daily tree keeps roughly six serials; the releases tree goes back
#      to release-20240423, which is why the pin lives there.
#
# Bumping the pin is a deliberate act: change the serial and the hash
# together, and record it in decisions/DECISIONS.md.
CLOUD_IMAGE_SERIAL = "20260826"
CLOUD_IMAGE_SHA256 =     "d0fe84bb5f80853425fa6be28e2c106f30104c3cfe8611933f2e65c9b63f0e30"
CLOUD_IMAGE_URL = ("https://cloud-images.ubuntu.com/releases/noble/"
                   "release-%s/ubuntu-24.04-server-cloudimg-amd64.img"
                   % CLOUD_IMAGE_SERIAL)
# The serial is in the destination name on purpose. The 'already present'
# check below matches on volid, so without it a bumped pin would find the old
# image sitting in storage and reuse it without ever downloading or verifying
# the new one, which is the cached-file trust bug in a different costume.
CLOUD_IMAGE = "ubuntu-24.04-server-cloudimg-amd64-%s.qcow2" % CLOUD_IMAGE_SERIAL
# 'import-from' will only read a volume whose content type is 'images' or
# 'import' -- an 'iso' volume is rejected outright, even though the file is
# identical. download-url can write straight into 'import', so the image is
# fetched there rather than moved.
IMAGE_CONTENT = "import"
TEMPLATE_NAME = "df-overseer-noble-template"
DISK_SIZE = "25G"
BRIDGE = "vmbr0"

# 6 GB max with a 2 GB balloon floor: the user's call on 2026-08-26 with ~5.5 GB
# available on the host. KVM only backs pages the guest touches, so idle DF sits
# far below this; the worldgen spike is the real peak. Memory is a one-line
# change on a stopped VM -- re-check node_memory()'s *available* before booting.
DEFAULT_MEMORY = 6144
DEFAULT_BALLOON = 2048
DEFAULT_CORES = 4
# 'host' blocks migration between the cluster's two different CPU
# generations (Kaby Lake / Coffee Lake), defeating the point of clustering
# at all; a common baseline fixes it, and DF's workload (single-threaded,
# not AVX-heavy) doesn't need 'host'. decisions/DECISIONS.md 2026-08-28.
DEFAULT_CPU = "x86-64-v2-AES"


def read_pubkey(env):
    """cloud-init 'sshkeys' takes the key material; the repo only ever holds
    the path to it.

    The value must be URL-encoded *before* it goes in the form body -- Proxmox
    decodes the field once as form data and then validates that what it finds
    is still a urlencoded string, so a plain key is rejected with
    "invalid urlencoded string". Verified by that exact failure, 2026-08-26.
    """
    path = env.get("DF_SSH_PUBKEY")
    if not path:
        raise PVEError("DF_SSH_PUBKEY is not set in .env")
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        raise PVEError("public key not found: %s" % path)
    with open(path, encoding="utf-8") as fh:
        return quote(fh.read().strip(), safe="")


def guest_address(env, var="DF_VM_IP"):
    """(ipconfig0 value, nameserver) for a clone, from .env.

    Static assignment replaces DHCP plus MAC pinning: the address is known
    before the VM ever boots, there is no router reservation to keep in sync
    with a rebuild, and the guest agent is no longer the way to find the VM --
    it is assigned at clone time, not discovered afterwards. This also removes
    the router's hand-edited reservation table as a source of truth: the
    address lives in .env, which this repo already treats as the record of
    what a VM is.

    `var` names which .env key holds the address, because this pool now holds
    more than one guest: DF_VM_IP is the fort, OPENCLAW_VM_IP is the agent
    host. It was hardcoded until 2026-09-12, which meant cloning any second
    VM would silently hand it the *running fort's* address. Nothing caught
    that, so see the collision check in cmd_clone() as well -- a wrong .env
    key should fail on the host, not on the network.

    DF_GW and DF_DNS stay unparameterised on purpose: a gateway and a resolver
    are properties of the subnet, not of a guest, and both VMs sit on the one
    subnet. DF_GW defaults to .1 of the same /24, which is right on
    essentially every home network and wrong loudly rather than silently if it
    is not.
    """
    cidr = env.get(var)
    if not cidr:
        raise PVEError(
            "%s is not set in .env.\n"
            "  A clone needs a static address assigned before it boots.\n"
            "  Pick one outside the router's DHCP pool, e.g."
            " %s=192.168.1.240/24" % (var, var)
        )
    if "/" not in cidr:
        raise PVEError("%s must include a prefix, e.g. %s/24" % (var, cidr))
    ip = cidr.split("/")[0]
    gw = env.get("DF_GW") or ".".join(ip.split(".")[:3] + ["1"])
    # A DHCP guest is handed DNS by the router; a static one is not. Without an
    # explicit nameserver the guest boots with no resolver and the guest
    # install fails on apt-get's first name lookup, which reads as a network
    # fault rather than a missing setting. The gateway answers DNS on
    # essentially every home router, and DF_DNS overrides it where it does not.
    dns = env.get("DF_DNS") or gw
    return "ip=%s,gw=%s" % (cidr, gw), dns


def ssh_guest(env, ip, command, timeout=120, check=True, input_data=None):
    """Run a command in the guest over SSH, as the cloud-init user.

    The build VM is short-lived and its host key dies with it, so it is kept
    out of the real known_hosts rather than accepted into it and left to
    collide with whatever later takes the address.

    The throwaway file lives in the system temp dir, NOT at os.devnull: on
    Windows that is the bare string "nul", which OpenSSH treats as a relative
    filename and duly creates in the working directory. That put an untracked
    file named `nul` in the repo root, which git cannot even index
    ("short read while indexing nul"). Verified by that exact failure,
    2026-08-27.

    `input_data` (str, optional): sent to the remote command over stdin
    instead of being embedded in `command` itself. **Required for any
    payload beyond a few KB** -- found 2026-09-10 debugging a silent
    `install_df.py ui-install` failure: this same `ssh.exe` (Git's MSYS-linked
    build) accepts an arbitrarily long command line when a POSIX parent
    (bash) execs it directly, but silently truncates the command line to
    ~8182 characters when a native Win32 parent (Python's `subprocess`,
    which must flatten argv into one `CreateProcess` command-line string)
    spawns it instead -- confirmed by reproducing the exact truncation length
    with a minimal script, and confirming bash-invoked `ssh` with an
    identical, longer payload does not truncate. No error, no non-zero exit:
    the remote side just receives and runs a truncated command. `remote()`'s
    base64 payload now goes over stdin for exactly this reason -- never
    revert to embedding a payload of unbounded size directly in `command`.
    """
    key = os.path.expanduser(env.get("DF_SSH_KEY", ""))
    if not key or not os.path.exists(key):
        raise PVEError("DF_SSH_KEY not found: %s" % key)
    argv = [
        "ssh", "-i", key,
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=%s" % os.path.join(
            tempfile.gettempdir(), "df-overseer-throwaway-known-hosts"),
        "-o", "ConnectTimeout=10",
        "-o", "LogLevel=ERROR",
        "%s@%s" % (env.get("DF_CIUSER", "df"), ip),
        command,
    ]
    # encoding/errors explicit: text=True alone decodes with the platform's
    # preferred encoding, cp1252 on Windows, which raised UnicodeDecodeError
    # on this workstation the first time a remote command's output contained
    # a UTF-8 multibyte character (systemd's unit-state bullet, 2026-08-30).
    # The guest is Ubuntu and everything it prints is UTF-8.
    proc = subprocess.run(argv, capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          timeout=timeout, input=input_data)
    if check and proc.returncode != 0:
        raise PVEError("ssh failed (%s): %s"
                       % (proc.returncode, (proc.stderr or proc.stdout).strip()))
    return proc


def wait_for_status(pve, vmid, want, timeout=300, poll=3):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = pve.get(pve.vm_path(vmid, "/status/current")).get("status")
        if status == want:
            return status
        time.sleep(poll)
    raise PVEError("VM %s did not reach '%s' within %ss" % (vmid, want, timeout))


def resize_disk(pve, vmid, disk="scsi0", size=DISK_SIZE, attempts=4, pause=20):
    """Grow a disk, retrying the storage-load timeout described at the call site.

    Growing is idempotent: PVE treats a resize to the current size as a no-op,
    so a retry after a *partial* success cannot shrink or damage anything.
    """
    for attempt in range(1, attempts + 1):
        log("resizing %s to %s (attempt %d/%d)" % (disk, size, attempt, attempts))
        try:
            upid = pve.put(pve.vm_path(vmid, "/resize"),
                           {"disk": disk, "size": size})
            pve.wait_task(upid, "resize", timeout=900)
            return
        except PVEError as exc:
            if "timeout" not in str(exc).lower() or attempt == attempts:
                raise
            log("  timed out, retrying in %ds: %s" % (pause, exc))
            time.sleep(pause)


def destroy_failed_build(pve, vmid):
    """Tear down a VM a failed build created, so no half-made VM is left.

    This deliberately discards the evidence: today's diagnosis of the resize
    timeout and the agent-verb bug both depended on the broken VM still being
    there. --keep-failed is the escape hatch, and richer failure capture (task
    logs, guest console) is the thing to add here if the teardown starts
    costing more than the clutter it prevents.
    """
    try:
        if pve.get(pve.vm_path(vmid, "/status/current")).get("status") == "running":
            log("  stopping %s" % vmid)
            pve.wait_task(pve.post(pve.vm_path(vmid, "/status/stop")), "stop")
            wait_for_status(pve, vmid, "stopped", timeout=180)
        log("  destroying %s" % vmid)
        pve.wait_task(pve.delete(pve.vm_path(vmid)), "destroy %s" % vmid)
        log("  cleaned up. re-run the build once the cause is fixed.")
    except PVEError as exc:
        # Never let cleanup mask the real failure being re-raised above it.
        log("  CLEANUP FAILED, VM %s is still on the host: %s" % (vmid, exc))


def cmd_status(pve, args):
    total, used, free, available = pve.node_memory()
    log("host memory: %.1f GiB total, %.1f available (%.1f used, %.1f free)"
        % (total, available, used, free))
    log("  gate on 'available', not 'free' -- see pve.node_memory()")
    log("next free vmid: %s" % pve.next_vmid())
    members = pve.pool_members()
    if not members:
        log("pool '%s': empty" % pve.pool)
        return
    log("pool '%s':" % pve.pool)
    for m in members:
        log("  %s  %-28s %-9s %s%s" % (
            m.get("vmid"), m.get("name", "?"), m.get("status", "?"),
            "%s MB" % (m.get("maxmem", 0) // 2 ** 20),
            "  [template]" if m.get("template") else "",
        ))


def cmd_fetch_image(pve, args):
    """Download the Ubuntu cloud image into the storage's 'import' content.

    Requires <storage> to have the 'import' content type enabled
    (Datacenter -> Storage -> Edit -> Content). That flag is datacenter
    configuration and needs Datastore.Allocate at /storage, which this token
    deliberately does not have -- it is a one-time human step.
    """
    existing = pve.get(pve.node_path("/storage/%s/content" % pve.storage),
                       params={"content": IMAGE_CONTENT}) or []
    volid = "%s:%s/%s" % (pve.storage, IMAGE_CONTENT, CLOUD_IMAGE)
    if any(v["volid"] == volid for v in existing):
        log("already present: %s" % volid)
        return volid
    log("downloading %s -> %s" % (CLOUD_IMAGE_URL, volid))
    upid = pve.post(pve.node_path("/storage/%s/download-url" % pve.storage), {
        "content": IMAGE_CONTENT,
        "filename": CLOUD_IMAGE,
        "url": CLOUD_IMAGE_URL,
        # PVE verifies this itself, during the download, on the host. A
        # mismatch fails the task rather than importing a wrong image.
        "checksum": CLOUD_IMAGE_SHA256,
        "checksum-algorithm": "sha256",
    })
    pve.wait_task(upid, "download cloud image", timeout=3600)
    log("done: %s" % volid)
    return volid


def cmd_build_template(pve, args):
    vmid = args.vmid or pve.next_vmid()
    pubkey = read_pubkey(pve.env)
    image = "%s:%s/%s" % (pve.storage, IMAGE_CONTENT, CLOUD_IMAGE)

    total, used, free, available = pve.node_memory()
    log("host memory now: %.1f GiB available of %.1f (%.1f used, %.1f free)"
        % (available, total, used, free))
    if available < args.memory / 1024.0:
        log("NOTE: %d MB requested exceeds available memory. The template is"
            " never booted, so building is still safe -- but re-check before"
            " starting a clone." % args.memory)

    log("creating VM %s (%s) in pool %s" % (vmid, TEMPLATE_NAME, pve.pool))
    upid = pve.post(pve.node_path("/qemu"), {
        "vmid": vmid,
        "name": TEMPLATE_NAME,
        "pool": pve.pool,
        "ostype": "l26",
        "cores": args.cores,
        "sockets": 1,
        "cpu": DEFAULT_CPU,
        "memory": args.memory,
        "balloon": args.balloon,
        "agent": "enabled=1",
        "scsihw": "virtio-scsi-single",
        # import-from turns the downloaded cloud image into this VM's disk.
        # qcow2 is mandatory: 'dir' storage cannot snapshot raw, and the whole
        # save-rotation design rests on snapshots.
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
    # VM that is neither a usable template nor obviously junk, and the next
    # run picks a different vmid rather than noticing it.
    try:

        # The resize fires immediately after a 25 GB import, while the storage is
        # still flushing, and PVE's qemu-img wrapper has its own timeout:
        #   qemu-img resize '--preallocation=metadata' ... failed: got timeout
        # Observed on 2026-08-27, then succeeded in 3s on a manual retry, so it is
        # load, not a real failure. Retrying beats failing a build that has already
        # copied 25 GB.
        resize_disk(pve, vmid)

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

    log("\nrecord DF_TEMPLATE_VMID=%s in .env" % vmid)
    return vmid


def pool_address_holder(pve, ip, exclude_vmid=None):
    """The vmid in our pool already configured with `ip`, or None.

    Only sees our own pool: every other guest on the host is outside it and
    invisible to this token (see pve.node_memory()'s note). So this catches
    "two df-automation VMs, one address", which is the collision that nearly
    happened on 2026-09-12, and cannot catch a clash with a guest we do not
    own. home-lab's inventory/ips.yaml remains the authority for that, which
    is why allocation there is a prerequisite rather than a formality.

    Read errors are deliberately not swallowed: a check that quietly skips a
    VM it could not read would report "free" without having looked.
    """
    for member in pve.pool_members():
        if member.get("type") != "qemu":
            continue
        vmid = member.get("vmid")
        if vmid is None or (exclude_vmid is not None
                            and int(vmid) == int(exclude_vmid)):
            continue
        config = pve.get(pve.vm_path(vmid, "/config")) or {}
        ipconfig = config.get("ipconfig0") or ""
        for field in ipconfig.split(","):
            field = field.strip()
            if field.startswith("ip=") and field[3:].split("/")[0] == ip:
                return vmid
    return None


def cmd_clone(pve, args):
    template_vmid = args.template or pve.env.get("DF_TEMPLATE_VMID")
    if not template_vmid:
        raise PVEError("no template vmid: pass --template or set "
                       "DF_TEMPLATE_VMID in .env")

    # Resolve and check the address BEFORE the clone, not after it: a clone
    # that succeeds and then refuses to configure leaves a half-made VM to
    # clean up by hand.
    ipconfig, dns = guest_address(pve.env, args.ip_var)
    ip = ipconfig.split(",")[0][len("ip="):].split("/")[0]
    holder = pool_address_holder(pve, ip)
    if holder is not None:
        raise PVEError(
            "%s's address is already configured on vm %s in pool '%s'.\n"
            "  Refusing to clone: two guests on one address takes down the\n"
            "  one that already works. Check which .env key you meant."
            % (args.ip_var, holder, pve.pool))

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
    pve.wait_task(upid, "clone", timeout=3600)

    # Assign the address now, before the VM is ever started, so it comes up
    # on it directly rather than taking a DHCP lease and switching later.
    log("assigning address: %s, dns %s" % (ipconfig, dns))
    pve.put(pve.vm_path(newid, "/config"),
            {"ipconfig0": ipconfig, "nameserver": dns})

    log("done. record the new vmid in .env (DF_VMID for the fort,"
        " OPENCLAW_VMID for the agent host): %s" % newid)
    return newid


def cmd_set_memory(pve, args):
    """Resize a stopped VM's memory. Refuses while it is running.

    A live `memory` change on a running guest is applied through the balloon
    driver and does not move the ceiling, so a "success" there would be
    misleading. Requiring the VM to be stopped keeps the reported result and
    the actual result the same thing.
    """
    vmid = args.vmid or pve.env.get("DF_VMID")
    if not vmid:
        raise PVEError("no vmid: pass --vmid or set DF_VMID in .env")

    status = pve.get(pve.vm_path(vmid, "/status/current"))
    if status.get("status") != "stopped":
        raise PVEError("vm %s is %s -- stop it before resizing memory"
                       % (vmid, status.get("status")))

    cfg = pve.get(pve.vm_path(vmid, "/config"))
    log("vm %s: memory %s -> %s MB, balloon %s -> %s MB"
        % (vmid, cfg.get("memory"), args.memory,
           cfg.get("balloon"), args.balloon))

    if args.balloon > args.memory:
        raise PVEError("balloon (%s) cannot exceed memory (%s)"
                       % (args.balloon, args.memory))

    pve.put(pve.vm_path(vmid, "/config"),
            {"memory": args.memory, "balloon": args.balloon})

    after = pve.get(pve.vm_path(vmid, "/config"))
    if int(after.get("memory", 0)) != args.memory:
        raise PVEError("config still reads memory=%s after the write"
                       % after.get("memory"))
    log("confirmed by read-back: memory=%s balloon=%s"
        % (after.get("memory"), after.get("balloon")))


def cmd_set_onboot(pve, args):
    """Set whether a VM starts automatically when the host boots.

    Unlike memory, `onboot` is a scheduling flag, not a hardware allocation --
    it applies live and needs no stopped VM. VM 104 shipped without it: the
    2026-08-27 host reboot brought Proxmox back but left the VM itself
    stopped, discovered only because 'verify' was run rather than assumed. A
    VM the host doesn't restart is a VM that doesn't survive its own crash.
    """
    vmid = args.vmid or pve.env.get("DF_VMID")
    if not vmid:
        raise PVEError("no vmid: pass --vmid or set DF_VMID in .env")

    want = 1 if args.enable else 0
    cfg = pve.get(pve.vm_path(vmid, "/config"))
    log("vm %s: onboot %s -> %s" % (vmid, cfg.get("onboot", 0), want))

    pve.put(pve.vm_path(vmid, "/config"), {"onboot": want})

    after = pve.get(pve.vm_path(vmid, "/config"))
    if int(after.get("onboot", 0)) != want:
        raise PVEError("config still reads onboot=%s after the write"
                       % after.get("onboot"))
    log("confirmed by read-back: onboot=%s" % after.get("onboot"))


def cmd_set_cpu(pve, args):
    """Change a VM's configured CPU type. Like onboot, this applies live (no
    stopped-VM requirement) but the guest only actually sees the new CPUID
    after its next cold stop/start -- a running VM keeps presenting whatever
    type it booted with. decisions/DECISIONS.md 2026-08-28: moving off
    'host' is accepted in principle (fixes cross-host migration, negligible
    loss for DF's workload) but was never applied; this is the apply step,
    still gated on the user's own go-ahead per this repo's live-infra rule
    since it sits dormant until a cold boot the fort's uptime shouldn't be
    interrupted for casually.
    """
    vmid = args.vmid or pve.env.get("DF_VMID")
    if not vmid:
        raise PVEError("no vmid: pass --vmid or set DF_VMID in .env")

    cfg = pve.get(pve.vm_path(vmid, "/config"))
    log("vm %s: cpu %s -> %s (takes effect on next cold stop/start)"
        % (vmid, cfg.get("cpu", "(unset, defaults to 'host')"), args.cpu_type))

    pve.put(pve.vm_path(vmid, "/config"), {"cpu": args.cpu_type})

    after = pve.get(pve.vm_path(vmid, "/config"))
    if after.get("cpu") != args.cpu_type:
        raise PVEError("config still reads cpu=%s after the write"
                       % after.get("cpu"))
    log("confirmed by read-back: cpu=%s" % after.get("cpu"))


def cmd_snapshot(pve, args):
    """Create a named Proxmox snapshot, as a rollback point before risky work.

    Added 2026-09-08 for live-testing the untested title-to-embark input
    sequence in research/2026-09-08-embark-automation.md against a running
    VM -- a state a bad simulated key could plausibly corrupt.
    """
    vmid = args.vmid or pve.env.get("DF_VMID")
    if not vmid:
        raise PVEError("no vmid: pass --vmid or set DF_VMID in .env")

    log("vm %s: creating snapshot '%s'" % (vmid, args.name))
    upid = pve.post(pve.vm_path(vmid, "/snapshot"),
                    {"snapname": args.name, "description": args.description or ""})
    pve.wait_task(upid, "snapshot %s" % args.name, timeout=300)

    snaps = pve.get(pve.vm_path(vmid, "/snapshot"))
    if not any(s.get("name") == args.name for s in snaps or []):
        raise PVEError("snapshot task finished but '%s' is not listed" % args.name)
    log("confirmed: snapshot '%s' exists" % args.name)


def cmd_rollback(pve, args):
    """Roll a VM back to a named snapshot."""
    vmid = args.vmid or pve.env.get("DF_VMID")
    if not vmid:
        raise PVEError("no vmid: pass --vmid or set DF_VMID in .env")

    snaps = pve.get(pve.vm_path(vmid, "/snapshot"))
    if not any(s.get("name") == args.name for s in snaps or []):
        names = [s.get("name") for s in snaps or [] if s.get("name") != "current"]
        raise PVEError("no snapshot '%s' on vm %s -- have: %s"
                       % (args.name, vmid, ", ".join(names) or "(none)"))

    log("vm %s: rolling back to snapshot '%s'" % (vmid, args.name))
    upid = pve.post(pve.vm_path(vmid, "/snapshot/%s/rollback" % quote(args.name, safe="")))
    pve.wait_task(upid, "rollback %s" % args.name, timeout=300)
    log("rollback finished")


def cmd_shutdown(pve, args):
    """Gracefully shut down a running VM (ACPI signal, guest OS halts on its
    own), the missing counterpart to cmd_start. Handles only the VM/QEMU
    level -- whatever is running inside the guest (DF, its own quicksave-
    before-stop discipline) is the caller's job to have already stopped
    cleanly first. Needed to apply any VM-level config change (e.g. 'cpu')
    that only takes effect on the next cold stop/start.
    """
    vmid = args.vmid or pve.env.get("DF_VMID")
    if not vmid:
        raise PVEError("no vmid: pass --vmid or set DF_VMID in .env")

    status = pve.get(pve.vm_path(vmid, "/status/current"))
    if status.get("status") == "stopped":
        log("vm %s is already stopped" % vmid)
        return

    log("vm %s: shutting down (ACPI, timeout %ss)" % (vmid, args.timeout))
    upid = pve.post(pve.vm_path(vmid, "/status/shutdown"),
                    {"timeout": args.timeout})
    pve.wait_task(upid, "shutdown vm %s" % vmid, timeout=args.timeout + 60)

    after = pve.get(pve.vm_path(vmid, "/status/current"))
    log("vm %s is now %s" % (vmid, after.get("status")))
    if after.get("status") != "stopped":
        raise PVEError("shutdown task finished but the vm is %s"
                       % after.get("status"))


def cmd_start(pve, args):
    """Start a VM, refusing if the host cannot currently back it.

    The standing rule from 2026-08-26: **read /nodes/<node>/status before
    starting.** The other VMs on this host are outside our pool and invisible
    to us, and this host's free memory moved 13.7 -> 4.8 -> 9.0 GB used inside
    two days. Gate on `available`, never on `free`.
    """
    vmid = args.vmid or pve.env.get("DF_VMID")
    if not vmid:
        raise PVEError("no vmid: pass --vmid or set DF_VMID in .env")

    status = pve.get(pve.vm_path(vmid, "/status/current"))
    if status.get("status") == "running":
        log("vm %s is already running" % vmid)
        return

    cfg = pve.get(pve.vm_path(vmid, "/config"))
    want_gib = int(cfg.get("memory", 0)) / 1024.0
    total, used, free, available = pve.node_memory()
    log("host: %.1f GiB available (%.1f used, %.1f free of %.1f total)"
        % (available, used, free, total))
    log("vm %s wants up to %.1f GiB" % (vmid, want_gib))

    headroom = available - want_gib
    if headroom < args.min_headroom and not args.force:
        raise PVEError(
            "only %.1f GiB would be left after starting (minimum %.1f). "
            "Free host memory, lower the VM's ceiling, or pass --force if "
            "you accept the risk." % (headroom, args.min_headroom))
    log("headroom after start: %.1f GiB" % headroom)

    upid = pve.post(pve.vm_path(vmid, "/status/start"), {})
    pve.wait_task(upid, "start vm %s" % vmid, timeout=300)

    after = pve.get(pve.vm_path(vmid, "/status/current"))
    log("vm %s is now %s" % (vmid, after.get("status")))
    if after.get("status") != "running":
        raise PVEError("start task finished but the vm is %s"
                       % after.get("status"))



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="host memory, next vmid, pool contents")
    sub.add_parser("fetch-image", help="download the cloud image into 'import'")

    build = sub.add_parser("build-template",
                           help="cloud image -> VM -> template")
    build.add_argument("--vmid", type=int)
    build.add_argument("--memory", type=int, default=DEFAULT_MEMORY)
    build.add_argument("--balloon", type=int, default=DEFAULT_BALLOON)
    build.add_argument("--cores", type=int, default=DEFAULT_CORES)
    build.add_argument("--ciuser", default="df")
    build.add_argument("--keep-failed", action="store_true",
                       help="on failure, leave the half-built VM on the host"
                            " for inspection instead of destroying it")

    clone = sub.add_parser("clone", help="clone the template into a VM")
    clone.add_argument("--template", type=int)
    clone.add_argument("--vmid", type=int)
    clone.add_argument("--name", default="df-fortress")
    clone.add_argument("--full", action="store_true",
                       help="full clone -- no dependency on the template")
    clone.add_argument("--ip-var", default="DF_VM_IP",
                       help="which .env key holds this guest's static address"
                            " (default DF_VM_IP, the fort; OPENCLAW_VM_IP is"
                            " the agent host)")

    setmem = sub.add_parser("set-memory",
                            help="resize a stopped VM's memory ceiling")
    setmem.add_argument("--vmid", type=int)
    setmem.add_argument("--memory", type=int, required=True)
    setmem.add_argument("--balloon", type=int, default=DEFAULT_BALLOON)

    onboot = sub.add_parser("set-onboot",
                            help="start (or not) the VM when the host boots")
    onboot.add_argument("--vmid", type=int)
    group = onboot.add_mutually_exclusive_group(required=True)
    group.add_argument("--enable", action="store_true", dest="enable",
                       help="start this VM automatically on host boot")
    group.add_argument("--disable", action="store_false", dest="enable",
                       help="do not start this VM automatically on host boot")

    setcpu = sub.add_parser("set-cpu",
                            help="change a VM's CPU type (effective on its"
                                 " next cold stop/start, not immediately)")
    setcpu.add_argument("--vmid", type=int)
    setcpu.add_argument("--cpu-type", default=DEFAULT_CPU,
                        help="default %r" % DEFAULT_CPU)

    snap = sub.add_parser("snapshot", help="create a named snapshot")
    snap.add_argument("--vmid", type=int)
    snap.add_argument("--name", required=True)
    snap.add_argument("--description")

    rollback = sub.add_parser("rollback", help="roll back to a named snapshot")
    rollback.add_argument("--vmid", type=int)
    rollback.add_argument("--name", required=True)

    shutdown = sub.add_parser("shutdown",
                              help="gracefully shut down a running VM (ACPI)")
    shutdown.add_argument("--vmid", type=int)
    shutdown.add_argument("--timeout", type=int, default=60,
                          help="seconds to wait for ACPI shutdown, default 60")

    start = sub.add_parser("start", help="start a VM, gated on host memory")
    start.add_argument("--vmid", type=int)
    start.add_argument("--min-headroom", type=float, default=1.0,
                       help="GiB that must remain available after starting")
    start.add_argument("--force", action="store_true",
                       help="start even if the headroom gate fails")

    args = parser.parse_args()
    pve = PVE()
    handler = {
        "status": cmd_status,
        "fetch-image": cmd_fetch_image,
        "build-template": cmd_build_template,
        "clone": cmd_clone,
        "set-memory": cmd_set_memory,
        "set-onboot": cmd_set_onboot,
        "set-cpu": cmd_set_cpu,
        "snapshot": cmd_snapshot,
        "rollback": cmd_rollback,
        "shutdown": cmd_shutdown,
        "start": cmd_start,
    }[args.command]
    try:
        handler(pve, args)
    except PVEError as exc:
        log("FAILED: %s" % exc)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
