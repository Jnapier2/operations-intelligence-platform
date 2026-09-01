import { buildAnalytics, groundedSummary, runScenario } from "./analytics.js";
import { answerOperationsQuestion, buildIntelligence, classifyRequestText } from "./intelligence.js";
import {
  governedAdvancePlaybook,
  governedAudit,
  governedAutomationState,
  governedCases,
  governedCreateCase,
  governedEvaluateAutomations,
  governedImprovementState,
  governedIngest,
  governedKpis,
  governedObservability,
  governedPlaybookState,
  governedRecordBacktest,
  governedRefresh,
  governedStartPlaybook,
  governedUpdateCase,
  hasPermission,
  initializePlatform,
  platformMode,
  platformSession,
  switchGovernedRole,
} from "./api.js";
import { APP_BUILD, APP_VERSION } from "./release.generated.js";
import { csvEscape, loadCsvDataset, parseCsv, toServiceRecords, validateHeaders, validateRecords } from "./csv.js";
import { downloadBrowserDiagnostics, installGlobalDiagnostics, logEvent, reportCritical } from "./diagnostics.js";
import { escapeHtml, forecastChart, gauge, horizontalBars, lineChart, safeCssToken, sparkline } from "./charts.js";
import {
  addAudit,
  loadAudit,
  loadCases,
  loadRole,
  resetLocalState,
  saveCases,
  saveDatasetName,
  saveRole,
  seedCases,
  updateCase,
} from "./storage.js";
import type {
  AnalyticsBundle,
  AppDataset,
  AuditEvent,
  AutomationExecution,
  AutomationRule,
  CaseStatus,
  FilterState,
  GovernedKpiDefinition,
  GroundedAnalystAnswer,
  ImprovementInitiative,
  IntelligenceBundle,
  ObservabilitySnapshot,
  PlatformMode,
  PlaybookDefinition,
  PlaybookRun,
  ProblemRecord,
  QualityIssue,
  Role,
  ServiceRecord,
  Severity,
  ValueRealizationSnapshot,
  ViewId,
  WorkflowCase,
} from "./types.js";

const rootCandidate = document.querySelector<HTMLDivElement>("#app");
if (!rootCandidate) throw new Error("Application root was not found.");
const root: HTMLDivElement = rootCandidate;

const roleLanding: Record<Role, ViewId> = {
  Executive: "overview",
  Analyst: "analysis",
  Operator: "workflow",
  "Data Steward": "governance",
};

let dataset: AppDataset | null = null;
let analytics: AnalyticsBundle | null = null;
let intelligence: IntelligenceBundle | null = null;
let role: Role = loadRole();
let view: ViewId = roleLanding[role];
let cases: WorkflowCase[] = loadCases();
let audit: AuditEvent[] = loadAudit();
let platformModeState: PlatformMode = "static-showcase";
let governedKpiCatalog: GovernedKpiDefinition[] = [];
let observabilitySnapshot: ObservabilitySnapshot | null = null;
let automationRules: AutomationRule[] = [];
let automationExecutions: AutomationExecution[] = [];
let problems: ProblemRecord[] = [];
let initiatives: ImprovementInitiative[] = [];
let playbooks: PlaybookDefinition[] = [];
let playbookRuns: PlaybookRun[] = [];
let valueRealization: ValueRealizationSnapshot = { initiativesActive: 0, initiativesCompleted: 0, successful: 0, inconclusive: 0, hoursSavedMonthly: 0, backlogAvoided: 0, slaImprovementPoints: 0, measuredInitiatives: [] };
let analystQuery = "What should management prioritize?";
let analystAnswer: GroundedAnalystAnswer | null = null;
let routingText = "Customer reports a duplicate invoice charge and requests a refund.";
let routingSuggestion = classifyRequestText(routingText);
let sessionDisplayName = "Local browser";
let summaryText = "";
let summaryMode: "local" | "ai" | "pending" = "local";
let scenarioDemand = 0;
let scenarioCapacity = 10;
let recordPage = 1;
let sidebarOpen = false;
let filters: FilterState = {
  category: "All",
  team: "All",
  location: "All",
  priority: "All",
  search: "",
  dateWindowDays: 120,
};

const navItems: Array<{ id: ViewId; label: string; icon: string; roles: Role[] }> = [
  { id: "overview", label: "Command Center", icon: "dashboard", roles: ["Executive", "Analyst", "Operator", "Data Steward"] },
  { id: "analysis", label: "Analysis Lab", icon: "analysis", roles: ["Executive", "Analyst", "Data Steward"] },
  { id: "process", label: "Process Intelligence", icon: "network", roles: ["Executive", "Analyst", "Operator", "Data Steward"] },
  { id: "automation", label: "Automation & Improvement", icon: "automation", roles: ["Executive", "Analyst", "Operator", "Data Steward"] },
  { id: "analyst", label: "Operations Analyst", icon: "ai", roles: ["Executive", "Analyst", "Operator", "Data Steward"] },
  { id: "workflow", label: "Action & Follow-up", icon: "workflow", roles: ["Executive", "Analyst", "Operator"] },
  { id: "governance", label: "Data Governance", icon: "shield", roles: ["Executive", "Analyst", "Data Steward"] },
  { id: "observability", label: "System Health", icon: "pulse", roles: ["Executive", "Analyst", "Data Steward"] },
  { id: "records", label: "Record Explorer", icon: "table", roles: ["Analyst", "Operator", "Data Steward", "Executive"] },
  { id: "about", label: "Product Story", icon: "briefcase", roles: ["Executive", "Analyst", "Operator", "Data Steward"] },
];

function icon(name: string, size = 20): string {
  const paths: Record<string, string> = {
    dashboard: '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
    analysis: '<path d="M4 19V9"/><path d="M10 19V5"/><path d="M16 19v-7"/><path d="M22 19V3"/><path d="M2 19h22"/>',
    workflow: '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
    shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
    table: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 4v16M15 4v16"/>',
    briefcase: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18M10 12v2h4v-2"/>',
    upload: '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 15v5h16v-5"/>',
    download: '<path d="M12 4v12m-5-5 5 5 5-5"/><path d="M4 20h16"/>',
    alert: '<path d="M10.3 2.9 1.8 17a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 2.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4m0 4h.01"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
    menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
    close: '<path d="m6 6 12 12M18 6 6 18"/>',
    ai: '<path d="M12 3l1.2 3.8L17 8l-3.8 1.2L12 13l-1.2-3.8L7 8l3.8-1.2L12 3zM5 14l.8 2.2L8 17l-2.2.8L5 20l-.8-2.2L2 17l2.2-.8L5 14zM19 13l.8 2.2L22 16l-2.2.8L19 19l-.8-2.2L16 16l2.2-.8L19 13z"/>',
    chevron: '<path d="m9 18 6-6-6-6"/>',
    reset: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>',
    copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    external: '<path d="M14 3h7v7M10 14 21 3"/><path d="M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10h.01"/>',
    pulse: '<path d="M3 12h4l2-6 4 12 2-6h6"/><path d="M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/>',
    network: '<circle cx="5" cy="6" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="12" cy="18" r="2"/><path d="m7 7 4 9M17 7l-4 9M7 6h10"/>',
    automation: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 9h8M8 13h5M8 17h3"/><circle cx="16" cy="15" r="2"/>',
  };
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] ?? paths.info}</svg>`;
}

function formatNumber(value: number, digits = 0): string {
  return value.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function formatDate(value: Date | string | null, options: Intl.DateTimeFormatOptions = { month: "short", day: "numeric", year: "numeric" }): string {
  if (!value) return "—";
  const date = typeof value === "string" ? new Date(value) : value;
  if (!Number.isFinite(date.getTime())) return "—";
  return date.toLocaleDateString("en-US", { ...options, timeZone: "UTC" });
}

function severityClass(severity: Severity): string {
  return severity.toLowerCase();
}

function statusClass(status: CaseStatus): string {
  return status.toLowerCase().replace(/\s+/g, "-");
}

function deltaMarkup(value: number, goodWhen: "up" | "down" | "neutral", suffix = "%"): string {
  const good = goodWhen === "neutral" || (goodWhen === "up" ? value >= 0 : value <= 0);
  const state = value === 0 ? "neutral" : good ? "positive" : "negative";
  const arrow = value > 0 ? "↑" : value < 0 ? "↓" : "→";
  return `<span class="delta delta--${state}">${arrow} ${Math.abs(value).toFixed(1)}${escapeHtml(suffix)}</span>`;
}

function kpiCard(title: string, value: string, note: string, delta: string, sparkValues: number[], sparkDirection: "good-up" | "good-down" | "neutral", accent = "default"): string {
  return `<article class="kpi-card kpi-card--${accent}"><div class="kpi-card__top"><span>${escapeHtml(title)}</span>${delta}</div><strong class="kpi-card__value">${escapeHtml(value)}</strong><div class="kpi-card__bottom"><small>${escapeHtml(note)}</small>${sparkline(sparkValues, sparkDirection)}</div></article>`;
}

function sectionHeader(eyebrow: string, title: string, description: string, actions = ""): string {
  return `<header class="page-header"><div><span class="eyebrow">${escapeHtml(eyebrow)}</span><h1>${escapeHtml(title)}</h1><p>${escapeHtml(description)}</p></div>${actions ? `<div class="page-header__actions">${actions}</div>` : ""}</header>`;
}

function button(label: string, action: string, style: "primary" | "secondary" | "ghost" | "danger" = "secondary", iconName?: string): string {
  return `<button class="button button--${style}" type="button" data-action="${escapeHtml(action)}">${iconName ? icon(iconName, 17) : ""}<span>${escapeHtml(label)}</span></button>`;
}

function emptyState(title: string, description: string): string {
  return `<div class="empty-state">${icon("info", 28)}<h3>${escapeHtml(title)}</h3><p>${escapeHtml(description)}</p></div>`;
}

function currentViewLabel(): string {
  return navItems.find((item) => item.id === view)?.label ?? "Command Center";
}

function shell(content: string): string {
  if (!dataset || !analytics) return content;
  const visibleNav = navItems.filter((item) => item.roles.includes(role));
  const criticalAlerts = analytics.alerts.filter((item) => item.severity === "Critical" || item.severity === "High").length;
  return `<div class="app-shell ${sidebarOpen ? "app-shell--sidebar-open" : ""}">
    <aside class="sidebar" aria-label="Primary navigation">
      <div class="brand"><div class="brand__mark">OI</div><div><strong>Operations Intelligence</strong><span>Automation Platform</span></div><button class="icon-button sidebar__close" type="button" data-action="toggle-sidebar" aria-label="Close navigation">${icon("close")}</button></div>
      <nav class="nav-list">${visibleNav
        .map(
          (item) => `<button type="button" class="nav-item ${view === item.id ? "nav-item--active" : ""}" data-nav="${item.id}">${icon(item.icon)}<span>${escapeHtml(item.label)}</span>${item.id === "workflow" && cases.filter((entry) => entry.status !== "Resolved").length > 0 ? `<b>${cases.filter((entry) => entry.status !== "Resolved").length}</b>` : ""}</button>`,
        )
        .join("")}</nav>
      <div class="sidebar__footer"><div class="dataset-chip"><span class="status-dot"></span><div><small>Active dataset</small><strong title="${escapeHtml(dataset.name)}">${escapeHtml(dataset.name)}</strong></div></div><div class="version-line">Portfolio release v${APP_VERSION}<small>${escapeHtml(APP_BUILD)}</small></div></div>
    </aside>
    <div class="sidebar-scrim" data-action="toggle-sidebar"></div>
    <main class="main-area">
      <header class="topbar"><div class="topbar__left"><button class="icon-button topbar__menu" type="button" data-action="toggle-sidebar" aria-label="Open navigation">${icon("menu")}</button><div><small>${escapeHtml(currentViewLabel())}</small><strong>${formatDate(analytics.kpis.analysisDate)} reporting cycle</strong></div></div><div class="topbar__right"><span class="mode-badge mode-badge--${platformModeState === "server-governed" ? "governed" : "static"}" title="${escapeHtml(sessionDisplayName)}">${platformModeState === "server-governed" ? "Governed local mode" : "Static showcase"}</span><button class="signal-button" type="button" data-nav="analysis" aria-label="Open alerts"><span>${icon("alert", 17)}</span><b>${criticalAlerts}</b><em>priority signals</em></button><label class="role-switch"><span>View as</span><select id="role-select" aria-label="Select role">${(["Executive", "Analyst", "Operator", "Data Steward"] as Role[])
        .map((item) => `<option value="${item}" ${item === role ? "selected" : ""}>${item}</option>`)
        .join("")}</select></label></div></header>
      <div class="content">${content}</div>
      <footer class="footer"><span>Copyright © 2026 Gateway Information Group LLC. All rights reserved.</span><span>${platformModeState === "server-governed" ? "Project-local SQLite · server-enforced demo roles" : "Static showcase fallback"} · No production data</span></footer>
    </main>
  </div>`;
}

function renderOverview(): string {
  if (!dataset || !analytics) return "";
  const { kpis, dailyTrend, alerts, recommendations, interventions, backlogByCategory, slaByTeam } = analytics;
  const netTrend = dailyTrend.map((item) => item.net);
  const createdTrend = dailyTrend.map((item) => item.created);
  const closedTrend = dailyTrend.map((item) => item.closed);
  const topAlert = alerts[0];
  const summaryBadge = summaryMode === "ai" ? "Live AI response" : summaryMode === "pending" ? "Generating…" : "Grounded local summary";

  return `${sectionHeader(
    "Service Operations Command Center",
    "Turn operational signals into accountable action",
    "Validated performance metrics, explainable alerts, root-cause evidence, assignments, and measured follow-up in one decision workflow.",
    `${hasPermission("ingest_data") ? button("Upload dataset", "open-upload", "secondary", "upload") : ""}${button("Export management brief", "export-brief", "primary", "download")}`,
  )}
  <section class="summary-hero">
    <div class="summary-hero__content"><div class="summary-heading"><span class="badge badge--ai">${icon("ai", 16)} ${escapeHtml(summaryBadge)}</span><span class="badge badge--neutral">${kpis.trustedRows.toLocaleString()} trusted rows</span></div><h2>Executive readout</h2><div class="summary-text">${summaryText
      .split("\n\n")
      .map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`)
      .join("")}</div><div class="summary-actions">${button("Generate with optional AI service", "generate-ai-summary", "secondary", "ai")}${button("Copy summary", "copy-summary", "ghost", "copy")}</div></div>
    <aside class="priority-callout ${topAlert ? `priority-callout--${severityClass(topAlert.severity)}` : ""}"><span class="eyebrow">Management attention</span>${topAlert ? `<div class="severity-label severity-label--${severityClass(topAlert.severity)}">${escapeHtml(topAlert.severity)}</div><h3>${escapeHtml(topAlert.title)}</h3><p>${escapeHtml(topAlert.description)}</p><button type="button" class="text-link" data-nav="analysis">Review supporting evidence ${icon("chevron", 15)}</button>` : `<h3>No material alert</h3><p>Current thresholds did not identify an actionable variance.</p>`}</aside>
  </section>
  <section class="kpi-grid">
    ${kpiCard("Open backlog", formatNumber(kpis.openBacklog), "Estimated at analysis date", deltaMarkup(kpis.backlogChangePct, "down"), netTrend.slice(-21), "good-down", kpis.backlogChangePct > 0 ? "warning" : "positive")}
    ${kpiCard("SLA attainment", `${formatNumber(kpis.slaAttainmentPct, 1)}%`, "Closed requests · last 28 days", deltaMarkup(kpis.slaChangePoints, "up", " pts"), closedTrend.slice(-21), "good-up", kpis.slaAttainmentPct < 80 ? "warning" : "positive")}
    ${kpiCard("Median resolution", `${formatNumber(kpis.medianResolutionHours, 1)} hrs`, "Closed requests · last 28 days", deltaMarkup(kpis.resolutionChangePct, "down"), createdTrend.slice(-21), "good-down")}
    ${kpiCard("Reopen rate", `${formatNumber(kpis.reopenRatePct, 1)}%`, "Closed requests · last 28 days", deltaMarkup(kpis.reopenChangePoints, "down", " pts"), netTrend.slice(-21).map(Math.abs), "good-down")}
    ${kpiCard("Customer satisfaction", `${formatNumber(kpis.satisfaction, 2)} / 5`, "Valid survey responses", deltaMarkup(kpis.satisfactionChange, "up", ""), closedTrend.slice(-21), "good-up")}
    ${kpiCard("Data-quality score", `${formatNumber(kpis.qualityScore, 1)}%`, `${dataset.quality.issueRowCount} rows need review`, deltaMarkup(kpis.qualityScore - 100, "up", " pts"), dataset.quality.rules.map((rule) => rule.score), "good-up", kpis.qualityScore < 98 ? "warning" : "positive")}
  </section>
  <section class="dashboard-grid dashboard-grid--wide-left">
    <article class="panel"><div class="panel__header"><div><span class="eyebrow">Demand and throughput</span><h2>Daily requests created vs. closed</h2><p>Trailing 42-day operational flow; the gap between lines explains backlog movement.</p></div><div class="chart-legend"><span><i class="legend-dot legend-dot--primary"></i>Created</span><span><i class="legend-dot legend-dot--secondary"></i>Closed</span></div></div>${lineChart(dailyTrend)}</article>
    <article class="panel"><div class="panel__header"><div><span class="eyebrow">Action queue</span><h2>Priority signals</h2><p>Threshold-based alerts with evidence and recommended follow-up.</p></div><button class="text-link" type="button" data-nav="analysis">View all ${icon("chevron", 15)}</button></div><div class="alert-stack">${alerts.slice(0, 5).map(renderAlertCompact).join("")}</div></article>
  </section>
  <section class="dashboard-grid">
    <article class="panel"><div class="panel__header"><div><span class="eyebrow">Backlog concentration</span><h2>Open work by category</h2><p>Drill into categories contributing most to current work-in-process.</p></div></div>${horizontalBars(backlogByCategory.slice(0, 6))}</article>
    <article class="panel"><div class="panel__header"><div><span class="eyebrow">Service-level comparison</span><h2>SLA attainment by team</h2><p>Recent closed-request performance, sorted from lowest to highest.</p></div></div>${horizontalBars(slaByTeam, { suffix: "%", maximum: 100, inverse: true })}</article>
  </section>
  <section class="dashboard-grid dashboard-grid--wide-right">
    <article class="panel"><div class="panel__header"><div><span class="eyebrow">Measured result</span><h2>Before-and-after workflow outcomes</h2><p>Documented intervention dates and comparable measurement windows.</p></div></div><div class="intervention-grid">${interventions.map(renderIntervention).join("")}</div></article>
    <article class="panel"><div class="panel__header"><div><span class="eyebrow">Recommended priorities</span><h2>What management should do next</h2><p>Each recommendation can become an owned case with a due date and target.</p></div></div><div class="recommendation-list">${recommendations.slice(0, 5).map(renderRecommendation).join("")}</div></article>
  </section>`;
}

