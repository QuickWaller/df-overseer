"""Build the df-overseer VM template from the Ubuntu cloud image, and clone it.

    python scripts/provision_vm.py status
    python scripts/provision_vm.py fetch-image
    python scripts/provision_vm.py build-template [--vmid N] [--memory 6144]
    python scripts/provision_vm.py clone [--name df-fortress] [--full]

The template is built from scratch out of a cloud image we downloaded, on
purpose: an earlier VM here was a linked clone of a template outside our pool,
invisible to us and able to take our VM with it if deleted.

Nothing host-specific is hardcoded -- it all comes from .env (gitignored).
"""

import argparse
import os
import sys
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
        log("NOTE: %d MB requested exceeds free memory. The template is never"
            " started, so building is safe -- but re-check before booting a"
            " clone." % args.memory)

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

    log("resizing scsi0 to %s" % DISK_SIZE)
    upid = pve.put(pve.vm_path(vmid, "/resize"),
                   {"disk": "scsi0", "size": DISK_SIZE})
    pve.wait_task(upid, "resize")

    log("converting %s to a template" % vmid)
    upid = pve.post(pve.vm_path(vmid, "/template"))
    pve.wait_task(upid, "template conversion")

    config = pve.get(pve.vm_path(vmid, "/config"))
    log("done. template %s:" % vmid)
    for key in ("name", "template", "memory", "balloon", "cores", "scsi0",
                "ide2", "net0", "ciuser", "ipconfig0"):
        if key in config:
            log("  %-9s %s" % (key, config[key]))
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
    log("done. record DF_VMID=%s in .env" % newid)
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
