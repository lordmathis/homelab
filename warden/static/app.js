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
  for (const a of w.current_actions || []) {
    html += `<span class="run">deploying ${esc(a.service)}: ${esc(a.command)} · ${fmtAgo(a.since)}</span>`;
  }
  if (w.last_error) {
    html += `<span class="err" title="${esc(w.last_error)}">last cycle errored — see log</span>`;
  }
  el.innerHTML = html;
}

function healthState(svc) {
  if (!svc.has_health || !svc.last_check) return "";
  if ((svc.consecutive_failures || 0) >= stateData.failure_threshold) return "down";
  return svc.last_check.ok ? "up" : "warn";
}

function healthDot(svc) {
  const st = healthState(svc);
  return st ? `<span class="dot ${st}"></span>` : "";
}

function latencyText(svc) {
  if (!svc.has_health || !svc.last_check) return "";
  const st = healthState(svc);
  if (st === "down") return "down";
  if (st === "warn") return "failing";
  if (svc.last_check.latency_ms == null) return "up";
  return `${Math.round(svc.last_check.latency_ms)}ms`;
}

function uptimeText(svc) {
  if (!svc.has_health || svc.uptime_24h == null) return "";
  const pct = (v) => v == null ? "—" : `${(v * 100).toFixed(1)}%`;
  return `uptime 24h ${pct(svc.uptime_24h)} · 7d ${pct(svc.uptime_7d)}`;
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
    const uptime = uptimeText(svc);
    return `<div class="card${svc.has_logs ? " has-logs" : ""}" data-service="${esc(svc.name)}">
      <div class="head">${healthDot(svc)}<span class="name">${esc(svc.name)}</span>
        <span class="latency">${esc(latencyText(svc))}</span></div>
      ${charts}${uptime ? `<div class="uptime">${esc(uptime)}</div>` : ""}
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

const LOG_POLL_MS = 2000;
const TAIL_LINES = 500;
const PIN_PX = 48;

const drawerState = {
  open: false,
  service: null,
  activeFile: null,
  files: [],
  follow: true,
  filter: "",
  lastJson: "",
  search: null,
};

let drawerBuilt = false;

function buildDrawer() {
  if (drawerBuilt) return;
  drawerBuilt = true;
  document.getElementById("drawer").innerHTML = `
    <div class="dhead">
      <span id="dtitle" class="dtitle"></span>
      <button id="dclose" class="dclose" aria-label="close">×</button>
    </div>
    <nav id="dtabs" class="dtabs"></nav>
    <div class="dtoolbar">
      <input id="dfilter" type="text" placeholder="filter">
      <span id="dcount" class="dcount"></span>
      <label id="dfollow-label" class="dfollow"><input id="dfollow" type="checkbox" checked> follow</label>
      <button id="dback" class="dback hidden">← tail</button>
      <input id="dsearch" type="text" placeholder="search (regex)">
    </div>
    <div id="logview" class="logview"></div>`;
  document.getElementById("dclose").addEventListener("click", closeDrawer);
  document.getElementById("scrim").addEventListener("click", closeDrawer);
  document.getElementById("dfilter").addEventListener("input", (e) => {
    drawerState.filter = e.target.value;
    renderTail();
  });
  document.getElementById("dfollow").addEventListener("change", (e) => {
    drawerState.follow = e.target.checked;
  });
  document.getElementById("dsearch").addEventListener("keydown", (e) => {
    if (e.key === "Enter") runSearch(e.target.value.trim());
  });
  document.getElementById("dback").addEventListener("click", exitSearch);
  document.getElementById("dtabs").addEventListener("click", (e) => {
    const tab = e.target.closest(".dtab");
    if (!tab) return;
    drawerState.activeFile = tab.dataset.file;
    renderTabs();
    renderTail();
  });
}

function setDrawerMode(searchMode) {
  const toggle = (id, show) => document.getElementById(id).classList.toggle("hidden", !show);
  toggle("dtabs", !searchMode);
  toggle("dfilter", !searchMode);
  toggle("dcount", !searchMode);
  toggle("dfollow-label", !searchMode);
  toggle("dback", searchMode);
}

function openDrawer(service) {
  const d = drawerState;
  d.open = true;
  d.service = service;
  d.activeFile = null;
  d.files = [];
  d.follow = true;
  d.filter = "";
  d.lastJson = "";
  d.search = null;
  buildDrawer();
  document.getElementById("dtitle").textContent = service;
  document.getElementById("dfilter").value = "";
  document.getElementById("dsearch").value = "";
  document.getElementById("dfollow").checked = true;
  document.getElementById("dtabs").innerHTML = "";
  document.getElementById("logview").innerHTML = '<div class="hint">loading…</div>';
  setDrawerMode(false);
  document.getElementById("scrim").classList.remove("hidden");
  document.getElementById("drawer").classList.remove("hidden");
  refreshTail(true);
}

function closeDrawer() {
  drawerState.open = false;
  drawerState.service = null;
  document.getElementById("scrim").classList.add("hidden");
  document.getElementById("drawer").classList.add("hidden");
}

async function refreshTail(force) {
  const d = drawerState;
  const service = d.service;
  if (!service) return;
  try {
    const data = await fetchJson(`/api/logs/${encodeURIComponent(service)}?lines=${TAIL_LINES}`);
    if (d.service !== service) return;
    const json = JSON.stringify(data);
    if (!force && json === d.lastJson) return;
    d.lastJson = json;
    d.files = data.files;
    if (!d.files.length || d.files.every((f) => f.lines == null)) {
      d.activeFile = null;
      document.getElementById("dtabs").innerHTML = "";
      document.getElementById("logview").innerHTML = '<div class="hint">no log files</div>';
      document.getElementById("dcount").textContent = "";
      return;
    }
    if (!d.activeFile || !d.files.some((f) => f.name === d.activeFile)) {
      const nonEmpty = d.files.find((f) => Array.isArray(f.lines) && f.lines.length);
      d.activeFile = (nonEmpty || d.files[0]).name;
      renderTabs();
    }
    renderTail();
  } catch (e) {
    console.error(e);
  }
}

async function followTick() {
  const d = drawerState;
  if (!d.open || !d.service || !d.activeFile || !d.follow || d.search) return;
  refreshTail(false);
}

function renderTabs() {
  document.getElementById("dtabs").innerHTML = drawerState.files.map((f) =>
    `<button class="dtab${f.name === drawerState.activeFile ? " active" : ""}"` +
    ` data-file="${esc(f.name)}">${esc(f.name)}</button>`).join("");
}

function renderTail() {
  const d = drawerState;
  const file = d.files.find((f) => f.name === d.activeFile);
  const view = document.getElementById("logview");
  if (!file) return;
  if (file.lines == null) {
    view.innerHTML = '<div class="hint">no log output yet</div>';
    document.getElementById("dcount").textContent = "";
    return;
  }
  const q = d.filter.toLowerCase();
  const shown = q ? file.lines.filter((l) => l.toLowerCase().includes(q)) : file.lines;
  document.getElementById("dcount").textContent = `${shown.length}/${file.lines.length}`;
  if (!shown.length) {
    view.innerHTML = '<div class="hint">no matching lines</div>';
    return;
  }
  const pinned = view.scrollHeight - view.scrollTop - view.clientHeight <= PIN_PX;
  view.innerHTML = shown.map((l) => `<div class="logline">${esc(l)}</div>`).join("");
  if (pinned) view.scrollTop = view.scrollHeight;
}

async function runSearch(q) {
  const d = drawerState;
  if (!q || !d.service) return;
  const service = d.service;
  try {
    const r = await fetch(`/api/search/${encodeURIComponent(service)}?q=${encodeURIComponent(q)}`);
    const data = await r.json().catch(() => null);
    if (d.service !== service) return;
    if (!r.ok || !data) {
      d.search = { error: (data && data.error) || `search failed (${r.status})` };
    } else {
      d.search = data;
    }
  } catch (e) {
    if (d.service !== service) return;
    d.search = { error: `search failed: ${e}` };
  }
  setDrawerMode(true);
  renderSearch();
}

function renderSearch() {
  const d = drawerState;
  const view = document.getElementById("logview");
  if (d.search.error) {
    view.innerHTML = `<div class="hint">${esc(d.search.error)}</div>`;
    return;
  }
  const parts = [];
  for (const f of d.search.files) {
    if (!f.exists) continue;
    parts.push(`<div class="sfile">${esc(f.name)} · ${f.total} match${f.total === 1 ? "" : "es"}</div>`);
    for (const m of f.matches) {
      parts.push(`<div class="smatch"><span class="sloc">${esc(f.name)}:${m.line}</span>${esc(m.text)}</div>`);
    }
  }
  view.innerHTML = parts.join("") || '<div class="hint">no matches</div>';
}

function exitSearch() {
  drawerState.search = null;
  drawerState.follow = true;
  document.getElementById("dfollow").checked = true;
  setDrawerMode(false);
  renderTabs();
  renderTail();
}

document.getElementById("cards").addEventListener("click", (e) => {
  const card = e.target.closest(".card.has-logs");
  if (!card) return;
  const svc = stateData && stateData.services.find((s) => s.name === card.dataset.service);
  if (!svc || !svc.has_logs) return;
  openDrawer(svc.name);
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && drawerState.open) closeDrawer();
});

setInterval(followTick, LOG_POLL_MS);
