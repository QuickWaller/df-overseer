"""Wiki mirror text stage (stream S2): wikitext to sections and chunks.

Pure text. Nothing here fetches, stores or timestamps anything; the store
(stream S1) attaches provenance (revid, fetch time) to what this returns.

The public function is `extract_page(wikitext, ...)`. It returns a `PageText`
holding `Chunk`s, each with a section path, plain text, and a `degraded` flag
with reasons. Design: `docs/CONSULTANT-WIKI.md` section 8.3 and 9.

What it does, in order (all deterministic, no clock, no randomness, no I/O
beyond loading the policy file):

1. Normalise: strip control and bidi characters, stash `<nowiki>` and `<pre>`
   bodies so nothing inside them is parsed, remove HTML comments.
2. Split on `=` headings, keeping the heading path. The lead is "Introduction".
3. Per section: flatten templates by the data policy in
   `template_policy.yaml` (parameters are kept as readable "key: value" text
   where they carry facts; dropped only where the policy says so), flatten
   tables to readable lines, resolve links to their display text, route
   categories to a separate field, strip formatting.
4. Chunk to a size bound on paragraph, line and sentence boundaries. No overlap:
   the design (8.3) asks for none.

Never executed, never interpreted: parser functions (`{{#if:...}}`), magic
words and page transclusions are not evaluated. They are rendered as plain
text where that is honest, and the chunk is flagged `degraded` with the reason,
so a silent loss of content is impossible by construction. Unknown or hostile
text stays text; this module has no code path that treats page text as an
instruction. HTML entities are decoded, so consumers must still escape the
text when embedding it in a structured prompt (stream S4 does that).

Standard library plus PyYAML (already a dependency of `dfmcp` and `doctrine`).
"""

from __future__ import annotations

import fnmatch
import functools
import html
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import yaml

DEFAULT_POLICY_PATH = Path(__file__).with_name("template_policy.yaml")
DEFAULT_MAX_CHUNK_CHARS = 2000
MIN_CHUNK_CHARS = 100
MAX_TEMPLATE_DEPTH = 4

LEAD_HEADING = "Introduction"

_ACTIONS = {"drop", "keep_body", "keep_parameters", "name_only", "category"}
_ENTRY_KEYS = {"action", "label", "only", "exclude", "positional_labels", "block", "source"}

# Placeholders for stashed nowiki/pre bodies. Private-use characters, stripped
# from the input first so page text cannot forge one.
_PH_OPEN = "\ue000"
_PH_CLOSE = "\ue001"
_PRIVATE_USE_RE = re.compile("[\ue000-\uf8ff]")
_PH_RE = re.compile(_PH_OPEN + r"(\d+)" + _PH_CLOSE)

# C0/C1 controls (except tab and newline), zero-width and bidi override marks.
_CONTROL_RE = re.compile(
    "[\x00-\x08\x0b-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]"
)

_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_HEADING_RE = re.compile(r"^(={1,6})[ \t]*(.+?)[ \t]*\1[ \t]*$")
_REDIRECT_RE = re.compile(r"^\s*#redirect\s*:?\s*\[\[([^\]|#]+)", re.IGNORECASE)

# Magic words and parser functions. Never evaluated; flagged when met.
_MAGIC_FUNCTIONS = {
    "lc", "uc", "lcfirst", "ucfirst", "urlencode", "anchorencode", "ns", "nse",
    "padleft", "padright", "plural", "int", "formatnum", "localurl", "fullurl",
    "filepath", "gender", "grammar", "safesubst", "subst", "msgnw", "raw", "msg",
}
_MAGIC_VARIABLES = {
    "pagename", "fullpagename", "basepagename", "subpagename", "namespace",
    "sitename", "currentyear", "currentmonth", "currentday", "currenttime",
    "revisionid", "server", "scriptpath",
}

_FILE_NAMESPACES = ("file:", "image:", "media:")
_FILE_OPTION_RE = re.compile(
    r"^(thumb|thumbnail|frame|framed|frameless|border|left|right|center|centre|none|"
    r"baseline|sub|super|top|text-top|middle|bottom|text-bottom|"
    r"\d*x?\d+px|upright.*|(link|alt|page|class|lang|langtag)=.*)$",
    re.IGNORECASE,
)

