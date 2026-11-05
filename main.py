#!/usr/bin/env python3
"""Five-minute deterministic demo for the UZ clinic appointment system.

Run from the repository root:

    python3 main.py

The script covers Q1-Q6, the MRO counter proof, all four P mod 4 twists and
deliberate logged failures.  It never reads the wall clock.
"""

from __future__ import annotations

from src.clinic import Clinic
from src.clock import Clock
from src.config import (
    COMBINED_PAIR_P,
    DEFAULT_P,
    DEMO_P_TWIST_0,
    DEMO_P_TWIST_3,
    STUDENT_1_ID,
    STUDENT_2_ID,
)
from src.exceptions import ClinicError
from src.models import (
    AppointmentStatus,
    Doctor,
    MedicalLecturer,
    Nurse,
    Patient,
    Person,
    Pharmacist,
    StaffMemberPatient,
    StudentPatient,
    VisitorPatient,
)


def banner() -> None:
    line = "=" * 78
    print(line)
    print("UNIVERSITY OF ZIMBABWE - DEPARTMENT OF COMPUTER SCIENCE")
    print("Programming Languages - Clinic Appointment System Mini Project")
    print("BSc Honours in Computer Science (HCS)")
    print("Super Washington Banga - R2420381")
    print("Anesu Prosper Matanhire - R2420441")
    print(line)


def section(title: str) -> None:
    print()
    print("-" * 78)
    print(title)
    print("-" * 78)


def caught(label: str, error: Exception) -> None:
    print(f"  caught {label}: {error}")


# ---------------------------------------------------------------------------
# Q1 / Q2 - hierarchy, encapsulation, state machine
# ---------------------------------------------------------------------------
def demo_q1_q2() -> None:
    section("Q1/Q2 - domain hierarchy, encapsulation and the state machine")
    clinic = Clinic(Clock(), p_value=DEFAULT_P)

    doctor = Doctor("Dr Chikwanha", 5001)
    nurse = Nurse("Nurse Moyo", 5002)
    pharmacist = Pharmacist("Pharm Ncube", 5003)
    patient = Patient("Tendai Patient", 6001)
    for member in (doctor, nurse, pharmacist):
        clinic.add_staff(member)
    clinic.add_patient(patient)

    print("  Person hierarchy roles:")
    for person in (doctor, nurse, pharmacist, patient):
        print(f"    {person.role():<12} {person.name} (#{person.id})")

    appointment = clinic.book_appointment(patient, doctor, 10, 1)
    print(f"  booked: {appointment!r}")
    print(f"  status after booking: {appointment.status.value}")
    clinic.confirm_appointment(1)
    print(f"  status after confirm: {appointment.status.value}")

    snapshot = clinic.appointments
    print(f"  clinic.appointments returns: {snapshot!r}")
    try:
        snapshot.append(None)
    except AttributeError:
        print("  defensive copy: caller cannot append to the internal collection")

    try:
        Patient("", 6002)
    except ValueError as error:
        caught("constructor validation", error)

    print(f"  internal appointment count remains: {len(clinic.appointments)}")


# ---------------------------------------------------------------------------
# Q3 - one polymorphic loop, no type checks
# ---------------------------------------------------------------------------
def demo_q3() -> None:
    section("Q3 - one loop over Staff; role() and fee() dispatch polymorphically")
    clinic = Clinic(Clock(), p_value=DEFAULT_P)
    for member in (
        Doctor("Dr Chikwanha", 5001),
        Nurse("Nurse Moyo", 5002),
        Pharmacist("Pharm Ncube", 5003),
    ):
        clinic.add_staff(member)

    print(f"  P = {DEFAULT_P}  ->  P mod 5 = {DEFAULT_P % 5}, "
          f"P mod 3 = {DEFAULT_P % 3}")
    for member in clinic.staff:
        print(f"    {member.role():<12} fee = {member.fee():.2f}")
    print("  No runtime type dispatch or role-string branching is used.")


