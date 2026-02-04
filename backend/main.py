from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import desc
from pydantic import BaseModel
from typing import Optional, List
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
from chat_agent import create_chat_agent, format_messages_for_langgraph
from langchain_core.messages import HumanMessage
from langchain_core.callbacks import CallbackManager
from agents import create_workflow
from executor import RuntimeExecutor
from langfuse_config import get_langfuse_handler
from complexity_analyzer import classify_task_type

app = FastAPI(title="CoTask Agent API", version="0.1.0")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],  # Next.js default port and Docker internal communication
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Initialize database on application startup
@app.on_event("startup")
async def startup_event():
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


# Pydanticモデル
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


@app.get("/")
async def root():
    return {"message": "CoTask Agent API", "version": "0.1.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


def invoke_chat_agent_with_langfuse(chat_agent, initial_state, session_id: str):
    """Helper function to execute chat agent with Langfuse callback"""
    langfuse_handler = get_langfuse_handler(
        session_id=session_id,
        trace_name="LangGraph Chat"
    )
    config = {}
    if langfuse_handler:
        callback_manager = CallbackManager([langfuse_handler])
        config["callbacks"] = callback_manager
        # Set Langfuse trace name
        config["metadata"] = {"trace_name": "LangGraph Chat"}
        config["run_name"] = "LangGraph Chat"
    return chat_agent.invoke(initial_state, config=config if config else None)


@app.post("/api/chat", response_model=ChatMessageResponse)
async def chat(
    request: ChatMessageRequest,
    db: Session = Depends(get_db)
):
    """
    Phase 2: LangGraph conversation flow and DB persistence
    Receives user message, generates AI response, and saves to DB
    """
    # Create new session if session_id is not specified
    if not request.session_id:
        session_id = str(uuid.uuid4())
        session = ChatSession(id=session_id)
        db.add(session)
        db.commit()
        db.refresh(session)
    else:
        session = db.query(ChatSession).filter(ChatSession.id == request.session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        session_id = request.session_id
    
    # Save user message to DB
    user_message = ChatMessage(
        session_id=session_id,
        role="user",
        content=request.message
    )
    db.add(user_message)
    db.commit()
    
    # Get existing messages and convert to LangGraph format
    existing_messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.timestamp).all()
    
    messages_for_agent = format_messages_for_langgraph([
        {"role": msg.role, "content": msg.content}
        for msg in existing_messages
    ])
    
    # Generate AI response with LangGraph
    requirements_defined = False
    requirements_summary = None
    try:
        if app.state.chat_agent:
            # Execute chat agent (set initial state)
            initial_state = {
                "messages": messages_for_agent,
                "requirements_defined": False,
                "requirements_summary": ""
            }
            result = invoke_chat_agent_with_langfuse(app.state.chat_agent, initial_state, session_id)
            ai_response_content = result["messages"][-1].content
            requirements_defined = result.get("requirements_defined", False)
            requirements_summary = result.get("requirements_summary", None)
        else:
            # Fallback: when agent is not initialized
            ai_response_content = "Sorry, the AI agent is not available. Please check if the OPENAI_API_KEY environment variable is set."
    except Exception as e:
        print(f"Error: Failed to generate AI response: {e}")
        import traceback
        traceback.print_exc()
        ai_response_content = f"An error occurred: {str(e)}"
    
    # Save AI response to DB
    ai_message = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=ai_response_content
    )
    db.add(ai_message)
    
    # Update session update time
    session.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ai_message)
    
    return ChatMessageResponse(
        id=ai_message.id,
        session_id=session_id,
        role=ai_message.role,
        content=ai_message.content,
        timestamp=ai_message.timestamp.isoformat(),
        requirements_defined=requirements_defined,
        requirements_summary=requirements_summary
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
    # Save task description as user message
    initial_user_message = ChatMessage(
        session_id=session_id,
        role="user",
        content=f"Task name: {task_data.name}\n\n{task_data.description}"
    )
    db.add(initial_user_message)
    db.commit()
    
    # AI starts requirements definition (define requirements without assumptions, confirm unclear points)
    try:
        if app.state.chat_agent:
            # Get existing messages and convert to LangGraph format
            existing_messages = db.query(ChatMessage).filter(
                ChatMessage.session_id == session_id
            ).order_by(ChatMessage.timestamp).all()
            
            messages_for_agent = format_messages_for_langgraph([
                {"role": msg.role, "content": msg.content}
                for msg in existing_messages
            ])
            
            # Execute chat agent (set initial state)
            initial_state = {
                "messages": messages_for_agent,
                "requirements_defined": False,
                "requirements_summary": ""
            }
            result = invoke_chat_agent_with_langfuse(app.state.chat_agent, initial_state, session_id)
            ai_response_content = result["messages"][-1].content
            
            # Save AI response to DB
            ai_message = ChatMessage(
                session_id=session_id,
                role="assistant",
                content=ai_response_content
            )
            db.add(ai_message)
            
            # Update session update time
            session.updated_at = datetime.utcnow()
            db.commit()
        else:
            # Fallback: when agent is not initialized
            ai_message = ChatMessage(
                session_id=session_id,
                role="assistant",
                content="Sorry, the AI agent is not available. Please check if the OPENAI_API_KEY environment variable is set."
            )
            db.add(ai_message)
            db.commit()
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
    
    # Use the same logic as the existing chat endpoint
    session_id = task.session_id
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Save user message to DB
    user_message = ChatMessage(
        session_id=session_id,
        role="user",
        content=request.message
    )
    db.add(user_message)
    db.commit()
    
    # Get existing messages and convert to LangGraph format
    existing_messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.timestamp).all()
    
    messages_for_agent = format_messages_for_langgraph([
        {"role": msg.role, "content": msg.content}
        for msg in existing_messages
    ])
    
    # Generate AI response with LangGraph
    requirements_defined = False
    requirements_summary = None
    try:
        if app.state.chat_agent:
            # Execute chat agent (set initial state)
            initial_state = {
                "messages": messages_for_agent,
                "requirements_defined": False,
                "requirements_summary": ""
            }
            result = invoke_chat_agent_with_langfuse(app.state.chat_agent, initial_state, session_id)
            ai_response_content = result["messages"][-1].content
            requirements_defined = result.get("requirements_defined", False)
            requirements_summary = result.get("requirements_summary", None)
        else:
            # Fallback: when agent is not initialized
            ai_response_content = "Sorry, the AI agent is not available. Please check if the OPENAI_API_KEY environment variable is set."
    except Exception as e:
        print(f"Error: Failed to generate AI response: {e}")
        import traceback
        traceback.print_exc()
        ai_response_content = f"An error occurred: {str(e)}"
    
    # Save AI response to DB
    ai_message = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=ai_response_content
    )
    db.add(ai_message)
    
    # Update session update time
    session.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ai_message)
    
    return ChatMessageResponse(
        id=ai_message.id,
        session_id=session_id,
        role=ai_message.role,
        content=ai_message.content,
        timestamp=ai_message.timestamp.isoformat(),
        requirements_defined=requirements_defined,
        requirements_summary=requirements_summary
    )


