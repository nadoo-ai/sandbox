"""
PostHog Analytics and Error Tracking Client for Sandbox

Provides centralized error tracking using PostHog cloud service.
"""

import logging
from typing import Any, Dict, Optional

from posthog import Posthog

logger = logging.getLogger(__name__)


class PostHogClient:
    """Singleton PostHog client for error tracking and analytics"""

    _instance: Optional[Posthog] = None
    _enabled: bool = False

    @classmethod
    def initialize(cls, api_key: Optional[str], api_host: Optional[str] = None) -> None:
        """Initialize PostHog client on application startup"""
        if not api_key or not api_host:
            logger.warning(
                "PostHog API key or host not configured. Error tracking disabled. "
                "Set POSTHOG_API_KEY and POSTHOG_HOST to enable."
            )
            cls._enabled = False
            return

        try:
            cls._instance = Posthog(
                project_api_key=api_key,
                host=api_host,
                # Enable automatic exception capture
                enable_exception_autocapture=True,
                # Server-side functions can be short-lived, so we flush immediately
                on_error=cls._on_error,
            )
            cls._enabled = True
            logger.info(f"PostHog client initialized successfully (host: {api_host})")
        except Exception as e:
            logger.error(f"Failed to initialize PostHog client: {e}")
            cls._enabled = False

    @classmethod
    def _on_error(cls, error: Exception, items: Any) -> None:
        """Error handler for PostHog client itself"""
        logger.error(f"PostHog client error: {error}")

    @classmethod
    def capture_exception(
        cls,
        exception: Exception,
        distinct_id: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Capture an exception to PostHog

        Args:
            exception: The exception to capture
            distinct_id: User ID or session ID (optional)
            properties: Additional properties to attach (optional)
        """
        if not cls._enabled or not cls._instance:
            return

        try:
            # Build properties
            error_properties = {
                "error_type": type(exception).__name__,
                "error_message": str(exception),
                "error_module": exception.__class__.__module__,
                "service": "nadoo-sandbox",
            }

            # Add custom properties
            if properties:
                error_properties.update(properties)

            # Use anonymous ID if no distinct_id provided
            if not distinct_id:
                distinct_id = "sandbox-anonymous"

            # Capture event
            cls._instance.capture(
                distinct_id=distinct_id,
                event="$exception",
                properties=error_properties,
            )

            # Flush immediately for server-side
            cls._instance.flush()

        except Exception as e:
            logger.error(f"Failed to capture exception to PostHog: {e}")

    @classmethod
    def shutdown(cls) -> None:
        """Shutdown PostHog client and flush any pending events"""
        if cls._instance:
            try:
                cls._instance.shutdown()
                logger.info("PostHog client shut down successfully")
            except Exception as e:
                logger.error(f"Error shutting down PostHog client: {e}")
            finally:
                cls._instance = None
                cls._enabled = False


# Convenience function
def capture_exception(
    exception: Exception,
    distinct_id: Optional[str] = None,
    properties: Optional[Dict[str, Any]] = None,
) -> None:
    """Capture an exception to PostHog"""
    PostHogClient.capture_exception(exception, distinct_id, properties)
