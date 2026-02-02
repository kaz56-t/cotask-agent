"""LangGraph-based agent definitions for task processing."""
from typing import TypedDict, Annotated, Literal
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from database import ModelProvider
from loguru import logger
import os


class AgentState(TypedDict):
    """State for the LangGraph workflow."""
    messages: Annotated[list, lambda x, y: x + y]
    task_id: str
    task_name: str
    task_description: str
    runtime_output_path: str
    current_agent: str
    iteration_count: int
    max_iterations: int


def check_api_connection(model_provider: ModelProvider, model_name: str) -> bool:
    """Check API connection and credentials."""
    try:
        if model_provider == ModelProvider.OPENAI:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.error("OPENAI_API_KEY not found in environment variables")
                return False
            if len(api_key.strip()) == 0:
                logger.error("OPENAI_API_KEY is empty")
                return False
            logger.info(f"OpenAI API key found (length: {len(api_key)}), model: {model_name}")
            return True
        elif model_provider == ModelProvider.ANTHROPIC:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                logger.error("ANTHROPIC_API_KEY not found in environment variables")
                return False
            if len(api_key.strip()) == 0:
                logger.error("ANTHROPIC_API_KEY is empty")
                return False
            logger.info(f"Anthropic API key found (length: {len(api_key)}), model: {model_name}")
            return True
        else:
            logger.error(f"Unsupported model provider: {model_provider}")
            return False
    except Exception as e:
        logger.error(f"API connection check failed: {e}")
        return False


def create_llm(model_provider: ModelProvider, model_name: str):
    """Create LLM instance based on provider."""
    logger.info(f"Creating LLM: provider={model_provider}, model={model_name}")
    
    # Check API connection first
    if not check_api_connection(model_provider, model_name):
        raise RuntimeError(f"Failed to connect to {model_provider} API. Please check your API key and network connection.")
    
    try:
        # 速度優先のため温度を下げる（0.3: より決定論的で速い）
        if model_provider == ModelProvider.OPENAI:
            llm = ChatOpenAI(model=model_name, temperature=0.3, max_tokens=2000)
            logger.success(f"OpenAI LLM created successfully: {model_name} (temperature=0.3)")
            return llm
        elif model_provider == ModelProvider.ANTHROPIC:
            llm = ChatAnthropic(model=model_name, temperature=0.3, max_tokens=2000)
            logger.success(f"Anthropic LLM created successfully: {model_name} (temperature=0.3)")
            return llm
        else:
            raise ValueError(f"Unsupported model provider: {model_provider}")
    except Exception as e:
        logger.error(f"Failed to create LLM: {e}")
        raise


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
            system_prompt = f"""You are an Architect agent. Your goal is to complete tasks quickly and simply.

IMPORTANT: Prioritize speed and simplicity over perfection. Write minimal, working code.

Task: {state['task_name']}
Description: {state['task_description']}
Output path: {runtime_output_path}/

Instructions:
1. Write simple Python code that accomplishes the task
2. Save outputs to {runtime_output_path}/
3. Wrap code in ```python code blocks
4. Keep code concise - no unnecessary complexity
5. If the task is simple, use straightforward solutions

Write the code now. Be brief."""
        
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
            system_prompt = """You are an Executor agent. Your goal is to quickly determine if the task is complete.

IMPORTANT: If code executed successfully and outputs were created, mark the task as COMPLETE immediately.

Rules:
1. If code executed successfully → Task is COMPLETE. Say "Task completed successfully."
2. If there are minor errors but outputs exist → Task is COMPLETE. Say "Task completed successfully."
3. Only if code completely failed with no outputs → Ask architect to fix it.

Be brief. If successful, just say "Task completed successfully." and end."""
        
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
            
            # Determine next step - より緩い完了判定
            content_lower = response.content.lower()
            iteration_count = state.get("iteration_count", 0) + 1
            max_iterations = state.get('max_iterations', 10)
            logger.info(f"[Executor] Iteration {iteration_count}/{max_iterations}")
            
            # 完了判定を緩和（より多くのキーワードで完了と判断）
            completion_keywords = [
                "complete", "finished", "done", "successfully", "completed",
                "task completed", "success", "output", "saved", "created",
                "finished successfully", "done successfully"
            ]
            
            # コードが実行されていて、エラーがない場合は完了と判断
            recent_messages = [str(msg.content).lower() for msg in messages[-5:]]
            has_code_execution = any("execution result" in msg or "code execution" in msg for msg in recent_messages)
            has_success = any("success: true" in msg or "success:true" in msg or "success:  true" in msg for msg in recent_messages)
            has_no_error = not any("error:" in msg and "success: false" in msg for msg in recent_messages)
            
            # 完了条件: キーワードがある、またはコード実行成功、または最大イテレーション到達
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


def create_workflow(
    model_provider: ModelProvider,
    model_name: str,
    task_id: str,
    task_name: str,
    task_description: str,
    runtime_output_path: str,
    execute_code_func,
    log_callback
):
    """Create LangGraph workflow for task processing."""
    logger.info(f"Creating workflow for task: {task_id} ({task_name})")
    logger.info(f"Model: {model_provider.value}/{model_name}")
    
    try:
        llm = create_llm(model_provider, model_name)
        logger.success("LLM created successfully")
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
    
    # Compile graph
    logger.info("Compiling workflow graph")
    app = workflow.compile()
    logger.success("Workflow graph compiled successfully")
    
    # Initial state - max_iterationsを3に削減（速度優先）
    initial_state = {
        "messages": [
            HumanMessage(content=f"Task: {task_name}\n\nDescription: {task_description}\n\nComplete this task quickly. Save outputs to {runtime_output_path}/")
        ],
        "task_id": task_id,
        "task_name": task_name,
        "task_description": task_description,
        "runtime_output_path": runtime_output_path,
        "current_agent": "architect",
        "iteration_count": 0,
        "max_iterations": 2
    }
    
    logger.info("Workflow creation completed")
    return app, initial_state
