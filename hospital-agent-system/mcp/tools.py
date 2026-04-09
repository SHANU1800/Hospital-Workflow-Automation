"""
MCP Tools — Concrete tool implementations.

These tools are the ONLY way agents interact with external systems.
Each tool is registered with the MCP ToolRegistry on import.

Plan 1.0 Tool Catalog (31 tools):
──────────────────────────────────
Core Platform (5):
  get_patient_data, assign_doctor, send_notification,
  get_patient_department, check_doctor_availability

Triage (5):
  calculate_triage_score, classify_emergency_level,
  prioritize_waitlist, flag_critical_case, record_triage_assessment

Bed Management (6):
  get_bed_inventory, find_best_bed_match, reserve_bed, assign_bed,
  release_bed, get_occupancy_snapshot

Billing Basics (8):
  initiate_billing_case, map_services_to_charge_codes,
  calculate_estimated_bill, generate_itemized_invoice,
  create_claim, validate_claim, submit_claim, track_claim_status

Insurance (1):
    get_insurance_eligibility

Lab Critical Path (6):
  create_lab_order, collect_sample, track_sample_status,
  get_lab_result, flag_critical_lab_result, attach_lab_report
"""

from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select, update

from models.database import (
    async_session_factory,
    Patient,
    Doctor,
    Notification,
    Bed,
    TriageRecord,
    LabOrder,
    BillingCase,
    InsuranceClaim,
    ChargeCode,
    InsuranceEligibilityRule,
    Appointment,
    DoctorAvailabilitySlot,
)
from mcp.tool_registry import register_tool

logger = logging.getLogger("mcp.tools")


# ═══════════════════════════════════════════════════════
# SECTION 1 — CORE PLATFORM TOOLS (5)
# ═══════════════════════════════════════════════════════

@register_tool(
    name="get_patient_data",
    description="Fetch a patient record from the database by patient ID",
    parameters={"patient_id": "Integer - the unique patient identifier"},
)
async def get_patient_data(patient_id: int) -> dict:
    """Retrieve a patient record from PostgreSQL and mark as admitted."""
    async with async_session_factory() as session:
        result = await session.execute(select(Patient).where(Patient.id == patient_id))
        patient = result.scalar_one_or_none()

        if patient is None:
            logger.warning(f"Patient {patient_id} not found in database")
            return {"error": f"Patient {patient_id} not found", "found": False}

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


@register_tool(
    name="assign_doctor",
    description="Find and assign an available doctor in the specified department",
    parameters={
        "department": "String - the medical department",
        "patient_id": "Integer - patient to assign (optional)",
    },
)
async def assign_doctor(department: str, patient_id: int = 0) -> dict:
    """Find an available doctor in the given department and assign them."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Doctor).where(
                Doctor.department == department.lower(),
                Doctor.available == True,  # noqa: E712
            )
        )
        doctor = result.scalars().first()

        if doctor is None:
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
    """Log and send a notification, persisted to PostgreSQL."""
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


# ═══════════════════════════════════════════════════════
# SECTION 2 — TRIAGE TOOLS (5)
# ═══════════════════════════════════════════════════════

@register_tool(
    name="calculate_triage_score",
    description="Calculate triage severity score from patient vitals and complaint",
    parameters={
        "patient_id": "Integer - patient identifier",
        "vitals": "Dict - HR, BP, SpO2, temp, RR values",
        "chief_complaint": "String - primary presenting complaint",
        "age": "Integer - patient age (optional)",
    },
)
async def calculate_triage_score(
    patient_id: int,
    vitals: dict,
    chief_complaint: str,
    age: int = 0,
) -> dict:
    """
    Rule-based triage scoring (0-100, higher = more severe).

    Clinical rules:
    - SpO2 < 90  -> +40 points (critical hypoxia)
    - HR > 130 or < 40  -> +30 points
    - Systolic BP < 90  -> +30 points
    - Temp > 39.5 or < 35  -> +15 points
    - Age > 75  -> +10 points
    - RR > 30  -> +20 points
    """
    score = 0.0

    # Vitals scoring
    spo2 = vitals.get("SpO2", 100)
    hr = vitals.get("HR", 80)
    sbp = vitals.get("BP_systolic", 120)
    temp = vitals.get("temp", 37.0)
    rr = vitals.get("RR", 16)

    if spo2 < 90:
        score += 40
    elif spo2 < 94:
        score += 20

    if hr > 130 or hr < 40:
        score += 30
    elif hr > 110 or hr < 50:
        score += 15

    if sbp < 90:
        score += 30
    elif sbp < 100:
        score += 15

    if temp > 39.5 or temp < 35:
        score += 15
    elif temp > 38.5:
        score += 7

    if rr > 30:
        score += 20
    elif rr > 24:
        score += 10

    if age > 75:
        score += 10

    # Complaint keywords boost
    critical_keywords = ["chest pain", "unconscious", "not breathing", "stroke", "seizure", "cardiac"]
    if any(kw in chief_complaint.lower() for kw in critical_keywords):
        score += 25

    score = min(score, 100.0)

    # Classify urgency
    if score >= 70:
        urgency = "critical"
    elif score >= 45:
        urgency = "urgent"
    elif score >= 20:
        urgency = "semi-urgent"
    else:
        urgency = "non-urgent"

    logger.info(f"🏥 Triage score for patient {patient_id}: {score:.1f} ({urgency})")
    return {
        "patient_id": patient_id,
        "score": round(score, 1),
        "urgency_level": urgency,
        "vitals_checked": vitals,
        "chief_complaint": chief_complaint,
    }


@register_tool(
    name="classify_emergency_level",
    description="Classify emergency response level based on triage score",
    parameters={"triage_score": "Float - score from calculate_triage_score"},
)
async def classify_emergency_level(triage_score: float) -> dict:
    """Map triage score to emergency classification and required response."""
    if triage_score >= 70:
        return {
            "level": "Level-1 Resuscitation",
            "response_time_target_minutes": 0,
            "team_required": "full_resus_team",
            "protocol": "immediate_activation",
        }
    elif triage_score >= 45:
        return {
            "level": "Level-2 Emergency",
            "response_time_target_minutes": 15,
            "team_required": "emergency_physician",
            "protocol": "fast_track",
        }
    elif triage_score >= 20:
        return {
            "level": "Level-3 Urgent",
            "response_time_target_minutes": 30,
            "team_required": "on_call_physician",
            "protocol": "standard_track",
        }
    else:
        return {
            "level": "Level-4 Semi-Urgent",
            "response_time_target_minutes": 60,
            "team_required": "nurse_practitioner",
            "protocol": "waiting_room",
        }


@register_tool(
    name="prioritize_waitlist",
    description="Re-sort patient waitlist by triage priority",
    parameters={"ward": "String - ward or department to prioritize"},
)
async def prioritize_waitlist(ward: str) -> dict:
    """
    Fetch all patients pending for a ward and return them sorted by
    triage score descending (highest urgency first).
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(Patient).where(
                Patient.department == ward.lower(),
                Patient.admitted == False,  # noqa: E712
            )
        )
        patients = result.scalars().all()

        sorted_patients = sorted(
            [p.to_dict() for p in patients],
            key=lambda x: x.get("triage_score") or 0,
            reverse=True,
        )

        return {
            "ward": ward,
            "queue_length": len(sorted_patients),
            "prioritized_queue": sorted_patients,
        }


