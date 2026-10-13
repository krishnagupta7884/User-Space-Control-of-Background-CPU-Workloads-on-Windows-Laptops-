"""Measure the foreground benchmark baseline and save laptop calibration data."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import multiprocessing
import platform
import statistics
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import winreg

from benchmark import run_benchmark


def read_cpu_model() -> str:
    """Read the processor model from Windows system information."""
    key_path = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as cpu_key:
        cpu_model, _ = winreg.QueryValueEx(cpu_key, "ProcessorNameString")
    if not isinstance(cpu_model, str) or not cpu_model.strip():
        raise RuntimeError("Windows did not provide a processor model.")
    return cpu_model.strip()


def read_latencies(csv_path: Path, run_id: str) -> list[float]:
    """Load only valid latency samples belonging to this calibration run."""
    with csv_path.open("r", newline="", encoding="utf-8") as csv_file:
        rows = csv.DictReader(csv_file)
        values = [
            float(row["latency_ms"])
            for row in rows
            if row["run_id"] == run_id
        ]
    if not values:
        raise ValueError(f"No benchmark samples were recorded in {csv_path}.")
    return values


def calculate_statistics(latencies: list[float]) -> tuple[float, float, float]:
    """Return median, nearest-rank p95, and population coefficient of variation."""
    if not latencies or any(value <= 0 for value in latencies):
        raise ValueError("Calibration requires positive latency samples.")

    ordered = sorted(latencies)
    median = statistics.median(ordered)
    p95_index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    p95 = ordered[p95_index]
    coefficient_of_variation = statistics.pstdev(ordered) / statistics.mean(ordered)
    return median, p95, coefficient_of_variation


def stop_process(process: Any, stop_event: Any, grace_seconds: float) -> None:
    """Stop the benchmark process gracefully, then terminate it if needed."""
    if process.is_alive():
        stop_event.set()
        process.join(grace_seconds)
    if process.is_alive():
        process.terminate()
        process.join(grace_seconds)
    if process.is_alive():
        raise RuntimeError("The benchmark process could not be stopped.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a 60-second foreground-only calibration."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).with_name("config.json"),
        help="Path to the project JSON configuration.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).with_name("results"),
        help="Parent directory for this run's new calibration folder.",
    )
    args = parser.parse_args()

    with args.config.open("r", encoding="utf-8") as config_file:
        config = json.load(config_file)
    run_settings = config["run"]
    benchmark_settings = config["benchmark"]
    calibration_settings = config["calibration"]
    duration_seconds = calibration_settings["duration_seconds"]
    cv_warning_threshold = calibration_settings["cv_warning_threshold"]
    if duration_seconds != 60:
        raise ValueError("Calibration duration_seconds must be exactly 60.")
    if cv_warning_threshold <= 0:
        raise ValueError("cv_warning_threshold must be positive.")
    if duration_seconds > run_settings["maximum_runtime_seconds"]:
        raise ValueError("Calibration duration exceeds the maximum runtime.")

    run_id = uuid.uuid4().hex
    run_dir = args.output_dir / f"calibration_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    samples_path = run_dir / f"benchmark_{run_id}.csv"
    calibration_path = run_dir / "calibration.json"

    context = multiprocessing.get_context("spawn")
    stop_event = context.Event()
    process_started = False
    process = context.Process(
        target=run_benchmark,
        args=(
            str(samples_path),
            run_id,
            duration_seconds,
            benchmark_settings["sample_interval_seconds"],
            benchmark_settings["task_iterations"],
            benchmark_settings["task_modulus"],
            run_settings["maximum_runtime_seconds"],
            stop_event,
        ),
        name="calibration-benchmark",
    )
    try:
        process.start()
        process_started = True
        process.join(
            run_settings["maximum_runtime_seconds"]
            + run_settings["shutdown_grace_seconds"]
        )
        if process.is_alive():
            raise TimeoutError("The calibration benchmark exceeded its maximum runtime.")
        if process.exitcode != 0:
            raise RuntimeError(
                f"The calibration benchmark exited with code {process.exitcode}."
            )

        latencies = read_latencies(samples_path, run_id)
        median, p95, coefficient_of_variation = calculate_statistics(latencies)
        calibration = {
            "run_id": run_id,
            "duration_seconds": duration_seconds,
            "sample_count": len(latencies),
            "median_latency_ms": median,
            "p95_latency_ms": p95,
            "coefficient_of_variation": coefficient_of_variation,
            "cv_warning_threshold": cv_warning_threshold,
            "cv_is_high": coefficient_of_variation > cv_warning_threshold,
            "cpu_model": read_cpu_model(),
            "windows_version": platform.platform(),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        with calibration_path.open("x", encoding="utf-8") as json_file:
            json.dump(calibration, json_file, indent=2)
            json_file.write("\n")

        if calibration["cv_is_high"]:
            logging.warning(
                "Calibration CV %.2f%% exceeds the configured %.2f%% warning limit; "
                "consider repeating calibration under steadier conditions.",
                coefficient_of_variation * 100,
                cv_warning_threshold * 100,
            )
        print(f"Saved calibration to {calibration_path}")
        print(
            f"Median: {median:.6f} ms; p95: {p95:.6f} ms; "
            f"CV: {coefficient_of_variation:.2%}; samples: {len(latencies)}"
        )
    finally:
        if process_started:
            stop_process(
                process,
                stop_event,
                run_settings["shutdown_grace_seconds"],
            )


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
