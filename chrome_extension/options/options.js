"use strict";

const KEYS = ["serverUrl", "aiProvider", "aiModel", "ollamaUrl", "defaultSection", "outputDir"];

const DEFAULTS = {
  serverUrl: "http://127.0.0.1:8765",
  aiProvider: "rules",
  aiModel: "",
  ollamaUrl: "http://localhost:11434",
  defaultSection: "Auto-generated",
  outputDir: "tests/cases/crawled",
};

function load() {
  chrome.storage.local.get(DEFAULTS, (vals) => {
    document.getElementById("server-url").value       = vals.serverUrl;
    document.getElementById("ai-provider").value      = vals.aiProvider;
    document.getElementById("ai-model").value         = vals.aiModel;
    document.getElementById("ollama-url").value       = vals.ollamaUrl;
    document.getElementById("default-section").value  = vals.defaultSection;
    document.getElementById("output-dir").value       = vals.outputDir;
    toggleOllama(vals.aiProvider);
  });
}

function toggleOllama(provider) {
  const show = provider === "ollama";
  document.getElementById("row-ollama-url").style.display = show ? "" : "none";
}

document.getElementById("ai-provider").addEventListener("change", (e) => {
  toggleOllama(e.target.value);
});

document.getElementById("btn-save").addEventListener("click", () => {
  const vals = {
    serverUrl:      document.getElementById("server-url").value.trim(),
    aiProvider:     document.getElementById("ai-provider").value,
    aiModel:        document.getElementById("ai-model").value.trim(),
    ollamaUrl:      document.getElementById("ollama-url").value.trim(),
    defaultSection: document.getElementById("default-section").value.trim(),
    outputDir:      document.getElementById("output-dir").value.trim(),
  };
  chrome.storage.local.set(vals, () => {
    const msg = document.getElementById("save-msg");
    msg.classList.add("show");
    setTimeout(() => msg.classList.remove("show"), 2000);
  });
});

load();
