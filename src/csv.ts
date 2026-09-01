import type { QualityIssue, QualityReport, QualityRuleResult, ServiceRecord, Severity } from "./types.js";

const REQUIRED_COLUMNS = [
  "request_id",
  "created_at",
  "closed_at",
  "status",
  "priority",
  "category",
  "subcategory",
  "location",
  "team",
  "owner",
  "channel",
  "sla_hours",
  "resolution_hours",
  "reopened",
  "satisfaction_score",
  "last_updated_at",
  "source_system",
] as const;

const KNOWN_CATEGORIES = new Set([
  "Account Access",
  "Billing & Payments",
  "Delivery & Fulfillment",
  "Equipment & Maintenance",
  "Permit & Compliance",
  "General Inquiry",
]);
const KNOWN_PRIORITIES = new Set(["Low", "Normal", "High", "Critical"]);
const KNOWN_STATUSES = new Set(["Open", "In Progress", "Pending Customer", "Closed"]);

export interface ParsedCsv {
  headers: string[];
  rows: Record<string, string>[];
}

/**
 * Escape a value for CSV while neutralizing spreadsheet formula execution.
 * Numeric values remain numeric; untrusted string values beginning with a
 * formula marker are prefixed with an apostrophe before normal CSV quoting.
 */
export function csvEscape(value: unknown): string {
  let text = value instanceof Date ? value.toISOString() : String(value ?? "");
  if (typeof value === "string" && /^[=+@\-\t\r]/.test(text)) text = `'${text}`;
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function parseCsv(text: string): ParsedCsv {
  const matrix: string[][] = [];
  let row: string[] = [];
  let field = "";
  let inQuotes = false;

  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    const next = text[index + 1];

    if (inQuotes) {
      if (character === '"' && next === '"') {
        field += '"';
        index += 1;
      } else if (character === '"') {
        inQuotes = false;
      } else {
        field += character;
      }
      continue;
    }

    if (character === '"') {
      inQuotes = true;
    } else if (character === ",") {
      row.push(field);
      field = "";
    } else if (character === "\n") {
      row.push(field.replace(/\r$/, ""));
      if (row.some((value) => value.trim() !== "")) matrix.push(row);
      row = [];
      field = "";
    } else {
      field += character;
    }
  }

  if (field.length > 0 || row.length > 0) {
    row.push(field.replace(/\r$/, ""));
    if (row.some((value) => value.trim() !== "")) matrix.push(row);
  }

  if (matrix.length === 0) return { headers: [], rows: [] };
  const headers = matrix[0].map((value) => value.trim().toLowerCase());
  const rows = matrix.slice(1).map((values) => {
    const item: Record<string, string> = {};
    headers.forEach((header, columnIndex) => {
      item[header] = (values[columnIndex] ?? "").trim();
    });
    return item;
  });
  return { headers, rows };
}

export function validateHeaders(headers: string[]): string[] {
  const available = new Set(headers);
  return REQUIRED_COLUMNS.filter((column) => !available.has(column));
}

function parseDate(value: string): Date | null {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isFinite(parsed.getTime()) ? parsed : null;
}

