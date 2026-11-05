"""P mod 4 twist policies.

Each policy is a small strategy object.  The Clinic asks the policy whether a
capability is enabled and, when it is, delegates to the domain object:

* buffer policy asks ``staff.buffer_hours()``;
* discount policy asks ``patient.discount_multiplier()``.

No policy inspects an object's type or role string.  Outside its active twist a
capability is dormant, which lets one Clinic implementation exercise all four
twists without cross-feature interference.
"""

from __future__ import annotations

from abc import ABC

from .config import (
    TWIST_BUFFER,
    TWIST_DISCOUNTS,
    TWIST_EMERGENCY,
    TWIST_WAITING_LIST,
    twist_for,
)


class TwistPolicy(ABC):
    """Default dormant capabilities for a twist."""

    code: int
    name: str

    def buffer_for(self, staff: object) -> int:
        """Return the required free gap after an appointment, if any."""

        return 0

    def price_multiplier(self, patient: object) -> float:
        """Return the fraction of the staff fee payable by the patient."""

        return 1.0

    def emergency_bump_enabled(self) -> bool:
        return False

    def waiting_list_offers_enabled(self) -> bool:
        return False

    def __repr__(self) -> str:
        return f"TwistPolicy(code={self.code}, name={self.name!r})"


class WaitingListPolicy(TwistPolicy):
    """Twist 0: cancellations automatically offer the slot to the queue."""

    code = TWIST_WAITING_LIST
    name = "Waiting list"

    def waiting_list_offers_enabled(self) -> bool:
        return True


class EmergencyBumpPolicy(TwistPolicy):
    """Twist 1: an emergency booking may bump a PENDING appointment."""

    code = TWIST_EMERGENCY
    name = "Emergency bump"

    def emergency_bump_enabled(self) -> bool:
        return True


class BufferPolicy(TwistPolicy):
    """Twist 2: staff declare their own required gap between appointments."""

    code = TWIST_BUFFER
    name = "Staff buffer"

    def buffer_for(self, staff: object) -> int:
        return staff.buffer_hours()  # polymorphic; never a type check


class DiscountPolicy(TwistPolicy):
    """Twist 3: the patient declares the fraction of the fee they pay."""

    code = TWIST_DISCOUNTS
    name = "Patient discounts"

    def price_multiplier(self, patient: object) -> float:
        return patient.discount_multiplier()  # polymorphic; never a type check


_POLICY_BY_TWIST = {
    TWIST_WAITING_LIST: WaitingListPolicy,
    TWIST_EMERGENCY: EmergencyBumpPolicy,
    TWIST_BUFFER: BufferPolicy,
    TWIST_DISCOUNTS: DiscountPolicy,
}


def policy_for(p_value: object) -> TwistPolicy:
    """Instantiate the policy selected by ``P mod 4``."""

    return _POLICY_BY_TWIST[twist_for(p_value)]()