@register_tool(
    name="flag_critical_case",
    description="Flag a patient as critical and trigger rapid response",
    parameters={
        "patient_id": "Integer - patient to flag",
        "reason": "String - reason for flagging critical",
    },
)
async def flag_critical_case(patient_id: int, reason: str) -> dict:
    """Flag a patient as critical and update their urgency in the DB."""
    async with async_session_factory() as session:
        await session.execute(
            update(Patient)
            .where(Patient.id == patient_id)
            .values(urgency_level="critical")
        )
        await session.commit()

    logger.warning(f"🚨 CRITICAL CASE FLAGGED: Patient {patient_id} — {reason}")
    return {
        "patient_id": patient_id,
        "flagged": True,
        "urgency_level": "critical",
        "reason": reason,
        "flagged_at": datetime.utcnow().isoformat(),
        "action": "rapid_response_triggered",
    }


@register_tool(
    name="record_triage_assessment",
    description="Persist a full triage assessment record for a patient",
    parameters={
        "patient_id": "Integer - patient identifier",
        "score": "Float - triage score",
        "urgency_level": "String - urgency classification",
        "chief_complaint": "String - primary complaint",
        "vitals": "Dict - vitals data",
        "pathway_recommendation": "String - recommended care pathway",
    },
)
async def record_triage_assessment(
    patient_id: int,
    score: float,
    urgency_level: str,
    chief_complaint: str,
    vitals: dict,
    pathway_recommendation: str = "",
) -> dict:
    """Persist a triage record and update patient urgency level."""
    async with async_session_factory() as session:
        record = TriageRecord(
            patient_id=patient_id,
            score=score,
            urgency_level=urgency_level,
            chief_complaint=chief_complaint,
            vitals=vitals,
            pathway_recommendation=pathway_recommendation,
            assessed_by="TriageAgent",
        )
        session.add(record)

        # Update patient record too
        await session.execute(
            update(Patient)
            .where(Patient.id == patient_id)
            .values(triage_score=score, urgency_level=urgency_level)
        )

        await session.commit()
        await session.refresh(record)

    logger.info(f"📋 Triage recorded: Patient {patient_id} score={score} ({urgency_level})")
    return record.to_dict()


# ═══════════════════════════════════════════════════════
# SECTION 3 — BED MANAGEMENT TOOLS (6)
# ═══════════════════════════════════════════════════════

@register_tool(
    name="get_bed_inventory",
    description="Get all beds and current status, optionally filtered by ward",
    parameters={"ward": "String - filter by ward (optional, empty = all wards)"},
)
async def get_bed_inventory(ward: str = "") -> dict:
    """Return complete bed inventory with occupancy stats."""
    async with async_session_factory() as session:
        query = select(Bed)
        if ward:
            query = query.where(Bed.ward == ward)
        result = await session.execute(query)
        beds = result.scalars().all()

        bed_list = [b.to_dict() for b in beds]
        available = [b for b in bed_list if b["status"] == "available"]
        occupied = [b for b in bed_list if b["status"] == "occupied"]

        return {
            "ward": ward or "all",
            "total_beds": len(bed_list),
            "available": len(available),
            "occupied": len(occupied),
            "beds": bed_list,
        }


