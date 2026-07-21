"use strict";

/**
 * State-only model for Adele Island.  This file has no Electron dependency so
 * it can be exercised with node:test and so a failed island window never
 * affects Adele's primary window.
 */
const DEFAULT_ISLAND_PREFERENCES = Object.freeze({
  enabled: false,
  show_media: true,
  show_notifications: false,
  show_microphone: true,
  show_camera: true,
  hide_in_fullscreen: true,
  hide_notification_body: true,
  monitor: "primary",
  monitor_mode: "primary",
  selected_display: "",
  reduced_motion: false,
  show_sleeping_indicator: true,
  vertical_offset: 0,
  blocked_notification_apps: [],
});

const MODE_PRIORITY = Object.freeze({
  sleeping: 0,
  privacy: 10,
  media: 20,
  notification: 30,
  success: 40,
  failure: 50,
  thinking: 60,
  speaking: 70,
  acting: 80,
  listening: 90,
  approval: 100,
});

const VALID_EVENT_TYPES = new Set([
  "adele.listening.started", "adele.listening.stopped",
  "adele.thinking.started", "adele.thinking.stopped",
  "adele.speaking.started", "adele.speaking.stopped",
  "adele.activity.idle",
  "adele.action.started", "adele.action.updated", "adele.action.completed", "adele.action.failed",
  "adele.approval.required", "adele.approval.resolved",
  "media.updated", "media.stopped",
  "notification.received", "notification.dismissed",
  "privacy.microphone.active", "privacy.microphone.inactive",
  "privacy.camera.active", "privacy.camera.inactive",
  "system.fullscreen.changed",
]);

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function cleanText(value, maxLength = 180) {
  if (typeof value !== "string") return "";
  return value.replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim().slice(0, maxLength);
}

function normalizePreferences(value = {}) {
  const candidate = isPlainObject(value) ? value : {};
  const legacyMonitor = cleanText(candidate.monitor_mode, 128);
  const requestedMonitor = cleanText(candidate.monitor, 32);
  const selectedDisplay = cleanText(candidate.selected_display, 128);
  const monitor = ["primary", "cursor", "selected"].includes(requestedMonitor)
    ? requestedMonitor
    : (legacyMonitor === "cursor" ? "cursor" : ((selectedDisplay || /^\d+$/.test(legacyMonitor)) ? "selected" : "primary"));
  const normalizedSelectedDisplay = selectedDisplay || (monitor === "selected" && /^\d+$/.test(legacyMonitor) ? legacyMonitor : "");
  return {
    ...DEFAULT_ISLAND_PREFERENCES,
    enabled: candidate.enabled === true,
    show_media: candidate.show_media !== false,
    show_notifications: candidate.show_notifications === true,
    show_microphone: candidate.show_microphone !== false,
    show_camera: candidate.show_camera !== false,
    hide_in_fullscreen: candidate.hide_in_fullscreen !== false,
    hide_notification_body: candidate.hide_notification_body !== false,
    monitor,
    monitor_mode: monitor === "selected" ? (normalizedSelectedDisplay || "primary") : monitor,
    selected_display: normalizedSelectedDisplay,
    reduced_motion: candidate.reduced_motion === true,
    show_sleeping_indicator: candidate.show_sleeping_indicator !== false,
    vertical_offset: Number.isFinite(candidate.vertical_offset)
      ? Math.max(-100, Math.min(100, Math.round(candidate.vertical_offset)))
      : 0,
    blocked_notification_apps: Array.isArray(candidate.blocked_notification_apps)
      ? candidate.blocked_notification_apps.map((item) => cleanText(item, 80).toLowerCase()).filter(Boolean).slice(0, 100)
      : [],
  };
}

function normalizedEvent(raw) {
  if (!isPlainObject(raw) || !VALID_EVENT_TYPES.has(raw.type) || !isPlainObject(raw.payload ?? {})) return null;
  const payload = raw.payload || {};
  const createdAt = Number.isFinite(raw.timestamp) ? raw.timestamp : Date.now();
  return {
    type: raw.type,
    createdAt,
    payload: {
      title: cleanText(payload.title || payload.task || payload.appName, 120),
      subtitle: cleanText(payload.subtitle || payload.artist || payload.appName, 120),
      detail: cleanText(payload.detail || payload.message || payload.body, 240),
      appName: cleanText(payload.appName, 80),
      taskId: cleanText(payload.taskId, 120),
      approvalId: cleanText(payload.approvalId, 120),
      notificationId: cleanText(payload.notificationId || payload.id, 120),
      progress: Number.isFinite(payload.progress) ? Math.max(0, Math.min(100, Math.round(payload.progress))) : undefined,
      playing: payload.playing === true,
      microphone: payload.microphone === true,
      camera: payload.camera === true,
    },
  };
}

class AdeleIslandState {
  constructor({ preferences = {}, onChange = null, clock = () => Date.now() } = {}) {
    this.clock = clock;
    this.preferences = normalizePreferences(preferences);
    this.onChange = typeof onChange === "function" ? onChange : null;
    this.slots = new Map();
    this.expiryTimers = new Map();
    this.lastState = this.current();
  }

