#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import os
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import requests

DEFAULT_DATA_FILE = Path("data/waitlist_history.csv")
DEFAULT_REPORT_FILE = Path("reports/waitlist_report.md")
DEFAULT_CHART_FILE = Path("reports/position_over_time.svg")


@dataclass
class Entry:
    date: dt.date
    position: int


def parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def load_entries(path: Path) -> List[Entry]:
    if not path.exists():
        return []

    rows: List[Entry] = []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(Entry(date=parse_date(row["date"]), position=int(row["position"])))

    return sorted(rows, key=lambda entry: entry.date)


def save_entries(path: Path, entries: List[Entry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "position"])
        for entry in sorted(entries, key=lambda item: item.date):
            writer.writerow([entry.date.isoformat(), entry.position])


def append_entry(path: Path, entry: Entry) -> None:
    entries = load_entries(path)
    entries = [item for item in entries if item.date != entry.date]
    entries.append(entry)
    save_entries(path, entries)


def fetch_page(url: str) -> str:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.text


def extract_position(html: str) -> int:
    text = re.sub(r"\s+", " ", html)
    patterns = [
        r"(?:waiting\s*list|waitlist|position|queue|rank|puesto|posici[oó]n|lista\s*de\s*espera)[^0-9]{0,60}(\d{2,6})",
        r"(?:\#|n[úu]mero)[^0-9]{0,20}(\d{2,6})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))

    candidates = [int(value) for value in re.findall(r"\b\d{4,6}\b", text)]
    if not candidates:
        raise ValueError("No plausible waiting-list position found in page content")

    return min(candidates)


def regression(entries: List[Entry]) -> Optional[Tuple[float, float]]:
    if len(entries) < 2:
        return None

    x = [(entry.date - entries[0].date).days for entry in entries]
    y = [entry.position for entry in entries]

    x_mean = statistics.mean(x)
    y_mean = statistics.mean(y)

    denominator = sum((value - x_mean) ** 2 for value in x)
    if denominator == 0:
        return None

    slope = sum((x[idx] - x_mean) * (y[idx] - y_mean) for idx in range(len(x))) / denominator
    intercept = y_mean - slope * x_mean
    return slope, intercept


def estimate_bib_date(entries: List[Entry]) -> Optional[dt.date]:
    line = regression(entries)
    if line is None:
        return None

    slope, intercept = line
    if slope >= 0:
        return None

    day_offset = -intercept / slope
    return entries[0].date + dt.timedelta(days=round(day_offset))


def build_svg_chart(entries: List[Entry], chart_path: Path) -> None:
    chart_path.parent.mkdir(parents=True, exist_ok=True)

    width, height = 900, 420
    margin_left, margin_right, margin_top, margin_bottom = 80, 30, 30, 70
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom

    min_date = min(item.date for item in entries)
    max_date = max(item.date for item in entries)
    min_pos = min(item.position for item in entries)
    max_pos = max(item.position for item in entries)

    span_days = max((max_date - min_date).days, 1)
    span_pos = max(max_pos - min_pos, 1)

    def point(entry: Entry) -> Tuple[float, float]:
        x = margin_left + ((entry.date - min_date).days / span_days) * plot_width
        y = margin_top + ((entry.position - min_pos) / span_pos) * plot_height
        return x, y

    points = [point(entry) for entry in entries]
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)

    y_ticks = [min_pos + span_pos * ratio for ratio in [0, 0.25, 0.5, 0.75, 1]]

    chart = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="450" y="20" text-anchor="middle" font-family="Arial" font-size="18">Valencia Marathon Waitlist Position</text>',
        f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_height}" stroke="#666"/>',
        f'<line x1="{margin_left}" y1="{margin_top + plot_height}" x2="{margin_left + plot_width}" y2="{margin_top + plot_height}" stroke="#666"/>',
    ]

    for tick in y_ticks:
        y = margin_top + ((tick - min_pos) / span_pos) * plot_height
        chart.append(f'<line x1="{margin_left}" y1="{y:.1f}" x2="{margin_left + plot_width}" y2="{y:.1f}" stroke="#eee"/>')
        chart.append(f'<text x="{margin_left - 10}" y="{y + 4:.1f}" text-anchor="end" font-family="Arial" font-size="12">{int(round(tick))}</text>')

    for entry, (x, y) in zip(entries, points):
        chart.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#005bbb"/>')
        chart.append(f'<text x="{x:.1f}" y="{y - 8:.1f}" text-anchor="middle" font-family="Arial" font-size="11">{entry.position}</text>')

    chart.append(f'<polyline points="{polyline}" fill="none" stroke="#005bbb" stroke-width="2"/>')
    chart.append(f'<text x="{margin_left}" y="{height - 20}" font-family="Arial" font-size="12">{min_date.isoformat()}</text>')
    chart.append(f'<text x="{margin_left + plot_width}" y="{height - 20}" text-anchor="end" font-family="Arial" font-size="12">{max_date.isoformat()}</text>')
    chart.append('</svg>')

    chart_path.write_text("\n".join(chart), encoding="utf-8")


