"""
SimpleChatAgent: Simple code generation tasks with direct execution.
Handles simple code generation tasks without the Architect+Executor overhead.
Uses a simple 1-2 node LangGraph workflow with code execution capability.
"""
from typing import Optional, Literal
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from database import ModelProvider
from agent.base import AgentState, create_llm
from loguru import logger
from langfuse_config import get_langfuse_handler
from prompts.simple_code_agent import get_simple_code_agent_prompt
import re


def create_simple_code_agent_node(
    llm,
    task_id: str,
    runtime_output_path: str,
    execute_code_func,
    log_callback
):
    """Create simple code agent node that generates and executes code efficiently."""
    def simple_code_agent_node(state: AgentState) -> AgentState:
        """Simple code agent: generates code, executes it, and reports results."""
        logger.info(f"[SimpleChatAgent] Processing task: {state['task_name']}")
        log_callback("simple_code_agent", "SimpleChatAgent is generating and executing code...")

        try:
            system_prompt = get_simple_code_agent_prompt(
                task_name=state['task_name'],
                task_description=state['task_description'],
                runtime_output_path=runtime_output_path
            )

            messages = state['messages'].copy()
            if not any(isinstance(msg, SystemMessage) for msg in messages):
                messages.insert(0, SystemMessage(content=system_prompt))

            logger.debug(f"[SimpleChatAgent] Invoking LLM with {len(messages)} messages")
            response = llm.invoke(messages)
            logger.success(f"[SimpleChatAgent] Received response (length: {len(response.content)} chars)")
            messages.append(response)

            log_callback("simple_code_agent", response.content)

            # Check for code blocks and execute them
            content = response.content
            code_blocks = re.findall(r'```(?:python)?\n(.*?)```', content, re.DOTALL)

            executed_code = False
            has_error = False

            if code_blocks:
                logger.info(f"[SimpleChatAgent] Found {len(code_blocks)} code block(s)")
                for idx, code in enumerate(code_blocks):
                    if code.strip():
                        logger.info(f"[SimpleChatAgent] Executing code block {idx + 1}/{len(code_blocks)}")
                        log_callback("simple_code_agent", f"Executing code:\n{code[:200]}...")

                        execution_result = execute_code_func(code.strip())
                        executed_code = True

                        # Check for errors
                        if "Success: False" in execution_result or "Error:" in execution_result:
                            has_error = True

                        messages.append(HumanMessage(content=f"Code execution result:\n{execution_result}"))
                        logger.success(f"[SimpleChatAgent] Code execution completed")
                        log_callback("simple_code_agent", f"Execution result: {execution_result[:500]}...")

            # Determine completion status
            iteration_count = state.get("iteration_count", 0) + 1
            max_iterations = state.get('max_iterations', 1)
            logger.info(f"[SimpleChatAgent] Iteration {iteration_count}/{max_iterations}")

            # Completion logic for simple tasks:
            # - If no code was executed, consider it complete (pure text task)
            # - If code was executed successfully (no errors), consider it complete
            # - If code was executed with errors and iterations remain, try again
            # - If max iterations reached, complete anyway

            is_complete = (
                not executed_code or  # No code to execute
                (executed_code and not has_error) or  # Code executed successfully
                iteration_count >= max_iterations  # Max iterations reached
            )

            if is_complete:
                logger.success(f"[SimpleChatAgent] Task completed (iteration {iteration_count})")
                return {
                    **state,
                    "messages": messages,
                    "current_agent": "end",
                    "iteration_count": iteration_count
                }
            else:
                logger.info("[SimpleChatAgent] Task needs retry due to execution error")
                # Add feedback message for retry
                messages.append(HumanMessage(content="The code execution encountered an error. Please fix the issue and try again. Save outputs to the correct path."))
                return {
                    **state,
                    "messages": messages,
                    "current_agent": "simple_code_agent",
                    "iteration_count": iteration_count
                }

        except Exception as e:
            logger.error(f"[SimpleChatAgent] Error occurred: {e}", exc_info=True)
            log_callback("simple_code_agent", f"Error: {str(e)}")
            raise

    return simple_code_agent_node


def should_continue_simple(state: AgentState) -> Literal["simple_code_agent", "__end__"]:
    """Determine whether to continue or end."""
    if state.get("current_agent") == "end":
        return "__end__"

    iteration_count = state.get("iteration_count", 0)
    max_iterations = state.get("max_iterations", 1)

    if iteration_count >= max_iterations:
        logger.warning(f"Reached max iterations ({max_iterations}), ending workflow")
        return "__end__"

    return "simple_code_agent"


def create_simple_code_workflow(
    model_provider: ModelProvider,
    model_name: str,
    task_id: str,
    task_name: str,
    task_description: str,
    runtime_output_path: str,
    execute_code_func,
    log_callback,
    session_id: Optional[str] = None,
    estimated_iterations: int = 1
):
    """Create LangGraph workflow for simple code generation tasks."""
    logger.info(f"Creating SimpleChatAgent workflow for task: {task_id} ({task_name})")
    logger.info(f"Model: {model_provider.value}/{model_name}")
    logger.info(f"Estimated iterations: {estimated_iterations}")

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

    # Create simple code agent node
    logger.info("Creating simple code agent node")
    simple_code_agent = create_simple_code_agent_node(
        llm, task_id, runtime_output_path, execute_code_func, log_callback
    )
    logger.success("Simple code agent node created successfully")

    # Create graph
    workflow = StateGraph(AgentState)
    workflow.add_node("simple_code_agent", simple_code_agent)
    workflow.set_entry_point("simple_code_agent")

    # Add conditional edge for potential retry
    workflow.add_conditional_edges(
        "simple_code_agent",
        should_continue_simple,
        {
            "simple_code_agent": "simple_code_agent",
            "__end__": END
        }
    )

    # Compile graph
    logger.info("Compiling workflow graph")
    app = workflow.compile()
    logger.success("Workflow graph compiled successfully")

    # Initial state - use estimated_iterations for simple tasks (typically 1)
    initial_state = {
        "messages": [
            HumanMessage(content=f"Task: {task_name}\n\nDescription: {task_description}\n\nComplete this simple task efficiently. Save outputs to {runtime_output_path}/")
        ],
        "task_id": task_id,
        "task_name": task_name,
        "task_description": task_description,
        "runtime_output_path": runtime_output_path,
        "current_agent": "simple_code_agent",
        "iteration_count": 0,
        "max_iterations": max(1, estimated_iterations),  # At least 1 iteration
        "task_type": "code_generation"
    }

    logger.info("SimpleChatAgent workflow creation completed")
    return app, initial_state