async def run_task_background(task_id: str):
    """Function to execute task in background"""
    logger.info(f"Starting background task execution: {task_id}")
    db = next(get_db())
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            logger.error(f"Task {task_id} not found")
            return
        
        logger.info(f"Task found: {task.name} (status: {task.status})")
        
        # Extract requirements from chat history (if session exists)
        requirements_summary = ""
        if task.session_id:
            messages = db.query(ChatMessage).filter(
                ChatMessage.session_id == task.session_id
            ).order_by(ChatMessage.timestamp).all()
            
            # Create requirements summary (from chat history)
            if messages:
                requirements_summary = "\n".join([
                    f"{msg.role}: {msg.content}" for msg in messages[-5:]  # Last 5 messages
                ])
        else:
            # Phase 0: Test execution mode - skip requirements definition
            logger.info("No session_id found - running in test execution mode (requirements skipped)")
            requirements_summary = ""
        
        # Artifact output path (host side)
        artifacts_dir = Path("/app/data/artifacts")
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        task_artifacts_dir = artifacts_dir / task_id
        task_artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        # Output path in Runtime container
        runtime_output_path = f"/workspace/outputs/{task_id}"
        
        # Initialize RuntimeExecutor (Phase 6: Execute in Runtime container)
        try:
            runtime_executor = RuntimeExecutor()
            logger.info("RuntimeExecutor initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize RuntimeExecutor: {e}")
            raise
        
        # Log callback function
        def log_callback(role: str, content: str):
            try:
                log_entry = TaskLog(
                    task_id=task_id,
                    role=role,
                    content=content
                )
                db.add(log_entry)
                db.commit()
                logger.info(f"[TaskLog][{role}] {content[:200]}")
            except Exception as e:
                logger.error(f"Failed to save task log: {e}")
                logger.debug(f"Log content: {content[:500]}")
        
        # Code execution function (Phase 6: Execute in Runtime container)
        def execute_code_func(code: str) -> str:
            """Execute code and return result (Phase 6: Runtime container execution)"""
            try:
                # Execute code in Runtime container
                success, stdout, stderr = runtime_executor.execute_code(
                    code=code,
                    task_id=task_id,
                    timeout=300
                )
                
                result_str = f"Success: {success}\n"
                if stdout:
                    result_str += f"Output:\n{stdout}\n"
                if stderr:
                    result_str += f"Error:\n{stderr}\n"
                
                log_callback("executor", f"Code execution result:\n{result_str}")
                return result_str
                
            except Exception as e:
                error_msg = f"Error executing code in runtime container: {str(e)}"
                log_callback("executor", error_msg)
                return f"Error: {error_msg}"
        
        # Set model provider
        model_provider = ModelProvider.OPENAI if task.model_provider == "openai" else ModelProvider.ANTHROPIC
        
        # Phase 1: Classify task type if not already set
        task_type = task.task_type
        if not task_type:
            try:
                logger.info("Task type not set, classifying task...")
                task_type = classify_task_type(
                    task_name=task.name,
                    task_description=task.description,
                    model_provider=model_provider,
                    model_name=task.model_name
                )
                # Update task in database
                task.task_type = task_type
                db.commit()
                logger.success(f"Task classified as type: {task_type}")
            except Exception as e:
                logger.error(f"Error classifying task type: {e}", exc_info=True)
                task_type = "code_generation"  # Default fallback
        
        # Create agent workflow
        logger.info("Creating agent workflow")
        # Phase 0: If no requirements summary, use task description only
        if requirements_summary:
            task_description_with_requirements = task.description + "\n\nRequirements:\n" + requirements_summary
        else:
            task_description_with_requirements = task.description
        
        workflow, initial_state = create_workflow(
            model_provider=model_provider,
            model_name=task.model_name,
            task_id=task_id,
            task_name=task.name,
            task_description=task_description_with_requirements,
            runtime_output_path=runtime_output_path,
            execute_code_func=execute_code_func,
            log_callback=log_callback,
            session_id=task.session_id,
            task_type=task_type
        )
        
        logger.info("Workflow created, starting execution")
        log_callback("system", f"Starting task execution: {task.name}")
        
        # Get Langfuse callback handler (for LangGraph execution)
        langfuse_handler = get_langfuse_handler(
            task_id=task_id,
            session_id=task.session_id,
            trace_name="LangGraph Task"
        )

        try:
            logger.info("Invoking workflow")
            # Pass callback to LangGraph invoke
            config = {}
            if langfuse_handler:
                callback_manager = CallbackManager([langfuse_handler])
                config["callbacks"] = callback_manager
                config["metadata"] = {"trace_name": "LangGraph Task"}
                config["run_name"] = "LangGraph Task"
            
            result = workflow.invoke(initial_state, config=config if config else None)
            logger.success("Workflow execution completed successfully")
            log_callback("system", "Task execution completed successfully")
            
            # Phase 6: Check artifacts (automatically shared via volume mount)
            # Volume mount automatically mounts /workspace/outputs/{task_id} in Runtime container
            # to ./backend/data/artifacts/{task_id} on host side
            logger.info("Checking for artifacts...")
            
            # Wait a bit before checking artifacts (wait for filesystem sync)
            import time
            time.sleep(1)
            
            # Check artifacts
            if task_artifacts_dir.exists():
                artifacts = list(task_artifacts_dir.iterdir())
                if artifacts:
                    artifact_path = str(task_artifacts_dir)
                    task.artifact_path = artifact_path
                    log_callback("system", f"Artifacts available at: {artifact_path}")
                    logger.success(f"Found {len(artifacts)} artifact(s) in {artifact_path}")
                else:
                    logger.warning("No artifacts found in artifacts directory")
                    # Try copying from Runtime container as a fallback
                    logger.info("Attempting to copy artifacts from runtime container...")
                    copy_success = runtime_executor.copy_artifacts_from_container(
                        task_id=task_id,
                        host_artifacts_dir=str(task_artifacts_dir)
                    )
                    if copy_success:
                        artifacts = list(task_artifacts_dir.iterdir())
                        if artifacts:
                            artifact_path = str(task_artifacts_dir)
                            task.artifact_path = artifact_path
                            log_callback("system", f"Artifacts copied from runtime container to: {artifact_path}")
            else:
                logger.warning("Artifacts directory does not exist")
                # Try copying from Runtime container as a fallback
                logger.info("Attempting to copy artifacts from runtime container...")
                copy_success = runtime_executor.copy_artifacts_from_container(
                    task_id=task_id,
                    host_artifacts_dir=str(task_artifacts_dir)
                )
                if copy_success and task_artifacts_dir.exists():
                    artifacts = list(task_artifacts_dir.iterdir())
                    if artifacts:
                        artifact_path = str(task_artifacts_dir)
                        task.artifact_path = artifact_path
                        log_callback("system", f"Artifacts copied from runtime container to: {artifact_path}")
            
            # Update task to completed status
            task.status = TaskStatus.COMPLETED.value
            task.completed_at = datetime.utcnow()
            db.commit()
            
        except Exception as e:
            logger.error(f"Task execution failed: {e}", exc_info=True)
            import traceback
            error_traceback = traceback.format_exc()
            logger.error(f"Traceback: {error_traceback}")
            log_callback("system", f"Task execution failed: {str(e)}\n\n{error_traceback}")
            task.status = TaskStatus.FAILED.value
            task.error_message = f"{str(e)}\n\n{error_traceback}"
            task.completed_at = datetime.utcnow()
            db.commit()
            logger.error(f"Task {task_id} marked as failed")
            
    except Exception as e:
        logger.error(f"Error in background task execution: {e}", exc_info=True)
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Traceback: {error_traceback}")
        db.rollback()
        # Update task to failed status
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                task.status = TaskStatus.FAILED.value
                task.error_message = f"{str(e)}\n\n{error_traceback}"
                task.completed_at = datetime.utcnow()
                db.commit()
                logger.error(f"Task {task_id} marked as failed in exception handler")
        except Exception as inner_e:
            logger.error(f"Failed to update task status: {inner_e}")
    finally:
        logger.info(f"Background task execution finished for task: {task_id}")
        db.close()


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
    
    # Execute task in background
    asyncio.create_task(run_task_background(task_id))
    
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
    
    # Execute task in background
    asyncio.create_task(run_task_background(task_id))
    
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
