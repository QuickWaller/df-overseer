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

from .schema import PASS, PROPOSAL, RULING

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


_RENDERERS = {PROPOSAL: _proposal_xml, PASS: _pass_xml, RULING: _ruling_xml}


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
