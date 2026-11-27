from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.redis import REDIS_TRANSIENT_ERRORS, RedisConnectionManager
from app.dependencies.auth import verify_api_key
from app.dependencies.redis import get_redis_client
from app.schemas.summarize import SummarizeRequest, SummarizeResponse
from app.services.summarization import (
    SummarizationConnectionError,
    SummarizationProviderError,
    SummarizationResponseError,
    SummarizationTimeoutError,
    summarize_text_with_gemini,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    redis_manager = RedisConnectionManager(settings)
    app.state.redis_manager = redis_manager

    await redis_manager.startup(fail_on_error=False)
    try:
        yield
    finally:
        await redis_manager.shutdown()

app = FastAPI(title="AI Text Summarization API", lifespan=lifespan)

@app.get("/")
def home() -> dict[str, str]:
    return {"message": "Hello World"}

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

@app.get("/redis-check")
async def redis_check(redis_client: Annotated[Redis, Depends(get_redis_client)]):
    try:
        pong = await redis_client.ping()
        return {"redis": "connected" if pong else "degraded"}
    except REDIS_TRANSIENT_ERRORS as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis command failed.",
        ) from exc

@app.post("/summarize", response_model=SummarizeResponse, dependencies=[Depends(verify_api_key)])
async def summarize_text(data: SummarizeRequest) -> SummarizeResponse:
    try:
        summary = await summarize_text_with_gemini(
           text=data.text, 
           length=data.length,
           style=data.style,
        )

    except SummarizationTimeoutError as exc:
       raise HTTPException(
           status_code=status.HTTP_504_GATEWAY_TIMEOUT,
           detail="Summarization request timed out."
        ) from exc

    except SummarizationProviderError as exc:
        if exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Summarization provider rate limit exceeded.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Summarization provider rejected or failed the request.",
        ) from exc
    
    except SummarizationConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to reach summarization provider.",
        ) from exc

    except SummarizationResponseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Invalid response received from summarization provider.",
        ) from exc

    return SummarizeResponse(summary=summary)