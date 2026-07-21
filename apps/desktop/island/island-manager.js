"use strict";

const path = require("node:path");
const { normalizePreferences } = require("./island-state");
const { IslandEventBroker } = require("./island-events");
const { IslandPhysicalState, PHYSICAL_STATES } = require("./island-physical-state");

const SHELL_WIDTH = 600;
const SHELL_HEIGHT = 260;
const POINTER_POLL_MS = 240;

function displayArea(display) {
  return display?.workArea || display?.bounds || { x: 0, y: 0, width: 1920, height: 1080 };
}

function displayBounds(display) {
  return display?.bounds || displayArea(display);
}

function selectedDisplay(screen, preferences = {}) {
  const preference = typeof preferences === "string" ? { monitor_mode: preferences } : (preferences || {});
  const displays = screen.getAllDisplays();
  const monitor = preference.monitor || preference.monitor_mode || "primary";
  if (monitor === "cursor") return screen.getDisplayNearestPoint(screen.getCursorScreenPoint());
  if (monitor === "selected" || preference.selected_display) {
    const requested = String(preference.selected_display || preference.monitor_mode || "");
    const display = displays.find((candidate) => String(candidate.id) === requested);
    if (display) return display;
  }
  const legacy = displays.find((candidate) => String(candidate.id) === String(monitor));
  return legacy || screen.getPrimaryDisplay();
}

function topCentreBounds(display, { width = SHELL_WIDTH, height = SHELL_HEIGHT, verticalOffset = 0, y } = {}) {
  const area = displayArea(display);
  return {
    width,
    height,
    x: Math.round(area.x + (area.width - width) / 2),
    y: Number.isFinite(y) ? Math.round(y) : Math.max(area.y + 8 + verticalOffset, 0),
  };
}

function physicalBounds(display, physicalState, preferences = {}) {
  const area = displayArea(display);
  const screenTop = displayBounds(display).y + (Number(preferences.vertical_offset) || 0);
  const sizes = {
    [PHYSICAL_STATES.SLEEPING]: { width: 240, height: 34, y: screenTop - 26 },
    [PHYSICAL_STATES.PEEKING]: { width: 430, height: 114, y: screenTop + 4 },
    [PHYSICAL_STATES.ACTIVE]: { width: 480, height: 108, y: screenTop + 8 },
    [PHYSICAL_STATES.HOME]: { width: Math.min(580, Math.max(360, area.width - 36)), height: Math.min(660, Math.max(380, area.height - 56)), y: screenTop + 8 },
  };
  const selected = sizes[physicalState] || sizes[PHYSICAL_STATES.SLEEPING];
  return topCentreBounds(display, { ...selected, verticalOffset: 0 });
}

function isActivity(state) {
  return state && state.mode && state.mode !== "sleeping";
}

/**
 * Owns Adele's optional, independent top-centre Island. The existing Adele
 * mainWindow and Cursor remain the work surface; this window is only presence
 * and home UI and never owns desktop actions or approval authority.
 */
class AdeleIslandManager {
  constructor({
    appRoot, screen, showMainWindow, reviewApproval, onBridgeCommand,
    onSubmitCommand, onStartListening, onStopListening, openAdvancedSettings,
    preferences = {}, logger = console,
  } = {}) {
    this.appRoot = appRoot;
    this.screen = screen;
    this.showMainWindow = typeof showMainWindow === "function" ? showMainWindow : () => {};
    this.reviewApproval = typeof reviewApproval === "function" ? reviewApproval : this.showMainWindow;
    this.onBridgeCommand = typeof onBridgeCommand === "function" ? onBridgeCommand : () => false;
    this.onSubmitCommand = typeof onSubmitCommand === "function" ? onSubmitCommand : () => false;
    this.onStartListening = typeof onStartListening === "function" ? onStartListening : () => false;
    this.onStopListening = typeof onStopListening === "function" ? onStopListening : () => false;
    this.openAdvancedSettings = typeof openAdvancedSettings === "function" ? openAdvancedSettings : this.showMainWindow;
    this.logger = logger;
    this.preferences = normalizePreferences(preferences);
    this.window = null;
    this.hiddenForFullscreen = false;
    this.pointerTimer = null;
    this.deepWorkspaceTimer = null;
    this.boundPosition = () => this.position();
    this.physical = new IslandPhysicalState({ onChange: () => this._syncWindow() });
    this.broker = new IslandEventBroker({
      preferences: this.preferences,
      onStateChange: (state) => this._handleActivityState(state),
    });
  }

  isEnabled() {
    return this.preferences.enabled && process.platform === "win32";
  }