def write_report(entries: List[Entry], report_path: Path, chart_path: Path, marathon_date: dt.date) -> str:
    report_path.parent.mkdir(parents=True, exist_ok=True)

    current = entries[-1]
    first = entries[0]
    trend = regression(entries)
    estimate = estimate_bib_date(entries)

    lines = [
        "# Valencia Marathon Waiting List Tracker",
        "",
        f"**Current position:** {current.position}",
        f"**Last updated:** {current.date.isoformat()}",
        "",
        f"**Start point:** {first.position} on {first.date.isoformat()}",
    ]

    if trend is None:
        lines.append("**Trend:** Need at least 2 data points to calculate movement rate.")
    else:
        per_day = -trend[0]
        lines.append(f"**Trend:** ~{per_day:.2f} places gained per day")

    if estimate is None:
        lines.append("**Estimated bib offer date:** Not enough data (or trend is not improving yet)")
    else:
        remaining_days = (estimate - current.date).days
        lines.append(f"**Estimated bib offer date:** {estimate.isoformat()} ({remaining_days} days from last update)")

    days_to_race = (marathon_date - current.date).days
    lines.extend(
        [
            f"**Race day:** {marathon_date.isoformat()} ({days_to_race} days from last update)",
            "",
            "## Position over time",
            "",
            f"![Waitlist position chart]({chart_path.as_posix()})",
            "",
            "## History",
            "",
            "| Date | Position |",
            "| --- | ---: |",
        ]
    )

    for entry in entries:
        lines.append(f"| {entry.date.isoformat()} | {entry.position} |")

    content = "\n".join(lines) + "\n"
    report_path.write_text(content, encoding="utf-8")
    return content


def resolve_position(args: argparse.Namespace) -> int:
    if args.position is not None:
        return args.position

    if args.html_file:
        html = Path(args.html_file).read_text(encoding="utf-8")
        return extract_position(html)

    url = args.url or os.environ.get("TRACKING_URL")
    if not url:
        raise ValueError("A tracking URL is required (pass --url or set TRACKING_URL)")

    html = fetch_page(url)
    return extract_position(html)


def command_log(args: argparse.Namespace) -> None:
    data_file = Path(args.data_file)
    date_value = parse_date(args.date) if args.date else dt.date.today()
    position = resolve_position(args)

    append_entry(data_file, Entry(date=date_value, position=position))
    entries = load_entries(data_file)

    report = Path(args.report_file)
    chart = Path(args.chart_file)
    marathon_date = parse_date(args.marathon_date)

    build_svg_chart(entries, chart)
    content = write_report(entries, report, chart, marathon_date)

    print(f"Logged {position} for {date_value.isoformat()}")
    print(f"Updated {data_file.as_posix()}")
    print(f"Updated {report.as_posix()}")
    print()
    print(content)


def command_report(args: argparse.Namespace) -> None:
    data_file = Path(args.data_file)
    entries = load_entries(data_file)
    if not entries:
        raise ValueError(f"No history found in {data_file.as_posix()}")

    report = Path(args.report_file)
    chart = Path(args.chart_file)
    marathon_date = parse_date(args.marathon_date)

    build_svg_chart(entries, chart)
    content = write_report(entries, report, chart, marathon_date)
    print(content)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Valencia Marathon waiting-list tracker")
    parser.set_defaults(handler=None)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data-file", default=str(DEFAULT_DATA_FILE))
    common.add_argument("--report-file", default=str(DEFAULT_REPORT_FILE))
    common.add_argument("--chart-file", default=str(DEFAULT_CHART_FILE))
    common.add_argument("--marathon-date", default="2026-12-07")

    log_parser = parser.add_subparsers(dest="command")

    log = log_parser.add_parser("log", parents=[common], help="Fetch today's position and store it")
    log.add_argument("--url", help="Tracking URL (or set TRACKING_URL env var)")
    log.add_argument("--html-file", help="Read HTML content from a local file")
    log.add_argument("--position", type=int, help="Manually provide the waitlist position")
    log.add_argument("--date", help="Date for the reading (YYYY-MM-DD), defaults to today")
    log.set_defaults(handler=command_log)

    report = log_parser.add_parser("report", parents=[common], help="Regenerate report from history")
    report.set_defaults(handler=command_report)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.handler:
        parser.print_help()
        return

    args.handler(args)


if __name__ == "__main__":
    main()
