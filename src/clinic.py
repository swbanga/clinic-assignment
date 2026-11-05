"""Clinic aggregate root: IDs, scheduling rules and transactional logging."""

from __future__ import annotations

from .clock import Clock
from .config import (
    APPOINTMENT_DURATION_HOURS,
    DEFAULT_P,
    validate_p,
    validate_start_hour,
    require_int,
)
from .exceptions import (
    CancellationError,
    ClinicError,
    ConflictError,
    NotFoundError,
)
from .logger import AppointmentLogger
from .models.appointment import Appointment, AppointmentStatus
from .models.patient import Patient
from .models.staff import Staff
from .policies import TwistPolicy, policy_for


# INVARIANTS (Clinic):
# C1. _used_ids is the single ID namespace for registered persons and
#     appointments; no id can appear twice.
# C2. Every appointment references the exact registered Patient and Staff
#     objects (not merely objects with the same id).
# C3. No staff member has two non-cancelled appointments at the same hour.
# C4. No patient has two non-cancelled appointments at the same hour.
# C5. A CONFIRMED appointment is never bumped by an emergency booking.
# C6. When the active twist requires staff buffers, every pair of active
#     appointments for that staff member has at least
#     1 + staff.buffer_hours() hours between starts.
# C7. Each staff waiting list contains unique registered patients in arrival
#     order; an offered patient is removed only after a new PENDING appointment
#     has been created.
# C8. Every public mutation opens exactly one logger session; failures are
#     recorded before the exception is re-raised.
# C9. The active P mod 4 policy is chosen once at construction and never
#     mutated.
class Clinic:
    """Aggregate root for patients, staff, appointments and waiting lists."""

    def __init__(
        self,
        clock: Clock,
        p_value: object = None,
        logger: AppointmentLogger | None = None,
    ) -> None:
        self._clock = clock
        self._p_value = validate_p(DEFAULT_P if p_value is None else p_value)
        self._policy = policy_for(self._p_value)
        self._logger = AppointmentLogger() if logger is None else logger

        self._persons: dict[int, object] = {}
        self._patients: dict[int, Patient] = {}
        self._staff_members: dict[int, Staff] = {}
        self._appointments: dict[int, Appointment] = {}
        self._used_ids: set[int] = set()

    # ------------------------------------------------------------------
    # Read-only views and metadata
    # ------------------------------------------------------------------
    @property
    def p_value(self) -> int:
        return self._p_value

    @property
    def p_mod_4(self) -> int:
        return self._p_value % 4

    @property
    def twist_name(self) -> str:
        return self._policy.name

    @property
    def policy(self) -> TwistPolicy:
        return self._policy

    @property
    def staff(self) -> tuple[Staff, ...]:
        return tuple(self._staff_members.values())

    @property
    def patients(self) -> tuple[Patient, ...]:
        return tuple(self._patients.values())

    @property
    def appointments(self) -> tuple[Appointment, ...]:
        return tuple(self._appointments.values())

    def waiting_list_for(self, staff: Staff) -> tuple[Patient, ...]:
        return staff.waiting_list

    def get_appointment(self, appointment_id: object) -> Appointment:
        identifier = require_int(appointment_id, "appointment id")
        appointment = self._appointments.get(identifier)
        if appointment is None:
            raise NotFoundError(f"appointment #{identifier} not found")
        return appointment

    def get_patient(self, patient_id: object) -> Patient:
        identifier = require_int(patient_id, "patient id")
        patient = self._patients.get(identifier)
        if patient is None:
            raise NotFoundError(f"patient #{identifier} not found")
        return patient

    def get_staff(self, staff_id: object) -> Staff:
        identifier = require_int(staff_id, "staff id")
        staff = self._staff_members.get(identifier)
        if staff is None:
            raise NotFoundError(f"staff #{identifier} not found")
        return staff

    def quote(self, staff: Staff, patient: Patient) -> float:
        """Price for a staff/patient pair under the active twist policy."""

        return float(staff.fee() * self._policy.price_multiplier(patient))

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def add_patient(self, patient: Patient) -> Patient:
        with self._logger.session() as log:
            try:
                self._register_person(patient, self._patients)
                log.write(
                    f"[log] registered patient #{patient.id} {patient.name} "
                    f"({patient.billing_label})"
                )
                return patient
            except ClinicError as exc:
                log.write(f"FAILED register: {exc}")
                raise

    def add_staff(self, staff: Staff) -> Staff:
        with self._logger.session() as log:
            try:
                self._register_person(staff, self._staff_members)
                log.write(
                    f"[log] registered staff #{staff.id} {staff.name} "
                    f"({staff.role()})"
                )
                return staff
            except ClinicError as exc:
                log.write(f"FAILED register: {exc}")
                raise

    def _register_person(self, person: object, collection: dict) -> None:
        identifier = person.id
        if identifier in self._used_ids:
            raise ConflictError(f"duplicate id {identifier}")
        self._persons[identifier] = person
        collection[identifier] = person
        self._used_ids.add(identifier)

    # ------------------------------------------------------------------
    # Booking
    # ------------------------------------------------------------------
    def book_appointment(
        self,
        patient: Patient,
        staff: Staff,
        start_hour: object,
        appointment_id: object = None,
        emergency: bool = False,
    ) -> Appointment:
        with self._logger.session() as log:
            try:
                registered_patient = self._require_patient(patient)
                registered_staff = self._require_staff(staff)
                hour = validate_start_hour(start_hour)
                identifier = self._resolve_appointment_id(appointment_id)
                effective_emergency = bool(emergency) or registered_patient.is_emergency

                patient_conflict = self._find_patient_conflict(
                    registered_patient.id, hour
                )
                if patient_conflict is not None:
                    raise ConflictError(f"patient conflict at hour {hour}")

                staff_conflict = self._find_staff_conflict(registered_staff.id, hour)
                if staff_conflict is not None:
                    if (
                        effective_emergency
                        and self._policy.emergency_bump_enabled()
                    ):
                        if staff_conflict.status is AppointmentStatus.CONFIRMED:
                            raise ConflictError(
                                f"cannot bump confirmed #{staff_conflict.id} "
                                f"at hour {hour}"
                            )
                        try:
                            staff_conflict.cancel(self._clock.now(), "bumped")
                        except CancellationError as exc:
                            raise ConflictError(
                                f"cannot bump #{staff_conflict.id}: {exc}"
                            ) from exc
                        log.write(
                            f"[log] bumped #{staff_conflict.id} by emergency "
                            f"booking at hour {hour} (reason=bumped)"
                        )
                    else:
                        raise ConflictError(f"staff conflict at hour {hour}")

                buffer_conflict = self._find_buffer_conflict(registered_staff, hour)
                if buffer_conflict is not None:
                    required_gap = self._policy.buffer_for(registered_staff)
                    raise ConflictError(
                        f"staff buffer conflict at hour {hour} "
                        f"(requires {required_gap}-hour gap after "
                        f"#{buffer_conflict.id})"
                    )

                appointment = Appointment(
                    identifier,
                    registered_patient,
                    registered_staff,
                    hour,
                )
                self._appointments[identifier] = appointment
                self._used_ids.add(identifier)
                log.write(
                    f"[log] booked #{identifier} patient=#{registered_patient.id} "
                    f"staff=#{registered_staff.id} hour={hour} "
                    f"price={self.quote(registered_staff, registered_patient):.2f}"
                )
                return appointment
            except ClinicError as exc:
                log.write(f"FAILED book: {exc}")
                raise

    def _resolve_appointment_id(self, appointment_id: object) -> int:
        if appointment_id is None:
            return self._next_appointment_id()
        identifier = require_int(appointment_id, "appointment id")
        if identifier <= 0:
            raise ConflictError("appointment id must be a positive integer")
        if identifier in self._used_ids:
            raise ConflictError(f"duplicate id {identifier}")
        return identifier

    def _next_appointment_id(self) -> int:
        identifier = 1
        while identifier in self._used_ids:
            identifier += 1
        return identifier

    def _require_patient(self, patient: object) -> Patient:
        try:
            identifier = patient.id
        except AttributeError as exc:
            raise ConflictError("patient is not registered") from exc
        registered = self._patients.get(identifier)
        if registered is not patient:
            raise ConflictError(f"patient #{identifier} is not registered")
        return registered

    def _require_staff(self, staff: object) -> Staff:
        try:
            identifier = staff.id
        except AttributeError as exc:
            raise ConflictError("staff member is not registered") from exc
        registered = self._staff_members.get(identifier)
        if registered is not staff:
            raise ConflictError(f"staff #{identifier} is not registered")
        return registered

    def _find_patient_conflict(self, patient_id: int, hour: int) -> Appointment | None:
        for appointment in self._appointments.values():
            if (
                appointment.is_active
                and appointment.start_hour == hour
                and appointment.patient.id == patient_id
            ):
                return appointment
        return None

    def _find_staff_conflict(self, staff_id: int, hour: int) -> Appointment | None:
        for appointment in self._appointments.values():
            if (
                appointment.is_active
                and appointment.start_hour == hour
                and appointment.staff.id == staff_id
            ):
                return appointment
        return None

    @staticmethod
    def _free_gap_hours(existing_hour: int, new_hour: int) -> int:
        """Free hours between two one-hour appointments.

        If the earlier appointment starts at ``h`` it occupies ``[h, h+1)``.
        The gap to the later start is therefore ``later - (earlier + 1)``.
        Equality with the staff buffer is allowed.
        """

        if existing_hour < new_hour:
            return new_hour - (existing_hour + APPOINTMENT_DURATION_HOURS)
        return existing_hour - (new_hour + APPOINTMENT_DURATION_HOURS)

    def _find_buffer_conflict(self, staff: Staff, hour: int) -> Appointment | None:
        required_gap = self._policy.buffer_for(staff)
        if required_gap <= 0:
            return None
        for appointment in self._appointments.values():
            if not appointment.is_active or appointment.staff.id != staff.id:
                continue
            if self._free_gap_hours(appointment.start_hour, hour) < required_gap:
                return appointment
        return None

    # ------------------------------------------------------------------
    # Confirmation and cancellation
    # ------------------------------------------------------------------
    def confirm_appointment(self, appointment_id: object) -> Appointment:
        with self._logger.session() as log:
            try:
                appointment = self.get_appointment(appointment_id)
                appointment.confirm()
                log.write(f"[log] confirmed #{appointment.id}")
                return appointment
            except ClinicError as exc:
                log.write(f"FAILED confirm #{appointment_id}: {exc}")
                raise

    def cancel_appointment(
        self,
        appointment_id: object,
        reason: object = "patient request",
    ) -> Appointment:
        with self._logger.session() as log:
            try:
                appointment = self.get_appointment(appointment_id)
                appointment.cancel(self._clock.now(), reason)
                log.write(
                    f"[log] cancelled #{appointment.id} "
                    f"reason={appointment.cancellation_reason}"
                )
                if self._policy.waiting_list_offers_enabled():
                    try:
                        self._offer_waiting_list(appointment, log)
                    except ClinicError as exc:
                        # Cancellation already succeeded; a failed offer must
                        # not turn the completed cancellation into a failure.
                        log.write(f"FAILED waiting list offer: {exc}")
                return appointment
            except ClinicError as exc:
                log.write(f"FAILED cancel #{appointment_id}: {exc}")
                raise

    # ------------------------------------------------------------------
    # Waiting list (Twist 0)
    # ------------------------------------------------------------------
    def join_waiting_list(self, patient: Patient, staff: Staff) -> Patient:
        with self._logger.session() as log:
            try:
                registered_patient = self._require_patient(patient)
                registered_staff = self._require_staff(staff)
                registered_staff._enqueue_waiting(registered_patient)
                log.write(
                    f"[log] waitlisted patient=#{registered_patient.id} "
                    f"staff=#{registered_staff.id}"
                )
                return registered_patient
            except ClinicError as exc:
                log.write(f"FAILED waitlist: {exc}")
                raise

    def _offer_waiting_list(self, cancelled: Appointment, log) -> Appointment | None:
        staff = cancelled.staff
        hour = cancelled.start_hour
        queued = staff.waiting_list
        if not queued:
            return None

        for candidate in queued:
            if candidate.id == cancelled.patient.id:
                # Do not offer patients their own just-cancelled slot.
                continue
            if self._patients.get(candidate.id) is not candidate:
                continue
            if self._find_patient_conflict(candidate.id, hour) is not None:
                continue
            if self._find_staff_conflict(staff.id, hour) is not None:
                continue
            if self._find_buffer_conflict(staff, hour) is not None:
                continue

            identifier = self._next_appointment_id()
            offered = Appointment(identifier, candidate, staff, hour)
            self._appointments[identifier] = offered
            self._used_ids.add(identifier)
            staff._dequeue_waiting(candidate)
            log.write(
                f"[log] waitlist offered #{identifier} to patient=#{candidate.id} "
                f"for staff=#{staff.id} at hour={hour} (PENDING)"
            )
            return offered

        log.write(
            f"[log] waitlist: no eligible patient for staff=#{staff.id} "
            f"at hour={hour}"
        )
        return None
