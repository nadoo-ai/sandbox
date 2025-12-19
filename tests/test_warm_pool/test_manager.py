"""
Tests for WarmPoolManager.
"""

import pytest
from unittest.mock import MagicMock

from core.executor.interface import Runtime
from core.warm_pool.manager import WarmPoolManager
from core.warm_pool.container import WarmContainer, ContainerState


class TestWarmPoolManager:
    """Test WarmPoolManager."""

    @pytest.fixture
    def mock_docker_client(self):
        """Create mock Docker client."""
        client = MagicMock()
        client.ping.return_value = True

        # Mock image operations
        client.images.get.return_value = MagicMock()
        client.images.pull.return_value = MagicMock()

        # Mock container operations
        container = MagicMock()
        container.id = "test_container_123456789abc"
        container.status = "running"
        container.exec_run.return_value = MagicMock(exit_code=0, output=(b"", b""))
        container.remove.return_value = None
        container.reload.return_value = None

        client.containers.run.return_value = container

        return client

    @pytest.fixture
    def pool_manager(self, mock_docker_client):
        """Create WarmPoolManager instance."""
        return WarmPoolManager(
            docker_client=mock_docker_client,
            pool_size_per_runtime=3,
            max_idle_time=300,
            container_ttl=3600,
            health_check_interval=30,
            memory_limit="256m",
            cpu_limit=0.5,
        )

    @pytest.mark.asyncio
    async def test_start_stop(self, pool_manager):
        """Test starting and stopping pool manager."""
        await pool_manager.start()
        assert pool_manager._started is True

        await pool_manager.stop()
        assert pool_manager._started is False

    @pytest.mark.asyncio
    async def test_warm_up(self, pool_manager):
        """Test warming up containers."""
        count = await pool_manager.warm_up(Runtime.PYTHON_311, count=2)

        assert count == 2
        assert Runtime.PYTHON_311 in pool_manager._pools
        assert len(pool_manager._pools[Runtime.PYTHON_311]) == 2

    @pytest.mark.asyncio
    async def test_acquire_container(self, pool_manager):
        """Test acquiring container from pool."""
        # First warm up
        await pool_manager.warm_up(Runtime.PYTHON_311, count=1)

        # Then acquire
        container = await pool_manager.acquire(Runtime.PYTHON_311)

        assert container is not None
        assert container.state == ContainerState.BUSY

    @pytest.mark.asyncio
    async def test_acquire_empty_pool(self, pool_manager):
        """Test acquiring from empty pool."""
        container = await pool_manager.acquire(Runtime.PYTHON_311)

        assert container is None

    @pytest.mark.asyncio
    async def test_acquire_all_busy(self, pool_manager):
        """Test acquiring when all containers are busy."""
        await pool_manager.warm_up(Runtime.PYTHON_311, count=1)

        # Acquire the only container
        container1 = await pool_manager.acquire(Runtime.PYTHON_311)
        assert container1 is not None

        # Try to acquire again - should fail
        container2 = await pool_manager.acquire(Runtime.PYTHON_311)
        assert container2 is None

    @pytest.mark.asyncio
    async def test_release_container(self, pool_manager):
        """Test releasing container back to pool."""
        await pool_manager.warm_up(Runtime.PYTHON_311, count=1)

        # Acquire and release
        container = await pool_manager.acquire(Runtime.PYTHON_311)
        assert container.state == ContainerState.BUSY

        await pool_manager.release(container, Runtime.PYTHON_311)
        assert container.state == ContainerState.WARM

    @pytest.mark.asyncio
    async def test_add_container(self, pool_manager, mock_docker_client):
        """Test adding container to pool."""
        # Create a warm container
        docker_container = mock_docker_client.containers.run.return_value
        warm_container = WarmContainer(
            container=docker_container,
            runtime="python:3.11",
        )

        await pool_manager.add(warm_container, Runtime.PYTHON_311)

        assert Runtime.PYTHON_311 in pool_manager._pools
        assert warm_container in pool_manager._pools[Runtime.PYTHON_311]
        assert warm_container.state == ContainerState.WARM

    @pytest.mark.asyncio
    async def test_get_status(self, pool_manager):
        """Test getting pool status."""
        await pool_manager.warm_up(Runtime.PYTHON_311, count=3)

        # Acquire one container
        await pool_manager.acquire(Runtime.PYTHON_311)

        status = await pool_manager.get_status(Runtime.PYTHON_311)

        assert status.runtime == Runtime.PYTHON_311
        assert status.total == 3
        assert status.available == 2
        assert status.busy == 1

    @pytest.mark.asyncio
    async def test_get_aggregate_status(self, pool_manager):
        """Test getting aggregate status."""
        await pool_manager.warm_up(Runtime.PYTHON_311, count=2)
        await pool_manager.warm_up(Runtime.NODE_20, count=1)

        status = await pool_manager.get_status()

        assert status.total == 3
        assert status.available == 3
        assert status.busy == 0

    @pytest.mark.asyncio
    async def test_create_container(self, pool_manager, mock_docker_client):
        """Test creating a single container."""
        container = await pool_manager._create_container(Runtime.PYTHON_311)

        assert container is not None
        assert container.runtime == "python:3.11"
        assert container.state == ContainerState.WARM

        # Verify Docker run was called with correct parameters
        mock_docker_client.containers.run.assert_called()
        call_kwargs = mock_docker_client.containers.run.call_args.kwargs

        assert call_kwargs["network_mode"] == "none"
        assert call_kwargs["mem_limit"] == "256m"
        assert call_kwargs["detach"] is True

    @pytest.mark.asyncio
    async def test_remove_container(self, pool_manager, mock_docker_client):
        """Test removing container."""
        await pool_manager.warm_up(Runtime.PYTHON_311, count=1)
        container = pool_manager._pools[Runtime.PYTHON_311][0]

        await pool_manager._remove_container(container, Runtime.PYTHON_311)

        assert container not in pool_manager._pools[Runtime.PYTHON_311]
        assert container.state == ContainerState.TERMINATING
        mock_docker_client.containers.run.return_value.remove.assert_called_with(force=True)

    @pytest.mark.asyncio
    async def test_cleanup_all_containers(self, pool_manager):
        """Test cleaning up all containers."""
        await pool_manager.warm_up(Runtime.PYTHON_311, count=2)
        await pool_manager.warm_up(Runtime.NODE_20, count=1)

        await pool_manager._cleanup_all_containers()

        assert len(pool_manager._pools) == 0

    @pytest.mark.asyncio
    async def test_handle_unhealthy_container(self, pool_manager):
        """Test handling unhealthy container."""
        await pool_manager.warm_up(Runtime.PYTHON_311, count=2)
        container = pool_manager._pools[Runtime.PYTHON_311][0]

        await pool_manager._handle_unhealthy_container(container, Runtime.PYTHON_311)

        assert container not in pool_manager._pools[Runtime.PYTHON_311]


