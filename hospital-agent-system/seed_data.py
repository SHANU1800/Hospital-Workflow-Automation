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


async def seed_database():
    """
    Seed the database with sample data.

    Checks if data already exists before inserting to avoid duplicates.
    Plan 1.0: also seeds beds inventory.
    Called on application startup.
    """
    from models.database import async_session_factory, Patient, Doctor, Bed

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


# Allow running standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed_database())
