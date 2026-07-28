/* RB5009 Monitor dashboard.
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
  routerHost: "",
  lastError: null,
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

/* A 401 means the session expired; go back to the login page. */
function handleUnauthorized(resp) {
  if (resp.status === 401) {
    window.location.replace("/login");
    return true;
  }
  return false;
}

/* Meters are driven by transform, not width: width would relayout the page on
   every frame of every update. */
function setMeter(id, percent, hotAbove) {
  const bar = document.getElementById(id);
  const value = Math.max(0, Math.min(100, percent || 0));
  bar.style.transform = `scaleX(${value / 100})`;
  bar.classList.toggle("hot", value > hotAbove);
}

async function loadInfo() {
  try {
    const resp = await fetch("/api/v1/info");
    if (handleUnauthorized(resp) || !resp.ok) return;
    const info = await resp.json();
    state.routerHost = info.router_host;
    document.getElementById("app-info").textContent =
      `v${info.version}${info.lan_mode ? " · LAN mode" : ""}`;
    if (document.getElementById("board").textContent === "—") {
      document.getElementById("board").textContent = info.router_host;
    }
    const signout = document.getElementById("signout");
    if (info.auth_enabled) {
      signout.hidden = false;
      signout.addEventListener("click", async () => {
        await fetch("/api/v1/logout", { method: "POST" });
        window.location.replace("/login");
      });
    }
  } catch (e) { /* transient */ }
}

