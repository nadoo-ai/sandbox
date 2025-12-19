"""
Pytest configuration and fixtures for Nadoo Sandbox tests
"""

import asyncio
import os
import sys
from typing import Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def api_key():
    """Test API key"""
    return "test-api-key-12345"


@pytest.fixture
def client():
    """FastAPI test client"""
    from main import app

    return TestClient(app)


@pytest.fixture
def auth_headers(api_key):
    """Authentication headers for API requests"""
    return {"X-API-Key": api_key}


# ============== Executor Fixtures ==============


@pytest.fixture
def mock_docker_client():
    """Mock Docker client."""
    client = MagicMock()
    client.ping.return_value = True
    client.images.get.return_value = MagicMock()
    client.images.pull.return_value = MagicMock()

    # Mock container
    container = MagicMock()
    container.id = "test_container_123456789"
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
def mock_container(mock_docker_client):
    """Mock Docker container."""
    return mock_docker_client.containers.run.return_value


@pytest.fixture
def sample_code():
    """Sample code for testing."""
    return {
        "python": "print('Hello, World!')",
        "python_with_input": "name = input(); print(f'Hello, {name}!')",
        "python_error": "raise ValueError('Test error')",
        "python_timeout": "import time; time.sleep(100)",
        "node": "console.log('Hello, World!');",
        "go": 'package main\nimport "fmt"\nfunc main() { fmt.Println("Hello, World!") }',
    }


@pytest.fixture
def execution_request():
    """Create sample execution request."""
    from core.executor.models import ExecutionRequest
    from core.executor.interface import Runtime

    return ExecutionRequest(
        code="print('Hello, World!')",
        runtime=Runtime.PYTHON_311,
        timeout_ms=30000,
        memory_mb=256,
    )


@pytest.fixture
def execution_result():
    """Create sample execution result."""
    from core.executor.models import ExecutionResult
    from core.executor.interface import ExecutorProvider

    return ExecutionResult(
        success=True,
        stdout="Hello, World!\n",
        stderr="",
        exit_code=0,
        execution_time_ms=50.0,
        cold_start=False,
        provider=ExecutorProvider.LOCAL_DOCKER,
    )


@pytest.fixture
def reset_registry():
    """Reset executor registry before and after each test."""
    from core.executor.registry import ExecutorRegistry

    ExecutorRegistry.reset()
    yield
    ExecutorRegistry.reset()


@pytest.fixture
def mock_executor(reset_registry):
    """Create and register a mock executor."""
    from core.executor.interface import BaseExecutor, ExecutorProvider
    from core.executor.models import ExecutionResult, HealthStatus, ExecutorMetrics
    from core.executor.registry import ExecutorRegistry

    class MockExecutor(BaseExecutor):
        provider = ExecutorProvider.LOCAL_DOCKER

        def __init__(self):
            self._healthy = True
            self._metrics = ExecutorMetrics(provider=self.provider)
            self.execute_calls = []
            self.warmup_calls = []

        async def execute(self, request):
            self.execute_calls.append(request)
            return ExecutionResult(
                success=True,
                stdout="Hello, World!\n",
                stderr="",
                exit_code=0,
                execution_time_ms=50.0,
                cold_start=False,
                provider=self.provider,
                execution_id=request.execution_id,
            )

        async def warm_up(self, runtime, count=1):
            self.warmup_calls.append((runtime, count))
            return count

        async def health_check(self):
            return HealthStatus(
                healthy=self._healthy,
                provider=self.provider,
                message="OK" if self._healthy else "Unhealthy",
                pool_size=5,
                available_containers=3,
                busy_containers=2,
            )

        async def cleanup(self):
            pass

        async def get_metrics(self):
            return self._metrics

        async def initialize(self):
            pass

    executor = MockExecutor()
    ExecutorRegistry.register(ExecutorProvider.LOCAL_DOCKER, executor)
    ExecutorRegistry.set_default(ExecutorProvider.LOCAL_DOCKER)

    return executor
