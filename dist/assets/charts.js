export function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
export function safeCssToken(value, fallback = "unknown") {
    const token = String(value ?? "")
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "")
        .slice(0, 48);
    return token || fallback;
}
function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
}
function points(values, width, height, padding = 10) {
    if (values.length === 0)
        return "";
    const minValue = Math.min(...values);
    const maxValue = Math.max(...values);
    const range = maxValue - minValue || 1;
    return values
        .map((value, index) => {
        const x = padding + (index / Math.max(values.length - 1, 1)) * (width - padding * 2);
        const y = padding + (1 - (value - minValue) / range) * (height - padding * 2);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
        .join(" ");
}
export function sparkline(values, direction = "neutral") {
    const width = 132;
    const height = 36;
    const last = values.at(-1) ?? 0;
    const first = values[0] ?? 0;
    const positive = last >= first;
    const state = direction === "neutral" ? "neutral" : direction === "good-up" ? (positive ? "positive" : "negative") : positive ? "negative" : "positive";
    return `<svg class="sparkline sparkline--${state}" viewBox="0 0 ${width} ${height}" role="img" aria-label="Metric trend"><polyline points="${points(values, width, height, 3)}" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}
export function lineChart(data) {
    const width = 880;
    const height = 270;
    const margin = { left: 42, right: 16, top: 18, bottom: 34 };
    const chartWidth = width - margin.left - margin.right;
    const chartHeight = height - margin.top - margin.bottom;
    const maximum = Math.max(1, ...data.flatMap((item) => [item.created, item.closed]));
    const x = (index) => margin.left + (index / Math.max(data.length - 1, 1)) * chartWidth;
    const y = (value) => margin.top + chartHeight - (value / maximum) * chartHeight;
    const created = data.map((item, index) => `${x(index).toFixed(1)},${y(item.created).toFixed(1)}`).join(" ");
    const closed = data.map((item, index) => `${x(index).toFixed(1)},${y(item.closed).toFixed(1)}`).join(" ");
    const grid = [0, 0.25, 0.5, 0.75, 1]
        .map((ratio) => {
        const yy = margin.top + chartHeight - ratio * chartHeight;
        const label = Math.round(maximum * ratio);
        return `<line x1="${margin.left}" y1="${yy}" x2="${width - margin.right}" y2="${yy}" class="chart-grid"/><text x="${margin.left - 9}" y="${yy + 4}" text-anchor="end" class="chart-label">${label}</text>`;
    })
        .join("");
    const labels = data
        .filter((_, index) => index % 7 === 0 || index === data.length - 1)
        .map((item) => {
        const index = data.indexOf(item);
        return `<text x="${x(index)}" y="${height - 9}" text-anchor="middle" class="chart-label">${escapeHtml(item.label)}</text>`;
    })
        .join("");
    return `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Daily incoming and closed service requests">${grid}<polyline points="${created}" fill="none" class="chart-line chart-line--primary" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><polyline points="${closed}" fill="none" class="chart-line chart-line--secondary" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>${labels}</svg>`;
}
export function horizontalBars(data, options = {}) {
    const maximum = options.maximum ?? Math.max(1, ...data.map((item) => item.value));
    return `<div class="bar-list">${data
        .map((item) => {
        const width = clamp((item.value / maximum) * 100, item.value > 0 ? 2 : 0, 100);
        const className = options.inverse ? (item.value < 75 ? "danger" : item.value < 85 ? "warning" : "positive") : "primary";
        return `<div class="bar-row"><div class="bar-row__header"><span>${escapeHtml(item.name)}</span><strong>${item.value.toLocaleString(undefined, { maximumFractionDigits: 1 })}${escapeHtml(options.suffix ?? "")}</strong></div><div class="bar-track"><span class="bar-fill bar-fill--${className}" style="width:${width}%"></span></div>${item.label ? `<small>${escapeHtml(item.label)}</small>` : ""}</div>`;
    })
        .join("")}</div>`;
}
export function gauge(score, label) {
    const normalized = clamp(score, 0, 100);
    const radius = 46;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference * (1 - normalized / 100);
    const state = normalized >= 98 ? "positive" : normalized >= 95 ? "warning" : "danger";
    return `<div class="gauge"><svg viewBox="0 0 120 120" role="img" aria-label="${escapeHtml(label)} ${normalized.toFixed(1)} percent"><circle cx="60" cy="60" r="${radius}" class="gauge__track"/><circle cx="60" cy="60" r="${radius}" class="gauge__value gauge__value--${state}" stroke-dasharray="${circumference}" stroke-dashoffset="${offset}"/><text x="60" y="58" text-anchor="middle" class="gauge__number">${normalized.toFixed(1)}</text><text x="60" y="76" text-anchor="middle" class="gauge__percent">%</text></svg><span>${escapeHtml(label)}</span></div>`;
}
export function forecastChart(data) {
    const width = 760;
    const height = 240;
    const margin = { left: 46, right: 16, top: 18, bottom: 34 };
    const chartWidth = width - margin.left - margin.right;
    const chartHeight = height - margin.top - margin.bottom;
    const maximum = Math.max(1, ...data.flatMap((item) => [item.projectedBacklog, item.baselineBacklog, item.upperBacklog]));
    const x = (index) => margin.left + (index / Math.max(data.length - 1, 1)) * chartWidth;
    const y = (value) => margin.top + chartHeight - (value / maximum) * chartHeight;
    const projected = data.map((item, index) => `${x(index).toFixed(1)},${y(item.projectedBacklog).toFixed(1)}`).join(" ");
    const baseline = data.map((item, index) => `${x(index).toFixed(1)},${y(item.baselineBacklog).toFixed(1)}`).join(" ");
    const upper = data.map((item, index) => `${x(index).toFixed(1)},${y(item.upperBacklog).toFixed(1)}`);
    const lower = [...data].reverse().map((item, reverseIndex) => {
        const index = data.length - 1 - reverseIndex;
        return `${x(index).toFixed(1)},${y(item.lowerBacklog).toFixed(1)}`;
    });
    const band = [...upper, ...lower].join(" ");
    const grid = [0, 0.5, 1]
        .map((ratio) => {
        const yy = margin.top + chartHeight - ratio * chartHeight;
        return `<line x1="${margin.left}" y1="${yy}" x2="${width - margin.right}" y2="${yy}" class="chart-grid"/><text x="${margin.left - 8}" y="${yy + 4}" text-anchor="end" class="chart-label">${Math.round(maximum * ratio)}</text>`;
    })
        .join("");
    const labels = data.map((item, index) => `<text x="${x(index)}" y="${height - 9}" text-anchor="middle" class="chart-label">${escapeHtml(item.label)}</text>`).join("");
    return `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Projected backlog scenario with uncertainty band">${grid}<polygon points="${band}" class="forecast-band"/><polyline points="${baseline}" fill="none" class="chart-line chart-line--muted" stroke-width="2.5" stroke-dasharray="7 6"/><polyline points="${projected}" fill="none" class="chart-line chart-line--primary" stroke-width="3"/>${labels}</svg>`;
}
//# sourceMappingURL=charts.js.map