"""FastAPI main application."""
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional
import uuid
import os
import asyncio
from datetime import datetime

from database import (
    get_db, init_db, Task, TaskLog, TaskStatus, ModelProvider
)
from models import (
    TaskCreate, TaskResponse, TaskListResponse, TaskStatusUpdate,
    TaskLogResponse, ConfigResponse
)
from orchestrator import orchestrator

# Initialize database
init_db()

# Create FastAPI app
app = FastAPI(
    title="CoTask Agent API",
    description="Backend API for CoTask Agent - Task Management System",
    version="0.1.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual frontend origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize on startup."""
    # Ensure artifact directories exist
    artifacts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "artifacts")
    os.makedirs(artifacts_dir, exist_ok=True)


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "CoTask Agent API", "version": "0.1.0"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/api/tasks", response_model=TaskResponse, status_code=201)
async def create_task(
    task: TaskCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Create a new task."""
    task_id = str(uuid.uuid4())
    
    # Create task record
    db_task = Task(
        id=task_id,
        name=task.name,
        description=task.description,
        model_provider=task.model_provider,
        model_name=task.model_name,
        status=TaskStatus.PENDING,
        artifact_path=orchestrator.get_artifact_path(task_id)
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    
    # Check if task can start immediately
    can_start = await orchestrator.can_start_task(task_id)
    if can_start:
        # Start task in background
        background_tasks.add_task(process_task, task_id)
    else:
        # Task will be queued (in future implementation)
        pass
    
    return TaskResponse.from_orm(db_task)


async def process_task(task_id: str):
    """Process a task (placeholder for future agent integration)."""
    db = next(get_db())
    try:
        # Mark task as running
        started = await orchestrator.start_task(task_id)
        if not started:
            # Task couldn't start, keep as pending
            return
        
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.utcnow()
            db.commit()
        
        # TODO: Here would be the AutoGen agent execution
        # For now, we'll just simulate completion
        
        # Simulate task completion (remove this when agent is integrated)
        await asyncio.sleep(1)
        
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.utcnow()
            db.commit()
        
        await orchestrator.finish_task(task_id)
    except Exception as e:
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.completed_at = datetime.utcnow()
            db.commit()
        await orchestrator.finish_task(task_id)
    finally:
        db.close()


@app.get("/api/tasks", response_model=TaskListResponse)
async def list_tasks(
    skip: int = 0,
    limit: int = 100,
    status: Optional[TaskStatus] = None,
    db: Session = Depends(get_db)
):
    """List all tasks with optional filtering."""
    query = db.query(Task)
    
    if status:
        query = query.filter(Task.status == status)
    
    total = query.count()
    tasks = query.order_by(desc(Task.created_at)).offset(skip).limit(limit).all()
    
    return TaskListResponse(
        tasks=[TaskResponse.from_orm(task) for task in tasks],
        total=total
    )


@app.get("/api/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, db: Session = Depends(get_db)):
    """Get a specific task by ID."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse.from_orm(task)


@app.patch("/api/tasks/{task_id}/status", response_model=TaskResponse)
async def update_task_status(
    task_id: str,
    status_update: TaskStatusUpdate,
    db: Session = Depends(get_db)
):
    """Update task status."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task.status = status_update.status
    if status_update.error_message:
        task.error_message = status_update.error_message
    
    if status_update.status == TaskStatus.RUNNING and not task.started_at:
        task.started_at = datetime.utcnow()
    elif status_update.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
        task.completed_at = datetime.utcnow()
    
    task.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(task)
    
    return TaskResponse.from_orm(task)


@app.delete("/api/tasks/{task_id}", status_code=204)
async def delete_task(task_id: str, db: Session = Depends(get_db)):
    """Delete a task."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    db.delete(task)
    db.commit()
    return None


@app.get("/api/tasks/{task_id}/logs", response_model=List[TaskLogResponse])
async def get_task_logs(
    task_id: str,
    skip: int = 0,
    limit: int = 1000,
    db: Session = Depends(get_db)
):
    """Get logs for a specific task."""
    # Verify task exists
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    logs = db.query(TaskLog).filter(
        TaskLog.task_id == task_id
    ).order_by(TaskLog.timestamp).offset(skip).limit(limit).all()
    
    return [TaskLogResponse.from_orm(log) for log in logs]


@app.post("/api/tasks/{task_id}/logs")
async def add_task_log(
    task_id: str,
    role: str,
    content: str,
    db: Session = Depends(get_db)
):
    """Add a log entry for a task."""
    # Verify task exists
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    log = TaskLog(
        task_id=task_id,
        role=role,
        content=content
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    
    return TaskLogResponse.from_orm(log)


@app.get("/api/tasks/{task_id}/artifacts")
async def list_task_artifacts(task_id: str):
    """List artifacts for a task."""
    # Verify task exists
    db = next(get_db())
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.close()
    
    artifact_dir = orchestrator.get_artifact_path(task_id)
    if not os.path.exists(artifact_dir):
        return {"artifacts": []}
    
    artifacts = []
    for root, dirs, files in os.walk(artifact_dir):
        for file in files:
            rel_path = os.path.relpath(os.path.join(root, file), artifact_dir)
            artifacts.append({
                "name": file,
                "path": rel_path,
                "size": os.path.getsize(os.path.join(root, file))
            })
    
    return {"artifacts": artifacts}


@app.get("/api/tasks/{task_id}/artifacts/{file_path:path}")
async def download_artifact(task_id: str, file_path: str):
    """Download a specific artifact file."""
    # Verify task exists
    db = next(get_db())
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.close()
    
    artifact_dir = orchestrator.get_artifact_path(task_id)
    full_path = os.path.join(artifact_dir, file_path)
    
    # Security check: ensure file is within artifact directory
    if not os.path.abspath(full_path).startswith(os.path.abspath(artifact_dir)):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not os.path.exists(full_path) or not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="Artifact not found")
    
    return FileResponse(
        full_path,
        filename=os.path.basename(file_path),
        media_type="application/octet-stream"
    )


@app.get("/api/config", response_model=ConfigResponse)
async def get_config():
    """Get current configuration."""
    return ConfigResponse(
        max_concurrent_tasks=orchestrator.max_concurrent_tasks,
        default_model_provider=None,
        default_model_name=None
    )


@app.patch("/api/config")
async def update_config(
    max_concurrent_tasks: Optional[int] = None
):
    """Update configuration."""
    if max_concurrent_tasks is not None:
        orchestrator.update_max_concurrent(max_concurrent_tasks)
    
    return ConfigResponse(
        max_concurrent_tasks=orchestrator.max_concurrent_tasks,
        default_model_provider=None,
        default_model_name=None
    )


@app.get("/api/stats")
async def get_stats():
    """Get system statistics."""
    db = next(get_db())
    total_tasks = db.query(Task).count()
    running_tasks = db.query(Task).filter(Task.status == TaskStatus.RUNNING).count()
    pending_tasks = db.query(Task).filter(Task.status == TaskStatus.PENDING).count()
    completed_tasks = db.query(Task).filter(Task.status == TaskStatus.COMPLETED).count()
    failed_tasks = db.query(Task).filter(Task.status == TaskStatus.FAILED).count()
    db.close()
    
    running_count = await orchestrator.get_running_count()
    queue_size = await orchestrator.get_queue_size()
    
    return {
        "total_tasks": total_tasks,
        "running_tasks": running_tasks,
        "pending_tasks": pending_tasks,
        "completed_tasks": completed_tasks,
        "failed_tasks": failed_tasks,
        "orchestrator_running": running_count,
        "queue_size": queue_size,
        "max_concurrent_tasks": orchestrator.max_concurrent_tasks
    }
