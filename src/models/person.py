"""Abstract Person base for all people in the clinic."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..config import validate_name
from ..exceptions import ValidationError
from ..config import require_int


class Person(ABC):
    """A named, uniquely identified participant in the clinic.

    Class invariants
    ----------------
    P1. ``_id`` is a positive integer.
    P2. ``_name`` is a non-empty, whitespace-trimmed string.
    P3. ``role()`` is implemented by every concrete subclass.
    P4. ``Person.init_call_count`` increments once for every completed
        ``Person.__init__`` call; ``person_init_calls`` records the number of
        times this particular instance's Person initialiser ran.
    """

    # Class-level counter used by the Q5 / D4 proof.
    init_call_count = 0

    # Class default; each instance shadows it with its own value on first init.
    person_init_calls = 0

    def __init__(self, name: object, id: object, **kwargs: object) -> None:
        self._name = validate_name(name, "name")
        identifier = require_int(id, "id")
        if identifier <= 0:
            raise ValidationError("id must be a positive integer")
        self._id = identifier
        self.person_init_calls = self.person_init_calls + 1
        Person.init_call_count += 1
        # Continue the cooperative chain (normally to ABC/object).
        super().__init__(**kwargs)

    @property
    def name(self) -> str:
        return self._name

    @property
    def id(self) -> int:
        return self._id

    @abstractmethod
    def role(self) -> str:
        """Return this person's human-readable role."""

    def __str__(self) -> str:
        return f"{self.role()} {self._name} (#{self._id})"
