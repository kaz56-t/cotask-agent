"""
Database configuration and model definitions
Chat history persistence with SQLite/SQLAlchemy
"""
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os
import enum
from pathlib import Path

# Create database directory
db_dir = Path("/app/data")
db_dir.mkdir(exist_ok=True)

# Database file path
db_path = db_dir / "cotask.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{db_path}")

# Create engine and session
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class TaskStatus(enum.Enum):
    """Task status"""
    PENDING = "pending"  # Defining
    RUNNING = "running"  # Running
    COMPLETED = "completed"  # Completed
    FAILED = "failed"  # Failed
    CANCELLED = "cancelled"  # Cancelled


class ModelProvider(enum.Enum):
    """Model provider"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class Task(Base):
    """Task table (Phase 3)"""
    __tablename__ = "tasks"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    model_provider = Column(String, nullable=False)  # "openai" or "anthropic"
    model_name = Column(String, nullable=False)
    # SQLite doesn't directly support Enum, so save as String
    status = Column(String, default=TaskStatus.PENDING.value, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    artifact_path = Column(String, nullable=True)
    task_type = Column(String, nullable=True)  # Task type: code_generation, web_search, text_generation, scraping, rag, simple_text
    
    # Link task and chat session one-to-one
    session_id = Column(String, ForeignKey("chat_sessions.id"), nullable=True, unique=True)
    session = relationship("ChatSession", back_populates="task", uselist=False)
    
    # Task log relationship
    logs = relationship("TaskLog", back_populates="task", cascade="all, delete-orphan")


class ChatSession(Base):
    """Chat session table"""
    __tablename__ = "chat_sessions"

    id = Column(String, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")
    task = relationship("Task", back_populates="session", uselist=False)


class ChatMessage(Base):
    """Chat message table"""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("chat_sessions.id"), nullable=False)
    role = Column(String, nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    session = relationship("ChatSession", back_populates="messages")


class TaskLog(Base):
    """Task log table (Phase 4)"""
    __tablename__ = "task_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String, ForeignKey("tasks.id"), nullable=False)
    role = Column(String, nullable=False)  # "architect", "executor", "system", etc.
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    task = relationship("Task", back_populates="logs")


def init_db():
    """Initialize database (create tables)"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
