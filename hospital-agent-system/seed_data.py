"""
Seed Data — Populate the database with sample patients and doctors.

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
    {"id": 101, "name": "John Smith", "age": 45, "department": "cardiology", "condition": "Chest pain, elevated troponin"},
    {"id": 102, "name": "Sarah Johnson", "age": 32, "department": "neurology", "condition": "Recurring migraines, MRI pending"},
    {"id": 103, "name": "Mike Davis", "age": 67, "department": "orthopedics", "condition": "Hip fracture from fall"},
    {"id": 104, "name": "Emily Chen", "age": 28, "department": "general", "condition": "Acute appendicitis symptoms"},
    {"id": 105, "name": "Robert Wilson", "age": 55, "department": "cardiology", "condition": "Atrial fibrillation, needs monitoring"},
    {"id": 106, "name": "Lisa Anderson", "age": 41, "department": "oncology", "condition": "Post-chemotherapy observation"},
    {"id": 107, "name": "James Taylor", "age": 73, "department": "pulmonology", "condition": "COPD exacerbation"},
    {"id": 108, "name": "Maria Garcia", "age": 36, "department": "general", "condition": "Severe dehydration, IV fluids needed"},
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
]


async def seed_database():
    """
    Seed the database with sample data.
    
    Checks if data already exists before inserting to avoid duplicates.
    Called on application startup.
    """
    from models.database import async_session_factory, Patient, Doctor

    async with async_session_factory() as session:
        # Check if already seeded
        result = await session.execute(select(Patient).limit(1))
        if result.scalar_one_or_none() is not None:
            logger.info("📦 Database already seeded — skipping")
            return

        logger.info("🌱 Seeding database with sample data...")

        # Insert patients
        for p_data in SAMPLE_PATIENTS:
            patient = Patient(**p_data)
            session.add(patient)

        # Insert doctors
        for d_data in SAMPLE_DOCTORS:
            doctor = Doctor(**d_data)
            session.add(doctor)

        await session.commit()
        logger.info(
            f"✅ Seeded {len(SAMPLE_PATIENTS)} patients and "
            f"{len(SAMPLE_DOCTORS)} doctors"
        )


# Allow running standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed_database())
