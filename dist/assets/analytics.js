import { trustedRecords } from "./csv.js";
const DAY_MS = 86_400_000;
function validDate(value) {
    return value instanceof Date && Number.isFinite(value.getTime());
}
function startOfDay(date) {
    const copy = new Date(date);
    copy.setUTCHours(0, 0, 0, 0);
    return copy;
}
function addDays(date, days) {
    return new Date(date.getTime() + days * DAY_MS);
}
function formatDay(date) {
    return date.toISOString().slice(0, 10);
}
function shortDate(date) {
    return date.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}
function inWindow(date, start, end) {
    return validDate(date) && date >= start && date <= end;
}
function round(value, digits = 1) {
    const factor = 10 ** digits;
    return Math.round(value * factor) / factor;
}
function percentage(numerator, denominator) {
    return denominator === 0 ? 0 : (numerator / denominator) * 100;
}
function median(values) {
    if (values.length === 0)
        return 0;
    const sorted = [...values].sort((a, b) => a - b);
    const midpoint = Math.floor(sorted.length / 2);
    return sorted.length % 2 === 0 ? (sorted[midpoint - 1] + sorted[midpoint]) / 2 : sorted[midpoint];
}
function mean(values) {
    return values.length === 0 ? 0 : values.reduce((sum, value) => sum + value, 0) / values.length;
}
function pctChange(current, baseline) {
    if (baseline === 0)
        return current === 0 ? 0 : 100;
    return ((current - baseline) / Math.abs(baseline)) * 100;
}
function isClosed(record) {
    return record.status === "Closed" && validDate(record.closedAt);
}
function metSla(record) {
    return isClosed(record) && record.slaHours !== null && record.resolutionHours !== null && record.resolutionHours <= record.slaHours;
}
function backlogAt(records, when, predicate) {
    return records.filter((record) => {
        if (predicate && !predicate(record))
            return false;
        if (!validDate(record.createdAt) || record.createdAt > when)
            return false;
        return !validDate(record.closedAt) || record.closedAt > when;
    }).length;
}
function analysisDateFor(records) {
    let latest = Number.NEGATIVE_INFINITY;
    for (const record of records) {
        for (const value of [record.lastUpdatedAt, record.closedAt, record.createdAt]) {
            if (validDate(value))
                latest = Math.max(latest, value.getTime());
        }
    }
    if (!Number.isFinite(latest))
        throw new Error("No trusted records with valid timestamps are available for analysis.");
    return new Date(latest);
}
function slaRate(records) {
    const closed = records.filter(isClosed);
    return percentage(closed.filter(metSla).length, closed.length);
}
function reopenRate(records) {
    const closed = records.filter(isClosed);
    return percentage(closed.filter((record) => record.reopened).length, closed.length);
}
function satisfactionAverage(records) {
    return mean(records.map((record) => record.satisfactionScore).filter((value) => value !== null && value >= 1 && value <= 5));
}
function resolutionMedian(records) {
    return median(records.filter(isClosed).map((record) => record.resolutionHours).filter((value) => value !== null && value >= 0));
}
export function computeKpis(records, quality) {
    const trusted = trustedRecords(records, quality);
    const analysisDate = analysisDateFor(trusted);
    const currentStart = addDays(analysisDate, -27);
    const priorStart = addDays(currentStart, -28);
    const priorEnd = addDays(currentStart, -1 / 86_400);
    const weekStart = addDays(analysisDate, -6);
    const previousWeekPoint = addDays(analysisDate, -7);
    const currentClosed = trusted.filter((record) => inWindow(record.closedAt, currentStart, analysisDate));
    const priorClosed = trusted.filter((record) => inWindow(record.closedAt, priorStart, priorEnd));
    const currentCreated = trusted.filter((record) => inWindow(record.createdAt, currentStart, analysisDate));
    const priorCreated = trusted.filter((record) => inWindow(record.createdAt, priorStart, priorEnd));
    const weekCreated = trusted.filter((record) => inWindow(record.createdAt, weekStart, analysisDate));
    const weekClosed = trusted.filter((record) => inWindow(record.closedAt, weekStart, analysisDate));
    const openBacklog = backlogAt(trusted, analysisDate);
    const previousBacklog = backlogAt(trusted, previousWeekPoint);
    const currentSla = slaRate(currentClosed);
    const priorSla = slaRate(priorClosed);
    const currentResolution = resolutionMedian(currentClosed);
    const priorResolution = resolutionMedian(priorClosed);
    const currentReopen = reopenRate(currentClosed);
    const priorReopen = reopenRate(priorClosed);
    const currentSatisfaction = satisfactionAverage(currentClosed);
    const priorSatisfaction = satisfactionAverage(priorClosed);
    return {
        analysisDate,
        totalRows: records.length,
        trustedRows: trusted.length,
        openBacklog,
        backlogChangePct: round(pctChange(openBacklog, previousBacklog)),
        slaAttainmentPct: round(currentSla),
        slaChangePoints: round(currentSla - priorSla),
        medianResolutionHours: round(currentResolution),
        resolutionChangePct: round(pctChange(currentResolution, priorResolution)),
        reopenRatePct: round(currentReopen),
        reopenChangePoints: round(currentReopen - priorReopen),
        satisfaction: round(currentSatisfaction, 2),
        satisfactionChange: round(currentSatisfaction - priorSatisfaction, 2),
        newThisWeek: weekCreated.length,
        closedThisWeek: weekClosed.length,
        closureToIntakeRatio: round(weekCreated.length === 0 ? 0 : weekClosed.length / weekCreated.length, 2),
        qualityScore: quality.score,
    };
}
export function buildDailyTrend(records, quality, days = 42) {
    const trusted = trustedRecords(records, quality);
    const end = startOfDay(analysisDateFor(trusted));
    const start = addDays(end, -(days - 1));
    const points = [];
    for (let offset = 0; offset < days; offset += 1) {
        const day = addDays(start, offset);
        const next = addDays(day, 1);
        const created = trusted.filter((record) => validDate(record.createdAt) && record.createdAt >= day && record.createdAt < next).length;
        const closed = trusted.filter((record) => validDate(record.closedAt) && record.closedAt >= day && record.closedAt < next).length;
        points.push({ date: formatDay(day), label: shortDate(day), created, closed, net: created - closed });
    }
    return points;
}
function groupCount(records, key) {
    const groups = new Map();
    for (const record of records) {
        const name = key(record) || "Unassigned";
        groups.set(name, (groups.get(name) ?? 0) + 1);
    }
    return groups;
}
function toSortedMetrics(groups, limit = 12) {
    return [...groups.entries()]
        .map(([name, value]) => ({ name, value }))
        .sort((a, b) => b.value - a.value)
        .slice(0, limit);
}
export function backlogByCategory(records, quality) {
    const trusted = trustedRecords(records, quality);
    const analysisDate = analysisDateFor(trusted);
    const open = trusted.filter((record) => validDate(record.createdAt) && record.createdAt <= analysisDate && (!validDate(record.closedAt) || record.closedAt > analysisDate));
    return toSortedMetrics(groupCount(open, (record) => record.category));
}
export function slaByTeam(records, quality) {
    const trusted = trustedRecords(records, quality);
    const end = analysisDateFor(trusted);
    const start = addDays(end, -29);
    const closed = trusted.filter((record) => inWindow(record.closedAt, start, end));
    const groups = new Map();
    for (const record of closed) {
        const name = record.team || "Unassigned";
        const group = groups.get(name) ?? [];
        group.push(record);
        groups.set(name, group);
    }
    return [...groups.entries()]
        .map(([name, values]) => ({ name, value: round(slaRate(values)), secondary: values.length, count: values.length, label: `${values.length} closed` }))
        .sort((a, b) => a.value - b.value);
}
export function volumeByLocation(records, quality) {
    const trusted = trustedRecords(records, quality);
    const end = analysisDateFor(trusted);
    const start = addDays(end, -29);
    return toSortedMetrics(groupCount(trusted.filter((record) => inWindow(record.createdAt, start, end)), (record) => record.location));
}
function severityFor(change, evidence, kind) {
    const magnitude = Math.abs(change);
    if (kind === "sla") {
        if (magnitude >= 25 && evidence >= 10)
            return "Critical";
        if (magnitude >= 16 && evidence >= 8)
            return "High";
        if (magnitude >= 10 && evidence >= 5)
            return "Medium";
        return "Low";
    }
    if (kind === "volume") {
        if (magnitude >= 100 && evidence >= 25)
            return "Critical";
        if (magnitude >= 60 && evidence >= 15)
            return "High";
        if (magnitude >= 30 && evidence >= 10)
            return "Medium";
        return "Low";
    }
    if (magnitude >= 100 && evidence >= 20)
        return "Critical";
    if (magnitude >= 50 && evidence >= 12)
        return "High";
    if (magnitude >= 25 && evidence >= 8)
        return "Medium";
    return "Low";
}
function alertId(prefix, dimension, name) {
    return `${prefix}-${dimension}-${name}`.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}
