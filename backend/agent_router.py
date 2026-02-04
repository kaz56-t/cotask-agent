"""
Agent Router: Routes tasks to appropriate agents based on task type.
"""
from typing import Optional, Tuple
from langgraph.graph.graph import CompiledGraph
from database import ModelProvider
from agents import AgentState
from loguru import logger

# Import agent workflows
from text_agent import create_text_workflow
from search_agent import create_search_workflow

# Import CodeAgent workflow (avoid circular import by importing function directly)
def _get_code_workflow():
    """Lazy import to avoid circular dependencies."""
    from agents import create_code_workflow
    return create_code_workflow


def route_task(
    task_type: str,
    model_provider: ModelProvider,
    model_name: str,
    task_id: str,
    task_name: str,
    task_description: str,
    runtime_output_path: str,
    execute_code_func,
    log_callback,
    session_id: Optional[str] = None
) -> Tuple[CompiledGraph, dict]:
    """
    Route task to appropriate agent based on task type.
    
    Args:
        task_type: Task type (code_generation, web_search, text_generation, etc.)
        model_provider: LLM provider
        model_name: Model name
        task_id: Task ID
        task_name: Task name
        task_description: Task description
        runtime_output_path: Output path for artifacts
        execute_code_func: Code execution function (for code_generation tasks)
        log_callback: Logging callback function
        session_id: Optional session ID
        
    Returns:
        Tuple of (workflow, initial_state)
    """
    logger.info(f"Routing task to agent based on type: {task_type}")
    
    if task_type == "text_generation" or task_type == "simple_text":
        logger.info("Routing to TextAgent")
        return create_text_workflow(
            model_provider=model_provider,
            model_name=model_name,
            task_id=task_id,
            task_name=task_name,
            task_description=task_description,
            runtime_output_path=runtime_output_path,
            log_callback=log_callback,
            session_id=session_id
        )
    
    elif task_type == "web_search":
        logger.info("Routing to SearchAgent")
        return create_search_workflow(
            model_provider=model_provider,
            model_name=model_name,
            task_id=task_id,
            task_name=task_name,
            task_description=task_description,
            runtime_output_path=runtime_output_path,
            log_callback=log_callback,
            session_id=session_id
        )
    
    elif task_type == "code_generation":
        logger.info("Routing to CodeAgent (Architect+Executor)")
        create_code_workflow = _get_code_workflow()
        return create_code_workflow(
            model_provider=model_provider,
            model_name=model_name,
            task_id=task_id,
            task_name=task_name,
            task_description=task_description,
            runtime_output_path=runtime_output_path,
            execute_code_func=execute_code_func,
            log_callback=log_callback,
            session_id=session_id,
            task_type=task_type
        )
    
    elif task_type == "scraping":
        # TODO: Implement ScrapingAgent in Phase 5
        logger.warning(f"ScrapingAgent not yet implemented, falling back to CodeAgent")
        create_code_workflow = _get_code_workflow()
        return create_code_workflow(
            model_provider=model_provider,
            model_name=model_name,
            task_id=task_id,
            task_name=task_name,
            task_description=task_description,
            runtime_output_path=runtime_output_path,
            execute_code_func=execute_code_func,
            log_callback=log_callback,
            session_id=session_id,
            task_type=task_type
        )
    
    elif task_type == "rag":
        # TODO: Implement RAGAgent in Phase 5
        logger.warning(f"RAGAgent not yet implemented, falling back to CodeAgent")
        create_code_workflow = _get_code_workflow()
        return create_code_workflow(
            model_provider=model_provider,
            model_name=model_name,
            task_id=task_id,
            task_name=task_name,
            task_description=task_description,
            runtime_output_path=runtime_output_path,
            execute_code_func=execute_code_func,
            log_callback=log_callback,
            session_id=session_id,
            task_type=task_type
        )
    
    else:
        # Unknown task type, default to CodeAgent
        logger.warning(f"Unknown task type '{task_type}', defaulting to CodeAgent")
        create_code_workflow = _get_code_workflow()
        return create_code_workflow(
            model_provider=model_provider,
            model_name=model_name,
            task_id=task_id,
            task_name=task_name,
            task_description=task_description,
            runtime_output_path=runtime_output_path,
            execute_code_func=execute_code_func,
            log_callback=log_callback,
            session_id=session_id,
            task_type=task_type or "code_generation"
        )
