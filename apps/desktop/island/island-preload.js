"use strict";

const { contextBridge, ipcRenderer } = require("electron");

const mediaActions = new Set(["media.toggle", "media.next", "media.previous", "media.seek"]);
const settings = new Set([
  "enabled", "show_media", "show_notifications", "show_microphone", "show_camera",
  "hide_in_fullscreen", "hide_notification_body", "monitor", "selected_display",
  "reduced_motion", "show_sleeping_indicator", "vertical_offset",
]);

function subscribe(channel, handler) {
  if (typeof handler !== "function") return () => {};
  const wrapped = (_event, value) => handler(value);
  ipcRenderer.on(channel, wrapped);
  return () => ipcRenderer.removeListener(channel, wrapped);
}

contextBridge.exposeInMainWorld("adeleIsland", {
  getState: () => ipcRenderer.invoke("island:get-state"),
  getSettings: () => ipcRenderer.invoke("island:get-settings"),
  subscribeState: (handler) => subscribe("island:state", handler),
  subscribeHome: (handler) => subscribe("island:focus-home", handler),
  setPointerInside: (inside) => ipcRenderer.send("island:pointer-inside", Boolean(inside)),
  setInternalInteraction: (active) => ipcRenderer.send("island:internal-interaction", Boolean(active)),
  openHome: (tab = "home") => ipcRenderer.invoke("island:open-home", String(tab || "home")),
  closeHome: () => ipcRenderer.invoke("island:close-home"),
  submitCommand: (text) => ipcRenderer.invoke("island:submit-command", typeof text === "string" ? text.slice(0, 2000) : ""),
  startListening: () => ipcRenderer.invoke("island:start-listening"),
  stopListening: () => ipcRenderer.invoke("island:stop-listening"),
  mediaToggle: () => ipcRenderer.invoke("island:action", "media.toggle", {}),
  mediaNext: () => ipcRenderer.invoke("island:action", "media.next", {}),
  mediaPrevious: () => ipcRenderer.invoke("island:action", "media.previous", {}),
  mediaSeek: (positionMs) => ipcRenderer.invoke("island:action", "media.seek", { positionMs }),
  openApproval: (approvalId) => ipcRenderer.invoke("island:action", "review-approval", { approvalId: String(approvalId || "").slice(0, 120) }),
  dismiss: (mode) => ipcRenderer.invoke("island:action", mode === "failure" ? "dismiss-error" : "dismiss-notification", {}),
  updateSetting: (key, value) => settings.has(key) ? ipcRenderer.invoke("island:update-setting", key, value) : Promise.resolve({ ok: false }),
  openAdvancedSettings: (section = "") => ipcRenderer.invoke("island:action", "open-advanced-settings", { section: String(section || "").slice(0, 80) }),
  restartIsland: () => ipcRenderer.invoke("island:restart"),
  openAdele: () => ipcRenderer.invoke("island:action", "open-main", {}),
  action: (name, payload = {}) => mediaActions.has(name) ? ipcRenderer.invoke("island:action", name, payload || {}) : Promise.resolve(false),
});
