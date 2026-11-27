import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from app.core.config import Settings, get_settings

_api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)


def verify_api_key(
    api_key: Annotated[str | None, Depends(_api_key_header)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    """Validate the incoming X-API-Key header against configured settings."""
    if not api_key or not api_key.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-API header")

    provided_key = api_key.strip()
    excepted_key = settings.api_key

    if not secrets.compare_digest(
        provided_key.encode("utf-8"),
        excepted_key.encode("utf-8"),
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API Key.")

    return provided_key
