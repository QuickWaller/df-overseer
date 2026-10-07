#!/usr/bin/env python3
"""Read-only drift check: repo vs what is actually deployed, for every
target in infra/deploy-manifest.yaml. Safe to run any time -- every host
command it issues is a listing, a `cat`, a `sha256sum`, or `systemctl
show`/`is-active`/`is-enabled`, through `scripts/vm-ssh.sh`, which already
masks any address-shaped string in its output. This script never prints
one either.

    python scripts/drift_check.py                      # every target, human report
    python scripts/drift_check.py --target vm103-dfmcp
    python scripts/drift_check.py --json
    python scripts/drift_check.py --write-state         # also writes docs/STATE.md

Exit code: 0 if nothing drifted, 1 if anything did (files, services, or a
documented tool count disagreeing with the registry).

Four checks per the handoff (handoffs/2026-10-02-deploy-and-drift-system.md):

1. files: sha256 of every manifest file on the target, against the
   committed bytes at the target's own stamped commit (DEPLOYED_COMMIT,
   written by scripts/deploy.py) and against origin/main, so it can say
   both "this file was edited in place" and "this host is N commits
   behind" in the same report. A target with no stamp yet (nothing this
   tool has ever deployed, e.g. relay-web, vm106-agents before their first
   deploy.py run) compares directly against origin/main instead and says so.
2. live behaviour: per-role tool IDS computed offline from
   dfmcp.registry/dfmcp.roles (the registry + roster this repo would load),
   cross-checked against a live MCP probe when one is deployed on the host
   -- an actual set comparison (`mcpcall.py names-all`, translated back to
   tool ids via dfmcp.tools.build_tool_names()'s name_to_id map), not just a
   count, because two roles can carry the same NUMBER of tools while
   disagreeing on which ones. scripts/ops/mcpcall.py is the existing probe
   (its own header: "Live MCP client for VM 103 checks, run from
   /opt/df/dfmcp-smoke/.venv") -- reused here rather than inventing a second
   one. Added to the vm103-dfmcp manifest target 2026-10-02
   (handoffs/2026-10-02-drift-followups.md), but a manifest entry alone
   does not ship it anywhere: this check still probes the host directly
   (`test -f {destination_root}/scripts/ops/mcpcall.py`) and degrades to
   "offline count only, live probe not deployed" until an actual
   `deploy.py --yes` run against vm103-dfmcp has put it there.
3. website: relay file hashes against repo HEAD, and the published
   agents.json/tools.json (dfqueue.site_data's own output, written by
   scripts/stream_publisher.py's write_site_data() call) against what the
   repo's registry + roster would generate right now via
   dfqueue.site_data.build_tools_json()/build_agents_json().
4. services: each named service's active/enabled state, reported, never
   judged -- conductor.service disabled+inactive is the DOCUMENTED state,
   not a drift finding by itself.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shlex
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(__file__))
import deploy_common as dc  # noqa: E402

REPO_ROOT = dc.REPO_ROOT
STATE_PATH = REPO_ROOT / "docs" / "STATE.md"


# ---------------------------------------------------------------------------
# stamp
# ---------------------------------------------------------------------------


def stamp_command(target: dc.Target, destination: str) -> str:
    """The target's own stamp, else the legacy shared one (see
    `Target.stamp_file`)."""
    return (f"cat {destination}/{target.stamp_file} 2>/dev/null"
            f" || cat {destination}/DEPLOYED_COMMIT 2>/dev/null || true")


def read_stamp(target: dc.Target, destination: str, runner) -> Optional[Dict[str, str]]:
    try:
        out = runner.run(target.host, stamp_command(target, destination))
    except dc.SSHError:
        return None
    stamp: Dict[str, str] = {}
    for line in out.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            stamp[k.strip()] = v.strip()
    return stamp or None


# ---------------------------------------------------------------------------
# 1. files
# ---------------------------------------------------------------------------


def remote_sha256_many(
    host: str, destination: str, files: List[str], runner, *, remote_path=lambda f: f,
) -> Dict[str, Optional[str]]:
    """{repo_path: sha256 or None if missing on the host}. A single ssh call
    for the whole target; `|| true` so one missing file doesn't blow up the
    rest (sha256sum exits non-zero if ANY named file is absent, but still
    prints the hashes it could compute).

    `remote_path(repo_path)` maps a repo-relative path to where it actually
    lands under `destination` -- identical for almost every target, but
    relay-web's and vm103-dfhack-scripts' `flatten: true` drops the leading
    directories (repo `web/stream/index.html` -> remote `index.html`),
    confirmed live 2026-10-02 after a first drift_check.py run misreported
    those files as missing entirely.

    Matches each output line to the requested file by POSITION, not by
    parsing the printed filename back out: `scripts/vm-ssh.sh`'s own
    address-leak scrubber masks any `df-[a-z0-9-]+`-shaped string in its
    output, including this project's own `df-overseer-*.lua` filenames
    (the exact false positive docs/DRIFT-AUDIT-2026-09-28.md already hit
    doing this by hand) -- confirmed live here too: `sha256sum
    df-overseer-ui.lua` comes back as `<hash>  <host>.lua`, which no
    name-based parse could ever match back to the real filename. GNU
    coreutils' sha256sum processes its arguments strictly in the order
    given and emits exactly one line per argument (a hash line on success,
    an error line otherwise) to the SAME requested order, so position is
    reliable even though the printed name is not -- the digest itself
    (pure hex) is never mangled by the scrubber."""
    if not files:
        return {}
    remote_names = [remote_path(f) for f in files]
    quoted = " ".join(shlex.quote(f) for f in remote_names)
    out = runner.run(
        host,
        f"cd {shlex.quote(destination)} && sha256sum {quoted} 2>&1 || true",
    )
    lines = [line for line in out.splitlines() if line.strip()]
    results: Dict[str, Optional[str]] = {}
    for f, line in zip(files, lines):
        parts = line.split(None, 1)
        if len(parts) == 2 and len(parts[0]) == 64 and all(c in "0123456789abcdef" for c in parts[0]):
            results[f] = parts[0]
        else:
            results[f] = None
    for f in files:
        results.setdefault(f, None)
    return results


def _norm_unit_name(name: str) -> str:
    """Compare unit names with `-` folded to `_`: scripts/vm-ssh.sh masks every
    `df-[a-z0-9-]+` string in its output to `<host>`, which would hide the very
    names this check needs, so the remote listing is run through `sed
    's/-/_/g'` (nothing the scrubber matches survives that) and both sides are
    folded the same way before comparing."""
    return name.replace("-", "_")


def find_untracked_units(target: dc.Target, destination: str, files: List[str], runner) -> dict:
    """Unit files and drop-ins installed under `destination` that the repo
    does not know about and the manifest does not declare `unmanaged_units`.
    Only for a unit target (daemon_reload: true). Lists regular files only
    (symlinks are `systemctl enable` wiring and vendor aliases, not content):
    top-level `*.service`/`*.timer`/..., and every `<unit>.d/*.conf`.

    Verifies the verification: if the host listing shows none of the files the
    repo says are installed, the listing itself failed (a bad find, an empty
    reply) and an empty "untracked" list would be a false all-clear, so that
    is reported as an error, not as clean."""
    try:
        out = runner.run(
            target.host,
            f"cd {shlex.quote(destination)} && find . -mindepth 1 -maxdepth 2 -type f "
            f"| sed 's/-/_/g' | sort || true",
        )
    except dc.SSHError as exc:
        return {"untracked": [], "error": f"listing failed: {exc}"}
    installed = [line[2:] if line.startswith("./") else line for line in out.splitlines() if line.strip()]
    tracked = {_norm_unit_name(target.remote_path(f)) for f in files}
    unmanaged = {_norm_unit_name(u["name"]) for u in target.unmanaged_units}
    # an unmanaged entry may name a whole drop-in directory: `<unit>.d` covers `<unit>.d/*`
    def declared(path: str) -> bool:
        return path in unmanaged or path.split("/", 1)[0] in unmanaged
    if tracked and not (tracked & set(installed)):
        return {"untracked": [], "error": "listing shows none of the tracked units; cannot trust an empty result"}
    untracked = [
        {"path": path, "kind": "drop-in" if "/" in path else "unit"}
        for path in installed
        if path not in tracked and not declared(path)
    ]
    return {"untracked": untracked, "error": None}


def check_target_files(target: dc.Target, env: Dict[str, str], runner) -> dict:
    destination = target.destination_root(env)
    stamp = read_stamp(target, destination, runner) if target.stamp else None
    stamped_commit = stamp.get("commit") if stamp else None

    compare_commit = stamped_commit or "origin/main"
    files = dc.target_files(target, compare_commit)
    local_hashes = {f: dc.sha256_at_commit(compare_commit, f) for f in files}
    remote_hashes = remote_sha256_many(target.host, destination, files, runner, remote_path=target.remote_path)

    per_file = []
    drifted = 0
    for f in files:
        local = local_hashes[f]
        remote = remote_hashes.get(f)
        if remote is None:
            status = "missing_on_host"
            drifted += 1
        elif remote == local:
            status = "match"
        else:
            status = "differ"
            drifted += 1
        per_file.append({"path": f, "status": status, "local_sha256": local, "remote_sha256": remote})

    commits_behind = None
    if stamped_commit:
        commits_behind = dc.commits_behind_origin_main(stamped_commit)

    untracked: List[dict] = []
    untracked_error = None
    if target.daemon_reload:  # a unit target: also look for host-only units/drop-ins
        found = find_untracked_units(target, destination, files, runner)
        untracked, untracked_error = found["untracked"], found["error"]

    return {
        "target": target.name,
        "destination_root": destination,
        "stamp": stamp,
        "compared_against": compare_commit if not stamped_commit else stamped_commit,
        "commits_behind_origin_main": commits_behind,
        "file_count": len(files),
        "drifted_count": drifted,
        "files": per_file,
        "untracked": untracked,
        "untracked_error": untracked_error,
        "clean": drifted == 0 and not untracked and untracked_error is None,
    }


# ---------------------------------------------------------------------------
# 2. live behaviour (tool counts)
# ---------------------------------------------------------------------------


def _load_registry_and_roster(agents_dir: Path = REPO_ROOT / "agents"):
    sys.path.insert(0, str(REPO_ROOT))
    from dfmcp.registry import load_registry
    from dfmcp.roles import load_roster
    from dfmcp import queue_tools, doctrine_tools, series_tools, gotchas_tools, knowledge_tools, conductor_tools, plan_tools

    registry = load_registry(native_tools={
        **queue_tools.NATIVE_TOOLS, **doctrine_tools.NATIVE_TOOLS, **series_tools.NATIVE_TOOLS,
        **gotchas_tools.NATIVE_TOOLS, **knowledge_tools.NATIVE_TOOLS, **conductor_tools.NATIVE_TOOLS, **plan_tools.NATIVE_TOOLS,
    })
    roster = load_roster(registry, agents_dir=agents_dir)
    return registry, roster


def offline_role_tool_counts(agents_dir: Path = REPO_ROOT / "agents") -> Dict[str, int]:
    _, roster = _load_registry_and_roster(agents_dir)
    return {name: len(perms.read) + len(perms.write) for name, perms in roster.roles.items()}


def offline_role_tool_ids(agents_dir: Path = REPO_ROOT / "agents") -> Dict[str, set]:
    """{role: {tool_id, ...}} -- every id the roster actually grants (read
    plus write), the same ids `dfmcp/tools.py`'s `build_tool_names()` maps to
    the MCP-visible dunder names a live `mcpcall.py names-all` reports."""
    _, roster = _load_registry_and_roster(agents_dir)
    return {name: set(perms.read) | set(perms.write) for name, perms in roster.roles.items()}


def check_live_tool_counts(targets: Dict[str, dc.Target], runner) -> dict:
    """Per-role live check against the vm103-dfmcp target, once
    scripts/ops/mcpcall.py is actually deployed there (`names-all`, not just
    `counts`: two roles can carry the same NUMBER of tools while disagreeing
    on which ones, and a count-only check would call that clean)."""
    offline_ids = offline_role_tool_ids()
    offline = {role: len(ids) for role, ids in offline_ids.items()}

    sys.path.insert(0, str(REPO_ROOT))
    from dfmcp.tools import build_tool_names
    registry, _ = _load_registry_and_roster()
    _, name_to_id = build_tool_names(registry)

    probe_deployed = False
    dfmcp_target = targets.get("vm103-dfmcp")
    live_ids: Dict[str, set] = {}
    unknown_live_names: Dict[str, list] = {}
    if dfmcp_target is not None:
        try:
            out = runner.run(
                dfmcp_target.host,
                f"test -f {dfmcp_target.destination_root_raw}/scripts/ops/mcpcall.py && echo present || echo absent",
            )
            probe_deployed = out.strip() == "present"
        except dc.SSHError:
            probe_deployed = False
        if probe_deployed:
            try:
                out = runner.run(
                    dfmcp_target.host,
                    f"cd {dfmcp_target.destination_root_raw} && .venv/bin/python scripts/ops/mcpcall.py names-all",
                )
                for line in out.splitlines():
                    if "\t" not in line:
                        continue
                    role, name = line.split("\t", 1)
                    tool_id = name_to_id.get(name)
                    if tool_id is None:
                        unknown_live_names.setdefault(role, []).append(name)
                        continue
                    live_ids.setdefault(role, set()).add(tool_id)
            except dc.SSHError:
                pass

    live_counts = {role: len(ids) for role, ids in live_ids.items()}
    mismatches = {}
    for role in set(offline) | set(live_ids):
        if role not in live_ids:
            continue  # not reported live at all -- not a per-id mismatch here
        missing_live = sorted(offline_ids.get(role, set()) - live_ids[role])
        extra_live = sorted(live_ids[role] - offline_ids.get(role, set()))
        if missing_live or extra_live or unknown_live_names.get(role):
            mismatches[role] = {
                "offline": offline.get(role),
                "live": live_counts.get(role),
                "missing_live": missing_live,
                "extra_live": extra_live,
                "unknown_live_names": unknown_live_names.get(role, []),
            }

    return {
        "offline_counts": offline,
        "probe_deployed": probe_deployed,
        "live_counts": live_counts,
        "mismatches": mismatches,
        "clean": not mismatches,
        "note": None if probe_deployed else (
            "scripts/ops/mcpcall.py is in the vm103-dfmcp manifest target (added "
            "2026-10-02) but not yet copied to the host by a real `deploy.py --yes` "
            "run; live counts cannot be cross-checked until it is deployed. "
            "offline_counts is what the repo's registry+roster would produce."
        ),
    }


# ---------------------------------------------------------------------------
# 3. website
# ---------------------------------------------------------------------------


def check_website(targets: Dict[str, dc.Target], env: Dict[str, str], runner) -> dict:
    result: dict = {"files": None, "generated_json": None}
    relay_target = targets.get("relay-web")
    if relay_target is not None:
        result["files"] = check_target_files(relay_target, env, runner)

    sys.path.insert(0, str(REPO_ROOT))
    try:
        from dfqueue import site_data
        tools_json = site_data.build_tools_json()
        role_counts_repo = {}
        for tool in tools_json["tools"]:
            for role in tool["roles"]:
                role_counts_repo[role] = role_counts_repo.get(role, 0) + 1
    except Exception as exc:  # pragma: no cover - defensive, reported not raised
        result["generated_json"] = {"error": f"could not build tools.json locally: {exc}"}
        return result

    live_json = None
    if relay_target is not None:
        destination = relay_target.destination_root(env)
        data_root = destination.rsplit("/", 1)[0] + "/data/public"  # .../web-public -> .../data/public
        try:
            out = runner.run(relay_target.host, f"cat {shlex.quote(data_root)}/tools.json 2>/dev/null || true")
            live_json = json.loads(out) if out.strip() else None
        except (dc.SSHError, json.JSONDecodeError):
            live_json = None

    if live_json is None:
        result["generated_json"] = {
            "repo_role_counts": role_counts_repo,
            "live_role_counts": None,
            "note": "tools.json not found live at the expected path -- the deployed "
                    "stream_publisher.py predates the write_site_data() call (confirmed "
                    "live 2026-10-02: only head/open/projects/status.json exist under "
                    "data/public), so this is not comparable yet, not a per-tool drift.",
            "clean": True,
        }
    else:
        live_counts = {}
        for tool in live_json.get("tools", []):
            for role in tool.get("roles", []):
                live_counts[role] = live_counts.get(role, 0) + 1
        result["generated_json"] = {
            "repo_role_counts": role_counts_repo,
            "live_role_counts": live_counts,
            "clean": role_counts_repo == live_counts,
        }
    return result


# ---------------------------------------------------------------------------
# 4. services
# ---------------------------------------------------------------------------


def check_services(targets: Dict[str, dc.Target], runner) -> dict:
    seen = {}
    for target in targets.values():
        for entry in target.restart:
            seen[(target.host, entry.service)] = entry
    out = {}
    for (host, service), entry in seen.items():
        try:
            raw = runner.run(
                host,
                f"systemctl show {shlex.quote(service)} --property=ActiveState,UnitFileState 2>&1 || true",
            )
        except dc.SSHError:
            raw = ""
        props = {}
        for line in raw.splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                props[k] = v
        out[service] = {
            "host": host,
            "active": props.get("ActiveState", "unknown"),
            "enabled": props.get("UnitFileState", "unknown"),
            "risk": entry.risk,
        }
    return out


# ---------------------------------------------------------------------------
# report assembly
# ---------------------------------------------------------------------------


def build_report(targets: Dict[str, dc.Target], selected: List[str], env: Dict[str, str], runner) -> dict:
    files = {}
    for name in selected:
        files[name] = check_target_files(targets[name], env, runner)

    report = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": files,
        "live_tool_counts": check_live_tool_counts(targets, runner),
        "website": check_website(targets, env, runner),
        "services": check_services(targets, runner),
    }
    report["clean"] = (
        all(f["clean"] for f in files.values())
        and report["live_tool_counts"]["clean"]
        and (report["website"]["generated_json"] or {}).get("clean", True)
        and (report["website"]["files"] is None or report["website"]["files"]["clean"])
    )
    return report


def print_report(report: dict) -> None:
    print(f"drift check, {report['generated_at']}")
    print()
    for name, result in report["files"].items():
        behind = result["commits_behind_origin_main"]
        behind_txt = f", {behind} commit(s) behind origin/main" if behind else (
            ", stamp not an ancestor of origin/main (check manually)" if result["stamp"] and behind is None else ""
        )
        stamp_txt = "no DEPLOYED_COMMIT stamp found" if not result["stamp"] else f"stamped {result['stamp'].get('commit', '?')[:12]}"
        print(f"[{'clean' if result['clean'] else 'DRIFT'}] {name}: {result['file_count']} file(s), "
              f"{result['drifted_count']} drifted ({stamp_txt}{behind_txt})")
        if not result["clean"]:
            for f in result["files"]:
                if f["status"] != "match":
                    print(f"    {f['status']}: {f['path']}")
            for u in result.get("untracked", []):
                print(f"    untracked {u['kind']} on host (not in the repo, not declared unmanaged): {u['path']}")
            if result.get("untracked_error"):
                print(f"    untracked-unit check could not run: {result['untracked_error']}")
    print()

    live = report["live_tool_counts"]
    print(f"[{'clean' if live['clean'] else 'DRIFT'}] live tool counts: "
          f"{', '.join(f'{r} {c}' for r, c in sorted(live['offline_counts'].items()))}")
    if live["note"]:
        print(f"    {live['note']}")
    for role, m in live["mismatches"].items():
        print(f"    MISMATCH {role}: offline {m['offline']} vs live {m['live']}")
        if m.get("missing_live"):
            print(f"        missing live: {', '.join(m['missing_live'])}")
        if m.get("extra_live"):
            print(f"        extra live (not in the allowlist): {', '.join(m['extra_live'])}")
        if m.get("unknown_live_names"):
            print(f"        live names not recognised by the current registry: {', '.join(m['unknown_live_names'])}")
    print()

    website = report["website"]
    if website["files"] is not None:
        wf = website["files"]
        print(f"[{'clean' if wf['clean'] else 'DRIFT'}] relay-web files: "
              f"{wf['file_count']} file(s), {wf['drifted_count']} drifted")
        for f in wf["files"]:
            if f["status"] != "match":
                print(f"    {f['status']}: {f['path']}")
    gj = website["generated_json"]
    if gj and "error" not in gj:
        print(f"[{'clean' if gj['clean'] else 'DRIFT'}] published tools.json role counts: "
              f"repo {gj['repo_role_counts']}")
        if gj.get("note"):
            print(f"    {gj['note']}")
        if gj.get("live_role_counts") not in (None,) and not gj["clean"]:
            print(f"    live {gj['live_role_counts']}")
    elif gj:
        print(f"[DRIFT] website generated_json: {gj['error']}")
    print()

    print("services (reported, not judged):")
    for service, info in sorted(report["services"].items()):
        print(f"    {service} [{info['host']}, risk={info['risk']}]: "
              f"active={info['active']}, enabled={info['enabled']}")


def write_state(report: dict, path: Path = STATE_PATH) -> None:
    lines = [
        "# docs/STATE.md",
        "",
        "Generated by `python scripts/drift_check.py --write-state`. Do not hand-edit --",
        "a number here that disagrees with this file's own generation command is a bug",
        "in the generator, not something to patch by hand.",
        "",
        f"Last check: {report['generated_at']}, overall: {'clean' if report['clean'] else 'DRIFT'}",
        "",
        "## Deployed commit per target",
        "",
        "| target | stamped commit | commits behind origin/main | files drifted | untracked units |",
        "|---|---|---|---|---|",
    ]
    for name, result in report["files"].items():
        commit = (result["stamp"] or {}).get("commit", "(no stamp)")
        behind = result["commits_behind_origin_main"]
        behind_txt = str(behind) if behind is not None else "?"
        untracked_txt = str(len(result.get("untracked", []))) if not result.get("untracked_error") else "check failed"
        lines.append(f"| {name} | {commit[:12]} | {behind_txt} | {result['drifted_count']}/{result['file_count']} | {untracked_txt} |")

    lines += ["", "## Per-role tool counts (offline, from the repo's own registry + roster)", ""]
    for role, count in sorted(report["live_tool_counts"]["offline_counts"].items()):
        lines.append(f"- **{role}**: {count}")
    if report["live_tool_counts"]["note"]:
        lines.append("")
        lines.append(report["live_tool_counts"]["note"])

    lines += ["", "## Services", ""]
    for service, info in sorted(report["services"].items()):
        lines.append(f"- `{service}` ({info['host']}, risk={info['risk']}): "
                      f"active={info['active']}, enabled={info['enabled']}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", default=None, help="one target name; default: every target")
    parser.add_argument("--json", action="store_true", help="print the report as JSON instead of text")
    parser.add_argument("--write-state", action="store_true", help="also write docs/STATE.md")
    parser.add_argument("--env-file", default=None, help="override .env path (for tests)")
    args = parser.parse_args(argv)

    env = dc.read_env_file(Path(args.env_file) if args.env_file else dc.ENV_PATH)
    targets = dc.load_manifest()

    if args.target:
        if args.target not in targets:
            print(f"Unknown target {args.target!r}. Known: {', '.join(sorted(targets))}", file=sys.stderr)
            return 2
        selected = [args.target]
    else:
        selected = [name for name, t in targets.items() if not str(t.destination_root_raw).startswith("${")
                    or env.get(t.destination_root_raw[2:-1])]
        skipped = [name for name in targets if name not in selected]
        for name in skipped:
            print(f"{name}: skipped, destination_root needs an unset env var", file=sys.stderr)

    runner = dc.SSHRunner()
    report = build_report(targets, selected, env, runner)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_report(report)

    if args.write_state:
        write_state(report)
        print(f"\nwrote {STATE_PATH}")

    return 0 if report["clean"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
