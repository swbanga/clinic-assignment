"""Comprehensive tests for the UZ clinic appointment system.

The suite is written with the standard-library ``unittest`` framework, so both
``python -m unittest discover -s tests -v`` and ``pytest`` work without any
runtime dependency.
"""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest

from src.clinic import Clinic
from src.clock import Clock
from src.config import (
    COMBINED_PAIR_P,
    DEFAULT_P,
    DEMO_P_TWIST_0,
    DEMO_P_TWIST_3,
    STUDENT_1_ID,
    STUDENT_2_ID,
    doctor_fee_for,
    nurse_fee_for,
)
from src.exceptions import (
    CancellationError,
    ClinicError,
    ConflictError,
    InvalidTransitionError,
    NotFoundError,
    ValidationError,
)
from src.logger import AppointmentLogger
from src.models import (
    Appointment,
    AppointmentStatus,
    Doctor,
    Lecturer,
    MedicalLecturer,
    Nurse,
    Patient,
    Pharmacist,
    Person,
    StaffMemberPatient,
    StudentPatient,
    VisitorPatient,
)
from src.models.staff import Staff
from src.policies import (
    BufferPolicy,
    DiscountPolicy,
    EmergencyBumpPolicy,
    WaitingListPolicy,
    policy_for,
)


def make_clinic(p_value=DEFAULT_P):
    """Return a clinic, its injected clock and captured log lines."""

    clock = Clock()
    lines = []
    clinic = Clinic(
        clock,
        p_value=p_value,
        logger=AppointmentLogger(sink=lines.append),
    )
    return clinic, clock, lines


def add_doctor_patient(
    clinic,
    staff_id=5001,
    patient_id=6001,
    staff_name="Dr Test",
    patient_name="Pat Test",
    p_value=None,
):
    """Register one doctor and one patient with unique ids."""

    doctor = Doctor(
        staff_name,
        staff_id,
        p_value=clinic.p_value if p_value is None else p_value,
    )
    patient = Patient(patient_name, patient_id)
    clinic.add_staff(doctor)
    clinic.add_patient(patient)
    return doctor, patient


class ClockTests(unittest.TestCase):
    def test_initial_time_and_advance(self):
        clock = Clock()
        self.assertEqual(clock.now(), 0)
        clock.advance_to(10)
        self.assertEqual(clock.now(), 10)
        self.assertEqual(clock.now(), 10)

    def test_clock_boundaries(self):
        self.assertEqual(Clock(0).now(), 0)
        self.assertEqual(Clock(168).now(), 168)
        clock = Clock()
        clock.advance_to(168)
        self.assertEqual(clock.now(), 168)

    def test_clock_rejects_invalid_initial_time(self):
        for value in (-1, 169, 1.5, "10", None):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    Clock(value)

    def test_clock_rejects_backwards_and_out_of_range(self):
        clock = Clock(10)
        with self.assertRaises(ValidationError):
            clock.advance_to(9)
        with self.assertRaises(ValidationError):
            clock.advance_to(-1)
        with self.assertRaises(ValidationError):
            clock.advance_to(169)
        self.assertEqual(clock.now(), 10)

    def test_advance_by(self):
        clock = Clock()
        clock.advance_by(5)
        self.assertEqual(clock.now(), 5)
        with self.assertRaises(ValidationError):
            clock.advance_by(-1)
        with self.assertRaises(ValidationError):
            clock.advance_by(200)


class ValidationTests(unittest.TestCase):
    def test_names_are_trimmed_and_empty_names_rejected(self):
        patient = Patient("  Alice  ", 1001)
        self.assertEqual(patient.name, "Alice")
        for name in ("", "   ", None):
            with self.subTest(name=name):
                with self.assertRaises(ValidationError):
                    Patient(name, 1002)

    def test_ids_must_be_positive_integers(self):
        for identifier in (0, -1, -99, 1.5, "1", None):
            with self.subTest(identifier=identifier):
                with self.assertRaises(ValidationError):
                    Patient("Alice", identifier)

    def test_staff_ids_use_the_same_validation(self):
        with self.assertRaises(ValidationError):
            Doctor("Dr A", 0)
        with self.assertRaises(ValidationError):
            Nurse("Nurse A", -1)
        with self.assertRaises(ValidationError):
            Pharmacist("Pharm A", "bad")

    def test_appointment_validation(self):
        patient = Patient("Alice", 1001)
        doctor = Doctor("Dr A", 2001)
        with self.assertRaises(ValidationError):
            Appointment(0, patient, doctor, 10)
        with self.assertRaises(ValidationError):
            Appointment(1, None, doctor, 10)
        with self.assertRaises(ValidationError):
            Appointment(1, patient, None, 10)
        with self.assertRaises(ValidationError):
            Appointment(1, patient, doctor, -1)
        with self.assertRaises(ValidationError):
            Appointment(1, patient, doctor, 169)
        with self.assertRaises(ValidationError):
            Appointment(1, patient, doctor, 1.5)

    def test_literal_upper_start_hour_is_accepted(self):
        appointment = Appointment(1, Patient("Alice", 1001), Doctor("Dr A", 2001), 168)
        self.assertEqual(appointment.start_hour, 168)
        self.assertEqual(appointment.end_hour, 169)

    def test_module_name_validation(self):
        with self.assertRaises(ValidationError):
            Lecturer("Lecturer", 1001, "")
        with self.assertRaises(ValidationError):
            MedicalLecturer("Lecturer", 1001, "   ")

    def test_clinic_p_validation(self):
        with self.assertRaises(ValidationError):
            Clinic(Clock(), p_value=-1)
        with self.assertRaises(ValidationError):
            Clinic(Clock(), p_value=1.5)

    def test_validation_error_is_also_value_error(self):
        with self.assertRaises(ValueError):
            Patient("", 1)


