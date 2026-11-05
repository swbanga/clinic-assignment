"""Patient model and polymorphic billing categories (Twist 3)."""

from __future__ import annotations

from .person import Person


class Patient(Person):
    """A patient; the base category behaves like a visitor (pays 100%)."""

    def __init__(self, name: object, id: object, **kwargs: object) -> None:
        self._emergency = False
        super().__init__(name=name, id=id, **kwargs)

    def role(self) -> str:
        return "Patient"

    def discount_multiplier(self) -> float:
        """Fraction of the staff fee this patient pays.

        The name follows the assignment's wording; the value is the payable
        fraction, not the amount removed.  Student=0.5, staff-member=0.0,
        visitor=1.0.
        """

        return 1.0

    @property
    def billing_label(self) -> str:
        return "Visitor"

    @property
    def is_emergency(self) -> bool:
        return self._emergency

    def mark_emergency(self) -> "Patient":
        """Flag this patient as an emergency case."""

        self._emergency = True
        return self

    def clear_emergency(self) -> "Patient":
        """Remove the emergency flag."""

        self._emergency = False
        return self

    def __repr__(self) -> str:
        return f"Patient(#{self._id}, name={self._name!r}, billing={self.billing_label})"


class StudentPatient(Patient):
    """Student patients pay 50% of the staff fee."""

    def discount_multiplier(self) -> float:
        return 0.5

    @property
    def billing_label(self) -> str:
        return "Student"


class StaffMemberPatient(Patient):
    """Staff-member patients pay 0% of the staff fee."""

    def discount_multiplier(self) -> float:
        return 0.0

    @property
    def billing_label(self) -> str:
        return "Staff member"


class VisitorPatient(Patient):
    """Visitors pay the full staff fee."""

    def discount_multiplier(self) -> float:
        return 1.0

    @property
    def billing_label(self) -> str:
        return "Visitor"
