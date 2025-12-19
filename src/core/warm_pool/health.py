"""
Pool Health Checker

Background task for monitoring container health and pool status.
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from .manager import WarmPoolManager

logger = logging.getLogger(__name__)


class PoolHealthChecker:
    """
    Background health checker for warm pool.

    Periodically checks container health and replaces unhealthy containers.
    """

    def __init__(
        self,
        pool_manager: "WarmPoolManager",
        check_interval: float = 30.0,
        container_timeout: float = 5.0,
    ):
        """
        Initialize health checker.

        Args:
            pool_manager: Pool manager to check
            check_interval: Seconds between health checks
            container_timeout: Timeout for container health check
        """
        self.pool_manager = pool_manager
        self.check_interval = check_interval
        self.container_timeout = container_timeout

        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Callbacks
        self._on_unhealthy: Optional[Callable] = None

    async def start(self) -> None:
        """Start health checker background task"""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._health_check_loop())
        logger.info("Pool health checker started")

    async def stop(self) -> None:
        """Stop health checker"""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("Pool health checker stopped")

    def on_unhealthy(self, callback: Callable) -> None:
        """Set callback for unhealthy container detection"""
        self._on_unhealthy = callback

    async def _health_check_loop(self) -> None:
        """Main health check loop"""
        while self._running:
            try:
                await self._check_all_containers()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}", exc_info=True)
                await asyncio.sleep(self.check_interval)

    async def _check_all_containers(self) -> None:
        """Check health of all containers in pool"""
        unhealthy_count = 0

        for runtime, containers in self.pool_manager._pools.items():
            for container in list(containers):
                try:
                    healthy = await self._check_container(container)

                    if not healthy:
                        unhealthy_count += 1
                        logger.warning(
                            f"Unhealthy container detected: {container.id} "
                            f"(runtime: {runtime})"
                        )

                        if self._on_unhealthy:
                            await self._on_unhealthy(container, runtime)

                except Exception as e:
                    logger.error(
                        f"Failed to check container {container.id}: {e}"
                    )
                    container.record_health_check(False, str(e))

        if unhealthy_count > 0:
            logger.info(f"Health check complete: {unhealthy_count} unhealthy containers")

    async def _check_container(self, container) -> bool:
        """
        Check single container health.

        Args:
            container: WarmContainer to check

        Returns:
            True if healthy
        """
        from .container import ContainerState

        # Skip containers that are busy or already unhealthy
        if container.state in (
            ContainerState.BUSY,
            ContainerState.UNHEALTHY,
            ContainerState.TERMINATING,
        ):
            return container.state != ContainerState.UNHEALTHY

        try:
            # Reload container state from Docker
            container.container.reload()
            docker_status = container.container.status

            if docker_status != "running":
                container.record_health_check(
                    False, f"Container not running: {docker_status}"
                )
                return False

            # Run simple health check command
            exit_code, _ = await asyncio.wait_for(
                asyncio.to_thread(
                    container.container.exec_run,
                    "echo health",
                    demux=True,
                ),
                timeout=self.container_timeout,
            )

            healthy = exit_code == 0
            container.record_health_check(healthy)
            return healthy

        except asyncio.TimeoutError:
            container.record_health_check(False, "Health check timed out")
            return False

        except Exception as e:
            container.record_health_check(False, str(e))
            return False


class PoolReplenisher:
    """
    Background task for replenishing the warm pool.

    Maintains target pool size by creating new containers as needed.
    """

    def __init__(
        self,
        pool_manager: "WarmPoolManager",
        check_interval: float = 5.0,
    ):
        """
        Initialize replenisher.

        Args:
            pool_manager: Pool manager to replenish
            check_interval: Seconds between replenish checks
        """
        self.pool_manager = pool_manager
        self.check_interval = check_interval

        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start replenisher background task"""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._replenish_loop())
        logger.info("Pool replenisher started")

    async def stop(self) -> None:
        """Stop replenisher"""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("Pool replenisher stopped")

    async def _replenish_loop(self) -> None:
        """Main replenish loop"""
        while self._running:
            try:
                await self._replenish_pools()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Replenish error: {e}", exc_info=True)
                await asyncio.sleep(self.check_interval)

    async def _replenish_pools(self) -> None:
        """Check and replenish all pools"""
        for runtime, target_size in self.pool_manager._target_sizes.items():
            current_size = len(self.pool_manager._pools.get(runtime, []))

            # Replenish if below target
            if current_size < target_size:
                needed = target_size - current_size
                logger.debug(
                    f"Replenishing pool for {runtime}: "
                    f"current={current_size}, target={target_size}, needed={needed}"
                )

                try:
                    await self.pool_manager._create_containers(runtime, needed)
                except Exception as e:
                    logger.error(f"Failed to replenish pool for {runtime}: {e}")
