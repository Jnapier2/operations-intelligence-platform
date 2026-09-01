let csrfToken = "";
let mode = "static-showcase";
let session = { mode, authenticated: false, permissions: [] };
// Deliberately public local-demo credential. It proves server-side credential validation
// without embedding a real secret in a portfolio artifact. Production deployments must use an external IdP.
const DEMO_LOCAL_PASSWORD = "portfolio-demo";
const USER_BY_ROLE = {
    Executive: "exec-demo",
    Analyst: "analyst-demo",
    Operator: "operator-demo",
    "Data Steward": "steward-demo",
};
async function jsonFetch(url, init = {}) {
    const response = await fetch(url, { cache: "no-store", ...init });
    const contentType = response.headers.get("content-type") ?? "";
    const payload = contentType.includes("application/json") ? await response.json() : {};
    if (!response.ok) {
        const message = typeof payload.error === "string" ? payload.error : `Request failed with status ${response.status}.`;
        throw new Error(message);
    }
    return payload;
}
async function governedPlatformAvailable() {
    const response = await fetch("/api/session", { cache: "no-store" });
    if (response.status === 404)
        return false;
    const contentType = response.headers.get("content-type") ?? "";
    if (!contentType.includes("application/json")) {
        if (response.ok)
            return false;
        throw new Error(`Governed platform probe failed with status ${response.status}.`);
    }
    const payload = await response.json();
    if (!response.ok)
        throw new Error(`Governed platform probe failed with status ${response.status}.`);
    return payload.mode === "server-governed";
}
function writeHeaders() {
    return { "content-type": "application/json", "x-csrf-token": csrfToken };
}
export function platformMode() {
    return mode;
}
export function platformSession() {
    return session;
}
export async function initializePlatform(preferredRole) {
    if (!await governedPlatformAvailable()) {
        mode = "static-showcase";
        csrfToken = "";
        session = { mode, authenticated: false, permissions: [] };
        return session;
    }
    const result = await jsonFetch("/api/auth/demo-login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ userId: USER_BY_ROLE[preferredRole], password: DEMO_LOCAL_PASSWORD }),
    });
    mode = "server-governed";
    csrfToken = result.csrfToken;
    const state = await jsonFetch("/api/session");
    session = { mode, authenticated: state.authenticated, user: state.user, permissions: state.permissions ?? [] };
    return session;
}
export async function switchGovernedRole(nextRole) {
    if (mode !== "server-governed")
        return session;
    const result = await jsonFetch("/api/auth/demo-login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ userId: USER_BY_ROLE[nextRole], password: DEMO_LOCAL_PASSWORD }),
    });
    csrfToken = result.csrfToken;
    const state = await jsonFetch("/api/session");
    session = { mode, authenticated: state.authenticated, user: state.user, permissions: state.permissions ?? [] };
    return session;
}
export function hasPermission(permission) {
    return mode !== "server-governed" || session.permissions.includes(permission);
}
export async function governedCases() {
    const result = await jsonFetch("/api/cases");
    return result.cases;
}
export async function governedAudit() {
    if (!hasPermission("read_audit"))
        return [];
    const result = await jsonFetch("/api/audit");
    return result.audit;
}
export async function governedKpis() {
    if (!hasPermission("read_governance"))
        return [];
    const result = await jsonFetch("/api/kpis");
    return result.kpis;
}
export async function governedObservability() {
    if (!hasPermission("read_observability"))
        return null;
    return jsonFetch("/api/observability");
}
export async function governedCreateCase(payload) {
    const result = await jsonFetch("/api/cases", { method: "POST", headers: writeHeaders(), body: JSON.stringify(payload) });
    return result.case;
}
export async function governedUpdateCase(caseId, changes) {
    const result = await jsonFetch(`/api/cases/${encodeURIComponent(caseId)}`, { method: "PATCH", headers: writeHeaders(), body: JSON.stringify(changes) });
    return result.case;
}
export async function governedIngest(csv, datasetName, sourceName) {
    const result = await jsonFetch("/api/ingest", {
        method: "POST",
        headers: writeHeaders(),
        body: JSON.stringify({ csv, datasetName, sourceName }),
    });
    return result.ingestion;
}
export async function governedRefresh() {
    await jsonFetch("/api/refresh", { method: "POST", headers: writeHeaders(), body: "{}" });
}
export async function governedRecordBacktest(backtest) {
    if (!hasPermission("record_backtests"))
        return;
    await jsonFetch("/api/backtests", { method: "POST", headers: writeHeaders(), body: JSON.stringify(backtest) });
}
export async function governedAutomationState() {
    if (!hasPermission("read_automation"))
        return { rules: [], executions: [] };
    return jsonFetch("/api/automations");
}
export async function governedEvaluateAutomations(metrics, execute) {
    if (!hasPermission("run_automation"))
        return [];
    const result = await jsonFetch("/api/automations/evaluate", {
        method: "POST", headers: writeHeaders(), body: JSON.stringify({ metrics, execute }),
    });
    return result.executions;
}
export async function governedImprovementState() {
    if (!hasPermission("read_improvements"))
        return { problems: [], initiatives: [], value: { initiativesActive: 0, initiativesCompleted: 0, successful: 0, inconclusive: 0, hoursSavedMonthly: 0, backlogAvoided: 0, slaImprovementPoints: 0, measuredInitiatives: [] } };
    return jsonFetch("/api/improvements");
}
export async function governedPlaybookState() {
    if (!hasPermission("read_improvements"))
        return { playbooks: [], runs: [] };
    return jsonFetch("/api/playbooks");
}
export async function governedStartPlaybook(playbookId, caseId) {
    const result = await jsonFetch(`/api/playbooks/${encodeURIComponent(playbookId)}/start`, {
        method: "POST", headers: writeHeaders(), body: JSON.stringify({ caseId: caseId ?? null }),
    });
    return result.run;
}
export async function governedAdvancePlaybook(runId) {
    const result = await jsonFetch(`/api/playbook-runs/${encodeURIComponent(runId)}`, {
        method: "PATCH", headers: writeHeaders(), body: "{}",
    });
    return result.run;
}
//# sourceMappingURL=api.js.map