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
from datetime import datetime, timedelta

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
    {"name": "Dr. Amanda Hart", "department": "cardiology", "specialization": "Interventional Cardiology"},
    {"name": "Dr. James Foster", "department": "cardiology", "specialization": "Electrophysiology"},
    {"name": "Dr. Sarah Kim", "department": "neurology", "specialization": "Stroke & Vascular Neurology"},
    {"name": "Dr. David Patel", "department": "neurology", "specialization": "Epilepsy"},
    {"name": "Dr. Michael Ross", "department": "orthopedics", "specialization": "Joint Replacement"},
    {"name": "Dr. Jennifer Liu", "department": "general", "specialization": "Internal Medicine"},
    {"name": "Dr. Robert Chang", "department": "general", "specialization": "Emergency Medicine"},
    {"name": "Dr. Emily Watson", "department": "oncology", "specialization": "Medical Oncology"},
    {"name": "Dr. Andrew Bell", "department": "pulmonology", "specialization": "Critical Care"},
    {"name": "Dr. Maria Santos", "department": "general", "specialization": "Family Medicine"},
    {"name": "Dr. Kevin Chen", "department": "icu", "specialization": "Intensive Care"},
    {"name": "Dr. Patricia Moore", "department": "icu", "specialization": "Critical Care Medicine"},
]

