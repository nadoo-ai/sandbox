"""
Tests for LocalDockerExecutor.
"""

import asyncio

import pytest
from unittest.mock import MagicMock, patch

from core.executor.interface import ExecutorProvider, Runtime
from core.executor.models import ExecutionRequest
from core.executor.providers.local_docker import LocalDockerExecutor


class TestLocalDockerExecutor:
    """Test LocalDockerExecutor."""

    @pytest.fixture
    def mock_docker_client(self):
        """Create mock Docker client."""
        client = MagicMock()
        client.ping.return_value = True
        client.images.get.return_value = MagicMock()
        client.images.pull.return_value = MagicMock()

        container = MagicMock()
        container.id = "test_container_123456789abc"
        container.status = "running"
        container.exec_run.return_value = MagicMock(
            exit_code=0,
            output=(b"Hello, World!\n", b""),
        )
        container.remove.return_value = None
        container.reload.return_value = None

        client.containers.run.return_value = container

        return client

    @pytest.fixture
    def executor(self, mock_docker_client):
        """Create LocalDockerExecutor with mock client."""
        with patch("docker.from_env", return_value=mock_docker_client):
            return LocalDockerExecutor(
                pool_size_per_runtime=3,
                max_idle_time_seconds=300,
                container_ttl_seconds=3600,
            )

    def test_provider_type(self, executor):
        """Test executor provider type."""
        assert executor.provider == ExecutorProvider.LOCAL_DOCKER

    @pytest.mark.asyncio
    async def test_initialize(self, executor):
        """Test executor initialization."""
        await executor.initialize()

        # Should have warmed up default runtimes
        assert executor.pool_manager._started is True

    @pytest.mark.asyncio
    async def test_execute_success(self, executor, mock_docker_client):
        """Test successful code execution."""
        # Warm up first
        await executor.pool_manager.warm_up(Runtime.PYTHON_311, count=1)

        request = ExecutionRequest(
            code="print('Hello, World!')",
            runtime=Runtime.PYTHON_311,
            timeout_ms=30000,
        )

        result = await executor.execute(request)

        assert result.success is True
        assert "Hello" in result.stdout or result.exit_code == 0
        assert result.provider == ExecutorProvider.LOCAL_DOCKER

    @pytest.mark.asyncio
    async def test_execute_cold_start(self, executor, mock_docker_client):
        """Test execution with cold start (empty pool)."""
        request = ExecutionRequest(
            code="print('Hello!')",
            runtime=Runtime.PYTHON_311,
        )

        result = await executor.execute(request)

        assert result.cold_start is True
        assert executor._metrics.cold_start_count == 1

    @pytest.mark.asyncio
    async def test_execute_warm_start(self, executor, mock_docker_client):
        """Test execution with warm start (from pool)."""
        # Warm up first
        await executor.pool_manager.warm_up(Runtime.PYTHON_311, count=1)

        request = ExecutionRequest(
            code="print('Hello!')",
            runtime=Runtime.PYTHON_311,
        )

        result = await executor.execute(request)

        assert result.cold_start is False
        assert executor._metrics.warm_start_count == 1
        assert executor._metrics.pool_hits == 1

    @pytest.mark.asyncio
    async def test_execute_with_environment(self, executor, mock_docker_client):
        """Test execution with environment variables."""
        await executor.pool_manager.warm_up(Runtime.PYTHON_311, count=1)

        request = ExecutionRequest(
            code="import os; print(os.environ.get('MY_VAR'))",
            runtime=Runtime.PYTHON_311,
            environment={"MY_VAR": "test_value"},
        )

        result = await executor.execute(request)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_with_stdin(self, executor, mock_docker_client):
        """Test execution with stdin."""
        await executor.pool_manager.warm_up(Runtime.PYTHON_311, count=1)

        request = ExecutionRequest(
            code="name = input(); print(f'Hello, {name}!')",
            runtime=Runtime.PYTHON_311,
            stdin="World",
        )

        result = await executor.execute(request)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_with_files(self, executor, mock_docker_client):
        """Test execution with additional files."""
        await executor.pool_manager.warm_up(Runtime.PYTHON_311, count=1)

        request = ExecutionRequest(
            code="from helper import greet; print(greet('World'))",
            runtime=Runtime.PYTHON_311,
            files={"helper.py": "def greet(name): return f'Hello, {name}!'"},
        )

        result = await executor.execute(request)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_timeout(self, executor, mock_docker_client):
        """Test execution timeout handling."""
        await executor.pool_manager.warm_up(Runtime.PYTHON_311, count=1)

        # Make exec_run simulate a long-running operation
        async def slow_exec(*args, **kwargs):
            import asyncio
            await asyncio.sleep(10)
            return MagicMock(exit_code=0, output=(b"", b""))

        with patch.object(
            executor,
            "_run_exec",
            side_effect=asyncio.TimeoutError(),
        ):
            request = ExecutionRequest(
                code="import time; time.sleep(100)",
                runtime=Runtime.PYTHON_311,
                timeout_ms=100,  # Very short timeout
            )

            with pytest.raises(Exception):  # Should raise timeout error
                await executor.execute(request)

    @pytest.mark.asyncio
    async def test_warm_up(self, executor):
        """Test warming up containers."""
        count = await executor.warm_up(Runtime.PYTHON_311, count=3)

        assert count == 3

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, executor, mock_docker_client):
        """Test health check when healthy."""
        await executor.pool_manager.warm_up(Runtime.PYTHON_311, count=2)

        status = await executor.health_check()

        assert status.healthy is True
        assert status.provider == ExecutorProvider.LOCAL_DOCKER
        assert status.pool_size >= 2

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, executor, mock_docker_client):
        """Test health check when Docker is unavailable."""
        mock_docker_client.ping.side_effect = Exception("Docker unavailable")

        status = await executor.health_check()

        assert status.healthy is False

    @pytest.mark.asyncio
    async def test_cleanup(self, executor):
        """Test executor cleanup."""
        await executor.pool_manager.warm_up(Runtime.PYTHON_311, count=2)

        await executor.cleanup()

        assert executor.pool_manager._started is False

    @pytest.mark.asyncio
    async def test_get_metrics(self, executor, mock_docker_client):
        """Test getting metrics."""
        await executor.pool_manager.warm_up(Runtime.PYTHON_311, count=1)

        # Execute a few times
        for _ in range(3):
            request = ExecutionRequest(
                code="print('Hello!')",
                runtime=Runtime.PYTHON_311,
            )
            await executor.execute(request)

        metrics = await executor.get_metrics()

        assert metrics.provider == ExecutorProvider.LOCAL_DOCKER
        assert metrics.total_executions == 3
        assert metrics.avg_execution_time_ms > 0

    @pytest.mark.asyncio
    async def test_metrics_tracking(self, executor, mock_docker_client):
        """Test metrics are properly tracked."""
        request = ExecutionRequest(
            code="print('Hello!')",
            runtime=Runtime.PYTHON_311,
        )

        await executor.execute(request)

        metrics = await executor.get_metrics()

        assert metrics.total_executions == 1
        assert metrics.successful_executions == 1
        assert metrics.cold_start_count == 1  # First execution is cold


