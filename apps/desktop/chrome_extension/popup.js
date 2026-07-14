const SOCKET = {
  CONNECTING: 0,
  OPEN: 1,
  CLOSING: 2,
  CLOSED: 3,
};

function socketLabel(state) {
  const labels = {
    [SOCKET.CONNECTING]: "Connecting",
    [SOCKET.OPEN]: "Open",
    [SOCKET.CLOSING]: "Closing",
    [SOCKET.CLOSED]: "Closed",
  };
  return labels[state] ?? String(state ?? "—");
}

function shortUrl(url) {
  const value = String(url || "").trim();
  if (!value) return "—";
  if (value.length <= 42) return value;
  return `${value.slice(0, 39)}…`;
}

function setText(id, value, className = "") {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = value ?? "—";
  if (className) {
    el.className = `value ${className}`.trim();
  }
}

function setVisible(id, visible) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.toggle("hidden", !visible);
}

function deriveState(status) {
  const socketState = status?.socketState ?? SOCKET.CLOSED;
  const authenticated = !!status?.authenticated;
  const hasError = !!(status?.lastBridgeError || "").trim();

  if (authenticated && socketState === SOCKET.OPEN) {
    return "connected";
  }
  if (socketState === SOCKET.CONNECTING) {
    return "connecting";
  }
  if (socketState === SOCKET.OPEN && !authenticated) {
    return "handshake";
  }
  if (hasError || socketState === SOCKET.CLOSED) {
    return "disconnected";
  }
  return "connecting";
}

function renderBanner(state, status) {
  const banner = document.getElementById("statusBanner");
  const dot = document.getElementById("statusDot");
  const title = document.getElementById("bannerTitle");
  const sub = document.getElementById("bannerSub");

  banner.className = "banner";
  dot.className = "status-dot";

  if (state === "connected") {
    banner.classList.add("ok");
    dot.classList.add("ok");
    title.textContent = "Connected to ADELE";
    sub.textContent = "Browser snapshots and actions are available to the desktop agent.";
    return;
  }

  if (state === "connecting" || state === "handshake") {
    banner.classList.add("warn");
    dot.classList.add("warn");
    title.textContent = state === "handshake" ? "Finishing handshake…" : "Connecting…";
    sub.textContent = status?.lastBridgeMessage || `Opening ${status?.bridgeUrl || "the bridge"}…`;
    return;
  }

  banner.classList.add("bad");
  dot.classList.add("bad");
  title.textContent = "Backend not reachable";
  sub.textContent =
    status?.lastBridgeError ||
    "Nothing is listening on the bridge port. Start the ADELE app or local_server.py.";
}

function renderStatus(status) {
  const state = deriveState(status);
  renderBanner(state, status);

  setVisible("helpCard", state === "disconnected");

  const ok = state === "connected";
  setText(
    "bridgeStatus",
    ok ? "Connected" : state === "handshake" ? "Handshaking" : "Disconnected",
    ok ? "ok" : state === "connecting" || state === "handshake" ? "warn" : "bad",
  );
  setText("bridgeUrl", status?.bridgeUrl || "ws://127.0.0.1:8765", "mono");
  setText("socketState", socketLabel(status?.socketState), ok ? "ok" : "");

  const err = (status?.lastBridgeError || "").trim();
  setVisible("errorRow", !!err);
  setText("lastError", err || "—", err ? "bad" : "");

  const tabHint = (status?.lastBridgeHint || status?.activeTabHint || "").trim();
  const hintEl = document.getElementById("tabHint");
  if (hintEl) {
    if (ok && tabHint) {
      hintEl.innerHTML = `<strong>Tip:</strong> ${tabHint}`;
      hintEl.classList.remove("hidden");
    } else if (ok && status?.activeTabCapturable === false) {
      hintEl.innerHTML = "<strong>Tip:</strong> Open a normal https:// website tab before capturing.";
      hintEl.classList.remove("hidden");
    } else {
      hintEl.textContent = "";
      hintEl.classList.add("hidden");
    }
  }

  setText("activeTabUrl", shortUrl(status?.activeTabUrl), "mono");

  const snapshotBtn = document.getElementById("snapshotBtn");
  if (snapshotBtn) {
    const canCapture = ok && (status?.activeTabCapturable !== false);
    snapshotBtn.disabled = !canCapture;
    if (!ok) {
      snapshotBtn.title = "Connect the bridge before capturing a tab snapshot.";
    } else if (status?.activeTabCapturable === false) {
      snapshotBtn.title = tabHint || "Switch to a normal https:// tab first.";
    } else {
      snapshotBtn.title = "";
    }
  }

  setText("snapshotCount", String(status?.snapshotCount ?? 0));

  const snapshot = status?.latestSnapshot || null;
  const hasSnapshot = !!snapshot;
  setText("latestUrl", snapshot?.url ? shortUrl(snapshot.url) : "—", "mono");
  setText("latestTitle", snapshot?.title || "—");
  setText("elementCount", snapshot?.elements ? String(snapshot.elements.length) : "—");

  setVisible("snapshotEmpty", !hasSnapshot);
  const meta = document.getElementById("snapshotMeta");
  if (meta) {
    if (!hasSnapshot) {
      meta.textContent = "";
      meta.classList.add("hidden");
    } else {
      meta.textContent = [
        `generation ${snapshot.generation}`,
        `tab ${snapshot.tab_id}`,
        `session ${snapshot.session_id}`,
      ].join(" · ");
      meta.classList.remove("hidden");
    }
  }

  const updated = document.getElementById("lastUpdated");
  if (updated) {
    updated.textContent = `Updated ${new Date().toLocaleTimeString()}`;
  }
}

async function loadStatus() {
  const status = await chrome.runtime.sendMessage({ type: "adele_get_status" });
  renderStatus(status);
  return status;
}

async function requestSnapshot() {
  const result = await chrome.runtime.sendMessage({ type: "adele_request_snapshot" });
  renderStatus(result);
}

async function reconnectBridge() {
  await chrome.runtime.sendMessage({ type: "adele_reconnect_bridge" });
  await loadStatus();
}

let refreshTimer = null;

function startAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(() => {
    loadStatus().catch(() => {});
  }, 2000);
}

document.getElementById("refreshBtn")?.addEventListener("click", () => loadStatus());
document.getElementById("snapshotBtn")?.addEventListener("click", () => requestSnapshot());
document.getElementById("reconnectBtn")?.addEventListener("click", () => reconnectBridge());
document.getElementById("openSettings")?.addEventListener("click", (event) => {
  event.preventDefault();
  chrome.runtime.openOptionsPage();
});

document.addEventListener("DOMContentLoaded", () => {
  loadStatus();
  startAutoRefresh();
});

window.addEventListener("unload", () => {
  if (refreshTimer) clearInterval(refreshTimer);
});