class FeeAndPolicyTests(unittest.TestCase):
    def test_partner_fee_values(self):
        for p_value in (STUDENT_1_ID, STUDENT_2_ID):
            with self.subTest(p_value=p_value):
                self.assertEqual(doctor_fee_for(p_value), 45.0)
                self.assertEqual(nurse_fee_for(p_value), 12.0)
                self.assertEqual(Pharmacist("P", 1, p_value=p_value).fee(), 5.0)

    def test_combined_fee_values(self):
        self.assertEqual(doctor_fee_for(COMBINED_PAIR_P), 50.0)
        self.assertEqual(nurse_fee_for(COMBINED_PAIR_P), 11.0)

    def test_synthetic_fee_values(self):
        self.assertEqual(doctor_fee_for(DEMO_P_TWIST_0), 40.0)
        self.assertEqual(nurse_fee_for(DEMO_P_TWIST_0), 11.0)
        self.assertEqual(doctor_fee_for(DEMO_P_TWIST_3), 55.0)
        self.assertEqual(nurse_fee_for(DEMO_P_TWIST_3), 11.0)

    def test_single_polymorphic_loop(self):
        clinic, _, _ = make_clinic()
        clinic.add_staff(Doctor("Dr A", 5001))
        clinic.add_staff(Nurse("Nurse A", 5002))
        clinic.add_staff(Pharmacist("Pharm A", 5003))
        observed = [(member.role(), member.fee()) for member in clinic.staff]
        self.assertEqual(
            observed,
            [("Doctor", 45.0), ("Nurse", 12.0), ("Pharmacist", 5.0)],
        )

    def test_custom_staff_subclass_needs_no_clinic_or_loop_change(self):
        class Radiologist(Staff):
            def role(self):
                return "Radiologist"

            def fee(self):
                return 70.0

            def buffer_hours(self):
                return 3

        clinic, _, _ = make_clinic()
        clinic.add_staff(Radiologist("Radiologist A", 5101))
        clinic.add_staff(Doctor("Dr A", 5001))
        observed = [(member.role(), member.fee()) for member in clinic.staff]
        self.assertEqual(
            observed,
            [("Radiologist", 70.0), ("Doctor", 45.0)],
        )
        self.assertEqual(clinic.staff[0].buffer_hours(), 3)

    def test_policy_mapping(self):
        cases = {
            STUDENT_1_ID: ("Emergency bump", 1),
            STUDENT_2_ID: ("Emergency bump", 1),
            COMBINED_PAIR_P: ("Staff buffer", 2),
            DEMO_P_TWIST_0: ("Waiting list", 0),
            DEMO_P_TWIST_3: ("Patient discounts", 3),
        }
        for p_value, expected in cases.items():
            with self.subTest(p_value=p_value):
                clinic, _, _ = make_clinic(p_value)
                self.assertEqual(clinic.p_mod_4, expected[1])
                self.assertEqual(clinic.twist_name, expected[0])

    def test_policy_capabilities_are_polymorphic(self):
        doctor = Doctor("Dr A", 5001)
        student = StudentPatient("Student", 6001)
        self.assertEqual(BufferPolicy().buffer_for(doctor), 2)
        self.assertEqual(DiscountPolicy().price_multiplier(student), 0.5)
        self.assertTrue(EmergencyBumpPolicy().emergency_bump_enabled())
        self.assertTrue(WaitingListPolicy().waiting_list_offers_enabled())
        self.assertFalse(WaitingListPolicy().emergency_bump_enabled())

    def test_policy_for_returns_expected_policy(self):
        self.assertEqual(policy_for(STUDENT_1_ID).code, 1)
        self.assertEqual(policy_for(STUDENT_1_ID).name, "Emergency bump")
        self.assertEqual(policy_for(COMBINED_PAIR_P).code, 2)
        self.assertEqual(policy_for(COMBINED_PAIR_P).name, "Staff buffer")
        self.assertEqual(policy_for(DEMO_P_TWIST_0).code, 0)
        self.assertEqual(policy_for(DEMO_P_TWIST_0).name, "Waiting list")
        self.assertEqual(policy_for(DEMO_P_TWIST_3).code, 3)
        self.assertEqual(policy_for(DEMO_P_TWIST_3).name, "Patient discounts")


class DefensiveCopyTests(unittest.TestCase):
    def test_clinic_collections_are_tuples(self):
        clinic, _, _ = make_clinic()
        doctor, patient = add_doctor_patient(clinic)
        clinic.book_appointment(patient, doctor, 10, 1)

        for collection in (
            clinic.appointments,
            clinic.staff,
            clinic.patients,
        ):
            with self.assertRaises(AttributeError):
                collection.append(None)
        self.assertEqual(len(clinic.appointments), 1)
        self.assertEqual(len(clinic.staff), 1)
        self.assertEqual(len(clinic.patients), 1)

    def test_waiting_list_is_a_defensive_tuple(self):
        clinic, _, _ = make_clinic(DEMO_P_TWIST_0)
        doctor, patient = add_doctor_patient(clinic)
        clinic.join_waiting_list(patient, doctor)
        waiting = clinic.waiting_list_for(doctor)
        with self.assertRaises(AttributeError):
            waiting.append(None)
        self.assertEqual(len(doctor.waiting_list), 1)

    def test_logger_entries_are_a_defensive_tuple(self):
        logger = AppointmentLogger(sink=lambda _message: None)
        with logger.session() as log:
            log.write("event")
        entries = logger.entries
        with self.assertRaises(AttributeError):
            entries.append("bad")
        self.assertEqual(len(logger.entries), 3)


