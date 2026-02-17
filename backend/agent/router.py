"""
Agent Router: Routes tasks to appropriate agents based on task type.
"""
from typing import Optional, Tuple, Any
from database import ModelProvider
from loguru import logger

# Import agent workflows
from agent.text_agent import create_text_workflow
from agent.search_agent import create_search_workflow
from agent.simple_code_agent import create_simple_code_workflow

# Import CodeAgent workflow (avoid circular import by importing function directly)
def _get_code_workflow():
    """Lazy import to avoid circular dependencies."""
    from agent.code_agent import create_code_workflow
    return create_code_workflow


def route_task(
    task_type: str,
    complexity: str,
    estimated_iterations: int,
    model_provider: ModelProvider,
    model_name: str,
    task_id: str,
    task_name: str,
    task_description: str,
    runtime_output_path: str,
    execute_code_func,
    log_callback,
    session_id: Optional[str] = None
) -> Tuple[Any, dict]:
    """
    Route task to appropriate agent based on task type and complexity.

    Args:
        task_type: Task type (code_generation, web_search, text_generation, etc.)
        complexity: Task complexity (simple, medium, complex)
        estimated_iterations: Estimated number of iterations needed
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
    logger.info(f"Routing task to agent based on type: {task_type}, complexity: {complexity}")
    
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
        # Phase 4: Route simple code tasks to SimpleChatAgent
        if complexity == "simple":
            logger.info("Routing to SimpleChatAgent (simple code task)")
            return create_simple_code_workflow(
                model_provider=model_provider,
                model_name=model_name,
                task_id=task_id,
                task_name=task_name,
                task_description=task_description,
                runtime_output_path=runtime_output_path,
                execute_code_func=execute_code_func,
                log_callback=log_callback,
                session_id=session_id,
                estimated_iterations=estimated_iterations
            )
        else:
            # Medium or complex tasks use full Architect+Executor pattern
            logger.info(f"Routing to CodeAgent (Architect+Executor) for {complexity} task")
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
                task_type=task_type,
                estimated_iterations=estimated_iterations
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
            task_type=task_type,
            estimated_iterations=estimated_iterations
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
            task_type=task_type,
            estimated_iterations=estimated_iterations
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
            task_type=task_type or "code_generation",
            estimated_iterations=estimated_iterations
        )
