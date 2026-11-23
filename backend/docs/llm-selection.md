## 1. Chosen Provider & Fit for Backend Integration

- **Provider:** Google Gemini API (via Google AI Studio)
- **Why It Fits This Milestone:**
  - **Documentation:** Clear REST and official Python SDK documentation (`google-genai`), making request/response schemas and error semantics straightforward to verify.
  - **Cost:** Fast, lightweight model tiers keep per-token costs low during development, chunking tests, and multi-chunk summarization runs.
  - **Reliability & Availability:** Backed by Google infrastructure with broad regional availability and well-defined rate limit / quota behavior.

## 2. API Endpoint

- **Generation Endpoint (REST):**
  `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`
- **Usage:** Replace `{model}` with your target Gemini model ID and send a `POST` request to `:generateContent` for non-streaming summary generation (suitable for both direct `/summarize` calls and per-chunk summarization).

## 3. Authentication Method

- **Header-Based API Key:** Send the API key in the `x-goog-api-key` HTTP header rather than hardcoding credentials in source files.
- **Operational Practices:**
  - Load the key from an environment variable (e.g., `GEMINI_API_KEY`) in application configuration.
  - Restrict the API key in Google AI Studio / Google Cloud to only the Gemini API.
  - Mock the provider layer in automated tests so `pytest` runs deterministically without live API calls or secrets.

## 4. Request Payload Structure

A `POST` request to `:generateContent` sends a JSON body containing:

- **`contents` (required):** Ordered list of content objects, each containing `parts` (e.g., text blocks) and an optional `role` (`"user"` or `"model"`). Holds the summarization prompt and input text (or chunk).
- **`systemInstruction` (optional):** Separates system-level instructions (enforcing `length` and `style` requirements such as `short` + `bullet_points`) from user-supplied text.
- **`generationConfig` (optional):** Controls generation behavior, such as `temperature` (lower values help keep summaries faithful to source text) and `maxOutputTokens`.

## 5. Response Payload Structure

A successful `200 OK` response returns JSON with:

- **`candidates`:** List of generated candidates; each candidate provides `content.parts` with the generated text and a `finishReason` indicating completion status or truncation/blocking.
- **`usageMetadata`:** Token accounting fields (such as prompt tokens, output/candidate tokens, and total tokens) useful for observability, cost tracking, and chunk sizing.

## 6. Error Communication & Service Handling

The Gemini API reports errors using **HTTP status codes** alongside a **JSON `error` object** (`code`, `message`, `status`, and optional `details`):

- **`400` (`INVALID_ARGUMENT`):** Invalid request payload, bad parameters, or input exceeding context limits.
- **`401` / `403` (`UNAUTHENTICATED` / `PERMISSION_DENIED`):** Missing, invalid, restricted, or unauthorized API key / project access.
- **`404` (`NOT_FOUND`):** Invalid model name or endpoint path.
- **`429` (`RESOURCE_EXHAUSTED`):** Rate limit or quota exceeded; appropriate target for backoff/retry or throttling handling.
- **`500` / `503` / `504` (`INTERNAL` / `UNAVAILABLE`):** Transient server errors or timeouts suitable for bounded retries with backoff.

**Service Layer Guideline:** Catch provider/client exceptions inside the summarization service and map them into clean domain/HTTP responses rather than exposing raw upstream error payloads directly to callers.
