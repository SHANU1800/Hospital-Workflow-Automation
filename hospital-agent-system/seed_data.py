"""
Seed Data — Populate the database with sample patients, doctors, and beds.

Plan 1.0 additions:
  - 20 beds across ICU, Cardiology, General, Neurology, Oncology wards
  - Patients now include department-matched bed assignments

Run on application startup to ensure the demo has data to work with.
Can also be run standalone: python seed_data.py
"""

from __future__ import annotations

import asyncio
import logging
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.security import get_password_hash

logger = logging.getLogger("seed_data")

# ─────────────────────────────────────────────
# Sample Data
# ─────────────────────────────────────────────

SAMPLE_PATIENTS = [
    {
        "id": 101,
        "name": "John Smith",
        "age": 45,
        "department": "cardiology",
        "condition": "Chest pain, elevated troponin",
        "insurance_provider": "BlueCross",
        "member_id": "BC-101-2024",
        "plan_type": "premium",
    },
    {
        "id": 102,
        "name": "Sarah Johnson",
        "age": 32,
        "department": "neurology",
        "condition": "Recurring migraines, MRI pending",
        "insurance_provider": "Aetna",
        "member_id": "AE-102-2024",
        "plan_type": "standard",
    },
    {
        "id": 103,
        "name": "Mike Davis",
        "age": 67,
        "department": "orthopedics",
        "condition": "Hip fracture from fall",
        "insurance_provider": "Medicare",
        "member_id": "MC-103-2024",
        "plan_type": "senior",
    },
    {
        "id": 104,
        "name": "Emily Chen",
        "age": 28,
        "department": "general",
        "condition": "Acute appendicitis symptoms",
        "insurance_provider": "Cigna",
        "member_id": "CI-104-2024",
        "plan_type": "standard",
    },
    {
        "id": 105,
        "name": "Robert Wilson",
        "age": 55,
        "department": "cardiology",
        "condition": "Atrial fibrillation, needs monitoring",
        "insurance_provider": "UnitedHealth",
        "member_id": "UH-105-2024",
        "plan_type": "premium",
    },
    {
        "id": 106,
        "name": "Lisa Anderson",
        "age": 41,
        "department": "oncology",
        "condition": "Post-chemotherapy observation",
        "insurance_provider": "BlueCross",
        "member_id": "BC-106-2024",
        "plan_type": "premium",
    },
    {
        "id": 107,
        "name": "James Taylor",
        "age": 73,
        "department": "pulmonology",
        "condition": "COPD exacerbation",
        "insurance_provider": "Medicare",
        "member_id": "MC-107-2024",
        "plan_type": "senior",
    },
    {
        "id": 108,
        "name": "Maria Garcia",
        "age": 36,
        "department": "general",
        "condition": "Severe dehydration, IV fluids needed",
        "insurance_provider": "Medicaid",
        "member_id": "MD-108-2024",
        "plan_type": "basic",
    },
    {
        "id": 109,
        "name": "David Kim",
        "age": 82,
        "department": "icu",
        "condition": "Sepsis, critical care required",
        "insurance_provider": "Medicare",
        "member_id": "MC-109-2024",
        "plan_type": "senior",
    },
    {
        "id": 110,
        "name": "Priya Patel",
        "age": 29,
        "department": "general",
        "condition": "Allergic reaction, anaphylaxis risk",
        "insurance_provider": "Aetna",
        "member_id": "AE-110-2024",
        "plan_type": "standard",
    },
]

SAMPLE_DOCTORS = [
    {"id": 1, "name": "Dr. Amanda Hart", "department": "cardiology", "specialization": "Interventional Cardiology"},
    {"id": 2, "name": "Dr. James Foster", "department": "cardiology", "specialization": "Electrophysiology"},
    {"id": 3, "name": "Dr. Sarah Kim", "department": "neurology", "specialization": "Stroke & Vascular Neurology"},
    {"id": 4, "name": "Dr. David Patel", "department": "neurology", "specialization": "Epilepsy"},
    {"id": 5, "name": "Dr. Michael Ross", "department": "orthopedics", "specialization": "Joint Replacement"},
    {"id": 6, "name": "Dr. Jennifer Liu", "department": "general", "specialization": "Internal Medicine"},
    {"id": 7, "name": "Dr. Robert Chang", "department": "general", "specialization": "Emergency Medicine"},
    {"id": 8, "name": "Dr. Emily Watson", "department": "oncology", "specialization": "Medical Oncology"},
    {"id": 9, "name": "Dr. Andrew Bell", "department": "pulmonology", "specialization": "Critical Care"},
    {"id": 10, "name": "Dr. Maria Santos", "department": "general", "specialization": "Family Medicine"},
    {"id": 11, "name": "Dr. Kevin Chen", "department": "icu", "specialization": "Intensive Care"},
    {"id": 12, "name": "Dr. Patricia Moore", "department": "icu", "specialization": "Critical Care Medicine"},
]

