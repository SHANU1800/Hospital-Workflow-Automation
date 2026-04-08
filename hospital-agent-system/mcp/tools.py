"""
MCP Tools — Concrete tool implementations.

These tools are the ONLY way agents interact with external systems.
Each tool is registered with the MCP ToolRegistry on import.

Tools:
- get_patient_data: Fetch patient record from PostgreSQL
- assign_doctor: Find and assign an available doctor
- send_notification: Log and send notifications
- get_patient_department: Quick lookup for patient department
- check_doctor_availability: Check if doctors are available in a department
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select, update

from models.database import async_session_factory, Patient, Doctor, Notification
from mcp.tool_registry import register_tool

logger = logging.getLogger("mcp.tools")


# ─────────────────────────────────────────────
# Tool: get_patient_data
# ─────────────────────────────────────────────

@register_tool(
    name="get_patient_data",
    description="Fetch a patient record from the database by patient ID",
    parameters={"patient_id": "Integer - the unique patient identifier"},
)
async def get_patient_data(patient_id: int) -> dict:
    """
    Retrieve a patient record from PostgreSQL.
    
    Returns the patient data as a dict, or an error dict if not found.
    This tool is typically called by the DataAgent during admission workflows.
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(Patient).where(Patient.id == patient_id)
        )
        patient = result.scalar_one_or_none()

        if patient is None:
            logger.warning(f"Patient {patient_id} not found in database")
            return {"error": f"Patient {patient_id} not found", "found": False}

        # Mark patient as admitted
        await session.execute(
            update(Patient)
            .where(Patient.id == patient_id)
            .values(admitted=True, admitted_at=datetime.utcnow())
        )
        await session.commit()

        data = patient.to_dict()
        data["found"] = True
        logger.info(f"📋 Patient data retrieved: {data['name']} (ID: {patient_id})")
        return data


# ─────────────────────────────────────────────
# Tool: assign_doctor
# ─────────────────────────────────────────────

@register_tool(
    name="assign_doctor",
    description="Find and assign an available doctor in the specified department",
    parameters={
        "department": "String - the medical department",
        "patient_id": "Integer - patient to assign (optional)",
    },
)
async def assign_doctor(department: str, patient_id: int = 0) -> dict:
    """
    Find an available doctor in the given department and assign them.
    
    The tool:
    1. Queries for available doctors in the department
    2. Picks the first available doctor
    3. Marks them as unavailable and assigns the patient
    4. Returns the assignment details
    
    If no doctors are available, returns an error dict.
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(Doctor).where(
                Doctor.department == department.lower(),
                Doctor.available == True,  # noqa: E712
            )
        )
        doctor = result.scalars().first()

        if doctor is None:
            # Try a general/any department fallback
            result = await session.execute(
                select(Doctor).where(Doctor.available == True)  # noqa: E712
            )
            doctor = result.scalars().first()
            
            if doctor is None:
                logger.warning(f"No available doctors in {department} or any department")
                return {
                    "error": f"No available doctors in {department}",
                    "assigned": False,
                }

        # Assign the doctor
        await session.execute(
            update(Doctor)
            .where(Doctor.id == doctor.id)
            .values(available=False, assigned_patient_id=patient_id)
        )
        await session.commit()

        assignment = {
            "assigned": True,
            "doctor_id": doctor.id,
            "doctor_name": doctor.name,
            "department": doctor.department,
            "specialization": doctor.specialization,
            "patient_id": patient_id,
        }
        logger.info(f"👨‍⚕️ Doctor assigned: {doctor.name} -> Patient {patient_id}")
        return assignment


# ─────────────────────────────────────────────
# Tool: send_notification
# ─────────────────────────────────────────────

@register_tool(
    name="send_notification",
    description="Send a notification/alert and log it to the database",
    parameters={
        "message": "String - notification message content",
        "recipient": "String - who should receive it (optional)",
        "channel": "String - delivery channel: system, email, sms (optional)",
    },
)
async def send_notification(
    message: str,
    recipient: str = "staff",
    channel: str = "system",
) -> dict:
    """
    Log and "send" a notification.
    
    In a production system, this would integrate with email/SMS services.
    For this demo, it persists the notification to PostgreSQL.
    """
    async with async_session_factory() as session:
        notification = Notification(
            message=message,
            recipient=recipient,
            channel=channel,
            status="sent",
        )
        session.add(notification)
        await session.commit()
        await session.refresh(notification)

        result = notification.to_dict()
        logger.info(f"📢 Notification sent: [{channel}] {recipient} <- {message[:80]}")
        return result


# ─────────────────────────────────────────────
# Tool: get_patient_department
# ─────────────────────────────────────────────

@register_tool(
    name="get_patient_department",
    description="Quick lookup for a patient's department",
    parameters={"patient_id": "Integer - the patient ID"},
)
async def get_patient_department(patient_id: int) -> dict:
    """Quick lookup returning just the department for a patient."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Patient.department, Patient.name).where(Patient.id == patient_id)
        )
        row = result.first()
        if row is None:
            return {"error": f"Patient {patient_id} not found", "found": False}
        return {
            "patient_id": patient_id,
            "department": row[0],
            "patient_name": row[1],
            "found": True,
        }


# ─────────────────────────────────────────────
# Tool: check_doctor_availability
# ─────────────────────────────────────────────

@register_tool(
    name="check_doctor_availability",
    description="Check how many doctors are available in a department",
    parameters={"department": "String - the medical department"},
)
async def check_doctor_availability(department: str) -> dict:
    """Check doctor availability in a given department."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Doctor).where(
                Doctor.department == department.lower(),
                Doctor.available == True,  # noqa: E712
            )
        )
        doctors = result.scalars().all()
        return {
            "department": department,
            "available_count": len(doctors),
            "doctors": [d.to_dict() for d in doctors],
        }
