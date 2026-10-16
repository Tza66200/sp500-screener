// Screener S&P 500 — application cliente (aucune dépendance, aucune donnée envoyée).
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const FACTORS = ["growth", "momentum", "quality", "value", "risk"];
const state = { data: {}, sort: { key: "rank", dir: 1 }, weights: null, refWeights: null };

// ---------------------------------------------------------------- formats
const nf = (d) => new Intl.NumberFormat("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d });
const NF0 = nf(0), NF1 = nf(1), NF2 = nf(2), NF3 = nf(3);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const isNum = (v) => typeof v === "number" && Number.isFinite(v);
const MINUS = "−";
const sign = (s) => s.replace(/^-/, MINUS);
const pct = (v, d = 1, plus = false) => (isNum(v) ? sign((plus && v > 0 ? "+" : "") + nf(d).format(v * 100)) + " %" : "—");
const num = (v, d = 0) => (isNum(v) ? sign(nf(d).format(v)) : "—");
const money = (v) => {
  if (!isNum(v)) return "—";
  const a = Math.abs(v);
  if (a >= 1e11) return sign(NF0.format(v / 1e9)) + " Md$";
  if (a >= 1e9) return sign(NF1.format(v / 1e9)) + " Md$";
  if (a >= 1e6) return sign(NF0.format(v / 1e6)) + " M$";
  return sign(NF0.format(v)) + " $";
};
const MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
const parseDate = (s) => (s ? new Date(s.length <= 10 ? s + "T12:00:00" : s) : null);
const dateFr = (s, long = false) => {
  const d = parseDate(s); if (!d || isNaN(d)) return "—";
  return long ? d.toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" })
    : `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
};
const daysUntil = (s) => Math.round((parseDate(s) - new Date()) / 864e5);
const tone = (v) => (isNum(v) ? (v > 0 ? "pos" : v < 0 ? "neg" : "") : "");

// ---------------------------------------------------------------- thème
function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem("theme"); } catch (e) { /* stockage indisponible */ }
  if (saved === "light" || saved === "dark") document.documentElement.dataset.theme = saved;
  $("#theme-toggle").addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    const next = dark ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("theme", next); } catch (e) { /* ignore */ }
    redrawCharts();
  });
}

// ---------------------------------------------------------------- onglets
function initTabs() {
  const tabs = $$('[role="tab"]');
  const show = (name, focus) => {
    tabs.forEach((t) => {
      const on = t.dataset.tab === name;
      t.setAttribute("aria-selected", on);
      t.tabIndex = on ? 0 : -1;
      $("#panel-" + t.dataset.tab).hidden = !on;
      if (on && focus) t.focus();
    });
    redrawCharts();
  };
  tabs.forEach((t, i) => {
    t.addEventListener("click", () => { history.replaceState(null, "", "#" + t.dataset.tab); show(t.dataset.tab); });
    t.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      const n = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
      history.replaceState(null, "", "#" + n.dataset.tab); show(n.dataset.tab, true);
    });
  });
  const fromHash = () => {
    const h = location.hash.slice(1);
    show(tabs.some((t) => t.dataset.tab === h) ? h : "classement");
  };
  addEventListener("hashchange", fromHash);
  fromHash();
}

// ---------------------------------------------------------------- données
async function load() {
  const meta = await fetch("data/meta.json", { cache: "no-store" }).then((r) => {
    if (!r.ok) throw new Error("meta"); return r.json();
  });
  const v = encodeURIComponent(meta.generated_at || "");
  const names = ["ranking", "portfolio", "backtest", "factors", "audit", "changes"];
  const res = await Promise.all(names.map((n) => fetch(`data/${n}.json?v=${v}`).then((r) => (r.ok ? r.json() : null))));
  state.data = { meta, ...Object.fromEntries(names.map((n, i) => [n, res[i]])) };
}

// ---------------------------------------------------------------- en-tête
function renderHeader() {
  const m = state.data.meta;
  $('[data-bind="model_version"]').textContent = m.model_version;
  const gen = new Date(m.generated_at);
  const genTxt = gen.toLocaleString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  let html = `Cours au ${esc(dateFr(m.price_last_date))}<br>Actualisé le ${esc(genTxt)}`;
  const age = (Date.now() - gen) / 864e5;
  if (age > 4) html += `<span class="warn">⚠ Pas d'actualisation depuis ${Math.floor(age)} jours</span>`;
  (m.warnings || []).forEach((w) => { html += `<span class="warn">⚠ ${esc(w)}</span>`; });
  $("#freshness").innerHTML = html;
}

// ---------------------------------------------------------------- tableau du portefeuille
function renderBoard() {
  const p = state.data.portfolio;
  const board = $("#board");
  if (!p || !p.holdings.length) {
    board.innerHTML = '<div class="tile empty">Aucune position : le backtest n\'a pas encore produit de portefeuille.</div>';
    return;
  }
  const lr = p.last_review;
  $("#board-note").textContent = lr ? `20 lignes à poids égaux, issues de la revue du ${dateFr(lr.review_date, true)}. Cliquez sur un titre pour sa fiche.` : "";
  board.innerHTML = p.holdings.map((h, i) => {
    const sell = h.action === "vendre";
    return `<button class="tile${sell ? " sell" : ""}" role="listitem" data-ticker="${esc(h.ticker)}" style="--i:${i}"
      aria-label="${esc(h.ticker)} ${esc(h.name || "")}, rang ${isNum(h.rank) ? h.rank : "non classé"}${sell ? ", à vendre à la prochaine revue" : ""}">
      <span class="tk">${esc(h.ticker)}</span>
      ${sell ? '<span class="nm flag">À vendre</span>' : `<span class="nm">${esc(h.name || "ancien membre")}</span>`}
      <span class="ln"><span class="rk">${isNum(h.rank) ? "n° " + h.rank : "exclu"}</span>
      <span class="${tone(h.return)}">${pct(h.return, 0, true)}</span></span></button>`;
  }).join("");
  board.onclick = (e) => { const t = e.target.closest("[data-ticker]"); if (t) openDrawer(t.dataset.ticker); };

  const n = p.next_review, d = daysUntil(n);
  const sells = p.holdings.filter((h) => h.action === "vendre").length;
  const buys = p.hypothetical_buys.length;
  $("#next-review").innerHTML = `<span>Prochaine revue : <strong>${esc(dateFr(n, true))}</strong> (dans ${d} jour${d > 1 ? "s" : ""})</span>
    <span>Si elle avait lieu aujourd'hui : <strong>${sells} vente${sells > 1 ? "s" : ""}, ${buys} achat${buys > 1 ? "s" : ""}</strong></span>
    <span>Le pourcentage est le rendement depuis l'entrée, dividendes compris.</span>`;
}

// ---------------------------------------------------------------- classement
function scoreRows() {
  const rows = state.data.ranking.rows;
  const w = state.weights, minF = state.data.meta.scoring.min_factors;
  const custom = FACTORS.some((f) => Math.abs(w[f] - state.refWeights[f]) > 1e-9);
  rows.forEach((r) => {
    if (!custom) { r._score = r.score; return; }
    let s = 0, ws = 0, n = 0;
    FACTORS.forEach((f) => { const v = r.factors[f]; if (isNum(v)) { s += v * w[f]; ws += w[f]; n++; } });
    r._score = n >= minF && ws > 0 ? s / ws : null;
  });
  const elig = rows.filter((r) => r.eligible && isNum(r._score)).sort((a, b) => b._score - a._score);
  rows.forEach((r) => { r._rank = null; });
  elig.forEach((r, i) => { r._rank = i + 1; });
  return custom;
}

function meter(v) {
  if (!isNum(v)) return '<span class="meter na"><span class="track"></span><span class="v">—</span></span>';
  return `<span class="meter"><span class="track"><span class="fill" style="width:${v.toFixed(1)}%"></span></span><span class="v">${Math.round(v)}</span></span>`;
}

function renderRanking() {
  const custom = scoreRows();
  const q = $("#q").value.trim().toLowerCase();
  const sector = $("#sector").value;
  const only = $("#only-eligible").checked;
  let rows = state.data.ranking.rows.filter((r) =>
    (!only || r.eligible) && (!sector || r.sector === sector) &&
    (!q || r.ticker.toLowerCase().includes(q) || (r.name || "").toLowerCase().includes(q)));
  const { key, dir } = state.sort;
  const val = (r) => key === "rank" ? (r._rank ?? 1e9) : key === "score" ? r._score : key === "ticker" ? r.ticker
    : key === "confidence" ? r.confidence : r.factors[key];
  rows = rows.slice().sort((a, b) => {
    if (a.eligible !== b.eligible) return a.eligible ? -1 : 1;
    const va = val(a), vb = val(b);
    if (va == null && vb == null) return 0; if (va == null) return 1; if (vb == null) return -1;
    return (va < vb ? -1 : va > vb ? 1 : 0) * dir;
  });
  $$("#rank-table th.sortable").forEach((th) => {
    th.setAttribute("aria-sort", th.dataset.sort === key ? (dir === 1 ? "ascending" : "descending") : "none");
  });
  let cutDone = false;
  $("#rank-table tbody").innerHTML = rows.map((r) => {
    let cls = r.eligible ? "" : "inel";
    if (!r.eligible && !cutDone && !only) { cls += " cut"; cutDone = true; }
    const res = r.next_earnings_est ? `vers le ${dateFr(r.next_earnings_est)}` : "—";
    return `<tr class="${cls}" data-ticker="${esc(r.ticker)}" tabindex="0">
      <td class="num rk">${r._rank ?? "—"}</td>
      <td><div class="co"><span class="tk">${esc(r.ticker)}</span>${r.in_portfolio ? '<span class="held" title="Dans le portefeuille modèle"></span>' : ""}<span class="nm">${esc(r.name)}</span></div>
        ${r.eligible ? "" : `<div class="reasons">${esc((r.reasons || []).join(" ; "))}</div>`}</td>
      <td class="hide-sm">${esc(r.sector)}</td>
      <td class="num score">${isNum(r._score) ? NF1.format(r._score) : "—"}</td>
      ${FACTORS.map((f) => `<td class="fac">${meter(r.factors[f])}</td>`).join("")}
      <td class="num hide-sm">${isNum(r.confidence) ? Math.round(r.confidence) + " %" : "—"}</td>
      <td class="hide-md">${res}</td></tr>`;
  }).join("") || '<tr><td colspan="11" class="empty-state">Aucun titre ne correspond à ces filtres.</td></tr>';
  const nEl = state.data.ranking.rows.filter((r) => r.eligible).length;
  $("#rank-foot").textContent = `${nEl} titres éligibles sur ${state.data.ranking.rows.length} membres actuels. ` +
    (custom ? "Classement recalculé avec vos pondérations." : "Pondérations de référence.") +
    " Le point indique les titres du portefeuille modèle.";
}

function initRanking() {
  const sectors = [...new Set(state.data.ranking.rows.map((r) => r.sector).filter(Boolean))].sort();
  $("#sector").insertAdjacentHTML("beforeend", sectors.map((s) => `<option>${esc(s)}</option>`).join(""));
  ["#q", "#sector", "#only-eligible"].forEach((s) => $(s).addEventListener("input", renderRanking));
  $$("#rank-table th.sortable").forEach((th) => th.addEventListener("click", () => {
    const k = th.dataset.sort;
    state.sort = state.sort.key === k ? { key: k, dir: -state.sort.dir } : { key: k, dir: k === "rank" || k === "ticker" ? 1 : -1 };
    renderRanking();
  }));
  const tbody = $("#rank-table tbody");
  tbody.addEventListener("click", (e) => { const tr = e.target.closest("tr[data-ticker]"); if (tr) openDrawer(tr.dataset.ticker); });
  tbody.addEventListener("keydown", (e) => { if (e.key === "Enter") { const tr = e.target.closest("tr[data-ticker]"); if (tr) openDrawer(tr.dataset.ticker); } });

  // Pondérations
  state.refWeights = { ...state.data.meta.weights };
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem("weights") || "null"); } catch (e) { /* ignore */ }
  state.weights = saved && FACTORS.every((f) => isNum(saved[f])) ? saved : { ...state.refWeights };
  const labels = state.data.meta.factor_labels;
  $("#weights-grid").innerHTML = FACTORS.map((f) => `<label>${esc(labels[f])}
      <input type="range" min="0" max="50" step="5" data-f="${f}" value="${Math.round(state.weights[f] * 100)}">
      <output data-o="${f}"></output></label>`).join("");
  const sync = () => {
    const raw = Object.fromEntries(FACTORS.map((f) => [f, +$(`input[data-f="${f}"]`).value]));
    const tot = FACTORS.reduce((a, f) => a + raw[f], 0) || 1;
    state.weights = Object.fromEntries(FACTORS.map((f) => [f, raw[f] / tot]));
    FACTORS.forEach((f) => { $(`output[data-o="${f}"]`).textContent = `${Math.round(state.weights[f] * 100)} % du score`; });
    try { localStorage.setItem("weights", JSON.stringify(state.weights)); } catch (e) { /* ignore */ }
    renderRanking();
  };
  $$("#weights-grid input").forEach((i) => i.addEventListener("input", sync));
  $("#weights-reset").addEventListener("click", () => {
    FACTORS.forEach((f) => { $(`input[data-f="${f}"]`).value = Math.round(state.refWeights[f] * 100); });
    sync();
  });
  $("#weights-toggle").addEventListener("click", (e) => {
    const open = $("#weights").hidden;
    $("#weights").hidden = !open; e.currentTarget.setAttribute("aria-expanded", open);
  });
  sync();

  const c = state.data.changes;
  if (c && c.available) {
    const parts = [];
    if (c.entered_top20.length) parts.push(`entrés dans le top 20 : ${c.entered_top20.join(", ")}`);
    if (c.left_top20.length) parts.push(`sortis : ${c.left_top20.join(", ")}`);
    $("#changes").textContent = parts.length
      ? `Depuis le ${dateFr(c.compared_to)}, ${parts.join(" ; ")}.`
      : `Aucun changement dans le top 20 depuis le ${dateFr(c.compared_to)}.`;
  } else {
    $("#changes").textContent = "Le suivi des changements commencera après une semaine d'actualisations.";
  }
}

