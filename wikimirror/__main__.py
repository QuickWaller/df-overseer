"""`python -m wikimirror pull|status` (docs/CONSULTANT-WIKI.md 5.1, 10).

    python -m wikimirror pull [--dry-run] [--out PATH] [--budget N] [--resume | --discard-staged]
    python -m wikimirror status [--db PATH]

Exit codes: 0 success, 1 failure (a named error is printed), 2 refused or bad usage.
`--out` and `--db` fall back to the DFWIKI_DB environment variable.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from typing import Callable, Mapping, Sequence

from wikimirror import pull as pullmod
from wikimirror.api import WikiApiError, WikiClient
from wikimirror.store import PromoteError, StoreError

ENV_DB = "DFWIKI_DB"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m wikimirror", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="command", required=True)
    pl = sub.add_parser("pull", help="full pull into a staged file, verify, promote atomically")
    pl.add_argument("--dry-run", action="store_true", help="enumerate and report; write nothing")
    pl.add_argument("--out", help=f"live database path (default: ${ENV_DB})")
    pl.add_argument("--budget", type=int, default=pullmod.DEFAULT_BUDGET,
                    help=f"per-run request budget (default {pullmod.DEFAULT_BUDGET})")
    g = pl.add_mutually_exclusive_group()
    g.add_argument("--resume", action="store_true", help="continue an interrupted staged pull")
    g.add_argument("--discard-staged", action="store_true", help="delete an interrupted staged pull and start clean")
    st = sub.add_parser("status", help="summarise a database; non-zero if missing or unreadable")
    st.add_argument("--db", help=f"database path (default: ${ENV_DB})")
    return p


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    client_factory: Callable[..., WikiClient] | None = None,
    stdout=None,
    stderr=None,
) -> int:
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    env = os.environ if env is None else env
    args = _parser().parse_args(argv)

    def say(msg: str) -> None:
        print(msg, file=out)

    def warn(msg: str) -> None:
        print(msg, file=err)

    if args.command == "status":
        db = args.db or env.get(ENV_DB)
        if not db:
            warn(f"status: give --db or set {ENV_DB}")
            return 2
        try:
            info = pullmod.database_status(db)
        except (StoreError, sqlite3.Error, OSError) as exc:
            warn(f"status: {type(exc).__name__}: {exc}")
            return 1
        say(json.dumps(info, indent=2, sort_keys=True))
        return 0

    # pull
    make_client = client_factory or (lambda **kw: WikiClient(**kw))
    if args.budget < 1:
        warn("pull: --budget must be at least 1")
        return 2
    if args.dry_run:
        try:
            client = make_client(max_requests=args.budget, env=env)
            plan = pullmod.plan_pull(client)
        except WikiApiError as exc:
            warn(f"dry-run failed: {type(exc).__name__}: {exc}")
            return 1
        say(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    outp = args.out or env.get(ENV_DB)
    if not outp:
        warn(f"pull: give --out or set {ENV_DB}")
        return 2
    try:
        pullmod.require_contact(env)
    except pullmod.ContactRequired as exc:
        warn(f"pull refused: {exc}")
        return 2
    try:
        client = make_client(max_requests=args.budget, env=env)
        result = pullmod.full_pull(
            client, outp, env=env, resume=args.resume, discard_staged=args.discard_staged,
            log=lambda m: warn(m),
        )
    except pullmod.StagedExists as exc:
        warn(f"pull refused: {exc}")
        return 2
    except (pullmod.PullError, WikiApiError, PromoteError, StoreError) as exc:
        reasons = getattr(exc, "reasons", None)
        warn(f"pull failed, live database untouched: {type(exc).__name__}: {exc}")
        if reasons:
            for r in reasons:
                warn(f"  - {r}")
        warn(f"the staged file (if any) is kept for --resume or --discard-staged: {pullmod.staged_path_for(outp)}")
        return 1
    except KeyboardInterrupt:
        warn("interrupted; the staged file is kept for --resume or --discard-staged")
        return 1
    say(pullmod.format_summary(result.report))
    say(f"promoted to {result.out}; report {result.report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
