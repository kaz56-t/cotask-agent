"""
CodeAgent: Code generation tasks using Architect+Executor pattern.
Handles tasks that require code generation and execution.
Uses a 2-node LangGraph workflow: architect -> executor.
"""
from typing import Literal, Optional
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from database import ModelProvider
from agent.base import AgentState, create_llm
from loguru import logger
from langfuse_config import get_langfuse_handler
from prompts.code_agent import get_architect_prompt, EXECUTOR_PROMPT


def create_architect_node(
    llm,
    task_id: str,
    runtime_output_path: str,
    log_callback
):
    """Create architect node that designs solutions."""
    def architect_node(state: AgentState) -> AgentState:
        """Architect agent: designs the solution and creates code."""
        logger.info(f"[Architect] Starting analysis for task: {state['task_name']}")
        log_callback("architect", "Architect is analyzing the task and designing a solution...")
        
        try:
            system_prompt = get_architect_prompt(
                task_name=state['task_name'],
                task_description=state['task_description'],
                runtime_output_path=runtime_output_path
            )
        
            messages = state['messages'].copy()
            if not any(isinstance(msg, SystemMessage) for msg in messages):
                messages.insert(0, SystemMessage(content=system_prompt))
            
            logger.debug(f"[Architect] Invoking LLM with {len(messages)} messages")
            # Get response from LLM
            response = llm.invoke(messages)
            logger.success(f"[Architect] Received response from LLM (length: {len(response.content)} chars)")
            messages.append(response)
            
            log_callback("architect", response.content)
            
            # Architect always passes to executor
            new_state = {
                **state,
                "messages": messages,
                "current_agent": "executor"
            }
            logger.info("[Architect] Task completed, passing to executor")
            return new_state
        except Exception as e:
            logger.error(f"[Architect] Error occurred: {e}", exc_info=True)
            log_callback("architect", f"Error: {str(e)}")
            raise
    
    return architect_node


def create_executor_node(
    llm,
    task_id: str,
    execute_code_func,
    log_callback
):
    """Create executor node that executes code."""
    def executor_node(state: AgentState) -> AgentState:
        """Executor agent: executes code and reports results."""
        logger.info(f"[Executor] Starting review for task: {state['task_name']}")
        log_callback("executor", "Executor is reviewing the code and execution results...")
        
        try:
            system_prompt = EXECUTOR_PROMPT
        
            messages = state['messages'].copy()
            if not any(isinstance(msg, SystemMessage) for msg in messages):
                messages.insert(0, SystemMessage(content=system_prompt))
            
            # Check if the last message contains code to execute
            last_message = messages[-1] if messages else None
            if last_message and isinstance(last_message, AIMessage):
                content = last_message.content
                logger.debug(f"[Executor] Checking for code blocks in last message (length: {len(content)} chars)")
                
                # Try to extract and execute Python code
                if "```python" in content or "```" in content:
                    # Extract code blocks
                    import re
                    code_blocks = re.findall(r'```(?:python)?\n(.*?)```', content, re.DOTALL)
                    logger.info(f"[Executor] Found {len(code_blocks)} code block(s)")
                    
                    for idx, code in enumerate(code_blocks):
                        if code.strip():
                            logger.info(f"[Executor] Executing code block {idx + 1}/{len(code_blocks)}")
                            log_callback("executor", f"Executing code:\n{code[:200]}...")
                            execution_result = execute_code_func(code.strip())
                            messages.append(HumanMessage(content=f"Code execution result:\n{execution_result}"))
                            logger.success(f"[Executor] Code execution completed: {execution_result[:100]}...")
                            log_callback("executor", f"Execution result: {execution_result[:500]}...")
            
            logger.debug(f"[Executor] Invoking LLM with {len(messages)} messages")
            # Get response from LLM
            response = llm.invoke(messages)
            logger.success(f"[Executor] Received response from LLM (length: {len(response.content)} chars)")
            messages.append(response)
            
            log_callback("executor", response.content)
            
            # Determine next step - more lenient completion check
            content_lower = response.content.lower()
            iteration_count = state.get("iteration_count", 0) + 1
            max_iterations = state.get('max_iterations', 10)
            logger.info(f"[Executor] Iteration {iteration_count}/{max_iterations}")
            
            # Relax completion check (judge as complete with more keywords)
            completion_keywords = [
                "complete", "finished", "done", "successfully", "completed",
                "task completed", "success", "output", "saved", "created",
                "finished successfully", "done successfully"
            ]
            
            # If code was executed and there are no errors, judge as complete
            recent_messages = [str(msg.content).lower() for msg in messages[-5:]]
            has_code_execution = any("execution result" in msg or "code execution" in msg for msg in recent_messages)
            has_success = any("success: true" in msg or "success:true" in msg or "success:  true" in msg for msg in recent_messages)
            has_no_error = not any("error:" in msg and "success: false" in msg for msg in recent_messages)
            
            # Completion condition: keywords exist, or code execution succeeded, or max iterations reached
            is_complete = (
                any(keyword in content_lower for keyword in completion_keywords) or 
                (has_code_execution and has_success and has_no_error) or
                iteration_count >= max_iterations
            )
            
            if is_complete:
                logger.success(f"[Executor] Task marked as complete (iteration {iteration_count})")
                return {
                    **state,
                    "messages": messages,
                    "current_agent": "end"
                }
            else:
                logger.info("[Executor] Task needs more work, returning to architect")
                return {
                    **state,
                    "messages": messages,
                    "current_agent": "architect",
                    "iteration_count": iteration_count
                }
        except Exception as e:
            logger.error(f"[Executor] Error occurred: {e}", exc_info=True)
            log_callback("executor", f"Error: {str(e)}")
            raise
    
    return executor_node


