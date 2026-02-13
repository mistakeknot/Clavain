# Mobile App Domain Profile

## Detection Signals

Primary signals (strong indicators):
- Directories: `ios/`, `android/`, `screens/`, `navigation/`, `app/`
- Files: `*.swift`, `*.kt`, `*.dart`, `Podfile`, `build.gradle`, `pubspec.yaml`, `app.json`, `Info.plist`, `AndroidManifest.xml`
- Frameworks: React Native, Flutter, SwiftUI, UIKit, Jetpack Compose, Expo, Capacitor, Ionic
- Keywords: `navigation`, `screen`, `gesture`, `touch`, `push_notification`, `deep_link`, `app_lifecycle`, `offline_first`

Secondary signals (supporting):
- Directories: `assets/`, `res/`, `components/`, `stores/`
- Files: `*.xib`, `*.storyboard`, `Fastfile`, `Appfile`, `google-services.json`
- Keywords: `foreground`, `background`, `suspend`, `memory_warning`, `accessibility`, `localization`

## Injection Criteria

When `mobile-app` is detected, inject these domain-specific review bullets into each core agent's prompt.

### fd-architecture

- Check that navigation graph is declarative and centralized, not scattered imperative push/pop calls across screens
- Verify that platform-specific code is isolated behind interfaces (don't scatter `if iOS` checks through shared logic)
- Flag missing offline architecture — if the app requires network, check graceful degradation; if offline-first, check sync strategy
- Check that state management doesn't force full-screen rebuilds (granular subscriptions for list items, form fields)
- Verify that the data layer separates local persistence, caching, and remote API concerns

### fd-safety

- Check that sensitive data (tokens, PII) is stored in Keychain/Keystore, not SharedPreferences/UserDefaults/AsyncStorage
- Verify that deep link handlers validate incoming URLs before navigating (malicious deep links shouldn't bypass auth)
- Flag certificate pinning absence for API communication (MITM risk on public WiFi)
- Check that biometric authentication has proper fallback (PIN/password) and doesn't cache auth state insecurely
- Verify that debug/logging doesn't write sensitive data to device logs (visible via adb logcat, Console.app)

### fd-correctness

- Check that app lifecycle callbacks handle state restoration correctly (coming back from background shouldn't lose user work)
- Verify that concurrent network requests and UI updates don't cause race conditions (stale data displayed after navigation)
- Flag missing error handling for platform permission denials (camera, location, notifications — denied ≠ crashed)
- Check that scroll position, form input, and selection state survive configuration changes (rotation, split-screen)
- Verify that push notification handling covers all states (foreground, background, terminated — different code paths)

### fd-quality

- Check that accessibility labels are present on interactive elements (VoiceOver/TalkBack must be navigable)
- Verify consistent spacing, typography, and color usage from a design system (not ad-hoc magic numbers per screen)
- Flag hardcoded strings — all user-visible text should be in localization files, even for single-language apps
- Check that platform conventions are followed (iOS: swipe-to-go-back, Android: system back button handling)
- Verify that loading/error/empty states are handled for every data-dependent screen (not just the happy path)

### fd-performance

- Check that images are appropriately sized and cached (don't download full-res photos for thumbnail lists)
- Flag expensive operations on the main/UI thread (network calls, JSON parsing, large list sorting, file IO)
- Verify that list rendering uses recycling (RecyclerView, LazyColumn, FlatList) not eager rendering of all items
- Check that app startup time is profiled — cold start should show content within 2 seconds on mid-range devices
- Flag memory leaks from retained listeners, closures capturing view controllers, or unremoved observers

### fd-user-product

- Check that the app provides meaningful feedback for every user action (tap → visual response within 100ms)
- Verify that onboarding can be skipped or deferred — don't gate core functionality behind a 5-screen tutorial
- Flag missing haptic/tactile feedback on destructive actions (delete, send, purchase)
- Check that error recovery is possible without restarting the app (network retry, form re-submission, undo)
- Verify that the app respects system settings (dark mode, text size, reduced motion, power saving)

## Agent Specifications

These are domain-specific agents that `/flux-gen` can generate for mobile app projects. They complement (not replace) the core fd-* agents.

### fd-platform-integration

Focus: OS-specific lifecycle, permissions, deep linking, notifications, background processing.

Persona: You are a mobile app lifecycle specialist — you think about what happens when the app backgrounds, the network drops, the OS kills your process, and the user rotates their device mid-animation.

Decision lens: Prefer fixes that prevent data loss on lifecycle events over fixes that improve navigation speed. Users forgive slow loads but not lost work.

Key review areas:
- Check lifecycle transitions handle pause, resume, and terminate correctly, and restore critical state on relaunch.
- Verify permissions are requested at point of need with clear fallback behavior when denied.
- Validate deep and universal links route to correct screens with secure parameter validation.
- Confirm push payloads are handled correctly in foreground, background, and terminated states.
- Ensure background tasks respect platform scheduling limits and complete within allowed execution windows.

### fd-mobile-ux

Focus: Touch interaction, accessibility, responsive layout, animation performance, gesture handling.

Persona: You are a mobile UX reviewer — you ensure the app feels native on each platform, respects OS conventions, and doesn't fight the system.

Decision lens: Prefer platform-idiomatic solutions over cross-platform abstractions when they conflict with native behavior. Users notice when an app doesn't feel right.

Key review areas:
- Check interactive targets meet minimum size requirements (44pt iOS and 48dp Android) on supported screens.
- Verify screen-reader order, labels, and actions are complete for all interactive views.
- Validate layouts adapt correctly across supported device sizes, orientations, and safe areas.
- Confirm critical animations maintain target frame rate and monitor jank against defined thresholds.
- Ensure gesture recognizers resolve conflicts predictably between scroll, swipe, and drag interactions.
