"""Build the df-overseer VM template from the Ubuntu cloud image, and clone it.

    python scripts/provision_vm.py status
    python scripts/provision_vm.py fetch-image
    python scripts/provision_vm.py build-template [--vmid N] [--memory 6144]
                                                  [--no-bake]
    python scripts/provision_vm.py clone [--name df-fortress] [--full]

The template is built from scratch out of a cloud image we downloaded, on
purpose: an earlier VM here was a linked clone of a template outside our pool,
invisible to us and able to take our VM with it if deleted.

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
CLOUD_IMAGE = "noble-server-cloudimg-amd64.qcow2"
CLOUD_IMAGE_URL = ("https://cloud-images.ubuntu.com/noble/current/"
                   "noble-server-cloudimg-amd64.img")
# 'import-from' will only read a volume whose content type is 'images' or
# 'import' -- an 'iso' volume is rejected outright, even though the file is
# identical. download-url can write straight into 'import', so the image is
# fetched there rather than moved.
IMAGE_CONTENT = "import"
TEMPLATE_NAME = "df-overseer-noble-template"
DISK_SIZE = "25G"
BRIDGE = "vmbr0"

# A router DHCP reservation binds to a MAC, and Proxmox rolls a fresh random
# one every time a NIC is created -- including on *clone*, which is why this is
# applied in cmd_clone and not in the template. Without it, deleting and
# rebuilding a VM silently orphans its reservation: the new VM pulls a random
# pool address and the symptom reads as "the static IP stopped working".
# Deriving the MAC from the vmid makes a rebuild reproduce the same address.
# BC:24:11 is Proxmox's own OUI, kept to stay out of other vendors' space.
MAC_PREFIX = "BC:24:11"
# VMs whose MAC predates this scheme and is already reserved on the router.
# Pinning the existing value is what makes a rebuild land on the reservation
# that is live today, so these entries must not be "tidied up" to match the
# derived scheme without re-reserving on the router first.
MAC_OVERRIDES = {
    104: "<reserved-mac>",  # df-fortress, reserved -> <df-vm-ip>
}

# Packages baked into the template while it is booted, before it is sealed.
# qemu-guest-agent is the one that matters: 'agent: enabled=1' only opens the
# virtio channel on the Proxmox side, and without the package in the guest
# every /agent/* call returns 500. Proxmox's native cloud-init fields cannot
# install a package -- that needs cicustom, which needs a snippets volume on
# the host filesystem, which has no API upload path. Booting the VM once and
# installing over SSH is the only route that needs no human step.
BAKE_PACKAGES = ["qemu-guest-agent"]
# The bake actually boots the VM, so the template's *configured* size is not
# what the host has to find -- an apt install needs nothing like it. Booting at
# the configured size would put a 6 GB ask on a host that has had ~3 GiB free
# all week, and fail the build for no reason. Restored before conversion.
BAKE_MEMORY = 2048

# 6 GB max with a 2 GB balloon floor: the user's call on 2026-08-26 with ~5.5 GB
# available on the host. KVM only backs pages the guest touches, so idle DF sits
# far below this; the worldgen spike is the real peak. Memory is a one-line
# change on a stopped VM -- re-check node_memory()'s *available* before booting.
DEFAULT_MEMORY = 6144
DEFAULT_BALLOON = 2048
DEFAULT_CORES = 4


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


def mac_for_vmid(vmid):
    """Stable MAC for a vmid, so a rebuilt VM keeps its DHCP reservation.

    Overrides win: a VM already reserved on the router keeps the MAC that
    reservation names, whatever the derived value would have been.
    """
    vmid = int(vmid)
    if vmid in MAC_OVERRIDES:
        return MAC_OVERRIDES[vmid]
    if not 0 <= vmid <= 0xFFFF:
        raise PVEError("vmid %s out of range for a derived MAC" % vmid)
    return "%s:00:%02X:%02X" % (MAC_PREFIX, (vmid >> 8) & 0xFF, vmid & 0xFF)


def build_address(env):
    """(ipconfig0 value, ip) for the template build, from .env.

    The bake has to SSH into the VM before the guest agent exists, so the API
    cannot be asked where the VM is -- that is the very capability being
    installed. A static address for the build breaks that circularity. It is
    used only while the template is being sealed and is reset to dhcp before
    conversion, so nothing clones with it.

    DF_BUILD_GW defaults to .1 of the same /24, which is right on essentially
    every home network and wrong loudly rather than silently if it is not.
    """
    cidr = env.get("DF_BUILD_IP")
    if not cidr:
        raise PVEError(
            "DF_BUILD_IP is not set in .env.\n"
            "  The template bake needs one free address to reach the VM on"
            " before the guest agent exists.\n"
            "  Pick any address outside the router's DHCP pool, e.g."
            " DF_BUILD_IP=<build-ip>/24\n"
            "  It is held only while the template is built, then released."
        )
    if "/" not in cidr:
        raise PVEError("DF_BUILD_IP must include a prefix, e.g. %s/24" % cidr)
    ip = cidr.split("/")[0]
    gw = env.get("DF_BUILD_GW") or ".".join(ip.split(".")[:3] + ["1"])
    # A DHCP guest is handed DNS by the router; a static one is not. Without an
    # explicit nameserver the guest boots with no resolver and the bake fails
    # on apt-get's first name lookup, which reads as a network fault rather
    # than a missing setting. The gateway answers DNS on essentially every
    # home router, and DF_BUILD_DNS overrides it where it does not.
    dns = env.get("DF_BUILD_DNS") or gw
    return "ip=%s,gw=%s" % (cidr, gw), ip, dns


def ssh_guest(env, ip, command, timeout=120, check=True):
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
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if check and proc.returncode != 0:
        raise PVEError("ssh failed (%s): %s"
                       % (proc.returncode, (proc.stderr or proc.stdout).strip()))
    return proc


def wait_for_ssh(env, ip, timeout=300, poll=5):
    log("waiting for ssh on %s (up to %ss)" % (ip, timeout))
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            proc = ssh_guest(env, ip, "true", timeout=20, check=False)
            if proc.returncode == 0:
                log("  ssh up after %ds" % (timeout - int(deadline - time.time())))
                return True
            last = (proc.stderr or proc.stdout).strip()
        except (subprocess.TimeoutExpired, PVEError) as exc:
            last = str(exc)
        time.sleep(poll)
    raise PVEError("no ssh on %s after %ss. last error: %s" % (ip, timeout, last))


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


def bake_template(pve, vmid, args):
    """Boot the VM once, install the guest packages, and seal it again.

    Sealing is the part that is easy to get wrong: a template cloned from a
    booted VM carries that VM's cloud-init instance-id, machine-id and SSH
    host keys, so every clone comes up as a duplicate of it. 'cloud-init clean'
    plus removing those files makes each clone re-run first boot as itself.
    """
    ipconfig, ip, dns = build_address(pve.env)
    log("baking %s: %s, dns %s, booting at %d MB"
        % (", ".join(BAKE_PACKAGES), ipconfig, dns, BAKE_MEMORY))
    mac = mac_for_vmid(vmid)
    pve.put(pve.vm_path(vmid, "/config"), {
        "net0": "virtio=%s,bridge=%s" % (mac, BRIDGE),
        "ipconfig0": ipconfig,
        "nameserver": dns,
        "memory": BAKE_MEMORY,
        "balloon": 0,
    })

    log("starting %s for the bake" % vmid)
    pve.wait_task(pve.post(pve.vm_path(vmid, "/status/start")), "start")
    try:
        wait_for_ssh(pve.env, ip)

        log("waiting for cloud-init to finish")
        ssh_guest(pve.env, ip, "sudo cloud-init status --wait", timeout=600,
                  check=False)

        log("installing: %s" % " ".join(BAKE_PACKAGES))
        ssh_guest(pve.env, ip,
                  "sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq && "
                  "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "
                  + " ".join(BAKE_PACKAGES), timeout=900)
        ssh_guest(pve.env, ip,
                  "sudo systemctl enable --now qemu-guest-agent", timeout=120)

        # Prove the channel end to end *now*, while there is still a running
        # VM to prove it against. After conversion the next chance is a clone,
        # and a template that silently lacks a working agent is exactly the
        # failure this whole change exists to stop.
        log("verifying the agent answers over the virtio channel")
        # ping is a *command*, and the command-style agent endpoints are POST;
        # only the info-style ones (network-get-interfaces, get-osinfo, ...)
        # answer GET. A GET here returns 501 "not implemented", which reads as
        # a missing agent rather than a wrong verb. Verified 2026-08-27.
        pinged = pve.post(pve.vm_path(vmid, "/agent/ping"))
        log("  /agent/ping -> %s" % ("ok" if pinged is not None else pinged))
        ifaces = pve.get(pve.vm_path(vmid, "/agent/network-get-interfaces"))
        addrs = [a.get("ip-address")
                 for i in (ifaces or {}).get("result", [])
                 for a in i.get("ip-addresses", [])
                 if a.get("ip-address-type") == "ipv4"]
        log("  agent reports ipv4: %s" % ", ".join(addrs))
        if ip not in addrs:
            raise PVEError("agent did not report the build address %s" % ip)

        log("sealing: cloud-init clean, machine-id and host keys removed")
        ssh_guest(pve.env, ip,
                  "sudo cloud-init clean --logs --seed && "
                  "sudo rm -f /etc/ssh/ssh_host_* && "
                  "sudo truncate -s 0 /etc/machine-id && "
                  "sudo rm -f /var/lib/dbus/machine-id && "
                  "sync", timeout=120)

        # Hard stop, deliberately. Sealing removes the machine-id systemd needs
        # to reach dbus, so a `systemctl poweroff` issued *after* it never
        # completes and the VM sits running until the wait times out (observed
        # 2026-08-27, hidden at the time by check=False on that call). Sealing
        # has to happen while the VM is up, so the guest cannot be the thing
        # that shuts it down. The `sync` above is what makes this safe: the
        # only writes outstanding are the seal's own handful of small changes.
        log("stopping %s (hard, see comment: the seal breaks graceful shutdown)"
            % vmid)
        pve.wait_task(pve.post(pve.vm_path(vmid, "/status/stop")), "stop")
        wait_for_status(pve, vmid, "stopped", timeout=180)
    except Exception:
        log("bake failed at %s; the caller decides whether %s survives it"
            % (ip, vmid))
        raise
    finally:
        # Never let the build address reach a clone, on the failure path either.
        pve.put(pve.vm_path(vmid, "/config"), {
            "ipconfig0": "ip=dhcp",
            "memory": args.memory,
            "balloon": args.balloon,
            # Drop the build nameserver rather than blanking it: a clone on
            # dhcp should take the router's resolver, not inherit ours.
            "delete": "nameserver",
        })
        log("build address released; ipconfig0 dhcp, memory back to %d/%d MB"
            % (args.memory, args.balloon))


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

    Requires ssd_storage to have the 'import' content type enabled
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
            " only ever booted at %d MB for the bake, so building is still"
            " safe -- but re-check before booting a clone."
            % (args.memory, BAKE_MEMORY))
    if not args.no_bake and available < BAKE_MEMORY / 1024.0:
        raise PVEError(
            "only %.1f GiB available and the bake needs to boot the VM at %d MB."
            " Free memory on the host, or build with --no-bake and install the"
            " guest agent by hand." % (available, BAKE_MEMORY))

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

        if args.no_bake:
            log("skipping the bake (--no-bake): this template will clone VMs with"
                " no guest agent, and the API will not be able to report their IP")
        else:
            bake_template(pve, vmid, args)

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


def cmd_clone(pve, args):
    template_vmid = args.template or pve.env.get("DF_TEMPLATE_VMID")
    if not template_vmid:
        raise PVEError("no template vmid: pass --template or set "
                       "DF_TEMPLATE_VMID in .env")
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

    # The clone came up with a randomly generated MAC. Overwrite it before the
    # VM is ever started, so it takes its first DHCP lease on the pinned
    # address rather than burning a random one and switching later.
    mac = mac_for_vmid(newid)
    log("pinning net0 MAC to %s (rebuild-safe DHCP reservation)" % mac)
    pve.put(pve.vm_path(newid, "/config"),
            {"net0": "virtio=%s,bridge=%s" % (mac, BRIDGE)})

    log("done. record DF_VMID=%s in .env" % newid)
    log("  reserve %s -> this VM's address on the router" % mac)
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
    build.add_argument("--no-bake", action="store_true",
                       help="skip booting the VM to install the guest agent"
                            " (clones will have no working /agent/* API)")

    clone = sub.add_parser("clone", help="clone the template into a VM")
    clone.add_argument("--template", type=int)
    clone.add_argument("--vmid", type=int)
    clone.add_argument("--name", default="df-fortress")
    clone.add_argument("--full", action="store_true",
                       help="full clone -- no dependency on the template")

    setmem = sub.add_parser("set-memory",
                            help="resize a stopped VM's memory ceiling")
    setmem.add_argument("--vmid", type=int)
    setmem.add_argument("--memory", type=int, required=True)
    setmem.add_argument("--balloon", type=int, default=DEFAULT_BALLOON)

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
        "start": cmd_start,
    }[args.command]
    try:
        handler(pve, args)
    except PVEError as exc:
        log("FAILED: %s" % exc)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
