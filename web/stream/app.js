"use strict";
/* The stream page: fetches static JSON files built by dfqueue/feed.py and
 * renders them. Plain HTML/CSS/JS, no build step, no framework, no external
 * requests (research/2026-10-01-stream-page-design.md section 5's
 * "static-site constraint" and section 7.2 layer 5's inert rendering).
 *
 * `research/2026-10-01-stream-page-design.md` section 7.2, layer 5:
 * "Rendering is inert. The page inserts every text with `textContent`,
 * never as HTML." Every function below that shows model- or game-written
 * text uses `el()`'s `text` option, which is always `.textContent`. There
 * is no innerHTML assignment anywhere in this file with untrusted content —
 * grep this file for "innerHTML" during review if that is ever in doubt.
 *
 * This is slice S0 (design section 8): local, static files only, no live
 * VM access, no polling of a real relay. `POLL_MS` and the Page Visibility
 * behaviour are implemented per design section 4.3 so this code needs no
 * changes when a real publisher exists in slice S1 — only `dataRoot`
 * changes, from a local folder to `/data/public/` or `/data/operator/`.
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
// stable-enough label; see the gaps note rendered under the panel.
const WHOS_WHO = [
  { role: "Overseer", does: "Arbitrates proposals, sets priorities, writes the plan, and is the only one who acts on the fort." },
  { role: "Architect", does: "Proposes rooms, workshops, stockpile siting, corridors, dig order. Never acts." },
  { role: "Quartermaster", does: "Proposes food, drink, seed and work-order plans. Never acts." },
  { role: "Consultant", does: "Answers Dwarf Fortress domain questions on demand. Never decides." },
  { role: "System (the conductor)", does: "Code, not an AI model: runs the game clock, wakes the other roles, and reports what code itself did (a finished step)." },
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

/** design section 6.2 item 10: Highlights (default) hides passes and
 * routine step completions; Everything shows all. Role is a secondary
 * filter. Kept as pure predicates so a test file (not written for the page
 * itself — see web/stream/README.md's gap note) could exercise them. */
function isHighlight(item) {
  if (item.kind === "pass") return false;
  if (item.kind === "executed") return false; // routine step completion
  return true;
}

