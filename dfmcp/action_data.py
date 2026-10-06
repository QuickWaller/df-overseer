"""Per-tool execution data (`docs/CONDUCTOR-EXECUTION.md` 2.3), read from the
`execution:` block of a command in `scripts/dfhack/TOOLS.yaml`.

The point of the module is that **nothing in it names a tool**. How the
conductor judges a dry run, finds the handle a real call issued, reads a
step's progress, resolves an Uncertain call by a `landed` read and cleans up
after an abandoned project are all declared as data per command, so the next
tool is one `execution:` entry and no code (user's rule, 2026-09-21: tools
must be generalisable). The behaviour that is shared by every tool, the order
of a run and what each outcome class means, lives in `dfmcp/executor_tools.py`.

Everything here is pure: parsed DFHack output in, a verdict out. No DFHack
call, no queue access.

Output conventions: a tool printing a JSON array reaches the server as
`{"result": [...]}` (the same wrap `dfmcp/server.py` applies), so a path into
such an output starts with `result`. A script that prints exactly
`{"error": "..."}` is a refusal, never data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

DRY_RUN_ARG = "dry_run"

#: Keys an `execution:` block may carry. Anything else is a load-time error, so
#: a typo can never silently turn a check off.
_TOP_KEYS = frozenset({
    "verdict", "dry_run_echo", "issues_handle", "resolution_fields", "nothing_applied",
    "append_to_arg", "override_args", "handle_args", "phases", "progress", "landed", "cleanup",
    "preview_fields",
})
_VERDICT_KEYS = frozenset({"ok", "dry_ok", "real_ok", "refused_if_true", "refused_if_present", "reason"})
_LANDED_KINDS = frozenset({"new_row", "field_set", "list_gains"})


class ActionDataError(Exception):
    """An `execution:` block is malformed (a hard load-time failure)."""


# ---------------------------------------------------------------- paths


def unwrap(parsed: Any) -> Dict[str, Any]:
    """The shape every tool result has on the server: a dict stays, anything
    else (a bare JSON array) is `{"result": value}`."""
    return parsed if isinstance(parsed, dict) else {"result": parsed}


def get_path(obj: Any, path: str) -> Tuple[bool, Any]:
    """`(found, value)` for a dotted path into dicts and lists (list items by
    index). A path that is not there is `(False, None)`, never an exception."""
    node = obj
    for part in str(path).split("."):
        if isinstance(node, list):
            if not part.isdigit() or int(part) >= len(node):
                return False, None
            node = node[int(part)]
        elif isinstance(node, Mapping):
            if part not in node:
                return False, None
            node = node[part]
        else:
            return False, None
    return True, node


def error_text(out: Any) -> Optional[str]:
    """The message when `out` is a script's own `{"error": "..."}` refusal."""
    if isinstance(out, Mapping) and set(out) == {"error"} and isinstance(out["error"], str):
        return out["error"]
    return None


_VAR_RE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")


def substitute(value: Any, ctx: Mapping[str, Any]) -> Any:
    """Replace `$name` in a string (or in every string of a dict or list) from
    `ctx`. A name missing from `ctx` raises `ActionDataError`."""
    if isinstance(value, str):
        def _sub(m: "re.Match[str]") -> str:
            if m.group(1) not in ctx or ctx[m.group(1)] is None:
                raise ActionDataError(f"${m.group(1)} has no value here")
            return str(ctx[m.group(1)])
        return _VAR_RE.sub(_sub, value)
    if isinstance(value, dict):
        return {k: substitute(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute(v, ctx) for v in value]
    return value


# ---------------------------------------------------------------- the spec


@dataclass(frozen=True)
class ExecSpec:
    tool_id: str
    verdict: Dict[str, Any]
    dry_run_echo: str
    issues_handle: Optional[str] = None
    resolution_fields: Tuple[str, ...] = ()
    nothing_applied: Optional[Dict[str, Any]] = None
    append_to_arg: Optional[Dict[str, str]] = None
    override_args: Tuple[str, ...] = ()
    handle_args: Tuple[str, ...] = ()
    phases: Optional[Dict[str, Any]] = None
    progress: Optional[Dict[str, Any]] = None
    landed: Tuple[Dict[str, Any], ...] = ()
    cleanup: Optional[Dict[str, Any]] = None
    preview_fields: Tuple[str, ...] = ()


def _str_list(tool_id: str, key: str, raw: Any) -> Tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(i, str) and i for i in raw):
        raise ActionDataError(f"{tool_id}: execution.{key} must be a list of non-empty strings")
    return tuple(raw)


