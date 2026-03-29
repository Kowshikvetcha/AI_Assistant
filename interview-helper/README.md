# Real-Time Interview Helper

A desktop tool that captures system audio from Zoom / Google Meet / Teams, transcribes it via OpenAI Whisper API, generates structured interview answers via GPT-4o, and displays them in a floating always-on-top overlay.

---

## Architecture

```
System Audio (WASAPI Loopback)
        |
        v  PCM chunks (1-2s)
+----------------------+
|   FastAPI Backend     |
|  +----------------+   |
|  | Audio Capture   |--+--> OpenAI Whisper API --> Transcript
|  | (soundcard)     |  |
|  +----------------+   |
|  +----------------+   |
|  | LLM Service     |--+--> OpenAI GPT-4o --> Structured JSON
|  +----------------+   |
|  +----------------+   |
|  | WebSocket Srv   |--+--> Push to Frontend
|  +----------------+   |
+----------------------+
        |
        v  WebSocket
+----------------------+
|  Electron Overlay     |
|  - Live transcript    |
|  - Answer + bullets   |
|  - Code snippets      |
|  - Always-on-top      |
|  - Ctrl+Shift+H toggle|
|  - In-app settings    |
+----------------------+
```

---

## Quick Start (Development)

```bash
# 1. Create and activate Python 3.10/3.13 virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# 2. Copy and configure .env
copy .env.example .env
# Edit .env and set your API key/model values

# 3. Install backend + frontend dependencies
cd backend && pip install -r requirements.txt && cd ..
cd frontend && npm install && cd ..

# 4. Start in two terminals
# Terminal 1:
cd backend && python main.py

# Terminal 2:
cd frontend && npm start
```

---

## Packaged App (End Users)

End users don't need Python, Node.js, or any dev tools. They receive a single installer:

```
Interview Helper Setup 1.0.0.exe
```

After installing:
1. Launch **Interview Helper** from the Desktop shortcut or Start Menu
2. Click the **gear icon** in the titlebar to open Settings
3. Select an **AI Provider** and enter an **API Key**
4. Optionally override LLM, Summary, or STT models (defaults are used if left empty)
5. Click **Save** — the backend starts automatically

No `.env` file editing required. Settings are stored in `%APPDATA%\interview-helper\settings.json`.

See [PACKAGING_GUIDE.md](PACKAGING_GUIDE.md) for build instructions.

---

## Prerequisites (Development)

- **Python 3.10 or 3.13** (NOT 3.14 — compatibility issues with pydantic-core)
- **Node.js 18+** and **npm**
- **Windows** (for WASAPI loopback audio capture)
- **API key** for your configured provider/model stack
- **Rust** (automatically installed with Python dependencies if needed)

---

## Installation Guide (Development)

### Step 1: Clone Repository

```bash
git clone <repo-url>
cd interview-helper
```

### Step 2: Create Virtual Environment

```bash
python -m venv venv

# Activate virtual environment
# On Windows PowerShell:
.\venv\Scripts\Activate.ps1
# On Windows CMD:
.\venv\Scripts\activate.bat
```

### Step 3: Configure Environment Variables

```bash
copy .env.example .env
```

Edit `.env` and set your API key/models:

```
AI_PROVIDER=openai
AI_API_KEY=sk-your-actual-key-here
WEBSOCKET_PORT=8765
# Optional model overrides (leave empty for provider defaults)
LLM_MODEL=
SUMMARY_MODEL=
STT_MODEL=
LLM_MAX_TOKENS=1024
AUDIO_CHUNK_DURATION=2
LOG_LEVEL=INFO
```

Note: In development mode, the backend reads from `.env`. In the packaged app, settings come from the in-app Settings UI instead.

### Step 4: Install Backend Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### Step 5: Install Frontend Dependencies

```bash
cd ../frontend
npm install
```

---

## Running the Application (Development)

### Terminal 1: Start the Backend

```bash
.\venv\Scripts\Activate.ps1
cd backend
python main.py
```

