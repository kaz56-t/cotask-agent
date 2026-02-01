"""LangGraph-based agent definitions for task processing."""
from typing import TypedDict, Annotated, Literal
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from database import ModelProvider
import logging

logger = logging.getLogger(__name__)


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


def create_llm(model_provider: ModelProvider, model_name: str):
    """Create LLM instance based on provider."""
    if model_provider == ModelProvider.OPENAI:
        return ChatOpenAI(model=model_name, temperature=0.7)
    elif model_provider == ModelProvider.ANTHROPIC:
        return ChatAnthropic(model=model_name, temperature=0.7)
    else:
        raise ValueError(f"Unsupported model provider: {model_provider}")


def create_architect_node(
    llm,
    task_id: str,
    runtime_output_path: str,
    log_callback
):
    """Create architect node that designs solutions."""
    def architect_node(state: AgentState) -> AgentState:
        """Architect agent: designs the solution and creates code."""
        log_callback("architect", "Architect is analyzing the task and designing a solution...")
        
        system_prompt = f"""You are an Architect agent responsible for designing solutions and writing code.

Your role:
1. Analyze the task requirements carefully
2. Design a solution approach
3. Write Python code to implement the solution
4. Ensure code saves outputs to {runtime_output_path}/

When you write code, use the execute_code function to run it. The code will be executed in a runtime container.

Current task: {state['task_name']}
Description: {state['task_description']}
Output path: {runtime_output_path}/

Provide clear, well-commented code that accomplishes the task."""
        
        messages = state['messages'].copy()
        if not any(isinstance(msg, SystemMessage) for msg in messages):
            messages.insert(0, SystemMessage(content=system_prompt))
        
        # Get response from LLM
        response = llm.invoke(messages)
        messages.append(response)
        
        log_callback("architect", response.content)
        
        # Architect always passes to executor
        new_state = {
            **state,
            "messages": messages,
            "current_agent": "executor"
        }
        return new_state
    
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
        log_callback("executor", "Executor is reviewing the code and execution results...")
        
        system_prompt = """You are an Executor agent responsible for executing code and analyzing results.

Your role:
1. Review code that was executed
2. Analyze execution results (success or errors)
3. Determine if the task is complete or if more work is needed
4. If the task is complete, summarize the results
5. If there are errors or the task needs more work, provide feedback to the architect

When code execution succeeds, verify that the outputs match the requirements.
When code execution fails, analyze the error and suggest fixes."""
        
        messages = state['messages'].copy()
        if not any(isinstance(msg, SystemMessage) for msg in messages):
            messages.insert(0, SystemMessage(content=system_prompt))
        
        # Check if the last message contains code to execute
        last_message = messages[-1] if messages else None
        if last_message and isinstance(last_message, AIMessage):
            content = last_message.content
            
            # Try to extract and execute Python code
            if "```python" in content or "```" in content:
                # Extract code blocks
                import re
                code_blocks = re.findall(r'```(?:python)?\n(.*?)```', content, re.DOTALL)
                
                for code in code_blocks:
                    if code.strip():
                        log_callback("executor", f"Executing code:\n{code[:200]}...")
                        execution_result = execute_code_func(code.strip())
                        messages.append(HumanMessage(content=f"Code execution result:\n{execution_result}"))
                        log_callback("executor", f"Execution result: {execution_result[:500]}...")
        
        # Get response from LLM
        response = llm.invoke(messages)
        messages.append(response)
        
        log_callback("executor", response.content)
        
        # Determine next step
        content_lower = response.content.lower()
        if any(word in content_lower for word in ["complete", "finished", "done", "successfully completed"]):
            return {
                **state,
                "messages": messages,
                "current_agent": "end"
            }
        else:
            return {
                **state,
                "messages": messages,
                "current_agent": "architect",
                "iteration_count": state.get("iteration_count", 0) + 1
            }
    
    return executor_node


def should_continue(state: AgentState) -> Literal["architect", "__end__"]:
    """Determine which node to go to next after executor."""
    if state.get("current_agent") == "end":
        return "__end__"
    
    iteration_count = state.get("iteration_count", 0)
    max_iterations = state.get("max_iterations", 50)
    
    if iteration_count >= max_iterations:
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
    llm = create_llm(model_provider, model_name)
    
    # Create nodes
    architect = create_architect_node(llm, task_id, runtime_output_path, log_callback)
    executor = create_executor_node(llm, task_id, execute_code_func, log_callback)
    
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
    app = workflow.compile()
    
    # Initial state
    initial_state = {
        "messages": [
            HumanMessage(content=f"Task: {task_name}\n\nDescription: {task_description}\n\nPlease complete this task. Output files should be saved to {runtime_output_path}/")
        ],
        "task_id": task_id,
        "task_name": task_name,
        "task_description": task_description,
        "runtime_output_path": runtime_output_path,
        "current_agent": "architect",
        "iteration_count": 0,
        "max_iterations": 50
    }
    
    return app, initial_state
