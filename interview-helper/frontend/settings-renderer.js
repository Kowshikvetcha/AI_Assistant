// ── Settings Renderer ──

// Provider defaults mirroring PROVIDER_PRESETS in backend/config.py
const PROVIDER_DEFAULTS = {
  openai:     { llm: "gpt-4o",           summary: "gpt-4o-mini",           stt: "whisper-1" },
  groq:       { llm: "openai/gpt-oss-120b", summary: "llama-3.1-8b-instant", stt: "whisper-large-v3" },
  openrouter: { llm: "openai/gpt-4o-mini",  summary: "openai/gpt-4o-mini",  stt: "whisper-1" },
  together:   { llm: "meta-llama/Llama-3.1-8B-Instruct-Turbo", summary: "meta-llama/Llama-3.1-8B-Instruct-Turbo", stt: "whisper-1" },
  fireworks:  { llm: "accounts/fireworks/models/llama-v3p1-8b-instruct", summary: "accounts/fireworks/models/llama-v3p1-8b-instruct", stt: "whisper-v3" },
  deepseek:   { llm: "deepseek-chat",    summary: "deepseek-chat",          stt: "whisper-1" },
  ollama:     { llm: "llama3.1:8b",      summary: "llama3.1:8b",            stt: "whisper-1" },
};

const PROVIDER_HINTS = {
  openai:     "Get your key at platform.openai.com/api-keys",
  groq:       "Get your key at console.groq.com",
  openrouter: "Get your key at openrouter.ai/keys",
  together:   "Get your key at api.together.xyz/settings/api-keys",
  fireworks:  "Get your key at fireworks.ai/account/api-keys",
  deepseek:   "Get your key at platform.deepseek.com/api_keys",
  ollama:     "No API key needed for local Ollama — enter any placeholder",
};

// DOM elements
const els = {
  provider:     document.getElementById("ai-provider"),
  apiKey:       document.getElementById("api-key"),
  llmModel:     document.getElementById("llm-model"),
  summaryModel: document.getElementById("summary-model"),
  sttModel:     document.getElementById("stt-model"),
  providerHint: document.getElementById("provider-hint"),
  toggleKey:    document.getElementById("toggle-key"),
  btnSave:      document.getElementById("btn-save"),
  btnCancel:    document.getElementById("btn-cancel"),
  btnClose:     document.getElementById("btn-close"),
  msg:          document.getElementById("msg"),
};

// ── Helpers ──

function updatePlaceholders() {
  const provider = els.provider.value;
  const defaults = PROVIDER_DEFAULTS[provider] || {};
  els.llmModel.placeholder     = defaults.llm     ? `Default: ${defaults.llm}`     : "";
  els.summaryModel.placeholder = defaults.summary  ? `Default: ${defaults.summary}` : "";
  els.sttModel.placeholder     = defaults.stt      ? `Default: ${defaults.stt}`     : "";
  els.providerHint.textContent = PROVIDER_HINTS[provider] || "";
}

function validateForm() {
  const hasProvider = !!els.provider.value;
  const hasKey      = !!els.apiKey.value.trim();
  els.btnSave.disabled = !(hasProvider && hasKey);
}

function showMsg(text, type) {
  els.msg.textContent = text;
  els.msg.className = `msg ${type}`;
}

function clearMsg() {
  els.msg.textContent = "";
  els.msg.className = "msg";
}

// ── Load saved settings ──

async function loadSettings() {
  if (!window.electronAPI) return;
  try {
    const settings = await window.electronAPI.getSettings();
    if (settings.AI_PROVIDER)   els.provider.value   = settings.AI_PROVIDER;
    if (settings.AI_API_KEY)    els.apiKey.value      = settings.AI_API_KEY;
    if (settings.LLM_MODEL)     els.llmModel.value    = settings.LLM_MODEL;
    if (settings.SUMMARY_MODEL) els.summaryModel.value = settings.SUMMARY_MODEL;
    if (settings.STT_MODEL)     els.sttModel.value    = settings.STT_MODEL;
  } catch (err) {
    console.error("Failed to load settings:", err);
  }
  updatePlaceholders();
  validateForm();
}

// ── Save settings ──

async function saveSettings() {
  if (!window.electronAPI) return;

  const provider = els.provider.value;
  const apiKey   = els.apiKey.value.trim();

  if (!provider || !apiKey) {
    showMsg("AI Provider and API Key are required.", "error");
    return;
  }

  const settings = {
    AI_PROVIDER:   provider,
    AI_API_KEY:    apiKey,
    LLM_MODEL:     els.llmModel.value.trim()     || "",
    SUMMARY_MODEL: els.summaryModel.value.trim()  || "",
    STT_MODEL:     els.sttModel.value.trim()      || "",
  };

  try {
    await window.electronAPI.saveSettings(settings);
    showMsg("Settings saved. Restarting backend...", "success");
  } catch (err) {
    showMsg("Failed to save settings.", "error");
    console.error(err);
  }
}

// ── Event listeners ──

els.provider.addEventListener("change", () => {
  updatePlaceholders();
  validateForm();
  clearMsg();
});

els.apiKey.addEventListener("input", () => {
  validateForm();
  clearMsg();
});

els.toggleKey.addEventListener("click", () => {
  const isPassword = els.apiKey.type === "password";
  els.apiKey.type = isPassword ? "text" : "password";
});

els.btnSave.addEventListener("click", saveSettings);

els.btnCancel.addEventListener("click", () => {
  if (window.electronAPI) window.electronAPI.closeSettings();
});

els.btnClose.addEventListener("click", () => {
  if (window.electronAPI) window.electronAPI.closeSettings();
});

// Allow Enter key to save when form is valid
document.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !els.btnSave.disabled) {
    saveSettings();
  }
  if (e.key === "Escape") {
    if (window.electronAPI) window.electronAPI.closeSettings();
  }
});

// ── Init ──
loadSettings();
