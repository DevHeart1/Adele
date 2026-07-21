# Adele Island architecture audit

Status: Phase 0 audit completed on the `feature/adele-island-home` branch. This
document describes the desktop as it exists before the Island-home migration;
it deliberately does not make the Python backend, primary window, or Adele
Cursor depend on Island.

## Current desktop architecture

```
Adele Python backend
        |
        | WebSocket messages
        v
Existing Electron main window and renderer
        |                         |
        | narrow, validated events | existing cursor/status/approval UI
        v                         v
Electron main process        Adele Cursor / overlay workspace
        |
        +-- optional Adele Island event broker
                |
                +-- isolated `islandWindow`
                +-- optional Windows bridge process
```

`main.js` starts the Python backend, owns the full-screen `mainWindow`, and
owns the tray and registered shortcuts. The existing renderer owns the user
conversation, rich results, tool approval, onboarding, and Cursor behaviour.
The Island is an optional second `BrowserWindow`; it receives a reduced event
view and can request existing actions through tightly scoped IPC. It must never
run the backend, execute tools, approve an action, or become the source of
truth for credentials.

## Current event map

The existing renderer maps backend WebSocket activity to its own states and
already mirrors these sanitized events to the main process:

| Adele source | Existing renderer state | Island event |
| --- | --- | --- |
| Push-to-talk / listening | `LISTENING` | `adele.listening.started` / stopped |
| Backend progress or thinking | `LOADING` | `adele.thinking.started` / stopped |
| Tool execution / progress | `DOING` | `adele.action.started` / updated |
| Response completion | `RESPONDING` then idle | `adele.action.completed` |
| Paused or failed task | `PAUSED` | `adele.action.failed` |
| Existing confirmation modal | Existing renderer controls it | `adele.approval.required` / resolved |

The event broker validates known event types, clamps/sanitizes text, and selects
one display state by priority. The Island may expose a **Review** action only;
the original approval modal remains the sole approval UI and authority.

## Current settings map

The encrypted Electron credential record (`credentials.enc`, protected by
Electron `safeStorage`) is the source for desktop preferences. Main process
`saveCredentials()` synchronizes only non-secret privacy/memory preferences to
`adele-data/preferences.json` for the Python backend. The existing Island
preference object is stored at `adele_island` inside the encrypted record.

There is no Island-specific credentials file. API keys, account state, and
other secrets remain unavailable to the Island renderer. The migration will use
an adapter around the existing credential read/save IPC and will normalize old
Island values rather than introducing a second store.

## Tray, shortcut, and Cursor behaviour today

The tray currently opens the existing assistant overlay, opens its existing
settings modal, restarts the Python backend, and quits the Electron app. The
main command shortcut wakes the overlay and begins listening; the settings
shortcut focuses the main window and opens the existing settings modal.

The Cursor is rendered by the existing main renderer. It follows task and
automation states and controls mouse passthrough on the primary overlay. The
Island must only publish a concise parallel presence. It must not change Cursor
geometry, automation locking, task cancellation, screenshot capture, or tool
execution.

## Current Island implementation and gaps

The current opt-in Island shell already has a separate transparent window,
event validation, media bridge framing, packaging entries, and a disabled-by-
default preference. It is not yet an Adele home: idle currently hides the
window, it uses one fixed-size pill, its UI has no Home/Activity/Settings tabs,
and the native bridge is optional and unbuilt when Rust is unavailable.

The migration therefore keeps these isolation boundaries but changes the shell
to explicit physical states:

```
sleeping -> peeking -> active -> home
    ^          |         |        |
    +----------+---------+--------+
                 deep-workspace (existing main window)
```

The visible state shown inside the physical shell is selected separately by
this precedence order:

```
approval > listening > acting > speaking > thinking > failure > success
         > notification > media > privacy > sleeping
```

## Packaging constraints and risks

* Island is Windows-only when enabled. Disabled Island must be a no-op on all
  platforms, so macOS and Linux packaging cannot require the Windows sidecar.
* `adele-island-bridge.exe` is optional at development time. Rust is not
  currently installed on this machine, so a native-sidecar build cannot be
  claimed until `cargo` is available.
* The current Electron package includes Island HTML, preload, and modules.
  Packaged sidecars must be located with `process.resourcesPath`, never a
  developer machine path.
* Passive Island updates must use `showInactive()` and never take focus. The
  Home panel may focus only after an intentional click or shortcut.
* A transparent desktop window can accidentally intercept clicks. The sleeping
  hitbox must be small and the body must restore mouse passthrough whenever the
  panel is not explicitly interactive.
* Fullscreen detection, media controls, notifications, microphone/camera
  status, and artwork are native integration work. They must fail closed and
  never prevent Adele, the tray recovery path, or the backend from starting.

## Rollback

Set `ADELE_ISLAND_ENABLED=0` or save `adele_island.enabled=false`. This stops
the optional Island window and its bridge while leaving the primary window,
Cursor, backend, approvals, settings, and automation system unchanged.
