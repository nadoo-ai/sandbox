"""
AWS Lambda Executor

Execute code using AWS Lambda functions.
Leverages Lambda's built-in warm pool for fast execution.
"""

import asyncio
import base64
import json
import logging
from datetime import datetime, timezone

from ..interface import BaseExecutor, ExecutorProvider, Runtime
from ..models import ExecutionRequest, ExecutionResult, HealthStatus, ExecutorMetrics
from ..exceptions import ExecutorNotAvailableError

logger = logging.getLogger(__name__)

# Optional boto3 import
try:
    import boto3
    from botocore.config import Config
    from botocore.exceptions import ClientError

    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    boto3 = None
    Config = None
    ClientError = Exception


class AWSLambdaExecutor(BaseExecutor):
    """
    AWS Lambda based executor.

    Uses Lambda functions for code execution with AWS-managed warm pools.
    Supports Provisioned Concurrency for consistent low latency.

    Prerequisites:
    - Lambda functions deployed for each runtime
    - IAM permissions for lambda:InvokeFunction
    - Function naming convention: {prefix}-{runtime}

    Example function names:
    - nadoo-sandbox-python-3-11
    - nadoo-sandbox-node-20
    """

    provider = ExecutorProvider.AWS_LAMBDA

    # Runtime to Lambda function suffix mapping
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
        region: str = "ap-northeast-2",
        function_prefix: str = "nadoo-sandbox",
        max_retries: int = 3,
        connect_timeout: int = 10,
        read_timeout: int = 60,
    ):
        """
        Initialize AWS Lambda executor.

        Args:
            region: AWS region
            function_prefix: Lambda function name prefix
            max_retries: Max retry attempts for failed invocations
            connect_timeout: Connection timeout in seconds
            read_timeout: Read timeout in seconds
        """
        if not BOTO3_AVAILABLE:
            raise ImportError(
                "boto3 is required for AWS Lambda executor. "
                "Install with: pip install boto3"
            )

        self.region = region
        self.function_prefix = function_prefix

        # Configure boto3 client
        config = Config(
            region_name=region,
            retries={"max_attempts": max_retries, "mode": "adaptive"},
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
        )
        self.lambda_client = boto3.client("lambda", config=config)

        # Metrics
        self._metrics = ExecutorMetrics(provider=self.provider)
        self._execution_times: list[float] = []

    async def initialize(self) -> None:
        """Initialize executor - verify Lambda functions exist"""
        logger.info("Initializing AWSLambdaExecutor")

        # Verify at least one function exists
        try:
            function_name = self._get_function_name(Runtime.PYTHON_311)
            await asyncio.to_thread(
                self.lambda_client.get_function,
                FunctionName=function_name,
            )
            logger.info(f"Verified Lambda function: {function_name}")
        except ClientError as e:
            logger.warning(f"Lambda function not found: {e}")

        logger.info("AWSLambdaExecutor initialized")

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute code using Lambda function"""
        start_time = datetime.now(timezone.utc)
        function_name = self._get_function_name(request.runtime)

        # Build Lambda payload
        payload = {
            "code": request.code,
            "entry_point": request.entry_point,
            "stdin": request.stdin,
            "environment": request.environment,
            "files": request.files,
            "timeout_ms": request.timeout_ms,
            "memory_mb": request.memory_mb,
        }

        try:
            # Invoke Lambda
            response = await asyncio.to_thread(
                self.lambda_client.invoke,
                FunctionName=function_name,
                InvocationType="RequestResponse",
                LogType="Tail",  # Get execution logs
                Payload=json.dumps(payload),
            )

            # Parse response
            response_payload = json.loads(response["Payload"].read())

            # Check for Lambda error
            if "FunctionError" in response:
                error_message = response_payload.get("errorMessage", "Unknown error")
                return ExecutionResult(
                    success=False,
                    stdout="",
                    stderr=error_message,
                    exit_code=-1,
                    execution_time_ms=self._calculate_duration(start_time),
                    cold_start=self._is_cold_start(response),
                    provider=self.provider,
                    execution_id=request.execution_id,
                )

            # Extract execution result
            success = response_payload.get("exit_code", 1) == 0
            execution_time_ms = response_payload.get(
                "duration_ms",
                self._calculate_duration(start_time),
            )

            # Update metrics
            self._update_metrics(execution_time_ms, success)

            cold_start = self._is_cold_start(response)
            if cold_start:
                self._metrics.cold_start_count += 1
            else:
                self._metrics.warm_start_count += 1

            return ExecutionResult(
                success=success,
                stdout=response_payload.get("stdout", ""),
                stderr=response_payload.get("stderr", ""),
                exit_code=response_payload.get("exit_code", 0),
                execution_time_ms=execution_time_ms,
                cold_start=cold_start,
                provider=self.provider,
                execution_id=request.execution_id,
                started_at=start_time,
                completed_at=datetime.now(timezone.utc),
            )

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))

            logger.error(f"Lambda invocation failed: {error_code} - {error_message}")
            self._metrics.failed_executions += 1

            if error_code == "ResourceNotFoundException":
                raise ExecutorNotAvailableError(
                    f"Lambda function not found: {function_name}",
                    provider=self.provider,
                )

            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Lambda error: {error_message}",
                exit_code=-1,
                execution_time_ms=self._calculate_duration(start_time),
                cold_start=False,
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
                cold_start=False,
                provider=self.provider,
                execution_id=request.execution_id,
            )

    def _get_function_name(self, runtime: Runtime) -> str:
        """Get Lambda function name for runtime"""
        suffix = self.RUNTIME_SUFFIX_MAP.get(runtime)

        if suffix:
            return f"{self.function_prefix}-{suffix}"

        # Fallback: convert runtime value
        runtime_str = runtime.value.replace(":", "-").replace(".", "-")
        return f"{self.function_prefix}-{runtime_str}"

    def _is_cold_start(self, response: dict) -> bool:
        """Check if Lambda execution was a cold start"""
        # Parse CloudWatch logs to detect Init Duration
        log_result = response.get("LogResult", "")
        if log_result:
            try:
                logs = base64.b64decode(log_result).decode("utf-8")
                return "Init Duration" in logs
            except Exception:
                pass
        return False

    def _calculate_duration(self, start_time: datetime) -> float:
        """Calculate duration in milliseconds"""
        delta = datetime.now(timezone.utc) - start_time
        return delta.total_seconds() * 1000

    def _update_metrics(self, execution_time_ms: float, success: bool) -> None:
        """Update execution metrics"""
        self._metrics.total_executions += 1

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
        """
        Warm up Lambda function.

        Note: Lambda manages its own warm pool. This method triggers
        invocations to pre-warm instances if Provisioned Concurrency
        is not configured.
        """
        function_name = self._get_function_name(runtime)
        warmed = 0

        for _ in range(count):
            try:
                # Invoke with minimal payload to warm up
                await asyncio.to_thread(
                    self.lambda_client.invoke,
                    FunctionName=function_name,
                    InvocationType="RequestResponse",
                    Payload=json.dumps({"warmup": True}),
                )
                warmed += 1
            except Exception as e:
                logger.warning(f"Warmup invocation failed: {e}")

        return warmed

    async def health_check(self) -> HealthStatus:
        """Check Lambda executor health"""
        try:
            function_name = self._get_function_name(Runtime.PYTHON_311)

            response = await asyncio.to_thread(
                self.lambda_client.get_function,
                FunctionName=function_name,
            )

            state = response.get("Configuration", {}).get("State", "Unknown")
            healthy = state == "Active"

            return HealthStatus(
                healthy=healthy,
                provider=self.provider,
                message=f"Lambda state: {state}",
                checks={
                    "function_exists": True,
                    "function_active": healthy,
                },
            )

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            return HealthStatus(
                healthy=False,
                provider=self.provider,
                message=f"Lambda error: {error_code}",
                checks={"function_exists": False},
            )

        except Exception as e:
            return HealthStatus(
                healthy=False,
                provider=self.provider,
                message=str(e),
            )

    async def cleanup(self) -> None:
        """Cleanup - nothing to do for Lambda"""
        logger.info("AWSLambdaExecutor cleanup complete")

    async def get_metrics(self) -> ExecutorMetrics:
        """Get execution metrics"""
        return self._metrics
