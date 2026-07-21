"use strict";

const api = window.adeleIsland;
const island = document.getElementById("island");
const surface = document.getElementById("surface");
const title = document.getElementById("presence-title");
const detail = document.getElementById("presence-detail");
const progress = document.getElementById("presence-progress");
const progressValue = progress.querySelector("span");
const privacy = document.getElementById("privacy-indicators");
const homePanel = document.getElementById("home-panel");
const askForm = document.getElementById("ask-form");
const askInput = document.getElementById("ask-input");
const taskLabel = document.getElementById("task-label");
const taskTitle = document.getElementById("task-title");
const taskDetail = document.getElementById("task-detail");
const reviewApproval = document.getElementById("review-approval");
const dismissState = document.getElementById("dismiss-state");
const taskActions = document.getElementById("task-actions");
const mediaControls = document.getElementById("media-controls");
const activityList = document.getElementById("activity-list");
const tabs = ["home", "activity", "settings"];
const activity = [];
let current = { mode: "sleeping", physicalState: "sleeping" };
let preferences = {};

function setHidden(element, hidden) {
  element.classList.toggle("hidden", Boolean(hidden));
}

function safeText(value, fallback = "") {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function addActivity(state) {
  const entry = {
    title: safeText(state.title, "Adele"),
    detail: safeText(state.detail || state.subtitle, "Updated"),
    mode: safeText(state.mode, "sleeping"),
    at: Date.now(),
  };
  const previous = activity[0];
  if (previous && previous.title === entry.title && previous.detail === entry.detail && previous.mode === entry.mode) return;
  activity.unshift(entry);
  activity.splice(8);
  activityList.textContent = "";
  for (const item of activity) {
    const li = document.createElement("li");
    const strong = document.createElement("strong");
    const copy = document.createElement("span");
    strong.textContent = item.title;
    copy.textContent = item.detail;
    li.append(strong, copy);
    activityList.append(li);
  }
}

function setTab(tab) {
  const next = tabs.includes(tab) ? tab : "home";
  for (const name of tabs) {
    const button = document.getElementById(`tab-${name}`);
    const panel = document.getElementById(`panel-${name}`);
    const active = name === next;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
    setHidden(panel, !active);
  }
}

function renderPrivacy(state) {
  privacy.textContent = "";
  const indicators = [];
  if (state.microphone) indicators.push("Mic active");
  if (state.camera) indicators.push("Camera active");
  for (const label of indicators) {
    const indicator = document.createElement("span");
    indicator.className = "privacy-dot";
    indicator.title = label;
    indicator.setAttribute("aria-label", label);
    privacy.append(indicator);
  }
}

function render(state) {
  current = state && typeof state === "object" ? state : current;
  const mode = safeText(current.mode, "sleeping").toLowerCase();
  const physical = safeText(current.physicalState, "sleeping").toLowerCase();
  island.className = `island mode-${mode} physical-${physical}`;
  title.textContent = safeText(current.title, "ADELE");
  detail.textContent = safeText(current.detail || current.subtitle, "Ready when you are");
  surface.setAttribute("aria-label", `${title.textContent}. ${detail.textContent}. Open Adele Home`);
  setHidden(progress, !Number.isFinite(current.progress));
  if (Number.isFinite(current.progress)) progressValue.style.width = `${Math.max(0, Math.min(100, current.progress))}%`;
  renderPrivacy(current);

  const homeOpen = physical === "home";
  setHidden(homePanel, !homeOpen);
  taskLabel.textContent = mode === "sleeping" ? "ADELE IS READY" : mode.toUpperCase();
  taskTitle.textContent = safeText(current.title, mode === "sleeping" ? "What can I help with?" : "Adele is working");
  taskDetail.textContent = safeText(current.detail || current.subtitle, "Ask a question or start a task.");
  const approval = mode === "approval";
  const dismissible = mode === "failure" || mode === "notification";
  setHidden(taskActions, !(approval || dismissible));
  setHidden(reviewApproval, !approval);
  setHidden(dismissState, !dismissible);
  setHidden(mediaControls, mode !== "media");
  document.getElementById("media-toggle").textContent = current.playing ? "Pause" : "Play";
  addActivity(current);
}

function renderSettings(next) {
  preferences = next && typeof next === "object" ? next : preferences;
  const mapping = {
    "setting-enabled": "enabled", "setting-media": "show_media", "setting-notifications": "show_notifications",
    "setting-hide-body": "hide_notification_body", "setting-microphone": "show_microphone",
    "setting-camera": "show_camera", "setting-fullscreen": "hide_in_fullscreen",
    "setting-reduced-motion": "reduced_motion", "setting-sleeping": "show_sleeping_indicator",
  };
  for (const [id, key] of Object.entries(mapping)) document.getElementById(id).checked = preferences[key] === true;
  document.getElementById("setting-monitor").value = preferences.monitor === "cursor" ? "cursor" : "primary";
  island.classList.toggle("reduced-motion", preferences.reduced_motion === true);
}

async function updateSetting(key, value) {
  const result = await api.updateSetting(key, value);
  if (result?.ok && result.preferences) renderSettings(result.preferences);
}

surface.addEventListener("click", () => { void api.openHome("home"); });
document.getElementById("close-home").addEventListener("click", () => { void api.closeHome(); });
document.getElementById("open-adele").addEventListener("click", () => { void api.openAdele(); });
document.getElementById("activity-open-adele").addEventListener("click", () => { void api.openAdele(); });
document.getElementById("ask-microphone").addEventListener("click", () => { void api.startListening(); });
document.getElementById("review-approval").addEventListener("click", () => { void api.openApproval(current.approvalId || ""); });
document.getElementById("dismiss-state").addEventListener("click", () => { void api.dismiss(current.mode); });
document.getElementById("media-previous").addEventListener("click", () => { void api.mediaPrevious(); });
document.getElementById("media-toggle").addEventListener("click", () => { void api.mediaToggle(); });
document.getElementById("media-next").addEventListener("click", () => { void api.mediaNext(); });
document.getElementById("restart-island").addEventListener("click", () => { void api.restartIsland(); });
document.getElementById("advanced-settings").addEventListener("click", () => { void api.openAdvancedSettings("island"); });

askForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = askInput.value.trim();
  if (!text) return askInput.focus();
  const accepted = await api.submitCommand(text);
  if (accepted) askInput.value = "";
});