_HTML_TAGS = (
    "b|i|u|s|small|big|sup|sub|span|div|p|center|font|code|tt|blockquote|ul|ol|li|"
    "dl|dt|dd|abbr|cite|em|strong|noinclude|includeonly|onlyinclude|references|hr|"
    "del|ins|strike|kbd|var|samp|caption|tr|td|th|table|tbody|thead|poem|math|"
    "syntaxhighlight|source|gallery|nowiki|br|pre"
)
_HTML_TAG_RE = re.compile(r"</?(?:%s)\b[^<>]*>" % _HTML_TAGS, re.IGNORECASE)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_REF_RE = re.compile(r"<ref\b[^<>]*?/>|<ref\b[^<>]*>.*?</ref\s*>", re.IGNORECASE | re.DOTALL)
_HTML_TABLE_RE = re.compile(r"<table\b", re.IGNORECASE)
_EXTLINK_RE = re.compile(r"\[((?:https?|ftp)://[^\s\]]+)(?:[ \t]+([^\]]*))?\]")
_MAGICWORD_RE = re.compile(r"__[A-Z]+__")
_QUOTES_RE = re.compile(r"'{2,5}")
_KEY_RE = re.compile(r"^[\w .\-]{1,60}$")


class PolicyError(ValueError):
    """The template policy file is malformed. Raised at load, never mid-page."""


# --------------------------------------------------------------------------
# Data types
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Chunk:
    """One retrievable piece of a page.

    index          position among the page's chunks, from 0
    section_path   heading path, e.g. ("Trading", "Trade depot"); the lead is
                   ("Introduction",)
    part, parts    which piece of a long section this is (0-based, and count)
    text           plain text, facts from template parameters included
    degraded       True when something in this chunk's section could not be
                   parsed faithfully; `degraded_reasons` says what
    """

    index: int
    section_path: Tuple[str, ...]
    part: int
    parts: int
    text: str
    degraded: bool = False
    degraded_reasons: Tuple[str, ...] = ()

    @property
    def section_path_str(self) -> str:
        return " > ".join(self.section_path)

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "section_path": list(self.section_path),
            "part": self.part,
            "parts": self.parts,
            "text": self.text,
            "degraded": self.degraded,
            "degraded_reasons": list(self.degraded_reasons),
        }


@dataclass(frozen=True)
class PageText:
    """The result of `extract_page`.

    categories          category names found in `[[Category:X]]` and category
                        templates, first-seen order, no duplicates
    degraded_reasons    every reason any chunk was flagged, plus page-level ones
    unlisted_templates  templates met that the policy does not list, with
                        counts (they got the default rule); for measuring what
                        to add to the policy next
    is_redirect         the page is a `#REDIRECT`; one chunk states the target
    """

    chunks: Tuple[Chunk, ...]
    categories: Tuple[str, ...] = ()
    degraded_reasons: Tuple[str, ...] = ()
    unlisted_templates: Dict[str, int] = field(default_factory=dict)
    is_redirect: bool = False
    redirect_target: str = ""

    @property
    def degraded(self) -> bool:
        return bool(self.degraded_reasons)

    def to_dict(self) -> dict:
        return {
            "chunks": [c.to_dict() for c in self.chunks],
            "categories": list(self.categories),
            "degraded": self.degraded,
            "degraded_reasons": list(self.degraded_reasons),
            "unlisted_templates": dict(sorted(self.unlisted_templates.items())),
            "is_redirect": self.is_redirect,
            "redirect_target": self.redirect_target,
        }


# --------------------------------------------------------------------------
# Template policy (data-driven)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TemplateRule:
    action: str
    label: str = ""
    only: Tuple[str, ...] = ()
    exclude: Tuple[str, ...] = ()
    positional_labels: Tuple[str, ...] = ()
    block: bool = False


@dataclass(frozen=True)
class TemplatePolicy:
    default: TemplateRule
    rules: Dict[str, TemplateRule]

    def lookup(self, normalised_name: str) -> Tuple[TemplateRule, bool]:
        """(rule, listed). An unlisted name gets the default rule, listed False."""
        rule = self.rules.get(normalised_name)
        if rule is not None:
            return rule, True
        return self.default, False


def normalise_template_name(name: str) -> str:
    n = name.strip().replace("_", " ")
    if n.lower().startswith("template:"):
        n = n[len("template:"):]
    return re.sub(r"\s+", " ", n).strip().lower()


