"""Thin Proxmox API client for df-overseer.

Python rather than bash on purpose: Git Bash's MSYS layer rewrites POSIX-looking
arguments into Windows paths ('/var/lib/vz/...' became 'C:/Program Files/Git/
var/lib/vz/...'), which silently corrupts any storage path or 'import-from'
value passed on a command line.

Credentials come from the repo-root .env, which is gitignored. Nothing in this
file identifies the host -- and as of 2026-09-08 no default value in it
names a real pool, storage or node either; those must all come from .env.
"""

import os
import sys
import time

import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env(path=None):
    """Read the repo-root .env into a dict. Handles quoted values.

    The Proxmox password contains '$E'; bash expanded that to nothing when the
    file was sourced, so values are single-quoted in .env. Strip the quotes
    here rather than relying on a shell.
    """
    path = path or os.path.join(REPO_ROOT, ".env")
    env = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            env[key.strip()] = value
    return env


def _retry_policy():
    """Retry transient failures. Never retry a POST.

    Added 2026-09-08. Before it, every call was a single unguarded attempt,
    and wait_task polls every 2s: fetch-image and clone pass timeout=3600, so
    roughly 1800 consecutive GETs, any one of which aborted the whole build.
    On a cluster with no QDevice that is the likeliest way a rebuild dies.

    This leans on urllib3's DEFAULT_ALLOWED_METHODS, which excludes POST.
    That is exactly right here and is not incidental: this client's POSTs
    create, clone, start and stop VMs, so a replayed POST after a timeout
    could create two VMs. The GETs are what the polling loop is made of.
    **Do not add POST to allowed_methods.**

    500 is deliberately not in status_forcelist. PVE returns it for real
    permission and quorum faults, which are persistent, and retrying those
    just turns a clear error into a slow one.
    """
    policy = dict(
        total=5,
        backoff_factor=1.0,
        status_forcelist=(502, 503, 504),
        # We raise on status ourselves in request(), with the body attached.
        raise_on_status=False,
    )
    try:
        return Retry(backoff_jitter=0.5, **policy)
    except TypeError:
        # backoff_jitter landed in urllib3 2.0; without it, retries from
        # several callers can still align, which is survivable here.
        return Retry(**policy)


class PVEError(RuntimeError):
    pass


class PVE:
    def __init__(self, env=None):
        self.env = env or load_env()
        self.host = self.env["PVE_HOST"]
        self.port = self.env.get("PVE_PORT", "8006")
        self.node = self.env["PVE_NODE"]
        # Required, deliberately. These carried hardcoded defaults until
        # 2026-09-08; both names stopped existing when the estate was rebuilt,
        # so the defaults resolved to nothing and the first symptom was an
        # error that read like a permissions fault. Fail loudly at
        # construction instead of resolving to a dead name.
        self.pool = self._require("PVE_POOL")
        self.storage = self._require("PVE_STORAGE")
        self.base = "https://%s:%s/api2/json" % (self.host, self.port)
        self.verify = self.env.get("PVE_TLS_VERIFY", "false").lower() not in (
            "false", "0", "no", ""
        )
        if not self.verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.session = requests.Session()
        self.session.mount("https://", HTTPAdapter(max_retries=_retry_policy()))
        self.session.headers["Authorization"] = "PVEAPIToken=%s=%s" % (
            self.env["PVE_TOKEN_ID"],
            self.env["PVE_TOKEN_SECRET"],
        )

    def _require(self, key):
        """Read a setting that has no safe default, or refuse to construct."""
        value = self.env.get(key, "").strip()
        if not value:
            raise PVEError(
                "%s is not set in .env. It has no default on purpose: a dead "
                "default reads as a permissions error, not a config error. "
                "Set it to the name this project's own pool or storage "
                "actually uses on your cluster." % key
            )
        return value

    # --- transport -------------------------------------------------------

    def request(self, method, path, **kwargs):
        url = self.base + path
        resp = self.session.request(
            method, url, verify=self.verify, timeout=60, **kwargs
        )
        if resp.status_code >= 400:
            hint = ""
            if resp.status_code in (403, 500):
                # Both repos predicted this misdiagnosis in writing before it
                # could happen: an inquorate node makes /etc/pve read-only and
                # every write fails in a way that reads exactly like an ACL
                # fault. No retry policy fixes it, so say so at the error.
                hint = ("\n  note: this can also mean the cluster is inquorate."
                        " Check `pvecm status` before assuming a permissions problem.")
            raise PVEError("%s %s -> %s %s%s" % (method, path, resp.status_code,
                                                 resp.text.strip(), hint))
        if not resp.text:
            return None
        return resp.json().get("data")

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, data=None):
        return self.request("POST", path, data=data or {})

    def put(self, path, data=None):
        return self.request("PUT", path, data=data or {})

    def delete(self, path):
        return self.request("DELETE", path)

    # --- node/vm helpers -------------------------------------------------

    def node_path(self, suffix=""):
        return "/nodes/%s%s" % (self.node, suffix)

    def vm_path(self, vmid, suffix=""):
        return "/nodes/%s/qemu/%s%s" % (self.node, vmid, suffix)

    def next_vmid(self):
        return int(self.get("/cluster/nextid"))

    def pool_members(self):
        return self.get("/pools/%s" % self.pool).get("members", [])

    def node_memory(self):
        """(total, used, free, available) in GiB, read live.

        **Size and gate on `available`, never on `free`.** `free` excludes page
        cache and reclaimable slab, so it collapses during any large file copy
        and reads as a memory shortage that isn't one -- pushing a 596 MB image
        and a 25 GB disk copy through this host on 2026-08-27 took `free` from
        5.5 to 1.7 GiB while `available` stayed at 5.4. `available` is the
        kernel's own estimate of what a new workload can obtain.

        Still read it live every time: the other VMs on this host are outside
        our pool and invisible to us.
        """
        mem = self.get(self.node_path("/status"))["memory"]
        gib = lambda n: round(n / float(2 ** 30), 1)
        # 'available' predates PVE 9 but fall back rather than KeyError on a
        # host that doesn't report it.
        available = mem.get("available", mem["free"])
        return gib(mem["total"]), gib(mem["used"]), gib(mem["free"]), gib(available)

    def wait_task(self, upid, label="task", timeout=1800, poll=2):
        """Block until a task finishes. Raises unless it exits OK."""
        if not upid:
            return None
        path = self.node_path("/tasks/%s/status" % upid)
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self.get(path)
            if status["status"] == "stopped":
                exit_status = status.get("exitstatus", "")
                if exit_status != "OK":
                    log = self.get(self.node_path("/tasks/%s/log" % upid))
                    tail = "\n".join(entry["t"] for entry in (log or [])[-15:])
                    raise PVEError("%s failed: %s\n%s" % (label, exit_status, tail))
                return exit_status
            time.sleep(poll)
        raise PVEError("%s timed out after %ss" % (label, timeout))


def log(msg):
    """Print one line, tolerating text the console's codepage can't show.

    Found live 2026-09-12 relaying real DF gamelog text (df-overseer-diff's
    recent-combat output) through a Windows console pinned to cp1252:
    sys.stdout.write raised UnicodeEncodeError on a single unencodable
    character and crashed the whole command after most of the output had
    already printed. DF text is not guaranteed to be cp1252-safe (it can
    carry arbitrary Unicode from dwarf/creature names), so encode explicitly
    against the stream's own reported encoding with errors='replace' rather
    than letting write() choose how to fail.
    """
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    line = (msg + "\n").encode(encoding, errors="replace").decode(encoding)
    sys.stdout.write(line)
    sys.stdout.flush()