for (const name of tabs) {
  document.getElementById(`tab-${name}`).addEventListener("click", () => setTab(name));
}

const settingBindings = {
  "setting-enabled": "enabled", "setting-media": "show_media", "setting-notifications": "show_notifications",
  "setting-hide-body": "hide_notification_body", "setting-microphone": "show_microphone",
  "setting-camera": "show_camera", "setting-fullscreen": "hide_in_fullscreen",
  "setting-reduced-motion": "reduced_motion", "setting-sleeping": "show_sleeping_indicator",
};
for (const [id, key] of Object.entries(settingBindings)) {
  document.getElementById(id).addEventListener("change", (event) => { void updateSetting(key, event.target.checked); });
}
document.getElementById("setting-monitor").addEventListener("change", (event) => { void updateSetting("monitor", event.target.value); });

for (const target of [surface, homePanel]) {
  target.addEventListener("pointerenter", () => api.setPointerInside(true));
  target.addEventListener("pointerleave", () => api.setPointerInside(false));
}
homePanel.addEventListener("focusin", () => api.setInternalInteraction(true));
homePanel.addEventListener("focusout", () => api.setInternalInteraction(false));
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && current.physicalState === "home") {
    event.preventDefault();
    void api.closeHome();
  }
});

api.subscribeState(render);
api.subscribeHome((payload) => {
  const tab = payload?.tab || "home";
  setTab(tab);
  requestAnimationFrame(() => (tab === "home" ? askInput : document.getElementById(`tab-${tab}`)).focus());
});

Promise.all([api.getState(), api.getSettings()]).then(([state, settings]) => {
  render(state);
  renderSettings(settings);
}).catch(() => {});
render(current);
