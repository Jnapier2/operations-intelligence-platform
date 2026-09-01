#!/usr/bin/env python3
"""Generate a deterministic synthetic service-operations dataset.

The data intentionally contains a small number of quality defects and several
operational patterns so the application can demonstrate validation, KPI logic,
anomaly detection, root-cause analysis, recommendations, and follow-up tracking.
"""
from __future__ import annotations

import csv
import json
import math
import random
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

SEED = 20260828
START = datetime(2026, 4, 27, 8, 0, tzinfo=timezone.utc)
END = datetime(2026, 8, 24, 18, 0, tzinfo=timezone.utc)

ROOT = Path(__file__).resolve().parents[1]
OUT_CSV = ROOT / "public" / "data" / "service_requests_demo.csv"
OUT_META = ROOT / "public" / "data" / "demo_metadata.json"

CATEGORIES = {
    "Account Access": ["Password reset", "Permission request", "Identity verification"],
    "Billing & Payments": ["Invoice question", "Payment failure", "Refund request"],
    "Delivery & Fulfillment": ["Late delivery", "Damaged item", "Address correction"],
    "Equipment & Maintenance": ["Device repair", "Preventive maintenance", "Replacement request"],
    "Permit & Compliance": ["Application status", "Documentation review", "Policy clarification"],
    "General Inquiry": ["Service information", "Status request", "Feedback"],
}

CATEGORY_WEIGHTS = {
    "Account Access": 0.21,
    "Billing & Payments": 0.19,
    "Delivery & Fulfillment": 0.18,
    "Equipment & Maintenance": 0.16,
    "Permit & Compliance": 0.14,
    "General Inquiry": 0.12,
}

CATEGORY_TEAM = {
    "Account Access": "Technical Support",
    "Billing & Payments": "Billing Operations",
    "Delivery & Fulfillment": "Customer Care",
    "Equipment & Maintenance": "Field Operations",
    "Permit & Compliance": "Compliance Services",
    "General Inquiry": "Customer Care",
}

LOCATIONS = ["Central Service Center", "North Service Center", "South Service Center", "West Service Center", "Remote"]
LOCATION_WEIGHTS = [0.28, 0.18, 0.22, 0.17, 0.15]
CHANNELS = ["Web", "Phone", "Email", "Mobile", "Walk-in"]
CHANNEL_WEIGHTS = [0.33, 0.23, 0.19, 0.17, 0.08]
PRIORITIES = ["Low", "Normal", "High", "Critical"]
PRIORITY_WEIGHTS = [0.16, 0.57, 0.22, 0.05]
OWNERS = {
    "Technical Support": ["A. Patel", "J. Brooks", "M. Chen", "S. Rivera"],
    "Billing Operations": ["T. Nguyen", "R. Williams", "C. Davis", "L. Moore"],
    "Customer Care": ["K. Johnson", "B. Martin", "E. Thompson", "D. Wilson"],
    "Field Operations": ["P. Garcia", "N. Lewis", "H. Clark", "V. Hall"],
    "Compliance Services": ["I. Adams", "G. Baker", "F. Wright", "O. Scott"],
}

SLA_BY_PRIORITY = {"Low": 96, "Normal": 48, "High": 16, "Critical": 4}
BASE_RESOLUTION = {
    "Account Access": 13,
    "Billing & Payments": 34,
    "Delivery & Fulfillment": 42,
    "Equipment & Maintenance": 62,
    "Permit & Compliance": 58,
    "General Inquiry": 17,
}


def weighted_choice(rng: random.Random, values: Iterable[str], weights: Iterable[float]) -> str:
    return rng.choices(list(values), weights=list(weights), k=1)[0]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def iso(dt: datetime | None) -> str:
    return "" if dt is None else dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class RequestRow:
    request_id: str
    created_at: str
    closed_at: str
    status: str
    priority: str
    category: str
    subcategory: str
    location: str
    team: str
    owner: str
    channel: str
    sla_hours: str
    resolution_hours: str
    reopened: str
    satisfaction_score: str
    last_updated_at: str
    source_system: str


