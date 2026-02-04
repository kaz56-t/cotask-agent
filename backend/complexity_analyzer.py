"""
Task complexity and type analysis module.
Analyzes tasks to determine their type and complexity for optimal agent selection.
"""
from typing import Literal, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.callbacks import BaseCallbackHandler
from database import ModelProvider
from agents import create_llm
from loguru import logger
import json
import re

# Task type definitions
TaskType = Literal[
    "code_generation",  # Requires Python code generation and execution
    "web_search",      # Requires web search capabilities
    "text_generation", # Simple text generation/editing (emails, reports, summaries)
    "scraping",        # Web scraping tasks
    "rag",             # Document search and Q&A
    "simple_text"      # Very simple text processing
]


def classify_task_type(
    task_name: str,
    task_description: str,
    model_provider: ModelProvider = ModelProvider.OPENAI,
    model_name: str = "gpt-4o-mini",
    callbacks: Optional[list[BaseCallbackHandler]] = None
) -> TaskType:
    """
    Classify task type using LLM-based analysis.
    
    Args:
        task_name: Name of the task
        task_description: Description of the task
        model_provider: LLM provider to use for classification
        model_name: Model name to use
        callbacks: Optional callbacks for LLM calls
        
    Returns:
        TaskType: One of the defined task types
    """
    logger.info(f"Classifying task type for: {task_name}")
    
    system_prompt = """You are a task classification system. Analyze the given task and classify it into one of the following types:

1. **code_generation**: Tasks that require writing and executing Python code to generate files, process data, or perform computations.
   Examples: "Generate a CSV file with sample data", "Create a Python script to analyze data", "Process images and save results"

2. **web_search**: Tasks that require searching the web for information.
   Examples: "Search for the latest news about AI", "Find information about Python best practices", "Look up current stock prices"

3. **text_generation**: Tasks that involve generating or editing text content (emails, reports, summaries, documents).
   Examples: "Write a thank you email", "Create a summary of a meeting", "Draft a formal letter", "Write a blog post"

4. **scraping**: Tasks that involve extracting data from websites.
   Examples: "Scrape product information from a website", "Extract article content from URLs", "Get data from a web page"

5. **rag**: Tasks that involve searching through documents or knowledge bases and answering questions.
   Examples: "Answer questions about a document", "Search through uploaded files", "Find information in a knowledge base"

6. **simple_text**: Very simple text processing tasks that don't require complex operations.
   Examples: "Capitalize text", "Count words", "Simple text formatting"

Respond with ONLY the task type name (e.g., "code_generation") without any additional explanation or formatting."""

    user_prompt = f"""Task Name: {task_name}

Task Description: {task_description}

Classify this task into one of the types: code_generation, web_search, text_generation, scraping, rag, or simple_text."""

    try:
        llm = create_llm(model_provider, model_name, callbacks=callbacks)
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        response = llm.invoke(messages)
        task_type_str = response.content.strip().lower()
        
        # Clean up the response (remove markdown formatting, quotes, etc.)
        task_type_str = re.sub(r'[`"\']', '', task_type_str)
        task_type_str = task_type_str.strip()
        
        # Validate and map to TaskType
        valid_types = ["code_generation", "web_search", "text_generation", "scraping", "rag", "simple_text"]
        
        # Try to find a match (handle variations)
        for valid_type in valid_types:
            if valid_type in task_type_str or task_type_str == valid_type:
                logger.success(f"Task classified as: {valid_type}")
                return valid_type  # type: ignore
        
        # Fallback: if no match found, default to code_generation
        logger.warning(f"Could not match task type '{task_type_str}', defaulting to 'code_generation'")
        return "code_generation"  # type: ignore
        
    except Exception as e:
        logger.error(f"Error classifying task type: {e}", exc_info=True)
        # Default to code_generation on error
        logger.warning("Defaulting to 'code_generation' due to classification error")
        return "code_generation"  # type: ignore


def analyze_task_complexity(
    task_name: str,
    task_description: str,
    model_provider: ModelProvider = ModelProvider.OPENAI,
    model_name: str = "gpt-4o-mini",
    callbacks: Optional[list[BaseCallbackHandler]] = None
) -> dict:
    """
    Analyze task complexity and return analysis results.
    
    Args:
        task_name: Name of the task
        task_description: Description of the task
        model_provider: LLM provider to use for analysis
        model_name: Model name to use
        callbacks: Optional callbacks for LLM calls
        
    Returns:
        dict: Analysis results containing:
            - complexity: "simple", "medium", or "complex"
            - estimated_iterations: Estimated number of iterations needed
            - reasoning: Brief explanation of the analysis
    """
    logger.info(f"Analyzing task complexity for: {task_name}")
    
    system_prompt = """You are a task complexity analyzer. Analyze the given task and determine its complexity level.

Respond with a JSON object containing:
- "complexity": "simple", "medium", or "complex"
- "estimated_iterations": A number between 1 and 5 indicating how many iterations might be needed
- "reasoning": A brief explanation of why this complexity level was assigned

Example response:
{
  "complexity": "simple",
  "estimated_iterations": 1,
  "reasoning": "This is a straightforward text generation task that can be completed in a single iteration."
}"""

    user_prompt = f"""Task Name: {task_name}

Task Description: {task_description}

Analyze the complexity of this task."""

    try:
        llm = create_llm(model_provider, model_name, callbacks=callbacks)
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        response = llm.invoke(messages)
        content = response.content.strip()
        
        # Try to extract JSON from the response
        json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            analysis = json.loads(json_str)
            
            # Validate and set defaults
            complexity = analysis.get("complexity", "medium")
            if complexity not in ["simple", "medium", "complex"]:
                complexity = "medium"
            
            estimated_iterations = analysis.get("estimated_iterations", 2)
            if not isinstance(estimated_iterations, int) or estimated_iterations < 1:
                estimated_iterations = 2
            
            reasoning = analysis.get("reasoning", "Complexity analysis completed")
            
            logger.success(f"Task complexity analyzed: {complexity} (iterations: {estimated_iterations})")
            return {
                "complexity": complexity,
                "estimated_iterations": estimated_iterations,
                "reasoning": reasoning
            }
        else:
            logger.warning("Could not extract JSON from complexity analysis response")
            return {
                "complexity": "medium",
                "estimated_iterations": 2,
                "reasoning": "Could not parse complexity analysis"
            }
            
    except Exception as e:
        logger.error(f"Error analyzing task complexity: {e}", exc_info=True)
        return {
            "complexity": "medium",
            "estimated_iterations": 2,
            "reasoning": f"Error during analysis: {str(e)}"
        }
