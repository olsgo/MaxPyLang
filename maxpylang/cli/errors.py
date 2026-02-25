"""CLI error hierarchy with stable exit-code mapping."""

from __future__ import annotations

from typing import Optional


class MaxPyCLIError(Exception):
    """Base error for expected CLI failures."""

    exit_code = 5

    def __init__(self, message: str, *, details: Optional[dict] = None):
        super().__init__(message)
        self.details = details or {}


class UsageError(MaxPyCLIError):
    exit_code = 2


class ObjectResolutionError(MaxPyCLIError):
    exit_code = 3


class ValidationError(MaxPyCLIError):
    exit_code = 4


class InternalError(MaxPyCLIError):
    exit_code = 5
