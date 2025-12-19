"""
Warm Container Wrapper

Represents a pre-warmed container ready for code execution.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from docker.models.containers import Container


class ContainerState(str, Enum):
    """Container state in the warm pool"""

    CREATING = "creating"  # Being created
    WARM = "warm"  # Ready for use
    BUSY = "busy"  # Currently executing
    RESETTING = "resetting"  # Being reset after execution
    UNHEALTHY = "unhealthy"  # Failed health check
    TERMINATING = "terminating"  # Being terminated


@dataclass
class WarmContainer:
    """
    Wrapper for a Docker container in the warm pool.

    Tracks container lifecycle, usage statistics, and health status.
    """

    # Container reference
    container: Container
    runtime: str

    # Identification
    container_id: str = field(default="")

    # State
    state: ContainerState = ContainerState.CREATING

    # Timestamps
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    last_health_check_at: float = field(default_factory=time.time)

    # Statistics
    execution_count: int = 0
    total_execution_time_ms: float = 0.0
    error_count: int = 0

    # Health
    consecutive_failures: int = 0
    last_error: Optional[str] = None

    def __post_init__(self):
        if not self.container_id:
            self.container_id = self.container.id[:12]

    @property
    def id(self) -> str:
        """Short container ID"""
        return self.container_id

    @property
    def age_seconds(self) -> float:
        """Container age in seconds"""
        return time.time() - self.created_at

    @property
    def idle_seconds(self) -> float:
        """Time since last use in seconds"""
        return time.time() - self.last_used_at

    @property
    def avg_execution_time_ms(self) -> float:
        """Average execution time"""
        if self.execution_count == 0:
            return 0.0
        return self.total_execution_time_ms / self.execution_count

    @property
    def is_available(self) -> bool:
        """Check if container is available for execution"""
        return self.state == ContainerState.WARM

    @property
    def is_healthy(self) -> bool:
        """Check if container is healthy"""
        return self.state not in (ContainerState.UNHEALTHY, ContainerState.TERMINATING)

    def mark_busy(self) -> None:
        """Mark container as busy (executing)"""
        self.state = ContainerState.BUSY
        self.last_used_at = time.time()

    def mark_warm(self) -> None:
        """Mark container as warm (ready)"""
        self.state = ContainerState.WARM

    def mark_resetting(self) -> None:
        """Mark container as resetting"""
        self.state = ContainerState.RESETTING

    def mark_unhealthy(self, error: Optional[str] = None) -> None:
        """Mark container as unhealthy"""
        self.state = ContainerState.UNHEALTHY
        self.consecutive_failures += 1
        if error:
            self.last_error = error

    def mark_terminating(self) -> None:
        """Mark container as terminating"""
        self.state = ContainerState.TERMINATING

    def record_execution(self, execution_time_ms: float, success: bool) -> None:
        """
        Record execution statistics.

        Args:
            execution_time_ms: Execution time in milliseconds
            success: Whether execution succeeded
        """
        self.execution_count += 1
        self.total_execution_time_ms += execution_time_ms

        if success:
            self.consecutive_failures = 0
            self.last_error = None
        else:
            self.error_count += 1
            self.consecutive_failures += 1

    def record_health_check(self, healthy: bool, error: Optional[str] = None) -> None:
        """
        Record health check result.

        Args:
            healthy: Whether health check passed
            error: Error message if failed
        """
        self.last_health_check_at = time.time()

        if healthy:
            self.consecutive_failures = 0
            self.last_error = None
        else:
            self.mark_unhealthy(error)

    def should_replace(self, max_age_seconds: int, max_idle_seconds: int) -> bool:
        """
        Check if container should be replaced.

        Args:
            max_age_seconds: Maximum container age (TTL)
            max_idle_seconds: Maximum idle time

        Returns:
            True if container should be replaced
        """
        # Check TTL
        if self.age_seconds > max_age_seconds:
            return True

        # Check idle time
        if self.idle_seconds > max_idle_seconds:
            return True

        # Check health
        if self.state == ContainerState.UNHEALTHY:
            return True

        # Check error rate
        if self.execution_count >= 10 and self.consecutive_failures >= 3:
            return True

        return False

    def to_dict(self) -> dict:
        """Convert to dictionary for debugging/logging"""
        return {
            "container_id": self.container_id,
            "runtime": self.runtime,
            "state": self.state.value,
            "created_at": datetime.fromtimestamp(self.created_at, tz=timezone.utc).isoformat(),
            "age_seconds": round(self.age_seconds, 1),
            "idle_seconds": round(self.idle_seconds, 1),
            "execution_count": self.execution_count,
            "avg_execution_time_ms": round(self.avg_execution_time_ms, 1),
            "error_count": self.error_count,
            "consecutive_failures": self.consecutive_failures,
            "last_error": self.last_error,
        }
