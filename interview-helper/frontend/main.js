/**
 * Electron Main Process
 * Creates a frameless, always-on-top, draggable overlay window.
 * Registers global shortcut Ctrl+Shift+H to toggle visibility.
 * Registers global shortcut Ctrl+Shift+S for screen capture.
 */

const {
  app,
  BrowserWindow,
  globalShortcut,
  ipcMain,
  dialog,
  desktopCapturer,
  screen,
} = require("electron");
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");

let mainWindow = null;
let settingsWindow = null;
let backendProcess = null;
let captureInProgress = false;

// ── Settings Storage ──

function getSettingsPath() {
  return path.join(app.getPath("userData"), "settings.json");
}

function loadSettings() {
  try {
    const p = getSettingsPath();
    if (fs.existsSync(p)) {
      return JSON.parse(fs.readFileSync(p, "utf-8"));
    }
  } catch (err) {
    console.error("Failed to load settings:", err);
  }
  return null;
}

function saveSettingsFile(settings) {
  const p = getSettingsPath();
  const dir = path.dirname(p);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  fs.writeFileSync(p, JSON.stringify(settings, null, 2), "utf-8");
}

// ── Backend Process Management ──

function getBackendExePath() {
  if (!app.isPackaged) {
    return null; // dev mode — use python directly
  }
  return path.join(process.resourcesPath, "backend", "main.exe");
}

function buildBackendEnv(settings) {
  // In packaged mode, start with a clean environment (only essential system vars)
  // to avoid leaking the builder's env vars (API keys, etc.) into the distributed app.
  // In dev mode, inherit the full environment so .env and system vars work normally.
  const env = app.isPackaged
    ? {
        PATH: process.env.PATH || "",
        SYSTEMROOT: process.env.SYSTEMROOT || "",
        TEMP: process.env.TEMP || "",
        TMP: process.env.TMP || "",
        USERPROFILE: process.env.USERPROFILE || "",
        APPDATA: process.env.APPDATA || "",
        LOCALAPPDATA: process.env.LOCALAPPDATA || "",
        PROGRAMDATA: process.env.PROGRAMDATA || "",
      }
    : { ...process.env };

  if (settings) {
    const keys = [
      "AI_PROVIDER", "AI_API_KEY", "AI_BASE_URL",
      "LLM_MODEL", "SUMMARY_MODEL", "STT_MODEL",
      "LLM_MAX_TOKENS", "WEBSOCKET_PORT", "AUDIO_CHUNK_DURATION", "LOG_LEVEL",
    ];
    for (const key of keys) {
      if (settings[key] !== undefined && settings[key] !== null && settings[key] !== "") {
        env[key] = String(settings[key]);
      }
    }
  }
  // When packaged, tell the backend where bundled Tesseract lives
  if (app.isPackaged) {
    const bundledTess = path.join(process.resourcesPath, "backend", "tesseract", "tesseract.exe");
    if (fs.existsSync(bundledTess)) {
      env.TESSERACT_CMD = bundledTess;
    }
  }
  return env;
}

