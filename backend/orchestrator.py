"""Task orchestrator for managing parallel task execution."""
import asyncio
from typing import Dict, Set
from datetime import datetime
from sqlalchemy.orm import Session
from database import Task, TaskStatus, SessionLocal
import os

# Default maximum concurrent tasks
DEFAULT_MAX_CONCURRENT_TASKS = 3


class TaskOrchestrator:
    """Manages task execution queue and parallel execution limits."""
    
    def __init__(self, max_concurrent_tasks: int = DEFAULT_MAX_CONCURRENT_TASKS):
        self.max_concurrent_tasks = max_concurrent_tasks
        self.running_tasks: Set[str] = set()
        self.task_queue: asyncio.Queue = asyncio.Queue()
        self.lock = asyncio.Lock()
    
    async def can_start_task(self, task_id: str) -> bool:
        """Check if a task can start immediately."""
        async with self.lock:
            return len(self.running_tasks) < self.max_concurrent_tasks
    
    async def start_task(self, task_id: str) -> bool:
        """Start a task if there's capacity."""
        async with self.lock:
            if len(self.running_tasks) < self.max_concurrent_tasks:
                self.running_tasks.add(task_id)
                return True
            return False
    
    async def finish_task(self, task_id: str):
        """Mark a task as finished and process next task in queue."""
        async with self.lock:
            self.running_tasks.discard(task_id)
    
    async def get_running_count(self) -> int:
        """Get current number of running tasks."""
        async with self.lock:
            return len(self.running_tasks)
    
    async def get_queue_size(self) -> int:
        """Get current queue size."""
        return self.task_queue.qsize()
    
    def update_max_concurrent(self, new_max: int):
        """Update maximum concurrent tasks."""
        self.max_concurrent_tasks = max(1, new_max)
    
    def get_artifact_path(self, task_id: str) -> str:
        """Get artifact directory path for a task."""
        base_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "artifacts")
        os.makedirs(base_dir, exist_ok=True)
        task_dir = os.path.join(base_dir, task_id)
        os.makedirs(task_dir, exist_ok=True)
        return task_dir


# Global orchestrator instance
orchestrator = TaskOrchestrator()