You should see:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8765 (Press CTRL+C to quit)
```

### Terminal 2: Start the Frontend

```bash
cd frontend
npm start
```

The Electron overlay window appears on screen. The frontend automatically connects to the backend on `localhost:8765`.

---

## Usage

1. **Start** the backend, then the frontend (or use the packaged installer).
2. Join a Zoom / Meet / Teams call (or play any audio).
3. Click **Start** in the overlay to begin capturing audio.
4. Watch live transcript and AI-generated answers populate.
5. Click **Stop** to pause, **Clear** to reset.
6. Press **Ctrl+Shift+H** to toggle overlay visibility.
7. Press **Ctrl+Shift+S** to capture a screen region for OCR.
8. Click the **gear icon** to change AI provider, API key, or model settings.

---

## Project Structure

```
interview-helper/
├── backend/
│   ├── main.py              # FastAPI server & pipeline orchestration
│   ├── audio_capture.py     # WASAPI loopback audio capture
│   ├── stt.py               # OpenAI Whisper API service
│   ├── llm.py               # LLM service (multi-provider)
│   ├── websocket_manager.py # WebSocket connection manager
│   ├── models.py            # Pydantic data models
│   ├── config.py            # Settings from env vars / .env
│   ├── resume_parser.py     # PDF resume parser
│   ├── screen_capture.py    # Tesseract OCR for screen capture
│   ├── utils.py             # Logging, timing, WAV encoding
│   ├── requirements.txt     # Python dependencies
│   └── tests/               # Unit tests
├── frontend/
│   ├── main.js              # Electron main process, backend spawning, settings management
│   ├── preload.js           # Context bridge (IPC for settings, capture, etc.)
│   ├── index.html           # Overlay UI
│   ├── styles.css           # Dark glassmorphism theme
│   ├── renderer.js          # WebSocket client & UI logic
│   ├── settings.html        # Settings window UI
│   ├── settings.css         # Settings window theme
│   ├── settings-renderer.js # Settings window logic
│   └── package.json         # Electron + electron-builder config
├── packaging/
│   ├── build.bat            # Master build script (5 steps)
│   └── backend.spec         # PyInstaller spec for backend bundling
├── .env.example             # Environment template (dev mode)
├── PACKAGING_GUIDE.md       # How to build the installer
└── README.md
```

---

## Running Tests

```bash
.\venv\Scripts\Activate.ps1
cd backend
python -m pytest tests/ -v
```

Tests mock all OpenAI API calls — no API key required.

---

## Configuration

### In-App Settings (Packaged App)

Click the gear icon in the titlebar. Mandatory fields:

| Field | Description |
|---|---|
| **AI Provider** | Select from: openai, groq, openrouter, together, fireworks, deepseek, ollama |
| **API Key** | Your provider's API key |

Optional fields (leave empty to use provider defaults):

| Field | Description |
|---|---|
| LLM Model | Override the main answer model |
| Summary Model | Override the transcript summary model |
| STT Model | Override the speech-to-text model |

Settings are saved to `%APPDATA%\interview-helper\settings.json` and passed as environment variables to the backend process.

### Environment Variables (Development)

| Variable | Default | Description |
|---|---|---|
| `AI_PROVIDER` | `openai` | Provider name |
| `AI_API_KEY` | — | API key |
| `AI_BASE_URL` | — | Optional base URL for OpenAI-compatible providers |
| `OPENAI_API_KEY` | — | Legacy fallback key variable |
| `WEBSOCKET_PORT` | `8765` | Backend WebSocket port |
| `AUDIO_CHUNK_DURATION` | `2` | Audio chunk length in seconds |
| `LLM_MODEL` | provider default | Main answer model override |
| `SUMMARY_MODEL` | provider default | Transcript summary model override |
| `STT_MODEL` | provider default | Speech-to-text model override |
| `LLM_MAX_TOKENS` | `1024` | Max response tokens |
| `LOG_LEVEL` | `INFO` | Logging level |
| `TESSERACT_CMD` | auto-detected | Path to Tesseract executable |

Provider presets (OpenAI-compatible): `openai`, `openrouter`, `groq`, `together`, `fireworks`, `deepseek`, `ollama`.

---

## Troubleshooting

### Missing API key

**Cause:** No API key configured.

**Solution (packaged app):** Click the gear icon in the titlebar, enter your API key, and click Save.

**Solution (dev mode):** Ensure `.env` is in the `interview-helper/` directory and contains `AI_API_KEY=...`.

### Port 8765 already in use

**Cause:** Backend is already running or a previous instance wasn't properly stopped.

**Solution:**
```bash
netstat -ano | findstr 8765
taskkill /PID <PID> /F
```

Or change the port in settings / `.env`.

### pydantic-core build errors / PyO3 compilation fails

**Cause:** Using Python 3.14, which is too new for current pydantic-core.

**Solution:**
- Use **Python 3.10 or 3.13**
- Delete the old venv: `Remove-Item -Recurse venv`
- Recreate with Python 3.10: `python3.10 -m venv venv`
- Reinstall dependencies

### Frontend won't connect to backend

**Cause:** Backend not running or wrong port.

**Solution:**
1. Verify backend is running: `netstat -ano | findstr 8765`
2. In the packaged app, check that settings are saved (click gear icon)
3. Ensure firewall isn't blocking localhost connections

### Audio not being captured

**Cause:** WASAPI loopback not enabled or wrong audio device.

**Solution:**
1. Ensure you have system audio playing (YouTube, Spotify, etc.)
2. Check `LOG_LEVEL=DEBUG` for detailed audio capture logs

### Symlink error during build (electron-builder)

**Cause:** Windows doesn't allow symlink creation without Developer Mode or admin privileges.

**Solution:**
1. Enable **Developer Mode**: Settings > For Developers > Developer Mode ON
2. Clear the failed cache: `rmdir /s /q "%LOCALAPPDATA%\electron-builder\Cache\winCodeSign"`
3. Re-run `packaging\build.bat`

---

## Performance Logging

Each processing cycle logs:
- **STT latency** — Whisper API response time
- **LLM latency** — GPT-4o response time
- **Total latency** — End-to-end time
- **Token usage** — Tokens consumed per request

Performance is also shown in the overlay's bottom bar.

---

## Known Limitations

- **Windows only** — WASAPI loopback is Windows-specific
- **Requires internet** — All AI processing is cloud-based
- **API costs** — Each audio chunk incurs STT + LLM API charges
- **Latency** — Dependent on network speed and API response times (~3-5s total)
- **Audio format** — Captures system-wide audio, not per-application

---

## Future Improvements

- [ ] macOS audio capture (via BlackHole / Core Audio)
- [ ] Linux support (PulseAudio loopback)
- [ ] Per-application audio isolation
- [ ] Streaming LLM responses (token by token)
- [ ] Conversation history / export
- [ ] Custom system prompts / personas
- [ ] Local STT fallback for offline use
- [x] Packaged installer (electron-builder)
- [x] In-app settings UI (no .env editing for end users)