// ---------------------------------------------------------------- fiche
function fmtMetric(m, v) {
  if (!isNum(v)) return "—";
  if (m === "leverage") {
    if (v <= -9) return "trésorerie nette";
    if (v >= 999) return "EBITDA négatif";
    return NF1.format(v) + " ×";
  }
  return pct(v, 1, m === "rev_growth" || m === "rev_accel" || m === "oi_change_assets" || m.startsWith("mom"));
}

function openDrawer(ticker) {
  const r = state.data.ranking.rows.find((x) => x.ticker === ticker);
  const meta = state.data.meta;
  const body = $("#drawer-body");
  if (!r) {
    const h = state.data.portfolio.holdings.find((x) => x.ticker === ticker);
    body.innerHTML = `<div class="d-head"><div class="tk">${esc(ticker)}</div><div class="nm">${esc(h?.name || "")}</div>
      <p class="sub">Ce titre n'est plus membre de l'indice : il sera vendu à la prochaine revue.</p></div>`;
  } else {
    const x = r.extra || {};
    const cikPad = isNum(r.cik) ? String(Math.round(r.cik)) : "";
    const metricRows = Object.keys(meta.metric_labels).map((m) => {
      const f = meta.metric_factor[m];
      return `<tr><td>${esc(meta.metric_labels[m])}<br><span class="reasons">${esc(meta.factor_labels[f])}${meta.metric_by_sector[m] ? ", comparé au secteur" : ""}${meta.metric_direction[m] < 0 ? ", plus bas = mieux" : ""}</span></td>
        <td class="num">${fmtMetric(m, r.metrics[m])}</td><td class="num">${isNum(r.pct[m]) ? Math.round(r.pct[m]) : "—"}</td></tr>`;
    }).join("");
    body.innerHTML = `
      <div class="d-head"><div class="tk" id="drawer-title">${esc(r.ticker)}</div><div class="nm">${esc(r.name)}</div>
        <div class="sub">${esc(r.sector)}${r.sub_industry ? ", " + esc(r.sub_industry) : ""}</div></div>
      <div class="d-score">
        <div><div class="big">${isNum(r._score) ? NF1.format(r._score) : "—"}</div><div class="lab">score sur 100</div></div>
        <div><div class="big">${r._rank ?? "—"}</div><div class="lab">rang${r.eligible ? "" : " (non éligible)"}</div></div>
        <div><div class="big">${isNum(x.price_adj) ? "" : ""}${isNum(r.price) ? NF2.format(r.price) : "—"}</div><div class="lab">cours en $</div></div>
      </div>
      ${r.in_portfolio ? `<p><span class="chip buy">Dans le portefeuille modèle</span> ${r.action ? `À la prochaine revue : ${esc(r.action)}.` : ""}</p>` : ""}
      ${r.eligible ? "" : `<p class="reasons">Exclu : ${esc((r.reasons || []).join(" ; "))}</p>`}
      <div class="d-factors">${FACTORS.map((f) => `<div class="meter"><span class="lab">${esc(meta.factor_labels[f])}</span>
        <span class="track"><span class="fill" style="width:${isNum(r.factors[f]) ? r.factors[f].toFixed(1) : 0}%"></span></span>
        <span class="v">${isNum(r.factors[f]) ? Math.round(r.factors[f]) : "—"}</span></div>`).join("")}</div>
      <h4>Mesures</h4>
      <table><thead><tr><th>Mesure</th><th class="num">Valeur</th><th class="num">Rang 0-100</th></tr></thead><tbody>${metricRows}</tbody></table>
      <h4>Données utilisées</h4>
      <dl class="facts">
        <dt>Chiffre d'affaires 12 mois</dt><dd>${money(x.revenue_ttm)}</dd>
        <dt>Résultat opérationnel 12 mois</dt><dd>${money(x.oi_ttm)}</dd>
        <dt>Capitalisation</dt><dd>${money(x.market_cap)}</dd>
        <dt>Valeur d'entreprise</dt><dd>${money(x.enterprise_value)}</dd>
        <dt>Dette nette</dt><dd>${money(x.net_debt)}</dd>
        <dt>Rendement sur 12 mois</dt><dd class="${tone(x.ret_1y)}">${pct(x.ret_1y, 1, true)}</dd>
        <dt>Volume moyen</dt><dd>${money(x.dollar_vol_63)} par jour</dd>
        <dt>Trimestre le plus récent</dt><dd>clos le ${esc(dateFr(x.quarter_end))}</dd>
        <dt>Dernier dépôt SEC utilisé</dt><dd>${esc(dateFr(x.known_date))}${isNum(x.fundamentals_age_days) ? ` (il y a ${x.fundamentals_age_days} jours)` : ""}</dd>
        <dt>Derniers résultats publiés</dt><dd>${esc(dateFr(r.last_earnings))}</dd>
        <dt>Prochains résultats</dt><dd>${r.next_earnings_est ? "vers le " + esc(dateFr(r.next_earnings_est)) + " (estimation)" : "—"}</dd>
        <dt>Mesures disponibles</dt><dd>${isNum(r.confidence) ? Math.round(r.confidence) + " %" : "—"}</dd>
      </dl>
      ${r.flags ? `<h4>Signalements sur les données</h4><p class="flags">${esc(r.flags).replaceAll(" | ", "<br>")}</p>` : ""}
      <div class="links">
        ${cikPad ? `<a href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${cikPad}&type=10-&dateb=&owner=include&count=40" target="_blank" rel="noopener noreferrer">Dépôts SEC</a>` : ""}
        <a href="https://finance.yahoo.com/quote/${encodeURIComponent(r.ticker)}" target="_blank" rel="noopener noreferrer">Yahoo Finance</a>
      </div>
      <p class="reasons">Vérification qualitative avant tout achat : élément exceptionnel qui gonfle les résultats, litige, actualité récente. Un veto s'ajoute dans config/vetoes.yaml.</p>`;
  }
  const dlg = $("#drawer");
  if (!dlg.open) dlg.showModal();
  $("#drawer-close").focus();
}

