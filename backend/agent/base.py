"""Base classes and utilities for agents."""
from typing import TypedDict, Annotated, Optional, List
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.callbacks import BaseCallbackHandler
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
    task_type: Optional[str]  # Task type: code_generation, web_search, text_generation, scraping, rag, simple_text


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


def create_llm(
    model_provider: ModelProvider,
    model_name: str,
    callbacks: Optional[List[BaseCallbackHandler]] = None
):
    """Create LLM instance based on provider."""
    logger.info(f"Creating LLM: provider={model_provider}, model={model_name}")
    
    # Check API connection first
    if not check_api_connection(model_provider, model_name):
        raise RuntimeError(f"Failed to connect to {model_provider} API. Please check your API key and network connection.")
    
    try:
        # Lower temperature for speed priority (0.3: more deterministic and faster)
        if model_provider == ModelProvider.OPENAI:
            llm = ChatOpenAI(
                model=model_name,
                temperature=0.3,
                max_tokens=2000,
                callbacks=callbacks
            )
            logger.success(f"OpenAI LLM created successfully: {model_name} (temperature=0.3)")
            return llm
        elif model_provider == ModelProvider.ANTHROPIC:
            llm = ChatAnthropic(
                model=model_name,
                temperature=0.3,
                max_tokens=2000,
                callbacks=callbacks
            )
            logger.success(f"Anthropic LLM created successfully: {model_name} (temperature=0.3)")
            return llm
        else:
            raise ValueError(f"Unsupported model provider: {model_provider}")
    except Exception as e:
        logger.error(f"Failed to create LLM: {e}")
        raise