class StateMachineTests(unittest.TestCase):
    def _confirmed_case(self, hour=10):
        clinic, clock, lines = make_clinic()
        doctor, patient = add_doctor_patient(clinic)
        clinic.book_appointment(patient, doctor, hour, 1)
        clinic.confirm_appointment(1)
        lines.clear()
        return clinic, clock, lines, doctor, patient

    def test_pending_to_confirmed(self):
        clinic, clock, lines = make_clinic()
        doctor, patient = add_doctor_patient(clinic)
        appointment = clinic.book_appointment(patient, doctor, 10, 1)
        self.assertIs(appointment.status, AppointmentStatus.PENDING)
        clinic.confirm_appointment(1)
        self.assertIs(appointment.status, AppointmentStatus.CONFIRMED)

    def test_pending_to_cancelled(self):
        clinic, _, lines = make_clinic()
        doctor, patient = add_doctor_patient(clinic)
        appointment = clinic.book_appointment(patient, doctor, 10, 1)
        lines.clear()
        clinic.cancel_appointment(1)
        self.assertIs(appointment.status, AppointmentStatus.CANCELLED)
        self.assertEqual(appointment.cancellation_reason, "patient request")
        self.assertEqual(lines.count("[log] opened"), 1)
        self.assertEqual(lines.count("[log] closed"), 1)

    def test_confirmed_to_cancelled_with_two_hours_notice(self):
        clinic, clock, lines, doctor, patient = self._confirmed_case(10)
        clock.advance_to(8)  # exactly two hours before start
        clinic.cancel_appointment(1)
        self.assertEqual(clinic.get_appointment(1).status, AppointmentStatus.CANCELLED)

    def test_confirmed_cannot_be_cancelled_one_hour_before(self):
        clinic, clock, lines, doctor, patient = self._confirmed_case(10)
        clock.advance_to(9)
        with self.assertRaises(CancellationError):
            clinic.cancel_appointment(1)
        self.assertEqual(clinic.get_appointment(1).status, AppointmentStatus.CONFIRMED)
        self.assertIn("FAILED cancel #1: too late", lines)

    def test_pending_can_be_cancelled_one_hour_before(self):
        clinic, clock, lines = make_clinic()
        doctor, patient = add_doctor_patient(clinic)
        clinic.book_appointment(patient, doctor, 10, 1)
        clock.advance_to(9)
        clinic.cancel_appointment(1)
        self.assertEqual(clinic.get_appointment(1).status, AppointmentStatus.CANCELLED)

    def test_no_appointment_can_be_cancelled_once_started(self):
        clinic, clock, lines = make_clinic()
        doctor, patient = add_doctor_patient(clinic)
        clinic.book_appointment(patient, doctor, 10, 1)
        clock.advance_to(10)
        with self.assertRaises(CancellationError):
            clinic.cancel_appointment(1)
        self.assertEqual(clinic.get_appointment(1).status, AppointmentStatus.PENDING)

    def test_cancelled_is_terminal(self):
        clinic, _, lines = make_clinic()
        doctor, patient = add_doctor_patient(clinic)
        clinic.book_appointment(patient, doctor, 10, 1)
        clinic.cancel_appointment(1)
        lines.clear()
        with self.assertRaises(InvalidTransitionError):
            clinic.confirm_appointment(1)
        with self.assertRaises(InvalidTransitionError):
            clinic.cancel_appointment(1)
        self.assertEqual(clinic.get_appointment(1).status, AppointmentStatus.CANCELLED)
        self.assertIn("FAILED confirm #1: cancelled appointment is terminal", lines)
        self.assertIn("FAILED cancel #1: already cancelled", lines)

    def test_confirming_twice_is_illegal(self):
        clinic, _, lines = make_clinic()
        doctor, patient = add_doctor_patient(clinic)
        clinic.book_appointment(patient, doctor, 10, 1)
        clinic.confirm_appointment(1)
        lines.clear()
        with self.assertRaises(InvalidTransitionError):
            clinic.confirm_appointment(1)
        self.assertIn("FAILED confirm #1: appointment is already confirmed", lines)

    def test_exact_failed_cancel_3_too_late(self):
        clinic, clock, lines = make_clinic()
        doctor, patient = add_doctor_patient(clinic)
        for hour in (8, 9, 10):
            clinic.book_appointment(patient, doctor, hour, hour - 7)
        clinic.confirm_appointment(3)
        lines.clear()
        clock.advance_to(9)
        with self.assertRaises(CancellationError):
            clinic.cancel_appointment(3)
        self.assertIn("FAILED cancel #3: too late", lines)
        self.assertEqual(lines.count("[log] opened"), 1)
        self.assertEqual(lines.count("[log] closed"), 1)

    def test_direct_appointment_state_rules(self):
        patient = Patient("Alice", 1001)
        doctor = Doctor("Dr A", 2001)
        appointment = Appointment(1, patient, doctor, 10)
        with self.assertRaises(CancellationError):
            appointment.cancel(10)
        appointment.cancel(8)
        self.assertIs(appointment.status, AppointmentStatus.CANCELLED)
        with self.assertRaises(InvalidTransitionError):
            appointment.confirm()
        with self.assertRaises(InvalidTransitionError):
            appointment.cancel(0)


