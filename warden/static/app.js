const STATE_MS = 5000;
const HISTORY_MS = 60000;

let stateData = null;
const historyCache = {};

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));

async function fetchJson(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} → ${r.status}`);
  return r.json();
}

function fmtAgo(ts) {
  if (!ts) return "never";
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function fmtDur(s) {
  if (s == null) return "—";
  return s < 10 ? `${s.toFixed(1)}s` : `${Math.round(s)}s`;
}

function renderBar(w) {
  const el = document.getElementById("bar");
  const parts = [];
  parts.push(w.synced
    ? '<span class="badge ok">synced</span>'
    : '<span class="badge bad">behind origin</span>');
  if (w.dirty) parts.push('<span class="badge bad">dirty tree</span>');
  parts.push(`<span>${esc(w.head.slice(0, 8) || "—")}</span>`);
  parts.push(`<span>polled ${fmtAgo(w.last_poll)}</span>`);
  parts.push(`<span>up ${fmtDur(w.uptime_s)}</span>`);
  let html = parts.join("");
  html += '<span class="spacer"></span>';
  if (w.current_action) {
    const a = w.current_action;
    html += `<span class="run">deploying ${esc(a.service)}: ${esc(a.command)} · ${fmtAgo(a.since)}</span>`;
  }
  if (w.last_error) {
    html += `<span class="err" title="${esc(w.last_error)}">last cycle errored — see log</span>`;
  }
  el.innerHTML = html;
}

function healthDot(svc) {
  if (!svc.has_health) return "";
  const cls = !svc.last_check ? "" : svc.last_check.ok ? "up" : "down";
  return `<span class="dot ${cls}"></span>`;
}

function latencyText(svc) {
  if (!svc.has_health || !svc.last_check) return "";
  if (!svc.last_check.ok) return "down";
  if (svc.last_check.latency_ms == null) return "up";
  return `${Math.round(svc.last_check.latency_ms)}ms`;
}

function uptimeStrip(checks) {
  const buckets = new Array(48).fill(null);
  const now = Date.now() / 1000;
  const window = 86400;
  for (const c of checks) {
    const age = now - c.ts;
    if (age < 0 || age >= window) continue;
    const idx = 47 - Math.floor(age / (window / 48));
    buckets[idx] = buckets[idx] === false ? false : !!c.ok;
  }
  const cells = buckets.map((b) => {
    const cls = b === null ? "" : b ? "up" : "down";
    return `<i class="${cls}"></i>`;
  }).join("");
  return `<div class="strip">${cells}</div>`;
}

function sparkline(checks) {
  const pts = checks.filter((c) => c.latency_ms != null);
  if (pts.length < 2) return "";
  const values = pts.map((c) => c.latency_ms);
  const min = Math.min(...values);
  const range = Math.max(...values) - min || 1;
  const w = 240;
  const h = 36;
  const coords = pts.map((c, i) => {
    const x = (i / (pts.length - 1)) * w;
    const y = h - 3 - ((c.latency_ms - min) / range) * (h - 6);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">` +
    `<polyline points="${coords.join(" ")}" fill="none" stroke="#7aa2f7" stroke-width="1.5"/></svg>`;
}

function renderCards() {
  if (!stateData) return;
  const el = document.getElementById("cards");
  el.innerHTML = stateData.services.map((svc) => {
    const checks = historyCache[svc.name] || [];
    const charts = svc.has_health ? uptimeStrip(checks) + sparkline(checks) : "";
    return `<div class="card">
      <div class="head">${healthDot(svc)}<span class="name">${esc(svc.name)}</span>
        <span class="latency">${esc(latencyText(svc))}</span></div>
      ${charts}
    </div>`;
  }).join("");
}

async function tick() {
  try {
    stateData = await fetchJson("/api/state");
    renderBar(stateData.warden);
    renderCards();
  } catch (e) {
    console.error(e);
  }
}

async function tickHistories() {
  if (!stateData) return;
  const targets = stateData.services.filter((s) => s.has_health);
  await Promise.all(targets.map(async (s) => {
    try {
      const h = await fetchJson(`/api/history/${encodeURIComponent(s.name)}?hours=24`);
      historyCache[s.name] = h.checks;
    } catch (e) {
      console.error(e);
    }
  }));
  renderCards();
}

tick();
tick().then(tickHistories);
setInterval(tick, STATE_MS);
setInterval(tickHistories, HISTORY_MS);
