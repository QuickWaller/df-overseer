"use strict";
/* The stream page: fetches static JSON files built by dfqueue/feed.py and
 * renders them as a project board. Plain HTML/CSS/JS, no build step, no
 * framework, no external requests (research/2026-10-01-stream-page-design.md
 * section 5's "static-site constraint" and section 7.2 layer 5's inert
 * rendering).
 *
 * Layout and visual spec: `research/2026-10-02-stream-board-mockup.html`,
 * option E, split layout (register 2026-10-02, "Stream page look"; handoff
 * `handoffs/2026-10-02-stream-board.md`). This file ports that mockup's
 * `renderE`/`detailPanel`/`jobGraph`/`miniGraph`/`layoutJobs`/`byDay`
 * functions to read the real feed instead of the mockup's hand-built data.
 *
 * `research/2026-10-01-stream-page-design.md` section 7.2, layer 5:
 * "Rendering is inert. The page inserts every text with `textContent`,
 * never as HTML." Every function below that shows model- or game-written
 * text uses `el()`'s `text` option, which is always `.textContent`, or sets
 * `.textContent` directly. There is no innerHTML assignment anywhere in
 * this file with untrusted content — grep this file for "innerHTML" during
 * review if that is ever in doubt.
 */

const POLL_MS = 5000;

const ROLE_COLORS = {
  overseer: "var(--role-overseer)",
  architect: "var(--role-architect)",
  quartermaster: "var(--role-quartermaster)",
  consultant: "var(--role-consultant)",
  conductor: "var(--role-system)",
  system: "var(--role-system)",
  executor: "var(--role-executor)",
  user: "var(--role-you)",
};

// design section 6.2 item 4: "four AI agents and a scheduler," plus a
// Who's who popover naming each role's job, model and allowlist in words.
// Model names are not read from agents/*/model.yaml here (deliberately
// avoided: exact model choices change independently of this page and are
// not this slice's job to keep in sync) -- "an AI model" is the honest,
// stable-enough label; see the gaps note rendered under the layout.
const WHOS_WHO = [
  { role: "Overseer", does: "Arbitrates proposals, sets priorities, writes the plan, and is the only one who acts on the fort." },
  { role: "Architect", does: "Proposes rooms, workshops, stockpile siting, corridors, dig order. Never acts." },
  { role: "Quartermaster", does: "Proposes food, drink, seed and work-order plans. Never acts." },
  { role: "Consultant", does: "Answers Dwarf Fortress domain questions on demand. Never decides." },
  { role: "System (the conductor)", does: "Code, not an AI model: runs the game clock, wakes the other roles, and reports what code itself did (a finished step)." },
];

//: The board's two themes (handoff item 5): Terminal 2 is the default for
//: every viewer regardless of system `prefers-color-scheme`; Stone 2 is
//: opt-in, behind the header toggle, remembered per browser.
const THEMES = ["terminal2", "stone2"];
const DEFAULT_THEME = "terminal2";

//: The board's four sections, in display order, and the project-status
//: value(s) each one collects (design register 2026-10-02; `abandoned`
//: joins `done` -- both are "no further work", the board does not give
//: an abandoned project its own fifth column).
const BOARD_SECTIONS = [
  ["Under way", ["active"]],
  ["On hold", ["hold"]],
  ["Done", ["done", "abandoned"]],
];

function el(tag, attrs, children) {
  const node = document.createElement(tag);
  attrs = attrs || {};
  for (const key of Object.keys(attrs)) {
    if (key === "text") {
      node.textContent = attrs[key]; // the ONLY place text ever enters the DOM
    } else if (key === "class") {
      node.className = attrs[key];
    } else if (key.startsWith("on")) {
      node.addEventListener(key.slice(2), attrs[key]);
    } else if (key === "hidden") {
      if (attrs[key]) node.setAttribute("hidden", "");
    } else {
      node.setAttribute(key, attrs[key]);
    }
  }
  (children || []).forEach((c) => {
    if (c) node.appendChild(c);
  });
  return node;
}

const SVGNS = "http://www.w3.org/2000/svg";
function svgEl(tag, attrs) {
  const node = document.createElementNS(SVGNS, tag);
  for (const key in attrs || {}) node.setAttribute(key, attrs[key]);
  return node;
}

async function fetchJson(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  return res.json();
}

