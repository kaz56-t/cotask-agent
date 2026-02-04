"""Prompts for task classification and complexity analysis."""

TASK_CLASSIFICATION_PROMPT = """You are a task classification system. Analyze the given task and classify it into one of the following types:

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


def get_task_classification_user_prompt(task_name: str, task_description: str) -> str:
    """Get the user prompt for task classification."""
    return f"""Task Name: {task_name}

Task Description: {task_description}

Classify this task into one of the types: code_generation, web_search, text_generation, scraping, rag, or simple_text."""


COMPLEXITY_ANALYSIS_PROMPT = """You are a task complexity analyzer. Analyze the given task and determine its complexity level.

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


def get_complexity_analysis_user_prompt(task_name: str, task_description: str) -> str:
    """Get the user prompt for complexity analysis."""
    return f"""Task Name: {task_name}

Task Description: {task_description}

Analyze the complexity of this task."""
