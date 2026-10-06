"use strict";
// The product's one page: invite code → paste a link or drop a file → talk to the video.
// Plain JS, no libraries. Every piece of text from the video goes in as text, never as HTML.
(() => {
  const ICON = {
    arrow: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
    up: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M6 11l6-6 6 6"/></svg>',
    clip: '<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5l-8.6 8.6a5.2 5.2 0 0 1-7.4-7.4l8.6-8.6a3.5 3.5 0 0 1 4.9 4.9l-8.6 8.6a1.7 1.7 0 0 1-2.5-2.5l7.9-7.9"/></svg>',
    back: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg>',
    chev: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>',
    check: '<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  };
  const LANGS = { zh: ["Chinese", "中文"], yue: ["Cantonese", "粵語"], ja: ["Japanese", "日本語"], ko: ["Korean", "한국어"],
                  en: ["English", "English"], es: ["Spanish", "Español"], fr: ["French", "Français"], de: ["German", "Deutsch"] };
  const STAGES = ["queued", "scenes", "words", "screens", "summary", "done"];

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
  const lang = code => LANGS[(code || "").split("_")[0]] || null;
  const checkedBy = c => ({ "jev+code": "Jev and code", jev: "Jev", code: "code (numbers only)" })[c] || c || "nothing yet";

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

  // ---- one video: the player and the ribbon on the left, the conversation on the right
  class Watch {
    constructor(key) {
      this.key = key;
      this.doc = null;
      this.lang = "orig";
      this.tab = "chat";
      this.alive = true;
      this.player = null;
      this.video = null;
      this.lines = null;
      this.cur = -1;
      this.lastScroll = 0;
      this.build();
      this.load();
      this.tick = setInterval(() => this.follow(), 300);
    }

    stop() { this.alive = false; clearTimeout(this.timer); clearInterval(this.tick); }

    build() {
      const E = this.el = {};
      E.player = h("div", { class: "player" }, h("div", { class: "wait" }, "Getting the video…"));
      E.title = h("h1");
      E.sub = h("p");
      E.ribbon = h("div", { class: "ribbon" });
      E.now = h("p", { class: "now" });
      E.lineO = h("p", { class: "o" });
      E.lineEn = h("p", { class: "en" });
      E.line = h("div", { class: "line-now", hidden: true, title: "What is being said now" }, E.lineO, E.lineEn);
      E.brief = h("div", { class: "slot" });
      E.qa = h("div", { class: "qa" });
      E.stream = h("div", { class: "stream", "aria-live": "polite" }, E.brief, E.qa);
      E.q = h("input", { placeholder: "Ask about this video…", "aria-label": "Ask about this video", autocomplete: "off", disabled: true });
      E.send = h("button", { type: "submit", class: "go", "aria-label": "Ask", disabled: true }, icon("up"));
      E.chat = h("div", { class: "pane chat" }, E.stream,
        h("form", { class: "composer", onsubmit: e => { e.preventDefault(); this.ask(E.q.value); } }, h("div", { class: "box" }, E.q, E.send)));
      E.words = h("div", { class: "pane words", hidden: true });
      E.terms = h("div", { class: "pane terms", hidden: true });
      for (const ev of ["wheel", "touchmove"]) E.words.addEventListener(ev, () => { this.lastScroll = Date.now(); }, { passive: true });
      E.tabs = {};
      const tab = (id, label) => (E.tabs[id] = h("button", { class: "tab", role: "tab", "aria-selected": String(id === "chat"), onclick: () => this.show(id) }, label));
      E.langs = ["orig", "en"].map(l => h("button", { "aria-pressed": String(l === this.lang), onclick: () => this.setLang(l) }, l));
      E.lang = h("div", { class: "lang", hidden: true }, E.langs);
      mount(h("div", { class: "watch" },
        h("section", { class: "stage" },
          h("a", { class: "back", href: "/", "data-nav": "", "aria-label": "Your videos", title: "Your videos" }, icon("back")),
          E.player, h("div", { class: "meta" }, E.title, E.sub), E.ribbon, h("div", { class: "now-box" }, E.now, E.line)),
        h("section", { class: "side" },
          h("nav", { class: "tabs", role: "tablist" }, tab("chat", "Chat"), tab("words", "Transcript"), tab("terms", "Terms"), E.lang),
          E.chat, E.words, E.terms)));
    }

    async load() {
      let doc;
      try { doc = await api(`/api/video/${this.key}`); } catch (e) {
        if (!this.alive) return;
        if (!ME.in) return route();
        this.el.brief.replaceChildren(bot(h("p", { class: "msg" }, e.message)));
        return;
      }
      if (!this.alive) return;
      const prev = this.doc;
      this.doc = doc;
      if (doc.video && !(prev && prev.video)) this.stage();
      const sig = d => [(d.transcript || []).length, !!d.summary, (d.screens || []).length, (d.terms || []).length, d.status && d.status.stage].join("/");
      if (!prev || sig(prev) !== sig(doc)) this.panes(!prev);
      else if (doc.status && doc.status.stage === "words") this.chatTop();  // the countdown
      const stage = doc.status && doc.status.stage;
      if (!["done", "error", "missing"].includes(stage)) this.timer = setTimeout(() => this.load(), 1500);
    }

    stage() {
      const v = this.doc.video;
      document.title = v.title;
      this.el.title.textContent = v.title;
      this.mountPlayer();
      this.ribbon();
    }

    panes(first) {
      const d = this.doc;
      if (d.video) {
        const l = lang(d.language);
        this.el.sub.textContent = [d.video.channel, clock(d.video.duration), l && l[0]].filter(Boolean).join(" · ");
        this.el.langs[0].textContent = l ? l[1] : "Original";
        this.el.langs[1].textContent = "EN";
        this.el.lang.hidden = !(d.summary && !d.english);
        this.ribbon();
      }
      const ready = !!(d.transcript && d.transcript.length);
      this.el.q.disabled = this.el.send.disabled = !ready;
      this.el.q.placeholder = ready ? "Ask about this video…" : "You can ask once the words are in";
      this.chatTop();
      if (first) for (const n of d.notes || []) this.el.qa.append(h("div", { class: "me" }, n.question), this.answer(n));
      this.transcript();
      this.glossary();
      if (first && (d.notes || []).length) this.scrollChat();
    }

    // The top of the conversation: how far the reading has got, then the briefing and suggestions.
    chatTop() {
      const d = this.doc, stage = (d.status && d.status.stage) || "queued";
      const top = [];
      if (stage !== "done" || !d.summary) top.push(this.progress());
      if (d.summary) top.push(this.briefing());
      top.push(this.suggestions());
      this.el.brief.replaceChildren(...top.filter(Boolean));
    }

    progress() {
      const d = this.doc, st = d.status || {}, stage = st.stage || "queued";
      if (stage === "missing") return bot(h("p", { class: "muted" }, "This video isn't here any more."));
      if (stage === "done") return d.summary ? null : bot(h("p", { class: "muted" }, st.note || "No summary for this one. The transcript is ready, and you can still read it."));
      const at = STAGES.indexOf(stage === "error" ? st.failed_at : stage);
      const eta = st.words_eta ? Math.max(1, Math.round(st.words_eta - Date.now() / 1000)) : null;
      const steps = [
        ["scenes", "Looking at the picture", !!d.video],
        ["words", stage === "words" && eta ? `Listening · about ${eta} s` : "Listening", !!(d.transcript && d.transcript.length)],
        ["screens", "Reading the screen", at > STAGES.indexOf("screens")],
        ["summary", "Writing the summary", !!d.summary],
      ];
      return bot(
        h("ul", { class: "steps" }, steps.map(([id, label, done]) =>
          h("li", { class: done ? "done" : id === stage && stage !== "error" ? "active" : "" }, h("span", { class: "mark" }, done ? icon("check") : null), label))),
        stage === "error" ? h("p", { class: "msg", style: "margin-top:10px" }, `Stopped: ${st.error || "something went wrong"}`) : null);
    }

    briefing() {
      const s = this.doc.summary, en = this.lang === "en";
      const all = [...s.tldr, ...s.sections.flatMap(x => x.sentences)];
      const ok = all.filter(x => x.check === "supported").length;
      return bot(
        h("p", { class: "tldr" }, s.tldr.map(x => this.sentence(x))),
        h("h3", {}, "In this video"),
        h("ol", { class: "sections" }, s.sections.map(sec => {
          const more = h("div", { class: "more", hidden: true }, sec.sentences.map(x => h("p", {}, this.sentence(x))));
          const btn = h("button", { class: "sec", "aria-expanded": "false", onclick: () => {
            more.hidden = !more.hidden;
            btn.setAttribute("aria-expanded", String(!more.hidden));
          } }, h("span", {}, (en && sec.en) || sec.title), icon("chev"));
          return h("li", {}, h("div", { class: "sec-row" }, this.chip(sec.t), btn), more);
        })),
        h("p", { class: "foot" }, `${ok} of ${all.length} sentences match what was said · checked by ${checkedBy(s.checker)}`));
    }

    suggestions() {
      const d = this.doc, chips = [];
      if (d.transcript && d.transcript.length) for (const q of d.questions || []) chips.push(h("button", { class: "chip", onclick: () => this.ask(q) }, q));
      if ((d.terms || []).length) chips.push(h("button", { class: "chip local", onclick: () => this.showTerms() }, "Key terms"));
      if ((d.screens || []).length) chips.push(h("button", { class: "chip local", onclick: () => this.showScreens() }, "What's on screen"));
      return chips.length ? h("div", { class: "chips" }, chips) : null;
    }

    sentence(x) {
      const text = (this.lang === "en" && x.en) || x.text;
      const unsure = x.check && x.check !== "supported";
      return h("span", { class: unsure ? "sent unsure" : "sent", title: unsure ? "Couldn't confirm this against what was said" : null },
        h("span", { class: "tx" }, text), x.t != null ? this.chip(x.t) : null, " ");
    }

    chip(t) {
      return h("button", { class: "t", type: "button", title: `Play from ${clock(t)}`, onclick: e => { e.stopPropagation(); this.seek(t); } }, clock(t));
    }

    async ask(q) {
      q = (q || "").trim();
      if (!q || this.asking) return;
      this.show("chat");
      this.el.q.value = "";
      const wait = bot(h("span", { class: "dots" }, h("i"), h("i"), h("i")));
      this.el.qa.append(h("div", { class: "me" }, q), wait);
      this.scrollChat();
      this.asking = true;
      try { wait.replaceWith(this.answer(await api("/api/ask", { key: this.key, q }))); }
      catch (e) { wait.replaceWith(bot(h("p", { class: "msg" }, e.message))); }
      finally { this.asking = false; this.scrollChat(); }
    }

    answer(r) {
      const said = r.answer || [];
      const ok = said.filter(a => a.check === "supported").length;
      return bot(
        r.verdict === "not in this video" ? h("p", { class: "muted" }, "This video doesn't seem to cover that.") : null,
        said.length ? h("p", {}, said.map(a => this.sentence({ text: a.text, t: a.t, check: a.check }))) : null,
        (r.frames || []).length ? h("div", { class: "shots" }, r.frames.map(f =>
          h("figure", { onclick: () => this.seek(f.t) }, h("img", { src: f.img, alt: "", loading: "lazy" }), h("figcaption", {}, clock(f.t))))) : null,
        (r.background || []).length ? h("div", { class: "bg" }, h("b", {}, "Background, not from the video"), r.background.map(b => h("p", {}, b))) : null,
        h("p", { class: "foot" }, [said.length ? `${ok} of ${said.length} checked against what was said` : "", r.seconds ? `${Number(r.seconds).toFixed(1)} s` : ""].filter(Boolean).join(" · ")));
    }

    showTerms() {
      this.show("chat");
      this.el.qa.append(h("div", { class: "me" }, "Key terms"), bot(h("div", { class: "term-list" }, this.doc.terms.map(t => this.termCard(t)))));
      this.scrollChat();
    }

    showScreens() {
      this.show("chat");
      const all = this.doc.screens, first = 12;
      const grid = h("div", { class: "screens" }, all.slice(0, first).map(sc => this.screenCard(sc)));
      const more = all.length > first ? h("button", { class: "chip", onclick: () => { grid.append(...all.slice(first).map(sc => this.screenCard(sc))); more.remove(); } }, `Show all ${all.length}`) : null;
      this.el.qa.append(h("div", { class: "me" }, "What's on screen"), bot(grid, more));
      this.scrollChat();
    }

    screenCard(sc) {
      const lines = sc.text.split("\n").filter(Boolean).slice(0, 3).join(" · ");
      return h("figure", { class: "screen", onclick: () => this.seek(sc.t) },
        h("img", { src: sc.img, alt: lines, loading: "lazy" }), h("figcaption", {}, h("span", { class: "t" }, clock(sc.t)), lines));
    }

    termCard(t) {
      return h("div", { class: "term" },
        h("div", { class: "term-head" }, h("b", {}, t.term), t.reading ? h("span", { class: "reading" }, t.reading) : null,
          t.en && t.en !== t.term ? h("span", { class: "en" }, t.en) : null),
        t.explain ? h("p", {}, t.explain) : null,
        t.said ? h("p", { class: "said" }, h("span", { class: "lbl" }, "In the video"), this.sentence({ text: t.said, en: t.said_en, t: t.t, check: t.check })) : null);
    }

    transcript() {
      const d = this.doc, box = this.el.words;
      if (!(d.transcript && d.transcript.length)) {
        this.lines = null;
        box.replaceChildren(h("p", { class: "empty" }, "The words will be here in a few seconds."));
        return;
      }
      const screens = d.screens || [];
      const list = h("ol", { class: "lines" });
      this.lines = [];
      let k = 0;
      for (const s of d.transcript) {
        while (k < screens.length && screens[k].t < s.t) list.append(this.screenRow(screens[k++]));
        const li = h("li", { class: "line" }, this.chip(s.t), h("div", {}, h("p", { class: "o" }, s.text), s.en ? h("p", { class: "en" }, s.en) : null));
        li.dataset.t = s.t;
        this.lines.push(li);
        list.append(li);
      }
      while (k < screens.length) list.append(this.screenRow(screens[k++]));
      const find = h("input", { type: "search", placeholder: "Search the words and the screen", "aria-label": "Search the transcript" });
      find.addEventListener("input", () => {
        const q = find.value.trim().toLowerCase();
        for (const li of list.children) li.hidden = !!q && !li.textContent.toLowerCase().includes(q);
      });
      box.replaceChildren(h("div", { class: "find" }, find), list);
      this.cur = -1;
    }

    screenRow(sc) { return h("li", { class: "scr" }, h("b", {}, `On screen · ${clock(sc.t)}`), sc.text.split("\n").filter(Boolean).join(" · ")); }

    glossary() {
      const d = this.doc;
      this.el.terms.replaceChildren((d.terms || []).length
        ? h("div", { class: "term-list pad" }, d.terms.map(t => this.termCard(t)))
        : h("p", { class: "empty" }, d.status && d.status.stage === "done" ? "No terms for this video." : "The terms come with the summary."));
    }

    show(id) {
      this.tab = id;
      for (const [k, b] of Object.entries(this.el.tabs)) b.setAttribute("aria-selected", String(k === id));
      this.el.chat.hidden = id !== "chat";
      this.el.words.hidden = id !== "words";
      this.el.terms.hidden = id !== "terms";
      if (id === "words" && this.lines && this.cur >= 0) this.lines[this.cur].scrollIntoView({ block: "center" });
    }

    setLang(l) {
      this.lang = l;
      this.el.langs.forEach((b, i) => b.setAttribute("aria-pressed", String(["orig", "en"][i] === l)));
      this.chatTop();
      if (!this.doc.chapters.length) this.ribbon();
    }

    scrollChat() {
      const s = this.el.stream;
      if (s.scrollHeight > s.clientHeight + 4 && getComputedStyle(s).overflowY !== "visible") s.scrollTop = s.scrollHeight;
      else if (this.el.qa.lastElementChild) this.el.qa.lastElementChild.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }

    // The video's parts: its own chapters, else the summary's sections.
    parts() {
      const d = this.doc;
      if (d.chapters.length) return d.chapters;
      const secs = (d.summary && d.summary.sections) || [];
      return secs.map(s => ({ t: s.t, title: (this.lang === "en" && s.en) || s.title }));
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
        return;
      }
      this.follow(t, true);
    }

    follow(t, force) {
      if (!this.doc || !this.doc.video || (!force && !this.playing())) return;
      if (t == null) t = this.now();
      if (t == null) return;
      const d = this.doc;
      if (this.head) {
        const x = Math.min(1000, (t / (d.video.duration || 1)) * 1000);
        this.head.setAttribute("x1", x);
        this.head.setAttribute("x2", x);
      }
      const parts = this.parts(), ci = parts.findLastIndex(c => c.t <= t + 0.5);
      this.el.now.textContent = ci >= 0 ? parts[ci].title : "";
      (this.chapRects || []).forEach((r, i) => r.classList.toggle("on", i === ci));
      const words = d.transcript || [];
      if (!words.length || (t === 0 && !force)) return;
      const i = Math.max(0, words.findLastIndex(s => s.t <= t + 0.3));
      if (i === this.cur && !this.el.line.hidden) return;
      if (this.lines) {
        if (this.cur >= 0 && this.lines[this.cur]) this.lines[this.cur].classList.remove("now");
        this.lines[i].classList.add("now");
        if (this.tab === "words" && Date.now() - this.lastScroll > 4000) this.lines[i].scrollIntoView({ block: "center", behavior: "smooth" });
      }
      this.cur = i;
      if (t > 0 || this.playing()) {
        this.el.lineO.textContent = words[i].text;
        this.el.lineEn.textContent = words[i].en || "";
        this.el.line.hidden = false;
      }
    }

    // The whole video on one strip: most replayed (the curve), chapters (the bar), new visuals (the ticks).
    ribbon() {
      const d = this.doc, dur = d.video.duration || 1, W = 1000;
      const NS = "http://www.w3.org/2000/svg";
      const s = (tag, attrs) => { const el = document.createElementNS(NS, tag); for (const k in attrs) el.setAttribute(k, attrs[k]); return el; };
      const svg = s("svg", { viewBox: `0 0 ${W} 44`, preserveAspectRatio: "none", role: "img", "aria-label": "The whole video: most replayed, chapters and new visuals" });
      if (d.heat.length) {
        let path = `M0 30 L0 ${(30 - d.heat[0].v * 24).toFixed(1)}`;
        for (const p of d.heat) path += ` L${((p.t + p.d / 2) / dur * W).toFixed(1)} ${(30 - p.v * 24).toFixed(1)}`;
        svg.append(s("path", { d: `${path} L${W} ${(30 - d.heat[d.heat.length - 1].v * 24).toFixed(1)} L${W} 30 Z`, class: "heat" }));
      }
      const parts = this.parts(), chapters = parts.length ? parts : [{ t: 0, title: "" }];
      this.chapRects = chapters.map((c, i) => {
        const x0 = c.t / dur * W, x1 = (i + 1 < chapters.length ? chapters[i + 1].t : dur) / dur * W, gap = i ? 2 : 0;
        const r = s("rect", { x: x0 + gap, y: 33, width: Math.max(0.5, x1 - x0 - gap), height: 4, class: "chap" });
        svg.append(r);
        return r;
      });
      for (const t of d.visuals) { const x = t / dur * W; svg.append(s("line", { x1: x, x2: x, y1: 40, y2: 44, class: "vis" })); }
      this.head = s("line", { x1: 0, x2: 0, y1: 0, y2: 44, class: "head" });
      svg.append(this.head);
      const tip = h("div", { class: "tip", hidden: true });
      const at = e => { const r = svg.getBoundingClientRect(); return [Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * dur, e.clientX - r.left, r.width]; };
      svg.addEventListener("mousemove", e => {
        const [t, x, w] = at(e);
        const c = parts.findLast(c => c.t <= t);
        tip.hidden = false;
        tip.textContent = c ? `${clock(t)}  ${c.title}` : clock(t);
        tip.style.left = `${Math.min(Math.max(x, 60), w - 60)}px`;
      });
      svg.addEventListener("mouseleave", () => { tip.hidden = true; });
      svg.addEventListener("click", e => this.seek(at(e)[0]));
      this.el.ribbon.replaceChildren(svg, tip);
      this.follow(this.now() || 0, true);
    }
  }

  api("/api/me").then(me => { ME = me; }, () => {}).finally(route);
})();
