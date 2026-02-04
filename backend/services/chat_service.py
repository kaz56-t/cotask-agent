"""Chat service for handling chat-related business logic."""
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from langchain_core.callbacks import CallbackManager
from database import ChatSession, ChatMessage
from agent.chat_agent import format_messages_for_langgraph
from langfuse_config import get_langfuse_handler
from models import ChatMessageResponse
import uuid


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


def process_chat_message(
    chat_agent,
    request_message: str,
    session_id: str,
    db: Session
) -> ChatMessageResponse:
    """
    Process a chat message: save user message, generate AI response, and save it.
    
    Args:
        chat_agent: The chat agent instance
        request_message: User's message
        session_id: Chat session ID
        db: Database session
        
    Returns:
        ChatMessageResponse with the AI's response
    """
    # Save user message to DB
    user_message = ChatMessage(
        session_id=session_id,
        role="user",
        content=request_message
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
        if chat_agent:
            # Execute chat agent (set initial state)
            initial_state = {
                "messages": messages_for_agent,
                "requirements_defined": False,
                "requirements_summary": ""
            }
            result = invoke_chat_agent_with_langfuse(chat_agent, initial_state, session_id)
            ai_response_content = result["messages"][-1].content
            requirements_defined = result.get("requirements_defined", False)
            requirements_summary = result.get("requirements_summary", None)
        else:
            # Fallback: when agent is not initialized
            ai_response_content = "Sorry, the AI agent is not available. Please check if the OPENAI_API_KEY environment variable is set."
    except Exception as e:
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
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if session:
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


def create_or_get_session(session_id: Optional[str], db: Session) -> str:
    """
    Create a new session or get existing session.
    
    Args:
        session_id: Optional session ID. If None, creates a new session.
        db: Database session
        
    Returns:
        Session ID
    """
    if not session_id:
        session_id = str(uuid.uuid4())
        session = ChatSession(id=session_id)
        db.add(session)
        db.commit()
        db.refresh(session)
    else:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not session:
            raise ValueError("Session not found")
    
    return session_id
