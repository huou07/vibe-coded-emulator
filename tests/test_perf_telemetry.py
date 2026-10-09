# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = (ROOT / "native-offline/native-runtime/core/perf_telemetry.h").read_text(encoding="utf-8")
SUMMARIZER_PATH = ROOT / "tools/summarize_perf_trace.py"


def load_summarizer():
    spec = importlib.util.spec_from_file_location("an3_perf_summarizer", SUMMARIZER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class PerformanceTelemetryTests(unittest.TestCase):
    def test_contract_is_bounded_opt_in_and_local(self):
        self.assertIn("kTimingSamples = 512", HEADER)
        self.assertIn("kTraceSamples = 65536", HEADER)
        self.assertIn('AN3_PERF_TRACE', HEADER)
        self.assertIn('AN3_PERF_TRACE_PATH', HEADER)
        self.assertIn("std::ofstream output(path_", HEADER)
        self.assertNotIn("std::deque", HEADER)
        for field in (
            "frame_id", "core_deadline_ns", "input_sample_ns", "emu_begin_ns",
            "emu_end_ns", "video_ready_ns", "frame_queue_depth", "acquire_wait_us",
            "fence_wait_us", "gpu_submit_ns", "present_call_ns", "displayed_ns",
            "presentation_interval_ns",
            "audio_fill_frames", "audio_xruns", "save_snapshot_us", "save_io_ms",
            "rss_bytes", "dropped", "duplicated",
        ):
            self.assertIn(field, HEADER)

    def test_summarizer_uses_explicit_or_observed_budget_and_reports_tail_metrics(self):
        summarizer = load_summarizer()
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "trace.jsonl"
            records = [{"type": "meta", "schema": 1, "core_id": "gba", "budget_ns": 16_666_667}]
            for index, interval_ns in enumerate((16_000_000, 17_000_000, 40_000_000)):
                records.append({
                    "type": "frame",
                    "frame_id": index + 1,
                    "frame_interval_ns": interval_ns,
                    "emu_begin_ns": index * 1_000_000,
                    "emu_end_ns": index * 1_000_000 + 5_000_000,
                    "present_duration_ns": 1_000_000 + index * 100_000,
                    "frame_queue_depth": index,
                    "audio_xruns": index == 2,
                    "save_snapshot_us": 100 + index,
                    "save_io_ms": 2 + index,
                    "rss_bytes": 1000 + index * 10,
                    "dropped": index == 1,
                    "duplicated": index == 2,
                })
            trace.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
            summary = summarizer.summarize(trace)
        self.assertEqual(summary["core_id"], "gba")
        self.assertEqual(summary["frames"], 3)
        self.assertAlmostEqual(summary["budget_us"], 16666.667)
        self.assertEqual(summary["frame_interval_us"]["over_2x"], 1)
        self.assertEqual(summary["dropped_frames"], 1)
        self.assertEqual(summary["duplicated_frames"], 1)
        self.assertEqual(summary["audio_xruns"], 1)
        self.assertEqual(summary["rss_bytes"]["peak"], 1020)

    def test_summarizer_ignores_zero_core_interval_for_display_duplicates(self):
        summarizer = load_summarizer()
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "trace.jsonl"
            records = [
                {"type": "meta", "schema": 1, "core_id": "gba", "budget_ns": 16_666_667},
                {"type": "frame", "frame_id": 1, "frame_interval_ns": 16_000_000,
                 "presentation_interval_ns": 16_000_000, "present_duration_ns": 2_000_000,
                 "emu_begin_ns": 1, "emu_end_ns": 2},
                {"type": "frame", "frame_id": 1, "frame_interval_ns": 0,
                 "presentation_interval_ns": 16_700_000, "present_duration_ns": 0,
                 "emu_begin_ns": 0, "emu_end_ns": 0,
                 "duplicated": True},
            ]
            trace.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
            summary = summarizer.summarize(trace)
        self.assertEqual(summary["core_interval_us"]["p50"], 16000.0)
        self.assertEqual(summary["presentation_us"]["p50"], 2000.0)
        self.assertEqual(summary["duplicated_frames"], 1)


if __name__ == "__main__":
    unittest.main()
