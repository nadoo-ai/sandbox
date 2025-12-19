"""
Executor Provider Registry

Singleton registry for managing execution providers.
Supports fallback chains for high availability.
"""

import logging
from typing import Dict, List, Optional

from .interface import BaseExecutor, ExecutorProvider
from .models import ExecutionRequest, ExecutionResult
from .exceptions import ExecutorNotFoundError, ExecutorNotAvailableError

logger = logging.getLogger(__name__)


class ExecutorRegistry:
    """
    Singleton registry for executor providers.

    Manages provider registration, lookup, and fallback chains.

    Example:
        # Register providers
        ExecutorRegistry.register(ExecutorProvider.LOCAL_DOCKER, docker_executor)
        ExecutorRegistry.register(ExecutorProvider.AWS_LAMBDA, lambda_executor)

        # Set default and fallback
        ExecutorRegistry.set_default(ExecutorProvider.LOCAL_DOCKER)
        ExecutorRegistry.set_fallback_chain([ExecutorProvider.AWS_LAMBDA])

        # Execute with automatic fallback
        result = await ExecutorRegistry.execute_with_fallback(request)
    """

    _instance: Optional["ExecutorRegistry"] = None
    _executors: Dict[ExecutorProvider, BaseExecutor] = {}
    _default_provider: ExecutorProvider = ExecutorProvider.LOCAL_DOCKER
    _fallback_chain: List[ExecutorProvider] = []
    _initialized: bool = False

    def __new__(cls) -> "ExecutorRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(cls, provider: ExecutorProvider, executor: BaseExecutor) -> None:
        """
        Register an executor for a provider.

        Args:
            provider: Provider type
            executor: Executor instance
        """
        cls._executors[provider] = executor
        logger.info(f"Registered executor for provider: {provider.value}")

    @classmethod
    def unregister(cls, provider: ExecutorProvider) -> None:
        """
        Unregister an executor.

        Args:
            provider: Provider to unregister
        """
        if provider in cls._executors:
            del cls._executors[provider]
            logger.info(f"Unregistered executor for provider: {provider.value}")

    @classmethod
    def get(cls, provider: Optional[ExecutorProvider] = None) -> BaseExecutor:
        """
        Get executor for provider.

        Args:
            provider: Provider type (uses default if None)

        Returns:
            BaseExecutor instance

        Raises:
            ExecutorNotFoundError: If provider not registered
        """
        target = provider or cls._default_provider

        if target not in cls._executors:
            raise ExecutorNotFoundError(target)

        return cls._executors[target]

    @classmethod
    def get_or_none(cls, provider: ExecutorProvider) -> Optional[BaseExecutor]:
        """
        Get executor for provider, returning None if not found.

        Args:
            provider: Provider type

        Returns:
            BaseExecutor instance or None
        """
        return cls._executors.get(provider)

    @classmethod
    def set_default(cls, provider: ExecutorProvider) -> None:
        """
        Set default provider.

        Args:
            provider: Provider to use as default
        """
        cls._default_provider = provider
        logger.info(f"Set default provider: {provider.value}")

    @classmethod
    def get_default(cls) -> ExecutorProvider:
        """Get current default provider"""
        return cls._default_provider

    @classmethod
    def set_fallback_chain(cls, chain: List[ExecutorProvider]) -> None:
        """
        Set fallback chain for automatic failover.

        Args:
            chain: List of providers to try in order after default fails
        """
        cls._fallback_chain = chain
        logger.info(f"Set fallback chain: {[p.value for p in chain]}")

    @classmethod
    def get_fallback_chain(cls) -> List[ExecutorProvider]:
        """Get current fallback chain"""
        return cls._fallback_chain.copy()

    @classmethod
    def get_available_providers(cls) -> List[ExecutorProvider]:
        """Get list of registered providers"""
        return list(cls._executors.keys())

    @classmethod
    def is_registered(cls, provider: ExecutorProvider) -> bool:
        """Check if provider is registered"""
        return provider in cls._executors

    @classmethod
    async def execute_with_fallback(cls, request: ExecutionRequest) -> ExecutionResult:
        """
        Execute request with automatic fallback on failure.

        Tries providers in order: preferred -> default -> fallback chain

        Args:
            request: Execution request

        Returns:
            ExecutionResult from first successful provider

        Raises:
            ExecutorNotAvailableError: If all providers fail
        """
        # Build provider order: preferred -> default -> fallback chain
        providers: List[ExecutorProvider] = []

        if request.preferred_provider and request.preferred_provider in cls._executors:
            providers.append(request.preferred_provider)

        if cls._default_provider not in providers and cls._default_provider in cls._executors:
            providers.append(cls._default_provider)

        for provider in cls._fallback_chain:
            if provider not in providers and provider in cls._executors:
                providers.append(provider)

        if not providers:
            raise ExecutorNotAvailableError("No executor providers registered")

        last_error: Optional[Exception] = None

        for provider in providers:
            executor = cls._executors[provider]

            try:
                # Check health first
                health = await executor.health_check()
                if not health.healthy:
                    logger.warning(
                        f"Provider {provider.value} unhealthy: {health.message}"
                    )
                    continue

                # Execute
                logger.debug(f"Executing with provider: {provider.value}")
                result = await executor.execute(request)
                return result

            except Exception as e:
                logger.warning(
                    f"Provider {provider.value} failed: {e}",
                    exc_info=True,
                )
                last_error = e
                continue

        raise ExecutorNotAvailableError(
            f"All providers failed. Tried: {[p.value for p in providers]}",
            last_error=last_error,
        )

    @classmethod
    async def initialize_all(cls) -> None:
        """Initialize all registered executors"""
        if cls._initialized:
            return

        for provider, executor in cls._executors.items():
            try:
                logger.info(f"Initializing executor: {provider.value}")
                await executor.initialize()
            except Exception as e:
                logger.error(f"Failed to initialize {provider.value}: {e}")
                raise

        cls._initialized = True
        logger.info("All executors initialized")

    @classmethod
    async def cleanup_all(cls) -> None:
        """Cleanup all registered executors"""
        for provider, executor in cls._executors.items():
            try:
                logger.info(f"Cleaning up executor: {provider.value}")
                await executor.cleanup()
            except Exception as e:
                logger.error(f"Failed to cleanup {provider.value}: {e}")

        cls._initialized = False
        logger.info("All executors cleaned up")

    @classmethod
    def reset(cls) -> None:
        """Reset registry state (for testing)"""
        cls._executors.clear()
        cls._default_provider = ExecutorProvider.LOCAL_DOCKER
        cls._fallback_chain.clear()
        cls._initialized = False
