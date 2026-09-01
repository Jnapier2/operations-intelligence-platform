export type Role = "Executive" | "Analyst" | "Operator" | "Data Steward";
export type ViewId = "overview" | "analysis" | "process" | "automation" | "analyst" | "workflow" | "governance" | "observability" | "records" | "about";
export type Severity = "Critical" | "High" | "Medium" | "Low";
export type CaseStatus = "Open" | "In Progress" | "Monitoring" | "Resolved";

export interface ServiceRecord {
  requestId: string;
  createdAt: Date | null;
  closedAt: Date | null;
  status: string;
  priority: string;
  category: string;
  subcategory: string;
  location: string;
  team: string;
  owner: string;
  channel: string;
  slaHours: number | null;
  resolutionHours: number | null;
  reopened: boolean;
  satisfactionScore: number | null;
  lastUpdatedAt: Date | null;
  sourceSystem: string;
  rowNumber: number;
  raw: Record<string, string>;
}

export interface QualityIssue {
  id: string;
  rowNumber: number;
  requestId: string;
  ruleId: string;
  field: string;
  severity: Severity;
  message: string;
  value: string;
}

export interface QualityRuleResult {
  id: string;
  name: string;
  dimension: "Completeness" | "Validity" | "Uniqueness" | "Consistency" | "Timeliness";
  description: string;
  severity: Severity;
  passed: number;
  failed: number;
  score: number;
}

export interface QualityReport {
  score: number;
  validRowCount: number;
  issueRowCount: number;
  duplicateRowCount: number;
  issues: QualityIssue[];
  rules: QualityRuleResult[];
}

export interface DailyPoint {
  date: string;
  label: string;
  created: number;
  closed: number;
  net: number;
}

export interface DimensionMetric {
  name: string;
  value: number;
  secondary?: number;
  count?: number;
  label?: string;
}

export interface KpiSet {
  analysisDate: Date;
  totalRows: number;
  trustedRows: number;
  openBacklog: number;
  backlogChangePct: number;
  slaAttainmentPct: number;
  slaChangePoints: number;
  medianResolutionHours: number;
  resolutionChangePct: number;
  reopenRatePct: number;
  reopenChangePoints: number;
  satisfaction: number;
  satisfactionChange: number;
  newThisWeek: number;
  closedThisWeek: number;
  closureToIntakeRatio: number;
  qualityScore: number;
}

export interface AlertItem {
  id: string;
  severity: Severity;
  type: "Volume" | "Backlog" | "Service Level" | "Data Quality" | "Workflow";
  title: string;
  description: string;
  dimension: string;
  currentValue: number;
  baselineValue: number;
  changePct: number;
  evidenceCount: number;
  recommendedAction: string;
}

export interface RootCauseItem {
  dimension: "Category" | "Team" | "Location" | "Channel";
  name: string;
  missCount: number;
  closedCount: number;
  missRatePct: number;
  contributionPct: number;
  relativeRisk: number;
}

export interface Recommendation {
  id: string;
  priority: Severity;
  title: string;
  rationale: string;
  action: string;
  ownerRole: string;
  expectedImpact: string;
  sourceAlertId?: string;
}

export interface WorkflowCase {
  id: string;
  title: string;
  description: string;
  priority: Severity;
  status: CaseStatus;
  owner: string;
  createdAt: string;
  dueAt: string;
  source: string;
  expectedImpact: string;
  baselineMetric: string;
  baselineValue: number;
  targetValue: number;
  currentValue: number;
  unit: string;
  notes: string;
}

export interface AuditEvent {
  id: string;
  timestamp: string;
  actor: string;
  action: string;
  entityType: string;
  entityId: string;
  details: string;
}

export interface InterventionResult {
  id: string;
  title: string;
  metric: string;
  before: number;
  after: number;
  change: number;
  unit: string;
  direction: "higher" | "lower";
  status: "Improved" | "Mixed" | "Insufficient data";
  description: string;
}

export interface ForecastPoint {
  week: number;
  label: string;
  projectedBacklog: number;
  baselineBacklog: number;
  lowerBacklog: number;
  upperBacklog: number;
}

export interface ForecastBacktest {
  horizonDays: number;
  meanAbsoluteError: number;
  meanBias: number;
  observedDailyFlow: number;
  modelVersion: string;
}

export interface ScenarioResult {
  demandChangePct: number;
  capacityChangePct: number;
  currentWeeklyIntake: number;
  currentWeeklyClosures: number;
  projectedWeeklyIntake: number;
  projectedWeeklyClosures: number;
  forecast: ForecastPoint[];
  endBacklog: number;
  baselineEndBacklog: number;
  confidenceLevel: number;
  agingConstraintPct: number;
  skillConstraintPct: number;
  backtest: ForecastBacktest;
  assumptions: string[];
}

export interface GovernedKpiDefinition {
  id: string;
  name: string;
  owner: string;
  version: string;
  effectiveDate: string;
  definition: string;
  formula: string;
  grain: string;
  window: string;
  target: string;
  sourceFields: string[];
  limitations: string;
}

export interface SloMeasurement {
  id: string;
  name: string;
  value: number;
  unit: string;
  target: string;
  status: "Healthy" | "Watch" | "Breach";
  details: string;
}

export interface ObservabilitySnapshot {
  measuredAt: string;
  measurements: SloMeasurement[];
  measuredImprovementRate: number;
  latestIngestion: {
    runId: string;
    datasetName: string;
    status: string;
    loadedAt: string;
    rowCount: number;
    trustedRowCount: number;
    issueRowCount: number;
    qualityScore: number;
    unexpectedColumns: string[];
  } | null;
  qualityHistory: Array<{ loadedAt: string; qualityScore: number; trustedRowCount: number; rowCount: number }>;
  alertReview: { reviewed: number; confirmedSignals: number; useful: number; precisionPct: number; usefulnessPct: number };
  latestBacktest: (ForecastBacktest & { id: string; createdAt: string; datasetRunId: string | null }) | null;
  refreshSchedule: { enabled: boolean; nextDueAt: string | null; lastResult: string | null };
  database: { engine: string; journalMode: string; location: string };
}