def parse(tool_id: str, raw: Any, *, takes_dry_run: bool = True) -> ExecSpec:
    """Validate one `execution:` block into an `ExecSpec`."""
    if not isinstance(raw, dict):
        raise ActionDataError(f"{tool_id}: execution must be a mapping")
    extra = sorted(set(raw) - _TOP_KEYS)
    if extra:
        raise ActionDataError(f"{tool_id}: execution has unknown key(s) {extra}")
    if not takes_dry_run:
        raise ActionDataError(f"{tool_id}: a routed tool must take DRY_RUN (docs/CONDUCTOR-EXECUTION.md 2.2)")
    verdict = raw.get("verdict")
    if not isinstance(verdict, dict) or not verdict:
        raise ActionDataError(f"{tool_id}: execution.verdict is required (a missing verdict refuses the tool)")
    extra = sorted(set(verdict) - _VERDICT_KEYS)
    if extra:
        raise ActionDataError(f"{tool_id}: execution.verdict has unknown key(s) {extra}")
    positive = [k for k in ("ok", "dry_ok", "real_ok", "refused_if_true", "refused_if_present") if verdict.get(k)]
    if not positive:
        raise ActionDataError(f"{tool_id}: execution.verdict declares nothing that can refuse or pass")
    for key in ("ok", "dry_ok", "real_ok", "reason"):
        if key in verdict and not isinstance(verdict[key], str):
            raise ActionDataError(f"{tool_id}: execution.verdict.{key} must be a path string")
    for key in ("refused_if_true", "refused_if_present"):
        _str_list(tool_id, f"verdict.{key}", verdict.get(key))
    echo = raw.get("dry_run_echo")
    if not isinstance(echo, str) or not echo:
        raise ActionDataError(f"{tool_id}: execution.dry_run_echo is required (the dry run must prove it was one)")
    na = raw.get("nothing_applied")
    if na is not None:
        if not isinstance(na, dict) or set(na) not in ({"all_zero"}, {"refusal"}):
            raise ActionDataError(f"{tool_id}: execution.nothing_applied is {{all_zero: [paths]}} or {{refusal: true}}")
        if "all_zero" in na:
            _str_list(tool_id, "nothing_applied.all_zero", na["all_zero"])
    app = raw.get("append_to_arg")
    if app is not None and not (isinstance(app, dict) and set(app) == {"arg", "text"}):
        raise ActionDataError(f"{tool_id}: execution.append_to_arg is {{arg, text}}")
    phases = raw.get("phases")
    if phases is not None:
        need = {"arg", "site_arg", "carry", "source"}
        if not isinstance(phases, dict) or not need <= set(phases):
            raise ActionDataError(f"{tool_id}: execution.phases needs {sorted(need)}")
        src = phases["source"]
        if not isinstance(src, dict) or not {"tool", "args", "rows", "label_field"} <= set(src):
            raise ActionDataError(f"{tool_id}: execution.phases.source needs tool, args, rows, label_field")
    progress = raw.get("progress")
    if progress is not None:
        if not isinstance(progress, dict) or not isinstance(progress.get("read"), dict) \
                or not isinstance(progress.get("done_field"), str):
            raise ActionDataError(f"{tool_id}: execution.progress needs read {{tool, args}} and done_field")
        extra = sorted(set(progress) - {"read", "done_field", "not_done_if", "stalled_if", "blocked_if"})
        if extra:
            raise ActionDataError(f"{tool_id}: execution.progress has unknown key(s) {extra}")
    landed = raw.get("landed") or []
    if not isinstance(landed, list):
        raise ActionDataError(f"{tool_id}: execution.landed must be a list")
    for i, entry in enumerate(landed):
        if not isinstance(entry, dict) or entry.get("kind") not in _LANDED_KINDS:
            raise ActionDataError(f"{tool_id}: execution.landed[{i}].kind must be one of {sorted(_LANDED_KINDS)}")
        if not isinstance(entry.get("read"), dict) or not {"tool", "rows"} <= set(entry["read"]):
            raise ActionDataError(f"{tool_id}: execution.landed[{i}].read needs tool and rows")
        if entry["kind"] == "new_row" and not (entry.get("handle_field") and isinstance(entry.get("match"), dict)):
            raise ActionDataError(f"{tool_id}: execution.landed[{i}] (new_row) needs handle_field and match")
        if entry["kind"] in ("field_set", "list_gains") and not (
            isinstance(entry.get("find"), dict) and entry.get("field")
        ):
            raise ActionDataError(f"{tool_id}: execution.landed[{i}] ({entry['kind']}) needs find and field")
        if entry["kind"] == "list_gains" and not (entry.get("value") and entry.get("handle")):
            raise ActionDataError(f"{tool_id}: execution.landed[{i}] (list_gains) needs value and handle")
    cleanup = raw.get("cleanup")
    if cleanup is not None and not (
        isinstance(cleanup, dict) and cleanup.get("handle_prefix") and isinstance(cleanup.get("args"), dict)
    ):
        raise ActionDataError(f"{tool_id}: execution.cleanup needs handle_prefix and args")
    return ExecSpec(
        tool_id=tool_id, verdict=dict(verdict), dry_run_echo=echo,
        issues_handle=raw.get("issues_handle"),
        resolution_fields=_str_list(tool_id, "resolution_fields", raw.get("resolution_fields")),
        nothing_applied=dict(na) if na else None,
        append_to_arg=dict(app) if app else None,
        override_args=_str_list(tool_id, "override_args", raw.get("override_args")),
        handle_args=_str_list(tool_id, "handle_args", raw.get("handle_args")),
        phases=dict(phases) if phases else None,
        progress=dict(progress) if progress else None,
        landed=tuple(dict(e) for e in landed),
        cleanup=dict(cleanup) if cleanup else None,
        preview_fields=_str_list(tool_id, "preview_fields", raw.get("preview_fields")),
    )


