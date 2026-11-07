"""Performance Intelligence and Telemetry Engine for DESK.
Tracks execution duration, CPU usage, bridge traffic, and cache efficiency
across CLI operations.
Zero external dependencies.
"""
import time
import os
import json
from typing import Dict, List, Optional, Any
from desk.profiler import TelemetryCollector, ProfileScope

class PerformanceReport:
    """Formats and exports telemetry metrics."""

    @staticmethod
    def generate_report(output_json: bool = False) -> str:
        collector = TelemetryCollector.get_instance()
        summary = collector.summary()

        if output_json:
            return json.dumps(summary, indent=2)

        lines = [
            "=" * 74,
            "DESK PERFORMANCE INTELLIGENCE REPORT",
            "=" * 74,
            f"Total Wall-Clock Time:  {summary['total_wall_ms']:.2f} ms",
            f"Total CPU Time:         {summary['total_cpu_ms']:.2f} ms",
            f"Total Bridge Calls:     {collector.bridge_calls_count}",
            f"Cache Hits / Misses:    {collector.cache_hits_count} / {collector.cache_misses_count}",
            "-" * 74,
            f"{'Operation':<36} {'Calls':<6} {'Total ms':<10} {'Avg ms':<10} {'Max ms':<10}",
            "-" * 74
        ]

        for op, data in summary["operations"].items():
            avg_ms = data["total_wall_ms"] / max(1, data["count"])
            lines.append(f"{op:<36} {data['count']:<6} {data['total_wall_ms']:<10.2f} {avg_ms:<10.2f} {data['max_wall_ms']:<10.2f}")

        lines.extend([
            "-" * 74,
            "Top Bottlenecks:",
        ])
        for idx, b in enumerate(summary["top_bottlenecks"], 1):
            lines.append(f"  {idx}. {b} ({summary['operations'][b]['total_wall_ms']:.2f} ms)")
        lines.append("=" * 74)

        return "\n".join(lines)
