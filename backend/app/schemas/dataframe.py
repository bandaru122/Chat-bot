"""Pydantic schemas for DataFrame question answering."""
from typing import Optional

from pydantic import BaseModel, model_validator


class DataframeAskRequest(BaseModel):
    question: str
    model: Optional[str] = None
    google_sheet_url: Optional[str] = None
    worksheet: str = "0"
    uploaded_file_url: Optional[str] = None
    max_rows: int = 2000

    @model_validator(mode="after")
    def validate_source(self) -> "DataframeAskRequest":
        if not (self.google_sheet_url or self.uploaded_file_url):
            raise ValueError("Provide either google_sheet_url or uploaded_file_url")
        return self


class DataframeAskResponse(BaseModel):
    answer: str
    row_count: int
    columns: list[str]
    source: str
    intermediate_steps: list[str]