export function detectAlerts(records, quality) {
    const trusted = trustedRecords(records, quality);
    const end = analysisDateFor(trusted);
    const currentStart = addDays(end, -6);
    const baselineEnd = addDays(currentStart, -1 / 86_400);
    const baselineStart = addDays(baselineEnd, -27);
    const priorWeekEnd = addDays(currentStart, -1 / 86_400);
    const priorWeekStart = addDays(priorWeekEnd, -6);
    const alerts = [];
    const dimensions = [
        { label: "Category", value: (record) => record.category },
        { label: "Team", value: (record) => record.team },
        { label: "Location", value: (record) => record.location },
    ];
    for (const dimension of dimensions) {
        const names = new Set(trusted.map(dimension.value).filter(Boolean));
        for (const name of names) {
            const matches = (record) => dimension.value(record) === name;
            const currentCreated = trusted.filter((record) => matches(record) && inWindow(record.createdAt, currentStart, end));
            const baselineCreated = trusted.filter((record) => matches(record) && inWindow(record.createdAt, baselineStart, baselineEnd));
            const baselineWeekly = baselineCreated.length / 4;
            const volumeChange = pctChange(currentCreated.length, baselineWeekly);
            if (currentCreated.length >= 7 && volumeChange >= 28) {
                const severity = severityFor(volumeChange, currentCreated.length, "volume");
                alerts.push({
                    id: alertId("volume", dimension.label, name),
                    severity,
                    type: "Volume",
                    title: `${name} request volume is above baseline`,
                    description: `${currentCreated.length} new requests arrived in the latest seven days versus a normalized weekly baseline of ${round(baselineWeekly)}.`,
                    dimension: `${dimension.label}: ${name}`,
                    currentValue: currentCreated.length,
                    baselineValue: round(baselineWeekly),
                    changePct: round(volumeChange),
                    evidenceCount: currentCreated.length,
                    recommendedAction: "Confirm whether the increase reflects demand, routing changes, or a data-capture shift; then align capacity to the verified driver.",
                });
            }
            const currentClosed = trusted.filter((record) => matches(record) && inWindow(record.closedAt, currentStart, end));
            const baselineClosed = trusted.filter((record) => matches(record) && inWindow(record.closedAt, baselineStart, baselineEnd));
            if (currentClosed.length >= 5 && baselineClosed.length >= 12) {
                const currentRate = slaRate(currentClosed);
                const baselineRate = slaRate(baselineClosed);
                const pointChange = currentRate - baselineRate;
                if (pointChange <= -9) {
                    const severity = severityFor(pointChange, currentClosed.length, "sla");
                    alerts.push({
                        id: alertId("sla", dimension.label, name),
                        severity,
                        type: "Service Level",
                        title: `${name} service-level performance deteriorated`,
                        description: `SLA attainment is ${round(currentRate)}%, down ${round(Math.abs(pointChange))} points from the prior four-week baseline.`,
                        dimension: `${dimension.label}: ${name}`,
                        currentValue: round(currentRate),
                        baselineValue: round(baselineRate),
                        changePct: round(pointChange),
                        evidenceCount: currentClosed.length,
                        recommendedAction: "Inspect the underlying missed records, route mix, and age profile; assign a recovery owner with a seven-day checkpoint.",
                    });
                }
            }
            const currentBacklog = backlogAt(trusted, end, matches);
            const previousBacklog = backlogAt(trusted, priorWeekEnd, matches);
            const olderBacklog = backlogAt(trusted, priorWeekStart, matches);
            const currentGrowth = currentBacklog - previousBacklog;
            const previousGrowth = previousBacklog - olderBacklog;
            if (currentBacklog >= 8 && currentGrowth >= 3 && currentGrowth > Math.max(1, previousGrowth * 1.35)) {
                const change = pctChange(currentBacklog, previousBacklog);
                const severity = severityFor(change, currentBacklog, "backlog");
                alerts.push({
                    id: alertId("backlog", dimension.label, name),
                    severity,
                    type: "Backlog",
                    title: `${name} backlog is growing faster`,
                    description: `Open work increased from ${previousBacklog} to ${currentBacklog} in seven days; the latest net growth is ${currentGrowth}.`,
                    dimension: `${dimension.label}: ${name}`,
                    currentValue: currentBacklog,
                    baselineValue: previousBacklog,
                    changePct: round(change),
                    evidenceCount: currentBacklog,
                    recommendedAction: "Prioritize oldest high-impact work, rebalance capacity, and monitor the closure-to-intake ratio daily until it returns above one.",
                });
            }
        }
    }
    if (quality.score < 99.5 || quality.issues.length > 0) {
        const critical = quality.issues.filter((item) => item.severity === "Critical").length;
        const high = quality.issues.filter((item) => item.severity === "High").length;
        alerts.push({
            id: "data-quality-trust-risk",
            severity: critical > 0 ? "High" : "Medium",
            type: "Data Quality",
            title: "Data defects can distort operational conclusions",
            description: `${quality.issues.length} rule failures affect ${quality.issueRowCount} rows, including ${critical} critical and ${high} high-severity issues.`,
            dimension: "Dataset",
            currentValue: quality.score,
            baselineValue: 100,
            changePct: round(quality.score - 100),
            evidenceCount: quality.issueRowCount,
            recommendedAction: "Quarantine blocking rows, repair the source-system rules, and retain the exception log with the management brief.",
        });
    }
    const severityRank = { Critical: 4, High: 3, Medium: 2, Low: 1 };
    const typeRank = { "Service Level": 5, Backlog: 4, "Data Quality": 3, Workflow: 2, Volume: 1 };
    const unique = new Map();
    for (const item of alerts)
        unique.set(item.id, item);
    const ranked = [...unique.values()].sort((a, b) => severityRank[b.severity] - severityRank[a.severity]
        || typeRank[b.type] - typeRank[a.type]
        || b.evidenceCount - a.evidenceCount
        || Math.abs(b.changePct) - Math.abs(a.changePct));
    const correlated = new Set();
    const reduced = [];
    for (const item of ranked) {
        const signature = [item.type, item.currentValue, item.baselineValue, item.changePct, item.evidenceCount].join("|");
        if (correlated.has(signature))
            continue;
        correlated.add(signature);
        reduced.push(item);
    }
    return reduced.slice(0, 10);
}
export function computeRootCauses(records, quality) {
    const trusted = trustedRecords(records, quality);
    const end = analysisDateFor(trusted);
    const start = addDays(end, -29);
    const closed = trusted.filter((record) => inWindow(record.closedAt, start, end) && isClosed(record));
    const misses = closed.filter((record) => !metSla(record));
    const overallMissRate = percentage(misses.length, closed.length);
    const dimensions = [
        { label: "Category", value: (record) => record.category },
        { label: "Team", value: (record) => record.team },
        { label: "Location", value: (record) => record.location },
        { label: "Channel", value: (record) => record.channel },
    ];
    const output = [];
    for (const dimension of dimensions) {
        const names = new Set(closed.map(dimension.value).filter(Boolean));
        for (const name of names) {
            const group = closed.filter((record) => dimension.value(record) === name);
            const groupMisses = group.filter((record) => !metSla(record));
            if (group.length < 5 || groupMisses.length === 0)
                continue;
            const missRate = percentage(groupMisses.length, group.length);
            output.push({
                dimension: dimension.label,
                name,
                missCount: groupMisses.length,
                closedCount: group.length,
                missRatePct: round(missRate),
                contributionPct: round(percentage(groupMisses.length, misses.length)),
                relativeRisk: round(overallMissRate === 0 ? 0 : missRate / overallMissRate, 2),
            });
        }
    }
    const ranked = output.sort((a, b) => b.contributionPct - a.contributionPct || b.relativeRisk - a.relativeRisk);
    const seenProfiles = new Set();
    const reduced = [];
    for (const item of ranked) {
        const signature = [item.missCount, item.closedCount, item.missRatePct, item.contributionPct, item.relativeRisk].join("|");
        if (seenProfiles.has(signature))
            continue;
        seenProfiles.add(signature);
        reduced.push(item);
    }
    return reduced.slice(0, 16);
}
export function buildRecommendations(alerts, rootCauses, quality) {
    const recommendations = [];
    const topRoot = rootCauses[0];
    for (const alert of alerts.slice(0, 5)) {
        const ownerRole = alert.type === "Data Quality" ? "Data Steward" : alert.type === "Service Level" ? "Operations Manager" : "Service Delivery Lead";
        recommendations.push({
            id: `rec-${alert.id}`,
            priority: alert.severity,
            title: alert.title.replace(/ is | are /, ": "),
            rationale: alert.description,
            action: alert.recommendedAction,
            ownerRole,
            expectedImpact: alert.type === "Data Quality" ? "Improve metric trust and reduce manual reconciliation." : "Stabilize backlog and restore service performance within one reporting cycle.",
            sourceAlertId: alert.id,
        });
    }
    if (topRoot) {
        recommendations.push({
            id: "rec-root-cause-review",
            priority: topRoot.relativeRisk >= 1.4 ? "High" : "Medium",
            title: `Target the largest verified source of SLA misses: ${topRoot.name}`,
            rationale: `${topRoot.name} contributes ${topRoot.contributionPct}% of recent misses with a ${topRoot.missRatePct}% miss rate and ${topRoot.relativeRisk}× relative risk.`,
            action: "Review the oldest missed records, routing logic, staffing coverage, and exception reasons; document one reversible intervention and its success measure.",
            ownerRole: "Operations Analyst",
            expectedImpact: "Concentrate management attention where it can remove the most misses first.",
        });
    }
    if (quality.duplicateRowCount > 0) {
        recommendations.push({
            id: "rec-duplicate-control",
            priority: "High",
            title: "Enforce request-level uniqueness before KPI publication",
            rationale: `${quality.duplicateRowCount} duplicate identifiers were detected at the stated analytical grain.`,
            action: "Add a source-system uniqueness constraint or deterministic deduplication rule, then reconcile affected records before publishing final totals.",
            ownerRole: "Data Steward",
            expectedImpact: "Prevent double counting and improve confidence in trend comparisons.",
        });
    }
    const priorityRank = { Critical: 4, High: 3, Medium: 2, Low: 1 };
    return recommendations.sort((a, b) => priorityRank[b.priority] - priorityRank[a.priority]).slice(0, 7);
}
function periodRecords(records, category, start, end) {
    return records.filter((record) => record.category === category && inWindow(record.closedAt, start, end));
}
export function evaluateInterventions(records, quality) {
    const trusted = trustedRecords(records, quality);
    const intervention = new Date("2026-07-15T00:00:00Z");
    const before = periodRecords(trusted, "Account Access", addDays(intervention, -30), addDays(intervention, -1 / 86_400));
    const after = periodRecords(trusted, "Account Access", intervention, addDays(intervention, 30));
    const beforeReopen = reopenRate(before);
    const afterReopen = reopenRate(after);
    const beforeResolution = resolutionMedian(before);
    const afterResolution = resolutionMedian(after);
    return [
        {
            id: "intervention-account-access-reopen",
            title: "Account Access knowledge workflow",
            metric: "Reopen rate",
            before: round(beforeReopen),
            after: round(afterReopen),
            change: round(afterReopen - beforeReopen),
            unit: "%",
            direction: "lower",
            status: after.length < 10 || before.length < 10 ? "Insufficient data" : afterReopen < beforeReopen ? "Improved" : "Mixed",
            description: `Compares 30-day closed-record windows before and after the July 15 workflow change (${before.length} before; ${after.length} after).`,
        },
        {
            id: "intervention-account-access-resolution",
            title: "Account Access knowledge workflow",
            metric: "Median resolution time",
            before: round(beforeResolution),
            after: round(afterResolution),
            change: round(afterResolution - beforeResolution),
            unit: " hrs",
            direction: "lower",
            status: after.length < 10 || before.length < 10 ? "Insufficient data" : afterResolution < beforeResolution ? "Improved" : "Mixed",
            description: "Uses the same before-and-after cohort to test whether faster resolution accompanied the reopen-rate change.",
        },
    ];
}
function standardDeviation(values) {
    if (values.length < 2)
        return 0;
    const average = mean(values);
    return Math.sqrt(values.reduce((sum, value) => sum + (value - average) ** 2, 0) / (values.length - 1));
}
function dailyFlowSeries(records, start, days) {
    const output = [];
    for (let offset = 0; offset < days; offset += 1) {
        const date = startOfDay(addDays(start, offset));
        const next = addDays(date, 1);
        const created = records.filter((record) => validDate(record.createdAt) && record.createdAt >= date && record.createdAt < next).length;
        const closed = records.filter((record) => validDate(record.closedAt) && record.closedAt >= date && record.closedAt < next).length;
        output.push({ date, weekday: date.getUTCDay(), created, closed, net: created - closed });
    }
    return output;
}
function weekdayMeans(series) {
    return Array.from({ length: 7 }, (_, weekday) => {
        const rows = series.filter((item) => item.weekday === weekday);
        return { created: mean(rows.map((item) => item.created)), closed: mean(rows.map((item) => item.closed)) };
    });
}
function mixConstraint(records, end) {
    const open = records.filter((record) => validDate(record.createdAt) && record.createdAt <= end && (!validDate(record.closedAt) || record.closedAt > end));
    const recentStart = addDays(end, -27);
    const closed = records.filter((record) => inWindow(record.closedAt, recentStart, end));
    if (open.length === 0 || closed.length === 0)
        return 0;
    const categories = new Set([...open.map((record) => record.category), ...closed.map((record) => record.category)]);
    let distance = 0;
    for (const category of categories) {
        const openShare = open.filter((record) => record.category === category).length / open.length;
        const closedShare = closed.filter((record) => record.category === category).length / closed.length;
        distance += Math.abs(openShare - closedShare);
    }
    return Math.min(12, (distance / 2) * 12);
}
function agingConstraint(records, end) {
    const open = records.filter((record) => validDate(record.createdAt) && record.createdAt <= end && (!validDate(record.closedAt) || record.closedAt > end));
    if (open.length === 0)
        return 0;
    const aged = open.filter((record) => validDate(record.createdAt) && end.getTime() - record.createdAt.getTime() >= 14 * DAY_MS).length;
    return Math.min(10, (aged / open.length) * 10);
}
function backtestScenarioModel(series) {
    if (series.length < 42) {
        return { horizonDays: 0, meanAbsoluteError: 0, meanBias: 0, observedDailyFlow: 0, modelVersion: "seasonal-capacity-v2" };
    }
    const train = series.slice(0, series.length - 28);
    const test = series.slice(-28);
    const means = weekdayMeans(train);
    const errors = test.map((item) => {
        const predicted = means[item.weekday].created - means[item.weekday].closed;
        return predicted - item.net;
    });
    return {
        horizonDays: test.length,
        meanAbsoluteError: round(mean(errors.map(Math.abs)), 2),
        meanBias: round(mean(errors), 2),
        observedDailyFlow: round(mean(test.map((item) => Math.abs(item.net))), 2),
        modelVersion: "seasonal-capacity-v2",
    };
}
export function runScenario(records, quality, demandChangePct, capacityChangePct, weeks = 6) {
    const trusted = trustedRecords(records, quality);
    const end = startOfDay(analysisDateFor(trusted));
    const recentStart = addDays(end, -27);
    const weeklyIntake = trusted.filter((record) => inWindow(record.createdAt, recentStart, addDays(end, 0.99999))).length / 4;
    const weeklyClosures = trusted.filter((record) => inWindow(record.closedAt, recentStart, addDays(end, 0.99999))).length / 4;
    const currentBacklog = backlogAt(trusted, addDays(end, 0.99999));
    const history = dailyFlowSeries(trusted, addDays(end, -55), 56);
    const seasonal = weekdayMeans(history);
    const backtest = backtestScenarioModel(history);
    const skillConstraintPct = round(mixConstraint(trusted, end), 1);
    const agingConstraintPct = round(agingConstraint(trusted, end), 1);
    const effectiveCapacity = (1 + capacityChangePct / 100) * (1 - skillConstraintPct / 100) * (1 - agingConstraintPct / 100);
    const projectedIntake = weeklyIntake * (1 + demandChangePct / 100);
    const projectedClosures = weeklyClosures * effectiveCapacity;
    const netStdDev = standardDeviation(history.map((item) => item.net));
    const confidenceZ = 1.28; // approximately 80% two-sided interval for a normal approximation.
    const forecast = [];
    let projected = currentBacklog;
    let baseline = currentBacklog;
    let cumulativeDays = 0;
    let weekIntake = 0;
    let weekClosed = 0;
    let baselineIntake = 0;
    let baselineClosed = 0;
    for (let day = 1; day <= weeks * 7; day += 1) {
        const future = addDays(end, day);
        const seasonalDay = seasonal[future.getUTCDay()];
        weekIntake += seasonalDay.created * (1 + demandChangePct / 100);
        weekClosed += seasonalDay.closed * effectiveCapacity;
        baselineIntake += seasonalDay.created;
        baselineClosed += seasonalDay.closed;
        cumulativeDays += 1;
        if (day % 7 !== 0)
            continue;
        projected = Math.max(0, projected + weekIntake - weekClosed);
        baseline = Math.max(0, baseline + baselineIntake - baselineClosed);
        const uncertainty = confidenceZ * netStdDev * Math.sqrt(cumulativeDays);
        forecast.push({
            week: day / 7,
            label: `Week ${day / 7}`,
            projectedBacklog: round(projected),
            baselineBacklog: round(baseline),
            lowerBacklog: round(Math.max(0, projected - uncertainty)),
            upperBacklog: round(projected + uncertainty),
        });
        weekIntake = 0;
        weekClosed = 0;
        baselineIntake = 0;
        baselineClosed = 0;
    }
    return {
        demandChangePct,
        capacityChangePct,
        currentWeeklyIntake: round(weeklyIntake),
        currentWeeklyClosures: round(weeklyClosures),
        projectedWeeklyIntake: round(projectedIntake),
        projectedWeeklyClosures: round(projectedClosures),
        forecast,
        endBacklog: round(projected),
        baselineEndBacklog: round(baseline),
        confidenceLevel: 80,
        agingConstraintPct,
        skillConstraintPct,
        backtest,
        assumptions: [
            "Day-of-week seasonality is estimated from the latest 56 trusted days.",
            `A ${agingConstraintPct.toFixed(1)}% capacity dampener represents backlog older than 14 days.`,
            `A ${skillConstraintPct.toFixed(1)}% capacity dampener represents mismatch between open-work category mix and recent closure mix.`,
            "The uncertainty band uses recent daily net-flow variability and is a planning interval, not a guarantee.",
        ],
    };
}
export function buildAnalytics(records, quality) {
    const kpis = computeKpis(records, quality);
    const alerts = detectAlerts(records, quality);
    const rootCauses = computeRootCauses(records, quality);
    return {
        kpis,
        dailyTrend: buildDailyTrend(records, quality),
        backlogByCategory: backlogByCategory(records, quality),
        slaByTeam: slaByTeam(records, quality),
        volumeByLocation: volumeByLocation(records, quality),
        alerts,
        rootCauses,
        recommendations: buildRecommendations(alerts, rootCauses, quality),
        interventions: evaluateInterventions(records, quality),
    };
}
export function groundedSummary(bundle, datasetName) {
    const { kpis, alerts, rootCauses, recommendations } = bundle;
    const topAlert = alerts[0];
    const topRoot = rootCauses[0];
    const backlogDirection = kpis.backlogChangePct > 0 ? "increased" : kpis.backlogChangePct < 0 ? "decreased" : "held steady";
    const ratioAssessment = kpis.closureToIntakeRatio >= 1 ? "kept pace with" : "did not keep pace with";
    const paragraphs = [
        `${datasetName} contains ${kpis.totalRows.toLocaleString()} source rows, of which ${kpis.trustedRows.toLocaleString()} are included in trusted KPI calculations. The data-quality score is ${kpis.qualityScore.toFixed(1)}%.`,
        `Open backlog is ${kpis.openBacklog.toLocaleString()} and has ${backlogDirection} ${Math.abs(kpis.backlogChangePct).toFixed(1)}% over seven days. Teams closed ${kpis.closedThisWeek} requests against ${kpis.newThisWeek} new requests, so completion volume ${ratioAssessment} incoming demand.`,
        `Recent SLA attainment is ${kpis.slaAttainmentPct.toFixed(1)}%, with median resolution time of ${kpis.medianResolutionHours.toFixed(1)} hours and a ${kpis.reopenRatePct.toFixed(1)}% reopen rate.`,
    ];
    if (topAlert)
        paragraphs.push(`The highest-priority signal is “${topAlert.title}.” ${topAlert.description}`);
    if (topRoot)
        paragraphs.push(`${topRoot.name} is the largest identified contributor to recent SLA misses at ${topRoot.contributionPct.toFixed(1)}% of misses and ${topRoot.relativeRisk.toFixed(2)}× relative risk.`);
    if (recommendations[0])
        paragraphs.push(`Management priority: ${recommendations[0].action}`);
    paragraphs.push("All statements are generated from the loaded dataset and the visible KPI rules; no unsupported narrative is added.");
    return paragraphs.join("\n\n");
}
//# sourceMappingURL=analytics.js.map