  snapshot() {
    return { ...this.broker.current(), ...this.physical.current() };
  }

  updatePreferences(preferences) {
    this.preferences = normalizePreferences(preferences);
    this.broker.setPreferences(this.preferences);
    if (this.isEnabled()) this.create();
    else this.destroy();
    this._syncWindow();
    return this.preferences;
  }

  create() {
    if (!this.isEnabled() || (this.window && !this.window.isDestroyed())) return this.window;
    try {
      // Delayed loading makes state and geometry tests runnable under node:test
      // without starting Electron's native runtime.
      const { BrowserWindow } = require("electron");
      const bounds = physicalBounds(selectedDisplay(this.screen, this.preferences), PHYSICAL_STATES.SLEEPING, this.preferences);
      this.window = new BrowserWindow({
        ...bounds,
        frame: false,
        transparent: true,
        show: false,
        resizable: false,
        movable: false,
        minimizable: false,
        maximizable: false,
        closable: false,
        focusable: true,
        skipTaskbar: true,
        alwaysOnTop: true,
        backgroundColor: "#00000000",
        webPreferences: {
          preload: path.join(this.appRoot, "island", "island-preload.js"),
          contextIsolation: true,
          nodeIntegration: false,
          sandbox: true,
        },
      });
      this.window.setAlwaysOnTop(true, "floating");
      this.window.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
      this.window.setIgnoreMouseEvents(true, { forward: true });
      this.window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
      this.window.webContents.on("will-navigate", (event) => event.preventDefault());
      this.window.webContents.once("did-finish-load", () => this._syncWindow());
      this.window.on("blur", () => {
        if (this.physical.current().homeOpen) this.closeHome();
      });
      this.window.on("closed", () => {
        this.window = null;
        this.broker.windowReady = false;
      });
      this.broker.attachWindow(this.window);
      this.window.loadFile(path.join(this.appRoot, "renderer", "island", "index.html"));
      this._watchDisplays();
      this._syncWindow();
      return this.window;
    } catch (error) {
      this.logger.warn?.("[Island] Could not create optional Island window:", error?.message || "unknown error");
      this.destroy();
      return null;
    }
  }

  destroy() {
    this._unwatchDisplays();
    this._stopPointerWatch();
    if (this.deepWorkspaceTimer) clearTimeout(this.deepWorkspaceTimer);
    this.deepWorkspaceTimer = null;
    if (this.window && !this.window.isDestroyed()) this.window.destroy();
    this.window = null;
  }

  restart() {
    if (!this.isEnabled()) return false;
    this.destroy();
    this.physical.sleep();
    return Boolean(this.create());
  }

  position() {
    this._syncWindow();
    return Boolean(this.window && !this.window.isDestroyed());
  }

  publish(event) {
    if (event?.type === "system.fullscreen.changed") {
      this.setFullscreenHidden(event?.payload?.fullscreen === true);
      return true;
    }
    return this.broker.publish(event);
  }

  async preview() {
    this.create();
    return this.broker.runPreview();
  }

  setFullscreenHidden(hidden) {
    this.hiddenForFullscreen = Boolean(hidden);
    this._syncWindow();
  }

  setPointerInside(inside) {
    if (inside) this.physical.pointerEntered();
    else this.physical.pointerLeft();
    this._syncWindow();
  }

  setInternalInteraction(active) {
    this.physical.setInternalInteraction(active);
    this._syncWindow();
  }

  openHome(tab = "home") {
    if (!this.create()) return false;
    this.physical.openHome(tab);
    this._syncWindow();
    // The one permitted focus transfer: a deliberate user click, tray action,
    // or global shortcut asked to open Adele Home.
    this.window.show();
    this.window.focus();
    this._send("island:focus-home", { tab });
    return true;
  }

  closeHome() {
    this.physical.closeHome({ active: isActivity(this.broker.current()) });
    this._syncWindow();
    return true;
  }

  openAdele() {
    this.physical.enterDeepWorkspace();
    this._syncWindow();
    this.showMainWindow();
    if (this.deepWorkspaceTimer) clearTimeout(this.deepWorkspaceTimer);
    this.deepWorkspaceTimer = setTimeout(() => {
      this.deepWorkspaceTimer = null;
      this.physical.leaveDeepWorkspace({ active: isActivity(this.broker.current()) });
      this._syncWindow();
    }, 900);
    return true;
  }

  submitCommand(text) {
    const command = typeof text === "string" ? text.replace(/[\u0000-\u001f\u007f]/g, " ").trim().slice(0, 2000) : "";
    if (!command) return false;
    this.openAdele();
    return Boolean(this.onSubmitCommand(command));
  }