def _rule_from_mapping(name: str, m: dict) -> TemplateRule:
    if not isinstance(m, dict):
        raise PolicyError(f"template {name!r}: entry must be a mapping")
    unknown = set(m) - _ENTRY_KEYS
    if unknown:
        raise PolicyError(f"template {name!r}: unknown keys {sorted(unknown)}")
    action = m.get("action")
    if action not in _ACTIONS:
        raise PolicyError(f"template {name!r}: action must be one of {sorted(_ACTIONS)}, got {action!r}")

    def _strs(key: str) -> Tuple[str, ...]:
        v = m.get(key, [])
        if not isinstance(v, list) or not all(isinstance(x, (str, int)) for x in v):
            raise PolicyError(f"template {name!r}: {key} must be a list of strings")
        return tuple(str(x) for x in v)

    label = m.get("label", "")
    if not isinstance(label, str):
        raise PolicyError(f"template {name!r}: label must be a string")
    return TemplateRule(
        action=action,
        label=label,
        only=_strs("only"),
        exclude=_strs("exclude"),
        positional_labels=_strs("positional_labels"),
        block=bool(m.get("block", False)),
    )


def load_policy(path: Optional[Path] = None) -> TemplatePolicy:
    """Loads and validates a policy file. Raises PolicyError on any defect."""
    p = Path(path) if path is not None else DEFAULT_POLICY_PATH
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PolicyError(f"cannot read template policy {p}: {exc}") from exc
    if not isinstance(data, dict) or "default" not in data or "templates" not in data:
        raise PolicyError(f"{p}: needs top-level 'default' and 'templates'")
    default = _rule_from_mapping("<default>", data["default"])
    if default.action == "name_only" or default.action == "category":
        raise PolicyError("default action must be keep_parameters, keep_body or drop")
    rules: Dict[str, TemplateRule] = {}
    templates = data["templates"]
    if not isinstance(templates, dict):
        raise PolicyError(f"{p}: 'templates' must be a mapping")
    for raw_name, entry in templates.items():
        key = normalise_template_name(str(raw_name))
        if key in rules:
            raise PolicyError(f"{p}: template {raw_name!r} listed twice")
        rules[key] = _rule_from_mapping(str(raw_name), entry)
    return TemplatePolicy(default=default, rules=rules)


@functools.lru_cache(maxsize=1)
def _default_policy() -> TemplatePolicy:
    return load_policy(DEFAULT_POLICY_PATH)


# --------------------------------------------------------------------------
# Scanning helpers (brace and bracket aware, never evaluating anything)
# --------------------------------------------------------------------------


def _brace_pairs(s: str) -> Dict[int, int]:
    """One pass over `s`: {index of an opening `{{` or `{{{`: index just past
    its matching close}. Unmatched openers are simply absent. Linear time, so a
    page of ten thousand unclosed `{{` cannot make the stage quadratic."""
    pairs: Dict[int, int] = {}
    stack: List[Tuple[int, int]] = []  # (opener position, opener width)
    j = 0
    n = len(s)
    while j < n:
        if s.startswith("{{{", j):
            stack.append((j, 3))
            j += 3
        elif s.startswith("{{", j):
            stack.append((j, 2))
            j += 2
        elif stack and stack[-1][1] == 3 and s.startswith("}}}", j):
            pairs[stack.pop()[0]] = j + 3
            j += 3
        elif stack and s.startswith("}}", j):
            # closes a 2, or a 3 whose third brace is missing (treated as closed)
            pairs[stack.pop()[0]] = j + 2
            j += 2
        else:
            j += 1
    return pairs


def _link_pairs(s: str) -> Dict[int, int]:
    """Like `_brace_pairs`, for `[[ ]]`."""
    pairs: Dict[int, int] = {}
    stack: List[int] = []
    j = 0
    n = len(s)
    while j < n:
        if s.startswith("[[", j):
            stack.append(j)
            j += 2
        elif stack and s.startswith("]]", j):
            pairs[stack.pop()] = j + 2
            j += 2
        else:
            j += 1
    return pairs


