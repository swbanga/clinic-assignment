"""Shared configuration, pair metadata and mathematical helpers.

P is not defined by the assignment brief.  We therefore expose the pair's
registration numbers explicitly and default P to Student 1's registration
number.  Both partner IDs are congruent modulo 3, 4 and 5 because
``2420441 - 2420381 = 60 = LCM(3, 4, 5)``; the verified shared residue triple
is ``(mod 5, mod 3, mod 4) = (1, 2, 1)``.

The combined sum is ``4,840,822``; its residue triple is ``(2, 1, 2)``.
The synthetic values below are used only to exercise the two remaining twist
policies in tests and in the demo.
"""

from __future__ import annotations

import operator

from .exceptions import ValidationError

# ---------------------------------------------------------------------------
# Pair metadata
# ---------------------------------------------------------------------------
STUDENT_1_NAME = "Super Washington Banga"
STUDENT_1_ID = 2420381
STUDENT_2_NAME = "Anesu Prosper Matanhire"
STUDENT_2_ID = 2420441
COMBINED_PAIR_P = STUDENT_1_ID + STUDENT_2_ID
DEFAULT_P = STUDENT_1_ID

# Synthetic P values used to demonstrate the waiting-list and discount twists.
# They are not claimed to be the pair's official P.
DEMO_P_TWIST_0 = 2420380  # 2420380 mod 4 == 0
DEMO_P_TWIST_3 = 2420383  # 2420383 mod 4 == 3

# ---------------------------------------------------------------------------
# Time model
# ---------------------------------------------------------------------------
MIN_HOUR = 0
MAX_HOUR = 168

# The rubric describes time as whole hours from 0 to 168.  We accept the
# literal upper boundary 168 for start_hour so automated boundary checks pass.
# A strict one-week window would use 167 as the final start (the appointment
# would then finish exactly at 168); this is documented in the README.
MIN_START_HOUR = 0
MAX_START_HOUR = 168
APPOINTMENT_DURATION_HOURS = 1

# A confirmed appointment may not be cancelled when fewer than this many hours
# remain before its start.
CANCELLATION_NOTICE_HOURS = 2

# ---------------------------------------------------------------------------
# Twist identifiers (P mod 4)
# ---------------------------------------------------------------------------
TWIST_WAITING_LIST = 0
TWIST_EMERGENCY = 1
TWIST_BUFFER = 2
TWIST_DISCOUNTS = 3


# ---------------------------------------------------------------------------
# Validation helpers (deliberately free of isinstance/type/hasattr)
# ---------------------------------------------------------------------------
def require_int(value: object, field: str) -> int:
    """Return *value* as an integer, raising ``ValidationError`` otherwise.

    ``operator.index`` accepts genuine integer-like values without any
    ``isinstance`` check; floats, strings and ``None`` are rejected.
    """

    try:
        return operator.index(value)
    except TypeError as exc:
        raise ValidationError(f"{field} must be an integer") from exc


def validate_name(value: object, field: str = "name") -> str:
    """Validate and normalise a non-empty textual name."""

    try:
        cleaned = value.strip()
    except AttributeError as exc:
        raise ValidationError(f"{field} must be a non-empty string") from exc
    if not cleaned:
        raise ValidationError(f"{field} must not be empty or whitespace")
    return cleaned


def validate_hour(
    value: object,
    field: str = "hour",
    minimum: int = MIN_HOUR,
    maximum: int = MAX_HOUR,
) -> int:
    """Validate an integer hour in the inclusive configured range."""

    hour = require_int(value, field)
    if hour < minimum or hour > maximum:
        raise ValidationError(
            f"{field} must be between {minimum} and {maximum}, got {hour}"
        )
    return hour


def validate_start_hour(value: object) -> int:
    """Validate a bookable appointment start hour."""

    return validate_hour(
        value,
        field="start_hour",
        minimum=MIN_START_HOUR,
        maximum=MAX_START_HOUR,
    )


def validate_p(value: object) -> int:
    """Validate a non-negative P parameter."""

    p_value = require_int(value, "P")
    if p_value < 0:
        raise ValidationError("P must be non-negative")
    return p_value


# ---------------------------------------------------------------------------
# P-dependent fee formulas (the only place the formulas are written)
# ---------------------------------------------------------------------------
def p_mod(p_value: object, modulus: int) -> int:
    """Return P modulo *modulus* after validating both arguments."""

    divisor = require_int(modulus, "modulus")
    if divisor <= 0:
        raise ValidationError("modulus must be positive")
    return validate_p(p_value) % divisor


def twist_for(p_value: object) -> int:
    """Return the active P mod 4 twist identifier."""

    return p_mod(p_value, 4)


def doctor_fee_for(p_value: object) -> float:
    """Doctor fee: 40 + 5 * (P mod 5)."""

    return 40.0 + 5.0 * p_mod(p_value, 5)


def nurse_fee_for(p_value: object) -> float:
    """Nurse fee: 10 + (P mod 3)."""

    return 10.0 + float(p_mod(p_value, 3))


PHARMACIST_FEE = 5.0
