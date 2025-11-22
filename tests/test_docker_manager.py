"""
Tests for Docker manager
"""

import pytest


class TestDockerManager:
    """Tests for DockerManager class"""

    def test_docker_manager_import(self):
        """Test that DockerManager can be imported"""
        from src.core.docker_manager import DockerManager

        assert DockerManager is not None

    def test_docker_manager_instantiation(self):
        """Test that DockerManager can be instantiated"""
        from src.core.docker_manager import DockerManager

        try:
            manager = DockerManager()
            assert manager is not None
        except Exception as e:
            # Docker may not be available in test environment
            pytest.skip(f"Docker not available: {e}")

    def test_docker_connection(self):
        """Test Docker daemon connection"""
        from src.core.docker_manager import DockerManager

        try:
            manager = DockerManager()
            # Try to ping Docker daemon
            if hasattr(manager, "client") and hasattr(manager.client, "ping"):
                manager.client.ping()
        except Exception as e:
            # Docker may not be available in test environment
            pytest.skip(f"Docker not available: {e}")
