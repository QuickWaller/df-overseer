"""Shared plumbing for scripts/deploy.py and scripts/drift_check.py.

Loads infra/deploy-manifest.yaml, resolves ${ENV_VAR} placeholders in
destination roots from the repo-root .env (read by key, never printed
whole -- CLAUDE.md), enumerates the concrete committed files a target
carries (honouring `exclude`), and wraps the one way this repo is allowed
to touch a VM: `scripts/vm-ssh.sh <host> '<command>'`.

Nothing in this module runs an ssh command by default at import time. The
`SSHRunner` class is the only thing that shells out for real; tests pass a
`FakeRunner` instead and never touch a real host.
"""
from __future__ import annotations

import fnmatch
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "infra" / "deploy-manifest.yaml"
VM_SSH = REPO_ROOT / "scripts" / "vm-ssh.sh"
ENV_PATH = REPO_ROOT / ".env"


class ManifestError(Exception):
    """The manifest failed to load or a target referenced something missing."""


@dataclass(frozen=True)
class RestartEntry:
    service: str
    risk: str  # "low" | "high"
    why: str = ""

    @property
    def is_high_risk(self) -> bool:
        return self.risk == "high"


@dataclass(frozen=True)
class Target:
    name: str
    host: str  # vm-ssh.sh target: df | openclaw | relay
    destination_root_raw: str  # may contain an ${ENV_VAR} placeholder
    paths: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)
    leave_alone: List[str] = field(default_factory=list)
    restart: List[RestartEntry] = field(default_factory=list)
    post_deploy: List[str] = field(default_factory=list)
    verified: str = ""
    flatten: bool = False
    #: write through `sudo -n` (a destination owned by root, e.g. the relay's web folders)
    sudo: bool = False
    # True only for a target where the destination drops the repo's leading
    # directories and keeps just each file's basename (relay-web: repo path
    # `web/stream/index.html` lands at `<destination_root>/index.html`, not
    # `<destination_root>/web/stream/index.html` -- confirmed live 2026-10-02).
    # Every other target mirrors the repo's relative path under
    # destination_root exactly, which is why this defaults to False rather
    # than being inferred.

    def remote_path(self, repo_path: str) -> str:
        """The path under destination_root this file actually lands at."""
        return repo_path.rsplit("/", 1)[-1] if self.flatten else repo_path

    def destination_root(self, env: Dict[str, str]) -> str:
        """Resolve a ${VAR} placeholder in destination_root_raw against `env`
        (as read_env_file() returns). Raises ManifestError if a placeholder
        is used but the variable is unset or absent -- never silently
        substitutes an empty string into a filesystem path."""
        raw = self.destination_root_raw
        if not raw.startswith("${") or not raw.endswith("}"):
            return raw
        var = raw[2:-1]
        value = env.get(var)
        if not value:
            raise ManifestError(
                f"target '{self.name}' destination_root references ${{{var}}}, "
                f"which is unset or empty in {ENV_PATH}. Set it before deploying "
                f"or checking drift for this target."
            )
        return value


def load_manifest(path: Path = MANIFEST_PATH) -> Dict[str, Target]:
    with path.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    targets_raw = doc.get("targets") or {}
    targets: Dict[str, Target] = {}
    for name, entry in targets_raw.items():
        if not isinstance(entry, dict):
            raise ManifestError(f"target '{name}': expected a mapping, got {type(entry).__name__}")
        host = entry.get("host")
        if host not in ("df", "openclaw", "relay"):
            raise ManifestError(f"target '{name}': host must be one of df/openclaw/relay, got {host!r}")
        restart = [
            RestartEntry(service=r["service"], risk=r.get("risk", "high"), why=r.get("why", ""))
            for r in (entry.get("restart") or [])
        ]
        for r in restart:
            if r.risk not in ("low", "high"):
                raise ManifestError(
                    f"target '{name}' restart entry '{r.service}': risk must be 'low' or 'high', got {r.risk!r}"
                )
        targets[name] = Target(
            name=name,
            host=host,
            destination_root_raw=entry.get("destination_root", ""),
            paths=list(entry.get("paths") or []),
            exclude=list(entry.get("exclude") or []),
            leave_alone=list(entry.get("leave_alone") or []),
            restart=restart,
            post_deploy=list(entry.get("post_deploy") or []),
            verified=entry.get("verified", ""),
            flatten=bool(entry.get("flatten", False)),
            sudo=bool(entry.get("sudo", False)),
        )
    if not targets:
        raise ManifestError(f"{path}: no targets defined")
    return targets


