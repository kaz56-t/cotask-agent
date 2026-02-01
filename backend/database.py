"""
データベース設定とモデル定義
SQLite/SQLAlchemyによるチャット履歴の永続化
"""
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os
import enum
from pathlib import Path

# データベースディレクトリの作成
db_dir = Path("/app/data")
db_dir.mkdir(exist_ok=True)

# データベースファイルのパス
db_path = db_dir / "cotask.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{db_path}")

# エンジンとセッションの作成
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class TaskStatus(enum.Enum):
    """タスクのステータス"""
    PENDING = "pending"  # 定義中
    RUNNING = "running"  # 実行中
    COMPLETED = "completed"  # 完了
    FAILED = "failed"  # 失敗
    CANCELLED = "cancelled"  # キャンセル


class ModelProvider(enum.Enum):
    """モデルプロバイダー"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class Task(Base):
    """タスクテーブル（Phase 3）"""
    __tablename__ = "tasks"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    model_provider = Column(String, nullable=False)  # "openai" or "anthropic"
    model_name = Column(String, nullable=False)
    # SQLiteではEnumを直接サポートしていないため、Stringとして保存
    status = Column(String, default=TaskStatus.PENDING.value, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    artifact_path = Column(String, nullable=True)
    
    # タスクとチャットセッションを1対1で紐付け
    session_id = Column(String, ForeignKey("chat_sessions.id"), nullable=True, unique=True)
    session = relationship("ChatSession", back_populates="task", uselist=False)


class ChatSession(Base):
    """チャットセッションテーブル"""
    __tablename__ = "chat_sessions"

    id = Column(String, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # リレーション
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")
    task = relationship("Task", back_populates="session", uselist=False)


class ChatMessage(Base):
    """チャットメッセージテーブル"""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("chat_sessions.id"), nullable=False)
    role = Column(String, nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # リレーション
    session = relationship("ChatSession", back_populates="messages")


def init_db():
    """データベースの初期化（テーブル作成）"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """データベースセッションの取得"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
