import type { AuditEvent, CaseStatus, Recommendation, Role, WorkflowCase } from "./types.js";

const CASES_KEY = "operations-intelligence.cases.v1";
const AUDIT_KEY = "operations-intelligence.audit.v1";
const ROLE_KEY = "operations-intelligence.role.v1";
const DATASET_KEY = "operations-intelligence.dataset-name.v1";

function storageGet(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function storageSet(key: string, value: string): boolean {
  try {
    localStorage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

function storageRemove(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    // Storage is optional for the portfolio demo.
  }
}

function readJson<T>(key: string, fallback: T): T {
  try {
    const value = storageGet(key);
    return value ? (JSON.parse(value) as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson<T>(key: string, value: T): void {
  storageSet(key, JSON.stringify(value));
}

function isoOffset(days: number): string {
  const date = new Date("2026-08-24T18:00:00Z");
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString();
}

export function loadRole(): Role {
  const value = storageGet(ROLE_KEY);
  return value === "Executive" || value === "Analyst" || value === "Operator" || value === "Data Steward" ? value : "Executive";
}

export function saveRole(role: Role): void {
  storageSet(ROLE_KEY, role);
}

export function saveDatasetName(name: string): void {
  storageSet(DATASET_KEY, name);
}

export function loadDatasetName(): string | null {
  return storageGet(DATASET_KEY);
}

export function seedCases(recommendations: Recommendation[]): WorkflowCase[] {
  const existing = readJson<WorkflowCase[]>(CASES_KEY, []);
  if (existing.length > 0) return existing;
  const owners = ["Operations Manager", "Billing Lead", "Data Steward", "Service Delivery Lead", "Operations Analyst"];
  const seeded = recommendations.slice(0, 5).map((recommendation, index) => ({
    id: `CASE-${String(index + 1).padStart(3, "0")}`,
    title: recommendation.title,
    description: recommendation.rationale,
    priority: recommendation.priority,
    status: (index === 3 ? "Monitoring" : index === 4 ? "Resolved" : index === 1 ? "In Progress" : "Open") as CaseStatus,
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

export function loadCases(): WorkflowCase[] {
  return readJson<WorkflowCase[]>(CASES_KEY, []);
}

export function saveCases(cases: WorkflowCase[]): void {
  writeJson(CASES_KEY, cases);
}

export function updateCase(caseId: string, changes: Partial<WorkflowCase>): WorkflowCase[] {
  const next = loadCases().map((item) => (item.id === caseId ? { ...item, ...changes } : item));
  saveCases(next);
  return next;
}

export function loadAudit(): AuditEvent[] {
  const existing = readJson<AuditEvent[]>(AUDIT_KEY, []);
  if (existing.length > 0) return existing;
  const seeded: AuditEvent[] = [
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

export function addAudit(actor: string, action: string, entityType: string, entityId: string, details: string): AuditEvent[] {
  const events = loadAudit();
  const item: AuditEvent = {
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

export function resetLocalState(): void {
  storageRemove(CASES_KEY);
  storageRemove(AUDIT_KEY);
  storageRemove(DATASET_KEY);
}
