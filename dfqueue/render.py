"""Rendering a queue record: `to_xml` for a prompt, `public_view` for the feed.

`docs/AGENT-ARCHITECTURE.md` §4: "Records are rendered as XML when placed
into a prompt, which is the form models handle most reliably." §8: "Allowlist
the fields published. Never regex-redact a firehose." These are two different
audiences reading two different projections of the same record, and they must
not be conflated — `to_xml` is everything a specialist or the Overseer needs
to reason about a record; `public_view` is the handful of fields the public
stream (step 2, not built here) is allowed to publish, ever, regardless of
what gets added to the schema later.
"""

from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr

from .schema import (
    ABANDON, AMEND, ANSWER, ASK, ESCALATION, EXECUTED, OBSERVATION, PASS,
    PROJECT, PROPOSAL, RULING,
)

#: §8's allowlist, plus id/ts/kind "so the feed can order and thread items"
#: (this stream's brief). Nothing else is ever published, by construction:
#: a field added to the schema tomorrow does not appear here until someone
#: deliberately adds it to this tuple.
ALLOWED_PUBLIC_FIELDS = (
    "id", "ts", "kind", "role", "type", "public_rationale", "decision",
    "suggested_priority",
)


def public_view(record: dict) -> dict:
    """The only fields the public stream may ever render. An allowlist, not
    a redaction: a field not named here cannot leak by omission from this
    function, only by someone editing `ALLOWED_PUBLIC_FIELDS` itself."""
    return {k: record[k] for k in ALLOWED_PUBLIC_FIELDS if k in record}


def _open_tag(tag: str, record: dict) -> str:
    attrs = "".join(
        f" {name}={quoteattr(str(record[name]))}"
        for name in ("id", "role", "cycle", "snapshot", "ts")
        if name in record
    )
    return f"<{tag}{attrs}>"


def _proposal_xml(record: dict) -> str:
    lines = [_open_tag("proposal", record)]
    lines.append(f"  <type>{escape(record['type'])}</type>")
    lines.append(f"  <summary>{escape(record['summary'])}</summary>")
    lines.append(f"  <rationale>{escape(record['rationale'])}</rationale>")
    if record.get("duplicate_of") is not None:
        # `handoffs/2026-09-28-queue-duplicate-proposal-check.md`: flagged,
        # never silently refused -- shown here so the Overseer's ruling (and
        # anyone reading the queue's history) sees the relationship plainly.
        lines.append(f"  <duplicate_of>{escape(record['duplicate_of'])}</duplicate_of>")

    pred = record["prediction"]
    pred_attrs = (
        f" signal={quoteattr(str(pred['signal']))}"
        f" op={quoteattr(str(pred['op']))}"
    )
    if pred.get("value") is not None:
        pred_attrs += f" value={quoteattr(str(pred['value']))}"
    pred_attrs += f" check_after_ticks={quoteattr(str(pred['check_after_ticks']))}"
    lines.append(f"  <prediction{pred_attrs}/>")

    cost = record["cost"]
    lines.append(
        f"  <cost estimate={quoteattr(str(cost['estimate']))} "
        f"unit={quoteattr(str(cost['unit']))}/>"
    )
    lines.append(f"  <suggested_priority>{record['suggested_priority']}</suggested_priority>")

    lines.append("  <preconditions>")
    for item in record["preconditions"]:
        key = "landmark" if "landmark" in item else "area"
        lines.append(
            f"    <requires {key}={quoteattr(str(item[key]))} "
            f"state={quoteattr(str(item['state']))}/>"
        )
    lines.append("  </preconditions>")

    for fact in record.get("cited") or []:
        lines.append(
            f"  <cited tool={quoteattr(str(fact['tool']))} field={quoteattr(str(fact['field']))} "
            f"value={quoteattr(str(fact['value']))} tick={quoteattr(str(fact['tick']))}/>"
        )

    lines.append(f"  <public_rationale>{escape(record['public_rationale'])}</public_rationale>")
    lines.append("</proposal>")
    return "\n".join(lines)


