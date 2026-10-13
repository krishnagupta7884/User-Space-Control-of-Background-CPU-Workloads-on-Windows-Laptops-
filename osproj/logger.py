"""Record system and background-process metrics once per second."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import multiprocessing
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import psutil


def run_logger(
    output_path: str,
    run_id: str,
    duration_seconds: float,
    sample_interval_seconds: float,
    maximum_runtime_seconds: float,
    background_pids: Sequence[int] = (),
    active_policy: str = "P0",
    controller_action: str = "",
    stop_event: Any = None,
) -> None:
    """Write CPU usage and available background-process metrics to a CSV."""
    if duration_seconds <= 0 or duration_seconds > maximum_runtime_seconds:
        raise ValueError("Logger duration must be positive and within the runtime limit.")
    if sample_interval_seconds <= 0:
        raise ValueError("sample_interval_seconds must be positive.")
    valid_run_id = all(
        character.isalnum() or character in "-_" for character in run_id
    )
    if not run_id or not valid_run_id:
        raise ValueError(
            "run_id may contain only letters, numbers, hyphens, and underscores."
        )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    processes: list[psutil.Process] = []
    for pid in background_pids:
        if pid <= 0:
            raise ValueError("Background process IDs must be positive.")
        processes.append(psutil.Process(pid))

    fields = (
        "run_id",
        "timestamp_utc",
        "elapsed_seconds",
        "cpu_total_pct",
        "background_cpu_pct",
        "background_priority",
        "active_policy",
        "controller_action",
    )
    start = time.monotonic()
    deadline = start + duration_seconds
    next_sample = start + sample_interval_seconds
    psutil.cpu_percent(interval=None)
    for process in processes:
        process.cpu_percent(interval=None)

    with output.open("x", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fields)
        writer.writeheader()
        csv_file.flush()

        while next_sample <= deadline:
            if stop_event is not None and stop_event.is_set():
                break
            remaining = next_sample - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
            if stop_event is not None and stop_event.is_set():
                break

            background_cpu: list[float] = []
            priorities: list[str] = []
            for process in processes:
                try:
                    background_cpu.append(process.cpu_percent(interval=None))
                    priorities.append(str(process.nice()))
                except psutil.Error as error:
                    logging.warning(
                        "Cannot read process %s metrics: %s", process.pid, error
                    )

            sample_time = time.monotonic()
            writer.writerow(
                {
                    "run_id": run_id,
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "elapsed_seconds": f"{sample_time - start:.9f}",
                    "cpu_total_pct": f"{psutil.cpu_percent(interval=None):.4f}",
                    "background_cpu_pct": (
                        f"{sum(background_cpu):.4f}" if background_cpu else ""
                    ),
                    "background_priority": "|".join(priorities),
                    "active_policy": active_policy,
                    "controller_action": controller_action,
                }
            )
            csv_file.flush()
            next_sample += sample_interval_seconds


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Log CPU and background-process metrics."
    )
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
    parser.add_argument("--background-pid", type=int, nargs="*", default=[])
    parser.add_argument("--policy", default="P0")
    parser.add_argument("--controller-action", default="")
    args = parser.parse_args()

    with args.config.open("r", encoding="utf-8") as config_file:
        config = json.load(config_file)
    settings = config["logger"]
    output_path = args.output_dir / f"logger_{args.run_id}.csv"
    run_logger(
        str(output_path),
        args.run_id,
        settings["duration_seconds"],
        settings["sample_interval_seconds"],
        config["run"]["maximum_runtime_seconds"],
        args.background_pid,
        args.policy,
        args.controller_action,
    )
    print(f"Saved logger samples to {output_path}")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
