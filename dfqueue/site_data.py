"""Project-wide data for the stream page's Agents, Tools and Forts views
(`handoffs/2026-10-02-site-agents-tools.md`). Unlike `dfqueue/feed.py`
(one fort's own queue), this module reads data that is the SAME across
every fort: the roster (`agents/ROSTER.yaml`), each enabled role's tool
allowlist (`dfmcp/roles.py`'s own loader, so a role's real, load-time
enforced tool list is what ships, never a hand-kept copy), each tool's
confidence (`gotchas/confidence.yaml`) and the known-gotchas store.

Three JSON documents, written once per export (not per fort) at the TOP
LEVEL of the published tree, a SIBLING of `forts/` (`web/stream/README.md`
"Multiple forts" already reserves this spot):

- `agents.json`  -- `build_agents_json`
- `tools.json`   -- `build_tools_json`
- `gotchas.json` -- `build_gotchas_json`, built from `load_gotchas_readonly`

## What this module does NOT do

- **It never writes to the gotcha store.** `load_gotchas_readonly` opens
  SQLite in read-only mode (`file:...?mode=ro`), the same pattern
  `dfqueue.feed.load_records_readonly` uses for the queue -- never
  `dfmcp.gotchas_store`'s own `_connect`, which can create or migrate the
  database on a bare open.
- **It never edits a gotcha's title or body.** The public projection
  withholds (`dfqueue.feed.find_unsafe_pattern`, the exact same safety net
  the chat feed uses) rather than editing or truncating -- a false
  positive costs one withheld entry, never a leak.
- **`call_excerpt` is operator-only, by construction.** `build_gotchas_json`
  with `public=True` never puts the key in the output dict at all (not
  merely `null`) -- see `test_site_data.py`'s own assertion for the exact
  shape this guarantees.
- **A general entry (no one tool) passes through as `tool: null`, never a
  placeholder string.** A sibling stream is relaxing
  `dfmcp/gotchas_store.py`'s `entries.tool` column from `NOT NULL` so a
  gotcha/vent about the work in general, not one tool, can be written; this
  reader does not wait on that landing (it already reads `tool` as-is,
  `None` included) and does not touch the store either way.
- **It does not touch `agents/`, `dfmcp/` or `dfqueue/schema.py`/`store.py`**,
  per this stream's handoff.

## Charter changes: git log on the workstation, with a committed fallback

The handoff asks for "say which you chose and why." Chosen: **both**.
`charter_changes_from_git` shells out to `git log --follow` against a
role's `role.md`, which only works where a `.git` directory exists (the
workstation, not a deployed VM checkout built from `git archive` -- this
repo's CLAUDE.md "traps" section is explicit that a VM checkout carries no
git history at all). `build_agents_json` tries that first and falls back to
`CHARTER_CHANGES_FALLBACK_PATH`, a committed JSON snapshot
(`dfqueue/charter_changes.json`) generated the same way and checked in, for
the case a publisher runs somewhere `git log` cannot reach. Regenerate the
committed snapshot with this module's own CLI (`python -m
dfqueue.site_data refresh-charter-changes`) whenever a charter changes.
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from dfqueue.feed import build_items, find_unsafe_pattern
from dfqueue.schema import (
    ANSWER,
    ASK,
    ASK_ROLES,
    ESCALATION,
    PASS,
    PROPOSAL,
    RULING,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / "agents"
CHARTER_CHANGES_FALLBACK_PATH = REPO_ROOT / "dfqueue" / "charter_changes.json"

# ---------------------------------------------------------------------------
# Small, generic lookup tables -- data, not per-role branches (CLAUDE.md
# "Tools must be generalisable": the same discipline applies to this reader,
# not only to the game-side tools it describes).
# ---------------------------------------------------------------------------

#: `agents/ROSTER.yaml`'s `kind` (actor/advisor/system) to a human phrase.
#: Generic over `kind`, never over a role name.
KIND_LABELS = {
    "actor": "Decides and acts",
    "advisor": "Advises",
    "system": "Code, not an agent",
}

#: A role of kind "system" displays as "System", not its own name (matches
#: the mockup's conductor card) -- keyed by `kind`, not by role id.
KIND_DISPLAY_NAME_OVERRIDE = {
    "system": "System",
}

_BRAND_WORDS = {"deepseek": "DeepSeek", "claude": "Claude", "anthropic": "Anthropic"}
_VERSION_WORD_RE = re.compile(r"^v\d")


def humanize_model_id(model_id: Optional[str]) -> Optional[str]:
    """"deepseek/deepseek-v4-pro" -> "DeepSeek V4 Pro". `None` stays `None`
    (the conductor's `model: null`, meaning no model at all, never "none")."""
    if not model_id:
        return None
    tail = model_id.split("/")[-1]
    words = []
    for tok in tail.split("-"):
        low = tok.lower()
        if low in _BRAND_WORDS:
            words.append(_BRAND_WORDS[low])
        elif _VERSION_WORD_RE.match(low):
            words.append("V" + low[1:])
        else:
            words.append(tok.capitalize())
    return " ".join(words)


#: Tool-id-prefix groupings for the Tools view ("Areas are data, not
#: branches" -- handoff item 3). A prefix absent here lands in "Other"
#: rather than erroring, so a brand-new tool family never crashes the build.
AREAS: List[tuple] = [
    ("Building and rooms", ["building", "construction", "workshop", "well", "farm", "zone", "blueprint", "surface", "trees"]),
    ("Digging and space", ["diggable", "openarea", "landmarks", "connectivity", "chokepoints", "breach"]),
    ("Supply and labor", ["orders", "workjob", "stocks", "stockpile", "labor", "nobles"]),
    ("Watching the fort", ["overview", "diff", "vitals", "threat", "stuckjobs", "ledger", "series", "fort", "announcement-levels", "clock"]),
    ("Queue and knowledge", ["queue", "gotchas", "knowledge", "doctrine", "web", "dfhack"]),
]


def area_of(tool_id: str) -> str:
    prefix = tool_id.split(".")[0]
    for name, prefixes in AREAS:
        if prefix in prefixes:
            return name
    return "Other"


# ---------------------------------------------------------------------------
# agents.json
# ---------------------------------------------------------------------------


def _load_roster_manifest(agents_dir: Path = AGENTS_DIR) -> dict:
    with (agents_dir / "ROSTER.yaml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def charter_changes_from_git(role_dir: str, *, repo_root: Path = REPO_ROOT) -> Optional[List[List[str]]]:
    """[[date, message], ...], newest first, from `git log --follow` on
    `agents/<role_dir>/role.md` -- the real commit history, never invented.
    `None` (not `[]`) when git itself is unavailable or this is not a git
    checkout at all (a `git archive` deploy, CLAUDE.md's own "traps"
    section), so the caller can tell "no history reachable here" apart from
    "this charter has never changed"."""
    role_md = f"agents/{role_dir}/role.md"
    try:
        result = subprocess.run(
            ["git", "log", "--follow", "--date=short", "--format=%ad\x1f%s", "--", role_md],
            cwd=repo_root, capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    changes = []
    for line in result.stdout.splitlines():
        if "\x1f" not in line:
            continue
        date, _, message = line.partition("\x1f")
        changes.append([date, message])
    return changes


def _charter_changes(role_dir: str, *, repo_root: Path = REPO_ROOT, fallback_path: Path = CHARTER_CHANGES_FALLBACK_PATH) -> List[List[str]]:
    live = charter_changes_from_git(role_dir, repo_root=repo_root)
    if live is not None:
        return live
    try:
        with fallback_path.open(encoding="utf-8") as fh:
            snapshot = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    return snapshot.get(role_dir, [])


def generate_charter_changes_snapshot(agents_dir: Path = AGENTS_DIR, repo_root: Path = REPO_ROOT) -> Dict[str, List[List[str]]]:
    """Every role's charter history, for the committed fallback file. Rolls
    disabled/planned roles in too (their `role.md` has history even while
    not enabled) by reading `ROSTER.yaml` directly rather than only the
    enabled subset `dfmcp.roles.load_roster` would resolve."""
    manifest = _load_roster_manifest(agents_dir)
    snapshot = {}
    for role_name, entry in (manifest.get("roles") or {}).items():
        if not isinstance(entry, dict):
            continue
        role_dir = entry.get("dir", role_name)
        changes = charter_changes_from_git(role_dir, repo_root=repo_root)
        if changes is not None:
            snapshot[role_dir] = changes
    return snapshot


def _role_md_text(role_dir: str, agents_dir: Path = AGENTS_DIR) -> str:
    path = agents_dir / role_dir / "role.md"
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _load_model(role_dir: str, agents_dir: Path = AGENTS_DIR) -> Optional[str]:
    path = agents_dir / role_dir / "model.yaml"
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    return doc.get("model")


def _default_registry():
    """The same merged registry `dfmcp/tests/test_roles.py` builds: every
    native tool module's ids folded in alongside `scripts/dfhack/TOOLS.yaml`,
    so `dfmcp.roles.load_roster` can resolve the real roster. Imported
    lazily so a caller that already has a registry (or roster) need not pay
    for building one twice."""
    from dfmcp.doctrine_tools import NATIVE_TOOLS as DOCTRINE_NATIVE_TOOLS
    from dfmcp.gotchas_tools import NATIVE_TOOLS as GOTCHAS_NATIVE_TOOLS
    from dfmcp.knowledge_tools import NATIVE_TOOLS as KNOWLEDGE_NATIVE_TOOLS
    from dfmcp.queue_tools import NATIVE_TOOLS as QUEUE_NATIVE_TOOLS
    from dfmcp.registry import load_registry
    from dfmcp.series_tools import NATIVE_TOOLS as SERIES_NATIVE_TOOLS

    return load_registry(native_tools={
        **QUEUE_NATIVE_TOOLS, **DOCTRINE_NATIVE_TOOLS, **SERIES_NATIVE_TOOLS,
        **GOTCHAS_NATIVE_TOOLS, **KNOWLEDGE_NATIVE_TOOLS,
    })


def _default_roster(registry=None, agents_dir: Path = AGENTS_DIR):
    from dfmcp.roles import load_roster

    return load_roster(registry or _default_registry(), agents_dir=agents_dir)


# ---- track record (queue records -> per-role counts) -----------------------


def _track_records(records: List[dict]) -> dict:
    proposals_by_role: Counter = Counter()
    passes_by_role: Counter = Counter()
    asks_by_role: Counter = Counter()
    answers_by_role: Counter = Counter()
    escalations_by_role: Counter = Counter()
    proposal_role_by_id: Dict[str, str] = {}
    ruling_decisions_by_proposer: Dict[str, Counter] = defaultdict(Counter)
    ruling_decisions_overall: Counter = Counter()
    rulings_total = 0

    for r in records:
        kind = r.get("kind")
        role = r.get("role")
        if kind == PROPOSAL:
            proposals_by_role[role] += 1
            rid = r.get("id")
            if rid:
                proposal_role_by_id[rid] = role
        elif kind == PASS:
            passes_by_role[role] += 1
        elif kind == ASK:
            asks_by_role[role] += 1
        elif kind == ANSWER:
            answers_by_role[role] += 1
        elif kind == ESCALATION:
            escalations_by_role[role] += 1
        elif kind == RULING:
            rulings_total += 1
            decision = r.get("decision")
            if decision:
                ruling_decisions_overall[decision] += 1
                proposer = proposal_role_by_id.get(r.get("proposal_id"))
                if proposer:
                    ruling_decisions_by_proposer[proposer][decision] += 1

    return {
        "proposals_by_role": proposals_by_role,
        "passes_by_role": passes_by_role,
        "asks_by_role": asks_by_role,
        "answers_by_role": answers_by_role,
        "escalations_by_role": escalations_by_role,
        "ruling_decisions_by_proposer": ruling_decisions_by_proposer,
        "ruling_decisions_overall": ruling_decisions_overall,
        "rulings_total": rulings_total,
    }


def _role_record(role: str, kind: str, is_sole_writer: bool, tr: dict) -> dict:
    """This role's own track-record numbers. Only what the queue actually
    recorded: a graded-prediction hit rate would need the `predictions`
    table (a separate read this stream does not build -- see the handoff's
    Result section), so it is simply absent here, never guessed at."""
    if is_sole_writer:
        overall = tr["ruling_decisions_overall"]
        return {
            "ruled": tr["rulings_total"],
            "accepted": overall.get("accept", 0),
            "rejected": overall.get("reject", 0),
            "deferred": overall.get("defer", 0),
            "asks": tr["asks_by_role"].get(role, 0),
        }
    if role in ASK_ROLES:  # a proposing advisor (architect, quartermaster)
        dec = tr["ruling_decisions_by_proposer"].get(role, Counter())
        proposals = tr["proposals_by_role"].get(role, 0)
        if not proposals and not dec:
            return {}
        return {
            "proposals": proposals,
            "accepted": dec.get("accept", 0),
            "rejected": dec.get("reject", 0),
            "deferred": dec.get("defer", 0),
        }
    answers = tr["answers_by_role"].get(role, 0)
    if answers:
        return {"answers": answers}
    return {}


def _spokes(roster, tr: dict) -> dict:
    spokes: Dict[str, dict] = {}
    for role, perms in roster.roles.items():
        if role == roster.sole_writer:
            continue
        if perms.kind == "system":
            spokes[role] = {"out": ["wakes", None]}  # wake-ups: slice S2, never recorded yet
            continue
        answers = tr["answers_by_role"].get(role, 0)
        if answers or role == "consultant":
            asks_total = sum(tr["asks_by_role"].values())
            spokes[role] = {"out": ["answers", answers], "in": ["asks", asks_total]}
            continue
        proposals = tr["proposals_by_role"].get(role, 0)
        dec = tr["ruling_decisions_by_proposer"].get(role, Counter())
        rulings = sum(dec.values())
        if proposals or rulings:
            spokes[role] = {"out": ["proposals", proposals], "in": ["rulings", rulings]}
    return spokes


def _recent_lines(records: List[dict], role: str, *, limit: int = 60) -> List[dict]:
    """This role's own public lines, oldest first (the page groups by game
    day itself, the same way the board does). Reuses `dfqueue.feed`'s own
    item builder and safety net rather than re-deriving either."""
    items = build_items(records, public=True)
    mine = [it for it in items if it.get("role") == role]
    lines = []
    for it in mine[-limit:]:
        if it.get("withheld"):
            text = "(one message withheld)"
        elif it.get("text"):
            text = it["text"]
        else:
            continue
        lines.append({"game_date": it.get("game_date"), "text": text, "type": it.get("type")})
    return lines


def build_agents_json(
    records: List[dict],
    *,
    agents_dir: Path = AGENTS_DIR,
    repo_root: Path = REPO_ROOT,
    registry=None,
    roster=None,
) -> dict:
    """The whole Agents page's data: roster, models, tool lists (from the
    SAME loader `dfmcp` enforces at runtime, never a hand-kept copy),
    charters and their git history, track record and recent lines from the
    current fort's queue, and spoke counts for the hub-and-spoke map."""
    manifest = _load_roster_manifest(agents_dir)
    sole_writer = manifest.get("sole_writer")
    roster = roster or _default_roster(registry, agents_dir)
    tr = _track_records(records)

    role_order: List[str] = []
    planned_order: List[str] = []
    roles_out: Dict[str, dict] = {}

    for role_name, entry in (manifest.get("roles") or {}).items():
        if not isinstance(entry, dict):
            continue
        enabled = bool(entry.get("enabled"))
        role_dir = entry.get("dir", role_name)
        kind = entry.get("kind", "advisor")
        display_name = KIND_DISPLAY_NAME_OVERRIDE.get(kind, role_name.capitalize())
        perms = roster.roles.get(role_name) if enabled else None
        tool_ids = sorted(set(perms.read) | set(perms.write)) if perms else []
        model_id = _load_model(role_dir, agents_dir) if enabled else None

        role_record: dict = {
            "name": display_name,
            "kind": kind,
            "kind_label": KIND_LABELS.get(kind, kind),
            "enabled": enabled,
            "planned": not enabled,
            "summary": entry.get("summary", ""),
            "blocked_on": entry.get("blocked_on"),
            "model": model_id,
            "model_label": humanize_model_id(model_id) if kind != "system" else ("Code, no model" if enabled else None),
            "tools": tool_ids,
            "tool_count": len(tool_ids),
            "is_sole_writer": role_name == sole_writer,
            "charter_md": _role_md_text(role_dir, agents_dir),
            "charter_changes": _charter_changes(role_dir, repo_root=repo_root),
            "record": _role_record(role_name, kind, role_name == sole_writer, tr) if enabled else {},
        }
        roles_out[role_name] = role_record
        (role_order if enabled else planned_order).append(role_name)

    return {
        "generated_at": _now_iso(),
        "sole_writer": sole_writer,
        "role_order": role_order,
        "planned_order": planned_order,
        "roles": roles_out,
        "spokes": _spokes(roster, tr),
    }


# ---------------------------------------------------------------------------
# tools.json
# ---------------------------------------------------------------------------


def _tool_description(tool, any_role: Optional[str]) -> str:
    """`Tool.description` for a TOOLS.yaml-backed tool; a native tool
    (`dfmcp.queue_tools.NativeTool` and its siblings) has no such property,
    only `describe(role)` -- its first element is the description, the
    schema dict discarded. `any_role` is any role actually holding the
    tool (its schema does not vary by caller for any of today's native
    tools); if none holds it, there is nothing meaningful to describe."""
    description = getattr(tool, "description", None)
    if description:
        return description
    describe = getattr(tool, "describe", None)
    if describe and any_role:
        try:
            text, _schema = describe(any_role)
            return text or ""
        except Exception:
            return ""
    return ""


def build_tools_json(registry=None, roster=None, *, agents_dir: Path = AGENTS_DIR) -> dict:
    from dfmcp.confidence import load_confidence

    registry = registry or _default_registry()
    roster = roster or _default_roster(registry, agents_dir)
    confidence = load_confidence()

    tools = []
    for tool_id in sorted(registry.ids()):
        tool = registry.get(tool_id)
        roles_with = sorted(r for r, perms in roster.roles.items() if perms.allows(tool_id))
        level = confidence.lookup(tool_id)
        tools.append({
            "id": tool_id,
            "write": bool(getattr(tool, "mutates", False)),
            "description": _tool_description(tool, roles_with[0] if roles_with else None),
            "area": area_of(tool_id),
            "roles": roles_with,
            "confidence": {"level": level.level, "note": level.note},
        })
    return {"generated_at": _now_iso(), "tools": tools, "areas": [a for a, _ in AREAS]}


# ---------------------------------------------------------------------------
# gotchas.json
# ---------------------------------------------------------------------------


def load_gotchas_readonly(db_path: str | Path) -> List[dict]:
    """Every entry in a live gotcha store, oldest first, opened strictly
    read-only (`file:...?mode=ro`) -- the same reasoning and the same
    pattern as `dfqueue.feed.load_records_readonly`: this reader must never
    create, migrate or write the store, unlike `dfmcp.gotchas_store`'s own
    `_connect`."""
    uri = f"file:{Path(db_path).resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, tool, kind, list, title, body, status, created_at, "
            "written_by_role, run_id, call_excerpt FROM entries ORDER BY rowid ASC"
        ).fetchall()
        entries = [dict(r) for r in rows]
        ids = [e["id"] for e in entries]
        outcomes: Dict[str, list] = {i: [] for i in ids}
        if ids:
            placeholders = ",".join("?" * len(ids))
            orows = conn.execute(
                f"SELECT entry_id, at, role, run_id, result, note FROM outcomes "
                f"WHERE entry_id IN ({placeholders}) ORDER BY seq ASC",
                ids,
            ).fetchall()
            for r in orows:
                outcomes[r["entry_id"]].append({
                    "at": r["at"], "role": r["role"], "run_id": r["run_id"],
                    "result": r["result"], "note": r["note"],
                })
        for e in entries:
            e["outcomes"] = outcomes[e["id"]]
        return entries
    finally:
        conn.close()


def _safe_text(text: Optional[str]) -> tuple:
    """(text, withheld) -- `dfqueue.feed.find_unsafe_pattern` applied the
    same conservative way the chat feed applies it: withhold, never edit."""
    if text is None:
        return None, False
    if find_unsafe_pattern(text) is not None:
        return None, True
    return text, False


def build_gotchas_json(entries: List[dict], *, public: bool) -> List[dict]:
    """The public projection withholds an unsafe title/body and NEVER
    carries `call_excerpt` at all (not merely `null` -- the key itself is
    absent, same "allowlist, not a redaction" discipline
    `dfqueue/feed.py`'s `PUBLIC_ITEM_FIELDS` assertion already uses). The
    operator projection is the trusted internal view: raw text, plus
    `call_excerpt` and `run_id`."""
    out = []
    for e in entries:
        if public:
            title, t_withheld = _safe_text(e.get("title"))
            body, b_withheld = _safe_text(e.get("body"))
            withheld = t_withheld or b_withheld
        else:
            title, body, withheld = e.get("title"), e.get("body"), False
        item = {
            "id": e["id"],
            "tool": e.get("tool"),
            "kind": e.get("kind"),
            "list": e["list"],
            "title": title,
            "body": body,
            "withheld": withheld,
            "status": e["status"],
            "created_at": e["created_at"],
            "by": e.get("written_by_role"),
            "outcomes": e.get("outcomes", []),
        }
        if not public:
            item["call_excerpt"] = e.get("call_excerpt")
            item["run_id"] = e.get("run_id")
        out.append(item)
    return out


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=None),
        encoding="utf-8",
    )