function renderAlertCompact(item: AnalyticsBundle["alerts"][number]): string {
  return `<button type="button" class="alert-item" data-nav="analysis"><span class="alert-item__severity alert-item__severity--${severityClass(item.severity)}"></span><div><div class="alert-item__top"><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.severity)}</span></div><p>${escapeHtml(item.description)}</p><small>${escapeHtml(item.dimension)} · ${item.evidenceCount} supporting records</small></div></button>`;
}

function renderRecommendation(item: AnalyticsBundle["recommendations"][number]): string {
  const exists = cases.some((entry) => entry.source.includes(item.sourceAlertId ?? "__none__") || entry.title === item.title);
  return `<div class="recommendation"><div class="recommendation__rank recommendation__rank--${severityClass(item.priority)}">${escapeHtml(item.priority.slice(0, 1))}</div><div><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.action)}</p><small>Suggested owner: ${escapeHtml(item.ownerRole)} · ${escapeHtml(item.expectedImpact)}</small></div><button type="button" class="button button--tiny ${exists ? "button--complete" : "button--secondary"}" data-create-case="${escapeHtml(item.id)}" ${exists ? "disabled" : ""}>${exists ? `${icon("check", 14)} Added` : `${icon("plus", 14)} Create case`}</button></div>`;
}

function renderIntervention(item: AnalyticsBundle["interventions"][number]): string {
  const improved = item.status === "Improved";
  const changeDisplay = `${item.change > 0 ? "+" : ""}${formatNumber(item.change, 1)}${item.unit}`;
  return `<article class="intervention"><div class="intervention__header"><span class="badge badge--${improved ? "positive" : "warning"}">${escapeHtml(item.status)}</span><small>${escapeHtml(item.metric)}</small></div><h3>${escapeHtml(item.title)}</h3><div class="before-after"><div><span>Before</span><strong>${formatNumber(item.before, 1)}${escapeHtml(item.unit)}</strong></div><span class="before-after__arrow">→</span><div><span>After</span><strong>${formatNumber(item.after, 1)}${escapeHtml(item.unit)}</strong></div></div><p><b>${escapeHtml(changeDisplay)}</b> · ${escapeHtml(item.description)}</p></article>`;
}

function optionList(values: string[], selected: string): string {
  return values.map((value) => `<option value="${escapeHtml(value)}" ${value === selected ? "selected" : ""}>${escapeHtml(value)}</option>`).join("");
}

function filteredRecords(): ServiceRecord[] {
  if (!dataset || !analytics) return [];
  const start = new Date(analytics.kpis.analysisDate.getTime() - filters.dateWindowDays * 86_400_000);
  const search = filters.search.trim().toLowerCase();
  return dataset.records.filter((record) => {
    if (filters.category !== "All" && record.category !== filters.category) return false;
    if (filters.team !== "All" && record.team !== filters.team) return false;
    if (filters.location !== "All" && record.location !== filters.location) return false;
    if (filters.priority !== "All" && record.priority !== filters.priority) return false;
    if (record.createdAt && record.createdAt < start) return false;
    if (search) {
      const haystack = [record.requestId, record.category, record.subcategory, record.location, record.team, record.owner, record.status, record.channel].join(" ").toLowerCase();
      if (!haystack.includes(search)) return false;
    }
    return true;
  });
}

function uniqueValues(key: keyof Pick<ServiceRecord, "category" | "team" | "location" | "priority">): string[] {
  if (!dataset) return ["All"];
  return ["All", ...new Set(dataset.records.map((record) => String(record[key] ?? "")).filter(Boolean))].sort((a, b) => (a === "All" ? -1 : b === "All" ? 1 : a.localeCompare(b)));
}

function filterBar(includeSearch = false): string {
  return `<div class="filter-bar"><label><span>Category</span><select data-filter="category">${optionList(uniqueValues("category"), filters.category)}</select></label><label><span>Team</span><select data-filter="team">${optionList(uniqueValues("team"), filters.team)}</select></label><label><span>Location</span><select data-filter="location">${optionList(uniqueValues("location"), filters.location)}</select></label><label><span>Priority</span><select data-filter="priority">${optionList(uniqueValues("priority"), filters.priority)}</select></label><label><span>Window</span><select data-filter="dateWindowDays">${[30, 60, 90, 120].map((days) => `<option value="${days}" ${days === filters.dateWindowDays ? "selected" : ""}>${days} days</option>`).join("")}</select></label>${includeSearch ? `<label class="filter-search"><span>Search records</span><div class="input-icon">${icon("search", 16)}<input data-filter="search" value="${escapeHtml(filters.search)}" placeholder="ID, owner, category…"></div></label>` : ""}<button type="button" class="button button--ghost button--compact" data-action="clear-filters">${icon("reset", 15)} Clear</button></div>`;
}

function renderAnalysis(): string {
  if (!dataset || !analytics) return "";
  const records = filteredRecords();
  if (records.length === 0) {
    return `${sectionHeader("Analysis Lab", "Diagnose movement and compare scenarios", "Use role-aware filters to trace headline metrics to underlying records.")}${filterBar()}${emptyState("No records match these filters", "Clear one or more filters to restore the analytical view.")}`;
  }
  const quality = validateRecords(records);
  const scoped = buildAnalytics(records, quality);
  const scenario = runScenario(records, quality, scenarioDemand, scenarioCapacity);
  const topRoot = scoped.rootCauses[0];
  return `${sectionHeader(
    "Analysis Lab",
    "Diagnose movement and compare scenarios",
    "Filters recalculate the visible KPIs, trends, anomalies, and root-cause rankings against the selected operational slice.",
    `${button("Export filtered records", "export-filtered", "secondary", "download")}${button("Create management brief", "export-brief", "primary", "download")}`,
  )}
  ${filterBar()}
  <div class="scope-banner"><div><strong>${records.length.toLocaleString()} source rows in scope</strong><span>${quality.score.toFixed(1)}% scoped quality score · analysis through ${formatDate(scoped.kpis.analysisDate)}</span></div><button type="button" class="text-link" data-nav="records">Open record explorer ${icon("chevron", 14)}</button></div>
  <section class="mini-kpi-grid">
    <article><span>Open backlog</span><strong>${scoped.kpis.openBacklog}</strong>${deltaMarkup(scoped.kpis.backlogChangePct, "down")}</article>
    <article><span>SLA attainment</span><strong>${scoped.kpis.slaAttainmentPct.toFixed(1)}%</strong>${deltaMarkup(scoped.kpis.slaChangePoints, "up", " pts")}</article>
    <article><span>Median resolution</span><strong>${scoped.kpis.medianResolutionHours.toFixed(1)} hrs</strong>${deltaMarkup(scoped.kpis.resolutionChangePct, "down")}</article>
    <article><span>Closure / intake</span><strong>${scoped.kpis.closureToIntakeRatio.toFixed(2)}×</strong><small>${scoped.kpis.closureToIntakeRatio >= 1 ? "Capacity kept pace" : "Backlog pressure"}</small></article>
  </section>
  <section class="dashboard-grid dashboard-grid--wide-left">
    <article class="panel"><div class="panel__header"><div><span class="eyebrow">Filtered trend</span><h2>Demand vs. throughput</h2><p>Created and closed records in the selected scope.</p></div><div class="chart-legend"><span><i class="legend-dot legend-dot--primary"></i>Created</span><span><i class="legend-dot legend-dot--secondary"></i>Closed</span></div></div>${lineChart(scoped.dailyTrend)}</article>
    <article class="panel"><div class="panel__header"><div><span class="eyebrow">Explainability</span><h2>Highest-contributing root cause</h2><p>Contribution and relative risk are calculated from recent closed records.</p></div></div>${topRoot ? `<div class="root-highlight"><span class="root-highlight__dimension">${escapeHtml(topRoot.dimension)}</span><strong>${escapeHtml(topRoot.name)}</strong><div class="root-highlight__stats"><div><span>Miss contribution</span><b>${topRoot.contributionPct.toFixed(1)}%</b></div><div><span>Miss rate</span><b>${topRoot.missRatePct.toFixed(1)}%</b></div><div><span>Relative risk</span><b>${topRoot.relativeRisk.toFixed(2)}×</b></div></div><p>${topRoot.missCount} of ${topRoot.closedCount} recently closed records missed SLA.</p></div>` : emptyState("No root cause available", "The selected scope does not contain enough recent closed records for a stable comparison.")}</article>
  </section>
  <section class="dashboard-grid">
    <article class="panel"><div class="panel__header"><div><span class="eyebrow">Root-cause ranking</span><h2>SLA miss contribution</h2><p>Dimensions ranked by share of recent misses, with volume and relative risk.</p></div></div>${renderRootCauseTable(scoped.rootCauses)}</article>
    <article class="panel"><div class="panel__header"><div><span class="eyebrow">Anomaly detection</span><h2>Material changes</h2><p>Seven-day values compared with normalized prior baselines.</p></div></div><div class="alert-stack">${scoped.alerts.length ? scoped.alerts.map(renderAlertDetailed).join("") : emptyState("No material anomalies", "No selected segment crossed the current evidence thresholds.")}</div></article>
  </section>
  <section class="panel scenario-panel"><div class="panel__header"><div><span class="eyebrow">Forecasting, uncertainty, and backtesting</span><h2>Six-week backlog outlook</h2><p>Day-of-week seasonality, queue aging, workload-mix constraints, and an 80% planning interval make the scenario explicit and testable.</p></div></div><div class="scenario-layout"><div class="scenario-controls"><label><span>Demand change <b>${scenarioDemand > 0 ? "+" : ""}${scenarioDemand}%</b></span><input type="range" min="-25" max="35" step="5" value="${scenarioDemand}" data-scenario="demand"></label><label><span>Capacity change <b>${scenarioCapacity > 0 ? "+" : ""}${scenarioCapacity}%</b></span><input type="range" min="-20" max="40" step="5" value="${scenarioCapacity}" data-scenario="capacity"></label><div class="scenario-readout"><div><span>Projected weekly intake</span><strong>${scenario.projectedWeeklyIntake}</strong><small>Current: ${scenario.currentWeeklyIntake}</small></div><div><span>Effective closures</span><strong>${scenario.projectedWeeklyClosures}</strong><small>Aging ${scenario.agingConstraintPct.toFixed(1)}% · mix ${scenario.skillConstraintPct.toFixed(1)}%</small></div><div><span>Week 6 backlog</span><strong>${scenario.endBacklog}</strong><small>80% range ${scenario.forecast.at(-1)?.lowerBacklog ?? 0}–${scenario.forecast.at(-1)?.upperBacklog ?? 0}</small></div></div><div class="backtest-card"><span>28-day backtest</span><strong>MAE ${scenario.backtest.meanAbsoluteError.toFixed(2)} requests/day</strong><small>Bias ${scenario.backtest.meanBias > 0 ? "+" : ""}${scenario.backtest.meanBias.toFixed(2)} · model ${escapeHtml(scenario.backtest.modelVersion)}</small></div><ul class="scenario-assumptions">${scenario.assumptions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div><div class="scenario-chart"><div class="chart-legend"><span><i class="legend-dot legend-dot--primary"></i>Scenario</span><span><i class="legend-dot legend-dot--muted"></i>Current run rate</span><span>Shaded: ${scenario.confidenceLevel}% planning interval</span></div>${forecastChart(scenario.forecast)}</div></div></section>
  <section class="panel"><div class="panel__header"><div><span class="eyebrow">Drill-down</span><h2>Underlying records</h2><p>The first 12 records in the current scope; open the explorer for full search and export.</p></div><button class="text-link" type="button" data-nav="records">Full record explorer ${icon("chevron", 14)}</button></div>${renderRecordsTable(records.slice(0, 12), false)}</section>`;
}