function roleTitle(role) {
  if (!role) return "Unknown";
  return role.charAt(0).toUpperCase() + role.slice(1);
}

function speakerName(item) {
  return item.speaker || roleTitle(item.role);
}

// ---- game date ordering, for grouping a project's conversation by day -----
// (mockup's own `dayKey`/`byDay`). "Now" (a live, in-progress step with no
// game date of its own) always sorts last.
const DF_MONTHS = [
  "Granite", "Slate", "Felsite", "Hematite", "Malachite", "Galena",
  "Limestone", "Sandstone", "Timber", "Moonstone", "Opal", "Obsidian",
];

function dayKey(gameDate) {
  if (!gameDate) return Infinity;
  const m = /^(\d+) (\w+), year (\d+)$/.exec(gameDate);
  if (!m) return Infinity;
  return Number(m[3]) * 1000 + (DF_MONTHS.indexOf(m[2]) + 1) * 40 + Number(m[1]);
}

function shortDate(gameDate) {
  const m = /^(\d+) (\w+), year (\d+)$/.exec(gameDate || "");
  if (!m) return gameDate;
  return `${m[1]}-${m[2]}-${m[3]}`;
}

/** Group a project's conversation items by game day, oldest day first,
 * original (seq) order preserved within a day; items with no game date
 * ("Happening now"-style lines) form their own trailing group. Mirrors the
 * mockup's `byDay`. */
function groupByDay(items) {
  const groups = [];
  const withKey = items.map((item, i) => [item, i]);
  withKey.sort((a, b) => dayKey(a[0].game_date) - dayKey(b[0].game_date) || a[1] - b[1]);
  withKey.forEach(([item]) => {
    const last = groups[groups.length - 1];
    if (last && last[0] === item.game_date) last[1].push(item);
    else groups.push([item.game_date, [item]]);
  });
  return groups;
}

// ---- job graph layout (ports the mockup's layoutJobs/miniGraph/jobGraph) --
//
// Unlike the mockup's hand-built data (which reconstructs a dependency graph
// from plan-slot positions), the real feed already carries each step's own
// `requires` edges (dfqueue.feed_status.step_board_states), so layout here
// is a plain DAG depth computation over real ids, not a slot-position
// reconstruction.

function layoutSteps(steps) {
  const byId = Object.fromEntries(steps.map((s) => [s.id, s]));
  const depth = {};
  const visiting = new Set();
  function depthOf(step) {
    if (depth[step.id] !== undefined) return depth[step.id];
    if (visiting.has(step.id)) return 0; // guard against a (should-never-happen) cycle
    visiting.add(step.id);
    const deps = (step.requires || []).filter((d) => byId[d]);
    depth[step.id] = deps.length ? 1 + Math.max(...deps.map((d) => depthOf(byId[d]))) : 0;
    visiting.delete(step.id);
    return depth[step.id];
  }
  steps.forEach(depthOf);
  const rows = [];
  steps.forEach((s) => {
    const d = depthOf(s);
    (rows[d] = rows[d] || []).push(s);
  });
  return { byId, rows: rows.filter(Boolean) };
}

const STEP_LOOK = {
  done: { bg: "var(--g-done-bg)", line: "var(--g-done-line)", fg: "var(--g-done-fg)", sub: "done" },
  active: { bg: "var(--g-now-bg)", line: "var(--g-now-line)", fg: "var(--g-now-fg)", sub: "in progress" },
  ready: { bg: "var(--ground)", line: "var(--g-ready-line)", fg: "var(--g-ready-fg)", sub: "ready" },
  waiting: { bg: "var(--ground)", line: "var(--g-wait-line)", fg: "var(--g-wait-fg)", sub: "waiting", dash: "4 3" },
  hold: { bg: "var(--g-hold-bg)", line: "var(--g-hold-line)", fg: "var(--g-hold-fg)", sub: "on hold" },
};

/** Compact left-to-right dependency graph for a board card (mockup's own
 * `miniGraph`): one small rect per step, no labels, state by colour and
 * border style only on the graph itself -- the card's own "N of M done"
 * label beside it is what makes the state readable in text too. */
