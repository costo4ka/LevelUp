"""Коды ошибок и общий формат ответа прикладного API: {ok, data, error}."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    DUPLICATE_TITLE = "DUPLICATE_TITLE"
    HABIT_LIMIT = "HABIT_LIMIT"
    STORAGE_LIMIT = "STORAGE_LIMIT"
    DATE_CHANGED = "DATE_CHANGED"
    CLOCK_ROLLBACK = "CLOCK_ROLLBACK"
    HABIT_NOT_ACTIVE = "HABIT_NOT_ACTIVE"
    NOT_FOUND = "NOT_FOUND"
    DATABASE_BUSY = "DATABASE_BUSY"
    STORAGE_ERROR = "STORAGE_ERROR"
    MIGRATION_FAILED = "MIGRATION_FAILED"
    ASSET_MISSING = "ASSET_MISSING"


DEFAULT_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.VALIDATION_ERROR: "Некорректные данные.",
    ErrorCode.DUPLICATE_TITLE: "Привычка с таким названием уже есть.",
    ErrorCode.HABIT_LIMIT: "Достигнут лимит активных привычек. Архивируйте одну из них.",
    ErrorCode.STORAGE_LIMIT: "Достигнут предел истории привычек.",
    ErrorCode.DATE_CHANGED: "Наступил новый день. Отметьте выполнение снова.",
    ErrorCode.CLOCK_ROLLBACK: (
        "Системные часы отстают от последней сохранённой даты. "
        "Исправьте время — изменения временно заблокированы."
    ),
    ErrorCode.HABIT_NOT_ACTIVE: "Эта привычка уже в архиве.",
    ErrorCode.NOT_FOUND: "Привычка не найдена.",
    ErrorCode.DATABASE_BUSY: "База данных занята. Повторите через секунду.",
    ErrorCode.STORAGE_ERROR: "Не удалось сохранить. Проверьте доступ к диску и повторите",
    ErrorCode.MIGRATION_FAILED: "Не удалось обновить базу данных.",
    ErrorCode.ASSET_MISSING: "Не найден файл изображения, показан запасной образ.",
}
RETRYABLE = {ErrorCode.DATABASE_BUSY, ErrorCode.STORAGE_ERROR}


@dataclass(frozen=True)
class ErrorInfo:
    code: str
    message: str
    field: str | None = None
    retryable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "field": self.field, "retryable": self.retryable}


class AppError(Exception):
    def __init__(self, code: ErrorCode, message: str, field: str | None = None, retryable: bool = False):
        super().__init__(f"{code.value}: {message}")
        self.code, self.message, self.field, self.retryable = code, message, field, retryable

    def info(self) -> ErrorInfo:
        return ErrorInfo(self.code.value, self.message, self.field, self.retryable)


def make_error(code: ErrorCode, message: str | None = None, field: str | None = None) -> AppError:
    return AppError(code, message or DEFAULT_MESSAGES[code], field, code in RETRYABLE)


@dataclass(frozen=True)
class Result:
    """Ровно одно из data и error непустое."""

    ok: bool
    data: dict[str, Any] | None = None
    error: ErrorInfo | None = None

    @classmethod
    def success(cls, data: dict[str, Any]) -> "Result":
        if not data:
            raise ValueError("data успешного ответа не может быть пустым")
        return cls(True, data, None)

    @classmethod
    def failure(cls, error: ErrorInfo) -> "Result":
        return cls(False, None, error)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "data": self.data, "error": self.error.to_dict() if self.error else None}