function renderRootCauseTable(items: AnalyticsBundle["rootCauses"]): string {
  if (!items.length) return emptyState("No root-cause ranking", "More recent closed records are required.");
  return `<div class="table-wrap"><table class="data-table"><thead><tr><th>Dimension</th><th>Value</th><th>Misses</th><th>Miss rate</th><th>Contribution</th><th>Risk</th></tr></thead><tbody>${items
    .slice(0, 12)
    .map((item) => `<tr><td><span class="table-tag">${escapeHtml(item.dimension)}</span></td><td><strong>${escapeHtml(item.name)}</strong></td><td>${item.missCount} / ${item.closedCount}</td><td>${item.missRatePct.toFixed(1)}%</td><td><div class="cell-bar"><span style="width:${Math.min(100, item.contributionPct)}%"></span><b>${item.contributionPct.toFixed(1)}%</b></div></td><td><span class="risk-badge ${item.relativeRisk >= 1.3 ? "risk-badge--high" : ""}">${item.relativeRisk.toFixed(2)}×</span></td></tr>`)
    .join("")}</tbody></table></div>`;
}

function renderAlertDetailed(item: AnalyticsBundle["alerts"][number]): string {
  return `<article class="alert-card alert-card--${severityClass(item.severity)}"><div class="alert-card__header"><span class="severity-label severity-label--${severityClass(item.severity)}">${escapeHtml(item.severity)}</span><small>${escapeHtml(item.type)} · ${escapeHtml(item.dimension)}</small></div><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.description)}</p><div class="alert-evidence"><span>Current <b>${formatNumber(item.currentValue, 1)}</b></span><span>Baseline <b>${formatNumber(item.baselineValue, 1)}</b></span><span>Change <b>${item.changePct > 0 ? "+" : ""}${formatNumber(item.changePct, 1)}%</b></span></div><div class="alert-action"><strong>Recommended follow-up</strong><p>${escapeHtml(item.recommendedAction)}</p></div></article>`;
}


function currentAutomationMetrics(): Record<string, number> {
  if (!dataset || !analytics) return {};
  return {
    backlogChangePct: analytics.kpis.backlogChangePct,
    slaAttainmentPct: analytics.kpis.slaAttainmentPct,
    trustedRows: analytics.kpis.trustedRows,
    qualityScore: analytics.kpis.qualityScore,
    issueRowCount: dataset.quality.issueRowCount,
    closureToIntakeRatio: analytics.kpis.closureToIntakeRatio,
    openBacklog: analytics.kpis.openBacklog,
  };
}

function conditionMatches(actual: number, operator: string, expected: number): boolean {
  if (operator === ">") return actual > expected;
  if (operator === ">=") return actual >= expected;
  if (operator === "<") return actual < expected;
  if (operator === "<=") return actual <= expected;
  if (operator === "==") return actual === expected;
  if (operator === "!=") return actual !== expected;
  return false;
}

function simulateLocalAutomations(): AutomationExecution[] {
  const metrics = currentAutomationMetrics();
  const now = new Date().toISOString();
  return automationRules.map((rule) => {
    const matched = rule.enabled && rule.conditions.every((condition) => Number.isFinite(metrics[condition.metric]) && conditionMatches(metrics[condition.metric], condition.operator, condition.value));
    return {
      id: `LOCAL-${rule.id}`,
      ruleId: rule.id,
      evaluatedAt: now,
      status: matched ? "Simulated" : "No Match",
      reason: matched ? "Conditions matched in static simulation; no governed write was performed." : "Conditions did not match the current analytical evidence.",
      caseId: null,
      evidence: Object.fromEntries(rule.conditions.filter((item) => Number.isFinite(metrics[item.metric])).map((item) => [item.metric, metrics[item.metric]])),
    };
  });
}

function deriveValueSnapshot(items: ImprovementInitiative[]): ValueRealizationSnapshot {
  const completed = items.filter((item) => item.status === "Completed");
  const successful = completed.filter((item) => {
    const lowerIsBetter = /resolution|reopen|backlog/i.test(item.baselineMetric);
    return lowerIsBetter ? item.measuredValue <= item.targetValue : item.measuredValue >= item.targetValue;
  });
  return {
    initiativesActive: items.filter((item) => item.status === "Active").length,
    initiativesCompleted: completed.length,
    successful: successful.length,
    inconclusive: Math.max(0, completed.length - successful.length),
    hoursSavedMonthly: items.reduce((sum, item) => sum + item.hoursSavedMonthly, 0),
    backlogAvoided: items.reduce((sum, item) => sum + item.backlogAvoided, 0),
    slaImprovementPoints: items.reduce((sum, item) => sum + item.slaImprovementPoints, 0),
    measuredInitiatives: items,
  };
}

function renderProcessIntelligence(): string {
  if (!dataset || !analytics || !intelligence) return "";
  const variants = intelligence.processVariants.slice(0, 8);
  const bottlenecks = intelligence.bottlenecks.slice(0, 10);
  const factors = intelligence.rootFactors.slice(0, 10);
  const graphNodes = intelligence.objectGraph.nodes.slice(0, 12);
  const graphEdges = intelligence.objectGraph.edges.slice(0, 12);
  return `${sectionHeader(
    "Process Intelligence",
    "See how work flows, where it stalls, and which patterns deserve investigation",
    "Derived process paths combine request attributes with actual cycle-time, SLA, and reopen evidence. Association signals are explicit and do not claim causality.",
    button("Open supporting records", "go-records", "secondary", "table"),
  )}
  <section class="process-intelligence-hero"><article><span>Derived variants</span><strong>${intelligence.processVariants.length}</strong><small>Top ${variants.length} shown</small></article><article><span>Priority bottleneck</span><strong>${escapeHtml(bottlenecks[0]?.name ?? "None")}</strong><small>${bottlenecks[0] ? `${bottlenecks[0].score.toFixed(1)}/100 signal score` : "No stable signal"}</small></article><article><span>Root factors</span><strong>${intelligence.rootFactors.length}</strong><small>Association signals with ≥5 records</small></article><article><span>Object relationships</span><strong>${intelligence.objectGraph.edges.length}</strong><small>Category · team · location</small></article></section>
  <section class="panel"><div class="panel__header"><div><span class="eyebrow">Process variants</span><h2>Common operational paths</h2><p>Paths are transparently derived from channel, team, category, priority, rework state, SLA outcome, and final status.</p></div></div><div class="process-variant-list">${variants.map((item) => `<article><div class="process-path">${item.path.map((step, index) => `<span>${escapeHtml(step)}</span>${index < item.path.length - 1 ? `<i>→</i>` : ""}`).join("")}</div><div class="process-variant-stats"><b>${item.count} requests</b><span>${item.sharePct.toFixed(1)}% of trusted work</span><span>${item.slaMissPct.toFixed(1)}% SLA miss</span><span>${item.reopenPct.toFixed(1)}% reopened</span><span>${item.medianResolutionHours.toFixed(1)}h median resolution</span></div></article>`).join("")}</div></section>
  <section class="dashboard-grid"><article class="panel"><div class="panel__header"><div><span class="eyebrow">Bottleneck ranking</span><h2>Where performance risk concentrates</h2><p>Score combines supported SLA misses, observed cycle time, reopen exposure, and evidence depth.</p></div></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Kind</th><th>Signal</th><th>Support</th><th>Median cycle</th><th>SLA miss</th><th>Reopen</th><th>Score</th></tr></thead><tbody>${bottlenecks.map((item) => `<tr><td><span class="table-tag">${escapeHtml(item.kind)}</span></td><td><strong>${escapeHtml(item.name)}</strong></td><td>${item.support}</td><td>${item.medianResolutionHours.toFixed(1)}h</td><td>${item.slaMissPct.toFixed(1)}%</td><td>${item.reopenPct.toFixed(1)}%</td><td><span class="risk-badge ${item.score >= 60 ? "risk-badge--high" : ""}">${item.score.toFixed(1)}</span></td></tr>`).join("")}</tbody></table></div></article>
  <article class="panel"><div class="panel__header"><div><span class="eyebrow">Process-aware root cause</span><h2>Conditions associated with misses</h2><p>Contribution and relative risk identify investigation targets; causality is deliberately not asserted.</p></div></div><div class="root-factor-list">${factors.map((item) => `<article><div><strong>${escapeHtml(item.condition)}</strong><small>${item.support} closed records in scope</small></div><div><b>${item.contributionPct.toFixed(1)}%</b><span>miss contribution</span></div><div><b>${item.relativeRisk.toFixed(2)}×</b><span>relative risk</span></div><p>${escapeHtml(item.interpretation)}</p></article>`).join("")}</div></article></section>
  <section class="dashboard-grid dashboard-grid--wide-left"><article class="panel"><div class="panel__header"><div><span class="eyebrow">Operational object graph</span><h2>Connected categories, teams, and locations</h2><p>Use relationships to understand where the same operational objects intersect instead of forcing every question into one case dimension.</p></div></div><div class="object-node-grid">${graphNodes.map((node) => `<article><span>${escapeHtml(node.type)}</span><strong>${escapeHtml(node.label)}</strong><small>${node.volume} requests · ${node.riskScore.toFixed(1)}% miss exposure</small></article>`).join("")}</div></article><article class="panel"><div class="panel__header"><div><span class="eyebrow">Strongest relationships</span><h2>Object connections</h2></div></div><div class="relationship-list">${graphEdges.map((edge) => { const source = intelligence!.objectGraph.nodes.find((node) => node.id === edge.source)?.label ?? edge.source; const target = intelligence!.objectGraph.nodes.find((node) => node.id === edge.target)?.label ?? edge.target; return `<div><strong>${escapeHtml(source)}</strong><span>${escapeHtml(edge.relationship)}</span><strong>${escapeHtml(target)}</strong><b>${edge.weight}</b></div>`; }).join("")}</div></article></section>
  <section class="assumption-callout"><strong>Method boundary</strong><ul>${intelligence.processAssumptions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></section>`;
}

function renderAutomationImprovement(): string {
  if (!dataset || !analytics || !intelligence) return "";
  const executions = automationExecutions.slice(0, 8);
  const activeRun = playbookRuns.find((item) => item.status === "Active") ?? playbookRuns[0];
  return `${sectionHeader(
    "Automation & Improvement",
    "Turn governed signals into controlled action—and prove whether the action worked",
    "Rules use Trigger → Logic → Action with simulation, cooldown, deduplication, case assignment, playbooks, problem management, and value realization.",
    `${button("Simulate rules", "simulate-automations", "secondary", "analysis")}${platformModeState === "server-governed" && hasPermission("run_automation") ? button("Run governed rules", "execute-automations", "primary", "automation") : ""}`,
  )}
  <section class="closed-loop-chain">${["Observe", "Explain", "Trigger", "Assign", "Playbook", "Measure", "Value"].map((step, index, all) => `<article><strong>${escapeHtml(step)}</strong>${index < all.length - 1 ? `<i>→</i>` : ""}</article>`).join("")}</section>
  <section class="dashboard-grid dashboard-grid--wide-left"><article class="panel"><div class="panel__header"><div><span class="eyebrow">Automation rules</span><h2>Trigger → logic → action</h2><p>External writes stay disabled; governed execution creates only project-local workflow cases after server-side RBAC, CSRF, dedupe, and cooldown checks.</p></div></div><div class="automation-rule-list">${automationRules.map((rule) => `<article><div class="automation-rule__head"><span class="severity-label severity-label--${severityClass(rule.severity)}">${escapeHtml(rule.severity)}</span><strong>${escapeHtml(rule.name)}</strong><span class="badge badge--${rule.enabled ? "positive" : "neutral"}">${rule.enabled ? "Enabled" : "Disabled"}</span></div><p>${escapeHtml(rule.description)}</p><div class="condition-list">${rule.conditions.map((condition) => `<code>${escapeHtml(condition.metric)} ${escapeHtml(condition.operator)} ${condition.value}</code>`).join("")}</div><small>Owner ${escapeHtml(rule.ownerRole)} · cooldown ${Math.round(rule.cooldownMinutes / 60)}h · dedupe ${escapeHtml(rule.dedupeKey)}</small><div class="rule-action"><b>${escapeHtml(rule.action.type)}</b><span>${escapeHtml(rule.action.title)}</span></div></article>`).join("")}</div></article><article class="panel"><div class="panel__header"><div><span class="eyebrow">Signal-to-noise</span><h2>Alert orchestration controls</h2><p>Detection is consolidated before it reaches management.</p></div></div><div class="noise-score"><article><span>Generated candidates</span><strong>${intelligence.alertNoise.generated}</strong></article><article><span>Consolidated</span><strong>${intelligence.alertNoise.consolidated}</strong></article><article><span>Suppressed</span><strong>${intelligence.alertNoise.suppressed}</strong></article><article><span>High priority</span><strong>${intelligence.alertNoise.highPriority}</strong></article></div><ul class="feature-list">${intelligence.alertNoise.suppressionReasons.map((item) => `<li><b>${escapeHtml(item)}</b><span>Prevents repeated operational noise from creating duplicate attention or work.</span></li>`).join("")}</ul>${executions.length ? `<div class="execution-history"><h3>Recent rule evaluations</h3>${executions.map((item) => `<div><span class="badge badge--${item.status === "Triggered" ? "positive" : item.status === "Suppressed" ? "warning" : "neutral"}">${escapeHtml(item.status)}</span><strong>${escapeHtml(item.ruleId)}</strong><small>${escapeHtml(item.reason)}</small>${item.caseId ? `<code>${escapeHtml(item.caseId)}</code>` : ""}</div>`).join("")}</div>` : ""}</article></section>
  <section class="dashboard-grid"><article class="panel"><div class="panel__header"><div><span class="eyebrow">Automation opportunity scoring</span><h2>Where automation may create value</h2><p>Scores balance volume, effort, repeatability, operational risk, and data confidence. Estimates are prioritization aids, not guarantees.</p></div></div><div class="opportunity-list">${intelligence.automationOpportunities.slice(0, 6).map((item) => `<article><div class="opportunity-score"><strong>${item.score}</strong><span>/100</span></div><div><h3>${escapeHtml(item.name)}</h3><p>${escapeHtml(item.rationale)}</p><small>${item.affectedMonthlyVolume} monthly requests · ~${item.estimatedHoursSavedMonthly.toFixed(1)} estimated hours/month · ${item.expectedCycleTimeReductionPct}% cycle opportunity · ${escapeHtml(item.complexity)} complexity</small></div></article>`).join("")}</div></article><article class="panel"><div class="panel__header"><div><span class="eyebrow">Explainable smart routing</span><h2>Human-reviewed categorization</h2><p>Deterministic portfolio classifier suggests category and team; operators can accept or override.</p></div></div><label class="analyst-input"><span>Example incoming request</span><textarea id="routing-text" rows="4">${escapeHtml(routingText)}</textarea></label><div class="routing-result"><span>Recommended category</span><strong>${escapeHtml(routingSuggestion.category)}</strong><small>${routingSuggestion.confidencePct}% confidence · team ${escapeHtml(routingSuggestion.team)}</small><ul>${routingSuggestion.reasons.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul><button class="button button--secondary" type="button" data-action="classify-routing">Recalculate suggestion</button></div><p class="method-note">No hidden model or external service is required; this demonstrates explainable routing and a human-override boundary rather than pretending to be production ML.</p></article></section>
  <section class="value-hero"><article><span>Active initiatives</span><strong>${valueRealization.initiativesActive}</strong></article><article><span>Completed</span><strong>${valueRealization.initiativesCompleted}</strong></article><article><span>Successful</span><strong>${valueRealization.successful}</strong></article><article><span>Synthetic hours saved / month</span><strong>${valueRealization.hoursSavedMonthly.toFixed(0)}</strong></article><article><span>Backlog avoided</span><strong>${valueRealization.backlogAvoided}</strong></article><article><span>SLA improvement</span><strong>+${valueRealization.slaImprovementPoints.toFixed(1)} pts</strong></article></section>
  <section class="dashboard-grid dashboard-grid--wide-right"><article class="panel"><div class="panel__header"><div><span class="eyebrow">Problem management</span><h2>Recurring patterns become improvement initiatives</h2></div></div><div class="problem-list">${problems.map((item) => `<article><span class="badge badge--warning">${escapeHtml(item.status)}</span><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.hypothesis)}</p><small>Owner ${escapeHtml(item.owner)}</small><ul>${item.evidence.map((evidence) => `<li>${escapeHtml(evidence)}</li>`).join("")}</ul></article>`).join("")}</div><div class="initiative-list">${initiatives.map((item) => `<article><div><span class="badge badge--${item.status === "Completed" ? "positive" : "neutral"}">${escapeHtml(item.status)}</span><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.owner)}</small></div><div><span>${escapeHtml(item.baselineMetric)}</span><b>${item.baselineValue}${escapeHtml(item.unit)} → ${item.measuredValue}${escapeHtml(item.unit)}</b><small>Target ${item.targetValue}${escapeHtml(item.unit)} · confidence ${item.confidencePct.toFixed(0)}%</small></div></article>`).join("")}</div></article><article class="panel"><div class="panel__header"><div><span class="eyebrow">Guided playbooks</span><h2>Reusable response sequences</h2><p>Playbooks make follow-up reproducible instead of relying on memory.</p></div></div><div class="playbook-list">${playbooks.map((item) => `<article><h3>${escapeHtml(item.name)}</h3><p>${escapeHtml(item.description)}</p><small>${item.steps.length} controlled steps</small><button type="button" class="button button--tiny button--secondary" data-start-playbook="${escapeHtml(item.id)}">Start playbook</button></article>`).join("")}</div>${activeRun ? `<div class="active-playbook"><span class="eyebrow">Current run</span><h3>${escapeHtml(playbooks.find((item) => item.id === activeRun.playbookId)?.name ?? activeRun.playbookId)}</h3><div class="playbook-steps">${activeRun.steps.map((step, index) => `<div class="${step.completed ? "playbook-step--done" : index === activeRun.currentStep ? "playbook-step--current" : ""}"><span>${step.completed ? "✓" : index + 1}</span><p>${escapeHtml(step.label)}</p></div>`).join("")}</div>${activeRun.status === "Active" ? `<button type="button" class="button button--primary" data-advance-playbook="${escapeHtml(activeRun.id)}">Complete current step</button>` : `<span class="badge badge--positive">Completed</span>`}</div>` : emptyState("No playbook run yet", "Start a playbook to demonstrate guided, auditable operational response.")}</article></section>`;
}

