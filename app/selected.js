/* Opportunity Radar · Sección «Seleccionadas» y manuales paso a paso.
   Lee data/selected.json (lo genera radar/selection.py) y se monta en la pantalla Radar. */
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const safeUrl = (u) => { try { const x = new URL(String(u)); return /^https?:$/.test(x.protocol) ? x.href : null; } catch { return null; } };
  const eur = (n) => (n == null || n === "" || isNaN(+n)) ? "—" : (+n === 0 ? "Gratis" : new Intl.NumberFormat("es-ES", {style: "currency", currency: "EUR", maximumFractionDigits: 2}).format(+n));
  const CAT = {cripto: "Cripto y Web3", startups: "Startups", ia_tecnologia: "IA y tecnología", lanzamientos: "Lanzamientos", negocio: "Ideas de negocio"};
  const PKEY = "radar-manual-progress";
  let data = null;
  let progress = {};
  try { progress = JSON.parse(localStorage.getItem(PKEY) || "{}"); } catch { progress = {}; }
  const saveProgress = () => { try { localStorage.setItem(PKEY, JSON.stringify(progress)); } catch {} };

  const css = `
  #selSection .sel-card{display:grid;grid-template-columns:52px 1fr;gap:12px;background:var(--surface);border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:var(--r);padding:12px}
  #selSection .sel-card.near{border-left-color:var(--warn)}
  #selSection .sel-main{background:none;border:0;padding:0;text-align:left;color:inherit;font:inherit;cursor:pointer;display:flex;flex-direction:column;gap:6px;min-width:0}
  #selSection .crit-mini{font-size:12px;color:var(--muted)}
  #selSection details summary{cursor:pointer;color:var(--info);font-size:14px}
  #selSheet{position:fixed;inset:0;background:var(--bg);z-index:30;overflow-y:auto;display:none}
  #selSheet.open{display:block}
  #selSheet .inner{max-width:720px;margin:0 auto;padding:calc(env(safe-area-inset-top) + 10px) 16px calc(env(safe-area-inset-bottom) + 40px)}
  #selSheet .back{align-self:flex-start}
  #selSheet h3{margin:18px 0 6px;font-size:16px}
  #selSheet ul,#selSheet ol{margin:0;padding-left:20px;display:flex;flex-direction:column;gap:6px}
  #selSheet .step{display:grid;grid-template-columns:28px 1fr;gap:8px;align-items:start;padding:10px 0;border-bottom:1px solid var(--line)}
  #selSheet .step input{width:22px;height:22px;margin-top:2px}
  #selSheet .step.done .t{text-decoration:line-through;color:var(--muted)}
  #selSheet .ok{color:var(--good)} #selSheet .ko{color:var(--bad)}
  #selSheet .warnbox{border:1px solid var(--warn);border-radius:var(--r);padding:12px;font-size:14px}`;
  const st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);

  // ---------- sección en la pantalla Radar ----------
  const section = document.createElement("div");
  section.className = "section"; section.id = "selSection";
  section.innerHTML = `<div class="section-head"><h2>⭐ Seleccionadas</h2><span class="small muted" id="selMeta"></span></div><div class="stack" id="selBody"><div class="empty">Cargando selección…</div></div>`;
  const mount = () => {
    const v = $("#v-radar"); if (!v || $("#selSection")) return;
    const head = $(".radar-head", v);
    if (head && head.nextSibling) v.insertBefore(section, head.nextSibling); else v.appendChild(section);
  };

  function card(r, near) {
    const pct = Math.round((r.passed / (data.criteria.length || 9)) * 100);
    return `<div class="sel-card ${near ? "near" : ""}">
      <div class="score">${esc(r.adjustedScore ?? r.score ?? "–")}</div>
      <div class="stack" style="gap:8px;min-width:0">
        <button class="sel-main" data-opp="${esc(r.id)}">
          <span class="opp-title">${esc(r.name)}</span>
          <span class="small muted">${esc(CAT[r.category] || r.category || "")} · ${eur(r.minEntry)} · Riesgo ${esc(r.risk || "desconocido")}</span>
        </button>
        <div class="crit-mini">${near ? `Cumple ${r.passed} de ${data.criteria.length} criterios · Le falta: ${esc(r.failed.join(" · "))}` : `Cumple los ${data.criteria.length} criterios (${pct} %)`}</div>
        ${r.hasManual ? `<div class="row"><button class="btn" data-manual="${esc(r.id)}" style="padding:7px 12px">📘 Cómo aprovecharla</button></div>` : ""}
      </div>
    </div>`;
  }

  function render() {
    mount();
    const body = $("#selBody"), meta = $("#selMeta");
    if (!body) return;
    if (!data) { body.innerHTML = `<div class="empty">La selección aparecerá tras la próxima exploración.</div>`; return; }
    const t = new Date(data.generatedAt);
    meta.textContent = `${data.studied} estudiadas · ${isNaN(t) ? "" : t.toLocaleString("es-ES", {timeZone: "Europe/Madrid", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit"})}`;
    const crit = `<details class="card"><summary>Criterios estrictos (${data.criteria.length})</summary><ol class="small" style="margin-top:8px">${data.criteria.map(c => `<li>${esc(c.label)}</li>`).join("")}</ol>
      <p class="small muted" style="margin:8px 0 0">Solo entra la que cumple todos. Máximo ${5} a la vez. Si la segunda opinión duda, queda fuera.</p></details>`;
    const sel = data.selected || [], near = data.nearMisses || [];
    body.innerHTML = (sel.length
      ? sel.map(r => card(r, false)).join("")
      : `<div class="empty">Ninguna oportunidad supera todavía los ${data.criteria.length} criterios. Es mejor no invertir que hacerlo en algo dudoso.</div>`)
      + (near.length ? `<div class="small muted" style="margin-top:6px">Las más cercanas (no seleccionadas):</div>` + near.slice(0, 3).map(r => card(r, true)).join("") : "")
      + crit;
    if (location.hash === "#seleccion") section.scrollIntoView({behavior: "smooth"});
  }

  // ---------- manual ----------
  const sheet = document.createElement("div");
  sheet.id = "selSheet"; sheet.setAttribute("role", "dialog"); sheet.setAttribute("aria-modal", "true");
  document.body.appendChild(sheet);
  const list = (a) => (Array.isArray(a) && a.length) ? `<ul>${a.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : `<p class="muted small">No consta.</p>`;
  const para = (t) => t ? `<p style="margin:0">${esc(t)}</p>` : `<p class="muted small">No consta.</p>`;

  function openManual(id) {
    const m = data?.manuals?.[id];
    const r = [...(data?.selected || []), ...(data?.nearMisses || [])].find(x => x.id === id);
    if (!m || !r) return;
    const isSel = (data.selected || []).some(x => x.id === id);
    const so = m.segundaOpinion || {}, via = m.viaDeBeneficio || {};
    const done = progress[id] || {};
    const url = safeUrl(r.officialUrl);
    sheet.innerHTML = `<div class="inner stack">
      <button class="back" data-selclose>← Volver</button>
      <div class="stack" style="gap:6px">
        <h2 style="margin:0">📘 Manual: ${esc(r.name)}</h2>
        <div class="chips">
          ${isSel ? `<span class="chip good">Seleccionada</span>` : `<span class="chip warn">No seleccionada · solo para investigar</span>`}
          <span class="chip">Nota ${esc(r.adjustedScore)}</span><span class="chip">Entrada ${eur(r.minEntry)}</span>
          ${r.canLoseAll ? `<span class="chip bad">Puedes perderlo todo</span>` : ""}
        </div>
      </div>
      ${!isSel ? `<div class="warnbox">No cumple: ${esc(r.failed.join(" · "))}. Úsalo para investigar, no para invertir todavía.</div>` : ""}
      <div class="card stack" style="gap:6px"><strong>Qué es</strong>${para(m.resumen)}</div>
      <div class="card stack" style="gap:6px"><strong>Cómo se gana dinero aquí</strong>${para(via.explicacion)}</div>
      <div class="card stack" style="gap:6px"><strong>Cuánto poner</strong>${para(m.cuantoPoner)}<p class="small muted" style="margin:0">Nunca más de lo que puedas perder sin problema. Límite del radar: ${eur(data.budget)}.</p></div>
      <h3>1. Antes de empezar, comprueba</h3>${list(m.antesDeEmpezar)}
      <h3>2. Paso a paso</h3>
      <div>${(m.pasos || []).map((p, i) => `<label class="step ${done[i] ? "done" : ""}"><input type="checkbox" data-step="${esc(id)}|${i}" ${done[i] ? "checked" : ""}><span><span class="t"><strong>${esc(p.titulo)}</strong>${p.tiempo ? ` <span class="muted small">· ${esc(p.tiempo)}</span>` : ""}</span><br><span class="small">${esc(p.detalle)}</span></span></label>`).join("") || `<p class="muted small">No consta.</p>`}</div>
      <h3>3. Plan de salida</h3>${para(m.planDeSalida)}
      <h3>Abandona si…</h3>${list(m.senalesDeAlarma)}
      <h3>Errores típicos</h3>${list(m.erroresTipicos)}
      <h3>Impuestos en España (orientativo)</h3>${para(m.fiscalidad)}
      <h3>Tiempo necesario</h3>${para(m.tiempoNecesario)}
      <h3>Criterios</h3>
      <ul style="list-style:none;padding:0">${data.criteria.map(c => `<li>${r.checks[c.id] ? `<span class="ok">✓</span>` : `<span class="ko">✗</span>`} ${esc(c.label)}</li>`).join("")}</ul>
      <h3>Segunda opinión</h3>
      <p style="margin:0">${esc(so.veredicto || "—")} · ${esc(so.motivo || "")}</p>
      ${(so.contradicciones || []).length ? list(so.contradicciones) : ""}
      <p class="small muted" style="margin:0">Modelo: ${esc(m.modelo || "—")}${m.independiente ? " (distinto del analista)" : " (mismo modelo que el analista: no cuenta como verificación)"} · ${m.webLeida ? "leyó la web oficial" : "no pudo leer la web oficial"}</p>
      <div class="row">
        ${url ? `<a class="btn" href="${esc(url)}" target="_blank" rel="noopener noreferrer">Web oficial</a>` : ""}
        <button class="btn" data-opp="${esc(id)}" data-selclose>Ver ficha completa</button>
      </div>
      <p class="small muted">Manual generado por IA a partir de los datos del radar. Puede contener errores: comprueba cada dato en la web oficial. No es asesoramiento financiero; el radar nunca compra ni mueve dinero por ti.</p>
    </div>`;
    sheet.classList.add("open"); sheet.scrollTop = 0;
    document.body.style.overflow = "hidden";
  }
  function closeManual() { sheet.classList.remove("open"); document.body.style.overflow = ""; }

  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-manual]"); if (b) { e.preventDefault(); openManual(b.dataset.manual); return; }
    if (e.target.closest("[data-selclose]")) closeManual();
  });
  document.addEventListener("change", (e) => {
    const c = e.target.closest("[data-step]"); if (!c) return;
    const [id, i] = c.dataset.step.split("|");
    progress[id] = progress[id] || {}; progress[id][i] = c.checked; saveProgress();
    c.closest(".step").classList.toggle("done", c.checked);
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && sheet.classList.contains("open")) closeManual(); });

  async function load() {
    try {
      const r = await fetch(`data/selected.json?t=${Date.now()}`, {cache: "no-store"});
      data = r.ok ? await r.json() : null;
    } catch { data = null; }
    render();
  }
  document.addEventListener("click", (e) => { if (e.target.closest("#refreshBtn")) setTimeout(load, 400); });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", load); else load();
})();