  setPreferences(preferences) {
    this.preferences = normalizePreferences(preferences);
    this._emit();
    return this.preferences;
  }

  isEnabled() {
    return this.preferences.enabled;
  }

  dispatch(raw) {
    const event = normalizedEvent(raw);
    if (!event || !this.isEnabled()) return false;
    const { type, payload, createdAt } = event;

    if (type === "adele.listening.started") this._put("adele", this._state("listening", payload, createdAt));
    if (type === "adele.listening.stopped") this._remove("adele");
    if (type === "adele.activity.idle") this._remove("adele");
    if (type === "adele.thinking.started") this._put("adele", this._state("thinking", payload, createdAt));
    if (type === "adele.thinking.stopped") this._remove("adele");
    if (type === "adele.speaking.started") this._put("adele", this._state("speaking", payload, createdAt));
    if (type === "adele.speaking.stopped") this._remove("adele");
    if (type === "adele.action.started" || type === "adele.action.updated") this._put("adele", this._state("acting", payload, createdAt));
    if (type === "adele.action.completed") {
      this._remove("adele");
      this._put("adele-result", this._state("success", payload, createdAt), 3500);
    }
    if (type === "adele.action.failed") {
      this._remove("adele");
      this._put("adele-error", this._state("failure", payload, createdAt));
    }
    if (type === "adele.approval.required") this._put("approval", this._state("approval", payload, createdAt));
    if (type === "adele.approval.resolved") this._remove("approval");
    if (type === "media.updated") {
      if (this.preferences.show_media && payload.playing) this._put("media", this._state("media", payload, createdAt));
      else this._remove("media");
    }
    if (type === "media.stopped") this._remove("media");
    if (type === "notification.received") {
      const blocked = this.preferences.blocked_notification_apps.includes(payload.appName.toLowerCase());
      if (this.preferences.show_notifications && !blocked) {
        const detail = this.preferences.hide_notification_body ? "New notification" : payload.detail;
        this._put("notification", this._state("notification", { ...payload, detail }, createdAt), 4500);
      }
    }
    if (type === "notification.dismissed") this._remove("notification");
    if (type === "privacy.microphone.active") {
      if (this.preferences.show_microphone) this._put("microphone", this._state("privacy", { ...payload, microphone: true }, createdAt));
    }
    if (type === "privacy.microphone.inactive") this._remove("microphone");
    if (type === "privacy.camera.active") {
      if (this.preferences.show_camera) this._put("camera", this._state("privacy", { ...payload, camera: true }, createdAt));
    }
    if (type === "privacy.camera.inactive") this._remove("camera");

    this._emit();
    return true;
  }

  dismiss(mode) {
    const keys = { notification: "notification", error: "adele-error", failure: "adele-error", approval: "approval" };
    if (!keys[mode]) return false;
    this._remove(keys[mode]);
    this._emit();
    return true;
  }

  clear() {
    for (const timer of this.expiryTimers.values()) clearTimeout(timer);
    this.expiryTimers.clear();
    this.slots.clear();
    this._emit();
  }

  current() {
    const entries = [...this.slots.values()];
    if (!entries.length) {
      return { mode: "sleeping", priority: MODE_PRIORITY.sleeping, title: "ADELE", subtitle: "Ready", createdAt: this.clock() };
    }
    return entries.sort((a, b) => b.priority - a.priority || b.createdAt - a.createdAt)[0];
  }

  _state(mode, payload, createdAt) {
    return {
      mode,
      priority: MODE_PRIORITY[mode],
      title: payload.title || this._titleFor(mode),
      subtitle: payload.subtitle,
      detail: payload.detail,
      appName: payload.appName,
      taskId: payload.taskId,
      approvalId: payload.approvalId,
      notificationId: payload.notificationId,
      progress: payload.progress,
      playing: payload.playing,
      microphone: payload.microphone,
      camera: payload.camera,
      createdAt,
    };
  }

  _titleFor(mode) {
    return ({ listening: "Listening", thinking: "Thinking", speaking: "Speaking", acting: "Working", success: "Completed", failure: "Needs attention", approval: "Approval required", media: "Now playing", notification: "Notification", privacy: "Privacy active" })[mode] || "ADELE";
  }

  _put(key, state, expiryMs = 0) {
    this._remove(key);
    this.slots.set(key, state);
    if (expiryMs > 0) {
      this.expiryTimers.set(key, setTimeout(() => {
        this._remove(key);
        this._emit();
      }, expiryMs));
    }
  }

  _remove(key) {
    const timer = this.expiryTimers.get(key);
    if (timer) clearTimeout(timer);
    this.expiryTimers.delete(key);
    this.slots.delete(key);
  }

  _emit() {
    const next = this.current();
    const changed = JSON.stringify(next) !== JSON.stringify(this.lastState);
    this.lastState = next;
    if (changed && this.onChange) this.onChange({ ...next });
  }
}

module.exports = {
  AdeleIslandState,
  DEFAULT_ISLAND_PREFERENCES,
  MODE_PRIORITY,
  VALID_EVENT_TYPES,
  normalizePreferences,
  normalizedEvent,
};
