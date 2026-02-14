/**
 * Electron Main Process
 * Creates a frameless, always-on-top, draggable overlay window.
 * Registers global shortcut Ctrl+Shift+H to toggle visibility.
 */

const { app, BrowserWindow, globalShortcut, ipcMain, dialog } = require("electron");
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
