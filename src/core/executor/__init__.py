"""
Executor Abstraction Layer

Provider-agnostic execution interface for sandboxed code execution.
Supports multiple backends: Local Docker (Warm Pool), AWS Lambda, GCP Cloud Run, Azure Container Apps.
"""

from .interface import BaseExecutor, ExecutorProvider, Runtime
from .models import ExecutionRequest, ExecutionResult, HealthStatus, ExecutorMetrics, PoolStatus
from .registry import ExecutorRegistry
from .client import UnifiedExecutorClient
from .exceptions import (
    ExecutorError,
    ExecutorNotFoundError,
    ExecutorNotAvailableError,
    ExecutionTimeoutError,
    ExecutionResourceError,
)

__all__ = [
    # Interface
    "BaseExecutor",
    "ExecutorProvider",
    "Runtime",
    # Models
    "ExecutionRequest",
    "ExecutionResult",
    "HealthStatus",
    "ExecutorMetrics",
    "PoolStatus",
    # Registry & Client
    "ExecutorRegistry",
    "UnifiedExecutorClient",
    # Exceptions
    "ExecutorError",
    "ExecutorNotFoundError",
    "ExecutorNotAvailableError",
    "ExecutionTimeoutError",
    "ExecutionResourceError",
]