function pulseForRole(): IntelligenceBundle["pulse"] {
  if (!intelligence) return [];
  if (role === "Data Steward") return intelligence.pulse.filter((item) => item.id === "pulse-quality" || item.id === "pulse-signal");
  if (role === "Operator") return intelligence.pulse.filter((item) => item.id === "pulse-backlog" || item.id === "pulse-signal");
  return intelligence.pulse;
}

function renderOperationsAnalyst(): string {
  if (!dataset || !analytics || !intelligence) return "";
  const answer = analystAnswer ?? answerOperationsQuestion(analystQuery, analytics, intelligence, dataset.name);
  const pulse = pulseForRole();
  return `${sectionHeader(
    "Operations Analyst",
    "Personalized signals and evidence-grounded operational Q&A",
    "The analyst answers only from the currently loaded governed metrics, process evidence, and documented assumptions; it does not fabricate records or hide metric definitions.",
  )}
  <section class="pulse-grid">${pulse.map((item) => `<article class="pulse-card pulse-card--${item.status.toLowerCase()}"><div><span>${escapeHtml(item.metric)}</span><b>${escapeHtml(item.status)}</b></div><h3>${escapeHtml(item.headline)}</h3><p>${escapeHtml(item.detail)}</p><ul>${item.evidence.map((evidence) => `<li>${escapeHtml(evidence)}</li>`).join("")}</ul><small>Next action: ${escapeHtml(item.nextAction)}</small></article>`).join("")}</section>
  <section class="dashboard-grid dashboard-grid--wide-left"><article class="panel analyst-console"><div class="panel__header"><div><span class="eyebrow">Grounded investigation</span><h2>Ask the current operation</h2><p>Try SLA, backlog, bottleneck, automation, quality, or management-priority questions.</p></div></div><label class="analyst-input"><span>Question</span><input id="analyst-query" value="${escapeHtml(analystQuery)}" placeholder="Why did SLA miss?"/></label><div class="suggested-questions">${["Why did SLA miss?", "Where is the biggest bottleneck?", "What should management prioritize?", "What is the best automation opportunity?", "Can I trust the data?"].map((item) => `<button type="button" data-analyst-question="${escapeHtml(item)}">${escapeHtml(item)}</button>`).join("")}</div><button type="button" class="button button--primary" data-action="ask-analyst">Analyze evidence</button><div class="analyst-answer"><span class="badge badge--ai">Grounded local analyst</span><h3>${escapeHtml(answer.answer)}</h3><div class="evidence-list"><strong>Evidence</strong>${answer.evidence.length ? `<ul>${answer.evidence.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : `<p>No evidence selected yet.</p>`}</div><div class="caveat"><strong>Boundary</strong><p>${escapeHtml(answer.caveat)}</p></div></div></article><article class="panel"><div class="panel__header"><div><span class="eyebrow">Follow-up investigation</span><h2>Recommended next questions</h2></div></div><div class="followup-list">${answer.followUps.map((item) => `<button type="button" data-analyst-question="${escapeHtml(item)}">${icon("chevron", 15)}<span>${escapeHtml(item)}</span></button>`).join("")}</div><div class="evidence-contract"><h3>Answer contract</h3><ul><li>Metric values come from the current analytical bundle.</li><li>Process evidence exposes its derived-path limitation.</li><li>Association is not labeled causation.</li><li>Automation estimates are labeled estimates.</li><li>Raw records stay local; no external model is required.</li></ul></div></article></section>`;
}

function renderWorkflow(): string {
  if (!dataset || !analytics) return "";
  const activeCases = cases.filter((item) => item.status !== "Resolved");
  const resolvedCases = cases.filter((item) => item.status === "Resolved");
  return `${sectionHeader(
    "Action & Follow-up",
    "Convert evidence into owned work",
    "Assign analytical findings, track status and targets, and preserve a complete audit history of operational decisions.",
    `${button("Add top recommendation", "add-top-case", "secondary", "plus")}${button("Export case register", "export-cases", "primary", "download")}`,
  )}
  <section class="workflow-stats"><article><span>Active cases</span><strong>${activeCases.length}</strong><small>${activeCases.filter((item) => item.priority === "Critical" || item.priority === "High").length} high-priority</small></article><article><span>In progress</span><strong>${cases.filter((item) => item.status === "In Progress").length}</strong><small>Owned and underway</small></article><article><span>Monitoring</span><strong>${cases.filter((item) => item.status === "Monitoring").length}</strong><small>Awaiting measured result</small></article><article><span>Resolved</span><strong>${resolvedCases.length}</strong><small>Closed with outcome</small></article></section>
  <section class="panel"><div class="panel__header"><div><span class="eyebrow">Case register</span><h2>Assignments and management follow-up</h2><p>${platformModeState === "server-governed" ? "Updates are authorized by role and persisted in the project-local SQLite case register." : "Static showcase fallback stores reversible workflow edits in this browser."}</p></div></div>${cases.length ? `<div class="case-list">${cases.map(renderCase).join("")}</div>` : emptyState("No cases yet", "Create a case from an analytical recommendation to start the action workflow.")}</section>
  <section class="dashboard-grid dashboard-grid--wide-right">
    <article class="panel"><div class="panel__header"><div><span class="eyebrow">Measured outcomes</span><h2>Did the action work?</h2><p>Before-and-after comparisons connect workflow changes to operational results.</p></div></div><div class="intervention-grid">${analytics.interventions.map(renderIntervention).join("")}</div></article>
    <article class="panel"><div class="panel__header"><div><span class="eyebrow">Audit trail</span><h2>Recent activity</h2><p>Actor, action, entity, timestamp, and supporting detail.</p></div></div>${renderAudit(audit.slice(0, 10))}</article>
  </section>`;
}

function renderCase(item: WorkflowCase): string {
  const progress = item.targetValue === item.baselineValue ? 0 : Math.max(0, Math.min(100, ((item.currentValue - item.baselineValue) / (item.targetValue - item.baselineValue)) * 100));
  return `<article class="case-card"><div class="case-card__rail case-card__rail--${severityClass(item.priority)}"></div><div class="case-card__body"><div class="case-card__header"><div><span class="severity-label severity-label--${severityClass(item.priority)}">${escapeHtml(item.priority)}</span><span class="status-pill status-pill--${statusClass(item.status)}">${escapeHtml(item.status)}</span></div><small>${escapeHtml(item.id)} · Due ${formatDate(item.dueAt, { month: "short", day: "numeric" })}</small></div><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.description)}</p><div class="case-card__grid"><label><span>Status</span><select data-case-status="${escapeHtml(item.id)}">${(["Open", "In Progress", "Monitoring", "Resolved"] as CaseStatus[]).map((status) => `<option value="${status}" ${status === item.status ? "selected" : ""}>${status}</option>`).join("")}</select></label><label><span>Owner</span><input data-case-owner="${escapeHtml(item.id)}" value="${escapeHtml(item.owner)}" maxlength="80"></label><div><span>Expected impact</span><strong>${escapeHtml(item.expectedImpact)}</strong></div></div><div class="case-measure"><div class="case-measure__header"><span>${escapeHtml(item.baselineMetric)}</span><strong>${formatNumber(item.currentValue, 1)}${escapeHtml(item.unit)} / target ${formatNumber(item.targetValue, 1)}${escapeHtml(item.unit)}</strong></div><div class="progress-track"><span style="width:${progress}%"></span></div><small>Baseline ${formatNumber(item.baselineValue, 1)}${escapeHtml(item.unit)} · ${Math.round(progress)}% of target movement achieved</small></div></div></article>`;
}

function renderAudit(events: AuditEvent[]): string {
  if (!events.length) return emptyState("No audit events", "Workflow actions will appear here.");
  return `<div class="timeline">${events.map((item) => `<div class="timeline__item"><span class="timeline__dot"></span><div><div class="timeline__top"><strong>${escapeHtml(item.action)}</strong><time>${formatDate(item.timestamp, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</time></div><p>${escapeHtml(item.details)}</p><small>${escapeHtml(item.actor)} · ${escapeHtml(item.entityType)} ${escapeHtml(item.entityId)}</small></div></div>`).join("")}</div>`;
}

const fallbackKpiCatalog = [
  { name: "Open backlog", definition: "Count of trusted requests created on or before the analysis date that do not have a closed timestamp on or before that date.", grain: "Request", window: "Point in time", owner: "Operations" },
  { name: "SLA attainment", definition: "Closed trusted requests with resolution hours less than or equal to the record-level SLA target, divided by all trusted closed requests.", grain: "Closed request", window: "Trailing 28 days", owner: "Service Delivery" },
  { name: "Median resolution time", definition: "Median elapsed resolution hours across trusted closed requests; median is used to reduce sensitivity to extreme cases.", grain: "Closed request", window: "Trailing 28 days", owner: "Operations Analytics" },
  { name: "Reopen rate", definition: "Trusted closed requests marked reopened, divided by trusted closed requests.", grain: "Closed request", window: "Trailing 28 days", owner: "Quality" },
  { name: "Closure-to-intake ratio", definition: "Requests closed during the last seven days divided by requests created during the same period.", grain: "Request flow", window: "Trailing 7 days", owner: "Capacity Planning" },
  { name: "Data-quality score", definition: "Weighted rule score based on completeness, validity, uniqueness, consistency, and timeliness failures. Critical defects carry the largest penalty.", grain: "Dataset", window: "Current load", owner: "Data Governance" },
];

const dataDictionary = [
  ["request_id", "String", "Stable request identifier and analytical grain key", "Required; unique"],
  ["created_at", "UTC timestamp", "Time the request entered the operation", "Required; valid date"],
  ["closed_at", "UTC timestamp", "Time the request completed", "Required when status is Closed"],
  ["status", "Controlled text", "Current workflow state", "Open, In Progress, Pending Customer, Closed"],
  ["priority", "Controlled text", "Operational urgency", "Low, Normal, High, Critical"],
  ["category", "Controlled text", "Primary service taxonomy", "Must map to controlled category list"],
  ["location", "Controlled text", "Responsible service location", "Required for location analysis"],
  ["team", "Controlled text", "Accountable delivery team", "Required for performance ownership"],
  ["sla_hours", "Number", "Record-level service target in hours", "Positive number"],
  ["resolution_hours", "Number", "Elapsed hours to closure", "Non-negative when closed"],
  ["reopened", "Boolean", "Whether completed work reopened", "Yes or No"],
  ["satisfaction_score", "Number", "Optional post-service survey score", "1 through 5"],
];

function renderGovernance(): string {
  if (!dataset || !analytics) return "";
  const issuesBySeverity = (severity: Severity) => dataset!.quality.issues.filter((item) => item.severity === severity).length;
  return `${sectionHeader(
    "Data Governance",
    "Make the analytical trust layer visible",
    "Quality rules, KPI definitions, data lineage assumptions, exceptions, and audit evidence are part of the product—not hidden documentation.",
    `${button("Download quality issues", "export-quality", "secondary", "download")}${hasPermission("ingest_data") ? button("Upload replacement data", "open-upload", "primary", "upload") : ""}`,
  )}
  <section class="quality-hero"><div>${gauge(dataset.quality.score, "Quality score")}</div><div class="quality-hero__summary"><span class="eyebrow">Current validation result</span><h2>${dataset.quality.validRowCount.toLocaleString()} rows pass all listed checks</h2><p>${dataset.quality.issueRowCount.toLocaleString()} rows contain one or more rule failures. Blocking records are excluded from trusted KPI calculations while remaining visible in the exception register.</p><div class="quality-severity"><span class="quality-severity__critical"><b>${issuesBySeverity("Critical")}</b> Critical</span><span class="quality-severity__high"><b>${issuesBySeverity("High")}</b> High</span><span class="quality-severity__medium"><b>${issuesBySeverity("Medium")}</b> Medium</span><span><b>${issuesBySeverity("Low")}</b> Low</span></div></div><div class="quality-hero__stats"><div><span>Source rows</span><strong>${dataset.records.length.toLocaleString()}</strong></div><div><span>Trusted KPI rows</span><strong>${analytics.kpis.trustedRows.toLocaleString()}</strong></div><div><span>Duplicate IDs</span><strong>${dataset.quality.duplicateRowCount}</strong></div><div><span>Total rule failures</span><strong>${dataset.quality.issues.length}</strong></div></div></section>
  <section class="dashboard-grid">
    <article class="panel"><div class="panel__header"><div><span class="eyebrow">Rule performance</span><h2>Quality dimensions and thresholds</h2><p>Every rule exposes its purpose, severity, pass count, fail count, and score.</p></div></div><div class="rule-list">${dataset.quality.rules.map((rule) => `<div class="rule-row"><div><strong>${escapeHtml(rule.name)}</strong><p>${escapeHtml(rule.description)}</p><small>${escapeHtml(rule.dimension)} · ${escapeHtml(rule.severity)} severity</small></div><div class="rule-row__score"><b>${rule.score.toFixed(1)}%</b><span>${rule.failed} failed</span></div></div>`).join("")}</div></article>
    <article class="panel"><div class="panel__header"><div><span class="eyebrow">Assumptions and limitations</span><h2>What this analysis does—and does not—claim</h2><p>Transparent boundaries reduce the risk of overinterpreting a polished dashboard.</p></div></div><ul class="assumption-list">${dataset.assumptions.map((item) => `<li>${icon("check", 16)}<span>${escapeHtml(item)}</span></li>`).join("")}<li>${icon("info", 16)}<span>Historical backlog is reconstructed from created and closed timestamps; intermediate status changes are not available.</span></li><li>${icon("info", 16)}<span>Anomaly thresholds are explainable heuristics, not statistical proof of causation.</span></li><li>${icon("info", 16)}<span>The scenario model includes observed day-of-week seasonality, queue aging, category-mix constraints, and a transparent planning interval; it remains a decision-support forecast rather than a causal guarantee.</span></li><li>${icon("info", 16)}<span>The demo dataset is synthetic and contains intentionally inserted defects and performance patterns.</span></li></ul></article>
  </section>
  <section class="panel"><div class="panel__header"><div><span class="eyebrow">Exception register</span><h2>Data-quality issues</h2><p>Trace each failure to the source row, record identifier, field, rule, and observed value.</p></div></div>${renderQualityIssues(dataset.quality.issues.slice(0, 80))}</section>
  <section class="panel"><div class="panel__header"><div><span class="eyebrow">Versioned semantic layer</span><h2>KPI catalog and lineage</h2><p>${platformModeState === "server-governed" ? "Definitions are read from the governed SQLite semantic layer with explicit versions, owners, source fields, targets, and limitations." : "Static fallback shows the release-bundled KPI definitions."}</p></div></div><div class="kpi-catalog">${(governedKpiCatalog.length ? governedKpiCatalog : fallbackKpiCatalog.map((item, index) => ({ ...item, id: `fallback-${index}`, version: "1.0.0", effectiveDate: "2026-08-29", formula: "See documented analytical implementation", target: "Documented in release catalog", sourceFields: [], limitations: "Static showcase definition; open governed local mode for full lineage." }))).map((item) => `<article><div class="kpi-title-row"><h3>${escapeHtml(item.name)}</h3><span class="version-pill">v${escapeHtml(item.version)}</span></div><p>${escapeHtml(item.definition)}</p><dl><div><dt>Grain</dt><dd>${escapeHtml(item.grain)}</dd></div><div><dt>Window</dt><dd>${escapeHtml(item.window)}</dd></div><div><dt>Owner</dt><dd>${escapeHtml(item.owner)}</dd></div><div><dt>Target</dt><dd>${escapeHtml(item.target)}</dd></div></dl>${item.sourceFields.length ? `<small>Lineage: ${item.sourceFields.map(escapeHtml).join(" · ")}</small>` : ""}<details><summary>Formula & limitation</summary><code>${escapeHtml(item.formula)}</code><p>${escapeHtml(item.limitations)}</p></details></article>`).join("")}</div></section>
  <section class="panel"><div class="panel__header"><div><span class="eyebrow">Data model</span><h2>Core field dictionary</h2><p>The source schema is documented in the application and included with the downloadable project.</p></div></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Field</th><th>Type</th><th>Business meaning</th><th>Validation</th></tr></thead><tbody>${dataDictionary.map((row) => `<tr>${row.map((cell, index) => `<td>${index === 0 ? `<code>${escapeHtml(cell)}</code>` : escapeHtml(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table></div></section>`;
}


function staticObservability(): ObservabilitySnapshot | null {
  if (!dataset || !analytics) return null;
  const progressed = cases.filter((item) => item.status !== "Open").length;
  return {
    measuredAt: new Date().toISOString(),
    measurements: [
      { id: "release_gate", name: "Static bundle identity", value: 100, unit: "%", target: "Release-bundled assets", status: "Healthy", details: "Static mode can show the committed release, but server release gating is only available through the Windows/local server." },
      { id: "data_quality", name: "Data-quality score", value: dataset.quality.score, unit: "%", target: ">= 95%", status: dataset.quality.score >= 95 ? "Healthy" : "Watch", details: `${analytics.kpis.trustedRows} trusted rows in the current browser analysis.` },
      { id: "case_followthrough", name: "Case follow-through", value: cases.length ? (progressed / cases.length) * 100 : 0, unit: "%", target: ">= 80% beyond Open", status: cases.length && progressed / cases.length >= 0.8 ? "Healthy" : "Watch", details: "Browser-local workflow state in static fallback." },
    ],
    measuredImprovementRate: analytics.interventions.length ? (analytics.interventions.filter((item) => item.status === "Improved").length / analytics.interventions.length) * 100 : 0,
    latestIngestion: null,
    qualityHistory: [{ loadedAt: dataset.loadedAt, qualityScore: dataset.quality.score, trustedRowCount: analytics.kpis.trustedRows, rowCount: dataset.records.length }],
    alertReview: { reviewed: 0, confirmedSignals: 0, useful: 0, precisionPct: 0, usefulnessPct: 0 },
    latestBacktest: { id: "static-current", createdAt: new Date().toISOString(), datasetRunId: null, ...runScenario(dataset.records, dataset.quality, 0, 0).backtest },
    refreshSchedule: { enabled: false, nextDueAt: null, lastResult: "Static showcase has no server scheduler" },
    database: { engine: "None", journalMode: "N/A", location: "Static showcase uses browser-local reversible state" },
  };
}

function renderObservability(): string {
  if (!dataset || !analytics) return "";
  const snapshot = observabilitySnapshot ?? staticObservability();
  if (!snapshot) return "";
  const healthy = snapshot.measurements.filter((item) => item.status === "Healthy").length;
  const watch = snapshot.measurements.filter((item) => item.status === "Watch").length;
  const breach = snapshot.measurements.filter((item) => item.status === "Breach").length;
  return `${sectionHeader(
    "System Health",
    "Operate the analytics platform, not just the dashboard",
    "Release identity, governed ingestion, data quality, workflow follow-through, measured outcomes, and refresh health are visible as service-level objectives.",
    platformModeState === "server-governed" && hasPermission("ingest_data") ? button("Check governed source now", "refresh-source", "secondary", "reset") : "",
  )}
  <section class="observability-hero"><article><span>Healthy controls</span><strong>${healthy}</strong><small>${watch} watch · ${breach} breach</small></article><article><span>Measured improvement</span><strong>${snapshot.measuredImprovementRate.toFixed(1)}%</strong><small>Recorded outcomes classified Improved</small></article><article><span>Runtime mode</span><strong>${platformModeState === "server-governed" ? "Governed" : "Static"}</strong><small>${escapeHtml(snapshot.database.engine)} · ${escapeHtml(snapshot.database.journalMode)}</small></article><article><span>Refresh automation</span><strong>${snapshot.refreshSchedule.enabled ? "Enabled" : "Not active"}</strong><small>${snapshot.refreshSchedule.nextDueAt ? `Next ${formatDate(snapshot.refreshSchedule.nextDueAt, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}` : escapeHtml(snapshot.refreshSchedule.lastResult ?? "No schedule")}</small></article></section>
  <section class="panel"><div class="panel__header"><div><span class="eyebrow">Service-level objectives</span><h2>Operational reliability scorecard</h2><p>Each measure has a named target, current status, and evidence statement.</p></div></div><div class="slo-grid">${snapshot.measurements.map((item) => `<article class="slo-card slo-card--${item.status.toLowerCase()}"><div><span class="status-dot"></span><b>${escapeHtml(item.status)}</b></div><h3>${escapeHtml(item.name)}</h3><strong>${formatNumber(item.value, item.value % 1 ? 1 : 0)}${escapeHtml(item.unit)}</strong><small>Target ${escapeHtml(item.target)}</small><p>${escapeHtml(item.details)}</p></article>`).join("")}</div></section>
  <section class="dashboard-grid"><article class="panel"><div class="panel__header"><div><span class="eyebrow">Governed ingestion</span><h2>Latest accepted dataset</h2><p>Schema contracts, content hashes, quarantine counts, and refresh cadence are persisted separately from the analytical UI.</p></div></div>${snapshot.latestIngestion ? `<dl class="observability-detail"><div><dt>Dataset</dt><dd>${escapeHtml(snapshot.latestIngestion.datasetName)}</dd></div><div><dt>Run</dt><dd><code>${escapeHtml(snapshot.latestIngestion.runId)}</code></dd></div><div><dt>Loaded</dt><dd>${formatDate(snapshot.latestIngestion.loadedAt, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</dd></div><div><dt>Rows</dt><dd>${snapshot.latestIngestion.trustedRowCount.toLocaleString()} trusted / ${snapshot.latestIngestion.rowCount.toLocaleString()} source</dd></div><div><dt>Quality</dt><dd>${snapshot.latestIngestion.qualityScore.toFixed(1)}%</dd></div><div><dt>Schema drift</dt><dd>${snapshot.latestIngestion.unexpectedColumns.length ? snapshot.latestIngestion.unexpectedColumns.map(escapeHtml).join(", ") : "None"}</dd></div></dl>` : emptyState("Static hosting has no governed ingestion store", "Launch through OperationsIntelligence.bat to demonstrate SQLite migrations, idempotent ingestion, scheduled refresh, and server-enforced role controls.")}</article>
  <article class="panel"><div class="panel__header"><div><span class="eyebrow">Control architecture</span><h2>Enterprise foundation</h2><p>The portfolio demo keeps production-like controls inspectable without pretending they are a full enterprise identity stack.</p></div></div><ul class="feature-list"><li><b>Controlled migrations</b><span>Append-only SQL migrations initialize project-local SQLite state and preserve versioned structure.</span></li><li><b>Server-enforced demo roles</b><span>HttpOnly SameSite sessions, per-role permissions, and CSRF checks protect local write APIs.</span></li><li><b>Idempotent ingestion</b><span>Dataset SHA-256 prevents identical content from being processed twice while schema drift is surfaced explicitly.</span></li><li><b>Scheduled refresh</b><span>A bounded local scheduler checks the canonical source on cadence without network activity or hidden repairs.</span></li><li><b>Outcome observability</b><span>Cases, audit events, measured results, release health, data-quality history, reviewed alert evidence, and forecast backtests are operational evidence, not presentation-only metrics.</span></li></ul></article></section>
  <section class="dashboard-grid"><article class="panel"><div class="panel__header"><div><span class="eyebrow">Evaluation evidence</span><h2>Forecast backtest</h2><p>Scenario accuracy is measured on a held-out recent window and persisted idempotently in governed mode.</p></div></div>${snapshot.latestBacktest ? `<dl class="observability-detail"><div><dt>Model</dt><dd><code>${escapeHtml(snapshot.latestBacktest.modelVersion)}</code></dd></div><div><dt>Horizon</dt><dd>${snapshot.latestBacktest.horizonDays} days</dd></div><div><dt>MAE</dt><dd>${snapshot.latestBacktest.meanAbsoluteError.toFixed(2)} requests/day</dd></div><div><dt>Bias</dt><dd>${snapshot.latestBacktest.meanBias > 0 ? "+" : ""}${snapshot.latestBacktest.meanBias.toFixed(2)} requests/day</dd></div></dl>` : emptyState("No backtest persisted yet", "Open the governed demo as Executive or Analyst to record the current deterministic backtest evidence.")}</article><article class="panel"><div class="panel__header"><div><span class="eyebrow">Signal governance</span><h2>Reviewed alert evidence</h2><p>Portfolio-seeded review data distinguishes detected movement from signals that operators judged actionable.</p></div></div><dl class="observability-detail"><div><dt>Reviewed alerts</dt><dd>${snapshot.alertReview.reviewed}</dd></div><div><dt>Confirmed signal</dt><dd>${snapshot.alertReview.precisionPct.toFixed(1)}%</dd></div><div><dt>Rated useful</dt><dd>${snapshot.alertReview.usefulnessPct.toFixed(1)}%</dd></div><div><dt>Quality history points</dt><dd>${snapshot.qualityHistory.length}</dd></div></dl></article></section>`;
}

async function recordCurrentBacktestEvidence(): Promise<void> {
  if (platformModeState !== "server-governed" || !dataset || !hasPermission("record_backtests")) return;
  const backtest = runScenario(dataset.records, dataset.quality, 0, 0).backtest;
  await governedRecordBacktest(backtest);
}

async function syncGovernedState(): Promise<void> {
  if (platformModeState !== "server-governed") return;
  const current = platformSession();
  sessionDisplayName = current.user ? `${current.user.displayName} · ${current.user.role}` : "Governed local session";
  cases = await governedCases();
  audit = await governedAudit().catch(() => []);
  governedKpiCatalog = await governedKpis().catch(() => []);
  observabilitySnapshot = await governedObservability().catch(() => null);
  const automationState = await governedAutomationState().catch(() => ({ rules: [] as AutomationRule[], executions: [] as AutomationExecution[] }));
  automationRules = automationState.rules;
  automationExecutions = automationState.executions;
  const improvementState = await governedImprovementState().catch(() => ({ problems: [] as ProblemRecord[], initiatives: [] as ImprovementInitiative[], value: valueRealization }));
  problems = improvementState.problems;
  initiatives = improvementState.initiatives;
  valueRealization = improvementState.value;
  const playbookState = await governedPlaybookState().catch(() => ({ playbooks: [] as PlaybookDefinition[], runs: [] as PlaybookRun[] }));
  playbooks = playbookState.playbooks;
  playbookRuns = playbookState.runs;
}

async function switchRole(nextRole: Role): Promise<void> {
  if (platformModeState === "server-governed") {
    const current = await switchGovernedRole(nextRole);
    role = current.user?.role ?? nextRole;
    await syncGovernedState();
    if (dataset && hasPermission("record_backtests")) { await recordCurrentBacktestEvidence(); await syncGovernedState(); }
  } else {
    role = nextRole;
    saveRole(role);
    audit = addAudit(role, "Role view changed", "Application", role, `Navigation and default landing view updated for ${role}.`);
  }
  view = roleLanding[role];
  render();
}

function renderQualityIssues(items: QualityIssue[]): string {
  if (!items.length) return emptyState("No quality exceptions", "All visible quality rules passed.");
  return `<div class="table-wrap"><table class="data-table"><thead><tr><th>Severity</th><th>Row</th><th>Request</th><th>Field</th><th>Issue</th><th>Observed value</th></tr></thead><tbody>${items.map((item) => `<tr><td><span class="severity-label severity-label--${severityClass(item.severity)}">${escapeHtml(item.severity)}</span></td><td>${item.rowNumber}</td><td><code>${escapeHtml(item.requestId)}</code></td><td><code>${escapeHtml(item.field)}</code></td><td>${escapeHtml(item.message)}</td><td class="truncate-cell" title="${escapeHtml(item.value)}">${escapeHtml(item.value || "(blank)")}</td></tr>`).join("")}</tbody></table></div>`;
}

function renderRecords(): string {
  if (!dataset || !analytics) return "";
  const records = filteredRecords();
  const pageSize = 25;
  const pageCount = Math.max(1, Math.ceil(records.length / pageSize));
  recordPage = Math.min(recordPage, pageCount);
  const start = (recordPage - 1) * pageSize;
  const pageRecords = records.slice(start, start + pageSize);
  return `${sectionHeader(
    "Record Explorer",
    "Drill from KPIs to source-level evidence",
    "Search, filter, inspect, and export the records supporting the visible operational conclusions.",
    `${hasPermission("ingest_data") ? button("Upload CSV", "open-upload", "secondary", "upload") : ""}${button("Export filtered CSV", "export-filtered", "primary", "download")}`,
  )}
  ${filterBar(true)}
  <div class="scope-banner"><div><strong>${records.length.toLocaleString()} matching records</strong><span>Showing ${records.length ? start + 1 : 0}–${Math.min(start + pageSize, records.length)} · source dataset has ${dataset.records.length.toLocaleString()} rows</span></div><div class="pagination"><button type="button" class="icon-button" data-page="${recordPage - 1}" ${recordPage <= 1 ? "disabled" : ""} aria-label="Previous page">‹</button><span>Page ${recordPage} of ${pageCount}</span><button type="button" class="icon-button" data-page="${recordPage + 1}" ${recordPage >= pageCount ? "disabled" : ""} aria-label="Next page">›</button></div></div>
  <section class="panel panel--flush">${pageRecords.length ? renderRecordsTable(pageRecords, true) : emptyState("No matching records", "Change the search text or clear a filter.")}</section>
  <section class="upload-guidance"><div>${icon("upload", 26)}<div><h3>Use your own service-operation data</h3><p>${platformModeState === "server-governed" ? "Authorized uploads are independently validated and persisted in project-local SQLite; blocking defects are quarantined from trusted KPI calculations. Raw records are never sent to the optional AI summary service." : "Static hosting validates and analyzes the CSV in this browser; raw records are not sent to the optional AI summary service."} Only aggregated metrics are eligible for AI summary generation.</p></div></div>${hasPermission("ingest_data") ? `<button type="button" class="button button--secondary" data-action="open-upload">Choose CSV</button>` : `<span class="badge badge--neutral">Current role is read-only for ingestion</span>`}</section>`;
}

function renderRecordsTable(records: ServiceRecord[], compact: boolean): string {
  return `<div class="table-wrap"><table class="data-table ${compact ? "data-table--compact" : ""}"><thead><tr><th>Request</th><th>Created</th><th>Status</th><th>Priority</th><th>Category</th><th>Location</th><th>Team</th><th>Owner</th><th>SLA</th><th>Resolution</th></tr></thead><tbody>${records.map((record) => `<tr><td><code>${escapeHtml(record.requestId || "(missing)")}</code></td><td>${formatDate(record.createdAt, { month: "short", day: "numeric" })}</td><td><span class="status-pill status-pill--${safeCssToken(record.status)}">${escapeHtml(record.status || "Missing")}</span></td><td><span class="priority-text priority-text--${safeCssToken(record.priority)}">${escapeHtml(record.priority || "Missing")}</span></td><td>${escapeHtml(record.category || "Missing")}</td><td>${escapeHtml(record.location || "Missing")}</td><td>${escapeHtml(record.team || "Missing")}</td><td>${escapeHtml(record.owner || "Missing")}</td><td>${record.slaHours === null ? "—" : `${formatNumber(record.slaHours)} hrs`}</td><td>${record.resolutionHours === null ? "Open" : `${formatNumber(record.resolutionHours, 1)} hrs`}</td></tr>`).join("")}</tbody></table></div>`;
}

function renderAbout(): string {
  const linkedStages = [
    ["01", "Raw data", "Contract-driven CSV ingestion with deterministic demo evidence"],
    ["02", "Validation", "Quality rules, quarantine, drift, freshness, and trusted-row boundaries"],
    ["03", "Data model", "Request grain plus connected category, team, and location objects"],
    ["04", "KPI definitions", "Versioned formulas, ownership, windows, targets, and limitations"],
    ["05", "Process intelligence", "Derived variants, bottlenecks, rework patterns, and association signals"],
    ["06", "Analytics & pulse", "Role-aware trends, anomalies, priorities, and evidence-linked signals"],
    ["07", "Root-cause investigation", "Contribution and relative-risk evidence without causal overclaiming"],
    ["08", "Automation", "Trigger → Logic → Action rules with simulation, dedupe, cooldown, and RBAC"],
    ["09", "Workflow & playbooks", "Cases, owners, due dates, reusable response steps, and audit history"],
    ["10", "Measured outcome", "Before/after measurements, forecast backtesting, and monitoring"],
    ["11", "Improvement value", "Problem records, initiatives, outcome confidence, and value realization"],
    ["12", "Operational learning", "Grounded questions, follow-up investigation, and documented boundaries"],
  ];
  return `${sectionHeader(
    "Product Story",
    "A closed-loop operations platform—not just a dashboard",
    "The platform demonstrates how trusted operational evidence becomes an explanation, a controlled action, a measured outcome, and an improvement decision.",
    `${button("Download project README", "download-readme", "secondary", "download")}${button("Open command center", "go-overview", "primary", "dashboard")}`,
  )}
  <section class="story-hero"><div><span class="eyebrow">Recruiter-facing narrative</span><h2>Observe → explain → act → verify</h2><p>A reviewer can trace a business problem from source records through governed metrics and process evidence, test a controlled automation, start a playbook, and see how improvement value is measured—all with transparent assumptions and drill-down evidence.</p><div class="story-tags"><span>Data analysis</span><span>Process intelligence</span><span>Business intelligence</span><span>Data governance</span><span>Workflow automation</span><span>Operations</span><span>Program management</span><span>Analytics engineering</span></div></div><div class="story-score"><strong>12</strong><span>linked stages from data to operational learning</span></div></section>
  <section class="process-chain">${linkedStages.map(([number, title, description], index) => `<article><span>${number}</span><div><h3>${escapeHtml(title)}</h3><p>${escapeHtml(description)}</p></div>${index < linkedStages.length - 1 ? `<i>${icon("chevron", 18)}</i>` : ""}</article>`).join("")}</section>
  <section class="dashboard-grid">
    <article class="panel"><div class="panel__header"><div><span class="eyebrow">v0.3.0 foundation</span><h2>Process intelligence + closed-loop automation</h2><p>The governed v0.2.x foundation remains intact while v0.3.0 adds investigation, automation, learning, and value measurement as first-class capabilities.</p></div></div><ul class="feature-list"><li><b>Process intelligence</b><span>Derived operational paths, bottleneck scoring, rework exposure, association-only root factors, and an object relationship graph.</span></li><li><b>Controlled automation</b><span>Governed Trigger → Logic → Action rules with simulation, role checks, CSRF, deduplication, cooldown, local case creation, and execution history.</span></li><li><b>Problem & improvement management</b><span>Recurring patterns can become problems, initiatives, measurable outcomes, and transparent value-realization evidence.</span></li><li><b>Guided playbooks</b><span>Reusable operational response sequences create consistent, auditable follow-through rather than relying on memory.</span></li><li><b>Grounded Operations Analyst</b><span>Role-aware Pulse signals and deterministic questions stay tied to current metrics, evidence, limitations, and follow-up paths.</span></li><li><b>Durable governed foundation</b><span>SQLite migrations, server-enforced demo roles, idempotent ingestion, KPI versions, forecasting/backtests, SLOs, and fail-closed release identity remain active.</span></li></ul></article>
    <article class="panel"><div class="panel__header"><div><span class="eyebrow">What a reviewer can test</span><h2>Interactive proof points</h2><p>The demonstration is designed around practical decisions rather than feature counts.</p></div></div><div class="proof-grid"><div><strong>Follow a process</strong><p>Inspect common paths, bottlenecks, rework, and supporting evidence.</p></div><div><strong>Investigate a root factor</strong><p>Compare contribution and relative risk with an explicit non-causal boundary.</p></div><div><strong>Simulate automation</strong><p>See which rules match before any governed action occurs.</p></div><div><strong>Run a governed rule</strong><p>Create project-local cases only after server authorization, dedupe, and cooldown checks.</p></div><div><strong>Start a playbook</strong><p>Advance a reusable response sequence and preserve progress.</p></div><div><strong>Ask the operation</strong><p>Use grounded Q&A that exposes evidence and assumptions instead of inventing answers.</p></div><div><strong>Measure improvement</strong><p>Review problem records, initiatives, outcomes, and synthetic value estimates.</p></div><div><strong>Trace the data</strong><p>Drill from a headline KPI to governed definitions, quality exceptions, and source rows.</p></div></div></article>
  </section>
  <section class="panel"><div class="panel__header"><div><span class="eyebrow">Delivery boundary</span><h2>Portfolio-safe by design</h2><p>The static showcase demonstrates analysis and simulation. Governed local mode adds durable storage and controlled writes. Real enterprise identity, production integrations, and external write-back remain deployment concerns rather than simulated claims.</p></div></div><div class="roadmap"><article><span>v0.2 · complete</span><h3>Governed operational foundation</h3><p>Durable state, identity, RBAC, ingestion contracts, KPI governance, forecasting, SLOs, and release controls.</p></article><article><span>v0.3 · complete</span><h3>Process intelligence & closed-loop automation</h3><p>Process variants, object relationships, root-factor evidence, rules, playbooks, routing, grounded analyst, problem management, and value realization.</p></article><article><span>Future deployment</span><h3>Approved enterprise integration</h3><p>When a real environment exists: SSO/OIDC, managed relational storage, vetted connectors, secret management, and explicit external write-back approvals.</p></article></div></section>`;
}

function renderModal(): string {
  return `<div class="modal" id="upload-modal" aria-hidden="true"><div class="modal__scrim" data-action="close-upload"></div><div class="modal__dialog" role="dialog" aria-modal="true" aria-labelledby="upload-title"><button class="icon-button modal__close" type="button" data-action="close-upload" aria-label="Close upload dialog">${icon("close")}</button><span class="eyebrow">${platformModeState === "server-governed" ? "Governed ingestion" : "Local browser ingestion"}</span><h2 id="upload-title">Load a service-operations CSV</h2><p>${platformModeState === "server-governed" ? "The server independently validates the data contract, records an idempotent ingestion run, quarantines blocking defects, and preserves the audit evidence in project-local SQLite." : "The static fallback validates and analyzes the file in this browser. Uploads are not transmitted to the optional AI summary endpoint."}</p><label class="drop-zone" for="dataset-file">${icon("upload", 32)}<strong>Choose a CSV file</strong><span>Expected columns are documented below</span><input id="dataset-file" type="file" accept=".csv,text/csv"></label><div class="schema-preview"><strong>Required schema</strong><code>request_id, created_at, closed_at, status, priority, category, subcategory, location, team, owner, channel, sla_hours, resolution_hours, reopened, satisfaction_score, last_updated_at, source_system</code></div><div class="modal__actions"><button type="button" class="button button--ghost" data-action="reset-demo">Reset to demo data</button><button type="button" class="button button--secondary" data-action="download-template">Download CSV template</button></div></div></div>`;
}

function render(): void {
  try {
    if (!dataset || !analytics) return;
    const content = view === "overview" ? renderOverview() : view === "analysis" ? renderAnalysis() : view === "process" ? renderProcessIntelligence() : view === "automation" ? renderAutomationImprovement() : view === "analyst" ? renderOperationsAnalyst() : view === "workflow" ? renderWorkflow() : view === "governance" ? renderGovernance() : view === "observability" ? renderObservability() : view === "records" ? renderRecords() : renderAbout();
    root.innerHTML = shell(content) + renderModal();
    document.title = `${currentViewLabel()} | Operations Intelligence`;
  } catch (error) {
    reportCritical(error, `render:${view}`);
    root.innerHTML = `<div class="fatal-screen"><div>${icon("alert", 36)}</div><h1>The view could not be rendered</h1><p>${escapeHtml(error instanceof Error ? error.message : String(error))}</p><button type="button" class="button button--primary" data-action="reset-demo">Restore demo state</button></div>`;
  }
}

function setView(next: ViewId): void {
  view = next;
  sidebarOpen = false;
  window.scrollTo({ top: 0, behavior: "smooth" });
  render();
}

function recompute(nextDataset: Omit<AppDataset, "analysisDate">): void {
  const nextAnalytics = buildAnalytics(nextDataset.records, nextDataset.quality);
  dataset = { ...nextDataset, analysisDate: nextAnalytics.kpis.analysisDate };
  analytics = nextAnalytics;
  intelligence = buildIntelligence(nextDataset.records, nextDataset.quality, nextAnalytics);
  analystAnswer = answerOperationsQuestion(analystQuery, nextAnalytics, intelligence, dataset.name);
  summaryText = groundedSummary(analytics, dataset.name);
  summaryMode = "local";
  if (platformModeState === "static-showcase") {
    cases = seedCases(analytics.recommendations);
    audit = loadAudit();
    saveDatasetName(dataset.name);
  }
  recordPage = 1;
}

async function loadStaticIntelligenceCatalogs(): Promise<void> {
  if (platformModeState !== "static-showcase") return;
  const [automationResponse, playbookResponse, improvementResponse] = await Promise.all([
    fetch("./data/automation_catalog.json", { cache: "no-store" }),
    fetch("./data/playbook_catalog.json", { cache: "no-store" }),
    fetch("./data/improvement_catalog.json", { cache: "no-store" }),
  ]);
  if (automationResponse.ok) {
    const payload = await automationResponse.json() as { rules?: Array<Record<string, unknown>> };
    automationRules = (payload.rules ?? []).map((rule) => ({
      id: String(rule.id ?? ""), name: String(rule.name ?? ""), description: String(rule.description ?? ""), enabled: Boolean(rule.enabled), severity: String(rule.severity ?? "Medium") as Severity,
      ownerRole: String(rule.owner_role ?? "Operations Analyst"), cooldownMinutes: Number(rule.cooldown_minutes ?? 0), dedupeKey: String(rule.dedupe_key ?? ""),
      conditions: Array.isArray(rule.conditions) ? rule.conditions as AutomationRule["conditions"] : [], action: (rule.action ?? {}) as AutomationRule["action"],
    }));
  }
  if (playbookResponse.ok) {
    const payload = await playbookResponse.json() as { playbooks?: Array<Record<string, unknown>> };
    playbooks = (payload.playbooks ?? []).map((item) => ({ id: String(item.id ?? ""), name: String(item.name ?? ""), description: String(item.description ?? ""), steps: Array.isArray(item.steps) ? item.steps.map(String) : [] }));
  }
  if (improvementResponse.ok) {
    const payload = await improvementResponse.json() as { problems?: Array<Record<string, unknown>>; initiatives?: Array<Record<string, unknown>> };
    problems = (payload.problems ?? []).map((item) => ({ id: String(item.id ?? ""), title: String(item.title ?? ""), status: String(item.status ?? ""), owner: String(item.owner ?? ""), hypothesis: String(item.hypothesis ?? ""), evidence: Array.isArray(item.evidence) ? item.evidence.map(String) : [] }));
    initiatives = (payload.initiatives ?? []).map((item) => ({
      id: String(item.id ?? ""), problemId: item.problem_id ? String(item.problem_id) : null, title: String(item.title ?? ""), status: String(item.status ?? ""), owner: String(item.owner ?? ""),
      baselineMetric: String(item.baseline_metric ?? ""), baselineValue: Number(item.baseline_value ?? 0), targetValue: Number(item.target_value ?? 0), measuredValue: Number(item.measured_value ?? 0), unit: String(item.unit ?? ""),
      hoursSavedMonthly: Number(item.hours_saved_monthly ?? 0), backlogAvoided: Number(item.backlog_avoided ?? 0), slaImprovementPoints: Number(item.sla_improvement_points ?? 0), confidencePct: Number(item.confidence_pct ?? 0),
    }));
    valueRealization = deriveValueSnapshot(initiatives);
  }
}

async function loadDemo(): Promise<void> {
  root.innerHTML = `<div class="loading-screen"><div class="loading-mark">OI</div><div class="loading-bar"><span></span></div><h1>Preparing the Service Operations Command Center</h1><p>Validating demo records and calculating decision metrics…</p></div>`;
  const [{ records, quality }, metadataResponse] = await Promise.all([loadCsvDataset("./data/service_requests_demo.csv"), fetch("./data/demo_metadata.json", { cache: "no-store" })]);
  const metadata = metadataResponse.ok ? (await metadataResponse.json()) as { name?: string; scenario_notes?: string[] } : {};
  recompute({
    name: metadata.name ?? "Synthetic Service Operations Demo",
    source: "demo",
    records,
    quality,
    loadedAt: new Date().toISOString(),
    assumptions: metadata.scenario_notes ?? [],
  });
  if (platformModeState === "server-governed") {
    await recordCurrentBacktestEvidence();
    await syncGovernedState();
  } else {
    await loadStaticIntelligenceCatalogs();
  }
  logEvent("info", "Demo dataset loaded.", `${records.length} rows; quality score ${quality.score}.`);
  render();
}

function openUpload(): void {
  const modal = document.querySelector<HTMLElement>("#upload-modal");
  modal?.setAttribute("aria-hidden", "false");
  modal?.classList.add("modal--open");
}

function closeUpload(): void {
  const modal = document.querySelector<HTMLElement>("#upload-modal");
  modal?.setAttribute("aria-hidden", "true");
  modal?.classList.remove("modal--open");
}

async function handleUpload(file: File): Promise<void> {
  if (file.size > 15 * 1024 * 1024) throw new Error("The demo upload limit is 15 MB.");
  const text = await file.text();
  const parsed = parseCsv(text);
  const missing = validateHeaders(parsed.headers);
  if (missing.length > 0) throw new Error(`Missing required columns: ${missing.join(", ")}`);
  const records = toServiceRecords(parsed.rows);
  if (records.length === 0) throw new Error("The CSV does not contain any data rows.");
  const quality = validateRecords(records);
  let ingestionNote = "Static showcase: uploaded records are processed in this browser and are not persisted after refresh.";
  if (platformModeState === "server-governed") {
    const result = await governedIngest(text, file.name.replace(/\.csv$/i, ""), file.name);
    ingestionNote = `Governed ingestion ${result.status}${result.idempotent ? " (idempotent; existing content reused)" : ""}: ${result.trustedRowCount}/${result.rowCount} trusted rows; ${result.issueRowCount} issue rows; quality ${result.qualityScore.toFixed(1)}%.`;
  }
  recompute({
    name: file.name.replace(/\.csv$/i, ""),
    source: "upload",
    records,
    quality,
    loadedAt: new Date().toISOString(),
    assumptions: [
      ingestionNote,
      "The application uses the latest valid record timestamp as the analysis date.",
      "Blocking quality defects are quarantined from trusted KPI calculations but remain visible in the exception register.",
    ],
  });
  if (platformModeState === "server-governed") {
    await recordCurrentBacktestEvidence();
    await syncGovernedState();
  } else {
    audit = addAudit(role, "Dataset uploaded", "Dataset", dataset!.name, `${records.length} rows loaded; quality score ${quality.score.toFixed(1)}%.`);
  }
  closeUpload();
  view = roleLanding[role];
  render();
}

function downloadBlob(filename: string, content: string, type: string): void {
  const blob = new Blob([content], { type });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
}


function recordsToCsv(records: ServiceRecord[]): string {
  const headers = ["request_id", "created_at", "closed_at", "status", "priority", "category", "subcategory", "location", "team", "owner", "channel", "sla_hours", "resolution_hours", "reopened", "satisfaction_score", "last_updated_at", "source_system"];
  const rows = records.map((record) => [record.requestId, record.createdAt, record.closedAt, record.status, record.priority, record.category, record.subcategory, record.location, record.team, record.owner, record.channel, record.slaHours, record.resolutionHours, record.reopened ? "Yes" : "No", record.satisfactionScore, record.lastUpdatedAt, record.sourceSystem].map(csvEscape).join(","));
  return `${headers.join(",")}\n${rows.join("\n")}\n`;
}

function exportFiltered(): void {
  const records = filteredRecords();
  downloadBlob("Operations_Intelligence_Filtered_Records.csv", recordsToCsv(records), "text/csv;charset=utf-8");
  audit = addAudit(role, "Filtered records exported", "Dataset", dataset?.name ?? "Unknown", `${records.length} records exported.`);
}

function exportQuality(): void {
  if (!dataset) return;
  const headers = ["severity", "row_number", "request_id", "rule_id", "field", "message", "observed_value"];
  const rows = dataset.quality.issues.map((item) => [item.severity, item.rowNumber, item.requestId, item.ruleId, item.field, item.message, item.value].map(csvEscape).join(","));
  downloadBlob("Operations_Intelligence_Data_Quality_Issues.csv", `${headers.join(",")}\n${rows.join("\n")}\n`, "text/csv;charset=utf-8");
  audit = addAudit(role, "Quality exceptions exported", "Dataset", dataset.name, `${dataset.quality.issues.length} rule failures exported.`);
}

function exportCases(): void {
  const headers = ["case_id", "title", "priority", "status", "owner", "created_at", "due_at", "source", "expected_impact", "baseline_metric", "baseline_value", "target_value", "current_value", "unit", "notes"];
  const rows = cases.map((item) => [item.id, item.title, item.priority, item.status, item.owner, item.createdAt, item.dueAt, item.source, item.expectedImpact, item.baselineMetric, item.baselineValue, item.targetValue, item.currentValue, item.unit, item.notes].map(csvEscape).join(","));
  downloadBlob("Operations_Intelligence_Case_Register.csv", `${headers.join(",")}\n${rows.join("\n")}\n`, "text/csv;charset=utf-8");
  audit = addAudit(role, "Case register exported", "Workflow", "Case register", `${cases.length} cases exported.`);
}

function managementBriefHtml(): string {
  if (!dataset || !analytics) return "";
  const a = analytics;
  const i = intelligence;
  const issueCounts = (severity: Severity) => dataset!.quality.issues.filter((item) => item.severity === severity).length;
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Operations Intelligence Management Brief</title><style>body{font-family:Arial,sans-serif;color:#172033;max-width:1000px;margin:40px auto;padding:0 28px;line-height:1.5}header{border-bottom:4px solid #167d87;padding-bottom:20px;margin-bottom:28px}.eyebrow{color:#167d87;text-transform:uppercase;font-weight:700;font-size:12px;letter-spacing:.12em}h1{font-size:34px;margin:6px 0}h2{font-size:22px;margin-top:34px}.meta{color:#657085}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.kpi{border:1px solid #d9dee7;border-radius:10px;padding:16px}.kpi span{display:block;color:#657085;font-size:12px;text-transform:uppercase}.kpi strong{font-size:25px}.callout{background:#edf7f7;border-left:4px solid #167d87;padding:18px;margin:20px 0}.alert,.rec{border-bottom:1px solid #e5e8ee;padding:14px 0}.alert b,.rec b{display:block}.badge{display:inline-block;padding:3px 8px;border-radius:999px;background:#eef1f5;font-size:11px;font-weight:bold;margin-right:8px}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;border-bottom:1px solid #e5e8ee;padding:9px}th{background:#f6f7f9}footer{margin-top:40px;padding-top:18px;border-top:1px solid #d9dee7;color:#657085;font-size:12px}@media print{body{margin:0}.no-print{display:none}}</style></head><body><header><span class="eyebrow">Service Operations Command Center</span><h1>Management Brief</h1><p>${escapeHtml(dataset.name)} · Analysis through ${formatDate(a.kpis.analysisDate)} · Generated ${formatDate(new Date())}</p></header><section class="callout"><h2>Executive summary</h2>${summaryText.split("\n\n").map((p) => `<p>${escapeHtml(p)}</p>`).join("")}</section><section><h2>Headline metrics</h2><div class="grid"><div class="kpi"><span>Open backlog</span><strong>${a.kpis.openBacklog}</strong><p>${a.kpis.backlogChangePct > 0 ? "+" : ""}${a.kpis.backlogChangePct.toFixed(1)}% in 7 days</p></div><div class="kpi"><span>SLA attainment</span><strong>${a.kpis.slaAttainmentPct.toFixed(1)}%</strong><p>${a.kpis.slaChangePoints > 0 ? "+" : ""}${a.kpis.slaChangePoints.toFixed(1)} points</p></div><div class="kpi"><span>Median resolution</span><strong>${a.kpis.medianResolutionHours.toFixed(1)} hrs</strong><p>${a.kpis.resolutionChangePct > 0 ? "+" : ""}${a.kpis.resolutionChangePct.toFixed(1)}%</p></div><div class="kpi"><span>Reopen rate</span><strong>${a.kpis.reopenRatePct.toFixed(1)}%</strong></div><div class="kpi"><span>Closure / intake</span><strong>${a.kpis.closureToIntakeRatio.toFixed(2)}×</strong></div><div class="kpi"><span>Data quality</span><strong>${a.kpis.qualityScore.toFixed(1)}%</strong></div></div></section><section><h2>Priority alerts</h2>${a.alerts.slice(0, 6).map((item) => `<div class="alert"><span class="badge">${escapeHtml(item.severity)}</span><span class="badge">${escapeHtml(item.type)}</span><b>${escapeHtml(item.title)}</b><p>${escapeHtml(item.description)}</p><small>Evidence: ${item.evidenceCount} records · ${escapeHtml(item.dimension)}</small></div>`).join("")}</section><section><h2>Recommended management actions</h2>${a.recommendations.slice(0, 6).map((item, index) => `<div class="rec"><b>${index + 1}. ${escapeHtml(item.title)}</b><p>${escapeHtml(item.action)}</p><small>Owner: ${escapeHtml(item.ownerRole)} · Expected impact: ${escapeHtml(item.expectedImpact)}</small></div>`).join("")}</section><section><h2>Root-cause evidence</h2><table><thead><tr><th>Dimension</th><th>Value</th><th>Misses</th><th>Miss rate</th><th>Contribution</th><th>Risk</th></tr></thead><tbody>${a.rootCauses.slice(0, 10).map((item) => `<tr><td>${escapeHtml(item.dimension)}</td><td>${escapeHtml(item.name)}</td><td>${item.missCount}/${item.closedCount}</td><td>${item.missRatePct.toFixed(1)}%</td><td>${item.contributionPct.toFixed(1)}%</td><td>${item.relativeRisk.toFixed(2)}×</td></tr>`).join("")}</tbody></table></section>${i ? `<section><h2>Process intelligence</h2><p><b>Priority bottleneck:</b> ${escapeHtml(i.bottlenecks[0]?.name ?? "No stable signal")} · ${i.bottlenecks[0] ? `${i.bottlenecks[0].score.toFixed(1)}/100 signal score` : "n/a"}. Process paths are derived from observed request attributes and outcome evidence; intermediate stage timestamps are not invented.</p><table><thead><tr><th>Condition</th><th>Support</th><th>Miss contribution</th><th>Relative risk</th></tr></thead><tbody>${i.rootFactors.slice(0, 8).map((item) => `<tr><td>${escapeHtml(item.condition)}</td><td>${item.support}</td><td>${item.contributionPct.toFixed(1)}%</td><td>${item.relativeRisk.toFixed(2)}×</td></tr>`).join("")}</tbody></table><p><small>Association identifies investigation targets; this analysis does not establish causality.</small></p></section><section><h2>Automation and improvement opportunities</h2>${i.automationOpportunities.slice(0, 4).map((item) => `<div class="rec"><b>${escapeHtml(item.name)} · ${item.score}/100</b><p>${escapeHtml(item.rationale)}</p><small>Estimated ${item.estimatedHoursSavedMonthly.toFixed(1)} hours/month · ${item.expectedCycleTimeReductionPct}% cycle opportunity · ${escapeHtml(item.complexity)} complexity. Estimates are prioritization aids, not guarantees.</small></div>`).join("")}</section>` : ""}<section><h2>Data-quality statement</h2><p>${dataset.quality.issueRowCount} rows contain one or more rule failures. ${a.kpis.trustedRows} of ${dataset.records.length} source rows are included in trusted KPI calculations. Failures: ${issueCounts("Critical")} critical, ${issueCounts("High")} high, ${issueCounts("Medium")} medium, and ${issueCounts("Low")} low.</p></section><section><h2>Assumptions and limitations</h2><ul>${dataset.assumptions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}<li>Backlog history is reconstructed from created and closed timestamps.</li><li>Anomaly thresholds identify management signals; they do not establish causation.</li><li>The six-week scenario incorporates recent seasonality, queue aging, workload-mix constraints, backtesting, and an 80% planning interval; it is still decision support rather than causal proof.</li></ul></section><footer>Operations Intelligence & Automation Platform v${APP_VERSION}<br>Copyright © 2026 Gateway Information Group LLC. All rights reserved.</footer></body></html>`;
}

function exportBrief(): void {
  downloadBlob("Operations_Intelligence_Management_Brief.html", managementBriefHtml(), "text/html;charset=utf-8");
  audit = addAudit(role, "Management brief exported", "Report", dataset?.name ?? "Unknown", "Evidence-backed HTML management brief downloaded.");
}

async function generateAiSummary(): Promise<void> {
  if (!dataset || !analytics || summaryMode === "pending") return;
  summaryMode = "pending";
  render();
  const payload = {
    dataset: dataset.name,
    analysisDate: analytics.kpis.analysisDate.toISOString(),
    kpis: analytics.kpis,
    alerts: analytics.alerts.slice(0, 6).map(({ id, ...item }) => item),
    rootCauses: analytics.rootCauses.slice(0, 6),
    recommendations: analytics.recommendations.slice(0, 5),
    quality: {
      score: dataset.quality.score,
      issueRows: dataset.quality.issueRowCount,
      issueCounts: {
        critical: dataset.quality.issues.filter((item) => item.severity === "Critical").length,
        high: dataset.quality.issues.filter((item) => item.severity === "High").length,
        medium: dataset.quality.issues.filter((item) => item.severity === "Medium").length,
      },
    },
  };
  try {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 12_000);
    const response = await fetch("/api/summary", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload), signal: controller.signal });
    window.clearTimeout(timer);
    if (!response.ok) throw new Error(`AI summary endpoint returned ${response.status}.`);
    const result = await response.json() as { summary?: string };
    if (!result.summary || result.summary.length < 80) throw new Error("AI summary response was incomplete.");
    summaryText = result.summary.slice(0, 6000);
    summaryMode = "ai";
    audit = addAudit(role, "AI summary generated", "Report", dataset.name, "Optional server-side summary generated from bounded aggregate evidence.");
    logEvent("info", "Optional AI summary generated.");
  } catch (error) {
    summaryText = groundedSummary(analytics, dataset.name);
    summaryMode = "local";
    logEvent("warning", "AI summary unavailable; local grounded fallback used.", error instanceof Error ? error.message : String(error));
    showToast("Optional AI service is not configured; the grounded local summary remains active.", "warning");
  }
  render();
}

