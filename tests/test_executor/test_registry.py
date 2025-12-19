"""
Tests for executor registry.
"""

import pytest

from core.executor.interface import ExecutorProvider, Runtime
from core.executor.registry import ExecutorRegistry
from core.executor.exceptions import ExecutorNotFoundError, ExecutorNotAvailableError
from core.executor.models import ExecutionRequest


class TestExecutorRegistry:
    """Test ExecutorRegistry."""

    def test_register_executor(self, mock_executor, reset_registry):
        """Test registering an executor."""
        # mock_executor fixture already registers the executor
        providers = ExecutorRegistry.get_available_providers()
        assert ExecutorProvider.LOCAL_DOCKER in providers

    def test_get_executor(self, mock_executor, reset_registry):
        """Test getting an executor."""
        executor = ExecutorRegistry.get(ExecutorProvider.LOCAL_DOCKER)
        assert executor is not None
        assert executor.provider == ExecutorProvider.LOCAL_DOCKER

    def test_get_default_executor(self, mock_executor, reset_registry):
        """Test getting default executor."""
        executor = ExecutorRegistry.get()
        assert executor is not None

    def test_get_nonexistent_executor(self, reset_registry):
        """Test getting non-existent executor raises error."""
        with pytest.raises(ExecutorNotFoundError):
            ExecutorRegistry.get(ExecutorProvider.AWS_LAMBDA)

    def test_unregister_executor(self, mock_executor, reset_registry):
        """Test unregistering an executor."""
        ExecutorRegistry.unregister(ExecutorProvider.LOCAL_DOCKER)
        assert not ExecutorRegistry.is_registered(ExecutorProvider.LOCAL_DOCKER)

    def test_set_default_provider(self, mock_executor, reset_registry):
        """Test setting default provider."""
        ExecutorRegistry.set_default(ExecutorProvider.LOCAL_DOCKER)
        assert ExecutorRegistry.get_default() == ExecutorProvider.LOCAL_DOCKER

    def test_set_fallback_chain(self, mock_executor, reset_registry):
        """Test setting fallback chain."""
        chain = [ExecutorProvider.AWS_LAMBDA, ExecutorProvider.GCP_CLOUD_RUN]
        ExecutorRegistry.set_fallback_chain(chain)
        assert ExecutorRegistry.get_fallback_chain() == chain

    def test_is_registered(self, mock_executor, reset_registry):
        """Test checking if provider is registered."""
        assert ExecutorRegistry.is_registered(ExecutorProvider.LOCAL_DOCKER)
        assert not ExecutorRegistry.is_registered(ExecutorProvider.AWS_LAMBDA)

    def test_get_or_none(self, mock_executor, reset_registry):
        """Test get_or_none method."""
        executor = ExecutorRegistry.get_or_none(ExecutorProvider.LOCAL_DOCKER)
        assert executor is not None

        executor = ExecutorRegistry.get_or_none(ExecutorProvider.AWS_LAMBDA)
        assert executor is None

    @pytest.mark.asyncio
    async def test_execute_with_fallback(self, mock_executor, reset_registry):
        """Test execute with fallback."""
        request = ExecutionRequest(
            code="print('hello')",
            runtime=Runtime.PYTHON_311,
        )

        result = await ExecutorRegistry.execute_with_fallback(request)

        assert result.success is True
        assert result.stdout == "Hello, World!\n"

    @pytest.mark.asyncio
    async def test_execute_with_fallback_no_providers(self, reset_registry):
        """Test execute with fallback when no providers available."""
        request = ExecutionRequest(
            code="print('hello')",
            runtime=Runtime.PYTHON_311,
        )

        with pytest.raises(ExecutorNotAvailableError):
            await ExecutorRegistry.execute_with_fallback(request)

    @pytest.mark.asyncio
    async def test_execute_with_preferred_provider(self, mock_executor, reset_registry):
        """Test execute with preferred provider."""
        request = ExecutionRequest(
            code="print('hello')",
            runtime=Runtime.PYTHON_311,
            preferred_provider=ExecutorProvider.LOCAL_DOCKER,
        )

        result = await ExecutorRegistry.execute_with_fallback(request)

        assert result.success is True
        assert len(mock_executor.execute_calls) == 1

    @pytest.mark.asyncio
    async def test_initialize_all(self, mock_executor, reset_registry):
        """Test initializing all executors."""
        await ExecutorRegistry.initialize_all()
        # Should not raise

    @pytest.mark.asyncio
    async def test_cleanup_all(self, mock_executor, reset_registry):
        """Test cleaning up all executors."""
        await ExecutorRegistry.cleanup_all()
        # Should not raise

    def test_reset(self, mock_executor):
        """Test resetting registry."""
        ExecutorRegistry.reset()

        assert len(ExecutorRegistry.get_available_providers()) == 0
        assert ExecutorRegistry.get_default() == ExecutorProvider.LOCAL_DOCKER
