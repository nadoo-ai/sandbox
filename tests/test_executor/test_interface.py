"""
Tests for executor interface and models.
"""

import pytest

from core.executor.interface import ExecutorProvider, Runtime
from core.executor.models import (
    ExecutionRequest,
    ExecutionResult,
    HealthStatus,
    ExecutorMetrics,
    PoolStatus,
)


class TestExecutorProvider:
    """Test ExecutorProvider enum."""

    def test_provider_values(self):
        """Test provider enum values."""
        assert ExecutorProvider.LOCAL_DOCKER.value == "local_docker"
        assert ExecutorProvider.AWS_LAMBDA.value == "aws_lambda"
        assert ExecutorProvider.GCP_CLOUD_RUN.value == "gcp_cloud_run"
        assert ExecutorProvider.AZURE_CONTAINER.value == "azure_container"

    def test_provider_from_string(self):
        """Test creating provider from string."""
        provider = ExecutorProvider("local_docker")
        assert provider == ExecutorProvider.LOCAL_DOCKER

    def test_invalid_provider(self):
        """Test invalid provider raises error."""
        with pytest.raises(ValueError):
            ExecutorProvider("invalid_provider")


class TestRuntime:
    """Test Runtime enum."""

    def test_runtime_values(self):
        """Test runtime enum values."""
        assert Runtime.PYTHON_311.value == "python:3.11"
        assert Runtime.NODE_20.value == "node:20"
        assert Runtime.GO_121.value == "go:1.21"

    def test_runtime_language(self):
        """Test runtime language property."""
        assert Runtime.PYTHON_311.language == "python"
        assert Runtime.NODE_20.language == "node"
        assert Runtime.GO_121.language == "go"

    def test_runtime_version(self):
        """Test runtime version property."""
        assert Runtime.PYTHON_311.version == "3.11"
        assert Runtime.NODE_20.version == "20"
        assert Runtime.GO_121.version == "1.21"

    def test_runtime_docker_image(self):
        """Test runtime docker image property."""
        assert Runtime.PYTHON_311.docker_image == "python:3.11-slim"
        assert Runtime.NODE_20.docker_image == "node:20-slim"
        assert Runtime.GO_121.docker_image == "golang:1.21-alpine"


class TestExecutionRequest:
    """Test ExecutionRequest model."""

    def test_create_request(self):
        """Test creating execution request."""
        request = ExecutionRequest(
            code="print('hello')",
            runtime=Runtime.PYTHON_311,
        )

        assert request.code == "print('hello')"
        assert request.runtime == Runtime.PYTHON_311
        assert request.entry_point == "main.py"
        assert request.timeout_ms == 30000
        assert request.memory_mb == 256
        assert request.execution_id is not None

    def test_request_with_options(self):
        """Test creating request with all options."""
        request = ExecutionRequest(
            code="print('hello')",
            runtime=Runtime.PYTHON_311,
            entry_point="app.py",
            timeout_ms=5000,
            memory_mb=128,
            cpu_cores=0.25,
            stdin="test input",
            environment={"KEY": "value"},
            files={"helper.py": "def foo(): pass"},
            workspace_id="ws-123",
            user_id="user-456",
        )

        assert request.entry_point == "app.py"
        assert request.timeout_ms == 5000
        assert request.memory_mb == 128
        assert request.cpu_cores == 0.25
        assert request.stdin == "test input"
        assert request.environment == {"KEY": "value"}
        assert "helper.py" in request.files
        assert request.workspace_id == "ws-123"
        assert request.user_id == "user-456"

    def test_request_validation_empty_code(self):
        """Test request validation for empty code."""
        with pytest.raises(ValueError, match="code cannot be empty"):
            ExecutionRequest(code="", runtime=Runtime.PYTHON_311)

    def test_request_validation_invalid_timeout(self):
        """Test request validation for invalid timeout."""
        with pytest.raises(ValueError, match="timeout_ms must be positive"):
            ExecutionRequest(
                code="print('hello')",
                runtime=Runtime.PYTHON_311,
                timeout_ms=-1,
            )

    def test_request_validation_invalid_memory(self):
        """Test request validation for invalid memory."""
        with pytest.raises(ValueError, match="memory_mb must be positive"):
            ExecutionRequest(
                code="print('hello')",
                runtime=Runtime.PYTHON_311,
                memory_mb=0,
            )


