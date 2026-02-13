/**
 * Electron Main Process
 * Creates a frameless, always-on-top, draggable overlay window.
 * Registers global shortcut Ctrl+Shift+H to toggle visibility.
 */

const { app, BrowserWindow, globalShortcut, ipcMain } = require("electron");
const path = require("path");

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
    focusable: false, // Don't steal focus
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

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
});

app.on("window-all-closed", () => {
  app.quit();
});
