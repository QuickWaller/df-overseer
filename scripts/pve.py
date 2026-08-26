"""Thin Proxmox API client for df-overseer.

Python rather than bash on purpose: Git Bash's MSYS layer rewrites POSIX-looking
arguments into Windows paths ('/var/lib/vz/...' became 'C:/Program Files/Git/
var/lib/vz/...'), which silently corrupts any storage path or 'import-from'
value passed on a command line.

Credentials come from the repo-root .env, which is gitignored. Nothing in this
file identifies the host.
"""

import os
import sys
import time

import requests
import urllib3

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


class PVEError(RuntimeError):
    pass


class PVE:
    def __init__(self, env=None):
        self.env = env or load_env()
        self.host = self.env["PVE_HOST"]
        self.port = self.env.get("PVE_PORT", "8006")
        self.node = self.env["PVE_NODE"]
        self.pool = self.env.get("PVE_POOL", "df-overseer")
        self.storage = self.env.get("PVE_STORAGE", "ssd_storage")
        self.base = "https://%s:%s/api2/json" % (self.host, self.port)
        self.verify = self.env.get("PVE_TLS_VERIFY", "false").lower() not in (
            "false", "0", "no", ""
        )
        if not self.verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.session = requests.Session()
        self.session.headers["Authorization"] = "PVEAPIToken=%s=%s" % (
            self.env["PVE_TOKEN_ID"],
            self.env["PVE_TOKEN_SECRET"],
        )

    # --- transport -------------------------------------------------------

    def request(self, method, path, **kwargs):
        url = self.base + path
        resp = self.session.request(
            method, url, verify=self.verify, timeout=60, **kwargs
        )
        if resp.status_code >= 400:
            raise PVEError("%s %s -> %s %s" % (method, path, resp.status_code,
                                               resp.text.strip()))
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
        """(total, used, free) in GiB, read live. Never size a VM from a
        number written down earlier -- this host's free memory has moved by
        9 GB inside two days and the other VMs are invisible to us."""
        mem = self.get(self.node_path("/status"))["memory"]
        gib = lambda n: round(n / float(2 ** 30), 1)
        return gib(mem["total"]), gib(mem["used"]), gib(mem["free"])

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
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()
