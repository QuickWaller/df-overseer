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

(executor fills this in; deploy targets expected: relay-web, relay-web-operator)
