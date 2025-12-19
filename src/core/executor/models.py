"""
Executor Data Models

Request/Response models for code execution.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .interface import ExecutorProvider, Runtime


def _utcnow() -> datetime:
    """Get current UTC time (timezone-aware)"""
    return datetime.now(timezone.utc)


@dataclass
class ExecutionRequest:
    """Code execution request"""

    # Required
    code: str
    runtime: Runtime

    # Execution options
    entry_point: str = "main.py"
    timeout_ms: int = 30000  # 30 seconds
    memory_mb: int = 256
    cpu_cores: float = 0.5

    # Input/Output
    stdin: Optional[str] = None
    environment: Dict[str, str] = field(default_factory=dict)

    # Metadata
    execution_id: str = field(default_factory=lambda: str(uuid4()))
    workspace_id: Optional[str] = None
    user_id: Optional[str] = None

    # Provider hints
    preferred_provider: Optional[ExecutorProvider] = None
    allow_cold_start: bool = True

    # Additional files (filename -> content)
    files: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        """Validate request parameters"""
        if not self.code:
            raise ValueError("code cannot be empty")
        if self.timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive")
        if self.memory_mb <= 0:
            raise ValueError("memory_mb must be positive")
        if self.cpu_cores <= 0:
            raise ValueError("cpu_cores must be positive")


@dataclass
class ExecutionResult:
    """Code execution result"""

    # Result
    success: bool
    stdout: str
    stderr: str
    exit_code: int

    # Performance metrics
    execution_time_ms: float
    cold_start: bool

    # Provider info (required)
    provider: ExecutorProvider

    # Performance metrics (with defaults)
    queue_time_ms: float = 0.0

    # Container info
    container_id: Optional[str] = None

    # Resource usage
    memory_used_mb: Optional[float] = None
    cpu_time_ms: Optional[float] = None

    # Timestamps
    started_at: datetime = field(default_factory=_utcnow)
    completed_at: Optional[datetime] = None

    # Request reference
    execution_id: Optional[str] = None

    @property
    def total_time_ms(self) -> float:
        """Total time including queue time"""
        return self.queue_time_ms + self.execution_time_ms

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "execution_time_ms": self.execution_time_ms,
            "cold_start": self.cold_start,
            "queue_time_ms": self.queue_time_ms,
            "provider": self.provider.value,
            "container_id": self.container_id,
            "memory_used_mb": self.memory_used_mb,
            "cpu_time_ms": self.cpu_time_ms,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "execution_id": self.execution_id,
        }


@dataclass
class HealthStatus:
    """Provider health status"""

    healthy: bool
    provider: ExecutorProvider
    message: str = ""

    # Pool status (for local docker)
    pool_size: int = 0
    available_containers: int = 0
    busy_containers: int = 0

    # Last check timestamp
    last_check: datetime = field(default_factory=_utcnow)

    # Detailed checks
    checks: Dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "healthy": self.healthy,
            "provider": self.provider.value,
            "message": self.message,
            "pool_size": self.pool_size,
            "available_containers": self.available_containers,
            "busy_containers": self.busy_containers,
            "last_check": self.last_check.isoformat(),
            "checks": self.checks,
        }


@dataclass
class PoolStatus:
    """Warm pool status"""

    runtime: Runtime
    total: int
    available: int
    busy: int

    # Container details
    container_ids: List[str] = field(default_factory=list)

    @property
    def utilization(self) -> float:
        """Pool utilization ratio (0.0 - 1.0)"""
        if self.total == 0:
            return 0.0
        return self.busy / self.total


@dataclass
class ExecutorMetrics:
    """Provider execution metrics"""

    provider: ExecutorProvider

    # Execution counts
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    timeout_executions: int = 0

    # Latency stats (milliseconds)
    avg_execution_time_ms: float = 0.0
    min_execution_time_ms: float = 0.0
    max_execution_time_ms: float = 0.0
    p50_execution_time_ms: float = 0.0
    p95_execution_time_ms: float = 0.0
    p99_execution_time_ms: float = 0.0

    # Cold start stats
    cold_start_count: int = 0
    warm_start_count: int = 0

    # Pool stats (for local docker)
    pool_hits: int = 0
    pool_misses: int = 0

    # Resource stats
    total_memory_used_mb: float = 0.0
    total_cpu_time_ms: float = 0.0

    # Timestamps
    first_execution_at: Optional[datetime] = None
    last_execution_at: Optional[datetime] = None

    @property
    def success_rate(self) -> float:
        """Execution success rate (0.0 - 1.0)"""
        if self.total_executions == 0:
            return 0.0
        return self.successful_executions / self.total_executions

    @property
    def cold_start_ratio(self) -> float:
        """Cold start ratio (0.0 - 1.0)"""
        total = self.cold_start_count + self.warm_start_count
        if total == 0:
            return 0.0
        return self.cold_start_count / total

    @property
    def pool_hit_ratio(self) -> float:
        """Pool hit ratio (0.0 - 1.0)"""
        total = self.pool_hits + self.pool_misses
        if total == 0:
            return 0.0
        return self.pool_hits / total

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "provider": self.provider.value,
            "total_executions": self.total_executions,
            "successful_executions": self.successful_executions,
            "failed_executions": self.failed_executions,
            "timeout_executions": self.timeout_executions,
            "success_rate": self.success_rate,
            "avg_execution_time_ms": self.avg_execution_time_ms,
            "min_execution_time_ms": self.min_execution_time_ms,
            "max_execution_time_ms": self.max_execution_time_ms,
            "p50_execution_time_ms": self.p50_execution_time_ms,
            "p95_execution_time_ms": self.p95_execution_time_ms,
            "p99_execution_time_ms": self.p99_execution_time_ms,
            "cold_start_count": self.cold_start_count,
            "warm_start_count": self.warm_start_count,
            "cold_start_ratio": self.cold_start_ratio,
            "pool_hits": self.pool_hits,
            "pool_misses": self.pool_misses,
            "pool_hit_ratio": self.pool_hit_ratio,
            "first_execution_at": self.first_execution_at.isoformat() if self.first_execution_at else None,
            "last_execution_at": self.last_execution_at.isoformat() if self.last_execution_at else None,
        }