class TestLocalDockerExecutorEdgeCases:
    """Edge case tests for LocalDockerExecutor."""

    @pytest.fixture
    def mock_docker_client(self):
        """Create mock Docker client."""
        client = MagicMock()
        client.ping.return_value = True
        client.images.get.return_value = MagicMock()

        container = MagicMock()
        container.id = "test_container_123"
        container.status = "running"
        container.exec_run.return_value = MagicMock(
            exit_code=0,
            output=(b"", b""),
        )

        client.containers.run.return_value = container

        return client

    @pytest.fixture
    def executor(self, mock_docker_client):
        """Create LocalDockerExecutor with mock client."""
        with patch("docker.from_env", return_value=mock_docker_client):
            return LocalDockerExecutor(pool_size_per_runtime=2)

    @pytest.mark.asyncio
    async def test_execute_with_error_output(self, executor, mock_docker_client):
        """Test execution that produces stderr."""
        mock_docker_client.containers.run.return_value.exec_run.return_value = MagicMock(
            exit_code=1,
            output=(b"", b"Error: something went wrong\n"),
        )

        await executor.pool_manager.warm_up(Runtime.PYTHON_311, count=1)

        request = ExecutionRequest(
            code="raise ValueError('test')",
            runtime=Runtime.PYTHON_311,
        )

        result = await executor.execute(request)

        assert result.success is False
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_execute_different_runtimes(self, executor, mock_docker_client):
        """Test execution with different runtimes."""
        await executor.pool_manager.warm_up(Runtime.PYTHON_311, count=1)
        await executor.pool_manager.warm_up(Runtime.NODE_20, count=1)

        # Python
        py_result = await executor.execute(
            ExecutionRequest(code="print('py')", runtime=Runtime.PYTHON_311)
        )
        assert py_result.success is True

        # Node
        node_result = await executor.execute(
            ExecutionRequest(code="console.log('js')", runtime=Runtime.NODE_20)
        )
        assert node_result.success is True


