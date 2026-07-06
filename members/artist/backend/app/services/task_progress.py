from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.services.task_events import task_events
from lamtools_core.run_event import RuntimeEventHub


class TaskStatus(str, Enum):
    IDLE = "idle"
    GENERATING = "generating"
    OPTIMIZING = "optimizing"
    PLANNING = "planning"
    ERROR = "error"


@dataclass
class TaskInfo:
    session_id: str
    status: TaskStatus
    progress: int = 0
    total: int = 0
    message: str = ""
    task_type: str = ""
    strategy: str = ""

    def to_snapshot(self) -> dict:
        return {
            "status": self.status.value,
            "progress": self.progress,
            "total": self.total,
            "message": self.message,
            "task_type": self.task_type,
            "strategy": self.strategy,
        }


class TaskProgressStore:
    """Session task status plus task_progress event publication."""

    def __init__(self, event_hub: RuntimeEventHub) -> None:
        self._event_hub = event_hub
        self._tasks: dict[str, TaskInfo] = {}

    def update_task(
        self,
        session_id: str,
        status: TaskStatus,
        progress: int = 0,
        total: int = 0,
        message: str = "",
        task_type: str = "",
        strategy: str = "",
    ) -> None:
        if status == TaskStatus.IDLE:
            self._tasks.pop(session_id, None)
        else:
            self._tasks[session_id] = TaskInfo(
                session_id=session_id,
                status=status,
                progress=progress,
                total=total,
                message=message,
                task_type=task_type,
                strategy=strategy,
            )
        self._event_hub.publish_runtime_record(
            name="task_progress",
            session_id=session_id,
            run_id=session_id,
            data={
                "type": "task_progress",
                "session_id": session_id,
                "status": status.value,
                "progress": progress,
                "total": total,
                "message": message,
                "task_type": task_type,
                "strategy": strategy,
            },
        )

    def get_task(self, session_id: str) -> TaskInfo | None:
        return self._tasks.get(session_id)

    def get_all_tasks(self) -> dict[str, dict]:
        return {session_id: task.to_snapshot() for session_id, task in self._tasks.items()}

    def cleanup_task(self, session_id: str) -> None:
        self._tasks.pop(session_id, None)
task_progress_store = TaskProgressStore(task_events.event_hub)
