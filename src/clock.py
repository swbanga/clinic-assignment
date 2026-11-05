"""Deterministic simulated clock.

The wall clock is never read.  Every time query in the domain goes through an
injected ``Clock`` instance, which is what makes boundary tests instant and
repeatable (D2).
"""

from __future__ import annotations

from .config import MAX_HOUR, MIN_HOUR, require_int, validate_hour
from .exceptions import ValidationError


class Clock:
    """A one-way simulated clock over the inclusive range 0..168."""

    def __init__(self, start_hour: object = MIN_HOUR) -> None:
        self._now = validate_hour(start_hour, "start_hour", MIN_HOUR, MAX_HOUR)

    def now(self) -> int:
        """Return the current simulated hour."""

        return self._now

    def advance_to(self, hour: object) -> None:
        """Move forward to *hour*.

        Moving backwards is rejected: deterministic tests should create a fresh
        clock rather than rewind time.
        """

        target = validate_hour(hour, "hour", MIN_HOUR, MAX_HOUR)
        if target < self._now:
            raise ValidationError(
                f"clock cannot move backwards from {self._now} to {target}"
            )
        self._now = target

    def advance_by(self, hours: object) -> None:
        """Advance by a non-negative number of hours."""

        delta = require_int(hours, "hours")
        if delta < 0:
            raise ValidationError("hours to advance must be non-negative")
        self.advance_to(self._now + delta)

    def __repr__(self) -> str:
        return f"Clock(now={self._now})"
