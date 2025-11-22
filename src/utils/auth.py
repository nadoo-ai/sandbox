"""
Authentication utilities for sandbox service
"""
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader
from typing import Optional

from ..core.config import get_settings

settings = get_settings()
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    """Verify API key"""

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key is required",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # In production, this should check against a database or secret store
    if api_key != settings.api_key:
        raise HTTPException(
            status_code=403,
            detail="Invalid API key",
        )

    return api_key
