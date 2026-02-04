"""
LangGraph-based conversation flow implementation
Conversation system where AI responds with questions to user's ambiguous instructions
Requirements definition flow: Define requirements without assumptions and confirm unclear points
"""
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI
import os
from dotenv import load_dotenv

# Load .env file (fallback for local development environment)
# If env_file is specified in docker-compose.yml, environment variables are already available
load_dotenv()


class ChatState(TypedDict):
    """Chat state definition"""
    messages: Annotated[list[BaseMessage], lambda x, y: x + y if y else x]
    requirements_defined: bool  # Whether requirements are defined
    requirements_summary: str  # Requirements summary


from prompts.chat import REQUIREMENTS_SYSTEM_PROMPT


def create_chat_agent():
    """Create chat agent with LangGraph"""
    
    # Check OpenAI API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    
    # Initialize LLM (callbacks are passed at execution time)
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.7,
        api_key=api_key
    )
    
    def chat_node(state: ChatState) -> ChatState:
        """Chat node: Generate AI response to user message"""
        messages = state["messages"]
        requirements_defined = state.get("requirements_defined", False)
        requirements_summary = state.get("requirements_summary", "")
        
        # Check if last message is from user
        if messages and isinstance(messages[-1], HumanMessage):
            # Add system prompt at the beginning (if not already added)
            messages_with_system = messages
            if not messages or not isinstance(messages[0], SystemMessage):
                messages_with_system = [SystemMessage(content=REQUIREMENTS_SYSTEM_PROMPT)] + list(messages)
            
            # Send messages to LLM (callbacks are already set on LLM instance)
            response = llm.invoke(messages_with_system)
            messages = list(messages) + [response]
            
            # Determine if requirements are defined
            response_content = response.content if hasattr(response, 'content') else str(response)
            requirements_defined = "[要件確定]" in response_content or "要件確定" in response_content
            
            # Extract requirements summary (use first paragraph as summary)
            if requirements_defined:
                # Extract summary when requirements are defined
                lines = response_content.split('\n')
                summary_lines = []
                for line in lines:
                    if line.strip() and not line.strip().startswith('['):
                        summary_lines.append(line.strip())
                        if len(summary_lines) >= 3:  # Use first 3 lines as summary
                            break
                requirements_summary = '\n'.join(summary_lines) if summary_lines else response_content[:200]
            
            return {
                "messages": messages,
                "requirements_defined": requirements_defined,
                "requirements_summary": requirements_summary
            }
        
        return {
            "messages": messages,
            "requirements_defined": requirements_defined,
            "requirements_summary": requirements_summary
        }
    
    # Build state graph
    workflow = StateGraph(ChatState)
    workflow.add_node("chat", chat_node)
    workflow.set_entry_point("chat")
    workflow.add_edge("chat", END)
    
    # Compile
    app = workflow.compile()
    return app


def format_messages_for_langgraph(messages: list[dict]) -> list[BaseMessage]:
    """Convert messages from database to LangGraph format"""
    formatted = []
    for msg in messages:
        if msg["role"] == "user":
            formatted.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            formatted.append(AIMessage(content=msg["content"]))
    return formatted
