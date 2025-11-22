"""
Code execution API endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid

from ..core.config import get_settings
from ..core.docker_manager import DockerManager
from ..services.execution_service import ExecutionService
from ..utils.auth import verify_api_key

router = APIRouter(prefix="/execute", tags=["execution"])
settings = get_settings()

class ExecuteRequest(BaseModel):
    """Code execution request"""
    code: str = Field(..., description="Code to execute")
    language: str = Field(..., description="Programming language")
    stdin: Optional[str] = Field(None, description="Standard input")
    environment: Optional[Dict[str, str]] = Field(None, description="Environment variables")
    timeout: Optional[int] = Field(None, description="Execution timeout in seconds")
    session_id: Optional[str] = Field(None, description="Session ID for tracking")

class ExecuteResponse(BaseModel):
    """Code execution response"""
    execution_id: str
    stdout: str
    stderr: str
    exit_code: int
    execution_time: float
    language: str
    session_id: Optional[str] = None

class ExecutionStatus(BaseModel):
    """Execution status"""
    execution_id: str
    status: str  # pending, running, completed, failed
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[ExecuteResponse] = None

# Initialize services
docker_manager = DockerManager()
execution_service = ExecutionService(docker_manager)

@router.post("/", response_model=ExecuteResponse)
async def execute_code(
    request: ExecuteRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key),
):
    """Execute code in a sandboxed environment"""

    # Validate language
    if request.language not in settings.supported_languages:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language: {request.language}. Supported languages: {', '.join(settings.supported_languages)}"
        )

    # Check execution limits
    if await execution_service.is_rate_limited(api_key):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please try again later."
        )

    try:
        # Execute code
        result = await execution_service.execute(
            code=request.code,
            language=request.language,
            stdin=request.stdin,
            environment=request.environment,
            timeout=request.timeout,
            session_id=request.session_id,
        )

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution failed: {str(e)}")

@router.post("/async", response_model=ExecutionStatus)
async def execute_code_async(
    request: ExecuteRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key),
):
    """Execute code asynchronously"""

    # Validate language
    if request.language not in settings.supported_languages:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language: {request.language}"
        )

    # Create execution task
    execution_id = str(uuid.uuid4())

    # Add to background tasks
    background_tasks.add_task(
        execution_service.execute_async,
        execution_id=execution_id,
        code=request.code,
        language=request.language,
        stdin=request.stdin,
        environment=request.environment,
        timeout=request.timeout,
        session_id=request.session_id,
    )

    return ExecutionStatus(
        execution_id=execution_id,
        status="pending",
        created_at=datetime.utcnow(),
    )

@router.get("/status/{execution_id}", response_model=ExecutionStatus)
async def get_execution_status(
    execution_id: str,
    api_key: str = Depends(verify_api_key),
):
    """Get execution status"""
    status = await execution_service.get_status(execution_id)

    if not status:
        raise HTTPException(
            status_code=404,
            detail=f"Execution {execution_id} not found"
        )

    return status

@router.post("/batch", response_model=List[ExecuteResponse])
async def execute_batch(
    requests: List[ExecuteRequest],
    api_key: str = Depends(verify_api_key),
):
    """Execute multiple code snippets"""

    if len(requests) > 10:
        raise HTTPException(
            status_code=400,
            detail="Maximum 10 executions allowed in a batch"
        )

    results = []
    for request in requests:
        try:
            result = await execution_service.execute(
                code=request.code,
                language=request.language,
                stdin=request.stdin,
                environment=request.environment,
                timeout=request.timeout,
                session_id=request.session_id,
            )
            results.append(result)
        except Exception as e:
            # Return error as result
            results.append(ExecuteResponse(
                execution_id=str(uuid.uuid4()),
                stdout="",
                stderr=str(e),
                exit_code=-1,
                execution_time=0,
                language=request.language,
                session_id=request.session_id,
            ))

    return results

@router.get("/languages", response_model=List[str])
async def get_supported_languages():
    """Get list of supported programming languages"""
    return settings.supported_languages

@router.get("/language/{language}/info")
async def get_language_info(language: str):
    """Get information about a specific language"""

    if language not in settings.supported_languages:
        raise HTTPException(
            status_code=404,
            detail=f"Language {language} not supported"
        )

    return {
        "language": language,
        "docker_image": settings.language_images.get(language),
        "file_extension": docker_manager._get_file_extension(language),
        "max_execution_time": settings.max_execution_time,
        "max_memory": settings.max_memory,
        "max_cpu": settings.max_cpu,
    }

@router.delete("/session/{session_id}")
async def cleanup_session(
    session_id: str,
    api_key: str = Depends(verify_api_key),
):
    """Cleanup all executions for a session"""
    await execution_service.cleanup_session(session_id)
    return {"message": f"Session {session_id} cleaned up"}

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "sandbox",
        "version": settings.app_version,
        "supported_languages": len(settings.supported_languages),
    }