def _split_top(s: str, sep: str, maxsplit: int = -1) -> List[str]:
    """Splits `s` on `sep` where `sep` is not inside `{{ }}`, `{{{ }}}`,
    `[[ ]]` or a `{| |}` table."""
    parts: List[str] = []
    stack: List[str] = []
    cur: List[str] = []
    j = 0
    n = len(s)
    while j < n:
        if s.startswith("{{{", j):
            stack.append("{{{")
            cur.append("{{{")
            j += 3
            continue
        if s.startswith("{{", j):
            stack.append("{{")
            cur.append("{{")
            j += 2
            continue
        if s.startswith("[[", j):
            stack.append("[[")
            cur.append("[[")
            j += 2
            continue
        if s.startswith("{|", j) and (j == 0 or s[j - 1] == "\n"):
            stack.append("{|")
            cur.append("{|")
            j += 2
            continue
        if stack:
            top = stack[-1]
            if top == "{{{" and s.startswith("}}}", j):
                stack.pop()
                cur.append("}}}")
                j += 3
                continue
            if top in ("{{", "{{{") and s.startswith("}}", j):
                stack.pop()
                cur.append("}}")
                j += 2
                continue
            if top == "[[" and s.startswith("]]", j):
                stack.pop()
                cur.append("]]")
                j += 2
                continue
            if top == "{|" and s.startswith("|}", j):
                stack.pop()
                cur.append("|}")
                j += 2
                continue
        if not stack and s.startswith(sep, j) and (maxsplit < 0 or len(parts) < maxsplit):
            parts.append("".join(cur))
            cur = []
            j += len(sep)
            continue
        cur.append(s[j])
        j += 1
    parts.append("".join(cur))
    return parts


# --------------------------------------------------------------------------
# Per-page and per-section context
# --------------------------------------------------------------------------


class _Ctx:
    """Mutable state for one section. `categories` and `unlisted` are shared
    across the page; `reasons` belongs to the section."""

    def __init__(self, policy: TemplatePolicy, categories: List[str], unlisted: Dict[str, int]):
        self.policy = policy
        self.categories = categories
        self.unlisted = unlisted
        self.reasons: List[str] = []

    def degrade(self, reason: str) -> None:
        if reason not in self.reasons:
            self.reasons.append(reason)

    def add_category(self, name: str) -> None:
        name = re.sub(r"\s+", " ", name.replace("_", " ")).strip()
        if name and name not in self.categories:
            self.categories.append(name)


# --------------------------------------------------------------------------
# Template flattening
# --------------------------------------------------------------------------


def _parse_args(parts: Sequence[str]) -> List[Tuple[str, str, bool]]:
    """[(key, value, positional)] in source order. Positional keys are "1", "2"..."""
    out: List[Tuple[str, str, bool]] = []
    pos = 0
    for part in parts:
        kv = _split_top(part, "=", maxsplit=1)
        if len(kv) == 2 and _KEY_RE.match(kv[0].strip() or "\x00"):
            out.append((kv[0].strip(), kv[1].strip(), False))
        else:
            pos += 1
            out.append((str(pos), part.strip(), True))
    return out


def _value_text(value: str) -> str:
    """One parameter value as a single readable line: bullet lists joined by
    commas, whitespace collapsed."""
    lines = []
    for line in value.split("\n"):
        line = re.sub(r"^[*#:;]+\s*", "", line.strip())
        if line:
            lines.append(line)
    return re.sub(r"[ \t]+", " ", ", ".join(lines)).strip()


def _selected(rule: TemplateRule, key: str) -> bool:
    if rule.only and not any(fnmatch.fnmatchcase(key.lower(), p.lower()) for p in rule.only):
        return False
    if any(fnmatch.fnmatchcase(key.lower(), p.lower()) for p in rule.exclude):
        return False
    return True


def _strip_braces(s: str) -> str:
    return s.replace("{{{", "").replace("}}}", "").replace("{{", "").replace("}}", "")


def _aside(text: str, depth: int) -> str:
    """Inline template output, set off from the prose. Square brackets at the
    top level; parentheses when nested, so `]]` never appears (it would read as
    the end of a link)."""
    return f" [{text}]" if depth <= 1 else f" ({text})"


