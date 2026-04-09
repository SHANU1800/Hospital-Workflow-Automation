"""
Database layer for the Hospital Workflow Automation System.

Uses SQLAlchemy 2.0 async engine with PostgreSQL (asyncpg driver).
Defines ORM models for persistent data:
  Patients, Doctors, Notifications, ExecutionLogs,
  Beds, LabOrders, BillingCases, InsuranceClaims, TriageRecords
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import AsyncGenerator

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    Float,
    JSON,
    func,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# ─────────────────────────────────────────────
# Engine & Session Factory
# ─────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not configured. This project uses external PostgreSQL (Neon). "
        "Set DATABASE_URL in hospital-agent-system/.env before starting the app."
    )

engine = create_async_engine(DATABASE_URL, echo=False, pool_size=10, max_overflow=20)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency-injectable async session generator."""
    async with async_session_factory() as session:
        yield session


# ─────────────────────────────────────────────
# Base Model
# ─────────────────────────────────────────────

class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


# ─────────────────────────────────────────────
# ORM Models
# ─────────────────────────────────────────────

class Patient(Base):
    """Patient records table."""
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    age = Column(Integer, nullable=False)
    department = Column(String(100), nullable=False)
    condition = Column(String(300), nullable=True)
    admitted = Column(Boolean, default=False)
    admitted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    # Triage & urgency
    triage_score = Column(Float, nullable=True)
    urgency_level = Column(String(50), nullable=True)  # critical, urgent, semi-urgent, non-urgent
    # Bed assignment
    bed_id = Column(Integer, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "age": self.age,
            "department": self.department,
            "condition": self.condition,
            "admitted": self.admitted,
            "admitted_at": str(self.admitted_at) if self.admitted_at else None,
            "triage_score": self.triage_score,
            "urgency_level": self.urgency_level,
            "bed_id": self.bed_id,
        }


class Doctor(Base):
    """Doctor records with availability tracking."""
    __tablename__ = "doctors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    department = Column(String(100), nullable=False)
    specialization = Column(String(200), nullable=True)
    available = Column(Boolean, default=True)
    assigned_patient_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "department": self.department,
            "specialization": self.specialization,
            "available": self.available,
            "assigned_patient_id": self.assigned_patient_id,
        }