function showToast(message: string, type: "success" | "warning" | "error" = "success"): void {
  document.querySelector(".toast")?.remove();
  const toast = document.createElement("div");
  toast.className = `toast toast--${type}`;
  toast.textContent = message;
  document.body.appendChild(toast);
  window.setTimeout(() => toast.classList.add("toast--visible"), 20);
  window.setTimeout(() => {
    toast.classList.remove("toast--visible");
    window.setTimeout(() => toast.remove(), 250);
  }, 3600);
}

async function createCaseFromRecommendation(recommendationId: string): Promise<void> {
  if (!analytics) return;
  const rec = analytics.recommendations.find((item) => item.id === recommendationId);
  if (!rec || cases.some((item) => item.title === rec.title)) return;
  const now = new Date();
  const due = new Date(now.getTime() + 7 * 86_400_000);
  const payload: Partial<WorkflowCase> = {
    title: rec.title,
    description: rec.rationale,
    priority: rec.priority,
    owner: rec.ownerRole,
    dueAt: due.toISOString(),
    source: rec.sourceAlertId ? `Alert ${rec.sourceAlertId}` : "Analytical recommendation",
    expectedImpact: rec.expectedImpact,
    baselineMetric: "SLA attainment",
    baselineValue: analytics.kpis.slaAttainmentPct,
    targetValue: Math.min(98, analytics.kpis.slaAttainmentPct + 10),
    currentValue: analytics.kpis.slaAttainmentPct,
    unit: "%",
  };
  if (platformModeState === "server-governed") {
    const item = await governedCreateCase(payload);
    await syncGovernedState();
    showToast(`${item.id} created in the governed case register.`);
  } else {
    const number = Math.max(0, ...cases.map((item) => Number(item.id.replace(/\D/g, "")) || 0)) + 1;
    const item: WorkflowCase = {
      id: `CASE-${String(number).padStart(3, "0")}`,
      title: payload.title ?? "Operational case",
      description: payload.description ?? "",
      priority: payload.priority ?? "Medium",
      status: "Open",
      owner: payload.owner ?? "Unassigned",
      createdAt: now.toISOString(),
      dueAt: payload.dueAt ?? due.toISOString(),
      source: payload.source ?? "Analytical recommendation",
      expectedImpact: payload.expectedImpact ?? "",
      baselineMetric: payload.baselineMetric ?? "Operational target",
      baselineValue: payload.baselineValue ?? 0,
      targetValue: payload.targetValue ?? 0,
      currentValue: payload.currentValue ?? 0,
      unit: payload.unit ?? "",
      notes: "",
    };
    cases = [item, ...cases];
    saveCases(cases);
    audit = addAudit(role, "Case created", "Case", item.id, `Created from recommendation: ${item.title}`);
    showToast(`${item.id} created and added to the browser-local action register.`);
  }
  render();
}

