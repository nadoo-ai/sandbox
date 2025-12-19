"""
Warm Pool Manager

Manages pre-warmed container pools for fast code execution.
"""

import asyncio
import logging
from collections import defaultdict
from typing import Dict, List, Optional

import docker
from docker.models.containers import Container

from .container import WarmContainer, ContainerState
from .health import PoolHealthChecker, PoolReplenisher
from ..executor.interface import Runtime
from ..executor.models import PoolStatus

logger = logging.getLogger(__name__)


class WarmPoolManager:
    """
    Manages pools of pre-warmed containers.

    Features:
    - Per-runtime container pools
    - Automatic container creation and cleanup
    - Health monitoring and replacement
    - TTL-based container recycling
    - Thread-safe container acquisition

    Example:
        manager = WarmPoolManager(docker_client)
        await manager.start()

        # Acquire container
        container = await manager.acquire(Runtime.PYTHON_311)

        # Use container...

        # Release back to pool
        await manager.release(container, Runtime.PYTHON_311)
    """

    # Docker image mapping
    RUNTIME_IMAGES = {
        Runtime.PYTHON_311: "python:3.11-slim",
        Runtime.PYTHON_312: "python:3.12-slim",
        Runtime.NODE_20: "node:20-slim",
        Runtime.NODE_22: "node:22-slim",
        Runtime.GO_121: "golang:1.21-alpine",
        Runtime.GO_122: "golang:1.22-alpine",
        Runtime.RUST_LATEST: "rust:slim",
        Runtime.JAVA_17: "openjdk:17-slim",
        Runtime.JAVA_21: "openjdk:21-slim",
    }

    # Container startup commands (keep alive)
    RUNTIME_COMMANDS = {
        Runtime.PYTHON_311: ["tail", "-f", "/dev/null"],
        Runtime.PYTHON_312: ["tail", "-f", "/dev/null"],
        Runtime.NODE_20: ["tail", "-f", "/dev/null"],
        Runtime.NODE_22: ["tail", "-f", "/dev/null"],
        Runtime.GO_121: ["tail", "-f", "/dev/null"],
        Runtime.GO_122: ["tail", "-f", "/dev/null"],
        Runtime.RUST_LATEST: ["tail", "-f", "/dev/null"],
        Runtime.JAVA_17: ["tail", "-f", "/dev/null"],
        Runtime.JAVA_21: ["tail", "-f", "/dev/null"],
    }

    def __init__(
        self,
        docker_client: Optional[docker.DockerClient] = None,
        pool_size_per_runtime: int = 5,
        max_idle_time: int = 300,
        container_ttl: int = 3600,
        health_check_interval: int = 30,
        memory_limit: str = "256m",
        cpu_limit: float = 0.5,
    ):
        """
        Initialize warm pool manager.

        Args:
            docker_client: Docker client (creates one if not provided)
            pool_size_per_runtime: Target containers per runtime
            max_idle_time: Max idle seconds before replacement
            container_ttl: Max container age in seconds
            health_check_interval: Seconds between health checks
            memory_limit: Memory limit per container
            cpu_limit: CPU limit per container
        """
        self.docker_client = docker_client or docker.from_env()
        self.pool_size_per_runtime = pool_size_per_runtime
        self.max_idle_time = max_idle_time
        self.container_ttl = container_ttl
        self.memory_limit = memory_limit
        self.cpu_limit = cpu_limit

        # Container pools: runtime -> list of WarmContainers
        self._pools: Dict[Runtime, List[WarmContainer]] = defaultdict(list)

        # Target sizes per runtime
        self._target_sizes: Dict[Runtime, int] = {}

        # Locks for thread safety
        self._locks: Dict[Runtime, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._global_lock = asyncio.Lock()

        # Background tasks
        self._health_checker = PoolHealthChecker(
            self, check_interval=health_check_interval
        )
        self._replenisher = PoolReplenisher(self, check_interval=5.0)

        # State
        self._started = False

    async def start(self) -> None:
        """Start the pool manager and background tasks"""
        if self._started:
            return

        logger.info("Starting warm pool manager")

        # Start background tasks
        await self._health_checker.start()
        await self._replenisher.start()

        # Set up unhealthy container handler
        self._health_checker.on_unhealthy(self._handle_unhealthy_container)

        self._started = True
        logger.info("Warm pool manager started")

    async def stop(self) -> None:
        """Stop the pool manager and cleanup all containers"""
        if not self._started:
            return

        logger.info("Stopping warm pool manager")

        # Stop background tasks
        await self._health_checker.stop()
        await self._replenisher.stop()

        # Cleanup all containers
        await self._cleanup_all_containers()

        self._started = False
        logger.info("Warm pool manager stopped")

    async def warm_up(self, runtime: Runtime, count: int = 1) -> int:
        """
        Pre-warm containers for a runtime.

        Args:
            runtime: Runtime to warm up
            count: Number of containers to create

        Returns:
            Number of containers actually created
        """
        # Set/update target size
        async with self._global_lock:
            current_target = self._target_sizes.get(runtime, 0)
            self._target_sizes[runtime] = max(current_target, count)

        created = await self._create_containers(runtime, count)
        logger.info(f"Warmed up {created} containers for {runtime.value}")
        return created

    async def acquire(self, runtime: Runtime) -> Optional[WarmContainer]:
        """
        Acquire a container from the pool.

        Args:
            runtime: Runtime needed

        Returns:
            WarmContainer if available, None if pool is empty
        """
        async with self._locks[runtime]:
            pool = self._pools[runtime]

            # Find available container
            for container in pool:
                if container.is_available:
                    container.mark_busy()
                    logger.debug(f"Acquired container {container.id} for {runtime.value}")
                    return container

            logger.debug(f"No available container in pool for {runtime.value}")
            return None

    async def release(self, container: WarmContainer, runtime: Runtime) -> None:
        """
        Release a container back to the pool.

        Args:
            container: Container to release
            runtime: Container's runtime
        """
        async with self._locks[runtime]:
            # Check if container should be replaced
            if container.should_replace(self.container_ttl, self.max_idle_time):
                logger.info(f"Replacing container {container.id} (TTL/idle)")
                await self._remove_container(container, runtime)
                return

            # Reset and mark as available
            container.mark_warm()
            logger.debug(f"Released container {container.id} back to pool")

    async def add(self, container: WarmContainer, runtime: Runtime) -> None:
        """
        Add a new container to the pool.

        Args:
            container: Container to add
            runtime: Container's runtime
        """
        async with self._locks[runtime]:
            container.mark_warm()
            self._pools[runtime].append(container)
            logger.debug(f"Added container {container.id} to {runtime.value} pool")

    async def get_status(self, runtime: Optional[Runtime] = None) -> PoolStatus:
        """
        Get pool status.

        Args:
            runtime: Specific runtime, or None for aggregate

        Returns:
            PoolStatus with pool statistics
        """
        if runtime:
            pool = self._pools.get(runtime, [])
            available = sum(1 for c in pool if c.is_available)
            busy = sum(1 for c in pool if c.state == ContainerState.BUSY)

            return PoolStatus(
                runtime=runtime,
                total=len(pool),
                available=available,
                busy=busy,
                container_ids=[c.id for c in pool],
            )
        else:
            # Aggregate across all runtimes
            total = sum(len(pool) for pool in self._pools.values())
            available = sum(
                sum(1 for c in pool if c.is_available)
                for pool in self._pools.values()
            )
            busy = sum(
                sum(1 for c in pool if c.state == ContainerState.BUSY)
                for pool in self._pools.values()
            )

            return PoolStatus(
                runtime=Runtime.PYTHON_311,  # Default for aggregate
                total=total,
                available=available,
                busy=busy,
            )

    async def _create_containers(self, runtime: Runtime, count: int) -> int:
        """Create multiple containers for a runtime"""
        created = 0
        tasks = []

        for _ in range(count):
            tasks.append(self._create_container(runtime))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, WarmContainer):
                async with self._locks[runtime]:
                    self._pools[runtime].append(result)
                created += 1
            elif isinstance(result, Exception):
                logger.error(f"Failed to create container: {result}")

        return created

    async def _create_container(self, runtime: Runtime) -> WarmContainer:
        """Create a single container"""
        image = self.RUNTIME_IMAGES.get(runtime, runtime.docker_image)
        command = self.RUNTIME_COMMANDS.get(runtime, ["tail", "-f", "/dev/null"])

        logger.debug(f"Creating container for {runtime.value} using {image}")

        # Pull image if needed
        try:
            self.docker_client.images.get(image)
        except docker.errors.ImageNotFound:
            logger.info(f"Pulling image: {image}")
            await asyncio.to_thread(self.docker_client.images.pull, image)

        # Create container
        container: Container = await asyncio.to_thread(
            self.docker_client.containers.run,
            image,
            command=command,
            detach=True,
            remove=False,
            network_mode="none",  # No network access
            mem_limit=self.memory_limit,
            nano_cpus=int(self.cpu_limit * 1e9),
            pids_limit=50,
            read_only=False,  # Need to write code files
            tmpfs={"/tmp": "size=10m,mode=1777"},
            labels={
                "nadoo.sandbox": "true",
                "nadoo.runtime": runtime.value,
            },
            security_opt=["no-new-privileges"],
        )

        warm_container = WarmContainer(
            container=container,
            runtime=runtime.value,
            container_id=container.id[:12],
            state=ContainerState.WARM,
        )

        logger.info(f"Created container {warm_container.id} for {runtime.value}")
        return warm_container

    async def _remove_container(
        self,
        container: WarmContainer,
        runtime: Runtime,
        from_pool: bool = True,
    ) -> None:
        """Remove and cleanup a container"""
        container.mark_terminating()

        if from_pool:
            try:
                self._pools[runtime].remove(container)
            except ValueError:
                pass

        try:
            await asyncio.to_thread(
                container.container.remove,
                force=True,
            )
            logger.debug(f"Removed container {container.id}")
        except Exception as e:
            logger.error(f"Failed to remove container {container.id}: {e}")

    async def _handle_unhealthy_container(
        self,
        container: WarmContainer,
        runtime: Runtime,
    ) -> None:
        """Handle unhealthy container detection"""
        logger.info(f"Handling unhealthy container {container.id}")
        await self._remove_container(container, runtime)

    async def _cleanup_all_containers(self) -> None:
        """Cleanup all containers in all pools"""
        tasks = []

        for runtime, pool in self._pools.items():
            for container in list(pool):
                tasks.append(
                    self._remove_container(container, runtime, from_pool=False)
                )

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self._pools.clear()
        logger.info("All containers cleaned up")
