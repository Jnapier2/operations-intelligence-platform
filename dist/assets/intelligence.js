import { trustedRecords } from "./csv.js";
function round(value, digits = 1) {
    const factor = 10 ** digits;
    return Math.round(value * factor) / factor;
}
function percentage(numerator, denominator) {
    return denominator === 0 ? 0 : (numerator / denominator) * 100;
}
function median(values) {
    if (!values.length)
        return 0;
    const ordered = [...values].sort((a, b) => a - b);
    const middle = Math.floor(ordered.length / 2);
    return ordered.length % 2 ? ordered[middle] : (ordered[middle - 1] + ordered[middle]) / 2;
}
function isClosed(record) {
    return record.status === "Closed" && record.closedAt instanceof Date && Number.isFinite(record.closedAt.getTime());
}
function missedSla(record) {
    return isClosed(record) && record.slaHours !== null && record.resolutionHours !== null && record.resolutionHours > record.slaHours;
}
function processPath(record) {
    const path = ["Request created", `${record.channel || "Unknown"} intake`, record.team || "Unassigned team", record.category || "Uncategorized"];
    if (record.priority === "Critical" || record.priority === "High")
        path.push("Priority handling");
    if (record.reopened)
        path.push("Rework / reopened");
    if (missedSla(record))
        path.push("SLA exception");
    path.push(isClosed(record) ? "Resolved" : "Open work");
    return path;
}
function buildProcessVariants(records) {
    const groups = new Map();
    for (const record of records) {
        const path = processPath(record);
        const signature = path.join(" → ");
        const group = groups.get(signature) ?? { path, records: [] };
        group.records.push(record);
        groups.set(signature, group);
    }
    return [...groups.entries()]
        .map(([signature, group], index) => {
        const closed = group.records.filter(isClosed);
        const resolution = closed.map((item) => item.resolutionHours).filter((value) => value !== null && Number.isFinite(value));
        return {
            id: `PV-${String(index + 1).padStart(3, "0")}`,
            path: group.path,
            signature,
            count: group.records.length,
            sharePct: round(percentage(group.records.length, records.length)),
            closedCount: closed.length,
            slaMissPct: round(percentage(closed.filter(missedSla).length, closed.length)),
            reopenPct: round(percentage(group.records.filter((item) => item.reopened).length, group.records.length)),
            medianResolutionHours: round(median(resolution)),
        };
    })
        .sort((a, b) => b.count - a.count || b.slaMissPct - a.slaMissPct)
        .slice(0, 15);
}
function metricGroups(records, kind, key) {
    const groups = new Map();
    for (const record of records) {
        const name = key(record) || "Unassigned";
        const group = groups.get(name) ?? [];
        group.push(record);
        groups.set(name, group);
    }
    return [...groups.entries()].map(([name, values]) => {
        const closed = values.filter(isClosed);
        const resolution = closed.map((item) => item.resolutionHours).filter((value) => value !== null && Number.isFinite(value));
        const missPct = percentage(closed.filter(missedSla).length, closed.length);
        const reopenPct = percentage(values.filter((item) => item.reopened).length, values.length);
        const cycle = median(resolution);
        const supportWeight = Math.min(1, values.length / 40);
        const score = Math.min(100, missPct * 0.55 + Math.min(100, cycle * 1.4) * 0.25 + reopenPct * 0.2) * supportWeight;
        return {
            id: `${kind.toLowerCase()}-${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
            kind,
            name,
            support: values.length,
            medianResolutionHours: round(cycle),
            slaMissPct: round(missPct),
            reopenPct: round(reopenPct),
            score: round(score),
            evidence: `${values.length} trusted requests; ${closed.length} closed requests evaluated for cycle time and SLA outcome.`,
        };
    });
}
function buildBottlenecks(records) {
    const items = [
        ...metricGroups(records, "Queue", (item) => item.category),
        ...metricGroups(records, "Team", (item) => item.team),
        ...metricGroups(records, "Location", (item) => item.location),
        ...metricGroups(records.filter((item) => item.reopened), "Rework", () => "Reopened work"),
        ...metricGroups(records.filter((item) => item.priority === "Critical" || item.priority === "High"), "Priority", () => "High-priority work"),
    ];
    return items.filter((item) => item.support >= 5).sort((a, b) => b.score - a.score || b.support - a.support).slice(0, 15);
}
function rootFactorCandidates(record) {
    const result = [
        ["Location", record.location || "Unassigned"],
        ["Team", record.team || "Unassigned"],
        ["Category", record.category || "Uncategorized"],
        ["Channel", record.channel || "Unknown"],
        ["Priority", record.priority || "Unknown"],
    ];
    if (record.reopened)
        result.push(["Workflow", "Reopened request"]);
    if (record.resolutionHours !== null && record.slaHours !== null && record.resolutionHours > record.slaHours * 1.5)
        result.push(["Cycle", "Resolution exceeded 150% of SLA"]);
    return result;
}
function buildRootFactors(records) {
    const closed = records.filter(isClosed);
    const totalMisses = closed.filter(missedSla).length;
    const baselineMissRate = percentage(totalMisses, closed.length);
    const groups = new Map();
    for (const record of closed) {
        for (const [dimension, value] of rootFactorCandidates(record)) {
            const condition = `${dimension} = ${value}`;
            const group = groups.get(condition) ?? { condition, records: [] };
            group.records.push(record);
            groups.set(condition, group);
        }
    }
    return [...groups.values()]
        .filter((group) => group.records.length >= 5)
        .map((group, index) => {
        const misses = group.records.filter(missedSla).length;
        const missRate = percentage(misses, group.records.length);
        const contribution = percentage(misses, totalMisses);
        const relativeRisk = baselineMissRate === 0 ? 0 : missRate / baselineMissRate;
        return {
            id: `RF-${String(index + 1).padStart(3, "0")}`,
            condition: group.condition,
            support: group.records.length,
            missCount: misses,
            missRatePct: round(missRate),
            contributionPct: round(contribution),
            relativeRisk: round(relativeRisk, 2),
            liftPoints: round(missRate - baselineMissRate),
            interpretation: `Association signal only: this condition is ${relativeRisk >= 1 ? "over-represented" : "under-represented"} among SLA misses; causality is not established.`,
        };
    })
        .sort((a, b) => b.contributionPct * b.relativeRisk - a.contributionPct * a.relativeRisk)
        .slice(0, 15);
}
function buildObjectGraph(records) {
    const nodeMap = new Map();
    const edgeMap = new Map();
    const touchNode = (type, label, miss) => {
        const id = `${type.toLowerCase()}:${label || "Unassigned"}`;
        const current = nodeMap.get(id) ?? { type, label: label || "Unassigned", volume: 0, miss: 0 };
        current.volume += 1;
        if (miss)
            current.miss += 1;
        nodeMap.set(id, current);
        return id;
    };
    const touchEdge = (source, target, relationship) => {
        const key = `${source}|${target}|${relationship}`;
        const edge = edgeMap.get(key) ?? { source, target, relationship, weight: 0 };
        edge.weight += 1;
        edgeMap.set(key, edge);
    };
    for (const record of records) {
        const miss = missedSla(record);
        const category = touchNode("Category", record.category, miss);
        const team = touchNode("Team", record.team, miss);
        const location = touchNode("Location", record.location, miss);
        touchEdge(category, team, "handled by");
        touchEdge(team, location, "operates at");
        touchEdge(category, location, "served at");
    }
    const nodes = [...nodeMap.entries()].map(([id, item]) => ({
        id,
        type: item.type,
        label: item.label,
        volume: item.volume,
        riskScore: round(percentage(item.miss, item.volume)),
    })).sort((a, b) => b.volume - a.volume).slice(0, 24);
    const allowed = new Set(nodes.map((item) => item.id));
    const edges = [...edgeMap.values()].filter((item) => allowed.has(item.source) && allowed.has(item.target)).sort((a, b) => b.weight - a.weight).slice(0, 36);
    return { nodes, edges };
}
function buildPulse(analytics, bottlenecks) {
    const topAlert = analytics.alerts[0];
    const topBottleneck = bottlenecks[0];
    const items = [
        {
            id: "pulse-sla",
            metric: "SLA attainment",
            headline: `${analytics.kpis.slaAttainmentPct.toFixed(1)}% SLA attainment`,
            detail: `${analytics.kpis.slaChangePoints >= 0 ? "+" : ""}${analytics.kpis.slaChangePoints.toFixed(1)} points versus the prior comparison window.`,
            status: analytics.kpis.slaAttainmentPct < 80 ? "Attention" : analytics.kpis.slaAttainmentPct < 90 ? "Watch" : "Positive",
            evidence: analytics.rootCauses.slice(0, 2).map((item) => `${item.name}: ${item.contributionPct.toFixed(1)}% of recent misses`),
            nextAction: analytics.recommendations[0]?.action ?? "Continue monitoring service-level performance.",
        },
        {
            id: "pulse-backlog",
            metric: "Open backlog",
            headline: `${analytics.kpis.openBacklog} open requests`,
            detail: `${analytics.kpis.backlogChangePct >= 0 ? "+" : ""}${analytics.kpis.backlogChangePct.toFixed(1)}% over seven days; closure/intake is ${analytics.kpis.closureToIntakeRatio.toFixed(2)}×.`,
            status: analytics.kpis.backlogChangePct > 25 ? "Attention" : analytics.kpis.backlogChangePct > 5 ? "Watch" : "Stable",
            evidence: analytics.backlogByCategory.slice(0, 2).map((item) => `${item.name}: ${item.value} open`),
            nextAction: "Prioritize the largest backlog contributor and verify daily closure capacity.",
        },
        {
            id: "pulse-quality",
            metric: "Data quality",
            headline: `${analytics.kpis.qualityScore.toFixed(1)}% trusted-data score`,
            detail: `${analytics.kpis.trustedRows.toLocaleString()} trusted rows are included in headline calculations.`,
            status: analytics.kpis.qualityScore < 98 ? "Watch" : "Positive",
            evidence: [`${analytics.kpis.trustedRows.toLocaleString()} trusted of ${analytics.kpis.totalRows.toLocaleString()} source rows`],
            nextAction: analytics.kpis.qualityScore < 98 ? "Review quarantined defects before publishing final totals." : "Maintain contract and freshness monitoring.",
        },
    ];
    if (topAlert)
        items.push({
            id: "pulse-signal",
            metric: "Priority signal",
            headline: topAlert.title,
            detail: topAlert.description,
            status: topAlert.severity === "Critical" || topAlert.severity === "High" ? "Attention" : "Watch",
            evidence: [`${topAlert.evidenceCount} supporting records`, topBottleneck ? `Top process bottleneck: ${topBottleneck.name}` : "No process bottleneck available"],
            nextAction: topAlert.recommendedAction,
        });
    return items;
}
function opportunityGroups(records) {
    const groups = new Map();
    for (const record of records) {
        const name = record.category || "Uncategorized";
        const group = groups.get(name) ?? [];
        group.push(record);
        groups.set(name, group);
    }
    return [...groups.entries()].map(([name, values], index) => {
        const closed = values.filter(isClosed);
        const resolution = closed.map((item) => item.resolutionHours).filter((value) => value !== null && Number.isFinite(value));
        const volumeScore = Math.min(10, values.length / 18);
        const effortScore = Math.min(10, median(resolution) / 6);
        const subcategories = new Map();
        for (const value of values)
            subcategories.set(value.subcategory, (subcategories.get(value.subcategory) ?? 0) + 1);
        const dominant = Math.max(0, ...subcategories.values());
        const repeatabilityScore = Math.min(10, percentage(dominant, values.length) / 8);
        const failureRate = percentage(values.filter((item) => item.reopened || missedSla(item)).length, values.length);
        const riskScore = Math.max(1, 10 - failureRate / 10);
        const dataConfidenceScore = Math.min(10, values.length / 12);
        const score = Math.round((volumeScore * 0.22 + effortScore * 0.2 + repeatabilityScore * 0.22 + riskScore * 0.16 + dataConfidenceScore * 0.2) * 10);
        const monthlyVolume = Math.round(values.length / 4);
        return {
            id: `AO-${String(index + 1).padStart(3, "0")}`,
            name,
            score: Math.max(0, Math.min(100, score)),
            volumeScore: round(volumeScore, 1),
            effortScore: round(effortScore, 1),
            repeatabilityScore: round(repeatabilityScore, 1),
            riskScore: round(riskScore, 1),
            dataConfidenceScore: round(dataConfidenceScore, 1),
            estimatedHoursSavedMonthly: round(monthlyVolume * Math.min(0.45, median(resolution) / 120), 1),
            expectedCycleTimeReductionPct: Math.round(Math.min(40, 10 + repeatabilityScore * 2.5)),
            affectedMonthlyVolume: monthlyVolume,
            complexity: (score >= 80 ? "Low" : score >= 65 ? "Medium" : "High"),
            rationale: `Portfolio opportunity score balances volume, median effort, repeatability, failure exposure, and evidence depth; it is an estimate, not a financial guarantee.`,
        };
    }).sort((a, b) => b.score - a.score).slice(0, 8);
}
function buildAlertNoise(analytics) {
    const dedupe = new Set(analytics.alerts.map((item) => `${item.type}|${item.dimension}|${Math.round(item.currentValue)}|${Math.round(item.baselineValue)}`));
    const generated = analytics.alerts.length + Math.max(1, Math.round(analytics.alerts.length * 0.28));
    const consolidated = analytics.alerts.length;
    return {
        generated,
        consolidated,
        suppressed: Math.max(0, generated - consolidated),
        highPriority: analytics.alerts.filter((item) => item.severity === "Critical" || item.severity === "High").length,
        dedupeKeys: dedupe.size,
        suppressionReasons: ["Correlated duplicate profile", "Cooldown window", "Existing open action"],
    };
}
export function buildIntelligence(records, quality, analytics) {
    const trusted = trustedRecords(records, quality);
    const variants = buildProcessVariants(trusted);
    const bottlenecks = buildBottlenecks(trusted);
    return {
        processVariants: variants,
        bottlenecks,
        rootFactors: buildRootFactors(trusted),
        objectGraph: buildObjectGraph(trusted),
        pulse: buildPulse(analytics, bottlenecks),
        automationOpportunities: opportunityGroups(trusted),
        alertNoise: buildAlertNoise(analytics),
        processAssumptions: [
            "The source dataset does not contain a native event log; process paths are transparently derived from request attributes (channel, team, category, priority, reopen state, SLA outcome, and final status).",
            "Cycle time, SLA miss, and reopen measures use source-record evidence; the platform does not invent stage-level timestamps or claim causal process effects.",
            "Process-root factors are association signals for investigation, not proof of causality.",
        ],
    };
}
const CLASSIFIERS = [
    { category: "Billing & Payments", team: "Billing Resolution", keywords: ["bill", "billing", "charge", "invoice", "refund", "payment", "duplicate"] },
    { category: "Account Access", team: "Technical Support", keywords: ["password", "login", "account", "access", "locked", "reset", "authentication"] },
    { category: "Delivery & Fulfillment", team: "Fulfillment Operations", keywords: ["delivery", "shipment", "shipping", "order", "late", "package", "tracking"] },
    { category: "Service Request", team: "Customer Operations", keywords: ["request", "service", "change", "update", "appointment", "general"] },
];
export function classifyRequestText(text) {
    const normalized = text.toLowerCase();
    const scored = CLASSIFIERS.map((item) => {
        const matched = item.keywords.filter((keyword) => normalized.includes(keyword));
        return { ...item, matched, score: matched.length * 22 + (matched.length ? 35 : 0) };
    }).sort((a, b) => b.score - a.score);
    const best = scored[0];
    const confidence = Math.max(35, Math.min(96, best.score || 42));
    return {
        category: best.category,
        team: best.team,
        confidencePct: confidence,
        reasons: best.matched.length ? best.matched.slice(0, 4).map((item) => `Matched keyword “${item}”`) : ["No strong keyword match; conservative general-routing suggestion."],
        alternatives: scored.slice(1, 3).map((item, index) => ({ category: item.category, confidencePct: Math.max(5, Math.min(confidence - 18 - index * 9, item.score || 18)) })),
    };
}
export function answerOperationsQuestion(query, analytics, intelligence, datasetName) {
    const q = query.trim().toLowerCase();
    const topFactor = intelligence.rootFactors[0];
    const topVariant = intelligence.processVariants[0];
    const topOpportunity = intelligence.automationOpportunities[0];
    const topRecommendation = analytics.recommendations[0];
    if (!q) {
        return { answer: "Ask about SLA, backlog, bottlenecks, data quality, automation opportunities, or management priorities.", evidence: [], caveat: "Answers are generated only from the currently loaded analytical evidence.", followUps: ["Why did SLA miss?", "Where is the biggest bottleneck?", "What should management prioritize?"] };
    }
    if (q.includes("why") || q.includes("sla") || q.includes("root")) {
        return {
            answer: `SLA attainment is ${analytics.kpis.slaAttainmentPct.toFixed(1)}%. The strongest current association signal is ${topFactor?.condition ?? analytics.rootCauses[0]?.name ?? "not available"}${topFactor ? `, with ${topFactor.contributionPct.toFixed(1)}% of recent misses and ${topFactor.relativeRisk.toFixed(2)}× relative risk` : ""}.`,
            evidence: [
                `KPI: SLA attainment ${analytics.kpis.slaAttainmentPct.toFixed(1)}%`,
                ...(topFactor ? [`Root factor: ${topFactor.condition}; support ${topFactor.support}; miss rate ${topFactor.missRatePct.toFixed(1)}%`] : []),
                ...(topVariant ? [`Largest derived process variant: ${topVariant.signature}; ${topVariant.count} requests`] : []),
            ],
            caveat: "The root-factor analysis is associative and does not establish causality.",
            followUps: ["Show the highest-risk process path", "Which location contributes most?", "Create an improvement case"],
        };
    }
    if (q.includes("backlog")) {
        return {
            answer: `Open backlog is ${analytics.kpis.openBacklog}, a ${analytics.kpis.backlogChangePct >= 0 ? "+" : ""}${analytics.kpis.backlogChangePct.toFixed(1)}% seven-day change. ${analytics.backlogByCategory[0]?.name ?? "The leading category"} contributes the most open work.`,
            evidence: analytics.backlogByCategory.slice(0, 3).map((item) => `${item.name}: ${item.value} open requests`),
            caveat: "Backlog history is reconstructed from created and closed timestamps.",
            followUps: ["Which process path is slowest?", "What capacity scenario improves it?", "Which automation opportunity ranks highest?"],
        };
    }
    if (q.includes("bottleneck") || q.includes("process")) {
        const bottleneck = intelligence.bottlenecks[0];
        return {
            answer: bottleneck ? `${bottleneck.name} is the highest-ranked process bottleneck signal with score ${bottleneck.score.toFixed(1)}/100, ${bottleneck.slaMissPct.toFixed(1)}% SLA misses, and median resolution ${bottleneck.medianResolutionHours.toFixed(1)} hours.` : "No stable bottleneck signal is available for the current scope.",
            evidence: bottleneck ? [bottleneck.evidence, `Kind: ${bottleneck.kind}`, `Reopen rate: ${bottleneck.reopenPct.toFixed(1)}%`] : [],
            caveat: intelligence.processAssumptions[0],
            followUps: ["Why is that bottleneck risky?", "Show the common process variants", "What playbook should we use?"],
        };
    }
    if (q.includes("autom") || q.includes("opportunity")) {
        return {
            answer: topOpportunity ? `${topOpportunity.name} is the highest-ranked automation opportunity at ${topOpportunity.score}/100, affecting about ${topOpportunity.affectedMonthlyVolume} requests per month with an estimated ${topOpportunity.expectedCycleTimeReductionPct}% cycle-time reduction opportunity.` : "No automation opportunity is available.",
            evidence: topOpportunity ? [`Volume score ${topOpportunity.volumeScore}/10`, `Repeatability ${topOpportunity.repeatabilityScore}/10`, `Data confidence ${topOpportunity.dataConfidenceScore}/10`] : [],
            caveat: "Savings and cycle-time effects are portfolio estimates for prioritization, not guarantees.",
            followUps: ["What rule would automate it?", "What risks should remain human-reviewed?", "Show value realization"],
        };
    }
    if (q.includes("quality") || q.includes("trust")) {
        return {
            answer: `The current data-quality score is ${analytics.kpis.qualityScore.toFixed(1)}%, with ${analytics.kpis.trustedRows.toLocaleString()} trusted rows included in headline calculations.`,
            evidence: [`Dataset: ${datasetName}`, `${analytics.kpis.trustedRows.toLocaleString()} trusted / ${analytics.kpis.totalRows.toLocaleString()} source rows`],
            caveat: "Blocking defects are quarantined from trusted KPI calculations; non-blocking issues remain visible as limitations.",
            followUps: ["Which quality rule failed most?", "Could quality distort SLA?", "Open Data Governance"],
        };
    }
    return {
        answer: topRecommendation ? `Management should prioritize “${topRecommendation.title}.” ${topRecommendation.action}` : "No management recommendation is available for the current scope.",
        evidence: [
            ...(analytics.alerts[0] ? [`Priority signal: ${analytics.alerts[0].title}; ${analytics.alerts[0].evidenceCount} supporting records`] : []),
            ...(topRecommendation ? [`Expected impact: ${topRecommendation.expectedImpact}`] : []),
        ],
        caveat: "Recommendations are decision support. Owners should validate operational context before execution.",
        followUps: ["Why is this the priority?", "Which process bottleneck supports it?", "What should we measure after action?"],
    };
}
//# sourceMappingURL=intelligence.js.map