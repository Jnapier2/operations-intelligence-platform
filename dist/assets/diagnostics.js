const LOG_KEY = "operations-intelligence.recent-log.v1";
const CRASH_KEY = "operations-intelligence.crash-capsule.v1";
const MAX_EVENTS = 40;
function redact(value) {
    return value
        .replace(/(api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+/gi, "$1=[REDACTED]")
        .slice(0, 8000);
}
function readLog() {
    try {
        return JSON.parse(localStorage.getItem(LOG_KEY) ?? "[]");
    }
    catch {
        return [];
    }
}
export function logEvent(level, message, details = "") {
    const events = readLog();
    events.push({ timestamp: new Date().toISOString(), level, message: redact(message), details: redact(details) });
    try {
        localStorage.setItem(LOG_KEY, JSON.stringify(events.slice(-MAX_EVENTS)));
    }
    catch {
        // Diagnostics are best-effort and must never break the application.
    }
}
async function sendCapsule(capsule) {
    try {
        const controller = new AbortController();
        const timer = window.setTimeout(() => controller.abort(), 1800);
        await fetch("/__diagnostics/critical", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify(capsule).slice(0, 32_000),
            signal: controller.signal,
            keepalive: true,
        });
        window.clearTimeout(timer);
    }
    catch {
        // Static hosting has no local diagnostic endpoint; localStorage is the fallback.
    }
}
export function reportCritical(error, context) {
    const normalized = error instanceof Error ? { name: error.name, message: error.message, stack: error.stack ?? "" } : { name: "UnknownError", message: String(error), stack: "" };
    const capsule = {
        schemaVersion: 1,
        project: "Operations Intelligence & Automation Platform",
        trigger: "browser-critical",
        timestamp: new Date().toISOString(),
        context: redact(context),
        error: {
            name: redact(normalized.name),
            message: redact(normalized.message),
            stack: redact(normalized.stack),
        },
        page: location.pathname,
        userAgent: navigator.userAgent.slice(0, 400),
        recentLog: readLog(),
    };
    try {
        localStorage.setItem(CRASH_KEY, JSON.stringify(capsule));
    }
    catch {
        // A missing browser fallback must not cause a recursive error.
    }
    void sendCapsule(capsule);
}
export function installGlobalDiagnostics() {
    window.addEventListener("error", (event) => {
        reportCritical(event.error ?? event.message, "window.error");
    });
    window.addEventListener("unhandledrejection", (event) => {
        reportCritical(event.reason, "window.unhandledrejection");
    });
    logEvent("info", "Application diagnostics initialized.");
}
export function downloadBrowserDiagnostics() {
    const payload = {
        exportedAt: new Date().toISOString(),
        crashCapsule: (() => {
            try {
                return JSON.parse(localStorage.getItem(CRASH_KEY) ?? "null");
            }
            catch {
                return null;
            }
        })(),
        recentLog: readLog(),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "Operations_Intelligence_Browser_Diagnostics.json";
    link.click();
    URL.revokeObjectURL(link.href);
}
//# sourceMappingURL=diagnostics.js.map