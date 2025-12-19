"""
Unified Executor Client

High-level client for executing code across different providers.
Provides a simple interface for workflows and plugins.
"""

import logging
from typing import Dict, Optional

from .interface import ExecutorProvider, Runtime
from .models import ExecutionRequest, ExecutionResult, HealthStatus
from .registry import ExecutorRegistry

logger = logging.getLogger(__name__)


class UnifiedExecutorClient:
    """
    Unified client for code execution.

    Provides a simple, high-level interface for executing code across
    different providers with automatic fallback support.

    Example:
        client = UnifiedExecutorClient()

        # Simple execution
        result = await client.execute("print('hello')")

        # With options
        result = await client.execute(
            code="console.log('hello')",
            runtime=Runtime.NODE_20,
            timeout_ms=5000,
        )

        # Specify provider
        result = await client.execute(
            code="print('hello')",
            provider=ExecutorProvider.AWS_LAMBDA,
        )
    """

    def __init__(
        self,
        default_provider: Optional[ExecutorProvider] = None,
        enable_fallback: bool = True,
    ):
        """
        Initialize executor client.

        Args:
            default_provider: Default provider to use (overrides registry default)
            enable_fallback: Whether to enable automatic fallback on failure
        """
        self.default_provider = default_provider
        self.enable_fallback = enable_fallback

    async def execute(
        self,
        code: str,
        runtime: Runtime = Runtime.PYTHON_311,
        timeout_ms: int = 30000,
        memory_mb: int = 256,
        cpu_cores: float = 0.5,
        stdin: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
        files: Optional[Dict[str, str]] = None,
        entry_point: str = "main.py",
        provider: Optional[ExecutorProvider] = None,
        workspace_id: Optional[str] = None,
        user_id: Optional[str] = None,
        **kwargs,
    ) -> ExecutionResult:
        """
        Execute code in an isolated environment.

        Args:
            code: Code to execute
            runtime: Runtime environment (default: Python 3.11)
            timeout_ms: Execution timeout in milliseconds
            memory_mb: Memory limit in MB
            cpu_cores: CPU core limit
            stdin: Standard input
            environment: Environment variables
            files: Additional files (filename -> content)
            entry_point: Entry point filename
            provider: Specific provider to use
            workspace_id: Workspace ID for tracking
            user_id: User ID for tracking
            **kwargs: Additional options

        Returns:
            ExecutionResult with stdout, stderr, exit_code, and metrics
        """
        request = ExecutionRequest(
            code=code,
            runtime=runtime,
            entry_point=entry_point,
            timeout_ms=timeout_ms,
            memory_mb=memory_mb,
            cpu_cores=cpu_cores,
            stdin=stdin,
            environment=environment or {},
            files=files or {},
            preferred_provider=provider or self.default_provider,
            workspace_id=workspace_id,
            user_id=user_id,
        )

        if self.enable_fallback:
            return await ExecutorRegistry.execute_with_fallback(request)
        else:
            provider = request.preferred_provider or ExecutorRegistry.get_default()
            executor = ExecutorRegistry.get(provider)
            return await executor.execute(request)

    async def execute_python(
        self,
        code: str,
        version: str = "3.11",
        **kwargs,
    ) -> ExecutionResult:
        """
        Execute Python code.

        Args:
            code: Python code to execute
            version: Python version ("3.11" or "3.12")
            **kwargs: Additional options

        Returns:
            ExecutionResult
        """
        runtime = Runtime.PYTHON_312 if version == "3.12" else Runtime.PYTHON_311
        return await self.execute(code, runtime=runtime, entry_point="main.py", **kwargs)

    async def execute_node(
        self,
        code: str,
        version: str = "20",
        **kwargs,
    ) -> ExecutionResult:
        """
        Execute Node.js code.

        Args:
            code: JavaScript code to execute
            version: Node version ("20" or "22")
            **kwargs: Additional options

        Returns:
            ExecutionResult
        """
        runtime = Runtime.NODE_22 if version == "22" else Runtime.NODE_20
        return await self.execute(code, runtime=runtime, entry_point="main.js", **kwargs)

    async def execute_go(
        self,
        code: str,
        version: str = "1.21",
        **kwargs,
    ) -> ExecutionResult:
        """
        Execute Go code.

        Args:
            code: Go code to execute
            version: Go version ("1.21" or "1.22")
            **kwargs: Additional options

        Returns:
            ExecutionResult
        """
        runtime = Runtime.GO_122 if version == "1.22" else Runtime.GO_121
        return await self.execute(code, runtime=runtime, entry_point="main.go", **kwargs)

    async def health_check(
        self,
        provider: Optional[ExecutorProvider] = None,
    ) -> HealthStatus:
        """
        Check health of a specific provider.

        Args:
            provider: Provider to check (uses default if None)

        Returns:
            HealthStatus
        """
        executor = ExecutorRegistry.get(provider or self.default_provider)
        return await executor.health_check()

    async def health_check_all(self) -> Dict[ExecutorProvider, HealthStatus]:
        """
        Check health of all registered providers.

        Returns:
            Dict mapping provider to its health status
        """
        results: Dict[ExecutorProvider, HealthStatus] = {}

        for provider in ExecutorRegistry.get_available_providers():
            try:
                executor = ExecutorRegistry.get(provider)
                status = await executor.health_check()
                results[provider] = status
            except Exception as e:
                logger.error(f"Health check failed for {provider.value}: {e}")
                results[provider] = HealthStatus(
                    healthy=False,
                    provider=provider,
                    message=str(e),
                )

        return results

    async def warm_up(
        self,
        runtime: Runtime,
        count: int = 1,
        provider: Optional[ExecutorProvider] = None,
    ) -> int:
        """
        Pre-warm execution environments.

        Args:
            runtime: Runtime to warm up
            count: Number of instances to prepare
            provider: Provider to warm up (uses default if None)

        Returns:
            Number of instances actually prepared
        """
        executor = ExecutorRegistry.get(provider or self.default_provider)
        return await executor.warm_up(runtime, count)

    def get_available_providers(self) -> list[ExecutorProvider]:
        """Get list of available providers"""
        return ExecutorRegistry.get_available_providers()

    def is_provider_available(self, provider: ExecutorProvider) -> bool:
        """Check if provider is available"""
        return ExecutorRegistry.is_registered(provider)
