"""Measure benchmark latency alone and while fixed-work workers run."""

from __future__ import annotations

import argparse
import csv
import json
import multiprocessing
import statistics
import uuid
from pathlib import Path
from typing import Any

from benchmark import run_benchmark
from workload import Workload, configured_worker_count


def median_latency(csv_path: Path) -> float:
    """Compute the median from the latencies recorded in one benchmark CSV."""
    with csv_path.open("r", newline="", encoding="utf-8") as csv_file:
        rows = csv.DictReader(csv_file)
        values = [float(row["latency_ms"]) for row in rows]
    if not values:
        raise ValueError(f"No benchmark samples were recorded in {csv_path}.")
    return statistics.median(values)


def run_benchmark_process(
    context: Any,
    csv_path: Path,
    run_id: str,
    duration_seconds: float,
    settings: dict[str, Any],
    maximum_runtime_seconds: float,
    shutdown_grace_seconds: float,
) -> None:
    """Run the foreground benchmark in its own spawned process."""
    stop_event = context.Event()
    process = context.Process(
        target=run_benchmark,
        args=(
            str(csv_path),
            run_id,
            duration_seconds,
            settings["sample_interval_seconds"],
            settings["task_iterations"],
            settings["task_modulus"],
            maximum_runtime_seconds,
            stop_event,
        ),
        name="foreground-benchmark",
    )
    process.start()
    try:
        process.join(maximum_runtime_seconds + shutdown_grace_seconds)
        if process.is_alive():
            stop_event.set()
            process.join(shutdown_grace_seconds)
            if process.is_alive():
                process.terminate()
                process.join(shutdown_grace_seconds)
            raise TimeoutError("The benchmark process exceeded its maximum runtime.")
        if process.exitcode != 0:
            raise RuntimeError(
                f"The benchmark process exited with code {process.exitcode}."
            )
    finally:
        if process.is_alive():
            stop_event.set()
            process.join(shutdown_grace_seconds)
            if process.is_alive():
                process.terminate()
                process.join(shutdown_grace_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure foreground latency alone and under background load."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).with_name("config.json"),
        help="Path to the project JSON configuration.",
    )
    args = parser.parse_args()
    project_dir = Path(__file__).resolve().parent
    with args.config.open("r", encoding="utf-8") as config_file:
        config = json.load(config_file)

    run_id = uuid.uuid4().hex
    output_dir = project_dir / "results" / f"test_{run_id}"
    output_dir.mkdir(parents=True, exist_ok=False)
    duration_seconds = config["test"]["duration_seconds"]
    maximum_runtime = config["run"]["maximum_runtime_seconds"]
    benchmark_settings = config["benchmark"]
    context = multiprocessing.get_context("spawn")

    alone_csv = output_dir / f"benchmark_alone_{run_id}.csv"
    run_benchmark_process(
        context,
        alone_csv,
        run_id,
        duration_seconds,
        benchmark_settings,
        maximum_runtime,
        config["run"]["shutdown_grace_seconds"],
    )
    alone_median = median_latency(alone_csv)

    worker_count = configured_worker_count(config["workload"]["worker_count"])

    workload = Workload(
        worker_count,
        config["workload"]["total_work_units"],
        config["workload"]["chunk_size"],
        config["run"]["shutdown_grace_seconds"],
    )
    loaded_csv = output_dir / f"benchmark_with_workload_{run_id}.csv"
    try:
        workload.start()
        run_benchmark_process(
            context,
            loaded_csv,
            run_id,
            duration_seconds,
            benchmark_settings,
            maximum_runtime,
            config["run"]["shutdown_grace_seconds"],
        )
    finally:
        workload.stop()
    loaded_median = median_latency(loaded_csv)

    print(f"Run ID: {run_id}")
    print(f"Workers: {worker_count}")
    print(f"Median latency alone: {alone_median:.6f} ms")
    print(f"Median latency with workload: {loaded_median:.6f} ms")
    print(f"Saved raw CSV logs to: {output_dir}")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