function renderResource() {
  const r = state.resource;
  if (!r) return;
  document.getElementById("identity").textContent = r.identity || r.board_name || "—";
  document.getElementById("board").textContent = r.board_name || state.routerHost || "";
  document.getElementById("version").textContent = "RouterOS " + (r.version || "—");
  document.getElementById("uptime").textContent = fmtDuration(r.uptime_seconds);

  const load = r.cpu_load_percent;
  document.getElementById("cpu-load").textContent = load == null ? "—" : load.toFixed(0) + "%";
  document.getElementById("cpu-info").textContent =
    `${r.cpu_count || "?"} cores @ ${r.cpu_frequency_mhz || "?"} MHz`;
  setMeter("cpu-bar", load, 80);

  if (r.total_memory_bytes != null && r.free_memory_bytes != null) {
    const used = r.total_memory_bytes - r.free_memory_bytes;
    const pct = (used / r.total_memory_bytes) * 100;
    document.getElementById("mem-used").textContent = fmtBytes(used);
    document.getElementById("mem-info").textContent =
      `of ${fmtBytes(r.total_memory_bytes)} (${pct.toFixed(0)}%)`;
    setMeter("mem-bar", pct, 85);
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
    val.className = "value";
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

  // Take the size from CSS layout, so the chart follows the fluid height and
  // any browser zoom instead of a hardcoded pixel box.
  const cssW = canvas.clientWidth;
  const cssH = canvas.clientHeight;
  if (cssW === 0 || cssH === 0) return;   // hidden or not laid out yet

  // Only touch the bitmap size when it actually changed: assigning to
  // canvas.width/height clears the canvas and is not free.
  const bitmapW = Math.round(cssW * dpr), bitmapH = Math.round(cssH * dpr);
  if (canvas.width !== bitmapW || canvas.height !== bitmapH) {
    canvas.width = bitmapW;
    canvas.height = bitmapH;
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);  // absolute, so repeat draws don't compound
  ctx.clearRect(0, 0, cssW, cssH);

  // Scale the plot furniture with the root font size so it stays legible at
  // any zoom level rather than shrinking to nothing.
  const rootPx = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
  const labelPx = Math.max(9, rootPx * 0.7);
  const data = state.series.get(state.selectedIface) || [];
  const now = Date.now() / 1000;
  const t0 = now - WINDOW_SECONDS;

  let max = 1000; // min scale: 1 kbps
  for (const p of data) max = Math.max(max, p.rx || 0, p.tx || 0);
  max *= 1.15;

  const css = getComputedStyle(document.documentElement);
  ctx.strokeStyle = css.getPropertyValue("--border").trim();
  ctx.fillStyle = css.getPropertyValue("--muted").trim();
  ctx.font = `${labelPx}px system-ui, -apple-system, sans-serif`;
  ctx.lineWidth = 1;

  // Measure the axis labels rather than guessing a gutter width: a guess
  // clips the widest value (e.g. "10.6 Mbps" losing its leading digit).
  const yLabels = [];
  for (let g = 0; g <= 4; g++) yLabels.push(fmtRate(max * (1 - g / 4)));
  const labelGap = rootPx * 0.45;
  const padL = Math.max(...yLabels.map(t => ctx.measureText(t).width)) + labelGap * 2;
  const padR = rootPx * 0.6;
  const padT = rootPx * 0.6;
  const padB = labelPx * 2;
  const w = cssW - padL - padR, h = cssH - padT - padB;
  if (w <= 0 || h <= 0) return;

  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (let g = 0; g <= 4; g++) {
    const y = padT + (h * g) / 4;
    ctx.beginPath();
    ctx.moveTo(padL, y);
    ctx.lineTo(padL + w, y);
    ctx.stroke();
    ctx.fillText(yLabels[g], padL - labelGap, y);
  }

  // Thin out time labels on narrow viewports so they never collide.
  ctx.textBaseline = "alphabetic";
  const ticks = w < rootPx * 22 ? 2 : w < rootPx * 34 ? 3 : 5;
  for (let g = 0; g <= ticks; g++) {
    const x = padL + (w * g) / ticks;
    const t = t0 + (WINDOW_SECONDS * g) / ticks;
    ctx.textAlign = g === 0 ? "left" : g === ticks ? "right" : "center";
    ctx.fillText(fmtTime(t), x, cssH - labelPx * 0.4);
  }
  ctx.textAlign = "left";

  const drawLine = (key, colorVar) => {
    ctx.strokeStyle = css.getPropertyValue(colorVar).trim();
    ctx.lineWidth = Math.max(1.5, dpr >= 2 ? 1.6 : 1.8);
    ctx.lineJoin = "round";
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
    if (handleUnauthorized(resp) || !resp.ok) return;
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

/* Turn a collector error into something actionable during first-time setup. */
function connectionHint(error) {
  const e = (error || "").toLowerCase();
  if (e.includes("401") || e.includes("credential")) {
    return "Check RBMON_ROUTER_USERNAME and RBMON_ROUTER_PASSWORD.";
  }
  if (e.includes("403")) {
    return "The router refused the request. Check the monitoring user's group has the rest-api and read policies.";
  }
  if (e.includes("certificate") || e.includes("ssl") || e.includes("tls")) {
    return "TLS verification failed. Set RBMON_ROUTER_CA_FILE to the router's CA certificate.";
  }
  if (e.includes("timeout") || e.includes("timed out")) {
    return "The router did not answer in time. Check it is powered on and reachable from this PC.";
  }
  return "Check RBMON_ROUTER_URL, the monitoring credentials, and that the RouterOS www-ssl service is enabled.";
}

function renderBanner() {
  const banner = document.getElementById("banner");
  if (state.reachable) {
    banner.hidden = true;
    return;
  }
  banner.hidden = false;
  banner.innerHTML =
    `<span class="reason">Cannot reach the router${state.lastError ? ": " + escapeHtml(state.lastError) : "."}</span>` +
    `<span class="hint">${escapeHtml(connectionHint(state.lastError))}</span>`;
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

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
  renderBanner();
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
    state.lastError = data.error || null;
    if (!data.reachable) refreshEvents();
  }
  renderConnectivity();
}

function connect() {
  const es = new EventSource("/api/v1/stream");
  es.addEventListener("snapshot", (e) => {
    const snap = JSON.parse(e.data);
    state.reachable = snap.router_reachable;
    state.lastError = snap.last_error || null;
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

/* ---------- redraw triggers ----------
 * The canvas has no automatic layout, so it must be told to redraw whenever
 * its box or the device pixel ratio changes: window resize alone misses
 * container-only changes (a scrollbar appearing, the events list growing)
 * and monitor-to-monitor DPI changes. */

let redrawQueued = false;
function scheduleRedraw() {
  if (redrawQueued) return;
  redrawQueued = true;
  requestAnimationFrame(() => { redrawQueued = false; drawChart(); });
}

/* Browser zoom changes devicePixelRatio. Firefox and Safari do not always
   fire resize for it, so watch the ratio itself; the query has to be
   re-armed after each change because it only matches one exact ratio. */
function watchPixelRatio() {
  const mq = matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`);
  mq.addEventListener("change", () => { scheduleRedraw(); watchPixelRatio(); }, { once: true });
}

function initChartSizing() {
  const canvas = document.getElementById("chart");
  if (window.ResizeObserver) {
    new ResizeObserver(scheduleRedraw).observe(canvas);
  }
  window.addEventListener("resize", scheduleRedraw);
  // Fonts finish loading after first paint and change the layout metrics.
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(scheduleRedraw);
  watchPixelRatio();
  scheduleRedraw();
}

loadInfo();
connect();
refreshEvents();
initChartSizing();
setInterval(refreshEvents, 15000);
setInterval(renderConnectivity, 1000);