  startListening() {
    this.physical.showActive();
    this._syncWindow();
    return Boolean(this.onStartListening());
  }

  stopListening() {
    this.publish({ type: "adele.listening.stopped", payload: {}, timestamp: Date.now() });
    return Boolean(this.onStopListening());
  }

  async handleAction(action, payload = {}) {
    if (action === "open-main") return this.openAdele();
    if (action === "open-home") return this.openHome(payload.tab || "home");
    if (action === "close-home") return this.closeHome();
    if (action === "review-approval") {
      this.reviewApproval(String(payload.approvalId || "").slice(0, 120));
      return true;
    }
    if (action === "open-advanced-settings") {
      this.openAdvancedSettings(String(payload.section || "").slice(0, 80));
      return true;
    }
    if (["media.toggle", "media.next", "media.previous", "media.seek"].includes(action)) {
      return Boolean(await this.onBridgeCommand(action, payload));
    }
    if (action === "dismiss-notification") return this.broker.dismiss("notification");
    if (action === "dismiss-error") return this.broker.dismiss("failure");
    return false;
  }

  _handleActivityState(state) {
    if (state.mode === "sleeping") this.physical.sleep();
    else this.physical.showActive();
    this._syncWindow();
  }

  _syncWindow() {
    if (!this.window || this.window.isDestroyed()) return;
    const physical = this.physical.current().physicalState;
    if (this.hiddenForFullscreen && this.preferences.hide_in_fullscreen || physical === PHYSICAL_STATES.DEEP_WORKSPACE) {
      this.window.hide();
      this._stopPointerWatch();
      return;
    }
    const bounds = physicalBounds(selectedDisplay(this.screen, this.preferences), physical, this.preferences);
    this.window.setBounds(bounds, false);
    const interactive = physical !== PHYSICAL_STATES.SLEEPING;
    this.window.setIgnoreMouseEvents(!interactive, { forward: true });
    // Never focus for passive activity. `openHome()` explicitly focuses after
    // an intentional user action.
    this.window.showInactive();
    this._sendState();
    this._updatePointerWatch();
  }

  _sendState() {
    this._send("island:state", this.snapshot());
  }

  _send(channel, payload) {
    if (!this.window || this.window.isDestroyed() || this.window.webContents.isLoading()) return;
    this.window.webContents.send(channel, payload);
  }

  _updatePointerWatch() {
    const state = this.physical.current().physicalState;
    if (!this.window || this.window.isDestroyed() || this.hiddenForFullscreen || state === PHYSICAL_STATES.HOME || state === PHYSICAL_STATES.DEEP_WORKSPACE) {
      this._stopPointerWatch();
      return;
    }
    if (this.pointerTimer) return;
    this.pointerTimer = setInterval(() => this._pollPointer(), POINTER_POLL_MS);
    this.pointerTimer.unref?.();
    this._pollPointer();
  }

  _stopPointerWatch() {
    if (this.pointerTimer) clearInterval(this.pointerTimer);
    this.pointerTimer = null;
  }

  _pollPointer() {
    if (!this.window || this.window.isDestroyed() || !this.screen) return;
    const point = this.screen.getCursorScreenPoint();
    const state = this.physical.current().physicalState;
    const display = selectedDisplay(this.screen, this.preferences);
    const bounds = state === PHYSICAL_STATES.SLEEPING
      ? { ...physicalBounds(display, PHYSICAL_STATES.SLEEPING, this.preferences), height: 56 }
      : this.window.getBounds();
    const inside = point.x >= bounds.x && point.x <= bounds.x + bounds.width && point.y >= bounds.y && point.y <= bounds.y + bounds.height;
    if (inside) this.physical.pointerEntered();
    else this.physical.pointerLeft();
  }

  _watchDisplays() {
    this._unwatchDisplays();
    this.screen.on("display-added", this.boundPosition);
    this.screen.on("display-removed", this.boundPosition);
    this.screen.on("display-metrics-changed", this.boundPosition);
  }

  _unwatchDisplays() {
    this.screen?.removeListener?.("display-added", this.boundPosition);
    this.screen?.removeListener?.("display-removed", this.boundPosition);
    this.screen?.removeListener?.("display-metrics-changed", this.boundPosition);
  }
}

module.exports = {
  AdeleIslandManager,
  SHELL_WIDTH,
  SHELL_HEIGHT,
  POINTER_POLL_MS,
  selectedDisplay,
  topCentreBounds,
  physicalBounds,
};
