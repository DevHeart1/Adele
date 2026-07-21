# Adele Island

Adele Island is an optional Windows-only home at the top centre of a display.
It is Adele's calm home for status, commands, short activity, pending approvals,
and non-secret Island preferences. Adele Cursor remains an independent movable
workspace presence while Adele helps on screen.

Island does not replace the main Adele window. The existing window continues to
own onboarding, conversation, rich results, approvals, tool execution,
verification, settings, and the Python backend.

## Architecture

```text
Adele Python backend
        |
        v
Electron main process
        |
        |-- Existing mainWindow
        |     |-- Conversations, onboarding, approvals, rich results
        |     `-- Adele Cursor and automation workspace
        |
        |-- Adele Island event broker
        |     `-- isolated islandWindow
        |           |-- Sleeping / peeking / activity / Home
        |           |-- Activity and Island settings
        |           `-- narrow, local-only preload API
        |
        `-- optional adele-island-bridge.exe
              `-- Windows media controls
```

The Island is a separate local `BrowserWindow` with context isolation, Node
integration disabled, sandboxed preload, denied navigation, denied popups, and
narrow validated IPC. It never receives API keys, ChatGPT credentials, browser
data, raw screenshots, or unrestricted filesystem access.

## Physical states

```text
sleeping -- intentional hover --> peeking -- task event --> active
   ^              |                |                       |
   |              +-- leave -------+                       +-- click --> home
   +--------------------------- close / complete <--------------------+
                                      |
                                      +-- Open full Adele --> deep workspace
```

- **Sleeping** rests partly behind the top display edge, remains click-through,
  and uses a deliberately small hover zone.
- **Peeking** reveals after an intentional hover without focus.
- **Active** shows concise task, approval, media, or privacy status without
  taking focus from the current app.
- **Home** opens only after an intentional click, tray action, or shortcut.
- **Deep workspace** briefly hides Island while the existing work surface opens.

Passive updates use `showInactive()` and never call `focus()`. The only focus
transfer is the user explicitly opening Home. Compact passive bounds minimise
the possible hitbox; unused body regions are mouse-passthrough.

## Event contract

The existing renderer mirrors a reduced, sanitized event to the main process.
The broker accepts only Adele listening/thinking/speaking/action/approval/idle,
media, notification, microphone/camera privacy, and fullscreen-change events.
Text is length-limited and control characters are removed before display.

```text
approval > listening > acting > speaking > thinking > failure > success
         > notification > media > privacy > sleeping
```

An approval is only surfaced. **Review approval** re-opens the existing Adele
approval UI; Island cannot approve an action or execute a desktop tool.

## Home, Activity, and Settings

Home shows the current task, a pending-approval affordance, supported media
controls, a microphone button, and **Ask Adele**. Submitted text is forwarded
to the existing quick-command path, preserving its model routing, plans,
approvals, and verification.

Activity is a short in-memory Island session timeline, not a second conversation
database. Island preferences remain in Adele's existing safeStorage-backed
`adele_island` settings object. The Island renderer sees normalized non-secret
preferences only. Existing Adele settings remain available through **Advanced
Settings** during migration.

Preferences include the feature toggle, media/notifications/microphone/camera,
notification content privacy, fullscreen hiding, monitor selection, reduced
motion, sleeping indicator, vertical offset, and blocked notification apps.
Legacy `monitor_mode` values are normalized; an unavailable selected display
falls back to the primary display.

## Tray, shortcuts, and rollback

When disabled, Island is a no-op and the existing tray and shortcut behaviour is
unchanged. When enabled, the tray offers Open Adele, Island Settings, Restart
Island, Restart Backend, Open Diagnostics, and Quit. The normal Adele shortcut
opens Home and the settings shortcut opens Home's Settings tab. Both fall back
to the existing UI when Island is disabled.

Enable for a development launch with:

```powershell
$env:ADELE_ISLAND_ENABLED = "1"
npm.cmd start
```

Rollback is immediate with `ADELE_ISLAND_ENABLED=0` or
`adele_island.enabled=false`. Stopping the bridge or removing Island modules
does not change the backend, main window, Cursor, approvals, settings, or
automation.

## Native bridge and packaging

`adele-island-bridge.exe` is optional, crash-isolated, and uses validated
newline-delimited JSON. Electron ignores malformed data and retries a crashed
bridge after 1, 3, and 10 seconds without interrupting Adele.

The current helper implements Windows Global System Media Transport controls.
Notification ingestion, microphone/camera status, and reliable fullscreen
detection are unavailable until their Windows APIs are implemented and
validated; no synthetic system data is sent to Adele or a model.

Build it on Windows with Rust installed:

```powershell
cd apps/desktop
npm.cmd run build:island:win
npm.cmd run prepare:island:win
npm.cmd run build:win
```

JavaScript development and non-Windows packaging do not require Rust. Packaged
builds resolve the optional executable from `process.resourcesPath`.

## Accessibility, privacy, and troubleshooting

Home has labelled controls, visible focus styles, logical tab order, Escape to
close, tooltips, and reduced-motion support. Notifications are opt-in and their
body is hidden by default. The test preview uses local sample events only and
does not request permissions or inspect system data.

- No Island: verify Windows and the feature toggle or environment flag.
- No media controls: the optional helper is missing or no media session exists.
- Panel blocking a click: press Escape to close Home; sleeping mode is
  click-through.
- Use **Open Diagnostics** in the tray for current backend and bridge status.

## Lumen attribution

The state broker, priority model, and native-boundary concepts are independently
informed by Risuleia/Lumen at commit
`5df6802ca489251ec78e28f7a7188290cf527bde`. No Lumen source, artwork, Slint
component, or binary is included. Lumen is MIT-licensed; see
[`THIRD_PARTY_NOTICES.md`](../../../THIRD_PARTY_NOTICES.md).
