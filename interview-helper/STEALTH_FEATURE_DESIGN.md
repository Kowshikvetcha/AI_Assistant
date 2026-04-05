# Stealth-Safe Feature Design Guide

This document explains how to add or modify features in `interview-helper` without breaking the app's stealth behavior during screen sharing, recording, or live interview use.

Use this file as the first reference in any future coding session before changing `frontend/` or Electron window behavior.

## Purpose

The app has two goals that must remain compatible:

1. Provide useful interview assistance features.
2. Keep helper UI, cursor behavior, and capture interactions hidden from screen-share viewers as much as the platform allows.

Future work must treat stealth as a product requirement, not a cosmetic detail.

---

## Stealth Invariants

These rules must remain true unless the user explicitly asks to change stealth behavior.

- The main overlay must remain content-protected.
- The app must assume visible on-screen UI can leak during some capture/share modes.
- Any newly added visible UI is a stealth risk until verified.
- Screen-capture flows must not leave the app permanently hidden.
- Capture overlays, cursors, and selection UIs must be treated as stealth-sensitive. 
- Any feature that changes Electron `BrowserWindow` behavior is high risk.

If a new feature conflicts with stealth, stealth wins by default.

---

## Architecture Boundaries

### 1. Backend logic is preferred

When adding capability, prefer implementing it in the backend first:

- prompt routing
- OCR processing
- LLM orchestration
- answer formatting
- state handling
- API endpoints

Backend changes are lower stealth risk than frontend window or overlay changes.

### 2. Renderer changes should be minimal

Only add renderer/UI changes when the feature truly requires user interaction.

Prefer:

- reusing existing sections
- reusing current controls
- keyboard shortcuts
- hidden/internal state

Avoid by default:

- extra floating panels
- new overlay windows
- hover-driven UI
- animated UI that may be visible in screen share
- extra visible status text

### 3. Electron main-process changes are highest risk

Changes in `frontend/main.js` can break stealth even if the rest of the app looks correct.

Treat these areas as high-risk:

- `BrowserWindow` options
- `setContentProtection(true)`
- `alwaysOnTop`
- `show()`, `hide()`, `focus()`
- screen-capture overlays
- global shortcuts
- window transparency / focusability / taskbar behavior

Do not refactor these casually.

---

## Safe Implementation Pattern

When adding a new feature, follow this order.

### Step 1: Preserve the current stealth surface

Before editing anything, identify whether the feature can be implemented using:

- backend-only changes
- an existing route or endpoint
- existing renderer sections
- an existing button or shortcut

Do not add a new window or new always-visible UI unless necessary.

### Step 2: Separate behavior from presentation

Add the feature in layers:

- backend behavior first
- renderer integration second
- Electron/window changes last

This keeps stealth-sensitive surface area small.

### Step 3: Prefer mode-based routing over UI duplication

If a feature needs different behavior for audio/text/screen, use explicit backend modes instead of cloning UI flows.

Examples:

- `input_mode="audio"`
- `input_mode="text"`
- `input_mode="screen"`

This is safer than creating multiple new windows or visible workflows.

### Step 4: Keep capture flows boring

For anything related to screen capture:

- keep the existing capture lifecycle intact
- avoid changing hide/show order unless necessary
- avoid changing selection overlay mechanics unless debugging that exact bug
- avoid adding fallback UI that becomes visible on shared screens

If capture must change, test cancel, success, and failure paths.

---

## Frontend Rules

### Allowed by default

- Reuse current answer sections
- Reuse existing input box
- Reuse current buttons if semantics remain similar
- Add backend calls behind existing controls
- Add keyboard shortcuts if they do not expose visible UI

### Require extra caution

- New control buttons
- New labels or status text
- New visible panels
- New cursor behavior
- New hover or click animations
- Anything shown during screen capture

### Avoid unless explicitly required

- New `BrowserWindow`s
- New transparent overlays
- New floating toolbars
- Debug banners visible in production UI
- UI that appears only while capturing or sharing

---

## Electron Rules

In `frontend/main.js`, do not change these unless the task explicitly requires it and you re-test stealth:

- `mainWindow.setContentProtection(true)`
- `mainWindow.setAlwaysOnTop(true, "screen-saver")`
- `skipTaskbar`
- transparency settings
- focusability
- global shortcut registration
- screen-capture selection-window lifecycle

If you must change them:

1. change one thing at a time,
2. preserve previous behavior exactly where possible,
3. test share visibility immediately after.

---

## Design Decision Checklist

Before implementing a feature, answer these questions:

1. Can this be backend-only?
2. Can this reuse existing UI instead of adding visible UI?
3. Does this require touching `frontend/main.js`?
4. Could this make text, buttons, cursor, or selection UI visible to viewers?
5. Can this use a shortcut instead of a button?
6. What happens during screen capture cancel/failure/success?
7. Does the app still restore correctly if capture is interrupted?

If any answer suggests stealth risk, redesign before coding.

---

## Mandatory Test Checklist

Any feature touching frontend or Electron must be tested against these cases.

### Basic app safety

- App launches normally
- Main overlay remains visible and interactive locally
- Start/Stop still work
- Existing answer UI still updates

### Capture safety

- Capture button works
- Hotkey capture works
- Cancel capture restores the main overlay
- Successful capture restores the main overlay
- Failed capture does not leave the app hidden

### Stealth safety

- Main overlay is not visible in the target screen-share mode
- Cursor is not visible to participants
- Button click feedback is not visible to participants
- Capture selection UI is not visible to participants, or its visibility is explicitly known and accepted
- New feature UI does not leak during sharing

### Window safety

- Main window still stays on top locally
- Settings window still works
- Minimize/close still work

---

## Recommended Future Feature Strategy

For most new features, use this strategy:

- extend backend capabilities first
- expose them through existing routes or small new endpoints
- keep the renderer changes small
- avoid modifying the Electron window model
- if a visible UX change is needed, make it optional and test it under screen share

Good examples:

- new answer mode
- improved OCR formatting
- better LLM prompts
- different output formatting
- additional backend route for a new processing mode

Higher-risk examples:

- new floating window
- new on-screen toolbar
- custom capture UX rewrite
- visible debug widgets

---

## Session Instructions for Future Coding Tools

When starting a future coding session, give the coding tool instructions like this:

> Read `STEALTH_FEATURE_DESIGN.md` first. Any feature changes must preserve stealth behavior during screen sharing. Prefer backend changes over Electron/frontend window changes. Do not alter capture-window lifecycle, content protection, cursor hiding, or always-on-top behavior unless the task explicitly requires it and you include a stealth regression check.

You can also add:

> If a new feature needs UI, reuse the existing overlay where possible. Avoid new windows or visible controls unless absolutely necessary.

---

## Current High-Risk Files

Treat these files as stealth-sensitive:

- `frontend/main.js`
- `frontend/preload.js`
- `frontend/renderer.js`
- `frontend/index.html`
- `frontend/styles.css`

Treat these as lower stealth risk:

- `backend/llm.py`
- `backend/main.py` API logic
- `backend/models.py`
- backend tests

---

## Final Rule

If a change improves functionality but introduces uncertainty about what screen-share participants can see, do not ship that change until stealth is re-tested.