def _pass_xml(record: dict) -> str:
    return "\n".join([
        _open_tag("pass", record),
        f"  <reason>{escape(record['reason'])}</reason>",
        "</pass>",
    ])


def _ruling_xml(record: dict) -> str:
    return "\n".join([
        _open_tag("ruling", record),
        f"  <decision>{escape(record['decision'])}</decision>",
        f"  <proposal_id>{escape(record['proposal_id'])}</proposal_id>",
        f"  <reason>{escape(record['reason'])}</reason>",
        f"  <public_rationale>{escape(record['public_rationale'])}</public_rationale>",
        "</ruling>",
    ])


def _executed_xml(record: dict) -> str:
    lines = [_open_tag("executed", record)]
    lines.append(f"  <ruling_id>{escape(record['ruling_id'])}</ruling_id>")
    if record.get("step_id") is not None:
        lines.append(f"  <step_id>{escape(record['step_id'])}</step_id>")
    lines.append("  <actions>")
    for action in record["actions"]:
        attrs = (
            f" tool={quoteattr(str(action['tool']))}"
            f" outcome={quoteattr(str(action['outcome']))}"
        )
        if action.get("detail") is not None:
            attrs += f" detail={quoteattr(str(action['detail']))}"
        if action.get("target_state") is not None:
            attrs += f" target_state={quoteattr(str(action['target_state']))}"
        if action.get("targets"):
            attrs += f" targets={quoteattr(','.join(str(t) for t in action['targets']))}"
        if action.get("game_refs"):
            attrs += f" game_refs={quoteattr(','.join(str(t) for t in action['game_refs']))}"
        lines.append(f"    <action{attrs}/>")
    lines.append("  </actions>")
    lines.append(f"  <notes>{escape(record['notes'])}</notes>")
    lines.append("</executed>")
    return "\n".join(lines)


def _step_xml(step: dict) -> str:
    attrs = f" id={quoteattr(str(step['id']))}"
    if step.get("tool") is not None:
        attrs += f" tool={quoteattr(str(step['tool']))}"
    if step.get("trigger"):
        attrs += f" trigger={quoteattr(str(step['trigger']))}"
    lines = [f"    <step{attrs}>"]
    requires = step.get("requires") or []
    if requires:
        lines.append(f"      <requires>{escape(','.join(requires))}</requires>")
    lines.append("    </step>")
    return "\n".join(lines)


def _project_xml(record: dict) -> str:
    lines = [_open_tag("project", record)]
    lines.append(f"  <from_ruling>{escape(record['from_ruling'])}</from_ruling>")
    if record.get("objective_id") is not None:
        lines.append(f"  <objective_id>{escape(record['objective_id'])}</objective_id>")
    if record.get("template") is not None:
        lines.append(f"  <template>{escape(record['template'])}</template>")
    lines.append(f"  <summary>{escape(record['summary'])}</summary>")
    lines.append(f"  <because>{escape(record['because'])}</because>")
    lines.append("  <steps>")
    for step in record.get("steps", []):
        lines.append(_step_xml(step))
    lines.append("  </steps>")
    lines.append("</project>")
    return "\n".join(lines)


def _observation_xml(record: dict) -> str:
    lines = [_open_tag("observation", record)]
    lines.append(f"  <project_id>{escape(record['project_id'])}</project_id>")
    lines.append(f"  <step_id>{escape(record['step_id'])}</step_id>")
    lines.append(f"  <game_tick>{record['game_tick']}</game_tick>")
    lines.append("  <results>")
    for r in record.get("results", []):
        attrs = (
            f" target={quoteattr(str(r['target']))}"
            f" status={quoteattr(str(r['status']))}"
        )
        lines.append(f"    <result{attrs}>{escape(r['reason'])}</result>")
    lines.append("  </results>")
    lines.append("</observation>")
    return "\n".join(lines)


