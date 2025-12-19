"""
Docker container management for secure code execution
"""
import asyncio
import docker
import uuid
import tempfile
import os
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
import logging

from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class DockerManager:
    """Manages Docker containers for code execution"""

    def __init__(self):
        self.client = docker.from_env()
        self.active_containers: Dict[str, Any] = {}

    async def execute_code(
        self,
        code: str,
        language: str,
        stdin: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> Tuple[str, str, int]:
        """
        Execute code in a Docker container

        Returns:
            Tuple of (stdout, stderr, exit_code)
        """
        if language not in settings.supported_languages:
            raise ValueError(f"Unsupported language: {language}")

        container_id = str(uuid.uuid4())
        timeout = timeout or settings.max_execution_time

        try:
            # Prepare code file
            code_file = await self._prepare_code_file(code, language)

            # Get container image
            image = settings.language_images.get(language)
            if not image:
                raise ValueError(f"No Docker image configured for {language}")

            # Pull image if not exists
            try:
                self.client.images.get(image)
            except docker.errors.ImageNotFound:
                logger.info(f"Pulling Docker image: {image}")
                self.client.images.pull(image)

            # Prepare command
            command = self._get_execution_command(language, code_file.name)

            # Create and run container
            container = self.client.containers.run(
                image=image,
                command=command,
                volumes={
                    str(code_file.parent): {
                        "bind": "/code",
                        "mode": "ro"
                    }
                },
                working_dir="/code",
                mem_limit=settings.max_memory,
                cpu_quota=int(settings.max_cpu * 100000),
                network_mode="none",  # No network access
                remove=False,
                detach=True,
                stdin_open=bool(stdin),
                environment=environment or {},
            )

            self.active_containers[container_id] = container

            # Send stdin if provided
            if stdin:
                container.attach_socket(params={"stdin": 1, "stream": 1}).send(stdin.encode())

            # Wait for completion with timeout
            try:
                exit_code = await asyncio.wait_for(
                    asyncio.to_thread(container.wait),
                    timeout=timeout
                )
                exit_code = exit_code["StatusCode"]
            except asyncio.TimeoutError:
                container.kill()
                return "", "Execution timeout exceeded", -1

            # Get output
            logs = container.logs(stdout=True, stderr=True, stream=False)
            stdout = container.logs(stdout=True, stderr=False).decode("utf-8")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8")

            return stdout, stderr, exit_code

        except Exception as e:
            logger.error(f"Error executing code: {e}")
            raise
        finally:
            # Cleanup
            if container_id in self.active_containers:
                container = self.active_containers.pop(container_id)
                try:
                    container.remove(force=True)
                except:
                    pass

            # Remove temp file
            try:
                if 'code_file' in locals():
                    os.unlink(code_file)
            except:
                pass

    async def _prepare_code_file(self, code: str, language: str) -> Path:
        """Prepare code file for execution"""
        extension = self._get_file_extension(language)

        # Create temp file
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=f".{extension}",
            dir=settings.temp_dir,
            delete=False
        ) as f:
            f.write(code)
            return Path(f.name)

    def _get_file_extension(self, language: str) -> str:
        """Get file extension for language"""
        extensions = {
            "python": "py",
            "javascript": "js",
            "typescript": "ts",
            "java": "java",
            "go": "go",
            "rust": "rs",
            "cpp": "cpp",
            "csharp": "cs",
            "ruby": "rb",
            "php": "php",
            "sql": "sql",
            "bash": "sh",
        }
        return extensions.get(language, "txt")

    def _get_execution_command(self, language: str, filename: str) -> str:
        """Get execution command for language"""
        basename = os.path.basename(filename)

        commands = {
            "python": f"python {basename}",
            "javascript": f"node {basename}",
            "typescript": f"npx ts-node {basename}",
            "java": f"javac {basename} && java {basename[:-5]}",
            "go": f"go run {basename}",
            "rust": f"rustc {basename} -o /tmp/program && /tmp/program",
            "cpp": f"g++ {basename} -o /tmp/program && /tmp/program",
            "csharp": f"dotnet script {basename}",
            "ruby": f"ruby {basename}",
            "php": f"php {basename}",
            "sql": f"psql -f {basename}",
            "bash": f"bash {basename}",
        }
        return commands.get(language, f"cat {basename}")

    async def cleanup_container(self, container_id: str):
        """Force cleanup a container"""
        if container_id in self.active_containers:
            container = self.active_containers.pop(container_id)
            try:
                container.kill()
                container.remove(force=True)
            except:
                pass

    async def cleanup_all(self):
        """Cleanup all active containers"""
        for container_id in list(self.active_containers.keys()):
            await self.cleanup_container(container_id)

    def get_container_stats(self, container_id: str) -> Optional[Dict[str, Any]]:
        """Get container resource usage stats"""
        if container_id in self.active_containers:
            container = self.active_containers[container_id]
            try:
                stats = container.stats(stream=False)
                return {
                    "cpu_usage": stats["cpu_stats"]["cpu_usage"]["total_usage"],
                    "memory_usage": stats["memory_stats"]["usage"],
                    "memory_limit": stats["memory_stats"]["limit"],
                }
            except:
                return None
        return None
