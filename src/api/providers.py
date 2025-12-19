"""
Provider Management API

Endpoints for managing and monitoring execution providers.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core.executor import (
    ExecutorProvider,
    ExecutorRegistry,
    Runtime,
)
from ..utils.auth import verify_api_key

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])


# Response Models
class ProviderInfo(BaseModel):
    """Provider information"""

    name: str
    healthy: bool
    message: str = ""
    pool_size: int = 0
    available: int = 0
    busy: int = 0


class ProvidersResponse(BaseModel):
    """List of providers response"""

    providers: List[ProviderInfo]
    default: str
    fallback_chain: List[str]


class MetricsResponse(BaseModel):
    """Provider metrics response"""

    provider: str
    total_executions: int
    successful_executions: int
    failed_executions: int
    timeout_executions: int
    success_rate: float
    avg_execution_time_ms: float
    p50_execution_time_ms: float
    p95_execution_time_ms: float
    p99_execution_time_ms: float
    cold_start_count: int
    warm_start_count: int
    cold_start_ratio: float
    pool_hits: int
    pool_misses: int
    pool_hit_ratio: float


class WarmUpRequest(BaseModel):
    """Warm up request"""

    runtime: str = "python:3.11"
    count: int = 1


class WarmUpResponse(BaseModel):
    """Warm up response"""

    runtime: str
    requested: int
    warmed: int


@router.get("", response_model=ProvidersResponse)
async def list_providers(api_key: str = Depends(verify_api_key)):
    """
    List all registered providers with their status.
    """
    providers_info: List[ProviderInfo] = []

    for provider in ExecutorRegistry.get_available_providers():
        try:
            executor = ExecutorRegistry.get(provider)
            health = await executor.health_check()

            providers_info.append(
                ProviderInfo(
                    name=provider.value,
                    healthy=health.healthy,
                    message=health.message,
                    pool_size=health.pool_size,
                    available=health.available_containers,
                    busy=health.busy_containers,
                )
            )
        except Exception as e:
            providers_info.append(
                ProviderInfo(
                    name=provider.value,
                    healthy=False,
                    message=str(e),
                )
            )

    return ProvidersResponse(
        providers=providers_info,
        default=ExecutorRegistry.get_default().value,
        fallback_chain=[p.value for p in ExecutorRegistry.get_fallback_chain()],
    )


@router.get("/{provider}", response_model=ProviderInfo)
async def get_provider_status(
    provider: str,
    api_key: str = Depends(verify_api_key),
):
    """
    Get status of a specific provider.
    """
    try:
        executor_provider = ExecutorProvider(provider)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    if not ExecutorRegistry.is_registered(executor_provider):
        raise HTTPException(status_code=404, detail=f"Provider not registered: {provider}")

    executor = ExecutorRegistry.get(executor_provider)
    health = await executor.health_check()

    return ProviderInfo(
        name=provider,
        healthy=health.healthy,
        message=health.message,
        pool_size=health.pool_size,
        available=health.available_containers,
        busy=health.busy_containers,
    )


@router.get("/{provider}/metrics", response_model=MetricsResponse)
async def get_provider_metrics(
    provider: str,
    api_key: str = Depends(verify_api_key),
):
    """
    Get execution metrics for a provider.
    """
    try:
        executor_provider = ExecutorProvider(provider)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    if not ExecutorRegistry.is_registered(executor_provider):
        raise HTTPException(status_code=404, detail=f"Provider not registered: {provider}")

    executor = ExecutorRegistry.get(executor_provider)
    metrics = await executor.get_metrics()

    return MetricsResponse(
        provider=metrics.provider.value,
        total_executions=metrics.total_executions,
        successful_executions=metrics.successful_executions,
        failed_executions=metrics.failed_executions,
        timeout_executions=metrics.timeout_executions,
        success_rate=metrics.success_rate,
        avg_execution_time_ms=metrics.avg_execution_time_ms,
        p50_execution_time_ms=metrics.p50_execution_time_ms,
        p95_execution_time_ms=metrics.p95_execution_time_ms,
        p99_execution_time_ms=metrics.p99_execution_time_ms,
        cold_start_count=metrics.cold_start_count,
        warm_start_count=metrics.warm_start_count,
        cold_start_ratio=metrics.cold_start_ratio,
        pool_hits=metrics.pool_hits,
        pool_misses=metrics.pool_misses,
        pool_hit_ratio=metrics.pool_hit_ratio,
    )


@router.post("/{provider}/warmup", response_model=WarmUpResponse)
async def warm_up_provider(
    provider: str,
    request: WarmUpRequest,
    api_key: str = Depends(verify_api_key),
):
    """
    Warm up containers for a provider.
    """
    try:
        executor_provider = ExecutorProvider(provider)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    if not ExecutorRegistry.is_registered(executor_provider):
        raise HTTPException(status_code=404, detail=f"Provider not registered: {provider}")

    try:
        runtime = Runtime(request.runtime)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown runtime: {request.runtime}")

    executor = ExecutorRegistry.get(executor_provider)
    warmed = await executor.warm_up(runtime, request.count)

    return WarmUpResponse(
        runtime=request.runtime,
        requested=request.count,
        warmed=warmed,
    )


@router.get("/{provider}/health")
async def health_check_provider(
    provider: str,
    api_key: str = Depends(verify_api_key),
):
    """
    Detailed health check for a provider.
    """
    try:
        executor_provider = ExecutorProvider(provider)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    if not ExecutorRegistry.is_registered(executor_provider):
        raise HTTPException(status_code=404, detail=f"Provider not registered: {provider}")

    executor = ExecutorRegistry.get(executor_provider)
    health = await executor.health_check()

    return health.to_dict()
