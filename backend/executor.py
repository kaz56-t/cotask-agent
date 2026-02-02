"""Code execution in runtime container using Docker."""
import docker
import os
import shutil
import tarfile
import io
from typing import Optional, Tuple, List
from pathlib import Path
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
            
            # Create output directory for this task
            output_dir = f"/workspace/outputs/{task_id}"
            exec_result = container.exec_run(
                f"mkdir -p {output_dir}",
                workdir="/workspace"
            )
            
            if exec_result.exit_code != 0:
                logger.warning(f"Failed to create output directory {output_dir}")
            
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
            
            # Execute the code in the task output directory
            # Note: exec_run() doesn't support timeout parameter directly
            # Use timeout command if available, otherwise execute directly
            try:
                exec_result = container.exec_run(
                    f"timeout {timeout} python {code_file}",
                    workdir=output_dir
                )
            except Exception:
                # Fallback if timeout command is not available
                exec_result = container.exec_run(
                    f"python {code_file}",
                    workdir=output_dir
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
    
    def copy_artifacts_from_container(
        self,
        task_id: str,
        host_artifacts_dir: str
    ) -> bool:
        """
        Copy artifacts from runtime container to host directory.
        
        Args:
            task_id: Task ID for organizing outputs
            host_artifacts_dir: Host directory path to copy artifacts to
            
        Returns:
            True if successful, False otherwise
        """
        try:
            container = self.client.containers.get(self.container_name)
            container_artifacts_dir = f"/workspace/outputs/{task_id}"
            
            # Check if artifacts directory exists in container
            exec_result = container.exec_run(
                f"test -d {container_artifacts_dir} && echo 'exists' || echo 'not_exists'",
                workdir="/workspace"
            )
            
            if b"not_exists" in exec_result.output:
                logger.warning(f"Artifacts directory {container_artifacts_dir} does not exist in container")
                return False
            
            # Create host artifacts directory if it doesn't exist
            host_path = Path(host_artifacts_dir)
            host_path.mkdir(parents=True, exist_ok=True)
            
            # Use docker cp to copy files from container to host
            # Note: docker cp works with container:path format
            try:
                # Get all files in the artifacts directory
                exec_result = container.exec_run(
                    f"find {container_artifacts_dir} -type f",
                    workdir="/workspace"
                )
                
                files = [
                    line.strip() 
                    for line in exec_result.output.decode('utf-8', errors='ignore').split('\n')
                    if line.strip()
                ]
                
                if not files:
                    logger.info(f"No artifacts found in {container_artifacts_dir}")
                    return True
                
                # Copy each file
                for container_file_path in files:
                    try:
                        # Get relative path from container_artifacts_dir
                        relative_path = container_file_path.replace(container_artifacts_dir, "").lstrip("/")
                        if not relative_path:
                            continue
                        
                        host_file_path = host_path / relative_path
                        host_file_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # Use docker cp API (returns tar archive)
                        bits, stat = container.get_archive(container_file_path)
                        
                        # Read tar archive into memory
                        tar_data = b''.join(bits)
                        
                        # Extract file from tar archive
                        with tarfile.open(fileobj=io.BytesIO(tar_data)) as tar:
                            # Get the file name from the tar archive
                            members = tar.getmembers()
                            if members:
                                member = members[0]
                                # Extract to the target path
                                member.name = host_file_path.name
                                tar.extract(member, host_file_path.parent)
                        
                        logger.info(f"Copied artifact: {container_file_path} -> {host_file_path}")
                        
                    except Exception as e:
                        logger.error(f"Error copying file {container_file_path}: {e}")
                        continue
                
                logger.success(f"Successfully copied artifacts from container to {host_artifacts_dir}")
                return True
                
            except Exception as e:
                logger.error(f"Error copying artifacts: {e}")
                return False
            
        except docker.errors.NotFound:
            logger.error(f"Container {self.container_name} not found")
            return False
        except Exception as e:
            logger.error(f"Error copying artifacts from container: {e}")
            return False
