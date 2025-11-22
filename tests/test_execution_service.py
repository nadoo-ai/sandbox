"""
Tests for the execution service
"""

import pytest


class TestExecutionService:
    """Tests for ExecutionService class"""

    def test_execution_service_import(self):
        """Test that ExecutionService can be imported"""
        from src.services.execution_service import ExecutionService

        assert ExecutionService is not None

    def test_execution_service_instantiation(self):
        """Test that ExecutionService can be instantiated"""
        from src.services.execution_service import ExecutionService

        service = ExecutionService()
        assert service is not None

    @pytest.mark.asyncio
    async def test_supported_languages_list(self):
        """Test that supported languages are defined"""
        from src.core.config import settings

        # Verify that language configuration exists
        assert hasattr(settings, "SUPPORTED_LANGUAGES") or hasattr(
            settings, "supported_languages"
        )
