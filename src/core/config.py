"""
Sandbox service configuration
"""
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    """Sandbox service settings"""

    # Application
    app_name: str = "Nadoo Sandbox Service"
    app_version: str = "0.1.0"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8002
    workers: int = 1

    # Security
    secret_key: str = "your-secret-key-here-change-in-production"
    api_key: str = "sandbox-api-key-change-in-production"
    allowed_origins: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Docker
    docker_socket: str = "unix://var/run/docker.sock"
    docker_network: str = "nadoo_sandbox_network"
    docker_timeout: int = 30

    # Execution limits
    max_execution_time: int = 60  # seconds
    max_memory: str = "512m"
    max_cpu: float = 0.5
    max_concurrent_executions: int = 10

    # Redis
    redis_url: str = "redis://localhost:6379/2"
    redis_prefix: str = "nadoo:sandbox:"

    # Storage
    temp_dir: str = "/tmp/nadoo_sandbox"
    max_file_size: int = 10 * 1024 * 1024  # 10MB

    # Supported languages
    supported_languages: List[str] = [
        "python",
        "javascript",
        "typescript",
        "java",
        "go",
        "rust",
        "cpp",
        "csharp",
        "ruby",
        "php",
        "sql",
        "bash",
    ]

    # Language images
    language_images: dict = {
        "python": "python:3.11-slim",
        "javascript": "node:20-slim",
        "typescript": "node:20-slim",
        "java": "openjdk:17-slim",
        "go": "golang:1.21-alpine",
        "rust": "rust:1.74-slim",
        "cpp": "gcc:13",
        "csharp": "mcr.microsoft.com/dotnet/sdk:8.0",
        "ruby": "ruby:3.2-slim",
        "php": "php:8.2-cli",
        "sql": "postgres:16-alpine",
        "bash": "ubuntu:22.04",
    }

    # Monitoring
    enable_metrics: bool = True
    enable_tracing: bool = True
    jaeger_endpoint: Optional[str] = None

    # PostHog Analytics & Error Tracking
    posthog_api_key: Optional[str] = None
    posthog_host: str = "https://us.i.posthog.com"

    model_config = SettingsConfigDict(
        env_prefix="NADOO_SANDBOX_",
        env_file=".env",
        case_sensitive=False,
    )

@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
