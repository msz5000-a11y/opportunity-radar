/* Opportunity Radar · Pestaña «Ideas para copiar» (data/ideas.json). */
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const safeUrl = (u) => { try { const x = new URL(String(u)); return /^https?:$/.test(x.protocol) ? x.href : null; } catch { return null; } };
  const nf = (n) => (n == null || isNaN(+n)) ? "—" : new Intl.NumberFormat("es-ES", {maximumFractionDigits: 0}).format(+n);
  const MK = {es: "🇪🇸 España", eg: "🇪🇬 Egipto", gcc: "🌴 Golfo"};
  const TYPE = {app: "App", saas: "SaaS", software: "Software", marketplace: "Marketplace", ecommerce: "E-commerce", servicio: "Servicio", negocio_local: "Negocio local"};
  let data = null, market = "all", type = "", minScore = 0;

  const st = document.createElement("style");
  st.textContent = `
  #ideasRoot .idea{display:grid;grid-template-columns:52px 1fr;gap:12px;background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:12px}
  #ideasRoot .bar{display:flex;gap:8px;flex-wrap:wrap}
  #ideasRoot select{flex:1 1 30%;min-width:0}
  #ideasRoot details summary{cursor:pointer;color:var(--info);font-size:14px;margin-top:4px}
  #ideasRoot h4{margin:12px 0 4px;font-size:14px}
  #ideasRoot ul{margin:0;padding-left:18px;display:flex;flex-direction:column;gap:4px;font-size:14px}
  #ideasRoot .mk{border:1px solid var(--line);border-radius:10px;padding:8px 10px;margin-top:6px;font-size:14px}`;
  document.head.appendChild(st);

  const fit = (it, m) => +((it.markets || {})[m] || {}).fit || 0;
  const list = (a) => Array.isArray(a) && a.length ? `<ul>${a.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : `<p class="small muted" style="margin:0">No consta.</p>`;

  function card(it) {
    const mv = it.mvp || {}, cost = Array.isArray(mv.costEur) ? mv.costEur : [];
    const orig = (m) => !!((it.markets || {})[m] || {}).origin;
    const fits = Object.keys(MK).map(m => orig(m) ? `<span class="chip">${MK[m]}: ya existe (origen)</span>` : `<span class="chip ${fit(it, m) >= 7 ? "good" : fit(it, m) >= 5 ? "" : "bad"}">${MK[m]} ${fit(it, m)}/10</span>`).join("")
      + (it.regulated ? `<span class="chip warn">Regulado: licencias</span>` : "");
    const links = (it.links || []).map(l => { const u = safeUrl(l.url); return u ? `<li><a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(l.title)}</a></li>` : ""; }).join("");
    const mk = Object.keys(MK).map(m => { const x = (it.markets || {})[m] || {};
      return `<div class="mk"><strong>${MK[m]} · ${fit(it, m)}/10</strong><br>${esc(x.why || "")}${x.adapt ? `<br><span class="muted">Adaptar: ${esc(x.adapt)}</span>` : ""}${x.competition ? `<br><span class="muted">Competencia: ${esc(x.competition)}</span>` : ""}</div>`; }).join("");
    return `<div class="idea">
      <div class="score">${esc(it.score)}</div>
      <div class="stack" style="gap:6px;min-width:0">
        <div><strong>${esc(it.name)}</strong> <span class="muted small">${esc(TYPE[it.type] || it.type || "")} · ${esc(it.originCountry || "")}</span></div>
        <div class="small">${esc(it.summary || "")}</div>
        <div class="chips">${fits}${it.verified ? `<span class="chip good">Datos comprobados</span>` : `<span class="chip warn">Datos sin comprobar</span>`}</div>
        <div class="small muted">MVP: ${cost.length ? nf(cost[0]) + "–" + nf(cost[1]) + " €" : "—"} · ${mv.weeks ? esc(mv.weeks) + " semanas" : "—"}${mv.noCode ? " · se puede sin programar" : ""}</div>
        <details><summary>Ver análisis completo</summary>
          <h4>Pruebas de éxito</h4>${list(it.traction)}
          ${it.droppedFacts ? `<p class="small muted" style="margin:4px 0">${esc(it.droppedFacts)} dato(s) eliminados porque no aparecían en la fuente.</p>` : ""}
          <h4>Por qué funcionó</h4>${list(it.whyItWorked)}
          <h4>Encaje por mercado</h4>${mk}
          <h4>Cómo gana dinero</h4><p class="small" style="margin:0">${esc(it.monetization || "No consta.")}</p>
          <h4>Qué hace falta (MVP)</h4><p class="small" style="margin:0">Equipo: ${esc(mv.team || "—")}<br>Herramientas: ${esc(mv.stack || "—")}</p>
          <h4>Primeros pasos para validarla</h4>${list(it.firstSteps)}
          <h4>Riesgos</h4>${list(it.risks)}
          <h4>Enlaces e información</h4><ul>${links}</ul>
          <p class="small muted" style="margin:8px 0 0">Analizada por IA el ${esc((it.foundAt || "").slice(0, 10))}${it.checkedBy ? ` y comprobada con otro modelo (${esc(it.checkedBy)})` : ""}. La competencia local y el tamaño de mercado hay que verificarlos antes de invertir.</p>
        </details>
      </div></div>`;
  }

  function render() {
    const root = $("#ideasRoot"); if (!root) return;
    if (!data || !(data.items || []).length) { root.innerHTML = `<div class="empty">Todavía no hay ideas. La primera tanda aparecerá tras la próxima exploración diaria.</div>`; return; }
    let items = data.items.filter(it => (!type || it.type === type) && (it.score || 0) >= minScore);
    if (market !== "all") items = items.filter(it => fit(it, market) >= 5 && !((it.markets || {})[market] || {}).origin).sort((a, b) => fit(b, market) - fit(a, market) || b.score - a.score);
    else items = items.slice().sort((a, b) => b.score - a.score);
    const t = new Date(data.generatedAt);
    root.innerHTML = `<div class="bar">
        <select id="iMk" aria-label="Mercado"><option value="all">Todos los mercados</option>${Object.keys(MK).map(m => `<option value="${m}" ${market === m ? "selected" : ""}>${MK[m]}</option>`).join("")}</select>
        <select id="iType" aria-label="Tipo"><option value="">Todos los tipos</option>${Object.keys(TYPE).map(k => `<option value="${k}" ${type === k ? "selected" : ""}>${TYPE[k]}</option>`).join("")}</select>
        <select id="iMin" aria-label="Nota mínima">${[0, 50, 65, 75].map(n => `<option value="${n}" ${minScore === n ? "selected" : ""}>${n ? "Nota " + n + "+" : "Cualquier nota"}</option>`).join("")}</select>
      </div>
      <p class="small muted" style="margin:0">${items.length} ideas · actualizado ${isNaN(t) ? "—" : t.toLocaleString("es-ES", {timeZone: "Europe/Madrid", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit"})}</p>
      ${items.map(card).join("") || `<div class="empty">Ninguna idea con estos filtros.</div>`}`;
  }

  document.addEventListener("change", (e) => {
    if (e.target.id === "iMk") { market = e.target.value; render(); }
    if (e.target.id === "iType") { type = e.target.value; render(); }
    if (e.target.id === "iMin") { minScore = +e.target.value; render(); }
  });
  async function load() {
    try { const r = await fetch(`data/ideas.json?t=${Date.now()}`, {cache: "no-store"}); data = r.ok ? await r.json() : null; } catch { data = null; }
    render();
  }
  document.addEventListener("click", (e) => { if (e.target.closest("#refreshBtn")) setTimeout(load, 400); });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", load); else load();
})();
