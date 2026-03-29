/**
 * Preload script — bridges main and renderer processes securely.
 */

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
    minimizeWindow: () => ipcRenderer.send("window-minimize"),
    closeWindow: () => ipcRenderer.send("window-close"),
    selectResumeFile: () => ipcRenderer.invoke("select-resume-file"),
    captureScreen: (rect) => ipcRenderer.invoke("capture-screen", rect),
    onTriggerScreenCapture: (callback) => ipcRenderer.on("trigger-screen-capture", callback),
    // Settings
    getSettings: () => ipcRenderer.invoke("get-settings"),
    saveSettings: (settings) => ipcRenderer.invoke("save-settings", settings),
    closeSettings: () => ipcRenderer.send("close-settings"),
    openSettings: () => ipcRenderer.send("open-settings"),
    // Backend lifecycle
    onBackendStatus: (callback) => ipcRenderer.on("backend-status", (_, status) => callback(status)),
    getBackendPort: () => ipcRenderer.invoke("get-backend-port"),
});
