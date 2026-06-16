from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agentmem.supersession import classify_relation


CASES = [
    (
        "NVDA Q3 guidance $32B",
        "NVDA Q3 guidance raised to $36B",
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 5, 1, tzinfo=timezone.utc),
        {"ticker": "NVDA", "metric": "guidance"},
        {"ticker": "NVDA", "metric": "guidance"},
        "SUPERSEDES",
    ),
    (
        "MSFT FY revenue guidance $300B",
        "MSFT FY revenue guidance $300B",
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 2, 1, tzinfo=timezone.utc),
        {"ticker": "MSFT", "metric": "revenue_guidance"},
        {"ticker": "MSFT", "metric": "revenue_guidance"},
        "CONFIRMS",
    ),
    (
        "AAPL gross margin 46%",
        "AAPL services revenue $26B",
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 2, 1, tzinfo=timezone.utc),
        {"ticker": "AAPL", "metric": "gross_margin"},
        {"ticker": "AAPL", "metric": "services_revenue"},
        "ADDS",
    ),
    (
        "TSLA deliveries 400k",
        "TSLA deliveries 380k",
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        {"ticker": "TSLA", "metric": "deliveries"},
        {"ticker": "TSLA", "metric": "deliveries"},
        "CONTRADICTS_SAME_TIME",
    ),
]


def main() -> None:
    true_positive = false_positive = false_negative = 0
    for old, new, old_t, new_t, old_meta, new_meta, expected in CASES:
        actual, confidence = classify_relation(
            old_content=old,
            new_content=new,
            old_event_time=old_t,
            new_event_time=new_t,
            old_meta=old_meta,
            new_meta=new_meta,
        )
        print(f"expected={expected} actual={actual} confidence={confidence:.2f}")
        if actual == "SUPERSEDES" and expected == "SUPERSEDES":
            true_positive += 1
        elif actual == "SUPERSEDES" and expected != "SUPERSEDES":
            false_positive += 1
        elif actual != "SUPERSEDES" and expected == "SUPERSEDES":
            false_negative += 1

    precision = true_positive / max(1, true_positive + false_positive)
    recall = true_positive / max(1, true_positive + false_negative)
    print(f"supersedes_precision={precision:.2f}")
    print(f"supersedes_recall={recall:.2f}")


if __name__ == "__main__":
    main()