export interface ProcessVariant {
  id: string;
  path: string[];
  signature: string;
  count: number;
  sharePct: number;
  closedCount: number;
  slaMissPct: number;
  reopenPct: number;
  medianResolutionHours: number;
}

export interface ProcessBottleneck {
  id: string;
  kind: "Queue" | "Team" | "Location" | "Rework" | "Priority";
  name: string;
  support: number;
  medianResolutionHours: number;
  slaMissPct: number;
  reopenPct: number;
  score: number;
  evidence: string;
}

export interface ProcessRootFactor {
  id: string;
  condition: string;
  support: number;
  missCount: number;
  missRatePct: number;
  contributionPct: number;
  relativeRisk: number;
  liftPoints: number;
  interpretation: string;
}

export interface ObjectGraphNode {
  id: string;
  type: "Category" | "Team" | "Location";
  label: string;
  volume: number;
  riskScore: number;
}

export interface ObjectGraphEdge {
  source: string;
  target: string;
  relationship: string;
  weight: number;
}

export interface OperationalObjectGraph {
  nodes: ObjectGraphNode[];
  edges: ObjectGraphEdge[];
}

export interface PulseInsight {
  id: string;
  metric: string;
  headline: string;
  detail: string;
  status: "Attention" | "Watch" | "Positive" | "Stable";
  evidence: string[];
  nextAction: string;
}

export interface ClassificationSuggestion {
  category: string;
  team: string;
  confidencePct: number;
  reasons: string[];
  alternatives: Array<{ category: string; confidencePct: number }>;
}

export interface AutomationOpportunity {
  id: string;
  name: string;
  score: number;
  volumeScore: number;
  effortScore: number;
  repeatabilityScore: number;
  riskScore: number;
  dataConfidenceScore: number;
  estimatedHoursSavedMonthly: number;
  expectedCycleTimeReductionPct: number;
  affectedMonthlyVolume: number;
  complexity: "Low" | "Medium" | "High";
  rationale: string;
}

export interface AlertNoiseSummary {
  generated: number;
  consolidated: number;
  suppressed: number;
  highPriority: number;
  dedupeKeys: number;
  suppressionReasons: string[];
}

export interface GroundedAnalystAnswer {
  answer: string;
  evidence: string[];
  caveat: string;
  followUps: string[];
}

export interface IntelligenceBundle {
  processVariants: ProcessVariant[];
  bottlenecks: ProcessBottleneck[];
  rootFactors: ProcessRootFactor[];
  objectGraph: OperationalObjectGraph;
  pulse: PulseInsight[];
  automationOpportunities: AutomationOpportunity[];
  alertNoise: AlertNoiseSummary;
  processAssumptions: string[];
}

export interface AutomationRule {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  severity: Severity;
  ownerRole: string;
  cooldownMinutes: number;
  dedupeKey: string;
  conditions: Array<{ metric: string; operator: string; value: number }>;
  action: { type: string; title: string; owner: string; priority: Severity; expectedImpact: string };
}

export interface AutomationExecution {
  id: string;
  ruleId: string;
  evaluatedAt: string;
  status: "Triggered" | "Suppressed" | "No Match" | "Simulated";
  reason: string;
  caseId: string | null;
  evidence: Record<string, number>;
}

export interface ProblemRecord {
  id: string;
  title: string;
  status: string;
  owner: string;
  hypothesis: string;
  evidence: string[];
}

export interface ImprovementInitiative {
  id: string;
  problemId: string | null;
  title: string;
  status: string;
  owner: string;
  baselineMetric: string;
  baselineValue: number;
  targetValue: number;
  measuredValue: number;
  unit: string;
  hoursSavedMonthly: number;
  backlogAvoided: number;
  slaImprovementPoints: number;
  confidencePct: number;
}

export interface PlaybookDefinition {
  id: string;
  name: string;
  description: string;
  steps: string[];
}

export interface PlaybookRun {
  id: string;
  playbookId: string;
  caseId: string | null;
  status: string;
  currentStep: number;
  steps: Array<{ label: string; completed: boolean }>;
  startedAt: string;
  updatedAt: string;
}

export interface ValueRealizationSnapshot {
  initiativesActive: number;
  initiativesCompleted: number;
  successful: number;
  inconclusive: number;
  hoursSavedMonthly: number;
  backlogAvoided: number;
  slaImprovementPoints: number;
  measuredInitiatives: ImprovementInitiative[];
}

export type PlatformMode = "server-governed" | "static-showcase";

export interface PlatformSession {
  mode: PlatformMode;
  authenticated: boolean;
  user?: { id: string; displayName: string; role: Role };
  permissions: string[];
}

export interface FilterState {
  category: string;
  team: string;
  location: string;
  priority: string;
  search: string;
  dateWindowDays: number;
}

export interface AppDataset {
  name: string;
  source: "demo" | "upload";
  records: ServiceRecord[];
  quality: QualityReport;
  loadedAt: string;
  analysisDate: Date;
  assumptions: string[];
}

export interface AnalyticsBundle {
  kpis: KpiSet;
  dailyTrend: DailyPoint[];
  backlogByCategory: DimensionMetric[];
  slaByTeam: DimensionMetric[];
  volumeByLocation: DimensionMetric[];
  alerts: AlertItem[];
  rootCauses: RootCauseItem[];
  recommendations: Recommendation[];
  interventions: InterventionResult[];
}
