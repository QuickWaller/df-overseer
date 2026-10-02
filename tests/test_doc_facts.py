"""Fails when a doc states a per-role tool count that disagrees with what
this repo's own registry + roster would actually produce right now.

Scope, deliberately narrow: this only checks the one sentence shape this
repo has used for a CURRENT, as-of-now count summary --
"Role tool lists (...): **overseer N, architect N, ...**". It does NOT flag
every number near the word "tool" anywhere in the repo: agents/*/role.md
and the decision register are full of legitimate, explicitly DATED
historical claims ("23 tools as of 2026-09-23", quartermaster/role.md) that
are supposed to stay exactly what they said that day, not track the live
count forever -- treating those as drift would be wrong, not useful. If a
future doc adds another "as of right now" count sentence in a different
shape, extend ROLE_COUNT_SENTENCE / the files list below rather than trying
to make this generic over arbitrary prose.

As of 2026-10-02, CLAUDE.md no longer hand-writes the numbers itself: its
status block points at `docs/STATE.md`'s generated "Per-role tool counts"
section instead (one source of truth, never hand-copied out of date). This
test therefore no longer requires the old sentence shape to appear anywhere
-- finding none is a pass, not a failure -- but it keeps scanning
CLAUDE.md, Working.md and every role charter (agents/*/role.md) for that
exact shape, so if one of them ever regresses to a hand-written count (or a
charter picks up the undated version of the sentence), a wrong number still
fails the build. It separately checks that CLAUDE.md's own pointer sentence
actually names `docs/STATE.md`, so the pointer itself cannot silently
disappear.

Run as part of the normal suite (`python -m pytest`); this is intentionally
cheap (parses a handful of small files, imports the registry once) so it is
never a reason to skip it.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT))

import drift_check  # noqa: E402

# Matches "Role tool lists ... : **overseer 87, architect 52, ...**" whether
# or not there is an "(aside in parens)" between "lists" and the colon, and
# regardless of exactly how many roles are listed.
ROLE_COUNT_SENTENCE = re.compile(
    r"Role tool lists[^:]*:\s*\*\*([^*]+)\*\*", re.IGNORECASE,
)
ROLE_NUMBER = re.compile(r"([a-z]+)\s+(\d+)")

FILES_TO_CHECK = [
    REPO_ROOT / "CLAUDE.md",
    REPO_ROOT / "Working.md",
    *sorted((REPO_ROOT / "agents").glob("*/role.md")),
]


def extract_claimed_counts(text: str) -> dict:
    """{role: claimed_count} for every "Role tool lists" sentence found."""
    claims = {}
    for match in ROLE_COUNT_SENTENCE.finditer(text):
        body = match.group(1)
        for role, count in ROLE_NUMBER.findall(body):
            claims[role.lower()] = int(count)
    return claims


def test_doc_role_tool_counts_match_the_registry():
    """Passes with nothing found (CLAUDE.md now points at docs/STATE.md instead of
    hand-writing numbers); fails if any scanned doc states a wrong one."""
    actual = drift_check.offline_role_tool_counts()
    mismatches = []
    for path in FILES_TO_CHECK:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        claims = extract_claimed_counts(text)
        for role, claimed in claims.items():
            if role not in actual:
                mismatches.append(
                    f"{path.name} claims a count for role {role!r}, which is not an "
                    f"enabled role in agents/ROSTER.yaml (known roles: {sorted(actual)})"
                )
                continue
            if actual[role] != claimed:
                mismatches.append(
                    f"{path.name} claims {role} has {claimed} tool(s); the repo's own "
                    f"registry + roster gives {actual[role]}. Update the doc's \"Role "
                    f"tool lists\" sentence (or, better, point it at docs/STATE.md's "
                    f"generated count instead of a hand-written number)."
                )
    assert not mismatches, "\n" + "\n".join(mismatches)


def test_claude_md_points_at_state_md_for_tool_counts():
    """CLAUDE.md's status block must not regress to hand-writing the per-role
    counts: it should point at docs/STATE.md's generated section instead."""
    text = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8", errors="replace")
    m = ROLE_COUNT_SENTENCE.search(text)
    assert m is not None, "CLAUDE.md's \"Role tool lists\" sentence is missing entirely"
    assert "STATE.md" in m.group(1), (
        "CLAUDE.md's \"Role tool lists\" sentence no longer points at docs/STATE.md"
    )
    assert not ROLE_NUMBER.findall(m.group(1)), (
        "CLAUDE.md's \"Role tool lists\" sentence hand-writes numbers again instead of "
        "pointing at docs/STATE.md's generated count"
    )


def test_extract_claimed_counts_parses_both_known_phrasings():
    claude_style = (
        "Role tool lists (read plus write, measured live 2026-09-30 over a real "
        "MCP client): **overseer 87, architect 52, consultant 29, quartermaster 24, "
        "conductor 16**."
    )
    working_style = "Role tool lists (read plus write): **overseer 79, architect 49**."
    assert extract_claimed_counts(claude_style) == {
        "overseer": 87, "architect": 52, "consultant": 29, "quartermaster": 24, "conductor": 16,
    }
    assert extract_claimed_counts(working_style) == {"overseer": 79, "architect": 49}