class StreamPage {
  constructor({ dataRoot, mode, root, liveViewSrc }) {
    this.dataRoot = dataRoot;
    // The live view is the existing noVNC viewer on the same origin, embedded.
    // Only when served from the real site: a local build has no viewer.
    this.liveViewSrc = liveViewSrc && location.port === "" ? liveViewSrc : null;
    this.mode = mode; // "public" | "operator"
    this.root = root;
    this.tab = "chat";
    this.filter = "highlights";
    this.roleFilter = "all";
    this.items = [];
    this.projects = { thread_to_project: {}, projects: {} };
    this.status = null;
    this.lastSeq = 0;
    this.atBottom = true;
    this.newSinceScroll = 0;
    this.itemsById = new Map();
    this._build();
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
    // S0 has no closed segments to speak of in the small local exports this
    // slice ships with, and no history-scrolling UI yet (see README's gap
    // note) -- only the open segment is rendered.
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

  // ---- chrome: header, video, status ------------------------------------

  _build() {
    this.root.textContent = "";
    this.el = {};

    const header = this._buildHeader();
    const layout = el("div", { class: "layout" });
    const left = this._buildLeftColumn();
    const chat = this._buildChatPanel();
    layout.appendChild(left);
    layout.appendChild(chat);

    this.root.appendChild(header);
    this.root.appendChild(this.whoswhoPanel);
    this.root.appendChild(el("p", { class: "header explainer", text: this._explainerText() }));
    this.root.appendChild(layout);
    this.root.appendChild(this._buildGapsNote());
  }

  _explainerText() {
    return "A Dwarf Fortress colony run by AI agents. Nobody is playing. This is what they are saying to each other.";
  }

  _buildHeader() {
    const title = el("h1", { text: "Ragwind" });
    const subtitle = el("span", {
      class: "subtitle",
      text: "Uniboslan, run by four AI agents and a scheduler",
    });
    const titles = el("div", { class: "header-titles" }, [title, subtitle]);

    const whoswhoBtn = el("button", {
      class: "whoswho-btn",
      text: "Who's who",
      "aria-expanded": "false",
      onclick: () => this._toggleWhosWho(),
    });
    this.whoswhoBtn = whoswhoBtn;

    const controls = el("div", { style: "display:flex;align-items:center;gap:8px" }, [whoswhoBtn]);
    if (this.mode === "operator") {
      const toggle = el("button", {
        class: "operator-toggle",
        text: this.showAsPublic ? "Showing: Public preview" : "Showing: Operator",
        "aria-pressed": String(!!this.showAsPublic),
        onclick: () => this._toggleShowAsPublic(),
      });
      this.operatorToggleBtn = toggle;
      controls.appendChild(toggle);
    }

    this.whoswhoPanel = el(
      "div",
      { class: "whoswho-panel", hidden: true },
      WHOS_WHO.map((w) =>
        el("div", { class: "whoswho-row" }, [
          el("strong", { text: w.role + ": " }),
          el("span", { class: "allow", text: w.does }),
        ])
      ).concat([
        el("div", {
          class: "gaps-note",
          text: "Model names and exact tool allowlists are not shown here yet (S0 gap; see web/stream/README.md).",
        }),
      ])
    );

    return el("div", { class: "header" }, [titles, controls]);
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

  _buildLeftColumn() {
    const frame = this.liveViewSrc
      ? el("div", { class: "video-frame" }, [
          el("iframe", { class: "live-view", src: this.liveViewSrc, title: "Live view of the fortress", allow: "fullscreen" }),
          el("span", { class: "live-badge live", text: "LIVE" }),
        ])
      : el("div", { class: "video-frame" }, [
          el("span", { class: "live-badge offline", text: "OFFLINE" }),
          el("div", { class: "placeholder" }, [
            el("div", { class: "tag", text: "LIVE VIEW" }),
            el("div", { class: "sub", text: "The live view appears here on the real site." }),
          ]),
        ]);
    this.videoFrame = frame;
    this.liveBadge = frame.querySelector(".live-badge");

    this.rightNow = el("div", { class: "right-now" }, [
      el("span", { text: "No live status source yet." }),
    ]);

    this.goalCard = el("div", { class: "goal-card" }, [
      el("span", { class: "label", text: "SEASON GOAL" }),
      el("div", { class: "empty", text: "No season goal has been set yet." }),
    ]);

    return el("div", { class: "left-col" }, [frame, this.rightNow, this.goalCard]);
  }

  _renderStatus() {
    if (!this.status || this.status.available === false) {
      this.liveBadge.className = "live-badge offline";
      this.liveBadge.textContent = "OFFLINE";
      this.rightNow.textContent = "";
      this.rightNow.appendChild(
        el("span", {
          class: "stale",
          text: this.status && this.status.note ? this.status.note : "No live status source yet.",
        })
      );
      return;
    }
    // design section 3.1's feed.status is not built (GAPS); this branch is
    // future-proofing for the day status.json carries real fields.
    const state = this.status.state || "offline";
    this.liveBadge.className = `live-badge ${state}`;
    this.liveBadge.textContent = state.toUpperCase();
    this.rightNow.textContent = "";
    this.rightNow.appendChild(el("span", { text: this.status.right_now || "" }));
  }

  _buildGapsNote() {
    return el("p", {
      class: "gaps-note",
      text:
        "This is slice S0: local test data only, no live VM access. " +
        "Fort status, the season goal, step labels, project timelines and " +
        "history scrolling are not built yet — see web/stream/README.md.",
    });
  }

  // ---- chat panel -------------------------------------------------------

  _buildChatPanel() {
    const panel = el("div", { class: "chat-panel" });

    const tabs = el("div", { class: "tabs", role: "tablist" }, [
      el("button", {
        class: "tab", text: "Chat", role: "tab", "aria-selected": "true",
        onclick: () => this._selectTab("chat"),
      }),
      el("button", {
        class: "tab", text: "Projects", role: "tab", "aria-selected": "false",
        onclick: () => this._selectTab("projects"),
      }),
      el("button", {
        class: "tab", text: "Season", role: "tab", "aria-selected": "false",
        onclick: () => this._selectTab("season"),
      }),
    ]);
    this.tabButtons = Array.from(tabs.children);

    this.filterBar = el("div", { class: "filters" }, [
      el("button", {
        class: "chip", text: "Highlights", "aria-pressed": "true",
        onclick: () => this._selectFilter("highlights"),
      }),
      el("button", {
        class: "chip", text: "Everything", "aria-pressed": "false",
        onclick: () => this._selectFilter("everything"),
      }),
      this._buildRoleSelect(),
    ]);
    this.filterChips = Array.from(this.filterBar.querySelectorAll(".chip"));

    this.messagesEl = el("div", {
      class: "messages", "aria-live": "polite", "aria-relevant": "additions",
    });
    this.messagesEl.addEventListener("scroll", () => this._onScroll());

    this.jumpLatestBtn = el("button", {
      class: "chip jump-latest", text: "Jump to latest", hidden: true,
      onclick: () => this._jumpToLatest(),
    });
    const chatFooter = el("div", { class: "chat-footer" }, [this.jumpLatestBtn]);

    this.chatSection = el("div", {}, [this.filterBar, this.messagesEl, chatFooter]);
    this.projectsSection = el("div", { class: "projects-panel", hidden: true });
    this.seasonSection = el("div", {
      class: "season-panel", hidden: true,
    }, [el("p", { text: "No finished season yet. The chronicle appears here once one exists (design section 6.6, slice S7)." })]);

    panel.appendChild(tabs);
    panel.appendChild(this.chatSection);
    panel.appendChild(this.projectsSection);
    panel.appendChild(this.seasonSection);
    return panel;
  }

  _buildRoleSelect() {
    const roles = ["all", "overseer", "architect", "quartermaster", "consultant", "conductor"];
    const select = el("select", {
      class: "role-select",
      onchange: (e) => {
        this.roleFilter = e.target.value;
        this._renderMessages();
      },
    });
    roles.forEach((r) => {
      const opt = document.createElement("option");
      opt.value = r;
      opt.textContent = r === "all" ? "All roles" : roleTitle(r);
      select.appendChild(opt);
    });
    return select;
  }

  _selectTab(tab) {
    this.tab = tab;
    this.tabButtons.forEach((btn) => {
      btn.setAttribute("aria-selected", String(btn.textContent.toLowerCase() === tab || (tab === "chat" && btn.textContent === "Chat")));
    });
    this.chatSection.hidden = tab !== "chat";
    this.projectsSection.hidden = tab !== "projects";
    this.seasonSection.hidden = tab !== "season";
    if (tab === "projects") this._renderProjects();
  }

  _selectFilter(filter) {
    this.filter = filter;
    this.filterChips.forEach((chip) => {
      chip.setAttribute("aria-pressed", String(chip.textContent.toLowerCase() === filter));
    });
    this._renderMessages();
  }

  _onScroll() {
    const el_ = this.messagesEl;
    const atBottom = el_.scrollHeight - el_.scrollTop - el_.clientHeight < 24;
    this.atBottom = atBottom;
    if (atBottom) {
      this.newSinceScroll = 0;
      this.jumpLatestBtn.hidden = true;
    }
  }

  _jumpToLatest() {
    this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
    this.newSinceScroll = 0;
    this.jumpLatestBtn.hidden = true;
  }

  // ---- rendering items ----------------------------------------------------

  _visibleItems() {
    return this.items.filter((item) => {
      if (this.filter === "highlights" && !isHighlight(item)) return false;
      if (this.roleFilter !== "all" && item.role !== this.roleFilter) return false;
      return true;
    });
  }

  _render() {
    this._renderStatus();
    this._renderMessages();
    if (this.tab === "projects") this._renderProjects();
  }

  _renderMessages() {
    const wasAtBottom = this.atBottom;
    this.messagesEl.textContent = "";
    const visible = this._visibleItems();
    visible.forEach((item) => this.messagesEl.appendChild(this._renderItem(item)));
    if (visible.length === 0) {
      this.messagesEl.appendChild(
        el("p", { class: "empty-note", text: "Nothing here yet. Run the export script (web/stream/README.md) to load real past conversation." })
      );
    }
    if (wasAtBottom) {
      this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
    }
  }

  _renderItem(item) {
    if (item.kind === "escalation") return this._renderEscalation(item);
    if (item.kind === "proposal") return this._renderProposal(item);
    if (item.kind === "ruling") return this._renderRuling(item);
    if (item.kind === "executed") return this._renderSystemLine(item);
    if (item.kind === "pass") return this._renderCollapsed(item);
    if (item.kind === "ask" || item.kind === "answer") return this._renderCollapsed(item);
    return this._renderGeneric(item);
  }

  _head(item, extra) {
    const who = el("span", {
      class: "msg-who", text: speakerName(item),
      style: `color:${ROLE_COLORS[item.role] || "var(--text)"}`,
    });
    const when = el("span", {
      class: "msg-when",
      text: item.game_date || "",
      title: item.ts || "",
    });
    const parts = [who, when];
    if (extra) parts.push(extra);
    return el("div", { class: "msg-head" }, parts);
  }

  _replyQuote(item) {
    if (!item.reply_to) return null;
    const original = this.itemsById.get(item.reply_to);
    const label = original
      ? `replying to ${speakerName(original)}: ${(original.text || "(no public text)").slice(0, 80)}`
      : `replying to ${item.reply_to}`;
    return el("div", {
      class: "msg-reply-quote", text: label,
      onclick: () => this._scrollToItem(item.reply_to),
    });
  }

  _scrollToItem(id) {
    const node = this.messagesEl.querySelector(`[data-item-id="${CSS.escape(id)}"]`);
    if (node) node.scrollIntoView({ block: "center" });
  }

  _projectChip(item) {
    const projectId = this.projects.thread_to_project
      ? this.projects.thread_to_project[item.thread]
      : null;
    if (!projectId) return null;
    return el("button", {
      class: "msg-project-chip", text: projectId,
      onclick: () => this._selectTab("projects"),
    });
  }

  _bodyText(item) {
    if (item.withheld) return "(one message withheld)";
    return item.text || `(${item.kind}, no public text yet)`;
  }

  _operatorDetail(item) {
    if (this.mode !== "operator" || this.showAsPublic) return null;
    const record = item.record || {};
    const line = JSON.stringify({ kind: record.kind, role: record.role, id: record.id });
    return el("div", { class: "msg-detail", text: line });
  }

  _wrap(item, bodyClass, bodyText, headExtra) {
    const container = el("div", { class: "msg", "data-item-id": item.id });
    container.appendChild(this._head(item, headExtra));
    const quote = this._replyQuote(item);
    if (quote) container.appendChild(quote);
    container.appendChild(el("div", { class: `msg-body ${bodyClass}`, text: bodyText }));
    const detail = this._operatorDetail(item);
    if (detail) container.appendChild(detail);
    return container;
  }

  _renderProposal(item) {
    const badge = el("span", {
      class: `msg-badge ${item.badge || "pending"}`,
      text: item.badge || "pending",
    });
    const chip = this._projectChip(item);
    const extra = chip ? el("span", {}, [badge, chip]) : badge;
    return this._wrap(item, "", this._bodyText(item), extra);
  }

  _renderRuling(item) {
    const chip = this._projectChip(item);
    return this._wrap(item, "", this._bodyText(item), chip);
  }

  _renderSystemLine(item) {
    const chip = this._projectChip(item);
    return this._wrap(item, "system", this._bodyText(item), chip);
  }

  _renderCollapsed(item) {
    return this._wrap(item, "system", this._bodyText(item));
  }

  _renderEscalation(item) {
    const container = this._wrap(item, "system", this._bodyText(item));
    container.classList.add("msg-escalation");
    return container;
  }

  _renderGeneric(item) {
    if (item.role === "user") {
      return this._wrap(item, "you", this._bodyText(item));
    }
    return this._wrap(item, "", this._bodyText(item));
  }

  // ---- projects tab -------------------------------------------------------

  _renderProjects() {
    this.projectsSection.textContent = "";
    const entries = Object.values(this.projects.projects || {});
    if (entries.length === 0) {
      this.projectsSection.appendChild(
        el("p", { class: "empty-note", text: "No projects in this export yet." })
      );
      return;
    }
    const active = entries.filter((p) => !p.abandoned);
    const abandoned = entries.filter((p) => p.abandoned);

    this.projectsSection.appendChild(el("div", { class: "section-label", text: "ACTIVE" }));
    active.forEach((p) => this.projectsSection.appendChild(this._projectCard(p)));
    if (abandoned.length) {
      this.projectsSection.appendChild(el("div", { class: "section-label", text: "RECENTLY FINISHED" }));
      abandoned.forEach((p) => this.projectsSection.appendChild(this._projectCard(p)));
    }
    this.projectsSection.appendChild(
      el("p", {
        class: "gaps-note",
        text: "Per-step progress, timelines and public titles are not built yet (design section 3.3 item 6, section 6.5; slice S4).",
      })
    );
  }

  _projectCard(p) {
    const statusClass = p.abandoned ? "abandoned" : "active";
    const statusText = p.abandoned ? "abandoned" : "active";
    const meta = [
      `version ${p.version || 1}`,
      this.mode === "operator" && p.summary ? p.summary : null,
      this.mode === "operator" && p.abandoned_reason ? `abandoned: ${p.abandoned_reason}` : null,
    ].filter(Boolean).join(" — ");
    return el("div", { class: "project-card" }, [
      el("div", { class: "project-card-head" }, [
        el("button", { class: "project-name", text: p.id }),
        el("span", { class: `project-status ${statusClass}`, text: statusText }),
      ]),
      el("div", { class: "project-meta", text: meta }),
    ]);
  }
}

window.StreamPage = StreamPage;