function miniGraph(steps) {
  const { byId, rows } = layoutSteps(steps);
  const NW = 18, NH = 9, HG = 9, VG = 3;
  const maxPer = Math.max(1, ...rows.map((r) => r.length));
  const H = maxPer * NH + (maxPer - 1) * VG;
  const W = rows.length * NW + Math.max(0, rows.length - 1) * HG;
  const pos = {};
  rows.forEach((row, ci) => {
    const total = row.length * NH + (row.length - 1) * VG;
    row.forEach((s, i) => {
      pos[s.id] = { x: ci * (NW + HG), y: (H - total) / 2 + i * (NH + VG) };
    });
  });
  const svg = svgEl("svg", {
    viewBox: `-1 -1 ${W + 2} ${H + 2}`, width: String(Math.min(W + 2, 160)),
    height: String(H + 2), class: "mini", "aria-hidden": "true",
  });
  steps.forEach((s) => {
    (s.requires || []).forEach((d) => {
      const a = pos[d], b = pos[s.id];
      if (!a || !b) return;
      svg.append(svgEl("path", {
        d: `M${a.x + NW},${a.y + NH / 2} C${a.x + NW + HG / 2},${a.y + NH / 2} ${b.x - HG / 2},${b.y + NH / 2} ${b.x},${b.y + NH / 2}`,
        fill: "none", stroke: "var(--line-strong)", "stroke-width": "1.2",
      }));
    });
  });
  steps.forEach((s) => {
    const p = pos[s.id];
    const look = STEP_LOOK[s.state] || STEP_LOOK.waiting;
    svg.append(svgEl("rect", {
      x: String(p.x), y: String(p.y), width: String(NW), height: String(NH), rx: "2.5",
      fill: s.state === "ready" || s.state === "waiting" ? "var(--ground)" : look.line,
      stroke: look.line, "stroke-width": s.state === "ready" ? "1.4" : "1",
      "stroke-dasharray": look.dash || "",
    }));
  });
  return svg;
}

/** The details panel's full job graph (mockup's own `jobGraph`): one named
 * box per step, a done tick, an on-hold "!", a progress bar and fraction
 * when a target count is known, and a "vN" tag on a step an amendment
 * added. */
