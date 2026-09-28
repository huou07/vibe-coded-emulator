#!/usr/bin/env python3
"""Summarize an AN3 bounded JSONL performance trace deterministically."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Iterable


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, int((len(ordered) * percent + 99) // 100)) - 1
    return ordered[min(rank, len(ordered) - 1)]


def numbers(frames: Iterable[dict], key: str, *, positive: bool = False) -> list[float]:
    return [
        float(frame[key])
        for frame in frames
        if frame.get(key) is not None and (float(frame[key]) > 0 if positive else float(frame[key]) >= 0)
    ]


def summarize(path: Path, budget_us: float | None = None) -> dict:
    metadata: dict = {}
    frames: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("type") == "meta":
            metadata = record
        elif record.get("type") == "frame":
            frames.append(record)

    presentation_intervals = numbers(frames, "presentation_interval_ns", positive=True)
    intervals = presentation_intervals if presentation_intervals else numbers(frames, "frame_interval_ns", positive=True)
    core_intervals = numbers(frames, "frame_interval_ns", positive=True)
    if budget_us is None and metadata.get("budget_ns"):
        budget_us = float(metadata["budget_ns"]) / 1000.0
    if budget_us is None:
        # A trace without an explicit scheduler budget is still useful: use
        # the observed median cadence, never a hard-coded 60 Hz assumption.
        budget_us = statistics.median(intervals) / 1000.0 if intervals else 0.0
    budget_ns = budget_us * 1000.0

    def budget_counts(values: list[float]) -> dict[str, int]:
        return {
            "missed_deadlines": sum(value > budget_ns for value in values) if budget_ns else 0,
            "over_1_5x": sum(value > budget_ns * 1.5 for value in values) if budget_ns else 0,
            "over_2x": sum(value > budget_ns * 2 for value in values) if budget_ns else 0,
            "over_3x": sum(value > budget_ns * 3 for value in values) if budget_ns else 0,
        }

    emu = [float(frame["emu_end_ns"]) - float(frame["emu_begin_ns"])
           for frame in frames if frame.get("emu_end_ns") is not None and frame.get("emu_begin_ns") is not None]
    present = numbers(frames, "present_duration_ns")
    queue = numbers(frames, "frame_queue_depth")
    save_snapshot = numbers(frames, "save_snapshot_us")
    save_io = numbers(frames, "save_io_ms")
    rss = numbers(frames, "rss_bytes")
    audio_xruns = numbers(frames, "audio_xruns")

    result = {
        "schema": int(metadata.get("schema", 1)),
        "core_id": metadata.get("core_id", ""),
        "frames": len(frames),
        "budget_us": budget_us,
        "frame_interval_us": {
            "p50": percentile(intervals, 50) / 1000.0,
            "p95": percentile(intervals, 95) / 1000.0,
            "p99": percentile(intervals, 99) / 1000.0,
            "max": max(intervals, default=0.0) / 1000.0,
            **budget_counts(intervals),
        },
        "core_interval_us": {
            "p50": percentile(core_intervals, 50) / 1000.0,
            "p95": percentile(core_intervals, 95) / 1000.0,
            "p99": percentile(core_intervals, 99) / 1000.0,
            "max": max(core_intervals, default=0.0) / 1000.0,
        },
        "emulation_us": {
            "p50": percentile(emu, 50) / 1000.0,
            "p95": percentile(emu, 95) / 1000.0,
            "p99": percentile(emu, 99) / 1000.0,
            "max": max(emu, default=0.0) / 1000.0,
            **budget_counts(emu),
        },
        "presentation_us": {
            "p50": percentile(present, 50) / 1000.0,
            "p95": percentile(present, 95) / 1000.0,
            "p99": percentile(present, 99) / 1000.0,
            "max": max(present, default=0.0) / 1000.0,
        },
        "queue_depth": {
            "p95": percentile(queue, 95),
            "max": max(queue, default=0.0),
        },
        "dropped_frames": sum(bool(frame.get("dropped")) for frame in frames),
        "duplicated_frames": sum(bool(frame.get("duplicated")) for frame in frames),
        "audio_xruns": max(audio_xruns, default=0.0),
        "save_snapshot_us": {
            "p95": percentile(save_snapshot, 95),
            "p99": percentile(save_snapshot, 99),
        },
        "save_io_ms": {
            "p95": percentile(save_io, 95),
            "p99": percentile(save_io, 99),
        },
        "rss_bytes": {
            "start": rss[0] if rss else 0,
            "end": rss[-1] if rss else 0,
            "peak": max(rss, default=0.0),
        },
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--budget-us", type=float, default=None)
    args = parser.parse_args()
    print(json.dumps(summarize(args.trace, args.budget_us), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
