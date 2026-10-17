from __future__ import annotations

from levelup.domain.errors import Result


def ok(result: Result) -> dict:
    assert result.ok, result.error
    assert result.error is None and result.data
    return result.data


def fail(result: Result, code: str):
    assert not result.ok, result.data
    assert result.data is None and result.error.code == code, result.error
    return result.error