function jobGraph(steps) {
  const { byId, rows } = layoutSteps(steps);
  const W = 320, NH = 40, VG = 24, HG = 10, PAD = 10;
  const maxPer = Math.max(1, ...rows.map((r) => r.length));
  const NW = Math.min(200, (W - PAD * 2 - HG * (maxPer - 1)) / maxPer);
  const pos = {};
  rows.forEach((row, ri) => {
    const total = row.length * NW + (row.length - 1) * HG;
    row.forEach((s, i) => {
      pos[s.id] = { x: (W - total) / 2 + i * (NW + HG), y: PAD + ri * (NH + VG) };
    });
  });
  const H = PAD * 2 + rows.length * NH + Math.max(0, rows.length - 1) * VG;
  const label = steps.map((s) => `${s.label} (${STEP_LOOK[s.state] ? STEP_LOOK[s.state].sub : s.state})`).join(", ");
  const svg = svgEl("svg", {
    viewBox: `0 0 ${W} ${H}`, width: "100%", role: "img",
    "aria-label": "Job order: " + label, class: "jgraph",
  });
  const defs = svgEl("defs", {});
  const marker = svgEl("marker", {
    id: "stream-arrow", viewBox: "0 0 8 8", refX: "7", refY: "4",
    markerWidth: "7", markerHeight: "7", orient: "auto-start-reverse",
  });
  marker.append(svgEl("path", { d: "M0,0 L8,4 L0,8 z", fill: "var(--faint)" }));
  defs.append(marker);
  svg.append(defs);

  steps.forEach((s) => {
    (s.requires || []).forEach((d) => {
      const a = pos[d], b = pos[s.id];
      if (!a || !b) return;
      const x1 = a.x + NW / 2, y1 = a.y + NH, x2 = b.x + NW / 2, y2 = b.y - 2, my = (y1 + y2) / 2;
      svg.append(svgEl("path", {
        d: `M${x1},${y1} C${x1},${my} ${x2},${my} ${x2},${y2}`, fill: "none",
        stroke: "var(--line-strong)", "stroke-width": "1.5", "marker-end": "url(#stream-arrow)",
      }));
    });
  });

  steps.forEach((s) => {
    const p = pos[s.id];
    const look = STEP_LOOK[s.state] || STEP_LOOK.waiting;
    const g = svgEl("g", {});
    const title = document.createElementNS(SVGNS, "title");
    title.textContent = `${s.label}: ${look.sub}`;
    g.append(title);
    g.append(svgEl("rect", {
      x: String(p.x), y: String(p.y), width: String(NW), height: String(NH), rx: "6",
      fill: look.bg, stroke: look.line,
      "stroke-width": s.state === "ready" || s.state === "active" ? "1.6" : "1",
      "stroke-dasharray": look.dash || "",
    }));
    if (s.state === "active" && typeof s.done === "number" && typeof s.total === "number" && s.total > 0) {
      const frac = s.done / s.total;
      g.append(svgEl("rect", { x: String(p.x + 6), y: String(p.y + NH - 7), width: String(NW - 12), height: "3", rx: "1.5", fill: "var(--g-now-barbg)" }));
      g.append(svgEl("rect", { x: String(p.x + 6), y: String(p.y + NH - 7), width: String((NW - 12) * frac), height: "3", rx: "1.5", fill: "var(--g-now-bar)" }));
    }
    const ix = p.x + 9;
    if (s.state === "done") {
      g.append(svgEl("path", {
        d: `M${ix},${p.y + 13} l3,3 l6,-6`, fill: "none", stroke: look.fg,
        "stroke-width": "1.6", "stroke-linecap": "round", "stroke-linejoin": "round",
      }));
    }
    if (s.state === "hold") {
      g.append(svgEl("circle", { cx: String(ix + 4), cy: String(p.y + 13), r: "6", fill: "var(--g-hold-icon)" }));
      const mark = svgEl("text", {
        x: String(ix + 4), y: String(p.y + 17), "text-anchor": "middle", fill: "var(--chip-ink)",
        "font-size": "10", "font-weight": "700",
      });
      mark.textContent = "!";
      g.append(mark);
    }
    const hasIcon = s.state === "done" || s.state === "hold";
    const tx = hasIcon ? p.x + 24 : p.x + 9;
    const maxChars = Math.max(1, Math.floor((NW - (hasIcon ? 30 : 16)) / 6.3));
    const name = svgEl("text", {
      x: String(tx), y: String(p.y + 17), fill: look.fg, "font-size": "12",
      "font-weight": s.state === "active" || s.state === "ready" ? "600" : "400",
    });
    name.textContent = s.label.length > maxChars ? s.label.slice(0, maxChars - 1) + "…" : s.label;
    g.append(name);
    const sub = svgEl("text", { x: String(tx), y: String(p.y + 30), fill: look.fg, opacity: "0.75", "font-size": "10" });
    sub.textContent = (s.state === "active" && typeof s.done === "number") ? `${s.done} of ${s.total}` : look.sub;
    g.append(sub);
    if (s.added_version) {
      g.append(svgEl("rect", { x: String(p.x + NW - 30), y: String(p.y - 7), width: "27", height: "14", rx: "4", fill: "var(--raised)", stroke: "var(--line-strong)" }));
      const tag = svgEl("text", { x: String(p.x + NW - 16.5), y: String(p.y + 3.5), "text-anchor": "middle", fill: "var(--muted)", "font-size": "9.5" });
      tag.textContent = "v" + s.added_version;
      g.append(tag);
    }
    svg.append(g);
  });
  return svg;
}

class StreamPage {
  constructor({ dataRoot, mode, root, liveViewSrc }) {
    this.dataRoot = dataRoot;
    // The live view is the existing noVNC viewer on the same origin, embedded.
    // Only when served from the real site: a local build has no viewer.
    this.liveViewSrc = liveViewSrc && location.port === "" ? liveViewSrc : null;
    this.mode = mode; // "public" | "operator"
    this.root = root;
    this.theme = this._loadTheme();
    this.selected = null; // {kind: "project"|"proposal", id} | null
    this.items = [];
    this.itemsById = new Map();
    this.projects = { thread_to_project: {}, projects: {} };
    this.status = null;
    this.lastSeq = 0;
    this._build();
  }

  // ---- theme (handoff item 5) -------------------------------------------

  _loadTheme() {
    try {
      const saved = localStorage.getItem("ragwind-theme");
      if (THEMES.includes(saved)) return saved;
    } catch (e) {
      // localStorage unavailable (private window, blocked storage): the
      // page still renders correctly with the default theme, just without
      // memory of a prior choice.
    }
    return DEFAULT_THEME;
  }

