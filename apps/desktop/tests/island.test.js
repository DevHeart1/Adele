"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { AdeleIslandState, normalizePreferences } = require("../island/island-state");
const { parseBridgeLines } = require("../island/island-native-bridge");
const { IslandPhysicalState } = require("../island/island-physical-state");
const { IslandSettingsAdapter } = require("../island/island-settings-adapter");
const { selectedDisplay, topCentreBounds, physicalBounds } = require("../island/island-manager");

function enabledState(t, preferences = {}) {
  const state = new AdeleIslandState({ preferences: { enabled: true, ...preferences } });
  t.after(() => state.clear());
  return state;
}

test("island is disabled by default and ignores external events", () => {
  const state = new AdeleIslandState();
  assert.equal(state.dispatch({ type: "adele.listening.started", payload: {} }), false);
  assert.equal(state.current().mode, "sleeping");
});

test("higher priority notification temporarily replaces media and media restores on dismissal", (t) => {
  const state = enabledState(t, { show_media: true, show_notifications: true });
  state.dispatch({ type: "media.updated", payload: { title: "Track", playing: true } });
  assert.equal(state.current().mode, "media");
  state.dispatch({ type: "notification.received", payload: { appName: "Mail", title: "Inbox", detail: "Hello" } });
  assert.equal(state.current().mode, "notification");
  assert.equal(state.dismiss("notification"), true);
  assert.equal(state.current().mode, "media");
});

test("approval remains visible until it resolves even after a completion state", (t) => {
  const state = enabledState(t);
  state.dispatch({ type: "adele.approval.required", payload: { approvalId: "approval-1" } });
  state.dispatch({ type: "adele.action.completed", payload: { title: "Done" } });
  assert.equal(state.current().mode, "approval");
  state.dispatch({ type: "adele.approval.resolved", payload: { approvalId: "approval-1" } });
  assert.equal(state.current().mode, "success");
});

test("error is retained until dismissed", (t) => {
  const state = enabledState(t);
  state.dispatch({ type: "adele.action.failed", payload: { detail: "Could not complete" } });
  assert.equal(state.current().mode, "failure");
  assert.equal(state.dismiss("error"), true);
  assert.equal(state.current().mode, "sleeping");
});

test("invalid event names and payloads are rejected", (t) => {
  const state = enabledState(t);
  assert.equal(state.dispatch({ type: "unknown.event", payload: {} }), false);
  assert.equal(state.dispatch({ type: "media.updated", payload: "not an object" }), false);
  assert.equal(state.current().mode, "sleeping");
});

test("privacy settings and notification privacy are normalized", () => {
  const prefs = normalizePreferences({ enabled: "yes", show_notifications: true, hide_notification_body: true, blocked_notification_apps: [" Banking ", 1] });
  assert.equal(prefs.enabled, false);
  assert.equal(prefs.show_notifications, true);
  assert.deepEqual(prefs.blocked_notification_apps, ["banking"]);
});

test("native bridge parser handles partial and malformed newline-delimited JSON", () => {
  const valid = JSON.stringify({ version: 1, type: "media.updated", payload: { title: "Song", playing: true }, timestamp: 1 });
  const partial = parseBridgeLines("", `${valid.slice(0, 30)}`);
  assert.equal(partial.messages.length, 0);
  const completed = parseBridgeLines(partial.remainder, `${valid.slice(30)}\nnot-json\n`);
  assert.equal(completed.messages.length, 1);
  assert.equal(completed.messages[0].type, "media.updated");
});

test("native bridge parser rejects wrong protocol versions and unknown events", () => {
  const payload = [
    JSON.stringify({ version: 2, type: "media.updated", payload: {}, timestamp: 1 }),
    JSON.stringify({ version: 1, type: "malicious.event", payload: {}, timestamp: 1 }),
  ].join("\n");
  assert.equal(parseBridgeLines("", `${payload}\n`).messages.length, 0);
});

test("island placement uses the selected display work area", () => {
  const primary = { id: 1, workArea: { x: 0, y: 0, width: 1920, height: 1040 } };
  const cursor = { id: 2, workArea: { x: 1920, y: 0, width: 2560, height: 1400 } };
  const screen = {
    getAllDisplays: () => [primary, cursor],
    getPrimaryDisplay: () => primary,
    getCursorScreenPoint: () => ({ x: 2300, y: 20 }),
    getDisplayNearestPoint: () => cursor,
  };
  assert.equal(selectedDisplay(screen, "cursor"), cursor);
  assert.deepEqual(topCentreBounds(cursor), { width: 600, height: 260, x: 2900, y: 8 });
  assert.equal(selectedDisplay(screen, { monitor: "selected", selected_display: "2" }), cursor);
  assert.deepEqual(physicalBounds(cursor, "sleeping", {}), { width: 240, height: 34, x: 3080, y: -26 });
});

test("sleeping reveals only after intentional hover and cancels when the pointer leaves", async () => {
  const machine = new IslandPhysicalState({ hoverDelayMs: 12, exitDelayMs: 12 });
  machine.pointerEntered();
  machine.pointerLeft();
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(machine.current().physicalState, "sleeping");
  machine.pointerEntered();
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(machine.current().physicalState, "peeking");
  machine.pointerLeft();
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(machine.current().physicalState, "sleeping");
  machine.dispose();
});

test("home remains open during interaction and Escape-equivalent close restores active or sleeping", () => {
  const machine = new IslandPhysicalState({ hoverDelayMs: 0, exitDelayMs: 0 });
  machine.openHome("settings");
  machine.pointerLeft();
  machine.setInternalInteraction(true);
  assert.equal(machine.current().physicalState, "home");
  assert.equal(machine.current().homeTab, "settings");
  machine.closeHome({ active: true });
  assert.equal(machine.current().physicalState, "active");
  machine.closeHome({ active: false });
  assert.equal(machine.current().physicalState, "sleeping");
  machine.dispose();
});

test("settings adapter uses Adele credentials without exposing secrets and normalizes legacy values", () => {
  let credentials = { elevenlabs_api_key: "secret", adele_island: { enabled: true, monitor_mode: "cursor" } };
  const adapter = new IslandSettingsAdapter({
    readCredentials: () => credentials,
    writeCredentials: (next) => { credentials = next; return true; },
  });
  const snapshot = adapter.read();
  assert.equal(snapshot.monitor, "cursor");
  assert.equal(Object.hasOwn(snapshot, "elevenlabs_api_key"), false);
  const result = adapter.update("hide_notification_body", false);
  assert.equal(result.ok, true);
  assert.equal(credentials.elevenlabs_api_key, "secret");
  assert.equal(credentials.adele_island.hide_notification_body, false);
  assert.equal(adapter.update("elevenlabs_api_key", "nope").ok, false);
});
