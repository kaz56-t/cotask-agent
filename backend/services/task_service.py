"""Task service for handling task execution and management."""
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session
from langchain_core.callbacks import CallbackManager
from database import Task, TaskStatus, ModelProvider, TaskLog, ChatMessage
from agent.router import route_task
from executor import RuntimeExecutor
from langfuse_config import get_langfuse_handler
from complexity_analyzer import classify_task_type
from loguru import logger
import time


def run_task_background(task_id: str, get_db):
    """Function to execute task in background"""
    logger.info(f"Starting background task execution: {task_id}")
    db = next(get_db())
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            logger.error(f"Task {task_id} not found")
            return
        
        logger.info(f"Task found: {task.name} (status: {task.status})")
        
        # Extract requirements from chat history (if session exists)
        requirements_summary = ""
        if task.session_id:
            messages = db.query(ChatMessage).filter(
                ChatMessage.session_id == task.session_id
            ).order_by(ChatMessage.timestamp).all()
            
            # Create requirements summary (from chat history)
            if messages:
                requirements_summary = "\n".join([
                    f"{msg.role}: {msg.content}" for msg in messages[-5:]  # Last 5 messages
                ])
        else:
            # Phase 0: Test execution mode - skip requirements definition
            logger.info("No session_id found - running in test execution mode (requirements skipped)")
            requirements_summary = ""
        
        # Artifact output path (host side)
        artifacts_dir = Path("/app/data/artifacts")
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        task_artifacts_dir = artifacts_dir / task_id
        task_artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        # Output path in Runtime container
        runtime_output_path = f"/workspace/outputs/{task_id}"
        
        # Initialize RuntimeExecutor (Phase 6: Execute in Runtime container)
        try:
            runtime_executor = RuntimeExecutor()
            logger.info("RuntimeExecutor initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize RuntimeExecutor: {e}")
            raise
        
        # Log callback function
        def log_callback(role: str, content: str):
            try:
                log_entry = TaskLog(
                    task_id=task_id,
                    role=role,
                    content=content
                )
                db.add(log_entry)
                db.commit()
                logger.info(f"[TaskLog][{role}] {content[:200]}")
            except Exception as e:
                logger.error(f"Failed to save task log: {e}")
                logger.debug(f"Log content: {content[:500]}")
        
        # Code execution function (Phase 6: Execute in Runtime container)
        def execute_code_func(code: str) -> str:
            """Execute code and return result (Phase 6: Runtime container execution)"""
            try:
                # Execute code in Runtime container
                success, stdout, stderr = runtime_executor.execute_code(
                    code=code,
                    task_id=task_id,
                    timeout=300
                )
                
                result_str = f"Success: {success}\n"
                if stdout:
                    result_str += f"Output:\n{stdout}\n"
                if stderr:
                    result_str += f"Error:\n{stderr}\n"
                
                log_callback("executor", f"Code execution result:\n{result_str}")
                return result_str
                
            except Exception as e:
                error_msg = f"Error executing code in runtime container: {str(e)}"
                log_callback("executor", error_msg)
                return f"Error: {error_msg}"
        
        # Set model provider
        model_provider = ModelProvider.OPENAI if task.model_provider == "openai" else ModelProvider.ANTHROPIC
        
        # Phase 1: Classify task type if not already set
        task_type = task.task_type
        if not task_type:
            try:
                logger.info("Task type not set, classifying task...")
                task_type = classify_task_type(
                    task_name=task.name,
                    task_description=task.description,
                    model_provider=model_provider,
                    model_name=task.model_name
                )
                # Update task in database
                task.task_type = task_type
                db.commit()
                logger.success(f"Task classified as type: {task_type}")
            except Exception as e:
                logger.error(f"Error classifying task type: {e}", exc_info=True)
                task_type = "code_generation"  # Default fallback
        
        # Create agent workflow using router (Phase 2)
        logger.info("Creating agent workflow using router")
        # Phase 0: If no requirements summary, use task description only
        if requirements_summary:
            task_description_with_requirements = task.description + "\n\nRequirements:\n" + requirements_summary
        else:
            task_description_with_requirements = task.description
        
        workflow, initial_state = route_task(
            task_type=task_type or "code_generation",
            model_provider=model_provider,
            model_name=task.model_name,
            task_id=task_id,
            task_name=task.name,
            task_description=task_description_with_requirements,
            runtime_output_path=runtime_output_path,
            execute_code_func=execute_code_func,
            log_callback=log_callback,
            session_id=task.session_id
        )
        
        logger.info("Workflow created, starting execution")
        log_callback("system", f"Starting task execution: {task.name}")
        
        # Get Langfuse callback handler (for LangGraph execution)
        langfuse_handler = get_langfuse_handler(
            task_id=task_id,
            session_id=task.session_id,
            trace_name="LangGraph Task"
        )

        try:
            logger.info("Invoking workflow")
            # Pass callback to LangGraph invoke
            config = {}
            if langfuse_handler:
                callback_manager = CallbackManager([langfuse_handler])
                config["callbacks"] = callback_manager
                config["metadata"] = {"trace_name": "LangGraph Task"}
                config["run_name"] = "LangGraph Task"
            
            result = workflow.invoke(initial_state, config=config if config else None)
            logger.success("Workflow execution completed successfully")
            log_callback("system", "Task execution completed successfully")
            
            # Phase 6: Check artifacts (automatically shared via volume mount)
            # Volume mount automatically mounts /workspace/outputs/{task_id} in Runtime container
            # to ./backend/data/artifacts/{task_id} on host side
            logger.info("Checking for artifacts...")
            
            # Wait a bit before checking artifacts (wait for filesystem sync)
            time.sleep(1)
            
            # Check artifacts
            if task_artifacts_dir.exists():
                artifacts = list(task_artifacts_dir.iterdir())
                if artifacts:
                    artifact_path = str(task_artifacts_dir)
                    task.artifact_path = artifact_path
                    log_callback("system", f"Artifacts available at: {artifact_path}")
                    logger.success(f"Found {len(artifacts)} artifact(s) in {artifact_path}")
                else:
                    logger.warning("No artifacts found in artifacts directory")
                    # For text-based tasks (text_generation, web_search), save LLM response as artifact
                    try:
                        # Extract final response from workflow result
                        final_messages = result.get("messages", [])
                        if final_messages:
                            final_response = final_messages[-1].content if hasattr(final_messages[-1], 'content') else str(final_messages[-1])
                            
                            # Save as markdown file
                            task_name_safe = "".join(c for c in task.name if c.isalnum() or c in (' ', '-', '_')).strip()
                            task_name_safe = task_name_safe.replace(' ', '_')[:50]
                            artifact_file = task_artifacts_dir / f"{task_name_safe}_result.md"
                            artifact_file.write_text(final_response, encoding='utf-8')
                            
                            artifact_path = str(task_artifacts_dir)
                            task.artifact_path = artifact_path
                            log_callback("system", f"Text result saved as artifact: {artifact_file}")
                            logger.success(f"Saved text result as artifact: {artifact_file}")
                    except Exception as e:
                        logger.warning(f"Failed to save text result as artifact: {e}")
                    
                    # Try copying from Runtime container as a fallback
                    logger.info("Attempting to copy artifacts from runtime container...")
                    copy_success = runtime_executor.copy_artifacts_from_container(
                        task_id=task_id,
                        host_artifacts_dir=str(task_artifacts_dir)
                    )
                    if copy_success:
                        artifacts = list(task_artifacts_dir.iterdir())
                        if artifacts:
                            artifact_path = str(task_artifacts_dir)
                            task.artifact_path = artifact_path
                            log_callback("system", f"Artifacts copied from runtime container to: {artifact_path}")
            else:
                logger.warning("Artifacts directory does not exist")
                # For text-based tasks, create directory and save LLM response as artifact
                if task_type in ["text_generation", "simple_text", "web_search"]:
                    try:
                        task_artifacts_dir.mkdir(parents=True, exist_ok=True)
                        # Extract final response from workflow result
                        final_messages = result.get("messages", [])
                        if final_messages:
                            final_response = final_messages[-1].content if hasattr(final_messages[-1], 'content') else str(final_messages[-1])
                            
                            # Save as markdown file
                            task_name_safe = "".join(c for c in task.name if c.isalnum() or c in (' ', '-', '_')).strip()
                            task_name_safe = task_name_safe.replace(' ', '_')[:50]
                            artifact_file = task_artifacts_dir / f"{task_name_safe}_result.md"
                            artifact_file.write_text(final_response, encoding='utf-8')
                            
                            artifact_path = str(task_artifacts_dir)
                            task.artifact_path = artifact_path
                            log_callback("system", f"Text result saved as artifact: {artifact_file}")
                            logger.success(f"Saved text result as artifact: {artifact_file}")
                    except Exception as e:
                        logger.warning(f"Failed to save text result as artifact: {e}")
                
                # Try copying from Runtime container as a fallback
                logger.info("Attempting to copy artifacts from runtime container...")
                copy_success = runtime_executor.copy_artifacts_from_container(
                    task_id=task_id,
                    host_artifacts_dir=str(task_artifacts_dir)
                )
                if copy_success and task_artifacts_dir.exists():
                    artifacts = list(task_artifacts_dir.iterdir())
                    if artifacts:
                        artifact_path = str(task_artifacts_dir)
                        task.artifact_path = artifact_path
                        log_callback("system", f"Artifacts copied from runtime container to: {artifact_path}")
            
            # Update task to completed status
            task.status = TaskStatus.COMPLETED.value
            task.completed_at = datetime.utcnow()
            db.commit()
            
        except Exception as e:
            logger.error(f"Task execution failed: {e}", exc_info=True)
            import traceback
            error_traceback = traceback.format_exc()
            logger.error(f"Traceback: {error_traceback}")
            log_callback("system", f"Task execution failed: {str(e)}\n\n{error_traceback}")
            task.status = TaskStatus.FAILED.value
            task.error_message = f"{str(e)}\n\n{error_traceback}"
            task.completed_at = datetime.utcnow()
            db.commit()
            logger.error(f"Task {task_id} marked as failed")
            
    except Exception as e:
        logger.error(f"Error in background task execution: {e}", exc_info=True)
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Traceback: {error_traceback}")
        db.rollback()
        # Update task to failed status
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                task.status = TaskStatus.FAILED.value
                task.error_message = f"{str(e)}\n\n{error_traceback}"
                task.completed_at = datetime.utcnow()
                db.commit()
                logger.error(f"Task {task_id} marked as failed in exception handler")
        except Exception as inner_e:
            logger.error(f"Failed to update task status: {inner_e}")
    finally:
        logger.info(f"Background task execution finished for task: {task_id}")
        db.close()
