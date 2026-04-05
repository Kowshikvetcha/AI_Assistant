/**
 * Renderer Process
 * WebSocket client for the Interview Helper overlay.
 * Connects to the FastAPI backend and updates the UI in real time.
 */

// ── Configuration ──
let BACKEND_PORT = 8765;
let WS_URL = `ws://localhost:${BACKEND_PORT}/ws`;
const RECONNECT_DELAY_MIN_MS = 3000;
const RECONNECT_DELAY_MAX_MS = 30000;
const MAX_TRANSCRIPT_LINES = 20;
let BACKEND_URL = `http://localhost:${BACKEND_PORT}`;

// ── DOM Elements ──
const $ = (id) => document.getElementById(id);

const elements = {
    btnStart: $("btn-start"),
    btnStop: $("btn-stop"),
    btnClear: $("btn-clear"),
    btnClearMemory: $("btn-clear-memory"),
    btnCapture: $("btn-capture"),
    btnMinimize: $("btn-minimize"),
    btnClose: $("btn-close"),
    btnResume: $("btn-resume"),
    chatInput: $("chat-input"),
    btnChatSend: $("btn-chat-send"),
    resumeStatus: $("resume-status"),
    statusDot: $("status-dot"),
    statusText: $("status-text"),
    transcript: $("transcript-content"),
    answer: $("answer-content"),
    bullets: $("bullets-content"),
    codeSection: $("section-code"),
    code: $("code-content"),
    followup: $("followup-content"),
    debugQuestion: $("debug-question-content"),
    perfStt: $("perf-stt"),
    perfLlm: $("perf-llm"),
    perfTokens: $("perf-tokens"),
};

// ── State ──
let ws = null;
let transcriptLines = [];
let isCapturing = false;
let isChatLoading = false;
let isCaptureLoading = false;
let reconnectDelay = RECONNECT_DELAY_MIN_MS;

// ── WebSocket Connection ──
function connect() {
    updateStatus("connecting", "Connecting to backend...");

    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
        reconnectDelay = RECONNECT_DELAY_MIN_MS; // reset backoff on success
        updateStatus("connected", "Connected");
        console.log("[WS] Connected to backend");
        checkResumeStatus();
    };

    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleMessage(msg);
        } catch (err) {
            console.error("[WS] Parse error:", err);
        }
    };

    ws.onclose = () => {
        // Reset capturing state so buttons are usable after reconnect
        setCapturing(false);
        const delay = reconnectDelay;
        reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_DELAY_MAX_MS);
        const secs = Math.round(delay / 1000);
        updateStatus("disconnected", `Backend offline — retrying in ${secs}s`);
        console.log(`[WS] Disconnected, retrying in ${secs}s`);
        ws = null;
        setTimeout(connect, delay);
    };

    ws.onerror = () => {
        // onclose always fires after onerror — let it handle the retry logic
        console.error("[WS] Connection error");
    };
}

// ── Message Handler ──
function handleMessage(msg) {
    switch (msg.type) {
        case "transcript":
            onTranscript(msg);
            break;
        case "llm_response":
            onLLMResponse(msg);
            break;
        case "status":
            onStatus(msg);
            break;
        case "error":
            onError(msg);
            break;
        default:
            console.warn("[WS] Unknown message type:", msg.type);
    }
}

// ── Transcript ──
function onTranscript(msg) {
    transcriptLines.push(msg.text);
    if (transcriptLines.length > MAX_TRANSCRIPT_LINES) {
        transcriptLines = transcriptLines.slice(-MAX_TRANSCRIPT_LINES);
    }

    elements.transcript.innerHTML = transcriptLines
        .map((line) => `<p class="fade-in">${escapeHtml(line)}</p>`)
        .join("");

    // Auto-scroll to bottom
    elements.transcript.scrollTop = elements.transcript.scrollHeight;

    // Update STT performance
    if (msg.latency_ms) {
        elements.perfStt.textContent = `STT: ${Math.round(msg.latency_ms)}ms`;
    }
}

// ── LLM Response ──
function onLLMResponse(msg) {
    // Direct answer
    if (msg.direct_answer) {
        elements.answer.innerHTML = `<p class="fade-in">${escapeHtml(
            msg.direct_answer
        )}</p>`;
    }

    // Bullet points
    if (msg.bullet_points && msg.bullet_points.length > 0) {
        elements.bullets.innerHTML = msg.bullet_points
            .map((bp) => `<li class="fade-in">${escapeHtml(bp)}</li>`)
            .join("");
    }

    // Code example
    if (msg.code_example && msg.code_example.trim()) {
        elements.codeSection.classList.add("visible");
        elements.code.innerHTML = `<code class="fade-in">${escapeHtml(
            msg.code_example
        )}</code>`;
    } else {
        elements.codeSection.classList.remove("visible");
    }

    // Follow-up question
    if (msg.followup_question) {
        elements.followup.innerHTML = `<p class="fade-in">${escapeHtml(
            msg.followup_question
        )}</p>`;
    }
    if (msg.latest_question_input) {
        elements.debugQuestion.innerHTML = `<p class="fade-in">${escapeHtml(
            msg.latest_question_input
        )}</p>`;
    }

    // Performance
    if (msg.latency_ms) {
        elements.perfLlm.textContent = `LLM: ${Math.round(msg.latency_ms)}ms`;
    }
    if (msg.tokens_used) {
        elements.perfTokens.textContent = `Tokens: ${msg.tokens_used}`;
    }
}

