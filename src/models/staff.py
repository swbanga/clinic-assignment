"""Staff hierarchy, polymorphic fees, buffers and per-staff waiting lists."""

from __future__ import annotations

from abc import abstractmethod

from ..config import (
    DEFAULT_P,
    PHARMACIST_FEE,
    doctor_fee_for,
    nurse_fee_for,
    validate_p,
)
from ..exceptions import ConflictError
from .person import Person


class Staff(Person):
    """Abstract staff member.

    Invariants
    ----------
    S1. ``_p_value`` is a validated non-negative P frozen at construction.
    S2. ``_waiting_list`` contains unique patients (by id) in arrival order.
    S3. ``waiting_list`` always returns a defensive tuple.
    S4. ``fee()`` is abstract and polymorphic.
    """

    def __init__(
        self,
        name: object,
        id: object,
        p_value: object = None,
        **kwargs: object,
    ) -> None:
        self._p_value = validate_p(DEFAULT_P if p_value is None else p_value)
        self._waiting_list: list[Patient] = []
        super().__init__(name=name, id=id, **kwargs)

    @property
    def p_value(self) -> int:
        return self._p_value

    @abstractmethod
    def fee(self) -> float:
        """Return this staff member's consultation fee."""

    def buffer_hours(self) -> int:
        """Required free hours after an appointment; default is none."""

        return 0

    @property
    def waiting_list(self) -> tuple["Patient", ...]:
        """Defensive copy of the per-staff waiting queue."""

        return tuple(self._waiting_list)

    def _enqueue_waiting(self, patient: "Patient") -> None:
        for waiting in self._waiting_list:
            if waiting.id == patient.id:
                raise ConflictError(
                    f"patient #{patient.id} is already on the waiting list"
                )
        self._waiting_list.append(patient)

    def _dequeue_waiting(self, patient: "Patient") -> None:
        self._waiting_list = [
            waiting for waiting in self._waiting_list if waiting.id != patient.id
        ]


# Imported at the end to avoid a circular import during type-only use.
from .patient import Patient  # noqa: E402  (needed for the waiting-list type)


class Doctor(Staff):
    """Doctor: fee 40 + 5*(P mod 5), buffer 2 hours."""

    def __init__(
        self,
        name: object,
        id: object,
        p_value: object = None,
        **kwargs: object,
    ) -> None:
        super().__init__(name=name, id=id, p_value=p_value, **kwargs)

    def role(self) -> str:
        return "Doctor"

    def fee(self) -> float:
        return doctor_fee_for(self._p_value)

    def buffer_hours(self) -> int:
        return 2


class Nurse(Staff):
    """Nurse: fee 10 + (P mod 3), buffer 1 hour."""

    def role(self) -> str:
        return "Nurse"

    def fee(self) -> float:
        return nurse_fee_for(self._p_value)

    def buffer_hours(self) -> int:
        return 1


class Pharmacist(Staff):
    """Pharmacist: flat fee 5, no buffer."""

    def role(self) -> str:
        return "Pharmacist"

    def fee(self) -> float:
        return PHARMACIST_FEE