# Plan 1.0: Hospital bed inventory
# Wards: ICU, Cardiology, General, Neurology, Oncology, Pulmonology, Orthopedics
SAMPLE_BEDS = [
    # ICU — 4 beds
    {"id": 1, "ward": "icu", "bed_number": "ICU-01", "status": "available"},
    {"id": 2, "ward": "icu", "bed_number": "ICU-02", "status": "available"},
    {"id": 3, "ward": "icu", "bed_number": "ICU-03", "status": "available"},
    {"id": 4, "ward": "icu", "bed_number": "ICU-04", "status": "available"},
    # Cardiology — 4 beds
    {"id": 5, "ward": "cardiology", "bed_number": "CARD-01", "status": "available"},
    {"id": 6, "ward": "cardiology", "bed_number": "CARD-02", "status": "available"},
    {"id": 7, "ward": "cardiology", "bed_number": "CARD-03", "status": "available"},
    {"id": 8, "ward": "cardiology", "bed_number": "CARD-04", "status": "available"},
    # General — 4 beds
    {"id": 9,  "ward": "general", "bed_number": "GEN-01", "status": "available"},
    {"id": 10, "ward": "general", "bed_number": "GEN-02", "status": "available"},
    {"id": 11, "ward": "general", "bed_number": "GEN-03", "status": "available"},
    {"id": 12, "ward": "general", "bed_number": "GEN-04", "status": "available"},
    # Neurology — 2 beds
    {"id": 13, "ward": "neurology", "bed_number": "NEURO-01", "status": "available"},
    {"id": 14, "ward": "neurology", "bed_number": "NEURO-02", "status": "available"},
    # Oncology — 2 beds
    {"id": 15, "ward": "oncology", "bed_number": "ONCO-01", "status": "available"},
    {"id": 16, "ward": "oncology", "bed_number": "ONCO-02", "status": "available"},
    # Pulmonology — 2 beds
    {"id": 17, "ward": "pulmonology", "bed_number": "PULM-01", "status": "available"},
    {"id": 18, "ward": "pulmonology", "bed_number": "PULM-02", "status": "available"},
    # Orthopedics — 2 beds
    {"id": 19, "ward": "orthopedics", "bed_number": "ORTHO-01", "status": "available"},
    {"id": 20, "ward": "orthopedics", "bed_number": "ORTHO-02", "status": "available"},
]

SAMPLE_CHARGE_CODES = [
    {"service_key": "admission", "service_name": "Admission", "code": "ADM001", "amount": 5000.0},
    {"service_key": "lab_cbc", "service_name": "CBC Lab", "code": "LAB010", "amount": 800.0},
    {"service_key": "lab_metabolic", "service_name": "Metabolic Panel", "code": "LAB020", "amount": 1200.0},
    {"service_key": "xray", "service_name": "X-Ray", "code": "RAD010", "amount": 2500.0},
    {"service_key": "icu_day", "service_name": "ICU Bed Day", "code": "ICU001", "amount": 15000.0},
    {"service_key": "general_day", "service_name": "General Bed Day", "code": "GEN001", "amount": 5000.0},
    {"service_key": "doctor_consult", "service_name": "Doctor Consultation", "code": "CON001", "amount": 2000.0},
    {"service_key": "medication", "service_name": "Medication", "code": "MED001", "amount": 500.0},
]

SAMPLE_INSURANCE_ELIGIBILITY_RULES = [
    {
        "insurance_provider": "BlueCross",
        "plan_type": "premium",
        "coverage_percentage": 85.0,
        "covered_services": ["inpatient", "emergency", "lab", "radiology", "icu"],
    },
    {
        "insurance_provider": "Aetna",
        "plan_type": "standard",
        "coverage_percentage": 70.0,
        "covered_services": ["inpatient", "emergency", "lab", "radiology"],
    },
    {
        "insurance_provider": "Medicare",
        "plan_type": "senior",
        "coverage_percentage": 75.0,
        "covered_services": ["inpatient", "emergency", "lab", "radiology", "rehab"],
    },
    {
        "insurance_provider": "default",
        "plan_type": "standard",
        "coverage_percentage": 60.0,
        "covered_services": ["inpatient", "emergency", "lab"],
    },
    {
        "insurance_provider": "default",
        "plan_type": "premium",
        "coverage_percentage": 80.0,
        "covered_services": ["inpatient", "emergency", "lab", "radiology", "icu"],
    },
    {
        "insurance_provider": "default",
        "plan_type": "general",
        "coverage_percentage": 60.0,
        "covered_services": ["inpatient", "emergency", "lab"],
    },
]

