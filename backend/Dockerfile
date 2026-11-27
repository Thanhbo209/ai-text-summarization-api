FROM python:3.13-slim

WORKDIR /app

# Install uv or pip dependencies depending on setup
COPY pyproject.toml uv.lock* ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev || pip install --no-cache-dir .

ENV PATH="/app/.venv/bin:$PATH"

COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]