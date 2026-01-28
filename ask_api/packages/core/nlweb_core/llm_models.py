# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Pydantic models for type-safe LLM responses.

These models provide:
1. Compile-time type hints for IDE support
2. Runtime validation with Pydantic
3. Automatic clamping/normalization of values
"""

from pydantic import BaseModel, Field, field_validator


class RankingResponse(BaseModel):
    """Response model for ranking/relevance scoring with description."""
    score: int = Field(..., ge=0, le=100, description="Relevance score between 0 and 100")
    description: str = Field(..., description="Short description of the item")

    @field_validator('score', mode='before')
    @classmethod
    def clamp_score(cls, v: int) -> int:
        """Clamp score to valid range 0-100."""
        if isinstance(v, (int, float)):
            return max(0, min(100, int(v)))
        return v


class ScoreResponse(BaseModel):
    """Response model for simple score-only responses (intent detection, elicitation checks)."""
    score: int = Field(..., ge=0, le=100, description="Score between 0 and 100")

    @field_validator('score', mode='before')
    @classmethod
    def clamp_score(cls, v: int) -> int:
        """Clamp score to valid range 0-100."""
        if isinstance(v, (int, float)):
            return max(0, min(100, int(v)))
        return v


class QuestionResponse(BaseModel):
    """Response model for generated follow-up questions."""
    question: str = Field(..., min_length=1, description="The generated question text")
