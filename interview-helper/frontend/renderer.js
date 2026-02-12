/**
 * Renderer Process
 * WebSocket client for the Interview Helper overlay.
 * Connects to the FastAPI backend and updates the UI in real time.
 */

// ── Configuration ──
const WS_URL = "ws://localhost:8765/ws";
const RECONNECT_DELAY_MS = 3000;
const MAX_TRANSCRIPT_LINES = 20;

// ── DOM Elements ──
const $ = (id) => document.getElementById(id);

const elements = {
    btnStart: $("btn-start"),
    btnStop: $("btn-stop"),
    btnClear: $("btn-clear"),
    btnMinimize: $("btn-minimize"),
    btnClose: $("btn-close"),
    statusDot: $("status-dot"),
    statusText: $("status-text"),
    transcript: $("transcript-content"),
    answer: $("answer-content"),
    bullets: $("bullets-content"),
    codeSection: $("section-code"),
    code: $("code-content"),
    followup: $("followup-content"),
    perfStt: $("perf-stt"),
    perfLlm: $("perf-llm"),
    perfTokens: $("perf-tokens"),
};

// ── State ──
let ws = null;
let transcriptLines = [];
let isCapturing = false;

// ── WebSocket Connection ──
function connect() {
    updateStatus("connecting", "Connecting...");

    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
        updateStatus("connected", "Connected");
        console.log("[WS] Connected to backend");
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
        updateStatus("disconnected", "Disconnected");
        console.log("[WS] Connection closed, reconnecting...");
        ws = null;
        setTimeout(connect, RECONNECT_DELAY_MS);
    };

    ws.onerror = (err) => {
        updateStatus("error", "Connection error");
        console.error("[WS] Error:", err);
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
        default:
            updateStatus("connected", msg.status);
    }
}

// ── Error ──
function onError(msg) {
    updateStatus("error", `Error: ${msg.error}`);
    console.error("[Backend]", msg.error);

    // Show error briefly, then restore
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

// Window controls via preload bridge
elements.btnMinimize.addEventListener("click", () => {
    if (window.electronAPI) window.electronAPI.minimizeWindow();
});

elements.btnClose.addEventListener("click", () => {
    if (window.electronAPI) window.electronAPI.closeWindow();
});

// ── Initialize ──
connect();