def read_env_file(path: Path = ENV_PATH) -> Dict[str, str]:
    """Read .env as a plain key->value map, by line, never loading it as a
    single blob the caller could print whole. Missing file returns {}
    (every caller must treat an unset key as "not configured", not crash --
    a worktree legitimately has no .env of its own, per CLAUDE.md)."""
    if not path.is_file():
        return {}
    out: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        out[key] = value
    return out


# ---------------------------------------------------------------------------
# git plumbing: committed bytes only, never the working tree
# ---------------------------------------------------------------------------


def git(*args: str, cwd: Path = REPO_ROOT) -> str:
    """Run `git -c core.autocrlf=false <args>` and return stdout, stripped.
    Raises CalledProcessError on failure. The autocrlf override is the one
    CLAUDE.md names explicitly: this workstation's own core.autocrlf=true
    would otherwise ship CRLF and break hash checks against a Linux host."""
    result = subprocess.run(
        ["git", "-c", "core.autocrlf=false", *args],
        cwd=cwd, capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def is_tree_clean(cwd: Path = REPO_ROOT) -> bool:
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=cwd, capture_output=True, text=True, check=True,
    ).stdout
    return status.strip() == ""


def current_commit(cwd: Path = REPO_ROOT) -> str:
    return git("rev-parse", "HEAD", cwd=cwd)


def is_ancestor_of_origin_main(commit: str, cwd: Path = REPO_ROOT) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "origin/main"],
        cwd=cwd, capture_output=True, text=True,
    )
    return result.returncode == 0


def commits_behind_origin_main(commit: str, cwd: Path = REPO_ROOT) -> Optional[int]:
    """How many commits origin/main is ahead of `commit`, or None if `commit`
    is not an ancestor of origin/main (can't meaningfully count)."""
    if not is_ancestor_of_origin_main(commit, cwd=cwd):
        return None
    out = git("rev-list", "--count", f"{commit}..origin/main", cwd=cwd)
    return int(out)


def list_files_at_commit(commit: str, pathspecs: List[str], cwd: Path = REPO_ROOT) -> List[str]:
    """Every tracked file under the given pathspecs, as of `commit`. A
    pathspec may be a directory (expands to everything under it), an exact
    file, or a glob (`scripts/dfhack/*.lua`).

    Plain `git ls-tree -- <glob>` does NOT expand a `*` the way a shell
    would (confirmed empirically: `ls-tree -- "scripts/dfhack/*.lua"`
    returns nothing against this repo's own history, even though the files
    exist) -- it needs the `:(glob)` pathspec magic, or filtering done here
    in Python instead. This does the latter: a glob pathspec lists its
    parent directory and keeps only the matching names, in commit order
    merged with everything else; a plain directory or exact file is passed
    straight to ls-tree, which handles those natively."""
    if not pathspecs:
        return []
    direct: List[str] = []
    glob_specs: List[str] = []
    for spec in pathspecs:
        if any(ch in spec for ch in "*?["):
            glob_specs.append(spec)
        else:
            direct.append(spec)

    results: List[str] = []
    if direct:
        out = git("ls-tree", "-r", "--name-only", commit, "--", *direct, cwd=cwd)
        results.extend(line for line in out.splitlines() if line)

    for spec in glob_specs:
        parent = spec.rsplit("/", 1)[0] if "/" in spec else "."
        out = git("ls-tree", "-r", "--name-only", commit, "--", parent, cwd=cwd)
        for line in out.splitlines():
            if line and fnmatch.fnmatch(line, spec):
                results.append(line)

    seen = set()
    deduped = []
    for f in results:
        if f not in seen:
            seen.add(f)
            deduped.append(f)
    return deduped