def _render_template(inner: str, depth: int, ctx: _Ctx) -> str:
    parts = _split_top(inner, "|")
    raw_name = parts[0].strip()
    args_raw = parts[1:]

    # Page transclusion: {{:Page}}. Content is not available to this stage.
    if raw_name.startswith(":"):
        ctx.degrade("page_transclusion_not_expanded:" + raw_name[1:].strip()[:60])
        return ""

    lowered = raw_name.lower()
    # Parser functions and magic words are never evaluated.
    if lowered.startswith("#") or (":" in lowered and lowered.split(":", 1)[0] in _MAGIC_FUNCTIONS):
        name_for_reason = lowered.split(":", 1)[0][:40]
        ctx.degrade("parser_function_not_evaluated:" + name_for_reason)
        pieces = []
        first = raw_name.split(":", 1)[1] if ":" in raw_name else ""
        for piece in [first] + list(args_raw):
            v = _value_text(_flatten(piece, depth, ctx))
            if v:
                pieces.append(v)
        return "; ".join(pieces)
    if lowered.replace(" ", "") in _MAGIC_VARIABLES and not args_raw:
        ctx.degrade("magic_word_not_resolved:" + lowered)
        return ""

    name_key = normalise_template_name(raw_name)
    rule, listed = ctx.policy.lookup(name_key)
    if not listed:
        ctx.unlisted[name_key] = ctx.unlisted.get(name_key, 0) + 1

    display = rule.label or re.sub(r"\s+", " ", raw_name.replace("_", " ")).strip()
    if display.lower().startswith("template:") and not rule.label:
        display = display[len("template:"):].strip()

    if rule.action == "drop":
        return ""
    if rule.action == "name_only":
        return display

    args = _parse_args(args_raw)
    values: List[Tuple[str, str, bool]] = []
    for key, val, positional in args:
        if not _selected(rule, key):
            continue
        text = _value_text(_flatten(val, depth, ctx))
        if text:
            values.append((key, text, positional))

    if rule.action == "category":
        for _key, text, _pos in values:
            ctx.add_category(text)
        return ""

    if not values:
        return ""

    if rule.action == "keep_body":
        body = "; ".join(v for _k, v, _p in values)
        if not rule.label:
            return body
        text = f"{display}: {body}"
        return f"\n\n{text}\n\n" if rule.block else _aside(text, depth)

    # keep_parameters
    items = []
    for key, text, positional in values:
        if positional:
            idx = int(key) - 1
            label = rule.positional_labels[idx] if idx < len(rule.positional_labels) else ""
            items.append(f"{label}: {text}" if label else text)
        else:
            items.append(f"{key}: {text}")
    text = f"{display}: " + "; ".join(items)
    if rule.block:
        return f"\n\n{text}\n\n"
    return _aside(text, depth)


def _flatten(s: str, depth: int, ctx: _Ctx) -> str:
    """Replaces every template and parameter reference in `s`. `depth` is the
    nesting level of the enclosing template (0 at the top of a section)."""
    out: List[str] = []
    i = 0
    pairs = _brace_pairs(s)
    while True:
        k = s.find("{{", i)
        if k < 0:
            out.append(s[i:])
            break
        out.append(s[i:k])
        end = pairs.get(k, -1)
        if end < 0:
            ctx.degrade("unbalanced_template_open")
            out.append("{{")
            i = k + 2
            continue
        if s.startswith("{{{", k):
            # A template parameter reference {{{1|default}}}: never bound here,
            # so it renders as its default text (empty when there is none).
            inner = s[k + 3:end - 3] if s[end - 3:end] == "}}}" else s[k + 3:end - 2]
            pieces = _split_top(inner, "|", maxsplit=1)
            out.append(_flatten(pieces[1], depth, ctx) if len(pieces) == 2 else "")
            i = end
            continue
        inner = s[k + 2:end - 2]
        if depth + 1 > MAX_TEMPLATE_DEPTH:
            name = normalise_template_name(_split_top(inner, "|")[0])[:40]
            ctx.degrade("template_depth_exceeded:" + name)
            out.append(_strip_braces(inner))
        else:
            out.append(_render_template(inner, depth + 1, ctx))
        i = end
    return "".join(out)


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------


def _strip_cell_attrs(cell: str) -> str:
    parts = _split_top(cell, "|", maxsplit=1)
    if len(parts) == 2 and "=" in parts[0] and "[[" not in parts[0]:
        return parts[1].strip()
    return cell.strip()


