import type {
  AuditEvent,
  AutomationExecution,
  AutomationRule,
  ForecastBacktest,
  GovernedKpiDefinition,
  ImprovementInitiative,
  ObservabilitySnapshot,
  PlatformMode,
  PlatformSession,
  PlaybookDefinition,
  PlaybookRun,
  ProblemRecord,
  Role,
  ValueRealizationSnapshot,
  WorkflowCase,
} from "./types.js";

let csrfToken = "";
let mode: PlatformMode = "static-showcase";
let session: PlatformSession = { mode, authenticated: false, permissions: [] };

// Deliberately public local-demo credential. It proves server-side credential validation
// without embedding a real secret in a portfolio artifact. Production deployments must use an external IdP.
const DEMO_LOCAL_PASSWORD = "portfolio-demo";

const USER_BY_ROLE: Record<Role, string> = {
  Executive: "exec-demo",
  Analyst: "analyst-demo",
  Operator: "operator-demo",
  "Data Steward": "steward-demo",
};

async function jsonFetch<T>(url: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(url, { cache: "no-store", ...init });
  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json") ? await response.json() as Record<string, unknown> : {};
  if (!response.ok) {
    const message = typeof payload.error === "string" ? payload.error : `Request failed with status ${response.status}.`;
    throw new Error(message);
  }
  return payload as T;
}

async function governedPlatformAvailable(): Promise<boolean> {
  const response = await fetch("/api/session", { cache: "no-store" });
  if (response.status === 404) return false;
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    if (response.ok) return false;
    throw new Error(`Governed platform probe failed with status ${response.status}.`);
  }
  const payload = await response.json() as { mode?: PlatformMode };
  if (!response.ok) throw new Error(`Governed platform probe failed with status ${response.status}.`);
  return payload.mode === "server-governed";
}

function writeHeaders(): HeadersInit {
  return { "content-type": "application/json", "x-csrf-token": csrfToken };
}

export function platformMode(): PlatformMode {
  return mode;
}

export function platformSession(): PlatformSession {
  return session;
}

export async function initializePlatform(preferredRole: Role): Promise<PlatformSession> {
  if (!await governedPlatformAvailable()) {
    mode = "static-showcase";
    csrfToken = "";
    session = { mode, authenticated: false, permissions: [] };
    return session;
  }

  const result = await jsonFetch<{ authenticated: boolean; csrfToken: string; user: { id: string; displayName: string; role: Role } }>("/api/auth/demo-login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ userId: USER_BY_ROLE[preferredRole], password: DEMO_LOCAL_PASSWORD }),
  });
  mode = "server-governed";
  csrfToken = result.csrfToken;
  const state = await jsonFetch<{ authenticated: boolean; user: { id: string; displayName: string; role: Role }; permissions: string[] }>("/api/session");
  session = { mode, authenticated: state.authenticated, user: state.user, permissions: state.permissions ?? [] };
  return session;
}

export async function switchGovernedRole(nextRole: Role): Promise<PlatformSession> {
  if (mode !== "server-governed") return session;
  const result = await jsonFetch<{ csrfToken: string; user: { id: string; displayName: string; role: Role } }>("/api/auth/demo-login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ userId: USER_BY_ROLE[nextRole], password: DEMO_LOCAL_PASSWORD }),
  });
  csrfToken = result.csrfToken;
  const state = await jsonFetch<{ authenticated: boolean; user: { id: string; displayName: string; role: Role }; permissions: string[] }>("/api/session");
  session = { mode, authenticated: state.authenticated, user: state.user, permissions: state.permissions ?? [] };
  return session;
}

export function hasPermission(permission: string): boolean {
  return mode !== "server-governed" || session.permissions.includes(permission);
}

export async function governedCases(): Promise<WorkflowCase[]> {
  const result = await jsonFetch<{ cases: WorkflowCase[] }>("/api/cases");
  return result.cases;
}

export async function governedAudit(): Promise<AuditEvent[]> {
  if (!hasPermission("read_audit")) return [];
  const result = await jsonFetch<{ audit: AuditEvent[] }>("/api/audit");
  return result.audit;
}

export async function governedKpis(): Promise<GovernedKpiDefinition[]> {
  if (!hasPermission("read_governance")) return [];
  const result = await jsonFetch<{ kpis: GovernedKpiDefinition[] }>("/api/kpis");
  return result.kpis;
}

