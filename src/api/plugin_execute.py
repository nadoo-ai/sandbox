"""
Plugin Execution API - Execute Nadoo plugins in secure containers
"""
import asyncio
import json
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel, Field

from core.config import get_settings
from services.plugin_runner import PluginRunner

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/plugin", tags=["Plugin Execution"])

# Initialize plugin runner
plugin_runner = PluginRunner()


class PluginExecutionRequest(BaseModel):
    """Plugin execution request"""
    plugin_code: str = Field(..., description="Plugin source code")
    entry_point: str = Field(default="main.py", description="Entry point file name")
    tool_name: str = Field(..., description="Tool to execute")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Tool parameters")

    # Execution context
    execution_id: str = Field(..., description="Execution UUID")
    plugin_id: str = Field(..., description="Plugin UUID")
    workspace_id: str = Field(..., description="Workspace UUID")
    user_id: Optional[str] = Field(None, description="User UUID")
    application_id: Optional[str] = Field(None, description="Application UUID")
    model_uuid: Optional[str] = Field(None, description="Model UUID")
    workflow_id: Optional[str] = Field(None, description="Workflow UUID")
    node_id: Optional[str] = Field(None, description="Node UUID")

    # Security
    permissions: list[str] = Field(default_factory=list, description="Plugin permissions")
    allowed_tool_ids: list[str] = Field(default_factory=list, description="Allowed tool IDs")
    allowed_kb_ids: list[str] = Field(default_factory=list, description="Allowed KB IDs")

    # API access
    api_base_url: str = Field(..., description="Backend API base URL")
    api_token: str = Field(..., description="JWT token for API access")

    # Plugin metadata
    sdk_version: str = Field(default="0.1.0", description="SDK version")
    plugin_version: str = Field(default="1.0.0", description="Plugin version")
    debug_mode: bool = Field(default=False, description="Debug mode")

    # Resource limits (override defaults)
    timeout: Optional[int] = Field(None, description="Execution timeout (seconds)")
    memory_limit: Optional[str] = Field(None, description="Memory limit (e.g., '256m')")


class PluginExecutionResponse(BaseModel):
    """Plugin execution response"""
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    traceback: Optional[str] = None
    logs: Optional[list] = None
    trace: Optional[list] = None
    execution_time: Optional[float] = None


def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """Verify API key"""
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


@router.post("/execute", response_model=PluginExecutionResponse)
async def execute_plugin(
    request: PluginExecutionRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Execute a plugin in a secure sandboxed environment

    This endpoint:
    1. Creates a temporary directory with plugin code
    2. Generates execution config
    3. Spawns a plugin-runner Docker container
    4. Executes plugin with RestrictedPython
    5. Returns results and cleans up
    """
    logger.info(f"Executing plugin {request.plugin_id}, tool: {request.tool_name}")

    temp_dir = None
    try:
        # Create temporary directory for plugin code
        temp_dir = Path(tempfile.mkdtemp(dir=settings.temp_dir))
        plugin_dir = temp_dir / "code"
        plugin_dir.mkdir()

        # Write plugin code
        entry_point_path = plugin_dir / request.entry_point
        entry_point_path.write_text(request.plugin_code, encoding='utf-8')

        # Create execution config
        config = {
            "execution_id": request.execution_id,
            "plugin_id": request.plugin_id,
            "workspace_id": request.workspace_id,
            "user_id": request.user_id,
            "application_id": request.application_id,
            "model_uuid": request.model_uuid,
            "workflow_id": request.workflow_id,
            "node_id": request.node_id,
            "tool_name": request.tool_name,
            "parameters": request.parameters,
            "permissions": request.permissions,
            "allowed_tool_ids": request.allowed_tool_ids,
            "allowed_kb_ids": request.allowed_kb_ids,
            "api_base_url": request.api_base_url,
            "api_token": request.api_token,
            "sdk_version": request.sdk_version,
            "plugin_version": request.plugin_version,
            "debug_mode": request.debug_mode,
            "entry_point": request.entry_point,
        }

        config_path = temp_dir / "config.json"
        config_path.write_text(json.dumps(config, indent=2), encoding='utf-8')

        # Execute in plugin-runner container
        result = await plugin_runner.execute(
            plugin_dir=str(plugin_dir),
            config_path=str(config_path),
            timeout=request.timeout or settings.max_execution_time,
            memory_limit=request.memory_limit or settings.max_memory,
        )

        return PluginExecutionResponse(**result)

    except asyncio.TimeoutError:
        logger.error(f"Plugin execution timeout: {request.plugin_id}")
        return PluginExecutionResponse(
            success=False,
            error="Execution timeout exceeded",
        )

    except Exception as e:
        logger.error(f"Plugin execution failed: {e}", exc_info=True)
        return PluginExecutionResponse(
            success=False,
            error=str(e),
            traceback=str(e),
        )

    finally:
        # Cleanup temp directory
        if temp_dir and temp_dir.exists():
            try:
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp dir: {e}")


@router.get("/health")
async def plugin_health():
    """Plugin execution health check"""
    # Check if plugin-runner image exists
    try:
        import docker
        client = docker.from_env()
        client.images.get("nadoo-plugin-runner:latest")
        runner_available = True
    except:
        runner_available = False

    return {
        "status": "healthy" if runner_available else "degraded",
        "plugin_runner_image": runner_available,
        "max_concurrent": settings.max_concurrent_executions,
    }