// ── Status ──
function onStatus(msg) {
    switch (msg.status) {
        case "capturing":
            updateStatus("capturing", "Capturing...");
            setCapturing(true);
            break;
        case "stopped":
            updateStatus("connected", "Stopped");
            setCapturing(false);
            break;
        case "connected":
            updateStatus("connected", msg.detail || "Connected");
            break;
        case "cleared":
            clearUI();
            break;
        case "resume_loaded":
            updateResumeStatus(msg.detail || "Resume loaded", true);
            break;
        case "memory_cleared":
            updateStatus("connected", msg.detail || "Memory cleared");
            break;
        default:
            updateStatus("connected", msg.status);
    }
}

// ── Error ──
function onError(msg) {
    const recoverable = msg.recoverable !== false;
    updateStatus("error", `❌ ${msg.error}`);
    console.error("[Backend]", msg.error);

    if (!recoverable) {
        // Show the full error message in the transcript area (it has more space)
        // so the user can read setup instructions etc.
        elements.transcript.innerHTML =
            `<p class="error-message">${escapeHtml(msg.error)}</p>`;
        setCapturing(false);
        // Do NOT auto-dismiss — user must read it and take action
        return;
    }

    // Recoverable errors: restore status after a short delay
    setTimeout(() => {
        if (isCapturing) {
            updateStatus("capturing", "Capturing...");
        } else {
            updateStatus("connected", "Connected");
        }
    }, 5000);
}

// ── UI Helpers ──
function updateStatus(state, text) {
    elements.statusDot.className = `status-dot ${state}`;
    elements.statusText.textContent = text;
}

function setCapturing(capturing) {
    isCapturing = capturing;
    elements.btnStart.disabled = capturing;
    elements.btnStop.disabled = !capturing;
}

function clearUI() {
    transcriptLines = [];
    elements.transcript.innerHTML = '<p class="placeholder">Waiting for audio...</p>';
    elements.answer.innerHTML = '<p class="placeholder">Answers will appear here</p>';
    elements.bullets.innerHTML = '<li class="placeholder">Key points will appear here</li>';
    elements.codeSection.classList.remove("visible");
    elements.code.innerHTML = '<code class="placeholder">Code snippets will appear here</code>';
    elements.followup.innerHTML = '<p class="placeholder">—</p>';
    elements.debugQuestion.innerHTML = '<p class="placeholder">Waiting for first LLM call...</p>';
    elements.perfStt.textContent = "STT: —";
    elements.perfLlm.textContent = "LLM: —";
    elements.perfTokens.textContent = "Tokens: —";
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

// ── Send Control Messages ──
function sendControl(action) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "control", action }));
    }
}

// ── Event Listeners ──
elements.btnStart.addEventListener("click", () => sendControl("start"));
elements.btnStop.addEventListener("click", () => sendControl("stop"));
elements.btnClear.addEventListener("click", () => {
    sendControl("clear");
    clearUI();
});
elements.btnClearMemory.addEventListener("click", () => {
    updateStatus("connected", "Clearing memory...");
    sendControl("clear_memory");
});

// Window controls via preload bridge
elements.btnMinimize.addEventListener("click", () => {
    if (window.electronAPI) window.electronAPI.minimizeWindow();
});

elements.btnClose.addEventListener("click", () => {
    if (window.electronAPI) window.electronAPI.closeWindow();
});

// Settings button
const btnSettings = document.getElementById("btn-settings");
if (btnSettings) {
    btnSettings.addEventListener("click", () => {
        if (window.electronAPI) window.electronAPI.openSettings();
    });
}

// Listen for backend status updates from main process
if (window.electronAPI && window.electronAPI.onBackendStatus) {
    window.electronAPI.onBackendStatus((status) => {
        updateStatus("connecting", status);
    });
}