# ---------------------------------------------------------------------------
# Q4 - context-managed logging and a deliberate failure
# ---------------------------------------------------------------------------
def demo_q4() -> None:
    section("Q4 - [log] opened / [log] closed, including a deliberate failure")
    clock = Clock()
    clinic = Clinic(clock, p_value=DEFAULT_P)
    doctor = Doctor("Dr Chikwanha", 5001)
    patient = Patient("Tendai Patient", 6001)
    other = Patient("Rudo Patient", 6002)
    clinic.add_staff(doctor)
    clinic.add_patient(patient)
    clinic.add_patient(other)

    clinic.book_appointment(patient, doctor, 8, 1)
    clinic.book_appointment(patient, doctor, 9, 2)
    clinic.book_appointment(patient, doctor, 10, 3)
    clinic.confirm_appointment(3)
    clock.advance_to(9)

    print("  Attempting to cancel confirmed appointment #3 at hour 9:")
    try:
        clinic.cancel_appointment(3)
    except ClinicError as error:
        caught("expected cancellation failure", error)

    print("  Attempting a double booking at hour 14:")
    clinic.book_appointment(patient, doctor, 14, 4)
    try:
        clinic.book_appointment(other, doctor, 14, 5)
    except ClinicError as error:
        caught("expected booking failure", error)

    print(f"  appointment #3 status is still: "
          f"{clinic.get_appointment(3).status.value}")


# ---------------------------------------------------------------------------
# Q5 - diamond inheritance and the Person counter
# ---------------------------------------------------------------------------
def demo_q5() -> None:
    section("Q5 - Lecturer + Doctor diamond, cooperative super() and MRO")
    before = Person.init_call_count
    medical_lecturer = MedicalLecturer(
        "Dr Super Lecturer",
        7001,
        "CS401 Advanced Programming",
    )
    after = Person.init_call_count

    print(f"  role(): {medical_lecturer.role()}")
    print(f"  module_name: {medical_lecturer.module_name}")
    print(f"  fee(): {medical_lecturer.fee():.2f} (inherited from Doctor.fee)")
    print(f"  buffer_hours(): {medical_lecturer.buffer_hours()} (inherited from Doctor)")
    print(f"  Person.__init__ delta: {after - before}")
    print(f"  instance person_init_calls: {medical_lecturer.person_init_calls}")
    print("  MRO: " + " -> ".join(cls.__name__ for cls in MedicalLecturer.__mro__))


# ---------------------------------------------------------------------------
# Q6 - all four P mod 4 twists
# ---------------------------------------------------------------------------
def demo_twist_emergency() -> None:
    section("Q6 Twist 1 (P mod 4 = 1) - emergency bump of a PENDING appointment")
    clinic = Clinic(Clock(), p_value=STUDENT_1_ID)
    doctor = Doctor("Dr Chikwanha", 5001)
    patient_a = Patient("Pending Patient", 6001)
    patient_b = Patient("Emergency Patient", 6002)
    patient_c = Patient("Confirmed Patient", 6003)
    patient_d = Patient("Emergency Other", 6004)
    for member in (doctor,):
        clinic.add_staff(member)
    for member in (patient_a, patient_b, patient_c, patient_d):
        clinic.add_patient(member)

    pending = clinic.book_appointment(patient_a, doctor, 14, 1)
    patient_b.mark_emergency()
    bumped = clinic.book_appointment(patient_b, doctor, 14, 2)
    print(f"  #1 status: {pending.status.value}; reason: {pending.cancellation_reason}")
    print(f"  #2 status: {bumped.status.value} for {bumped.patient.name}")

    confirmed = clinic.book_appointment(patient_c, doctor, 15, 3)
    clinic.confirm_appointment(3)
    patient_d.mark_emergency()
    try:
        clinic.book_appointment(patient_d, doctor, 15, 4)
    except ClinicError as error:
        caught("confirmed appointment cannot be bumped", error)
    print(f"  #3 status remains: {confirmed.status.value}")