export async function governedObservability(): Promise<ObservabilitySnapshot | null> {
  if (!hasPermission("read_observability")) return null;
  return jsonFetch<ObservabilitySnapshot>("/api/observability");
}

export async function governedCreateCase(payload: Partial<WorkflowCase>): Promise<WorkflowCase> {
  const result = await jsonFetch<{ case: WorkflowCase }>("/api/cases", { method: "POST", headers: writeHeaders(), body: JSON.stringify(payload) });
  return result.case;
}

export async function governedUpdateCase(caseId: string, changes: Partial<WorkflowCase>): Promise<WorkflowCase> {
  const result = await jsonFetch<{ case: WorkflowCase }>(`/api/cases/${encodeURIComponent(caseId)}`, { method: "PATCH", headers: writeHeaders(), body: JSON.stringify(changes) });
  return result.case;
}

export async function governedIngest(csv: string, datasetName: string, sourceName: string): Promise<{ status: string; idempotent: boolean; qualityScore: number; rowCount: number; trustedRowCount: number; issueRowCount: number; unexpectedColumns: string[] }> {
  const result = await jsonFetch<{ ingestion: { status: string; idempotent: boolean; qualityScore: number; rowCount: number; trustedRowCount: number; issueRowCount: number; unexpectedColumns: string[] } }>("/api/ingest", {
    method: "POST",
    headers: writeHeaders(),
    body: JSON.stringify({ csv, datasetName, sourceName }),
  });
  return result.ingestion;
}

export async function governedRefresh(): Promise<void> {
  await jsonFetch("/api/refresh", { method: "POST", headers: writeHeaders(), body: "{}" });
}

export async function governedRecordBacktest(backtest: ForecastBacktest): Promise<void> {
  if (!hasPermission("record_backtests")) return;
  await jsonFetch("/api/backtests", { method: "POST", headers: writeHeaders(), body: JSON.stringify(backtest) });
}

export async function governedAutomationState(): Promise<{ rules: AutomationRule[]; executions: AutomationExecution[] }> {
  if (!hasPermission("read_automation")) return { rules: [], executions: [] };
  return jsonFetch<{ rules: AutomationRule[]; executions: AutomationExecution[] }>("/api/automations");
}

export async function governedEvaluateAutomations(metrics: Record<string, number>, execute: boolean): Promise<AutomationExecution[]> {
  if (!hasPermission("run_automation")) return [];
  const result = await jsonFetch<{ executions: AutomationExecution[] }>("/api/automations/evaluate", {
    method: "POST", headers: writeHeaders(), body: JSON.stringify({ metrics, execute }),
  });
  return result.executions;
}

export async function governedImprovementState(): Promise<{ problems: ProblemRecord[]; initiatives: ImprovementInitiative[]; value: ValueRealizationSnapshot }> {
  if (!hasPermission("read_improvements")) return { problems: [], initiatives: [], value: { initiativesActive: 0, initiativesCompleted: 0, successful: 0, inconclusive: 0, hoursSavedMonthly: 0, backlogAvoided: 0, slaImprovementPoints: 0, measuredInitiatives: [] } };
  return jsonFetch<{ problems: ProblemRecord[]; initiatives: ImprovementInitiative[]; value: ValueRealizationSnapshot }>("/api/improvements");
}

export async function governedPlaybookState(): Promise<{ playbooks: PlaybookDefinition[]; runs: PlaybookRun[] }> {
  if (!hasPermission("read_improvements")) return { playbooks: [], runs: [] };
  return jsonFetch<{ playbooks: PlaybookDefinition[]; runs: PlaybookRun[] }>("/api/playbooks");
}

export async function governedStartPlaybook(playbookId: string, caseId?: string): Promise<PlaybookRun> {
  const result = await jsonFetch<{ run: PlaybookRun }>(`/api/playbooks/${encodeURIComponent(playbookId)}/start`, {
    method: "POST", headers: writeHeaders(), body: JSON.stringify({ caseId: caseId ?? null }),
  });
  return result.run;
}

export async function governedAdvancePlaybook(runId: string): Promise<PlaybookRun> {
  const result = await jsonFetch<{ run: PlaybookRun }>(`/api/playbook-runs/${encodeURIComponent(runId)}`, {
    method: "PATCH", headers: writeHeaders(), body: "{}",
  });
  return result.run;
}
