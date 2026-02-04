"""
SearchAgent: Web search tasks using DuckDuckGo.
Handles web search queries and summarizes results.
Uses a 2-node LangGraph workflow: search -> summarize.
"""
from typing import Optional, List
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from database import ModelProvider
from agent.base import AgentState, create_llm
from loguru import logger
from langfuse_config import get_langfuse_handler
from prompts.search_agent import get_summarizer_prompt
from pathlib import Path

from duckduckgo_search import DDGS


def search_web(query: str, max_results: int = 5) -> List[dict]:
    """
    Search the web using DuckDuckGo.
    
    Args:
        query: Search query string
        max_results: Maximum number of results to return
        
    Returns:
        List of search results with 'title', 'link', 'snippet' keys
    """
    try:
        logger.info(f"Searching DuckDuckGo for: {query}")
        with DDGS() as ddgs:
            results = []
            for result in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": result.get("title", ""),
                    "link": result.get("href", ""),
                    "snippet": result.get("body", "")
                })
            logger.success(f"Found {len(results)} search results")
            return results
    except Exception as e:
        logger.error(f"Error searching DuckDuckGo: {e}", exc_info=True)
        return []


def create_search_node(
    task_id: str,
    log_callback
):
    """Create search node that performs web search."""
    def search_node(state: AgentState) -> AgentState:
        """Search node: performs web search based on task description."""
        logger.info(f"[SearchAgent] Performing web search for: {state['task_name']}")
        log_callback("search", "SearchAgent is searching the web...")
        
        try:
            # Extract search query from task description
            task_description = state['task_description']
            
            # Try to extract search query from messages if available
            search_query = task_description
            if state['messages']:
                last_message = state['messages'][-1]
                if isinstance(last_message, HumanMessage):
                    # Use the last human message as search query
                    search_query = last_message.content
                elif isinstance(last_message, AIMessage):
                    # If AI suggested a query, use it
                    search_query = last_message.content
            
            # Perform web search
            search_results = search_web(search_query, max_results=5)
            
            if not search_results:
                error_msg = "No search results found. Please check your query or try again."
                logger.warning(f"[SearchAgent] {error_msg}")
                log_callback("search", error_msg)
                messages = state['messages'].copy()
                messages.append(AIMessage(content=error_msg))
                return {
                    **state,
                    "messages": messages,
                    "current_agent": "summarizer"
                }
            
            # Format search results
            results_text = "Search Results:\n\n"
            for i, result in enumerate(search_results, 1):
                results_text += f"{i}. {result['title']}\n"
                results_text += f"   URL: {result['link']}\n"
                results_text += f"   Summary: {result['snippet']}\n\n"
            
            logger.success(f"[SearchAgent] Retrieved {len(search_results)} search results")
            log_callback("search", f"Found {len(search_results)} results:\n{results_text[:500]}...")
            
            # Add search results to messages
            messages = state['messages'].copy()
            messages.append(AIMessage(content=f"Search completed. Found {len(search_results)} results:\n\n{results_text}"))
            
            return {
                **state,
                "messages": messages,
                "current_agent": "summarizer"
            }
            
        except Exception as e:
            logger.error(f"[SearchAgent] Error in search node: {e}", exc_info=True)
            log_callback("search", f"Error: {str(e)}")
            raise
    
    return search_node


def create_summarizer_node(
    llm,
    task_id: str,
    runtime_output_path: str,
    log_callback
):
    """Create summarizer node that summarizes search results."""
    def summarizer_node(state: AgentState) -> AgentState:
        """Summarizer node: summarizes search results and saves output."""
        logger.info(f"[SearchAgent] Summarizing search results for: {state['task_name']}")
        log_callback("summarizer", "SearchAgent is summarizing search results...")
        
        try:
            system_prompt = get_summarizer_prompt(
                task_name=state['task_name'],
                task_description=state['task_description'],
                runtime_output_path=runtime_output_path
            )

            messages = state['messages'].copy()
            if not any(isinstance(msg, SystemMessage) for msg in messages):
                messages.insert(0, SystemMessage(content=system_prompt))
            
            logger.debug(f"[SearchAgent] Invoking LLM with {len(messages)} messages")
            response = llm.invoke(messages)
            logger.success(f"[SearchAgent] Received summary (length: {len(response.content)} chars)")
            messages.append(response)
            
            log_callback("summarizer", response.content)
            
            # Save summary to file as markdown (text content as artifact)
            try:
                task_name_safe = "".join(c for c in state['task_name'] if c.isalnum() or c in (' ', '-', '_')).strip()
                task_name_safe = task_name_safe.replace(' ', '_')[:50]
                
                file_path = Path(runtime_output_path) / f"{task_name_safe}_search_summary.md"
                file_path.write_text(response.content, encoding='utf-8')
                
                logger.success(f"[SearchAgent] Saved summary to {file_path}")
                log_callback("summarizer", f"Summary saved to: {file_path}")
                
            except Exception as e:
                logger.warning(f"[SearchAgent] Could not save file: {e}")
            
            # SearchAgent completes after summarization
            new_state = {
                **state,
                "messages": messages,
                "current_agent": "end"
            }
            logger.info("[SearchAgent] Task completed")
            return new_state
            
        except Exception as e:
            logger.error(f"[SearchAgent] Error in summarizer node: {e}", exc_info=True)
            log_callback("summarizer", f"Error: {str(e)}")
            raise
    
    return summarizer_node


def create_search_workflow(
    model_provider: ModelProvider,
    model_name: str,
    task_id: str,
    task_name: str,
    task_description: str,
    runtime_output_path: str,
    log_callback,
    session_id: Optional[str] = None
):
    """Create LangGraph workflow for web search tasks."""
    logger.info(f"Creating SearchAgent workflow for task: {task_id} ({task_name})")
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
    
    # Create nodes
    logger.info("Creating search and summarizer nodes")
    search = create_search_node(task_id, log_callback)
    summarizer = create_summarizer_node(llm, task_id, runtime_output_path, log_callback)
    logger.success("Nodes created successfully")
    
    # Create graph (2-node workflow: search -> summarize)
    workflow = StateGraph(AgentState)
    workflow.add_node("search", search)
    workflow.add_node("summarizer", summarizer)
    workflow.set_entry_point("search")
    workflow.add_edge("search", "summarizer")
    workflow.add_edge("summarizer", END)
    
    # Compile graph
    logger.info("Compiling workflow graph")
    app = workflow.compile()
    logger.success("Workflow graph compiled successfully")
    
    # Initial state
    initial_state = {
        "messages": [
            HumanMessage(content=f"Task: {task_name}\n\nDescription: {task_description}\n\nSearch the web and provide a comprehensive summary.")
        ],
        "task_id": task_id,
        "task_name": task_name,
        "task_description": task_description,
        "runtime_output_path": runtime_output_path,
        "current_agent": "search",
        "iteration_count": 0,
        "max_iterations": 2,  # SearchAgent: search + summarize
        "task_type": "web_search"
    }
    
    logger.info("SearchAgent workflow creation completed")
    return app, initial_state
