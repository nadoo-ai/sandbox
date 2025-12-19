"""
Executor Setup

Initialize and configure executors based on settings.
"""

import logging
from typing import List

from .config import Settings, get_settings
from .executor import (
    ExecutorProvider,
    ExecutorRegistry,
    UnifiedExecutorClient,
)
from .executor.providers import (
    LocalDockerExecutor,
    AWSLambdaExecutor,
    GCPCloudRunExecutor,
    AzureContainerExecutor,
)

logger = logging.getLogger(__name__)


async def setup_executors(settings: Settings = None) -> UnifiedExecutorClient:
    """
    Set up executors based on configuration.

    Args:
        settings: Settings instance (uses default if None)

    Returns:
        Configured UnifiedExecutorClient
    """
    settings = settings or get_settings()

    # Reset registry for clean state
    ExecutorRegistry.reset()

    # Set up Local Docker Executor (default)
    if settings.warm_pool_enabled:
        logger.info("Setting up Local Docker Executor with Warm Pool")

        local_executor = LocalDockerExecutor(
            pool_size_per_runtime=settings.warm_pool_size_per_runtime,
            max_idle_time_seconds=settings.warm_pool_max_idle_time,
            container_ttl_seconds=settings.warm_pool_container_ttl,
            health_check_interval_seconds=settings.warm_pool_health_check_interval,
            memory_limit=settings.max_memory,
            cpu_limit=settings.max_cpu,
        )

        ExecutorRegistry.register(ExecutorProvider.LOCAL_DOCKER, local_executor)
        logger.info("Local Docker Executor registered")

    # Set up AWS Lambda Executor
    if settings.aws_lambda_enabled:
        logger.info("Setting up AWS Lambda Executor")

        try:
            lambda_executor = AWSLambdaExecutor(
                region=settings.aws_lambda_region,
                function_prefix=settings.aws_lambda_function_prefix,
            )
            ExecutorRegistry.register(ExecutorProvider.AWS_LAMBDA, lambda_executor)
            logger.info("AWS Lambda Executor registered")
        except ImportError as e:
            logger.warning(f"AWS Lambda Executor not available: {e}")

    # Set up GCP Cloud Run Executor
    if settings.gcp_cloud_run_enabled and settings.gcp_project_id:
        logger.info("Setting up GCP Cloud Run Executor")

        try:
            gcp_executor = GCPCloudRunExecutor(
                project_id=settings.gcp_project_id,
                region=settings.gcp_region,
                job_prefix=settings.gcp_job_prefix,
            )
            ExecutorRegistry.register(ExecutorProvider.GCP_CLOUD_RUN, gcp_executor)
            logger.info("GCP Cloud Run Executor registered")
        except ImportError as e:
            logger.warning(f"GCP Cloud Run Executor not available: {e}")

    # Set up Azure Container Apps Executor
    if (
        settings.azure_container_enabled
        and settings.azure_subscription_id
        and settings.azure_resource_group
    ):
        logger.info("Setting up Azure Container Apps Executor")

        try:
            azure_executor = AzureContainerExecutor(
                subscription_id=settings.azure_subscription_id,
                resource_group=settings.azure_resource_group,
                job_prefix=settings.azure_job_prefix,
            )
            ExecutorRegistry.register(ExecutorProvider.AZURE_CONTAINER, azure_executor)
            logger.info("Azure Container Apps Executor registered")
        except ImportError as e:
            logger.warning(f"Azure Container Apps Executor not available: {e}")

    # Set default provider
    try:
        default_provider = ExecutorProvider(settings.executor_default_provider)
    except ValueError:
        logger.warning(
            f"Invalid default provider '{settings.executor_default_provider}', "
            "falling back to LOCAL_DOCKER"
        )
        default_provider = ExecutorProvider.LOCAL_DOCKER

    # Ensure default provider is registered
    if not ExecutorRegistry.is_registered(default_provider):
        available = ExecutorRegistry.get_available_providers()
        if available:
            default_provider = available[0]
            logger.warning(f"Default provider not available, using: {default_provider.value}")
        else:
            raise RuntimeError("No executor providers available")

    ExecutorRegistry.set_default(default_provider)
    logger.info(f"Default executor provider: {default_provider.value}")

    # Set fallback chain
    if settings.executor_fallback_enabled:
        fallback_chain: List[ExecutorProvider] = []
        for provider_str in settings.executor_fallback_chain.split(","):
            provider_str = provider_str.strip()
            if provider_str:
                try:
                    provider = ExecutorProvider(provider_str)
                    if ExecutorRegistry.is_registered(provider):
                        fallback_chain.append(provider)
                except ValueError:
                    logger.warning(f"Unknown provider in fallback chain: {provider_str}")

        ExecutorRegistry.set_fallback_chain(fallback_chain)
        logger.info(f"Fallback chain: {[p.value for p in fallback_chain]}")

    # Initialize all registered executors
    await ExecutorRegistry.initialize_all()

    # Create and return client
    client = UnifiedExecutorClient(
        default_provider=default_provider,
        enable_fallback=settings.executor_fallback_enabled,
    )

    logger.info("Executor setup complete")
    return client


async def cleanup_executors() -> None:
    """Cleanup all executors on shutdown"""
    logger.info("Cleaning up executors")
    await ExecutorRegistry.cleanup_all()
    logger.info("Executor cleanup complete")


# Global client instance
_executor_client: UnifiedExecutorClient = None


async def get_executor_client() -> UnifiedExecutorClient:
    """Get the global executor client instance"""
    global _executor_client

    if _executor_client is None:
        _executor_client = await setup_executors()

    return _executor_client


def get_executor_client_sync() -> UnifiedExecutorClient:
    """Get executor client synchronously (must be initialized first)"""
    global _executor_client

    if _executor_client is None:
        raise RuntimeError("Executor client not initialized. Call setup_executors() first.")

    return _executor_client
