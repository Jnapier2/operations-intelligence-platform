const CASES_KEY = "operations-intelligence.cases.v1";
const AUDIT_KEY = "operations-intelligence.audit.v1";
const ROLE_KEY = "operations-intelligence.role.v1";
const DATASET_KEY = "operations-intelligence.dataset-name.v1";
function storageGet(key) {
    try {
        return localStorage.getItem(key);
    }
    catch {
        return null;
    }
}
function storageSet(key, value) {
    try {
        localStorage.setItem(key, value);
        return true;
    }
    catch {
        return false;
    }
}
function storageRemove(key) {
    try {
        localStorage.removeItem(key);
    }
    catch {
        // Storage is optional for the portfolio demo.
    }
}
function readJson(key, fallback) {
    try {
        const value = storageGet(key);
        return value ? JSON.parse(value) : fallback;
    }
    catch {
        return fallback;
    }
}
function writeJson(key, value) {
    storageSet(key, JSON.stringify(value));
}
function isoOffset(days) {
    const date = new Date("2026-08-24T18:00:00Z");
    date.setUTCDate(date.getUTCDate() + days);
    return date.toISOString();
}
export function loadRole() {
    const value = storageGet(ROLE_KEY);
    return value === "Executive" || value === "Analyst" || value === "Operator" || value === "Data Steward" ? value : "Executive";
}
export function saveRole(role) {
    storageSet(ROLE_KEY, role);
}
export function saveDatasetName(name) {
    storageSet(DATASET_KEY, name);
}
export function loadDatasetName() {
    return storageGet(DATASET_KEY);
}
export function seedCases(recommendations) {
    const existing = readJson(CASES_KEY, []);
    if (existing.length > 0)
        return existing;
    const owners = ["Operations Manager", "Billing Lead", "Data Steward", "Service Delivery Lead", "Operations Analyst"];
    const seeded = recommendations.slice(0, 5).map((recommendation, index) => ({
        id: `CASE-${String(index + 1).padStart(3, "0")}`,
        title: recommendation.title,
        description: recommendation.rationale,
        priority: recommendation.priority,
        status: (index === 3 ? "Monitoring" : index === 4 ? "Resolved" : index === 1 ? "In Progress" : "Open"),
        owner: owners[index % owners.length],
        createdAt: isoOffset(-Math.max(1, 7 - index)),
        dueAt: isoOffset(index + 3),
        source: recommendation.sourceAlertId ? `Alert ${recommendation.sourceAlertId}` : "Analytical recommendation",
        expectedImpact: recommendation.expectedImpact,
        baselineMetric: index % 2 === 0 ? "SLA attainment" : "Open backlog",
        baselineValue: index % 2 === 0 ? 72 + index : 38 + index * 4,
        targetValue: index % 2 === 0 ? 88 : 28,
        currentValue: index % 2 === 0 ? 78 + index : 34 + index * 2,
        unit: index % 2 === 0 ? "%" : " requests",
        notes: "",
    }));
    writeJson(CASES_KEY, seeded);
    return seeded;
}
export function loadCases() {
    return readJson(CASES_KEY, []);
}
export function saveCases(cases) {
    writeJson(CASES_KEY, cases);
}
export function updateCase(caseId, changes) {
    const next = loadCases().map((item) => (item.id === caseId ? { ...item, ...changes } : item));
    saveCases(next);
    return next;
}
export function loadAudit() {
    const existing = readJson(AUDIT_KEY, []);
    if (existing.length > 0)
        return existing;
    const seeded = [
        {
            id: "AUD-001",
            timestamp: "2026-08-24T18:05:00Z",
            actor: "System",
            action: "Dataset validated",
            entityType: "Dataset",
            entityId: "Synthetic Service Operations Demo",
            details: "Validation rules executed; blocking rows quarantined from trusted KPI calculations.",
        },
        {
            id: "AUD-002",
            timestamp: "2026-08-24T18:06:00Z",
            actor: "System",
            action: "Alerts generated",
            entityType: "Analysis",
            entityId: "Current reporting cycle",
            details: "Volume, backlog, service-level, and data-quality signals compared with prior baselines.",
        },
        {
            id: "AUD-003",
            timestamp: "2026-08-24T18:08:00Z",
            actor: "Operations Manager",
            action: "Case assigned",
            entityType: "Case",
            entityId: "CASE-002",
            details: "Billing recovery case assigned for seven-day follow-up.",
        },
    ];
    writeJson(AUDIT_KEY, seeded);
    return seeded;
}
export function addAudit(actor, action, entityType, entityId, details) {
    const events = loadAudit();
    const item = {
        id: `AUD-${Date.now().toString(36).toUpperCase()}`,
        timestamp: new Date().toISOString(),
        actor,
        action,
        entityType,
        entityId,
        details,
    };
    const next = [item, ...events].slice(0, 250);
    writeJson(AUDIT_KEY, next);
    return next;
}
export function resetLocalState() {
    storageRemove(CASES_KEY);
    storageRemove(AUDIT_KEY);
    storageRemove(DATASET_KEY);
}
//# sourceMappingURL=storage.js.map