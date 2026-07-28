/* RB5009 Monitor - Phase A dashboard.
 * Receives state over SSE; keeps a rolling throughput window per interface
 * and renders a self-contained canvas chart (no external chart library, so
 * the dashboard works with no internet access on the LAN). */
"use strict";

const state = {
  resource: null,
  health: null,
  interfaces: null,
  updatedAt: {},
  reachable: false,
  selectedIface: null,
  series: new Map(), // iface -> [{t, rx, tx}]
};

const WINDOW_SECONDS = 300;

/* ---------- formatting helpers ---------- */

function fmtBytes(n) {
  if (n == null) return "—";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return n.toFixed(n >= 100 || i === 0 ? 0 : 1) + " " + units[i];
}

function fmtRate(bps) {
  if (bps == null) return "—";
  const units = ["bps", "kbps", "Mbps", "Gbps"];
  let i = 0;
  while (bps >= 1000 && i < units.length - 1) { bps /= 1000; i++; }
  return bps.toFixed(bps >= 100 || i === 0 ? 0 : 1) + " " + units[i];
}

function fmtDuration(seconds) {
  if (seconds == null) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m ${Math.floor(seconds % 60)}s`;
}

function fmtTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString();
}

/* ---------- render: cards ---------- */

function renderResource() {
  const r = state.resource;
  if (!r) return;
  document.getElementById("identity").textContent = r.identity || r.board_name || "—";
  document.getElementById("board").textContent = r.board_name || "";
  document.getElementById("version").textContent = "RouterOS " + (r.version || "—");
  document.getElementById("uptime").textContent = fmtDuration(r.uptime_seconds);

  const load = r.cpu_load_percent;
  document.getElementById("cpu-load").textContent = load == null ? "—" : load.toFixed(0) + "%";
  document.getElementById("cpu-info").textContent =
    `${r.cpu_count || "?"} cores @ ${r.cpu_frequency_mhz || "?"} MHz`;
  const cpuBar = document.getElementById("cpu-bar");
  cpuBar.style.width = (load || 0) + "%";
  cpuBar.classList.toggle("hot", (load || 0) > 80);

  if (r.total_memory_bytes != null && r.free_memory_bytes != null) {
    const used = r.total_memory_bytes - r.free_memory_bytes;
    const pct = (used / r.total_memory_bytes) * 100;
    document.getElementById("mem-used").textContent = fmtBytes(used);
    document.getElementById("mem-info").textContent =
      `of ${fmtBytes(r.total_memory_bytes)} (${pct.toFixed(0)}%)`;
    const memBar = document.getElementById("mem-bar");
    memBar.style.width = pct + "%";
    memBar.classList.toggle("hot", pct > 85);
  }
}

function renderHealth() {
  const list = document.getElementById("health-list");
  if (!state.health || state.health.length === 0) {
    list.textContent = "no sensors reported";
    return;
  }
  list.innerHTML = "";
  for (const s of state.health) {
    if (s.value == null && !s.raw_value) continue;
    const row = document.createElement("div");
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = s.name;
    const val = document.createElement("span");
    val.textContent = s.value != null ? `${s.value}${s.unit === "C" ? " °C" : " " + (s.unit || "")}` : s.raw_value;
    row.append(name, val);
    list.appendChild(row);
  }
}

/* ---------- render: interface table ---------- */

function renderInterfaces() {
  const ifaces = state.interfaces;
  if (!ifaces) return;
  const tbody = document.querySelector("#iface-table tbody");
  tbody.innerHTML = "";
  for (const it of ifaces) {
    const tr = document.createElement("tr");
    tr.dataset.name = it.name;
    if (it.name === state.selectedIface) tr.classList.add("selected");
    const stateCls = it.disabled ? "disabled" : (it.running ? "up" : "down");
    const stateTxt = it.disabled ? "disabled" : (it.running ? "up" : "down");
    tr.innerHTML =
      `<td>${it.name}</td><td>${it.type || ""}</td>` +
      `<td><span class="state ${stateCls}">${stateTxt}</span></td>` +
      `<td>${fmtRate(it.rx_rate_bps)}</td><td>${fmtRate(it.tx_rate_bps)}</td>` +
      `<td class="${it.rx_errors ? "err" : ""}">${it.rx_errors ?? "—"}</td>` +
      `<td class="${it.tx_errors ? "err" : ""}">${it.tx_errors ?? "—"}</td>` +
      `<td>${(it.rx_drops ?? 0) + (it.tx_drops ?? 0)}</td>` +
      `<td>${it.link_downs ?? "—"}</td>`;
    tr.addEventListener("click", () => selectInterface(it.name));
    tbody.appendChild(tr);
  }
}

function selectInterface(name) {
  state.selectedIface = name;
  document.getElementById("chart-iface").textContent = "— " + name;
  renderInterfaces();
  drawChart();
}

/* ---------- throughput series + chart ---------- */

function recordSeries() {
  const now = Date.now() / 1000;
  for (const it of state.interfaces || []) {
    if (it.rx_rate_bps == null) continue;
    if (!state.series.has(it.name)) state.series.set(it.name, []);
    const arr = state.series.get(it.name);
    arr.push({ t: now, rx: it.rx_rate_bps, tx: it.tx_rate_bps });
    while (arr.length && arr[0].t < now - WINDOW_SECONDS) arr.shift();
  }
  if (!state.selectedIface && state.interfaces && state.interfaces.length) {
    // default to the busiest running interface
    const running = state.interfaces.filter(i => i.running);
    const pick = (running.length ? running : state.interfaces)
      .slice().sort((a, b) => (b.rx_rate_bps || 0) - (a.rx_rate_bps || 0))[0];
    if (pick) selectInterface(pick.name);
  }
}

function drawChart() {
  const canvas = document.getElementById("chart");
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const cssW = canvas.clientWidth, cssH = 220;
  canvas.width = cssW * dpr;
  canvas.height = cssH * dpr;
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, cssW, cssH);

  const data = state.series.get(state.selectedIface) || [];
  const padL = 64, padR = 10, padT = 10, padB = 22;
  const w = cssW - padL - padR, h = cssH - padT - padB;
  const now = Date.now() / 1000;
  const t0 = now - WINDOW_SECONDS;

  let max = 1000; // min scale: 1 kbps
  for (const p of data) max = Math.max(max, p.rx || 0, p.tx || 0);
  max *= 1.15;

  const css = getComputedStyle(document.documentElement);
  ctx.strokeStyle = css.getPropertyValue("--border").trim();
  ctx.fillStyle = css.getPropertyValue("--muted").trim();
  ctx.font = "11px system-ui, sans-serif";
  ctx.lineWidth = 1;

  for (let g = 0; g <= 4; g++) {
    const y = padT + (h * g) / 4;
    ctx.beginPath();
    ctx.moveTo(padL, y);
    ctx.lineTo(padL + w, y);
    ctx.stroke();
    ctx.fillText(fmtRate(max * (1 - g / 4)), 4, y + 4);
  }
  for (let g = 0; g <= 5; g++) {
    const x = padL + (w * g) / 5;
    const t = t0 + (WINDOW_SECONDS * g) / 5;
    ctx.fillText(fmtTime(t), x - 20, cssH - 6);
  }

  const drawLine = (key, colorVar) => {
    ctx.strokeStyle = css.getPropertyValue(colorVar).trim();
    ctx.lineWidth = 1.8;
    ctx.beginPath();
    let started = false;
    for (const p of data) {
      const x = padL + ((p.t - t0) / WINDOW_SECONDS) * w;
      const y = padT + h - (Math.min(p[key] || 0, max) / max) * h;
      if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
    }
    ctx.stroke();
  };
  drawLine("rx", "--rx");
  drawLine("tx", "--tx");
}

/* ---------- events list ---------- */

async function refreshEvents() {
  try {
    const resp = await fetch("/api/v1/events?limit=50");
    if (!resp.ok) return;
    const body = await resp.json();
    const ul = document.getElementById("events");
    ul.innerHTML = "";
    for (const ev of body.events) {
      const li = document.createElement("li");
      li.innerHTML = `<span class="ts">${fmtTime(ev.ts)}</span>` +
        `<span class="${ev.level}">${ev.source}: ${ev.message}</span>`;
      ul.appendChild(li);
    }
  } catch (e) { /* transient */ }
}

/* ---------- staleness + connectivity ---------- */

function renderConnectivity() {
  const dot = document.getElementById("conn-dot");
  const text = document.getElementById("conn-text");
  dot.className = "dot " + (state.reachable ? "online" : "offline");
  const age = state.updatedAt.interfaces ? (Date.now() / 1000 - state.updatedAt.interfaces) : null;
  if (state.reachable) {
    text.textContent = "router online";
  } else {
    text.textContent = age != null ? `router unreachable · data ${Math.round(age)}s old` : "router unreachable";
  }
  const ageEl = document.getElementById("iface-age");
  if (age != null) {
    ageEl.textContent = `updated ${Math.round(age)}s ago`;
    ageEl.classList.toggle("stale", age > 15);
  }
}

/* ---------- SSE wiring ---------- */

function applyGroup(group, data, updatedAt) {
  if (updatedAt) state.updatedAt[group] = updatedAt;
  if (group === "resource") { state.resource = data; renderResource(); }
  else if (group === "health") { state.health = data; renderHealth(); }
  else if (group === "interfaces") {
    state.interfaces = data;
    recordSeries();
    renderInterfaces();
    drawChart();
  }
  else if (group === "connectivity") {
    state.reachable = data.reachable;
    if (!data.reachable) refreshEvents();
  }
  renderConnectivity();
}

function connect() {
  const es = new EventSource("/api/v1/stream");
  es.addEventListener("snapshot", (e) => {
    const snap = JSON.parse(e.data);
    state.reachable = snap.router_reachable;
    for (const [group, entry] of Object.entries(snap.groups || {})) {
      if (entry) applyGroup(group, entry.data, entry.updated_at);
    }
  });
  es.addEventListener("update", (e) => {
    const msg = JSON.parse(e.data);
    applyGroup(msg.group, msg.data, msg.updated_at);
  });
  es.onerror = () => {
    // EventSource reconnects automatically; reflect it in the header
    document.getElementById("conn-text").textContent = "reconnecting…";
    document.getElementById("conn-dot").className = "dot offline";
  };
}

connect();
refreshEvents();
setInterval(refreshEvents, 15000);
setInterval(renderConnectivity, 1000);
window.addEventListener("resize", drawChart);