function initDrawer() {
  const dlg = $("#drawer");
  $("#drawer-close").addEventListener("click", () => dlg.close());
  dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
}

// ---------------------------------------------------------------- portefeuille
function renderPortfolio() {
  const p = state.data.portfolio;
  if (!p) return;
  const prm = p.params;
  $("#rules").innerHTML = [
    `${prm.n_positions} lignes à poids égaux, ${Math.floor(prm.n_positions * prm.max_sector_fraction)} au maximum par secteur.`,
    `Revue le ${prm.review_day} de chaque mois de revue : ${prm.review_months.map((m) => MONTHS[m - 1]).join(", ")}.`,
    `Achat quand un titre entre dans le top ${prm.n_positions} ; conservation tant qu'il reste dans le top ${prm.hold_rank}.`,
    "Vente aussi en cas d'offre de rachat, de sortie de l'indice ou de veto qualitatif.",
    `Frais simulés : ${NF2.format(prm.cost_per_trade * 100)} % de chaque montant échangé.`,
  ].map((t) => `<li>${esc(t)}</li>`).join("");
  $("#holdings-table").innerHTML = `<thead><tr><th>Société</th><th class="hide-sm">Secteur</th><th class="num">Entrée</th>
    <th class="num">Depuis l'entrée</th><th class="num">Rang</th><th>Prochaine revue</th></tr></thead><tbody>${
    p.holdings.map((h) => `<tr><td><div class="co"><span class="tk">${esc(h.ticker)}</span><span class="nm">${esc(h.name || "")}</span></div></td>
      <td class="hide-sm">${esc(h.sector || "—")}</td><td class="num">${esc(dateFr(h.entry_date))}</td>
      <td class="num ${tone(h.return)}">${pct(h.return, 1, true)}</td><td class="num">${isNum(h.rank) ? h.rank : "—"}</td>
      <td>${h.action === "vendre" ? `<span class="chip sell">Vendre</span> <span class="reasons">${esc(h.sell_reason)}</span>` : '<span class="chip">Garder</span>'}</td></tr>`).join("")}</tbody>`;
  $("#hypo").innerHTML = p.hypothetical_buys.length
    ? `<p class="reasons">Titres qui remplaceraient les ventes, dans l'ordre du classement et dans la limite du plafond sectoriel :</p>
       <div class="table-wrap"><table class="data-table"><thead><tr><th>Société</th><th>Secteur</th><th class="num">Rang</th><th class="num">Score</th></tr></thead><tbody>${
        p.hypothetical_buys.map((b) => `<tr><td><div class="co"><span class="tk">${esc(b.ticker)}</span><span class="nm">${esc(b.name || "")}</span></div></td>
        <td>${esc(b.sector)}</td><td class="num">${b.rank}</td><td class="num">${NF1.format(b.score)}</td></tr>`).join("")}</tbody></table></div>`
    : '<p class="empty-state">Aucun changement : toutes les lignes resteraient dans le top 50.</p>';
  const counts = {};
  p.holdings.forEach((h) => { const s = h.sector || "Ancien membre"; counts[s] = (counts[s] || 0) + 1; });
  const cap = Math.floor(prm.n_positions * prm.max_sector_fraction);
  $("#sector-bars").innerHTML = Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([s, n]) =>
    `<div class="hbar"><span class="lab">${esc(s)}</span><span class="track"><span class="fill" style="width:${(n / cap) * 100}%"></span></span><span class="v">${n}</span></div>`).join("")
    + `<p class="reasons">Barre pleine = plafond de ${cap} titres.</p>`;
  $("#recent-reviews").innerHTML = p.recent_reviews.slice().reverse().map((rv) => `<div class="review"><span class="d">${esc(dateFr(rv.review_date, true))}</span>
    <div class="l">${rv.buy.length ? "Achats : " + esc(rv.buy.join(", ")) : "Aucun achat"}</div>
    <div class="l">${rv.sell.length ? "Ventes : " + esc(rv.sell.join(", ")) : "Aucune vente"}</div></div>`).join("");
}

