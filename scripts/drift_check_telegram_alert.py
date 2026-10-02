#!/usr/bin/env python3
"""Run scripts/drift_check.py; if it finds drift, send one Telegram message
to the user's existing private line (register 2026-10-01: TELEGRAM_BOT_TOKEN
+ USER_TELEGRAM_ID in .env, read by key). Silent on a clean run -- this is
meant for a daily unattended schedule, not a chat log.

    python scripts/drift_check_telegram_alert.py            # real run
    python scripts/drift_check_telegram_alert.py --dry-run   # print the
        message that WOULD be sent; never calls the Telegram API

This script is WRITTEN AND TESTED OFFLINE ONLY by this stream
(handoffs/2026-10-02-deploy-and-drift-system.md). It is NOT installed as a
scheduled task or systemd timer by this stream -- see docs/RUNBOOK-DEPLOY.md
for the exact Windows Task Scheduler / systemd-timer commands a human runs
to enable it, once they choose to.

Exit code mirrors drift_check's: 0 clean, 1 drifted (whether or not the
Telegram send succeeded -- a failed alert must never be reported as "no
drift" by a caller only checking the exit code).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(__file__))
import deploy_common as dc  # noqa: E402
import drift_check  # noqa: E402

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def read_telegram_credentials(env_path: Path = dc.ENV_PATH) -> Optional[tuple]:
    """(bot_token, chat_id), read by key, never the whole file. None if
    either is unset -- callers must treat that as "alerting not configured
    here", never crash a drift check over it."""
    env = dc.read_env_file(env_path)
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat_id = env.get("USER_TELEGRAM_ID")
    if not token or not chat_id:
        return None
    return token, chat_id


def format_message(report: dict) -> str:
    lines = [f"df-overseer drift check: DRIFT found ({report['generated_at']})"]
    for name, result in report["files"].items():
        if not result["clean"]:
            lines.append(f"- {name}: {result['drifted_count']}/{result['file_count']} file(s) drifted")
    live = report["live_tool_counts"]
    if not live["clean"]:
        for role, m in live["mismatches"].items():
            lines.append(f"- live tool count mismatch, {role}: offline {m['offline']} vs live {m['live']}")
    website = report["website"]
    if website["files"] is not None and not website["files"]["clean"]:
        lines.append(f"- relay-web: {website['files']['drifted_count']} file(s) drifted")
    gj = website.get("generated_json")
    if gj and not gj.get("clean", True):
        lines.append("- published tools.json role counts disagree with the repo")
    lines.append("Run `python scripts/drift_check.py` for the full report.")
    return "\n".join(lines)


def send_telegram_message(token: str, chat_id: str, text: str) -> None:
    url = TELEGRAM_API.format(token=token)
    payload = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        response.read()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="print the alert message; never send or require credentials")
    parser.add_argument("--env-file", default=None, help="override .env path (for tests)")
    args = parser.parse_args(argv)

    env_path = Path(args.env_file) if args.env_file else dc.ENV_PATH
    targets = dc.load_manifest()
    env = dc.read_env_file(env_path)
    selected = [name for name, t in targets.items() if not str(t.destination_root_raw).startswith("${")
                or env.get(t.destination_root_raw[2:-1])]
    runner = dc.SSHRunner(env_file=env_path if args.env_file else None)
    report = drift_check.build_report(targets, selected, env, runner)

    if report["clean"]:
        return 0

    message = format_message(report)
    if args.dry_run:
        print(message)
        return 1

    creds = read_telegram_credentials(env_path)
    if creds is None:
        print("drift found, but TELEGRAM_BOT_TOKEN/USER_TELEGRAM_ID are not both set -- not alerting.", file=sys.stderr)
        return 1
    token, chat_id = creds
    send_telegram_message(token, chat_id, message)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
