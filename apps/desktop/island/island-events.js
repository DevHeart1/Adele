"use strict";

const { AdeleIslandState } = require("./island-state");

/**
 * The only route into the island renderer.  It observes Adele events; it never
 * consumes or changes the messages delivered to the primary renderer.
 */
class IslandEventBroker {
  constructor({ preferences = {}, onStateChange = null } = {}) {
    this.window = null;
    this.windowReady = false;
    this.onStateChange = typeof onStateChange === "function" ? onStateChange : null;
    this.state = new AdeleIslandState({
      preferences,
      onChange: (next) => this._handleStateChange(next),
    });
  }

  attachWindow(window) {
    this.window = window || null;
    this.windowReady = false;
    if (!window || window.isDestroyed?.()) return;
    window.webContents.once("did-finish-load", () => {
      this.windowReady = true;
      this._send(this.state.current());
    });
  }

  publish(event) {
    return this.state.dispatch(event);
  }

  setPreferences(preferences) {
    return this.state.setPreferences(preferences);
  }

  dismiss(mode) {
    return this.state.dismiss(mode);
  }

  current() {
    return this.state.current();
  }

  async runPreview() {
    if (!this.state.isEnabled()) return false;
    const originalPreferences = this.state.preferences;
    // Preview is deliberately complete even when optional live providers are
    // disabled. It uses no system data and restores the saved preferences.
    this.state.setPreferences({ ...originalPreferences, show_media: true, show_notifications: true });
    const preview = [
      ["adele.listening.started", { title: "Listening", detail: "Test preview" }],
      ["adele.thinking.started", { title: "Thinking", detail: "Test preview" }],
      ["adele.action.started", { title: "Working", detail: "Test preview", progress: 50 }],
      ["notification.received", { appName: "ADELE", title: "Test notification", detail: "This is local preview data." }],
      ["media.updated", { appName: "ADELE", title: "Preview track", subtitle: "ADELE", playing: true }],
      ["adele.action.completed", { title: "Completed", detail: "Test preview complete" }],
      ["adele.action.failed", { title: "Preview error", detail: "This is a local preview." }],
      ["adele.approval.required", { title: "Approval required", detail: "Review this test action.", approvalId: "island-preview" }],
    ];
    for (const [type, payload] of preview) {
      this.publish({ type, payload });
      await new Promise((resolve) => setTimeout(resolve, 550));
    }
    this.dismiss("approval");
    this.dismiss("error");
    this.publish({ type: "adele.listening.stopped", payload: {} });
    this.state.setPreferences(originalPreferences);
    return true;
  }

  _handleStateChange(next) {
    this._send(next);
    if (this.onStateChange) this.onStateChange(next);
  }

  _send(state) {
    if (!this.windowReady || !this.window || this.window.isDestroyed?.()) return;
    this.window.webContents.send("island:state", state);
  }
}

module.exports = { IslandEventBroker };