  _saveTheme() {
    try {
      localStorage.setItem("ragwind-theme", this.theme);
    } catch (e) {
      // Same as above: losing the memory of a choice is fine, failing to
      // render is not.
    }
  }

  _setTheme(theme) {
    this.theme = theme;
    this.wrap.setAttribute("data-style", theme);
    this.themeButtons.forEach((btn) => {
      btn.setAttribute("aria-pressed", String(btn.dataset.theme === theme));
    });
    this._saveTheme();
  }

  // ---- data loading ---------------------------------------------------

  async loadAll() {
    const head = await fetchJson(`${this.dataRoot}/head.json`).catch(() => null);
    const open = await fetchJson(`${this.dataRoot}/open.json`).catch(() => ({ items: [] }));
    const projects = await fetchJson(`${this.dataRoot}/projects.json`).catch(
      () => ({ thread_to_project: {}, projects: {} })
    );
    const status = await fetchJson(`${this.dataRoot}/status.json`).catch(() => null);

    this.head = head;
    // S0/S1 have no closed segments to speak of in the small local exports
    // this slice ships with, and no history-scrolling UI yet (see README's
    // gap note) -- only the open segment is rendered.
    this.items = open.items || [];
    this.itemsById = new Map(this.items.map((it) => [it.id, it]));
    this.projects = projects;
    this.status = status;
    this.lastSeq = head ? head.last_seq : this.items.length;
    this._render();
  }

  async poll() {
    if (document.hidden) return; // Page Visibility API, design section 4.3
    try {
      const head = await fetchJson(`${this.dataRoot}/head.json`);
      if (!head || head.last_seq === this.lastSeq) return;
      await this.loadAll();
    } catch (e) {
      // Static-file 404s are expected before an export has been run; the
      // page should not spam the console for a local demo.
    }
  }

  start() {
    this.loadAll();
    this._pollTimer = setInterval(() => this.poll(), POLL_MS);
  }

  // ---- chrome: header, live view ----------------------------------------

  _build() {
    this.root.textContent = "";
    this.wrap = el("div", { class: "e-wrap", "data-style": this.theme });

    const header = this._buildHeader();
    const view = this._buildLiveView();
    this.col = el("div", { class: "e-col" });
    const split = el("div", { class: "e-split" }, [view, this.col]);

    this.wrap.appendChild(header);
    this.wrap.appendChild(this.whoswhoPanel);
    this.wrap.appendChild(split);
    this.root.appendChild(this.wrap);
    this.root.appendChild(this._buildGapsNote());
  }

  _buildHeader() {
    const name = el("span", { class: "e-name", text: "Ragwind" });
    const subtitle = el("span", { class: "muted", text: "  Uniboslan, run by four AI agents and a scheduler" });
    const titles = el("div", {}, [name, subtitle]);

    const whoswhoBtn = el("button", {
      type: "button", class: "closebtn", style: "width:auto;padding:0 12px;font-size:12px",
      text: "Who's who", "aria-expanded": "false",
      onclick: () => this._toggleWhosWho(),
    });
    this.whoswhoBtn = whoswhoBtn;

    this.themeButtons = THEMES.map((t) => el("button", {
      type: "button", "aria-pressed": String(t === this.theme), "data-theme": t,
      text: t === "terminal2" ? "Terminal 2" : "Stone 2",
      onclick: () => this._setTheme(t),
    }));
    const themeSwitch = el("div", { class: "e-switch", role: "group", "aria-label": "Theme" }, this.themeButtons);

    const controls = [
      el("span", { class: "e-clabel", text: "Theme" }), themeSwitch, whoswhoBtn,
    ];
    if (this.mode === "operator") {
      const toggle = el("button", {
        type: "button", class: "closebtn", style: "width:auto;padding:0 12px;font-size:12px",
        text: this.showAsPublic ? "Showing: Public preview" : "Showing: Operator",
        "aria-pressed": String(!!this.showAsPublic),
        onclick: () => this._toggleShowAsPublic(),
      });
      this.operatorToggleBtn = toggle;
      controls.push(toggle);
    }

    this.whoswhoPanel = el(
      "div",
      { class: "e-sec", hidden: true },
      WHOS_WHO.map((w) => el("div", { class: "meta" }, [
        el("strong", { text: w.role + ": ", style: "color:var(--text)" }),
        el("span", { text: w.does }),
      ])).concat([
        el("p", {
          class: "muted", style: "font-size:12px",
          text: "Model names and exact tool allowlists are not shown here yet (see web/stream/README.md).",
        }),
      ])
    );

    return el("header", { class: "e-head" }, [titles, el("div", { class: "e-controls" }, controls)]);
  }