@register_tool(
    name="find_best_bed_match",
    description="Find the best available bed for a patient based on ward preference",
    parameters={
        "preferred_ward": "String - preferred ward (ICU, General, Cardiology, etc.)",
        "urgency_level": "String - patient urgency level for priority matching",
    },
)
async def find_best_bed_match(preferred_ward: str, urgency_level: str = "semi-urgent") -> dict:
    """
    Find the best available bed:
    1. First try exact ward match
    2. If critical patient and no ICU bed, escalate
    3. Fall back to any available bed
    """
    async with async_session_factory() as session:
        # Try exact ward
        result = await session.execute(
            select(Bed).where(
                Bed.ward == preferred_ward,
                Bed.status == "available",
            )
        )
        bed = result.scalars().first()

        if bed is None and urgency_level == "critical":
            # Try ICU for critical patients
            result = await session.execute(
                select(Bed).where(Bed.ward == "ICU", Bed.status == "available")
            )
            bed = result.scalars().first()

        if bed is None:
            # Fall back to any ward
            result = await session.execute(
                select(Bed).where(Bed.status == "available")
            )
            bed = result.scalars().first()

        if bed is None:
            return {
                "found": False,
                "error": "No available beds in any ward",
                "preferred_ward": preferred_ward,
            }

        return {
            "found": True,
            "bed_id": bed.id,
            "ward": bed.ward,
            "bed_number": bed.bed_number,
            "preferred_ward": preferred_ward,
            "match_type": "exact" if bed.ward == preferred_ward else "fallback",
        }


@register_tool(
    name="reserve_bed",
    description="Reserve a specific bed for an incoming patient",
    parameters={
        "bed_id": "Integer - bed to reserve",
        "patient_id": "Integer - patient to reserve for",
    },
)
async def reserve_bed(bed_id: int, patient_id: int) -> dict:
    """Mark a bed as reserved for a specific patient."""
    async with async_session_factory() as session:
        result = await session.execute(select(Bed).where(Bed.id == bed_id))
        bed = result.scalar_one_or_none()

        if bed is None:
            return {"error": f"Bed {bed_id} not found", "reserved": False}
        if bed.status != "available":
            return {
                "error": f"Bed {bed_id} is not available (status: {bed.status})",
                "reserved": False,
            }

        await session.execute(
            update(Bed)
            .where(Bed.id == bed_id)
            .values(status="reserved", reserved_for_patient_id=patient_id)
        )
        await session.commit()

    logger.info(f"🛏️ Bed {bed_id} reserved for Patient {patient_id}")
    return {
        "reserved": True,
        "bed_id": bed_id,
        "patient_id": patient_id,
        "ward": bed.ward,
        "bed_number": bed.bed_number,
    }


@register_tool(
    name="assign_bed",
    description="Assign a reserved or available bed to a patient (marks as occupied)",
    parameters={
        "bed_id": "Integer - bed to assign",
        "patient_id": "Integer - patient to assign to",
    },
)
async def assign_bed(bed_id: int, patient_id: int) -> dict:
    """Assign a bed to a patient and update patient's bed_id."""
    async with async_session_factory() as session:
        result = await session.execute(select(Bed).where(Bed.id == bed_id))
        bed = result.scalar_one_or_none()

        if bed is None:
            return {"error": f"Bed {bed_id} not found", "assigned": False}

        await session.execute(
            update(Bed)
            .where(Bed.id == bed_id)
            .values(status="occupied", patient_id=patient_id, reserved_for_patient_id=None)
        )
        await session.execute(
            update(Patient)
            .where(Patient.id == patient_id)
            .values(bed_id=bed_id)
        )
        await session.commit()

    logger.info(f"🛏️ Bed {bed_id} ({bed.ward}) assigned to Patient {patient_id}")
    return {
        "assigned": True,
        "bed_id": bed_id,
        "patient_id": patient_id,
        "ward": bed.ward,
        "bed_number": bed.bed_number,
    }


@register_tool(
    name="release_bed",
    description="Release a bed when a patient is discharged or transferred",
    parameters={"bed_id": "Integer - bed to release"},
)
async def release_bed(bed_id: int) -> dict:
    """Release an occupied bed, marking it ready for cleaning."""
    async with async_session_factory() as session:
        result = await session.execute(select(Bed).where(Bed.id == bed_id))
        bed = result.scalar_one_or_none()

        if bed is None:
            return {"error": f"Bed {bed_id} not found", "released": False}

        prev_patient = bed.patient_id

        await session.execute(
            update(Bed)
            .where(Bed.id == bed_id)
            .values(status="cleaning", patient_id=None, reserved_for_patient_id=None)
        )
        await session.commit()

    logger.info(f"🛏️ Bed {bed_id} released (was Patient {prev_patient}) — pending cleaning")
    return {
        "released": True,
        "bed_id": bed_id,
        "previous_patient_id": prev_patient,
        "status": "cleaning",
        "ward": bed.ward,
    }


