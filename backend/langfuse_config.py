"""Langfuse configuration and callback handler setup."""
import os
from typing import Optional
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from loguru import logger


def get_langfuse_handler(
    task_id: Optional[str] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    trace_name: Optional[str] = None
) -> Optional[CallbackHandler]:
    """
    Langfuseのコールバックハンドラーを取得する。
    
    Args:
        task_id: タスクID（オプション）
        session_id: セッションID（オプション）
        user_id: ユーザーID（オプション）
        trace_name: トレース名（オプション）
    
    Returns:
        LangfuseCallbackHandlerまたはNone（Langfuseが無効な場合）
    """
    # 環境変数からLangfuseの設定を取得
    # Docker内部通信の場合はコンテナ名を使用、外部からの場合はlocalhostを使用
    langfuse_host = os.getenv("LANGFUSE_BASE_URL", "http://langfuse:3000")
    langfuse_public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    
    # Langfuseが無効な場合（環境変数が設定されていない場合）
    if not langfuse_public_key or not langfuse_secret_key:
        logger.debug("Langfuse is not configured (LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY not set)")
        return None
    
    try:
        # 環境変数を明示的に設定（CallbackHandlerが環境変数から読み取るため）
        # 既に設定されている場合は上書きされない
        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", langfuse_public_key)
        os.environ.setdefault("LANGFUSE_SECRET_KEY", langfuse_secret_key)
        os.environ.setdefault("LANGFUSE_HOST", langfuse_host)
        
        # Langfuseクライアントを初期化（手動トラッキング用）
        langfuse = Langfuse(
            public_key=langfuse_public_key,
            secret_key=langfuse_secret_key,
            host=langfuse_host
        )
        
        # コールバックハンドラーを作成
        # CallbackHandlerは環境変数から認証情報を読み取るため、パラメータを渡さない
        # trace_nameがある場合は、invoke時のconfigで設定する
        handler = CallbackHandler()
        
        # trace_nameをハンドラーに保存（後でconfigで使用）
        if trace_name:
            handler._trace_name = trace_name
        
        logger.info(f"Langfuse callback handler created successfully (host: {langfuse_host})")
        return handler
        
    except Exception as e:
        logger.error(f"Failed to create Langfuse callback handler: {e}")
        return None


def get_langfuse_trace(
    task_id: Optional[str] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    name: Optional[str] = None
):
    """
    Langfuseのトレースオブジェクトを取得する（手動トラッキング用）。
    
    Args:
        task_id: タスクID（オプション）
        session_id: セッションID（オプション）
        user_id: ユーザーID（オプション）
        name: トレース名（オプション）
    
    Returns:
        LangfuseトレースオブジェクトまたはNone
    """
    langfuse_host = os.getenv("LANGFUSE_HOST", "http://langfuse:3000")
    langfuse_public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    
    if not langfuse_public_key or not langfuse_secret_key:
        return None
    
    try:
        langfuse = Langfuse(
            public_key=langfuse_public_key,
            secret_key=langfuse_secret_key,
            host=langfuse_host
        )
        
        trace = langfuse.trace(
            name=name or f"task_{task_id}" if task_id else "trace",
            session_id=session_id or task_id,
            user_id=user_id,
        )
        
        return trace
        
    except Exception as e:
        logger.error(f"Failed to create Langfuse trace: {e}")
        return None
