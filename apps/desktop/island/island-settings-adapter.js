"use strict";

const { normalizePreferences } = require("./island-state");

const SETTING_KEYS = new Set([
  "enabled", "show_media", "show_notifications", "show_microphone",
  "show_camera", "hide_in_fullscreen", "hide_notification_body", "monitor",
  "monitor_mode", "selected_display", "reduced_motion", "show_sleeping_indicator",
  "vertical_offset", "blocked_notification_apps",
]);

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function safePatch(key, value) {
  if (!SETTING_KEYS.has(key)) return null;
  if (["enabled", "show_media", "show_notifications", "show_microphone", "show_camera", "hide_in_fullscreen", "hide_notification_body", "reduced_motion", "show_sleeping_indicator"].includes(key)) {
    return typeof value === "boolean" ? { [key]: value } : null;
  }
  if (["monitor", "monitor_mode", "selected_display"].includes(key)) {
    return typeof value === "string" ? { [key]: value.slice(0, 128) } : null;
  }
  if (key === "vertical_offset") return Number.isFinite(value) ? { vertical_offset: value } : null;
  if (key === "blocked_notification_apps") return Array.isArray(value) ? { [key]: value.slice(0, 100) } : null;
  return null;
}

/**
 * Keeps Island preferences in Adele's existing safeStorage-backed credential
 * record.  Its public snapshot never includes the credential object or secrets.
 */
class IslandSettingsAdapter {
  constructor({ readCredentials, writeCredentials, onChange = null } = {}) {
    this.readCredentials = typeof readCredentials === "function" ? readCredentials : () => ({});
    this.writeCredentials = typeof writeCredentials === "function" ? writeCredentials : () => false;
    this.onChange = typeof onChange === "function" ? onChange : null;
    this.listeners = new Set();
  }

  read() {
    const credentials = this.readCredentials() || {};
    return normalizePreferences(credentials.adele_island || {});
  }

  update(key, value) {
    const patch = safePatch(key, value);
    if (!patch) return { ok: false, preferences: this.read() };
    const currentCredentials = this.readCredentials() || {};
    const preferences = normalizePreferences({ ...(currentCredentials.adele_island || {}), ...patch });
    const saved = this.writeCredentials({ ...currentCredentials, adele_island: preferences });
    if (!saved) return { ok: false, preferences: this.read() };
    this._emit(preferences);
    return { ok: true, preferences };
  }

  replace(value) {
    if (!isPlainObject(value)) return { ok: false, preferences: this.read() };
    const currentCredentials = this.readCredentials() || {};
    const preferences = normalizePreferences({ ...(currentCredentials.adele_island || {}), ...value });
    const saved = this.writeCredentials({ ...currentCredentials, adele_island: preferences });
    if (!saved) return { ok: false, preferences: this.read() };
    this._emit(preferences);
    return { ok: true, preferences };
  }

  subscribe(listener) {
    if (typeof listener !== "function") return () => {};
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  _emit(preferences) {
    this.onChange?.(preferences);
    for (const listener of this.listeners) listener(preferences);
  }
}

module.exports = { IslandSettingsAdapter, SETTING_KEYS, safePatch };
