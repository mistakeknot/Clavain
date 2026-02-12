# Desktop (Tauri) Domain Profile

## Detection Signals

Primary signals (strong indicators):
- Directories: `src-tauri/`, `frontend/`, `webview/`
- Files: `tauri.conf.json`, `Cargo.toml`, `*.tsx`, `*.svelte`
- Frameworks: Tauri, Electron, Wails, Neutralinojs
- Keywords: `invoke`, `tauri_command`, `window`, `webview`, `ipc`, `menu`, `tray`, `system_tray`, `auto_update`

Secondary signals (supporting):
- Directories: `src-tauri/src/`, `public/`, `build/`
- Files: `capabilities/*.json` (Tauri v2), `icons/`, `*.icns`, `*.ico`
- Keywords: `notification`, `file_dialog`, `clipboard`, `global_shortcut`, `deep_link`, `sidecar`

## Injection Criteria

When `desktop-tauri` is detected, inject these domain-specific review bullets into each core agent's prompt.

### fd-architecture

- Check that the IPC boundary between frontend (webview) and backend (Rust/Go) is well-defined with typed command contracts
- Verify that heavy computation runs in the backend, not in the webview (JavaScript should handle UI, Rust handles processing)
- Flag frontend state that duplicates backend state without a synchronization mechanism (stale UI after backend changes)
- Check that window management (multi-window, modal dialogs) uses a centralized manager, not ad-hoc window.open calls
- Verify that the app supports headless/CLI mode for operations that don't need a GUI (batch processing, automation)

### fd-safety

- Check that Tauri command permissions use the principle of least privilege (capabilities model in v2, allowlist in v1)
- Verify that IPC commands validate all arguments from the frontend (the webview is an untrusted boundary)
- Flag filesystem access that doesn't scope to specific directories (app data dir, not arbitrary paths from frontend)
- Check that auto-update verifies signatures and uses HTTPS (tampered updates = remote code execution)
- Verify that sensitive data isn't stored in webview localStorage (accessible to any JS, including injected scripts)

### fd-correctness

- Check that IPC serialization handles edge cases (large payloads, binary data, Unicode, null values) without truncation
- Verify that window lifecycle events (close requested, focus/blur, resize) are handled in both frontend and backend
- Flag race conditions between frontend navigation and backend state (navigating away while a backend operation is pending)
- Check that file associations and deep link handlers work after installation (not just in development mode)
- Verify that the app handles missing OS features gracefully (system tray not available on all Linux DEs, notifications may be disabled)

### fd-quality

- Check that native menus follow platform conventions (macOS: app menu with Preferences/About, Windows: File/Edit/View/Help)
- Verify that keyboard shortcuts match platform expectations (Cmd on macOS, Ctrl on Windows/Linux)
- Flag web-only patterns that feel wrong on desktop (hover states instead of focus states, no drag-and-drop, no right-click menus)
- Check that the app icon and window title are set correctly for all platforms (not "localhost:3000" in the title bar)
- Verify that error dialogs use native OS dialog APIs, not in-webview modals (for critical errors like crash recovery)

### fd-performance

- Check that the webview doesn't load unnecessary web frameworks or heavy CSS libraries (desktop apps should feel light)
- Flag IPC calls in hot loops — batch operations into single commands instead of calling invoke() per item
- Verify that the backend doesn't block the main thread (Tauri commands should be async, heavy work on background threads)
- Check that app startup is fast — pre-built frontend assets, lazy-load secondary windows, show splash if >2 seconds
- Flag memory leaks from retained IPC listeners or unremoved event handlers across window navigations

### fd-user-product

- Check that the app behaves like a native desktop app (window chrome, minimize/maximize, system tray, file drag-and-drop)
- Verify that the app remembers window position, size, and state across restarts (don't reset to center of primary monitor)
- Flag missing offline capability — desktop apps should work without internet (unlike web apps, users expect this)
- Check that the app integrates with OS conventions (default browser for links, system file picker for open/save)
- Verify that first-run experience doesn't require account creation or internet connectivity for basic functionality

## Agent Specifications

These are domain-specific agents that `/flux-gen` can generate for desktop (Tauri/Electron) projects. They complement (not replace) the core fd-* agents.

### fd-ipc-bridge

Focus: Frontend-backend communication patterns, command typing, payload serialization, event streaming.

Key review areas:
- Command type safety across the IPC boundary
- Payload size and serialization efficiency
- Event subscription lifecycle management
- Error propagation from backend to frontend
- Binary data transfer patterns (streaming vs base64)

### fd-native-integration

Focus: OS-specific behavior, platform conventions, window management, system services, auto-update.

Key review areas:
- Platform-specific menu and shortcut conventions
- File association and protocol handler registration
- System tray behavior and notification delivery
- Auto-update flow with signature verification
- Installer/uninstaller correctness (clean removal, migration)
