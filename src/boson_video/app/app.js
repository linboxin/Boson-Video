"use strict";
// The product's one page: invite code → paste a link or drop a file → read and ask.
// A video: the player, the ribbon (hover to see the frame and the words at any second) and the
// readout on the left; Summary, Transcript, Terms, Scenes and Ask on the right, in the original,
// both languages, or English. Plain JS, no libraries; text from the video always goes in as text.
(() => {
  const ICON = {
    arrow: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
    up: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M6 11l6-6 6 6"/></svg>',
    clip: '<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5l-8.6 8.6a5.2 5.2 0 0 1-7.4-7.4l8.6-8.6a3.5 3.5 0 0 1 4.9 4.9l-8.6 8.6a1.7 1.7 0 0 1-2.5-2.5l7.9-7.9"/></svg>',
    back: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg>',
    check: '<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  };
  const LANGS = { zh: ["Chinese", "中文"], yue: ["Cantonese", "粵語"], ja: ["Japanese", "日本語"], ko: ["Korean", "한국어"],
                  en: ["English", "English"], es: ["Spanish", "Español"], fr: ["French", "Français"], de: ["German", "Deutsch"] };
  const STAGES = ["queued", "scenes", "words", "screens", "summary", "done"];
  const MARKS = {
    supported: ["ok", "✓", "Checked: matches what was said"],
    contradicted: ["bad", "✗", "What was said says otherwise"],
    unsupported: ["warn", "?", "The passages it cites don't say this"],
    uncited: ["warn", "?", "No passage cited"],
  };
  const KINDS = { new: "new visual", repeat: "seen before", base: "base shot" };
  const GLOSSED = 2;  // a term carries its English above it on its first mentions; later ones are only underlined

  // ---- small helpers
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (k === "class") el.className = v;
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat(Infinity)) {
      if (kid == null || kid === false || kid === "") continue;
      el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
    return el;
  }
  const icon = name => { const s = document.createElement("span"); s.className = "ic"; s.innerHTML = ICON[name]; return s; };
  const bot = (...kids) => h("article", { class: "bot" }, ...kids);
  const clock = t => {
    t = Math.max(0, Math.floor(t || 0));
    const hh = Math.floor(t / 3600), mm = Math.floor(t / 60) % 60, ss = String(t % 60).padStart(2, "0");
    return hh ? `${hh}:${String(mm).padStart(2, "0")}:${ss}` : `${mm}:${ss}`;
  };
  const length = t => { t = Math.round(t); return t >= 60 ? `${Math.floor(t / 60)} min ${String(t % 60).padStart(2, "0")} s` : `${t} s`; };
  const lang = code => LANGS[(code || "").split("_")[0]] || null;
  const checkedBy = c => ({ "jev+code": "Jev and code", jev: "Jev", code: "code (numbers only)" })[c] || c || "nothing yet";
  const two = (orig, en) => !!(en && en.trim() && en.trim() !== (orig || "").trim());
  // The original with its English: CSS shows one, the other, or both (.lang-orig / .lang-both / .lang-en).
  function bi(orig, en, tag = "span", cls = "") {
    return h(tag, { class: `${cls}${two(orig, en) ? " has-en" : ""}`.trim() },
      h("span", { class: "t-orig" }, orig), two(orig, en) ? h("span", { class: "t-en", lang: "en" }, en) : null);
  }
  function mark(x) {
    const m = MARKS[x.check];
    if (!m) return null;
    const why = x.note ? `${m[2]}: ${x.note}` : x.p ? `${m[2]} (Jev ${Number(x.p).toFixed(2)})` : m[2];
    return h("span", { class: `mark ${m[0]}`, title: why, "aria-label": why }, m[1]);
  }

  async function api(path, body) {
    const opts = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json", "X-BV": "1" }, body: JSON.stringify(body) };
    const r = await fetch(path, opts);
    let data = {};
    try { data = await r.json(); } catch { /* not JSON */ }
    if (r.status === 401) ME = { in: false, videos: [] };
    if (!r.ok) throw new Error(data.error || `Something went wrong (${r.status}).`);
    return data;
  }

  // ---- pages
  const root = document.getElementById("root");
  const mount = node => root.replaceChildren(node);
  let ME = { in: false, videos: [] };
  let view = null;
  let onDrop = null;

  function go(path) { history.pushState(null, "", path); route(); }
  window.addEventListener("popstate", route);
  document.addEventListener("click", e => {
    const a = e.target.closest("a[data-nav]");
    if (!a || e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault();
    go(a.getAttribute("href"));
  });
  document.addEventListener("dragover", e => {
    if (!onDrop || !e.dataTransfer || ![...e.dataTransfer.types].includes("Files")) return;
    e.preventDefault();
    document.body.classList.add("dragging");
  });
  document.addEventListener("dragleave", e => { if (!e.relatedTarget) document.body.classList.remove("dragging"); });
  document.addEventListener("drop", e => {
    document.body.classList.remove("dragging");
    if (!onDrop) return;
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f) onDrop(f);
  });

  function route() {
    if (view) { view.stop(); view = null; }
    onDrop = null;
    if (!ME.in) return gate();
    const m = location.pathname.match(/^\/v\/([A-Za-z0-9_-]{1,64})$/);
    if (m) { view = new Watch(m[1]); return; }
    home();
  }

  function gate() {
    document.title = "Invite only";
    const input = h("input", { placeholder: "Invite code", autocomplete: "off", autocapitalize: "characters", spellcheck: "false", maxlength: "14", "aria-label": "Invite code" });
    const msg = h("p", { class: "msg", role: "status" });
    const form = h("form", { class: "gate", onsubmit: async e => {
      e.preventDefault();
      msg.textContent = "";
      try {
        await api("/api/join", { code: input.value });
        ME = await api("/api/me");
        route();
      } catch (err) { msg.textContent = err.message; input.select(); }
    } },
      h("p", { class: "lede" }, "Read any video like a document."),
      h("div", { class: "box" }, input, h("button", { class: "go", type: "submit", "aria-label": "Enter" }, icon("arrow"))),
      msg);
    mount(h("main", { class: "center" }, form));
    input.focus();
  }

  async function home() {
    document.title = "Read a video";
    try { ME = await api("/api/me"); } catch { /* keep what we had */ }
    if (!ME.in) return gate();
    const msg = h("p", { class: "msg", role: "status" });
    const fill = h("i");
    const bar = h("div", { class: "bar", hidden: true }, fill);
    const input = h("input", { type: "text", inputmode: "url", autocomplete: "off", spellcheck: "false", "aria-label": "YouTube link",
                               placeholder: ME.hosted ? "Choose a video file to read" : "Paste a YouTube link" });
    const picker = h("input", { type: "file", accept: "video/*,.mkv", hidden: true, onchange: () => picker.files[0] && upload(picker.files[0]) });
    function upload(file) {
      msg.textContent = "";
      bar.hidden = false;
      fill.style.width = "0%";
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/upload");
      xhr.setRequestHeader("X-BV", "1");
      xhr.setRequestHeader("X-Name", encodeURIComponent(file.name));
      xhr.upload.onprogress = e => { if (e.lengthComputable) fill.style.width = `${(100 * e.loaded / e.total).toFixed(1)}%`; };
      xhr.onload = () => {
        let d = {};
        try { d = JSON.parse(xhr.responseText); } catch { /* not JSON */ }
        if (xhr.status === 200) return go(`/v/${d.key}`);
        bar.hidden = true;
        msg.textContent = d.error || "The upload didn't go through.";
      };
      xhr.onerror = () => { bar.hidden = true; msg.textContent = "The upload didn't go through."; };
      xhr.send(file);
    }
    onDrop = upload;
    const form = h("form", { class: "box", onsubmit: async e => {
      e.preventDefault();
      const link = input.value.trim();
      if (!link) { if (ME.hosted) picker.click(); return; }
      msg.textContent = "";
      try { go(`/v/${(await api("/api/open", { link })).key}`); } catch (err) { msg.textContent = err.message; }
    } },
      h("button", { type: "button", class: "icon-btn", title: "Upload a video file", "aria-label": "Upload a video file", onclick: () => picker.click() }, icon("clip")),
      input,
      h("button", { type: "submit", class: "go", "aria-label": "Open" }, icon("arrow")));
    const list = ME.videos && ME.videos.length
      ? h("section", { class: "recent" }, h("h2", {}, "Your videos"), h("ul", {}, ME.videos.map(card)))
      : null;
    mount(h("main", { class: "home" },
      h("h1", {}, "What do you want to read?"),
      form,
      h("p", { class: "hint" }, ME.hosted ? "Video files up to 2 GB. YouTube links come with the browser extension." : "Or drop a video file anywhere on this page."),
      bar, msg, picker, list));
    if (!matchMedia("(pointer: coarse)").matches) input.focus();
  }

  function card(v) {
    const busy = v.stage && !["done", "missing"].includes(v.stage);
    const sub = [v.channel, v.duration ? clock(v.duration) : "", v.stage === "error" ? "stopped" : busy ? "reading…" : ""].filter(Boolean).join(" · ");
    return h("li", {}, h("a", { href: `/v/${v.key}`, "data-nav": "" },
      h("img", { src: v.poster, alt: "", loading: "lazy" }),
      h("div", {}, h("b", {}, v.title || "Getting the video…"), h("span", {}, sub))));
  }

  // ---- the YouTube player, loaded once
  let ytReady = null;
  function loadYT() {
    if (window.YT && window.YT.Player) return Promise.resolve();
    if (!ytReady) ytReady = new Promise(resolve => {
      window.onYouTubeIframeAPIReady = resolve;
      document.head.append(h("script", { src: "https://www.youtube.com/iframe_api" }));
    });
    return ytReady;
  }

  const TABS = [["summary", "Summary"], ["words", "Transcript"], ["terms", "Terms"], ["scenes", "Scenes"], ["ask", "Ask"]];

  class Watch {
    constructor(key) {
      this.key = key;
      this.doc = null;
      this.mode = null;  // "orig" | "both" | "en", chosen when the words arrive
      this.chose = false;
      this.tab = "summary";
      this.alive = true;
      this.player = null;
      this.video = null;
      this.lines = null;
      this.cur = -1;
      this.lastScroll = 0;
      this.followOn = true;
      this.looking = false;
      this.build();
      this.load();
      this.tick = setInterval(() => this.follow(), 300);
      this.onKey = e => { if (e.key === "Escape") this.hideCard(); };
      this.onDocClick = e => { if (this.cardEl && !this.cardEl.contains(e.target) && !e.target.closest("ruby.term")) this.hideCard(); };
      document.addEventListener("keydown", this.onKey);
      document.addEventListener("click", this.onDocClick);
    }

    stop() {
      this.alive = false;
      clearTimeout(this.timer);
      clearInterval(this.tick);
      this.hideCard();
      document.removeEventListener("keydown", this.onKey);
      document.removeEventListener("click", this.onDocClick);
    }

    build() {
      const E = this.el = {};
      E.player = h("div", { class: "player" }, h("div", { class: "wait" }, "Getting the video…"));
      E.title = h("h1");
      E.sub = h("p", { class: "sub" });
      E.headline = h("p", { class: "headline" });
      E.stats = h("p", { class: "stats" });
      E.ribbon = h("div", { class: "ribbon" });
      E.legend = h("div", { class: "legend" });
      E.roFrame = h("div", { class: "f" });
      E.roTime = h("button", { class: "t", type: "button", onclick: () => this.seek(this.roAt || 0) }, "0:00");
      E.roWhere = h("span", { class: "ro-where" });
      E.roSaid = h("div", { class: "ro-said" });
      E.readout = h("div", { class: "readout", "aria-live": "polite", hidden: true }, E.roFrame,
        h("div", { class: "ro-text" }, h("div", {}, E.roTime, E.roWhere), E.roSaid));
      E.panes = {};
      E.tabs = {};
      for (const [id, label] of TABS) {
        E.tabs[id] = h("button", { class: "tab", role: "tab", "aria-selected": String(id === this.tab), onclick: () => this.show(id) }, label, h("span", { class: "count" }));
        E.panes[id] = h("div", { class: "pane", role: "tabpanel", hidden: id !== this.tab });
      }
      for (const ev of ["wheel", "touchmove"]) E.panes.words.addEventListener(ev, () => { this.lastScroll = Date.now(); }, { passive: true });
      E.askTop = h("div", { class: "ask-pane" });
      E.qa = h("div", { class: "ask-pane" });
      E.panes.ask.append(h("div", { class: "ask-pane" }, E.askTop, E.qa));
      E.langs = ["orig", "both", "en"].map(m => h("button", { type: "button", "aria-pressed": "false", onclick: () => this.setLang(m) }, m));
      E.lang = h("div", { class: "langs", role: "group", "aria-label": "Language", hidden: true }, E.langs);
      E.q = h("input", { placeholder: "Ask about this video…", "aria-label": "Ask about this video", autocomplete: "off", disabled: true });
      E.send = h("button", { type: "submit", class: "go", "aria-label": "Ask", disabled: true }, icon("up"));
      E.root = h("div", { class: "watch lang-orig" },
        h("section", { class: "stage" },
          h("a", { class: "back", href: "/", "data-nav": "", "aria-label": "Your videos", title: "Your videos" }, icon("back")),
          E.player, h("div", { class: "meta" }, E.title, E.sub, E.headline, E.stats), h("div", {}, E.ribbon, E.legend), E.readout),
        h("section", { class: "side" },
          h("div", { class: "tabbar" }, h("nav", { class: "tabs", role: "tablist" }, Object.values(E.tabs)), E.lang),
          Object.values(E.panes),
          h("form", { class: "composer", onsubmit: e => { e.preventDefault(); this.ask(E.q.value); } }, h("div", { class: "box" }, E.q, E.send))));
      mount(E.root);
    }

    async load() {
      let doc;
      try { doc = await api(`/api/video/${this.key}`); } catch (e) {
        if (!this.alive) return;
        if (!ME.in) return route();
        this.el.panes.summary.replaceChildren(h("p", { class: "msg" }, e.message));
        return;
      }
      if (!this.alive) return;
      const prev = this.doc;
      this.doc = doc;
      if (doc.video && !(prev && prev.video)) this.stage();
      const sig = d => [(d.transcript || []).length, !!d.summary, (d.screens || []).length, (d.terms || []).length,
                        (d.scenes || []).length, d.status && d.status.stage].join("/");
      if (!prev || sig(prev) !== sig(doc)) this.panes(!prev);
      else if (doc.status && doc.status.stage === "words") this.renderSummary();  // the countdown
      const stage = doc.status && doc.status.stage;
      if (!["done", "error", "missing"].includes(stage)) this.timer = setTimeout(() => this.load(), 1500);
    }

    stage() {
      const v = this.doc.video;
      document.title = v.title;
      this.el.title.textContent = v.title;
      this.mountPlayer();
    }

    panes(first) {
      const d = this.doc, E = this.el;
      if (!d.video) { this.renderSummary(); return; }
      const bilingual = !d.english && ((d.transcript || []).some(s => two(s.text, s.en)) || !!(d.summary && d.summary.tldr.some(x => two(x.text, x.en))));
      if (!this.chose) this.mode = bilingual ? "both" : "orig";
      E.lang.hidden = !bilingual;
      const l = lang(d.language);
      E.langs[0].textContent = l ? l[1] : "Original";
      E.langs[1].textContent = "Both";
      E.langs[2].textContent = "English";
      this.applyLang();
      this.header();
      const n = { words: (d.transcript || []).length, terms: (d.terms || []).length, scenes: (d.scenes || []).length };
      for (const [id] of TABS) E.tabs[id].lastChild.textContent = n[id] ? String(n[id]) : "";
      const ready = !!(d.transcript && d.transcript.length);
      E.q.disabled = E.send.disabled = !ready;
      E.q.placeholder = ready ? "Ask about this video…" : "You can ask once the words are in";
      this.ribbon();
      this.renderSummary();
      this.renderWords();
      this.renderTerms();
      this.renderScenes();
      this.renderAskTop();
      if (first) for (const note of d.notes || []) E.qa.append(h("div", { class: "me" }, note.question), this.answer(note));
      E.readout.hidden = false;
      this.readout(this.now() || 0);
    }

    header() {
      const d = this.doc, l = lang(d.language);
      this.el.sub.textContent = [d.video.channel, clock(d.video.duration), l && l[0]].filter(Boolean).join(" · ");
      this.el.headline.textContent = d.headline || "";
      const F = d.frames || [], S = d.scenes || [];
      const every = F.length > 1 ? Math.round((F[F.length - 1][0] - F[0][0]) / (F.length - 1)) : 0;
      this.el.stats.textContent = [
        F.length ? `${F.length} frames${every ? ` (one every ${every} s)` : ""} → ${S.length} scenes, ${S.filter(s => s.kind === "new").length} new visuals` : "",
        this.captions(),
        (d.transcript || []).length ? `${d.transcript.length} passages${d.transcriber ? ` by ${d.transcriber}` : ""}` : "",
      ].filter(Boolean).join(" · ");
    }

    // Human captions by name; YouTube's machine ones (often 20+ translations) just counted.
    captions() {
      const all = this.doc.captions || [], made = all.filter(c => !c.endsWith("(auto)")), auto = all.length - made.length;
      if (!all.length) return this.doc.video.yt ? "no captions" : "";
      return `captions: ${[made.join(", "), auto ? `${auto} automatic` : ""].filter(Boolean).join(" + ")}`;
    }

    // ---- languages
    setLang(m) { this.mode = m; this.chose = true; this.applyLang(); this.ribbon(); this.readout(this.roAt || 0); }
    applyLang() {
      const r = this.el.root;
      r.classList.remove("lang-orig", "lang-both", "lang-en");
      r.classList.add(`lang-${this.mode || "orig"}`);
      this.el.langs.forEach((b, i) => b.setAttribute("aria-pressed", String(["orig", "both", "en"][i] === this.mode)));
    }
    title(x) { return (this.mode === "en" && x.en) || x.title; }

    show(id) {
      this.tab = id;
      for (const [k, b] of Object.entries(this.el.tabs)) b.setAttribute("aria-selected", String(k === id));
      for (const [k, p] of Object.entries(this.el.panes)) p.hidden = k !== id;
      if (id === "words" && this.lines && this.cur >= 0) this.lines[this.cur].scrollIntoView({ block: "center" });
    }

    // The video's parts: its own chapters, else the summary's sections.
    parts() {
      const d = this.doc;
      if (d.chapters && d.chapters.length) return d.chapters;
      return ((d.summary && d.summary.sections) || []).map(s => ({ t: s.t, title: s.title, en: s.en }));
    }

    img(t) { return `/media/${this.key}/at/${Math.max(0, Math.round(t * 1000))}`; }
    shot(t, cls = "") {
      return h("button", { type: "button", class: cls, title: `Play from ${clock(t)}`, onclick: () => this.seek(t) },
        h("img", { src: this.img(t), alt: "", loading: "lazy" }));
    }
    chip(t) {
      return h("button", { class: "t", type: "button", title: `Play from ${clock(t)}`, onclick: e => { e.stopPropagation(); this.seek(t); } }, clock(t));
    }
    sentence(x) {
      const both = two(x.text, x.en);
      return h("span", { class: `sent${both ? " has-en" : ""}` },
        x.t != null ? this.chip(x.t) : null,
        h("span", { class: "t-orig" }, x.text, mark(x)),
        both ? h("span", { class: "t-en", lang: "en" }, x.en, mark(x)) : null);
    }

    // ---- Summary
    renderSummary() {
      const d = this.doc, pane = this.el.panes.summary, out = [];
      const stage = (d.status && d.status.stage) || "queued";
      if (stage !== "done" || !d.summary) out.push(this.progress());
      if (d.summary) {
        const s = d.summary, all = [...s.tldr, ...s.sections.flatMap(x => x.sentences)];
        const checked = all.filter(x => x.check), ok = checked.filter(x => x.check === "supported").length;
        out.push(h("div", { class: "tldr" }, s.tldr.map(x => this.sentence(x))));
        const visuals = (d.scenes || []).filter(x => x.kind === "new");
        for (const sec of s.sections) {
          const end = sec.end || d.video.duration;
          const strip = visuals.filter(v => v.start >= sec.t && v.start < end).slice(0, 4);
          out.push(h("article", { class: "sec" },
            h("div", { class: "sec-head" }, bi(sec.title, sec.en, "h3"), h("button", { class: "t", type: "button", onclick: () => this.seek(sec.t) }, `${clock(sec.t)} – ${clock(end)}`)),
            strip.length ? h("div", { class: "strip" }, strip.map(v => this.shot(v.start))) : null,
            h("ul", { class: "lines" }, sec.sentences.map(x => h("li", {}, this.sentence(x))))));
        }
        out.push(h("p", { class: "note", style: "margin-top:14px" }, s.checker === "code"
          ? "Numbers checked by code against the passages each sentence cites; the meaning wasn't checked (no key for Jev). ? marks a sentence the passages don't support."
          : `${ok} of ${checked.length} sentences checked against what was said (✓). ? means the passages it cites don't say it; ✗ means they say otherwise. Hover a mark for why. Checked by ${checkedBy(s.checker)}.`));
        out.push(h("p", { class: "about" }, this.about()));
      }
      pane.replaceChildren(...out.filter(Boolean));
    }

    about() {
      const d = this.doc, t = d.timings || {}, parts = [];
      if (t.total != null) parts.push(`scenes in ${t.total.toFixed(1)} s`);
      if (t["words total"] != null) parts.push(`words in ${t["words total"].toFixed(1)} s more`);
      if (t.screens != null) parts.push(`screen read in ${t.screens.toFixed(1)} s`);
      if (t.write != null) parts.push(`summary written in ${t.write.toFixed(1)} s and checked in ${(t.check || 0).toFixed(1)} s`);
      const who = d.summary ? ` Written by ${d.summary.writer}${d.summary.checker ? `, checked by ${checkedBy(d.summary.checker)}` : ""}.` : "";
      return parts.length ? `Built ${parts.join("; ")}.${who}` : who.trim();
    }

    progress() {
      const d = this.doc, st = d.status || {}, stage = st.stage || "queued";
      if (stage === "missing") return h("p", { class: "muted" }, "This video isn't here any more.");
      if (stage === "done") return d.summary ? null : h("p", { class: "note" }, st.note || "No summary for this one. The transcript, terms and scenes are in the other tabs.");
      const at = STAGES.indexOf(stage === "error" ? st.failed_at : stage);
      const eta = st.words_eta ? Math.max(1, Math.round(st.words_eta - Date.now() / 1000)) : null;
      const steps = [
        ["scenes", "Looking at the picture", !!d.video],
        ["words", stage === "words" && eta ? `Listening · about ${eta} s` : "Listening", !!(d.transcript && d.transcript.length)],
        ["screens", "Reading the screen", at > STAGES.indexOf("screens")],
        ["summary", "Writing the summary", !!d.summary],
      ];
      return h("div", {},
        h("ul", { class: "steps" }, steps.map(([id, label, done]) =>
          h("li", { class: done ? "done" : id === stage && stage !== "error" ? "active" : "" }, h("span", { class: "mk" }, done ? icon("check") : null), label))),
        stage === "error" ? h("p", { class: "msg" }, `Stopped: ${st.error || "something went wrong"}`) : null);
    }

    // ---- Transcript: the original over its English, terms glossed above the words, the screen and chapters in between
    renderWords() {
      const d = this.doc, pane = this.el.panes.words;
      if (!(d.transcript && d.transcript.length)) {
        this.lines = null;
        pane.replaceChildren(h("p", { class: "empty" }, "The words will be here in a few seconds."));
        return;
      }
      const find = this.finder(), seen = {}, parts = this.parts(), screens = d.screens || [];
      const list = h("ol", { class: "transcript" });
      this.lines = [];
      let pi = 0, si = 0;
      for (const s of d.transcript) {
        while (pi < parts.length && parts[pi].t <= s.t + 0.5) { const p = parts[pi++]; list.append(h("li", { class: "chapter-row" }, bi(p.title, p.en))); }
        while (si < screens.length && screens[si].t <= s.t + 0.5) list.append(this.screenRow(screens[si++]));
        const li = h("li", { class: "line" }, this.chip(s.t),
          h("div", { class: two(s.text, s.en) ? "has-en" : "" },
            h("span", { class: "t-orig" }, this.gloss(s.text, find, seen)), two(s.text, s.en) ? h("span", { class: "t-en", lang: "en" }, s.en) : null));
        this.lines.push(li);
        list.append(li);
      }
      while (si < screens.length) list.append(this.screenRow(screens[si++]));
      const count = h("span", { class: "count", "aria-live": "polite" });
      const search = h("input", { type: "search", placeholder: "Search what was said or shown, in either language", "aria-label": "Search the transcript" });
      search.addEventListener("input", () => {
        const q = search.value.trim().toLowerCase();
        let hits = 0;
        for (const li of list.children) {
          if (li.classList.contains("chapter-row")) continue;
          const hit = !q || li.textContent.toLowerCase().includes(q);
          li.hidden = !hit;
          if (q && hit) hits++;
        }
        count.textContent = q ? `${hits} match${hits === 1 ? "" : "es"}` : "";
      });
      const follow = h("input", { type: "checkbox", checked: this.followOn ? true : null, onchange: e => { this.followOn = e.target.checked; } });
      const english = d.transcript.some(s => two(s.text, s.en));
      pane.replaceChildren(
        h("div", { class: "tools" }, search, count, h("label", {}, follow, "Follow the video")),
        h("p", { class: "note" }, `Machine transcript${d.transcriber ? ` (${d.transcriber})` : ""}${english ? ", English by Mercury" : ""}.`,
          (d.terms || []).length ? " Underlined terms open an explanation." : ""),
        list);
      this.cur = -1;
    }

    screenRow(sc) { return h("li", { class: "scr" }, h("span", { class: "lbl" }, `On screen · ${clock(sc.t)}`), sc.text.split("\n").filter(Boolean).join(" · ")); }

    finder() {
      const terms = this.doc.terms || [];
      const keys = [...new Set(terms.map(t => t.heard || t.term).filter(Boolean))].sort((a, b) => b.length - a.length);
      this.termIndex = new Map(terms.map((t, k) => [(t.heard || t.term || "").replace(/\s+/g, "").toLowerCase(), k]));
      if (!keys.length) return null;
      const esc = c => c.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      return new RegExp(`(${keys.map(k => [...k.replace(/\s+/g, "")].map(esc).join("\\s*")).join("|")})`, "gi");
    }

    gloss(text, find, seen) {
      if (!find) return text;
      const out = [];
      let last = 0;
      for (const m of text.matchAll(find)) {
        const k = this.termIndex.get(m[0].replace(/\s+/g, "").toLowerCase());
        if (k == null) continue;
        const t = this.doc.terms[k];
        out.push(text.slice(last, m.index));
        seen[k] = (seen[k] || 0) + 1;
        const en = t.en && t.en.toLowerCase() !== m[0].trim().toLowerCase() && seen[k] <= GLOSSED ? t.en : "";
        out.push(h("ruby", { class: "term", tabindex: "0", role: "button", "aria-label": `${t.term}: ${t.en}`,
                             onclick: e => this.showCard(k, e.currentTarget), onkeydown: e => { if (e.key === "Enter") this.showCard(k, e.currentTarget); } },
          m[0], en ? h("rt", {}, en) : null));
        last = m.index + m[0].length;
      }
      out.push(text.slice(last));
      return out;
    }

    // ---- Terms
    renderTerms() {
      const d = this.doc, terms = d.terms || [];
      this.el.panes.terms.replaceChildren(terms.length
        ? h("div", {},
          h("p", { class: "note" }, "Technical terms in the order they come up. “Background” is general knowledge to help you follow; “In this video” is what the speaker says, checked against the transcript."),
          h("div", { class: "term-list" }, terms.map((t, k) => this.termCard(t, k, true))))
        : h("p", { class: "empty" }, d.status && d.status.stage === "done" ? "No terms for this video." : "The terms come with the summary."));
    }

    termCard(t, k, withId) {
      return h("article", { class: "term", id: withId ? `term-${this.key}-${k}` : null },
        h("div", { class: "term-head" }, h("b", {}, t.term), t.reading ? h("span", { class: "reading" }, t.reading) : null,
          t.en && t.en.toLowerCase() !== t.term.toLowerCase() ? h("span", { class: "en" }, t.en) : null,
          t.first != null ? h("span", { class: "times" }, "first said ", this.chip(t.first), t.mentions > 1 ? `said ${t.mentions}×` : "") : null),
        t.explain ? h("p", {}, h("span", { class: "lbl" }, "Background"), t.explain) : null,
        t.said ? h("p", {}, h("span", { class: "lbl" }, "In this video"), this.sentence({ text: t.said, en: t.said_en, t: t.t, check: t.check, p: t.p })) : null);
    }

    showCard(k, target) {
      this.hideCard();
      const t = this.doc.terms[k];
      const el = this.cardEl = h("div", { class: `card lang-${this.mode || "orig"}`, role: "dialog", "aria-label": t.term }, this.termCard(t, k, false),
        h("button", { class: "more", type: "button", onclick: () => {
          this.hideCard();
          this.show("terms");
          const card = document.getElementById(`term-${this.key}-${k}`);
          if (card) { card.scrollIntoView({ block: "start" }); card.classList.add("flash"); setTimeout(() => card.classList.remove("flash"), 1500); }
        } }, "All terms →"));
      document.body.append(el);
      const r = target.getBoundingClientRect();
      el.style.left = `${Math.max(16, Math.min(r.left, innerWidth - el.offsetWidth - 16))}px`;
      el.style.top = `${r.bottom + 8 + el.offsetHeight > innerHeight ? Math.max(8, r.top - el.offsetHeight - 8) : r.bottom + 8}px`;
    }

    hideCard() { if (this.cardEl) { this.cardEl.remove(); this.cardEl = null; } }

    // ---- Scenes: every scene, its picture, its build steps, what it shows and what was said
    renderScenes() {
      const d = this.doc, S = d.scenes || [], F = d.frames || [], pane = this.el.panes.scenes;
      if (!S.length) { pane.replaceChildren(h("p", { class: "empty" }, "The scenes will be here in a second.")); return; }
      if (d.dense) {
        pane.replaceChildren(h("p", { class: "note" }, `${S.length} shots: a grid reads better than a list.`),
          h("div", { class: "dense" }, S.map(s => h("button", { type: "button", onclick: () => this.seek(s.start) },
            h("img", { src: this.img(s.start), alt: "", loading: "lazy" }), clock(s.start)))));
        return;
      }
      const parts = this.parts(), screens = d.screens || [], words = d.transcript || [], out = [];
      let pi = 0;
      S.forEach((s, i) => {
        while (pi < parts.length && parts[pi].t <= s.start + 0.5) { const p = parts[pi++]; out.push(bi(p.title, p.en, "h3", "chapter-h")); }
        const keyT = F[s.key] ? F[s.key][0] : s.start;
        const body = [this.shot(keyT, "shot")];
        if (s.kind === "new") {
          const steps = (s.changes || []).filter(f => f !== s.key && F[f]).map(f => F[f][0]);
          if (steps.length) body.push(h("div", { class: "builds" }, steps.map(t => this.shot(t))));
          const shown = screens.filter(x => x.t >= s.start - 0.5 && x.t < s.end).map(x => x.text.split("\n").filter(Boolean).join(" · ")).join(" · ");
          if (shown) body.push(h("p", { class: "shown" }, h("span", { class: "lbl" }, "On screen"), shown.length > 280 ? `${shown.slice(0, 280)}…` : shown));
        } else if (s.kind === "base") {
          const share = S.filter(o => o.look === s.look).reduce((a, o) => a + o.end - o.start, 0) / Math.max(d.video.duration, 1);
          body.push(h("p", { class: "kind-note" }, `Base shot (${Math.round(share * 100)}% of the video): the picture it keeps returning to.`));
        } else {
          const first = S.findIndex(o => o.look === s.look);
          body.push(h("p", { class: "kind-note" }, "Same picture as ", h("button", { type: "button", onclick: () => {
            const row = pane.querySelector(`[data-scene="${first}"]`);
            if (row) row.scrollIntoView({ block: "start", behavior: "smooth" });
          } }, clock(S[first].start)), "."));
        }
        const said = words.filter(w => (w.t + w.e) / 2 >= s.start && (w.t + w.e) / 2 < s.end);
        if (said.length) body.push(h("div", { class: "said" }, said.map(w => h("p", { class: two(w.text, w.en) ? "has-en" : "" },
          this.chip(w.t), h("span", { class: "t-orig" }, w.text), two(w.text, w.en) ? h("span", { class: "t-en", lang: "en" }, w.en) : null))));
        const row = h("section", { class: `scene ${s.kind}` },
          h("div", { class: "when" }, this.chip(s.start), h("br"), length(s.end - s.start), h("br"), KINDS[s.kind] || ""), h("div", {}, body));
        row.dataset.scene = i;
        out.push(row);
      });
      pane.replaceChildren(...out);
    }

    // ---- Ask
    renderAskTop() {
      const d = this.doc, chips = [];
      if (d.transcript && d.transcript.length) for (const q of d.questions || []) chips.push(h("button", { class: "chip", onclick: () => this.ask(q) }, q));
      if ((d.terms || []).length) chips.push(h("button", { class: "chip local", onclick: () => this.showTerms() }, "Key terms"));
      if ((d.screens || []).length) chips.push(h("button", { class: "chip local", onclick: () => this.showScreens() }, "What's on screen"));
      this.el.askTop.replaceChildren(
        h("p", { class: "note" }, "Ask in any language. Jev finds the moments that answer you, Mercury explains them in plain English, and Jev checks each sentence against what was said; anything the video doesn't say is kept apart as background. Your questions are saved with the video."),
        chips.length ? h("div", { class: "chips" }, chips) : null);
    }

    async ask(q) {
      q = (q || "").trim();
      if (!q || this.asking) return;
      this.show("ask");
      this.el.q.value = "";
      const wait = bot(h("span", { class: "dots" }, h("i"), h("i"), h("i")));
      this.el.qa.append(h("div", { class: "me" }, q), wait);
      this.scrollAsk();
      this.asking = true;
      try { wait.replaceWith(this.answer(await api("/api/ask", { key: this.key, q }))); }
      catch (e) { wait.replaceWith(bot(h("p", { class: "msg" }, e.message))); }
      finally { this.asking = false; this.scrollAsk(); }
    }

    answer(r) {
      const said = r.answer || [];
      const ok = said.filter(a => a.check === "supported").length;
      return bot(
        r.verdict === "not in this video" ? h("p", { class: "muted" }, "This video doesn't seem to cover that.") : null,
        said.length ? h("p", {}, said.map(a => h("span", { class: a.check && a.check !== "supported" ? "unsure" : "", title: a.check && a.check !== "supported" ? "Couldn't confirm this against what was said" : null },
          h("span", { class: "tx" }, a.text), mark({ check: a.check, note: a.note }), a.t != null ? [" ", this.chip(a.t)] : null, " "))) : null,
        (r.frames || []).length ? h("div", { class: "shots" }, r.frames.map(f =>
          h("figure", { onclick: () => this.seek(f.t) }, h("img", { src: f.img, alt: "", loading: "lazy" }), h("figcaption", {}, clock(f.t))))) : null,
        (r.background || []).length ? h("div", { class: "bg" }, h("b", {}, "Background, not from the video"), r.background.map(b => h("p", {}, b))) : null,
        h("p", { class: "foot" }, [said.length ? `${ok} of ${said.length} checked against what was said` : "", r.seconds ? `${Number(r.seconds).toFixed(1)} s` : ""].filter(Boolean).join(" · ")));
    }

    showTerms() {
      this.show("ask");
      this.el.qa.append(h("div", { class: "me" }, "Key terms"), bot(h("div", { class: "term-list" }, this.doc.terms.map((t, k) => this.termCard(t, k, false)))));
      this.scrollAsk();
    }

    showScreens() {
      this.show("ask");
      const all = this.doc.screens, first = 12;
      const grid = h("div", { class: "screens" }, all.slice(0, first).map(sc => this.screenCard(sc)));
      const more = all.length > first ? h("button", { class: "chip", onclick: () => { grid.append(...all.slice(first).map(sc => this.screenCard(sc))); more.remove(); } }, `Show all ${all.length}`) : null;
      this.el.qa.append(h("div", { class: "me" }, "What's on screen"), bot(grid, more));
      this.scrollAsk();
    }

    screenCard(sc) {
      const lines = sc.text.split("\n").filter(Boolean).slice(0, 3).join(" · ");
      return h("figure", { class: "screen", onclick: () => this.seek(sc.t) },
        h("img", { src: sc.img, alt: lines, loading: "lazy" }), h("figcaption", {}, h("span", { class: "t" }, clock(sc.t)), lines));
    }

    scrollAsk() {
      const p = this.el.panes.ask;
      if (getComputedStyle(p).overflowY === "visible") { if (this.el.qa.lastElementChild) this.el.qa.lastElementChild.scrollIntoView({ block: "nearest" }); }
      else p.scrollTop = p.scrollHeight;
    }

    // ---- playing
    mountPlayer() {
      const v = this.doc.video, box = this.el.player;
      if (v.file) {
        this.video = h("video", { src: `/media/${this.key}/video`, controls: true, preload: "metadata", playsinline: true });
        box.replaceChildren(this.video);
        return;
      }
      const slot = h("div");
      box.replaceChildren(slot);
      loadYT().then(() => {
        if (!this.alive) return;
        this.player = new YT.Player(slot, {
          videoId: v.yt,
          playerVars: { playsinline: 1, rel: 0 },
          // 101/150: the owner doesn't allow playback on other sites; times open on YouTube instead
          events: { onError: e => { if ([100, 101, 150, 153].includes(e.data)) this.noEmbed(); } },
        });
      });
    }

    noEmbed() {
      const v = this.doc.video;
      this.player = null;
      this.el.player.replaceChildren(h("a", { class: "poster", href: `https://www.youtube.com/watch?v=${v.yt}`, target: "_blank", rel: "noopener" },
        h("img", { src: `https://i.ytimg.com/vi/${v.yt}/hqdefault.jpg`, alt: "" }), h("span", {}, "Watch on YouTube ↗")));
    }

    now() {
      if (this.video) return this.video.currentTime || 0;
      if (this.player && this.player.getCurrentTime) return this.player.getCurrentTime() || 0;
      return null;
    }

    playing() {
      if (this.video) return !this.video.paused;
      return !!(this.player && this.player.getPlayerState && this.player.getPlayerState() === 1);
    }

    seek(t) {
      if (this.video) { this.video.currentTime = t; this.video.play().catch(() => {}); }
      else if (this.player && this.player.seekTo) { this.player.seekTo(t, true); this.player.playVideo(); }
      else if (this.doc && this.doc.video && this.doc.video.yt) {
        window.open(`https://www.youtube.com/watch?v=${this.doc.video.yt}&t=${Math.floor(t)}s`, "_blank", "noopener");
      }
      this.follow(t, true);
    }

    follow(t, force) {
      if (!this.doc || !this.doc.video || (!force && !this.playing())) return;
      if (t == null) t = this.now();
      if (t == null) return;
      if (this.head) { const x = Math.min(1000, (t / (this.doc.video.duration || 1)) * 1000); this.head.setAttribute("x1", x); this.head.setAttribute("x2", x); }
      const parts = this.parts(), ci = parts.findLastIndex(c => c.t <= t + 0.5);
      (this.partRects || []).forEach((r, i) => r.classList.toggle("on", i === ci));
      if (!this.looking) this.readout(t);
      const words = this.doc.transcript || [];
      if (!words.length || !this.lines) return;
      const i = Math.max(0, words.findLastIndex(s => s.t <= t + 0.3));
      if (i === this.cur) return;
      if (this.cur >= 0 && this.lines[this.cur]) this.lines[this.cur].classList.remove("now");
      this.lines[i].classList.add("now");
      this.cur = i;
      if (this.tab === "words" && this.followOn && Date.now() - this.lastScroll > 4000) this.lines[i].scrollIntoView({ block: "center", behavior: "smooth" });
    }

    // ---- the ribbon: the whole video on one strip; hover to see the frame and the words at any second
    ribbon() {
      const d = this.doc, dur = d.video.duration || 1, W = 1000, NS = "http://www.w3.org/2000/svg";
      const s = (tag, attrs, ...kids) => { const el = document.createElementNS(NS, tag); for (const k in attrs) el.setAttribute(k, attrs[k]); el.append(...kids); return el; };
      const heat = d.heat || [], top = heat.length ? 24 : 0, H = top + 38;
      const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none", tabindex: "0", role: "slider",
                             "aria-label": "Position in the video", "aria-valuemin": "0", "aria-valuemax": String(Math.round(dur)) });
      svg.style.height = `${H}px`;
      if (heat.length) {
        const pts = heat.map(p => `${((p.t + p.d / 2) / dur * W).toFixed(1)},${(22 - 20 * p.v).toFixed(1)}`).join(" ");
        svg.append(s("polygon", { class: "heat", points: `0,22 ${pts} ${W},22` }), s("polyline", { class: "heat-line", points: pts }));
      }
      for (const sc of d.scenes || []) {
        svg.append(s("rect", { class: `sc-${sc.kind}`, x: (W * sc.start / dur).toFixed(1), y: top + 2,
                               width: Math.max(W * (sc.end - sc.start) / dur - 0.6, 0.6).toFixed(1), height: 18 }));
      }
      const parts = this.parts();
      this.partRects = parts.map((p, i) => {
        const x0 = W * p.t / dur, x1 = W * (i + 1 < parts.length ? parts[i + 1].t : dur) / dur;
        const r = s("rect", { class: `ch${i % 2 ? " alt" : ""}`, x: x0.toFixed(1), y: top + 24, width: Math.max(x1 - x0 - 1, 1).toFixed(1), height: 12 },
          s("title", {}, this.title(p)));
        svg.append(r);
        return r;
      });
      const look = s("line", { class: "look", x1: 0, x2: 0, y1: 0, y2: H, visibility: "hidden" });
      this.head = s("line", { class: "head", x1: 0, x2: 0, y1: 0, y2: H });
      svg.append(look, this.head);
      const peekFrame = h("div", { class: "f" }), peekTime = h("span");
      const peek = h("div", { class: "peek", hidden: true }, peekFrame, peekTime);
      const at = e => { const r = svg.getBoundingClientRect(); const f = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)); return [f * dur, f * r.width, r.width]; };
      const lookAt = (t, x, w) => {
        this.looking = true;
        look.setAttribute("x1", W * t / dur);
        look.setAttribute("x2", W * t / dur);
        look.setAttribute("visibility", "visible");
        if (x != null) {
          this.thumb(peekFrame, t, 0.6);
          peekTime.textContent = clock(t);
          peek.hidden = false;
          peek.style.left = `${Math.min(Math.max(x, 110), w - 110)}px`;
        }
        svg.setAttribute("aria-valuenow", String(Math.round(t)));
        this.readout(t);
      };
      const leave = () => { this.looking = false; peek.hidden = true; look.setAttribute("visibility", "hidden"); this.readout(this.now() || this.roAt || 0); };
      svg.addEventListener("pointermove", e => lookAt(...at(e)));
      svg.addEventListener("pointerleave", leave);
      svg.addEventListener("click", e => this.seek(at(e)[0]));
      svg.addEventListener("keydown", e => {
        const step = { ArrowLeft: -5, ArrowRight: 5, PageDown: -60, PageUp: 60 }[e.key];
        if (step) { e.preventDefault(); lookAt(Math.max(0, Math.min(dur, (this.roAt || 0) + step))); }
        if (e.key === "Enter") this.seek(this.roAt || 0);
      });
      svg.addEventListener("blur", leave);
      this.el.ribbon.replaceChildren(svg, peek);
      const legend = [["var(--new)", "new visual"], ["var(--repeat)", "seen before"], ["var(--base)", "base shot"]];
      if (heat.length) legend.push(["var(--heat)", "most replayed"]);
      if (parts.length) legend.push(["var(--line)", d.chapters && d.chapters.length ? "chapters" : "sections"]);
      this.el.legend.replaceChildren(...legend.map(([c, l]) => h("span", {}, h("i", { style: `background:${c}` }), l)),
        h("span", {}, "hover to look · click to play from there"));
      this.follow(this.now() || 0, true);
    }

    // A thumbnail cut from the sheets, instantly, by moving the sheet behind a small window.
    thumb(el, t, scale) {
      const d = this.doc, F = d.frames || [];
      let i = F.findLastIndex(f => f[0] <= t + 0.01);
      if (i < 0) i = 0;
      const f = F[i], sh = f && (d.sheets || [])[f[1]];
      if (!sh) { el.style.display = "none"; return; }
      Object.assign(el.style, {
        display: "", width: `${f[4] * scale}px`, height: `${f[5] * scale}px`, backgroundImage: `url("${sh.url}")`,
        backgroundSize: `${sh.w * scale}px ${sh.h * scale}px`, backgroundPosition: `-${f[2] * scale}px -${f[3] * scale}px`,
      });
    }

    // The readout under the ribbon: the frame, where we are, and what is being said, in the chosen languages.
    readout(t) {
      const d = this.doc;
      if (!d || !d.video) return;
      this.roAt = t;
      this.thumb(this.el.roFrame, t, 0.5);
      this.el.roTime.textContent = clock(t);
      const p = this.parts().findLast(c => c.t <= t + 0.5);
      const sc = (d.scenes || []).find(x => x.start <= t && t < x.end);
      this.el.roWhere.textContent = [p ? this.title(p) : "", sc ? KINDS[sc.kind] : ""].filter(Boolean).join(" · ");
      const words = d.transcript || [];
      const w = words.findLast(s => s.t <= t + 0.3);
      this.el.roSaid.replaceChildren(w ? bi(w.text, w.en, "div") : h("span", { class: "muted" }, words.length ? "" : "The words come in a few seconds."));
    }
  }

  api("/api/me").then(me => { ME = me; }, () => {}).finally(route);
})();