def demo_twist_buffer() -> None:
    section("Q6 Twist 2 (P mod 4 = 2) - polymorphic staff buffer hours")
    clinic = Clinic(Clock(), p_value=COMBINED_PAIR_P)
    doctor = Doctor("Dr Buffer", 5001, p_value=COMBINED_PAIR_P)
    nurse = Nurse("Nurse Buffer", 5002, p_value=COMBINED_PAIR_P)
    pharmacist = Pharmacist("Pharm Buffer", 5003, p_value=COMBINED_PAIR_P)
    patient_a = Patient("Buffer A", 6001)
    patient_b = Patient("Buffer B", 6002)
    for member in (doctor, nurse, pharmacist):
        clinic.add_staff(member)
    for member in (patient_a, patient_b):
        clinic.add_patient(member)

    print(
        f"  buffer_hours(): doctor={doctor.buffer_hours()}, "
        f"nurse={nurse.buffer_hours()}, pharmacist={pharmacist.buffer_hours()}"
    )
    clinic.book_appointment(patient_a, doctor, 30, 1)
    for hour in (31, 32):
        try:
            clinic.book_appointment(patient_b, doctor, hour)
        except ClinicError as error:
            print(f"  hour {hour} rejected: {error}")
    clinic.book_appointment(patient_b, doctor, 33, 2)
    print("  doctor at 30 -> next allowed at 33 (2-hour free gap after [30,31))")
       

def demo_twist_waiting_list() -> None:
    section("Q6 Twist 0 (synthetic P mod 4 = 0) - waiting-list offer")
    clinic = Clinic(Clock(), p_value=DEMO_P_TWIST_0)
    doctor = Doctor("Dr Queue", 5001)
    patient_a = Patient("Booked Patient", 6001)
    patient_b = Patient("Waiting Patient", 6002)
    clinic.add_staff(doctor)
    clinic.add_patient(patient_a)
    clinic.add_patient(patient_b)

    original = clinic.book_appointment(patient_a, doctor, 20, 1)
    clinic.join_waiting_list(patient_b, doctor)
    print(f"  waiting list before cancellation: "
          f"{[patient.id for patient in doctor.waiting_list]}")
    clinic.cancel_appointment(original.id)
    offered = clinic.get_appointment(2)
    print(f"  cancelled #1; offered #{offered.id} to {offered.patient.name} "
          f"at hour {offered.start_hour} as {offered.status.value}")
    print(f"  waiting list after offer: {doctor.waiting_list}")


def demo_twist_discounts() -> None:
    section("Q6 Twist 3 (synthetic P mod 4 = 3) - polymorphic patient discounts")
    clinic = Clinic(Clock(), p_value=DEMO_P_TWIST_3)
    doctor = Doctor("Dr Fees", 5001, p_value=DEMO_P_TWIST_3)
    student = StudentPatient("Student Patient", 6001)
    staff_member = StaffMemberPatient("Staff-member Patient", 6002)
    visitor = VisitorPatient("Visitor Patient", 6003)
    clinic.add_staff(doctor)
    for patient in (student, staff_member, visitor):
        clinic.add_patient(patient)

    print(f"  doctor fee: {doctor.fee():.2f}")
    for patient in (student, staff_member, visitor):
        print(
            f"  {patient.billing_label:<13} multiplier="
            f"{patient.discount_multiplier():.2f} -> "
            f"price={clinic.quote(doctor, patient):.2f}"
        )


def main() -> None:
    banner()
    demo_q1_q2()
    demo_q3()
    demo_q4()
    demo_q5()
    demo_twist_emergency()
    demo_twist_buffer()
    demo_twist_waiting_list()
    demo_twist_discounts()

    section("Verification")
    print("  python3 -m unittest discover -s tests -v")
    print("  pytest -q")
    print("  Both commands should report 80 passing tests.")
    print()
    print("Demo complete: Q1-Q6, all four twists, MRO counter and logged failures.")
    print(f"Pair P default = {DEFAULT_P}; combined P = {COMBINED_PAIR_P}; "
          f"student IDs = {STUDENT_1_ID}, {STUDENT_2_ID}.")


if __name__ == "__main__":
    main()