  _toggleWhosWho() {
    const hidden = this.whoswhoPanel.hasAttribute("hidden");
    if (hidden) this.whoswhoPanel.removeAttribute("hidden");
    else this.whoswhoPanel.setAttribute("hidden", "");
    this.whoswhoBtn.setAttribute("aria-expanded", String(hidden));
  }

  _toggleShowAsPublic() {
    this.showAsPublic = !this.showAsPublic;
    this.dataRoot = this.showAsPublic ? "data/public" : "data/operator";
    this.mode = this.showAsPublic ? "public" : "operator";
    this.operatorToggleBtn.textContent = this.showAsPublic
      ? "Showing: Public preview"
      : "Showing: Operator";
    this.operatorToggleBtn.setAttribute("aria-pressed", String(this.showAsPublic));
    this.loadAll();
  }

  _buildLiveView() {
    const frame = this.liveViewSrc
      ? el("div", { class: "video-frame" }, [
          el("iframe", { class: "live-view", src: this.liveViewSrc, title: "Live view of the fortress", allow: "fullscreen" }),
          el("span", { class: "e-live", text: "LIVE" }),
        ])
      : el("div", { class: "video-frame" }, [
          el("span", { class: "e-live", style: "background:var(--line-strong);color:var(--muted)", text: "OFFLINE" }),
          el("div", { class: "placeholder" }, [
            el("div", { class: "tag", text: "LIVE VIEW" }),
            el("div", { class: "sub", text: "The live view appears here on the real site." }),
          ]),
        ]);
    this.liveBadge = frame.querySelector(".e-live");
    return el("div", { class: "e-view" }, [frame]);
  }

  _renderStatus() {
    // design §3.1's feed.status is not built (GAPS); only the badge's
    // live/offline state reflects anything real (whether an embed exists).
    if (!this.liveViewSrc) return;
    if (!this.status || this.status.available === false) return;
    const state = this.status.state || "offline";
    this.liveBadge.textContent = state.toUpperCase();
  }

  _buildGapsNote() {
    return el("p", {
      class: "muted", style: "font-size:12px;padding:0 16px 16px",
      text:
        "Fort status, the season goal and history scrolling past the open " +
        "segment are not built yet — see web/stream/README.md.",
    });
  }

  // ---- rendering ----------------------------------------------------------

  _render() {
    this._renderStatus();
    this._renderColumn();
  }

  _renderColumn() {
    this.col.textContent = "";
    if (this.selected) {
      this.col.appendChild(
        this._detailPanel(this.selected, () => { this.selected = null; this._renderColumn(); })
      );
      return;
    }
    this.col.appendChild(this._goalStrip());
    // Mockup's own renderE: a section with nothing in it is omitted
    // entirely, not shown empty with a "None" placeholder (that is option
    // C's board behaviour, not option E's split layout, which is the one
    // this page follows).
    const cards = this._boardCards();
    let shown = 0;
    BOARD_SECTIONS.forEach(([label, statuses]) => {
      const entries = cards.filter((c) => statuses.includes(c.status));
      if (!entries.length) return;
      shown += entries.length;
      this.col.appendChild(this._sectionEl(label, entries));
    });
    const turnedDown = this._turnedDownCards();
    if (turnedDown.length) {
      shown += turnedDown.length;
      this.col.appendChild(this._sectionEl("Turned down", turnedDown));
    }
    if (!shown) {
      this.col.appendChild(el("p", { class: "muted", text: "Nothing here yet. Run the export script (web/stream/README.md) to load real past conversation." }));
    }
  }

  _goalStrip() {
    return el("div", { class: "e-goal" }, [
      el("span", { class: "sectionlabel", text: "Season goal" }),
      el("span", { class: "muted", text: "None set yet. The Overseer sets one at its seasonal review." }),
    ]);
  }