def should_continue(state: AgentState) -> Literal["architect", "__end__"]:
    """Determine which node to go to next after executor."""
    if state.get("current_agent") == "end":
        return "__end__"
    
    iteration_count = state.get("iteration_count", 0)
    max_iterations = state.get("max_iterations", 2)
    
    if iteration_count >= max_iterations:
        logger.warning(f"Reached max iterations ({max_iterations}), ending workflow")
        return "__end__"
    
    # Executor decides: continue with architect or end
    # If current_agent is still "executor", it means we need more work
    # If current_agent is "end", we're done
    if state.get("current_agent") == "end":
        return "__end__"
    else:
        # Need more work, go back to architect
        return "architect"


def create_code_workflow(
    model_provider: ModelProvider,
    model_name: str,
    task_id: str,
    task_name: str,
    task_description: str,
    runtime_output_path: str,
    execute_code_func,
    log_callback,
    session_id: Optional[str] = None,
    task_type: Optional[str] = None,
    estimated_iterations: int = 2
):
    """Create LangGraph workflow for code generation tasks (Architect+Executor)."""
    logger.info(f"Creating CodeAgent workflow for task: {task_id} ({task_name})")
    logger.info(f"Model: {model_provider.value}/{model_name}")
    logger.info(f"Estimated iterations: {estimated_iterations}")
    if task_type:
        logger.info(f"Task type: {task_type}")
    
    # Get Langfuse callback handler
    langfuse_handler = get_langfuse_handler(
        task_id=task_id,
        session_id=session_id
    )
    callbacks = [langfuse_handler] if langfuse_handler else None
    
    try:
        llm = create_llm(model_provider, model_name, callbacks=callbacks)
        logger.success("LLM created successfully")
        if langfuse_handler:
            logger.info("Langfuse tracking enabled for this workflow")
    except Exception as e:
        logger.error(f"Failed to create LLM: {e}")
        raise
    
    # Create nodes
    logger.info("Creating architect and executor nodes")
    architect = create_architect_node(llm, task_id, runtime_output_path, log_callback)
    executor = create_executor_node(llm, task_id, execute_code_func, log_callback)
    logger.success("Nodes created successfully")
    
    # Create graph
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("architect", architect)
    workflow.add_node("executor", executor)
    
    # Set entry point
    workflow.set_entry_point("architect")
    
    # Architect always goes to executor
    workflow.add_edge("architect", "executor")
    
    workflow.add_conditional_edges(
        "executor",
        should_continue,
        {
            "architect": "architect",
            "__end__": END
        }
    )
    
    # Compile graph with Langfuse callbacks if available
    logger.info("Compiling workflow graph")
    compile_kwargs = {}
    if langfuse_handler:
        compile_kwargs["checkpointer"] = None  # Add checkpointer if needed
        logger.info("Langfuse callbacks will be used during workflow execution")
    
    app = workflow.compile(**compile_kwargs)
    logger.success("Workflow graph compiled successfully")

    # Initial state - use estimated_iterations (dynamically set based on complexity)
    # Ensure max_iterations is at least 2 for complex tasks
    max_iterations = max(2, estimated_iterations)
    logger.info(f"Setting max_iterations to {max_iterations}")

    initial_state = {
        "messages": [
            HumanMessage(content=f"Task: {task_name}\n\nDescription: {task_description}\n\nComplete this task efficiently. Save outputs to {runtime_output_path}/")
        ],
        "task_id": task_id,
        "task_name": task_name,
        "task_description": task_description,
        "runtime_output_path": runtime_output_path,
        "current_agent": "architect",
        "iteration_count": 0,
        "max_iterations": max_iterations,
        "task_type": task_type or "code_generation"  # Default to code_generation if not specified
    }

    logger.info("CodeAgent workflow creation completed")
    return app, initial_state
