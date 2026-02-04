"""
TextAgent: Simple text generation and editing tasks.
Handles tasks like email writing, report generation, summaries, etc.
Uses a simple 1-node LangGraph workflow.
"""
from typing import Optional
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from database import ModelProvider
from agent.base import AgentState, create_llm
from loguru import logger
from langfuse_config import get_langfuse_handler
from prompts.text_agent import get_text_agent_prompt
from pathlib import Path
import json


def create_text_agent_node(
    llm,
    task_id: str,
    runtime_output_path: str,
    log_callback
):
    """Create text agent node that generates/edits text."""
    def text_agent_node(state: AgentState) -> AgentState:
        """Text agent: generates or edits text content."""
        logger.info(f"[TextAgent] Processing task: {state['task_name']}")
        log_callback("text_agent", "TextAgent is generating/editing text content...")
        
        try:
            system_prompt = get_text_agent_prompt(
                task_name=state['task_name'],
                task_description=state['task_description'],
                runtime_output_path=runtime_output_path
            )

            messages = state['messages'].copy()
            if not any(isinstance(msg, SystemMessage) for msg in messages):
                messages.insert(0, SystemMessage(content=system_prompt))
            
            logger.debug(f"[TextAgent] Invoking LLM with {len(messages)} messages")
            response = llm.invoke(messages)
            logger.success(f"[TextAgent] Received response (length: {len(response.content)} chars)")
            messages.append(response)
            
            log_callback("text_agent", response.content)
            
            # Try to extract file content and save it
            try:
                content = response.content
                
                # Check if response contains code blocks with file content
                import re
                file_blocks = re.findall(r'```(?:json|txt|md|text)?\n(.*?)```', content, re.DOTALL)
                
                if file_blocks:
                    # Use the first code block as file content
                    file_content = file_blocks[0].strip()
                else:
                    # Use the entire response as file content
                    file_content = content.strip()
                
                # Determine file name and extension
                task_name_safe = "".join(c for c in state['task_name'] if c.isalnum() or c in (' ', '-', '_')).strip()
                task_name_safe = task_name_safe.replace(' ', '_')[:50]  # Limit length
                
                # Try to detect format from content
                if content.strip().startswith('{') or content.strip().startswith('['):
                    # Looks like JSON
                    try:
                        json.loads(file_content)
                        file_path = Path(runtime_output_path) / f"{task_name_safe}.json"
                        file_path.write_text(file_content, encoding='utf-8')
                    except json.JSONDecodeError:
                        # Not valid JSON, save as markdown
                        file_path = Path(runtime_output_path) / f"{task_name_safe}.md"
                        file_path.write_text(file_content, encoding='utf-8')
                else:
                    # Save as markdown file (text content as artifact)
                    file_path = Path(runtime_output_path) / f"{task_name_safe}.md"
                    file_path.write_text(file_content, encoding='utf-8')
                
                logger.success(f"[TextAgent] Saved output to {file_path}")
                log_callback("text_agent", f"Output saved to: {file_path}")
                
            except Exception as e:
                logger.warning(f"[TextAgent] Could not save file automatically: {e}")
                log_callback("text_agent", f"Note: Could not save file automatically. Content: {response.content[:200]}...")
            
            # TextAgent completes in one step
            new_state = {
                **state,
                "messages": messages,
                "current_agent": "end"
            }
            logger.info("[TextAgent] Task completed")
            return new_state
            
        except Exception as e:
            logger.error(f"[TextAgent] Error occurred: {e}", exc_info=True)
            log_callback("text_agent", f"Error: {str(e)}")
            raise
    
    return text_agent_node


def create_text_workflow(
    model_provider: ModelProvider,
    model_name: str,
    task_id: str,
    task_name: str,
    task_description: str,
    runtime_output_path: str,
    log_callback,
    session_id: Optional[str] = None
):
    """Create LangGraph workflow for text generation/editing tasks."""
    logger.info(f"Creating TextAgent workflow for task: {task_id} ({task_name})")
    logger.info(f"Model: {model_provider.value}/{model_name}")
    
    # Get Langfuse callback handler
    langfuse_handler = get_langfuse_handler(
        task_id=task_id,
        session_id=session_id
    )
    callbacks = [langfuse_handler] if langfuse_handler else None
    
    try:
        llm = create_llm(model_provider, model_name, callbacks=callbacks)
        logger.success("LLM created successfully")
    except Exception as e:
        logger.error(f"Failed to create LLM: {e}")
        raise
    
    # Create text agent node
    logger.info("Creating text agent node")
    text_agent = create_text_agent_node(llm, task_id, runtime_output_path, log_callback)
    logger.success("Text agent node created successfully")
    
    # Create graph (simple 1-node workflow)
    workflow = StateGraph(AgentState)
    workflow.add_node("text_agent", text_agent)
    workflow.set_entry_point("text_agent")
    workflow.add_edge("text_agent", END)
    
    # Compile graph
    logger.info("Compiling workflow graph")
    app = workflow.compile()
    logger.success("Workflow graph compiled successfully")
    
    # Initial state
    initial_state = {
        "messages": [
            HumanMessage(content=f"Task: {task_name}\n\nDescription: {task_description}\n\nGenerate or edit the text content as requested.")
        ],
        "task_id": task_id,
        "task_name": task_name,
        "task_description": task_description,
        "runtime_output_path": runtime_output_path,
        "current_agent": "text_agent",
        "iteration_count": 0,
        "max_iterations": 1,  # TextAgent completes in one iteration
        "task_type": "text_generation"
    }
    
    logger.info("TextAgent workflow creation completed")
    return app, initial_state
