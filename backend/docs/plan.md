# Feature Branch Plan

| Order | Branch Name | Architecture Component | Key Deliverables & Pytest Coverage |
| :---: | :--- | :--- | :--- |
| 1 | `feat/pydantic-schemas` | **E / K / O**: Pydantic Validation & Response Model | Request/response models, input length constraints, `422` validation tests |
| 2 | `feat/llm-provider` | **I**: LLM Provider | Base provider interface/client wrapper, API key config via `.env`, mocked unit tests |
| 3 | `feat/summarization-service` | **G / H**: Summarization Service (Small Input) | Core `/summarize` endpoint for small texts, mocked provider integration tests |
| 4 | `feat/text-chunker` | **J / L / M / N**: Text Chunker & Map-Reduce Flow | Token/character splitting, chunk summarization, final synthesis for large inputs |
| 5 | `feat/api-key-auth` | **C**: API Key Authentication | FastAPI `Depends()` security header check, `401`/`403` unauthorized tests |
| 6 | `feat/redis-rate-limiter` | **D**: Redis Rate Limiter | Redis connection/Docker setup, sliding-window or fixed-window limiter, `429` tests |
