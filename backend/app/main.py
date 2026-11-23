from fastapi import FastAPI, HTTPException, status

from app.schemas.summarize import SummarizeRequest, SummarizeResponse
from app.services.summarization import (
    SummarizationConnectionError,
    SummarizationProviderError,
    SummarizationResponseError,
    SummarizationTimeoutError,
    summarize_text_with_gemini,
)

app = FastAPI()

@app.get("/")
def home() -> dict[str, str]:
    return {"message": "Hello World"}

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

@app.post("/summarize", response_model=SummarizeResponse)
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