/* Opportunity Radar · Ventana «Mercados»: acciones de EE. UU. y cripto infravaloradas (data/markets.json, data/paper.json). */
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const safeUrl = (u) => { try { const x = new URL(String(u)); return /^https?:$/.test(x.protocol) ? x.href : null; } catch { return null; } };
  const nf = (n, d = 2) => (n == null || isNaN(+n)) ? "—" : new Intl.NumberFormat("es-ES", {maximumFractionDigits: d}).format(+n);
  const usd = (n) => n == null ? "—" : (+n >= 1 ? "$" + nf(n, 2) : "$" + nf(n, 6));
  const big = (n) => n == null ? "—" : +n >= 1e12 ? nf(n / 1e12, 2) + " B$" : +n >= 1e9 ? nf(n / 1e9, 1) + " mil M$" : nf(n / 1e6, 0) + " M$";
  const pct = (n, d = 1) => n == null ? "—" : nf(n, d) + " %";
  let data = null, paper = null, tab = "acciones";
  const budget = () => { try { return Math.min(2000, +(JSON.parse(localStorage.getItem("radar-profile") || "{}").budget) || 2000); } catch { return 2000; } };

  const st = document.createElement("style");
  st.textContent = `
  #mkEntry{display:flex;gap:12px;align-items:center;background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:12px;cursor:pointer;width:100%;text-align:left;color:inherit;font:inherit}
  #mkSheet{position:fixed;inset:0;background:var(--bg);z-index:30;overflow-y:auto;display:none}
  #mkSheet.open{display:block}
  #mkSheet .inner{max-width:760px;margin:0 auto;padding:calc(env(safe-area-inset-top) + 10px) 16px calc(env(safe-area-inset-bottom) + 40px)}
  #mkSheet .tabs{display:flex;gap:6px;overflow-x:auto;padding-bottom:4px}
  #mkSheet .tabs button{flex:0 0 auto;border:1px solid var(--line);background:var(--surface);color:inherit;border-radius:999px;padding:7px 12px;font:inherit;font-size:14px;cursor:pointer}
  #mkSheet .tabs button[aria-pressed="true"]{background:var(--accent);color:var(--bg);border-color:var(--accent)}
  #mkSheet .mk-card{display:grid;grid-template-columns:52px 1fr;gap:12px;background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:12px}
  #mkSheet .mk-card.sig{border-left:4px solid var(--accent)}
  #mkSheet details summary{cursor:pointer;color:var(--info);font-size:14px;margin-top:4px}
  #mkSheet .kv{display:grid;grid-template-columns:1fr auto;gap:4px 12px;font-size:14px;margin:6px 0}
  #mkSheet .kv span:nth-child(even){text-align:right;font-variant-numeric:tabular-nums}
  #mkSheet h4{margin:12px 0 4px;font-size:14px}
  #mkSheet .back{align-self:flex-start}`;
  document.head.appendChild(st);

  const entry = document.createElement("button");
  entry.id = "mkEntry"; entry.type = "button";
  entry.innerHTML = `<span style="font-size:26px">📈</span><span class="stack" style="gap:2px"><strong>Mercados</strong><span class="small muted" id="mkEntryMeta">Acciones de EE. UU. y cripto que parecen infravaloradas</span></span>`;
  const mount = () => {
    const v = $("#v-radar"); if (!v || $("#mkEntry")) return;
    const head = $(".radar-head", v);
    if (head && head.nextSibling) v.insertBefore(entry, head.nextSibling); else v.prepend(entry);
  };

  const sheet = document.createElement("div");
  sheet.id = "mkSheet"; sheet.setAttribute("role", "dialog"); sheet.setAttribute("aria-modal", "true");
  document.body.appendChild(sheet);

  function regimeChips() {
    const out = [];
    for (const r of [data?.stocks?.regime, data?.crypto?.regime]) {
      if (r) out.push(`<span class="chip ${r.riskOn ? "good" : "warn"}">${esc(r.symbol)} ${r.riskOn ? "por encima" : "por debajo"} de su media de 200</span>`);
    }
    const f = data?.crypto?.fearGreed;
    if (f) out.push(`<span class="chip">Miedo y codicia: ${esc(f.value)} (${esc(f.label)})</span>`);
    return out.join("");
  }

  function card(it, kind) {
    const m = it.metrics || {}, t = it.tech || {};
    const sig = it.trigger && !it.fallingKnife;
    const line = kind === "accion"
      ? `PER ${nf(m.pe, 1)} · Precio/caja libre ${nf(m.pfcf, 1)} · ROI ${pct(m.roi)} · Calidad ${m.fscore ?? "—"}/9`
      : `Cap./comisiones ${nf(m.pf, 1)} · MVRV ${nf(m.mvrv, 2)} · ${pct(m.athDiscount, 0)} bajo máximos`;
    const lossMax = t.riskPct != null ? Math.round(budget() * t.riskPct / 100) : null;
    const fair = it.fairValue ? `${usd(it.fairValue[0])} – ${usd(it.fairValue[1])} (${nf((it.fairValue[0] / it.price - 1) * 100, 0)} % – ${nf((it.fairValue[1] / it.price - 1) * 100, 0)} %)` : "—";
    const rd = it.reddit;
    const news = (it.news || []).map(n => { const u = safeUrl(n.url); return u ? `<li><a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(n.title)}</a></li>` : ""; }).join("");
    return `<div class="mk-card ${sig ? "sig" : ""}">
      <div class="score">${esc(it.score)}</div>
      <div class="stack" style="gap:6px;min-width:0">
        <div><strong>${esc(it.symbol)}</strong> <span class="muted">${esc(it.name)}</span></div>
        <div class="chips">
          ${sig ? `<span class="chip good">🎯 ${esc(it.trigger.type === "media50" ? "Giro: recupera la media de 50" : "Rebote en la media de 200")}</span>` : `<span class="chip">👀 En vigilancia</span>`}
          ${it.fallingKnife ? `<span class="chip bad">⚠️ Cuchillo cayendo</span>` : ""}
          ${it.sector ? `<span class="chip">${esc(it.sector)}</span>` : ""}
        </div>
        <div class="small muted">${usd(it.price)} · ${big(it.mcap)} · ${line}</div>
        <details><summary>Ver análisis y plan</summary>
          <h4>Plan orientativo</h4>
          <div class="kv"><span>Precio de referencia</span><span>${usd(it.price)}</span>
            <span>Stop (la idea se invalida)</span><span>${usd(t.stop)} (−${pct(t.riskPct)})</span>
            <span>Pérdida hasta el stop con ${nf(budget(), 0)} €</span><span>${lossMax != null ? "≈ " + nf(lossMax, 0) + " €" : "—"}</span>
            ${kind === "accion" ? `<span>Valor razonable por múltiplos</span><span>${fair}</span>` : ""}</div>
          ${it.trigger ? `<p class="small" style="margin:4px 0">${esc(it.trigger.text)}.</p>` : `<p class="small muted" style="margin:4px 0">Sin señal de giro todavía: el radar te avisará si aparece.</p>`}
          <h4>${kind === "accion" ? "Valor y calidad" : "Valor y uso"}</h4>
          <div class="kv">${kind === "accion" ? `
            <span>PER (mediana: ${nf(data.stocks.medians?.pe, 1)})</span><span>${nf(m.pe, 1)}</span>
            <span>Precio / caja libre (mediana: ${nf(data.stocks.medians?.pfcf, 1)})</span><span>${nf(m.pfcf, 1)}</span>
            <span>Valor de empresa / caja libre</span><span>${nf(m.evFcf, 1)}</span>
            <span>Precio / valor contable</span><span>${nf(m.pb, 2)}</span>
            <span>Rentabilidad sobre la inversión (ROI)</span><span>${pct(m.roi)}</span>
            <span>Margen bruto / operativo</span><span>${pct(m.gm)} / ${pct(m.om)}</span>
            <span>Deuda / patrimonio</span><span>${nf(m.de, 2)}</span>
            <span>Crecimiento de ventas (12 meses)</span><span>${pct(m.revG)}</span>` : `
            <span>Capitalización / comisiones anuales</span><span>${nf(m.pf, 1)}</span>
            <span>Capitalización / ingresos anuales</span><span>${nf(m.ps, 1)}</span>
            <span>MVRV (&lt; 1 = barato históricamente)</span><span>${nf(m.mvrv, 2)}</span>
            <span>Caída desde máximos</span><span>${pct(m.athDiscount, 0)}</span>
            <span>Crecimiento de comisiones (30 días)</span><span>${pct(m.feesGrowth)}</span>
            <span>En circulación</span><span>${pct(m.circulating, 0)}</span>`}</div>
          ${it.fscoreDetail?.length ? `<p class="small muted" style="margin:2px 0">Calidad (tipo Piotroski): ${esc(it.fscoreDetail.join(" · "))}</p>` : ""}
          <h4>Técnico</h4>
          <div class="kv"><span>Media 50 / 200 sesiones</span><span>${usd(t.sma50)} / ${usd(t.sma200)}</span>
            <span>RSI (14)</span><span>${nf(t.rsi, 0)}</span>
            ${t.mom12_1 != null ? `<span>Momento 12-1 meses</span><span>${pct(t.mom12_1)}</span>` : ""}
            <span>Fuerza frente a ${kind === "accion" ? "S&amp;P 500" : "BTC"} (3 meses)</span><span>${pct(t.rs3m)}</span></div>
          ${rd ? `<h4>Reddit</h4><p class="small" style="margin:0">${esc(rd.mentions)} menciones en 24 h (puesto ${esc(rd.rank)}, antes ${esc(rd.rank24hAgo ?? "—")}).</p>` : ""}
          ${news ? `<h4>Noticias</h4><ul class="small" style="margin:0;padding-left:18px">${news}</ul>` : ""}
        </details>
      </div></div>`;
  }

  function list(block, kind) {
    if (!block?.enabled) {
      const miss = kind === "accion" ? (data?.status?.massive?.error || "Sin datos todavía.") : "Sin datos todavía.";
      return `<div class="empty">${esc(miss)}</div>`;
    }
    const items = block.items || [];
    const head = kind === "accion"
      ? `<p class="small muted" style="margin:0">${nf(block.universe, 0)} empresas líquidas (cierre ${esc(block.priceDate)}); cuentas revisadas de ${nf(block.covered, 0)} (se amplía cada día); ${nf(block.passed, 0)} pasan los descartes; se muestran las mejores (${items.length}).</p>`
      : `<p class="small muted" style="margin:0">${nf(block.universe, 0)} criptos estudiadas; ${nf(block.passed, 0)} pasan los descartes; se muestran las mejores (${items.length}).</p>`;
    return head + (items.length ? items.map(i => card(i, kind)).join("") : `<div class="empty">Ninguna cumple los criterios hoy.</div>`);
  }

  function paperView() {
    const s = paper?.summary;
    if (!s || !s.signals) return `<div class="empty">Todavía no hay señales. Cada señal se apunta aquí con su precio para medir, sin dinero real, si el sistema funciona.</div>`;
    const rows = (paper.positions || []).slice().reverse().map(p => `<div class="card stack" style="gap:4px">
      <div><strong>${esc(p.symbol)}</strong> <span class="muted small">${esc(p.name)} · ${esc(p.date)}</span></div>
      <div class="small">Entrada ${usd(p.entry)} · Ahora ${usd(p.last ?? p.entry)} · <strong>${pct(p.returnPct)}</strong> (índice ${pct(p.benchPct)})</div>
      <div class="small muted">${p.status === "abierta" ? "Abierta" : "Cerrada (" + esc(p.exitReason) + ")"} · Stop ${usd(p.stop)}</div></div>`).join("");
    return `<div class="kv"><span>Señales</span><span>${s.signals}</span><span>Abiertas / cerradas</span><span>${s.open} / ${s.closed}</span>
      <span>Rentabilidad media</span><span>${pct(s.avgReturn)}</span><span>Índice en el mismo periodo</span><span>${pct(s.avgBench)}</span>
      <span>Aciertos (cerradas)</span><span>${s.hitRate != null ? pct(s.hitRate, 0) : "—"}</span></div>${rows}`;
  }

  const HOW = `<div class="stack small" style="gap:8px">
    <p style="margin:0"><strong>Método:</strong> como un fondo cuantitativo. Se combinan valor, calidad y momento, y solo se avisa cuando aparece una señal técnica de giro.</p>
    <p style="margin:0"><strong>Acciones (EE. UU.):</strong> capitalización &gt; 500 M$, liquidez &gt; 5 M$/día y precio &gt; 5 $. Descarte automático: pierde dinero y quema caja, calidad de 3 puntos o menos sobre 9, deuda &gt; 2,5× patrimonio, intereses mal cubiertos, ventas cayendo &gt; 20 % o sin beneficios. Nota: valor 40 % (PER, precio/caja libre, precio/valor contable), calidad 35 % (ROI, márgenes y una puntuación tipo Piotroski) y momento 25 %.</p>
    <p style="margin:0"><strong>Cripto:</strong> top 300 con más de 5 M$/día, sin stablecoins ni tokens envueltos. Descarte: menos del 50 % en circulación o sin datos para valorarla. Nota: valor 35 %, uso 25 %, técnico 20 % y sentimiento 20 %.</p>
    <p style="margin:0"><strong>Señal de giro:</strong> recupera la media de 50 sesiones tras semanas por debajo (RSI &gt; 50 y volumen alto) o rebota en una media de 200 que sube. Si el S&amp;P 500 o BTC están por debajo de su media de 200, se exige más nota.</p>
    <p style="margin:0"><strong>Cuchillo cayendo:</strong> barata pero con muy mala tendencia; se marca y no genera señal.</p>
    <p class="muted" style="margin:0">Datos: Finnhub, Massive, CoinGecko, DefiLlama, CoinMetrics, alternative.me, ApeWisdom y Tavily. Las cuentas son de los últimos 12 meses y los precios, del cierre anterior. No es asesoramiento financiero: el radar nunca compra ni vende por ti.</p></div>`;

  function render() {
    const t = data?.generatedAt ? new Date(data.generatedAt).toLocaleString("es-ES", {timeZone: "Europe/Madrid", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit"}) : "sin datos";
    const body = tab === "acciones" ? list(data?.stocks, "accion") : tab === "cripto" ? list(data?.crypto, "cripto") : tab === "cartera" ? paperView() : HOW;
    sheet.innerHTML = `<div class="inner stack">
      <button class="back" data-mkclose>← Volver</button>
      <div class="stack" style="gap:6px"><h2 style="margin:0">📈 Mercados</h2><span class="small muted">Actualizado: ${esc(t)}</span>
      <div class="chips">${regimeChips()}</div></div>
      <div class="tabs">${[["acciones", "Acciones"], ["cripto", "Cripto"], ["cartera", "Cartera fantasma"], ["como", "Cómo funciona"]]
        .map(([k, l]) => `<button data-mktab="${k}" aria-pressed="${tab === k}">${l}</button>`).join("")}</div>
      <div class="stack">${body}</div></div>`;
  }

  function open() { render(); sheet.classList.add("open"); sheet.scrollTop = 0; document.body.style.overflow = "hidden"; }
  function close() { sheet.classList.remove("open"); document.body.style.overflow = ""; if (location.hash === "#mercados") history.replaceState(null, "", "#radar"); }

  document.addEventListener("click", (e) => {
    if (e.target.closest("#mkEntry")) { open(); return; }
    if (e.target.closest("[data-mkclose]")) { close(); return; }
    const tb = e.target.closest("[data-mktab]"); if (tb) { tab = tb.dataset.mktab; render(); }
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && sheet.classList.contains("open")) close(); });

  async function load() {
    mount();
    try {
      const [a, b] = await Promise.all([fetch(`data/markets.json?t=${Date.now()}`, {cache: "no-store"}), fetch(`data/paper.json?t=${Date.now()}`, {cache: "no-store"})]);
      data = a.ok ? await a.json() : null; paper = b.ok ? await b.json() : null;
    } catch { data = data || null; }
    const sig = [...(data?.stocks?.items || []), ...(data?.crypto?.items || [])].filter(i => i.trigger && !i.fallingKnife).length;
    const meta = $("#mkEntryMeta");
    if (meta && data) meta.textContent = sig ? `${sig} con señal de giro · toca para ver` : "Acciones de EE. UU. y cripto que parecen infravaloradas";
    if (location.hash === "#mercados") open();
  }
  document.addEventListener("click", (e) => { if (e.target.closest("#refreshBtn")) setTimeout(load, 400); });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", load); else load();
})();