@register_tool(
    name="get_occupancy_snapshot",
    description="Get current occupancy snapshot across all wards",
    parameters={},
)
async def get_occupancy_snapshot() -> dict:
    """Return per-ward occupancy rates and totals."""
    async with async_session_factory() as session:
        result = await session.execute(select(Bed))
        beds = result.scalars().all()

    wards: dict = {}
    for bed in beds:
        w = bed.ward
        if w not in wards:
            wards[w] = {"total": 0, "available": 0, "occupied": 0, "cleaning": 0, "reserved": 0}
        wards[w]["total"] += 1
        wards[w][bed.status] = wards[w].get(bed.status, 0) + 1

    total = len(beds)
    occupied = sum(1 for b in beds if b.status == "occupied")
    occupancy_rate = round((occupied / total * 100) if total else 0, 1)

    return {
        "snapshot_at": datetime.utcnow().isoformat(),
        "total_beds": total,
        "occupied": occupied,
        "occupancy_rate_pct": occupancy_rate,
        "by_ward": wards,
    }


# ═══════════════════════════════════════════════════════
# SECTION 4 — BILLING BASICS TOOLS (8)
# ═══════════════════════════════════════════════════════


@register_tool(
    name="initiate_billing_case",
    description="Open a billing case for a newly admitted patient",
    parameters={"patient_id": "Integer - patient to open billing for"},
)
async def initiate_billing_case(patient_id: int) -> dict:
    """Create a new billing case record for a patient."""
    async with async_session_factory() as session:
        case = BillingCase(
            patient_id=patient_id,
            status="open",
            services=[],
            estimated_total=0.0,
        )
        session.add(case)
        await session.commit()
        await session.refresh(case)

    logger.info(f"💰 Billing case initiated: Patient {patient_id}, Case #{case.id}")
    return case.to_dict()


@register_tool(
    name="map_services_to_charge_codes",
    description="Map a list of service names to their charge codes and amounts",
    parameters={"services": "List[str] - service names to map"},
)
async def map_services_to_charge_codes(services: list) -> dict:
    """Map service names to standardized charge codes from the database."""
    service_keys = [svc.lower().strip().replace(" ", "_") for svc in services]

    async with async_session_factory() as session:
        result = await session.execute(
            select(ChargeCode).where(
                ChargeCode.service_key.in_(service_keys),
                ChargeCode.is_active == True,  # noqa: E712
            )
        )
        db_codes = result.scalars().all()

    code_map = {c.service_key: c for c in db_codes}
    mapped = []
    unmapped = []

    for svc in services:
        key = svc.lower().strip().replace(" ", "_")
        code_row = code_map.get(key)
        if code_row:
            mapped.append(
                {
                    "service": svc,
                    "code": code_row.code,
                    "amount": code_row.amount,
                }
            )
        else:
            unmapped.append(svc)
            mapped.append({"service": svc, "code": "MISC001", "amount": 0.0})

    return {
        "mapped_services": mapped,
        "unmapped_services": unmapped,
        "total": sum(m["amount"] for m in mapped),
    }


@register_tool(
    name="get_insurance_eligibility",
    description="Validate insurance details and fetch coverage rules from database",
    parameters={
        "insurance_provider": "String - insurance company name",
        "plan_type": "String - insurance plan type",
        "member_id": "String - insurance member ID",
    },
)
async def get_insurance_eligibility(
    insurance_provider: str,
    plan_type: str,
    member_id: str,
) -> dict:
    """Return eligibility and coverage using DB-configured insurance rules."""
    normalized_provider = (insurance_provider or "").strip().lower()
    normalized_plan = (plan_type or "").strip().lower()

    issues = []
    if not member_id or member_id.strip() in ("", "unknown"):
        issues.append("member_id_missing")
    if normalized_provider in ("", "unknown", "none"):
        issues.append("provider_unknown")

    async with async_session_factory() as session:
        result = await session.execute(
            select(InsuranceEligibilityRule).where(
                func.lower(InsuranceEligibilityRule.insurance_provider)
                == normalized_provider,
                func.lower(InsuranceEligibilityRule.plan_type) == normalized_plan,
                InsuranceEligibilityRule.is_active == True,  # noqa: E712
            )
        )
        rule = result.scalar_one_or_none()

        if rule is None:
            fallback = await session.execute(
                select(InsuranceEligibilityRule).where(
                    func.lower(InsuranceEligibilityRule.insurance_provider) == "default",
                    func.lower(InsuranceEligibilityRule.plan_type) == normalized_plan,
                    InsuranceEligibilityRule.is_active == True,  # noqa: E712
                )
            )
            rule = fallback.scalar_one_or_none()

    if rule is None:
        issues.append("plan_not_supported")

    eligible = len(issues) == 0
    coverage_pct = (rule.coverage_percentage if rule else 0.0) if eligible else 0.0
    covered_services = (rule.covered_services if rule else []) if eligible else []

    return {
        "eligible": eligible,
        "coverage_percentage": coverage_pct,
        "covered_services": covered_services,
        "issues": issues,
    }


@register_tool(
    name="calculate_estimated_bill",
    description="Calculate estimated bill from a list of charge items",
    parameters={
        "billing_case_id": "Integer - billing case to update",
        "charge_items": "List[Dict] - items with code, service, amount",
    },
)
async def calculate_estimated_bill(billing_case_id: int, charge_items: list) -> dict:
    """Calculate total and update billing case with service charges."""
    total = sum(item.get("amount", 0.0) for item in charge_items)

    async with async_session_factory() as session:
        await session.execute(
            update(BillingCase)
            .where(BillingCase.id == billing_case_id)
            .values(services=charge_items, estimated_total=total)
        )
        await session.commit()

    logger.info(f"💰 Estimated bill for Case {billing_case_id}: ₹{total:,.2f}")
    return {
        "billing_case_id": billing_case_id,
        "charge_items": charge_items,
        "estimated_total": total,
        "currency": "INR",
    }


