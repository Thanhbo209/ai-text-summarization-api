from enum import Enum

from pydantic import BaseModel, Field, field_validator


class LengthEnum(str, Enum):
    short = 'short'
    medium = 'medium'
    long = 'long'

class StyleEnum(str, Enum):
    paragraph = 'paragraph'
    bullet_points = 'bullet_points'
    executive = 'executive'

class SummarizeRequest(BaseModel):
    text: str = Field(..., min_length=1)
    length: LengthEnum = LengthEnum.medium
    style: StyleEnum = StyleEnum.paragraph

    @field_validator("text")
    @classmethod
    def validate_text_not_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("text cannot be empty or consist only of whitespace")
        return stripped
