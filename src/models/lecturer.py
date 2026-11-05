"""Multiple inheritance: Lecturer and MedicalLecturer (Q5 / D4)."""

from __future__ import annotations

from ..config import validate_name
from .person import Person
from .staff import Doctor


class Lecturer(Person):
    """A lecturer with a module name; not a clinical staff member."""

    def __init__(
        self,
        name: object,
        id: object,
        module_name: object,
        **kwargs: object,
    ) -> None:
        self._module_name = validate_name(module_name, "module_name")
        super().__init__(name=name, id=id, **kwargs)

    @property
    def module_name(self) -> str:
        return self._module_name

    def role(self) -> str:
        return "Lecturer"


class MedicalLecturer(Doctor, Lecturer):
    """A clinician who also lectures.

    MRO: MedicalLecturer -> Doctor -> Staff -> Lecturer -> Person -> ABC.
    The cooperative ``super()`` chain consumes each class's arguments and calls
    Person.__init__ exactly once.
    """

    def __init__(
        self,
        name: object,
        id: object,
        module_name: object,
        p_value: object = None,
        **kwargs: object,
    ) -> None:
        super().__init__(
            name=name,
            id=id,
            module_name=module_name,
            p_value=p_value,
            **kwargs,
        )

    def role(self) -> str:
        return "Doctor and Lecturer"

    # fee() is intentionally inherited from Doctor: a clinical appointment is
    # charged at the medical consultation rate.  MRO resolves Doctor.fee before
    # any Lecturer fee (Lecturer has none).
