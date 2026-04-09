"""Quick verification of seeded record counts from the configured database."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from sqlalchemy import func, select

from models.database import (
    Appointment,
    Bed,
    BillingCase,
    ChargeCode,
    Doctor,
    DoctorAvailabilitySlot,
    ExecutionRecord,
    InsuranceClaim,
    InsuranceEligibilityRule,
    LabOrder,
    Notification,
    Patient,
    PatientInsuranceProfile,
    TriageRecord,
    User,
    async_session_factory,
)


async def main() -> None:
    async with async_session_factory() as session:
        checks = {
            "patients": select(func.count(Patient.id)),
            "doctors": select(func.count(Doctor.id)),
            "beds": select(func.count(Bed.id)),
            "charge_codes": select(func.count(ChargeCode.id)),
            "insurance_rules": select(func.count(InsuranceEligibilityRule.id)),
            "users": select(func.count(User.id)),
            "insurance_profiles": select(func.count(PatientInsuranceProfile.id)),
            "triage_records": select(func.count(TriageRecord.id)),
            "availability_slots": select(func.count(DoctorAvailabilitySlot.id)),
            "appointments": select(func.count(Appointment.id)),
            "lab_orders": select(func.count(LabOrder.id)),
            "billing_cases": select(func.count(BillingCase.id)),
            "insurance_claims": select(func.count(InsuranceClaim.id)),
            "notifications": select(func.count(Notification.id)),
            "execution_logs": select(func.count(ExecutionRecord.id)),
        }

        print("📊 Seed verification counts")
        print("-" * 36)
        for label, stmt in checks.items():
            value = (await session.execute(stmt)).scalar() or 0
            print(f"{label:18} : {int(value)}")


if __name__ == "__main__":
    asyncio.run(main())
