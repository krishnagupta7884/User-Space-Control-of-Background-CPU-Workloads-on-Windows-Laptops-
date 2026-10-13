"""Run a fixed amount of CPU-bound work across worker processes."""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import time
from pathlib import Path
from typing import Any


def load_config(config_path: Path) -> dict[str, Any]:
    """Read workload settings from the project JSON configuration."""
    with config_path.open("r", encoding="utf-8") as config_file:
        config = json.load(config_file)
    if not isinstance(config, dict):
        raise ValueError("The configuration file must contain a JSON object.")
    return config


def configured_worker_count(setting: Any) -> int:
    """Resolve the worker count from an integer or the logical-core setting."""
    if setting == "logical_cores":
        worker_count = os.cpu_count()
        if worker_count is None:
            raise RuntimeError("Windows did not report a logical CPU count.")
    elif isinstance(setting, int) and not isinstance(setting, bool):
        worker_count = setting
    else:
        raise ValueError("worker_count must be a positive integer or 'logical_cores'.")

    if worker_count <= 0:
        raise ValueError("worker_count must be positive.")
    return worker_count


def _work_worker(
    work_units: int,
    chunk_size: int,
    start_event: Any,
    stop_event: Any,
    completed: Any,
) -> None:
    """Perform assigned iterations, checking for stop requests between chunks."""
    while not start_event.wait(0.05):
        if stop_event.is_set():
            return

    done = 0
    while done < work_units and not stop_event.is_set():
        chunk = min(chunk_size, work_units - done)
        checksum = 0
        for value in range(chunk):
            checksum += value * 31
        done += chunk
        completed.value = done


class Workload:
    """Manage the worker processes for one fixed-work run."""

    def __init__(
        self,
        worker_count: int,
        total_work_units: int,
        chunk_size: int,
        shutdown_grace_seconds: float,
    ) -> None:
        if worker_count <= 0 or total_work_units <= 0 or chunk_size <= 0:
            raise ValueError("Worker count, total work, and chunk size must be positive.")
        if shutdown_grace_seconds <= 0:
            raise ValueError("shutdown_grace_seconds must be positive.")

        self.worker_count = worker_count
        self.total_work_units = total_work_units
        self.chunk_size = chunk_size
        self.shutdown_grace_seconds = shutdown_grace_seconds
        self._context = multiprocessing.get_context("spawn")
        self._start_event = self._context.Event()
        self._stop_event = self._context.Event()
        self._progress = [
            self._context.Value("Q", 0, lock=False) for _ in range(worker_count)
        ]
        self._processes: list[Any] = []
        self._started = False

    @property
    def completed_work_units(self) -> int:
        """Return the number of iterations reported by all workers."""
        return sum(progress.value for progress in self._progress)

    @property
    def is_running(self) -> bool:
        """Report whether at least one worker process is still running."""
        return any(process.is_alive() for process in self._processes)

    @property
    def process_ids(self) -> list[int]:
        """Return the process IDs of workers that have started."""
        return [process.pid for process in self._processes if process.pid is not None]

    def start(self, paused: bool = False) -> None:
        """Start workers, optionally waiting for release before they do work."""
        if self._started:
            raise RuntimeError("This workload has already been started.")
        base, remainder = divmod(self.total_work_units, self.worker_count)

        try:
            for index, progress in enumerate(self._progress):
                assigned_work = base + (1 if index < remainder else 0)
                process = self._context.Process(
                    target=_work_worker,
                    args=(
                        assigned_work,
                        self.chunk_size,
                        self._start_event,
                        self._stop_event,
                        progress,
                    ),
                    name=f"workload-worker-{index}",
                )
                process.start()
                self._processes.append(process)
        except BaseException:
            self.stop()
            raise

        self._started = True
        if not paused:
            self.release()

    def release(self) -> None:
        """Allow workers started in paused mode to begin their assigned work."""
        if not self._started:
            raise RuntimeError("Start the workload before releasing its workers.")
        self._start_event.set()

    def wait(self, maximum_runtime_seconds: float, poll_interval_seconds: float) -> None:
        """Wait for completion, stopping all workers if the deadline is exceeded."""
        if not self._started:
            raise RuntimeError("Start the workload before waiting for completion.")
        if maximum_runtime_seconds <= 0 or poll_interval_seconds <= 0:
            raise ValueError("Runtime and poll interval must be positive.")

        deadline = time.monotonic() + maximum_runtime_seconds
        try:
            while self.is_running:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("The workload exceeded its maximum runtime.")
                time.sleep(min(poll_interval_seconds, remaining))
            for process in self._processes:
                process.join()
            failed = [process for process in self._processes if process.exitcode != 0]
            if failed:
                raise RuntimeError(
                    f"{len(failed)} workload worker process(es) failed."
                )
            if self.completed_work_units != self.total_work_units:
                raise RuntimeError(
                    "Workers exited before completing the configured work amount."
                )
        except BaseException:
            self.stop()
            raise

    def stop(self) -> None:
        """Request a graceful stop, then terminate any worker that does not exit."""
        self._stop_event.set()
        self._start_event.set()
        for process in self._processes:
            process.join(self.shutdown_grace_seconds)
        remaining = [process for process in self._processes if process.is_alive()]
        for process in remaining:
            process.terminate()
        for process in remaining:
            process.join(self.shutdown_grace_seconds)
        if any(process.is_alive() for process in self._processes):
            raise RuntimeError("A workload worker could not be stopped.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the configured CPU workload.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).with_name("config.json"),
        help="Path to the project JSON configuration.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    run_settings = config["run"]
    settings = config["workload"]
    worker_count = configured_worker_count(settings["worker_count"])

    workload = Workload(
        worker_count,
        settings["total_work_units"],
        settings["chunk_size"],
        run_settings["shutdown_grace_seconds"],
    )
    try:
        workload.start()
        workload.wait(
            run_settings["maximum_runtime_seconds"],
            settings["progress_poll_interval_seconds"],
        )
        print(f"Completed {workload.completed_work_units} work units.")
    except KeyboardInterrupt:
        print("Stop requested; shutting down workload workers.")
    finally:
        workload.stop()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