class TestExecutionResult:
    """Test ExecutionResult model."""

    def test_create_result(self):
        """Test creating execution result."""
        result = ExecutionResult(
            success=True,
            stdout="Hello, World!\n",
            stderr="",
            exit_code=0,
            execution_time_ms=50.0,
            cold_start=False,
            provider=ExecutorProvider.LOCAL_DOCKER,
        )

        assert result.success is True
        assert result.stdout == "Hello, World!\n"
        assert result.stderr == ""
        assert result.exit_code == 0
        assert result.execution_time_ms == 50.0
        assert result.cold_start is False
        assert result.provider == ExecutorProvider.LOCAL_DOCKER

    def test_result_total_time(self):
        """Test total time calculation."""
        result = ExecutionResult(
            success=True,
            stdout="",
            stderr="",
            exit_code=0,
            execution_time_ms=50.0,
            cold_start=False,
            provider=ExecutorProvider.LOCAL_DOCKER,
            queue_time_ms=10.0,
        )

        assert result.total_time_ms == 60.0

    def test_result_to_dict(self):
        """Test result to dict conversion."""
        result = ExecutionResult(
            success=True,
            stdout="output",
            stderr="",
            exit_code=0,
            execution_time_ms=50.0,
            cold_start=False,
            provider=ExecutorProvider.LOCAL_DOCKER,
        )

        d = result.to_dict()
        assert d["success"] is True
        assert d["stdout"] == "output"
        assert d["provider"] == "local_docker"
        assert d["execution_time_ms"] == 50.0


class TestHealthStatus:
    """Test HealthStatus model."""

    def test_create_health_status(self):
        """Test creating health status."""
        status = HealthStatus(
            healthy=True,
            provider=ExecutorProvider.LOCAL_DOCKER,
            message="OK",
            pool_size=10,
            available_containers=8,
            busy_containers=2,
        )

        assert status.healthy is True
        assert status.provider == ExecutorProvider.LOCAL_DOCKER
        assert status.pool_size == 10
        assert status.available_containers == 8
        assert status.busy_containers == 2

    def test_health_status_to_dict(self):
        """Test health status to dict conversion."""
        status = HealthStatus(
            healthy=True,
            provider=ExecutorProvider.LOCAL_DOCKER,
        )

        d = status.to_dict()
        assert d["healthy"] is True
        assert d["provider"] == "local_docker"
        assert "last_check" in d


class TestExecutorMetrics:
    """Test ExecutorMetrics model."""

    def test_create_metrics(self):
        """Test creating metrics."""
        metrics = ExecutorMetrics(
            provider=ExecutorProvider.LOCAL_DOCKER,
            total_executions=100,
            successful_executions=95,
            failed_executions=5,
        )

        assert metrics.total_executions == 100
        assert metrics.successful_executions == 95
        assert metrics.failed_executions == 5

    def test_metrics_success_rate(self):
        """Test success rate calculation."""
        metrics = ExecutorMetrics(
            provider=ExecutorProvider.LOCAL_DOCKER,
            total_executions=100,
            successful_executions=95,
            failed_executions=5,
        )

        assert metrics.success_rate == 0.95

    def test_metrics_success_rate_zero(self):
        """Test success rate when no executions."""
        metrics = ExecutorMetrics(
            provider=ExecutorProvider.LOCAL_DOCKER,
        )

        assert metrics.success_rate == 0.0

    def test_metrics_cold_start_ratio(self):
        """Test cold start ratio calculation."""
        metrics = ExecutorMetrics(
            provider=ExecutorProvider.LOCAL_DOCKER,
            cold_start_count=10,
            warm_start_count=90,
        )

        assert metrics.cold_start_ratio == 0.1

    def test_metrics_pool_hit_ratio(self):
        """Test pool hit ratio calculation."""
        metrics = ExecutorMetrics(
            provider=ExecutorProvider.LOCAL_DOCKER,
            pool_hits=80,
            pool_misses=20,
        )

        assert metrics.pool_hit_ratio == 0.8

    def test_metrics_to_dict(self):
        """Test metrics to dict conversion."""
        metrics = ExecutorMetrics(
            provider=ExecutorProvider.LOCAL_DOCKER,
            total_executions=100,
        )

        d = metrics.to_dict()
        assert d["provider"] == "local_docker"
        assert d["total_executions"] == 100
        assert "success_rate" in d


class TestPoolStatus:
    """Test PoolStatus model."""

    def test_create_pool_status(self):
        """Test creating pool status."""
        status = PoolStatus(
            runtime=Runtime.PYTHON_311,
            total=10,
            available=8,
            busy=2,
        )

        assert status.runtime == Runtime.PYTHON_311
        assert status.total == 10
        assert status.available == 8
        assert status.busy == 2

    def test_pool_utilization(self):
        """Test pool utilization calculation."""
        status = PoolStatus(
            runtime=Runtime.PYTHON_311,
            total=10,
            available=8,
            busy=2,
        )

        assert status.utilization == 0.2

    def test_pool_utilization_empty(self):
        """Test pool utilization when empty."""
        status = PoolStatus(
            runtime=Runtime.PYTHON_311,
            total=0,
            available=0,
            busy=0,
        )

        assert status.utilization == 0.0