class User(Base):
    """Application users for JWT authentication and RBAC."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    email = Column(String(200), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="staff")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": str(self.created_at) if self.created_at else None,
            "updated_at": str(self.updated_at) if self.updated_at else None,
        }


class UserDoctorLink(Base):
    """Mapping between auth user account and doctor profile record."""
    __tablename__ = "user_doctor_links"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, unique=True, index=True)
    doctor_id = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "doctor_id": self.doctor_id,
            "created_at": str(self.created_at) if self.created_at else None,
            "updated_at": str(self.updated_at) if self.updated_at else None,
        }


class Notification(Base):
    """Notification log — every alert/notification sent is recorded here."""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    message = Column(Text, nullable=False)
    recipient = Column(String(200), nullable=True)
    channel = Column(String(50), default="system")  # system, email, sms
    status = Column(String(50), default="sent")
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "message": self.message,
            "recipient": self.recipient,
            "channel": self.channel,
            "status": self.status,
            "created_at": str(self.created_at),
        }


class ExecutionRecord(Base):
    """Persistent execution log for auditing workflow runs."""
    __tablename__ = "execution_logs"

    id = Column(Integer, primary_key=True, index=True)
    execution_id = Column(String(100), unique=True, index=True)
    plan_id = Column(String(100), index=True)
    event = Column(String(200), nullable=False)
    status = Column(String(50), default="running")
    log_data = Column(JSON, nullable=True)  # Full ExecutionLog as JSON
    started_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)
    total_duration_ms = Column(Float, nullable=True)


# ─────────────────────────────────────────────
# Plan 1.0 — New Domain Models
# ─────────────────────────────────────────────

class Bed(Base):
    """Hospital bed inventory and status tracking."""
    __tablename__ = "beds"

    id = Column(Integer, primary_key=True, index=True)
    ward = Column(String(100), nullable=False)          # ICU, General, Cardiology, etc.
    bed_number = Column(String(20), nullable=False)
    status = Column(String(50), default="available")    # available, occupied, cleaning, reserved
    patient_id = Column(Integer, nullable=True)
    reserved_for_patient_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ward": self.ward,
            "bed_number": self.bed_number,
            "status": self.status,
            "patient_id": self.patient_id,
            "reserved_for_patient_id": self.reserved_for_patient_id,
        }


class TriageRecord(Base):
    """Triage assessments — one per admission/visit."""
    __tablename__ = "triage_records"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, nullable=False, index=True)
    score = Column(Float, nullable=False)               # 0–100
    urgency_level = Column(String(50), nullable=False)  # critical/urgent/semi-urgent/non-urgent
    chief_complaint = Column(Text, nullable=True)
    vitals = Column(JSON, nullable=True)                # HR, BP, SpO2, temp, RR
    pathway_recommendation = Column(String(200), nullable=True)
    assessed_at = Column(DateTime, server_default=func.now())
    assessed_by = Column(String(200), nullable=True)    # triage nurse/system

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "score": self.score,
            "urgency_level": self.urgency_level,
            "chief_complaint": self.chief_complaint,
            "vitals": self.vitals,
            "pathway_recommendation": self.pathway_recommendation,
            "assessed_at": str(self.assessed_at),
        }


class LabOrder(Base):
    """Lab test orders and their lifecycle."""
    __tablename__ = "lab_orders"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, nullable=False, index=True)
    test_name = Column(String(200), nullable=False)
    ordered_by = Column(String(200), nullable=True)     # doctor name/id
    status = Column(String(50), default="ordered")      # ordered, sample_collected, in_lab, resulted, critical
    priority = Column(String(50), default="routine")    # stat, urgent, routine
    result = Column(JSON, nullable=True)
    is_critical = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    ordered_at = Column(DateTime, server_default=func.now())
    resulted_at = Column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "test_name": self.test_name,
            "ordered_by": self.ordered_by,
            "status": self.status,
            "priority": self.priority,
            "result": self.result,
            "is_critical": self.is_critical,
            "notes": self.notes,
            "ordered_at": str(self.ordered_at),
            "resulted_at": str(self.resulted_at) if self.resulted_at else None,
        }


class BillingCase(Base):
    """Billing cases tracking charges and invoices."""
    __tablename__ = "billing_cases"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, nullable=False, index=True)
    status = Column(String(50), default="open")         # open, invoiced, submitted, paid, closed
    services = Column(JSON, nullable=True)              # list of service charges
    estimated_total = Column(Float, nullable=True)
    invoice_number = Column(String(100), nullable=True)
    insurance_claim_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "status": self.status,
            "services": self.services,
            "estimated_total": self.estimated_total,
            "invoice_number": self.invoice_number,
            "insurance_claim_id": self.insurance_claim_id,
            "created_at": str(self.created_at),
        }


class InsuranceClaim(Base):
    """Insurance claim state machine."""
    __tablename__ = "insurance_claims"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, nullable=False, index=True)
    billing_case_id = Column(Integer, nullable=True)
    insurance_provider = Column(String(200), nullable=True)
    plan_type = Column(String(100), nullable=True)
    member_id = Column(String(100), nullable=True)
    status = Column(String(50), default="pending")      # pending, submitted, approved, rejected, paid
    claim_amount = Column(Float, nullable=True)
    approved_amount = Column(Float, nullable=True)
    prior_auth_number = Column(String(100), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    eligibility_verified = Column(Boolean, default=False)
    submitted_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "billing_case_id": self.billing_case_id,
            "insurance_provider": self.insurance_provider,
            "plan_type": self.plan_type,
            "member_id": self.member_id,
            "status": self.status,
            "claim_amount": self.claim_amount,
            "approved_amount": self.approved_amount,
            "prior_auth_number": self.prior_auth_number,
            "eligibility_verified": self.eligibility_verified,
        }


class PatientInsuranceProfile(Base):
    """Saved insurance details for each patient, reusable across claim submissions."""
    __tablename__ = "patient_insurance_profiles"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, nullable=False, unique=True, index=True)
    insurance_provider = Column(String(200), nullable=True)
    plan_type = Column(String(100), nullable=True)
    member_id = Column(String(100), nullable=True)
    policy_number = Column(String(100), nullable=True)
    group_number = Column(String(100), nullable=True)
    updated_at = Column(DateTime, onupdate=func.now(), server_default=func.now(), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "insurance_provider": self.insurance_provider,
            "plan_type": self.plan_type,
            "member_id": self.member_id,
            "policy_number": self.policy_number,
            "group_number": self.group_number,
            "updated_at": str(self.updated_at) if self.updated_at else None,
        }


class ChargeCode(Base):
    """Service to billing code lookup table."""
    __tablename__ = "charge_codes"

    id = Column(Integer, primary_key=True, index=True)
    service_key = Column(String(100), nullable=False, unique=True, index=True)
    service_name = Column(String(200), nullable=False)
    code = Column(String(50), nullable=False)
    amount = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "service_key": self.service_key,
            "service_name": self.service_name,
            "code": self.code,
            "amount": self.amount,
            "is_active": self.is_active,
        }


class InsuranceEligibilityRule(Base):
    """Insurance eligibility and coverage rules by provider + plan."""
    __tablename__ = "insurance_eligibility_rules"

    id = Column(Integer, primary_key=True, index=True)
    insurance_provider = Column(String(200), nullable=False, index=True)
    plan_type = Column(String(100), nullable=False, index=True)
    coverage_percentage = Column(Float, nullable=False, default=0.0)
    covered_services = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "insurance_provider": self.insurance_provider,
            "plan_type": self.plan_type,
            "coverage_percentage": self.coverage_percentage,
            "covered_services": self.covered_services or [],
            "is_active": self.is_active,
        }


class DoctorAvailabilitySlot(Base):
    """Fixed-size appointment slots for each doctor."""
    __tablename__ = "doctor_availability_slots"

    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, nullable=False, index=True)
    department = Column(String(100), nullable=False, index=True)
    slot_start = Column(DateTime, nullable=False, index=True)
    slot_end = Column(DateTime, nullable=False)
    is_booked = Column(Boolean, default=False)
    booked_patient_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "doctor_id": self.doctor_id,
            "department": self.department,
            "slot_start": str(self.slot_start),
            "slot_end": str(self.slot_end),
            "is_booked": self.is_booked,
            "booked_patient_id": self.booked_patient_id,
        }


class Appointment(Base):
    """Booked appointment record with lifecycle status for patient and doctor flows."""
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, nullable=False, index=True)
    doctor_id = Column(Integer, nullable=False, index=True)
    department = Column(String(100), nullable=False, index=True)
    slot_id = Column(Integer, nullable=False, index=True)
    appointment_start = Column(DateTime, nullable=False, index=True)
    appointment_end = Column(DateTime, nullable=False)
    status = Column(String(50), default="confirmed")  # confirmed, completed, cancelled
    notes = Column(Text, nullable=True)
    confirmation_code = Column(String(100), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "doctor_id": self.doctor_id,
            "department": self.department,
            "slot_id": self.slot_id,
            "appointment_start": str(self.appointment_start),
            "appointment_end": str(self.appointment_end),
            "status": self.status,
            "notes": self.notes,
            "confirmation_code": self.confirmation_code,
            "created_at": str(self.created_at),
        }


# ─────────────────────────────────────────────
# Database Initialization
# ─────────────────────────────────────────────

async def init_db():
    """Create all tables. Called on application startup.

    Implements retry logic with exponential backoff to wait for database
    to be ready, since Docker service health checks don't guarantee that
    the database is accepting async connections immediately.
    """
    max_retries = 10
    retry_delay = 1  # Start with 1 second

    for attempt in range(max_retries):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            print("✅ Database tables created successfully")
            return
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                print(f"⚠️  Database connection failed (attempt {attempt + 1}/{max_retries}). "
                      f"Retrying in {wait_time}s... Error: {str(e)[:100]}")
                await asyncio.sleep(wait_time)
            else:
                print(f"❌ Failed to connect to database after {max_retries} attempts")
                raise


async def drop_db():
    """Drop all tables. Used for testing/reset."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    print("🗑️  Database tables dropped")
