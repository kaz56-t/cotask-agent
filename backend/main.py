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

# .envファイルを読み込む（ローカル開発環境用のフォールバック）
# docker-compose.ymlでenv_fileを指定している場合は、環境変数として既に利用可能
load_dotenv()

from database import init_db, get_db, ChatSession, ChatMessage, Task, TaskStatus, ModelProvider
from chat_agent import create_chat_agent, format_messages_for_langgraph
from langchain_core.messages import HumanMessage

app = FastAPI(title="CoTask Agent API", version="0.1.0")

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],  # Next.jsのデフォルトポートとDocker内部通信
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# アプリケーション起動時にデータベースを初期化
@app.on_event("startup")
async def startup_event():
    init_db()
    # チャットエージェントをグローバルに初期化（必要に応じて）
    try:
        # 環境変数を確認
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("警告: OPENAI_API_KEY環境変数が設定されていません。")
            print("docker-compose.ymlでenv_fileを指定しているか、.envファイルを確認してください。")
            app.state.chat_agent = None
        else:
            app.state.chat_agent = create_chat_agent()
            print("チャットエージェントの初期化に成功しました")
    except Exception as e:
        print(f"警告: チャットエージェントの初期化に失敗しました: {e}")
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
    requirements_defined: Optional[bool] = False  # 要件が確定したかどうか
    requirements_summary: Optional[str] = None  # 要件の要約


class ChatSessionResponse(BaseModel):
    id: str
    created_at: str
    updated_at: str
    messages: List[ChatMessageResponse]


# Phase 3: タスク管理のPydanticモデル
class TaskCreate(BaseModel):
    name: str
    description: str
    model_provider: str  # "openai" or "anthropic"
    model_name: str


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

    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    tasks: List[TaskResponse]
    total: int


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
    Phase 2: LangGraphによる対話フローとDB保存
    ユーザーのメッセージを受け取り、AIが応答を生成してDBに保存
    """
    # セッションIDが指定されていない場合は新規作成
    if not request.session_id:
        session_id = str(uuid.uuid4())
        session = ChatSession(id=session_id)
        db.add(session)
        db.commit()
        db.refresh(session)
    else:
        session = db.query(ChatSession).filter(ChatSession.id == request.session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="セッションが見つかりません")
        session_id = request.session_id
    
    # ユーザーメッセージをDBに保存
    user_message = ChatMessage(
        session_id=session_id,
        role="user",
        content=request.message
    )
    db.add(user_message)
    db.commit()
    
    # 既存のメッセージを取得してLangGraph形式に変換
    existing_messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.timestamp).all()
    
    messages_for_agent = format_messages_for_langgraph([
        {"role": msg.role, "content": msg.content}
        for msg in existing_messages
    ])
    
    # LangGraphでAI応答を生成
    requirements_defined = False
    requirements_summary = None
    try:
        if app.state.chat_agent:
            # チャットエージェントを実行（初期状態を設定）
            initial_state = {
                "messages": messages_for_agent,
                "requirements_defined": False,
                "requirements_summary": ""
            }
            result = app.state.chat_agent.invoke(initial_state)
            ai_response_content = result["messages"][-1].content
            requirements_defined = result.get("requirements_defined", False)
            requirements_summary = result.get("requirements_summary", None)
        else:
            # フォールバック: エージェントが初期化されていない場合
            ai_response_content = "申し訳ございませんが、AIエージェントが利用できません。環境変数OPENAI_API_KEYが設定されているか確認してください。"
    except Exception as e:
        print(f"エラー: AI応答の生成に失敗しました: {e}")
        import traceback
        traceback.print_exc()
        ai_response_content = f"エラーが発生しました: {str(e)}"
    
    # AI応答をDBに保存
    ai_message = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=ai_response_content
    )
    db.add(ai_message)
    
    # セッションの更新時刻を更新
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
    """指定されたセッションIDのチャット履歴を取得"""
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    
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
    """新しいチャットセッションを作成"""
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
    要件が確定したタスクを実行
    Phase 4で本格実装予定、今はモック
    """
    # セッションの確認
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    
    # チャット履歴を取得して要件を確認
    messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.timestamp).all()
    
    # 最後のメッセージで要件が確定しているか確認
    last_message = messages[-1] if messages else None
    if not last_message or last_message.role != "assistant":
        raise HTTPException(status_code=400, detail="要件が確定していません")
    
    # 実行開始のメッセージを返す（Phase 4で実装予定）
    return {
        "message": "タスクの実行を開始しました。\n\n（Phase 4で本格実装予定）",
        "session_id": session_id,
        "status": "executing"
    }