// ---------------------------------------------------------------- graphiques
const charts = [];
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
function redrawCharts() { charts.forEach((c) => { if (c.el.offsetParent !== null) c.draw(); }); }
let resizeT;
addEventListener("resize", () => { clearTimeout(resizeT); resizeT = setTimeout(redrawCharts, 120); });

function niceTicks(min, max, n = 5) {
  const span = max - min || 1;
  const step0 = span / n, mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0);
  const out = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}

function lineChart(el, opts) {
  const chart = { el, opts, draw };
  charts.push(chart);
  function draw() {
    const series = opts.series().filter((s) => s.points.length);
    const W = Math.max(el.clientWidth, 280), H = opts.height || (W < 600 ? 240 : 320);
    const m = { t: 12, r: series.length <= 4 && opts.endLabels !== false ? (W < 600 ? 64 : 120) : 16, b: 28, l: 52 };
    const xs = series.flatMap((s) => s.points.map((p) => p[0]));
    const ys = series.flatMap((s) => s.points.map((p) => p[1])).filter(isNum);
    if (!xs.length) { el.innerHTML = '<p class="empty-state">Pas encore de données.</p>'; return; }
    let x0 = Math.min(...xs), x1 = Math.max(...xs);
    let y0 = Math.min(...ys, opts.yMin ?? Infinity), y1 = Math.max(...ys, opts.yMax ?? -Infinity);
    const log = opts.log && y0 > 0;
    const ty = (v) => (log ? Math.log(v) : v);
    if (y0 === y1) { y0 -= 1; y1 += 1; }
    const pad = (ty(y1) - ty(y0)) * 0.06;
    const Y0 = ty(y0) - (opts.yMin != null && !log ? 0 : pad), Y1 = ty(y1) + pad;
    const sx = (v) => m.l + ((v - x0) / (x1 - x0 || 1)) * (W - m.l - m.r);
    const sy = (v) => m.t + (1 - (ty(v) - Y0) / (Y1 - Y0)) * (H - m.t - m.b);
    let yt = log ? niceTicks(y0, y1, 5).filter((v) => v > 0) : niceTicks(Y0, Y1, 5);
    if (log) { yt = []; const cands = [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 5, 6, 8, 10, 15, 20]; cands.forEach((c) => { if (c >= y0 * 0.95 && c <= y1 * 1.05) yt.push(c); }); }
    const xt = opts.xTicks ? opts.xTicks(x0, x1) : yearTicks(x0, x1, W);
    let svg = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(opts.label)}">`;
    svg += '<g class="grid">' + yt.map((v) => `<line x1="${m.l}" x2="${W - m.r}" y1="${sy(v)}" y2="${sy(v)}"/>`).join("") + "</g>";
    if (opts.zero != null) svg += `<line class="zero" x1="${m.l}" x2="${W - m.r}" y1="${sy(opts.zero)}" y2="${sy(opts.zero)}"/>`;
    svg += '<g class="axis">' + yt.map((v) => `<text x="${m.l - 8}" y="${sy(v) + 4}" text-anchor="end">${esc(opts.yFormat(v))}</text>`).join("");
    svg += xt.map(([v, t]) => `<text x="${sx(v)}" y="${H - 8}" text-anchor="middle">${esc(t)}</text>`).join("") + "</g>";
    series.forEach((s) => {
      const d = s.points.filter((p) => isNum(p[1])).map((p, i) => `${i ? "L" : "M"}${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join("");
      if (opts.area) svg += `<path d="${d}L${sx(s.points.at(-1)[0])},${sy(opts.zero ?? y0)}L${sx(s.points[0][0])},${sy(opts.zero ?? y0)}Z" fill="${css(s.color)}" opacity=".14"/>`;
      svg += `<path d="${d}" fill="none" stroke="${css(s.color)}" stroke-width="${s.width || 2}" stroke-linejoin="round" stroke-linecap="round"/>`;
    });
    if (m.r > 20) {
      const ends = series.map((s) => { const p = s.points.filter((q) => isNum(q[1])).at(-1); return { s, y: sy(p[1]), v: p[1] }; }).sort((a, b) => a.y - b.y);
      for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 15) ends[i].y = ends[i - 1].y + 15;
      ends.forEach((e) => { svg += `<text class="lbl" x="${W - m.r + 8}" y="${e.y + 4}">${esc(W < 600 ? opts.yFormat(e.v) : e.s.short || e.s.label)}</text>`; });
    }
    svg += `<line class="xh" x1="0" x2="0" y1="${m.t}" y2="${H - m.b}" visibility="hidden"/>`;
    svg += `<rect x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${H - m.t - m.b}" fill="transparent"/></svg>`;
    const legend = series.length > 1 ? `<div class="legend">${series.map((s) => `<span><i style="background:${css(s.color)}"></i>${esc(s.label)}</span>`).join("")}</div>` : "";
    el.innerHTML = svg + legend;
    const svgEl = $("svg", el), xh = $(".xh", el), tip = $("#tooltip");
    const allX = [...new Set(xs)].sort((a, b) => a - b);
    const move = (e) => {
      const rect = svgEl.getBoundingClientRect();
      const px = ((e.clientX - rect.left) / rect.width) * W;
      const xv = x0 + ((px - m.l) / (W - m.l - m.r)) * (x1 - x0);
      let best = allX[0];
      for (const v of allX) if (Math.abs(v - xv) < Math.abs(best - xv)) best = v;
      xh.setAttribute("x1", sx(best)); xh.setAttribute("x2", sx(best)); xh.setAttribute("visibility", "visible");
      const rows = series.map((s) => {
        let pt = null; for (const p of s.points) { if (p[0] <= best) pt = p; else break; }
        return pt && isNum(pt[1]) ? `<div class="row"><span><i style="background:${css(s.color)}"></i>${esc(s.label)}</span><b>${esc(opts.tipFormat ? opts.tipFormat(pt[1]) : opts.yFormat(pt[1]))}</b></div>` : "";
      }).join("");
      tip.innerHTML = `<b>${esc(opts.xFormat(best))}</b>${rows}`;
      tip.hidden = false;
      const tx = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8);
      tip.style.left = tx + "px"; tip.style.top = Math.max(8, e.clientY - tip.offsetHeight - 12) + "px";
    };
    const leave = () => { tip.hidden = true; xh.setAttribute("visibility", "hidden"); };
    svgEl.addEventListener("pointermove", move);
    svgEl.addEventListener("pointerleave", leave);
  }
  draw();
  return chart;
}

function yearTicks(x0, x1, W) {
  const a = new Date(x0).getFullYear(), b = new Date(x1).getFullYear();
  const every = Math.max(1, Math.ceil((b - a + 1) / Math.max(2, Math.floor(W / 80))));
  const out = [];
  for (let y = a + 1; y <= b; y += every) out.push([new Date(y, 0, 1).getTime(), String(y)]);
  return out;
}
const ts = (s) => parseDate(s).getTime();

// ---------------------------------------------------------------- backtest
const RUN_COLORS = { reference: "--s1", equal_weight: "--s2", sp500: "--s3", equal_weights: "--s4", trend_filter: "--s5", fixed_12m: "--s6" };
function renderBacktest() {
  const b = state.data.backtest;
  if (!b) return;
  const L = b.labels;
  $("#holdout-notice").innerHTML = b.revealed
    ? `Période réservée révélée : les résultats depuis le ${esc(dateFr(b.holdout_start, true))} sont inclus. Le modèle ne doit plus être modifié en fonction de ces résultats.`
    : `Les résultats sont affichés du ${esc(dateFr(b.start, true))} au ${esc(dateFr(b.design_end, true))}. La période depuis le ${esc(dateFr(b.holdout_start, true))} est réservée : elle reste masquée tant que le modèle n'est pas figé, puis sera révélée une seule fois (paramètre <code>holdout.revealed</code> de <code>config/protocol.yaml</code>).`;
  $("#criteria").innerHTML = b.criteria.map((c) => {
    const k = c.status === "réussi" ? "ok" : c.status === "échoué" ? "ko" : "na";
    const icon = k === "ok" ? "✓" : k === "ko" ? "✕" : "?";
    return `<li class="${k}"><span class="ic" aria-hidden="true">${icon}</span><span><span class="st">${esc(c.status[0].toUpperCase() + c.status.slice(1))}</span> : ${esc(c.text)}<span class="dt">${esc(c.detail)}</span></span></li>`;
  }).join("");

  const extra = new Set();
  const opt = ["equal_weights", "trend_filter", "fixed_12m"];
  $("#variant-toggles").innerHTML = opt.map((v) => `<label><input type="checkbox" data-v="${v}"> ${esc(L[v])}</label>`).join("");
  $$("#variant-toggles input").forEach((i) => i.addEventListener("change", () => { i.checked ? extra.add(i.dataset.v) : extra.delete(i.dataset.v); eq.draw(); }));
  const mk = (key, short) => ({ key, label: L[key] || key, short, color: RUN_COLORS[key],
    points: b.curves.filter((r) => isNum(r[key])).map((r) => [ts(r.date), r[key]]) });
  const eq = lineChart($("#equity-chart"), {
    label: "Valeur de 1 dollar investi", log: true,
    series: () => [mk("reference", "Référence"), mk("equal_weight", "Équipondéré"), mk("sp500", "S&P 500"), ...[...extra].map((k) => mk(k, L[k]))],
    yFormat: (v) => NF2.format(v) + " $", xFormat: (x) => dateFr(new Date(x).toISOString().slice(0, 10)),
  });
  lineChart($("#dd-chart"), {
    label: "Baisse depuis le plus haut", area: true, zero: 0, height: 180, endLabels: false, yMax: 0,
    series: () => [{ key: "dd", label: "Référence", color: "--s1", points: b.drawdown.map((r) => [ts(r.date), r.value]) }],
    yFormat: (v) => pct(v, 0), xFormat: (x) => dateFr(new Date(x).toISOString().slice(0, 10)),
  });

  const cols = [["cagr", "Rendement annuel", (v) => pct(v, 1)], ["excess_equal_weight", "Écart vs équipondéré", (v) => pct(v, 1, true)],
    ["excess_sp500", "Écart vs S&P 500", (v) => pct(v, 1, true)], ["volatility", "Volatilité", (v) => pct(v, 1)],
    ["sharpe", "Sharpe", (v) => num(v, 2)], ["max_drawdown", "Pire baisse", (v) => pct(v, 1)],
    ["te_equal_weight", "Écart de suivi", (v) => pct(v, 1)], ["turnover_per_year", "Rotation / an", (v) => pct(v, 0)],
    ["hit_rate", "Positions gagnantes", (v) => pct(v, 0)]];
  const head = `<thead><tr><th>Stratégie</th>${cols.map((c) => `<th class="num">${c[1]}</th>`).join("")}</tr></thead>`;
  const row = (name, m, cls = "") => `<tr class="${cls}"><td>${esc(L[name] || name)}</td>${cols.map(([k, , f]) => {
    const v = m?.[k]; const t = k.startsWith("excess") ? tone(v) : "";
    return `<td class="num ${t}">${f(v)}</td>`;
  }).join("")}</tr>`;
  const ref = b.metrics.reference?.design || {};
  const benchRow = (key, label) => `<tr class="bench"><td>${esc(label)}</td><td class="num">${pct(ref["bench_cagr_" + key], 1)}</td>${cols.slice(1).map(() => '<td class="num">—</td>').join("")}</tr>`;
  $("#metrics-table").innerHTML = head + "<tbody>" +
    row("reference", ref, "ref") +
    `<tr class="group"><td colspan="${cols.length + 1}">Variantes</td></tr>` +
    b.variants.filter((v) => v !== "reference").map((v) => row(v, b.metrics[v]?.design)).join("") +
    `<tr class="group"><td colspan="${cols.length + 1}">Tests de robustesse</td></tr>` +
    b.robustness.map((v) => row(v, b.metrics[v]?.design)).join("") +
    `<tr class="group"><td colspan="${cols.length + 1}">Indices de référence</td></tr>` +
    benchRow("equal_weight", L.equal_weight) + benchRow("sp500", L.sp500) + "</tbody>";

  const subs = (b.metrics.reference?.subperiods || []).concat(b.revealed && b.metrics.reference.holdout ? [{ ...b.metrics.reference.holdout, _h: true }] : []);
  $("#sub-table").innerHTML = `<thead><tr><th>Période</th><th class="num">Référence</th><th class="num">Équipondéré</th><th class="num">S&amp;P 500</th><th class="num">Écart vs équipondéré</th><th class="num">Pire baisse</th><th class="num">Pire 12 mois relatifs</th></tr></thead><tbody>${
    subs.map((s) => `<tr><td>${esc(dateFr(s.start))} au ${esc(dateFr(s.end))}${s._h ? " (réservée)" : ""}</td><td class="num">${pct(s.cagr)}</td><td class="num">${pct(s.bench_cagr_equal_weight)}</td>
    <td class="num">${pct(s.bench_cagr_sp500)}</td><td class="num ${tone(s.excess_equal_weight)}">${pct(s.excess_equal_weight, 1, true)}</td><td class="num">${pct(s.max_drawdown)}</td><td class="num">${pct(s.worst_12m_rel_equal_weight, 1, true)}</td></tr>`).join("")}</tbody>`;
  $("#yearly-table").innerHTML = `<thead><tr><th>Année</th><th class="num">Référence</th><th class="num">Équipondéré</th><th class="num">S&amp;P 500</th><th class="num">Écart vs équipondéré</th></tr></thead><tbody>${
    b.yearly.map((y) => { const ex = isNum(y.reference) && isNum(y.equal_weight) ? y.reference - y.equal_weight : null;
      return `<tr><td>${y.year}</td><td class="num">${pct(y.reference)}</td><td class="num">${pct(y.equal_weight)}</td><td class="num">${pct(y.sp500)}</td><td class="num ${tone(ex)}">${pct(ex, 1, true)}</td></tr>`; }).join("")}</tbody>`;
  $("#bt-limits").innerHTML = `<p>Ordres simulés à la clôture de la séance suivant chaque revue, ${NF2.format(b.cost_per_trade * 100)} % de frais par transaction, dividendes réinvestis, avant impôts et frais de change. Les années incomplètes (première et dernière) ne couvrent qu'une partie de l'année.</p>
    <p>Le backtest ne contient que les sociétés dont Yahoo fournit encore les cours : celles rachetées ou en faillite manquent, ce qui embellit les résultats (voir l'onglet Données). Avec une quinzaine d'années de recul, un écart de quelques points par an n'est pas statistiquement prouvé : ce test sert surtout à repérer un modèle défaillant.</p>`;
}

// ---------------------------------------------------------------- facteurs
function icCell(v) {
  if (!isNum(v)) return '<td class="num">—</td>';
  const a = Math.min(Math.abs(v) / 0.15, 1);
  const col = v >= 0 ? css("--div-pos") : css("--div-neg");
  const bg = `color-mix(in srgb, ${col} ${Math.round(a * 38)}%, transparent)`;
  return `<td class="num" style="background:${bg}">${sign(NF3.format(v))}</td>`;
}
function renderFactors() {
  const f = state.data.factors;
  if (!f || !f.summary.length) { $("#ic-table").innerHTML = '<tbody><tr><td class="empty-state">Historique insuffisant pour cette analyse.</td></tr></tbody>'; return; }
  const L = f.labels, H = f.horizons, keys = [...FACTORS, "composite"];
  const get = (k, h) => f.summary.find((r) => r.factor === k && r.horizon === h);
  $("#ic-table").innerHTML = `<thead><tr><th>Facteur</th>${H.map((h) => `<th class="num">${h} mois</th>`).join("")}<th class="num" title="t-statistique à 12 mois corrigée du chevauchement des fenêtres">t à 12 mois</th><th class="num">Mois positifs à 12 mois</th></tr></thead><tbody>${
    keys.map((k) => { const r12 = get(k, 12);
      return `<tr${k === "composite" ? ' class="ref"' : ""}><td>${esc(L[k])}</td>${H.map((h) => icCell(get(k, h)?.mean_ic)).join("")}
      <td class="num">${num(r12?.t_overlap_adj, 1)}</td><td class="num">${pct(r12?.pct_positive, 0)}</td></tr>`; }).join("")}</tbody>`;
  const colors = { growth: "--s1", momentum: "--s2", quality: "--s3", value: "--s4", risk: "--s5", composite: "--s6" };
  lineChart($("#decay-chart"), {
    label: "Corrélation moyenne selon l'horizon", zero: 0, endLabels: false,
    series: () => keys.map((k) => ({ key: k, label: L[k], color: colors[k], width: k === "composite" ? 3 : 2,
      points: f.decay.filter((r) => r.factor === k).flatMap((r) => H.map((h) => [h, r[String(h)]])).filter((p) => isNum(p[1])) })),
    yFormat: (v) => sign(NF2.format(v)), tipFormat: (v) => sign(NF3.format(v)), xFormat: (x) => `${x} mois`,
    xTicks: () => H.map((h) => [h, `${h} m`]),
  });
  $("#ic-year-table").innerHTML = `<thead><tr><th>Année</th>${keys.map((k) => `<th class="num">${esc(L[k])}</th>`).join("")}</tr></thead><tbody>${
    f.by_year.map((y) => `<tr><td>${y.year}</td>${keys.map((k) => icCell(y[k])).join("")}</tr>`).join("")}</tbody>`;
}

// ---------------------------------------------------------------- données
function renderAudit() {
  const a = state.data.audit, m = state.data.meta;
  if (!a) return;
  const st = a.status || {};
  const facts = [
    ["Dernière séance", dateFr(m.price_last_date, true)],
    ["Calcul", new Date(m.generated_at).toLocaleString("fr-FR")],
    ["Données SEC lues le", st.sec_refreshed_at ? new Date(st.sec_refreshed_at).toLocaleString("fr-FR") : "—"],
    ["Composition actuelle", m.constituents_source === "wikipedia" ? "Wikipedia" : "fja05680/sp500 (Wikipedia indisponible)"],
    ["Composition historique", `fja05680/sp500, à jour au ${dateFr(m.history_last_date, true)}`],
    ["Cours", st.prices ? `${st.prices.downloaded} séries sur ${st.prices.requested} demandées` : "—"],
    ["Séries anciennes conservées", st.prices?.stale?.length ? st.prices.stale.join(", ") : "aucune"],
    ["Dépôts SEC", st.sec ? `${st.sec.submissions_ok} sociétés lues, ${st.sec.facts_updated} jeux de comptes mis à jour, ${st.sec.errors} erreur(s)` : "—"],
  ];
  $("#sources").innerHTML = facts.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("") +
    (m.warnings?.length ? `<dt>Alertes</dt><dd class="flags">${m.warnings.map(esc).join("<br>")}</dd>` : "");
  const u = a.backtest_universe;
  const share = u.former_members ? u.former_without_prices / u.members_since_start : 0;
  $("#survivorship").innerHTML = `<div class="stat-row">
      <div class="stat"><div class="n">${u.members_since_start}</div><div class="l">membres depuis le ${esc(dateFr(u.start))}</div></div>
      <div class="stat"><div class="n">${u.former_members}</div><div class="l">ont quitté l'indice</div></div>
      <div class="stat"><div class="n">${u.former_without_prices}</div><div class="l">sans cours disponibles</div></div>
      <div class="stat"><div class="n">${pct(share, 0)}</div><div class="l">de l'univers manque au backtest</div></div></div>
    <p class="prose">Les anciens membres sans cours sont surtout des sociétés rachetées, fusionnées ou en faillite. Leur absence biaise le backtest à la hausse, car les faillites en font partie. Les ${u.former_still_quoted + u.former_quotes_ended} anciens membres dont les cours sont disponibles (le plus souvent parce qu'ils sont toujours cotés) sont bien inclus.${u.reused_symbols_dropped.length ? ` ${u.reused_symbols_dropped.length} symboles réattribués depuis à une autre société ont été écartés.` : ""}</p>
    ${u.former_without_prices_list.length ? `<details><summary>Voir les ${u.former_without_prices} anciens membres sans cours</summary><p class="ticker-list">${esc(u.former_without_prices_list.join(" "))}</p></details>` : ""}
    ${u.without_cik.length ? `<details><summary>${u.without_cik.length} titres sans identifiant SEC</summary><p class="ticker-list">${esc(u.without_cik.join(" "))}</p></details>` : ""}`;
  lineChart($("#elig-chart"), {
    label: "Nombre de titres éligibles", height: 180, endLabels: false,
    series: () => [{ key: "e", label: "Titres éligibles", color: "--s1", points: a.eligible_over_time.map((r) => [ts(r.date), r.eligible]) }],
    yFormat: (v) => NF0.format(v), xFormat: (x) => dateFr(new Date(x).toISOString().slice(0, 10)),
  });
  const et = Object.entries(a.eligibility_today);
  $("#elig-today").innerHTML = `<div class="stat-row"><div class="stat"><div class="n">${a.eligible_today}</div><div class="l">titres éligibles</div></div></div>` +
    (et.length ? `<p class="reasons">Motifs d'exclusion des autres membres :</p>` + et.map(([k, v]) => `<div class="hbar"><span class="lab" title="${esc(k)}">${esc(k)}</span><span class="track"><span class="fill" style="width:${(v / m.counts.members) * 100 * 4}%"></span></span><span class="v">${v}</span></div>`).join("") : "");
  const cov = a.sec_coverage.metric_coverage;
  $("#coverage").innerHTML = Object.entries(cov).map(([k, v]) => `<div class="hbar"><span class="lab" title="${esc(m.metric_labels[k])}">${esc(m.metric_labels[k])}</span><span class="track"><span class="fill" style="width:${v * 100}%"></span></span><span class="v">${Math.round(v * 100)}</span></div>`).join("") +
    '<p class="reasons">Part des membres hors financières et immobilier pour lesquels la mesure est calculable, en %.</p>';
  const fl = Object.entries(a.flags || {});
  $("#flags").innerHTML = fl.length ? fl.map(([k, v]) => `<div class="review"><span class="d">${v}</span> <span class="l">${esc(k)}</span></div>`).join("") : '<p class="reasons">Aucun.</p>';
}

function renderMethod() {
  const m = state.data.meta;
  const byF = {};
  Object.keys(m.metric_labels).forEach((k) => { (byF[m.metric_factor[k]] ||= []).push(k); });
  $("#method-metrics").innerHTML = `<thead><tr><th>Facteur</th><th class="num">Poids</th><th>Mesures</th></tr></thead><tbody>${
    FACTORS.map((f) => `<tr><td>${esc(m.factor_labels[f])}</td><td class="num">${NF0.format(m.weights[f] * 100)} %</td>
      <td>${byF[f].map((k) => esc(m.metric_labels[k]) + (m.metric_direction[k] < 0 ? " (plus bas = mieux)" : "")).join("<br>")}</td></tr>`).join("")}</tbody>`;
}

// ---------------------------------------------------------------- démarrage
async function main() {
  initTheme();
  try {
    await load();
  } catch (e) {
    $("#freshness").textContent = "";
    $("#board").innerHTML = '<div class="tile empty">Les données ne sont pas encore générées. Lancez le workflow « Actualisation » dans l\'onglet Actions du dépôt GitHub.</div>';
    return;
  }
  renderHeader();
  renderBoard();
  initRanking();
  initDrawer();
  renderPortfolio();
  initTabs();
  renderBacktest();
  renderFactors();
  renderAudit();
  renderMethod();
  redrawCharts();
}
main();