// ── Resume Upload ──
elements.btnResume.addEventListener("click", async () => {
    if (!window.electronAPI) {
        console.error("[Resume] electronAPI not available");
        return;
    }

    try {
        updateResumeStatus("Selecting file...", false);
        const fileData = await window.electronAPI.selectResumeFile();

        if (!fileData) {
            updateResumeStatus("No resume loaded", false);
            return;
        }

        updateResumeStatus("Uploading...", false);

        // Convert base64 back to binary and create FormData
        const byteChars = atob(fileData.buffer);
        const byteArray = new Uint8Array(byteChars.length);
        for (let i = 0; i < byteChars.length; i++) {
            byteArray[i] = byteChars.charCodeAt(i);
        }
        const blob = new Blob([byteArray]);

        const formData = new FormData();
        formData.append("file", blob, fileData.name);

        const response = await fetch(`${BACKEND_URL}/upload-resume`, {
            method: "POST",
            body: formData,
        });

        const result = await response.json();

        if (result.status === "ok") {
            updateResumeStatus(`✅ ${result.filename}`, true);
            console.log(`[Resume] Loaded: ${result.filename} (${result.chars} chars)`);
        } else {
            updateResumeStatus(`❌ ${result.error}`, false);
            console.error("[Resume] Upload error:", result.error);
        }
    } catch (err) {
        updateResumeStatus("❌ Upload failed", false);
        console.error("[Resume] Error:", err);
    }
});

function updateResumeStatus(text, loaded) {
    elements.resumeStatus.textContent = text;
    elements.resumeStatus.className = loaded
        ? "resume-status loaded"
        : "resume-status";
}

async function checkResumeStatus() {
    try {
        const response = await fetch(`${BACKEND_URL}/resume-status`);
        const data = await response.json();
        if (data.loaded) {
            updateResumeStatus(`✅ ${data.filename}`, true);
        }
    } catch (err) {
        console.log("[Resume] Could not check resume status:", err.message);
    }
}

// ── Initialize ──
function setChatLoading(loading) {
    isChatLoading = loading;
    elements.chatInput.disabled = loading;
    elements.btnChatSend.disabled = loading;
    elements.btnChatSend.textContent = loading ? "..." : "Send";
}

async function sendChatQuestion() {
    if (isChatLoading) return;

    const question = elements.chatInput.value.trim();
    if (!question) return;

    setChatLoading(true);
    updateStatus("connected", "Thinking...");

    try {
        const response = await fetch(`${BACKEND_URL}/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question }),
        });

        const result = await response.json();
        if (result.type === "llm_response") {
            onLLMResponse(result);
            elements.chatInput.value = "";
            updateStatus(
                isCapturing ? "capturing" : "connected",
                isCapturing ? "Capturing..." : "Connected"
            );
            return;
        }

        throw new Error(result.error || "Chat request failed");
    } catch (err) {
        onError({ error: err.message || "Chat request failed" });
    } finally {
        setChatLoading(false);
    }
}

elements.btnChatSend.addEventListener("click", sendChatQuestion);
elements.chatInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
        event.preventDefault();
        sendChatQuestion();
    }
});

// ── Screen Capture ──
function setCaptureLoading(loading) {
    isCaptureLoading = loading;
    elements.btnCapture.disabled = loading;
    elements.btnCapture.textContent = loading ? "..." : "📸 Capture";
}

async function captureScreen() {
    if (isCaptureLoading) return;
    if (!window.electronAPI || !window.electronAPI.captureScreen) {
        console.error("[Capture] electronAPI.captureScreen not available");
        return;
    }

    setCaptureLoading(true);
    updateStatus("connected", "Capturing...");

    try {
        const base64Image = await window.electronAPI.captureScreen();

        if (!base64Image) {
            updateStatus(
                isCapturing ? "capturing" : "connected",
                isCapturing ? "Capturing..." : "Connected"
            );
            return;
        }

        updateStatus("connected", "Processing OCR...");

        const response = await fetch(`${BACKEND_URL}/capture-screen`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ image: base64Image }),
        });

        const result = await response.json();

        if (result.status === "ok" && result.text) {
            // Place OCR text in the chat input for user review/edit
            elements.chatInput.value = result.text;
            elements.chatInput.focus();
            updateStatus(
                isCapturing ? "capturing" : "connected",
                "OCR done — review and hit Send"
            );
            return;
        }

        if (result.status === "error") {
            throw new Error(result.error || "Screen capture failed");
        }

        throw new Error("Unexpected response from capture endpoint");
    } catch (err) {
        onError({ error: err.message || "Screen capture failed" });
    } finally {
        setCaptureLoading(false);
    }
}

elements.btnCapture.addEventListener("click", captureScreen);

// Listen for hotkey trigger from main process
if (window.electronAPI && window.electronAPI.onTriggerScreenCapture) {
    window.electronAPI.onTriggerScreenCapture(() => {
        captureScreen();
    });
}

// Resolve backend port from settings, then connect
(async function init() {
    if (window.electronAPI && window.electronAPI.getBackendPort) {
        try {
            const port = await window.electronAPI.getBackendPort();
            if (port) {
                BACKEND_PORT = port;
                WS_URL = `ws://localhost:${BACKEND_PORT}/ws`;
                BACKEND_URL = `http://localhost:${BACKEND_PORT}`;
            }
        } catch (err) {
            console.warn("[Init] Could not get backend port, using default:", err);
        }
    }
    connect();
})();