def spec_for(tool: Any) -> Optional[ExecSpec]:
    """The parsed spec of a registry tool, or `None` if it declares none."""
    raw = getattr(tool, "execution", None)
    if raw is None:
        return None
    takes = any(a.lower().strip("[]") in ("dry_run",) or "DRY_RUN" in a for a in getattr(tool, "args", []))
    return parse(tool.id, raw, takes_dry_run=takes)


def load_all(registry: Any) -> Dict[str, ExecSpec]:
    """Parse every declaration in a registry; any malformed one raises."""
    out: Dict[str, ExecSpec] = {}
    for tool in registry.all():
        spec = spec_for(tool)
        if spec is not None:
            out[tool.id] = spec
    return out


# ---------------------------------------------------------------- verdicts


@dataclass(frozen=True)
class Verdict:
    """`kind`: `ok` (the call did what was asked), `refused` (the tool itself
    declined; `reason` says why) or `invalid` (a declared field is absent or
    the echo is wrong, so nothing can be concluded: the call is refused at
    filing and Uncertain at execution)."""

    kind: str
    reason: str = ""
    missing: Tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.kind == "ok"


def judge(spec: ExecSpec, out: Any, *, dry: bool) -> Verdict:
    """The declared verdict of one output. An absent declared field is
    `invalid`, never a pass."""
    err = error_text(out)
    if err is not None:
        return Verdict("refused", err)
    if not isinstance(out, Mapping):
        return Verdict("invalid", "the output is not an object")
    found, echo = get_path(out, spec.dry_run_echo)
    if not found:
        return Verdict("invalid", f"the output has no {spec.dry_run_echo!r} field", (spec.dry_run_echo,))
    if echo is not dry:
        return Verdict(
            "invalid",
            f"the output says {spec.dry_run_echo}={echo!r} but this was a {'dry' if dry else 'real'} call",
            (),
        )
    v = spec.verdict
    reason = ""
    if v.get("reason"):
        rf, rv = get_path(out, v["reason"])
        if rf and isinstance(rv, str):
            reason = rv
    for path in v.get("refused_if_true") or ():
        f, val = get_path(out, path)
        if f and val:
            return Verdict("refused", reason or f"{path} is set")
    for path in v.get("refused_if_present") or ():
        f, val = get_path(out, path)
        if f and val not in (None, False, ""):
            return Verdict("refused", reason or (val if isinstance(val, str) else f"{path} is set"))
    missing = []
    for key, applies in (("ok", True), ("dry_ok", dry), ("real_ok", not dry)):
        path = v.get(key)
        if not path or not applies:
            continue
        f, val = get_path(out, path)
        if not f:
            missing.append(path)
        elif val is not True:
            return Verdict("refused", reason or f"{path} is {val!r}")
    if missing:
        return Verdict("invalid", f"declared field(s) absent: {missing}", tuple(missing))
    return Verdict("ok")


