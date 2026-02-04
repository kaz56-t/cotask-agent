from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional, List
from contextlib import asynccontextmanager
import uuid
import os
from datetime import datetime
from dotenv import load_dotenv
import asyncio
from pathlib import Path
from loguru import logger
import sys

# Load .env file (fallback for local development environment)
# If env_file is specified in docker-compose.yml, environment variables are already available
load_dotenv()

# Loguru configuration
logger.remove()  # Remove default handler
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="DEBUG"
)
logger.add(
    "/app/data/app.log",
    rotation="10 MB",
    retention="7 days",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level="DEBUG"
)

from database import init_db, get_db, ChatSession, ChatMessage, Task, TaskStatus, ModelProvider, TaskLog
from agent.chat_agent import create_chat_agent
from services.chat_service import process_chat_message, create_or_get_session, invoke_chat_agent_with_langfuse
from services.task_service import run_task_background
from models import (
    ChatMessageRequest,
    ChatMessageResponse,
    ChatSessionResponse,
    TaskCreate,
    TestExecuteRequest,
    TaskResponse,
    TaskListResponse,
    TaskLogResponse,
    ArtifactResponse,
    ArtifactsResponse
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    # Initialize chat agent globally (if needed)
    try:
        # Check environment variables
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("Warning: OPENAI_API_KEY environment variable is not set.")
            print("Please check if env_file is specified in docker-compose.yml or check the .env file.")
            app.state.chat_agent = None
        else:
            app.state.chat_agent = create_chat_agent()
            print("Chat agent initialized successfully")
    except Exception as e:
        print(f"Warning: Failed to initialize chat agent: {e}")
        import traceback
        traceback.print_exc()
        app.state.chat_agent = None
    
    yield
    
    # Shutdown (if needed)
    # Add any cleanup code here if necessary


app = FastAPI(title="CoTask Agent API", version="0.1.0", lifespan=lifespan)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],  # Next.js default port and Docker internal communication
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




@app.get("/")
async def root():
    return {"message": "CoTask Agent API", "version": "0.1.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/api/chat", response_model=ChatMessageResponse)
async def chat(
    request: ChatMessageRequest,
    db: Session = Depends(get_db)
):
    """
    Phase 2: LangGraph conversation flow and DB persistence
    Receives user message, generates AI response, and saves to DB
    """
    try:
        session_id = create_or_get_session(request.session_id, db)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return process_chat_message(
        chat_agent=app.state.chat_agent,
        request_message=request.message,
        session_id=session_id,
        db=db
    )


@app.get("/api/chat/sessions/{session_id}", response_model=ChatSessionResponse)
async def get_chat_session(
    session_id: str,
    db: Session = Depends(get_db)
):
    """Get chat history for the specified session ID"""
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.timestamp).all()
    
    return ChatSessionResponse(
        id=session.id,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
        messages=[
            ChatMessageResponse(
                id=msg.id,
                session_id=msg.session_id,
                role=msg.role,
                content=msg.content,
                timestamp=msg.timestamp.isoformat()
            )
            for msg in messages
        ]
    )


@app.post("/api/chat/sessions", response_model=ChatSessionResponse)
async def create_chat_session(db: Session = Depends(get_db)):
    """Create a new chat session"""
    session_id = str(uuid.uuid4())
    session = ChatSession(id=session_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    
    return ChatSessionResponse(
        id=session.id,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
        messages=[]
    )


@app.post("/api/chat/sessions/{session_id}/execute")
async def execute_task(
    session_id: str,
    db: Session = Depends(get_db)
):
    """
    Execute task with defined requirements
    Full implementation planned for Phase 4, currently a mock
    """
    # Check session
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get chat history and check requirements
    messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.timestamp).all()
    
    # Check if requirements are defined in the last message
    last_message = messages[-1] if messages else None
    if not last_message or last_message.role != "assistant":
        raise HTTPException(status_code=400, detail="Requirements are not defined")
    
    # Return execution start message (full implementation planned for Phase 4)
    return {
        "message": "Task execution started.\n\n(Full implementation planned for Phase 4)",
        "session_id": session_id,
        "status": "executing"
    }