class LoggingTests(unittest.TestCase):
    def test_open_and_close_exactly_once_on_success(self):
        clinic, _, lines = make_clinic()
        doctor, patient = add_doctor_patient(clinic)
        lines.clear()
        clinic.book_appointment(patient, doctor, 10, 1)
        self.assertEqual(lines.count("[log] opened"), 1)
        self.assertEqual(lines.count("[log] closed"), 1)
        self.assertEqual(lines[0], "[log] opened")
        self.assertEqual(lines[-1], "[log] closed")

    def test_failed_book_is_logged_with_exact_format(self):
        clinic, _, lines = make_clinic()
        doctor, patient = add_doctor_patient(clinic)
        other = Patient("Other", 6002)
        clinic.add_patient(other)
        clinic.book_appointment(patient, doctor, 14, 1)
        lines.clear()
        with self.assertRaises(ConflictError):
            clinic.book_appointment(other, doctor, 14, 2)
        self.assertIn("FAILED book: staff conflict at hour 14", lines)
        self.assertEqual(lines.count("[log] opened"), 1)
        self.assertEqual(lines.count("[log] closed"), 1)
        self.assertEqual(len(clinic.appointments), 1)

    def test_broken_sink_does_not_abort_successful_operation(self):
        def broken(_message):
            raise OSError("simulated disk full")

        logger = AppointmentLogger(sink=broken)
        clinic = Clinic(Clock(), logger=logger)
        with contextlib.redirect_stderr(io.StringIO()):
            doctor, patient = add_doctor_patient(clinic)
            appointment = clinic.book_appointment(patient, doctor, 10, 1)
        self.assertEqual(appointment.id, 1)
        self.assertIn("[log] opened", logger.entries)
        self.assertIn("[log] closed", logger.entries)

    def test_broken_sink_on_timing_failure_keeps_domain_exception(self):
        def broken(_message):
            raise OSError("simulated disk full")

        logger = AppointmentLogger(sink=broken)
        clock = Clock()
        clinic = Clinic(clock, logger=logger)
        with contextlib.redirect_stderr(io.StringIO()):
            doctor, patient = add_doctor_patient(clinic)
            clinic.book_appointment(patient, doctor, 10, 1)
            clinic.confirm_appointment(1)
            clock.advance_to(9)
            with self.assertRaises(CancellationError):
                clinic.cancel_appointment(1)
        self.assertIn("FAILED cancel #1: too late", logger.entries)

    def test_bad_log_file_does_not_abort_operation(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = AppointmentLogger(sink=lambda _message: None, path=directory)
            clinic = Clinic(Clock(), logger=logger)
            with contextlib.redirect_stderr(io.StringIO()):
                doctor, patient = add_doctor_patient(clinic)
                clinic.book_appointment(patient, doctor, 10, 1)
            self.assertEqual(len(clinic.appointments), 1)
            self.assertIn("[log] opened", logger.entries)

    def test_file_log_is_written(self):
        with tempfile.TemporaryDirectory() as directory:
            path = f"{directory}/appointment.log"
            logger = AppointmentLogger(sink=lambda _message: None, path=path)
            clinic = Clinic(Clock(), logger=logger)
            doctor, patient = add_doctor_patient(clinic)
            clinic.book_appointment(patient, doctor, 10, 1)
            with open(path, encoding="utf-8") as handle:
                contents = handle.read()
            self.assertIn("[log] opened", contents)
            self.assertIn("[log] booked #1", contents)
            self.assertIn("[log] closed", contents)

    def test_nested_sessions_are_rejected_and_outer_closes(self):
        logger = AppointmentLogger(sink=lambda _message: None)
        with logger.session():
            with self.assertRaises(RuntimeError):
                with logger.session():
                    pass
        self.assertEqual(logger.entries.count("[log] opened"), 1)
        self.assertEqual(logger.entries.count("[log] closed"), 1)


class IdAndConflictTests(unittest.TestCase):
    def test_duplicate_person_id_is_rejected_and_logged(self):
        clinic, _, lines = make_clinic()
        clinic.add_patient(Patient("Alice", 7000))
        lines.clear()
        with self.assertRaises(ConflictError):
            clinic.add_staff(Doctor("Dr B", 7000))
        self.assertIn("FAILED register: duplicate id 7000", lines)

    def test_duplicate_patient_registration_is_rejected(self):
        clinic, _, _ = make_clinic()
        clinic.add_patient(Patient("Alice", 7001))
        clinic.add_patient(Patient("Another Alice", 7002))
        with self.assertRaises(ConflictError):
            clinic.add_patient(Patient("Alice again", 7001))

    def test_person_and_appointment_ids_share_one_namespace(self):
        clinic, _, lines = make_clinic()
        patient = Patient("Alice", 1)
        doctor = Doctor("Dr A", 5001)
        clinic.add_patient(patient)
        clinic.add_staff(doctor)
        appointment = clinic.book_appointment(patient, doctor, 10)
        self.assertEqual(appointment.id, 2)  # id 1 is already the patient
        lines.clear()
        with self.assertRaises(ConflictError):
            clinic.book_appointment(patient, doctor, 11, 1)
        self.assertIn("FAILED book: duplicate id 1", lines)

    def test_duplicate_appointment_id_is_rejected(self):
        clinic, _, lines = make_clinic()
        doctor, patient = add_doctor_patient(clinic)
        clinic.book_appointment(patient, doctor, 10, 5)
        lines.clear()
        with self.assertRaises(ConflictError):
            clinic.book_appointment(patient, doctor, 11, 5)
        self.assertIn("FAILED book: duplicate id 5", lines)

    def test_get_missing_entities_raise_not_found(self):
        clinic, _, _ = make_clinic()
        with self.assertRaises(NotFoundError):
            clinic.get_appointment(99)
        with self.assertRaises(NotFoundError):
            clinic.get_patient(99)
        with self.assertRaises(NotFoundError):
            clinic.get_staff(99)

    def test_unregistered_participants_are_rejected(self):
        clinic, _, lines = make_clinic()
        doctor, patient = add_doctor_patient(clinic)
        stranger = Patient("Stranger", 8001)
        with self.assertRaises(ConflictError):
            clinic.book_appointment(stranger, doctor, 10)
        self.assertIn("FAILED book: patient #8001 is not registered", lines)
        other_doctor = Doctor("Other", 8002)
        with self.assertRaises(ConflictError):
            clinic.book_appointment(patient, other_doctor, 10)
        self.assertIn("FAILED book: staff #8002 is not registered", lines)

    def test_staff_and_patient_double_booking_are_rejected(self):
        clinic, _, _ = make_clinic()
        doctor = Doctor("Dr A", 5001)
        doctor2 = Doctor("Dr B", 5002)
        patient = Patient("Alice", 6001)
        patient2 = Patient("Bob", 6002)
        clinic.add_staff(doctor)
        clinic.add_staff(doctor2)
        clinic.add_patient(patient)
        clinic.add_patient(patient2)
        clinic.book_appointment(patient, doctor, 14, 1)
        with self.assertRaises(ConflictError):
            clinic.book_appointment(patient2, doctor, 14, 2)  # staff conflict
        with self.assertRaises(ConflictError):
            clinic.book_appointment(patient, doctor2, 14, 3)  # patient conflict
        self.assertEqual(len(clinic.appointments), 1)

    def test_cancelling_frees_the_slot(self):
        clinic, _, _ = make_clinic()
        doctor = Doctor("Dr A", 5001)
        patient = Patient("Alice", 6001)
        patient2 = Patient("Bob", 6002)
        clinic.add_staff(doctor)
        clinic.add_patient(patient)
        clinic.add_patient(patient2)
        clinic.book_appointment(patient, doctor, 14, 1)
        clinic.cancel_appointment(1)
        replacement = clinic.book_appointment(patient2, doctor, 14, 2)
        self.assertEqual(replacement.start_hour, 14)
        self.assertIs(replacement.status, AppointmentStatus.PENDING)


class DiamondTests(unittest.TestCase):
    def test_medical_lecturer_initialises_person_once(self):
        before = Person.init_call_count
        medical_lecturer = MedicalLecturer("Dr Lecturer", 9001, "CS401")
        self.assertEqual(Person.init_call_count - before, 1)
        self.assertEqual(medical_lecturer.person_init_calls, 1)
        self.assertEqual(medical_lecturer.role(), "Doctor and Lecturer")
        self.assertEqual(medical_lecturer.module_name, "CS401")
        self.assertEqual(medical_lecturer.fee(), 45.0)
        self.assertEqual(medical_lecturer.buffer_hours(), 2)

    def test_mro_contains_person_once_and_doctor_before_lecturer(self):
        names = [cls.__name__ for cls in MedicalLecturer.__mro__]
        self.assertEqual(names.count("Person"), 1)
        self.assertLess(names.index("Doctor"), names.index("Lecturer"))
        self.assertEqual(names[-1], "object")

    def test_medical_lecturer_fee_tracks_p(self):
        default_fee = MedicalLecturer("A", 9002, "CS401").fee()
        combined_fee = MedicalLecturer("B", 9003, "CS401", p_value=COMBINED_PAIR_P).fee()
        self.assertEqual(default_fee, 45.0)
        self.assertEqual(combined_fee, 50.0)

    def test_naive_double_initialisation_demonstrates_the_bug(self):
        class NaiveLecturer(Person):
            def __init__(self, name, id, module_name, **kwargs):
                self._module_name = module_name
                super().__init__(name=name, id=id, **kwargs)

            def role(self):
                return "Lecturer"

        class NaiveMedicalLecturer(Doctor, NaiveLecturer):
            def __init__(self, name, id, module_name):
                Doctor.__init__(self, name=name, id=id, module_name=module_name)
                NaiveLecturer.__init__(self, name=name, id=id, module_name=module_name)

            def role(self):
                return "Doctor and Lecturer"

        before = Person.init_call_count
        naive = NaiveMedicalLecturer("Naive", 9004, "CS402")
        self.assertEqual(Person.init_call_count - before, 2)
        self.assertEqual(naive.person_init_calls, 2)

    def test_lecturer_and_doctor_are_independently_constructible(self):
        lecturer = Lecturer("Lecturer", 9005, "CS403")
        doctor = Doctor("Doctor", 9006)
        self.assertEqual(lecturer.role(), "Lecturer")
        self.assertEqual(doctor.role(), "Doctor")
        self.assertEqual(lecturer.module_name, "CS403")
        self.assertEqual(doctor.fee(), 45.0)


class EmergencyTwistTests(unittest.TestCase):
    def test_emergency_bumps_pending(self):
        clinic, _, lines = make_clinic(STUDENT_1_ID)
        doctor, patient_a = add_doctor_patient(clinic, 5001, 6001, "Dr A", "A")
        patient_b = Patient("B", 6002)
        clinic.add_patient(patient_b)
        first = clinic.book_appointment(patient_a, doctor, 14, 1)
        patient_b.mark_emergency()
        lines.clear()
        second = clinic.book_appointment(patient_b, doctor, 14, 2)
        self.assertIs(first.status, AppointmentStatus.CANCELLED)
        self.assertEqual(first.cancellation_reason, "bumped")
        self.assertIs(second.status, AppointmentStatus.PENDING)
        self.assertIn("[log] bumped #1 by emergency booking at hour 14 (reason=bumped)", lines)
        self.assertEqual(lines.count("[log] opened"), 1)
        self.assertEqual(lines.count("[log] closed"), 1)

    def test_emergency_cannot_bump_confirmed(self):
        clinic, _, lines = make_clinic(STUDENT_2_ID)
        doctor, patient_a = add_doctor_patient(clinic, 5001, 6001, "Dr A", "A")
        patient_b = Patient("B", 6002)
        clinic.add_patient(patient_b)
        first = clinic.book_appointment(patient_a, doctor, 15, 1)
        clinic.confirm_appointment(1)
        patient_b.mark_emergency()
        lines.clear()
        with self.assertRaises(ConflictError):
            clinic.book_appointment(patient_b, doctor, 15, 2)
        self.assertIs(first.status, AppointmentStatus.CONFIRMED)
        self.assertIn("FAILED book: cannot bump confirmed #1 at hour 15", lines)
        self.assertEqual(len(clinic.appointments), 1)

    def test_patient_conflict_prevents_any_bump(self):
        clinic, _, lines = make_clinic(STUDENT_1_ID)
        doctor_a, patient_a = add_doctor_patient(clinic, 5001, 6001, "Dr A", "A")
        doctor_b = Doctor("Dr B", 5002)
        patient_b = Patient("B", 6002)
        clinic.add_staff(doctor_b)
        clinic.add_patient(patient_b)
        first = clinic.book_appointment(patient_a, doctor_a, 14, 1)
        clinic.book_appointment(patient_b, doctor_b, 14, 2)
        patient_b.mark_emergency()
        lines.clear()
        with self.assertRaises(ConflictError):
            clinic.book_appointment(patient_b, doctor_a, 14, 3)
        self.assertIs(first.status, AppointmentStatus.PENDING)
        self.assertIn("FAILED book: patient conflict at hour 14", lines)

    def test_started_pending_cannot_be_bumped(self):
        clinic, clock, lines = make_clinic(STUDENT_1_ID)
        doctor, patient_a = add_doctor_patient(clinic, 5001, 6001, "Dr A", "A")
        patient_b = Patient("B", 6002)
        clinic.add_patient(patient_b)
        first = clinic.book_appointment(patient_a, doctor, 6, 1)
        clock.advance_to(6)
        patient_b.mark_emergency()
        lines.clear()
        with self.assertRaises(ConflictError):
            clinic.book_appointment(patient_b, doctor, 6, 2)
        self.assertIs(first.status, AppointmentStatus.PENDING)
        self.assertIn("FAILED book: cannot bump #1: too late", lines)

    def test_emergency_bump_is_dormant_under_buffer_policy(self):
        clinic, _, _ = make_clinic(COMBINED_PAIR_P)
        doctor, patient_a = add_doctor_patient(clinic, 5001, 6001, "Dr A", "A")
        patient_b = Patient("B", 6002)
        clinic.add_patient(patient_b)
        first = clinic.book_appointment(patient_a, doctor, 14, 1)
        patient_b.mark_emergency()
        with self.assertRaises(ConflictError):
            clinic.book_appointment(patient_b, doctor, 14, 2)
        self.assertIs(first.status, AppointmentStatus.PENDING)
        self.assertEqual(len(clinic.appointments), 1)


class BufferTwistTests(unittest.TestCase):
    def test_doctor_buffer_boundaries(self):
        clinic, _, lines = make_clinic(COMBINED_PAIR_P)
        doctor, patient = add_doctor_patient(clinic)
        patient2 = Patient("Other", 6002)
        clinic.add_patient(patient2)
        clinic.book_appointment(patient, doctor, 30, 1)
        for hour in (31, 32):
            with self.subTest(hour=hour):
                with self.assertRaises(ConflictError):
                    clinic.book_appointment(patient2, doctor, hour)
        clinic.book_appointment(patient2, doctor, 33, 2)
        self.assertEqual(len(clinic.appointments), 2)

    def test_nurse_and_pharmacist_buffers(self):
        clinic, _, _ = make_clinic(COMBINED_PAIR_P)
        nurse = Nurse("Nurse A", 5001)
        pharmacist = Pharmacist("Pharm A", 5002)
        patient1 = Patient("P1", 6001)
        patient2 = Patient("P2", 6002)
        patient3 = Patient("P3", 6003)
        for member in (nurse, pharmacist):
            clinic.add_staff(member)
        for patient in (patient1, patient2, patient3):
            clinic.add_patient(patient)

        clinic.book_appointment(patient1, nurse, 40, 1)
        with self.assertRaises(ConflictError):
            clinic.book_appointment(patient2, nurse, 41)
        clinic.book_appointment(patient2, nurse, 42, 2)
        clinic.book_appointment(patient3, pharmacist, 50, 3)
        clinic.book_appointment(patient1, pharmacist, 51, 4)
        self.assertEqual(len(clinic.appointments), 4)

    def test_buffer_is_symmetric_before_and_after(self):
        clinic, _, _ = make_clinic(COMBINED_PAIR_P)
        doctor, patient = add_doctor_patient(clinic)
        patient2 = Patient("Other", 6002)
        clinic.add_patient(patient2)
        clinic.book_appointment(patient, doctor, 13, 1)
        clinic.book_appointment(patient2, doctor, 10, 2)  # free gap 2: allowed
        with self.assertRaises(ConflictError):
            clinic.book_appointment(patient2, doctor, 11, 3)  # free gap 1: rejected
        self.assertEqual(len(clinic.appointments), 2)

    def test_custom_staff_buffer_is_polymorphic(self):
        class Radiologist(Staff):
            def role(self):
                return "Radiologist"

            def fee(self):
                return 70.0

            def buffer_hours(self):
                return 3

        clinic, _, _ = make_clinic(COMBINED_PAIR_P)
        radiologist = Radiologist("Rad", 5001)
        patient1 = Patient("P1", 6001)
        patient2 = Patient("P2", 6002)
        clinic.add_staff(radiologist)
        clinic.add_patient(patient1)
        clinic.add_patient(patient2)
        clinic.book_appointment(patient1, radiologist, 20, 1)
        with self.assertRaises(ConflictError):
            clinic.book_appointment(patient2, radiologist, 23)
        clinic.book_appointment(patient2, radiologist, 24, 2)
        self.assertEqual(len(clinic.appointments), 2)

    def test_buffer_is_dormant_under_default_policy(self):
        clinic, _, _ = make_clinic(STUDENT_1_ID)
        doctor, patient = add_doctor_patient(clinic)
        patient2 = Patient("Other", 6002)
        clinic.add_patient(patient2)
        clinic.book_appointment(patient, doctor, 30, 1)
        clinic.book_appointment(patient2, doctor, 31, 2)
        self.assertEqual(len(clinic.appointments), 2)

    def test_free_gap_helper(self):
        self.assertEqual(Clinic._free_gap_hours(10, 13), 2)
        self.assertEqual(Clinic._free_gap_hours(10, 12), 1)
        self.assertEqual(Clinic._free_gap_hours(13, 10), 2)
        self.assertEqual(Clinic._free_gap_hours(13, 11), 1)


class WaitingListTwistTests(unittest.TestCase):
    def test_cancellation_offers_slot_to_first_waiting_patient(self):
        clinic, _, lines = make_clinic(DEMO_P_TWIST_0)
        doctor, patient_a = add_doctor_patient(clinic, 5001, 6001, "Dr A", "A")
        patient_b = Patient("B", 6002)
        clinic.add_patient(patient_b)
        clinic.book_appointment(patient_a, doctor, 20, 1)
        clinic.join_waiting_list(patient_b, doctor)
        lines.clear()
        clinic.cancel_appointment(1)
        offered = clinic.get_appointment(2)
        self.assertEqual(offered.patient.id, patient_b.id)
        self.assertEqual(offered.start_hour, 20)
        self.assertIs(offered.status, AppointmentStatus.PENDING)
        self.assertEqual(doctor.waiting_list, ())
        self.assertIn("[log] waitlist offered #2", "\n".join(lines))
        self.assertEqual(lines.count("[log] opened"), 1)
        self.assertEqual(lines.count("[log] closed"), 1)

    def test_conflicting_first_patient_is_skipped(self):
        clinic, _, lines = make_clinic(DEMO_P_TWIST_0)
        doctor_a = Doctor("Dr A", 5001)
        doctor_b = Doctor("Dr B", 5002)
        patient_a = Patient("A", 6001)
        patient_b = Patient("B", 6002)
        patient_c = Patient("C", 6003)
        for member in (doctor_a, doctor_b):
            clinic.add_staff(member)
        for member in (patient_a, patient_b, patient_c):
            clinic.add_patient(member)

        clinic.book_appointment(patient_a, doctor_a, 20, 1)
        clinic.book_appointment(patient_b, doctor_b, 20, 2)
        clinic.join_waiting_list(patient_b, doctor_a)
        clinic.join_waiting_list(patient_c, doctor_a)
        lines.clear()
        clinic.cancel_appointment(1)
        offered = clinic.get_appointment(3)
        self.assertEqual(offered.patient.id, patient_c.id)
        self.assertEqual([patient.id for patient in doctor_a.waiting_list], [patient_b.id])
        self.assertTrue(any("waitlist offered #3" in line for line in lines))

    def test_no_eligible_patient_keeps_queue(self):
        clinic, _, lines = make_clinic(DEMO_P_TWIST_0)
        doctor_a = Doctor("Dr A", 5001)
        doctor_b = Doctor("Dr B", 5002)
        patient_a = Patient("A", 6001)
        patient_b = Patient("B", 6002)
        clinic.add_staff(doctor_a)
        clinic.add_staff(doctor_b)
        clinic.add_patient(patient_a)
        clinic.add_patient(patient_b)
        clinic.book_appointment(patient_a, doctor_a, 20, 1)
        clinic.book_appointment(patient_b, doctor_b, 20, 2)
        clinic.join_waiting_list(patient_b, doctor_a)
        lines.clear()
        clinic.cancel_appointment(1)
        self.assertEqual(len(clinic.appointments), 2)
        self.assertEqual([patient.id for patient in doctor_a.waiting_list], [patient_b.id])
        self.assertTrue(any("waitlist: no eligible patient" in line for line in lines))

    def test_waiting_list_is_dormant_under_default_policy(self):
        clinic, _, lines = make_clinic(STUDENT_1_ID)
        doctor, patient_a = add_doctor_patient(clinic, 5001, 6001, "Dr A", "A")
        patient_b = Patient("B", 6002)
        clinic.add_patient(patient_b)
        clinic.book_appointment(patient_a, doctor, 20, 1)
        clinic.join_waiting_list(patient_b, doctor)
        lines.clear()
        clinic.cancel_appointment(1)
        self.assertEqual(len(clinic.appointments), 1)
        self.assertEqual([patient.id for patient in doctor.waiting_list], [patient_b.id])

    def test_duplicate_waiting_list_join_is_rejected(self):
        clinic, _, lines = make_clinic(DEMO_P_TWIST_0)
        doctor, patient = add_doctor_patient(clinic)
        clinic.join_waiting_list(patient, doctor)
        lines.clear()
        with self.assertRaises(ConflictError):
            clinic.join_waiting_list(patient, doctor)
        self.assertIn("FAILED waitlist: patient #6001 is already on the waiting list", lines)

    def test_patient_is_not_offered_their_own_cancelled_slot(self):
        clinic, _, lines = make_clinic(DEMO_P_TWIST_0)
        doctor, patient = add_doctor_patient(clinic)
        clinic.book_appointment(patient, doctor, 20, 1)
        clinic.join_waiting_list(patient, doctor)
        lines.clear()
        clinic.cancel_appointment(1)
        self.assertEqual(len(clinic.appointments), 1)
        self.assertEqual([waiting.id for waiting in doctor.waiting_list], [patient.id])


class DiscountTwistTests(unittest.TestCase):
    def test_patient_discount_multipliers(self):
        self.assertEqual(StudentPatient("S", 6001).discount_multiplier(), 0.5)
        self.assertEqual(StaffMemberPatient("M", 6002).discount_multiplier(), 0.0)
        self.assertEqual(VisitorPatient("V", 6003).discount_multiplier(), 1.0)
        self.assertEqual(Patient("P", 6004).discount_multiplier(), 1.0)

    def test_quotes_under_discount_policy(self):
        clinic, _, _ = make_clinic(DEMO_P_TWIST_3)
        doctor = Doctor("Dr A", 5001, p_value=DEMO_P_TWIST_3)  # fee 55
        student = StudentPatient("Student", 6001)
        staff_member = StaffMemberPatient("Staff member", 6002)
        visitor = VisitorPatient("Visitor", 6003)
        clinic.add_staff(doctor)
        for patient in (student, staff_member, visitor):
            clinic.add_patient(patient)
        self.assertEqual(clinic.quote(doctor, student), 27.5)
        self.assertEqual(clinic.quote(doctor, staff_member), 0.0)
        self.assertEqual(clinic.quote(doctor, visitor), 55.0)

    def test_custom_patient_category_needs_no_clinic_change(self):
        class SeniorPatient(Patient):
            def discount_multiplier(self):
                return 0.25

        clinic, _, _ = make_clinic(DEMO_P_TWIST_3)
        doctor = Doctor("Dr A", 5001, p_value=DEMO_P_TWIST_3)
        senior = SeniorPatient("Senior", 6001)
        clinic.add_staff(doctor)
        clinic.add_patient(senior)
        self.assertEqual(clinic.quote(doctor, senior), 13.75)

    def test_discount_is_dormant_under_default_policy(self):
        clinic, _, _ = make_clinic(STUDENT_1_ID)
        doctor, _ = add_doctor_patient(clinic)
        student = StudentPatient("Student", 6002)
        clinic.add_patient(student)
        self.assertEqual(clinic.quote(doctor, student), 45.0)

    def test_booked_log_contains_discounted_price(self):
        clinic, _, lines = make_clinic(DEMO_P_TWIST_3)
        doctor = Doctor("Dr A", 5001, p_value=DEMO_P_TWIST_3)
        student = StudentPatient("Student", 6001)
        clinic.add_staff(doctor)
        clinic.add_patient(student)
        lines.clear()
        clinic.book_appointment(student, doctor, 10, 1)
        self.assertTrue(any("price=27.50" in line for line in lines))


class ClinicIntegrationTests(unittest.TestCase):
    def test_full_lifecycle_and_views(self):
        clinic, clock, lines = make_clinic()
        doctor, patient = add_doctor_patient(clinic)
        appointment = clinic.book_appointment(patient, doctor, 10, 1)
        clinic.confirm_appointment(1)
        self.assertEqual(clinic.get_appointment(1), appointment)
        self.assertEqual(clinic.get_patient(6001), patient)
        self.assertEqual(clinic.get_staff(5001), doctor)
        clock.advance_to(8)
        clinic.cancel_appointment(1)
        self.assertIs(appointment.status, AppointmentStatus.CANCELLED)
        self.assertTrue(any("cancelled #1" in line for line in lines))

    def test_bookings_at_literal_boundary_hours(self):
        clinic, _, _ = make_clinic()
        doctor, patient = add_doctor_patient(clinic)
        at_zero = clinic.book_appointment(patient, doctor, 0, 1)
        at_max = clinic.book_appointment(patient, doctor, 168, 2)
        self.assertEqual(at_zero.start_hour, 0)
        self.assertEqual(at_max.start_hour, 168)
        with self.assertRaises(ValidationError):
            clinic.book_appointment(patient, doctor, 169)

    def test_same_patient_can_book_different_hours(self):
        clinic, _, _ = make_clinic()
        doctor, patient = add_doctor_patient(clinic)
        clinic.book_appointment(patient, doctor, 10, 1)
        clinic.book_appointment(patient, doctor, 12, 2)
        self.assertEqual(len(clinic.appointments), 2)

    def test_default_p_is_student_one(self):
        clinic = Clinic(Clock())
        self.assertEqual(clinic.p_value, STUDENT_1_ID)
        self.assertEqual(clinic.p_mod_4, 1)


if __name__ == "__main__":
    unittest.main()
