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
  // Menos pestañas: «Para ti» (lo que elige Claude) primero; IA, lanzamientos, noticias y redes siguen en «En vivo»
  const TABS = [
    {id: "parati", e: "🎯", es: "Para ti", en: "For you", c: "var(--c-top)"},
    {id: "casa", e: "🏡", es: "Desde casa", en: "From home", c: "var(--c-casa)"},
    {id: "vivo", e: "⚡", es: "En vivo", en: "Live", c: "var(--c-vivo)"},
    {id: "cripto", e: "🪙", es: "Cripto", en: "Crypto", c: "var(--c-cripto)"},
    {id: "bolsa", e: "📈", es: "Bolsa", en: "Stocks", c: "var(--c-bolsa)"},
    {id: "startups", e: "🚀", es: "Startups", en: "Startups", c: "var(--c-startups)"},
    {id: "ideas", e: "💡", es: "Ideas", en: "Ideas", c: "var(--c-ideas)"},
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
    feed: null, opps: [], selected: null, markets: null, paper: null, ideas: null, status: null, brief: null, prof: LS.get("radar-prof", null),
    tab: "parati", seg: LS.get("radar-segs", {}), chip: {}, useful: LS.get("radar-useful", true), limit: 60,
    lastSeen: LS.get("radar-lastseen", {}), visitFrom: {}, fresh: new Set(), saved: LS.get("radar-saved", {}),
    actions: LS.get("radar-actions", {}), profile: LS.get("radar-profile", null), loaded: false, live: null,
    ideaMk: "all", ideaType: "", oppMin: 45, casaTema: LS.get("radar-casa-tema", "all"),
  };
  let merged = null;
  const items = () => {
    if (merged) return merged;
    const srv = arr(S.feed?.items).filter((x) => x.cat !== "casa");  // lo de «Desde casa» va en su pestaña
    const ids = new Set(srv.map((x) => x.id));
    merged = LIVE.items.filter((x) => !ids.has(x.id)).concat(srv);
    return merged;
  };
  const invalidate = () => { merged = null; };
  const LIVE = {items: arr(LS.get("radar-live-items", [])).filter((x) => Date.now() - (toDate(x.t) || 0) < 12 * 3600e3 && (x.m || {}).cur !== "EUR"), at: null, cgAt: 0, trAt: 0, bnAt: 0};
  const inCat = (it, c) => it.cat === c || arr(it.also).includes(c);
  const useful = (it) => !it.h && (((it.opp ?? 1) >= 2 && (it.s ?? 0) >= 55) || (it.s ?? 0) >= 78);
  const txt = (it) => (LANG === "en" ? it.en || it.title || it.es : it.es || it.title) || "";
  const why = (it) => (LANG === "en" ? it.why_en || it.why : it.why) || "";
  const act = (it) => (LANG === "en" ? it.act_en || it.act : it.act) || "";
  const when = (it) => it.w || it.t || it.pub;

  // ------------------------------------------------------------------ datos
  async function getJSON(name) {
    // revalidación con ETag cada vez (cache: no-cache) y, por si el navegador la ignora, la URL cambia cada 2 minutos
    const r = await fetch(`data/${name}?m=${Math.floor(Date.now() / 120000)}`, {cache: "no-cache"});
    if (!r.ok) throw new Error(`${name} ${r.status}`);
    return r.json();
  }
  async function loadAll(manual = false) {
    const btn = $("#refreshBtn"); btn.classList.add("spin");
    const [feed, opps, selected, markets, paper, ideas, status, brief, profiles] = await Promise.all(
      ["feed.json", "opps.json", "selected.json", "markets.json", "paper.json", "ideas.json", "status.json", "brief.json", "profiles.json"].map((n) => getJSON(n).catch(() => null)));
    if (brief) S.brief = brief;
    if (profiles) S.profiles = profiles;
    btn.classList.remove("spin");
    if (feed) acceptFeed(feed, !S.loaded); else if (!S.feed) { S.feed = LS.get("radar-feed-cache", null); invalidate(); }
    if (opps) S.opps = arr(opps); if (selected) S.selected = selected; if (markets) S.markets = markets;
    if (paper) S.paper = paper; if (ideas) S.ideas = ideas; if (status) S.status = status;
    S.loaded = true;
    if (manual) toast(feed ? L("Actualizado", "Updated") : L("Sin conexión: se muestran los últimos datos guardados", "Offline: showing the last saved data"));
    if (S.autoTab) {  // sin enlace concreto: abre la pestaña que prefiera el perfil de este móvil
      S.autoTab = false;
      const st = curProfile()?.profile?.start_tab;
      if (st && TAB_IDS.includes(st) && st !== S.tab) S.tab = st;
    }
    render(); renderLive(); renderTicker(); renderTabbar();
    routeHash();
  }
  function acceptFeed(feed, first) {
    const before = new Set([...arr(S.feed?.items), ...LIVE.items].map((x) => x.id));
    const prevAt = S.feed?.generatedAt;
    S.feed = feed; invalidate();
    try {
      const all = arr(feed.items);
      LS.set("radar-feed-cache", {...feed, items: [...all.filter((x) => x.cat !== "casa").slice(0, 250), ...all.filter((x) => x.cat === "casa").slice(0, 80)]});
    } catch {}
    if (first || !prevAt) return 0;
    const added = arr(feed.items).filter((x) => !before.has(x.id));
    added.forEach((x) => S.fresh.add(x.id));
    return added.filter((x) => (x.cat === "casa") === (S.tab === "casa")).length;  // el aviso «↑ nuevas», solo con lo de esta pestaña
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
    const [opps, selected, markets, ideas, status, paper, brief, profiles] = await Promise.all(
      ["opps.json", "selected.json", "markets.json", "ideas.json", "status.json", "paper.json", "brief.json", "profiles.json"].map((n) => getJSON(n).catch(() => null)));
    if (opps) S.opps = arr(opps); if (selected) S.selected = selected; if (markets) S.markets = markets;
    if (ideas) S.ideas = ideas; if (status) S.status = status; if (paper) S.paper = paper;
    if (brief) S.brief = brief; if (profiles) S.profiles = profiles;
    if (!["vivo", "noticias", "redes"].includes(S.tab) && window.scrollY < 160 && !$("#sheet").classList.contains("open")) render();
  }
  let liveTicker = {};
  const num = (v) => { const x = parseFloat(String(v ?? "").replace(/[,%+\s]/g, "")); return isNaN(x) ? null : x; };
  const MACRO = {".SPX": "SPX", ".IXIC": "IXIC", "US10Y": "US10Y", "@LCO.1": "BRENT", "@GC.1": "GOLD", "@SI.1": "SILVER", "XAU=": "GOLD_SPOT", "XAG=": "SILVER_SPOT"};
  const qTime = (s) => { s = String(s || ""); if (s.length <= 10) return null; const d = new Date(s.replace(/([+-]\d{2})(\d{2})$/, "$1:$2")); return isNaN(d) ? null : d; };
  const bdays = (a, b) => {  // días laborables entre dos fechas AAAA-MM-DD
    let d = new Date(a.slice(0, 10) + "T12:00:00Z"), n = 0; const e = new Date(String(b).slice(0, 10) + "T12:00:00Z");
    if (isNaN(d) || isNaN(e)) return 0;
    while (d < e && n < 9) { d = new Date(+d + 864e5); const w = d.getUTCDay(); if (w > 0 && w < 6) n++; }
    return n;
  };
  // La caché de CNBC a veces devuelve el registro de otra sesión con la fecha de hoy: se guarda la hora y el cierre de
  // referencia del último registro bueno de cada símbolo y se descarta lo que sea más viejo (mismas reglas que el servidor).
  const lastGood = {};
  async function pollPrices() {
    if (document.hidden) return;
    const crypto = (async () => {
      const r = await fetch("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd&include_24hr_change=true", {cache: "no-store"});
      if (!r.ok) return;
      const d = await r.json();
      for (const [id, sym] of [["bitcoin", "BTC"], ["ethereum", "ETH"], ["solana", "SOL"]]) {
        if (d[id]) liveTicker[sym] = {p: d[id].usd, ch: d[id].usd_24h_change, cur: "USD"};
      }
    })().catch(() => {});
    const macro = (async () => {
      const got = {};
      try {
        const r = await fetch("https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols=" + encodeURIComponent(Object.keys(MACRO).join("|")) +
          "&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json&events=1", {cache: "no-store"});
        if (r.ok) {
          const d = await r.json(), now = Date.now(), tk = S.feed?.ticker || {};
          for (const k of ["SPX", "IXIC", "US10Y", "BRENT"]) {  // lo ya validado por el servidor sirve de punto de partida
            const t = qTime(tk[k]?.at);
            if (t && !lastGood[k]) lastGood[k] = {t: +t, settle: tk[k].settle || null};
          }
          for (const q of arr(d?.FormattedQuoteResult?.FormattedQuote)) {
            const k = MACRO[q.symbol], p = num(q.last), t = qTime(q.last_time), settle = String(q.settleDate || "").slice(0, 10) || null, g = lastGood[k] || {};
            if (!k || !(p > 0)) continue;
            if (t && (t - now > 3 * 60e3 || now - t > 5 * 864e5)) continue;
            const newer = settle && g.settle && settle > g.settle;
            if (!newer && ((t && g.t && t < g.t - 120e3) || (settle && g.settle && settle < g.settle))) continue;
            const rec = {p, ch: num(q.change_pct), chg: num(q.change), cur: "USD"};
            if (settle && bdays(settle, q.last_time) > 1) rec.ch = rec.chg = null;  // cierre de referencia de hace más de una sesión
            got[k] = rec;
            lastGood[k] = {t: t ? +t : g.t, settle: settle || g.settle || null};
          }
        }
      } catch {}
      for (const [k, tol] of [["GOLD", 1.5], ["SILVER", 2.5]]) {  // oro y plata al contado, contrastados con el futuro
        const f = got[k], s = got[k + "_SPOT"];
        delete got[k + "_SPOT"];
        if (s) got[k] = f && f.ch != null && s.ch != null && Math.abs(f.ch - s.ch) > tol ? {...s, ch: null, chg: null} : s;
      }
      Object.assign(liveTicker, got);
      const tk = S.feed?.ticker || {};
      await Promise.all([["GOLD", "XAU"], ["SILVER", "XAG"]].filter(([k]) => !liveTicker[k] && !tk[k]).map(async ([k, sym]) => {
        try { const r = await fetch(`https://api.gold-api.com/price/${sym}`, {cache: "no-store"}); const d = r.ok ? await r.json() : null; if (d?.price) liveTicker[k] = {p: d.price, cur: "USD"}; } catch {}
      }));
    })();
    await Promise.all([crypto, macro]);
    renderTicker();
  }

  // ------------------------------------------------------------------ pulso en el navegador
  // Con la app abierta se miran cada pocos minutos las fuentes que lo permiten desde el móvil (CoinGecko y anuncios de
  // Binance), con las mismas reglas e identificadores que el motor: así hay novedades aunque GitHub retrase su pulso.
  const STABLES = new Set("usdt usdc dai fdusd usde tusd pyusd usdd eurc eurs usds usd1 gusd frax lusd susd busd usdp rlusd usdx eure usdtb susde buidl usyc bfusd usdf usdg".split(" "));
  const WRAPPED = new Set("wbtc weth steth wsteth cbbtc reth weeth ezeth cbeth wbeth meth lbtc solvbtc jitosol msol bnsol rseth tbtc wbnb clbtc fbtc jlp bbsol stkaave oseth pufeth lseth sweth".split(" "));
  const plainCoin = (sym, name) => {
    const s = String(sym || "").toLowerCase(), n = String(name || "").toLowerCase();
    if (STABLES.has(s) || WRAPPED.has(s)) return false;
    return !["wrapped", "staked", "bridged", "usd coin", "stablecoin", "liquid staking", "restaked", "tokenized", "xstock", "bstocks", "tokenised", "backed ", "(ondo"].some((w) => n.includes(w));
  };
  const bucket = (p, steps) => steps.filter((x) => Math.abs(p) >= x).length;
  const scoreMove = (p, vr, mcap, thr) => {
    let s = 52 + Math.min(22, (Math.abs(p) - thr) * 1.6);
    if (vr) s += Math.min(10, Math.max(0, (vr - 0.05) * 60));
    s += mcap >= 5e9 ? 6 : mcap >= 1e9 ? 3 : mcap >= 2e8 ? 0 : -6;
    return Math.round(Math.max(0, Math.min(95, s)));
  };
  const absPct = (x) => nf(Math.abs(x), 1) + (LANG === "en" ? "%" : " %");
  function cgMoves(data, day) {
    const hot = new Set(LIVE.trending || []), out = [];
    for (const c of data) {
      const sym = String(c.symbol || "").toUpperCase(), name = c.name || "";
      const mcap = c.market_cap || 0, vol = c.total_volume || 0;
      if (!plainCoin(sym, name) || mcap < 1e8 || vol < 5e6) continue;
      const ch1 = c.price_change_percentage_1h_in_currency, ch24 = c.price_change_percentage_24h_in_currency ?? c.price_change_percentage_24h;
      const vr = mcap ? vol / mcap : null, isHot = hot.has(c.id);
      const m = {price: c.current_price, cur: "USD", ch1h: ch1, ch24h: ch24, vol, mcap, rank: c.market_cap_rank};
      const url = `https://www.coingecko.com/${LANG === "en" ? "en/coins" : "es/monedas"}/${c.id}`;
      if (ch24 != null && Math.abs(ch24) >= 10) {
        const up = ch24 > 0;
        out.push({id: `mv:${c.id}:${day}:${up ? "u" : "d"}${bucket(ch24, [10, 20, 35, 60])}`, cat: "cripto", kind: "move", src: "CoinGecko", local: 1,
          title: `${name} (${sym}) ${up ? "sube" : "cae"} un ${nf(Math.abs(ch24), 1)} % en 24 h`,
          es: `${name} (${sym}) ${up ? "sube" : "cae"} un ${nf(Math.abs(ch24), 1)} % en 24 h`, en: `${name} (${sym}) ${up ? "up" : "down"} ${Math.abs(ch24).toFixed(1)}% in 24h`,
          why: `Movimiento fuerte con ${big(vol, "USD")} de volumen en 24 h.` + (isHot ? " Además está entre las más buscadas en CoinGecko." : ""),
          why_en: "Strong move on heavy 24h volume." + (isHot ? " It is also trending on CoinGecko searches." : ""),
          act: up ? "Busca la noticia que lo explica antes de entrar. Si compras, que sea poco y con stop." : "No compres a ciegas «porque está barato»: espera a que se estabilice y busca la causa.",
          act_en: up ? "Find the news behind it before buying. Size small and use a stop." : "Don't buy blindly because it's cheaper: wait for it to stabilise and find the cause.",
          sym, m, s: scoreMove(ch24, vr, mcap, 10) + (isHot ? 6 : 0), opp: 2, risk: mcap < 3e8 ? "muy_alto" : "alto", url});
      } else if (ch1 != null && Math.abs(ch1) >= 4 && mcap >= 3e8) {
        const up = ch1 > 0;
        out.push({id: `m1:${c.id}:${day}:${up ? "u" : "d"}${bucket(ch1, [4, 8, 12, 20])}`, cat: "cripto", kind: "move", src: "CoinGecko", local: 1,
          title: `${name} (${sym}) ${up ? "se dispara" : "se desploma"} un ${nf(Math.abs(ch1), 1)} % en la última hora`,
          es: `${name} (${sym}) ${up ? "se dispara" : "se desploma"} un ${nf(Math.abs(ch1), 1)} % en la última hora`, en: `${name} (${sym}) ${up ? "spikes" : "drops"} ${Math.abs(ch1).toFixed(1)}% in the last hour`,
          why: "Movimiento brusco en muy poco tiempo: suele haber una noticia o una orden grande detrás.", why_en: "Sharp move in a short time: usually news or a large order behind it.",
          act: "Mira Noticias y Redes para ver la causa. No entres solo por el impulso.", act_en: "Check News and Social for the cause. Don't chase momentum alone.",
          sym, m, s: scoreMove(ch1 * 2.2, vr, mcap, 10) + (isHot ? 5 : 0), opp: 2, risk: "alto", url});
      }
    }
    return out;
  }
  function cgTrending(data, day) {
    const out = [], ids = [];
    arr(data.coins).slice(0, 15).forEach((c, i) => {
      const it = c.item || {}, sym = String(it.symbol || "").toUpperCase(), name = it.name || "";
      if (!it.id || !plainCoin(sym, name)) return;
      ids.push(it.id);
      const rank = it.market_cap_rank;
      if ((rank || 999) <= 10) return;
      const ch = ((it.data || {}).price_change_percentage_24h || {}).usd;
      let s = 40 + Math.max(0, 15 - i) * 1.4 + (ch != null && Math.abs(ch) >= 10 ? 8 : 0) + (rank && rank <= 100 ? 4 : 0) - (!rank || rank > 600 ? 6 : 0);
      out.push({id: `tr:cg:${it.id}:${day}`, cat: "cripto", kind: "trend", src: "CoinGecko", local: 1,
        title: `${name} (${sym}) entre las más buscadas en CoinGecko (#${i + 1})`, es: `${name} (${sym}) entre las más buscadas en CoinGecko (#${i + 1})`,
        en: `${name} (${sym}) trending on CoinGecko searches (#${i + 1})`,
        why: "Mucha gente la está buscando ahora" + (ch != null ? `; ${pct(ch)} en 24 h.` : "."), why_en: "Lots of people are searching for it right now" + (ch != null ? `; ${pct(ch)} in 24h.` : "."),
        act: "El interés en búsquedas suele acompañar a movimientos fuertes. Compara con el precio antes de actuar.", act_en: "Search interest often comes with strong moves. Compare with price action first.",
        sym, m: {rank, ch24h: ch}, s: Math.round(s), opp: i < 3 ? 2 : 1, risk: !rank || rank > 300 ? "muy_alto" : "alto", url: `https://www.coingecko.com/${LANG === "en" ? "en/coins" : "es/monedas"}/${it.id}`});
    });
    LIVE.trending = ids;
    return out;
  }
  const DERIV = /perpetual|futures|options|margin|usd[sⓢ]-m|coin-margined|leverage|contract|pre-market|premarket|tradfi/i;
  function binanceAnns(d) {
    const out = [];
    for (const a of arr((d.data || {}).catalogs).flatMap((c) => arr(c.articles))) {
      const title = a.title || "", rel = a.releaseDate ? new Date(a.releaseDate) : null;
      if (!a.code || (rel && Date.now() - rel > 4 * 86400e3)) continue;
      const t = title.toLowerCase();
      if (DERIV.test(t) || t.includes("bstocks") || t.includes("tokenized") || /delist|remove|cease/.test(t)) continue;
      const sym = (title.match(/\(([A-Z0-9]{2,12})\)/) || [])[1];
      const asset = (title.match(/(?:will list|to list|lists|will add|adds|introducing|launch(?:es)?)\s+(.+?)(?:\s+\(|\s+with|\s+on\b|\s+for\b|[!,.]|$)/i) || [])[1];
      const pool = /launchpool|hodler airdrop|megadrop|airdrop/.test(t);
      const listing = /will list|to list|lists|listing|will add|adds/.test(t);
      if (!pool && !listing) continue;
      out.push({id: `an:binance:${sym || a.id || a.code}`, cat: "lanzamientos", also: ["cripto"], kind: pool ? "launch" : "listing", src: "Binance", local: 1,
        title, es: pool ? `Binance: ${t.includes("launchpool") ? "Launchpool" : "airdrop"} de ${asset || L("un nuevo token", "a new token")}` : (asset ? `Binance listará ${asset}` : `Binance: ${title}`), en: title,
        why: "Anuncio oficial del exchange.", why_en: "Official exchange announcement.",
        act: pool ? "Si ya tienes los activos requeridos en el exchange, participar no cuesta más que bloquearlos; revisa fechas y condiciones." : "Los anuncios de listado suelen mover el precio antes de que empiece a cotizar; no persigas subidas verticales.",
        act_en: "Read the official announcement for dates and conditions; expect volatility.",
        sym, s: pool ? 86 : 82, opp: 3, risk: "alto", tags: [pool ? "launchpool" : "listado"], url: `https://www.binance.com/${LANG === "en" ? "en" : "es"}/support/announcement/${a.code}`,
        pub: rel ? rel.toISOString() : undefined});
    }
    return out;
  }
  function liveAdd(list) {
    const now = new Date().toISOString(), srv = new Set(arr(S.feed?.items).map((x) => x.id));
    const byId = new Map(LIVE.items.map((x) => [x.id, x]));
    let added = 0;
    for (const it of list) {
      if (srv.has(it.id)) continue;
      const cur = byId.get(it.id);
      if (cur) { cur.m = it.m; cur.s = Math.max(cur.s, it.s); cur.es = it.es; cur.en = it.en; continue; }
      it.t = now; it.w = it.pub && it.pub < now ? it.pub : now;
      byId.set(it.id, it); S.fresh.add(it.id); added++;
    }
    LIVE.items = [...byId.values()].filter((x) => Date.now() - (toDate(x.t) || 0) < 12 * 3600e3).slice(-200);
    LS.set("radar-live-items", LIVE.items);
    invalidate();
    return added;
  }
  async function localPulse() {
    if (document.hidden) return;
    const now = Date.now(), day = dayKey(new Date()), out = [];
    const get = async (url) => { const r = await fetch(url, {cache: "no-store"}); if (!r.ok) throw new Error(r.status); return r.json(); };
    try {
      if (now - LIVE.trAt > 290e3) { LIVE.trAt = now; out.push(...cgTrending(await get("https://api.coingecko.com/api/v3/search/trending"), day)); }
    } catch {}
    try {
      if (now - LIVE.cgAt > 170e3) {
        LIVE.cgAt = now;
        const data = await get("https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=150&page=1&price_change_percentage=1h,24h,7d");
        out.push(...cgMoves(data, day));
        for (const [id, sym] of [["bitcoin", "BTC"], ["ethereum", "ETH"], ["solana", "SOL"]]) {
          const c = data.find((x) => x.id === id);
          if (c) liveTicker[sym] = {p: c.current_price, ch: c.price_change_percentage_24h_in_currency ?? c.price_change_percentage_24h, cur: "USD"};
        }
      }
    } catch {}
    try {
      if (now - LIVE.bnAt > 110e3) { LIVE.bnAt = now; out.push(...binanceAnns(await get("https://www.binance.com/bapi/composite/v1/public/cms/article/list/query?type=1&catalogId=48&pageNo=1&pageSize=10"))); }
    } catch {}
    LIVE.at = new Date().toISOString();
    const n = liveAdd(out);
    renderLive(); renderTicker();
    if (n) { renderTabbar(); if (window.scrollY < 160 && !$("#sheet").classList.contains("open")) render(); else showNewPill(n); }
  }

  // pedir un pulso nuevo al motor si el feed está viejo (solo con token de GitHub con permiso de Actions)
  async function nudgeServer() {
    if (!gh.ready() || document.hidden) return;
    const age = Date.now() - (toDate(S.feed?.generatedAt) || 0);
    if (age < 8 * 60e3 || Date.now() - LS.get("radar-nudge-at", 0) < 6 * 60e3) return;
    LS.set("radar-nudge-at", Date.now());
    try {
      const c = gh.cfg();
      const r = await fetch(`https://api.github.com/repos/${c.owner}/${c.repo}/actions/workflows/pulse.yml/dispatches`,
        {method: "POST", headers: {Authorization: `Bearer ${c.token}`, Accept: "application/vnd.github+json"}, body: JSON.stringify({ref: "main"})});
      LS.set("radar-nudge-ok", r.status === 204);
    } catch { LS.set("radar-nudge-ok", false); }
  }

  async function ghDispatch(wf, inputs = {}) {
    if (!gh.ready()) return false;
    try {
      const c = gh.cfg();
      const r = await fetch(`https://api.github.com/repos/${c.owner}/${c.repo}/actions/workflows/${wf}/dispatches`,
        {method: "POST", headers: {Authorization: `Bearer ${c.token}`, Accept: "application/vnd.github+json"}, body: JSON.stringify({ref: "main", inputs})});
      return r.status === 204;
    } catch { return false; }
  }
  const runBrief = () => ghDispatch("brief.yml");
  async function ghPutFile(path, text, message) {
    if (!gh.ready()) return false;
    const c = gh.cfg();
    const api = `https://api.github.com/repos/${c.owner}/${c.repo}/contents/${path}`;
    const h = {Authorization: `Bearer ${c.token}`, Accept: "application/vnd.github+json"};
    try {
      const cur = await fetch(api + "?ref=main", {headers: h, cache: "no-store"});
      const sha = cur.ok ? (await cur.json()).sha : undefined;
      const bytes = new TextEncoder().encode(text);
      let bin = "";
      for (let i = 0; i < bytes.length; i += 4096) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 4096));
      const r = await fetch(api, {method: "PUT", headers: h, body: JSON.stringify({message, content: btoa(bin), sha, branch: "main"})});
      return r.ok;
    } catch { return false; }
  }

  // ------------------------------------------------------------------ cabecera
  function renderLive() {
    const el = $("#live"), tx = $("#liveTxt");
    const at = toDate(S.feed?.generatedAt);
    el.classList.remove("ok", "slow", "off");
    if (!at) { el.classList.add("off"); tx.textContent = S.loaded ? L("Esperando el primer pulso", "Waiting for the first pulse") : L("Conectando…", "Connecting…"); return; }
    const mins = (Date.now() - at) / 60000;
    const local = toDate(LIVE.at), localFresh = local && Date.now() - local < 3 * 60e3;
    el.classList.add(mins < 16 || localFresh ? "ok" : mins < 60 ? "slow" : "off");
    tx.textContent = localFresh && mins >= 6
      ? L(`En vivo · comprobado ${ago(local.toISOString())}`, `Live · checked ${ago(local.toISOString())}`)
      : (mins < 16 ? L("En vivo · ", "Live · ") : L("Último pulso ", "Last pulse ")) + ago(at.toISOString());
  }
  const nfg = (n, d) => { try { return new Intl.NumberFormat(LOC(), {maximumFractionDigits: d, useGrouping: "always"}).format(+n); } catch { return nf(n, d); } };
  const usdShort = (n) => {
    if (n == null || isNaN(+n)) return "—";
    const v = +n, a = Math.abs(v), d = a >= 1000 ? 0 : a >= 100 ? 1 : 2;
    return LANG === "en" ? "$" + nfg(v, d) : nfg(v, d) + " $";
  };
  function renderTicker() {
    const tk = {...(S.feed?.ticker || {}), ...liveTicker};
    if (!tk.SPX && tk.SPY) tk.SPX = {...tk.SPY, etf: "SPY"};
    if (!tk.IXIC && tk.QQQ) tk.IXIC = {...tk.QQQ, etf: "QQQ"};
    const rows = [["BTC", "BTC", "usd"], ["ETH", "ETH", "usd"], ["SOL", "SOL", "usd"], ["SPX", "S&P 500", "idx"], ["IXIC", "Nasdaq", "idx"],
      ["GOLD", L("Oro", "Gold"), "usd"], ["SILVER", L("Plata", "Silver"), "usd"], ["BRENT", "Brent", "usd"], ["US10Y", "US10Y", "yield"]];
    const parts = [];
    for (const [k, name, kind] of rows) {
      const x = tk[k]; if (!x || x.p == null) continue;
      let val, chg;
      if (kind === "yield") {
        val = nf(x.p, 2) + (LANG === "en" ? "%" : " %");
        const bp = x.chg != null ? Math.round(+x.chg * 100) : null;
        chg = bp == null ? "" : `<span class="${bp >= 0 ? "up" : "dn"}">${bp > 0 ? "+" : ""}${bp} ${L("pb", "bp")}</span>`;
      } else {
        val = kind === "idx" ? (x.etf ? usdShort(x.p) : nfg(x.p, 0)) : usdShort(x.p);
        chg = x.ch == null ? "" : `<span class="${+x.ch >= 0 ? "up" : "dn"}">${esc(pct(x.ch, 1))}</span>`;
      }
      parts.push(`<span class="tk"><b>${esc(name)}${x.etf ? ` (${esc(x.etf)})` : ""}</b>${esc(val)} ${chg}</span>`);
    }
    if (tk.FNG) parts.push(`<span class="tk"><b>${L("Miedo/codicia", "Fear/greed")}</b><span class="${tk.FNG.v <= 25 ? "dn" : tk.FNG.v >= 75 ? "up" : ""}">${esc(tk.FNG.v)}</span></span>`);
    $("#ticker").innerHTML = parts.join("") || `<span class="tk">${L("Cotizaciones en camino…", "Prices on the way…")}</span>`;
  }
  function tabItems(id) {
    const all = items();
    if (id === "vivo") return all;
    if (id === "top") return all.filter((x) => (x.s ?? 0) >= 72 && (x.opp ?? 1) >= 2);
    if (id === "noticias") return all.filter((x) => x.kind === "news");
    if (id === "redes") return all.filter((x) => x.kind === "social" || x.kind === "trend");
    if (id === "ideas" || id === "parati" || id === "casa") return [];
    return all.filter((x) => inCat(x, id));
  }
  function newCount(id) {
    if (id === "parati") return S.brief?.generatedAt && S.brief.generatedAt > LS.get("radar-brief-seen", "") ? 1 : 0;
    if (id === "casa") {  // ideas y novedades que han llegado desde la última visita
      const cur = curProfile(), since = S.lastSeen.casa;
      if (!cur?.profile?.casa) return 0;
      if (!since) return arr(cur.casa?.ideas).filter((i) => i.nueva).length;
      return arr(cur.casa?.ideas).filter((i) => (i.fecha || "") > since).length + casaFeed(cur.profile.id).filter((x) => (x.t || "") > since).length;
    }
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
    if (!TAB_IDS.includes(tab)) tab = "parati";
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
  function feedBlock(list, emptyMsg, showAll = false) {
    const shown = (S.useful && !showAll ? list.filter(useful) : list.filter((x) => !x.h)).sort(byWhen);
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
      case "parati": html = viewForYou(); break;
      case "casa": html = viewHome(); break;
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

  // ---------- Para ti (lo elige Claude para cada perfil)
  const BRIEF_SECS = [
    ["startups", "🚀", "var(--c-startups)", () => L("Invertir en una startup", "Invest in a startup")],
    ["clonar", "🧬", "var(--c-ideas)", (p) => L(`Clonar en ${p?.name || "tu país"}`, `Clone in ${p?.name === "Egipto" ? "Egypt" : p?.name === "España" ? "Spain" : p?.name || "your country"}`)],
    ["accion", "📈", "var(--c-bolsa)", () => L("Acción del día", "Stock of the day")],
    ["ayudas", "🏛️", "var(--c-negocio)", () => L("Ayudas para ti", "Grants for you")],
    ["extra", "⚡", "var(--c-vivo)", () => L("Además", "Also worth a look")],
  ];
  const modelName = (p) => {
    if (!p?.model) return "";
    if (p.provider === "anthropic") return String(p.model).replace(/^claude-/, "Claude ").replace(/-(\d+)-(\d+)$/, " $1.$2").replace(/(^|\s)([a-z])/g, (m, a, b) => a + b.toUpperCase());
    const n = {gemini: "Gemini", groq: "Groq", openrouter: "OpenRouter"}[p.provider] || p.provider;
    return L(`${n} (gratis)`, `${n} (free)`);
  };
  const prettyKey = (k) => { const t = String(k).replace(/_/g, " ").trim(); return t.charAt(0).toUpperCase() + t.slice(1); };
  function pickCard(p, color) {
    const facts = [[L("Cuánto hace falta", "What it takes"), p.coste], [L("Plazo", "Deadline"), p.plazo],
      [L("Confianza", "Confidence"), p.confianza ? `<span class="conf-${esc(p.confianza)}">${esc({alta: L("alta", "high"), media: L("media", "medium"), baja: L("baja", "low")}[p.confianza] || p.confianza)}</span>` : ""]]
      .filter((f) => f[1]);
    const datos = Object.entries(p.datos || {});
    const link = safeUrl(p.enlace);
    const srcs = arr(p.fuentes).map(safeUrl).filter(Boolean).filter((u) => u !== link);
    const more = datos.length || arr(p.riesgos).length || p.potencial || srcs.length;
    return `<article class="pick" style="--pc:${color}">
      <h3>${esc(p.titulo)}</h3>
      ${p.resumen ? `<p>${esc(p.resumen)}</p>` : ""}
      ${p.por_que ? `<p class="pwhy"><b>${L("Por qué para ti", "Why for you")}:</b> ${esc(p.por_que)}</p>` : ""}
      ${facts.length ? `<ul class="facts">${facts.map(([k, v]) => `<li>${esc(k)}<b>${k === L("Confianza", "Confidence") ? v : esc(v)}</b></li>`).join("")}</ul>` : ""}
      ${arr(p.pasos).length ? `<ol>${p.pasos.map((x) => `<li>${esc(x)}</li>`).join("")}</ol>` : ""}
      ${more ? `<details><summary>${L("Datos, riesgos y fuentes", "Data, risks and sources")}</summary>
        ${p.potencial ? `<p><b>${L("Potencial", "Upside")}:</b> ${esc(p.potencial)}</p>` : ""}
        ${datos.length ? `<dl class="kv">${datos.map(([k, v]) => `<dt>${esc(prettyKey(k))}</dt><dd>${esc(v)}</dd>`).join("")}</dl>` : ""}
        ${arr(p.riesgos).length ? `<p><b>${L("Riesgos", "Risks")}:</b></p><ul class="risks">${p.riesgos.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
        ${srcs.length ? `<p class="src">${srcs.map((u) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(u.replace(/^https?:\/\/(www\.)?/, "").slice(0, 60))}</a>`).join("<br>")}</p>` : ""}
      </details>` : ""}
      ${link ? `<a class="btn go" href="${esc(link)}" target="_blank" rel="noopener">${L("Abrir", "Open")} ↗</a>` : ""}
    </article>`;
  }
  const allProfiles = () => {  // en el orden de data/profiles.json
    const order = arr(S.profiles?.profiles).map((p) => p.id);
    const pos = (id) => (order.includes(id) ? order.indexOf(id) : 99);
    return Object.values(S.brief?.profiles || {}).filter((p) => p?.profile && (!order.length || order.includes(p.profile.id)))
      .sort((a, b) => pos(a.profile.id) - pos(b.profile.id));
  };
  function curProfile() {
    const profs = allProfiles();
    return profs.find((p) => p.profile.id === S.prof) || profs[0] || null;
  }
  const profLabel = (p) => `${p.emoji || p.flag || ""} ${p.name}`.trim();
  function profSwitch(profs, cur) {
    return `<div class="tools">${profs.length > 1 ? chips(profs.map((p) => [p.profile.id, profLabel(p.profile)]), cur.profile.id, "data-prof") : ""}
      <button class="linkbtn" type="button" data-pedit="${esc(cur.profile.id)}">${L("Personalizar", "Personalise")}</button></div>`;
  }
  function viewForYou() {
    const profs = allProfiles();
    if (!profs.length) {
      return `<div class="empty">${L("Claude está preparando tu primer informe: startups en las que entrar con poco dinero, negocios que funcionan fuera para clonar, la acción infravalorada que rompe al alza y ayudas que puedes pedir. Llega en unos minutos.", "Claude is preparing your first brief: startups you can back with little money, businesses that work abroad and can be cloned, the undervalued stock breaking out and grants you can apply for. It will be here in a few minutes.")}
        ${gh.ready() ? `<br><br><button class="btn" type="button" data-brief-run="1">${L("Pedirlo ahora", "Request it now")}</button>` : ""}</div>`;
    }
    const cur = curProfile();
    LS.set("radar-brief-seen", S.brief.generatedAt || "");
    const sw = profSwitch(profs, cur);
    const secs = cur.secciones || {};
    if (!cur.secciones) {
      return `${sw}${liveMore(cur)}<div class="empty">${cur.profile.casa ? L("Este perfil se centra en «Desde casa»: ahí tienes tus ideas y las ayudas para emprender.", "This profile focuses on “From home”: your ideas and grants are there.") + `<br><br><button class="btn" type="button" data-tab="casa">🏡 ${L("Ir a Desde casa", "Go to From home")}</button>` : L("Aún no hay informe para este perfil. Llega con el próximo análisis.", "No brief for this profile yet. It arrives with the next analysis.")}</div>`;
    }
    const body = BRIEF_SECS.map(([k, e, color, title]) => {
      if (!secs[k]) return "";  // sección que este perfil no ha pedido
      const sec = secs[k];
      if (k === "ayudas" && !arr(sec.picks).length && (cur.profile.country || "") !== "ES") return "";
      const picks = arr(sec.picks);
      return `<div class="section-h"><h2>${e} ${esc(title(cur.profile))}</h2><span>${picks.length || ""}</span></div>
        ${picks.length ? picks.map((p) => pickCard(p, color)).join("") : `<p class="note">${esc(sec.nota || L("Hoy nada que merezca la pena.", "Nothing worth it today."))}</p>`}`;
    }).join("");
    const free = cur.provider && cur.provider !== "anthropic";
    const meta = [L("Actualizado ", "Updated ") + ago(cur.generatedAt), modelName(cur) && L("analizado por ", "analysed by ") + modelName(cur)].filter(Boolean).join(" · ");
    const saved = Object.values(S.saved).sort(byWhen);
    return `${sw}
      ${cur.resumen ? `<p class="brief-sum">${esc(cur.resumen)}</p>` : ""}
      <p class="brief-meta">${esc(meta)}${gh.ready() ? ` · <button class="linkbtn" type="button" data-brief-run="1">${L("actualizar", "refresh")}</button>` : ""}</p>
      ${free ? `<p class="note">${L("Ahora decide un modelo gratuito porque falta la clave de Claude (o se llegó al tope de gasto de hoy). Con la clave, decide Claude y comprueba en la web.", "A free model is deciding because the Claude key is missing (or today's spending cap was reached). With the key, Claude decides and checks the web.")}</p>` : ""}
      ${body}
      ${liveMore(cur)}
      ${cur.descartado ? `<p class="note">🧹 ${esc(cur.descartado)}</p>` : ""}
      <p class="disclaimer">${L("No es asesoramiento financiero. Nada se compra ni se vende solo: Claude analiza y tú decides. Invierte solo lo que puedas perder.", "Not financial advice. Nothing is bought or sold automatically: Claude analyses and you decide. Only invest what you can afford to lose.")}</p>
      ${saved.length ? `<div class="section-h"><h2>🔖 ${L("Guardadas", "Saved")}</h2><span>${saved.length}</span></div><div class="rows">${saved.map(row).join("")}</div>` : ""}`;
  }

  // ---------- Desde casa: ideas desarrolladas por Claude y novedades al momento para cada perfil
  const bullets = (title, a) => (arr(a).length ? `<p class="lbl">${esc(title)}</p><ul class="risks">${a.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "");
  // palabras con las que se reconoce cada interés cuando la idea o la noticia no trae su tema
  const TEMA_WORDS = {inmobiliaria: "inmobil|vivienda|pisos?\\b|alquiler|staging|real estate|propert|realtor|airbnb", arte: "arte\\b|art\\b|artist|pintur|acuarel|laminas?\\b|ilustr|cuadros?\\b|painting|ceramic",
    diseno: "diseno|design|grafic|branding|logos?\\b|plantilla|template|canva|printable|imprimible", ninos: "ninos?\\b|infantil|kids?\\b|child|bebes?\\b|baby|toddler|crianza|escolar|juguete|toys?\\b",
    cocina: "cocina|receta|recipe|menus?\\b|comida|tartas?\\b|reposter|baker|bakes?\\b|baking|cook|food|meal|chef|pasteler|catering|obrador|galletas|cookies|kitchen"};
  const temaRe = {};
  // ideas: manda el tema que puso Claude; novedades: mandan las palabras del titular (la IA barata tiende a poner el primer interés)
  function temasOf(x, ints, wordsFirst = false) {
    const given = [...arr(x.temas), x.tema].filter(Boolean).map(_fold);
    const hit = ints.filter((i) => given.includes(_fold(i)));
    const text = _fold([x.titulo, x.gancho, x.es, x.title].filter(Boolean).join(" "));
    const words = () => ints.filter((i) => {
      const k = _fold(i);
      temaRe[k] = temaRe[k] || new RegExp(`(^|[^a-z])(${TEMA_WORDS[k] || k.replace(/[^a-z0-9 ]/g, "")})`);
      return temaRe[k].test(text);
    });
    if (wordsFirst) { const w = words(); return w.length ? w : hit; }
    return hit.length || given.includes("otros") ? hit : words();
  }
  const interestsOf = (cur) => arr(cur?.profile?.interests).length ? arr(cur.profile.interests) : arr(arr(S.profiles?.profiles).find((x) => x.id === cur?.profile?.id)?.interests);
  const casaFeed = (pid) => arr(S.feed?.items).filter((x) => x.cat === "casa" && !x.h && arr(x.pf).includes(pid)).sort(byWhen);
  const capWord = (w) => String(w).charAt(0).toUpperCase() + String(w).slice(1);
  function novRow(it) {
    const isNew = S.visitFrom.casa && (it.t || "") > S.visitFrom.casa;
    const u = safeUrl(it.url);
    const tm = temasOf(it, interestsOf(curProfile()), true).map(capWord).join(", ");
    const meta = [it.src, it.kind === "local" ? L("En tu zona", "Near you") : L("Historia real", "Real story"), tm].filter(Boolean);
    return `<a class="row nov${S.fresh.has(it.id) ? " fresh" : ""}" href="${esc(u || "#")}" target="_blank" rel="noopener noreferrer" style="--cc:var(--c-casa)">
      <span class="when">${whenCol(when(it))}</span>
      <span class="body"><span class="ttl">${esc(txt(it))}</span>${why(it) ? `<span class="why">${esc(why(it))}</span>` : ""}
        <span class="meta">${meta.map((m, i) => `<span${i === 0 ? ' class="src"' : ""}>${esc(m)}</span>`).join("")}</span></span>
      ${isNew ? `<span class="dot-new" title="${L("Nueva", "New")}"></span>` : ""}</a>`;
  }
  function homeIdea(it, c, open) {
    const grants = Object.fromEntries(arr(c.ayudas).map((g) => [g.id, g]));
    const facts = [[L("Para empezar", "To start"), it.coste_inicial], [L("Horas a la semana", "Hours a week"), it.horas_semana],
      [L("Qué cobrar", "What to charge"), it.precio], [L("Ingresos posibles", "Possible income"), it.ingresos_posibles]].filter((f) => f[1]);
    const cases = arr(it.casos).filter((k) => safeUrl(k.url));
    const gl = arr(it.ayudas).map((id) => grants[id]).filter(Boolean);
    const isNew = S.visitFrom.casa ? (it.fecha || "") > S.visitFrom.casa : it.nueva;
    return `<article class="pick home" style="--pc:var(--c-casa)"><details class="idea"${open ? " open" : ""}>
      <summary>${isNew ? `<span class="tag new">${L("Nueva", "New")}</span>` : ""}
        <h3>${esc(it.titulo)}</h3>
        ${it.gancho ? `<p class="hook">${esc(it.gancho)}</p>` : ""}
        <span class="idea-more">${L("Ver la idea completa", "See the full idea")}</span></summary>
      ${it.que_es ? `<p>${esc(it.que_es)}</p>` : ""}
      ${cases.length ? `<div class="cases"><p class="lbl">${L("Ya funciona en", "Already working in")}</p>${cases.map((k) => `<a href="${esc(k.url)}" target="_blank" rel="noopener">
        <b>${esc([k.pais, k.quien].filter(Boolean).join(", "))}</b>${k.resultado ? `<span>${esc((LANG === "es" && k.resultado_es) || k.resultado)}</span>` : ""}</a>`).join("")}</div>` : ""}
      ${it.por_que_tu ? `<p class="pwhy"><b>${L("Por qué tú", "Why you")}:</b> ${esc(it.por_que_tu)}</p>` : ""}
      ${facts.length ? `<ul class="facts">${facts.map(([k, v]) => `<li>${esc(k)}<b>${esc(v)}</b></li>`).join("")}</ul>` : ""}
      ${arr(it.como_empezar).length ? `<p class="lbl">${L("Cómo empezar", "How to start")}</p><ol>${it.como_empezar.map((x) => `<li>${esc(x)}</li>`).join("")}</ol>` : ""}
      <details><summary>${L("Herramientas, primeras clientas, trámites y riesgos", "Tools, first customers, paperwork and risks")}</summary>
        ${bullets(L("Herramientas", "Tools"), it.herramientas)}
        ${bullets(L("Primeras clientas", "First customers"), it.primeras_clientas)}
        ${bullets(L("Trámites", "Paperwork"), it.tramites)}
        ${gl.length ? `<p class="lbl">${L("Ayudas que encajan", "Matching grants")}</p><ul class="risks">${gl.map((g) => `<li><a href="${esc(safeUrl(g.url) || "#")}" target="_blank" rel="noopener">${esc(g.titulo)}</a></li>`).join("")}</ul>` : ""}
        ${bullets(L("Riesgos", "Risks"), it.riesgos)}
        ${it.confianza ? `<p><b>${L("Confianza", "Confidence")}:</b> <span class="conf-${esc(it.confianza)}">${esc({alta: L("alta", "high"), media: L("media", "medium"), baja: L("baja", "low")}[it.confianza] || it.confianza)}</span></p>` : ""}
      </details>
      <p class="fine">${esc([it.fecha && L("Propuesta ", "Suggested ") + ago(it.fecha), arr(it.temas).map(capWord).join(", ")].filter(Boolean).join(" · "))}</p>
    </details></article>`;
  }
  function viewHome() {
    const profs = allProfiles();
    const cur = curProfile();
    if (!cur) return `<div class="empty">${L("Claude está preparando las primeras ideas. Llegan en unos minutos.", "Claude is preparing the first ideas. They'll be here in a few minutes.")}</div>`;
    const sw = profSwitch(profs, cur);
    const id = cur.profile.id;
    if (!cur.profile.casa) {
      return `${sw}<div class="empty">${L("«Desde casa» no está activado en este perfil. Actívalo en Personalizar y Claude buscará negocios pequeños que ya funcionan en otros países, adaptados a lo que sabes hacer.", "“From home” is off for this profile. Turn it on in Personalise and Claude will look for small businesses that already work in other countries, adapted to your skills.")}
        <br><br><button class="btn" type="button" data-pedit="${esc(id)}">${L("Personalizar perfil", "Personalise profile")}</button></div>`;
    }
    const c = cur.casa || {};
    const ints = interestsOf(cur);
    const since = S.visitFrom.casa;
    const ideas = arr(c.ideas).map((it) => ({it, t: temasOf(it, ints)}));
    const novs = casaFeed(id).map((it) => ({it, t: temasOf(it, ints, true)}));
    const grants = arr(c.ayudas);
    const local = arr(c.oportunidades_locales).filter((o) => safeUrl(o.url));
    const nearNovs = novs.filter((o) => o.it.kind === "local");
    const seg = ["ideas", "nov", "zona"].includes(S.seg.casa) ? S.seg.casa : "ideas";
    const newIdeas = ideas.filter((o) => (since ? (o.it.fecha || "") > since : o.it.nueva)).length;
    const newNovs = since ? novs.filter((o) => (o.it.t || "") > since).length : 0;
    const tag = (n, fresh) => (fresh ? `${n} · ${fresh} ${L(fresh === 1 ? "nueva" : "nuevas", "new")}` : n);
    const segs = chips([["ideas", `💡 ${L("Ideas", "Ideas")}`, tag(ideas.length, newIdeas)], ["nov", `⚡ ${L("Al momento", "Live")}`, tag(novs.length, newNovs)],
      ["zona", `📍 ${L("Tu zona y ayudas", "Near you & grants")}`, local.length + nearNovs.length + grants.length]], seg, "data-seg");
    const tema = S.casaTema || "all";
    const pool = seg === "ideas" ? ideas : novs;
    const match = (o, k) => k === "all" || (k === "otros" ? !o.t.length : o.t.some((x) => _fold(x) === _fold(k)));
    const temaChips = ints.length && pool.length ? chips([["all", L("Todos los temas", "All topics"), pool.length],
      ...ints.map((i) => [i, capWord(i), pool.filter((o) => match(o, i)).length]).filter((x) => x[2]),
      ...(pool.some((o) => !o.t.length) ? [["otros", L("Otros", "Other"), pool.filter((o) => !o.t.length).length]] : [])], tema, "data-ctema") : "";
    const meta = [c.generatedAt && L("Ideas: ", "Ideas: ") + ago(c.generatedAt), modelName(c) && L("desarrolladas por ", "developed by ") + modelName(c),
      L("3 nuevas cada 3 horas", "3 new every 3 hours"), S.feed?.generatedAt && L("novedades: ", "news: ") + ago(S.feed.generatedAt)].filter(Boolean).join(" · ");
    let body = "";
    if (seg === "ideas") {
      const shown = ideas.filter((o) => match(o, tema));
      const openN = Math.max(1, Math.min(3, shown.filter((o) => (since ? (o.it.fecha || "") > since : o.it.nueva)).length));
      body = shown.length ? shown.map((o, i) => homeIdea(o.it, c, i < openN)).join("")
        : `<p class="note">${esc(c.error && !ideas.length ? L("No se han podido preparar ideas esta vez; se reintenta en la próxima tanda.", "Ideas couldn't be prepared this time; it will retry with the next batch.")
          : ideas.length ? L("Aún no hay ideas de este tema. Llegan 3 nuevas cada 3 horas.", "No ideas on this topic yet. 3 new ones arrive every 3 hours.") : L("Claude está buscando las primeras ideas para ti. Llegan en la próxima tanda.", "Claude is looking for your first ideas. They arrive with the next batch."))}</p>`;
    } else if (seg === "nov") {
      const shown = novs.filter((o) => match(o, tema)).map((o) => o.it);
      body = `<p class="note">${L("Historias reales de gente que gana dinero desde casa y oportunidades en tu zona, de todo el mundo. El radar las busca cada 15 minutos y una IA las traduce y quita lo que no sirve. Toca para abrir la noticia.", "Real stories of people earning from home and opportunities near you, from around the world. The radar looks every 15 minutes and an AI translates them and drops what isn't useful. Tap to open the story.")}</p>
        ${shown.length ? grouped(shown, novRow) : `<div class="empty">${L("Todavía no hay novedades: el radar las está buscando. Vuelve en un rato.", "No news yet: the radar is looking. Check back soon.")}</div>`}`;
    } else {
      const where = cur.profile.municipality ? L(` en ${cur.profile.municipality} y alrededores`, ` around ${cur.profile.municipality}`) : "";
      body = `${nearNovs.length ? `<div class="section-h"><h2>📰 ${L("Novedades en tu zona", "News near you")}</h2><span>${nearNovs.length}</span></div><div class="rows">${nearNovs.slice(0, 12).map((o) => novRow(o.it)).join("")}</div>` : ""}
        ${local.length ? `<div class="section-h"><h2>📍 ${L("Programas y recursos", "Programmes and resources")}</h2><span>${local.length}</span></div>
          <div class="pick plain">${local.map((o) => `<p><a href="${esc(o.url)}" target="_blank" rel="noopener"><b>${esc(o.titulo)}</b></a>${o.que_es ? `<br>${esc(o.que_es)}` : ""}</p>`).join("")}</div>` : ""}
        ${grants.length ? `<div class="section-h"><h2>🏛️ ${L("Ayudas para emprender", "Grants to start up")}${esc(where)}</h2><span>${grants.length}</span></div>
          <div class="pick plain">${grants.map((g) => `<p><a href="${esc(safeUrl(g.url) || "#")}" target="_blank" rel="noopener"><b>${esc(g.titulo)}</b></a><br>
            <span class="muted">${esc([g.donde, g.solicitud?.hasta && L("hasta el ", "until ") + g.solicitud.hasta].filter(Boolean).join(" · "))}</span></p>`).join("")}</div>`
          : `<p class="note">${L("Ahora mismo no hay ayudas abiertas para emprender que encajen contigo en tu ayuntamiento, la diputación, la Generalitat ni el Estado. Se revisa cada día.", "No open start-up grants that fit you right now from your town, province, region or the State. Checked every day.")}</p>`}`;
    }
    return `${sw}
      <p class="brief-sum">${L("Negocios pequeños que ya funcionan en otros países, desarrollados para que puedas empezar desde casa con poco dinero, y novedades al momento.", "Small businesses that already work in other countries, developed so you can start from home with little money, plus live news.")}</p>
      <p class="brief-meta">${esc(meta)}${gh.ready() ? ` · <button class="linkbtn" type="button" data-casa-run="${esc(id)}">${L("pedir más ideas ahora", "more ideas now")}</button>` : ""}</p>
      ${c.provider && c.provider !== "anthropic" && seg === "ideas" ? `<p class="note">${L("Ahora las desarrolla un modelo gratuito porque falta la clave de Claude. Con ella, Claude busca más casos reales en la web.", "A free model is developing them because the Claude key is missing. With it, Claude finds more real cases on the web.")}</p>` : ""}
      <div class="tools">${segs}</div>
      ${seg !== "zona" && temaChips ? `<div class="tools">${temaChips}</div>` : ""}
      ${body}
      ${c.nota && seg === "ideas" ? `<p class="note">🔎 ${esc(c.nota)}</p>` : ""}
      <p class="disclaimer">${L("Antes de empezar, confirma los trámites (autónomos, IVA, registro sanitario si vendes comida) con tu gestoría o en la oficina de empleo y desarrollo local de tu ayuntamiento.", "Before you start, confirm the paperwork (self-employment, VAT, food-safety registration if you sell food) with an adviser or your town's local development office.")}</p>`;
  }

  // ---------- Para ti: además de lo que elige Claude, señales concretas del radar al momento que encajan con el perfil.
  // Solo hechos con algo que hacer (directivos que compran, resultados, salidas a bolsa, listados, lanzamientos y noticias
  // que la IA marca como accionables); nada de simples subidas y bajadas, y las ayudas solo las que filtra Claude.
  const SEC_CATS = {startups: ["startups"], clonar: ["negocio", "ia"], accion: ["bolsa"], extra: ["cripto", "lanzamientos", "ia", "negocio"]};
  const LIVE_KINDS = new Set(["insider", "earnings", "ipo", "listing", "launch", "defi"]);
  const RISK_OK = {bajo: ["bajo"], medio: ["bajo", "medio"], alto: ["bajo", "medio", "alto"]};
  const LIVE_NOISE = /\?|préstam|prestad|apalanc|\bloan|borrow|leverag/i;  // nada de préstamos ni apalancamiento; las preguntas suelen ser opinión
  function liveMore(cur) {
    const secs = Object.keys(cur.secciones || {});
    const cats = new Set(secs.flatMap((k) => SEC_CATS[k] || []));
    const full = arr(S.profiles?.profiles).find((x) => x.id === cur.profile.id) || {};
    const okRisk = RISK_OK[full.risk || "medio"] || RISK_OK.medio;
    const picked = new Set(Object.values(cur.secciones || {}).flatMap((sec) => arr(sec.picks)).flatMap((p) => [p.ref, safeUrl(p.enlace)]).filter(Boolean));
    const since = Date.now() - 24 * 3600e3;
    const list = !cats.size ? [] : items().filter((x) => !x.h && (toDate(x.t) || 0) > since && !picked.has(x.id) && !picked.has(safeUrl(x.url))
      && [...cats].some((c) => inCat(x, c)) && okRisk.includes(x.risk || "medio") && !LIVE_NOISE.test(`${x.title} ${txt(x)}`)
      && ((LIVE_KINDS.has(x.kind) && (x.opp ?? 1) >= 2 && (x.s ?? 0) >= 72) || (x.kind === "news" && (x.opp ?? 1) >= 3 && x.cat !== "startups" && x.cat !== "negocio")))
      .sort((a, b) => (b.s ?? 0) - (a.s ?? 0) || byWhen(a, b)).slice(0, 6);
    const home = cur.profile.casa ? casaFeed(cur.profile.id).slice(0, 5) : [];
    if (!list.length && !home.length) return "";
    return `<div class="section-h"><h2>⚡ ${L("Más oportunidades al momento", "More live opportunities")}</h2><span>${list.length + home.length}</span></div>
      <p class="note">${list.length ? L("Señales concretas del radar de las últimas 24 horas que encajan con tu perfil. Se actualizan cada pocos minutos; Claude no las ha revisado.", "Concrete radar signals from the last 24 hours that fit your profile. Updated every few minutes; not reviewed by Claude.")
        : L("Lo último de «Desde casa»: se actualiza cada pocos minutos.", "The latest from “From home”: updated every few minutes.")}</p>
      ${list.length ? `<div class="rows">${list.map(row).join("")}</div>` : ""}
      ${home.length ? `${list.length ? `<p class="lbl" style="padding:10px var(--pad) 0">🏡 ${L("Desde casa", "From home")}</p>` : ""}<div class="rows">${home.map(novRow).join("")}</div>
        <p style="padding:8px var(--pad)"><button class="linkbtn" type="button" data-tab="casa">${L("Ver todo en Desde casa", "See everything in From home")}</button></p>` : ""}`;
  }

  // ---------- editor de perfil (cada persona el suyo)
  const NUTS_ES = [["ES61", "Andalucía"], ["ES24", "Aragón"], ["ES12", "Asturias"], ["ES53", "Illes Balears"], ["ES70", "Canarias"], ["ES13", "Cantabria"],
    ["ES41", "Castilla y León"], ["ES42", "Castilla-La Mancha"], ["ES51", "Cataluña"], ["ES52", "Comunitat Valenciana"], ["ES43", "Extremadura"],
    ["ES11", "Galicia"], ["ES30", "Comunidad de Madrid"], ["ES62", "Región de Murcia"], ["ES22", "Navarra"], ["ES21", "País Vasco"], ["ES23", "La Rioja"],
    ["ES63", "Ceuta"], ["ES64", "Melilla"]];
  const SEC_NAMES = () => ({casa: L("Ideas de negocio desde casa", "Work-from-home business ideas"), startups: L("Invertir en startups con poco dinero", "Investing in startups with little money"),
    clonar: L("Negocios para clonar en tu país", "Businesses to clone in your country"), accion: L("Acción infravalorada que rompe al alza", "Undervalued stock breaking out"),
    ayudas: L("Ayudas y subvenciones", "Grants and subsidies"), extra: L("Otras oportunidades del día", "Other opportunities of the day")});
  const splitList = (v) => String(v || "").split(",").map((x) => x.trim()).filter(Boolean).slice(0, 12);
  function openProfileEditor(pid) {
    const list = arr(S.profiles?.profiles);
    const p = list.find((x) => x.id === pid) || {id: "", name: "", emoji: "🙂", language: LANG, country: "ES", sections: ["ayudas", "extra"], casa: true, start_tab: "casa"};
    const on = new Set([...arr(p.sections), ...(p.casa ? ["casa"] : [])]);
    const opt = (v, cur, label) => `<option value="${esc(v)}" ${String(cur ?? "") === String(v) ? "selected" : ""}>${esc(label)}</option>`;
    openSheet(`<div class="d-head"><h2 class="d-title">${p.id ? L("Tu perfil: ", "Your profile: ") + esc(p.name) : L("Nuevo perfil", "New profile")}</h2>
        <p class="muted">${L("Claude lo usa para elegir y desarrollar lo que te enseña. Cada persona puede tener el suyo.", "Claude uses it to choose and develop what it shows you. Everyone can have their own.")}</p></div>
      <div class="blk">
        <div class="field"><label for="pName">${L("Nombre", "Name")}</label><input id="pName" maxlength="30" value="${esc(p.name || "")}"></div>
        <div class="field"><label for="pEmoji">${L("Icono (un emoji)", "Icon (one emoji)")}</label><input id="pEmoji" maxlength="4" value="${esc(p.emoji || p.flag || "")}"></div>
        <div class="field"><label for="pLang">${L("Idioma", "Language")}</label><select id="pLang">${opt("es", p.language, "Español")}${opt("en", p.language, "English")}</select></div>
        <div class="field"><label for="pCountry">${L("País", "Country")}</label><select id="pCountry">${opt("ES", p.country, "España")}${opt("EG", p.country, "Egipto / Egypt")}${opt("", p.country, L("Otro", "Other"))}</select></div>
        <div class="field"><label for="pRegion">${L("Comunidad autónoma", "Region (Spain)")}</label><select id="pRegion">${opt("", p.region, "—")}${NUTS_ES.map(([k, n]) => opt(k, p.region, n)).join("")}</select></div>
        <div class="field"><label for="pProv">${L("Provincia", "Province")}</label><input id="pProv" value="${esc(p.province || "")}"></div>
        <div class="field"><label for="pMuni">${L("Municipio", "Town")}</label><input id="pMuni" value="${esc(p.municipality || "")}"></div>
        <div class="field"><label for="pAbout">${L("A qué te dedicas y qué sabes hacer", "What you do and what you're good at")}</label><textarea id="pAbout" rows="4">${esc(p.about || "")}</textarea></div>
        <div class="field"><label for="pInt">${L("Intereses, separados por comas", "Interests, comma-separated")}</label><input id="pInt" value="${esc(arr(p.interests).join(", "))}"></div>
        <div class="field"><label for="pCap">${L("Dinero que podrías invertir (€)", "Money you could invest (€)")}</label><input id="pCap" type="number" min="0" step="50" value="${esc(p.capital ?? "")}"></div>
        <div class="field"><label for="pHours">${L("Horas a la semana que puedes dedicar", "Hours a week you can put in")}</label><input id="pHours" type="number" min="0" max="80" value="${esc(p.hours_week ?? "")}"></div>
        <fieldset class="field checks"><legend>${L("Qué quieres que te busque Claude", "What you want Claude to look for")}</legend>
          ${Object.entries(SEC_NAMES()).map(([k, l]) => `<label class="chk"><input type="checkbox" value="${k}" ${on.has(k) ? "checked" : ""}> ${esc(l)}</label>`).join("")}</fieldset>
        <div class="field"><label for="pAvoid">${L("Lo que no quieres, separado por comas", "What you don't want, comma-separated")}</label><input id="pAvoid" value="${esc(arr(p.avoid).join(", "))}"></div>
        <div class="field"><label for="pStart">${L("Pestaña al abrir la app", "Tab when opening the app")}</label><select id="pStart">${opt("parati", p.start_tab, "Para ti")}${opt("casa", p.start_tab, "Desde casa")}${opt("vivo", p.start_tab, "En vivo")}</select></div>
        <p class="fine">${gh.ready() ? L("Al guardar, Claude prepara resultados nuevos para este perfil en unos minutos.", "When you save, Claude prepares new results for this profile in a few minutes.") : L("Para que Claude use los cambios hay que guardarlos en el radar con el token de GitHub (Ajustes → Sincronización). Sin token se quedan solo en este móvil.", "For Claude to use the changes they must be saved to the radar with the GitHub token (Settings → Sync). Without it they stay on this phone only.")}</p>
        <div class="btns"><button class="btn primary" type="button" data-psave="${esc(p.id || "")}">${L("Guardar", "Save")}</button>${p.id ? `<button class="btn" type="button" data-pedit="__new">${L("Crear otro perfil", "Create another profile")}</button>` : ""}</div>
      </div>`);
  }
  async function saveProfileForm(pid) {
    const v = (id) => ($("#" + id)?.value || "").trim();
    const doc = JSON.parse(JSON.stringify(S.profiles || {version: 1, profiles: []}));
    doc.profiles = arr(doc.profiles);
    let p = doc.profiles.find((x) => x.id === pid);
    if (!p) {
      let base = (_fold(v("pName")).replace(/[^a-z0-9]+/g, "") || "perfil").slice(0, 12), nid = base, i = 2;
      while (doc.profiles.some((x) => x.id === nid)) nid = base + i++;
      p = {id: nid, currency: "EUR", risk: "bajo"}; doc.profiles.push(p);
    }
    const checked = [...document.querySelectorAll("#sheetBody .checks input:checked")].map((x) => x.value);
    const region = v("pRegion");
    Object.assign(p, {name: v("pName") || p.name || L("Perfil", "Profile"), emoji: v("pEmoji") || p.emoji, language: v("pLang") || "es", country: v("pCountry") || null,
      region: region || null, region_name: (NUTS_ES.find(([k]) => k === region) || [])[1] || null, province: v("pProv") || null, municipality: v("pMuni") || null,
      about: v("pAbout"), interests: splitList(v("pInt")), capital: v("pCap") ? +v("pCap") : null, hours_week: v("pHours") ? +v("pHours") : null,
      sections: checked.filter((x) => x !== "casa"), casa: checked.includes("casa"), avoid: splitList(v("pAvoid")), start_tab: v("pStart") || "parati"});
    doc.updatedAt = new Date().toISOString();
    S.profiles = doc; S.prof = p.id; LS.set("radar-prof", p.id); LS.set("radar-profiles-draft", doc);
    if (!gh.ready()) { toast(L("Guardado en este móvil", "Saved on this phone")); closeSheet(); render(); return; }
    const ok = await ghPutFile("data/profiles.json", JSON.stringify(doc, null, 1) + "\n", `Perfil «${p.name}» actualizado desde la app`);
    if (ok) await ghDispatch("brief.yml", {perfil: p.id, force: "true", solo: "todo"});
    toast(ok ? L("Guardado. Claude prepara lo nuevo en unos minutos.", "Saved. Claude is preparing new results.") : L("No se pudo guardar en el radar: revisa el token.", "Couldn't save to the radar: check the token."));
    closeSheet(); render();
  }
  const _fold = (x) => String(x || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

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
    const pick = (f, empty, showAll = false) => { scope = all.filter(f); body = feedBlock(scope, empty, showAll); if (showAll) showSwitch = false; };
    switch (seg) {
      case "sig": pick((x) => SIGNAL_KINDS.has(x.kind)); break;
      case "news": pick((x) => x.kind === "news"); break;
      case "social": pick((x) => x.kind === "social" || x.kind === "trend"); break;
      case "grant":
        pick((x) => x.kind === "grant", L("Sin convocatorias nuevas de ayudas en los últimos días.", "No new grant calls in recent days."), true);
        body = `<p class="note">${L("Convocatorias oficiales de la Base de Datos Nacional de Subvenciones. Las municipales y provinciales solo sirven si tu negocio está allí.", "Official calls from Spain's national grants database. Municipal and provincial ones only apply if your business is there.")}</p>` + body;
        break;
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
    const opts = [[45, "45+"], [60, "60+"], [0, L("Todas", "All")]].map(([k, l]) => [String(k), l]);
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
    yield: L("Rentabilidad (%)", "Yield (%)"), chg: L("Cambio (puntos)", "Change (points)"), nivel: L("Administración", "Administration"), org: L("Organismo", "Body"), fecha: L("Publicada", "Published"), dollarVol: L("Negociado", "Traded"), cat: L("Categoría", "Category"),
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
      <div class="blk"><h3>${L("Perfiles de cada persona", "Each person's profile")}</h3>
        <p>${L("«Para ti» y «Desde casa» se preparan para cada perfil: dónde vive, a qué se dedica, qué le interesa y cuánto puede invertir. Elige el tuyo arriba en esas pestañas.", "“For you” and “From home” are prepared for each profile: where they live, what they do, their interests and how much they can invest. Pick yours at the top of those tabs.")}</p>
        <div class="btns"><button class="btn primary" type="button" data-pedit="${esc(curProfile()?.profile?.id || "")}">${L("Editar mi perfil", "Edit my profile")}</button><button class="btn" type="button" data-pedit="__new">${L("Crear otro perfil", "Create another profile")}</button></div></div>
      <div class="blk"><h3>${L("Análisis profundo: región y capital", "Deep analysis: region and capital")}</h3>
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
        <p class="fine" style="margin-top:0">${L("Permite que el motor en la nube use tu región, presupuesto y descartes y, si el pulso de GitHub se retrasa, que la app pida uno nuevo al abrirla. Necesita un token de GitHub de acceso detallado, solo para este repositorio, con permisos «Contents» y «Actions» de lectura y escritura.", "Lets the cloud engine use your region, budget and dismissals and, if GitHub's pulse is late, lets the app request a fresh one when opened. Needs a fine-grained GitHub token for this repository only, with read and write “Contents” and “Actions” permissions.")}</p>
        ${gh.ready() ? `<p class="fine">${LS.get("radar-nudge-ok", null) === false ? L("El token no tiene permiso de Actions: la app no puede pedir pulsos nuevos.", "The token lacks Actions permission: the app can't request new pulses.") : L("Token guardado en este móvil.", "Token saved on this phone.")}</p>` : ""}
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
    const pf = t.closest("[data-prof]"); if (pf) { S.prof = pf.dataset.prof; LS.set("radar-prof", S.prof); render(); renderTabbar(); return; }
    const pe = t.closest("[data-pedit]"); if (pe) { openProfileEditor(pe.dataset.pedit === "__new" ? "" : pe.dataset.pedit); return; }
    const ps = t.closest("[data-psave]"); if (ps) { ps.disabled = true; await saveProfileForm(ps.dataset.psave); return; }
    const cr = t.closest("[data-casa-run]"); if (cr) { cr.disabled = true; cr.textContent = await ghDispatch("brief.yml", {perfil: cr.dataset.casaRun, solo: "casa", force: "true"}) ? L("pedidas: llegan en unos minutos", "requested: a few minutes") : L("no se pudo pedir (revisa el token)", "could not request (check the token)"); return; }
    const br = t.closest("[data-brief-run]"); if (br) { br.disabled = true; br.textContent = await runBrief() ? L("Pedido: llega en unos minutos", "Requested: a few minutes") : L("No se pudo pedir (revisa el token)", "Could not request it (check the token)"); return; }
    const ct = t.closest("[data-ctema]"); if (ct) { S.casaTema = ct.dataset.ctema; LS.set("radar-casa-tema", S.casaTema); S.limit = 60; render(); return; }
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
    if (h === "seleccion" || h === "top") { go("parati", {push: false}); return; }
    if (S.opps.some((o) => o.id === h)) openOpp(h);
  }
  window.addEventListener("hashchange", () => { if (!sheet.classList.contains("open")) routeHash(); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) { pollFeed(); pollPrices(); localPulse(); nudgeServer(); } });

  // ------------------------------------------------------------------ arranque
  const h0 = decodeURIComponent(location.hash.slice(1));
  S.tab = TAB_IDS.includes(h0) ? h0 : "parati";
  S.autoTab = !h0;
  if (!Object.keys(S.lastSeen).length) S.lastSeen = {};
  S.visitFrom[S.tab] = S.lastSeen[S.tab] || null;
  render(); renderTabbar(); renderTicker();
  loadAll().then(() => {
    if (!Object.keys(S.lastSeen).length && S.feed?.generatedAt) {
      for (const t of TAB_IDS) S.lastSeen[t] = S.feed.generatedAt;
      LS.set("radar-lastseen", S.lastSeen);
    }
    seenTimer = setTimeout(() => markSeen(S.tab), 2500);
    nudgeServer();
  });
  pollPrices();
  setTimeout(localPulse, 4000);
  setInterval(pollFeed, 60000);
  setInterval(() => { pollPrices(); localPulse(); nudgeServer(); }, 60000);
  setInterval(pollSlow, 5 * 60000);
  setInterval(renderLive, 30000);
})();
