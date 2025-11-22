"""
Plugin Runner Service - Manages plugin execution in Docker containers
"""
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

import docker
from docker.errors import DockerException, ImageNotFound, ContainerError

from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class PluginRunner:
    """Manages plugin execution in sandboxed Docker containers"""

    def __init__(self):
        """Initialize Docker client"""
        try:
            self.client = docker.from_env()
            self.client.ping()
            logger.info("Docker client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            raise

        # Ensure plugin-runner image exists
        self._ensure_runner_image()

    def _ensure_runner_image(self):
        """Ensure plugin-runner image exists"""
        try:
            self.client.images.get("nadoo-plugin-runner:latest")
            logger.info("Plugin runner image found")
        except ImageNotFound:
            logger.warning("Plugin runner image not found. Build it with: cd sandbox && ./scripts/build.sh")
            # Don't raise - we'll handle it at execution time

    async def execute(
        self,
        plugin_dir: str,
        config_path: str,
        timeout: int = 30,
        memory_limit: str = "256m",
    ) -> Dict[str, Any]:
        """
        Execute plugin in a sandboxed container

        Args:
            plugin_dir: Directory containing plugin code
            config_path: Path to config.json
            timeout: Execution timeout in seconds
            memory_limit: Memory limit (e.g., '256m')

        Returns:
            Execution result dictionary
        """
        container = None
        start_time = time.time()

        try:
            # Verify image exists
            try:
                self.client.images.get("nadoo-plugin-runner:latest")
            except ImageNotFound:
                return {
                    "success": False,
                    "error": "Plugin runner image not found",
                    "details": "Run: cd sandbox && ./scripts/build.sh"
                }

            # Prepare volume mounts
            plugin_dir_path = Path(plugin_dir).resolve()
            config_path_abs = Path(config_path).resolve()

            volumes = {
                str(plugin_dir_path): {
                    'bind': '/plugin/code',
                    'mode': 'ro'  # Read-only
                },
                str(config_path_abs): {
                    'bind': '/plugin/config.json',
                    'mode': 'ro'  # Read-only
                }
            }

            # Container configuration
            container_config = {
                'image': 'nadoo-plugin-runner:latest',
                'volumes': volumes,
                'network_mode': 'none',  # No network access
                'mem_limit': memory_limit,
                'memswap_limit': memory_limit,  # Disable swap
                'cpu_quota': int(0.5 * 100000),  # 0.5 CPU
                'cpu_period': 100000,
                'pids_limit': 50,  # Max 50 processes
                'security_opt': ['no-new-privileges'],
                'cap_drop': ['ALL'],  # Drop all capabilities
                'read_only': True,  # Read-only root filesystem
                'tmpfs': {
                    '/tmp': 'size=10M,mode=1777',  # 10MB temp space
                },
                'detach': False,
                'remove': True,  # Auto-remove after execution
                'stdout': True,
                'stderr': True,
            }

            logger.info(f"Starting plugin container with timeout={timeout}s, memory={memory_limit}")

            # Run container with timeout
            try:
                output = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.client.containers.run,
                        **container_config
                    ),
                    timeout=timeout + 5  # Add 5s buffer
                )
            except asyncio.TimeoutError:
                logger.error("Container execution timeout")
                return {
                    "success": False,
                    "error": "Execution timeout",
                    "execution_time": time.time() - start_time,
                }

            # Parse output
            output_str = output.decode('utf-8') if isinstance(output, bytes) else str(output)

            # Try to parse JSON output
            try:
                result = json.loads(output_str)
            except json.JSONDecodeError:
                # If not JSON, treat as raw output
                logger.warning(f"Container output is not JSON: {output_str[:200]}")
                result = {
                    "success": False,
                    "error": "Invalid output format",
                    "raw_output": output_str,
                }

            # Add execution time
            result['execution_time'] = time.time() - start_time

            logger.info(f"Plugin execution completed: success={result.get('success')}, time={result['execution_time']:.2f}s")
            return result

        except ContainerError as e:
            logger.error(f"Container error: {e}")
            return {
                "success": False,
                "error": "Container execution error",
                "details": str(e),
                "exit_code": e.exit_status,
                "execution_time": time.time() - start_time,
            }

        except DockerException as e:
            logger.error(f"Docker error: {e}")
            return {
                "success": False,
                "error": "Docker error",
                "details": str(e),
                "execution_time": time.time() - start_time,
            }

        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            return {
                "success": False,
                "error": "Unexpected error",
                "details": str(e),
                "execution_time": time.time() - start_time,
            }

        finally:
            # Cleanup container if it's still running
            if container:
                try:
                    container.stop(timeout=1)
                    container.remove(force=True)
                except:
                    pass

    def cleanup_dangling_containers(self):
        """Cleanup any dangling plugin containers"""
        try:
            filters = {'ancestor': 'nadoo-plugin-runner:latest'}
            containers = self.client.containers.list(all=True, filters=filters)

            for container in containers:
                try:
                    logger.info(f"Removing dangling container: {container.id[:12]}")
                    container.stop(timeout=1)
                    container.remove(force=True)
                except Exception as e:
                    logger.warning(f"Failed to remove container: {e}")

        except Exception as e:
            logger.error(f"Failed to cleanup containers: {e}")
