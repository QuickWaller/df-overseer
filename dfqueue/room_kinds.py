"""Room kind data: loader, validator and Lua renderer for
`blueprints/room-kinds.yaml` (register 2026-10-08, D1, D2, D5, D7).

One entry per room kind: shape generator, size range, required furniture,
access rule, privacy, door policy. The guest has no YAML parser, so
`render_lua()` emits `scripts/dfhack/df-overseer-roomkinds.lua`, which the
placement gate in df-overseer-blueprint.lua and the circulation graph read.
A test fails when the committed Lua differs from `render_lua()`.

    python -m dfqueue.room_kinds --check        # validate, exit 1 on problems
    python -m dfqueue.room_kinds --write-lua    # regenerate the Lua module

Pure data and files: no DFHack, no queue.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
KINDS_FILE = REPO_ROOT / "blueprints" / "room-kinds.yaml"
TEMPLATES_DIR = REPO_ROOT / "blueprints" / "templates"
LUA_FILE = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-roomkinds.lua"

KIND_ID = re.compile(r"^[a-z][a-z0-9_]*$")
BASES = {"game", "template", "prior", "user"}
DOOR_DEFAULTS = {"none", "door"}


def load(path: Path | None = None) -> dict:
    return yaml.safe_load(Path(path or KINDS_FILE).read_text(encoding="utf-8"))


def _range_problem(label: str, v) -> str | None:
    ok = (isinstance(v, list) and len(v) == 2
          and all(isinstance(x, int) and not isinstance(x, bool) and x >= 1 for x in v)
          and v[0] <= v[1])
    return None if ok else f"{label} must be [min, max] with 1 <= min <= max"


def normalise_access(access) -> dict | None:
    """`corridor` | `any` | `{opens_onto: [kinds]}` as `{mode, kinds}`, else None."""
    if access in ("corridor", "any"):
        return {"mode": access, "kinds": []}
    if (isinstance(access, dict) and set(access) == {"opens_onto"}
            and isinstance(access["opens_onto"], list) and access["opens_onto"]
            and all(isinstance(k, str) for k in access["opens_onto"])):
        return {"mode": "opens_onto", "kinds": list(access["opens_onto"])}
    return None


def validate(doc: dict, templates_dir: Path | None = None) -> list[str]:
    """Every problem found, as sentences; empty means valid."""
    out: list[str] = []
    if not isinstance(doc, dict):
        return ["room-kinds file is not a mapping"]
    gens = doc.get("shape_generators")
    gen_names: set[str] = set()
    if not isinstance(gens, list) or len(gens) != 6:
        out.append("shape_generators must list exactly the six generators of D1")
    else:
        gen_names = {g for g in gens if isinstance(g, str)}
        if len(gen_names) != 6:
            out.append("shape_generators must be six distinct names")
    grounds = doc.get("door_grounds")
    ground_names = set(grounds) if isinstance(grounds, list) else set()
    if not ground_names:
        out.append("door_grounds must be a non-empty list")
    kinds = doc.get("kinds")
    if not isinstance(kinds, dict) or not kinds:
        return out + ["kinds must be a non-empty mapping"]
    zone_primary: dict[str, str] = {}
    for kid, k in kinds.items():
        p = f"kind '{kid}': "
        if not isinstance(kid, str) or not KIND_ID.match(kid):
            out.append(p + "id must be snake_case")
        if not isinstance(k, dict):
            out.append(p + "entry must be a mapping")
            continue
        zk = k.get("zone_kind")
        if zk is not None and not isinstance(zk, str):
            out.append(p + "zone_kind must be a string or null")
        if isinstance(zk, str) and "location" not in k:
            if zk in zone_primary:
                out.append(p + f"zone_kind '{zk}' is already the primary zone of '{zone_primary[zk]}' "
                           "(a second kind on one zone needs a `location`)")
            zone_primary[zk] = kid
        if k.get("shape_generator") not in gen_names:
            out.append(p + "shape_generator must be one of shape_generators")
        size = k.get("size")
        if not isinstance(size, dict):
            out.append(p + "size must be a mapping")
        else:
            for f in ("interior_width", "interior_depth"):
                bad = _range_problem(p + f"size.{f}", size.get(f))
                if bad:
                    out.append(bad)
        rf = k.get("required_furniture")
        if not isinstance(rf, list):
            out.append(p + "required_furniture must be a list")
        else:
            for item in rf:
                if (not isinstance(item, dict) or not isinstance(item.get("item"), str)
                        or isinstance(item.get("count"), bool) or not isinstance(item.get("count"), int)
                        or item["count"] < 1 or item.get("basis") not in BASES):
                    out.append(p + "each required_furniture entry needs item, count >= 1 and basis "
                               f"in {sorted(BASES)}")
        if not isinstance(k.get("private"), bool):
            out.append(p + "private must be true or false")
        if normalise_access(k.get("access")) is None:
            out.append(p + "access must be corridor, any, or {opens_onto: [kinds]}")
        dp = k.get("door_policy")
        if (not isinstance(dp, dict) or dp.get("default") not in DOOR_DEFAULTS
                or not (dp.get("ground") is None or dp.get("ground") in ground_names)):
            out.append(p + "door_policy needs default none|door and ground null or a listed door ground")
        elif dp["default"] == "door" and dp["ground"] is None:
            out.append(p + "a default door needs a ground (a door must be justified)")
        if not isinstance(k.get("basis"), str) or not k["basis"].strip():
            out.append(p + "basis (provenance sentence) is required")
    for kid, k in kinds.items():
        acc = normalise_access(k.get("access")) if isinstance(k, dict) else None
        for other in (acc or {}).get("kinds", []):
            if other not in kinds:
                out.append(f"kind '{kid}': access names unknown kind '{other}'")
    out.extend(template_problems(doc, templates_dir))
    return out


def template_kinds(templates_dir: Path | None = None) -> dict[str, str | None]:
    """Template id -> its `kind:` (None when missing), across all revisions."""
    d = Path(templates_dir or TEMPLATES_DIR)
    out: dict[str, str | None] = {}
    for path in sorted(d.glob("*.yaml")):
        try:
            t = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if isinstance(t, dict) and isinstance(t.get("id"), str):
            k = t.get("kind")
            if out.get(t["id"]) in (None, k):
                out[t["id"]] = k if isinstance(k, str) else None
            else:
                out[t["id"]] = "<conflicting>"
    return out


def template_problems(doc: dict, templates_dir: Path | None = None) -> list[str]:
    kinds = doc.get("kinds") if isinstance(doc, dict) else None
    kinds = kinds if isinstance(kinds, dict) else {}
    out = []
    for tid, k in template_kinds(templates_dir).items():
        if k is None:
            out.append(f"template '{tid}' has no `kind:`")
        elif k not in kinds:
            out.append(f"template '{tid}' names kind '{k}', which room-kinds.yaml does not define")
    return out


# ---------------------------------------------------------------------------
# Lua rendering
# ---------------------------------------------------------------------------

def _lua(v, indent: int = 0) -> str:
    pad = "  " * (indent + 1)
    end = "  " * indent
    if v is None:
        return "nil"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'
    if isinstance(v, list):
        if not v:
            return "{}"
        return "{\n" + "".join(f"{pad}{_lua(x, indent + 1)},\n" for x in v) + end + "}"
    if isinstance(v, dict):
        items = [(k, x) for k, x in sorted(v.items(), key=lambda kv: str(kv[0])) if x is not None]
        if not items:
            return "{}"
        return "{\n" + "".join(f"{pad}[{_lua(str(k))}] = {_lua(x, indent + 1)},\n" for k, x in items) + end + "}"
    raise TypeError(type(v))


def lua_data(doc: dict, templates_dir: Path | None = None) -> dict:
    kinds = {}
    for kid, k in doc["kinds"].items():
        acc = normalise_access(k["access"])
        kinds[kid] = {
            "zone_kind": k.get("zone_kind"),
            "location": k.get("location"),
            "shape_generator": k["shape_generator"],
            "private": k["private"],
            "access": acc,
            "door_default": k["door_policy"]["default"],
            "door_ground": k["door_policy"]["ground"],
            "interior_width": k["size"]["interior_width"],
            "interior_depth": k["size"]["interior_depth"],
            "required_furniture": [{"item": f["item"], "count": f["count"]} for f in k["required_furniture"]],
        }
    zone_to_kind = {k["zone_kind"]: kid for kid, k in doc["kinds"].items()
                    if k.get("zone_kind") and "location" not in k}
    tmpl = {tid: k for tid, k in template_kinds(templates_dir).items() if k in doc["kinds"]}
    return {"kinds": kinds, "zone_to_kind": zone_to_kind, "template_kind": tmpl}


def render_lua(doc: dict | None = None, templates_dir: Path | None = None) -> str:
    doc = doc if doc is not None else load()
    data = lua_data(doc, templates_dir)
    head = (
        "--@module = true\n"
        "-- GENERATED from blueprints/room-kinds.yaml and blueprints/templates/*.yaml by\n"
        "--   python -m dfqueue.room_kinds --write-lua\n"
        "-- Do not edit by hand: a test fails when this differs from the YAML. The guest\n"
        "-- has no YAML parser, which is the only reason this file exists.\n"
        "--\n"
        "-- Room kind data (register 2026-10-08, D1/D2/D5/D7): per kind its shape\n"
        "-- generator, size range, required furniture, access rule, privacy and door\n"
        "-- policy, keyed by the kind id the templates' `kind:` names. Read by\n"
        "-- df-overseer-blueprint.lua (the placement gate) and df-overseer-circulation.lua.\n"
        "-- Reqscript only; no CLI.\n\n"
    )
    body = (
        f"local DATA = {_lua(data)}\n\n"
        "function data() return DATA end\n\n"
        "-- The kind entry (with its id) for a kind id, or nil.\n"
        "function kind(id)\n"
        "  local k = DATA.kinds[id]\n"
        "  if not k then return nil end\n"
        "  local out = { id = id }\n"
        "  for f, v in pairs(k) do out[f] = v end\n"
        "  return out\n"
        "end\n\n"
        "-- The kind id of a blueprint name (\"bedroom-cell-v1\" or \"bedroom-cell\"), or nil.\n"
        "function kind_of_blueprint(name)\n"
        "  local base = tostring(name or \"\"):gsub(\"%-v%d+$\", \"\")\n"
        "  return DATA.template_kind[base]\n"
        "end\n\n"
        "-- The kind id for a df.civzone_type name (primary zone of a kind only), or nil.\n"
        "function kind_of_zone(zone_kind)\n"
        "  return DATA.zone_to_kind[zone_kind]\n"
        "end\n\n"
        "-- True if the kind id is private (nobody should walk through it).\n"
        "function is_private(id)\n"
        "  local k = DATA.kinds[id]\n"
        "  return k ~= nil and k.private == true\n"
        "end\n"
    )
    return head + body


def main(argv: list[str]) -> int:
    doc = load()
    problems = validate(doc)
    if "--write-lua" in argv:
        if problems:
            print("\n".join(problems))
            return 1
        LUA_FILE.write_text(render_lua(doc), encoding="utf-8", newline="\n")
        print(f"wrote {LUA_FILE.relative_to(REPO_ROOT)}")
        return 0
    if problems:
        print("\n".join(problems))
        return 1
    print(f"ok: {len(doc['kinds'])} room kinds")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
