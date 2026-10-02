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
//: One theme only: the light one was dropped (user's call, 2026-10-02; it
//: is in git history). Kept as a list so a theme can return without rewiring.
const THEMES = ["terminal2"];
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
    // No value means no attribute: `null` must not become the text "null",
    // which would open a <details> or mark a link as aria-current.
    if (attrs[key] == null || attrs[key] === false) continue;
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
  constructor({ dataRoot, mode, root, liveViewSrc, embedded }) {
    this.dataRoot = dataRoot;
    // Inside the site shell the site owns the header and the theme toggle.
    this.embedded = !!embedded;
    // The live view is the existing noVNC viewer on the same origin, embedded.
    // Only when served from the real site: a local build has no viewer.
    this.liveViewSrc = liveViewSrc && location.port === "" ? liveViewSrc : null;
    this.mode = mode; // "public" | "operator"
    this.root = root;
    this.theme = this._loadTheme();
    this.selected = null; // {kind: "project"|"proposal", id} | null
    // Multi-fort data layout (register 2026-10-02, "plan for more than one
    // fort"): `dataRoot` is the PROJECTION root (`data/public`), not a
    // feed directly. `fortId`/`fortMeta` are resolved once from
    // `${dataRoot}/forts.json`'s own `current` fort -- never hard-coded
    // here. `_feedRoot()` is what loadAll/poll actually fetch from.
    this.fortId = null;
    this.fortMeta = null;
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

  /** `${dataRoot}/forts.json`'s own `current` fort, resolved once (cached
   * on `this.fortId`). Falls back to `dataRoot` itself as the feed root
   * (the pre-multi-fort layout) when `forts.json` is missing or empty --
   * a static-file 404 here is expected for an older export, not an error
   * to surface to the viewer. */
  async _resolveFort() {
    if (this.fortId !== null || this._fortResolved) return;
    this._fortResolved = true;
    const index = await fetchJson(`${this.dataRoot}/forts.json`).catch(() => null);
    const forts = (index && Array.isArray(index.forts)) ? index.forts : [];
    const current = forts.find((f) => f.current) || forts[0] || null;
    if (current) {
      this.fortId = current.id;
      this.fortMeta = current;
    }
  }

  _feedRoot() {
    return this.fortId ? `${this.dataRoot}/forts/${this.fortId}` : this.dataRoot;
  }

  async loadAll() {
    await this._resolveFort();
    this._applyFortMeta();
    const root = this._feedRoot();
    const head = await fetchJson(`${root}/head.json`).catch(() => null);
    const open = await fetchJson(`${root}/open.json`).catch(() => ({ items: [] }));
    const projects = await fetchJson(`${root}/projects.json`).catch(
      () => ({ thread_to_project: {}, projects: {} })
    );
    const status = await fetchJson(`${root}/status.json`).catch(() => null);

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
      const head = await fetchJson(`${this._feedRoot()}/head.json`);
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

    if (!this.embedded) {
      this.wrap.appendChild(header);
      this.wrap.appendChild(this.whoswhoPanel);
    } else {
      this.wrap.classList.add("embedded");
    }
    this.wrap.appendChild(split);
    this.root.appendChild(this.wrap);
    // Developer notes stay off the public page.
    if (this.mode === "operator") this.root.appendChild(this._buildGapsNote());
  }

  _buildHeader() {
    // Placeholder only -- never the data path's fort id. Replaced by the
    // real fort's own `name` once `forts.json` resolves (`_applyFortMeta`);
    // a fort with no name at all, or no fort listed, just keeps this.
    this.titleEl = el("span", { class: "e-name", text: "Fortress" });
    const subtitle = el("span", { class: "muted", text: "  run by four AI agents and a scheduler" });
    const titles = el("div", {}, [this.titleEl, subtitle]);

    const whoswhoBtn = el("button", {
      type: "button", class: "closebtn", style: "width:auto;padding:0 12px;font-size:12px",
      text: "Who's who", "aria-expanded": "false",
      onclick: () => this._toggleWhosWho(),
    });
    this.whoswhoBtn = whoswhoBtn;

    this.themeButtons = THEMES.map((t) => el("button", {
      type: "button", "aria-pressed": String(t === this.theme), "data-theme": t,
      text: t === "terminal2" ? "Dark" : "Light",
      onclick: () => this._setTheme(t),
    }));
    const themeSwitch = el("div", { class: "e-switch", role: "group", "aria-label": "Theme" }, this.themeButtons);

    const controls = [
      whoswhoBtn,
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
          text: "Each agent's model, tools and charter are on the Agents page.",
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
    // A different projection root could in principle list a different
    // fort (or none yet) -- re-resolve rather than keep the old one.
    this.fortId = null;
    this.fortMeta = null;
    this._fortResolved = false;
    this.loadAll();
  }

  /** The header's fort name, once resolved (handoff: "never hard-coded in
   * app.js"). Before the first load, or if no fort is listed at all, shows
   * a generic placeholder rather than inventing a name. */
  _applyFortMeta() {
    if (this.fortMeta && this.fortMeta.name) {
      this.titleEl.textContent = this.fortMeta.name;
    }
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
        "segment are not built yet (web/stream/README.md).",
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
    // The board's sections as tabs, each with its count; an empty section
    // has no tab. The chosen tab is kept while the board polls.
    const cards = this._boardCards();
    const groups = BOARD_SECTIONS
      .map(([label, statuses]) => [label, cards.filter((c) => statuses.includes(c.status))])
      .concat([["Turned down", this._turnedDownCards()]])
      .filter(([, entries]) => entries.length);
    if (!groups.length) {
      this.col.appendChild(el("p", { class: "muted", text: "Nothing here yet." }));
      return;
    }
    if (!groups.some(([label]) => label === this.boardTab)) this.boardTab = groups[0][0];
    this.col.appendChild(el("div", { class: "btabs", role: "tablist" }, groups.map(([label, entries]) => el("button", {
      type: "button", role: "tab", class: "btab", "aria-selected": String(label === this.boardTab),
      onclick: () => { this.boardTab = label; this._renderColumn(); },
    }, [document.createTextNode(label + " "), el("span", { class: "count", text: String(entries.length) })]))));
    const [, entries] = groups.find(([label]) => label === this.boardTab);
    const list = el("div", { class: "e-sec", role: "tabpanel" });
    entries.forEach((entry) => list.appendChild(this._cardEl(entry)));
    this.col.appendChild(list);
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
    const projects = Object.values(this.projects.projects || {}).map((p) => ({
      kind: "project",
      id: p.id,
      name: p.name || `Project ${p.id}`,
      description: p.description || null,
      urgency: p.urgency || null,
      status: p.status || "active",
      steps: p.steps || [],
    }));
    return projects.concat(this._acceptedWithoutProject());
  }

  /** Proposals accepted before project records existed never founded a
   * project, so they would show nowhere. Each shows as its own card: done
   * when something was executed on its thread, otherwise under way. */
  _acceptedWithoutProject() {
    const threadToProject = this.projects.thread_to_project || {};
    return this.items
      .filter((item) => item.kind === "proposal" && item.badge === "accepted" && !threadToProject[item.thread])
      .map((item) => {
        const executed = this.items.some((i) => i.kind === "executed" && i.thread === item.thread);
        return {
          kind: "proposal", id: item.id, name: item.type || "Proposal",
          description: item.text || null, urgency: null,
          status: executed ? "done" : "active", steps: [], noPlan: true,
        };
      });
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
        // The section already says "Turned down": show the reason alone.
        const reason = ruling && ruling.text ? ruling.text.replace(/^(rejected|deferred)\s*:\s*/i, "") : null;
        return {
          kind: "proposal", id: item.id, name: item.type || "Proposal",
          description: reason, urgency: null,
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
    if (entry.noPlan) {
      parts.push(el("div", { class: "bstatus" }, [
        el("span", { class: "slabel", text: entry.status === "done" ? "Done, before job plans existed" : "Accepted" }),
      ]));
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

/* ============================================================================
 * Site shell: navigation, Agents, Tools, Forts and a Chronicle stub
 * (handoffs/2026-10-02-site-agents-tools.md). Spec and layout:
 * research/2026-10-02-site-agents-tools-mockup.html -- ported here to read
 * real data (dfqueue.site_data's agents.json/tools.json/gotchas.json, plus
 * the existing per-fort feed for Recent lines) instead of the mockup's
 * hand-built constants. The Board view is untouched: `SitePage` mounts the
 * existing `StreamPage` unchanged for `#board` and never reaches into it.
 *
 * Roles and planned roles are never hard-coded here -- they come from
 * `agents.json`'s `role_order`/`planned_order`/`roles`, built from
 * `agents/ROSTER.yaml` (dfqueue/site_data.py). "Will" and "Executor" are
 * the two fixed extras the handoff names explicitly: a human and a
 * not-yet-built role with no entry in the roster at all.
 * ============================================================================
 */

//: Pinned, from cdnjs (CLAUDE.md: "external scripts only from cdnjs or
//: jsdelivr, pinned") -- same version the mockup uses. Declared here so a
//: page that does not load the script (an older cached index.html) still
//: renders the charter as plain preformatted text rather than failing.
const MARKED_VERSION = "12.0.2";

const FIXED_EXTRAS = {
  will: {
    name: "Will", kindLabel: "The human", noLink: true, color: "var(--will)",
    line: "Messages the Overseer in plain words. The Overseer can message back, and may question an instruction before acting on it.",
  },
  executor: {
    name: "Executor", kindLabel: "Planned: runs the jobs", planned: true, color: "var(--role-executor)",
    line: "Would carry out each project's jobs step by step in code, waking a cheap model only when a job is held. Today the Overseer does this itself.",
  },
};

function roleCssVar(role) {
  if (role === "conductor") return "var(--role-system)";
  if (FIXED_EXTRAS[role]) return FIXED_EXTRAS[role].color;
  return `var(--role-${role}, var(--text))`;
}

/** Evenly spaced spoke order around the ring: every enabled role but the
 * sole writer (hub), then every planned role, with the two fixed extras
 * worked in -- "Executor" at the midpoint, "Will" last. Order (not a fixed
 * angle table) is what's data-driven here: the roster can grow or shrink
 * and the ring just redistributes. */
function buildSpokeOrder(agents) {
  const enabled = (agents.role_order || []).filter((r) => r !== agents.sole_writer);
  const planned = agents.planned_order || [];
  const list = enabled.map((key) => ({ key, planned: false }))
    .concat(planned.map((key) => ({ key, planned: true })));
  const mid = Math.ceil(list.length / 2);
  list.splice(mid, 0, { key: "executor", planned: true, extra: true });
  list.push({ key: "will", planned: false, extra: true });
  return list;
}

function spelledCount(n, one, many) {
  return `${n} ${n === 1 ? one : many}`;
}

function countChips(entries) {
  const by = (list) => entries.filter((e) => e.list === list).length;
  const g = by("gotcha"), v = by("vent"), u = by("unexplained");
  const chips = [];
  if (g) chips.push(el("span", { class: "cnt cnt-g", text: spelledCount(g, "gotcha", "gotchas") }));
  if (v) chips.push(el("span", { class: "cnt cnt-v", text: spelledCount(v, "vent", "vents") }));
  if (u) chips.push(el("span", { class: "cnt cnt-u", text: spelledCount(u, "unexplained", "unexplained") }));
  return chips;
}

function confidencePillClass(level) {
  if (level === "full") return "pill p-ok";
  if (level === "low") return "pill p-bad";
  return "pill p-warn";
}

/** One gotcha/vent/unexplained entry, rendered the same way on an agent's
 * tool tree, a tool page and (once general entries exist) a "general"
 * group -- never the operator-only `call_excerpt`, which this page never
 * fetches in the first place (dfqueue.site_data.build_gotchas_json strips
 * it from the public projection before this page ever sees the JSON). */
function gotchaEntryEl(g, { showTool } = {}) {
  const listPill = g.list === "gotcha"
    ? el("span", { class: "pill " + (g.status === "accepted" ? "p-ok" : "p-info"), text: g.status === "accepted" ? "gotcha" : "gotcha, proposed" })
    : g.list === "vent" ? el("span", { class: "pill p-warn", text: "vent" }) : el("span", { class: "pill p-bad", text: "unexplained" });
  const head = [listPill, el("span", { class: "etitle", text: g.withheld ? "(withheld)" : (g.title || "(untitled)") })];
  if (showTool) {
    head.push(g.tool
      ? el("a", { class: "tagchip", href: "#tool-" + g.tool, text: g.tool })
      : el("span", { class: "tagchip", text: "general" }));
  }
  const outcomes = (g.outcomes || []).map((o) => el("span", {
    class: "oc-" + (o.result === "worked" ? "ok" : o.result === "did_not_work" ? "bad" : "unclear"),
  }, [
    document.createTextNode((o.result === "worked" ? "worked" : o.result === "did_not_work" ? "didn't help" : o.result) + "  "),
    el("span", { style: `color:${roleCssVar(o.role)};font-weight:600`, text: roleTitle(o.role) }),
    document.createTextNode("  " + (o.at || "")),
  ]));
  return el("div", { class: "entry" }, [
    el("div", { class: "ehead" }, head),
    el("div", { class: "muted small", text: g.withheld ? "This entry's text was withheld by the public-text safety net." : (g.body || "") }),
    el("div", { class: "outcomes" }, [
      el("span", {}, [document.createTextNode("by "), el("span", { style: `color:${roleCssVar(g.by)};font-weight:600`, text: roleTitle(g.by) })]),
      ...outcomes,
    ]),
  ]);
}

class SitePage {
  constructor({ dataRoot, mode, root, liveViewSrc }) {
    this.dataRoot = dataRoot;
    this.mode = mode;
    this.liveViewSrc = liveViewSrc;
    this.root = root;
    this.theme = this._loadTheme();
    this.forts = [];
    this.fortMeta = null;
    this.agents = null;
    this.tools = null;
    this.gotchas = null;
    this.chronicleFixture = null;
    this._boardPage = null;
    this._boardContainer = null;
    this.mapSel = null;
    this.mapFocus = null;
    this.agentTab = "tools";
    this._agentTabFor = null;
    this.toolFilter = { q: "", role: null, only: null };
    this.toolAreasOpen = new Set();
    this.showAllSeasons = new Set();
    this._boundHashChange = () => this._onHashChange();
    window.addEventListener("hashchange", this._boundHashChange);
    this._build();
  }

  // ---- theme: same localStorage key StreamPage uses, so both toggles
  // (this page's own, and the Board's internal one) stay in sync. --------

  _loadTheme() {
    try {
      const saved = localStorage.getItem("ragwind-theme");
      if (THEMES.includes(saved)) return saved;
    } catch (e) { /* private window or blocked storage: default theme */ }
    // ?theme= is a smoke-test aid (web/stream/README.md), not a feature a
    // viewer is expected to use: it saves to the SAME localStorage key the
    // Board's own StreamPage reads, so a screenshot tool can set the theme
    // once via the URL and have it hold across a hash navigation into the
    // Board, which has no query-param reading of its own.
    const q = new URLSearchParams(location.search).get("theme");
    if (THEMES.includes(q)) {
      try { localStorage.setItem("ragwind-theme", q); } catch (e) { /* see above */ }
      return q;
    }
    return DEFAULT_THEME;
  }

  _saveTheme() {
    try { localStorage.setItem("ragwind-theme", this.theme); } catch (e) { /* see above */ }
  }

  _setTheme(theme) {
    this.theme = theme;
    this.shell.setAttribute("data-style", theme);
    this._saveTheme();
    this.themeButtons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.theme === theme)));
    if (this._boardPage) this._boardPage._setTheme(theme);
  }

  _build() {
    this.root.textContent = "";
    this.shell = el("div", { class: "site", "data-style": this.theme });
    this.navHost = el("div", {});
    this.main = el("main", { class: "sitemain" });
    this.shell.appendChild(this.navHost);
    this.shell.appendChild(this.main);
    this.root.appendChild(this.shell);
  }

  async start() {
    await this._loadForts();
    await this._render();
  }

  async _loadForts() {
    const index = await fetchJson(`${this.dataRoot}/forts.json`).catch(() => null);
    this.forts = (index && Array.isArray(index.forts)) ? index.forts : [];
    this.fortMeta = this.forts.find((f) => f.current) || this.forts[0] || null;
    // Forts that ended, and the map's ring order, from the site's own text
    // file (site.json). A past fort the publisher already lists wins.
    this.siteText = await fetchJson(`${this.dataRoot}/site.json`).catch(() => ({}));
    (this.siteText.past_forts || []).forEach((f) => {
      if (!this.forts.some((x) => x.id === f.id)) this.forts.push({ ...f, current: false });
    });
  }

  async _ensureAgents() {
    if (this.agents) return;
    this.agents = await fetchJson(`${this.dataRoot}/agents.json`).catch(
      () => ({ role_order: [], planned_order: [], roles: {}, spokes: {}, sole_writer: null })
    );
  }

  async _ensureTools() {
    if (this.tools) return;
    this.tools = await fetchJson(`${this.dataRoot}/tools.json`).catch(() => ({ tools: [], areas: [] }));
  }

  async _ensureGotchas() {
    if (this.gotchas) return;
    this.gotchas = await fetchJson(`${this.dataRoot}/gotchas.json`).catch(() => []);
  }

  /** The current fort's own chat items (`open.json`), the same file
   * `StreamPage` reads for the board -- reused here, not re-fetched into a
   * second per-role file, so "Recent lines" shows exactly the public text
   * the board itself would show for that role. */
  async _ensureFeedItems() {
    if (this.feedItems) return;
    const root = this.fortMeta ? `${this.dataRoot}/forts/${this.fortMeta.id}` : this.dataRoot;
    const open = await fetchJson(`${root}/open.json`).catch(() => ({ items: [] }));
    this.feedItems = open.items || [];
  }

  async _ensureProjects() {
    if (this.fortProjects) return;
    const root = this.fortMeta ? `${this.dataRoot}/forts/${this.fortMeta.id}` : this.dataRoot;
    this.fortProjects = await fetchJson(`${root}/projects.json`).catch(() => ({ projects: {} }));
  }

  /** A few real numbers for the live fort's card, all from data the board
   * already publishes: the latest game date, proposals and projects. */
  _liveFortStats() {
    const items = this.feedItems || [];
    const latest = [...items].reverse().find((i) => i.game_date);
    const proposals = items.filter((i) => i.kind === "proposal");
    const accepted = proposals.filter((i) => i.badge === "accepted").length;
    const projects = Object.keys((this.fortProjects && this.fortProjects.projects) || {}).length;
    const lines = [];
    if (latest) lines.push(shortDate(latest.game_date));
    if (proposals.length) lines.push(`${spelledCount(proposals.length, "proposal", "proposals")}, ${accepted} accepted`);
    if (projects) lines.push(spelledCount(projects, "project", "projects"));
    return lines;
  }

  /** The Chronicle is a clearly marked stub (handoff item 5): one fixture
   * file of pretend data, never mixed into anything real this page reads
   * elsewhere. */
  async _ensureChronicleFixture() {
    if (this.chronicleFixture) return;
    this.chronicleFixture = await fetchJson("fixtures/chronicle-demo.json").catch(() => null);
  }

  _route() {
    const hash = (location.hash || "#board").slice(1);
    if (hash.startsWith("agent-")) return { view: "agents", param: hash.slice(6) };
    if (hash.startsWith("tool-")) return { view: "tools", param: hash.slice(5) };
    if (hash.startsWith("chronicle-")) return { view: "lost-chronicle", param: hash.slice(10) };
    if (["board", "chronicle", "agents", "tools", "forts"].includes(hash)) return { view: hash, param: null };
    return { view: "board", param: null };
  }

  _onHashChange() {
    const route = this._route();
    this._render();
    if (route.view !== "agents") window.scrollTo(0, 0);
    else if (window.innerWidth <= 900) {
      const panel = document.getElementById("site-apanel");
      if (panel) panel.scrollIntoView({ block: "start" });
    }
  }

  async _render() {
    const route = this._route();
    this._renderNav(route);
    this.main.textContent = "";
    // The Agents page is full-width (handoff item 2: the map/panel split
    // needs the room); every other view keeps the page's usual max-width.
    this.main.classList.add("full");
    this.main.classList.toggle("agentsview", route.view === "agents");
    // Agents fills the window exactly: the map stays put, only the open
    // tab's body scrolls.
    this.shell.classList.toggle("fullheight", ["agents", "board", "tools", "forts"].includes(route.view));
    if (route.view === "board") {
      this.main.appendChild(this._boardEl());
      return;
    }
    if (route.view === "chronicle") {
      await this._ensureChronicleFixture();
      this.main.appendChild(this._viewChronicle());
      return;
    }
    if (route.view === "lost-chronicle") {
      await this._ensureChronicleFixture();
      this.main.appendChild(this._viewLostChronicle(route.param));
      return;
    }
    if (route.view === "agents") {
      await this._ensureAgents();
      await this._ensureTools();
      await this._ensureGotchas();
      await this._ensureFeedItems();
      this.main.appendChild(await this._viewAgents(route.param));
      return;
    }
    if (route.view === "tools") {
      await this._ensureAgents();
      await this._ensureTools();
      await this._ensureGotchas();
      this.main.appendChild(route.param ? this._viewTool(route.param) : this._viewTools());
      return;
    }
    if (route.view === "forts") {
      await this._ensureFeedItems();
      await this._ensureProjects();
      this.main.appendChild(this._viewForts());
      return;
    }
  }

  // ---- nav: fort group (current fort, Board, Chronicle) + project group
  // (Agents, Tools, Forts) -- the mockup's header, built from forts.json's
  // own current fort rather than any name in this file. ------------------

  _renderNav(route) {
    this.navHost.textContent = "";
    const fortName = (this.fortMeta && this.fortMeta.name) || "Fortress";
    const current = route.view;
    const navLink = (hash, label, active) => el("a", {
      href: "#" + hash, "aria-current": active ? "page" : null, text: label,
    });
    // The current fort's own views sit inside one box with its name.
    const fortGroup = el("div", { class: "navgroup fortgroup" }, [
      el("span", { class: "fortpick", title: "The fort running now" }, [el("span", { class: "dot" }), document.createTextNode(" " + fortName)]),
      navLink("board", "Board", current === "board"),
      navLink("chronicle", "Chronicle", current === "chronicle"),
    ]);
    const projectGroup = el("div", { class: "navgroup" }, [
      navLink("agents", "Agents", current === "agents"),
      navLink("tools", "Tools", current === "tools"),
      navLink("forts", "Forts", current === "forts" || current === "lost-chronicle"),
    ]);
    this.themeButtons = THEMES.map((t) => el("button", {
      type: "button", "aria-pressed": String(t === this.theme), "data-theme": t,
      text: t === "terminal2" ? "Dark" : "Light",
      onclick: () => this._setTheme(t),
    }));
    const header = el("header", { class: "top" }, [
      el("div", { class: "brand" }, [document.createTextNode("df-overseer"), el("small", { text: "  a fort run by AI agents" })]),
      el("nav", { class: "nav", "aria-label": "Site" }, [fortGroup, projectGroup]),
    ]);
    this.navHost.appendChild(header);
  }

  // ---- Board: the existing StreamPage, completely untouched. A single
  // instance is kept across hash navigations (it keeps polling in the
  // background, same as it would standalone) rather than rebuilt. --------

  _boardEl() {
    if (!this._boardPage) {
      this._boardContainer = el("div", { class: "boardhost" });
      this._boardPage = new StreamPage({
        dataRoot: this.dataRoot, mode: this.mode, liveViewSrc: this.liveViewSrc,
        root: this._boardContainer, embedded: true,
      });
      this._boardPage.start();
    }
    return this._boardContainer;
  }

  // ---- Agents ------------------------------------------------------------

  async _viewAgents(selRaw) {
    let sel = null;
    if (selRaw) {
      const key = selRaw.endsWith("-charter") ? selRaw.slice(0, -8) : selRaw;
      if (this.agents.roles[key]) sel = key;
    }
    this.mapSel = sel;
    let panelBody;
    if (sel) {
      panelBody = [this._agentPanel(sel, selRaw.endsWith("-charter") ? "charter" : null)];
    } else {
      panelBody = this._panelIntro();
    }
    const mapWrap = el("div", { id: "site-mapwrap" }, [this._agentMapSvg()]);
    return el("div", {}, [
      el("div", { class: "asplit" }, [
        el("div", { class: "box amapbox" }, [
          el("div", { class: "mapstage" }, [mapWrap]),
        ]),
        el("aside", { class: "apanel", id: "site-apanel", "aria-live": "polite" }, panelBody),
      ]),
    ]);
  }

  _panelIntro() {
    return [el("div", { class: "sec" }, [
      el("div", { class: "faint small", text: "Point at an agent on the map to see its card. Click to open everything about it here: what it does, its record, the gotchas and vents it wrote, its tools and its charter." }),
      el("div", { class: "box legend" }, [
        el("span", { class: "faint", text: "spokes" }), el("span", { text: "Everything goes through the Overseer." }),
        el("span", { class: "faint", text: "width" }), el("span", { text: "A thicker spoke means more messages." }),
        el("span", { class: "faint", text: "dashed" }), el("span", { text: "A planned role, not built yet." }),
      ]),
    ])];
  }

  _spokeCard(key) {
    const extra = FIXED_EXTRAS[key];
    if (extra) {
      return el("div", { class: "box acard" + (extra.planned ? " planned" : "") }, [
        el("div", { class: "aname", style: `color:${extra.color}`, text: extra.name }),
        el("div", { class: "faint small", text: extra.kindLabel }),
        el("div", { class: "small", text: extra.line }),
      ]);
    }
    const r = this.agents.roles[key];
    if (!r) return null;
    const traffic = this.agents.spokes && this.agents.spokes[key];
    const lines = [];
    if (traffic) {
      const parts = [];
      if (traffic.out) parts.push(`${traffic.out[1] == null ? "some" : traffic.out[1]} ${traffic.out[0]} sent`);
      if (traffic.in) parts.push(`${traffic.in[1] == null ? "some" : traffic.in[1]} ${traffic.in[0]} back`);
      if (parts.length) lines.push(el("div", { class: "faint small traffic", text: parts.join(", ") + " so far" }));
    }
    return el("a", { class: "box acard" + (r.planned ? " planned" : ""), href: "#agent-" + key + (r.planned ? "-charter" : "") }, [
      el("div", { class: "aname", style: `color:${roleCssVar(key)}`, text: r.name }),
      el("div", { class: "faint small", text: r.planned ? r.kind_label : r.kind_label }),
      el("div", { class: "small", text: r.summary }),
      el("div", { class: "chips" }, [
        r.planned ? el("span", { class: "tagchip", text: "not enabled" }) : el("span", { class: "tagchip", text: spelledCount(r.tool_count, "tool", "tools") }),
        r.planned ? null : (r.model_label ? el("span", { class: "tagchip", text: r.model_label }) : null),
      ]),
      ...lines,
    ]);
  }

  _showMapPop(key) {
    const panel = document.getElementById("site-apanel");
    if (!panel || this.mapSel) return;
    const card = this._spokeCard(key);
    if (!card) return;
    panel.replaceChildren(el("div", { class: "sec" }, [card, (!FIXED_EXTRAS[key]) ? el("div", { class: "faint small", text: "Click to open." }) : null]));
  }

  _hideMapPop() {
    const panel = document.getElementById("site-apanel");
    if (panel && !this.mapSel) panel.replaceChildren(...this._panelIntro());
  }

  /** Spoke order and angle: `site.json`'s `map_ring` (degrees, 0 = right)
   * when it names a spoke, otherwise even spacing in `buildSpokeOrder`'s
   * order, so a new role still lands on the ring. */
  _ringLayout() {
    const order = buildSpokeOrder(this.agents);
    const ring = (this.siteText && this.siteText.map_ring) || {};
    const n = Math.max(order.length, 1);
    return order.map((sp, i) => ({ ...sp, angle: ring[sp.key] != null ? ring[sp.key] : -90 + (360 * i) / n }));
  }

  _agentMapSvg() {
    const order = this._ringLayout();
    const W = 1120, H = 700, NW = 210, NH = 64;
    const hub = { x: 470, y: 350 };
    const ry = 275, rx = ry * 1.18;
    const pos = (sp) => {
      const a = (sp.angle * Math.PI) / 180;
      return { x: hub.x + rx * Math.cos(a), y: hub.y + ry * Math.sin(a) };
    };
    const traffic = (key) => {
      const t = this.agents.spokes && this.agents.spokes[key];
      return ((t && t.out && t.out[1]) || 0) + ((t && t.in && t.in[1]) || 0);
    };
    const maxN = Math.max(1, ...order.map((sp) => traffic(sp.key)));
    // Where a line from a toward b leaves a box of half-size (hw, hh) centred on a.
    const leave = (a, b, hw, hh) => {
      const dx = b.x - a.x, dy = b.y - a.y;
      const t = Math.min(hw / Math.abs(dx || 1e-6), hh / Math.abs(dy || 1e-6));
      return { x: a.x + dx * t, y: a.y + dy * t };
    };

    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "xMidYMid meet", role: "img", "aria-label": "Every agent talks through the Overseer", class: "amap" });
    svg.append(svgEl("ellipse", { cx: hub.x, cy: hub.y, rx, ry, fill: "none", stroke: "var(--line)", "stroke-dasharray": "2 6" }));

    const nodeBox = (x, y, title, sub, color, opts) => {
      opts = opts || {};
      const hw = opts.hw || NW / 2, hh = opts.hh || NH / 2;
      const g = svgEl("g", { class: "mnode", tabindex: opts.link ? "0" : "-1", opacity: opts.dim ? "0.3" : "1" });
      if (opts.sel) g.append(svgEl("rect", { x: x - hw - 7, y: y - hh - 7, width: hw * 2 + 14, height: hh * 2 + 14, fill: "none", stroke: color, "stroke-width": "1", "stroke-dasharray": "2 3" }));
      g.append(svgEl("rect", { x: x - hw, y: y - hh, width: hw * 2, height: hh * 2, fill: "var(--raised)", stroke: color, "stroke-width": opts.planned ? "1.5" : "2", "stroke-dasharray": opts.planned ? "5 4" : "" }));
      if (opts.double) g.append(svgEl("rect", { x: x - hw + 5, y: y - hh + 5, width: hw * 2 - 10, height: hh * 2 - 10, fill: "none", stroke: color, "stroke-width": "1" }));
      const t1 = svgEl("text", { x, y: y - (opts.big ? 5 : 3), "text-anchor": "middle", fill: color, "font-size": opts.big ? "22" : "17", "font-weight": "700", "font-family": "inherit" });
      t1.textContent = title;
      g.append(t1);
      const t2 = svgEl("text", { x, y: y + (opts.big ? 21 : 18), "text-anchor": "middle", fill: "var(--faint)", "font-size": "13", "font-family": "inherit" });
      t2.textContent = sub;
      g.append(t2);
      if (opts.hoverKey) {
        const show = () => { this._showMapPop(opts.hoverKey); this.mapFocus = opts.hoverKey; };
        g.addEventListener("mouseenter", show);
        g.addEventListener("focus", show);
      }
      if (opts.link) {
        g.style.cursor = "pointer";
        const go = () => { location.hash = opts.link; };
        g.addEventListener("click", go);
        g.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
      }
      return g;
    };

    const focusKey = this.mapFocus || this.mapSel;
    const overseerKey = this.agents.sole_writer;
    const lines = svgEl("g", {});
    const nodes = svgEl("g", {});
    order.forEach((sp) => {
      const p = pos(sp);
      const dim = focusKey && focusKey !== sp.key && focusKey !== overseerKey;
      const w = sp.planned ? 1.5 : 1.5 + (4.5 * traffic(sp.key)) / maxN;
      const a = leave(p, hub, NW / 2 + 4, NH / 2 + 4), b = leave(hub, p, 122 + 4, 42 + 4);
      lines.append(svgEl("line", {
        x1: a.x, y1: a.y, x2: b.x, y2: b.y, stroke: roleCssVar(sp.key), "stroke-width": String(w),
        "stroke-dasharray": sp.planned ? "6 5" : "", opacity: dim ? "0.12" : "0.75",
      }));
      const extra = FIXED_EXTRAS[sp.key];
      const roleData = this.agents.roles[sp.key];
      const title = extra ? extra.name : (roleData ? roleData.name : sp.key);
      const kind = extra ? (sp.key === "will" ? "by Telegram" : "runs jobs") : (roleData ? roleData.kind_label : "");
      const sub = sp.planned && !/^planned/i.test(kind) ? kind + " · planned" : kind;
      const link = extra ? null : ("#agent-" + sp.key + (sp.planned ? "-charter" : ""));
      nodes.append(nodeBox(p.x, p.y, title, sub, roleCssVar(sp.key), {
        dim, sel: this.mapSel === sp.key, planned: sp.planned, double: !sp.planned, link, hoverKey: sp.key,
      }));
      if (sp.key === "executor") {
        // The fort hangs off the Executor, outside the ring.
        const fort = { x: p.x + 236, y: p.y };
        const fdim = focusKey && focusKey !== "executor";
        lines.append(svgEl("line", { x1: p.x + NW / 2 + 4, y1: p.y, x2: fort.x - 86, y2: fort.y, stroke: "var(--muted)", "stroke-width": "1.5", "stroke-dasharray": "6 5", opacity: fdim ? "0.12" : "0.75" }));
        nodes.append(nodeBox(fort.x, fort.y, "The fort", "Dwarf Fortress", "var(--text)", { dim: fdim, hw: 82, hh: 30 }));
      }
    });
    if (overseerKey && this.agents.roles[overseerKey]) {
      nodes.append(nodeBox(hub.x, hub.y, this.agents.roles[overseerKey].name, this.agents.roles[overseerKey].kind_label, roleCssVar(overseerKey), {
        sel: this.mapSel === overseerKey, big: true, double: true, hw: 122, hh: 42, link: "#agent-" + overseerKey, hoverKey: overseerKey,
      }));
    }
    svg.append(lines, nodes);
    svg.addEventListener("mouseleave", () => { this.mapFocus = null; this._hideMapPop(); this._redrawMap(); });
    return svg;
  }

  _redrawMap() {
    const wrap = document.getElementById("site-mapwrap");
    if (wrap) wrap.replaceChildren(this._agentMapSvg());
  }

  _agentPanel(role, forceTab) {
    const r = this.agents.roles[role];
    if (!r) return el("p", { class: "muted", text: "Unknown role." });
    if (this._agentTabFor !== role) { this.agentTab = r.planned ? "charter" : (new URLSearchParams(location.search).get("tab") || "tools"); this._agentTabFor = role; }
    if (forceTab) this.agentTab = forceTab;
    if (r.planned) this.agentTab = "charter";

    const mine = (this.tools ? this.tools.tools : []).filter((t) => t.roles.includes(role));
    const tabs = r.planned ? [["charter", "Charter"]] : [
      ["tools", `Tools ${mine.length}`], ["lines", "Recent lines"], ["charter", "Charter"],
    ];

    let body;
    if (this.agentTab === "tools") {
      body = this._toolTree(mine, role);
    } else if (this.agentTab === "lines") {
      body = this._recentLinesEl(role);
    } else {
      body = el("div", { class: "sec" }, [
        el("div", { class: "faint small", text: `agents/${role}/role.md` }),
        this._charterEl(r.charter_md),
        (r.charter_changes || []).length ? el("div", {}, [
          el("h2", { text: "Changes" }),
          el("div", { class: "box timeline" }, r.charter_changes.map(([d, t]) => el("div", { class: "tlrow" }, [el("span", { class: "trd", text: d }), el("span", { text: t })]))),
        ]) : null,
      ]);
    }

    const head = el("div", { class: "phead" }, [
      el("div", { class: "phrow" }, [
        el("h1", { style: `color:${roleCssVar(role)}`, text: r.name }),
        el("a", { href: "#agents", class: "tagchip", text: "close" }),
      ]),
      el("div", { class: "faint small", text: `${r.kind_label}${r.planned ? "" : " · " + (r.model_label || "unknown model") + " · " + spelledCount(mine.length, "tool", "tools")}` }),
      el("p", { class: "lede", text: r.summary || r.blocked_on || "" }),
    ]);
    const tabBar = el("div", { class: "tabs", role: "tablist" }, tabs.map(([k, l]) => el("button", {
      type: "button", role: "tab", class: "tabbtn", "aria-selected": String(this.agentTab === k),
      onclick: () => { this.agentTab = k; this._render(); }, text: l,
    })));
    return el("div", { class: "pbody" }, [head, tabBar, el("div", { class: "ptab", role: "tabpanel" }, [body])]);
  }

  /** `role.md` is this repo's own committed prose, never live/model/operator
   * output, so rendering it through `marked` (loaded, pinned, from cdnjs)
   * is the one place this page allows HTML from parsed text -- every link
   * `marked` would produce is immediately stripped back to plain text
   * first, so nothing clickable or script-bearing survives either way. A
   * page that has not loaded `marked` (network blocked) falls back to a
   * plain, fully inert `<pre>`. */
  _charterEl(md) {
    const box = el("article", { class: "box md" });
    if (window.marked) {
      box.innerHTML = window.marked.parse(md || "");
      box.querySelectorAll("a").forEach((a) => {
        const span = document.createElement("span");
        span.className = "ref";
        span.textContent = a.textContent;
        a.replaceWith(span);
      });
      box.querySelectorAll("script").forEach((s) => s.remove());
    } else {
      box.appendChild(el("pre", { text: md || "" }));
    }
    return box;
  }

  /** This role's own lines from the current fort's real feed (`open.json`,
   * the same file the board reads), grouped by game day with the board's
   * own `groupByDay`/`shortDate` helpers -- real data, never a fixture,
   * unlike the Chronicle tab. */
  _recentLinesEl(role) {
    const mine = (this.feedItems || []).filter((it) => it.role === role && (it.withheld || it.text));
    if (!mine.length) {
      return el("div", { class: "box" }, [el("div", { class: "faint", text: "Nothing in the current fort's feed yet." })]);
    }
    const groups = groupByDay(mine.slice(-60));
    return el("div", { class: "box" }, groups.map(([day, items]) => el("div", {}, [
      el("div", { class: "day", text: day ? shortDate(day) : "Now" }),
      ...items.map((it) => el("div", { class: "line" }, [
        document.createTextNode(it.withheld ? "(one message withheld)" : it.text),
        it.type ? el("div", { class: "ctx", text: it.type }) : null,
      ])),
    ])));
  }

  _toolTree(tools, role) {
    const gotchasFor = (toolId) => (this.gotchas || []).filter((g) => g.tool === toolId);
    const generalFor = (r) => (this.gotchas || []).filter((g) => !g.tool && g.by === r);
    const fams = {};
    tools.forEach((t) => {
      const fam = t.id.split(".")[0];
      (fams[fam] = fams[fam] || []).push(t);
    });
    const famGotchaCount = (fam) => fams[fam].reduce((n, t) => n + gotchasFor(t.id).length, 0);
    const names = Object.keys(fams).sort((a, b) => famGotchaCount(b) - famGotchaCount(a) || a.localeCompare(b));
    const gen = generalFor(role);
    const generalDetails = el("details", { class: "tfam", open: gen.length ? "" : null }, [
      el("summary", {}, [
        el("span", { class: "fname2", text: "general" }),
        el("span", { class: "faint small", text: "not about one tool" }),
        el("span", { class: "counts" }, countChips(gen)),
      ]),
      el("div", { class: "tlist" }, gen.length
        ? [el("div", { class: "tgs" }, gen.map((g) => gotchaEntryEl(g, { showTool: false })))]
        : [el("div", { class: "faint small", text: "Nothing general yet." })]),
    ]);
    const famEls = names.map((fam) => {
      const ts = fams[fam];
      const gs = ts.flatMap((t) => gotchasFor(t.id));
      return el("details", { class: "tfam" }, [
        el("summary", {}, [
          el("span", { class: "fname2", text: fam }),
          el("span", { class: "faint small", text: spelledCount(ts.length, "tool", "tools") }),
          el("span", { class: "counts" }, countChips(gs)),
        ]),
        el("div", { class: "tlist" }, ts.map((t) => {
          const tg = gotchasFor(t.id);
          return el("div", { class: "titem" }, [
            el("div", { class: "ehead" }, [
              el("a", { class: "tid2", href: "#tool-" + t.id, text: t.id }),
              t.write ? el("span", { class: "pill p-plain", text: "changes the fort" }) : null,
              el("span", { class: "counts" }, countChips(tg)),
            ]),
            t.description ? el("div", { class: "muted small", text: t.description }) : null,
            tg.length ? el("div", { class: "tgs" }, tg.map((g) => gotchaEntryEl(g, { showTool: false }))) : null,
          ]);
        })),
      ]);
    });
    return el("div", { class: "box ttree" }, [generalDetails, ...famEls]);
  }

  // ---- Tools ---------------------------------------------------------------

  _viewTools() {
    const render = () => {
      const q = this.toolFilter.q.toLowerCase();
      const list = this.tools.tools.filter((t) =>
        (!q || t.id.includes(q) || (t.description || "").toLowerCase().includes(q)) &&
        (!this.toolFilter.role || t.roles.includes(this.toolFilter.role)) &&
        (!this.toolFilter.only || (this.gotchas || []).some((g) => g.tool === t.id && g.list === this.toolFilter.only)) &&
        (this.toolFilter.ungranted || t.roles.length > 0)
      );
      const areas = [...this.tools.areas, "Other"];
      const groups = areas.map((a) => [a, list.filter((t) => t.area === a)]).filter(([, ts]) => ts.length);
      wrap.replaceChildren(
        el("div", { class: "faint small", text: `${list.length} of ${this.tools.tools.length} tools` + (this.toolFilter.ungranted ? "" : `, hiding ${this.tools.tools.filter((t) => !t.roles.length).length} no agent has`) }),
        // Each area is a dropdown: closed until opened, kept open across
        // filtering, and opened for every area while a search or filter
        // narrows the list.
        ...groups.map(([area, ts]) => el("details", {
          class: "tarea tfam", open: (this.toolAreasOpen.has(area) || q || this.toolFilter.role || this.toolFilter.only) ? "" : null,
          ontoggle: (e) => { if (e.currentTarget.open) this.toolAreasOpen.add(area); else this.toolAreasOpen.delete(area); },
        }, [
          el("summary", {}, [
            el("span", { class: "fname2", text: area }),
            el("span", { class: "faint small", text: spelledCount(ts.length, "tool", "tools") }),
            el("span", { class: "counts" }, countChips(ts.flatMap((t) => (this.gotchas || []).filter((g) => g.tool === t.id)))),
          ]),
          el("div", { style: "margin-top:6px" }, ts.map((t) => {
            const gs = (this.gotchas || []).filter((g) => g.tool === t.id);
            return el("a", { class: "trow", href: "#tool-" + t.id }, [
              el("span", { class: "tid", text: t.id }),
              el("span", { class: "tdesc", text: (t.write ? "Changes the fort. " : "") + (t.description || "No description yet.") }),
              el("span", { class: "roles" }, t.roles.length
                ? t.roles.map((r) => el("span", { class: "rdot", title: roleTitle(r), style: `background:${roleCssVar(r)}` }))
                : [el("span", { class: "faint small", text: "not granted" })]),
              el("span", { class: "counts" }, countChips(gs)),
            ]);
          })),
        ])),
      );
    };
    const wrap = el("div", { class: "sec scrollbody" });
    const roleBtn = (role, label) => el("button", {
      class: "tbtn", type: "button", "aria-pressed": String(this.toolFilter.role === role),
      onclick: () => { this.toolFilter.role = this.toolFilter.role === role ? null : role; this._render(); },
      text: label,
    });
    const onlyBtn = (key, label) => el("button", {
      class: "tbtn", type: "button", "aria-pressed": String(this.toolFilter.only === key),
      onclick: () => { this.toolFilter.only = this.toolFilter.only === key ? null : key; this._render(); },
      text: label,
    });
    const roleOrder = (this.agents && this.agents.role_order) || [];
    const filters = el("div", { class: "tfilters" }, [
      el("input", {
        type: "search", placeholder: "Search tools", value: this.toolFilter.q, "aria-label": "Search tools",
        oninput: (e) => { this.toolFilter.q = e.target.value; render(); },
      }),
      el("span", { class: "chips" }, roleOrder.map((r) => roleBtn(r, (this.agents.roles[r] && this.agents.roles[r].name) || roleTitle(r)))),
      el("span", { class: "chips" }, [["gotcha", "Has gotchas"], ["vent", "Has vents"], ["unexplained", "Has unexplained"]].map(([k, l]) => onlyBtn(k, l))),
      el("button", {
        class: "tbtn", type: "button", "aria-pressed": String(!!this.toolFilter.ungranted),
        onclick: (e) => { this.toolFilter.ungranted = !this.toolFilter.ungranted; e.currentTarget.setAttribute("aria-pressed", String(this.toolFilter.ungranted)); render(); },
        text: "Include tools no agent has",
      }),
    ]);
    render();
    return el("div", {}, [
      filters, wrap,
    ]);
  }

  _viewTool(id) {
    const t = (this.tools.tools || []).find((x) => x.id === id);
    if (!t) return this._viewTools();
    const gs = (this.gotchas || []).filter((g) => g.tool === id);
    const by = (list) => gs.filter((g) => g.list === list);
    const pile = by("gotcha").length + by("vent").length >= 4;
    const section = (title, list, emptyText) => el("div", { class: "sec" }, [
      el("h2", {}, [document.createTextNode(title + " "), el("span", { class: "n", text: String(list.length) })]),
      el("div", { class: "box" }, list.length ? list.map((g) => gotchaEntryEl(g, { showTool: false })) : [el("div", { class: "faint", text: emptyText })]),
    ]);
    const confidence = t.confidence || { level: "medium", note: "" };
    return el("div", {}, [
      el("div", { class: "crumbs" }, [el("a", { href: "#tools", text: "Tools" }), document.createTextNode(" / " + t.area + " / " + id)]),
      el("div", { class: "sec" }, [el("h1", { text: id }), el("p", { class: "lede", text: t.description || "No description yet." })]),
      el("div", { class: "scrollbody sec" }, [
      t.guide ? el("div", { class: "sec" }, [el("h2", { text: "How to use it" }), el("div", { class: "box guide", text: t.guide })]) : null,
      pile ? el("div", { class: "warnbar", text: "Gotchas and vents are piling up on this tool. The rule is to consider rebuilding it, or rewriting its description." }) : null,
      el("div", { class: "cols" }, [
        el("div", { class: "sec" }, [
          gs.length ? null : el("div", { class: "box faint", text: "No gotchas, vents or unexplained errors recorded for this tool yet." }),
          section("Gotchas", by("gotcha"), "None yet."),
          section("Vents", by("vent"), "No complaints yet."),
          section("Unexplained errors", by("unexplained"), "None."),
        ]),
        el("div", { class: "sec" }, [
          el("h2", { text: "About" }),
          el("div", { class: "box" }, [el("dl", { class: "kv" }, [
            el("dt", { text: "Effect" }), el("dd", { text: t.write ? "Changes the fort" : "Reads only" }),
            el("dt", { text: "Area" }), el("dd", { text: t.area }),
            el("dt", { text: "Confidence" }), el("dd", {}, [el("span", { class: confidencePillClass(confidence.level), text: confidence.level })]),
            el("dt", { text: "Used by" }), el("dd", { class: "chips" }, t.roles.length ? t.roles.map((r) => el("a", { class: "who", href: "#agent-" + r, style: `color:${roleCssVar(r)}`, text: roleTitle(r) })) : [el("span", { class: "faint", text: "No agent has this tool." })]),
          ])]),
          el("h2", { text: "What confidence means" }),
          el("div", { class: "box legend" }, [
            el("span", { class: "pill p-ok", text: "full" }), el("span", { text: "Just use it." }),
            el("span", { class: "pill p-warn", text: "medium" }), el("span", { text: "Read the description closely, check the gotchas, watch the result." }),
            el("span", { class: "pill p-bad", text: "low" }), el("span", { text: "Never run live, or known to be awkward. Dry-run first." }),
            el("span", {}), el("span", { class: "faint small", text: "Every tool starts at medium and only changes when we review it." }),
          ]),
        ]),
      ]),
      ]),
    ]);
  }

  // ---- Forts ---------------------------------------------------------------

  _viewForts() {
    const cards = this.forts.map((f) => el("a", {
      class: "box fcard", href: f.status === "lost" ? "#chronicle-" + f.id : "#chronicle", style: "text-decoration:none",
    }, [
      el("div", { class: "ehead" }, [el("span", { class: "fname", text: f.name }), el("span", { class: "pill " + (f.status === "live" ? "p-ok" : "p-bad"), text: f.status })]),
      ...(f.status === "live" ? this._liveFortStats() : [f.fate || ""]).filter(Boolean).map((line) => el("div", { class: "small muted", text: line })),
      el("div", { class: "faint small", text: f.status === "live" ? "Read its chronicle so far" : "Read its chronicle" }),
    ]));
    cards.push(el("div", { class: "box fcard planned" }, [
      el("div", { class: "ehead" }, [el("span", { class: "fname faint", text: "Next fort" }), el("span", { class: "pill p-plain", text: "planned" })]),
      el("div", { class: "small muted", text: "Starts once this fort runs smoothly." }),
      el("div", { class: "small muted", text: "Takes over the board, and starts a new chronicle. Same agents, tools and gotchas, with everything they learned." }),
    ]));
    return el("div", {}, [
      el("div", { class: "ptitle" }, [el("h1", { text: "Forts" }), el("span", { class: "scope", text: "all forts" })]),
      el("p", { class: "lede", text: "Every fort the agents have run, each with its chronicle. The board always shows the fort running now. Forts end; the agents, tools and gotchas carry on to the next one." }),
      el("div", { class: "grid scrollbody" }, cards),
    ]);
  }

  // ---- Chronicle: a clearly marked stub (handoff item 5) -------------------
  // Pretend data, kept in exactly one fixture file
  // (web/stream/fixtures/chronicle-demo.json), never mixed into real data
  // this page reads anywhere else.

  _exampleTag() {
    return el("span", { class: "example", text: "example data" });
  }

  _sparkChart(s) {
    const W = 300, H = 120, L = 34, R = 10, T = 12, B = 22;
    const max = Math.max(...s.v, 1);
    const x = (i) => L + (i * (W - L - R)) / (s.v.length - 1);
    const y = (v) => T + (1 - v / max) * (H - T - B);
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `${s.k} by month` });
    const col = s.tone === "bad" ? "var(--bad)" : "var(--chart, var(--g-now-line))";
    [0, max].forEach((v) => {
      svg.append(svgEl("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: "var(--grid, var(--line))", "stroke-width": "1" }));
      const t = svgEl("text", { x: L - 6, y: y(v) + 4, "text-anchor": "end", fill: "var(--faint)", "font-size": "10", "font-family": "inherit" });
      t.textContent = String(v);
      svg.append(t);
    });
    const pts = s.v.map((v, i) => `${x(i)},${y(v)}`).join(" ");
    svg.append(svgEl("polygon", { points: `${x(0)},${y(0)} ${pts} ${x(s.v.length - 1)},${y(0)}`, fill: s.tone === "bad" ? "transparent" : "var(--chart-fill, rgba(85,255,255,0.1))" }));
    svg.append(svgEl("polyline", { points: pts, fill: "none", stroke: col, "stroke-width": "2" }));
    svg.append(svgEl("circle", { cx: x(s.v.length - 1), cy: y(s.v[s.v.length - 1]), r: "3.5", fill: col }));
    [0, s.v.length - 1].forEach((i) => {
      const t = svgEl("text", { x: x(i), y: H - 6, "text-anchor": i ? "end" : "start", fill: "var(--faint)", "font-size": "10", "font-family": "inherit" });
      t.textContent = s.months[i];
      svg.append(t);
    });
    return el("div", { class: "box chart" }, [
      el("div", { class: "ch" }, [el("span", { class: "faint small", text: s.k.toUpperCase() }), el("span", { class: "now", style: `color:${col}`, text: String(s.v[s.v.length - 1]) })]),
      svg,
    ]);
  }

  /** One vital's value at the season's end and its change over the season
   * (`months` is [first, end) as month indexes into the vital's series). */
  _seasonDelta(v, months) {
    const [a, b] = months || [0, v.v.length];
    const start = a === 0 ? v.v[0] : v.v[a - 1];
    const end = v.v[Math.min(b, v.v.length) - 1];
    const d = end - start;
    // `worse` says which way is bad for this vital (deaths up, drink down).
    const bad = v.worse === "up" ? d > 0 : d < 0;
    const good = d !== 0 && !bad;
    return el("div", { class: "stat" }, [
      el("span", { text: v.k }),
      el("b", {}, [
        document.createTextNode(String(end)),
        el("small", { class: d === 0 ? "faint" : bad ? "oc-bad" : good ? "oc-ok" : "faint", text: d === 0 ? "  \u00b10" : `  ${d > 0 ? "+" : ""}${d}` }),
      ]),
    ]);
  }

  _chronThought(t) {
    return el("figure", { class: "thought", style: `border-color:${roleCssVar(t.by)}` }, [
      el("blockquote", { text: t.text }),
      el("figcaption", { class: "small" }, [
        el("span", { style: `color:${roleCssVar(t.by)};font-weight:600`, text: roleTitle(t.by) }),
        el("span", { class: "faint", text: t.by === "chronicler" ? " · its own aside" : " · quoted, " + (t.about || "") }),
      ]),
    ]);
  }

  _chronBlock(season) {
    const c = season.chron;
    return el("div", { class: "chron" }, [
      el("div", { class: "ctx small" }, [
        el("span", { style: `color:${roleCssVar("chronicler")};font-weight:600`, text: "Chronicler" }),
        el("span", { class: "faint", text: " · the season in brief" }),
      ]),
      el("p", { class: "account", text: c.account }),
      c.thoughts && c.thoughts.length ? el("div", { class: "thoughts" }, c.thoughts.map((t) => this._chronThought(t))) : null,
    ]);
  }

  _viewChronicle() {
    const fx = this.chronicleFixture;
    if (!fx) return el("p", { class: "muted", text: "The example chronicle data could not be loaded." });
    const seasons = fx.seasons || [];
    const EV = fx.event_kinds || {};
    return el("div", {}, [
      el("div", { class: "ptitle" }, [el("h1", { text: "Chronicle" }), this._exampleTag()]),
      el("p", { class: "lede", text: "The fort's story, season by season, as the Chronicler will tell it. This is example data: the Chronicler is not enabled yet, so none of it reflects the real fort." }),
      el("div", { class: "sec" }, [el("h2", { text: "The fort so far" }), el("div", { class: "charts" }, (fx.vitals || []).map((v) => this._sparkChart(v)))]),
      ...seasons.map((s, i) => {
        const all = this.showAllSeasons.has(i);
        const picked = s.events.filter((e) => e[3]);
        const shown = all ? s.events : picked;
        return el("section", { class: "sec" }, [
          el("h2", {}, [document.createTextNode(s.s + " "), s.result ? el("span", { class: "pill " + s.result[1], text: "goal " + s.result[0] }) : null]),
          el("div", { class: "box sec" }, [
            this._chronBlock(s),
            el("div", { class: "cols" }, [
              el("div", { class: "sec" }, [
                s.goal ? el("div", {}, [el("span", { class: "faint", text: "Goal  " }), document.createTextNode(s.goal)]) : el("div", { class: "faint", text: "No goal this season." }),
                s.end ? el("div", {}, [el("span", { class: "faint", text: "Result  " }), document.createTextNode(s.end)]) : null,
                s.review ? el("div", { class: "line" }, [el("div", { class: "ctx" }, [el("span", { style: `color:${roleCssVar("overseer")};font-weight:600`, text: "Overseer" }), document.createTextNode(" · review")]), document.createTextNode(s.review)]) : null,
                el("div", { class: "timeline" }, shown.map(([d, t, k]) => el("div", { class: "tlrow" }, [el("span", { class: "trd", text: d }), el("span", {}, [el("span", { class: "pill " + (EV[k] ? EV[k][1] : "p-plain"), text: EV[k] ? EV[k][0] : k }), document.createTextNode("  " + t)])]))),
                el("button", {
                  class: "tbtn", type: "button", "aria-pressed": String(all),
                  onclick: () => { all ? this.showAllSeasons.delete(i) : this.showAllSeasons.add(i); this._render(); },
                  text: all ? `Show only the Chronicler's ${picked.length}` : `Show all ${s.events.length} events (${s.events.length - picked.length} left out)`,
                }),
              ]),
              el("div", { class: "sec" }, [
                el("div", { class: "faint small", text: "This season" }),
                el("div", { class: "stats sstats" }, (fx.vitals || []).map((v) => this._seasonDelta(v, s.months))),
              ]),
            ]),
          ]),
        ]);
      }),
    ]);
  }

  _viewLostChronicle(id) {
    const fx = this.chronicleFixture;
    const lost = fx && fx.lost_forts && fx.lost_forts[id];
    if (!lost) return this._viewChronicle();
    const EV = fx.event_kinds || {};
    return el("div", {}, [
      el("div", { class: "crumbs" }, [el("a", { href: "#forts", text: "Forts" }), document.createTextNode(" / " + lost.name)]),
      el("div", {}, [el("h1", { text: lost.name + ": chronicle" }), document.createTextNode(" "), el("span", { class: "pill p-bad", text: "lost" }), document.createTextNode(" "), this._exampleTag()]),
      el("p", { class: "lede", text: "An archive: the chronicle as the fort ended. The board moved on to the next fort." }),
      el("section", { class: "sec" }, [
        el("h2", { text: lost.s }),
        el("div", { class: "box sec" }, [
          el("div", { class: "chron" }, [
            el("div", { class: "ctx small" }, [el("span", { style: `color:${roleCssVar("chronicler")};font-weight:600`, text: "Chronicler" }), el("span", { class: "faint", text: " · the fort in brief" })]),
            el("p", { class: "account", text: lost.account }),
          ]),
          el("div", { class: "timeline" }, lost.events.map(([d, t, k]) => el("div", { class: "tlrow" }, [el("span", { class: "trd", text: d }), el("span", {}, [el("span", { class: "pill " + (EV[k] ? EV[k][1] : "p-plain"), text: EV[k] ? EV[k][0] : k }), document.createTextNode("  " + t)])]))),
        ]),
      ]),
    ]);
  }
}

window.SitePage = SitePage;