function addTopCase(): void {
  if (!analytics) return;
  const available = analytics.recommendations.find((rec) => !cases.some((item) => item.title === rec.title));
  if (available) void createCaseFromRecommendation(available.id).catch((error) => showToast(error instanceof Error ? error.message : String(error), "error"));
  else showToast("All current recommendations already have cases.", "warning");
}

function resetFilters(): void {
  filters = { category: "All", team: "All", location: "All", priority: "All", search: "", dateWindowDays: 120 };
  recordPage = 1;
  render();
}

function downloadTemplate(): void {
  const headers = "request_id,created_at,closed_at,status,priority,category,subcategory,location,team,owner,channel,sla_hours,resolution_hours,reopened,satisfaction_score,last_updated_at,source_system\n";
  const example = "SR-EXAMPLE-001,2026-08-01T09:00:00Z,2026-08-01T15:30:00Z,Closed,Normal,Account Access,Password reset,Central Service Center,Technical Support,A. Patel,Web,48,6.5,No,5,2026-08-01T15:30:00Z,Service Portal\n";
  downloadBlob("Operations_Intelligence_CSV_Template.csv", headers + example, "text/csv;charset=utf-8");
}

function downloadReadme(): void {
  const text = `# Operations Intelligence & Automation Platform\n\nPortfolio release v${APP_VERSION}\n\n## Purpose\n\nA closed-loop service-operations platform that connects trusted data, governed KPIs, process intelligence, evidence-grounded investigation, controlled automation, workflow playbooks, measured outcomes, and improvement value.\n\n## Demonstrated decision chain\n\nRaw Data → Validation → Governed Metrics → Process Intelligence → Root-Factor Evidence → Trigger/Logic/Action → Workflow/Playbook → Measured Outcome → Improvement Value → Operational Learning\n\n## Included roles\n\n- Executive\n- Analyst\n- Operator\n- Data Steward\n\n## Safety and deployment boundary\n\nGoverned local mode records authorized ingestions and operational writes in project-local SQLite. Static hosting provides an analysis/simulation showcase without pretending to provide server-side controls. External system writes are not enabled by default. The grounded Operations Analyst works from current application evidence and documented assumptions.\n\nCopyright © 2026 Gateway Information Group LLC. All rights reserved.\n`;
  downloadBlob("Operations_Intelligence_README.md", text, "text/markdown;charset=utf-8");
}

