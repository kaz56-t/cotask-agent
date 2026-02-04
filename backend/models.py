"""Pydantic models for API requests and responses."""
from pydantic import BaseModel
from typing import Optional, List


class ChatMessageRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatMessageResponse(BaseModel):
    id: int
    session_id: str
    role: str
    content: str
    timestamp: str
    requirements_defined: Optional[bool] = False  # Whether requirements are defined
    requirements_summary: Optional[str] = None  # Requirements summary


class ChatSessionResponse(BaseModel):
    id: str
    created_at: str
    updated_at: str
    messages: List[ChatMessageResponse]


# Phase 3: Task management Pydantic models
class TaskCreate(BaseModel):
    name: str
    description: str
    model_provider: str  # "openai" or "anthropic"
    model_name: str


class TestExecuteRequest(BaseModel):
    """Request model for test execution endpoint (Phase 0)"""
    name: str = "Test Task: Generate CSV"
    description: str = "Generate a CSV file with sample data containing 10 rows with columns: id, name, email, age"
    model_provider: str = "openai"  # "openai" or "anthropic"
    model_name: str = "gpt-5-nano"


class TaskResponse(BaseModel):
    id: str
    name: str
    description: str
    model_provider: str
    model_name: str
    status: str
    created_at: str
    updated_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    error_message: Optional[str]
    artifact_path: Optional[str]
    session_id: Optional[str]
    task_type: Optional[str] = None  # Task type: code_generation, web_search, text_generation, scraping, rag, simple_text

    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    tasks: List[TaskResponse]
    total: int


class TaskLogResponse(BaseModel):
    id: int
    task_id: str
    timestamp: str
    role: str
    content: str

    class Config:
        from_attributes = True


class ArtifactResponse(BaseModel):
    name: str
    path: str
    size: int


class ArtifactsResponse(BaseModel):
    artifacts: List[ArtifactResponse]
