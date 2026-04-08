"""
Database layer for the Hospital Workflow Automation System.

Uses SQLAlchemy 2.0 async engine with PostgreSQL (asyncpg driver).
Defines ORM models for persistent data: Patients, Doctors, Notifications, ExecutionLogs.
"""

from __future__ import annotations

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

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://hospital:hospital@db:5432/hospital_db",
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

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "age": self.age,
            "department": self.department,
            "condition": self.condition,
            "admitted": self.admitted,
            "admitted_at": str(self.admitted_at) if self.admitted_at else None,
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
# Database Initialization
# ─────────────────────────────────────────────

async def init_db():
    """Create all tables. Called on application startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database tables created successfully")


async def drop_db():
    """Drop all tables. Used for testing/reset."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    print("🗑️  Database tables dropped")
