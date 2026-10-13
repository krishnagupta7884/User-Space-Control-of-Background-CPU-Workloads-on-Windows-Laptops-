"""Apply and restore the P0 and P1 background worker priorities."""

from __future__ import annotations

from typing import TypeAlias

import psutil


PrioritySnapshot: TypeAlias = list[tuple[psutil.Process, int]]


def apply_policy(policy: str, process_ids: list[int]) -> PrioritySnapshot:
    """Set every worker to normal (P0) or below-normal (P1) priority."""
    if policy not in {"P0", "P1"}:
        raise ValueError(f"Unsupported policy {policy!r}; only P0 and P1 are available.")
    if not process_ids:
        raise ValueError("At least one background worker process ID is required.")

    priority = (
        psutil.NORMAL_PRIORITY_CLASS
        if policy == "P0"
        else psutil.BELOW_NORMAL_PRIORITY_CLASS
    )
    snapshot: PrioritySnapshot = []
    try:
        for process_id in process_ids:
            process = psutil.Process(process_id)
            previous_priority = process.nice()
            snapshot.append((process, previous_priority))
            process.nice(priority)
    except BaseException:
        restore_priorities(snapshot)
        raise
    return snapshot


def restore_priorities(snapshot: PrioritySnapshot) -> None:
    """Restore each surviving worker to the priority it had before the run."""
    for process, previous_priority in snapshot:
        try:
            process.nice(previous_priority)
        except psutil.NoSuchProcess:
            # A completed worker no longer has a priority to restore.
            continue
