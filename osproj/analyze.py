"""Summarize saved experiment CSVs and plot foreground latency per run."""

from __future__ import annotations

import argparse
import csv
import json
import math
import multiprocessing
import statistics
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt


def parse_timestamp(value: str) -> datetime:
    """Parse the UTC ISO timestamps written by the benchmark."""
    return datetime.fromisoformat(value)


def percentile(values: list[float], fraction: float) -> float:
    """Return a nearest-rank percentile from non-empty measured samples."""
    if not values:
        raise ValueError("Cannot calculate a percentile without samples.")
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def load_run_samples(
    run_dir: Path,
    metadata: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[float], list[float]]:
    """Load a run's saved benchmark samples and select its valid time window."""
    csv_path = run_dir / metadata["benchmark_csv"]
    run_id = metadata["run_id"]
    background_start = metadata["background_start_utc"]
    background_end = metadata["background_end_utc"]
    start_time = parse_timestamp(background_start) if background_start else None
    end_time = parse_timestamp(background_end) if background_end else None

    all_samples: list[dict[str, Any]] = []
    selected_samples: list[dict[str, Any]] = []
    with csv_path.open("r", newline="", encoding="utf-8") as csv_file:
        for row in csv.DictReader(csv_file):
            if row["run_id"] != run_id:
                continue
            sample = {
                "timestamp": parse_timestamp(row["timestamp_utc"]),
                "elapsed_seconds": float(row["elapsed_seconds"]),
                "latency_ms": float(row["latency_ms"]),
            }
            all_samples.append(sample)
            if start_time is None:
                selected_samples.append(sample)
            elif end_time is not None and start_time <= sample["timestamp"] <= end_time:
                selected_samples.append(sample)

    if not all_samples:
        raise ValueError(f"No benchmark samples for run {run_id} in {csv_path}.")
    if not selected_samples:
        raise ValueError(
            f"No benchmark samples overlap the measured window for run {run_id}."
        )
    return (
        selected_samples,
        [sample["elapsed_seconds"] for sample in selected_samples],
        [sample["latency_ms"] for sample in selected_samples],
    )


def plot_run(
    run_id: str,
    condition: str,
    elapsed: list[float],
    latencies: list[float],
    output_path: Path,
) -> None:
    """Save one latency-over-time plot using only this run's recorded samples."""
    figure, axes = plt.subplots()
    try:
        axes.plot(elapsed, latencies, linewidth=1)
        axes.set_title(f"Foreground latency - {condition} - run {run_id}")
        axes.set_xlabel("Elapsed time (seconds)")
        axes.set_ylabel("Latency (ms)")
        axes.grid(True, alpha=0.3)
        figure.tight_layout()
        figure.savefig(output_path)
    finally:
        plt.close(figure)


def analyze(
    results_dir: Path,
    calibration_path: Path,
    output_root: Path,
) -> Path:
    """Create one analysis CSV and one plot for every completed run."""
    with calibration_path.open("r", encoding="utf-8") as calibration_file:
        calibration = json.load(calibration_file)
    baseline_median = float(calibration["median_latency_ms"])
    if baseline_median <= 0:
        raise ValueError("Calibration median latency must be positive.")

    run_metadata_files = sorted(results_dir.rglob("run_metadata_*.json"))
    completed_runs: list[tuple[Path, dict[str, Any]]] = []
    for metadata_path in run_metadata_files:
        with metadata_path.open("r", encoding="utf-8") as metadata_file:
            metadata = json.load(metadata_file)
        if metadata.get("status") == "completed":
            completed_runs.append((metadata_path.parent, metadata))
    if not completed_runs:
        raise ValueError(f"No completed experiment runs found under {results_dir}.")

    analysis_id = uuid.uuid4().hex
    analysis_dir = output_root / f"analysis_{analysis_id}"
    analysis_dir.mkdir(parents=True, exist_ok=False)
    summary_path = analysis_dir / f"summary_{analysis_id}.csv"
    fields = (
        "analysis_id",
        "run_id",
        "condition",
        "policy",
        "sample_count",
        "foreground_p50_ms",
        "foreground_p95_ms",
        "p50_slowdown_ratio",
        "p95_slowdown_ratio",
        "background_completion_seconds",
        "background_work_completed",
        "expected_background_work_units",
    )

    with summary_path.open("x", newline="", encoding="utf-8") as summary_file:
        writer = csv.DictWriter(summary_file, fieldnames=fields)
        writer.writeheader()
        for run_dir, metadata in completed_runs:
            _, elapsed, latencies = load_run_samples(run_dir, metadata)
            p50 = statistics.median(latencies)
            p95 = percentile(latencies, 0.95)
            writer.writerow(
                {
                    "analysis_id": analysis_id,
                    "run_id": metadata["run_id"],
                    "condition": metadata["condition"],
                    "policy": metadata["policy"],
                    "sample_count": len(latencies),
                    "foreground_p50_ms": f"{p50:.6f}",
                    "foreground_p95_ms": f"{p95:.6f}",
                    "p50_slowdown_ratio": f"{p50 / baseline_median:.6f}",
                    "p95_slowdown_ratio": f"{p95 / baseline_median:.6f}",
                    "background_completion_seconds": (
                        metadata["background_completion_seconds"]
                        if metadata["background_completion_seconds"] is not None
                        else ""
                    ),
                    "background_work_completed": (
                        metadata["background_work_completed"]
                        if metadata["background_work_completed"] is not None
                        else ""
                    ),
                    "expected_background_work_units": (
                        metadata["expected_background_work_units"]
                        if metadata["expected_background_work_units"] is not None
                        else ""
                    ),
                }
            )
            plot_path = analysis_dir / (
                f"latency_over_time_{metadata['run_id']}_{analysis_id}.png"
            )
            plot_run(
                metadata["run_id"],
                metadata["condition"],
                elapsed,
                latencies,
                plot_path,
            )
    return analysis_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze completed runs against a saved calibration."
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path(__file__).with_name("results"),
    )
    parser.add_argument(
        "--calibration",
        type=Path,
        required=True,
        help="Path to the calibration.json to use for normalization.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).with_name("results"),
    )
    args = parser.parse_args()
    analysis_dir = analyze(args.results_dir, args.calibration, args.output_dir)
    print(f"Saved analysis CSV and per-run plots to {analysis_dir}")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