REQUIRED_DOCTOR_DEPARTMENTS = [
    "cardiology",
    "neurology",
    "orthopedics",
    "general",
    "oncology",
    "pulmonology",
    "icu",
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
    {
        "username": "patient_user",
        "email": "patient@hospital.local",
        "password": "PatientUser@123",
        "role": "patient",
    },
]


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _build_execution_log(event: str, agent: str, task: str, status: str = "completed") -> dict:
    now = datetime.utcnow()
    started = now - timedelta(seconds=2)
    completed = now - timedelta(seconds=1)
    return {
        "execution_id": f"seed-{event}-{int(now.timestamp())}",
        "plan_id": f"seed-plan-{event}",
        "event": event,
        "status": status,
        "steps": [
            {
                "step_number": 1,
                "task_id": f"seed-task-{event}",
                "task": task,
                "agent": agent,
                "status": "completed",
                "started_at": _iso(started),
                "completed_at": _iso(completed),
                "duration_ms": 650.0,
                "tool_calls": [],
                "a2a_messages": [],
                "result": {"seeded": True, "event": event},
                "error": None,
            }
        ],
        "started_at": _iso(started),
        "completed_at": _iso(completed),
        "total_duration_ms": 1000.0,
    }


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
        DoctorAvailabilitySlot,
        Appointment,
        TriageRecord,
        LabOrder,
        BillingCase,
        InsuranceClaim,
        PatientInsuranceProfile,
        Notification,
        ExecutionRecord,
        UserDoctorLink,
    )

    async with async_session_factory() as session:
        # Check if patients already seeded
        result = await session.execute(select(Patient).limit(1))
        if result.scalar_one_or_none() is not None:
            logger.info("📦 Patients already seeded — skipping patient insert")
        else:
            logger.info("🌱 Seeding database with sample patients...")

            for p_data in SAMPLE_PATIENTS:
                # Filter out extra fields not in the Patient model
                patient_fields = {
                    k: v for k, v in p_data.items()
                    if k in ("id", "name", "age", "department", "condition")
                }
                patient = Patient(**patient_fields)
                session.add(patient)

            await session.commit()
            logger.info(f"✅ Seeded {len(SAMPLE_PATIENTS)} patients")

        # Ensure doctor catalog exists and covers each required department
        existing_doctors_result = await session.execute(select(Doctor))
        existing_doctors = existing_doctors_result.scalars().all()
        existing_doctor_names = {d.name.strip().lower() for d in existing_doctors}

        inserted_sample_doctors = 0
        for d_data in SAMPLE_DOCTORS:
            normalized_name = d_data["name"].strip().lower()
            if normalized_name in existing_doctor_names:
                continue
            session.add(Doctor(**d_data))
            existing_doctor_names.add(normalized_name)
            inserted_sample_doctors += 1

        if inserted_sample_doctors:
            await session.commit()
            logger.info(f"✅ Seeded {inserted_sample_doctors} missing sample doctors")
        else:
            logger.info("📦 Sample doctors already seeded — skipping")

        # Add at least one doctor for any missing department
        department_rows = await session.execute(select(Doctor.department))
        existing_departments = {
            (row[0] or "").strip().lower() for row in department_rows.all() if row[0]
        }

        patient_department_rows = await session.execute(select(Patient.department))
        patient_departments = {
            (row[0] or "").strip().lower() for row in patient_department_rows.all() if row[0]
        }
        required_departments = sorted(set(REQUIRED_DOCTOR_DEPARTMENTS).union(patient_departments))

        added_department_doctors = 0
        for department in required_departments:
            if department in existing_departments:
                continue

            generated_name = f"Dr. Auto {department.title()}"
            suffix = 1
            while generated_name.strip().lower() in existing_doctor_names:
                suffix += 1
                generated_name = f"Dr. Auto {department.title()} {suffix}"

            session.add(
                Doctor(
                    name=generated_name,
                    department=department,
                    specialization=f"{department.title()} Specialist",
                    available=True,
                )
            )
            existing_doctor_names.add(generated_name.strip().lower())
            added_department_doctors += 1

        if added_department_doctors:
            await session.commit()
            logger.info(
                f"✅ Added {added_department_doctors} doctors to cover missing departments"
            )
        else:
            logger.info("📦 Doctors already cover all required departments")

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

        # Ensure default users exist (idempotent insert of missing usernames)
        existing_users_result = await session.execute(select(User.username))
        existing_usernames = {row[0] for row in existing_users_result.all()}

        missing_users = [u for u in SAMPLE_USERS if u["username"] not in existing_usernames]
        if not missing_users:
            logger.info("📦 Users already seeded — skipping")
        else:
            logger.info("🔐 Seeding missing default auth users...")
            for u_data in missing_users:
                user = User(
                    username=u_data["username"],
                    email=u_data["email"],
                    password_hash=get_password_hash(u_data["password"]),
                    role=u_data["role"],
                    is_active=True,
                )
                session.add(user)
            await session.commit()
            logger.info(f"✅ Seeded {len(missing_users)} missing users for RBAC auth")

        # Ensure doctor account is linked to a doctor profile for dashboard auto-fill
        link_result = await session.execute(select(UserDoctorLink).limit(1))
        if link_result.scalar_one_or_none() is not None:
            logger.info("📦 User-doctor links already seeded — skipping")
        else:
            doctor_user_result = await session.execute(select(User).where(User.username == "doctor_user"))
            doctor_user = doctor_user_result.scalar_one_or_none()
            first_doctor_result = await session.execute(select(Doctor).order_by(Doctor.id.asc()))
            first_doctor = first_doctor_result.scalars().first()

            if doctor_user is not None and first_doctor is not None:
                session.add(UserDoctorLink(user_id=doctor_user.id, doctor_id=first_doctor.id))
                await session.commit()
                logger.info(
                    f"✅ Seeded user-doctor link: user #{doctor_user.id} -> doctor #{first_doctor.id}"
                )
            else:
                logger.info("⚠️ Unable to seed user-doctor link (missing doctor_user or doctor record)")

        # Seed reusable patient insurance profiles for demo claims
        profile_result = await session.execute(select(PatientInsuranceProfile).limit(1))
        if profile_result.scalar_one_or_none() is not None:
            logger.info("📦 Insurance profiles already seeded — skipping")
        else:
            logger.info("🪪 Seeding patient insurance profiles...")
            for p_data in SAMPLE_PATIENTS[:8]:
                session.add(
                    PatientInsuranceProfile(
                        patient_id=p_data["id"],
                        insurance_provider=p_data.get("insurance_provider", "default"),
                        plan_type=p_data.get("plan_type", "general"),
                        member_id=p_data.get("member_id", ""),
                        policy_number=f"POL-{p_data['id']}",
                        group_number=f"GRP-{p_data['id']}",
                    )
                )
            await session.commit()
            logger.info("✅ Seeded patient insurance profiles")

        # Seed triage records for dashboard/demo history
        triage_result = await session.execute(select(TriageRecord).limit(1))
        if triage_result.scalar_one_or_none() is not None:
            logger.info("📦 Triage records already seeded — skipping")
        else:
            logger.info("🩺 Seeding triage records...")
            triage_rows = [
                (101, 88.0, "urgent", "Chest pain", {"bp": "150/95", "hr": 110}, "cardiology_fast_track"),
                (102, 62.0, "semi-urgent", "Migraine", {"bp": "130/85", "hr": 88}, "neurology_consult"),
                (109, 96.0, "critical", "Sepsis signs", {"bp": "85/50", "hr": 132, "spo2": 89}, "icu_emergency"),
                (104, 55.0, "semi-urgent", "Abdominal pain", {"bp": "125/80", "hr": 92}, "general_observation"),
            ]
            for patient_id, score, urgency, complaint, vitals, pathway in triage_rows:
                session.add(
                    TriageRecord(
                        patient_id=patient_id,
                        score=score,
                        urgency_level=urgency,
                        chief_complaint=complaint,
                        vitals=vitals,
                        pathway_recommendation=pathway,
                        assessed_by="seed_system",
                    )
                )
            await session.commit()
            logger.info("✅ Seeded triage records")

        # Build doctor map for slot/appointment seeding
        doctors_result = await session.execute(select(Doctor))
        doctors = doctors_result.scalars().all()
        dept_doctor = {}
        for d in doctors:
            dept = (d.department or "").strip().lower()
            if dept and dept not in dept_doctor:
                dept_doctor[dept] = d

        # Seed availability slots
        slot_result = await session.execute(select(DoctorAvailabilitySlot).limit(1))
        if slot_result.scalar_one_or_none() is not None:
            logger.info("📦 Doctor availability slots already seeded — skipping")
        else:
            logger.info("🗓️ Seeding doctor availability slots...")
            now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
            slot_rows = []
            for offset_days in range(0, 4):
                day_base = now + timedelta(days=offset_days)
                for dept in ["cardiology", "neurology", "orthopedics", "general", "oncology", "pulmonology", "icu"]:
                    doc = dept_doctor.get(dept)
                    if not doc:
                        continue
                    for hour in [9, 10, 11, 14, 15]:
                        slot_start = day_base.replace(hour=hour)
                        slot_end = slot_start + timedelta(minutes=30)
                        slot_rows.append(
                            DoctorAvailabilitySlot(
                                doctor_id=doc.id,
                                department=dept,
                                slot_start=slot_start,
                                slot_end=slot_end,
                                is_booked=False,
                            )
                        )
            session.add_all(slot_rows)
            await session.commit()
            logger.info(f"✅ Seeded {len(slot_rows)} availability slots")

        # Seed appointments using earliest available slots per patient department
        appt_result = await session.execute(select(Appointment).limit(1))
        if appt_result.scalar_one_or_none() is not None:
            logger.info("📦 Appointments already seeded — skipping")
        else:
            logger.info("🧾 Seeding appointments...")
            appointments_created = 0
            patients_result = await session.execute(select(Patient).order_by(Patient.id.asc()))
            patients = patients_result.scalars().all()

            status_cycle = ["confirmed", "completed", "cancelled", "confirmed", "completed"]
            for idx, patient in enumerate(patients[:8]):
                dept = (patient.department or "general").strip().lower()
                doc = dept_doctor.get(dept) or next(iter(dept_doctor.values()), None)
                if not doc:
                    continue

                slot_query = await session.execute(
                    select(DoctorAvailabilitySlot)
                    .where(
                        DoctorAvailabilitySlot.doctor_id == doc.id,
                        DoctorAvailabilitySlot.is_booked.is_(False),
                    )
                    .order_by(DoctorAvailabilitySlot.slot_start.asc())
                )
                slot = slot_query.scalars().first()
                if not slot:
                    continue

                slot.is_booked = True
                slot.booked_patient_id = patient.id

                status_value = status_cycle[idx % len(status_cycle)]
                appt = Appointment(
                    patient_id=patient.id,
                    doctor_id=doc.id,
                    department=dept,
                    slot_id=slot.id,
                    appointment_start=slot.slot_start,
                    appointment_end=slot.slot_end,
                    status=status_value,
                    notes=f"Demo appointment for {patient.name}",
                    confirmation_code=f"CONF-{patient.id}-{slot.id}",
                )
                session.add(appt)
                appointments_created += 1

            await session.commit()
            logger.info(f"✅ Seeded {appointments_created} appointments")

        # Seed lab orders with mixed statuses
        lab_result = await session.execute(select(LabOrder).limit(1))
        if lab_result.scalar_one_or_none() is not None:
            logger.info("📦 Lab orders already seeded — skipping")
        else:
            logger.info("🧪 Seeding lab orders...")
            lab_rows = [
                LabOrder(patient_id=101, test_name="Troponin", ordered_by="Dr. Amanda Hart", status="resulted", priority="urgent", result={"finding": "elevated", "value": "1.2 ng/mL"}, is_critical=False),
                LabOrder(patient_id=102, test_name="MRI Brain", ordered_by="Dr. Sarah Kim", status="in_lab", priority="routine", result=None, is_critical=False),
                LabOrder(patient_id=109, test_name="Blood Culture", ordered_by="Dr. Kevin Chen", status="critical", priority="stat", result={"finding": "sepsis marker high"}, is_critical=True),
                LabOrder(patient_id=104, test_name="CBC", ordered_by="Dr. Jennifer Liu", status="sample_collected", priority="urgent", result=None, is_critical=False),
            ]
            session.add_all(lab_rows)
            await session.commit()
            logger.info("✅ Seeded lab orders")

        # Seed billing cases and linked claims
        billing_result = await session.execute(select(BillingCase).limit(1))
        if billing_result.scalar_one_or_none() is not None:
            logger.info("📦 Billing cases already seeded — skipping")
        else:
            logger.info("💼 Seeding billing cases and insurance claims...")
            billing_rows = [
                BillingCase(patient_id=101, status="open", services=[{"service": "admission", "amount": 5000}, {"service": "doctor_consult", "amount": 2000}], estimated_total=7000.0, invoice_number="INV-101"),
                BillingCase(patient_id=102, status="submitted", services=[{"service": "lab_cbc", "amount": 800}, {"service": "doctor_consult", "amount": 2000}], estimated_total=2800.0, invoice_number="INV-102"),
                BillingCase(patient_id=109, status="invoiced", services=[{"service": "icu_day", "amount": 15000}, {"service": "lab_metabolic", "amount": 1200}], estimated_total=16200.0, invoice_number="INV-109"),
                BillingCase(patient_id=104, status="paid", services=[{"service": "general_day", "amount": 5000}, {"service": "medication", "amount": 500}], estimated_total=5500.0, invoice_number="INV-104"),
            ]
            session.add_all(billing_rows)
            await session.flush()

            claim_rows = [
                InsuranceClaim(patient_id=102, billing_case_id=billing_rows[1].id, insurance_provider="Aetna", plan_type="standard", member_id="AE-102-2024", status="submitted", claim_amount=2800.0, approved_amount=0.0, eligibility_verified=True),
                InsuranceClaim(patient_id=109, billing_case_id=billing_rows[2].id, insurance_provider="Medicare", plan_type="senior", member_id="MC-109-2024", status="approved", claim_amount=16200.0, approved_amount=12000.0, eligibility_verified=True),
                InsuranceClaim(patient_id=104, billing_case_id=billing_rows[3].id, insurance_provider="Cigna", plan_type="standard", member_id="CI-104-2024", status="paid", claim_amount=5500.0, approved_amount=4800.0, eligibility_verified=True),
                InsuranceClaim(patient_id=101, billing_case_id=billing_rows[0].id, insurance_provider="BlueCross", plan_type="premium", member_id="BC-101-2024", status="pending", claim_amount=7000.0, approved_amount=0.0, eligibility_verified=False),
            ]
            session.add_all(claim_rows)
            await session.flush()

            # Link billing cases to their claims where available
            claim_map = {c.billing_case_id: c.id for c in claim_rows if c.billing_case_id}
            for case in billing_rows:
                if case.id in claim_map:
                    case.insurance_claim_id = claim_map[case.id]

            await session.commit()
            logger.info("✅ Seeded billing and insurance claims")

        # Seed notifications for dashboard visibility
        notif_result = await session.execute(select(Notification).limit(1))
        if notif_result.scalar_one_or_none() is not None:
            logger.info("📦 Notifications already seeded — skipping")
        else:
            logger.info("🔔 Seeding notifications...")
            notifications = [
                Notification(message="Patient 101 admitted and assigned to cardiology care team.", recipient="nursing_station", channel="system", status="sent"),
                Notification(message="Critical lab result for patient 109. Immediate review required.", recipient="attending_physician", channel="system", status="sent"),
                Notification(message="Insurance claim #2 approved for patient 109.", recipient="billing_department", channel="system", status="sent"),
                Notification(message="Appointment reminder: patient 102 at 10:00 AM.", recipient="patient_102", channel="system", status="sent"),
            ]
            session.add_all(notifications)
            await session.commit()
            logger.info("✅ Seeded notifications")

        # Seed execution logs to showcase timeline/audit pages
        exec_result = await session.execute(select(ExecutionRecord).limit(1))
        if exec_result.scalar_one_or_none() is not None:
            logger.info("📦 Execution logs already seeded — skipping")
        else:
            logger.info("🧠 Seeding execution logs...")
            now = datetime.utcnow()
            records = [
                ExecutionRecord(
                    execution_id=f"seed-exec-admit-{int(now.timestamp())}",
                    plan_id="seed-plan-admit",
                    event="patient_admitted",
                    status="completed",
                    log_data=_build_execution_log("patient_admitted", "SupervisorAgent", "supervise_admission", "completed"),
                    started_at=now - timedelta(minutes=30),
                    completed_at=now - timedelta(minutes=29, seconds=55),
                    total_duration_ms=5000.0,
                ),
                ExecutionRecord(
                    execution_id=f"seed-exec-lab-{int(now.timestamp())}",
                    plan_id="seed-plan-lab",
                    event="lab_results_ready",
                    status="completed",
                    log_data=_build_execution_log("lab_results_ready", "LabAgent", "check_lab_results", "completed"),
                    started_at=now - timedelta(minutes=20),
                    completed_at=now - timedelta(minutes=19, seconds=56),
                    total_duration_ms=4000.0,
                ),
                ExecutionRecord(
                    execution_id=f"seed-exec-doctor-{int(now.timestamp())}",
                    plan_id="seed-plan-doctor-followup",
                    event="doctor_followup_workflow",
                    status="completed",
                    log_data=_build_execution_log("doctor_followup_workflow", "SupervisorAgent", "coordinate_multi_domain", "completed"),
                    started_at=now - timedelta(minutes=10),
                    completed_at=now - timedelta(minutes=9, seconds=53),
                    total_duration_ms=7000.0,
                ),
            ]
            session.add_all(records)
            await session.commit()
            logger.info("✅ Seeded execution logs")


# Allow running standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed_database())
