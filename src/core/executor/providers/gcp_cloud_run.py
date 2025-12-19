"""
GCP Cloud Run Executor

Execute code using Google Cloud Run Jobs.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from ..interface import BaseExecutor, ExecutorProvider, Runtime
from ..models import ExecutionRequest, ExecutionResult, HealthStatus, ExecutorMetrics
from ..exceptions import ExecutorNotAvailableError

logger = logging.getLogger(__name__)

# Optional google-cloud imports
try:
    from google.cloud import run_v2
    from google.api_core.exceptions import GoogleAPIError, NotFound

    GCP_AVAILABLE = True
except ImportError:
    GCP_AVAILABLE = False
    run_v2 = None
    GoogleAPIError = Exception
    NotFound = Exception


class GCPCloudRunExecutor(BaseExecutor):
    """
    GCP Cloud Run based executor.

    Uses Cloud Run Jobs for isolated code execution.

    Prerequisites:
    - Cloud Run Jobs deployed for each runtime
    - IAM permissions for Cloud Run Job execution
    - Service account with appropriate permissions
    """

    provider = ExecutorProvider.GCP_CLOUD_RUN

    # Runtime to Cloud Run job suffix mapping
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
        project_id: str,
        region: str = "asia-northeast3",
        job_prefix: str = "nadoo-sandbox",
    ):
        """
        Initialize GCP Cloud Run executor.

        Args:
            project_id: GCP project ID
            region: GCP region
            job_prefix: Cloud Run job name prefix
        """
        if not GCP_AVAILABLE:
            raise ImportError(
                "google-cloud-run is required for GCP executor. "
                "Install with: pip install google-cloud-run"
            )

        self.project_id = project_id
        self.region = region
        self.job_prefix = job_prefix

        # Initialize Cloud Run client
        self.jobs_client = run_v2.JobsClient()
        self.executions_client = run_v2.ExecutionsClient()

        # Metrics
        self._metrics = ExecutorMetrics(provider=self.provider)
        self._execution_times: list[float] = []

    async def initialize(self) -> None:
        """Initialize executor"""
        logger.info("Initializing GCPCloudRunExecutor")
        logger.info("GCPCloudRunExecutor initialized")

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute code using Cloud Run Job"""
        start_time = datetime.now(timezone.utc)
        job_name = self._get_job_name(request.runtime)

        try:
            # Create execution with overrides
            execution = await self._run_job(job_name, request)

            # Wait for completion
            result = await self._wait_for_execution(execution, request.timeout_ms)

            execution_time_ms = self._calculate_duration(start_time)
            self._update_metrics(execution_time_ms, result["success"])

            return ExecutionResult(
                success=result["success"],
                stdout=result.get("stdout", ""),
                stderr=result.get("stderr", ""),
                exit_code=result.get("exit_code", 0),
                execution_time_ms=execution_time_ms,
                cold_start=True,  # Cloud Run Jobs always cold start
                provider=self.provider,
                execution_id=request.execution_id,
                started_at=start_time,
                completed_at=datetime.now(timezone.utc),
            )

        except NotFound:
            raise ExecutorNotAvailableError(
                f"Cloud Run job not found: {job_name}",
                provider=self.provider,
            )

        except GoogleAPIError as e:
            logger.error(f"Cloud Run error: {e}")
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

    async def _run_job(self, job_name: str, request: ExecutionRequest):
        """Run Cloud Run job with overrides"""
        parent = f"projects/{self.project_id}/locations/{self.region}/jobs/{job_name}"

        # Build override with code and parameters
        override = run_v2.RunJobRequest.Overrides(
            container_overrides=[
                run_v2.RunJobRequest.Overrides.ContainerOverride(
                    env=[
                        run_v2.EnvVar(name="CODE", value=request.code),
                        run_v2.EnvVar(name="ENTRY_POINT", value=request.entry_point),
                        run_v2.EnvVar(name="STDIN", value=request.stdin or ""),
                        run_v2.EnvVar(name="FILES", value=json.dumps(request.files)),
                        *[
                            run_v2.EnvVar(name=k, value=v)
                            for k, v in request.environment.items()
                        ],
                    ],
                )
            ],
            timeout=f"{request.timeout_ms // 1000}s",
        )

        run_request = run_v2.RunJobRequest(
            name=parent,
            overrides=override,
        )

        operation = await asyncio.to_thread(
            self.jobs_client.run_job,
            request=run_request,
        )

        return operation

    async def _wait_for_execution(self, operation, timeout_ms: int) -> dict:
        """Wait for job execution to complete"""
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(operation.result),
                timeout=timeout_ms / 1000 + 30,  # Add buffer
            )

            # Parse execution result
            succeeded = result.succeeded_count > 0
            return {
                "success": succeeded,
                "stdout": "",  # Cloud Run Jobs don't capture stdout directly
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
        """Get Cloud Run job name for runtime"""
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
        self._metrics.cold_start_count += 1  # Always cold start

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
        """Cloud Run Jobs don't support warm-up"""
        return 0

    async def health_check(self) -> HealthStatus:
        """Check Cloud Run executor health"""
        try:
            job_name = self._get_job_name(Runtime.PYTHON_311)
            parent = f"projects/{self.project_id}/locations/{self.region}/jobs/{job_name}"

            # Verify job exists by fetching it
            await asyncio.to_thread(
                self.jobs_client.get_job,
                name=parent,
            )

            return HealthStatus(
                healthy=True,
                provider=self.provider,
                message="OK",
                checks={
                    "job_exists": True,
                    "job_name": job_name,
                },
            )

        except NotFound:
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
        logger.info("GCPCloudRunExecutor cleanup complete")

    async def get_metrics(self) -> ExecutorMetrics:
        """Get execution metrics"""
        return self._metrics
