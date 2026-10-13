"""Run and record the fixed foreground CPU benchmark."""

from __future__ import annotations

import argparse
import csv
import json
import multiprocessing
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_config(config_path: Path) -> dict[str, Any]:
    """Read benchmark settings from the project JSON configuration."""
    with config_path.open("r", encoding="utf-8") as config_file:
        config = json.load(config_file)
    if not isinstance(config, dict):
        raise ValueError("The configuration file must contain a JSON object.")
    return config


def cpu_task(iterations: int, modulus: int) -> int:
    """Perform a repeatable integer-only task and return its final checksum."""
    checksum = 0
    for value in range(iterations):
        checksum = (checksum + value * 31) % modulus
    return checksum


def run_benchmark(
    output_path: str,
    run_id: str,
    duration_seconds: float,
    sample_interval_seconds: float,
    task_iterations: int,
    task_modulus: int,
    maximum_runtime_seconds: float,
    stop_event: Any = None,
) -> None:
    """Time repeated CPU tasks and stream their results to a new CSV file."""
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive.")
    if duration_seconds > maximum_runtime_seconds:
        raise ValueError("duration_seconds exceeds the configured maximum runtime.")
    if sample_interval_seconds <= 0 or task_iterations <= 0 or task_modulus <= 0:
        raise ValueError("Sample interval, task iterations, and modulus must be positive.")
    valid_run_id = all(
        character.isalnum() or character in "-_" for character in run_id
    )
    if not run_id or not valid_run_id:
        raise ValueError(
            "run_id may contain only letters, numbers, hyphens, and underscores."
        )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    end = start + duration_seconds
    next_sample = start
    fields = ("run_id", "timestamp_utc", "elapsed_seconds", "latency_ms")

    with output.open("x", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fields)
        writer.writeheader()
        csv_file.flush()

        while time.perf_counter() < end:
            if stop_event is not None and stop_event.is_set():
                break

            now = time.perf_counter()
            if now < next_sample:
                time.sleep(min(next_sample - now, end - now))
                continue

            task_start_ns = time.perf_counter_ns()
            cpu_task(task_iterations, task_modulus)
            latency_ns = time.perf_counter_ns() - task_start_ns
            sample_time = time.perf_counter()
            writer.writerow(
                {
                    "run_id": run_id,
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "elapsed_seconds": f"{sample_time - start:.9f}",
                    "latency_ms": f"{latency_ns / 1_000_000:.6f}",
                }
            )
            csv_file.flush()

            next_sample += sample_interval_seconds
            if next_sample < sample_time:
                next_sample = sample_time


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the foreground CPU benchmark.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).with_name("config.json"),
        help="Path to the project JSON configuration.",
    )
    parser.add_argument("--run-id", default=uuid.uuid4().hex)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).with_name("results"),
    )
    args = parser.parse_args()

    config = load_config(args.config)
    settings = config["benchmark"]
    maximum_runtime = config["run"]["maximum_runtime_seconds"]
    output_path = args.output_dir / f"benchmark_{args.run_id}.csv"
    run_benchmark(
        str(output_path),
        args.run_id,
        settings["duration_seconds"],
        settings["sample_interval_seconds"],
        settings["task_iterations"],
        settings["task_modulus"],
        maximum_runtime,
    )
    print(f"Saved benchmark samples to {output_path}")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