def project_status_line(status: dict) -> str:
    """One line for the Overseer's prompt, design §6: "status, target counts
    by state, and the top blocker's reason if any is held." Never the whole
    graph -- see `dfqueue.store.project_status`, this function's only
    caller-shaped input.

    `version` (added `handoffs/2026-10-01-queue-bugs-and-amend.md` item 3)
    is shown only once a project has been amended at least once (`v2` and
    up) -- the common, unamended case reads exactly as it always has,
    nothing new to learn for every project that was never revised.
    `abandoned_reason`, when present, is appended the same way a held
    target's reason already is.
    """
    counts = ", ".join(f"{n} {state}" for state, n in sorted(status["counts"].items())) or "no tracked targets"
    version = status.get("version", 1)
    version_suffix = f" (v{version})" if version and version > 1 else ""
    line = f"{status['project_id']}{version_suffix}: {status['status']} ({counts})"
    if status.get("abandoned_reason"):
        line += f"; abandoned: {status['abandoned_reason']}"
    blocker = status.get("top_blocker")
    if blocker:
        line += f"; held: {blocker['target']} ({blocker['reason']})"
    return line


def _amend_xml(record: dict) -> str:
    lines = [_open_tag("amend", record)]
    lines.append(f"  <project_id>{escape(record['project_id'])}</project_id>")
    lines.append(f"  <reason>{escape(record['reason'])}</reason>")
    for name in ("replaces", "adds", "drops"):
        ids = record.get(name)
        if ids:
            lines.append(f"  <{name}>{escape(','.join(ids))}</{name}>")
    lines.append("  <steps>")
    for step in record.get("steps", []):
        lines.append(_step_xml(step))
    lines.append("  </steps>")
    lines.append("</amend>")
    return "\n".join(lines)


def _abandon_xml(record: dict) -> str:
    return "\n".join([
        _open_tag("abandon", record),
        f"  <project_id>{escape(record['project_id'])}</project_id>",
        f"  <reason>{escape(record['reason'])}</reason>",
        "</abandon>",
    ])


def _ask_xml(record: dict) -> str:
    lines = [_open_tag("ask", record)]
    lines.append(f"  <question>{escape(record['question'])}</question>")
    if record.get("proposal_id") is not None:
        lines.append(f"  <proposal_id>{escape(record['proposal_id'])}</proposal_id>")
    lines.append("</ask>")
    return "\n".join(lines)


def _answer_xml(record: dict) -> str:
    return "\n".join([
        _open_tag("answer", record),
        f"  <ask_id>{escape(record['ask_id'])}</ask_id>",
        f"  <answer>{escape(record['answer'])}</answer>",
        "</answer>",
    ])


def _escalation_xml(record: dict) -> str:
    return "\n".join([
        _open_tag("escalation", record),
        f"  <reason>{escape(record['reason'])}</reason>",
        "</escalation>",
    ])


_RENDERERS = {
    PROPOSAL: _proposal_xml, PASS: _pass_xml, RULING: _ruling_xml,
    EXECUTED: _executed_xml, ASK: _ask_xml, ANSWER: _answer_xml,
    ESCALATION: _escalation_xml, PROJECT: _project_xml,
    OBSERVATION: _observation_xml, AMEND: _amend_xml, ABANDON: _abandon_xml,
}


def to_xml(record: dict) -> str:
    """Render one record as the §4 prompt form. Assumes `record` already
    passed `schema.validate` — this is a renderer, not a second validator,
    so a field missing from a record that skipped validation raises
    `KeyError` rather than being silently omitted."""
    kind = record.get("kind")
    renderer = _RENDERERS.get(kind)
    if renderer is None:
        raise ValueError(f"to_xml: unknown record kind {kind!r}")
    return renderer(record)