function startBackend(settings) {
  stopBackend();

  const backendExe = getBackendExePath();
  const env = buildBackendEnv(settings);

  if (backendExe && fs.existsSync(backendExe)) {
    // Production: run PyInstaller-bundled exe
    backendProcess = spawn(backendExe, [], {
      env,
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
  } else {
    // Development: run Python directly
    const pythonScript = path.join(__dirname, "..", "backend", "main.py");
    backendProcess = spawn("python", [pythonScript], {
      env,
      stdio: ["ignore", "pipe", "pipe"],
      cwd: path.join(__dirname, "..", "backend"),
    });
  }

  backendProcess.stdout.on("data", (data) => {
    console.log(`[Backend] ${data.toString().trim()}`);
  });

  backendProcess.stderr.on("data", (data) => {
    console.error(`[Backend] ${data.toString().trim()}`);
  });

  backendProcess.on("exit", (code) => {
    console.log(`[Backend] Process exited with code ${code}`);
    backendProcess = null;
  });

  // Notify frontend that backend is starting
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("backend-status", "Starting backend...");
  }
}

function stopBackend() {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
}

// ── Settings Window ──

function openSettingsWindow() {
  if (settingsWindow && !settingsWindow.isDestroyed()) {
    settingsWindow.focus();
    return;
  }

  settingsWindow = new BrowserWindow({
    width: 450,
    height: 560,
    resizable: false,
    frame: false,
    transparent: false,
    parent: mainWindow,
    modal: true,
    show: false,
    backgroundColor: "#0f0f19",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  settingsWindow.loadFile("settings.html");
  settingsWindow.once("ready-to-show", () => settingsWindow.show());
  settingsWindow.on("closed", () => { settingsWindow = null; });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 480,
    height: 700,
    x: 50,
    y: 80,
    frame: false,
    transparent: true,
    type: "toolbar", // Windows: Treats window as a toolbar/dock, often hiding it from "Share Application" lists
    alwaysOnTop: true,
    resizable: true,
    skipTaskbar: true,
    focusable: true, // Required so text inputs in the overlay can receive keyboard focus
    hasShadow: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadFile("index.html");
  // Prevent window from being captured in screen shares/recordings
  mainWindow.setContentProtection(true);
  mainWindow.setAlwaysOnTop(true, "screen-saver"); // Highest priority
  mainWindow.setVisibleOnAllWorkspaces(true);

  // Aggressively keep window on top (paused during screen capture and settings)
  const topInterval = setInterval(() => {
    const paused = captureInProgress || (settingsWindow && !settingsWindow.isDestroyed());
    if (mainWindow && !mainWindow.isDestroyed() && !paused) {
      mainWindow.setAlwaysOnTop(true, "screen-saver");
      mainWindow.moveTop();
    }
  }, 1000);

  mainWindow.on("blur", () => {
    const paused = captureInProgress || (settingsWindow && !settingsWindow.isDestroyed());
    if (mainWindow && !mainWindow.isDestroyed() && !paused) {
      mainWindow.setAlwaysOnTop(true, "screen-saver");
    }
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// ── Region Selection Overlay (Two-Pass: select on pre-captured screenshot) ────
function createScreenshotSelectionWindow(screenshotBase64) {
  return new Promise((resolve) => {
    const primaryDisplay = screen.getPrimaryDisplay();
    const { width, height } = primaryDisplay.size;
    const scaleFactor = primaryDisplay.scaleFactor || 1;

    const selectionWindow = new BrowserWindow({
      x: 0,
      y: 0,
      width,
      height,
      frame: false,
      transparent: false,
      alwaysOnTop: true,
      skipTaskbar: true,
      resizable: false,
      movable: false,
      fullscreen: false,
      show: false, // Don't show until screenshot background is ready
      webPreferences: {
        contextIsolation: false,
        nodeIntegration: true,
      },
    });

    selectionWindow.setContentProtection(true);
    selectionWindow.setAlwaysOnTop(true, "screen-saver");

    // HTML is kept small — screenshot is sent via IPC after load to avoid
    // exceeding Chromium's ~2 MB data-URL navigation limit.
    // cursor:none hides the OS cursor (which screen-share captures);
    // a DOM-rendered crosshair replaces it (hidden by setContentProtection).
    const selectionHTML = `
    <!DOCTYPE html>
    <html>
    <head>
    <style>
      * { margin: 0; padding: 0; }
      html, body {
        width: 100vw; height: 100vh; overflow: hidden;
        cursor: none;
        user-select: none;
        -webkit-app-region: no-drag;
        background: #000;
        background-size: cover;
        background-repeat: no-repeat;
        background-position: center center;
      }
      #veil {
        position: absolute;
        top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(0, 0, 0, 0.15);
        pointer-events: none;
      }
      #crosshair {
        position: absolute;
        pointer-events: none;
        z-index: 9999;
        display: none;
      }
      #crosshair::before, #crosshair::after {
        content: '';
        position: absolute;
        background: #fff;
        box-shadow: 0 0 3px rgba(0,0,0,0.7);
      }
      #crosshair::before {
        width: 2px; height: 24px;
        left: 50%; top: 50%;
        transform: translate(-50%, -50%);
      }
      #crosshair::after {
        height: 2px; width: 24px;
        left: 50%; top: 50%;
        transform: translate(-50%, -50%);
      }
      #selection {
        position: absolute;
        border: 2px dashed #fff;
        background: rgba(124, 106, 255, 0.15);
        pointer-events: none;
        display: none;
      }
      #hint {
        position: absolute;
        top: 50%; left: 50%;
        transform: translate(-50%, -50%);
        color: #fff;
        font-family: 'Inter', -apple-system, sans-serif;
        font-size: 18px;
        text-shadow: 0 2px 8px rgba(0,0,0,0.8);
        pointer-events: none;
      }
    </style>
    </head>
    <body>
      <div id="veil"></div>
      <div id="crosshair"></div>
      <div id="hint">Drag to select a region &middot; Press Escape to cancel</div>
      <div id="selection"></div>
      <script>
        const { ipcRenderer } = require("electron");
        const sel = document.getElementById("selection");
        const hint = document.getElementById("hint");
        const crosshair = document.getElementById("crosshair");
        const scaleFactor = ${scaleFactor};
        let startX = 0, startY = 0, dragging = false;

        // Receive screenshot from main process and set as background
        ipcRenderer.on("set-screenshot", (event, base64) => {
          document.body.style.backgroundImage =
            'url("data:image/png;base64,' + base64 + '")';
          ipcRenderer.send("screenshot-ready");
        });

        // Track mouse to position custom crosshair
        document.addEventListener("mousemove", (e) => {
          crosshair.style.display = "block";
          crosshair.style.left = e.clientX + "px";
          crosshair.style.top = e.clientY + "px";

          if (!dragging) return;
          const x = Math.min(e.clientX, startX);
          const y = Math.min(e.clientY, startY);
          const w = Math.abs(e.clientX - startX);
          const h = Math.abs(e.clientY - startY);
          sel.style.left = x + "px";
          sel.style.top = y + "px";
          sel.style.width = w + "px";
          sel.style.height = h + "px";
        });

        document.addEventListener("mousedown", (e) => {
          startX = e.clientX;
          startY = e.clientY;
          dragging = true;
          hint.style.display = "none";
          sel.style.display = "block";
          sel.style.left = startX + "px";
          sel.style.top = startY + "px";
          sel.style.width = "0px";
          sel.style.height = "0px";
        });

        document.addEventListener("mouseup", (e) => {
          if (!dragging) return;
          dragging = false;
          const x = Math.min(e.clientX, startX);
          const y = Math.min(e.clientY, startY);
          const w = Math.abs(e.clientX - startX);
          const h = Math.abs(e.clientY - startY);
          if (w > 10 && h > 10) {
            ipcRenderer.send("selection-result", {
              x: Math.round(x * scaleFactor),
              y: Math.round(y * scaleFactor),
              width: Math.round(w * scaleFactor),
              height: Math.round(h * scaleFactor),
            });
          } else {
            ipcRenderer.send("selection-result", null);
          }
        });

        document.addEventListener("keydown", (e) => {
          if (e.key === "Escape") {
            ipcRenderer.send("selection-result", null);
          }
        });
      </script>
    </body>
    </html>`;

    selectionWindow.loadURL(
      `data:text/html;charset=utf-8,${encodeURIComponent(selectionHTML)}`
    );

    // Once HTML is loaded, send the screenshot via IPC and show after it's set
    selectionWindow.webContents.on("did-finish-load", () => {
      selectionWindow.webContents.send("set-screenshot", screenshotBase64);
    });

    ipcMain.once("screenshot-ready", () => {
      if (!selectionWindow.isDestroyed()) {
        selectionWindow.show();
        // Re-apply after show() — calling before show on a hidden window
        // may not persist on all Windows versions
        selectionWindow.setContentProtection(true);
        selectionWindow.setAlwaysOnTop(true, "screen-saver");
        selectionWindow.focus();
      }
    });

    let settled = false;
    const settle = (value) => {
      if (settled) return;
      settled = true;
      ipcMain.removeAllListeners("screenshot-ready");
      resolve(value);
    };

    ipcMain.once("selection-result", (event, rect) => {
      settle(rect); // resolve BEFORE destroy so the "closed" handler is a no-op
      if (!selectionWindow.isDestroyed()) {
        selectionWindow.destroy();
      }
    });

    selectionWindow.on("closed", () => {
      settle(null); // only fires if user closed the window without selecting
    });
  });
}

// ── IPC: Screen Capture (Two-Pass: capture first, then select on screenshot) ──
ipcMain.handle("capture-screen", async () => {
  captureInProgress = true;

  // Temporarily hide the main overlay so it doesn't appear in the capture
  const wasVisible = mainWindow && mainWindow.isVisible();
  if (wasVisible) {
    mainWindow.hide();
  }

  try {
    // Brief pause so the OS finishes hiding the main window
    await new Promise((r) => setTimeout(r, 150));

    // Step 1: Capture the full screen BEFORE showing any overlay
    const primaryDisplay = screen.getPrimaryDisplay();
    const scaleFactor = primaryDisplay.scaleFactor || 1;
    const sources = await desktopCapturer.getSources({
      types: ["screen"],
      thumbnailSize: {
        width: primaryDisplay.size.width * scaleFactor,
        height: primaryDisplay.size.height * scaleFactor,
      },
    });

    if (!sources || sources.length === 0) {
      return null;
    }

    const source = sources[0];
    const fullImage = source.thumbnail;
    const screenshotBase64 = fullImage.toPNG().toString("base64");

    // Step 2: Show selection overlay with the captured screenshot as background
    const rect = await createScreenshotSelectionWindow(screenshotBase64);

    if (!rect) {
      return null; // User cancelled
    }

    // Step 3: Crop from the already-captured image (no second capture needed)
    const cropped = fullImage.crop(rect);
    const base64 = cropped.toPNG().toString("base64");

    return base64;
  } finally {
    // Restore main overlay visibility and re-apply protection
    if (wasVisible && mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.show();
      mainWindow.setContentProtection(true);
      mainWindow.setAlwaysOnTop(true, "screen-saver");
    }
    captureInProgress = false;
  }
});

// ── IPC: Settings ──

ipcMain.handle("get-settings", () => {
  return loadSettings() || {};
});

ipcMain.handle("save-settings", (event, settings) => {
  saveSettingsFile(settings);
  // Restart backend with new settings
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("backend-status", "Restarting backend...");
  }
  startBackend(settings);
  // Close settings window
  if (settingsWindow && !settingsWindow.isDestroyed()) {
    settingsWindow.close();
  }
  return { success: true };
});

ipcMain.on("close-settings", () => {
  if (settingsWindow && !settingsWindow.isDestroyed()) {
    settingsWindow.close();
  }
});

ipcMain.on("open-settings", () => {
  openSettingsWindow();
});

ipcMain.handle("get-backend-port", () => {
  const settings = loadSettings();
  return (settings && settings.WEBSOCKET_PORT) || 8765;
});

app.whenReady().then(() => {
  createWindow();

  // Load settings and start backend
  const settings = loadSettings();
  if (settings && settings.AI_API_KEY) {
    startBackend(settings);
  }

  // Register global shortcut: Ctrl+Shift+H to toggle visibility
  const ret = globalShortcut.register("CommandOrControl+Shift+H", () => {
    if (mainWindow) {
      if (mainWindow.isVisible()) {
        mainWindow.hide();
      } else {
        mainWindow.show();
        mainWindow.focus();
      }
    }
  });

  if (!ret) {
    console.warn("Failed to register global shortcut Ctrl+Shift+H");
  }

  // Register global shortcut: Ctrl+Shift+S for screen capture
  const ret2 = globalShortcut.register("CommandOrControl+Shift+S", () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send("trigger-screen-capture");
    }
  });

  if (!ret2) {
    console.warn("Failed to register global shortcut Ctrl+Shift+S");
  }
});

// IPC: Window dragging
ipcMain.on("window-drag-start", () => {
  // No-op, handled by CSS -webkit-app-region: drag
});

// IPC: Minimize / close
ipcMain.on("window-minimize", () => {
  if (mainWindow) mainWindow.minimize();
});

ipcMain.on("window-close", () => {
  if (mainWindow) mainWindow.close();
});

// IPC: Resume file selection
ipcMain.handle("select-resume-file", async () => {
  const result = await dialog.showOpenDialog({
    title: "Select Resume",
    filters: [
      { name: "Resume Files", extensions: ["pdf", "txt"] },
      { name: "All Files", extensions: ["*"] },
    ],
    properties: ["openFile"],
  });

  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }

  const filePath = result.filePaths[0];
  const fileBuffer = fs.readFileSync(filePath);
  const fileName = path.basename(filePath);

  return {
    buffer: fileBuffer.toString("base64"),
    name: fileName,
  };
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
});

app.on("before-quit", () => {
  stopBackend();
});

app.on("window-all-closed", () => {
  stopBackend();
  app.quit();
});