def apply_excludes(files: List[str], exclude_patterns: List[str]) -> List[str]:
    """Drop any file matching an exclude glob. `**/tests/` and
    `**/__pycache__/` match any path with a `tests`/`__pycache__` path
    segment; a trailing-`/` pattern is treated as "this directory anywhere
    in the path", not a literal fnmatch pattern, since fnmatch has no native
    "any directory" semantics."""
    def excluded(f: str) -> bool:
        for pat in exclude_patterns:
            if pat.endswith("/"):
                segment = pat.rstrip("/").lstrip("*/")
                if f"/{segment}/" in f"/{f}" or f.startswith(f"{segment}/"):
                    return True
            elif fnmatch.fnmatch(f, pat):
                return True
        return False
    return [f for f in files if not excluded(f)]


def target_files(target: Target, commit: str, cwd: Path = REPO_ROOT) -> List[str]:
    files = list_files_at_commit(commit, target.paths, cwd=cwd)
    return apply_excludes(files, target.exclude)


def sha256_at_commit(commit: str, path: str, cwd: Path = REPO_ROOT) -> str:
    import hashlib
    result = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "show", f"{commit}:{path}"],
        cwd=cwd, capture_output=True, check=True,
    )
    return hashlib.sha256(result.stdout).hexdigest()


# ---------------------------------------------------------------------------
# SSH runner: the only thing allowed to touch a real host
# ---------------------------------------------------------------------------


class SSHError(Exception):
    pass


def _default_bash() -> str:
    """scripts/vm-ssh.sh is a bash script; on Windows, subprocess cannot
    exec it directly (`%1 is not a valid Win32 application`), and a bare
    "bash" on PATH may resolve to WSL's wrapper instead of Git Bash (which
    fails with no WSL distro installed -- confirmed empirically on this
    workstation). GIT_BASH overrides the path; the Git-for-Windows default
    install location is the fallback. On a real POSIX host, vm-ssh.sh can
    be exec'd directly, so this is only consulted when that fails."""
    import os
    return os.environ.get("GIT_BASH", r"C:\Program Files\Git\bin\bash.exe")


class SSHRunner:
    """Real runner: shells out to scripts/vm-ssh.sh. Every call is read-only
    at this layer's discretion -- it is the CALLER's job (deploy.py vs
    drift_check.py) to only ever pass a read-only command here except from
    deploy.py's own explicitly-confirmed write path."""

    def __init__(self, vm_ssh: Path = VM_SSH, env_file: Optional[Path] = None):
        self.vm_ssh = vm_ssh
        self.env_file = env_file

    def run(self, host: str, command: str, input_bytes: Optional[bytes] = None) -> str:
        env = dict(**{**_os_environ()})
        if self.env_file is not None:
            env["DF_ENV_FILE"] = str(self.env_file)
        try:
            result = subprocess.run(
                [str(self.vm_ssh), host, command],
                input=input_bytes, capture_output=True, env=env,
            )
        except OSError:
            # Windows: vm-ssh.sh cannot be exec'd directly. Fall back to an
            # explicit Git Bash. Left as a fallback rather than the default
            # path so a real POSIX host (or CI) never pays for the probe.
            result = subprocess.run(
                [_default_bash(), str(self.vm_ssh), host, command],
                input=input_bytes, capture_output=True, env=env,
            )
        if result.returncode != 0:
            raise SSHError(
                f"vm-ssh.sh {host} failed (exit {result.returncode}): "
                f"{result.stderr.decode(errors='replace').strip()}"
            )
        return result.stdout.decode(errors="replace")


def _os_environ() -> Dict[str, str]:
    import os
    return dict(os.environ)


class FakeRunner:
    """Test double. `responses` maps (host, command) -> stdout string, or a
    callable(host, command, input_bytes) -> str. Records every call in
    `.calls` so a test can assert exactly what would have been run, which
    matters most for deploy.py's dry-run path: the test is really asserting
    "this would have been the real command", not just "something happened"."""

    def __init__(self, responses: Optional[dict] = None):
        self.responses = responses or {}
        self.calls: List[tuple] = []

    def run(self, host: str, command: str, input_bytes: Optional[bytes] = None) -> str:
        self.calls.append((host, command, input_bytes))
        key = (host, command)
        if key in self.responses:
            value = self.responses[key]
            return value(host, command, input_bytes) if callable(value) else value
        for (h, pattern), value in self.responses.items():
            if h == host and pattern == "*":
                return value(host, command, input_bytes) if callable(value) else value
        raise SSHError(f"FakeRunner: no response configured for host={host!r} command={command!r}")
