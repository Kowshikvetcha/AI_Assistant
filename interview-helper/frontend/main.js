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

let mainWindow = null;

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

  // Aggressively keep window on top
  const topInterval = setInterval(() => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.setAlwaysOnTop(true, "screen-saver");
      mainWindow.moveTop();
    }
  }, 1000);

  mainWindow.on("blur", () => {
    // Re-assert always on top
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.setAlwaysOnTop(true, "screen-saver");
    }
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// ── Region Selection Overlay ──────────────────────────────────────────
function createSelectionWindow() {
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
      transparent: true,
      alwaysOnTop: true,
      skipTaskbar: true,
      resizable: false,
      movable: false,
      fullscreen: false,
      webPreferences: {
        contextIsolation: false,
        nodeIntegration: true,
      },
    });

    selectionWindow.setContentProtection(true);
    selectionWindow.setAlwaysOnTop(true, "screen-saver");

    const selectionHTML = `
    <!DOCTYPE html>
    <html>
    <head>
    <style>
      * { margin: 0; padding: 0; }
      html, body {
        width: 100vw; height: 100vh; overflow: hidden;
        background: rgba(0, 0, 0, 0.3);
        cursor: crosshair;
        user-select: none;
        -webkit-app-region: no-drag;
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
      <div id="hint">Drag to select a region &middot; Press Escape to cancel</div>
      <div id="selection"></div>
      <script>
        const { ipcRenderer } = require("electron");
        const sel = document.getElementById("selection");
        const hint = document.getElementById("hint");
        const scaleFactor = ${scaleFactor};
        let startX = 0, startY = 0, dragging = false;

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

        document.addEventListener("mousemove", (e) => {
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

    let settled = false;
    const settle = (value) => {
      if (settled) return;
      settled = true;
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

// ── IPC: Screen Capture ───────────────────────────────────────────────
ipcMain.handle("capture-screen", async () => {
  // Temporarily hide the main overlay so it doesn't appear in the capture
  const wasVisible = mainWindow && mainWindow.isVisible();
  if (wasVisible) {
    mainWindow.hide();
  }

  try {
    // Show region selection overlay
    const rect = await createSelectionWindow();

    if (!rect) {
      return null; // User cancelled
    }

    // Brief pause so the OS finishes removing the selection overlay from screen
    await new Promise((r) => setTimeout(r, 150));

    // Capture the screen
    const sources = await desktopCapturer.getSources({
      types: ["screen"],
      thumbnailSize: {
        width: screen.getPrimaryDisplay().size.width * (screen.getPrimaryDisplay().scaleFactor || 1),
        height: screen.getPrimaryDisplay().size.height * (screen.getPrimaryDisplay().scaleFactor || 1),
      },
    });

    if (!sources || sources.length === 0) {
      return null;
    }

    // Use the primary display source
    const source = sources[0];
    const fullImage = source.thumbnail;

    // Crop to the selected region
    const cropped = fullImage.crop(rect);
    const base64 = cropped.toPNG().toString("base64");

    return base64;
  } finally {
    // Restore main overlay visibility
    if (wasVisible && mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.show();
      mainWindow.setAlwaysOnTop(true, "screen-saver");
    }
  }
});

app.whenReady().then(() => {
  createWindow();

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

app.on("window-all-closed", () => {
  app.quit();
});
