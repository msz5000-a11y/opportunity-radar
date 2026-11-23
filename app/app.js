/* Opportunity Radar · app en vivo.
   Datos que publica el motor (GitHub Pages): data/feed.json (pulso cada ~5 min), opps.json (análisis profundo),
   selected.json, markets.json, paper.json, ideas.json, status.json. La app consulta el feed cada minuto. */
(() => {
  "use strict";

  // ------------------------------------------------------------------ utilidades
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const safeUrl = (u) => { try { const x = new URL(String(u)); return /^https?:$/.test(x.protocol) ? x.href : null; } catch { return null; } };
  const arr = (a) => (Array.isArray(a) ? a : []);
  const LS = {
    get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch { return false; } },
  };
  const TZ = "Europe/Madrid";
  let LANG = LS.get("radar-lang", null) || ((navigator.language || "es").toLowerCase().startsWith("es") ? "es" : "en");
  document.documentElement.lang = LANG;
  const L = (es, en) => (LANG === "en" ? (en ?? es) : es);
  const LOC = () => (LANG === "en" ? "en-GB" : "es-ES");
  const nf = (n, d = 2) => (n == null || n === "" || isNaN(+n)) ? "—" : new Intl.NumberFormat(LOC(), {maximumFractionDigits: d}).format(+n);
  const pct = (n, d = 1, sign = true) => (n == null || n === "" || isNaN(+n)) ? "—" : (sign && +n > 0 ? "+" : "") + nf(n, d) + (LANG === "en" ? "%" : " %");
  const money = (n, cur = "EUR") => {
    if (n == null || n === "" || isNaN(+n)) return "—";
    const v = +n, a = Math.abs(v), d = a >= 1000 ? 0 : a >= 1 ? 2 : a >= 0.01 ? 4 : 8;
    try { return new Intl.NumberFormat(LOC(), {style: "currency", currency: cur, maximumFractionDigits: d, minimumFractionDigits: Math.min(d, 2)}).format(v); }
    catch { return nf(v, d) + " " + cur; }
  };
  const big = (n, cur = "USD") => {
    if (n == null || n === "" || isNaN(+n)) return "—";
    const v = +n, a = Math.abs(v), s = cur === "EUR" ? "€" : "$";
    if (LANG === "en") return a >= 1e12 ? s + nf(v / 1e12, 2) + "T" : a >= 1e9 ? s + nf(v / 1e9, 1) + "B" : a >= 1e6 ? s + nf(v / 1e6, 1) + "M" : a >= 1e3 ? s + nf(v / 1e3, 0) + "K" : s + nf(v, 0);
    return a >= 1e12 ? nf(v / 1e12, 2) + " B" + s : a >= 1e9 ? nf(v / 1e9, 1) + " mil M" + s : a >= 1e6 ? nf(v / 1e6, 1) + " M" + s : a >= 1e3 ? nf(v / 1e3, 0) + " mil " + s : nf(v, 0) + " " + s;
  };
  const toDate = (iso) => { const d = new Date(iso); return isNaN(d) ? null : d; };
  const ago = (iso) => {
    const d = toDate(iso); if (!d) return "";
    const s = (Date.now() - d) / 1000;
    if (s < 60) return L("ahora", "now");
    if (s < 3600) return L(`hace ${Math.floor(s / 60)} min`, `${Math.floor(s / 60)} min ago`);
    if (s < 86400) return L(`hace ${Math.floor(s / 3600)} h`, `${Math.floor(s / 3600)} h ago`);
    const days = Math.floor(s / 86400);
    return days === 1 ? L("ayer", "yesterday") : L(`hace ${days} días`, `${days} days ago`);
  };
  const dayKey = (d) => d.toLocaleDateString("en-CA", {timeZone: TZ});
  const hhmm = (d) => d.toLocaleTimeString(LOC(), {timeZone: TZ, hour: "2-digit", minute: "2-digit"});
  const fmtDate = (iso) => { const d = toDate(iso); return d ? d.toLocaleString(LOC(), {timeZone: TZ, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit"}) : "—"; };
  const shortDate = (iso) => { const d = toDate(iso); return d ? d.toLocaleDateString(LOC(), {timeZone: TZ, day: "numeric", month: "short"}) : "—"; };
  let toastTimer = null;
  const toast = (msg) => { const t = $("#toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove("show"), 3200); };
  const link = (u, label) => { const s = safeUrl(u); return s ? `<a href="${esc(s)}" target="_blank" rel="noopener noreferrer">${esc(label || new URL(s).hostname.replace(/^www\./, ""))}</a>` : esc(label || "—"); };

  // ------------------------------------------------------------------ vocabulario
  const CATS = {
    cripto: {e: "🪙", es: "Cripto", en: "Crypto"}, bolsa: {e: "📈", es: "Bolsa", en: "Stocks"}, startups: {e: "🚀", es: "Startups", en: "Startups"},
    ia: {e: "🤖", es: "IA", en: "AI"}, lanzamientos: {e: "🎁", es: "Lanzamientos", en: "Launches"}, negocio: {e: "💼", es: "Negocio", en: "Business"},
  };
  const catName = (c) => (CATS[c] ? L(CATS[c].es, CATS[c].en) : c || "");
  const OPP_CAT = {cripto: "cripto", startups: "startups", ia_tecnologia: "ia", lanzamientos: "lanzamientos", negocio: "negocio"};
  const kindName = (k) => ({
    move: L("Movimiento", "Price move"), trend: L("Tendencia", "Trending"), social: L("Redes", "Social"), news: L("Noticia", "News"),
    listing: L("Listado", "Listing"), ipo: L("Salida a bolsa", "IPO"), earnings: L("Resultados", "Earnings"), insider: L("Directivos compran", "Insider buying"),
    defi: "DeFi", launch: L("Lanzamiento", "Launch"), grant: L("Ayuda pública", "Public grant"), context: L("Contexto", "Context"), alert: L("Aviso", "Alert"),
  }[k] || k || "");
  const oppName = (o) => [L("Ruido", "Noise"), L("Contexto", "Context"), L("Interesante", "Worth watching"), L("Accionable", "Actionable")][Math.max(0, Math.min(3, o ?? 1))];
  const riskName = (r) => ({bajo: L("bajo", "low"), medio: L("medio", "medium"), alto: L("alto", "high"), muy_alto: L("muy alto", "very high")}[r] || r || "");
  const TABS = [
    {id: "vivo", e: "⚡", es: "En vivo", en: "Live", c: "var(--c-vivo)"},
    {id: "top", e: "⭐", es: "Top", en: "Top", c: "var(--c-top)"},
    {id: "cripto", e: "🪙", es: "Cripto", en: "Crypto", c: "var(--c-cripto)"},
    {id: "bolsa", e: "📈", es: "Bolsa", en: "Stocks", c: "var(--c-bolsa)"},
    {id: "startups", e: "🚀", es: "Startups", en: "Startups", c: "var(--c-startups)"},
    {id: "ia", e: "🤖", es: "IA", en: "AI", c: "var(--c-ia)"},
    {id: "lanzamientos", e: "🎁", es: "Lanzamientos", en: "Launches", c: "var(--c-lanzamientos)"},
    {id: "ideas", e: "💡", es: "Ideas", en: "Ideas", c: "var(--c-ideas)"},
    {id: "noticias", e: "📰", es: "Noticias", en: "News", c: "var(--c-noticias)"},
    {id: "redes", e: "💬", es: "Redes", en: "Social", c: "var(--c-redes)"},
  ];
  const TAB_IDS = TABS.map((t) => t.id);
  const SIGNAL_KINDS = new Set(["move", "trend", "listing", "defi", "launch", "context", "alert", "earnings", "insider", "ipo", "grant"]);
  const SEGS = {
    cripto: () => [["all", L("Todo", "All")], ["sig", L("Señales", "Signals")], ["news", L("Noticias", "News")], ["social", L("Redes", "Social")], ["value", L("Infravaloradas", "Undervalued")], ["deep", L("Analizadas", "Deep dives")]],
    bolsa: () => [["all", L("Todo", "All")], ["sig", L("Señales", "Signals")], ["news", L("Noticias", "News")], ["social", L("Redes", "Social")], ["value", L("Infravaloradas", "Undervalued")], ["paper", L("Cartera de prueba", "Paper portfolio")]],
    startups: () => [["all", L("Todo", "All")], ["grant", L("Ayudas", "Grants")], ["news", L("Noticias", "News")], ["deep", L("Analizadas", "Deep dives")]],
    ia: () => [["all", L("Todo", "All")], ["tools", L("Herramientas", "Tools")], ["news", L("Noticias", "News")], ["deep", L("Analizadas", "Deep dives")]],
    lanzamientos: () => [["all", L("Todo", "All")], ["listing", L("Listados", "Listings")], ["ipo", L("Salidas a bolsa", "IPOs")], ["drop", L("Airdrops y DeFi", "Airdrops & DeFi")], ["news", L("Noticias", "News")], ["deep", L("Analizadas", "Deep dives")]],
  };

  // ------------------------------------------------------------------ estado
  const S = {
    feed: null, opps: [], selected: null, markets: null, paper: null, ideas: null, status: null,
    tab: "vivo", seg: LS.get("radar-segs", {}), chip: {}, useful: LS.get("radar-useful", true), limit: 60,
    lastSeen: LS.get("radar-lastseen", {}), visitFrom: {}, fresh: new Set(), saved: LS.get("radar-saved", {}),
    actions: LS.get("radar-actions", {}), profile: LS.get("radar-profile", null), loaded: false, live: null,
    ideaMk: "all", ideaType: "", oppMin: 0,
  };
  const items = () => arr(S.feed?.items);
  const inCat = (it, c) => it.cat === c || arr(it.also).includes(c);
  const useful = (it) => !it.h && (((it.opp ?? 1) >= 2 && (it.s ?? 0) >= 45) || (it.s ?? 0) >= 70);
  const txt = (it) => (LANG === "en" ? it.en || it.title || it.es : it.es || it.title) || "";
  const why = (it) => (LANG === "en" ? it.why_en || it.why : it.why) || "";
  const act = (it) => (LANG === "en" ? it.act_en || it.act : it.act) || "";
  const when = (it) => it.w || it.t || it.pub;

  // ------------------------------------------------------------------ datos
  async function getJSON(name) {
    const r = await fetch(`data/${name}?m=${Math.floor(Date.now() / 60000)}`, {cache: "no-cache"});
    if (!r.ok) throw new Error(`${name} ${r.status}`);
    return r.json();
  }
  async function loadAll(manual = false) {
    const btn = $("#refreshBtn"); btn.classList.add("spin");
    const [feed, opps, selected, markets, paper, ideas, status] = await Promise.all(
      ["feed.json", "opps.json", "selected.json", "markets.json", "paper.json", "ideas.json", "status.json"].map((n) => getJSON(n).catch(() => null)));
    btn.classList.remove("spin");
    if (feed) acceptFeed(feed, !S.loaded); else if (!S.feed) S.feed = LS.get("radar-feed-cache", null);
    if (opps) S.opps = arr(opps); if (selected) S.selected = selected; if (markets) S.markets = markets;
    if (paper) S.paper = paper; if (ideas) S.ideas = ideas; if (status) S.status = status;
    S.loaded = true;
    if (manual) toast(feed ? L("Actualizado", "Updated") : L("Sin conexión: se muestran los últimos datos guardados", "Offline: showing the last saved data"));
    render(); renderLive(); renderTicker(); renderTabbar();
    routeHash();
  }
  function acceptFeed(feed, first) {
    const before = new Set(items().map((x) => x.id));
    const prevAt = S.feed?.generatedAt;
    S.feed = feed;
    try { LS.set("radar-feed-cache", {...feed, items: arr(feed.items).slice(0, 250)}); } catch {}
    if (first || !prevAt) return 0;
    const added = arr(feed.items).filter((x) => !before.has(x.id));
    added.forEach((x) => S.fresh.add(x.id));
    return added.length;
  }
  async function pollFeed() {
    if (document.hidden) return;
    try {
      const f = await getJSON("feed.json");
      if (!f || f.generatedAt === S.feed?.generatedAt) { renderLive(); return; }
      const n = acceptFeed(f, false);
      renderTicker(); renderTabbar(); renderLive();
      if (!n) return;
      if (window.scrollY < 160 && !$("#sheet").classList.contains("open")) render();
      else showNewPill(n);
    } catch { renderLive(); }
  }
  async function pollSlow() {
    if (document.hidden) return;
    const [opps, selected, markets, ideas, status, paper] = await Promise.all(
      ["opps.json", "selected.json", "markets.json", "ideas.json", "status.json", "paper.json"].map((n) => getJSON(n).catch(() => null)));
    if (opps) S.opps = arr(opps); if (selected) S.selected = selected; if (markets) S.markets = markets;
    if (ideas) S.ideas = ideas; if (status) S.status = status; if (paper) S.paper = paper;
    if (!["vivo", "noticias", "redes"].includes(S.tab) && window.scrollY < 160 && !$("#sheet").classList.contains("open")) render();
  }
  let liveTicker = {};
  async function pollPrices() {
    if (document.hidden) return;
    try {
      const r = await fetch("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=eur&include_24hr_change=true", {cache: "no-store"});
      if (!r.ok) return;
      const d = await r.json();
      for (const [id, sym] of [["bitcoin", "BTC"], ["ethereum", "ETH"], ["solana", "SOL"]]) {
        if (d[id]) liveTicker[sym] = {p: d[id].eur, ch: d[id].eur_24h_change, cur: "EUR"};
      }
      renderTicker();
    } catch {}
  }

  // ------------------------------------------------------------------ cabecera
  function renderLive() {
    const el = $("#live"), tx = $("#liveTxt");
    const at = toDate(S.feed?.generatedAt);
    el.classList.remove("ok", "slow", "off");
    if (!at) { el.classList.add("off"); tx.textContent = S.loaded ? L("Esperando el primer pulso", "Waiting for the first pulse") : L("Conectando…", "Connecting…"); return; }
    const mins = (Date.now() - at) / 60000;
    el.classList.add(mins < 16 ? "ok" : mins < 60 ? "slow" : "off");
    tx.textContent = (mins < 16 ? L("En vivo · ", "Live · ") : L("Último pulso ", "Last pulse ")) + ago(at.toISOString());
  }
  function renderTicker() {
    const tk = {...(S.feed?.ticker || {}), ...liveTicker};
    const parts = [];
    for (const sym of ["BTC", "ETH", "SOL", "SPY", "QQQ"]) {
      const x = tk[sym]; if (!x || x.p == null) continue;
      const ch = +x.ch;
      const name = sym === "SPY" ? "S&P 500" : sym === "QQQ" ? "Nasdaq" : sym;
      parts.push(`<span class="tk"><b>${esc(name)}</b>${esc(sym === "SPY" || sym === "QQQ" ? money(x.p, "USD") : money(x.p, x.cur || "EUR"))} <span class="${ch >= 0 ? "up" : "dn"}">${esc(pct(ch, 1))}</span></span>`);
    }
    if (tk.FNG) parts.splice(3, 0, `<span class="tk"><b>${L("Miedo/codicia", "Fear/greed")}</b><span class="${tk.FNG.v <= 25 ? "dn" : tk.FNG.v >= 75 ? "up" : ""}">${esc(tk.FNG.v)}</span></span>`);
    $("#ticker").innerHTML = parts.join("") || `<span class="tk">${L("Cotizaciones en camino…", "Prices on the way…")}</span>`;
  }
  function tabItems(id) {
    const all = items();
    if (id === "vivo") return all;
    if (id === "top") return all.filter((x) => (x.s ?? 0) >= 72 && (x.opp ?? 1) >= 2);
    if (id === "noticias") return all.filter((x) => x.kind === "news");
    if (id === "redes") return all.filter((x) => x.kind === "social" || x.kind === "trend");
    if (id === "ideas") return [];
    return all.filter((x) => inCat(x, id));
  }
  function newCount(id) {
    const since = S.lastSeen[id];
    if (!since) return 0;
    return tabItems(id).filter((x) => useful(x) && (x.t || "") > since).length;
  }
  function renderTabbar() {
    $("#tabbar").innerHTML = TABS.map((t) => {
      const n = t.id === S.tab ? 0 : newCount(t.id);
      return `<button class="tab" role="tab" type="button" data-tab="${t.id}" aria-selected="${t.id === S.tab}" style="--tc:${t.c}">
        <span class="e" aria-hidden="true">${t.e}</span>${esc(L(t.es, t.en))}${n ? `<span class="badge" aria-label="${n} ${L("nuevas", "new")}">${n > 99 ? "99+" : n}</span>` : ""}</button>`;
    }).join("");
    const cur = $(`.tab[data-tab="${S.tab}"]`);
    if (cur) cur.scrollIntoView({block: "nearest", inline: "nearest"});
  }
  let seenTimer = null;
  function go(tab, {push = true, keepScroll = false} = {}) {
    if (!TAB_IDS.includes(tab)) tab = "vivo";
    markSeen(S.tab);
    S.tab = tab; S.limit = 60;
    S.visitFrom[tab] = S.lastSeen[tab] || null;
    if (push && location.hash !== "#" + tab) history.replaceState(history.state, "", "#" + tab);
    render(); renderTabbar();
    if (!keepScroll) window.scrollTo({top: 0});
    clearTimeout(seenTimer);
    seenTimer = setTimeout(() => markSeen(tab), 2500);
  }
  function markSeen(tab) {
    if (!tab || !S.feed?.generatedAt) return;
    S.lastSeen[tab] = S.feed.generatedAt;
    LS.set("radar-lastseen", S.lastSeen);
  }
  function showNewPill(n) {
    const p = $("#newPill");
    p.textContent = L(`↑ ${n} ${n === 1 ? "nueva" : "nuevas"}`, `↑ ${n} new`);
    p.classList.add("show");
  }

  // ------------------------------------------------------------------ filas del tablero
  function sigBars(s, o) {
    const n = s >= 80 ? 4 : s >= 65 ? 3 : s >= 50 ? 2 : 1;
    return `<span class="sig o${Math.max(0, Math.min(3, o ?? 1))}" aria-hidden="true">${[1, 2, 3, 4].map((k) => `<i class="${k <= n ? "on" : ""}"></i>`).join("")}</span>`;
  }
  function whenCol(iso) {
    const d = toDate(iso);
    if (!d) return `<b>—</b>`;
    const today = dayKey(new Date()), k = dayKey(d);
    if (k === today) return `<b>${esc(hhmm(d))}</b>`;
    const y = new Date(); y.setDate(y.getDate() - 1);
    return `<b>${esc(hhmm(d))}</b><small>${esc(k === dayKey(y) ? L("ayer", "yesterday") : shortDate(iso))}</small>`;
  }
  function metricBit(it) {
    const m = it.m || {};
    if (m.ch24h != null && (it.kind === "move" || it.kind === "trend")) return `<span class="num ${+m.ch24h >= 0 ? "up" : "dn"}">${esc(pct(m.ch24h))}</span>`;
    if (it.kind === "listing" && it.sym) return `<span class="tag gold">${esc(it.sym)}</span>`;
    if (m.mentions != null) return `<span class="num">${esc(nf(m.mentions, 0))} ${L("menciones", "mentions")}</span>`;
    if (m.tvl != null) return `<span class="num">${esc(big(m.tvl))}</span>`;
    if (m.points != null) return `<span class="num">${esc(nf(m.points, 0))} pts</span>`;
    if (m.surprise != null) return `<span class="num ${+m.surprise >= 0 ? "up" : "dn"}">${esc(pct(m.surprise, 0))}</span>`;
    return "";
  }
  function row(it) {
    const isNew = S.visitFrom[S.tab] && (it.t || "") > S.visitFrom[S.tab];
    const w = why(it);
    const extra = (it.n || 1) > 1 ? `<span>${L(`${it.n} fuentes`, `${it.n} sources`)}</span>` : "";
    return `<button class="row${S.fresh.has(it.id) ? " fresh" : ""}" type="button" data-item="${esc(it.id)}" style="--cc:var(--c-${esc(it.cat)})">
      <span class="when">${whenCol(when(it))}${sigBars(it.s ?? 0, it.opp)}</span>
      <span class="body"><span class="ttl">${esc(txt(it))}</span>${w && it.kind !== "news" || (w && it.ai) ? `<span class="why">${esc(w)}</span>` : ""}
        <span class="meta"><span class="src">${esc(it.src)}</span><span>${esc(kindName(it.kind))}</span><span class="cat">${esc(catName(it.cat))}</span>${metricBit(it)}${extra}</span></span>
      ${isNew ? `<span class="dot-new" title="${L("Nueva", "New")}"></span>` : ""}</button>`;
  }
  function grouped(list, render = row) {
    if (!list.length) return "";
    const now = Date.now(), today = dayKey(new Date());
    const y = new Date(); y.setDate(y.getDate() - 1); const yk = dayKey(y);
    let html = "", last = null;
    for (const it of list.slice(0, S.limit)) {
      const d = toDate(when(it));
      const g = !d ? L("Sin fecha", "Undated") : (now - d < 3600e3 ? L("Última hora", "Last hour") : dayKey(d) === today ? L("Hoy", "Today") : dayKey(d) === yk ? L("Ayer", "Yesterday") : L("Antes", "Earlier"));
      if (g !== last) { if (last !== null) html += `</div>`; html += `<div class="group">${esc(g)}</div><div class="rows">`; last = g; }
      html += render(it);
    }
    html += `</div>`;
    if (list.length > S.limit) html += `<button class="more" type="button" data-more="1">${L(`Ver más (${list.length - S.limit})`, `Show more (${list.length - S.limit})`)}</button>`;
    return html;
  }
  const byWhen = (a, b) => String(when(b) || "").localeCompare(String(when(a) || "")) || (b.s ?? 0) - (a.s ?? 0);
  function usefulSwitch() {
    return `<button class="switch" type="button" role="switch" aria-checked="${S.useful}" data-useful="1"><span class="sw"></span>${L("Solo útiles", "Useful only")}</button>`;
  }
  function filterLine(list, extra = "") {
    const total = list.filter((x) => !x.h).length, good = list.filter(useful).length;
    const label = S.useful ? L(`${good} útiles de ${total}`, `${good} useful of ${total}`) : L(`${total} en total`, `${total} in total`);
    return `<div class="tools" style="padding-top:2px"><span class="hint" style="padding:0;flex:1">${esc(label)}${extra ? " · " + esc(extra) : ""}</span>${usefulSwitch()}</div>`;
  }
  function chips(list, cur, attr) {
    return `<div class="segs" role="group">${list.map(([k, label, n]) => `<button class="seg" type="button" ${attr}="${esc(k)}" aria-pressed="${k === cur}">${esc(label)}${n != null ? `<span class="n">${n}</span>` : ""}</button>`).join("")}</div>`;
  }
  function feedBlock(list, emptyMsg) {
    const shown = (S.useful ? list.filter(useful) : list.filter((x) => !x.h)).sort(byWhen);
    if (!shown.length) {
      const hidden = list.length - shown.length;
      return `<div class="empty">${esc(emptyMsg || L("Nada nuevo por aquí en las últimas horas. El radar vuelve a mirar cada 5 minutos.", "Nothing new here in the last few hours. The radar checks again every 5 minutes."))}${S.useful && hidden > 0 ? `<br><br><button class="btn" type="button" data-useful="1">${L(`Ver también lo poco relevante (${hidden})`, `Show low-relevance items too (${hidden})`)}</button>` : ""}</div>`;
    }
    return grouped(shown);
  }

  // ------------------------------------------------------------------ pestañas
  function render() {
    const v = $("#view");
    if (!S.loaded) { v.innerHTML = `<div class="empty">${L("Cargando el radar…", "Loading the radar…")}</div>`; return; }
    let html;
    switch (S.tab) {
      case "vivo": html = viewLive(); break;
      case "top": html = viewTop(); break;
      case "ideas": html = viewIdeas(); break;
      case "noticias": html = viewNews(); break;
      case "redes": html = viewSocial(); break;
      default: html = viewCategory(S.tab);
    }
    v.innerHTML = html;
    setTimeout(() => S.fresh.clear(), 2700);
  }

  function viewLive() {
    const c = S.chip.vivo || "all";
    const all = items();
    const list = c === "all" ? all : all.filter((x) => inCat(x, c));
    const cnt = (k) => (S.useful ? all.filter(useful) : all).filter((x) => k === "all" || inCat(x, k)).length;
    const opts = [["all", L("Todo", "All"), cnt("all")], ...Object.keys(CATS).map((k) => [k, catName(k), cnt(k)])];
    const hourAgo = new Date(Date.now() - 3600e3).toISOString();
    const lastHour = all.filter((x) => (x.t || "") >= hourAgo && useful(x)).length;
    const nsrc = Object.keys(S.feed?.sources || {}).length;
    const lh = S.feed ? (lastHour ? L(`${lastHour} en la última hora`, `${lastHour} in the last hour`) + " · " : "") + L(`${nsrc} fuentes`, `${nsrc} sources`) : "";
    return `<div class="tools">${chips(opts, c, "data-chip")}</div>${filterLine(list, lh)}${feedBlock(list)}`;
  }

  function viewNews() {
    const c = S.chip.noticias || "all";
    const all = items().filter((x) => x.kind === "news");
    const list = c === "all" ? all : all.filter((x) => inCat(x, c));
    const opts = [["all", L("Todas", "All")], ...Object.keys(CATS).map((k) => [k, catName(k)])];
    return `<div class="tools">${chips(opts, c, "data-chip")}</div>${filterLine(list)}${feedBlock(list, L("No hay titulares que pasen el filtro ahora mismo.", "No headlines pass the filter right now."))}`;
  }

  const SOCIAL_SRC = [["all", () => L("Todas", "All")], ["Reddit", () => "Reddit"], ["StockTwits", () => "StockTwits"], ["CoinGecko", () => "CoinGecko"],
    ["Bluesky", () => "Bluesky"], ["Hacker News", () => "Hacker News"], ["GitHub", () => "GitHub"], ["Hugging Face", () => "Hugging Face"]];
  function viewSocial() {
    const c = S.chip.redes || "all";
    const all = items().filter((x) => x.kind === "social" || x.kind === "trend");
    const list = c === "all" ? all : all.filter((x) => (x.src || "").startsWith(c));
    const opts = SOCIAL_SRC.map(([k, f]) => [k, f(), k === "all" ? null : all.filter((x) => (x.src || "").startsWith(k)).length]).filter((o) => o[0] === "all" || o[2]);
    return `<div class="tools">${chips(opts, c, "data-chip")}</div>${filterLine(list)}
      <div class="hint">${L("Qué se dispara en Reddit, StockTwits, búsquedas de CoinGecko, Bluesky y Hacker News. X (Twitter) no ofrece acceso gratuito.", "What's spiking on Reddit, StockTwits, CoinGecko searches, Bluesky and Hacker News. X (Twitter) offers no free access.")}</div>
      ${feedBlock(list, L("Sin picos en redes ahora mismo.", "No social spikes right now."))}`;
  }

  function viewCategory(cat) {
    const segs = SEGS[cat]();
    const seg = S.seg[cat] && segs.some((s) => s[0] === S.seg[cat]) ? S.seg[cat] : "all";
    const all = items().filter((x) => inCat(x, cat));
    let body = "", showSwitch = true, scope = all;
    const deepCount = deepOpps(cat).length;
    const opts = segs.map(([k, label]) => [k, label, k === "deep" ? deepCount : null]);
    const pick = (f, empty) => { scope = all.filter(f); body = feedBlock(scope, empty); };
    switch (seg) {
      case "sig": pick((x) => SIGNAL_KINDS.has(x.kind)); break;
      case "news": pick((x) => x.kind === "news"); break;
      case "social": pick((x) => x.kind === "social" || x.kind === "trend"); break;
      case "grant": pick((x) => x.kind === "grant", L("Sin convocatorias nuevas de ayudas en los últimos días.", "No new grant calls in recent days.")); break;
      case "tools": pick((x) => x.kind === "launch" || x.kind === "trend"); break;
      case "listing": pick((x) => x.kind === "listing"); break;
      case "ipo": pick((x) => x.kind === "ipo" || arr(x.tags).includes("ipo"), L("No hay salidas a bolsa previstas en los próximos 14 días.", "No IPOs expected in the next 14 days.")); break;
      case "drop": pick((x) => x.kind === "defi" || x.kind === "launch" || arr(x.tags).some((t) => ["airdrop", "launchpool", "sin_token", "tge"].includes(t))); break;
      case "value": showSwitch = false; body = viewValue(cat === "bolsa" ? "stocks" : "crypto"); break;
      case "paper": showSwitch = false; body = viewPaper(); break;
      case "deep": showSwitch = false; body = viewDeep(cat); break;
      default: body = feedBlock(all);
    }
    return `<div class="tools">${chips(opts, seg, "data-seg")}</div>${showSwitch ? filterLine(scope) : ""}${body}`;
  }

  // ---------- Top
  function viewTop() {
    const sel = S.selected || {};
    const selRows = arr(sel.selected).map((r) => oppRowFromSel(r, false)).join("");
    const near = arr(sel.nearMisses).slice(0, 3).map((r) => oppRowFromSel(r, true)).join("");
    const day = Date.now() - 24 * 3600e3;
    const strong = items().filter((x) => useful(x) && (x.s ?? 0) >= 72 && (toDate(when(x)) || 0) >= day).sort((a, b) => (b.s ?? 0) - (a.s ?? 0) || byWhen(a, b)).slice(0, 15);
    const turns = [...arr(S.markets?.stocks?.items).map((x) => ({...x, _k: "stocks"})), ...arr(S.markets?.crypto?.items).map((x) => ({...x, _k: "crypto"}))]
      .filter((x) => x.trigger && !x.fallingKnife).sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
    const saved = Object.values(S.saved).sort(byWhen);
    const savedOpps = S.opps.filter((o) => S.actions[o.id]?.action === "guardada");
    return `
      <div class="section-h"><h2>⭐ ${L("Seleccionadas", "Shortlisted")}</h2><span>${sel.generatedAt ? esc(ago(sel.generatedAt)) : ""}</span></div>
      ${selRows ? `<div class="rows">${selRows}</div>` : `<p class="note">${L(`Ninguna oportunidad cumple aún los ${arr(sel.criteria).length || 9} criterios estrictos. Mejor no invertir que hacerlo en algo dudoso.`, `Nothing meets all ${arr(sel.criteria).length || 9} strict criteria yet. Better not to invest than to invest in something doubtful.`)}</p>`}
      ${near ? `<p class="note">${L("Las que más se acercan:", "Closest ones:")}</p><div class="rows">${near}</div>` : ""}
      <div class="section-h"><h2>🔥 ${L("Lo más fuerte (24 h)", "Strongest (24 h)")}</h2><span>${strong.length}</span></div>
      ${strong.length ? `<div class="rows">${strong.map(row).join("")}</div>` : `<p class="note">${L("Todavía no hay señales fuertes hoy.", "No strong signals yet today.")}</p>`}
      <div class="section-h"><h2>🎯 ${L("Infravaloradas con giro", "Undervalued, turning")}</h2><span>${turns.length}</span></div>
      ${turns.length ? `<div class="rows">${turns.slice(0, 8).map((x) => mkRow(x, x._k)).join("")}</div>` : `<p class="note">${L("Ningún valor infravalorado muestra hoy señal de giro. El análisis de mercados se hace una vez al día.", "No undervalued asset shows a turn signal today. The market scan runs once a day.")}</p>`}
      ${saved.length || savedOpps.length ? `<div class="section-h"><h2>🔖 ${L("Guardadas", "Saved")}</h2><span>${saved.length + savedOpps.length}</span></div>
        <div class="rows">${saved.map(row).join("")}${savedOpps.map(oppRow).join("")}</div>` : ""}`;
  }

  // ---------- análisis profundo (opps.json)
  function deepOpps(cat) {
    return S.opps.filter((o) => OPP_CAT[o.category] === cat && S.actions[o.id]?.action !== "descartada" && (o.score ?? 0) >= S.oppMin && o.tier !== "descartar")
      .sort((a, b) => String(b.firstSeenAt || "").localeCompare(String(a.firstSeenAt || "")));
  }
  function oppRow(o) {
    const s = o.score ?? 0;
    const opp = o.critical ? 0 : o.actionable === false ? 1 : s >= 70 ? 3 : 2;
    const c = o.costs || {};
    return `<button class="row" type="button" data-opp="${esc(o.id)}" style="--cc:var(--c-${esc(OPP_CAT[o.category] || "negocio")})">
      <span class="when">${whenCol(o.firstSeenAt)}${sigBars(s, opp)}</span>
      <span class="body"><span class="ttl">${esc(o.name)}</span>${arr(o.whyInteresting)[0] ? `<span class="why">${esc(arr(o.whyInteresting)[0])}</span>` : ""}
        <span class="meta"><span class="num">${esc(s)}/100</span><span>${esc(o.tierLabel || "")}</span><span>${L("Entrada", "Entry")} ${esc(c.minEntry === 0 ? L("gratis", "free") : money(c.minEntry))}</span>${o.critical ? `<span class="tag bad">${L("Riesgo crítico", "Critical risk")}</span>` : ""}${S.actions[o.id]?.action === "guardada" ? `<span class="tag gold">${L("Guardada", "Saved")}</span>` : ""}</span></span></button>`;
  }
  function oppRowFromSel(r, near) {
    return `<button class="row" type="button" data-opp="${esc(r.id)}" style="--cc:${near ? "var(--warn)" : "var(--gold)"}">
      <span class="when"><b class="score-n">${esc(r.adjustedScore ?? r.score ?? "–")}</b>${sigBars(r.adjustedScore ?? r.score ?? 0, near ? 2 : 3)}</span>
      <span class="body"><span class="ttl">${esc(r.name)}</span>
        <span class="why">${near ? L(`Cumple ${r.passed} de ${arr(S.selected?.criteria).length} criterios. Le falta: `, `Meets ${r.passed} of ${arr(S.selected?.criteria).length} criteria. Missing: `) + esc(arr(r.failed).join(", ")) : L("Cumple todos los criterios estrictos.", "Meets every strict criterion.")}</span>
        <span class="meta"><span>${esc(catName(OPP_CAT[r.category] || r.category))}</span><span>${L("Entrada", "Entry")} ${esc(r.minEntry === 0 ? L("gratis", "free") : money(r.minEntry))}</span><span>${L("Riesgo", "Risk")} ${esc(riskName(r.risk))}</span>${r.hasManual ? `<span class="tag gold">${L("Con manual", "Has guide")}</span>` : ""}</span></span></button>`;
  }
  function viewDeep(cat) {
    const list = deepOpps(cat);
    const opts = [[0, L("Todas", "All")], [50, "50+"], [65, "65+"]].map(([k, l]) => [String(k), l]);
    return `<div class="tools">${chips(opts, String(S.oppMin), "data-oppmin")}</div>
      <p class="note">${L("Fichas completas que una IA analiza y otra distinta verifica cada 3 horas. Solo entran candidatas con una vía real de ganar dinero.", "Full write-ups that one AI analyses and a different one verifies every 3 hours. Only candidates with a real way to make money get in.")}</p>
      ${list.length ? grouped(list.map((o) => ({...o, w: o.firstSeenAt})), oppRow) : `<div class="empty">${L("Sin fichas en esta categoría todavía.", "No write-ups in this category yet.")}</div>`}`;
  }

  // ---------- mercados (markets.json, paper.json)
  function mkRow(x, kind) {
    const sig = x.trigger && !x.fallingKnife;
    const m = x.metrics || {};
    const line = kind === "stocks" ? `PER ${nf(m.pe, 1)} · ${L("calidad", "quality")} ${m.fscore ?? "—"}/9` : `MVRV ${nf(m.mvrv, 2)} · ${pct(m.athDiscount, 0, false)} ${L("bajo máximos", "below ATH")}`;
    return `<button class="row" type="button" data-mk="${esc(kind)}|${esc(x.symbol)}" style="--cc:var(--c-${kind === "stocks" ? "bolsa" : "cripto"})">
      <span class="when"><b class="score-n">${esc(x.score)}</b>${sigBars(x.score ?? 0, sig ? 3 : 1)}</span>
      <span class="body"><span class="ttl">${esc(x.symbol)} · ${esc(x.name || "")}</span>
        <span class="why">${sig ? esc(L("Señal de giro: ", "Turn signal: ") + (x.trigger.type === "media50" ? L("recupera la media de 50 sesiones", "reclaims its 50-day average") : L("rebota en una media de 200 que sube", "bounces on a rising 200-day average"))) : L("En vigilancia: barata, pero aún sin señal de giro.", "On watch: cheap, but no turn signal yet.")}</span>
        <span class="meta"><span class="num">${esc(money(x.price, "USD"))}</span><span>${esc(big(x.mcap))}</span><span>${esc(line)}</span>${x.fallingKnife ? `<span class="tag bad">${L("Cuchillo cayendo", "Falling knife")}</span>` : ""}</span></span></button>`;
  }
  function viewValue(kind) {
    const b = S.markets?.[kind];
    if (!b?.enabled) return `<div class="empty">${L("El análisis de mercados aparece tras su ejecución diaria.", "The market scan appears after its daily run.")}</div>`;
    const reg = b.regime;
    const fg = S.markets?.crypto?.fearGreed;
    const head = kind === "stocks"
      ? L(`${nf(b.universe, 0)} empresas líquidas de EE. UU. (cierre ${b.priceDate}); ${nf(b.passed, 0)} pasan los descartes. Valor + calidad + momento, como un fondo cuantitativo.`, `${nf(b.universe, 0)} liquid US companies (close ${b.priceDate}); ${nf(b.passed, 0)} pass the filters. Value + quality + momentum, quant-fund style.`)
      : L(`${nf(b.universe, 0)} criptos estudiadas; ${nf(b.passed, 0)} pasan los descartes.`, `${nf(b.universe, 0)} cryptos studied; ${nf(b.passed, 0)} pass the filters.`);
    const sorted = arr(b.items).slice().sort((a, c) => ((c.trigger && !c.fallingKnife) - (a.trigger && !a.fallingKnife)) || (c.score ?? 0) - (a.score ?? 0));
    return `<p class="note">${esc(head)}${reg ? ` ${esc(reg.symbol)} ${reg.riskOn ? L("está por encima de su media de 200: mercado favorable.", "is above its 200-day average: favourable market.") : L("está por debajo de su media de 200: se exige más para dar señal.", "is below its 200-day average: signals need more.")}` : ""}${kind === "crypto" && fg ? ` ${L("Miedo y codicia", "Fear & greed")}: ${esc(fg.value)}.` : ""}</p>
      <div class="rows">${sorted.map((x) => mkRow(x, kind)).join("") || `<div class="empty">${L("Ninguna cumple los criterios hoy.", "None meets the criteria today.")}</div>`}</div>
      <p class="fine" style="margin:14px var(--pad)">${L("Actualizado", "Updated")} ${esc(fmtDate(S.markets?.generatedAt))}. ${L("No es asesoramiento financiero: el radar nunca compra por ti.", "Not financial advice: the radar never buys for you.")}</p>`;
  }
  function viewPaper() {
    const s = S.paper?.summary || S.markets?.paperSummary;
    if (!s || !s.signals) return `<div class="empty">${L("Aún no hay señales. Cada señal de giro se apunta aquí con su precio para medir, sin dinero real, si el sistema acierta.", "No signals yet. Each turn signal is logged here with its price to measure, without real money, whether the system works.")}</div>`;
    const pos = arr(S.paper?.positions).slice().reverse();
    return `<div style="padding:8px var(--pad)"><dl class="kv">
        <dt>${L("Señales", "Signals")}</dt><dd>${esc(s.signals)}</dd><dt>${L("Abiertas / cerradas", "Open / closed")}</dt><dd>${esc(s.open)} / ${esc(s.closed)}</dd>
        <dt>${L("Rentabilidad media", "Average return")}</dt><dd class="${+s.avgReturn >= 0 ? "up" : "dn"}">${esc(pct(s.avgReturn))}</dd>
        <dt>${L("Índice en el mismo periodo", "Index over the same period")}</dt><dd>${esc(pct(s.avgBench))}</dd>
        <dt>${L("Aciertos (cerradas)", "Hit rate (closed)")}</dt><dd>${s.hitRate != null ? esc(pct(s.hitRate, 0, false)) : "—"}</dd></dl></div>
      <div class="rows">${pos.map((p) => `<div class="row" style="--cc:var(--c-bolsa);cursor:default"><span class="when"><b>${esc(shortDate(p.date))}</b></span>
        <span class="body"><span class="ttl">${esc(p.symbol)} · ${esc(p.name || "")}</span>
        <span class="meta"><span>${L("Entrada", "Entry")} ${esc(money(p.entry, "USD"))}</span><span>${L("Ahora", "Now")} ${esc(money(p.last ?? p.entry, "USD"))}</span><span class="num ${+p.returnPct >= 0 ? "up" : "dn"}">${esc(pct(p.returnPct))}</span><span>${p.status === "abierta" ? L("Abierta", "Open") : L("Cerrada", "Closed")}</span></span></span></div>`).join("")}</div>`;
  }

  // ---------- ideas (ideas.json)
  const MK = {es: "🇪🇸 España", eg: "🇪🇬 Egipto", gcc: "🌴 Golfo"};
  const MKEN = {es: "🇪🇸 Spain", eg: "🇪🇬 Egypt", gcc: "🌴 Gulf"};
  const mkName = (m) => (LANG === "en" ? MKEN[m] : MK[m]);
  const ITYPE = {app: "App", saas: "SaaS", software: "Software", marketplace: "Marketplace", ecommerce: "E-commerce", servicio: L("Servicio", "Service"), negocio_local: L("Negocio local", "Local business")};
  const fit = (it, m) => +((it.markets || {})[m] || {}).fit || 0;
  function viewIdeas() {
    const d = S.ideas;
    if (!d || !arr(d.items).length) return `<div class="empty">${L("Las ideas aparecen tras la exploración diaria.", "Ideas appear after the daily scan.")}</div>`;
    let list = arr(d.items).filter((it) => !S.ideaType || it.type === S.ideaType);
    if (S.ideaMk !== "all") list = list.filter((it) => fit(it, S.ideaMk) >= 5 && !((it.markets || {})[S.ideaMk] || {}).origin).sort((a, b) => fit(b, S.ideaMk) - fit(a, S.ideaMk) || b.score - a.score);
    else list = list.slice().sort((a, b) => String(b.foundAt || "").localeCompare(String(a.foundAt || "")) || (b.score ?? 0) - (a.score ?? 0));
    const mkOpts = [["all", L("Todos los mercados", "All markets")], ...Object.keys(MK).map((m) => [m, mkName(m)])];
    const types = [...new Set(arr(d.items).map((x) => x.type).filter(Boolean))];
    const tOpts = [["", L("Todos los tipos", "All types")], ...types.map((t) => [t, ITYPE[t] || t])];
    return `<div class="tools">${chips(mkOpts, S.ideaMk, "data-ideamk")}</div><div class="tools" style="padding-top:2px">${chips(tOpts, S.ideaType, "data-ideatype")}</div>
      <p class="note">${L("Negocios que han funcionado hace poco en otro país y se pueden copiar o adaptar en España, Egipto o el Golfo. Cada cifra de éxito se comprueba contra la fuente.", "Businesses that recently worked somewhere else and can be copied or adapted in Spain, Egypt or the Gulf. Every traction figure is checked against the source.")}</p>
      ${list.length ? `<div class="rows">${list.map(ideaRow).join("")}</div>` : `<div class="empty">${L("Ninguna idea con estos filtros.", "No ideas with these filters.")}</div>`}`;
  }
  function ideaRow(it) {
    const mv = it.mvp || {}, cost = arr(mv.costEur);
    const fits = Object.keys(MK).map((m) => ((it.markets || {})[m] || {}).origin ? null : `${mkName(m).split(" ")[0]} ${fit(it, m)}/10`).filter(Boolean).join("  ");
    return `<button class="row" type="button" data-idea="${esc(it.id)}" style="--cc:var(--c-ideas)">
      <span class="when"><b class="score-n">${esc(it.score)}</b>${sigBars(it.score ?? 0, (it.score ?? 0) >= 70 ? 3 : 2)}</span>
      <span class="body"><span class="ttl">${esc(it.name)}</span><span class="why">${esc(it.summary || "")}</span>
        <span class="meta"><span>${esc(ITYPE[it.type] || it.type || "")}</span><span>${L("Origen", "Origin")}: ${esc(it.originCountry || "—")}</span><span>${esc(fits)}</span>${cost.length ? `<span>MVP ${esc(nf(cost[0], 0))}–${esc(nf(cost[1], 0))} €</span>` : ""}${it.regulated ? `<span class="tag warn">${L("Regulado", "Regulated")}</span>` : ""}</span></span></button>`;
  }

  // ------------------------------------------------------------------ fichas
  const sheet = $("#sheet");
  function openSheet(html) {
    $("#sheetBody").innerHTML = `<div class="sheet-bar"><button class="back" type="button" data-close="1">‹ ${L("Volver", "Back")}</button></div>${html}`;
    sheet.classList.add("open"); sheet.scrollTop = 0; document.body.classList.add("noscroll");
    if (!history.state?.sheet) history.pushState({sheet: 1}, "", location.hash);
  }
  function closeSheet(fromPop = false) {
    if (!sheet.classList.contains("open")) return;
    sheet.classList.remove("open"); document.body.classList.remove("noscroll");
    if (!fromPop && history.state?.sheet) history.back();
  }
  const listHtml = (a) => (arr(a).length ? `<ul>${arr(a).map((x) => `<li>${esc(typeof x === "string" ? x : x.detail || x.title || JSON.stringify(x))}</li>`).join("")}</ul>` : `<p class="muted">${L("No consta.", "Not stated.")}</p>`);
  const strength = (s, o, label) => `<div class="strength">${sigBars(s, o)}<b>${esc(s)}/100</b><span>${esc(label || oppName(o))}</span></div>`;
  const M_LABEL = () => ({
    price: L("Precio", "Price"), ch1h: L("Cambio 1 h", "1h change"), ch24h: L("Cambio 24 h", "24h change"), ch7d: L("Cambio 7 días", "7d change"),
    vol: L("Volumen 24 h", "24h volume"), mcap: L("Capitalización", "Market cap"), rank: L("Puesto por capitalización", "Market-cap rank"), tvl: L("Depositado (TVL)", "TVL"),
    ch1d: L("TVL 24 h", "TVL 24h"), mentions: L("Menciones 24 h", "Mentions 24h"), mentions24hAgo: L("Menciones el día anterior", "Mentions the day before"),
    rank24hAgo: L("Puesto ayer", "Rank yesterday"), points: L("Puntos", "Points"), comments: L("Comentarios", "Comments"), stars: L("Estrellas", "Stars"),
    likes: L("Me gusta", "Likes"), downloads: L("Descargas", "Downloads"), epsActual: L("BPA real", "Actual EPS"), epsEstimate: L("BPA esperado", "Expected EPS"),
    surprise: L("Sorpresa", "Surprise"), total: L("Importe comprado", "Amount bought"), insiders: L("Directivos", "Insiders"), buys: L("Compras", "Purchases"),
    date: L("Fecha", "Date"), value: L("Tamaño de la operación", "Deal size"), shares: L("Acciones", "Shares"), fng: L("Índice", "Index"),
    nivel: L("Administración", "Administration"), org: L("Organismo", "Body"), fecha: L("Publicada", "Published"), dollarVol: L("Negociado", "Traded"), cat: L("Categoría", "Category"),
  });
  function metricsTable(it) {
    const m = it.m || {}, lab = M_LABEL(), cur = m.cur || "USD";
    const rows = [];
    for (const [k, v] of Object.entries(m)) {
      if (v == null || v === "" || ["cur", "hn", "chains", "lang", "trending"].includes(k) || !lab[k]) continue;
      let val = v;
      if (k === "price") val = money(v, cur === "EUR" ? "EUR" : "USD");
      else if (["ch1h", "ch24h", "ch7d", "ch1d", "surprise"].includes(k)) val = `<span class="${+v >= 0 ? "up" : "dn"}">${esc(pct(v))}</span>`;
      else if (["vol", "mcap", "tvl", "total", "value", "dollarVol"].includes(k)) val = big(v, ["vol", "mcap"].includes(k) && cur === "EUR" ? "EUR" : "USD");
      else if (typeof v === "number") val = nf(v, 2);
      rows.push(`<dt>${esc(lab[k])}</dt><dd>${String(val).startsWith("<span") ? val : esc(val)}</dd>`);
    }
    return rows.length ? `<div class="blk"><h3>${L("Datos", "Data")}</h3><dl class="kv">${rows.join("")}</dl></div>` : "";
  }
  function chartUrl(it) {
    if (!it.sym) return null;
    if (it.cat === "bolsa" || it.kind === "earnings" || it.kind === "insider") return `https://www.tradingview.com/symbols/${encodeURIComponent(it.sym)}/`;
    if (it.cat === "cripto" || it.kind === "listing") return `https://www.coingecko.com/${LANG === "en" ? "en" : "es"}/search?query=${encodeURIComponent(it.sym)}`;
    return null;
  }
  function openItem(id) {
    const it = items().find((x) => x.id === id) || S.saved[id];
    if (!it) return false;
    const orig = it.title && txt(it) !== it.title ? `<p class="d-orig">${L("Titular original", "Original headline")}: ${esc(it.title)}</p>` : "";
    const srcs = arr(it.srcs).length ? arr(it.srcs) : [{n: it.src, u: it.url}];
    const ch = chartUrl(it);
    const q = encodeURIComponent((it.sym ? it.sym + " " : "") + (it.kind === "news" ? it.title : txt(it)).slice(0, 90));
    const saved = !!S.saved[id];
    openSheet(`<div class="d-head">
        <div class="d-kind"><span class="tag" style="background:color-mix(in srgb,var(--c-${esc(it.cat)}) 22%,transparent);color:var(--c-${esc(it.cat)})">${esc(catName(it.cat))}</span><span>${esc(kindName(it.kind))}</span><span>${esc(it.src)}</span><span>${esc(fmtDate(when(it)))} (${esc(ago(when(it)))})</span></div>
        <h2 class="d-title">${esc(txt(it))}</h2>${orig}
        ${strength(it.s ?? 0, it.opp)}
        <div class="d-kind">${it.risk ? `<span class="tag ${it.risk === "muy_alto" ? "bad" : it.risk === "alto" ? "warn" : ""}">${L("Riesgo", "Risk")} ${esc(riskName(it.risk))}</span>` : ""}${arr(it.tags).includes("confirmada") ? `<span class="tag good">${L("Confirmada por varias señales", "Confirmed by several signals")}</span>` : ""}${(it.n || 1) > 1 ? `<span class="tag">${L(`${it.n} fuentes`, `${it.n} sources`)}</span>` : ""}${it.ai ? `<span class="tag">${L("Resumen hecho por IA", "AI summary")}</span>` : ""}</div>
      </div>
      ${it.sum ? `<div class="blk"><p>${esc(it.sum)}</p></div>` : ""}
      ${why(it) ? `<div class="blk"><h3>${L("Por qué importa", "Why it matters")}</h3><p>${esc(why(it))}</p></div>` : ""}
      ${act(it) ? `<div class="blk callout"><h3>${L("Qué hacer", "What to do")}</h3><p>${esc(act(it))}</p></div>` : ""}
      ${metricsTable(it)}
      <div class="blk srcs"><h3>${L("Fuentes", "Sources")}</h3><ul>${srcs.map((s) => `<li>${link(s.u, s.n)}</li>`).join("")}</ul></div>
      <div class="btns">
        ${safeUrl(it.url) ? `<a class="btn primary" href="${esc(safeUrl(it.url))}" target="_blank" rel="noopener noreferrer">${L("Abrir la fuente", "Open source")}</a>` : ""}
        ${ch ? `<a class="btn" href="${esc(ch)}" target="_blank" rel="noopener noreferrer">${L("Ver gráfico", "View chart")}</a>` : ""}
        <a class="btn" href="https://news.google.com/search?q=${q}&hl=${LANG === "en" ? "en-US&gl=US&ceid=US:en" : "es&gl=ES&ceid=ES:es"}" target="_blank" rel="noopener noreferrer">${L("Buscar más noticias", "Search more news")}</a>
        <button class="btn ${saved ? "on" : ""}" type="button" data-save="${esc(id)}">${saved ? L("Guardada", "Saved") : L("Guardar", "Save")}</button>
        <button class="btn" type="button" data-share="${esc(id)}">${L("Compartir", "Share")}</button>
      </div>
      <p class="fine">${L("Información automática de fuentes públicas. No es asesoramiento financiero: decide tú y nunca inviertas lo que no puedas perder. El radar jamás compra, vende ni pide claves.", "Automated information from public sources. Not financial advice: decide for yourself and never invest what you can't afford to lose. The radar never buys, sells or asks for keys.")}</p>`);
    return true;
  }

  function openOpp(id) {
    const o = S.opps.find((x) => x.id === id);
    const selR = [...arr(S.selected?.selected), ...arr(S.selected?.nearMisses)].find((x) => x.id === id);
    if (!o && !selR) return false;
    const x = o || {...selR, name: selR.name};
    const c = x.costs || {}, sc = x.scenarios || {}, reg = x.regulatory || {}, a = S.actions[id] || {};
    const flags = arr(x.flags || x.redFlags);
    const manual = S.selected?.manuals?.[id];
    openSheet(`<div class="d-head">
        <div class="d-kind"><span class="tag" style="color:var(--c-${esc(OPP_CAT[x.category] || "negocio")})">${esc(catName(OPP_CAT[x.category] || x.category))}</span><span>${esc(x.subcategory || "")}</span><span>${L("Vista", "Seen")} ${esc(fmtDate(x.firstSeenAt))}</span></div>
        <h2 class="d-title">${esc(x.name)}</h2>
        ${strength(x.score ?? x.adjustedScore ?? 0, x.critical ? 0 : (x.score ?? 0) >= 70 ? 3 : 2)}
        <div class="d-kind">${x.tierLabel ? `<span class="tag">${esc(x.tierLabel)}</span>` : ""}${x.critical ? `<span class="tag bad">${L("Riesgo crítico", "Critical risk")}</span>` : x.risk ? `<span class="tag warn">${L("Riesgo", "Risk")} ${esc(riskName(x.risk))}</span>` : ""}${x.verification?.verdict ? `<span class="tag ${x.verification.verdict === "confirmada" ? "good" : "warn"}">${L("Verificación", "Verification")}: ${esc(x.verification.verdict)}</span>` : ""}</div>
      </div>
      ${x.critical ? `<div class="blk callout bad"><p>${L("Riesgo crítico detectado: no se recomienda participar.", "Critical risk detected: participation is not recommended.")}</p></div>` : ""}
      ${manual ? `<div class="btns"><button class="btn primary" type="button" data-manual="${esc(id)}">📘 ${L("Cómo aprovecharla, paso a paso", "Step-by-step guide")}</button></div>` : ""}
      <div class="blk"><h3>${L("Qué es", "What it is")}</h3><p>${esc(x.description || L("Sin descripción.", "No description."))}</p></div>
      <div class="blk"><dl class="kv">
        <dt>${L("En España", "In Spain")}</dt><dd>${esc(x.spainAvailability || "—")}</dd>
        <dt>${L("Web oficial", "Official site")}</dt><dd>${link(x.officialUrl, L("abrir", "open"))}</dd>
        <dt>${L("Participar", "Join")}</dt><dd>${x.participateUrl ? link(x.participateUrl, L("abrir", "open")) : "—"}</dd>
        <dt>${L("Plazo", "Deadline")}</dt><dd>${esc(x.deadline ? shortDate(x.deadline) : x.horizon || "—")}</dd>
        <dt>${L("Coste mínimo", "Minimum cost")}</dt><dd>${esc(c.minEntry === 0 ? L("gratis", "free") : money(c.minEntry))}</dd>
        <dt>${L("Capital recomendado", "Suggested capital")}</dt><dd>${esc(money(c.recommended))}</dd>
        <dt>${L("¿Puedo perderlo todo?", "Can I lose it all?")}</dt><dd>${x.canLoseAll === false ? L("No", "No") : L("Sí", "Yes")}</dd>
        <dt>${L("Dificultad / tiempo", "Difficulty / time")}</dt><dd>${esc([x.difficulty, x.timeNeeded].filter(Boolean).join(" · ") || "—")}</dd></dl></div>
      ${x.profitPath ? `<div class="blk callout"><h3>${L("Cómo se gana dinero", "How you make money")}</h3><p>${esc(x.profitPath)}</p></div>` : ""}
      <div class="blk"><h3>${L("Por qué puede ser interesante", "Why it may be interesting")}</h3>${listHtml(x.whyInteresting)}</div>
      <div class="blk"><h3>${L("Cómo participar", "How to take part")}</h3>${arr(x.howToParticipate).length ? `<ol>${arr(x.howToParticipate).map((s) => `<li>${esc(s)}</li>`).join("")}</ol>` : listHtml([])}</div>
      <div class="blk"><h3>${L("Motivos para desconfiar", "Reasons for caution")}</h3>${listHtml([...flags.map((f) => (f.severity ? `[${f.severity}] ` : "") + (f.detail || f.code || "")), ...arr(x.distrust)])}</div>
      <div class="blk"><h3>${L("Qué podría hacerte perder el dinero", "What could make you lose money")}</h3>${listHtml(x.lossCauses)}</div>
      ${+sc.stakeEur > 0 ? `<div class="blk"><h3>${L("Escenarios (simulación, no predicción)", "Scenarios (simulation, not a forecast)")}</h3><div class="table-wrap"><table><thead><tr><th>${L("Escenario", "Scenario")}</th><th>${L("Bruto", "Gross")}</th><th>${L("Neto", "Net")}</th></tr></thead><tbody>
        ${sc.lossScenarioEur != null ? `<tr><td>${L("Pérdida total", "Total loss")}</td><td>${esc(money(0))}</td><td class="dn">${esc(money(sc.lossScenarioEur))}</td></tr>` : ""}
        ${arr(sc.rows).map((r) => `<tr><td>${esc(r.multiple)}x</td><td>${esc(money(r.grossEur))}</td><td>${esc(money(r.netEur))}</td></tr>`).join("")}</tbody></table></div>
        <p class="fine" style="margin-top:6px">${L("Con", "With")} ${esc(money(sc.stakeEur))}. ${esc(sc.disclaimer || "")}</p></div>` : ""}
      ${reg.status ? `<div class="blk"><h3>${L("Regulación", "Regulation")}</h3><p><span class="tag ${["advertencia_cnmv", "no_autorizada"].includes(reg.status) ? "bad" : reg.status === "autorizada" ? "good" : "warn"}">${esc(reg.status)}</span> ${esc(reg.notes || "")}</p></div>` : ""}
      <div class="blk srcs"><h3>${L("Fuentes", "Sources")}</h3><ul>${arr(x.sources).map((s) => `<li>${link(s.url, s.title || s.url)}</li>`).join("") || `<li>${L("Sin fuentes", "No sources")}</li>`}</ul></div>
      <div class="blk"><h3>${L("Tu seguimiento", "Your tracking")}</h3>
        <div class="btns" style="margin-top:6px">
          ${[["guardada", L("Guardar", "Save")], ["investigada", L("Investigada", "Researched")], ["descartada", L("Descartar", "Dismiss")]].map(([k, l]) => `<button class="btn ${a.action === k ? "on" : ""}" type="button" data-oppact="${esc(id)}|${k}">${esc(l)}${a.action === k ? " ✓" : ""}</button>`).join("")}
        </div>
        <div class="field"><label for="oppNote">${L("Notas (solo en este móvil)", "Notes (this phone only)")}</label><input id="oppNote" type="text" value="${esc(a.note || "")}" data-oppnote="${esc(id)}"></div></div>
      <p class="fine">${L("Analizada por", "Analysed by")} ${esc(x.aiModels?.analyst || "—")} · ${L("verificada por", "verified by")} ${esc(x.aiModels?.verifier || L("nadie (sin verificación independiente)", "nobody (no independent check)"))}. ${L("No es asesoramiento financiero.", "Not financial advice.")}</p>`);
    return true;
  }

  function openManual(id) {
    const m = S.selected?.manuals?.[id];
    const r = [...arr(S.selected?.selected), ...arr(S.selected?.nearMisses)].find((x) => x.id === id);
    if (!m || !r) return;
    const isSel = arr(S.selected?.selected).some((x) => x.id === id);
    const prog = LS.get("radar-manual-progress", {})[id] || {};
    const so = m.segundaOpinion || {}, via = m.viaDeBeneficio || {};
    openSheet(`<div class="d-head"><h2 class="d-title">📘 ${esc(r.name)}</h2>
        <div class="d-kind">${isSel ? `<span class="tag good">${L("Seleccionada", "Shortlisted")}</span>` : `<span class="tag warn">${L("No seleccionada: solo para investigar", "Not shortlisted: research only")}</span>`}<span class="tag">${L("Entrada", "Entry")} ${esc(r.minEntry === 0 ? L("gratis", "free") : money(r.minEntry))}</span>${r.canLoseAll ? `<span class="tag bad">${L("Puedes perderlo todo", "You can lose it all")}</span>` : ""}</div></div>
      ${!isSel ? `<div class="blk callout warn"><p>${L("No cumple", "Misses")}: ${esc(arr(r.failed).join(", "))}.</p></div>` : ""}
      <div class="blk"><h3>${L("Qué es", "What it is")}</h3><p>${esc(m.resumen || "—")}</p></div>
      <div class="blk"><h3>${L("Cómo se gana dinero aquí", "How money is made here")}</h3><p>${esc(via.explicacion || "—")}</p></div>
      <div class="blk"><h3>${L("Cuánto poner", "How much to put in")}</h3><p>${esc(m.cuantoPoner || "—")}</p></div>
      <div class="blk"><h3>${L("Antes de empezar", "Before you start")}</h3>${listHtml(m.antesDeEmpezar)}</div>
      <div class="blk"><h3>${L("Paso a paso", "Step by step")}</h3>${arr(m.pasos).map((p, i) => `<label class="step ${prog[i] ? "done" : ""}"><input type="checkbox" data-step="${esc(id)}|${i}" ${prog[i] ? "checked" : ""}><span><span class="t"><b>${esc(p.titulo)}</b>${p.tiempo ? ` · ${esc(p.tiempo)}` : ""}</span><br><span>${esc(p.detalle || "")}</span>${p.enlace && safeUrl(p.enlace) ? `<br>${link(p.enlace)}` : ""}</span></label>`).join("")}</div>
      <div class="blk"><h3>${L("Plan de salida", "Exit plan")}</h3><p>${esc(m.planDeSalida || "—")}</p></div>
      <div class="blk"><h3>${L("Abandona si…", "Walk away if…")}</h3>${listHtml(m.senalesDeAlarma)}</div>
      <div class="blk"><h3>${L("Errores típicos", "Common mistakes")}</h3>${listHtml(m.erroresTipicos)}</div>
      <div class="blk"><h3>${L("Impuestos (orientativo)", "Taxes (indicative)")}</h3><p>${esc(m.fiscalidad || "—")}</p></div>
      <div class="blk"><h3>${L("Segunda opinión", "Second opinion")}</h3><p>${esc(so.veredicto || "—")} · ${esc(so.motivo || "")}</p></div>
      <p class="fine">${L("Manual generado por IA con los datos del radar: comprueba cada dato en la web oficial. No es asesoramiento financiero.", "AI-generated guide from radar data: check every detail on the official site. Not financial advice.")}</p>`);
  }

  function openMk(kind, sym) {
    const b = S.markets?.[kind]; const x = arr(b?.items).find((i) => i.symbol === sym);
    if (!x) return;
    const m = x.metrics || {}, t = x.tech || {};
    const budget = Math.min(2000, +(S.profile?.budget) || 2000);
    const loss = t.riskPct != null ? Math.round(budget * t.riskPct / 100) : null;
    const fair = x.fairValue ? `${money(x.fairValue[0], "USD")} – ${money(x.fairValue[1], "USD")}` : "—";
    const news = arr(x.news).map((n) => `<li>${link(n.url, n.title)}</li>`).join("");
    const isStock = kind === "stocks";
    const chart = isStock ? `https://www.tradingview.com/symbols/${encodeURIComponent(sym)}/` : `https://www.coingecko.com/${LANG === "en" ? "en" : "es"}/search?query=${encodeURIComponent(sym)}`;
    openSheet(`<div class="d-head"><div class="d-kind"><span class="tag" style="color:var(--c-${isStock ? "bolsa" : "cripto"})">${isStock ? L("Acción de EE. UU.", "US stock") : L("Cripto", "Crypto")}</span>${x.sector ? `<span>${esc(x.sector)}</span>` : ""}</div>
        <h2 class="d-title">${esc(sym)} · ${esc(x.name || "")}</h2>${strength(x.score ?? 0, x.trigger && !x.fallingKnife ? 3 : 1, x.trigger && !x.fallingKnife ? L("Señal de giro", "Turn signal") : L("Barata, en vigilancia", "Cheap, on watch"))}
        <div class="d-kind">${x.trigger && !x.fallingKnife ? `<span class="tag good">${L("Señal de giro", "Turn signal")}</span>` : `<span class="tag">${L("En vigilancia", "On watch")}</span>`}${x.fallingKnife ? `<span class="tag bad">${L("Cuchillo cayendo", "Falling knife")}</span>` : ""}</div></div>
      ${x.trigger?.text ? `<div class="blk callout"><h3>${L("La señal", "The signal")}</h3><p>${esc(x.trigger.text)}.</p></div>` : ""}
      <div class="blk"><h3>${L("Plan orientativo", "Indicative plan")}</h3><dl class="kv">
        <dt>${L("Precio de referencia", "Reference price")}</dt><dd>${esc(money(x.price, "USD"))}</dd>
        <dt>${L("Stop (la idea se invalida)", "Stop (idea invalidated)")}</dt><dd>${esc(money(t.stop, "USD"))} (${esc(pct(t.riskPct != null ? -t.riskPct : null))})</dd>
        <dt>${L(`Pérdida hasta el stop con ${nf(budget, 0)} €`, `Loss to stop with €${nf(budget, 0)}`)}</dt><dd>${loss != null ? "≈ " + esc(money(loss)) : "—"}</dd>
        ${isStock ? `<dt>${L("Valor razonable por múltiplos", "Fair value by multiples")}</dt><dd>${esc(fair)}</dd>` : ""}</dl></div>
      <div class="blk"><h3>${isStock ? L("Valor y calidad", "Value and quality") : L("Valor y uso", "Value and usage")}</h3><dl class="kv">${isStock ? `
        <dt>PER (${L("mediana", "median")} ${esc(nf(b.medians?.pe, 1))})</dt><dd>${esc(nf(m.pe, 1))}</dd>
        <dt>${L("Precio / caja libre", "Price / free cash flow")}</dt><dd>${esc(nf(m.pfcf, 1))}</dd>
        <dt>ROI</dt><dd>${esc(pct(m.roi, 1, false))}</dd><dt>${L("Margen bruto / operativo", "Gross / operating margin")}</dt><dd>${esc(pct(m.gm, 1, false))} / ${esc(pct(m.om, 1, false))}</dd>
        <dt>${L("Deuda / patrimonio", "Debt / equity")}</dt><dd>${esc(nf(m.de, 2))}</dd><dt>${L("Crecimiento de ventas", "Revenue growth")}</dt><dd>${esc(pct(m.revG))}</dd>
        <dt>${L("Calidad (0-9)", "Quality (0-9)")}</dt><dd>${esc(m.fscore ?? "—")}</dd>` : `
        <dt>${L("Capitalización / comisiones", "Market cap / fees")}</dt><dd>${esc(nf(m.pf, 1))}</dd><dt>MVRV</dt><dd>${esc(nf(m.mvrv, 2))}</dd>
        <dt>${L("Caída desde máximos", "Drawdown from ATH")}</dt><dd>${esc(pct(m.athDiscount, 0, false))}</dd><dt>${L("En circulación", "Circulating")}</dt><dd>${esc(pct(m.circulating, 0, false))}</dd>`}</dl></div>
      <div class="blk"><h3>${L("Técnico", "Technicals")}</h3><dl class="kv"><dt>${L("Medias 50 / 200", "50 / 200-day averages")}</dt><dd>${esc(money(t.sma50, "USD"))} / ${esc(money(t.sma200, "USD"))}</dd>
        <dt>RSI (14)</dt><dd>${esc(nf(t.rsi, 0))}</dd><dt>${L("Fuerza relativa 3 meses", "Relative strength 3m")}</dt><dd>${esc(pct(t.rs3m))}</dd></dl></div>
      ${x.reddit ? `<div class="blk"><h3>Reddit</h3><p>${esc(x.reddit.mentions)} ${L("menciones en 24 h (puesto", "mentions in 24h (rank")} ${esc(x.reddit.rank)}).</p></div>` : ""}
      ${news ? `<div class="blk srcs"><h3>${L("Noticias", "News")}</h3><ul>${news}</ul></div>` : ""}
      <div class="btns"><a class="btn primary" href="${esc(chart)}" target="_blank" rel="noopener noreferrer">${L("Ver gráfico", "View chart")}</a></div>
      <p class="fine">${L("Método: valor + calidad + momento con filtros anti-trampa; solo hay señal cuando aparece un giro técnico. No es asesoramiento financiero.", "Method: value + quality + momentum with value-trap filters; a signal needs a technical turn. Not financial advice.")}</p>`);
  }

  function openIdea(id) {
    const it = arr(S.ideas?.items).find((x) => x.id === id);
    if (!it) return;
    const mv = it.mvp || {}, cost = arr(mv.costEur);
    const mk = Object.keys(MK).map((m) => { const x = (it.markets || {})[m] || {};
      return `<div class="blk" style="margin-top:10px"><h3>${esc(mkName(m))} · ${x.origin ? L("ya existe (origen)", "already exists (origin)") : esc(fit(it, m)) + "/10"}</h3><p>${esc(x.why || "")}</p>${x.adapt ? `<p class="d-orig">${L("Adaptar", "Adapt")}: ${esc(x.adapt)}</p>` : ""}${x.competition ? `<p class="d-orig">${L("Competencia", "Competition")}: ${esc(x.competition)}</p>` : ""}</div>`; }).join("");
    openSheet(`<div class="d-head"><div class="d-kind"><span class="tag" style="color:var(--c-ideas)">${esc(ITYPE[it.type] || it.type || "")}</span><span>${L("Origen", "Origin")}: ${esc(it.originCountry || "—")}</span><span>${esc(shortDate(it.foundAt))}</span></div>
        <h2 class="d-title">${esc(it.name)}</h2>${strength(it.score ?? 0, (it.score ?? 0) >= 70 ? 3 : 2, L("Nota de la idea", "Idea score"))}
        <div class="d-kind">${it.verified ? `<span class="tag good">${L("Datos comprobados", "Facts checked")}</span>` : `<span class="tag warn">${L("Datos sin comprobar", "Facts unchecked")}</span>`}${it.regulated ? `<span class="tag warn">${L("Regulado: licencias", "Regulated: licences")}</span>` : ""}</div></div>
      <div class="blk"><p>${esc(it.summary || "")}</p></div>
      <div class="blk"><h3>${L("Pruebas de éxito", "Proof of traction")}</h3>${listHtml(it.traction)}</div>
      <div class="blk"><h3>${L("Por qué funcionó", "Why it worked")}</h3>${listHtml(it.whyItWorked)}</div>
      ${mk}
      <div class="blk"><h3>${L("Cómo gana dinero", "Business model")}</h3><p>${esc(it.monetization || "—")}</p></div>
      <div class="blk"><h3>MVP</h3><dl class="kv"><dt>${L("Coste", "Cost")}</dt><dd>${cost.length ? esc(nf(cost[0], 0)) + "–" + esc(nf(cost[1], 0)) + " €" : "—"}</dd><dt>${L("Semanas", "Weeks")}</dt><dd>${esc(mv.weeks || "—")}</dd><dt>${L("Equipo", "Team")}</dt><dd>${esc(mv.team || "—")}</dd></dl></div>
      <div class="blk"><h3>${L("Primeros pasos para validarla", "First validation steps")}</h3>${listHtml(it.firstSteps)}</div>
      <div class="blk"><h3>${L("Riesgos", "Risks")}</h3>${listHtml(it.risks)}</div>
      <div class="blk srcs"><h3>${L("Enlaces", "Links")}</h3><ul>${arr(it.links).map((l) => `<li>${link(l.url, l.title)}</li>`).join("")}</ul></div>
      <p class="fine">${L("Analizada por IA y contrastada con la fuente. La competencia local y el tamaño de mercado hay que comprobarlos sobre el terreno.", "AI-analysed and checked against the source. Local competition and market size need checking on the ground.")}</p>`);
  }

  // ------------------------------------------------------------------ ajustes y sincronización opcional
  const repoGuess = (() => {
    const host = location.hostname, seg = location.pathname.split("/").filter(Boolean)[0];
    return host.endsWith(".github.io") ? {owner: host.split(".")[0], repo: seg || host} : null;
  })();
  const gh = {
    cfg() { return {...(repoGuess || {}), ...LS.get("radar-gh", {})}; },
    ready() { const c = this.cfg(); return !!(c.token && c.owner && c.repo); },
    async getFile(path) {
      const c = this.cfg();
      const r = await fetch(`https://api.github.com/repos/${c.owner}/${c.repo}/contents/${path}`, {headers: {Authorization: `Bearer ${c.token}`, Accept: "application/vnd.github+json"}, cache: "no-store"});
      if (r.status === 404) return {data: null, sha: null};
      if (!r.ok) throw new Error("GitHub " + r.status);
      const j = await r.json();
      return {data: JSON.parse(decodeURIComponent(escape(atob(j.content.replace(/\n/g, ""))))), sha: j.sha};
    },
    async putFile(path, data, message) {
      const c = this.cfg();
      for (let i = 0; i < 2; i++) {
        const cur = await this.getFile(path).catch(() => ({sha: null}));
        const body = {message, content: btoa(unescape(encodeURIComponent(JSON.stringify(data, null, 1)))), ...(cur.sha ? {sha: cur.sha} : {})};
        const r = await fetch(`https://api.github.com/repos/${c.owner}/${c.repo}/contents/${path}`, {method: "PUT", headers: {Authorization: `Bearer ${c.token}`, Accept: "application/vnd.github+json"}, body: JSON.stringify(body)});
        if (r.ok) return true;
        if (r.status !== 409) throw new Error("GitHub " + r.status);
      }
      throw new Error("conflicto al guardar");
    },
  };
  const defaultProfile = () => ({budget: 2000, budgetAuthorizedAbove150: true, alertThreshold: 75, urgentThreshold: 85, categories: ["cripto", "startups", "ia_tecnologia", "lanzamientos", "negocio"], region: "es", language: LANG});
  let syncTimer = null;
  function scheduleSync() {
    if (!gh.ready()) return;
    clearTimeout(syncTimer);
    syncTimer = setTimeout(async () => {
      try {
        const slim = Object.fromEntries(Object.entries(S.actions).filter(([, v]) => v.action).map(([k, v]) => [k, {action: v.action, at: v.at}]));
        await gh.putFile("data/actions.json", slim, "App: acciones del usuario");
        await gh.putFile("data/profile.json", {...(S.profile || defaultProfile()), updatedAt: new Date().toISOString()}, "App: ajustes del usuario");
        toast(L("Sincronizado con el radar", "Synced with the radar"));
      } catch (e) { toast(L("No se pudo sincronizar: ", "Sync failed: ") + e.message); }
    }, 1200);
  }
  function setAction(id, actName) {
    const prev = S.actions[id] || {};
    const next = prev.action === actName ? null : actName;
    S.actions[id] = {...prev, action: next, at: new Date().toISOString()};
    LS.set("radar-actions", S.actions); scheduleSync();
    toast(next === "guardada" ? L("Guardada", "Saved") : next === "investigada" ? L("Marcada como investigada", "Marked as researched") : next === "descartada" ? L("Descartada", "Dismissed") : L("Estado quitado", "Status cleared"));
    if (next === "descartada") { closeSheet(); render(); } else openOpp(id);
  }

  function sourceRows() {
    const out = [];
    for (const [n, s] of Object.entries(S.feed?.sources || {})) out.push({n, ok: s.ok, c: s.n, at: s.at, err: s.err});
    for (const [n, s] of Object.entries(S.status?.sources || {})) if (!out.some((o) => o.n === n)) out.push({n: n.replace(/_/g, " "), ok: s.ok, c: s.items, at: s.at, err: s.error});
    out.sort((a, b) => (a.ok - b.ok) || a.n.localeCompare(b.n));
    return out.map((s) => `<div class="src-row"><i class="${s.ok ? "" : "bad"}"></i><span title="${esc(s.err || "")}">${esc(s.n)}${s.ok ? "" : ` · ${esc(s.err || "")}`}</span><em>${esc(s.c ?? 0)} · ${esc(ago(s.at))}</em></div>`).join("");
  }
  function openSettings() {
    const p = S.profile || defaultProfile();
    const theme = LS.get("radar-theme", "auto");
    const c = gh.cfg();
    const run = S.feed?.run || {};
    openSheet(`<div class="d-head"><h2 class="d-title">${L("Ajustes", "Settings")}</h2></div>
      <div class="blk"><h3>${L("Idioma y aspecto", "Language and look")}</h3>
        <div class="field"><label for="sLang">${L("Idioma", "Language")}</label><select id="sLang"><option value="es" ${LANG === "es" ? "selected" : ""}>Español</option><option value="en" ${LANG === "en" ? "selected" : ""}>English</option></select></div>
        <div class="field"><label for="sTheme">${L("Tema", "Theme")}</label><select id="sTheme">${[["auto", L("Automático", "Automatic")], ["dark", L("Oscuro", "Dark")], ["light", L("Claro", "Light")]].map(([k, l]) => `<option value="${k}" ${theme === k ? "selected" : ""}>${l}</option>`).join("")}</select></div></div>
      <div class="blk"><h3>${L("Tu perfil para el análisis", "Your profile for the analysis")}</h3>
        <div class="field"><label for="sRegion">${L("Región donde buscar oportunidades", "Region to search for opportunities")}</label><select id="sRegion">${[["es", "España"], ["eu", L("Unión Europea", "European Union")], ["uk", L("Reino Unido", "United Kingdom")], ["us", L("Estados Unidos", "United States")], ["latam", "Latinoamérica"], ["global", "Global"]].map(([k, l]) => `<option value="${k}" ${p.region === k ? "selected" : ""}>${l}</option>`).join("")}</select></div>
        <div class="field"><label for="sBudget">${L("Capital máximo (€)", "Maximum capital (€)")}</label><input id="sBudget" type="number" min="0" max="2000" step="1" value="${esc(p.budget ?? 2000)}"></div>
        <p class="fine" style="margin-top:8px">${gh.ready() ? L("Se envía al radar con la sincronización.", "Sent to the radar through sync.") : L("Se guarda en este móvil. Para que el motor en la nube lo use, conecta la sincronización (abajo).", "Saved on this phone. Connect sync (below) for the cloud engine to use it.")}</p>
        <div class="btns"><button class="btn primary" type="button" id="saveProfile">${L("Guardar perfil", "Save profile")}</button></div></div>
      <div class="blk"><h3>${L("Avisos en el móvil", "Phone alerts")}</h3>
        <p>${L("Llegan con la app gratuita ntfy aunque tengas esta app cerrada: solo lo muy fuerte (nota 82 o más), como mucho 3 por hora y 18 al día, y de 23:00 a 8:00 solo lo excepcional.", "They arrive via the free ntfy app even with this app closed: only very strong items (score 82+), at most 3 per hour and 18 a day, and from 23:00 to 8:00 only exceptional ones.")}</p></div>
      <div class="blk"><h3>${L("Compartir e instalar", "Share and install")}</h3>
        <p>${L("Android (Chrome): menú ⋮ → «Instalar aplicación». iPhone (Safari): Compartir → «Añadir a pantalla de inicio».", "Android (Chrome): menu ⋮ → “Install app”. iPhone (Safari): Share → “Add to Home Screen”.")}</p>
        <div class="btns"><button class="btn" type="button" id="shareApp">${L("Compartir la app", "Share the app")}</button><button class="btn" type="button" id="installBtn" ${installEvt ? "" : "hidden"}>${L("Instalar", "Install")}</button></div></div>
      <div class="blk"><h3>${L("Sincronización con el motor (opcional)", "Sync with the engine (optional)")}</h3>
        <p class="fine" style="margin-top:0">${L("Permite que el motor en la nube use tu región, presupuesto y descartes. Necesita un token de GitHub de acceso detallado con permiso «Contents: lectura y escritura» solo para este repositorio.", "Lets the cloud engine use your region, budget and dismissals. Needs a fine-grained GitHub token with “Contents: read and write” on this repository only.")}</p>
        <div class="field"><label for="ghToken">Token</label><input id="ghToken" type="password" autocomplete="off" placeholder="${c.token ? L("Token guardado en este móvil", "Token saved on this phone") : "github_pat_…"}"></div>
        <div class="btns"><button class="btn" type="button" id="saveGh">${L("Conectar", "Connect")}</button><button class="btn" type="button" id="clearGh">${L("Borrar token", "Delete token")}</button></div></div>
      <div class="blk"><h3>${L("Cómo funciona", "How it works")}</h3>
        <p>${L("Un motor en la nube (GitHub Actions) revisa cada 5 minutos más de 50 fuentes gratuitas: precios y movimientos de cripto, anuncios de Binance, OKX, Coinbase y Kraken, DeFi, bolsa de EE. UU. (cotizaciones, resultados, salidas a bolsa y compras de directivos), noticias, Reddit, StockTwits, Bluesky, Hacker News y ayudas públicas de la BDNS. Una IA filtra el ruido y resume en español. GitHub no permite programarlo más a menudo y a veces retrasa las ejecuciones; esta app comprueba si hay novedades cada minuto.", "A cloud engine (GitHub Actions) checks 50+ free sources every 5 minutes: crypto prices and moves, Binance/OKX/Coinbase/Kraken announcements, DeFi, US stocks (quotes, earnings, IPOs and insider buying), news, Reddit, StockTwits, Bluesky, Hacker News and Spanish public grants. An AI filters noise and summarises. GitHub doesn't allow a tighter schedule and sometimes delays runs; this app checks for news every minute.")}</p>
        <p style="margin-top:8px">${L("Cada 3 horas se analizan a fondo las mejores candidatas (una IA analiza y otra distinta verifica), y una vez al día se estudian los mercados y las ideas de negocio. Nunca compra, vende ni pide claves o frases semilla.", "Every 3 hours the best candidates get a deep dive (one AI analyses, a different one verifies), and once a day markets and business ideas are studied. It never buys, sells or asks for keys or seed phrases.")}</p>
        ${run.seconds ? `<p class="fine">${L("Último pulso", "Last pulse")}: ${esc(fmtDate(S.feed.generatedAt))} · ${esc(run.collectors)} ${L("fuentes consultadas", "sources checked")} · ${esc(run.added)} ${L("novedades", "new items")} · ${esc(run.seconds)} s</p>` : ""}</div>
      <div class="blk"><h3>${L("Estado de las fuentes", "Source status")}</h3>${sourceRows() || `<p class="fine">${L("Sin datos todavía.", "No data yet.")}</p>`}</div>`);
  }

  // ------------------------------------------------------------------ eventos
  let installEvt = null;
  window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); installEvt = e; const b = $("#installBtn"); if (b) b.hidden = false; });

  document.addEventListener("click", async (e) => {
    const t = e.target;
    const tab = t.closest("[data-tab]"); if (tab) { go(tab.dataset.tab); return; }
    if (t.closest("[data-close]")) { closeSheet(); return; }
    const itemEl = t.closest("[data-item]"); if (itemEl) { openItem(itemEl.dataset.item); return; }
    const oppEl = t.closest("[data-opp]"); if (oppEl) { openOpp(oppEl.dataset.opp); return; }
    const mkEl = t.closest("[data-mk]"); if (mkEl) { const [k, s] = mkEl.dataset.mk.split("|"); openMk(k, s); return; }
    const ideaEl = t.closest("[data-idea]"); if (ideaEl) { openIdea(ideaEl.dataset.idea); return; }
    const man = t.closest("[data-manual]"); if (man) { openManual(man.dataset.manual); return; }
    const chip = t.closest("[data-chip]"); if (chip) { S.chip[S.tab] = chip.dataset.chip; S.limit = 60; render(); return; }
    const seg = t.closest("[data-seg]"); if (seg) { S.seg[S.tab] = seg.dataset.seg; LS.set("radar-segs", S.seg); S.limit = 60; render(); return; }
    const om = t.closest("[data-oppmin]"); if (om) { S.oppMin = +om.dataset.oppmin; render(); return; }
    const imk = t.closest("[data-ideamk]"); if (imk) { S.ideaMk = imk.dataset.ideamk; render(); return; }
    const ity = t.closest("[data-ideatype]"); if (ity) { S.ideaType = ity.dataset.ideatype; render(); return; }
    if (t.closest("[data-useful]")) { S.useful = !S.useful; LS.set("radar-useful", S.useful); render(); return; }
    if (t.closest("[data-more]")) { S.limit += 60; render(); return; }
    const sv = t.closest("[data-save]");
    if (sv) {
      const id = sv.dataset.save, it = items().find((x) => x.id === id) || S.saved[id];
      if (S.saved[id]) delete S.saved[id]; else if (it) S.saved[id] = it;
      const keys = Object.keys(S.saved); if (keys.length > 200) delete S.saved[keys[0]];
      LS.set("radar-saved", S.saved);
      toast(S.saved[id] ? L("Guardada en Top", "Saved to Top") : L("Quitada de guardadas", "Removed from saved"));
      sv.classList.toggle("on", !!S.saved[id]); sv.textContent = S.saved[id] ? L("Guardada", "Saved") : L("Guardar", "Save");
      return;
    }
    const sh = t.closest("[data-share]");
    if (sh) {
      const it = items().find((x) => x.id === sh.dataset.share) || S.saved[sh.dataset.share];
      const url = location.origin + location.pathname + "#item=" + encodeURIComponent(sh.dataset.share);
      const data = {title: "Radar", text: it ? txt(it) : "Radar", url: safeUrl(it?.url) || url};
      try { if (navigator.share) { await navigator.share(data); return; } } catch { return; }
      try { await navigator.clipboard.writeText(data.url); toast(L("Enlace copiado", "Link copied")); } catch { toast(data.url); }
      return;
    }
    const oa = t.closest("[data-oppact]"); if (oa) { const [id, a] = oa.dataset.oppact.split("|"); setAction(id, a); return; }
    if (t.closest("#newPill")) { $("#newPill").classList.remove("show"); window.scrollTo({top: 0, behavior: "smooth"}); render(); return; }
    if (t.closest("#refreshBtn")) { loadAll(true); return; }
    if (t.closest("#settingsBtn")) { openSettings(); return; }
    if (t.closest("#shareApp")) {
      const url = location.origin + location.pathname;
      const data = {title: "Opportunity Radar", text: L("Radar de oportunidades en vivo: cripto, bolsa, startups, IA e ideas de negocio", "Live opportunity radar: crypto, stocks, startups, AI and business ideas"), url};
      try { if (navigator.share) { await navigator.share(data); return; } } catch { return; }
      try { await navigator.clipboard.writeText(url); toast(L("Enlace copiado: ", "Link copied: ") + url); } catch { toast(url); }
      return;
    }
    if (t.closest("#installBtn") && installEvt) { installEvt.prompt(); await installEvt.userChoice; installEvt = null; t.closest("#installBtn").hidden = true; return; }
    if (t.closest("#saveProfile")) {
      let budget = Math.max(0, Math.min(2000, +$("#sBudget").value || 0));
      S.profile = {...(S.profile || defaultProfile()), budget, budgetAuthorizedAbove150: budget > 150, region: $("#sRegion").value, language: LANG, updatedAt: new Date().toISOString()};
      LS.set("radar-profile", S.profile); scheduleSync();
      toast(gh.ready() ? L("Perfil guardado: el radar lo usará en el próximo análisis", "Profile saved: the radar will use it in the next analysis") : L("Perfil guardado en este móvil", "Profile saved on this phone"));
      return;
    }
    if (t.closest("#saveGh")) {
      const tok = $("#ghToken").value.trim();
      if (!tok) { toast(L("Pega primero el token", "Paste the token first")); return; }
      LS.set("radar-gh", {...LS.get("radar-gh", {}), token: tok}); $("#ghToken").value = "";
      try { await gh.getFile("data/status.json"); toast(L("Conectado con el repositorio", "Connected to the repository")); scheduleSync(); }
      catch (err) { toast(L("No se pudo conectar: ", "Could not connect: ") + err.message); }
      return;
    }
    if (t.closest("#clearGh")) { LS.set("radar-gh", {}); toast(L("Token borrado de este móvil", "Token deleted from this phone")); return; }
  });
  document.addEventListener("change", (e) => {
    const t = e.target;
    if (t.id === "sLang") { LS.set("radar-lang", t.value); location.reload(); return; }
    if (t.id === "sTheme") {
      LS.set("radar-theme", t.value);
      const light = t.value === "light" || (t.value === "auto" && matchMedia("(prefers-color-scheme: light)").matches);
      if (light) document.documentElement.dataset.theme = "light"; else delete document.documentElement.dataset.theme;
      return;
    }
    if (t.dataset.oppnote) { const id = t.dataset.oppnote; S.actions[id] = {...(S.actions[id] || {}), note: t.value.slice(0, 500)}; LS.set("radar-actions", S.actions); toast(L("Nota guardada", "Note saved")); return; }
    if (t.dataset.step) {
      const [id, i] = t.dataset.step.split("|"); const prog = LS.get("radar-manual-progress", {});
      prog[id] = prog[id] || {}; prog[id][i] = t.checked; LS.set("radar-manual-progress", prog);
      t.closest(".step").classList.toggle("done", t.checked);
    }
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeSheet(); });
  window.addEventListener("popstate", () => closeSheet(true));
  window.addEventListener("scroll", () => { if (window.scrollY < 60) $("#newPill").classList.remove("show"); }, {passive: true});

  // deslizar a izquierda/derecha para cambiar de pestaña
  let touch = null;
  $("#view").addEventListener("touchstart", (e) => {
    if (e.touches.length !== 1 || e.target.closest(".segs,.table-wrap,.ticker,.tabbar")) { touch = null; return; }
    touch = {x: e.touches[0].clientX, y: e.touches[0].clientY, t: Date.now()};
  }, {passive: true});
  $("#view").addEventListener("touchend", (e) => {
    if (!touch) return;
    const dx = e.changedTouches[0].clientX - touch.x, dy = e.changedTouches[0].clientY - touch.y, dt = Date.now() - touch.t;
    touch = null;
    if (Math.abs(dx) < 70 || Math.abs(dx) < Math.abs(dy) * 1.8 || dt > 650) return;
    const i = TAB_IDS.indexOf(S.tab);
    const next = TAB_IDS[(i + (dx < 0 ? 1 : -1) + TAB_IDS.length) % TAB_IDS.length];
    go(next);
  }, {passive: true});

  function routeHash() {
    const h = decodeURIComponent(location.hash.slice(1));
    if (!h) return;
    if (TAB_IDS.includes(h)) { if (S.tab !== h) go(h, {push: false}); return; }
    if (h.startsWith("item=")) { openItem(h.slice(5)); return; }
    if (h === "mercados") { S.seg.bolsa = "value"; go("bolsa", {push: false}); return; }
    if (h === "seleccion") { go("top", {push: false}); return; }
    if (S.opps.some((o) => o.id === h)) openOpp(h);
  }
  window.addEventListener("hashchange", () => { if (!sheet.classList.contains("open")) routeHash(); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) { pollFeed(); pollPrices(); } });

  // ------------------------------------------------------------------ arranque
  const h0 = decodeURIComponent(location.hash.slice(1));
  S.tab = TAB_IDS.includes(h0) ? h0 : "vivo";
  if (!Object.keys(S.lastSeen).length) S.lastSeen = {};
  S.visitFrom[S.tab] = S.lastSeen[S.tab] || null;
  render(); renderTabbar(); renderTicker();
  loadAll().then(() => {
    if (!Object.keys(S.lastSeen).length && S.feed?.generatedAt) {
      for (const t of TAB_IDS) S.lastSeen[t] = S.feed.generatedAt;
      LS.set("radar-lastseen", S.lastSeen);
    }
    seenTimer = setTimeout(() => markSeen(S.tab), 2500);
  });
  pollPrices();
  setInterval(pollFeed, 60000);
  setInterval(pollPrices, 60000);
  setInterval(pollSlow, 5 * 60000);
  setInterval(renderLive, 30000);
})();