def write_site_data(
    root_dir: str | Path, *, agents_json: dict, tools_json: dict,
    gotchas_entries: List[dict], public: bool,
) -> None:
    """`agents.json`, `tools.json` and `gotchas.json` at the TOP of a
    projection root (`<root>/`, a sibling of `<root>/forts/` and
    `<root>/forts.json` -- `web/stream/README.md`'s "Multiple forts"
    section already reserves this spot). `agents.json`/`tools.json` carry
    nothing sensitive, so the same payload goes to both projections;
    `gotchas.json` is projected per `public` (see `build_gotchas_json`)."""
    root_dir = Path(root_dir)
    _write_json(root_dir / "agents.json", agents_json)
    _write_json(root_dir / "tools.json", tools_json)
    _write_json(root_dir / "gotchas.json", build_gotchas_json(gotchas_entries, public=public))


# ---------------------------------------------------------------------------
# CLI: regenerate the committed charter-changes fallback snapshot
# ---------------------------------------------------------------------------


def _main(argv: List[str]) -> int:
    if len(argv) != 1 or argv[0] != "refresh-charter-changes":
        print("usage: python -m dfqueue.site_data refresh-charter-changes", file=sys.stderr)
        return 2
    snapshot = generate_charter_changes_snapshot()
    CHARTER_CHANGES_FALLBACK_PATH.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {CHARTER_CHANGES_FALLBACK_PATH} ({len(snapshot)} role(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
