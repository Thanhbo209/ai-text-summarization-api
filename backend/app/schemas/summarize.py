from typing import Literal

from pydantic import BaseModel, Field, field_validator

LengthType = Literal["short", "medium", "long"]
StyleType = Literal["paragraph", "bullet_points", "executive"]


class SummarizeRequest(BaseModel):
    # "..." mean required, no default
    text: str = Field(..., min_length=1)
    length: LengthType = "medium"
    style: StyleType = "paragraph"

    @field_validator("text")
    @classmethod
    def validate_text_not_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("text cannot be empty or consist only of whitespace")
        return stripped


class SummarizeResponse(BaseModel):
    summary: str = Field(..., min_length=1)