def nothing_applied(spec: ExecSpec, out: Any) -> Optional[bool]:
    """After a refusal, did the real call provably change nothing? `True`
    (changed nothing), `False` (something may have changed) or `None`
    (cannot tell: no declaration, or an unreadable field)."""
    na = spec.nothing_applied
    if not na:
        return None
    if na.get("refusal"):
        return True
    for path in na.get("all_zero") or ():
        f, val = get_path(out, path)
        if not f:
            continue  # the refusal came before the group was computed
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            return None
        if val != 0:
            return False
    return True


def issued_handle(spec: ExecSpec, out: Any) -> Optional[str]:
    """The handle a real call issued, or `None` (also when none is declared)."""
    if not spec.issues_handle:
        return None
    f, val = get_path(out, spec.issues_handle)
    return val if f and isinstance(val, str) and val else None


def resolution(spec: ExecSpec, out: Any) -> Tuple[Dict[str, Any], List[str]]:
    """`(values, missing)` for the declared resolution fields."""
    vals: Dict[str, Any] = {}
    missing: List[str] = []
    for path in spec.resolution_fields:
        f, val = get_path(out, path)
        if f:
            vals[path] = val
        else:
            missing.append(path)
    return vals, missing


# ---------------------------------------------------------------- argument rules


def apply_append(spec: ExecSpec, args: Mapping[str, Any], ctx: Mapping[str, Any]) -> Dict[str, Any]:
    """`args` with the declared text appended to its argument (the server
    appends the proposal id to a reserve's purpose, P3-B4). Idempotent."""
    out = dict(args)
    if spec.append_to_arg:
        name = spec.append_to_arg["arg"]
        text = substitute(spec.append_to_arg["text"], ctx)
        cur = str(out.get(name, ""))
        if not cur.endswith(text):
            out[name] = f"{cur} {text}".strip()
    return out


HANDLE_RE = re.compile(r"^(res|site)-[0-9]+$")


# ---------------------------------------------------------------- phases


