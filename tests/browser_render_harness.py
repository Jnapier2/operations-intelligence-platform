#!/usr/bin/env python3
"""Render the compiled browser application without external navigation.

The build environment blocks Chromium navigation by administrator policy. This
harness executes the exact compiled modules in an about:blank document, with a
memory-only localStorage and same-origin fetch responses for committed demo data.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
OUTPUT = ROOT / "reports" / "browser"
OUTPUT.mkdir(parents=True, exist_ok=True)
for stale_png in OUTPUT.glob("*.png"):
    stale_png.unlink()


def strip_module_syntax(code: str) -> str:
    code = re.sub(r"^import\s+.*?;\s*$", "", code, flags=re.MULTILINE)
    code = re.sub(r"^export\s+", "", code, flags=re.MULTILINE)
    return code


order = [
    "csv.js",
    "analytics.js",
    "intelligence.js",
    "charts.js",
    "storage.js",
    "diagnostics.js",
    "release.generated.js",
    "api.js",
    "app.js",
]
combined = "\n\n".join(strip_module_syntax((DIST / "assets" / name).read_text(encoding="utf-8")) for name in order)
css = (DIST / "styles.css").read_text(encoding="utf-8")
csv = (DIST / "data" / "service_requests_demo.csv").read_text(encoding="utf-8")
metadata = json.loads((DIST / "data" / "demo_metadata.json").read_text(encoding="utf-8"))
automation_catalog = json.loads((DIST / "data" / "automation_catalog.json").read_text(encoding="utf-8"))
playbook_catalog = json.loads((DIST / "data" / "playbook_catalog.json").read_text(encoding="utf-8"))
improvement_catalog = json.loads((DIST / "data" / "improvement_catalog.json").read_text(encoding="utf-8"))

bootstrap = f"""
(() => {{
  const store = new Map();
  const localStorageShim = {{
    getItem: key => store.has(String(key)) ? store.get(String(key)) : null,
    setItem: (key, value) => store.set(String(key), String(value)),
    removeItem: key => store.delete(String(key)),
    clear: () => store.clear(),
    key: index => [...store.keys()][index] ?? null,
    get length() {{ return store.size; }}
  }};
  Object.defineProperty(window, 'localStorage', {{ configurable: true, value: localStorageShim }});
  Object.defineProperty(navigator, 'clipboard', {{ configurable: true, value: {{ writeText: async () => undefined }} }});
  const demoCsv = {json.dumps(csv)};
  const demoMetadata = {json.dumps(metadata)};
  const automationCatalog = {json.dumps(automation_catalog)};
  const playbookCatalog = {json.dumps(playbook_catalog)};
  const improvementCatalog = {json.dumps(improvement_catalog)};
  window.fetch = async input => {{
    const url = String(input);
    if (url.includes('service_requests_demo.csv')) return new Response(demoCsv, {{ status: 200, headers: {{ 'content-type': 'text/csv' }} }});
    if (url.includes('demo_metadata.json')) return Response.json(demoMetadata, {{ status: 200 }});
    if (url.includes('automation_catalog.json')) return Response.json(automationCatalog, {{ status: 200 }});
    if (url.includes('playbook_catalog.json')) return Response.json(playbookCatalog, {{ status: 200 }});
    if (url.includes('improvement_catalog.json')) return Response.json(improvementCatalog, {{ status: 200 }});
    if (url.includes('/__diagnostics/critical')) return Response.json({{ status: 'captured' }}, {{ status: 202 }});
    if (url.includes('/api/summary')) return Response.json({{ error: 'disabled in render harness' }}, {{ status: 503 }});
    return Response.json({{ error: 'not found' }}, {{ status: 404 }});
  }};
}})();
"""

html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Operations Intelligence</title><style>{css}</style></head><body><div id="app"></div><script>{bootstrap}\n{combined}</script></body></html>"""

console_errors: list[str] = []
page_errors: list[str] = []
assertions: list[str] = []