@register_tool(
    name="generate_itemized_invoice",
    description="Generate a formatted itemized invoice for a billing case",
    parameters={"billing_case_id": "Integer - billing case to invoice"},
)
async def generate_itemized_invoice(billing_case_id: int) -> dict:
    """Generate an itemized invoice and assign an invoice number."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(BillingCase).where(BillingCase.id == billing_case_id)
        )
        case = result.scalar_one_or_none()

        if case is None:
            return {"error": f"Billing case {billing_case_id} not found"}

        invoice_number = f"INV-{datetime.utcnow().strftime('%Y%m%d')}-{billing_case_id:04d}"
        await session.execute(
            update(BillingCase)
            .where(BillingCase.id == billing_case_id)
            .values(invoice_number=invoice_number, status="invoiced")
        )
        await session.commit()

    return {
        "invoice_number": invoice_number,
        "billing_case_id": billing_case_id,
        "patient_id": case.patient_id,
        "services": case.services,
        "total": case.estimated_total,
        "generated_at": datetime.utcnow().isoformat(),
        "status": "invoiced",
    }


@register_tool(
    name="create_claim",
    description="Create an insurance claim for a billing case",
    parameters={
        "patient_id": "Integer - patient ID",
        "billing_case_id": "Integer - associated billing case",
        "insurance_provider": "String - insurance company name",
        "plan_type": "String - insurance plan type",
        "member_id": "String - patient insurance member ID",
        "claim_amount": "Float - amount to claim",
    },
)
async def create_claim(
    patient_id: int,
    billing_case_id: int,
    insurance_provider: str,
    plan_type: str,
    member_id: str,
    claim_amount: float,
) -> dict:
    """Create a new insurance claim record."""
    async with async_session_factory() as session:
        claim = InsuranceClaim(
            patient_id=patient_id,
            billing_case_id=billing_case_id,
            insurance_provider=insurance_provider,
            plan_type=plan_type,
            member_id=member_id,
            claim_amount=claim_amount,
            status="pending",
        )
        session.add(claim)
        await session.commit()
        await session.refresh(claim)

    logger.info(f"📋 Claim created: Patient {patient_id}, Provider: {insurance_provider}, Amount: {claim_amount}")
    return claim.to_dict()


@register_tool(
    name="validate_claim",
    description="Validate an insurance claim for completeness and policy compliance",
    parameters={"claim_id": "Integer - claim to validate"},
)
async def validate_claim(claim_id: int) -> dict:
    """Run validation checks on a claim before submission."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(InsuranceClaim).where(InsuranceClaim.id == claim_id)
        )
        claim = result.scalar_one_or_none()

        if claim is None:
            return {"error": f"Claim {claim_id} not found", "valid": False}

    checks = {
        "member_id_present": bool(claim.member_id),
        "provider_present": bool(claim.insurance_provider),
        "amount_positive": (claim.claim_amount or 0) > 0,
        "billing_case_linked": claim.billing_case_id is not None,
    }
    all_valid = all(checks.values())
    issues = [k for k, v in checks.items() if not v]

    return {
        "claim_id": claim_id,
        "valid": all_valid,
        "checks": checks,
        "issues": issues,
    }


@register_tool(
    name="submit_claim",
    description="Submit a validated claim to the insurance provider",
    parameters={"claim_id": "Integer - claim to submit"},
)
async def submit_claim(claim_id: int) -> dict:
    """Mark claim as submitted and record submission time."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(InsuranceClaim).where(InsuranceClaim.id == claim_id)
        )
        claim = result.scalar_one_or_none()

        if claim is None:
            return {"error": f"Claim {claim_id} not found", "submitted": False}

        await session.execute(
            update(InsuranceClaim)
            .where(InsuranceClaim.id == claim_id)
            .values(status="submitted", submitted_at=datetime.utcnow())
        )
        await session.commit()

    logger.info(f"📤 Claim {claim_id} submitted to {claim.insurance_provider}")
    return {
        "submitted": True,
        "claim_id": claim_id,
        "provider": claim.insurance_provider,
        "submitted_at": datetime.utcnow().isoformat(),
        "reference_number": f"CLM-{claim_id}-{uuid.uuid4().hex[:8].upper()}",
    }


@register_tool(
    name="track_claim_status",
    description="Check the current status of an insurance claim",
    parameters={"claim_id": "Integer - claim ID to track"},
)
async def track_claim_status(claim_id: int) -> dict:
    """Retrieve current claim status from the database."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(InsuranceClaim).where(InsuranceClaim.id == claim_id)
        )
        claim = result.scalar_one_or_none()

        if claim is None:
            return {"error": f"Claim {claim_id} not found"}

    return claim.to_dict()


# ═══════════════════════════════════════════════════════
# SECTION 5 — LAB CRITICAL PATH TOOLS (6)
# ═══════════════════════════════════════════════════════

