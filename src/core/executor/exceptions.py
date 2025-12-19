"""
Executor Exceptions

Custom exceptions for executor operations.
"""

from typing import Optional

from .interface import ExecutorProvider


class ExecutorError(Exception):
    """Base exception for executor errors"""

    def __init__(self, message: str, provider: Optional[ExecutorProvider] = None):
        self.message = message
        self.provider = provider
        super().__init__(message)


class ExecutorNotFoundError(ExecutorError):
    """Raised when requested executor provider is not registered"""

    def __init__(self, provider: ExecutorProvider):
        super().__init__(
            f"Executor provider not registered: {provider.value}",
            provider=provider,
        )


class ExecutorNotAvailableError(ExecutorError):
    """Raised when executor provider is not available (unhealthy or all failed)"""

    def __init__(
        self,
        message: str = "No executor provider available",
        provider: Optional[ExecutorProvider] = None,
        last_error: Optional[Exception] = None,
    ):
        self.last_error = last_error
        super().__init__(message, provider=provider)


class ExecutionTimeoutError(ExecutorError):
    """Raised when execution exceeds timeout limit"""

    def __init__(
        self,
        timeout_ms: int,
        provider: Optional[ExecutorProvider] = None,
        execution_id: Optional[str] = None,
    ):
        self.timeout_ms = timeout_ms
        self.execution_id = execution_id
        super().__init__(
            f"Execution timed out after {timeout_ms}ms",
            provider=provider,
        )


class ExecutionResourceError(ExecutorError):
    """Raised when execution exceeds resource limits (memory, CPU, etc.)"""

    def __init__(
        self,
        resource: str,
        limit: str,
        actual: Optional[str] = None,
        provider: Optional[ExecutorProvider] = None,
        execution_id: Optional[str] = None,
    ):
        self.resource = resource
        self.limit = limit
        self.actual = actual
        self.execution_id = execution_id
        message = f"Resource limit exceeded: {resource} (limit: {limit}"
        if actual:
            message += f", actual: {actual}"
        message += ")"
        super().__init__(message, provider=provider)


class ContainerError(ExecutorError):
    """Raised when container operations fail"""

    def __init__(
        self,
        message: str,
        container_id: Optional[str] = None,
        provider: Optional[ExecutorProvider] = None,
    ):
        self.container_id = container_id
        super().__init__(message, provider=provider)


class WarmPoolError(ExecutorError):
    """Raised when warm pool operations fail"""

    def __init__(
        self,
        message: str,
        pool_size: Optional[int] = None,
        provider: Optional[ExecutorProvider] = None,
    ):
        self.pool_size = pool_size
        super().__init__(message, provider=provider)