root.addEventListener("click", (event) => {
  const target = event.target as HTMLElement;
  const nav = target.closest<HTMLElement>("[data-nav]");
  if (nav?.dataset.nav) {
    setView(nav.dataset.nav as ViewId);
    return;
  }
  const action = target.closest<HTMLElement>("[data-action]")?.dataset.action;
  if (action) {
    if (action === "toggle-sidebar") { sidebarOpen = !sidebarOpen; render(); }
    else if (action === "open-upload") openUpload();
    else if (action === "close-upload") closeUpload();
    else if (action === "export-filtered") exportFiltered();
    else if (action === "export-quality") exportQuality();
    else if (action === "export-cases") exportCases();
    else if (action === "export-brief") exportBrief();
    else if (action === "generate-ai-summary") void generateAiSummary();
    else if (action === "copy-summary") void navigator.clipboard.writeText(summaryText).then(() => showToast("Summary copied to the clipboard.")).catch(() => showToast("Clipboard access is unavailable.", "warning"));
    else if (action === "clear-filters") resetFilters();
    else if (action === "download-template") downloadTemplate();
    else if (action === "download-readme") downloadReadme();
    else if (action === "go-overview") setView("overview");
    else if (action === "go-records") setView("records");
    else if (action === "simulate-automations") {
      void (async () => {
        automationExecutions = platformModeState === "server-governed" ? await governedEvaluateAutomations(currentAutomationMetrics(), false) : simulateLocalAutomations();
        showToast(`${automationExecutions.filter((item) => item.status === "Simulated").length} automation rules matched in simulation.`);
        render();
      })().catch((error) => showToast(error instanceof Error ? error.message : String(error), "error"));
    }
    else if (action === "execute-automations") {
      void (async () => {
        if (platformModeState !== "server-governed") throw new Error("Governed automation execution requires the local server mode.");
        automationExecutions = await governedEvaluateAutomations(currentAutomationMetrics(), true);
        await syncGovernedState();
        showToast(`${automationExecutions.filter((item) => item.status === "Triggered").length} governed actions created; duplicate/cooldown rules were suppressed.`);
        render();
      })().catch((error) => showToast(error instanceof Error ? error.message : String(error), "error"));
    }
    else if (action === "classify-routing") {
      const field = document.querySelector<HTMLTextAreaElement>("#routing-text");
      routingText = field?.value.trim() || routingText;
      routingSuggestion = classifyRequestText(routingText);
      render();
    }
    else if (action === "ask-analyst") {
      const field = document.querySelector<HTMLInputElement>("#analyst-query");
      analystQuery = field?.value.trim() || analystQuery;
      if (dataset && analytics && intelligence) analystAnswer = answerOperationsQuestion(analystQuery, analytics, intelligence, dataset.name);
      render();
    }
    else if (action === "add-top-case") addTopCase();
    else if (action === "download-diagnostics") downloadBrowserDiagnostics();
    else if (action === "refresh-source") {
      void governedRefresh().then(async () => { await syncGovernedState(); showToast("Governed source refresh checked."); render(); }).catch((error) => showToast(error instanceof Error ? error.message : String(error), "error"));
    }
    else if (action === "reset-demo") {
      closeUpload();
      if (platformModeState === "static-showcase") resetLocalState();
      void (async () => {
        if (platformModeState === "server-governed" && hasPermission("ingest_data")) { await governedRefresh(); await syncGovernedState(); }
        await loadDemo();
        showToast(platformModeState === "server-governed" ? "Demo data reloaded; governed workflow history was preserved." : "Demo data and browser-local workflow state were restored.");
      })().catch((error) => reportCritical(error, "reset-demo"));
    }
    return;
  }
  const caseButton = target.closest<HTMLElement>("[data-create-case]");
  if (caseButton?.dataset.createCase) void createCaseFromRecommendation(caseButton.dataset.createCase).catch((error) => showToast(error instanceof Error ? error.message : String(error), "error"));
  const playbookButton = target.closest<HTMLElement>("[data-start-playbook]");
  if (playbookButton?.dataset.startPlaybook) {
    const playbookId = playbookButton.dataset.startPlaybook;
    void (async () => {
      if (platformModeState === "server-governed") {
        const linkedCase = cases.find((item) => item.status !== "Resolved")?.id;
        await governedStartPlaybook(playbookId, linkedCase);
        await syncGovernedState();
      } else {
        const definition = playbooks.find((item) => item.id === playbookId);
        if (!definition) return;
        const now = new Date().toISOString();
        playbookRuns = [{ id: `LOCAL-${playbookId}`, playbookId, caseId: cases.find((item) => item.status !== "Resolved")?.id ?? null, status: "Active", currentStep: 0, steps: definition.steps.map((label) => ({ label, completed: false })), startedAt: now, updatedAt: now }, ...playbookRuns.filter((item) => item.playbookId !== playbookId)];
      }
      showToast("Playbook started."); render();
    })().catch((error) => showToast(error instanceof Error ? error.message : String(error), "error"));
  }
  const advanceButton = target.closest<HTMLElement>("[data-advance-playbook]");
  if (advanceButton?.dataset.advancePlaybook) {
    const runId = advanceButton.dataset.advancePlaybook;
    void (async () => {
      if (platformModeState === "server-governed") {
        await governedAdvancePlaybook(runId); await syncGovernedState();
      } else {
        playbookRuns = playbookRuns.map((run) => {
          if (run.id !== runId) return run;
          const steps = run.steps.map((step, index) => index === run.currentStep ? { ...step, completed: true } : step);
          const next = Math.min(steps.length, run.currentStep + 1);
          return { ...run, steps, currentStep: next, status: next >= steps.length ? "Completed" : "Active", updatedAt: new Date().toISOString() };
        });
      }
      showToast("Playbook progress recorded."); render();
    })().catch((error) => showToast(error instanceof Error ? error.message : String(error), "error"));
  }
  const analystQuestion = target.closest<HTMLElement>("[data-analyst-question]")?.dataset.analystQuestion;
  if (analystQuestion) {
    analystQuery = analystQuestion;
    if (dataset && analytics && intelligence) analystAnswer = answerOperationsQuestion(analystQuery, analytics, intelligence, dataset.name);
    render();
  }
  const page = target.closest<HTMLElement>("[data-page]")?.dataset.page;
  if (page) {
    recordPage = Math.max(1, Number(page));
    render();
  }
});

