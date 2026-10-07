"""Template metadata loader: `provides` and `requires` of
`blueprints/templates/*.yaml`, read by the server
(`research/2026-10-07-planner-design.md` 2.3, F-22).

No server code read the template metadata before this: `blueprint.plan` reads
the `.csv` on the VM. The fort plan needs two facts per template, both
declared in its yaml and nothing else read here:

- `provides`: a list of `{signal, units}`, what one built copy adds to a plan
  target's signal (`units` defaults to 1). The bedroom cell provides one
  `zones."Bedroom".furnished`.
- `requires`: a list of item names (`bed`), the furniture the template needs
  that someone must make. The plan derives a target's inputs from these, never
  from anything the Planner writes, so a plan cannot forget the bed (F-1).

Pure data and files: no DFHack, no queue. `TEMPLATES_DIR` can be pointed at a
temp directory by a test. When more than one revision of a template provides
the same signal, the highest revision serves.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO_ROOT / "blueprints" / "templates"


def _entries(provides) -> list[dict]:
    out = []
    for item in provides or []:
        if isinstance(item, dict) and isinstance(item.get("signal"), str):
            units = item.get("units", 1)
            if isinstance(units, bool) or not isinstance(units, (int, float)) or units <= 0:
                continue
            out.append({"signal": item["signal"], "units": units})
    return out


def load_templates(directory: Path | None = None) -> list[dict]:
    """Every template's `{id, revision, provides, requires, file}`, newest
    revision first within an id. A file that is not a mapping with an `id` is
    skipped; a malformed `provides` entry is dropped, never guessed at."""
    d = Path(directory) if directory is not None else Path(TEMPLATES_DIR)
    out = []
    if not d.is_dir():
        return out
    for path in sorted(d.glob("*.yaml")):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(doc, dict) or not isinstance(doc.get("id"), str):
            continue
        rev = doc.get("revision")
        out.append({
            "id": doc["id"],
            "revision": rev if isinstance(rev, int) and not isinstance(rev, bool) else 0,
            "provides": _entries(doc.get("provides")),
            "requires": [r for r in (doc.get("requires") or []) if isinstance(r, str) and r],
            "file": path.name,
        })
    out.sort(key=lambda t: (t["id"], -t["revision"]))
    return out


def serving(signal: str, directory: Path | None = None) -> dict | None:
    """The template that provides `signal` (highest revision), as
    `{id, revision, units, requires}`, or `None` when no template does."""
    best = None
    for t in load_templates(directory):
        for p in t["provides"]:
            if p["signal"] == signal and (best is None or t["revision"] > best["revision"]):
                best = {
                    "id": t["id"], "revision": t["revision"], "units": p["units"],
                    "requires": list(t["requires"]),
                }
    return best