@register_tool(
    name="create_lab_order",
    description="Create a lab test order for a patient",
    parameters={
        "patient_id": "Integer - patient ID",
        "test_name": "String - name of the lab test",
        "ordered_by": "String - name of ordering physician",
        "priority": "String - stat, urgent, or routine",
    },
)
async def create_lab_order(
    patient_id: int,
    test_name: str,
    ordered_by: str,
    priority: str = "routine",
) -> dict:
    """Create a lab order record."""
    async with async_session_factory() as session:
        order = LabOrder(
            patient_id=patient_id,
            test_name=test_name,
            ordered_by=ordered_by,
            priority=priority,
            status="ordered",
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)

    logger.info(f"🧪 Lab order created: {test_name} for Patient {patient_id} [{priority}]")
    return order.to_dict()


@register_tool(
    name="collect_sample",
    description="Mark sample as collected for a lab order",
    parameters={
        "order_id": "Integer - lab order ID",
        "collected_by": "String - name of nurse/phlebotomist",
    },
)
async def collect_sample(order_id: int, collected_by: str = "nursing") -> dict:
    """Update lab order status to sample_collected."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(LabOrder).where(LabOrder.id == order_id)
        )
        order = result.scalar_one_or_none()

        if order is None:
            return {"error": f"Lab order {order_id} not found", "collected": False}

        await session.execute(
            update(LabOrder)
            .where(LabOrder.id == order_id)
            .values(status="sample_collected", notes=f"Collected by: {collected_by}")
        )
        await session.commit()

    return {
        "collected": True,
        "order_id": order_id,
        "test_name": order.test_name,
        "collected_by": collected_by,
        "collected_at": datetime.utcnow().isoformat(),
    }


@register_tool(
    name="track_sample_status",
    description="Get the current lifecycle status of a lab order",
    parameters={"order_id": "Integer - lab order to track"},
)
async def track_sample_status(order_id: int) -> dict:
    """Return current status of a lab order."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(LabOrder).where(LabOrder.id == order_id)
        )
        order = result.scalar_one_or_none()

        if order is None:
            return {"error": f"Lab order {order_id} not found"}

    status_messages = {
        "ordered": "Order placed, awaiting sample collection",
        "sample_collected": "Sample collected, in transit to lab",
        "in_lab": "Sample received by lab, processing",
        "resulted": "Results available",
        "critical": "CRITICAL RESULT — immediate physician notification required",
    }

    return {
        "order_id": order_id,
        "status": order.status,
        "status_message": status_messages.get(order.status, order.status),
        "test_name": order.test_name,
        "priority": order.priority,
        "patient_id": order.patient_id,
    }


@register_tool(
    name="get_lab_result",
    description="Retrieve lab test result and mark order as resulted",
    parameters={
        "order_id": "Integer - lab order ID",
        "result_data": "Dict - result values from lab system",
    },
)
async def get_lab_result(order_id: int, result_data: dict) -> dict:
    """Store lab result and determine if critical."""
    # Determine if result is critical based on result data
    is_critical = result_data.get("is_critical", False)

    async with async_session_factory() as session:
        new_status = "critical" if is_critical else "resulted"
        await session.execute(
            update(LabOrder)
            .where(LabOrder.id == order_id)
            .values(
                status=new_status,
                result=result_data,
                is_critical=is_critical,
                resulted_at=datetime.utcnow(),
            )
        )
        await session.commit()

        result = await session.execute(select(LabOrder).where(LabOrder.id == order_id))
        order = result.scalar_one_or_none()

    if order is None:
        return {"error": f"Lab order {order_id} not found"}

    return {
        "order_id": order_id,
        "test_name": order.test_name,
        "patient_id": order.patient_id,
        "result": result_data,
        "is_critical": is_critical,
        "status": new_status,
        "resulted_at": datetime.utcnow().isoformat(),
    }


@register_tool(
    name="flag_critical_lab_result",
    description="Escalate a critical lab result and notify the ordering physician",
    parameters={
        "order_id": "Integer - lab order with critical result",
        "critical_value": "String - description of the critical finding",
    },
)
async def flag_critical_lab_result(order_id: int, critical_value: str) -> dict:
    """Flag critical lab result and trigger immediate notification chain."""
    async with async_session_factory() as session:
        result = await session.execute(select(LabOrder).where(LabOrder.id == order_id))
        order = result.scalar_one_or_none()

        if order is None:
            return {"error": f"Lab order {order_id} not found"}

        await session.execute(
            update(LabOrder)
            .where(LabOrder.id == order_id)
            .values(status="critical", is_critical=True)
        )
        await session.commit()

    logger.warning(
        f"🚨 CRITICAL LAB RESULT: Order {order_id} ({order.test_name}) "
        f"— Patient {order.patient_id}: {critical_value}"
    )
    return {
        "order_id": order_id,
        "test_name": order.test_name,
        "patient_id": order.patient_id,
        "critical_value": critical_value,
        "flagged": True,
        "escalation": "immediate_physician_notification",
        "flagged_at": datetime.utcnow().isoformat(),
    }


@register_tool(
    name="attach_lab_report",
    description="Attach a lab report reference to a completed order",
    parameters={
        "order_id": "Integer - lab order ID",
        "report_url": "String - URL or path to the report document",
    },
)
async def attach_lab_report(order_id: int, report_url: str) -> dict:
    """Record the lab report reference on the order."""
    async with async_session_factory() as session:
        result = await session.execute(select(LabOrder).where(LabOrder.id == order_id))
        order = result.scalar_one_or_none()

        if order is None:
            return {"error": f"Lab order {order_id} not found"}

        # Append report URL to result
        existing_result = order.result or {}
        existing_result["report_url"] = report_url

        await session.execute(
            update(LabOrder)
            .where(LabOrder.id == order_id)
            .values(result=existing_result)
        )
        await session.commit()

    return {
        "order_id": order_id,
        "report_attached": True,
        "report_url": report_url,
        "test_name": order.test_name,
        "patient_id": order.patient_id,
    }


