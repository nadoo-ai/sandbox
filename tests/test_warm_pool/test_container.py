"""
Tests for WarmContainer.
"""

import time
import pytest
from unittest.mock import MagicMock

from core.warm_pool.container import WarmContainer, ContainerState


class TestContainerState:
    """Test ContainerState enum."""

    def test_state_values(self):
        """Test state enum values."""
        assert ContainerState.CREATING.value == "creating"
        assert ContainerState.WARM.value == "warm"
        assert ContainerState.BUSY.value == "busy"
        assert ContainerState.RESETTING.value == "resetting"
        assert ContainerState.UNHEALTHY.value == "unhealthy"
        assert ContainerState.TERMINATING.value == "terminating"


class TestWarmContainer:
    """Test WarmContainer."""

    @pytest.fixture
    def mock_docker_container(self):
        """Create mock Docker container."""
        container = MagicMock()
        container.id = "test_container_abc123def456"
        container.status = "running"
        return container

    @pytest.fixture
    def warm_container(self, mock_docker_container):
        """Create WarmContainer instance."""
        return WarmContainer(
            container=mock_docker_container,
            runtime="python:3.11",
            state=ContainerState.WARM,
        )

    def test_create_container(self, warm_container):
        """Test creating warm container."""
        assert warm_container.runtime == "python:3.11"
        assert warm_container.state == ContainerState.WARM
        assert warm_container.container_id == "test_contain"  # First 12 chars

    def test_container_id(self, warm_container):
        """Test container ID property."""
        assert warm_container.id == "test_contain"

    def test_age_seconds(self, warm_container):
        """Test age calculation."""
        # Age should be very small (just created)
        assert warm_container.age_seconds < 1.0

    def test_idle_seconds(self, warm_container):
        """Test idle time calculation."""
        # Idle time should be very small (just created)
        assert warm_container.idle_seconds < 1.0

    def test_is_available(self, warm_container):
        """Test availability check."""
        assert warm_container.is_available is True

        warm_container.state = ContainerState.BUSY
        assert warm_container.is_available is False

    def test_is_healthy(self, warm_container):
        """Test health check."""
        assert warm_container.is_healthy is True

        warm_container.state = ContainerState.UNHEALTHY
        assert warm_container.is_healthy is False

        warm_container.state = ContainerState.TERMINATING
        assert warm_container.is_healthy is False

    def test_mark_busy(self, warm_container):
        """Test marking container as busy."""
        old_last_used = warm_container.last_used_at

        time.sleep(0.01)
        warm_container.mark_busy()

        assert warm_container.state == ContainerState.BUSY
        assert warm_container.last_used_at > old_last_used

    def test_mark_warm(self, warm_container):
        """Test marking container as warm."""
        warm_container.state = ContainerState.BUSY
        warm_container.mark_warm()

        assert warm_container.state == ContainerState.WARM

    def test_mark_resetting(self, warm_container):
        """Test marking container as resetting."""
        warm_container.mark_resetting()

        assert warm_container.state == ContainerState.RESETTING

    def test_mark_unhealthy(self, warm_container):
        """Test marking container as unhealthy."""
        warm_container.mark_unhealthy("Test error")

        assert warm_container.state == ContainerState.UNHEALTHY
        assert warm_container.consecutive_failures == 1
        assert warm_container.last_error == "Test error"

    def test_mark_terminating(self, warm_container):
        """Test marking container as terminating."""
        warm_container.mark_terminating()

        assert warm_container.state == ContainerState.TERMINATING

    def test_record_execution_success(self, warm_container):
        """Test recording successful execution."""
        warm_container.record_execution(100.0, True)

        assert warm_container.execution_count == 1
        assert warm_container.total_execution_time_ms == 100.0
        assert warm_container.error_count == 0
        assert warm_container.consecutive_failures == 0

    def test_record_execution_failure(self, warm_container):
        """Test recording failed execution."""
        warm_container.record_execution(100.0, False)

        assert warm_container.execution_count == 1
        assert warm_container.error_count == 1
        assert warm_container.consecutive_failures == 1

    def test_record_multiple_executions(self, warm_container):
        """Test recording multiple executions."""
        warm_container.record_execution(100.0, True)
        warm_container.record_execution(50.0, True)
        warm_container.record_execution(150.0, True)

        assert warm_container.execution_count == 3
        assert warm_container.total_execution_time_ms == 300.0
        assert warm_container.avg_execution_time_ms == 100.0

    def test_record_health_check_success(self, warm_container):
        """Test recording successful health check."""
        warm_container.consecutive_failures = 3

        warm_container.record_health_check(True)

        assert warm_container.consecutive_failures == 0
        assert warm_container.last_error is None

    def test_record_health_check_failure(self, warm_container):
        """Test recording failed health check."""
        warm_container.record_health_check(False, "Health check failed")

        assert warm_container.state == ContainerState.UNHEALTHY
        assert warm_container.consecutive_failures == 1
        assert warm_container.last_error == "Health check failed"

    def test_should_replace_ttl(self, warm_container):
        """Test should replace due to TTL."""
        warm_container.created_at = time.time() - 4000  # 4000 seconds ago

        assert warm_container.should_replace(
            max_age_seconds=3600,  # 1 hour
            max_idle_seconds=300,
        ) is True

    def test_should_replace_idle(self, warm_container):
        """Test should replace due to idle time."""
        warm_container.last_used_at = time.time() - 400  # 400 seconds ago

        assert warm_container.should_replace(
            max_age_seconds=3600,
            max_idle_seconds=300,  # 5 minutes
        ) is True

    def test_should_replace_unhealthy(self, warm_container):
        """Test should replace due to unhealthy state."""
        warm_container.state = ContainerState.UNHEALTHY

        assert warm_container.should_replace(
            max_age_seconds=3600,
            max_idle_seconds=300,
        ) is True

    def test_should_replace_error_rate(self, warm_container):
        """Test should replace due to high error rate."""
        warm_container.execution_count = 10
        warm_container.consecutive_failures = 3

        assert warm_container.should_replace(
            max_age_seconds=3600,
            max_idle_seconds=300,
        ) is True

    def test_should_not_replace(self, warm_container):
        """Test should not replace healthy container."""
        assert warm_container.should_replace(
            max_age_seconds=3600,
            max_idle_seconds=300,
        ) is False

    def test_to_dict(self, warm_container):
        """Test converting to dictionary."""
        d = warm_container.to_dict()

        assert "container_id" in d
        assert "runtime" in d
        assert "state" in d
        assert "created_at" in d
        assert "age_seconds" in d
        assert "execution_count" in d
        assert d["runtime"] == "python:3.11"
        assert d["state"] == "warm"
