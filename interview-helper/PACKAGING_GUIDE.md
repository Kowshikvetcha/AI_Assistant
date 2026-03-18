# Interview Helper — Complete Packaging Guide

This guide explains how to turn the Interview Helper source code into a Windows installer (`.exe`) that anyone can download and install — without needing Python or Node.js on their computer.

---

## What you are building

A standard Windows installer called:
```
Interview Helper Setup 1.0.0.exe
```

When someone runs this installer, it:
1. Installs the app to their computer (like any normal program)
2. Creates a Desktop shortcut and Start Menu entry
3. Bundles everything needed — no extra software required

The only thing the end user needs to do after installing is add their API key to a config file.

---

## Part 1 — Setting up YOUR computer (one-time)

These are tools you need on your computer to BUILD the installer. End users do NOT need any of this.

---

### Step 1 — Install Python

1. Open your browser and go to **https://www.python.org/downloads/**
2. Click the big yellow **"Download Python 3.x.x"** button
3. Run the downloaded installer
4. **IMPORTANT**: On the first screen of the installer, check the box that says **"Add Python to PATH"** before clicking Install
5. Click **"Install Now"**
6. Wait for installation to finish, then click **Close**

**Verify it worked:**
- Press `Win + R`, type `cmd`, press Enter
- Type `python --version` and press Enter
- You should see something like `Python 3.12.4`
- If you see an error, Python is not on PATH — reinstall and make sure to check "Add to PATH"

---

### Step 2 — Install Node.js

1. Open your browser and go to **https://nodejs.org/**
2. Click the **"LTS"** version (the one labeled "Recommended For Most Users")
3. Run the downloaded installer
4. Click through all the defaults — just keep clicking Next and then Install
5. Wait for it to finish

**Verify it worked:**
- Open a new Command Prompt (`Win + R` → `cmd` → Enter)
- Type `node --version` and press Enter
- You should see something like `v20.11.0`
- Type `npm --version` and press Enter
- You should see something like `10.2.4`

---

---

## Part 2 — Setting up the project (one-time)

### Step 4 — Get the project files

If you haven't already, make sure you have the full Interview Helper project folder on your computer, including all of these subfolders:
```
interview-helper/
├── backend/
├── frontend/
├── packaging/     ← must exist (contains the build scripts)
└── .env.example   ← must exist
```

If the `packaging/` folder is missing, it needs to be recreated. Ask the developer for the packaging scripts or refer to the project documentation.

---

### Step 5 — Open a terminal in the project folder

1. Open **File Explorer**
2. Navigate to the `interview-helper` folder
3. Click on the address bar at the top (where it shows the folder path)
4. Type `cmd` and press Enter

A black Command Prompt window will open, already inside the correct folder. You can verify by checking the prompt — it should show the path ending in `interview-helper`.

---

## Part 3 — Building the installer

### Step 6 — Run the build script

In the Command Prompt window you opened in Step 5, type exactly:

```
packaging\build.bat
```

Press Enter and wait.

**The script will run 4 steps automatically:**

#### Step 1 of 4 — Installing Python dependencies
```
[1/4] Installing Python dependencies...
```
- Downloads and installs all the Python libraries the backend needs
- Also installs PyInstaller (the tool that bundles Python into an .exe)
- Takes 1–3 minutes on first run (faster after that, as packages are cached)

#### Step 2 of 4 — Building the backend executable
```
[2/4] Building backend executable (this may take a few minutes)...
```
- PyInstaller bundles the entire Python backend into a single folder
- This is the most time-consuming step — can take 3–8 minutes
- You will see a lot of text scrolling by — this is normal
- Output goes to: `packaging\dist\backend\`

#### Step 3 of 4 — Installing electron-builder
```
[3/4] Installing electron-builder (packaging tool)...
```
- Downloads electron-builder (the tool that creates the Windows installer)
- Takes 1–2 minutes on first run

#### Step 4 of 4 — Building the installer
```
[4/4] Building Windows installer (this may take a few minutes)...
```
- Packages the Electron frontend + Python backend into one installer
- Downloads Electron binaries if not already cached (~60 MB, one-time)
- Takes 2–5 minutes

#### Success message
When everything works, you will see:
```
============================================================
  Build complete!

  Installer: C:\...\packaging\release\
  ...
============================================================
```

---

### Where is the installer?

After a successful build, your installer is at:
```
interview-helper\packaging\release\Interview Helper Setup 1.0.0.exe
```

This is the file you send to users.

---

## Part 4 — Common errors and fixes

### Error: `python not found` or `'python' is not recognized`
**Cause:** Python is not on PATH
**Fix:** Reinstall Python and make sure to check **"Add Python to PATH"** during installation. Then close and reopen your terminal.

---

### Error: `node not found` or `'npm' is not recognized`
**Cause:** Node.js is not on PATH
**Fix:** Reinstall Node.js. Then close and reopen your terminal.

---


### Error: `[1/4]` fails with pip errors
**Cause:** Python packages failed to install
**Fix:**
1. Make sure you have an internet connection
2. If you are behind a corporate firewall/proxy, pip may be blocked — contact your IT team
3. Try running the Command Prompt as Administrator (right-click → "Run as administrator")

---

### Error: PyInstaller step fails with `ModuleNotFoundError`
**Cause:** A Python library is missing from the spec's hidden imports
**Fix:** Note the missing module name from the error, then open `packaging\backend.spec` and add it to the `hiddenimports` list.

---

### Error: electron-builder step fails with `backend folder not found`
**Cause:** PyInstaller (Step 2) did not complete successfully
**Fix:** Scroll up in the terminal to find the PyInstaller error and fix it first. The `packaging\dist\backend\` folder must exist before electron-builder runs.

---

### The build ran before and now I want to rebuild

Just run `packaging\build.bat` again. It is safe to run multiple times:
- PyInstaller uses `--clean` to wipe and rebuild from scratch
- Old installer in `packaging\release\` will be overwritten
- Nothing in the main project folders is ever touched

---

## Part 5 — Sending the app to users

### What to send
Send users the single file:
```
Interview Helper Setup 1.0.0.exe
```
(found in `packaging\release\` after the build)

You can share it via Google Drive, WeTransfer, USB drive, or any file sharing method.

---

### What users need to do after installing

1. Run the installer — click through the wizard (Next → Next → Install)
2. After installation, open **File Explorer**
3. Paste this path into the address bar and press Enter:
   ```
   %LOCALAPPDATA%\Programs\Interview Helper\resources
   ```
4. Find the file named `.env` and open it with **Notepad**
   - Right-click the file → Open with → Notepad
5. Find this line:
   ```
   AI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxx
   ```
6. Replace the placeholder with their actual API key:
   ```
   AI_API_KEY=sk-proj-YOUR_ACTUAL_KEY_HERE
   ```
7. Save the file (Ctrl+S) and close Notepad
8. Launch **Interview Helper** from the Desktop shortcut or Start Menu

That's it — the app is ready to use.

---

## Part 6 — Advanced: Changing the version number

Before building, if you want to change the version shown in the installer:

1. Open `frontend\package.json`
2. Find the line: `"version": "1.0.0"`
3. Change it to your desired version, e.g. `"version": "1.1.0"`
4. Save the file
5. Run the build — the installer will be named `Interview Helper Setup 1.1.0.exe`

---

## Summary cheatsheet

| Task | Command |
|------|---------|
| Build the installer | `packaging\build.bat` |
| Find the installer | `packaging\release\` |
| User's config file | `%LOCALAPPDATA%\Programs\Interview Helper\resources\.env` |
| Rebuild from scratch | Just run `packaging\build.bat` again |