# ═══════════════════════════════════════════════════════
# SECTION 6 — APPOINTMENT & SCHEDULING TOOLS (7)
# ═══════════════════════════════════════════════════════

def _department_from_symptoms(symptoms: str, urgency_level: str) -> tuple[str, str]:
    """Simple rule-based department suggestion from symptom text."""
    text = (symptoms or "").lower()

    keyword_map = [
        ("cardiology", ["chest pain", "palpitation", "heart", "cardiac", "pressure chest"]),
        ("neurology", ["headache", "migraine", "seizure", "stroke", "dizziness", "numbness"]),
        ("pulmonology", ["shortness of breath", "breath", "cough", "wheezing", "asthma"]),
        ("orthopedics", ["fracture", "bone", "joint", "sprain", "back pain", "knee"]),
        ("oncology", ["tumor", "cancer", "chemotherapy", "oncology"]),
        ("icu", ["unconscious", "not breathing", "collapse", "septic", "critical"]),
    ]

    for department, keywords in keyword_map:
        if any(keyword in text for keyword in keywords):
            return (
                department,
                f"Symptoms matched {department.title()} keyword profile.",
            )

    if urgency_level == "critical":
        return "icu", "Urgency level is critical, recommending ICU fast-track."

    return "general", "No specialty keyword matched; routing to General Medicine."


@register_tool(
    name="recommend_department_from_symptoms",
    description="Suggest the most appropriate department from symptom text and urgency",
    parameters={
        "symptoms": "String - patient-reported symptoms",
        "urgency_level": "String - urgency level from triage score",
    },
)
async def recommend_department_from_symptoms(symptoms: str, urgency_level: str = "non-urgent") -> dict:
    """Return department recommendation and explanation from symptom narrative."""
    department, explanation = _department_from_symptoms(symptoms=symptoms, urgency_level=urgency_level)
    return {
        "recommended_department": department,
        "explanation": explanation,
        "urgency_level": urgency_level,
    }


