"""Langfuse configuration and callback handler setup."""
import os
from typing import Optional
from langfuse import Langfuse
from langfuse.callback import CallbackHandler
from loguru import logger


def get_langfuse_handler(
    task_id: Optional[str] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> Optional[CallbackHandler]:
    """
    Langfuseのコールバックハンドラーを取得する。
    
    Args:
        task_id: タスクID（オプション）
        session_id: セッションID（オプション）
        user_id: ユーザーID（オプション）
    
    Returns:
        LangfuseCallbackHandlerまたはNone（Langfuseが無効な場合）
    """
    # 環境変数からLangfuseの設定を取得
    # Docker内部通信の場合はコンテナ名を使用、外部からの場合はlocalhostを使用
    langfuse_host = os.getenv("LANGFUSE_HOST", "http://langfuse:3000")
    langfuse_public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    
    # Langfuseが無効な場合（環境変数が設定されていない場合）
    if not langfuse_public_key or not langfuse_secret_key:
        logger.debug("Langfuse is not configured (LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY not set)")
        return None
    
    try:
        # Langfuseクライアントを初期化
        langfuse = Langfuse(
            public_key=langfuse_public_key,
            secret_key=langfuse_secret_key,
            host=langfuse_host
        )
        
        # コールバックハンドラーを作成
        handler = CallbackHandler(
            public_key=langfuse_public_key,
            secret_key=langfuse_secret_key,
            host=langfuse_host,
            session_id=session_id or task_id,  # session_idまたはtask_idを使用
            user_id=user_id,
        )
        
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