def daily_volume(rng: random.Random, day: datetime) -> int:
    weekday_factor = 0.62 if day.weekday() >= 5 else 1.0
    seasonal = 1.0 + 0.08 * math.sin((day - START).days / 11)
    base = 12.4 * weekday_factor * seasonal
    return max(2, int(round(rng.gauss(base, 2.6))))


def generate() -> tuple[list[RequestRow], dict]:
    rng = random.Random(SEED)
    rows: list[RequestRow] = []
    serial = 100001
    day = START.replace(hour=0, minute=0)

    while day.date() <= END.date():
        for _ in range(daily_volume(rng, day)):
            created = day + timedelta(hours=rng.uniform(7.0, 20.5), minutes=rng.randint(0, 59))
            if created > END:
                continue

            category = weighted_choice(rng, CATEGORY_WEIGHTS.keys(), CATEGORY_WEIGHTS.values())

            # Deliberate recent demand surge concentrated in Billing/South/Mobile.
            if created >= END - timedelta(days=14) and rng.random() < 0.30:
                category = "Billing & Payments"

            subcategory = rng.choice(CATEGORIES[category])
            location = weighted_choice(rng, LOCATIONS, LOCATION_WEIGHTS)
            if created >= END - timedelta(days=14) and category == "Billing & Payments" and rng.random() < 0.58:
                location = "South Service Center"

            team = CATEGORY_TEAM[category]
            priority = weighted_choice(rng, PRIORITIES, PRIORITY_WEIGHTS)
            channel = weighted_choice(rng, CHANNELS, CHANNEL_WEIGHTS)
            owner = rng.choice(OWNERS[team])
            sla = SLA_BY_PRIORITY[priority]

            resolution_mean = BASE_RESOLUTION[category]
            priority_factor = {"Low": 1.18, "Normal": 1.0, "High": 0.67, "Critical": 0.30}[priority]
            location_factor = {
                "Central Service Center": 0.92,
                "North Service Center": 1.03,
                "South Service Center": 1.14,
                "West Service Center": 1.08,
                "Remote": 0.88,
            }[location]
            recent_factor = 1.0

            # Historical improvement following an Account Access knowledge intervention.
            if category == "Account Access" and created >= datetime(2026, 7, 15, tzinfo=timezone.utc):
                recent_factor *= 0.78

            # Recent Billing/Field capacity pressure creates current anomalies.
            if created >= END - timedelta(days=14) and category == "Billing & Payments":
                recent_factor *= 1.52
            if created >= END - timedelta(days=10) and team == "Field Operations":
                recent_factor *= 1.25

            resolution_hours = max(0.6, rng.lognormvariate(math.log(resolution_mean * priority_factor * location_factor * recent_factor), 0.46))
            age_hours = (END - created).total_seconds() / 3600

            close_probability = clamp((age_hours - resolution_hours * 0.35) / max(14.0, resolution_hours * 1.3), 0.05, 0.995)
            if created >= END - timedelta(days=7) and category == "Billing & Payments":
                close_probability *= 0.68
            is_closed = rng.random() < close_probability

            closed = created + timedelta(hours=resolution_hours) if is_closed else None
            if closed and closed > END:
                closed = None
                is_closed = False

            status = "Closed" if is_closed else rng.choices(["Open", "In Progress", "Pending Customer"], weights=[0.34, 0.48, 0.18])[0]
            actual_resolution = resolution_hours if is_closed else None

            reopen_probability = {
                "Account Access": 0.105,
                "Billing & Payments": 0.085,
                "Delivery & Fulfillment": 0.074,
                "Equipment & Maintenance": 0.092,
                "Permit & Compliance": 0.061,
                "General Inquiry": 0.048,
            }[category]
            if category == "Account Access" and created >= datetime(2026, 7, 15, tzinfo=timezone.utc):
                reopen_probability *= 0.55
            reopened = is_closed and rng.random() < reopen_probability

            satisfaction = None
            if is_closed and rng.random() < 0.76:
                penalty = 1.0 if resolution_hours > sla else 0.0
                satisfaction = int(round(clamp(rng.gauss(4.35 - penalty * 0.72 - (0.38 if reopened else 0), 0.58), 1, 5)))

            last_updated = closed or min(END, created + timedelta(hours=rng.uniform(1, max(2, min(age_hours, 72)))))

            rows.append(
                RequestRow(
                    request_id=f"SR-{serial}",
                    created_at=iso(created),
                    closed_at=iso(closed),
                    status=status,
                    priority=priority,
                    category=category,
                    subcategory=subcategory,
                    location=location,
                    team=team,
                    owner=owner,
                    channel=channel,
                    sla_hours=str(sla),
                    resolution_hours="" if actual_resolution is None else f"{actual_resolution:.2f}",
                    reopened="Yes" if reopened else "No",
                    satisfaction_score="" if satisfaction is None else str(satisfaction),
                    last_updated_at=iso(last_updated),
                    source_system=rng.choices(["Service Portal", "Contact Center", "Field App"], weights=[0.58, 0.27, 0.15])[0],
                )
            )
            serial += 1
        day += timedelta(days=1)

    # Intentionally introduce bounded defects for the governance workflow.
    row_indexes = list(range(len(rows)))
    rng.shuffle(row_indexes)
    issue_counts = {
        "missing_location": 14,
        "missing_team": 7,
        "invalid_satisfaction": 5,
        "closed_before_created": 4,
        "unknown_category": 4,
        "invalid_sla": 3,
        "duplicate_id": 8,
    }

    cursor = 0
    for i in row_indexes[cursor : cursor + issue_counts["missing_location"]]:
        rows[i].location = ""
    cursor += issue_counts["missing_location"]
    for i in row_indexes[cursor : cursor + issue_counts["missing_team"]]:
        rows[i].team = ""
    cursor += issue_counts["missing_team"]
    for i in row_indexes[cursor : cursor + issue_counts["invalid_satisfaction"]]:
        rows[i].satisfaction_score = "7"
    cursor += issue_counts["invalid_satisfaction"]
    for i in row_indexes[cursor : cursor + issue_counts["closed_before_created"]]:
        created_dt = datetime.fromisoformat(rows[i].created_at.replace("Z", "+00:00"))
        rows[i].closed_at = iso(created_dt - timedelta(hours=3))
        rows[i].resolution_hours = "-3"
        rows[i].status = "Closed"
    cursor += issue_counts["closed_before_created"]
    for i in row_indexes[cursor : cursor + issue_counts["unknown_category"]]:
        rows[i].category = "Unmapped / Legacy"
    cursor += issue_counts["unknown_category"]
    for i in row_indexes[cursor : cursor + issue_counts["invalid_sla"]]:
        rows[i].sla_hours = "0"

    duplicate_sources = rng.sample(rows, issue_counts["duplicate_id"])
    for original in duplicate_sources:
        duplicate = RequestRow(**asdict(original))
        duplicate.last_updated_at = iso(END - timedelta(hours=rng.uniform(1, 36)))
        rows.append(duplicate)

    rows.sort(key=lambda row: (row.created_at, row.request_id))
    metadata = {
        "name": "Synthetic Service Operations Demo",
        "description": "Deterministic synthetic service-request records with intentional operational patterns and bounded data-quality defects.",
        "seed": SEED,
        "analysis_date": iso(END),
        "period_start": iso(START),
        "period_end": iso(END),
        "row_count": len(rows),
        "intentional_issue_counts": issue_counts,
        "scenario_notes": [
            "Billing & Payments demand rises during the final two weeks, concentrated in the South Service Center.",
            "Account Access resolution and reopen performance improves after a July 15 knowledge intervention.",
            "Field Operations experiences a smaller recent capacity pressure signal.",
            "A bounded set of missing, invalid, unmapped, and duplicate records is included for governance demonstrations.",
        ],
        "generated_at": "2026-08-28T10:00:00Z",
        "copyright": "Copyright © 2026 Gateway Information Group LLC. All rights reserved.",
    }
    return rows, metadata


def write(rows: list[RequestRow], metadata: dict) -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(RequestRow.__annotations__.keys())
    with OUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
    OUT_META.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    generated_rows, generated_metadata = generate()
    write(generated_rows, generated_metadata)
    print(f"Generated {len(generated_rows)} rows -> {OUT_CSV}")