SAMPLE_USERS = [
    {
        "username": "super_admin",
        "email": "super_admin@hospital.local",
        "password": "SuperAdmin@123",
        "role": "super_admin",
    },
    {
        "username": "staff_user",
        "email": "staff@hospital.local",
        "password": "StaffUser@123",
        "role": "staff",
    },
    {
        "username": "doctor_user",
        "email": "doctor@hospital.local",
        "password": "DoctorUser@123",
        "role": "doctor",
    },
    {
        "username": "auditor_user",
        "email": "auditor@hospital.local",
        "password": "AuditorUser@123",
        "role": "auditor",
    },
]


async def seed_database():
    """
    Seed the database with sample data.

    Checks if data already exists before inserting to avoid duplicates.
    Plan 1.0: also seeds beds inventory.
    Called on application startup.
    """
    from models.database import (
        async_session_factory,
        Patient,
        Doctor,
        Bed,
        ChargeCode,
        InsuranceEligibilityRule,
        User,
    )

    async with async_session_factory() as session:
        # Check if patients already seeded
        result = await session.execute(select(Patient).limit(1))
        if result.scalar_one_or_none() is not None:
            logger.info("📦 Database already seeded — skipping patients/doctors")
        else:
            logger.info("🌱 Seeding database with sample patients and doctors...")

            for p_data in SAMPLE_PATIENTS:
                # Filter out extra fields not in the Patient model
                patient_fields = {
                    k: v for k, v in p_data.items()
                    if k in ("id", "name", "age", "department", "condition")
                }
                patient = Patient(**patient_fields)
                session.add(patient)

            for d_data in SAMPLE_DOCTORS:
                doctor = Doctor(**d_data)
                session.add(doctor)

            await session.commit()
            logger.info(
                f"✅ Seeded {len(SAMPLE_PATIENTS)} patients and "
                f"{len(SAMPLE_DOCTORS)} doctors"
            )

        # Check if beds already seeded
        bed_result = await session.execute(select(Bed).limit(1))
        if bed_result.scalar_one_or_none() is not None:
            logger.info("📦 Beds already seeded — skipping")
        else:
            logger.info("🛏️ Seeding bed inventory (Plan 1.0)...")
            for b_data in SAMPLE_BEDS:
                bed = Bed(**b_data)
                session.add(bed)
            await session.commit()
            logger.info(f"✅ Seeded {len(SAMPLE_BEDS)} beds across all wards")

        # Check if charge codes already seeded
        charge_result = await session.execute(select(ChargeCode).limit(1))
        if charge_result.scalar_one_or_none() is not None:
            logger.info("📦 Charge codes already seeded — skipping")
        else:
            logger.info("💳 Seeding charge code catalog...")
            for c_data in SAMPLE_CHARGE_CODES:
                code = ChargeCode(**c_data)
                session.add(code)
            await session.commit()
            logger.info(f"✅ Seeded {len(SAMPLE_CHARGE_CODES)} charge code mappings")

        # Check if insurance eligibility rules already seeded
        rule_result = await session.execute(select(InsuranceEligibilityRule).limit(1))
        if rule_result.scalar_one_or_none() is not None:
            logger.info("📦 Insurance eligibility rules already seeded — skipping")
        else:
            logger.info("🛡️ Seeding insurance eligibility rules...")
            for r_data in SAMPLE_INSURANCE_ELIGIBILITY_RULES:
                rule = InsuranceEligibilityRule(**r_data)
                session.add(rule)
            await session.commit()
            logger.info(
                f"✅ Seeded {len(SAMPLE_INSURANCE_ELIGIBILITY_RULES)} insurance eligibility rules"
            )

        # Check if users already seeded
        user_result = await session.execute(select(User).limit(1))
        if user_result.scalar_one_or_none() is not None:
            logger.info("📦 Users already seeded — skipping")
        else:
            logger.info("🔐 Seeding default auth users...")
            for u_data in SAMPLE_USERS:
                user = User(
                    username=u_data["username"],
                    email=u_data["email"],
                    password_hash=get_password_hash(u_data["password"]),
                    role=u_data["role"],
                    is_active=True,
                )
                session.add(user)
            await session.commit()
            logger.info(f"✅ Seeded {len(SAMPLE_USERS)} users for RBAC auth")


# Allow running standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed_database())
