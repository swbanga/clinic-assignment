"""Appointment state machine and invariants (Q2 / D1)."""

from __future__ import annotations

from enum import Enum

from ..config import (
    CANCELLATION_NOTICE_HOURS,
    require_int,
    validate_hour,
    validate_name,
    validate_start_hour,
)
from ..exceptions import (
    CancellationError,
    InvalidTransitionError,
    ValidationError,
)


class AppointmentStatus(Enum):
    """The only statuses an appointment may hold."""

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


# INVARIANTS (Appointment):
# A1. _id is a positive integer.
# A2. 0 <= _start_hour <= MAX_START_HOUR (the literal rubric boundary is 168).
# A3. _status is exactly one of PENDING, CONFIRMED or CANCELLED.
# A4. CANCELLED is terminal: no transition out of it is ever permitted.
# A5. The only legal transitions are PENDING->CONFIRMED, PENDING->CANCELLED and
#     CONFIRMED->CANCELLED.
# A6. A CONFIRMED appointment cannot be cancelled when
#     _start_hour - current_hour < CANCELLATION_NOTICE_HOURS.
# A7. No appointment (PENDING or CONFIRMED) can be cancelled when
#     current_hour >= _start_hour.
# A8. _cancellation_reason is set if and only if the status is CANCELLED.
# A9. _patient and _staff are stable references; the appointment never replaces
#     its participants.  Clinic registration/conflict rules are enforced by the
#     aggregate root, not by mutating these references.
class Appointment:
    """A one-hour appointment identified by a clinic-unique id."""

    def __init__(
        self,
        id: object,
        patient: object,
        staff: object,
        start_hour: object,
    ) -> None:
        identifier = require_int(id, "appointment id")
        if identifier <= 0:
            raise ValidationError("appointment id must be a positive integer")
        if patient is None or staff is None:
            raise ValidationError("appointment requires a patient and a staff member")
        self._id = identifier
        self._patient = patient
        self._staff = staff
        self._start_hour = validate_start_hour(start_hour)
        self._status = AppointmentStatus.PENDING
        self._cancellation_reason: str | None = None

    @property
    def id(self) -> int:
        return self._id

    @property
    def patient(self) -> object:
        return self._patient

    @property
    def staff(self) -> object:
        return self._staff

    @property
    def start_hour(self) -> int:
        return self._start_hour

    @property
    def end_hour(self) -> int:
        """Derived end label; may be 169 at the literal start-hour boundary."""

        return self._start_hour + 1

    @property
    def status(self) -> AppointmentStatus:
        return self._status

    @property
    def cancellation_reason(self) -> str | None:
        return self._cancellation_reason

    @property
    def is_active(self) -> bool:
        return self._status is not AppointmentStatus.CANCELLED

    def confirm(self) -> None:
        """Move PENDING -> CONFIRMED; reject every other source status."""

        if self._status is AppointmentStatus.CANCELLED:
            raise InvalidTransitionError("cancelled appointment is terminal")
        if self._status is AppointmentStatus.CONFIRMED:
            raise InvalidTransitionError("appointment is already confirmed")
        self._status = AppointmentStatus.CONFIRMED

    def cancel(self, current_hour: object, reason: object = "patient request") -> None:
        """Move PENDING/CONFIRMED -> CANCELLED, enforcing all timing rules."""

        now = validate_hour(current_hour, "current_hour")
        cleaned_reason = validate_name(reason, "cancellation reason")

        if self._status is AppointmentStatus.CANCELLED:
            raise InvalidTransitionError("already cancelled")
        if now >= self._start_hour:
            raise CancellationError("too late")
        if (
            self._status is AppointmentStatus.CONFIRMED
            and self._start_hour - now < CANCELLATION_NOTICE_HOURS
        ):
            raise CancellationError("too late")

        self._status = AppointmentStatus.CANCELLED
        self._cancellation_reason = cleaned_reason

    def __repr__(self) -> str:
        return (
            f"Appointment(#{self._id}, hour={self._start_hour}, "
            f"status={self._status.value})"
        )
