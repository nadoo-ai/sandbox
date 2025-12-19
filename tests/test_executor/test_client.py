"""
Tests for unified executor client.
"""

import pytest

from core.executor.interface import ExecutorProvider, Runtime
from core.executor.client import UnifiedExecutorClient


class TestUnifiedExecutorClient:
    """Test UnifiedExecutorClient."""

    @pytest.mark.asyncio
    async def test_execute(self, mock_executor, reset_registry):
        """Test basic code execution."""
        client = UnifiedExecutorClient()

        result = await client.execute("print('hello')")

        assert result.success is True
        assert result.stdout == "Hello, World!\n"
        assert result.provider == ExecutorProvider.LOCAL_DOCKER

    @pytest.mark.asyncio
    async def test_execute_with_options(self, mock_executor, reset_registry):
        """Test execution with options."""
        client = UnifiedExecutorClient()

        result = await client.execute(
            code="print('hello')",
            runtime=Runtime.PYTHON_312,
            timeout_ms=5000,
            memory_mb=128,
            environment={"KEY": "value"},
        )

        assert result.success is True
        # Check that request was created with correct options
        request = mock_executor.execute_calls[-1]
        assert request.runtime == Runtime.PYTHON_312
        assert request.timeout_ms == 5000
        assert request.memory_mb == 128
        assert request.environment == {"KEY": "value"}

    @pytest.mark.asyncio
    async def test_execute_python(self, mock_executor, reset_registry):
        """Test Python execution convenience method."""
        client = UnifiedExecutorClient()

        result = await client.execute_python("print('hello')")

        assert result.success is True
        request = mock_executor.execute_calls[-1]
        assert request.runtime == Runtime.PYTHON_311

    @pytest.mark.asyncio
    async def test_execute_python_312(self, mock_executor, reset_registry):
        """Test Python 3.12 execution."""
        client = UnifiedExecutorClient()

        result = await client.execute_python("print('hello')", version="3.12")

        assert result.success is True
        request = mock_executor.execute_calls[-1]
        assert request.runtime == Runtime.PYTHON_312

    @pytest.mark.asyncio
    async def test_execute_node(self, mock_executor, reset_registry):
        """Test Node.js execution convenience method."""
        client = UnifiedExecutorClient()

        result = await client.execute_node("console.log('hello')")

        assert result.success is True
        request = mock_executor.execute_calls[-1]
        assert request.runtime == Runtime.NODE_20
        assert request.entry_point == "main.js"

    @pytest.mark.asyncio
    async def test_execute_go(self, mock_executor, reset_registry):
        """Test Go execution convenience method."""
        client = UnifiedExecutorClient()

        result = await client.execute_go('package main\nfunc main() {}')

        assert result.success is True
        request = mock_executor.execute_calls[-1]
        assert request.runtime == Runtime.GO_121
        assert request.entry_point == "main.go"

    @pytest.mark.asyncio
    async def test_execute_with_provider(self, mock_executor, reset_registry):
        """Test execution with specific provider."""
        client = UnifiedExecutorClient()

        result = await client.execute(
            code="print('hello')",
            provider=ExecutorProvider.LOCAL_DOCKER,
        )

        assert result.success is True
        assert result.provider == ExecutorProvider.LOCAL_DOCKER

    @pytest.mark.asyncio
    async def test_execute_with_default_provider(self, mock_executor, reset_registry):
        """Test execution with default provider set in client."""
        client = UnifiedExecutorClient(
            default_provider=ExecutorProvider.LOCAL_DOCKER,
        )

        result = await client.execute("print('hello')")

        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_without_fallback(self, mock_executor, reset_registry):
        """Test execution without fallback."""
        client = UnifiedExecutorClient(enable_fallback=False)

        result = await client.execute("print('hello')")

        assert result.success is True

    @pytest.mark.asyncio
    async def test_health_check(self, mock_executor, reset_registry):
        """Test health check."""
        client = UnifiedExecutorClient()

        status = await client.health_check()

        assert status.healthy is True
        assert status.provider == ExecutorProvider.LOCAL_DOCKER

    @pytest.mark.asyncio
    async def test_health_check_all(self, mock_executor, reset_registry):
        """Test health check for all providers."""
        client = UnifiedExecutorClient()

        results = await client.health_check_all()

        assert ExecutorProvider.LOCAL_DOCKER in results
        assert results[ExecutorProvider.LOCAL_DOCKER].healthy is True

    @pytest.mark.asyncio
    async def test_warm_up(self, mock_executor, reset_registry):
        """Test warm up."""
        client = UnifiedExecutorClient()

        count = await client.warm_up(Runtime.PYTHON_311, count=3)

        assert count == 3
        assert (Runtime.PYTHON_311, 3) in mock_executor.warmup_calls

    def test_get_available_providers(self, mock_executor, reset_registry):
        """Test getting available providers."""
        client = UnifiedExecutorClient()

        providers = client.get_available_providers()

        assert ExecutorProvider.LOCAL_DOCKER in providers

    def test_is_provider_available(self, mock_executor, reset_registry):
        """Test checking if provider is available."""
        client = UnifiedExecutorClient()

        assert client.is_provider_available(ExecutorProvider.LOCAL_DOCKER) is True
        assert client.is_provider_available(ExecutorProvider.AWS_LAMBDA) is False
