"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { VALID_EVENT_TYPES } = require("./island-state");

const BRIDGE_VERSION = 1;
const RESTART_DELAYS_MS = [1000, 3000, 10000];

function parseBridgeLines(buffer, chunk) {
  const combined = `${buffer || ""}${Buffer.isBuffer(chunk) ? chunk.toString("utf8") : String(chunk || "")}`;
  const lines = combined.split(/\r?\n/);
  const remainder = lines.pop() || "";
  const messages = [];
  for (const line of lines) {
    if (!line.trim()) continue;
    try {
      const message = JSON.parse(line);
      if (isValidBridgeMessage(message)) messages.push(message);
    } catch {
      // Deliberately ignore malformed sidecar data. It must never crash Adele.
    }
  }
  return { remainder: remainder.slice(0, 256 * 1024), messages };
}

function isValidBridgeMessage(message) {
  return Boolean(
    message &&
    typeof message === "object" &&
    message.version === BRIDGE_VERSION &&
    VALID_EVENT_TYPES.has(message.type) &&
    message.payload &&
    typeof message.payload === "object" &&
    !Array.isArray(message.payload) &&
    Number.isFinite(message.timestamp)
  );
}

class AdeleIslandNativeBridge {
  constructor({ appRoot, resourcesPath, packaged = false, onEvent, logger = console, spawnProcess = spawn } = {}) {
    this.appRoot = appRoot;
    this.resourcesPath = resourcesPath;
    this.packaged = packaged;
    this.onEvent = typeof onEvent === "function" ? onEvent : () => {};
    this.logger = logger;
    this.spawnProcess = spawnProcess;
    this.child = null;
    this.stdoutBuffer = "";
    this.restartCount = 0;
    this.restartTimer = null;
    this.stopping = false;
  }

  executablePath() {
    if (this.packaged) return path.join(this.resourcesPath, "adele-island-bridge.exe");
    return path.join(this.appRoot, "native", "adele-island-bridge", "target", "release", "adele-island-bridge.exe");
  }

  available() {
    return process.platform === "win32" && fs.existsSync(this.executablePath());
  }

  start() {
    if (this.child || this.stopping || !this.available()) return false;
    try {
      this.child = this.spawnProcess(this.executablePath(), [], { windowsHide: true, stdio: ["pipe", "pipe", "pipe"] });
      this.stdoutBuffer = "";
      this.child.stdout?.on("data", (chunk) => this._read(chunk));
      this.child.stderr?.on("data", () => this.logger.warn?.("[Island bridge] Native helper emitted diagnostics."));
      this.child.on("error", () => this._handleExit());
      this.child.on("exit", () => this._handleExit());
      return true;
    } catch {
      this._handleExit();
      return false;
    }
  }

  stop() {
    this.stopping = true;
    if (this.restartTimer) clearTimeout(this.restartTimer);
    this.restartTimer = null;
    const child = this.child;
    this.child = null;
    if (child && !child.killed) {
      try { child.kill(); } catch {}
    }
  }

  send(type, payload = {}) {
    if (!this.child?.stdin?.writable || !["media.toggle", "media.next", "media.previous", "media.seek"].includes(type)) return false;
    const safePayload = type === "media.seek" && Number.isFinite(payload.positionMs)
      ? { positionMs: Math.max(0, Math.floor(payload.positionMs)) }
      : {};
    try {
      this.child.stdin.write(`${JSON.stringify({ version: BRIDGE_VERSION, type, payload: safePayload, timestamp: Date.now() })}\n`);
      return true;
    } catch {
      return false;
    }
  }

  _read(chunk) {
    const parsed = parseBridgeLines(this.stdoutBuffer, chunk);
    this.stdoutBuffer = parsed.remainder;
    for (const message of parsed.messages) this.onEvent(message);
  }

  _handleExit() {
    this.child = null;
    if (this.stopping || this.restartTimer || this.restartCount >= RESTART_DELAYS_MS.length) return;
    const delay = RESTART_DELAYS_MS[this.restartCount++];
    this.restartTimer = setTimeout(() => {
      this.restartTimer = null;
      this.start();
    }, delay);
  }
}

module.exports = { AdeleIslandNativeBridge, BRIDGE_VERSION, RESTART_DELAYS_MS, isValidBridgeMessage, parseBridgeLines };