def _convert_tables(text: str, ctx: _Ctx) -> str:
    if "{|" not in text:
        return text
    lines = text.split("\n")
    out: List[str] = []
    depth = 0
    rows: List[str] = []
    row: List[str] = []
    cell: Optional[List[str]] = None

    def end_cell() -> None:
        nonlocal cell
        if cell is not None:
            row.append(re.sub(r"\s+", " ", " ".join(cell)).strip())
            cell = None

    def end_row() -> None:
        end_cell()
        if any(c for c in row):
            rows.append(" | ".join(row))
        row.clear()

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("{|"):
            if depth == 0:
                rows, row, cell = [], [], None
            else:
                end_row()
            depth += 1
            continue
        if depth == 0:
            out.append(line)
            continue
        if stripped.startswith("|}"):
            depth -= 1
            if depth == 0:
                end_row()
                out.append("")
                out.extend(rows)
                out.append("")
                rows = []
            continue
        if stripped.startswith("|+"):
            end_row()
            caption = stripped[2:].strip()
            if caption:
                rows.append(_strip_cell_attrs(caption))
        elif stripped.startswith("|-"):
            end_row()
        elif stripped.startswith("!"):
            end_cell()
            for piece in _split_top(stripped[1:], "!!"):
                end_cell()
                cell = [_strip_cell_attrs(piece)]
        elif stripped.startswith("|"):
            end_cell()
            for piece in _split_top(stripped[1:], "||"):
                end_cell()
                cell = [_strip_cell_attrs(piece)]
        elif stripped:
            if cell is None:
                cell = []
            cell.append(stripped)
    if depth > 0:
        ctx.degrade("unclosed_table")
        end_row()
        out.append("")
        out.extend(rows)
    return "\n".join(out)


# --------------------------------------------------------------------------
# Links and inline markup
# --------------------------------------------------------------------------


MAX_LINK_DEPTH = 8


def _file_caption(parts: Sequence[str], ctx: _Ctx, depth: int) -> str:
    candidates = [p.strip() for p in parts if p.strip() and not _FILE_OPTION_RE.match(p.strip())]
    if not candidates:
        return ""
    return _resolve_links(candidates[-1], ctx, depth + 1) + " "


def _render_link(inner: str, ctx: _Ctx, depth: int) -> str:
    parts = _split_top(inner, "|")
    target = parts[0].strip()
    bare = target.lstrip(":").strip()
    low = bare.lower()
    if not target.startswith(":") and low.startswith(_FILE_NAMESPACES):
        return _file_caption(parts[1:], ctx, depth)
    if not target.startswith(":") and low.startswith("category:"):
        ctx.add_category(bare.split(":", 1)[1])
        return ""
    if len(parts) > 1 and parts[1].strip():
        return _resolve_links("|".join(parts[1:]).strip(), ctx, depth + 1)
    return bare


def _resolve_links(s: str, ctx: _Ctx, depth: int = 0) -> str:
    if "[[" not in s:
        return s
    if depth >= MAX_LINK_DEPTH:
        ctx.degrade("link_depth_exceeded")
        return s.replace("[[", "").replace("]]", "")
    out: List[str] = []
    i = 0
    pairs = _link_pairs(s)
    while True:
        k = s.find("[[", i)
        if k < 0:
            out.append(s[i:])
            break
        out.append(s[i:k])
        end = pairs.get(k, -1)
        if end < 0:
            ctx.degrade("unbalanced_link")
            out.append("[[")
            i = k + 2
            continue
        out.append(_render_link(s[k + 2:end - 2], ctx, depth))
        i = end
    return "".join(out)


def _gallery_to_lines(m: "re.Match[str]") -> str:
    lines = []
    for line in m.group(1).split("\n"):
        parts = line.split("|")
        cap = parts[-1].strip() if len(parts) > 1 else ""
        if cap:
            lines.append(cap)
    return "\n".join(lines)


_GALLERY_RE = re.compile(r"<gallery\b[^<>]*>(.*?)</gallery\s*>", re.IGNORECASE | re.DOTALL)


def _inline_clean(s: str, ctx: _Ctx) -> str:
    if _HTML_TABLE_RE.search(s):
        ctx.degrade("html_table_flattened")
    s = _REF_RE.sub("", s)
    s = _GALLERY_RE.sub(_gallery_to_lines, s)
    s = _BR_RE.sub(" ", s)
    s = _resolve_links(s, ctx)
    s = _EXTLINK_RE.sub(lambda m: (m.group(2) or m.group(1)).strip(), s)
    s = _HTML_TAG_RE.sub("", s)
    s = _MAGICWORD_RE.sub("", s)
    s = _QUOTES_RE.sub("", s)
    s = html.unescape(s).replace("\xa0", " ")
    return s


