"""
Base Executor Interface

Abstract base class for all execution providers.
New providers should inherit from BaseExecutor and implement all abstract methods.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import ExecutionRequest, ExecutionResult, HealthStatus, ExecutorMetrics


class ExecutorProvider(str, Enum):
    """Supported execution environment providers"""

    LOCAL_DOCKER = "local_docker"
    AWS_LAMBDA = "aws_lambda"
    GCP_CLOUD_RUN = "gcp_cloud_run"
    AZURE_CONTAINER = "azure_container"


class Runtime(str, Enum):
    """Supported runtime environments"""

    # Python
    PYTHON_311 = "python:3.11"
    PYTHON_312 = "python:3.12"

    # Node.js
    NODE_20 = "node:20"
    NODE_22 = "node:22"

    # Go
    GO_121 = "go:1.21"
    GO_122 = "go:1.22"

    # Others
    RUST_LATEST = "rust:latest"
    JAVA_17 = "java:17"
    JAVA_21 = "java:21"

    @property
    def language(self) -> str:
        """Extract language name from runtime"""
        return self.value.split(":")[0]

    @property
    def version(self) -> str:
        """Extract version from runtime"""
        return self.value.split(":")[1]

    @property
    def docker_image(self) -> str:
        """Get corresponding Docker image name"""
        image_map = {
            "python:3.11": "python:3.11-slim",
            "python:3.12": "python:3.12-slim",
            "node:20": "node:20-slim",
            "node:22": "node:22-slim",
            "go:1.21": "golang:1.21-alpine",
            "go:1.22": "golang:1.22-alpine",
            "rust:latest": "rust:latest",
            "java:17": "openjdk:17-slim",
            "java:21": "openjdk:21-slim",
        }
        return image_map.get(self.value, self.value)


class BaseExecutor(ABC):
    """
    Abstract base class for all execution providers.

    All providers must implement these methods:
    - execute(): Run code in isolated environment
    - warm_up(): Pre-warm execution environments
    - health_check(): Check provider health
    - cleanup(): Release resources
    - get_metrics(): Get execution metrics

    Example:
        class MyExecutor(BaseExecutor):
            provider = ExecutorProvider.LOCAL_DOCKER

            async def execute(self, request):
                # Implementation
                pass
    """

    provider: ExecutorProvider

    @abstractmethod
    async def execute(self, request: "ExecutionRequest") -> "ExecutionResult":
        """
        Execute code in an isolated environment.

        Args:
            request: Execution request containing code, runtime, and options

        Returns:
            ExecutionResult with stdout, stderr, exit_code, and metrics

        Raises:
            ExecutionTimeoutError: When execution exceeds timeout
            ExecutionResourceError: When resource limits are exceeded
            ExecutorNotAvailableError: When provider is unavailable
        """
        pass

    @abstractmethod
    async def warm_up(self, runtime: Runtime, count: int = 1) -> int:
        """
        Pre-warm execution environments for faster cold starts.

        Args:
            runtime: Runtime to warm up
            count: Number of instances to prepare

        Returns:
            Number of instances actually prepared
        """
        pass

    @abstractmethod
    async def health_check(self) -> "HealthStatus":
        """
        Check provider health and availability.

        Returns:
            HealthStatus with healthy flag and details
        """
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """
        Release all resources held by this executor.

        Called during service shutdown.
        """
        pass

    @abstractmethod
    async def get_metrics(self) -> "ExecutorMetrics":
        """
        Get execution metrics for this provider.

        Returns:
            ExecutorMetrics with execution counts, latencies, etc.
        """
        pass

    async def initialize(self) -> None:
        """
        Initialize the executor.

        Override this method to perform async initialization.
        Called during service startup.
        """
        pass