  _sectionEl(label, entries) {
    const section = el("section", { class: "e-sec" }, [
      el("h3", {}, [el("span", { text: label }), el("span", { class: "count", text: String(entries.length) })]),
    ]);
    if (!entries.length) {
      section.appendChild(el("div", { class: "muted", style: "font-size:0.85em", text: "None." }));
      return section;
    }
    entries.forEach((entry) => section.appendChild(this._cardEl(entry)));
    return section;
  }

  // ---- board data (dfqueue.feed.build_projects_view's own shape) --------

  _boardCards() {
    return Object.values(this.projects.projects || {}).map((p) => ({
      kind: "project",
      id: p.id,
      name: p.name || `Project ${p.id}`,
      description: p.description || null,
      urgency: p.urgency || null,
      status: p.status || "active",
      steps: p.steps || [],
    }));
  }

  /** A rejected or deferred proposal that never founded a project (handoff
   * item 2: "a turned-down proposal shows its name and the ruling's public
   * reason"). A proposal carries no `public_title` of its own (only a
   * project does, design §3.3 item 6), so its board "name" is its own
   * public `type` label (`Room siting`, already public, design §3.5) --
   * never a guess at a title it was never given. */
  _turnedDownCards() {
    const threadToProject = this.projects.thread_to_project || {};
    return this.items
      .filter((item) => item.kind === "proposal" && (item.badge === "rejected" || item.badge === "deferred"))
      .filter((item) => !threadToProject[item.thread])
      .map((item) => {
        const ruling = [...this.items]
          .filter((r) => r.kind === "ruling" && r.reply_to === item.id)
          .pop();
        return {
          kind: "proposal", id: item.id, name: item.type || "Proposal",
          description: ruling ? ruling.text : null, urgency: null,
          status: "turned_down", steps: [],
        };
      });
  }

  _cardEl(entry) {
    const parts = [
      el("div", { class: "btop" }, [
        el("span", { class: "bt", text: entry.name }),
        entry.urgency && entry.urgency !== "normal"
          ? el("span", { class: "urg u-" + entry.urgency, text: entry.urgency })
          : null,
      ]),
    ];
    if (entry.description) {
      parts.push(el("div", { class: "bdesc", text: entry.description }));
    }
    if (entry.steps.length) {
      const done = entry.steps.filter((s) => s.state === "done").length;
      const total = entry.steps.length;
      const label = entry.status === "done" ? "All done"
        : entry.status === "abandoned" ? "Abandoned"
        : entry.status === "hold" ? `${done}/${total} steps · held`
        : `${done}/${total} steps done`;
      parts.push(el("div", { class: "bstatus" }, [
        miniGraph(entry.steps),
        el("span", { class: "slabel", text: label }),
      ]));
    }
    return el("button", {
      class: "ecard", type: "button",
      onclick: () => { this.selected = { kind: entry.kind, id: entry.id }; this._renderColumn(); },
    }, parts);
  }

  // ---- details panel ------------------------------------------------------

  _detailPanel(selected, onClose) {
    if (selected.kind === "project") return this._projectDetailPanel(selected.id, onClose);
    return this._proposalDetailPanel(selected.id, onClose);
  }

  _projectConversation(projectId) {
    // A project's own thread is the proposal that founded it (design
    // §3.4): `thread_to_project` maps that thread id -> project id, so the
    // reverse lookup finds the thread, and every item sharing that thread
    // is the project's whole conversation, oldest first (items are already
    // in seq order).
    const threadToProject = this.projects.thread_to_project || {};
    const thread = Object.keys(threadToProject).find((t) => threadToProject[t] === projectId);
    if (!thread) return [];
    return this.items.filter((item) => item.thread === thread);
  }

