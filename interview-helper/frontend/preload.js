/**
 * Preload script — bridges main and renderer processes securely.
 */

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
    minimizeWindow: () => ipcRenderer.send("window-minimize"),
    closeWindow: () => ipcRenderer.send("window-close"),
    selectResumeFile: () => ipcRenderer.invoke("select-resume-file"),
});