with sync_playwright() as pw:
    launch_options = {"headless": True, "args": ["--no-sandbox"]}
    system_chromium = Path("/usr/bin/chromium")
    if system_chromium.is_file():
        launch_options["executable_path"] = str(system_chromium)
    browser = pw.chromium.launch(**launch_options)
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    page.set_content(html, wait_until="load", timeout=30_000)
    page.wait_for_selector("text=Service Operations Command Center", timeout=15_000)
    page.wait_for_selector("text=Billing & Payments service-level performance deteriorated", timeout=15_000)
    assertions.append("command center loaded")
    assert page.locator("text=Open backlog").count() >= 1
    assert page.locator("text=37").count() >= 1
    assertions.append("headline KPI rendered")
    page.screenshot(path=str(OUTPUT / "01_command_center.png"), full_page=True)

    page.locator('.nav-item[data-nav="analysis"]').click()
    page.wait_for_selector("text=SLA miss contribution")
    assertions.append("analysis lab navigation")
    page.screenshot(path=str(OUTPUT / "02_analysis_lab.png"), full_page=True)

    page.locator('.nav-item[data-nav="process"]').click()
    page.wait_for_selector("text=Common operational paths")
    page.wait_for_selector("text=Conditions associated with misses")
    assertions.append("process intelligence navigation")
    page.screenshot(path=str(OUTPUT / "03_process_intelligence.png"), full_page=True)

    page.locator('.nav-item[data-nav="automation"]').click()
    page.wait_for_selector("text=Automation rules")
    page.wait_for_selector("text=Synthetic hours saved / month")
    assertions.append("automation and improvement navigation")
    page.screenshot(path=str(OUTPUT / "04_automation_improvement.png"), full_page=True)

    page.locator('.nav-item[data-nav="analyst"]').click()
    page.wait_for_selector("text=Ask the current operation")
    page.wait_for_selector("text=Answer contract")
    assertions.append("operations analyst navigation")
    page.screenshot(path=str(OUTPUT / "05_operations_analyst.png"), full_page=True)

    page.locator('.nav-item[data-nav="workflow"]').click()
    page.wait_for_selector("text=Case register")
    assertions.append("workflow navigation")
    page.screenshot(path=str(OUTPUT / "06_action_followup.png"), full_page=True)

    page.locator('.nav-item[data-nav="governance"]').click()
    page.wait_for_selector("text=Quality dimensions and thresholds")
    assertions.append("governance navigation")
    page.screenshot(path=str(OUTPUT / "07_data_governance.png"), full_page=True)

    page.locator('.nav-item[data-nav="observability"]').click()
    page.wait_for_selector("text=Operational reliability scorecard")
    page.wait_for_selector("text=Forecast backtest")
    assertions.append("system health navigation")
    page.screenshot(path=str(OUTPUT / "08_system_health.png"), full_page=True)

    page.locator('[data-nav="overview"]').click(force=True, timeout=5_000)
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate("document.querySelector('.topbar__menu').click()")
    page.wait_for_function("document.querySelector('.app-shell')?.classList.contains('app-shell--sidebar-open')", timeout=5_000)
    assertions.append("mobile navigation opened")
    page.screenshot(path=str(OUTPUT / "09_mobile_navigation.png"), full_page=False, timeout=10_000)

    browser.close()

report = {
    "schema_version": 1,
    "passed": not console_errors and not page_errors,
    "method": "compiled-module inline render harness",
    "navigation_constraint": "Direct Chromium URL navigation was blocked by administrator policy in the build environment; the exact compiled modules were rendered in about:blank with committed demo data and a memory-only storage shim.",
    "browser": "Chromium headless",
    "viewport_desktop": "1440x1000",
    "viewport_mobile": "390x844",
    "assertions": assertions,
    "screenshots": [path.name for path in sorted(OUTPUT.glob("*.png"))],
    "console_errors": console_errors,
    "page_errors": page_errors,
    "generated_at": datetime.now(timezone.utc).isoformat(),
}
(ROOT / "reports" / "browser_smoke_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["passed"] else 1)