def _clean_lines(s: str) -> str:
    out: List[str] = []
    for line in s.split("\n"):
        line = line.strip()
        if re.fullmatch(r"-{4,}", line):
            continue
        m = re.match(r"^([*#:;]+)\s*(.*)$", line)
        if m:
            marks, rest = m.group(1), m.group(2)
            line = ("- " + rest) if marks[0] in "*#" else rest
        line = re.sub(r"[ \t]+", " ", line).strip()
        out.append(line)
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# --------------------------------------------------------------------------
# Section splitting and chunking
# --------------------------------------------------------------------------


def _stash(text: str, stash: List[str], reasons: List[str]) -> str:
    """Replace `<nowiki>` and `<pre>` bodies with placeholders so nothing in
    them is parsed. Their text is restored, literally, before chunking."""

    def sub_for(tag: str, s: str) -> str:
        pat = re.compile(r"<%s\b[^<>]*>(.*?)</%s\s*>" % (tag, tag), re.IGNORECASE | re.DOTALL)

        def repl(m: "re.Match[str]") -> str:
            stash.append(m.group(1))
            return f"{_PH_OPEN}{len(stash) - 1}{_PH_CLOSE}"

        s = pat.sub(repl, s)
        if re.search(r"<%s\b[^<>]*>" % tag, s, re.IGNORECASE):
            reasons.append(f"unclosed_{tag}_tag")
        return s

    text = sub_for("nowiki", text)
    text = sub_for("pre", text)
    return text


def _restore(text: str, stash: Sequence[str]) -> str:
    return _PH_RE.sub(lambda m: stash[int(m.group(1))], text)


def _normalise(wikitext: str, stash: List[str], page_reasons: List[str]) -> str:
    text = wikitext.replace("\r\n", "\n").replace("\r", "\n")
    text = _PRIVATE_USE_RE.sub("", text)
    text = _CONTROL_RE.sub("", text)
    text = _stash(text, stash, page_reasons)
    if "<!--" in text:
        text = _COMMENT_RE.sub("", text)
        if "<!--" in text:
            page_reasons.append("unclosed_comment")
            text = text.replace("<!--", "")
    return text


def _split_sections(text: str) -> List[Tuple[Tuple[str, ...], str]]:
    """[(raw heading path, body)] in order. The first is the lead, with an empty
    path. Titles are returned raw so they go through the same cleaning as text."""
    sections: List[Tuple[List[Tuple[int, str]], List[str]]] = []
    stack: List[Tuple[int, str]] = []
    current: List[str] = []
    sections.append(([], current))
    for line in text.split("\n"):
        m = _HEADING_RE.match(line)
        if m:
            level, title = len(m.group(1)), m.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            current = []
            sections.append((list(stack), current))
        else:
            current.append(line)
    return [(tuple(t for _l, t in path), "\n".join(body)) for path, body in sections]


def _hard_split(unit: str, max_chars: int) -> List[str]:
    pieces = []
    while len(unit) > max_chars:
        cut = unit.rfind(" ", 0, max_chars)
        if cut < max_chars // 2:
            cut = max_chars
        pieces.append(unit[:cut].rstrip())
        unit = unit[cut:].lstrip()
    if unit:
        pieces.append(unit)
    return pieces


def _split_long(paragraph: str, max_chars: int) -> List[str]:
    if len(paragraph) <= max_chars:
        return [paragraph]
    units: List[Tuple[str, str]] = []  # (text, separator before it)
    for li, line in enumerate(paragraph.split("\n")):
        sentences = re.split(r"(?<=[.!?])\s+", line)
        for si, sent in enumerate(sentences):
            if not sent:
                continue
            sep = "" if not units else ("\n" if si == 0 and li > 0 else " ")
            if len(sent) > max_chars:
                for pi, piece in enumerate(_hard_split(sent, max_chars)):
                    units.append((piece, sep if pi == 0 else " "))
            else:
                units.append((sent, sep))
    pieces: List[str] = []
    cur = ""
    for text, sep in units:
        if cur and len(cur) + len(sep) + len(text) <= max_chars:
            cur += sep + text
        else:
            if cur:
                pieces.append(cur)
            cur = text
    if cur:
        pieces.append(cur)
    return pieces


