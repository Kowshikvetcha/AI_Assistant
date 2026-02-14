# 🎯 Real-Time Interview Helper

A desktop tool that captures system audio from Zoom / Google Meet / Teams, transcribes it via OpenAI Whisper API, generates structured interview answers via GPT-4o, and displays them in a floating always-on-top overlay.

---

## Architecture

```
System Audio (WASAPI Loopback)
        │
        ▼  PCM chunks (1-2s)
┌──────────────────────┐
│   FastAPI Backend     │
│  ┌────────────────┐   │
│  │ Audio Capture   │──┼──► OpenAI Whisper API ──► Transcript
│  │ (soundcard)     │  │
│  └────────────────┘   │
│  ┌────────────────┐   │
│  │ LLM Service     │──┼──► OpenAI GPT-4o ──► Structured JSON
│  └────────────────┘   │
│  ┌────────────────┐   │
│  │ WebSocket Srv   │──┼──► Push to Frontend
│  └────────────────┘   │
└──────────────────────┘
        │
        ▼  WebSocket
┌──────────────────────┐
│  Electron Overlay     │
│  • Live transcript    │
│  • Answer + bullets   │
│  • Code snippets      │
│  • Always-on-top      │
│  • Ctrl+Shift+H toggle│
└──────────────────────┘
```

---

## 🚀 Quick Start (30 seconds)

```bash
# 1. Create and activate Python 3.10/3.13 virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# 2. Copy and configure .env
copy .env.example .env
# Edit .env and add your OpenAI API key

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

## Prerequisites

- **Python 3.10 or 3.13** (⚠️ NOT 3.14 — compatibility issues with pydantic-core)
- **Node.js 18+** and **npm**
- **Windows** (for WASAPI loopback audio capture)
- **OpenAI API Key** with access to Whisper and GPT-4o
- **Rust** (automatically installed with Python dependencies if needed)

---

## Installation Guide

### Step 1: Clone Repository

```bash
git clone <repo-url>
cd interview-helper
```

### Step 2: Create Virtual Environment

Create a Python 3.10/3.13 virtual environment in the project root:

```bash
# Using Python 3.10 (replace with py or python3.10 if needed)
python -m venv venv

# Activate virtual environment
# On Windows PowerShell:
.\venv\Scripts\Activate.ps1
# On Windows CMD:
.\venv\Scripts\activate.bat
```

### Step 3: Configure Environment Variables

Create a `.env` file in the `interview-helper/` directory (NOT the root):

```bash
# Copy the template
copy .env.example .env
```

Edit `.env` and set your OpenAI API key:

```
OPENAI_API_KEY=sk-your-actual-key-here
WEBSOCKET_PORT=8765
LLM_MODEL=gpt-4o
LLM_MAX_TOKENS=1024
AUDIO_CHUNK_DURATION=2
LOG_LEVEL=INFO
```

### Step 4: Install Backend Dependencies

```bash
# Make sure virtual environment is activated
cd backend

# Install Python dependencies
pip install -r requirements.txt

# (If you encounter Rust compilation errors, ensure Rust is installed)
# Download from: https://rustup.rs/
```

### Step 5: Install Frontend Dependencies

```bash
cd ../frontend
npm install
```

---

## Running the Application

### Terminal 1: Start the Backend

```bash
# From project root, make sure venv is activated
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

1. **Start** the backend, then the frontend.
2. Join a Zoom / Meet / Teams call (or play any audio).
3. Click **▶ Start** in the overlay to begin capturing audio.
4. Watch live transcript and AI-generated answers populate.
5. Click **⏹ Stop** to pause, **🗑 Clear** to reset.
6. Press **Ctrl+Shift+H** to toggle overlay visibility.

---

## Project Structure

```
interview-helper/
├── backend/
│   ├── main.py              # FastAPI server & pipeline orchestration
│   ├── audio_capture.py     # WASAPI loopback audio capture
│   ├── stt.py               # OpenAI Whisper API service
│   ├── llm.py               # OpenAI GPT-4o service
│   ├── websocket_manager.py # WebSocket connection manager
│   ├── models.py            # Pydantic data models
│   ├── config.py            # Settings from .env
│   ├── utils.py             # Logging, timing, WAV encoding
│   ├── requirements.txt     # Python dependencies
│   └── tests/               # Unit tests
│       ├── test_stt.py
│       ├── test_llm.py
│       ├── test_websocket.py
│       └── test_performance.py
├── frontend/
│   ├── main.js              # Electron main process
│   ├── preload.js           # Context bridge
│   ├── index.html           # Overlay UI
│   ├── styles.css           # Dark glassmorphism theme
│   ├── renderer.js          # WebSocket client & UI logic
│   └── package.json         # Electron dependencies
├── .env.example             # Environment template
└── README.md
```

---

## Running Tests

```bash
# From project root
.\venv\Scripts\Activate.ps1

cd backend
python -m pytest tests/ -v
```

Tests mock all OpenAI API calls — no API key required.

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | Required. Your OpenAI API key |
| `WEBSOCKET_PORT` | `8765` | Backend WebSocket port |
| `AUDIO_CHUNK_DURATION` | `2` | Audio chunk length in seconds |
| `LLM_MODEL` | `gpt-4o` | OpenAI model name |
| `LLM_MAX_TOKENS` | `1024` | Max response tokens |
| `LOG_LEVEL` | `INFO` | Logging level |

---

## Troubleshooting

### ❌ `ValidationError: OPENAI_API_KEY Field required`

**Cause:** `.env` file not found or in wrong location.

**Solution:** 
- Ensure `.env` is in the `interview-helper/` directory (not root)
- Verify it contains: `OPENAI_API_KEY=sk-your-key`
- Restart the backend after creating `.env`

### ❌ `Port 8765 already in use`

**Cause:** Backend is already running or a previous instance wasn't properly stopped.

**Solution:**
```bash
# Kill the process using port 8765
netstat -ano | findstr 8765
taskkill /PID <PID> /F

# Or change the port in .env
WEBSOCKET_PORT=8766
```

### ❌ `pydantic-core build errors / PyO3 compilation fails`

**Cause:** Using Python 3.14, which is too new for current pydantic-core.

**Solution:**
- Ensure you're using **Python 3.10 or 3.13**
- Delete the old venv: `Remove-Item -Recurse venv`
- Recreate with Python 3.10: `python3.10 -m venv venv`
- Reinstall dependencies

### ❌ `Rust not found` when installing dependencies

**Cause:** Rust toolchain not installed.

**Solution:**
- Download and install from: https://rustup.rs/
- It will set up Rust automatically
- After installation, restart your terminal and retry `pip install -r requirements.txt`

### ❌ Frontend won't connect to backend

**Cause:** Backend not running or wrong port/host.

**Solution:**
1. Verify backend is running: `netstat -ano | findstr 8765`
2. Check browser console in frontend for errors
3. Verify `.env` has correct `WEBSOCKET_PORT`
4. Ensure firewall isn't blocking localhost connections

### ❌ Audio not being captured

**Cause:** WASAPI loopback not enabled or wrong audio device.

**Solution:**
1. Ensure you have system audio loopback enabled (varies by audio driver)
2. Try with playing system audio (YouTube, Spotify, etc.)
3. Check `LOG_LEVEL=DEBUG` in `.env` for detailed audio capture logs

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
- **Requires internet** — All AI processing is cloud-based (OpenAI)
- **API costs** — Each audio chunk incurs Whisper + GPT-4o API charges
- **Latency** — Dependent on network speed and OpenAI response times (~3-5s total)
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
- [ ] Packaged installer (electron-builder)