class TestWarmPoolManagerIntegration:
    """Integration tests for WarmPoolManager."""

    @pytest.fixture
    def mock_docker_client(self):
        """Create mock Docker client with more realistic behavior."""
        client = MagicMock()
        client.ping.return_value = True
        client.images.get.return_value = MagicMock()

        container_counter = [0]

        def create_container(*args, **kwargs):
            container_counter[0] += 1
            container = MagicMock()
            # Use hex format to ensure unique first 12 chars
            container.id = f"{container_counter[0]:012x}abcdef123456"
            container.status = "running"
            container.exec_run.return_value = MagicMock(exit_code=0, output=(b"", b""))
            return container

        client.containers.run.side_effect = create_container

        return client

    @pytest.fixture
    def pool_manager(self, mock_docker_client):
        """Create WarmPoolManager instance."""
        return WarmPoolManager(
            docker_client=mock_docker_client,
            pool_size_per_runtime=5,
        )

    @pytest.mark.asyncio
    async def test_concurrent_acquire_release(self, pool_manager):
        """Test concurrent acquire and release operations."""
        import asyncio

        await pool_manager.warm_up(Runtime.PYTHON_311, count=5)

        async def acquire_and_release():
            container = await pool_manager.acquire(Runtime.PYTHON_311)
            if container:
                await asyncio.sleep(0.01)  # Simulate work
                await pool_manager.release(container, Runtime.PYTHON_311)
                return True
            return False

        # Run multiple concurrent operations
        results = await asyncio.gather(*[acquire_and_release() for _ in range(10)])

        # At least 5 should succeed (pool size)
        assert sum(results) >= 5

    @pytest.mark.asyncio
    async def test_multiple_runtimes(self, pool_manager):
        """Test managing multiple runtimes."""
        await pool_manager.warm_up(Runtime.PYTHON_311, count=2)
        await pool_manager.warm_up(Runtime.NODE_20, count=2)
        await pool_manager.warm_up(Runtime.GO_121, count=1)

        assert len(pool_manager._pools[Runtime.PYTHON_311]) == 2
        assert len(pool_manager._pools[Runtime.NODE_20]) == 2
        assert len(pool_manager._pools[Runtime.GO_121]) == 1

        # Acquire from each
        py_container = await pool_manager.acquire(Runtime.PYTHON_311)
        node_container = await pool_manager.acquire(Runtime.NODE_20)
        go_container = await pool_manager.acquire(Runtime.GO_121)

        assert py_container is not None
        assert node_container is not None
        assert go_container is not None

        # Check different containers
        assert py_container.id != node_container.id
        assert py_container.id != go_container.id
