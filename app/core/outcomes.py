from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

from app.core.enums import OperationStatus

T = TypeVar("T")


class OperationOutcome(BaseModel, Generic[T]):
    status: OperationStatus
    data: T | None = None
    error_code: str | None = None
    error_message: str | None = None