  _projectDetailPanel(projectId, onClose) {
    const p = (this.projects.projects || {})[projectId];
    const back = el("button", { class: "closebtn", type: "button", "aria-label": "Back to the board", onclick: onClose, text: "←" });
    if (!p) {
      return el("aside", { class: "cpanel in-col" }, [back, el("p", { class: "muted", text: "This project is no longer in the feed." })]);
    }
    const name = p.name || `Project ${p.id}`;
    const chips = [el("span", { class: "chip " + (p.status === "done" ? "ok" : p.status === "hold" ? "no" : "active"), text: p.status })];
    if (p.urgency && p.urgency !== "normal") chips.push(el("span", { class: "urg u-" + p.urgency, text: p.urgency }));

    const convo = this._projectConversation(projectId);
    const founder = convo.find((i) => i.kind === "proposal");
    const metaLine = founder
      ? el("div", { class: "meta" }, [
          el("span", { text: roleTitle(founder.role) + "  " }),
          el("span", { class: "date", text: shortDate(founder.game_date) }),
        ])
      : null;

    const sections = [];
    if (p.steps && p.steps.length) {
      sections.push(el("section", { class: "psec" }, [
        el("div", { class: "sectionlabel", text: "Jobs" }),
        el("div", { class: "jgraph-wrap" }, [jobGraph(p.steps)]),
      ]));
      const live = p.steps.filter((s) => s.state === "active" || s.state === "hold");
      if (live.length) {
        sections.push(el("section", { class: "psec" }, [
          el("div", { class: "sectionlabel", text: "Happening now" }),
          ...live.map((s) => el("div", { class: "liveitem" + (s.state === "hold" ? " l-hold" : "") }, [
            el("div", { class: "ln", text: s.label }),
            el("div", { class: "ld", text: s.state === "hold" ? (s.hold_text || "On hold.") : (typeof s.done === "number" ? `${s.done} of ${s.total}` : "In progress.") }),
          ])),
        ]));
      }
    }
    sections.push(el("section", { class: "psec" }, [
      el("div", { class: "sectionlabel", text: "Conversation" }),
      ...this._conversationEl(convo),
    ]));

    return el("aside", { class: "cpanel in-col", "aria-label": "Project details" }, [
      el("div", { class: "cph" }, [
        el("div", { class: "cphl" }, [el("div", { class: "chips" }, chips), el("h2", { text: name })]),
        back,
      ]),
      metaLine,
      p.description ? el("p", { class: "pdesc", text: p.description }) : null,
      ...sections,
    ]);
  }

  _proposalDetailPanel(proposalId, onClose) {
    const item = this.itemsById.get(proposalId);
    const back = el("button", { class: "closebtn", type: "button", "aria-label": "Back to the board", onclick: onClose, text: "←" });
    if (!item) {
      return el("aside", { class: "cpanel in-col" }, [back, el("p", { class: "muted", text: "This proposal is no longer in the feed." })]);
    }
    const ruling = [...this.items].filter((r) => r.kind === "ruling" && r.reply_to === item.id).pop();
    const convo = this.items.filter((i) => i.thread === item.thread);
    return el("aside", { class: "cpanel in-col", "aria-label": "Proposal details" }, [
      el("div", { class: "cph" }, [
        el("div", { class: "cphl" }, [
          el("div", { class: "chips" }, [el("span", { class: "chip " + (item.badge || "pending"), text: item.badge || "pending" })]),
          el("h2", { text: item.type || "Proposal" }),
        ]),
        back,
      ]),
      el("div", { class: "meta" }, [el("span", { text: roleTitle(item.role) + "  " }), el("span", { class: "date", text: shortDate(item.game_date) })]),
      item.text ? el("p", { class: "pdesc", text: item.text }) : null,
      el("section", { class: "psec" }, [
        el("div", { class: "sectionlabel", text: "Conversation" }),
        ...this._conversationEl(convo),
      ]),
    ]);
  }

  _conversationEl(items) {
    const groups = groupByDay(items);
    return groups.map(([day, lines]) => el("div", { class: "tday" }, [
      el("div", { class: "tdayh", text: day ? shortDate(day) : "Now" }),
      el("ol", { class: "tl" }, lines.map((item) => el("li", {}, [
        el("span", { class: "tdot", style: `background:${ROLE_COLORS[item.role] || "var(--text)"}` }),
        el("div", { class: "tline" }, [
          el("span", { style: `color:${ROLE_COLORS[item.role] || "var(--text)"};font-weight:600`, text: speakerName(item) + " " }),
          item.badge ? el("span", { class: "chip " + item.badge, text: item.badge }) : null,
          el("span", { text: " " + this._bodyText(item) }),
        ]),
      ]))),
    ]));
  }

  _bodyText(item) {
    if (item.withheld) return "(one message withheld)";
    return item.text || `(${item.kind}, no public text yet)`;
  }
}

window.StreamPage = StreamPage;
