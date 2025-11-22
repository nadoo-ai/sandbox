"""
Nadoo Sandbox Service - Secure code execution environment
"""
import os
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
import uvicorn

from core.config import get_settings
from core.docker_manager import DockerManager
from api import execute

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Initialize Docker manager
docker_manager = DockerManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""

    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")

    # Initialize PostHog for error tracking
    from core.posthog_client import PostHogClient
    PostHogClient.initialize(settings.posthog_api_key, settings.posthog_host)

    # Create temp directory
    Path(settings.temp_dir).mkdir(parents=True, exist_ok=True)

    # Pre-pull Docker images
    logger.info("Pre-pulling Docker images...")
    for language, image in settings.language_images.items():
        try:
            docker_manager.client.images.get(image)
            logger.info(f"Image {image} already exists")
        except:
            logger.info(f"Pulling image {image} for {language}...")
            try:
                docker_manager.client.images.pull(image)
                logger.info(f"Successfully pulled {image}")
            except Exception as e:
                logger.warning(f"Failed to pull {image}: {e}")

    yield

    # Shutdown
    logger.info("Shutting down sandbox service")

    # Shutdown PostHog client
    from core.posthog_client import PostHogClient
    PostHogClient.shutdown()

    # Cleanup containers
    await docker_manager.cleanup_all()

    # Cleanup temp files
    try:
        import shutil
        shutil.rmtree(settings.temp_dir, ignore_errors=True)
    except:
        pass

# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

# Mount Prometheus metrics
if settings.enable_metrics:
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

# Include routers
app.include_router(execute.router, prefix="/api/v1")

# Import and include plugin router
try:
    from api import plugin_execute
    app.include_router(plugin_execute.router, prefix="/api/v1")
    logger.info("Plugin execution API registered")
except ImportError as e:
    logger.warning(f"Plugin execution API not available: {e}")

# Exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "type": type(exc).__name__,
        }
    )

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Nadoo Sandbox Service",
        "version": settings.app_version,
        "status": "running",
        "endpoints": {
            "execute": "/api/v1/execute",
            "languages": "/api/v1/execute/languages",
            "health": "/api/v1/execute/health",
            "metrics": "/metrics" if settings.enable_metrics else None,
            "docs": "/docs" if settings.debug else None,
        }
    }

# Health check
@app.get("/health")
async def health():
    """Health check endpoint"""

    # Check Docker
    docker_healthy = False
    try:
        docker_manager.client.ping()
        docker_healthy = True
    except:
        pass

    return {
        "status": "healthy" if docker_healthy else "degraded",
        "service": "sandbox",
        "version": settings.app_version,
        "checks": {
            "docker": docker_healthy,
        }
    }

def main():
    """Main entry point"""
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        workers=settings.workers if not settings.debug else 1,
        log_level="info" if not settings.debug else "debug",
    )

if __name__ == "__main__":
    main()
