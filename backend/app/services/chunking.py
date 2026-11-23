import re

_PARAGRAPH_SPLIT_RE = re.compile(r"\r?\n\s*\r?\n+")

def _split_paragraphs(text: str) -> list[str]:
    """Split text into non-empty trimmed paragraphs."""
    return [
        part.strip()
        for part in _PARAGRAPH_SPLIT_RE.split(text)
        if part and part.strip()
    ]

def _split_oversized_paragraph(paragraph: str, max_chars: int) -> list[str]:
    """Split a single paragraph exceeding max_chars into pieces each <= max_chars."""  
    pieces: list[str] = []
    remaining = paragraph.strip()

    while len(remaining) > max_chars:
        window = remaining[:max_chars]

        # Splitting at a whitespace boundary inside the budget window
        split_at = window.rfind(" ")
        if split_at <= 0:
            # Fallback for a single unbroken token longer than max_chars
            split_at = max_chars

        piece = remaining[:split_at].strip()
        if piece:
            pieces.append(piece)

        remaining = remaining[split_at:].strip()

    if remaining:
        pieces.append(remaining)

    return pieces

def chunk_text(text: str, max_chars: int) -> list[str]:
    """Deterministically split text into chunks each within max_chars."""
    if max_chars <= 0:
        raise ValueError("max_chars must be a positive integer.")

    if not text or not text.strip():
        return []

    paragraphs = _split_paragraphs(text)
    chunks: list[str] = []
    current_chunk: str | None = None

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            # Finalize any active chunk before splitting an oversized paragraph
            if current_chunk is not None:
                chunks.append(current_chunk)
                current_chunk = None
            oversized_pieces = _split_oversized_paragraph(paragraph, max_chars)
            chunks.extend(oversized_pieces)
            continue

        if current_chunk is None:
            current_chunk = paragraph
            continue

        candidate = f"{current_chunk}\n\n{paragraph}"
        if len(candidate) <= max_chars:
            current_chunk = candidate

        else:
            chunks.append(current_chunk)
            current_chunk = paragraph

    if current_chunk is not None:
        chunks.append(current_chunk)

    return [chunk for chunk in chunks if chunk.strip()]