# Phase 3: タスク管理API
@app.post("/api/tasks", response_model=TaskResponse, status_code=201)
async def create_task(
    task_data: TaskCreate,
    db: Session = Depends(get_db)
):
    """Create a new task"""
    # Generate task ID
    task_id = str(uuid.uuid4())
    
    # Create chat session (independent chat history for each task)
    session_id = str(uuid.uuid4())
    session = ChatSession(id=session_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    
    # Create task (task_type will be set during execution)
    task = Task(
        id=task_id,
        name=task_data.name,
        description=task_data.description,
        model_provider=task_data.model_provider,
        model_name=task_data.model_name,
        status=TaskStatus.PENDING.value,
        session_id=session_id,
        task_type=None  # Will be classified during task execution
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    
    # When creating a task, AI starts requirements definition based on description
    # Use process_chat_message which will save user message and generate AI response
    try:
        process_chat_message(
            chat_agent=app.state.chat_agent,
            request_message=f"Task name: {task_data.name}\n\n{task_data.description}",
            session_id=session_id,
            db=db
        )
    except Exception as e:
        print(f"Error: Failed to generate initial requirements definition: {e}")
        import traceback
        traceback.print_exc()
        # Create task even if error occurs
        ai_message = ChatMessage(
            session_id=session_id,
            role="assistant",
            content=f"An error occurred: {str(e)}"
        )
        db.add(ai_message)
        db.commit()
    
    return TaskResponse(
        id=task.id,
        name=task.name,
        description=task.description,
        model_provider=task.model_provider,
        model_name=task.model_name,
        status=task.status if isinstance(task.status, str) else task.status.value,
        created_at=task.created_at.isoformat(),
        updated_at=task.updated_at.isoformat(),
        started_at=task.started_at.isoformat() if task.started_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
        error_message=task.error_message,
        artifact_path=task.artifact_path,
        session_id=task.session_id,
        task_type=task.task_type
    )


@app.get("/api/tasks", response_model=TaskListResponse)
async def get_tasks(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get task list"""
    query = db.query(Task)
    
    # Filter by status
    if status:
        query = query.filter(Task.status == status)
    
    # Get total count
    total = query.count()
    
    # Pagination
    tasks = query.order_by(desc(Task.created_at)).offset(skip).limit(limit).all()
    
    return TaskListResponse(
        tasks=[
            TaskResponse(
                id=task.id,
                name=task.name,
                description=task.description,
                model_provider=task.model_provider,
                model_name=task.model_name,
                status=task.status if isinstance(task.status, str) else task.status.value,
                created_at=task.created_at.isoformat(),
                updated_at=task.updated_at.isoformat(),
                started_at=task.started_at.isoformat() if task.started_at else None,
                completed_at=task.completed_at.isoformat() if task.completed_at else None,
                error_message=task.error_message,
                artifact_path=task.artifact_path,
                session_id=task.session_id,
                task_type=task.task_type
            )
            for task in tasks
        ],
        total=total
    )


@app.get("/api/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    db: Session = Depends(get_db)
):
    """Get a specific task"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return TaskResponse(
        id=task.id,
        name=task.name,
        description=task.description,
        model_provider=task.model_provider,
        model_name=task.model_name,
        status=task.status if isinstance(task.status, str) else task.status.value,
        created_at=task.created_at.isoformat(),
        updated_at=task.updated_at.isoformat(),
        started_at=task.started_at.isoformat() if task.started_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
        error_message=task.error_message,
        artifact_path=task.artifact_path,
        session_id=task.session_id,
        task_type=task.task_type
    )


@app.get("/api/tasks/{task_id}/chat", response_model=ChatSessionResponse)
async def get_task_chat(
    task_id: str,
    db: Session = Depends(get_db)
):
    """Get chat history associated with a task"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if not task.session_id:
        raise HTTPException(status_code=404, detail="Task has no associated chat session")
    
    session = db.query(ChatSession).filter(ChatSession.id == task.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == task.session_id
    ).order_by(ChatMessage.timestamp).all()
    
    return ChatSessionResponse(
        id=session.id,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
        messages=[
            ChatMessageResponse(
                id=msg.id,
                session_id=msg.session_id,
                role=msg.role,
                content=msg.content,
                timestamp=msg.timestamp.isoformat()
            )
            for msg in messages
        ]
    )


@app.post("/api/tasks/{task_id}/chat", response_model=ChatMessageResponse)
async def send_task_message(
    task_id: str,
    request: ChatMessageRequest,
    db: Session = Depends(get_db)
):
    """Send message to chat session associated with a task"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if not task.session_id:
        raise HTTPException(status_code=404, detail="Task has no associated chat session")
    
    return process_chat_message(
        chat_agent=app.state.chat_agent,
        request_message=request.message,
        session_id=task.session_id,
        db=db
    )




@app.post("/api/tasks/{task_id}/execute")
async def execute_task(
    task_id: str,
    db: Session = Depends(get_db)
):
    """Execute task (when requirements are defined)"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Error if already running or completed
    if task.status == TaskStatus.RUNNING.value:
        raise HTTPException(status_code=400, detail="Task is already running")
    if task.status == TaskStatus.COMPLETED.value:
        raise HTTPException(status_code=400, detail="Task is already completed")
    
    if not task.session_id:
        raise HTTPException(status_code=404, detail="Task has no associated chat session")
    
    # Check session
    session = db.query(ChatSession).filter(ChatSession.id == task.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get chat history and check if requirements are defined
    messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == task.session_id
    ).order_by(ChatMessage.timestamp).all()
    
    # Check if requirements are defined in the last message
    last_message = messages[-1] if messages else None
    if not last_message or last_message.role != "assistant":
        raise HTTPException(status_code=400, detail="Requirements are not defined")
    
    # Check requirements definition marker
    if "[要件確定]" not in last_message.content and "要件確定" not in last_message.content:
        raise HTTPException(status_code=400, detail="Requirements are not defined. Please define requirements in the chat.")
    
    # Update task status
    task.status = TaskStatus.RUNNING.value
    task.started_at = datetime.utcnow()
    db.commit()
    
    # Execute task in background using thread pool executor
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, run_task_background, task_id, get_db)
    
    return {
        "message": "Task execution started.",
        "task_id": task_id,
        "status": "running"
    }


@app.post("/api/tasks/test-execute", response_model=TaskResponse)
async def test_execute_task(
    request: TestExecuteRequest,
    db: Session = Depends(get_db)
):
    """
    Phase 0: Test execution endpoint - Skip requirements definition and execute task directly.
    Useful for development and debugging.
    """
    # Generate task ID
    task_id = str(uuid.uuid4())
    
    # Create task without session_id (test execution mode)
    # task_type will be classified during task execution
    task = Task(
        id=task_id,
        name=request.name,
        description=request.description,
        model_provider=request.model_provider,
        model_name=request.model_name,
        status=TaskStatus.RUNNING.value,  # Start immediately
        session_id=None,  # No chat session for test execution
        task_type=None  # Will be classified during task execution
    )
    db.add(task)
    task.started_at = datetime.utcnow()
    db.commit()
    db.refresh(task)
    
    logger.info(f"Test execution task created: {task_id} ({request.name})")
    
    # Execute task in background using thread pool executor
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, run_task_background, task_id, get_db)
    
    return TaskResponse(
        id=task.id,
        name=task.name,
        description=task.description,
        model_provider=task.model_provider,
        model_name=task.model_name,
        status=task.status,
        created_at=task.created_at.isoformat(),
        updated_at=task.updated_at.isoformat(),
        started_at=task.started_at.isoformat() if task.started_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
        error_message=task.error_message,
        artifact_path=task.artifact_path,
        session_id=task.session_id,
        task_type=task.task_type
    )


# Phase 4: Task logs and artifacts API
@app.get("/api/tasks/{task_id}/logs", response_model=List[TaskLogResponse])
async def get_task_logs(
    task_id: str,
    skip: int = 0,
    limit: int = 1000,
    db: Session = Depends(get_db)
):
    """Get task logs"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    logs = db.query(TaskLog).filter(
        TaskLog.task_id == task_id
    ).order_by(TaskLog.timestamp).offset(skip).limit(limit).all()
    
    return [
        TaskLogResponse(
            id=log.id,
            task_id=log.task_id,
            timestamp=log.timestamp.isoformat(),
            role=log.role,
            content=log.content
        )
        for log in logs
    ]


@app.get("/api/tasks/{task_id}/artifacts", response_model=ArtifactsResponse)
async def get_task_artifacts(
    task_id: str,
    db: Session = Depends(get_db)
):
    """Get task artifacts list"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    artifacts = []
    if task.artifact_path:
        artifacts_dir = Path(task.artifact_path)
        if artifacts_dir.exists():
            for file_path in artifacts_dir.iterdir():
                if file_path.is_file():
                    # Make path relative to artifacts directory
                    relative_path = file_path.relative_to(artifacts_dir)
                    artifacts.append(ArtifactResponse(
                        name=file_path.name,
                        path=str(relative_path),
                        size=file_path.stat().st_size
                    ))
    
    return ArtifactsResponse(artifacts=artifacts)


@app.get("/api/tasks/{task_id}/artifacts/{file_path:path}")
async def download_artifact(
    task_id: str,
    file_path: str,
    db: Session = Depends(get_db)
):
    """Download artifact file"""
    from fastapi.responses import FileResponse
    
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if not task.artifact_path:
        raise HTTPException(status_code=404, detail="Artifacts not found")
    
    artifacts_dir = Path(task.artifact_path)
    full_path = artifacts_dir / file_path
    
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    
    # Security check: prevent path traversal attacks
    try:
        full_path.resolve().relative_to(artifacts_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid file path")
    
    return FileResponse(
        path=str(full_path),
        filename=full_path.name,
        media_type='application/octet-stream'
    )


# Keep old endpoint for compatibility with Phase 1
@app.post("/api/chat/legacy")
async def chat_legacy(message: dict):
    """
    Simple chat endpoint for Phase 1 (kept for compatibility)
    Returns "[Template] Received" when "こんにちは" is sent from input field
    """
    user_message = message.get("message", "")
    
    # Phase 1 requirement: Return "[Template] Received" when "こんにちは" is received
    if user_message == "こんにちは":
        return {"response": "[Template] Received"}
    
    # Handle other messages as well
    return {"response": f"[Template] Received: {user_message}"}
