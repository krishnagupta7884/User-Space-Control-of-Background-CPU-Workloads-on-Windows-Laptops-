"""Run baseline, P0, and P1 conditions with isolated run outputs."""

from __future__ import annotations

import argparse
import json
import multiprocessing
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmark import run_benchmark
from logger import run_logger
from policies import PrioritySnapshot, apply_policy, restore_priorities
from workload import Workload, configured_worker_count


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def stop_child(process: Any, stop_event: Any, grace_seconds: float) -> None:
    """Request child shutdown, then terminate it if it ignores the request."""
    if process.pid is None:
        return
    if process.is_alive():
        stop_event.set()
        process.join(grace_seconds)
    if process.is_alive():
        process.terminate()
        process.join(grace_seconds)
    if process.is_alive():
        raise RuntimeError(f"Child process {process.name!r} could not be stopped.")


def run_condition(
    condition: str,
    policy: str,
    config: dict[str, Any],
    config_path: Path,
    output_root: Path,
) -> None:
    """Run one benchmark condition and persist its inputs, logs, and metadata."""
    run_id = uuid.uuid4().hex
    run_dir = output_root / f"run_{condition}_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    snapshot_path = run_dir / f"config_snapshot_{run_id}.json"
    benchmark_path = run_dir / f"benchmark_{run_id}.csv"
    logger_path = run_dir / f"logger_{run_id}.csv"
    metadata_path = run_dir / f"run_metadata_{run_id}.json"

    with snapshot_path.open("x", encoding="utf-8") as snapshot_file:
        json.dump(config, snapshot_file, indent=2)
        snapshot_file.write("\n")

    run_settings = config["run"]
    benchmark_settings = config["benchmark"]
    logger_settings = config["logger"]
    workload_settings = config["workload"]
    experiment_settings = config["experiment"]
    duration_seconds = benchmark_settings["duration_seconds"]
    maximum_runtime = run_settings["maximum_runtime_seconds"]
    grace_seconds = run_settings["shutdown_grace_seconds"]
    poll_interval = experiment_settings["monitor_poll_interval_seconds"]
    if duration_seconds <= 0 or duration_seconds > maximum_runtime:
        raise ValueError("Benchmark duration must be positive and within the runtime limit.")
    if poll_interval <= 0:
        raise ValueError("monitor_poll_interval_seconds must be positive.")
    if logger_settings["sample_interval_seconds"] <= 0:
        raise ValueError("Logger sample interval must be positive.")

    context = multiprocessing.get_context("spawn")
    stop_event = context.Event()
    benchmark_process = context.Process(
        target=run_benchmark,
        args=(
            str(benchmark_path),
            run_id,
            duration_seconds,
            benchmark_settings["sample_interval_seconds"],
            benchmark_settings["task_iterations"],
            benchmark_settings["task_modulus"],
            maximum_runtime,
            stop_event,
        ),
        name=f"benchmark-{condition}",
    )
    logger_process: Any = None

    workload: Workload | None = None
    priority_snapshot: PrioritySnapshot = []
    background_started_monotonic: float | None = None
    background_started_utc: str | None = None
    background_ended_monotonic: float | None = None
    background_ended_utc: str | None = None
    background_completion_seconds: float | None = None
    background_work_completed: int | None = None
    error_message: str | None = None
    run_status = "running"

    try:
        background_pids: list[int] = []
        if condition != "baseline":
            worker_count = configured_worker_count(workload_settings["worker_count"])
            workload = Workload(
                worker_count,
                workload_settings["total_work_units"],
                workload_settings["chunk_size"],
                grace_seconds,
            )
            workload.start(paused=True)
            background_pids = workload.process_ids
            priority_snapshot = apply_policy(policy, background_pids)
            background_started_monotonic = time.monotonic()
            background_started_utc = utc_now()
            workload.release()

        logger_process = context.Process(
            target=run_logger,
            args=(
                str(logger_path),
                run_id,
                duration_seconds,
                logger_settings["sample_interval_seconds"],
                maximum_runtime,
                background_pids,
                policy,
                "none",
                stop_event,
            ),
            name=f"logger-{condition}",
        )
        benchmark_process.start()
        logger_process.start()
        if workload is not None and not workload.is_running:
            raise RuntimeError(
                f"{condition} workload completed before benchmark sampling began."
            )
        child_deadline = time.monotonic() + maximum_runtime + grace_seconds

        while benchmark_process.is_alive():
            if time.monotonic() >= child_deadline:
                raise TimeoutError(f"{condition} benchmark exceeded its runtime limit.")
            if workload is not None and background_ended_monotonic is None:
                if not workload.is_running:
                    background_ended_monotonic = time.monotonic()
                    background_ended_utc = utc_now()
                    background_completion_seconds = (
                        background_ended_monotonic - background_started_monotonic
                    )
            benchmark_process.join(poll_interval)

        if benchmark_process.exitcode != 0:
            raise RuntimeError(
                f"{condition} benchmark exited with code {benchmark_process.exitcode}."
            )
        logger_process.join(maximum_runtime + grace_seconds)
        if logger_process.is_alive():
            raise TimeoutError(f"{condition} logger exceeded its runtime limit.")
        if logger_process.exitcode != 0:
            raise RuntimeError(
                f"{condition} logger exited with code {logger_process.exitcode}."
            )

        if workload is not None:
            if background_ended_monotonic is None:
                elapsed = time.monotonic() - background_started_monotonic
                remaining_runtime = maximum_runtime - elapsed
                if remaining_runtime <= 0:
                    raise TimeoutError(
                        f"{condition} workload exceeded its runtime limit."
                    )
                workload.wait(
                    remaining_runtime,
                    workload_settings["progress_poll_interval_seconds"],
                )
                background_ended_monotonic = time.monotonic()
                background_ended_utc = utc_now()
                background_completion_seconds = (
                    background_ended_monotonic - background_started_monotonic
                )
            else:
                workload.wait(
                    maximum_runtime,
                    workload_settings["progress_poll_interval_seconds"],
                )
            background_work_completed = workload.completed_work_units
        run_status = "completed"
    except BaseException as error:
        error_message = f"{type(error).__name__}: {error}"
        run_status = "failed"
        raise
    finally:
        try:
            stop_child(benchmark_process, stop_event, grace_seconds)
        finally:
            try:
                if logger_process is not None:
                    stop_child(logger_process, stop_event, grace_seconds)
            finally:
                try:
                    restore_priorities(priority_snapshot)
                finally:
                    try:
                        if workload is not None:
                            workload.stop()
                    finally:
                        metadata = {
                            "run_id": run_id,
                            "condition": condition,
                            "policy": policy,
                            "status": run_status,
                            "error": error_message,
                            "config_snapshot": snapshot_path.name,
                            "benchmark_csv": benchmark_path.name,
                            "logger_csv": logger_path.name,
                            "background_start_utc": background_started_utc,
                            "background_end_utc": background_ended_utc,
                            "background_completion_seconds": background_completion_seconds,
                            "background_work_completed": background_work_completed,
                            "expected_background_work_units": (
                                workload_settings["total_work_units"]
                                if workload is not None
                                else None
                            ),
                            "created_utc": utc_now(),
                            "source_config": str(config_path),
                        }
                        with metadata_path.open("x", encoding="utf-8") as metadata_file:
                            json.dump(metadata, metadata_file, indent=2)
                            metadata_file.write("\n")

    print(f"Completed {condition} run {run_id}: {run_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run baseline, uncontrolled P0, and below-normal P1 conditions."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).with_name("config.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).with_name("results"),
    )
    args = parser.parse_args()

    with args.config.open("r", encoding="utf-8") as config_file:
        config = json.load(config_file)
    experiment_settings = config["experiment"]
    cooldown = experiment_settings["cool_down_seconds"]
    if cooldown < 0:
        raise ValueError("cool_down_seconds cannot be negative.")

    conditions = (("baseline", "P0"), ("P0", "P0"), ("P1", "P1"))
    for index, (condition, policy) in enumerate(conditions):
        run_condition(condition, policy, config, args.config, args.output_dir)
        if index < len(conditions) - 1 and cooldown:
            print(f"Cooling down for {cooldown:g} seconds.")
            time.sleep(cooldown)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
