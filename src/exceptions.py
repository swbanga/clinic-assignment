"""Domain exceptions used across the clinic system.

``ValidationError`` deliberately inherits from both ``ValueError`` and the
clinic root exception so callers can catch either the domain hierarchy or the
built-in type expected by the assignment (empty names, non-positive IDs and
invalid hours).
"""

from __future__ import annotations


class ClinicError(Exception):
    """Root of all expected clinic domain failures."""


class ValidationError(ClinicError, ValueError):
    """Invalid constructor or method argument."""


class ConflictError(ClinicError):
    """A booking, ID or scheduling conflict."""


class NotFoundError(ClinicError):
    """A requested entity does not exist in this clinic."""


class InvalidTransitionError(ClinicError):
    """An appointment status transition is not legal."""


class CancellationError(ClinicError):
    """The cancellation window or started-appointment rule was violated."""