root.addEventListener("change", (event) => {
  const target = event.target as HTMLInputElement | HTMLSelectElement;
  if (target.id === "role-select") {
    void switchRole(target.value as Role).catch((error) => {
      showToast(error instanceof Error ? error.message : String(error), "error");
      render();
    });
    return;
  }
  if (target.id === "dataset-file" && target instanceof HTMLInputElement && target.files?.[0]) {
    const file = target.files[0];
    void handleUpload(file).then(() => showToast(`${file.name} loaded successfully.`)).catch((error) => {
      logEvent("error", "Dataset upload failed.", error instanceof Error ? error.message : String(error));
      showToast(error instanceof Error ? error.message : String(error), "error");
    });
    return;
  }
  if (target.dataset.filter) {
    const key = target.dataset.filter as keyof FilterState;
    if (key === "dateWindowDays") filters.dateWindowDays = Number(target.value);
    else if (key === "search") filters.search = target.value;
    else filters[key] = target.value as never;
    recordPage = 1;
    render();
    return;
  }
  if (target.dataset.caseStatus) {
    const caseId = target.dataset.caseStatus;
    const changes = { status: target.value as CaseStatus };
    if (platformModeState === "server-governed") {
      void governedUpdateCase(caseId, changes).then(async () => { await syncGovernedState(); showToast(`${caseId} status updated.`); render(); }).catch((error) => showToast(error instanceof Error ? error.message : String(error), "error"));
    } else {
      cases = updateCase(caseId, changes);
      audit = addAudit(role, "Case status updated", "Case", caseId, `Status changed to ${target.value}.`);
      showToast(`${caseId} status updated.`);
      render();
    }
    return;
  }
  if (target.dataset.caseOwner) {
    const caseId = target.dataset.caseOwner;
    const changes = { owner: target.value.trim() || "Unassigned" };
    if (platformModeState === "server-governed") {
      void governedUpdateCase(caseId, changes).then(async () => { await syncGovernedState(); showToast(`${caseId} owner updated.`); render(); }).catch((error) => showToast(error instanceof Error ? error.message : String(error), "error"));
    } else {
      cases = updateCase(caseId, changes);
      audit = addAudit(role, "Case owner updated", "Case", caseId, `Owner changed to ${changes.owner}.`);
      showToast(`${caseId} owner updated.`);
      render();
    }
  }
});

root.addEventListener("input", (event) => {
  const target = event.target as HTMLInputElement | HTMLTextAreaElement;
  if (target.id === "analyst-query") analystQuery = target.value;
  else if (target.id === "routing-text") routingText = target.value;
  else if (target.dataset.scenario === "demand") {
    scenarioDemand = Number(target.value);
    render();
  } else if (target.dataset.scenario === "capacity") {
    scenarioCapacity = Number(target.value);
    render();
  } else if (target.dataset.filter === "search") {
    filters.search = target.value;
    recordPage = 1;
    window.clearTimeout((window as unknown as { __searchTimer?: number }).__searchTimer);
    (window as unknown as { __searchTimer?: number }).__searchTimer = window.setTimeout(() => render(), 180);
  }
});

installGlobalDiagnostics();
void (async () => {
  const state = await initializePlatform(role);
  platformModeState = state.mode;
  if (state.user) role = state.user.role;
  if (platformModeState === "server-governed") await syncGovernedState();
  await loadDemo();
})().catch((error) => {
  reportCritical(error, "initial-load");
  root.innerHTML = `<div class="fatal-screen"><div>${icon("alert", 36)}</div><h1>The demo dataset could not be loaded</h1><p>${escapeHtml(error instanceof Error ? error.message : String(error))}</p><p>Launch the production bundle through <code>OperationsIntelligence.bat</code> or serve the <code>dist</code> folder with a local web server.</p></div>`;
});
