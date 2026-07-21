const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("overlayAPI", {
  hideWindow: () => ipcRenderer.invoke("overlay:hide"),
  minimizeWindow: () => ipcRenderer.invoke("window:minimize"),
  toggleMaximizeWindow: () => ipcRenderer.invoke("window:maximize-toggle"),
  closeWindow: () => ipcRenderer.invoke("window:close"),
  isWindowMaximized: () => ipcRenderer.invoke("window:is-maximized"),
  setOnboardingMode: (active) => ipcRenderer.invoke("window:set-onboarding-mode", Boolean(active)),
  setAutomationLock: (active) => ipcRenderer.invoke("window:set-automation-lock", Boolean(active)),
  onWindowMaximizedChange: (handler) => {
    const wrapped = (_, isMaximized) => handler(isMaximized);
    ipcRenderer.on("window:maximized-change", wrapped);
    return () => ipcRenderer.removeListener("window:maximized-change", wrapped);
  },
  onWindowModeChange: (handler) => {
    const wrapped = (_, mode) => handler(mode);
    ipcRenderer.on("window:mode-change", wrapped);
    return () => ipcRenderer.removeListener("window:mode-change", wrapped);
  },
  enableMouse: () => ipcRenderer.send("enable-mouse"),
  disableMouse: () => ipcRenderer.send("disable-mouse"),
  onStartListening: (handler) => {
    ipcRenderer.on("start-listening", handler);
    return () => ipcRenderer.removeListener("start-listening", handler);
  },
  onPushToTalkChange: (handler) => {
    const wrapped = (_, active) => handler(Boolean(active));
    ipcRenderer.on("ptt:change", wrapped);
    return () => ipcRenderer.removeListener("ptt:change", wrapped);
  },
  onAdeleShow: (handler) => {
    const wrapped = () => handler();
    ipcRenderer.on("adele:show", wrapped);
    return () => ipcRenderer.removeListener("adele:show", wrapped);
  },
  onOverlayHidden: (handler) => {
    ipcRenderer.on("overlay-hidden", handler);
    return () => ipcRenderer.removeListener("overlay-hidden", handler);
  },
  logError: (msg) => ipcRenderer.send("log-error", msg),
  logInfo: (msg) => ipcRenderer.send("log-info", msg),
  openExternal: (url) => ipcRenderer.invoke("app:open-external", url),
  openCodexAuthUrl: (url) => ipcRenderer.invoke("auth:open-codex-url", url),

  // ── Auth / Credentials ──
  loadCredentials: () => ipcRenderer.invoke("auth:load-credentials"),
  saveCredentials: (creds) => ipcRenderer.invoke("auth:save-credentials", creds),
  generateUserId: () => ipcRenderer.invoke("auth:generate-user-id"),
  clearCredentials: () => ipcRenderer.invoke("auth:clear-credentials"),
  isFirstLaunch: () => ipcRenderer.invoke("auth:is-first-launch"),

  // ── App info ──
  getVersion: () => ipcRenderer.invoke("app:get-version"),
  isPackaged: () => ipcRenderer.invoke("app:is-packaged"),
  getPlatform: () => ipcRenderer.invoke("app:get-platform"),
  getVenvPath: () => ipcRenderer.invoke("app:get-venv-path"),

  // ── Chrome Extension ──
  exportExtension: () => ipcRenderer.invoke("extension:export"),
  revealExtension: () => ipcRenderer.invoke("extension:reveal"),
  openChromeExtensions: () => ipcRenderer.invoke("extension:open-chrome-extensions"),

  // ── Backend lifecycle ──
  startBackend: () => ipcRenderer.invoke("backend:start"),
  getOllamaStatus: () => ipcRenderer.invoke("ollama:status"),
  pullOllamaModel: (modelName) => ipcRenderer.invoke("ollama:pull", modelName),
  onOllamaProgress: (handler) => {
    const wrapped = (_, text) => handler(text);
    ipcRenderer.on("ollama:progress", wrapped);
    return () => ipcRenderer.removeListener("ollama:progress", wrapped);
  },

  // ── Setup progress (setup.sh stdout forwarded from main process) ──
  onSetupProgress: (handler) => {
    const wrapped = (_, text) => handler(text);
    ipcRenderer.on("setup:progress", wrapped);
    return () => ipcRenderer.removeListener("setup:progress", wrapped);
  },

  onSettingsOpen: (handler) => {
    const wrapped = () => handler();
    ipcRenderer.on("settings:open", wrapped);
    return () => ipcRenderer.removeListener("settings:open", wrapped);
  },
  setPresenceStatus: (state, detail) => {
    ipcRenderer.send("presence:update", { state, detail });
  },
  onIslandReviewApproval: (handler) => {
    const wrapped = (_, approvalId) => handler(String(approvalId || ""));
    ipcRenderer.on("island:review-approval", wrapped);
    return () => ipcRenderer.removeListener("island:review-approval", wrapped);
  },
  onIslandSubmitCommand: (handler) => {
    const wrapped = (_, command) => handler(String(command || ""));
    ipcRenderer.on("island:submit-command", wrapped);
    return () => ipcRenderer.removeListener("island:submit-command", wrapped);
  },
  onIslandOpenSettings: (handler) => {
    const wrapped = (_, section) => handler(String(section || ""));
    ipcRenderer.on("settings:open-island", wrapped);
    return () => ipcRenderer.removeListener("settings:open-island", wrapped);
  },
  publishIslandEvent: (event) => {
    if (!event || typeof event !== "object" || Array.isArray(event)) return;
    ipcRenderer.send("island:renderer-event", event);
  },
  applyIslandPreferences: (preferences) => ipcRenderer.invoke("island:apply-preferences", preferences),
  previewIsland: () => ipcRenderer.invoke("island:preview"),
  restartBackend: () => ipcRenderer.invoke("backend:restart"),
  getBackendWsUrl: () => ipcRenderer.invoke("backend:get-ws-url"),
  getDataDirPath: () => ipcRenderer.invoke("app:get-data-dir-path"),

  // ── Auto-Updater ──
  checkForUpdates: () => ipcRenderer.invoke("updater:check"),
  downloadUpdate: () => ipcRenderer.invoke("updater:download"),
  installUpdate: () => ipcRenderer.invoke("updater:install"),
  onUpdaterStatus: (handler) => {
    const wrapped = (_, status, data) => handler(status, data);
    ipcRenderer.on("updater:status", wrapped);
    return () => ipcRenderer.removeListener("updater:status", wrapped);
  },
});