@register_tool(
    name="list_available_doctors",
    description="List currently available doctors in a department",
    parameters={"department": "String - medical department"},
)
async def list_available_doctors(department: str) -> dict:
    """Return department doctors with availability flag (available first)."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Doctor).where(
                Doctor.department == department.lower().strip(),
            )
        )
        doctors = result.scalars().all()

    doctors_sorted = sorted(doctors, key=lambda d: d.available, reverse=True)

    return {
        "department": department.lower().strip(),
        "doctors": [doctor.to_dict() for doctor in doctors_sorted],
        "count": len(doctors_sorted),
    }


@register_tool(
    name="get_doctor_slots",
    description="Get fixed 30-minute slots for a doctor and date, auto-generating if missing",
    parameters={
        "doctor_id": "Integer - doctor ID",
        "date": "String - date in YYYY-MM-DD",
    },
)
async def get_doctor_slots(doctor_id: int, date: str) -> dict:
    """Return unbooked 30-minute appointment slots for a doctor on a given date."""
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Invalid date format. Expected YYYY-MM-DD") from exc

    day_start = datetime.combine(target_date, datetime.min.time()).replace(hour=9, minute=0, second=0, microsecond=0)
    day_end = datetime.combine(target_date, datetime.min.time()).replace(hour=17, minute=0, second=0, microsecond=0)

    async with async_session_factory() as session:
        doctor_result = await session.execute(select(Doctor).where(Doctor.id == doctor_id))
        doctor = doctor_result.scalar_one_or_none()
        if doctor is None:
            return {"error": f"Doctor {doctor_id} not found", "slots": []}

        existing_result = await session.execute(
            select(DoctorAvailabilitySlot).where(
                DoctorAvailabilitySlot.doctor_id == doctor_id,
                DoctorAvailabilitySlot.slot_start >= day_start,
                DoctorAvailabilitySlot.slot_start < day_end,
            )
        )
        existing_slots = existing_result.scalars().all()

        if not existing_slots:
            slots_to_create = []
            cursor = day_start
            while cursor < day_end:
                next_cursor = cursor + timedelta(minutes=30)
                if cursor >= datetime.utcnow():
                    slots_to_create.append(
                        DoctorAvailabilitySlot(
                            doctor_id=doctor_id,
                            department=doctor.department,
                            slot_start=cursor,
                            slot_end=next_cursor,
                            is_booked=False,
                        )
                    )
                cursor = next_cursor

            if slots_to_create:
                session.add_all(slots_to_create)
                await session.commit()

            existing_result = await session.execute(
                select(DoctorAvailabilitySlot).where(
                    DoctorAvailabilitySlot.doctor_id == doctor_id,
                    DoctorAvailabilitySlot.slot_start >= day_start,
                    DoctorAvailabilitySlot.slot_start < day_end,
                )
            )
            existing_slots = existing_result.scalars().all()

    available_slots = [
        slot.to_dict()
        for slot in existing_slots
        if not slot.is_booked and slot.slot_start >= datetime.utcnow()
    ]

    return {
        "doctor_id": doctor_id,
        "date": date,
        "department": doctor.department,
        "slots": available_slots,
        "count": len(available_slots),
    }


@register_tool(
    name="book_appointment",
    description="Book an appointment against an available doctor slot",
    parameters={
        "patient_id": "Integer - patient ID",
        "doctor_id": "Integer - doctor ID",
        "slot_id": "Integer - slot ID from get_doctor_slots",
        "symptoms": "String - optional symptom summary",
    },
)
async def book_appointment(patient_id: int, doctor_id: int, slot_id: int, symptoms: str = "") -> dict:
    """Book appointment if slot is still available; marks slot as booked and creates appointment."""
    async with async_session_factory() as session:
        patient_result = await session.execute(select(Patient).where(Patient.id == patient_id))
        patient = patient_result.scalar_one_or_none()
        if patient is None:
            return {"error": f"Patient {patient_id} not found", "booked": False}

        doctor_result = await session.execute(select(Doctor).where(Doctor.id == doctor_id))
        doctor = doctor_result.scalar_one_or_none()
        if doctor is None:
            return {"error": f"Doctor {doctor_id} not found", "booked": False}

        slot_result = await session.execute(
            select(DoctorAvailabilitySlot)
            .where(
                DoctorAvailabilitySlot.id == slot_id,
                DoctorAvailabilitySlot.doctor_id == doctor_id,
            )
            .with_for_update()
        )
        slot = slot_result.scalar_one_or_none()
        if slot is None:
            return {"error": f"Slot {slot_id} not found for doctor {doctor_id}", "booked": False}

        if slot.is_booked:
            return {"error": "Selected slot is already booked", "booked": False}

        confirmation_code = f"APT-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        appointment = Appointment(
            patient_id=patient_id,
            doctor_id=doctor_id,
            department=doctor.department,
            slot_id=slot.id,
            appointment_start=slot.slot_start,
            appointment_end=slot.slot_end,
            status="confirmed",
            notes=(symptoms or "").strip() or None,
            confirmation_code=confirmation_code,
        )

        slot.is_booked = True
        slot.booked_patient_id = patient_id
        session.add(appointment)
        await session.commit()
        await session.refresh(appointment)

    return {
        "booked": True,
        "appointment": appointment.to_dict(),
    }


@register_tool(
    name="get_appointment_details",
    description="Fetch a single appointment by ID",
    parameters={"appointment_id": "Integer - appointment ID"},
)
async def get_appointment_details(appointment_id: int) -> dict:
    """Return appointment details by appointment ID."""
    async with async_session_factory() as session:
        result = await session.execute(select(Appointment).where(Appointment.id == appointment_id))
        appointment = result.scalar_one_or_none()
        if appointment is None:
            return {"error": f"Appointment {appointment_id} not found"}
        return appointment.to_dict()


@register_tool(
    name="list_doctor_appointments",
    description="List all appointments for a doctor, optionally filtered by date",
    parameters={
        "doctor_id": "Integer - doctor ID",
        "date": "String - optional date filter YYYY-MM-DD",
    },
)
async def list_doctor_appointments(doctor_id: int, date: str = "") -> dict:
    """Return appointment list for doctor dashboard views."""
    async with async_session_factory() as session:
        query = select(Appointment).where(Appointment.doctor_id == doctor_id)
        if date:
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d").date()
            except ValueError as exc:
                raise ValueError("Invalid date format. Expected YYYY-MM-DD") from exc

            start = datetime.combine(target_date, datetime.min.time())
            end = start + timedelta(days=1)
            query = query.where(
                Appointment.appointment_start >= start,
                Appointment.appointment_start < end,
            )

        query = query.order_by(Appointment.appointment_start.asc())
        result = await session.execute(query)
        appointments = result.scalars().all()

    return {
        "doctor_id": doctor_id,
        "appointments": [a.to_dict() for a in appointments],
        "count": len(appointments),
    }


@register_tool(
    name="update_appointment",
    description="Update doctor-facing appointment fields (status and notes)",
    parameters={
        "appointment_id": "Integer - appointment ID",
        "status": "String - optional status update (confirmed/completed/cancelled)",
        "notes": "String - optional notes",
    },
)
async def update_appointment(appointment_id: int, status: str = "", notes: str = "") -> dict:
    """Update appointment status and/or notes from doctor dashboard actions."""
    allowed_status = {"confirmed", "completed", "cancelled"}
    update_payload = {}
    if status:
        normalized = status.lower().strip()
        if normalized not in allowed_status:
            return {"error": f"Invalid status '{status}'", "updated": False}
        update_payload["status"] = normalized

    if notes:
        update_payload["notes"] = notes

    if not update_payload:
        return {"error": "No update fields provided", "updated": False}

    async with async_session_factory() as session:
        result = await session.execute(select(Appointment).where(Appointment.id == appointment_id))
        appointment = result.scalar_one_or_none()
        if appointment is None:
            return {"error": f"Appointment {appointment_id} not found", "updated": False}

        await session.execute(
            update(Appointment)
            .where(Appointment.id == appointment_id)
            .values(**update_payload)
        )
        await session.commit()

        refreshed = await session.execute(select(Appointment).where(Appointment.id == appointment_id))
        appointment = refreshed.scalar_one_or_none()

    return {
        "updated": True,
        "appointment": appointment.to_dict() if appointment else None,
    }