# Phase 3: タスク管理API
@app.post("/api/tasks", response_model=TaskResponse, status_code=201)
async def create_task(
    task_data: TaskCreate,
    db: Session = Depends(get_db)
):
    """新しいタスクを作成"""
    # タスクIDを生成
    task_id = str(uuid.uuid4())
    
    # チャットセッションを作成（タスクごとに独立したチャット履歴）
    session_id = str(uuid.uuid4())
    session = ChatSession(id=session_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    
    # タスクを作成
    task = Task(
        id=task_id,
        name=task_data.name,
        description=task_data.description,
        model_provider=task_data.model_provider,
        model_name=task_data.model_name,
        status=TaskStatus.PENDING.value,
        session_id=session_id
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    
    # タスク作成時に、説明を基にAIが要件定義を開始
    # ユーザーメッセージとしてタスクの説明を保存
    initial_user_message = ChatMessage(
        session_id=session_id,
        role="user",
        content=f"タスク名: {task_data.name}\n\n{task_data.description}"
    )
    db.add(initial_user_message)
    db.commit()
    
    # AIが要件定義を開始（推測を入れずに要件を定義し、不明点を確認）
    try:
        if app.state.chat_agent:
            # 既存のメッセージを取得してLangGraph形式に変換
            existing_messages = db.query(ChatMessage).filter(
                ChatMessage.session_id == session_id
            ).order_by(ChatMessage.timestamp).all()
            
            messages_for_agent = format_messages_for_langgraph([
                {"role": msg.role, "content": msg.content}
                for msg in existing_messages
            ])
            
            # チャットエージェントを実行（初期状態を設定）
            initial_state = {
                "messages": messages_for_agent,
                "requirements_defined": False,
                "requirements_summary": ""
            }
            result = app.state.chat_agent.invoke(initial_state)
            ai_response_content = result["messages"][-1].content
            
            # AI応答をDBに保存
            ai_message = ChatMessage(
                session_id=session_id,
                role="assistant",
                content=ai_response_content
            )
            db.add(ai_message)
            
            # セッションの更新時刻を更新
            session.updated_at = datetime.utcnow()
            db.commit()
        else:
            # フォールバック: エージェントが初期化されていない場合
            ai_message = ChatMessage(
                session_id=session_id,
                role="assistant",
                content="申し訳ございませんが、AIエージェントが利用できません。環境変数OPENAI_API_KEYが設定されているか確認してください。"
            )
            db.add(ai_message)
            db.commit()
    except Exception as e:
        print(f"エラー: 初期要件定義の生成に失敗しました: {e}")
        import traceback
        traceback.print_exc()
        # エラーが発生してもタスクは作成する
        ai_message = ChatMessage(
            session_id=session_id,
            role="assistant",
            content=f"エラーが発生しました: {str(e)}"
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
        session_id=task.session_id
    )


@app.get("/api/tasks", response_model=TaskListResponse)
async def get_tasks(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """タスク一覧を取得"""
    query = db.query(Task)
    
    # ステータスでフィルタリング
    if status:
        query = query.filter(Task.status == status)
    
    # 総数を取得
    total = query.count()
    
    # ページネーション
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
                session_id=task.session_id
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
    """特定のタスクを取得"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="タスクが見つかりません")
    
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
        session_id=task.session_id
    )


@app.get("/api/tasks/{task_id}/chat", response_model=ChatSessionResponse)
async def get_task_chat(
    task_id: str,
    db: Session = Depends(get_db)
):
    """タスクに関連付けられたチャット履歴を取得"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="タスクが見つかりません")
    
    if not task.session_id:
        raise HTTPException(status_code=404, detail="タスクにチャットセッションが関連付けられていません")
    
    session = db.query(ChatSession).filter(ChatSession.id == task.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="チャットセッションが見つかりません")
    
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
    """タスクに関連付けられたチャットセッションにメッセージを送信"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="タスクが見つかりません")
    
    if not task.session_id:
        raise HTTPException(status_code=404, detail="タスクにチャットセッションが関連付けられていません")
    
    # 既存のチャットエンドポイントと同じロジックを使用
    session_id = task.session_id
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    
    # ユーザーメッセージをDBに保存
    user_message = ChatMessage(
        session_id=session_id,
        role="user",
        content=request.message
    )
    db.add(user_message)
    db.commit()
    
    # 既存のメッセージを取得してLangGraph形式に変換
    existing_messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.timestamp).all()
    
    messages_for_agent = format_messages_for_langgraph([
        {"role": msg.role, "content": msg.content}
        for msg in existing_messages
    ])
    
    # LangGraphでAI応答を生成
    requirements_defined = False
    requirements_summary = None
    try:
        if app.state.chat_agent:
            # チャットエージェントを実行（初期状態を設定）
            initial_state = {
                "messages": messages_for_agent,
                "requirements_defined": False,
                "requirements_summary": ""
            }
            result = app.state.chat_agent.invoke(initial_state)
            ai_response_content = result["messages"][-1].content
            requirements_defined = result.get("requirements_defined", False)
            requirements_summary = result.get("requirements_summary", None)
        else:
            # フォールバック: エージェントが初期化されていない場合
            ai_response_content = "申し訳ございませんが、AIエージェントが利用できません。環境変数OPENAI_API_KEYが設定されているか確認してください。"
    except Exception as e:
        print(f"エラー: AI応答の生成に失敗しました: {e}")
        import traceback
        traceback.print_exc()
        ai_response_content = f"エラーが発生しました: {str(e)}"
    
    # AI応答をDBに保存
    ai_message = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=ai_response_content
    )
    db.add(ai_message)
    
    # セッションの更新時刻を更新
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


@app.post("/api/tasks/{task_id}/execute")
async def execute_task(
    task_id: str,
    db: Session = Depends(get_db)
):
    """タスクを実行（要件が確定している場合）"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="タスクが見つかりません")
    
    if not task.session_id:
        raise HTTPException(status_code=404, detail="タスクにチャットセッションが関連付けられていません")
    
    # セッションの確認
    session = db.query(ChatSession).filter(ChatSession.id == task.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    
    # チャット履歴を取得して要件が確定しているか確認
    messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == task.session_id
    ).order_by(ChatMessage.timestamp).all()
    
    # 最後のメッセージで要件が確定しているか確認
    last_message = messages[-1] if messages else None
    if not last_message or last_message.role != "assistant":
        raise HTTPException(status_code=400, detail="要件が確定していません")
    
    # 要件確定のマーカーを確認
    if "[要件確定]" not in last_message.content and "要件確定" not in last_message.content:
        raise HTTPException(status_code=400, detail="要件が確定していません。チャットで要件を確定させてください。")
    
    # タスクのステータスを更新
    task.status = TaskStatus.RUNNING.value
    task.started_at = datetime.utcnow()
    db.commit()
    
    # 実行開始のメッセージを返す（Phase 4で本格実装予定）
    return {
        "message": "タスクの実行を開始しました。\n\n（Phase 4で本格実装予定）",
        "task_id": task_id,
        "status": "running"
    }


# Phase 1との互換性のため、旧エンドポイントも残す
@app.post("/api/chat/legacy")
async def chat_legacy(message: dict):
    """
    Phase 1用の簡単なチャットエンドポイント（互換性のため残す）
    入力欄から「こんにちは」と送ると、「[定型文] 受信しました」と返す
    """
    user_message = message.get("message", "")
    
    # Phase 1の要件: 「こんにちは」を受け取ったら「[定型文] 受信しました」を返す
    if user_message == "こんにちは":
        return {"response": "[定型文] 受信しました"}
    
    # その他のメッセージにも対応
    return {"response": f"[定型文] 受信しました: {user_message}"}
