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
    Get Langfuse callback handler.
    
    Args:
        task_id: Task ID (optional)
        session_id: Session ID (optional)
        user_id: User ID (optional)
        trace_name: Trace name (optional)
    
    Returns:
        LangfuseCallbackHandler or None (if Langfuse is disabled)
    """
    # Get Langfuse configuration from environment variables
    # Use container name for Docker internal communication, localhost for external access
    langfuse_host = os.getenv("LANGFUSE_BASE_URL", "http://langfuse:3000")
    langfuse_public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    
    # Langfuse is disabled if environment variables are not set
    if not langfuse_public_key or not langfuse_secret_key:
        logger.debug("Langfuse is not configured (LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY not set)")
        return None
    
    try:
        # Explicitly set environment variables (CallbackHandler reads from environment variables)
        # Won't overwrite if already set
        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", langfuse_public_key)
        os.environ.setdefault("LANGFUSE_SECRET_KEY", langfuse_secret_key)
        os.environ.setdefault("LANGFUSE_HOST", langfuse_host)
        
        # Initialize Langfuse client (for manual tracking)
        langfuse = Langfuse(
            public_key=langfuse_public_key,
            secret_key=langfuse_secret_key,
            host=langfuse_host
        )
        
        # Create callback handler
        # CallbackHandler reads credentials from environment variables, so don't pass parameters
        # If trace_name exists, set it in config during invoke
        handler = CallbackHandler()
        
        # Save trace_name to handler (for later use in config)
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
    Get Langfuse trace object (for manual tracking).
    
    Args:
        task_id: Task ID (optional)
        session_id: Session ID (optional)
        user_id: User ID (optional)
        name: Trace name (optional)
    
    Returns:
        Langfuse trace object or None
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
