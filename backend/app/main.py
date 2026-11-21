from fastapi import FastAPI

from app.schemas.summarize import SummarizeRequest, SummarizeResponse

app = FastAPI()

@app.get("/")
def home() -> dict[str, str]:
    return {"message": "Hello World"}

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

@app.post("/summarize", response_model=SummarizeResponse)
def summarize_text(data: SummarizeRequest) -> SummarizeResponse:
    placeholder_summary = (
        f"[{data.length} | {data.style}] "
        f"Temporary summary for input of length {len(data.text)}."
    )
    return SummarizeResponse(summary=placeholder_summary)