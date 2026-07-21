"use strict";

/**
 * The physical state of the Island is intentionally independent from the
 * activity displayed in it.  Keeping this small state machine Electron-free
 * makes accidental focus/click-through regressions testable without a desktop.
 */
const PHYSICAL_STATES = Object.freeze({
  SLEEPING: "sleeping",
  PEEKING: "peeking",
  ACTIVE: "active",
  HOME: "home",
  DEEP_WORKSPACE: "deep-workspace",
});

class IslandPhysicalState {
  constructor({ hoverDelayMs = 420, exitDelayMs = 650, onChange = null, setTimer = setTimeout, clearTimer = clearTimeout } = {}) {
    this.hoverDelayMs = Math.max(0, Number(hoverDelayMs) || 0);
    this.exitDelayMs = Math.max(0, Number(exitDelayMs) || 0);
    this.onChange = typeof onChange === "function" ? onChange : null;
    this.setTimer = setTimer;
    this.clearTimer = clearTimer;
    this.state = PHYSICAL_STATES.SLEEPING;
    this.homeTab = "home";
    this.pointerInside = false;
    this.internalInteraction = false;
    this.hoverTimer = null;
    this.exitTimer = null;
  }

  current() {
    return {
      physicalState: this.state,
      homeOpen: this.state === PHYSICAL_STATES.HOME,
      homeTab: this.homeTab,
      pointerInside: this.pointerInside,
    };
  }

  pointerEntered() {
    this.pointerInside = true;
    this._clearExit();
    if (this.state !== PHYSICAL_STATES.SLEEPING) return this.current();
    this._clearHover();
    this.hoverTimer = this.setTimer(() => {
      this.hoverTimer = null;
      if (this.pointerInside && this.state === PHYSICAL_STATES.SLEEPING) this._set(PHYSICAL_STATES.PEEKING);
    }, this.hoverDelayMs);
    return this.current();
  }

  pointerLeft() {
    this.pointerInside = false;
    this._clearHover();
    if (this.state === PHYSICAL_STATES.HOME || this.internalInteraction) return this.current();
    if (this.state === PHYSICAL_STATES.PEEKING || this.state === PHYSICAL_STATES.ACTIVE) {
      this._scheduleSleep();
    }
    return this.current();
  }

  setInternalInteraction(active) {
    this.internalInteraction = Boolean(active);
    if (this.internalInteraction) this._clearExit();
    else if (!this.pointerInside && this.state !== PHYSICAL_STATES.HOME) this._scheduleSleep();
    return this.current();
  }

  showActive() {
    this._clearHover();
    this._clearExit();
    if (this.state !== PHYSICAL_STATES.HOME && this.state !== PHYSICAL_STATES.DEEP_WORKSPACE) this._set(PHYSICAL_STATES.ACTIVE);
    return this.current();
  }

  openHome(tab = "home") {
    this.homeTab = ["home", "activity", "settings"].includes(tab) ? tab : "home";
    this._clearHover();
    this._clearExit();
    this._set(PHYSICAL_STATES.HOME);
    return this.current();
  }

  closeHome({ active = false } = {}) {
    this.internalInteraction = false;
    this._clearHover();
    this._clearExit();
    this._set(active ? PHYSICAL_STATES.ACTIVE : PHYSICAL_STATES.SLEEPING);
    return this.current();
  }

  sleep() {
    if (this.state === PHYSICAL_STATES.HOME) return this.current();
    this._clearHover();
    this._clearExit();
    this._set(PHYSICAL_STATES.SLEEPING);
    return this.current();
  }

  enterDeepWorkspace() {
    this._clearHover();
    this._clearExit();
    this._set(PHYSICAL_STATES.DEEP_WORKSPACE);
    return this.current();
  }

  leaveDeepWorkspace({ active = false } = {}) {
    this._set(active ? PHYSICAL_STATES.ACTIVE : PHYSICAL_STATES.SLEEPING);
    return this.current();
  }

  dispose() {
    this._clearHover();
    this._clearExit();
  }

  _scheduleSleep() {
    this._clearExit();
    this.exitTimer = this.setTimer(() => {
      this.exitTimer = null;
      if (!this.pointerInside && !this.internalInteraction && this.state !== PHYSICAL_STATES.HOME) this._set(PHYSICAL_STATES.SLEEPING);
    }, this.exitDelayMs);
  }

  _set(next) {
    if (this.state === next) return;
    this.state = next;
    this.onChange?.(this.current());
  }

  _clearHover() {
    if (this.hoverTimer) this.clearTimer(this.hoverTimer);
    this.hoverTimer = null;
  }

  _clearExit() {
    if (this.exitTimer) this.clearTimer(this.exitTimer);
    this.exitTimer = null;
  }
}

module.exports = { IslandPhysicalState, PHYSICAL_STATES };
