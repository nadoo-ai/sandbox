"""
Azure Container Apps Executor

Execute code using Azure Container Apps Jobs.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from ..interface import BaseExecutor, ExecutorProvider, Runtime
from ..models import ExecutionRequest, ExecutionResult, HealthStatus, ExecutorMetrics
from ..exceptions import ExecutorNotAvailableError

logger = logging.getLogger(__name__)

# Optional Azure SDK imports
try:
    from azure.identity import DefaultAzureCredential
    from azure.mgmt.appcontainers import ContainerAppsAPIClient
    from azure.core.exceptions import ResourceNotFoundError, AzureError

    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False
    DefaultAzureCredential = None
    ContainerAppsAPIClient = None
    ResourceNotFoundError = Exception
    AzureError = Exception


class AzureContainerExecutor(BaseExecutor):
    """
    Azure Container Apps based executor.

    Uses Container Apps Jobs for isolated code execution.

    Prerequisites:
    - Container Apps Jobs deployed for each runtime
    - Azure identity configured (DefaultAzureCredential)
    - Appropriate RBAC permissions
    """

    provider = ExecutorProvider.AZURE_CONTAINER

    # Runtime to Container Apps job suffix mapping
    RUNTIME_SUFFIX_MAP = {
        Runtime.PYTHON_311: "python-3-11",
        Runtime.PYTHON_312: "python-3-12",
        Runtime.NODE_20: "node-20",
        Runtime.NODE_22: "node-22",
        Runtime.GO_121: "go-1-21",
        Runtime.GO_122: "go-1-22",
    }

    def __init__(
        self,
        subscription_id: str,
        resource_group: str,
        job_prefix: str = "nadoo-sandbox",
    ):
        """
        Initialize Azure Container Apps executor.

        Args:
            subscription_id: Azure subscription ID
            resource_group: Azure resource group name
            job_prefix: Container Apps job name prefix
        """
        if not AZURE_AVAILABLE:
            raise ImportError(
                "azure-mgmt-appcontainers is required for Azure executor. "
                "Install with: pip install azure-mgmt-appcontainers azure-identity"
            )

        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.job_prefix = job_prefix

        # Initialize Azure client
        credential = DefaultAzureCredential()
        self.client = ContainerAppsAPIClient(credential, subscription_id)

        # Metrics
        self._metrics = ExecutorMetrics(provider=self.provider)
        self._execution_times: list[float] = []

    async def initialize(self) -> None:
        """Initialize executor"""
        logger.info("Initializing AzureContainerExecutor")
        logger.info("AzureContainerExecutor initialized")

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute code using Container Apps Job"""
        start_time = datetime.now(timezone.utc)
        job_name = self._get_job_name(request.runtime)

        try:
            # Start job execution
            execution = await self._start_job(job_name, request)

            # Wait for completion
            result = await self._wait_for_execution(
                job_name, execution, request.timeout_ms
            )

            execution_time_ms = self._calculate_duration(start_time)
            self._update_metrics(execution_time_ms, result["success"])

            return ExecutionResult(
                success=result["success"],
                stdout=result.get("stdout", ""),
                stderr=result.get("stderr", ""),
                exit_code=result.get("exit_code", 0),
                execution_time_ms=execution_time_ms,
                cold_start=True,  # Container Apps Jobs always cold start
                provider=self.provider,
                execution_id=request.execution_id,
                started_at=start_time,
                completed_at=datetime.now(timezone.utc),
            )

        except ResourceNotFoundError:
            raise ExecutorNotAvailableError(
                f"Container Apps job not found: {job_name}",
                provider=self.provider,
            )

        except AzureError as e:
            logger.error(f"Azure error: {e}")
            self._metrics.failed_executions += 1

            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                execution_time_ms=self._calculate_duration(start_time),
                cold_start=True,
                provider=self.provider,
                execution_id=request.execution_id,
            )

        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            self._metrics.failed_executions += 1

            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                execution_time_ms=self._calculate_duration(start_time),
                cold_start=True,
                provider=self.provider,
                execution_id=request.execution_id,
            )

    async def _start_job(self, job_name: str, request: ExecutionRequest):
        """Start Container Apps job execution"""
        # Build environment variables
        env_vars = [
            {"name": "CODE", "value": request.code},
            {"name": "ENTRY_POINT", "value": request.entry_point},
            {"name": "STDIN", "value": request.stdin or ""},
            {"name": "FILES", "value": json.dumps(request.files)},
        ]
        env_vars.extend(
            {"name": k, "value": v} for k, v in request.environment.items()
        )

        # Start job with template override
        result = await asyncio.to_thread(
            self.client.jobs.begin_start,
            resource_group_name=self.resource_group,
            job_name=job_name,
            template={
                "containers": [
                    {
                        "env": env_vars,
                        "resources": {
                            "cpu": request.cpu_cores,
                            "memory": f"{request.memory_mb / 1024}Gi",
                        },
                    }
                ],
            },
        )

        return result

    async def _wait_for_execution(
        self, job_name: str, operation, timeout_ms: int
    ) -> dict:
        """Wait for job execution to complete"""
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(operation.result),
                timeout=timeout_ms / 1000 + 30,
            )

            # Check execution status
            execution_name = result.name
            execution = await asyncio.to_thread(
                self.client.job_execution.get,
                resource_group_name=self.resource_group,
                job_name=job_name,
                job_execution_name=execution_name,
            )

            succeeded = execution.status == "Succeeded"
            return {
                "success": succeeded,
                "stdout": "",
                "stderr": "" if succeeded else "Execution failed",
                "exit_code": 0 if succeeded else 1,
            }

        except asyncio.TimeoutError:
            return {
                "success": False,
                "stdout": "",
                "stderr": "Execution timed out",
                "exit_code": -1,
            }

    def _get_job_name(self, runtime: Runtime) -> str:
        """Get Container Apps job name for runtime"""
        suffix = self.RUNTIME_SUFFIX_MAP.get(runtime)
        if suffix:
            return f"{self.job_prefix}-{suffix}"
        runtime_str = runtime.value.replace(":", "-").replace(".", "-")
        return f"{self.job_prefix}-{runtime_str}"

    def _calculate_duration(self, start_time: datetime) -> float:
        """Calculate duration in milliseconds"""
        delta = datetime.now(timezone.utc) - start_time
        return delta.total_seconds() * 1000

    def _update_metrics(self, execution_time_ms: float, success: bool) -> None:
        """Update execution metrics"""
        self._metrics.total_executions += 1
        self._metrics.cold_start_count += 1

        if success:
            self._metrics.successful_executions += 1
        else:
            self._metrics.failed_executions += 1

        self._execution_times.append(execution_time_ms)
        if len(self._execution_times) > 1000:
            self._execution_times = self._execution_times[-1000:]

        if self._execution_times:
            self._metrics.avg_execution_time_ms = (
                sum(self._execution_times) / len(self._execution_times)
            )

        now = datetime.now(timezone.utc)
        if self._metrics.first_execution_at is None:
            self._metrics.first_execution_at = now
        self._metrics.last_execution_at = now

    async def warm_up(self, runtime: Runtime, count: int = 1) -> int:
        """Container Apps Jobs don't support warm-up"""
        return 0

    async def health_check(self) -> HealthStatus:
        """Check Azure Container Apps executor health"""
        try:
            job_name = self._get_job_name(Runtime.PYTHON_311)

            job = await asyncio.to_thread(
                self.client.jobs.get,
                resource_group_name=self.resource_group,
                job_name=job_name,
            )

            return HealthStatus(
                healthy=True,
                provider=self.provider,
                message="OK",
                checks={
                    "job_exists": True,
                    "job_name": job_name,
                    "provisioning_state": job.provisioning_state,
                },
            )

        except ResourceNotFoundError:
            return HealthStatus(
                healthy=False,
                provider=self.provider,
                message="Job not found",
                checks={"job_exists": False},
            )

        except Exception as e:
            return HealthStatus(
                healthy=False,
                provider=self.provider,
                message=str(e),
            )

    async def cleanup(self) -> None:
        """Cleanup - nothing to do"""
        logger.info("AzureContainerExecutor cleanup complete")

    async def get_metrics(self) -> ExecutorMetrics:
        """Get execution metrics"""
        return self._metrics