def chunk_text(text: str, max_chars: int = DEFAULT_MAX_CHUNK_CHARS) -> List[str]:
    """Splits section text to at most `max_chars` per piece on paragraph
    boundaries, then lines and sentences, then whitespace. No overlap."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: List[str] = []
    cur = ""
    for p in paragraphs:
        for piece in _split_long(p, max_chars):
            if cur and len(cur) + 2 + len(piece) <= max_chars:
                cur += "\n\n" + piece
            else:
                if cur:
                    chunks.append(cur)
                cur = piece
    if cur:
        chunks.append(cur)
    return chunks


def _render_section(body: str, stash: Sequence[str], ctx: _Ctx) -> str:
    flat = _flatten(body, 0, ctx)
    if "{{" in flat or "}}" in flat:
        ctx.degrade("unbalanced_braces")
    flat = _convert_tables(flat, ctx)
    flat = _inline_clean(flat, ctx)
    flat = _clean_lines(flat)
    return _restore(flat, stash)


def _clean_title(raw: str, stash: Sequence[str], ctx: _Ctx) -> str:
    cleaned = _render_section(raw, stash, ctx).replace("\n", " ")
    return re.sub(r"\s+", " ", cleaned).strip() or raw.strip()


def extract_page(
    wikitext: str,
    *,
    policy: Optional[TemplatePolicy] = None,
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
) -> PageText:
    """Wikitext to chunks. The function stream S3, S4 and S5 call.

    Deterministic and side-effect free. Never raises on page content; anything
    it cannot parse faithfully is reported through `degraded` on the affected
    chunks and `PageText.degraded_reasons`. Raises `ValueError` only for a bad
    `max_chunk_chars`.
    """
    if max_chunk_chars < MIN_CHUNK_CHARS:
        raise ValueError(f"max_chunk_chars must be at least {MIN_CHUNK_CHARS}")
    policy = policy or _default_policy()

    redirect = _REDIRECT_RE.match(wikitext or "")
    if redirect:
        target = re.sub(r"\s+", " ", redirect.group(1)).strip()
        chunk = Chunk(0, (LEAD_HEADING,), 0, 1, f"Redirect to: {target}")
        return PageText(chunks=(chunk,), is_redirect=True, redirect_target=target)

    stash: List[str] = []
    page_reasons: List[str] = []
    categories: List[str] = []
    unlisted: Dict[str, int] = {}

    text = _normalise(wikitext or "", stash, page_reasons)
    all_reasons: List[str] = list(page_reasons)
    chunks: List[Chunk] = []

    for raw_path, body in _split_sections(text):
        ctx = _Ctx(policy, categories, unlisted)
        if raw_path:
            path = tuple(_clean_title(t, stash, ctx) for t in raw_path)
        else:
            path = (LEAD_HEADING,)
        body_text = _render_section(body, stash, ctx)
        if not body_text:
            if ctx.reasons and body.strip():
                # Content existed and all of it was lost: say so, do not drop silently.
                all_reasons.extend(r for r in ctx.reasons if r not in all_reasons)
                pieces = ["(no text could be extracted from this section)"]
            else:
                all_reasons.extend(r for r in ctx.reasons if r not in all_reasons)
                continue
        else:
            pieces = chunk_text(body_text, max_chunk_chars)
        all_reasons.extend(r for r in ctx.reasons if r not in all_reasons)
        reasons = tuple(ctx.reasons)
        if not body_text:
            reasons = reasons + ("section_text_lost",)
            if "section_text_lost" not in all_reasons:
                all_reasons.append("section_text_lost")
        for n, piece in enumerate(pieces):
            chunks.append(
                Chunk(
                    index=len(chunks),
                    section_path=path,
                    part=n,
                    parts=len(pieces),
                    text=piece,
                    degraded=bool(reasons),
                    degraded_reasons=reasons,
                )
            )

    if not chunks and (wikitext or "").strip():
        all_reasons.append("no_text_extracted")
        chunks.append(
            Chunk(0, (LEAD_HEADING,), 0, 1, "(no text could be extracted from this page)",
                  True, ("no_text_extracted",))
        )

    # A page-level reason (unclosed comment or tag) marks every chunk.
    if page_reasons:
        marked = tuple(page_reasons)
        chunks = [
            Chunk(c.index, c.section_path, c.part, c.parts, c.text, True,
                  c.degraded_reasons + tuple(r for r in marked if r not in c.degraded_reasons))
            for c in chunks
        ]

    # Deduplicate page reasons, stable order.
    seen: List[str] = []
    for r in all_reasons:
        if r not in seen:
            seen.append(r)

    return PageText(
        chunks=tuple(chunks),
        categories=tuple(categories),
        degraded_reasons=tuple(seen),
        unlisted_templates=dict(unlisted),
    )
