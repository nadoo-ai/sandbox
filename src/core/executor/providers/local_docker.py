"""
Local Docker Executor

Warm Pool based Docker executor for fast, isolated code execution.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import docker

from ..interface import BaseExecutor, ExecutorProvider, Runtime
from ..models import ExecutionRequest, ExecutionResult, HealthStatus, ExecutorMetrics
from ..exceptions import ExecutionTimeoutError
from ...warm_pool.manager import WarmPoolManager
from ...warm_pool.container import WarmContainer

logger = logging.getLogger(__name__)


class LocalDockerExecutor(BaseExecutor):
    """
    Warm Pool based local Docker executor.

    Uses pre-warmed containers to minimize cold start latency.
    Containers are reused with environment reset between executions.

    Features:
    - Pre-warmed container pool per runtime
    - Fast execution (~50-100ms warm start)
    - Full isolation (network, filesystem, resources)
    - Automatic health monitoring and replacement
    """

    provider = ExecutorProvider.LOCAL_DOCKER

    # Execution commands per runtime
    EXEC_COMMANDS = {
        Runtime.PYTHON_311: ["python3", "/tmp/code/{entry_point}"],
        Runtime.PYTHON_312: ["python3", "/tmp/code/{entry_point}"],
        Runtime.NODE_20: ["node", "/tmp/code/{entry_point}"],
        Runtime.NODE_22: ["node", "/tmp/code/{entry_point}"],
        Runtime.GO_121: ["go", "run", "/tmp/code/{entry_point}"],
        Runtime.GO_122: ["go", "run", "/tmp/code/{entry_point}"],
        Runtime.RUST_LATEST: ["rustc", "/tmp/code/{entry_point}", "-o", "/tmp/out", "&&", "/tmp/out"],
        Runtime.JAVA_17: ["java", "/tmp/code/{entry_point}"],
        Runtime.JAVA_21: ["java", "/tmp/code/{entry_point}"],
    }

    def __init__(
        self,
        pool_size_per_runtime: int = 5,
        max_idle_time_seconds: int = 300,
        container_ttl_seconds: int = 3600,
        health_check_interval_seconds: int = 30,
        memory_limit: str = "256m",
        cpu_limit: float = 0.5,
    ):
        """
        Initialize executor.

        Args:
            pool_size_per_runtime: Containers to keep warm per runtime
            max_idle_time_seconds: Max idle time before replacement
            container_ttl_seconds: Max container age
            health_check_interval_seconds: Health check interval
            memory_limit: Memory limit per container
            cpu_limit: CPU limit per container

        Raises:
            docker.errors.DockerException: If Docker is not available
        """
        try:
            self.docker_client = docker.from_env()
            # Verify connection
            self.docker_client.ping()
        except docker.errors.DockerException as e:
            logger.error(f"Failed to connect to Docker: {e}")
            raise

        self.pool_manager = WarmPoolManager(
            docker_client=self.docker_client,
            pool_size_per_runtime=pool_size_per_runtime,
            max_idle_time=max_idle_time_seconds,
            container_ttl=container_ttl_seconds,
            health_check_interval=health_check_interval_seconds,
            memory_limit=memory_limit,
            cpu_limit=cpu_limit,
        )

        # Metrics tracking
        self._metrics = ExecutorMetrics(provider=self.provider)
        self._execution_times: list[float] = []

    async def initialize(self) -> None:
        """Initialize executor and warm pool"""
        logger.info("Initializing LocalDockerExecutor")

        await self.pool_manager.start()

        # Pre-warm default runtimes
        await self.warm_up(Runtime.PYTHON_311, count=3)
        await self.warm_up(Runtime.NODE_20, count=2)

        logger.info("LocalDockerExecutor initialized")

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """
        Execute code in isolated container.

        Args:
            request: Execution request

        Returns:
            ExecutionResult with stdout, stderr, and metrics
        """
        start_time = time.time()
        cold_start = False
        container: Optional[WarmContainer] = None

        try:
            # 1. Acquire container from pool
            container = await self.pool_manager.acquire(request.runtime)

            if container is None:
                # Cold start - create new container
                cold_start = True
                self._metrics.cold_start_count += 1
                self._metrics.pool_misses += 1

                logger.debug(f"Cold start for {request.runtime.value}")
                container = await self.pool_manager._create_container(request.runtime)
            else:
                self._metrics.warm_start_count += 1
                self._metrics.pool_hits += 1

            # 2. Execute code in container
            result = await self._execute_in_container(container, request)

            # 3. Calculate execution time
            execution_time_ms = (time.time() - start_time) * 1000

            # 4. Update metrics
            self._update_metrics(execution_time_ms, result["success"])
            container.record_execution(execution_time_ms, result["success"])

            return ExecutionResult(
                success=result["success"],
                stdout=result["stdout"],
                stderr=result["stderr"],
                exit_code=result["exit_code"],
                execution_time_ms=execution_time_ms,
                cold_start=cold_start,
                provider=self.provider,
                container_id=container.id,
                memory_used_mb=result.get("memory_used_mb"),
                execution_id=request.execution_id,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )

        except asyncio.TimeoutError:
            execution_time_ms = request.timeout_ms
            self._metrics.timeout_executions += 1

            if container:
                # Kill any running processes
                await self._kill_container_processes(container)
                container.record_execution(execution_time_ms, False)

            raise ExecutionTimeoutError(
                timeout_ms=request.timeout_ms,
                provider=self.provider,
                execution_id=request.execution_id,
            )

        except Exception as e:
            logger.error(f"Execution failed: {e}", exc_info=True)

            if container:
                container.record_execution(
                    (time.time() - start_time) * 1000, False
                )

            self._metrics.failed_executions += 1

            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                execution_time_ms=(time.time() - start_time) * 1000,
                cold_start=cold_start,
                provider=self.provider,
                execution_id=request.execution_id,
            )

        finally:
            # 5. Reset and release container
            if container:
                try:
                    await self._reset_container(container)

                    if cold_start:
                        # Add new container to pool
                        await self.pool_manager.add(container, request.runtime)
                    else:
                        # Release back to pool
                        await self.pool_manager.release(container, request.runtime)

                except Exception as e:
                    logger.error(f"Failed to release container: {e}")

    async def _execute_in_container(
        self,
        container: WarmContainer,
        request: ExecutionRequest,
    ) -> dict:
        """Execute code inside container"""
        # 1. Write code files to container
        await self._write_code_files(container, request)

        # 2. Build execution command
        cmd = self._build_exec_command(request)

        # 3. Execute with timeout
        try:
            exit_code, output = await asyncio.wait_for(
                self._run_exec(container, cmd, request.stdin, request.environment),
                timeout=request.timeout_ms / 1000,
            )

            stdout, stderr = output if output else ("", "")

            return {
                "success": exit_code == 0,
                "stdout": stdout or "",
                "stderr": stderr or "",
                "exit_code": exit_code,
            }

        except asyncio.TimeoutError:
            raise

    async def _write_code_files(
        self,
        container: WarmContainer,
        request: ExecutionRequest,
    ) -> None:
        """Write code and additional files to container"""
        # Create code directory
        await asyncio.to_thread(
            container.container.exec_run,
            ["mkdir", "-p", "/tmp/code"],
        )

        # Write main code file
        code_content = request.code.encode("utf-8")
        await self._write_file_to_container(
            container,
            f"/tmp/code/{request.entry_point}",
            code_content,
        )

        # Write additional files
        for filename, content in request.files.items():
            await self._write_file_to_container(
                container,
                f"/tmp/code/{filename}",
                content.encode("utf-8"),
            )

    async def _write_file_to_container(
        self,
        container: WarmContainer,
        path: str,
        content: bytes,
    ) -> None:
        """Write file content to container using exec"""
        import base64

        encoded = base64.b64encode(content).decode("utf-8")

        # Use echo and base64 decode to write file
        cmd = f"echo '{encoded}' | base64 -d > {path}"
        await asyncio.to_thread(
            container.container.exec_run,
            ["sh", "-c", cmd],
        )

    def _build_exec_command(self, request: ExecutionRequest) -> list[str]:
        """Build execution command for runtime"""
        template = self.EXEC_COMMANDS.get(
            request.runtime,
            ["python3", "/tmp/code/{entry_point}"],
        )

        return [
            part.format(entry_point=request.entry_point)
            for part in template
        ]

    async def _run_exec(
        self,
        container: WarmContainer,
        cmd: list[str],
        stdin: Optional[str],
        environment: dict,
    ) -> tuple[int, tuple[str, str]]:
        """Run command in container"""
        # Build environment string
        env_list = [f"{k}={v}" for k, v in environment.items()]

        result = await asyncio.to_thread(
            container.container.exec_run,
            cmd,
            environment=env_list if env_list else None,
            stdin=stdin is not None,
            demux=True,
        )

        exit_code = result.exit_code
        output = result.output

        if output:
            stdout = output[0].decode("utf-8", errors="replace") if output[0] else ""
            stderr = output[1].decode("utf-8", errors="replace") if output[1] else ""
        else:
            stdout, stderr = "", ""

        return exit_code, (stdout, stderr)

    async def _reset_container(self, container: WarmContainer) -> None:
        """Reset container state for reuse"""
        container.mark_resetting()

        # Clean up code files
        await asyncio.to_thread(
            container.container.exec_run,
            ["rm", "-rf", "/tmp/code"],
        )

        # Kill any remaining processes (except the main tail process)
        await asyncio.to_thread(
            container.container.exec_run,
            ["pkill", "-9", "-f", "python|node|go|java|rustc"],
        )

    async def _kill_container_processes(self, container: WarmContainer) -> None:
        """Kill all user processes in container"""
        try:
            await asyncio.to_thread(
                container.container.exec_run,
                ["pkill", "-9", "-f", "."],
            )
        except Exception:
            pass

    def _update_metrics(self, execution_time_ms: float, success: bool) -> None:
        """Update execution metrics"""
        self._metrics.total_executions += 1

        if success:
            self._metrics.successful_executions += 1
        else:
            self._metrics.failed_executions += 1

        # Track execution times for percentile calculation
        self._execution_times.append(execution_time_ms)

        # Keep only last 1000 samples
        if len(self._execution_times) > 1000:
            self._execution_times = self._execution_times[-1000:]

        # Update timing stats
        if self._execution_times:
            self._metrics.avg_execution_time_ms = (
                sum(self._execution_times) / len(self._execution_times)
            )
            self._metrics.min_execution_time_ms = min(self._execution_times)
            self._metrics.max_execution_time_ms = max(self._execution_times)

            sorted_times = sorted(self._execution_times)
            n = len(sorted_times)
            self._metrics.p50_execution_time_ms = sorted_times[n // 2]
            self._metrics.p95_execution_time_ms = sorted_times[int(n * 0.95)]
            self._metrics.p99_execution_time_ms = sorted_times[int(n * 0.99)]

        # Update timestamps
        now = datetime.now(timezone.utc)
        if self._metrics.first_execution_at is None:
            self._metrics.first_execution_at = now
        self._metrics.last_execution_at = now

    async def warm_up(self, runtime: Runtime, count: int = 1) -> int:
        """Pre-warm containers for a runtime"""
        return await self.pool_manager.warm_up(runtime, count)

    async def health_check(self) -> HealthStatus:
        """Check executor health"""
        try:
            # Check Docker connectivity
            self.docker_client.ping()

            # Get pool status
            pool_status = await self.pool_manager.get_status()

            return HealthStatus(
                healthy=True,
                provider=self.provider,
                message="OK",
                pool_size=pool_status.total,
                available_containers=pool_status.available,
                busy_containers=pool_status.busy,
                checks={
                    "docker": True,
                    "pool": pool_status.total > 0,
                },
            )

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return HealthStatus(
                healthy=False,
                provider=self.provider,
                message=str(e),
                checks={"docker": False},
            )

    async def cleanup(self) -> None:
        """Cleanup all resources"""
        logger.info("Cleaning up LocalDockerExecutor")
        await self.pool_manager.stop()
        logger.info("LocalDockerExecutor cleaned up")

    async def get_metrics(self) -> ExecutorMetrics:
        """Get execution metrics"""
        return self._metrics
