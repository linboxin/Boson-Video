"use strict";
// The page inside an AI app (MCP Apps: Claude, ChatGPT, Cursor). app.js draws it as on the web; this
// file is where its data comes from when there is no server: the plugin's page_* tools, asked through
// the app (JSON-RPC over postMessage). Questions go to the chat, where the user's own AI answers.
(() => {
  const PROTOCOL = "2026-01-26";
  const AT_ONCE = 3;  // pictures and sheets asked for at the same time
  let nextId = 1;
  const waiting = new Map();
  const on = {};
  let host = {};
  let modeChanged = () => {};

  const send = msg => window.parent.postMessage({ jsonrpc: "2.0", ...msg }, "*");
  function request(method, params) {
    const id = nextId++;
    send({ id, method, params });
    return new Promise((resolve, reject) => waiting.set(id, { resolve, reject }));
  }
  window.addEventListener("message", e => {
    const m = e.data;
    if (e.source !== window.parent || !m || m.jsonrpc !== "2.0") return;
    if (m.id != null && !m.method) {
      const w = waiting.get(m.id);
      if (!w) return;
      waiting.delete(m.id);
      if (m.error) w.reject(new Error(m.error.message || "The app said no."));
      else w.resolve(m.result || {});
      return;
    }
    if (m.method === "ping") return send({ id: m.id, result: {} });
    if (m.method === "ui/resource-teardown") { (on.teardown || (() => {}))(); return send({ id: m.id, result: {} }); }
    if (m.id != null) return send({ id: m.id, error: { code: -32601, message: `No ${m.method} here` } });
    (on[m.method] || (() => {}))(m.params || {});
  });

  const text = r => ((r.content || []).find(c => c.type === "text") || {}).text || "";
  const image = r => { const c = (r.content || []).find(c => c.type === "image"); return c ? `data:${c.mimeType};base64,${c.data}` : null; };
  async function call(name, args) {
    const r = await request("tools/call", { name, arguments: args });
    if (r.isError) throw new Error(text(r) || "The plugin couldn't answer.");
    return r;
  }

  // A few at a time, so a long scene list doesn't ask for a hundred pictures at once.
  const queue = [];
  let busy = 0;
  function later(job) {
    return new Promise(resolve => {
      queue.push(() => job().then(resolve, () => resolve(null)));
      pump();
    });
  }
  function pump() {
    while (busy < AT_ONCE && queue.length) {
      busy++;
      queue.shift()().finally(() => { busy--; pump(); });
    }
  }

  let doc = null, said = null;
  async function fetchDoc(key) {
    const r = JSON.parse(text(await call("page_document", { video: key, since: doc ? doc.version : "" })));
    if (r.same && doc) return doc;
    // Nothing there yet: the app can show the page before video_open has started the build, so keep
    // waiting until it has answered; after that, a link it couldn't open shows what it said.
    if (!r.video && r.status && r.status.stage === "missing") {
      doc = null;
      return { ...r, status: said == null ? { stage: "queued" } : { stage: "error", error: said || "The plugin couldn't open this video." } };
    }
    return (doc = r);
  }

  const pictures = new Map();
  const shown = new IntersectionObserver(entries => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      shown.unobserve(e.target);
      const img = e.target, s = Number(img.dataset.t);
      if (!pictures.has(s)) pictures.set(s, later(async () => image(await call("page_picture", { video: img.dataset.key, t: s }))));
      pictures.get(s).then(url => { if (url) img.src = url; });
    }
  }, { rootMargin: "300px" });
  function picture(key, t) {
    const img = document.createElement("img");
    img.alt = "";
    img.dataset.key = key;
    img.dataset.t = String(Math.max(0, Math.round(t)));
    shown.observe(img);
    return img;
  }

  const sheets = new Map();
  function sheet(key, i, redraw) {
    const got = sheets.get(i);
    if (typeof got === "string") return got;
    if (!got) {
      sheets.set(i, later(async () => image(await call("page_sheet", { video: key, index: i }))).then(url => {
        if (url) { sheets.set(i, url); redraw(); } else sheets.delete(i);
      }));
    }
    return null;
  }

  const clock = t => { t = Math.floor(t || 0); return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`; };
  function ask(key, q, at, title) {
    const where = [title ? `"${title}"` : "", `video: ${key}`, at != null ? `at ${clock(at)}` : ""].filter(Boolean).join(", ");
    return request("ui/message", { role: "user", content: [{ type: "text", text: `${q}\n\n(asked on the video's page: ${where})` }] });
  }
  const open = url => request("ui/open-link", { url }).catch(() => {});

  function apply(ctx) {
    const root = document.documentElement;
    if (ctx.theme) root.dataset.theme = ctx.theme;
    if (ctx.displayMode) { root.classList.toggle("full", ctx.displayMode === "fullscreen"); modeChanged(ctx.displayMode === "fullscreen"); }
  }
  async function fullscreen() {
    const want = host.displayMode === "fullscreen" ? "inline" : "fullscreen";
    try { host.displayMode = (await request("ui/request-display-mode", { mode: want })).mode || host.displayMode; } catch { /* the app said no */ }
    apply({ displayMode: host.displayMode });
  }

  // The app sizes the frame to the page: tell it the height whenever that changes.
  function sizes() {
    let last = "";
    const report = () => requestAnimationFrame(() => {
      const html = document.documentElement, before = html.style.height;
      html.style.height = "max-content";
      const height = Math.ceil(html.getBoundingClientRect().height);
      html.style.height = before;
      const now = `${innerWidth}x${height}`;
      if (now !== last) { last = now; send({ method: "ui/notifications/size-changed", params: { width: Math.ceil(innerWidth), height } }); }
    });
    const ro = new ResizeObserver(report);
    ro.observe(document.documentElement);
    ro.observe(document.body);
    report();
  }

  window.BV_SOURCE = {
    doc: fetchDoc, picture, sheet, ask, open, fullscreen,
    canFullscreen: () => (host.availableDisplayModes || []).includes("fullscreen"),
    onMode: fn => { modeChanged = fn; },
    // Draw the page for the video video_open was called with; `stop` when the app takes it away.
    async start(begin, stop) {
      let started = false;
      document.documentElement.classList.add("embed");
      on.teardown = stop;
      on["ui/notifications/tool-input"] = p => {
        const v = p.arguments && p.arguments.video;
        if (v && !started) { started = true; begin(String(v)); }
      };
      on["ui/notifications/tool-result"] = r => { said = text(r); };
      on["ui/notifications/host-context-changed"] = p => { host = { ...host, ...p }; apply(p); };
      try {
        const r = await request("ui/initialize", { appInfo: { name: "boson-video", version: "1" },
          appCapabilities: { availableDisplayModes: ["inline", "fullscreen"] }, protocolVersion: PROTOCOL });
        host = r.hostContext || {};
      } catch { host = {}; }
      apply(host);
      send({ method: "ui/notifications/initialized", params: {} });
      sizes();
    },
  };
})();
