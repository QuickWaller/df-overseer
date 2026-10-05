# Handoff: render agents' Markdown safely on the Board

Date: 2026-10-05. **Executor, Sonnet, worktree. Offline; no deploys.**

## Why

User, 2026-10-05: the Board's "Full report" (and Thinking) shows raw Markdown
(`**bold**`, `- ` lists, backticks): the fort agents run on DeepSeek, which
writes Markdown. The page sets text as text (`el(..., {text})` in
`web/stream/app.js` around lines 1283 to 1295 and 1388 to 1393), which is
safe but unreadable.

## What to build

- A small Markdown-to-DOM renderer in `web/stream/app.js` that builds elements
  with `document.createElement` and text nodes only. **Never `innerHTML`,
  never a parsed HTML string, never an `href`.** Supported: paragraphs (blank
  line), headings (`#` to `###`, rendered as small bold lines, not page-sized
  headings), bullet lists (`- ` / `* `), numbered lists (`1. `), `**bold**`,
  `*italic*` / `_italic_`, inline `` `code` ``, and hard line breaks inside a
  paragraph. Anything else (links, images, HTML, tables, fences) shows as its
  literal text. Nested lists one level is enough.
- Use it for the run's "Full report", the run's Thinking, the item Thinking,
  and the main run summary if it is shown as an agent message. Keep the text
  the publisher already filtered; this is display only.
- Styling in `web/stream/style.css` fits the existing dark theme and the
  `fthink`/`freport` boxes: compact spacing, code in the existing mono font,
  lists indented modestly. Phone width must not scroll horizontally (long
  code spans wrap).
- Bump the asset version in `index.html` and `operator.html` (currently v59).

## Tests

- Node tests on the real `app.js` in the style of the existing
  `dfqueue/tests/test_site_js_*.py` (read them first): each supported
  construct, and that `<script>`, `<img onerror>`, `[x](javascript:...)` and an
  HTML entity come out as literal text with no element created from them.
- A headless check at 1280x700 and at phone width against the preview data
  (`scripts/preview_stream_live.py`; port 8934 may be taken, use another),
  console clean.

## Rules

- First step: `git merge --ff-only main`. Commit after each milestone.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md`.
- Touched surfaces: `web/stream/app.js`, `web/stream/style.css`,
  `web/stream/index.html` and `operator.html` (version only), new tests in
  `dfqueue/tests/`, this handoff.
- Public repo: no hostnames, IPs or tokens. No em dashes. No attribution lines
  in commits.
- Full ambient `python -m pytest` green.

## Result

Done. Asset version now v60.

- `renderMarkdown(text)` and `mdInline` in `web/stream/app.js`: createElement and
  text nodes only, no innerHTML, no HTML parsing, no href. Supported: paragraphs,
  hard line breaks, headings `#` to `###` (small bold line), `-`/`*` bullets,
  `1.` numbers, one nesting level, `**bold**`, `*italic*`/`_italic_` (underscore
  only at word edges, so snake_case stays), inline code (content literal).
  Everything else (links, images, HTML, tables, fences, entities, `####`) is
  literal text. `mdPlain(text)` strips the markers for single-line places.
- Scope addition (user, 2026-10-05). Rendered as blocks: run summary, Full
  report, run Thinking, item Thinking, thread replies (`ftext`, `frtext`), the
  proposal "Why", project and proposal detail (`pdesc`), lesson panel. Plain
  (markers stripped): board card description, reply quote, answer preview, the
  agent page's recent lines, wake detail, executed/hold reasons, pause reason.
  Left alone: Chronicle fixture quotes, site-text roster lines.
- Newline loss: only `dfqueue/live.py::_public_summary` collapsed whitespace
  (a join of `body.split()`). It now uses `_keep_lines` (spaces collapsed per
  line, blank runs reduced to one, nesting indent kept, sentence cut also at a
  full stop plus newline). `find_unsafe_pattern` is untouched and still checked
  on the whole text and on the final cut. Feed items, reports and thinking
  already kept newlines; the operator summary is the raw answer.
- Tests: `dfqueue/tests/test_site_js_markdown.py` (21: constructs, mdPlain, and
  hostile `<script>`, `<img onerror>`, `[x](javascript:...)`, entities, nested
  hostile cases; assert only allowed tags are created and no attribute is ever
  set); `tests/test_stream_publisher_runs.py` (newlines kept, an unsafe later
  line still withholds). Full `python -m pytest`: 2847 passed, 3 skipped.
- Headless (Chrome via CDP, preview data with markdown injected into runs.json):
  1280x700 and 390x800, no horizontal scroll, long code span wraps, no console
  errors (only a favicon 404 from the plain static server), zero script, img,
  a or iframe elements inside `.md`, hostile text shown literally.
- Deploy targets: relay-web, relay-web-operator, and vm103-stream-publisher
  (live.py change; already-published summaries stay collapsed until the
  publisher runs).