def plan_request(spec: ExecSpec, args: Mapping[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """`(tool, args)` of the read that lists a template's phases."""
    src = spec.phases["source"]  # type: ignore[index]
    return src["tool"], {a: args[a] for a in src["args"] if a in args}


def plan_phases(spec: ExecSpec, parsed: Any) -> List[Dict[str, Any]]:
    """`[{label, applies: [leaf labels]}]` in template order."""
    src = spec.phases["source"]  # type: ignore[index]
    f, rows = get_path(unwrap(parsed), src["rows"])
    if not f or not isinstance(rows, list):
        raise ActionDataError(f"the phase read has no {src['rows']!r} list")
    out = []
    for row in rows:
        label = row.get(src["label_field"]) if isinstance(row, Mapping) else None
        if not isinstance(label, str):
            raise ActionDataError("a phase row has no label")
        applies = row.get(src.get("applies_field") or "applies") or []
        out.append({"label": label, "applies": [a for a in applies if isinstance(a, str)]})
    return out


def check_declared_phases(
    plan: List[Dict[str, Any]], declared: List[str], first_phase: Optional[str],
) -> List[str]:
    """Problems with a proposal's declared phase list (2.2 item 5): a phase the
    template does not have, an order that is not the template's, and a meta
    phase whose leaves repeat another listed phase (they would be applied
    twice, P3-B2). `first_phase` is the phase the proposal's own step applies,
    if its tool is the phases tool; it counts as listed for the repeat check."""
    errors: List[str] = []
    labels = [p["label"] for p in plan]
    for name in declared:
        if name not in labels:
            errors.append(f"declared phase {name!r} is not a phase of the template ({labels})")
    known = [n for n in declared if n in labels]
    if [labels.index(n) for n in known] != sorted(labels.index(n) for n in known):
        errors.append("declared phases are not in the template's order")
    by_label = {p["label"]: p for p in plan}
    listed = list(declared) + ([first_phase] if first_phase else [])

    def leaves(label: str) -> set:
        p = by_label.get(label)
        if p is None:
            return {label}
        return set(p["applies"]) if p["applies"] else {label}

    for i, a in enumerate(listed):
        for b in listed[i + 1:]:
            both = leaves(a) & leaves(b)
            if both and a != b:
                errors.append(
                    f"phases {a!r} and {b!r} would apply {sorted(both)} twice; list a meta "
                    "phase or its leaves, not both"
                )
    return errors


# ---------------------------------------------------------------- progress


def progress_request(spec: ExecSpec, ctx: Mapping[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
    if not spec.progress:
        return None
    read = spec.progress["read"]
    return read["tool"], substitute(read.get("args") or {}, ctx)


def _cond(out: Any, cond: Optional[Mapping[str, Any]]) -> bool:
    if not cond:
        return False
    f, val = get_path(out, cond["path"])
    if not f:
        return False
    if "equals" in cond:
        return val == cond["equals"]
    if "greater_than" in cond:
        return isinstance(val, (int, float)) and not isinstance(val, bool) and val > cond["greater_than"]
    return False


def judge_progress(spec: ExecSpec, out: Any) -> Dict[str, Any]:
    """`{state, done}` for one progress read. `state` is `done`, `issued` (in
    progress), `stalled`, `blocked_material` or `unknown` (an unreadable or
    null read never counts as done)."""
    p = spec.progress
    if p is None:
        return {"state": "done", "done": True, "reason": "no progress read declared; the call itself is the work"}
    if error_text(out) is not None or not isinstance(out, Mapping):
        return {"state": "unknown", "done": None, "reason": error_text(out) or "the read is not an object"}
    f, done = get_path(out, p["done_field"])
    if not f or done is None:
        return {"state": "unknown", "done": None, "reason": f"{p['done_field']} is null or absent"}
    if done is True and not _cond(out, p.get("not_done_if")):
        return {"state": "done", "done": True, "reason": "the game says it is done"}
    if _cond(out, p.get("blocked_if")):
        return {"state": "blocked_material", "done": False, "reason": "something cannot be finished (material)"}
    if _cond(out, p.get("stalled_if")):
        return {"state": "stalled", "done": False, "reason": "work has stalled"}
    return {"state": "issued", "done": False, "reason": "in progress"}


# ---------------------------------------------------------------- landed


def landed_entry(spec: ExecSpec, args: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """The `landed` declaration that applies to this call's arguments."""
    for entry in spec.landed:
        when = entry.get("when")
        if when is None:
            return entry
        v = args.get(when["arg"])
        if isinstance(v, str) and re.search(when["matches"], v):
            return entry
    return None


def landed_request(entry: Mapping[str, Any], ctx: Mapping[str, Any]) -> Tuple[str, Dict[str, Any]]:
    read = entry["read"]
    return read["tool"], substitute(read.get("args") or {}, ctx)


def _rows(entry: Mapping[str, Any], parsed: Any) -> Optional[list]:
    f, rows = get_path(unwrap(parsed), entry["read"]["rows"])
    return rows if f and isinstance(rows, list) else None


def _find_row(entry: Mapping[str, Any], rows: list, ctx: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    find = entry["find"]
    want = substitute(find["equals"], ctx)
    for r in rows:
        if isinstance(r, Mapping) and r.get(find["field"]) == want:
            return r
    return None


def landed_baseline(entry: Mapping[str, Any], parsed: Any, ctx: Mapping[str, Any]) -> Any:
    """A JSON-able snapshot taken before the real call; `None` if the read is
    unusable (the caller then refuses to send the call: it could not be
    resolved afterwards)."""
    rows = _rows(entry, parsed)
    if rows is None:
        return None
    kind = entry["kind"]
    if kind == "new_row":
        return {"handles": sorted(str(r.get(entry["handle_field"])) for r in rows if isinstance(r, Mapping))}
    row = _find_row(entry, rows, ctx)
    if row is None:
        return {"missing": True}
    val = row.get(entry["field"])
    return {"value": list(val) if isinstance(val, list) else val}


def landed_resolve(
    entry: Mapping[str, Any], baseline: Any, parsed: Any, ctx: Mapping[str, Any],
) -> Tuple[str, Optional[str]]:
    """Settle an Uncertain call: `("success", handle)`, `("nothing", None)`
    (it did not land) or `("unreadable", None)` (cannot tell)."""
    rows = _rows(entry, parsed)
    if rows is None or not isinstance(baseline, Mapping):
        return "unreadable", None
    kind = entry["kind"]
    if kind == "new_row":
        before = set(baseline.get("handles") or [])
        m = entry["match"]
        suffix = substitute(m["ends_with"], ctx)
        new = [
            r for r in rows
            if isinstance(r, Mapping) and str(r.get(entry["handle_field"])) not in before
            and isinstance(r.get(m["field"]), str) and r[m["field"]].endswith(suffix)
        ]
        if len(new) > 1:
            return "unreadable", None
        return ("success", str(new[0][entry["handle_field"]])) if new else ("nothing", None)
    row = _find_row(entry, rows, ctx)
    if row is None:
        return "unreadable", None
    now = row.get(entry["field"])
    before = baseline.get("value")
    if kind == "field_set":
        if now not in (None, "") and now != before:
            return "success", str(now)
        return "nothing", None
    want = substitute(entry["value"], ctx)
    gained = isinstance(now, list) and want in now and not (isinstance(before, list) and want in before)
    if gained:
        return "success", substitute(entry["handle"], ctx)
    return ("nothing", None) if isinstance(now, list) else ("unreadable", None)


# ---------------------------------------------------------------- cleanup


def cleanup_for(registry: Any, handle: str) -> Optional[Tuple[str, Dict[str, Any], ExecSpec]]:
    """`(tool, args, spec)` that undoes what a handle reserved or designated,
    chosen by the handle's prefix from the tools' own `cleanup` data."""
    for tool in registry.all():
        spec = spec_for(tool)
        if spec is not None and spec.cleanup and handle.startswith(spec.cleanup["handle_prefix"]):
            return tool.id, substitute(spec.cleanup["args"], {"handle": handle}), spec
    return None


def declared_paths(spec: ExecSpec) -> Dict[str, List[str]]:
    """Every output path a spec relies on, grouped by what kind of output it is
    read from: `dry`, `real`, `refusal`, `status`, `rows:<tool>`, `plan`. The
    fixture test (dfmcp/tests/test_action_data.py) checks each exists in a real
    output."""
    v = spec.verdict
    out: Dict[str, List[str]] = {"dry": [spec.dry_run_echo], "real": [spec.dry_run_echo], "refusal": []}
    for key, kind in (("ok", "dry"), ("dry_ok", "dry"), ("real_ok", "real")):
        if v.get(key):
            out[kind].append(v[key])
    if v.get("ok"):
        out["real"].append(v["ok"])
    for p in v.get("refused_if_true") or ():
        out["refusal"].append(p)
    if v.get("reason"):
        out["refusal"].append(v["reason"])
    if spec.issues_handle:
        out["real"].append(spec.issues_handle)
    out["dry"].extend(spec.resolution_fields)
    if spec.nothing_applied and "all_zero" in spec.nothing_applied:
        out["real"].extend(spec.nothing_applied["all_zero"])
    return out
