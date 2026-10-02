#!/usr/bin/env python3
"""Deploy one commit to one or all targets in infra/deploy-manifest.yaml.

    python scripts/deploy.py --target vm103-dfmcp --dry-run
    python scripts/deploy.py --all --dry-run
    python scripts/deploy.py --target vm103-dfmcp --yes     # the real thing

Refuses to run for real (regardless of --yes) when:
  - the working tree is dirty (`git status --porcelain` is non-empty);
  - the commit being deployed (HEAD, unless --commit is given) is not an
    ancestor of `origin/main` -- this repo's rule that a deploy ships a
    reviewed commit, never a local-only one;
  - a target's restart list names a "risk: high" service (conductor.service,
    df-fortress.service) -- printed as the exact manual command plus the doc
    to read first, never executed. This is a different gate from --yes: no
    flag on this CLI will ever run a high-risk restart. See
    infra/deploy-manifest.yaml's own `why` field per entry for the save-state
    or write-authority reasoning behind each one.

Ships committed bytes only: `git -c core.autocrlf=false archive <commit> --
<files>` (CLAUDE.md's CRLF trap), piped as a tar stream through
`scripts/vm-ssh.sh <host> 'tar xf - -C <destination_root>'`. Never an scp of
the working tree, never a plain `git pull` on the host.

After a successful real deploy to a target: writes `DEPLOYED_COMMIT` (commit,
UTC timestamp, manifest sha256) at that target's destination_root, then runs
scripts/drift_check.py for that one target and fails loudly (non-zero exit,
the drift report printed) if it is not clean -- a deploy that leaves drift
behind is not considered to have succeeded.

This script was written and tested offline (FakeRunner, no real ssh) by the
stream that built it (handoffs/2026-10-02-deploy-and-drift-system.md), which
was explicitly barred from running it for real. `--dry-run` is always safe
to run against the real manifest; nothing else is, until a human reviews a
real `--dry-run` plan and gives the go-ahead per deploy, per CLAUDE.md's
"treat git push and any deploy as outward-facing, needing explicit go-ahead
each time" rule.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import os
import subprocess
import sys
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(__file__))
import deploy_common as dc  # noqa: E402


def manifest_hash(path: Path = dc.MANIFEST_PATH) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def build_tar(commit: str, files: List[str], cwd: Path = dc.REPO_ROOT, *, flatten: bool = False) -> bytes:
    """`git archive` of exactly `files` (never a whole directory the caller
    didn't ask for) as of `commit`. Returns the tar bytes; raises
    CalledProcessError if any file is missing from that commit.

    `flatten=True` (relay-web only, per infra/deploy-manifest.yaml's own
    `flatten: true` comment) rewrites each tar member's name to just its
    basename before returning, since `git archive` has no built-in way to
    do that -- it only ever preserves the repo-relative path."""
    if not files:
        return b""
    result = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "archive", "--format=tar", commit, "--", *files],
        cwd=cwd, capture_output=True, check=True,
    )
    tar_bytes = result.stdout
    if not flatten:
        return tar_bytes
    src = tarfile.open(fileobj=BytesIO(tar_bytes), mode="r:")
    out_buf = BytesIO()
    dst = tarfile.open(fileobj=out_buf, mode="w:")
    for member in src.getmembers():
        if not member.isfile():
            continue  # directory entries have no meaningful flattened name
        data = src.extractfile(member)
        member.name = member.name.rsplit("/", 1)[-1]
        dst.addfile(member, data)
    dst.close()
    return out_buf.getvalue()


def plan_for_target(target: dc.Target, commit: str, env: Dict[str, str]) -> dict:
    """Everything a deploy to `target` would do, computed without touching
    any host. Shared by --dry-run (which only prints this) and the real
    path (which prints the same thing, then executes it)."""
    files = dc.target_files(target, commit)
    destination = target.destination_root(env)
    stamp = f"commit={commit}\ndeployed_at={_utc_now()}\nmanifest_sha256={manifest_hash()}\n"
    low_risk_restarts = [r for r in target.restart if not r.is_high_risk]
    high_risk_restarts = [r for r in target.restart if r.is_high_risk]
    return {
        "target": target.name,
        "host": target.host,
        "destination_root": destination,
        "files": files,
        "file_count": len(files),
        "stamp_contents": stamp,
        "low_risk_restarts": [r.service for r in low_risk_restarts],
        "high_risk_restarts": [r.service for r in high_risk_restarts],
        "post_deploy": target.post_deploy,
    }


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def print_plan(plan: dict) -> None:
    print(f"--- {plan['target']} ({plan['host']} -> {plan['destination_root']}) ---")
    print(f"  {plan['file_count']} file(s):")
    for f in plan["files"][:20]:
        print(f"    {f}")
    if plan["file_count"] > 20:
        print(f"    ... and {plan['file_count'] - 20} more")
    print(f"  write stamp: DEPLOYED_COMMIT at {plan['destination_root']}")
    print(f"    {plan['stamp_contents'].strip().replace(chr(10), ', ')}")
    if plan["low_risk_restarts"]:
        print(f"  would restart (low risk): {', '.join(plan['low_risk_restarts'])}")
    if plan["high_risk_restarts"]:
        print(f"  WOULD NOT restart (high risk, manual only): {', '.join(plan['high_risk_restarts'])}")
    for step in plan["post_deploy"]:
        print(f"  post-deploy: {step}")
    print(f"  then: drift_check.py --target {plan['target']} (must come back clean)")


def deploy_target(
    target: dc.Target,
    commit: str,
    env: Dict[str, str],
    runner,
    *,
    dry_run: bool,
    yes: bool,
) -> dict:
    plan = plan_for_target(target, commit, env)
    if dry_run:
        print_plan(plan)
        return {"target": target.name, "dry_run": True, "plan": plan}

    if not yes:
        print(f"--- {target.name}: refusing to deploy for real without --yes ---")
        print_plan(plan)
        return {"target": target.name, "skipped": "no --yes"}

    destination = plan["destination_root"]
    su = "sudo -n " if target.sudo else ""
    tar_bytes = build_tar(commit, plan["files"], flatten=target.flatten)
    print(f"--- {target.name}: deploying {commit[:12]} ({len(plan['files'])} file(s)) to {destination} ---")
    runner.run(target.host, f"{su}mkdir -p {destination}")
    if tar_bytes:
        runner.run(target.host, f"{su}tar xf - -C {destination}", input_bytes=tar_bytes)
    runner.run(
        target.host,
        f"{su}tee {destination}/DEPLOYED_COMMIT >/dev/null <<'EOF'\n{plan['stamp_contents']}EOF",
    )
    print("  files copied, stamp written")

    for service in plan["low_risk_restarts"]:
        runner.run(target.host, f"sudo systemctl restart {service}")
        print(f"  restarted {service}")

    for entry in target.restart:
        if entry.is_high_risk:
            print(f"  NOT restarting high-risk service '{entry.service}'. Manual step:")
            print(f"    scripts/vm-ssh.sh {target.host} 'sudo systemctl restart {entry.service}'")
            print(f"    Read first: {entry.why.strip()}")

    # The deploy is only done when this target's drift check is clean (the
    # docstring's promise; tests use a fake runner and skip the real check).
    if isinstance(runner, dc.SSHRunner):
        check = subprocess.run(
            [sys.executable, str(dc.REPO_ROOT / "scripts" / "drift_check.py"), "--target", target.name],
            cwd=dc.REPO_ROOT, capture_output=True, text=True,
        )
        print(check.stdout.rstrip())
        if check.returncode != 0:
            print(f"  DRIFT after deploying {target.name}: see the report above.")
            return {"target": target.name, "deployed": True, "commit": commit, "plan": plan, "drift": True}
        print(f"  {target.name}: clean")
    return {"target": target.name, "deployed": True, "commit": commit, "plan": plan}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--target", help="one target name from infra/deploy-manifest.yaml")
    group.add_argument("--all", action="store_true", help="every target in the manifest")
    parser.add_argument("--commit", default=None, help="commit to deploy (default: HEAD)")
    parser.add_argument("--dry-run", action="store_true", help="print the plan; touch nothing")
    parser.add_argument("--yes", action="store_true", help="actually deploy (still refuses high-risk restarts)")
    parser.add_argument("--env-file", default=None, help="override .env path (for tests)")
    args = parser.parse_args(argv)

    if not args.dry_run and not args.yes:
        print("Refusing to run for real without --yes. Use --dry-run to preview.", file=sys.stderr)
        return 2

    if not dc.is_tree_clean():
        print("Refusing: working tree is not clean (git status --porcelain is non-empty).", file=sys.stderr)
        return 2

    commit = args.commit or dc.current_commit()
    if not dc.is_ancestor_of_origin_main(commit):
        print(
            f"Refusing: commit {commit} is not an ancestor of origin/main. "
            "Only a commit that has reached origin/main may be deployed.",
            file=sys.stderr,
        )
        return 2

    env = dc.read_env_file(Path(args.env_file) if args.env_file else dc.ENV_PATH)
    targets = dc.load_manifest()

    if args.target:
        if args.target not in targets:
            print(f"Unknown target {args.target!r}. Known: {', '.join(sorted(targets))}", file=sys.stderr)
            return 2
        selected = {args.target: targets[args.target]}
    else:
        selected = targets

    runner = dc.SSHRunner()
    results = []
    hard_fail = False
    for name, target in selected.items():
        try:
            results.append(deploy_target(target, commit, env, runner, dry_run=args.dry_run, yes=args.yes))
        except dc.ManifestError as exc:
            # A single target whose destination_root needs an env var this
            # .env doesn't have yet is a configuration gap, not a reason to
            # abort every other target's plan too -- report it and keep
            # going for --dry-run; a real (--yes) run still must not
            # silently skip a target the caller asked for, so it is a hard
            # failure there.
            print(f"{name}: not configured: {exc}", file=sys.stderr)
            results.append({"target": name, "error": str(exc)})
            if args.yes:
                hard_fail = True
    if any(r.get("drift") for r in results):
        hard_fail = True
    if hard_fail:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
