"""Code execution in runtime container using Docker."""
import docker
import os
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# Runtime container name from docker-compose
RUNTIME_CONTAINER_NAME = "cotask-agent-runtime"


class RuntimeExecutor:
    """Manages code execution in the runtime container."""
    
    def __init__(self, container_name: str = RUNTIME_CONTAINER_NAME):
        """Initialize executor with Docker client."""
        try:
            self.client = docker.from_env()
            self.container_name = container_name
            self._ensure_container_exists()
        except Exception as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            raise
    
    def _ensure_container_exists(self):
        """Ensure the runtime container exists and is running."""
        try:
            container = self.client.containers.get(self.container_name)
            if container.status != "running":
                logger.warning(f"Container {self.container_name} is not running, attempting to start...")
                container.start()
        except docker.errors.NotFound:
            raise RuntimeError(
                f"Runtime container '{self.container_name}' not found. "
                "Please ensure docker-compose is running and the runtime service is up."
            )
    
    def execute_code(
        self,
        code: str,
        task_id: str,
        timeout: int = 300
    ) -> Tuple[bool, str, str]:
        """
        Execute Python code in the runtime container.
        
        Args:
            code: Python code to execute
            task_id: Task ID for organizing outputs
            timeout: Execution timeout in seconds
        
        Returns:
            Tuple of (success: bool, stdout: str, stderr: str)
        """
        try:
            container = self.client.containers.get(self.container_name)
            
            # Prepare code execution
            # Save code to a temporary file in the container
            code_file = f"/workspace/task_{task_id}_code.py"
            
            # Write code to file in container
            exec_result = container.exec_run(
                f"bash -c 'cat > {code_file} << \"EOF\"\n{code}\nEOF'",
                workdir="/workspace"
            )
            
            if exec_result.exit_code != 0:
                return False, "", exec_result.output.decode('utf-8', errors='ignore')
            
            # Execute the code
            # Note: exec_run() doesn't support timeout parameter directly
            # Use timeout command if available, otherwise execute directly
            try:
                exec_result = container.exec_run(
                    f"timeout {timeout} python {code_file}",
                    workdir="/workspace"
                )
            except Exception:
                # Fallback if timeout command is not available
                exec_result = container.exec_run(
                    f"python {code_file}",
                    workdir="/workspace"
                )
            
            stdout = exec_result.output.decode('utf-8', errors='ignore')
            stderr = ""
            
            if exec_result.exit_code != 0:
                return False, stdout, stderr
            
            # Clean up temporary file
            container.exec_run(f"rm -f {code_file}", workdir="/workspace")
            
            return True, stdout, stderr
            
        except docker.errors.NotFound:
            return False, "", f"Container {self.container_name} not found"
        except docker.errors.APIError as e:
            return False, "", f"Docker API error: {str(e)}"
        except Exception as e:
            logger.error(f"Error executing code: {e}")
            return False, "", str(e)
    
    def execute_command(
        self,
        command: str,
        workdir: str = "/workspace",
        timeout: int = 300
    ) -> Tuple[bool, str, str]:
        """
        Execute a shell command in the runtime container.
        
        Args:
            command: Shell command to execute
            workdir: Working directory
            timeout: Execution timeout in seconds
        
        Returns:
            Tuple of (success: bool, stdout: str, stderr: str)
        """
        try:
            container = self.client.containers.get(self.container_name)
            # Note: exec_run() doesn't support timeout parameter directly
            # Use timeout command if timeout is needed and available
            if timeout and timeout > 0:
                try:
                    exec_result = container.exec_run(
                        f"timeout {timeout} {command}",
                        workdir=workdir
                    )
                except Exception:
                    # Fallback if timeout command is not available
                    exec_result = container.exec_run(
                        command,
                        workdir=workdir
                    )
            else:
                exec_result = container.exec_run(
                    command,
                    workdir=workdir
                )
            
            stdout = exec_result.output.decode('utf-8', errors='ignore')
            stderr = ""
            
            if exec_result.exit_code != 0:
                return False, stdout, stderr
            
            return True, stdout, stderr
            
        except docker.errors.NotFound:
            return False, "", f"Container {self.container_name} not found"
        except docker.errors.APIError as e:
            return False, "", f"Docker API error: {str(e)}"
        except Exception as e:
            logger.error(f"Error executing command: {e}")
            return False, "", str(e)
    
    def list_artifacts(self, task_id: str) -> list:
        """List artifacts generated for a task."""
        try:
            container = self.client.containers.get(self.container_name)
            exec_result = container.exec_run(
                f"find /workspace/outputs/{task_id} -type f 2>/dev/null || true",
                workdir="/workspace"
            )
            
            output = exec_result.output.decode('utf-8', errors='ignore')
            files = [line.strip() for line in output.split('\n') if line.strip()]
            return files
            
        except Exception as e:
            logger.error(f"Error listing artifacts: {e}")
            return []
