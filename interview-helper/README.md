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

## Prerequisites

- **Python 3.10+**
- **Node.js 18+** and **npm**
- **Windows** (for WASAPI loopback audio capture)
- **OpenAI API Key** with access to Whisper and GPT-4o

---

## Setup

### 1. Clone & Configure

```bash
cd interview-helper
copy .env.example .env
```

Edit `.env` and set your OpenAI API key:

```
OPENAI_API_KEY=sk-your-actual-key-here
```

### 2. Backend Setup

```bash
cd backend

# Create and activate virtual environment (already created at ../venv)
..\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Frontend Setup

```bash
cd frontend
npm install
```

---

## Running

### Start Backend

```bash
cd backend
..\venv\Scripts\activate
python main.py
```

The backend starts on `http://localhost:8765`. Verify with:

```
GET http://localhost:8765/health
```

### Start Frontend

```bash
cd frontend
npm start
```

The Electron overlay window appears on screen.

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
cd backend
..\venv\Scripts\activate
pip install pytest pytest-asyncio
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
