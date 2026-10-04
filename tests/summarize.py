#!/usr/bin/env python3
"""Combine per-model JSON reports into a concise Markdown comparison."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_reports(paths: list[Path]) -> list[dict[str, Any]]:
    reports = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema_version") != 1:
            raise ValueError(f"Unsupported report schema in {path}")
        reports.append(data)
    return reports


def markdown(reports: list[dict[str, Any]]) -> str:
    categories = sorted({category for report in reports for category in report["summary"].get("categories", {})})
    header = ["Model", "Overall", *categories, "Mean latency"]
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    for report in reports:
        summary = report["summary"]
        overall = f"{summary['passed']}/{summary['total']} ({summary['accuracy']:.1%})"
        cells = [report["label"], overall]
        for category in categories:
            item = summary.get("categories", {}).get(category)
            cells.append(f"{item['passed']}/{item['total']} ({item['accuracy']:.1%})" if item else "—")
        latency = summary.get("mean_latency_s")
        cells.append(f"{latency:.2f}s" if isinstance(latency, (int, float)) else "—")
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")

    lines.extend(["", "## Runs", ""])
    for report in reports:
        usage = [row.get("usage", {}) for row in report.get("results", [])]
        completion_tokens = sum(int(item.get("completion_tokens", 0) or 0) for item in usage)
        latencies = [row["latency_s"] for row in report.get("results", []) if "latency_s" in row]
        tps = completion_tokens / sum(latencies) if completion_tokens and sum(latencies) else None
        extra = f"; {completion_tokens} completion tokens" + (f"; {tps:.1f} generated tokens/s" if tps else "")
        lines.append(f"- **{report['label']}** — model `{report.get('model_id', 'unknown')}`, suite `{report.get('suite', '')}`, run {report.get('started_at', '')}{extra}.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path, help="Per-model JSON report files")
    parser.add_argument("--out", type=Path, help="Write Markdown here; also prints to stdout")
    args = parser.parse_args()
    try:
        text = markdown(load_reports(args.reports))
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