function parseNumber(value: string): number | null {
  if (value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizeBoolean(value: string): boolean {
  return ["yes", "true", "1", "y"].includes(value.trim().toLowerCase());
}

export function toServiceRecords(rows: Record<string, string>[]): ServiceRecord[] {
  return rows.map((raw, index) => ({
    requestId: raw.request_id ?? "",
    createdAt: parseDate(raw.created_at ?? ""),
    closedAt: parseDate(raw.closed_at ?? ""),
    status: raw.status ?? "",
    priority: raw.priority ?? "",
    category: raw.category ?? "",
    subcategory: raw.subcategory ?? "",
    location: raw.location ?? "",
    team: raw.team ?? "",
    owner: raw.owner ?? "",
    channel: raw.channel ?? "",
    slaHours: parseNumber(raw.sla_hours ?? ""),
    resolutionHours: parseNumber(raw.resolution_hours ?? ""),
    reopened: normalizeBoolean(raw.reopened ?? ""),
    satisfactionScore: parseNumber(raw.satisfaction_score ?? ""),
    lastUpdatedAt: parseDate(raw.last_updated_at ?? ""),
    sourceSystem: raw.source_system ?? "",
    rowNumber: index + 2,
    raw,
  }));
}

function issue(
  record: ServiceRecord,
  ruleId: string,
  field: string,
  severity: Severity,
  message: string,
  value: unknown,
): QualityIssue {
  return {
    id: `${ruleId}-${record.rowNumber}-${field}`,
    rowNumber: record.rowNumber,
    requestId: record.requestId || "(missing)",
    ruleId,
    field,
    severity,
    message,
    value: String(value ?? ""),
  };
}

function scoreRule(id: string, name: string, dimension: QualityRuleResult["dimension"], description: string, severity: Severity, failed: number, total: number): QualityRuleResult {
  const passed = Math.max(0, total - failed);
  return {
    id,
    name,
    dimension,
    description,
    severity,
    passed,
    failed,
    score: total === 0 ? 100 : Math.round((passed / total) * 1000) / 10,
  };
}

export function validateRecords(records: ServiceRecord[]): QualityReport {
  const issues: QualityIssue[] = [];
  const seen = new Map<string, number>();
  const failureCounts = new Map<string, number>();
  const add = (item: QualityIssue) => {
    issues.push(item);
    failureCounts.set(item.ruleId, (failureCounts.get(item.ruleId) ?? 0) + 1);
  };

  for (const record of records) {
    if (!record.requestId) add(issue(record, "required-id", "request_id", "Critical", "Request ID is required.", record.requestId));
    if (!record.createdAt) add(issue(record, "valid-created", "created_at", "Critical", "Created timestamp is missing or invalid.", record.raw.created_at));
    if (!record.status) add(issue(record, "required-status", "status", "High", "Status is required.", record.status));
    if (!record.category) add(issue(record, "required-category", "category", "High", "Category is required.", record.category));
    if (!record.location) add(issue(record, "required-location", "location", "Medium", "Location is required for geographic analysis.", record.location));
    if (!record.team) add(issue(record, "required-team", "team", "High", "Team is required for accountability reporting.", record.team));
    if (!record.owner) add(issue(record, "required-owner", "owner", "Medium", "Owner is required for work assignment.", record.owner));
    if (!KNOWN_CATEGORIES.has(record.category)) add(issue(record, "known-category", "category", "High", "Category is not mapped to the controlled taxonomy.", record.category));
    if (!KNOWN_PRIORITIES.has(record.priority)) add(issue(record, "known-priority", "priority", "High", "Priority is not recognized.", record.priority));
    if (!KNOWN_STATUSES.has(record.status)) add(issue(record, "known-status", "status", "High", "Status is not recognized.", record.status));
    if (record.slaHours === null || record.slaHours <= 0) add(issue(record, "valid-sla", "sla_hours", "High", "SLA hours must be a positive number.", record.raw.sla_hours));
    if (record.satisfactionScore !== null && (record.satisfactionScore < 1 || record.satisfactionScore > 5)) {
      add(issue(record, "valid-satisfaction", "satisfaction_score", "Medium", "Satisfaction score must be between 1 and 5.", record.satisfactionScore));
    }
    if (record.closedAt && record.createdAt && record.closedAt < record.createdAt) {
      add(issue(record, "chronology", "closed_at", "Critical", "Closed timestamp occurs before created timestamp.", record.raw.closed_at));
    }
    if (record.status === "Closed" && !record.closedAt) add(issue(record, "closed-consistency", "closed_at", "High", "Closed records require a closed timestamp.", record.raw.closed_at));
    if (record.status !== "Closed" && record.closedAt) add(issue(record, "open-consistency", "closed_at", "Medium", "Open records should not have a closed timestamp.", record.raw.closed_at));
    if (record.resolutionHours !== null && record.resolutionHours < 0) add(issue(record, "valid-resolution", "resolution_hours", "Critical", "Resolution hours cannot be negative.", record.resolutionHours));
    if (!record.lastUpdatedAt) add(issue(record, "valid-updated", "last_updated_at", "Medium", "Last-updated timestamp is missing or invalid.", record.raw.last_updated_at));

    if (record.requestId) {
      const firstRow = seen.get(record.requestId);
      if (firstRow !== undefined) {
        add(issue(record, "unique-id", "request_id", "Critical", `Duplicate request ID; first seen on row ${firstRow}.`, record.requestId));
      } else {
        seen.set(record.requestId, record.rowNumber);
      }
    }
  }

  const total = Math.max(records.length, 1);
  const rules: QualityRuleResult[] = [
    scoreRule("required-id", "Request ID completeness", "Completeness", "Every record must have a stable request identifier.", "Critical", failureCounts.get("required-id") ?? 0, total),
    scoreRule("required-location", "Location completeness", "Completeness", "Location must be present for geographic drill-down.", "Medium", failureCounts.get("required-location") ?? 0, total),
    scoreRule("required-team", "Team completeness", "Completeness", "Team must be present for accountability metrics.", "High", failureCounts.get("required-team") ?? 0, total),
    scoreRule("unique-id", "Request ID uniqueness", "Uniqueness", "Request identifiers must occur once in the analytical grain.", "Critical", failureCounts.get("unique-id") ?? 0, total),
    scoreRule("known-category", "Category validity", "Validity", "Categories must map to the controlled service taxonomy.", "High", failureCounts.get("known-category") ?? 0, total),
    scoreRule("valid-sla", "SLA validity", "Validity", "Service targets must be positive numeric values.", "High", failureCounts.get("valid-sla") ?? 0, total),
    scoreRule("valid-satisfaction", "Satisfaction validity", "Validity", "Survey scores must fall between one and five.", "Medium", failureCounts.get("valid-satisfaction") ?? 0, total),
    scoreRule("chronology", "Timestamp chronology", "Consistency", "Closed time cannot precede created time.", "Critical", failureCounts.get("chronology") ?? 0, total),
    scoreRule("closed-consistency", "Status and closure consistency", "Consistency", "Closed status requires a closed timestamp.", "High", failureCounts.get("closed-consistency") ?? 0, total),
    scoreRule("valid-updated", "Update timestamp validity", "Timeliness", "Records require a usable last-updated timestamp.", "Medium", failureCounts.get("valid-updated") ?? 0, total),
  ];

  const severityWeight: Record<Severity, number> = { Critical: 4.0, High: 2.5, Medium: 1.5, Low: 0.75 };
  const weightedDefects = issues.reduce((sum, item) => sum + severityWeight[item.severity], 0);
  const maximumWeight = total * 4.0;
  const score = Math.max(0, Math.round((1 - weightedDefects / maximumWeight) * 1000) / 10);
  const issueRows = new Set(issues.map((item) => item.rowNumber));

  return {
    score,
    validRowCount: records.length - issueRows.size,
    issueRowCount: issueRows.size,
    duplicateRowCount: failureCounts.get("unique-id") ?? 0,
    issues,
    rules,
  };
}

export function trustedRecords(records: ServiceRecord[], report: QualityReport): ServiceRecord[] {
  const blockingRows = new Set(
    report.issues
      .filter((item) => item.severity === "Critical" || item.ruleId === "known-category" || item.ruleId === "valid-sla")
      .map((item) => item.rowNumber),
  );
  return records.filter((record) => !blockingRows.has(record.rowNumber));
}

export async function loadCsvDataset(url: string): Promise<{ records: ServiceRecord[]; quality: QualityReport }> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`Dataset request failed with status ${response.status}.`);
  const parsed = parseCsv(await response.text());
  const missing = validateHeaders(parsed.headers);
  if (missing.length > 0) throw new Error(`Dataset is missing required columns: ${missing.join(", ")}.`);
  const records = toServiceRecords(parsed.rows);
  return { records, quality: validateRecords(records) };
}
