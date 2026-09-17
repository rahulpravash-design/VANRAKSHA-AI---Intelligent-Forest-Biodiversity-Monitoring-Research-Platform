"""Shared response envelopes and query helpers."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    """Base for schemas read straight out of SQLAlchemy objects."""

    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    """A single page of results plus the metadata a table UI needs."""

    items: list[T]
    total: int = Field(description="Total rows matching the filter, ignoring pagination")
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total


class PaginationParams(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class Message(BaseModel):
    detail: str


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    database: str
    ai_engine: str
