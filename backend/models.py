"""Pydantic models for API requests and responses."""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from database import TaskStatus, ModelProvider


class TaskCreate(BaseModel):
    """Request model for creating a task."""
    name: str = Field(..., description="Task name")
    description: str = Field(..., description="Task description/request")
    model_provider: ModelProvider = Field(..., description="AI model provider")
    model_name: str = Field(..., description="Specific model name (e.g., 'gpt-4o', 'claude-3-5-sonnet-20241022')")


class TaskResponse(BaseModel):
    """Response model for task information."""
    id: str
    name: str
    description: str
    model_provider: ModelProvider
    model_name: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    artifact_path: Optional[str] = None

    class Config:
        from_attributes = True


class TaskLogResponse(BaseModel):
    """Response model for task log entry."""
    id: int
    task_id: str
    timestamp: datetime
    role: str
    content: str

    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    """Response model for task list."""
    tasks: List[TaskResponse]
    total: int


class TaskStatusUpdate(BaseModel):
    """Request model for updating task status."""
    status: TaskStatus
    error_message: Optional[str] = None


class ConfigResponse(BaseModel):
    """Response model for configuration."""
    max_concurrent_tasks: int
    default_model_provider: Optional[str] = None
    default_model_name: Optional[str] = None
