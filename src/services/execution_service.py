"""
Code execution service
"""
import time
import uuid
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import redis.asyncio as redis
import logging

from ..core.config import get_settings
from ..core.docker_manager import DockerManager
from ..api.execute import ExecuteResponse, ExecutionStatus

logger = logging.getLogger(__name__)
settings = get_settings()

class ExecutionService:
    """Service for managing code executions"""

    def __init__(self, docker_manager: DockerManager):
        self.docker_manager = docker_manager
        self.redis_client = None
        self._init_redis()

    def _init_redis(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.from_url(
                settings.redis_url,
                decode_responses=True
            )
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")

    async def execute(
        self,
        code: str,
        language: str,
        stdin: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> ExecuteResponse:
        """Execute code and return result"""

        execution_id = str(uuid.uuid4())
        start_time = time.time()

        # Store execution start
        await self._store_execution_start(execution_id, language, session_id)

        try:
            # Execute code in Docker
            stdout, stderr, exit_code = await self.docker_manager.execute_code(
                code=code,
                language=language,
                stdin=stdin,
                environment=environment,
                timeout=timeout,
            )

            execution_time = time.time() - start_time

            # Create response
            response = ExecuteResponse(
                execution_id=execution_id,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                execution_time=execution_time,
                language=language,
                session_id=session_id,
            )

            # Store execution result
            await self._store_execution_result(execution_id, response)

            # Update statistics
            await self._update_statistics(language, execution_time, exit_code == 0)

            return response

        except Exception as e:
            logger.error(f"Execution failed: {e}")

            # Store error
            response = ExecuteResponse(
                execution_id=execution_id,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                execution_time=time.time() - start_time,
                language=language,
                session_id=session_id,
            )

            await self._store_execution_result(execution_id, response, error=str(e))

            raise

    async def execute_async(
        self,
        execution_id: str,
        code: str,
        language: str,
        stdin: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        session_id: Optional[str] = None,
    ):
        """Execute code asynchronously"""

        # Store execution start
        await self._store_execution_start(execution_id, language, session_id)

        try:
            # Execute code
            result = await self.execute(
                code=code,
                language=language,
                stdin=stdin,
                environment=environment,
                timeout=timeout,
                session_id=session_id,
            )

            # Update with actual execution_id
            result.execution_id = execution_id

            # Store result
            await self._store_execution_result(execution_id, result)

        except Exception as e:
            # Store error
            await self._store_execution_error(execution_id, str(e))

    async def get_status(self, execution_id: str) -> Optional[ExecutionStatus]:
        """Get execution status"""

        if not self.redis_client:
            return None

        try:
            # Get execution data
            key = f"{settings.redis_prefix}execution:{execution_id}"
            data = await self.redis_client.hgetall(key)

            if not data:
                return None

            # Parse result if completed
            result = None
            if data.get("result"):
                result_data = json.loads(data["result"])
                result = ExecuteResponse(**result_data)

            return ExecutionStatus(
                execution_id=execution_id,
                status=data.get("status", "unknown"),
                created_at=datetime.fromisoformat(data.get("created_at", datetime.utcnow().isoformat())),
                started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
                completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
                result=result,
            )

        except Exception as e:
            logger.error(f"Failed to get execution status: {e}")
            return None

    async def is_rate_limited(self, api_key: str) -> bool:
        """Check if API key is rate limited"""

        if not self.redis_client:
            return False

        try:
            # Check rate limit (10 requests per minute)
            key = f"{settings.redis_prefix}rate:{api_key}"
            count = await self.redis_client.incr(key)

            if count == 1:
                await self.redis_client.expire(key, 60)

            return count > 10

        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            return False

    async def cleanup_session(self, session_id: str):
        """Cleanup all executions for a session"""

        if not self.redis_client:
            return

        try:
            # Get all executions for session
            pattern = f"{settings.redis_prefix}session:{session_id}:*"
            keys = await self.redis_client.keys(pattern)

            # Delete all keys
            if keys:
                await self.redis_client.delete(*keys)

        except Exception as e:
            logger.error(f"Session cleanup failed: {e}")

    async def _store_execution_start(
        self,
        execution_id: str,
        language: str,
        session_id: Optional[str] = None
    ):
        """Store execution start in Redis"""

        if not self.redis_client:
            return

        try:
            key = f"{settings.redis_prefix}execution:{execution_id}"
            data = {
                "status": "running",
                "language": language,
                "created_at": datetime.utcnow().isoformat(),
                "started_at": datetime.utcnow().isoformat(),
            }

            if session_id:
                data["session_id"] = session_id

                # Also store in session index
                session_key = f"{settings.redis_prefix}session:{session_id}:{execution_id}"
                await self.redis_client.set(session_key, execution_id, ex=3600)

            await self.redis_client.hset(key, mapping=data)
            await self.redis_client.expire(key, 3600)  # Expire after 1 hour

        except Exception as e:
            logger.error(f"Failed to store execution start: {e}")

    async def _store_execution_result(
        self,
        execution_id: str,
        response: ExecuteResponse,
        error: Optional[str] = None
    ):
        """Store execution result in Redis"""

        if not self.redis_client:
            return

        try:
            key = f"{settings.redis_prefix}execution:{execution_id}"

            data = {
                "status": "failed" if error else "completed",
                "completed_at": datetime.utcnow().isoformat(),
                "result": response.model_dump_json() if not error else None,
                "error": error,
            }

            # Remove None values
            data = {k: v for k, v in data.items() if v is not None}

            await self.redis_client.hset(key, mapping=data)

        except Exception as e:
            logger.error(f"Failed to store execution result: {e}")

    async def _store_execution_error(self, execution_id: str, error: str):
        """Store execution error"""

        if not self.redis_client:
            return

        try:
            key = f"{settings.redis_prefix}execution:{execution_id}"

            data = {
                "status": "failed",
                "completed_at": datetime.utcnow().isoformat(),
                "error": error,
            }

            await self.redis_client.hset(key, mapping=data)

        except Exception as e:
            logger.error(f"Failed to store execution error: {e}")

    async def _update_statistics(
        self,
        language: str,
        execution_time: float,
        success: bool
    ):
        """Update execution statistics"""

        if not self.redis_client:
            return

        try:
            # Update language statistics
            stats_key = f"{settings.redis_prefix}stats:{language}"

            await self.redis_client.hincrby(stats_key, "total_executions", 1)

            if success:
                await self.redis_client.hincrby(stats_key, "successful_executions", 1)
            else:
                await self.redis_client.hincrby(stats_key, "failed_executions", 1)

            # Update average execution time
            await self.redis_client.hincrbyfloat(stats_key, "total_time", execution_time)

            # Update global statistics
            global_key = f"{settings.redis_prefix}stats:global"
            await self.redis_client.hincrby(global_key, "total_executions", 1)

        except Exception as e:
            logger.error(f"Failed to update statistics: {e}")
