"""Domain model exports for the clinic appointment system."""

from .appointment import Appointment, AppointmentStatus
from .lecturer import Lecturer, MedicalLecturer
from .patient import (
    Patient,
    StaffMemberPatient,
    StudentPatient,
    VisitorPatient,
)
from .person import Person
from .staff import Doctor, Nurse, Pharmacist, Staff

__all__ = [
    "Appointment",
    "AppointmentStatus",
    "Doctor",
    "Lecturer",
    "MedicalLecturer",
    "Nurse",
    "Patient",
    "Person",
    "Pharmacist",
    "Staff",
    "StaffMemberPatient",
    "StudentPatient",
    "VisitorPatient",
]
