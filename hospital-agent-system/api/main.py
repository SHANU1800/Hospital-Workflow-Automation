"""
Hospital Workflow Automation — FastAPI Application (Plan 1.0).

This is the main entry point. It wires together all layers:
- Initializes the database (including Plan 1.0 tables: beds, lab, billing, etc.)
- Registers all 31 MCP tools (by importing mcp.tools)
- Creates all 9 agents and registers them with the orchestrator
- Exposes API endpoints

Agent Hierarchy:
  SupervisorAgent (coordinator)
  ├── TriageAgent
  ├── BedManagementAgent
  ├── LabAgent
  ├── BillingAgent
  ├── InsuranceAgent
  ├── SchedulerAgent
  └── AlertAgent
  └── DataAgent

Endpoints:
  POST /admit_patient       — Trigger patient admission workflow
  POST /trigger_event       — Trigger ANY event dynamically
  POST /lab_order           — Create a lab order
  POST /trigger_emergency   — Trigger emergency fast-track
  GET  /health              — Health check
  GET  /agents              — List registered agents
  GET  /tools               — List registered MCP tools
  GET  /execution_logs      — View past execution logs
  GET  /planning_rules      — View planner rules
  GET  /bed_status          — View bed inventory and occupancy
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, Optional
from io import BytesIO

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select

# ── Configure logging before anything else ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-24s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("api")

# ── Import all layers ──
from api.dependencies import get_current_user, require_roles
from api.security import (
    create_access_token,
    get_jwt_expire_minutes,
    validate_jwt_config,
    verify_password,
)
from models.database import (
    Appointment,
    Bed,
    BillingCase,
    ExecutionRecord,
    InsuranceClaim,
    PatientInsuranceProfile,
    Patient,
    User,
    UserDoctorLink,
    async_session_factory,
    init_db,
)
from models.schemas import (
    AdmitPatientRequest,
    AppointmentBookingRequest,
    AppointmentConfirmationResponse,
    AppointmentResponse,
    BedResponse,
    BedUpdateRequest,
    BillingCaseResponse,
    BillingCaseUpdateRequest,
    CreatePatientRequest,
    DepartmentRecommendationResponse,
    DoctorAppointmentUpdateRequest,
    DoctorDashboardContextResponse,
    DoctorMultiAgentWorkflowRequest,
    DoctorSummaryResponse,
    AvailabilitySlotResponse,
    GenericEventRequest,
    InsuranceClaimResponse,
    InsuranceClaimUpdateRequest,
    LoginRequest,
    PatientBillingOverviewResponse,
    PatientBillingRecordResponse,
    CreateInsuranceClaimRequest,
    PatientInsuranceProfileResponse,
    PatientInsuranceProfileUpdateRequest,
    PatientDetailResponse,
    PatientResolveRequest,
    PatientResolveResponse,
    PatientResponse,
    PatientUpdateRequest,
    StaffReportSummaryResponse,
    SymptomIntakeRequest,
    TokenResponse,
    UserPublic,
    UserRole,
)
from mcp.tool_registry import get_registry
import mcp.tools  # noqa: F401 — triggers all 30 tool registrations
from api.appointment_letter import build_appointment_letter_pdf

# ── Import all Plan 1.0 agents ──
from models.database import Doctor
from agents.supervisor_agent import SupervisorAgent
from agents.triage_agent import TriageAgent
from agents.bed_management_agent import BedManagementAgent
from agents.lab_agent import LabAgent
from agents.billing_agent import BillingAgent
from agents.insurance_agent import InsuranceAgent
from agents.data_agent import DataAgent
from agents.scheduler_agent import SchedulerAgent
from agents.alert_agent import AlertAgent

from orchestrator.dispatcher import Orchestrator
from planner.planner import RuleBasedPlanner, LLMPlanner
from seed_data import seed_database


# ── Global instances ──
orchestrator = Orchestrator()
planner = RuleBasedPlanner()


# ─────────────────────────────────────────────
# Extra Request Models (Plan 1.0)
# ─────────────────────────────────────────────

class LabOrderRequest(BaseModel):
    """Payload for creating a lab order."""
    patient_id: int = Field(..., description="Patient ID")
    test_name: str = Field(..., description="Lab test name, e.g. 'CBC'")
    ordered_by: str = Field(default="attending_physician", description="Ordering physician")
    priority: str = Field(default="routine", description="stat, urgent, or routine")


class EmergencyRequest(BaseModel):
    """Payload for triggering an emergency workflow."""
    patient_id: int = Field(..., description="Patient ID")
    emergency_type: str = Field(..., description="e.g. 'code_blue', 'cardiac_arrest'")
    vitals: Optional[Dict[str, Any]] = Field(default=None, description="Current vitals")
    chief_complaint: str = Field(default="emergency", description="Presenting complaint")


# ─────────────────────────────────────────────
# Application Lifespan (startup / shutdown)
# ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup and shutdown handler.

    Startup:
    1. Initialize all database tables (including Plan 1.0 additions)
    2. Seed sample data (patients, doctors, beds)
    3. Register all 9 agents in hierarchy order
    4. Log system status
    """
    logger.info("🏥 Hospital Workflow Automation System (Plan 1.0) starting...")

    # 1. Validate auth config and initialize database
    validate_jwt_config()
    await init_db()

    # 2. Seed sample data
    await seed_database()

    # 3. Create and register all agents
    # IMPORTANT: SupervisorAgent must be registered first so sub-agents
    # can send escalations to it during startup.
    supervisor = SupervisorAgent()
    triage = TriageAgent()
    bed_mgmt = BedManagementAgent()
    lab = LabAgent()
    billing = BillingAgent()
    insurance = InsuranceAgent()
    data = DataAgent()
    scheduler = SchedulerAgent()
    alert = AlertAgent()

    # Register all with orchestrator (gives each agent a back-reference for A2A)
    for agent in [supervisor, triage, bed_mgmt, lab, billing, insurance, data, scheduler, alert]:
        orchestrator.register_agent(agent)

    # 4. Log system status
    registry = get_registry()
    tool_names = registry.get_tool_names()
    agent_names = [a["name"] for a in orchestrator.list_agents()]
    rule_count = len(planner.list_rules())

    logger.info(f"🔧 MCP Tools registered ({len(tool_names)}): {tool_names}")
    logger.info(f"🤖 Agents registered ({len(agent_names)}): {agent_names}")
    logger.info(f"📋 Planning rules: {rule_count}")
    logger.info("✅ System ready! All Plan 1.0 agents and tools online.")

    yield  # App is running

    logger.info("🛑 Hospital Workflow Automation System shutting down.")


# ─────────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────────

app = FastAPI(
    title="Hospital Workflow Automation — Plan 1.0",
    description=(
        "Hierarchical A2A hospital workflow system with MCP tool access. "
        "Plan 1.0: SupervisorAgent + TriageAgent + BedManagementAgent + "
        "LabAgent + BillingAgent + InsuranceAgent + SchedulerAgent + "
        "AlertAgent + DataAgent. 31 MCP tools. 9 planning rules."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (frontend dashboard)
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def root():
    """Serve the dashboard frontend."""
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.post("/login", response_model=TokenResponse, summary="Authenticate and get JWT access token")
async def login(request: LoginRequest):
    """Authenticate user credentials and issue JWT token."""
    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.username == request.username))
        user = result.scalar_one_or_none()

    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive",
        )

    expires_in_minutes = get_jwt_expire_minutes()
    token = create_access_token(
        {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role,
        },
        expires_minutes=expires_in_minutes,
    )

    return TokenResponse(
        access_token=token,
        expires_in=expires_in_minutes * 60,
    )


@app.get("/me", response_model=UserPublic, summary="Get currently authenticated user")
async def get_me(current_user: User = Depends(get_current_user)):
    """Return the authenticated user profile."""
    return UserPublic(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        role=UserRole(current_user.role),
        is_active=current_user.is_active,
    )


# ─────────────────────────────────────────────
# Workflow Trigger Endpoints
# ─────────────────────────────────────────────

@app.post("/admit_patient", summary="Admit a patient — triggers full 7-step workflow")
async def admit_patient(
    request: AdmitPatientRequest,
    current_user: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.STAFF)),
):
    """
    Main endpoint: Admit a patient.

    Plan 1.0 Flow:
    1. DataAgent fetches patient record
    2. TriageAgent scores patient urgency (+ escalates if critical)
    3. BedManagementAgent finds and reserves a bed
    4. SchedulerAgent assigns a doctor
    5. BillingAgent opens a billing case
    6. InsuranceAgent verifies eligibility and creates claim
    7. AlertAgent notifies nursing station

    Returns full execution trace with all A2A messages and tool calls.
    """
    logger.info(f"\n{'#'*60}")
    logger.info(f"# NEW ADMISSION: Patient {request.patient_id}")
    logger.info(f"{'#'*60}\n")

    try:
        async with async_session_factory() as session:
            patient_result = await session.execute(
                select(Patient).where(Patient.id == request.patient_id)
            )
            patient = patient_result.scalar_one_or_none()

        if patient is None:
            raise HTTPException(
                status_code=404,
                detail=f"Patient {request.patient_id} not found. Create patient first via POST /patients.",
            )

        context = {
            "patient_id": request.patient_id,
            "_user_id": current_user.id,
            "_user_role": current_user.role,
        }
        agent_capabilities = orchestrator.get_agent_capabilities()

        plan = await planner.plan(
            event="patient_admitted",
            context=context,
            agent_capabilities=agent_capabilities,
        )

        logger.info(f"📋 Plan generated: {len(plan.tasks)} tasks")
        execution_log = await orchestrator.execute_plan(
            plan,
            user_id=current_user.id,
            user_role=current_user.role,
        )

        return JSONResponse(
            status_code=200,
            content={
                "status": execution_log.status,
                "execution_id": execution_log.execution_id,
                "event": execution_log.event,
                "plan": plan.model_dump(mode="json"),
                "execution": execution_log.model_dump(mode="json"),
                "summary": {
                    "total_steps": len(execution_log.steps),
                    "completed": sum(1 for s in execution_log.steps if s.status == "completed"),
                    "failed": sum(1 for s in execution_log.steps if s.status == "failed"),
                    "total_duration_ms": execution_log.total_duration_ms,
                },
            },
        )

    except Exception as e:
        logger.error(f"❌ Error processing admission: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/trigger_event", summary="Trigger any event dynamically")
async def trigger_event(
    request: GenericEventRequest,
    current_user: User = Depends(
        require_roles(UserRole.SUPER_ADMIN, UserRole.STAFF, UserRole.DOCTOR)
    ),
):
    """
    Generic event endpoint — trigger ANY workflow dynamically.

    The planner will match the event against its 9-rule table
    and generate an appropriate plan.

    Examples:
    - {"event": "patient_discharged", "context": {"patient_id": 101, "billing_case_id": 1}}
    - {"event": "lab_results_ready", "context": {"patient_id": 102, "order_id": 1}}
    - {"event": "emergency_code_blue", "context": {"patient_id": 103}}
    - {"event": "triage_request", "context": {"patient_id": 104, "chief_complaint": "chest pain"}}
    - {"event": "bed_request", "context": {"patient_id": 105, "department": "ICU"}}
    - {"event": "lab_order_request", "context": {"patient_id": 106, "test_name": "CBC"}}
    - {"event": "billing_inquiry", "context": {"patient_id": 107, "insurance_provider": "BlueCross"}}
    """
    logger.info(f"\n{'#'*60}")
    logger.info(f"# EVENT TRIGGER: {request.event}")
    logger.info(f"{'#'*60}\n")

    try:
        agent_capabilities = orchestrator.get_agent_capabilities()

        context = {
            **request.context,
            "_user_id": current_user.id,
            "_user_role": current_user.role,
        }

        plan = await planner.plan(
            event=request.event,
            context=context,
            agent_capabilities=agent_capabilities,
        )

        execution_log = await orchestrator.execute_plan(
            plan,
            user_id=current_user.id,
            user_role=current_user.role,
        )

        return JSONResponse(
            status_code=200,
            content={
                "status": execution_log.status,
                "execution_id": execution_log.execution_id,
                "event": execution_log.event,
                "plan": plan.model_dump(mode="json"),
                "execution": execution_log.model_dump(mode="json"),
                "summary": {
                    "total_steps": len(execution_log.steps),
                    "completed": sum(1 for s in execution_log.steps if s.status == "completed"),
                    "failed": sum(1 for s in execution_log.steps if s.status == "failed"),
                    "total_duration_ms": execution_log.total_duration_ms,
                },
            },
        )

    except Exception as e:
        logger.error(f"❌ Error processing event: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/trigger_emergency", summary="Trigger emergency fast-track workflow")
async def trigger_emergency(
    request: EmergencyRequest,
    current_user: User = Depends(
        require_roles(UserRole.SUPER_ADMIN, UserRole.STAFF, UserRole.DOCTOR)
    ),
):
    """
    Emergency endpoint — triggers highest-priority workflow.

    Flow: DataAgent → SupervisorAgent (emergency mode) → SchedulerAgent → AlertAgent.
    The SupervisorAgent will activate TriageAgent and BedManagementAgent
    via A2A with ICU prioritization.
    """
    logger.info(f"\n{'#'*60}")
    logger.info(f"# 🚨 EMERGENCY: {request.emergency_type} — Patient {request.patient_id}")
    logger.info(f"{'#'*60}\n")

    try:
        context = {
            "patient_id": request.patient_id,
            "chief_complaint": request.chief_complaint,
            "vitals": request.vitals or {},
            "_user_id": current_user.id,
            "_user_role": current_user.role,
        }
        agent_capabilities = orchestrator.get_agent_capabilities()

        plan = await planner.plan(
            event=f"emergency_{request.emergency_type}",
            context=context,
            agent_capabilities=agent_capabilities,
        )

        execution_log = await orchestrator.execute_plan(
            plan,
            user_id=current_user.id,
            user_role=current_user.role,
        )

        return JSONResponse(
            status_code=200,
            content={
                "status": execution_log.status,
                "emergency_type": request.emergency_type,
                "execution_id": execution_log.execution_id,
                "plan": plan.model_dump(mode="json"),
                "execution": execution_log.model_dump(mode="json"),
                "summary": {
                    "total_steps": len(execution_log.steps),
                    "completed": sum(1 for s in execution_log.steps if s.status == "completed"),
                    "total_duration_ms": execution_log.total_duration_ms,
                },
            },
        )

    except Exception as e:
        logger.error(f"❌ Emergency processing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/lab_order", summary="Create a lab test order via LabAgent")
async def create_lab_order(
    request: LabOrderRequest,
    current_user: User = Depends(
        require_roles(UserRole.SUPER_ADMIN, UserRole.STAFF, UserRole.DOCTOR)
    ),
):
    """
    Create a lab order and initiate sample collection.
    Triggers the 'lab_order_request' event.
    """
    try:
        context = {
            "patient_id": request.patient_id,
            "test_name": request.test_name,
            "ordered_by": request.ordered_by,
            "priority": request.priority,
            "_user_id": current_user.id,
            "_user_role": current_user.role,
        }
        agent_capabilities = orchestrator.get_agent_capabilities()

        plan = await planner.plan(
            event="lab_order_request",
            context=context,
            agent_capabilities=agent_capabilities,
        )

        execution_log = await orchestrator.execute_plan(
            plan,
            user_id=current_user.id,
            user_role=current_user.role,
        )

        return JSONResponse(
            status_code=200,
            content={
                "status": execution_log.status,
                "execution_id": execution_log.execution_id,
                "execution": execution_log.model_dump(mode="json"),
            },
        )

    except Exception as e:
        logger.error(f"❌ Lab order error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
# Status & Info Endpoints
# ─────────────────────────────────────────────

@app.get("/health", summary="Health check")
async def health_check():
    """Health check endpoint."""
    registry = get_registry()
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "plan-1.0",
        "agents": len(orchestrator.list_agents()),
        "tools": len(registry.get_tool_names()),
        "rules": len(planner.list_rules()),
    }


@app.get("/agents", summary="List all registered agents")
async def list_agents(
    _: User = Depends(
        require_roles(
            UserRole.SUPER_ADMIN,
            UserRole.STAFF,
            UserRole.DOCTOR,
            UserRole.AUDITOR,
        )
    ),
):
    """List all registered agents and their capabilities."""
    return {
        "agents": orchestrator.list_agents(),
        "total": len(orchestrator.list_agents()),
        "hierarchy": {
            "coordinator": "SupervisorAgent",
            "domain_agents": [
                "TriageAgent",
                "BedManagementAgent",
                "LabAgent",
                "BillingAgent",
                "InsuranceAgent",
                "SchedulerAgent",
            ],
            "support_agents": ["DataAgent", "AlertAgent"],
        },
    }


@app.get("/tools", summary="List all registered MCP tools")
async def list_tools(
    _: User = Depends(
        require_roles(
            UserRole.SUPER_ADMIN,
            UserRole.STAFF,
            UserRole.DOCTOR,
            UserRole.AUDITOR,
        )
    ),
):
    """List all registered MCP tools."""
    registry = get_registry()
    tools = registry.list_tools()
    return {
        "tools": tools,
        "total": len(tools),
        "domains": {
            "core_platform": [
                "get_patient_data", "assign_doctor", "send_notification",
                "get_patient_department", "check_doctor_availability",
            ],
            "triage": [
                "calculate_triage_score", "classify_emergency_level",
                "prioritize_waitlist", "flag_critical_case", "record_triage_assessment",
            ],
            "bed_management": [
                "get_bed_inventory", "find_best_bed_match", "reserve_bed",
                "assign_bed", "release_bed", "get_occupancy_snapshot",
            ],
            "billing": [
                "initiate_billing_case", "map_services_to_charge_codes",
                "calculate_estimated_bill", "generate_itemized_invoice",
                "create_claim", "validate_claim", "submit_claim", "track_claim_status",
            ],
            "lab": [
                "create_lab_order", "collect_sample", "track_sample_status",
                "get_lab_result", "flag_critical_lab_result", "attach_lab_report",
            ],
            "insurance": ["get_insurance_eligibility"],
        },
    }


@app.get("/execution_logs", summary="View execution history")
async def get_execution_logs(
    _: User = Depends(
        require_roles(
            UserRole.SUPER_ADMIN,
            UserRole.STAFF,
            UserRole.DOCTOR,
            UserRole.AUDITOR,
        )
    ),
):
    """View all past workflow execution logs."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(ExecutionRecord).order_by(ExecutionRecord.started_at.desc())
        )
        records = result.scalars().all()

    history = [r.log_data for r in records if r.log_data]

    # Fallback to in-memory records (e.g., before persistence exists)
    if not history:
        memory_history = orchestrator.get_execution_history()
        history = [log.model_dump(mode="json") for log in memory_history]

    return {
        "executions": history,
        "total": len(history),
    }


@app.get("/patients", response_model=list[PatientResponse], summary="List all patients")
async def list_patients(
    _: User = Depends(
        require_roles(
            UserRole.SUPER_ADMIN,
            UserRole.STAFF,
            UserRole.DOCTOR,
            UserRole.AUDITOR,
        )
    ),
):
    """List all patients from database."""
    async with async_session_factory() as session:
        result = await session.execute(select(Patient).order_by(Patient.id.asc()))
        patients = result.scalars().all()
    return [PatientResponse(**p.to_dict()) for p in patients]

@app.post(
    "/patient/intake",
    response_model=DepartmentRecommendationResponse,
    summary="Analyze symptoms and recommend department",
)
async def patient_intake(request: SymptomIntakeRequest):
    """Public patient-intake endpoint for symptom analysis and department recommendation."""
    registry = get_registry()

    score_result = await registry.call(
        "calculate_triage_score",
        {
            "patient_id": request.patient_id or 0,
            "vitals": request.vitals,
            "chief_complaint": request.symptoms,
            "age": request.age or 0,
        },
        caller_agent="api",
    )
    if not score_result.success:
        raise HTTPException(status_code=500, detail=score_result.error)

    triage_score = float(score_result.result.get("score", 0.0))
    urgency_level = score_result.result.get("urgency_level", "non-urgent")

    recommend_result = await registry.call(
        "recommend_department_from_symptoms",
        {
            "symptoms": request.symptoms,
            "urgency_level": urgency_level,
        },
        caller_agent="api",
    )
    if not recommend_result.success:
        raise HTTPException(status_code=500, detail=recommend_result.error)

    recommendation = recommend_result.result
    return DepartmentRecommendationResponse(
        recommended_department=recommendation.get("recommended_department", "general"),
        urgency_level=urgency_level,
        triage_score=triage_score,
        explanation=recommendation.get("explanation", "Department recommendation generated"),
        suggested_next_step="Review doctors in the recommended department and choose an available slot.",
    )


@app.get(
    "/departments/{department}/doctors",
    response_model=list[DoctorSummaryResponse],
    summary="List available doctors by department",
)
async def get_available_doctors(department: str):
    """Public endpoint listing available doctors for a department."""
    registry = get_registry()
    result = await registry.call(
        "list_available_doctors",
        {"department": department},
        caller_agent="api",
    )
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)

    doctors = result.result.get("doctors", [])
    return [DoctorSummaryResponse(**d) for d in doctors]


@app.get(
    "/doctors/{doctor_id}/slots",
    response_model=list[AvailabilitySlotResponse],
    summary="List available slots for a doctor and date",
)
async def get_doctor_slots(
    doctor_id: int,
    date: str = Query(..., description="Date in YYYY-MM-DD"),
):
    """Public endpoint to fetch available 30-minute slots for booking."""
    registry = get_registry()
    result = await registry.call(
        "get_doctor_slots",
        {"doctor_id": doctor_id, "date": date},
        caller_agent="api",
    )
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)

    if result.result.get("error"):
        raise HTTPException(status_code=404, detail=result.result["error"])

    slots = result.result.get("slots", [])
    return [
        AvailabilitySlotResponse(
            slot_id=s["id"],
            doctor_id=s["doctor_id"],
            department=s["department"],
            slot_start=s["slot_start"],
            slot_end=s["slot_end"],
        )
        for s in slots
    ]


@app.post(
    "/appointments/book",
    response_model=AppointmentResponse,
    summary="Book an appointment from selected doctor slot",
)
async def book_appointment(request: AppointmentBookingRequest):
    """Public endpoint to create appointment booking."""
    registry = get_registry()
    result = await registry.call(
        "book_appointment",
        {
            "patient_id": request.patient_id,
            "doctor_id": request.doctor_id,
            "slot_id": request.slot_id,
            "symptoms": request.symptoms or "",
        },
        caller_agent="api",
    )
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)

    if result.result.get("error"):
        detail = result.result["error"]
        code = 409 if "already booked" in detail.lower() else 404
        raise HTTPException(status_code=code, detail=detail)

    appointment = result.result.get("appointment") or {}

    await registry.call(
        "send_notification",
        {
            "message": (
                f"Appointment confirmed for patient {request.patient_id} "
                f"with doctor {request.doctor_id} at {appointment.get('appointment_start', '-')}."
            ),
            "recipient": f"patient_{request.patient_id}",
            "channel": "system",
        },
        caller_agent="api",
    )

    return AppointmentResponse(**appointment)


@app.get(
    "/appointments/{appointment_id}/confirmation",
    response_model=AppointmentConfirmationResponse,
    summary="Fetch booking confirmation details",
)
async def get_appointment_confirmation(appointment_id: int):
    """Return confirmation payload for patient confirmation page."""
    registry = get_registry()
    details = await registry.call(
        "get_appointment_details",
        {"appointment_id": appointment_id},
        caller_agent="api",
    )
    if not details.success:
        raise HTTPException(status_code=500, detail=details.error)
    if details.result.get("error"):
        raise HTTPException(status_code=404, detail=details.result["error"])

    appointment = details.result

    async with async_session_factory() as session:
        p_result = await session.execute(select(Patient).where(Patient.id == appointment["patient_id"]))
        d_result = await session.execute(select(Doctor).where(Doctor.id == appointment["doctor_id"]))
        patient = p_result.scalar_one_or_none()
        doctor = d_result.scalar_one_or_none()

    patient_name = patient.name if patient else f"Patient {appointment['patient_id']}"
    doctor_name = doctor.name if doctor else f"Doctor {appointment['doctor_id']}"

    return AppointmentConfirmationResponse(
        appointment=AppointmentResponse(**appointment),
        patient_name=patient_name,
        doctor_name=doctor_name,
        message="Your appointment is confirmed. Please download the appointment letter.",
    )


@app.get(
    "/appointments/{appointment_id}/letter",
    summary="Download appointment letter PDF",
)
async def download_appointment_letter(appointment_id: int):
    """Generate and stream a PDF appointment letter."""
    registry = get_registry()
    details = await registry.call(
        "get_appointment_details",
        {"appointment_id": appointment_id},
        caller_agent="api",
    )
    if not details.success:
        raise HTTPException(status_code=500, detail=details.error)
    if details.result.get("error"):
        raise HTTPException(status_code=404, detail=details.result["error"])

    appointment = details.result
    async with async_session_factory() as session:
        p_result = await session.execute(select(Patient).where(Patient.id == appointment["patient_id"]))
        d_result = await session.execute(select(Doctor).where(Doctor.id == appointment["doctor_id"]))
        patient = p_result.scalar_one_or_none()
        doctor = d_result.scalar_one_or_none()

    patient_name = patient.name if patient else f"Patient {appointment['patient_id']}"
    doctor_name = doctor.name if doctor else f"Doctor {appointment['doctor_id']}"

    pdf_bytes = build_appointment_letter_pdf(
        appointment=appointment,
        patient_name=patient_name,
        doctor_name=doctor_name,
    )
    filename = f"appointment-letter-{appointment_id}.pdf"

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get(
    "/doctor/dashboard/context",
    response_model=DoctorDashboardContextResponse,
    summary="Doctor dashboard: resolve doctor profile for current login",
)
async def get_doctor_dashboard_context(
    current_user: User = Depends(require_roles(UserRole.DOCTOR)),
):
    """Resolve doctor_id from the current doctor's login for automatic UI population."""
    async with async_session_factory() as session:
        link_result = await session.execute(
            select(UserDoctorLink).where(UserDoctorLink.user_id == current_user.id)
        )
        link = link_result.scalar_one_or_none()

        if link is not None:
            doctor_result = await session.execute(select(Doctor).where(Doctor.id == link.doctor_id))
            doctor = doctor_result.scalar_one_or_none()
            if doctor is not None:
                return DoctorDashboardContextResponse(
                    user_id=current_user.id,
                    username=current_user.username,
                    doctor_id=doctor.id,
                    doctor_name=doctor.name,
                    department=doctor.department,
                    mapped=True,
                )

        # Demo-safe fallback: if not mapped yet, bind this doctor user to first doctor profile.
        fallback_result = await session.execute(select(Doctor).order_by(Doctor.id.asc()))
        fallback_doctor = fallback_result.scalars().first()
        if fallback_doctor is None:
            return DoctorDashboardContextResponse(
                user_id=current_user.id,
                username=current_user.username,
                doctor_id=None,
                doctor_name=None,
                department=None,
                mapped=False,
            )

        session.add(UserDoctorLink(user_id=current_user.id, doctor_id=fallback_doctor.id))
        await session.commit()

        return DoctorDashboardContextResponse(
            user_id=current_user.id,
            username=current_user.username,
            doctor_id=fallback_doctor.id,
            doctor_name=fallback_doctor.name,
            department=fallback_doctor.department,
            mapped=True,
        )


@app.get(
    "/doctors/{doctor_id}/appointments",
    response_model=list[AppointmentResponse],
    summary="Doctor dashboard: list appointments",
)
async def list_doctor_appointments(
    doctor_id: int,
    date: str = Query(default="", description="Optional YYYY-MM-DD date filter"),
    _: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.STAFF, UserRole.DOCTOR)),
):
    """List appointments for a doctor, optional date filtering for dashboard."""
    registry = get_registry()
    result = await registry.call(
        "list_doctor_appointments",
        {"doctor_id": doctor_id, "date": date},
        caller_agent="api",
    )
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    if result.result.get("error"):
        raise HTTPException(status_code=400, detail=result.result["error"])

    return [AppointmentResponse(**a) for a in result.result.get("appointments", [])]


@app.patch(
    "/appointments/{appointment_id}",
    response_model=AppointmentResponse,
    summary="Doctor dashboard: update appointment status/notes",
)
async def patch_appointment(
    appointment_id: int,
    request: DoctorAppointmentUpdateRequest,
    _: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.STAFF, UserRole.DOCTOR)),
):
    """Update appointment status and/or notes from doctor dashboard actions."""
    registry = get_registry()
    result = await registry.call(
        "update_appointment",
        {
            "appointment_id": appointment_id,
            "status": request.status or "",
            "notes": request.notes or "",
        },
        caller_agent="api",
    )

    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    if result.result.get("error"):
        detail = result.result["error"]
        code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=code, detail=detail)

    return AppointmentResponse(**(result.result.get("appointment") or {}))


@app.post(
    "/doctors/appointments/{appointment_id}/multi-agent-workflow",
    summary="Doctor dashboard: run real multi-agent follow-up workflow",
)
async def run_doctor_multi_agent_workflow(
    appointment_id: int,
    request: DoctorMultiAgentWorkflowRequest,
    current_user: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.STAFF, UserRole.DOCTOR)),
):
    """
    Trigger a real multi-agent workflow from doctor dashboard context.

    Flow is generated by planner rule `doctor_followup_workflow` and executed
    by orchestrator, so timeline includes true agent and A2A interactions.
    """
    async with async_session_factory() as session:
        a_result = await session.execute(select(Appointment).where(Appointment.id == appointment_id))
        appointment = a_result.scalar_one_or_none()
        if appointment is None:
            raise HTTPException(status_code=404, detail=f"Appointment {appointment_id} not found")

        p_result = await session.execute(select(Patient).where(Patient.id == appointment.patient_id))
        patient = p_result.scalar_one_or_none()
        if patient is None:
            raise HTTPException(status_code=404, detail=f"Patient {appointment.patient_id} not found")

        profile_result = await session.execute(
            select(PatientInsuranceProfile).where(PatientInsuranceProfile.patient_id == patient.id)
        )
        profile = profile_result.scalar_one_or_none()

    context = {
        "appointment_id": appointment.id,
        "patient_id": patient.id,
        "doctor_id": appointment.doctor_id,
        "department": (appointment.department or patient.department or "general"),
        "chief_complaint": (
            request.chief_complaint
            or appointment.notes
            or patient.condition
            or request.workflow_reason
            or "doctor follow-up review"
        ),
        "test_name": (request.test_name or "CBC"),
        "priority": (request.priority or "urgent"),
        "ordered_by": f"doctor_dashboard_user_{current_user.id}",
        "insurance_provider": (profile.insurance_provider if profile else "default"),
        "member_id": (profile.member_id if profile else ""),
        "plan_type": (profile.plan_type if profile else "general"),
        "_user_id": current_user.id,
        "_user_role": current_user.role,
    }

    agent_capabilities = orchestrator.get_agent_capabilities()
    plan = await planner.plan(
        event="doctor_followup_workflow",
        context=context,
        agent_capabilities=agent_capabilities,
    )

    execution_log = await orchestrator.execute_plan(
        plan,
        user_id=current_user.id,
        user_role=current_user.role,
    )

    return JSONResponse(
        status_code=200,
        content={
            "status": execution_log.status,
            "execution_id": execution_log.execution_id,
            "event": execution_log.event,
            "plan": plan.model_dump(mode="json"),
            "execution": execution_log.model_dump(mode="json"),
            "summary": {
                "total_steps": len(execution_log.steps),
                "completed": sum(1 for s in execution_log.steps if s.status == "completed"),
                "failed": sum(1 for s in execution_log.steps if s.status == "failed"),
                "total_duration_ms": execution_log.total_duration_ms,
            },
        },
    )


@app.get(
    "/patient/appointments",
    response_model=list[AppointmentResponse],
    summary="Patient portal: list patient appointments by date",
)
async def patient_list_appointments(
    patient_id: int = Query(..., ge=1, description="Patient ID"),
    date: str = Query(default="", description="Optional YYYY-MM-DD date filter"),
    _: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.STAFF, UserRole.PATIENT)),
):
    """Return appointments for a patient, optionally filtered by date for schedule calendar view."""
    async with async_session_factory() as session:
        patient_result = await session.execute(select(Patient).where(Patient.id == patient_id))
        patient = patient_result.scalar_one_or_none()
        if patient is None:
            raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

        stmt = (
            select(Appointment)
            .where(Appointment.patient_id == patient_id)
            .order_by(Appointment.appointment_start.asc())
        )
        if date.strip():
            try:
                target_date = datetime.strptime(date.strip(), "%Y-%m-%d").date()
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Invalid date format. Expected YYYY-MM-DD") from exc
            stmt = stmt.where(func.date(Appointment.appointment_start) == target_date)

        result = await session.execute(stmt)
        appointments = result.scalars().all()

    return [AppointmentResponse(**row.to_dict()) for row in appointments]


@app.get(
    "/patient/billing",
    response_model=PatientBillingOverviewResponse,
    summary="Patient portal: billing + insurance claim status",
)
async def patient_billing_overview(
    patient_id: int = Query(..., ge=1, description="Patient ID"),
    _: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.STAFF, UserRole.PATIENT)),
):
    """Get patient billing cases with linked insurance claim status and claim eligibility."""
    async with async_session_factory() as session:
        p_result = await session.execute(select(Patient).where(Patient.id == patient_id))
        patient = p_result.scalar_one_or_none()
        if patient is None:
            raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

        profile_result = await session.execute(
            select(PatientInsuranceProfile).where(PatientInsuranceProfile.patient_id == patient_id)
        )
        profile = profile_result.scalar_one_or_none()

        b_result = await session.execute(
            select(BillingCase)
            .where(BillingCase.patient_id == patient_id)
            .order_by(BillingCase.created_at.desc())
        )
        cases = b_result.scalars().all()

        records: list[PatientBillingRecordResponse] = []
        for case in cases:
            claim_result = await session.execute(
                select(InsuranceClaim)
                .where(InsuranceClaim.billing_case_id == case.id)
                .order_by(InsuranceClaim.created_at.desc())
            )
            claim = claim_result.scalars().first()

            insurance_status = claim.status if claim is not None else "not_claimed"
            records.append(
                PatientBillingRecordResponse(
                    billing_case=BillingCaseResponse(**case.to_dict()),
                    insurance_claim=InsuranceClaimResponse(**claim.to_dict()) if claim else None,
                    insurance_status=insurance_status,
                    can_claim_insurance=claim is None,
                )
            )

    return PatientBillingOverviewResponse(
        patient_id=patient_id,
        insurance_profile=PatientInsuranceProfileResponse(**profile.to_dict()) if profile else None,
        records=records,
    )


@app.get(
    "/patient/insurance/profile",
    response_model=PatientInsuranceProfileResponse,
    summary="Patient portal: get saved insurance details",
)
async def get_patient_insurance_profile(
    patient_id: int = Query(..., ge=1, description="Patient ID"),
    _: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.STAFF, UserRole.PATIENT)),
):
    """Return saved insurance profile for the patient (or empty profile if not yet saved)."""
    async with async_session_factory() as session:
        p_result = await session.execute(select(Patient).where(Patient.id == patient_id))
        patient = p_result.scalar_one_or_none()
        if patient is None:
            raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

        profile_result = await session.execute(
            select(PatientInsuranceProfile).where(PatientInsuranceProfile.patient_id == patient_id)
        )
        profile = profile_result.scalar_one_or_none()

    if profile is None:
        return PatientInsuranceProfileResponse(patient_id=patient_id)
    return PatientInsuranceProfileResponse(**profile.to_dict())


@app.put(
    "/patient/insurance/profile",
    response_model=PatientInsuranceProfileResponse,
    summary="Patient portal: save insurance details",
)
async def upsert_patient_insurance_profile(
    request: PatientInsuranceProfileUpdateRequest,
    patient_id: int = Query(..., ge=1, description="Patient ID"),
    _: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.STAFF, UserRole.PATIENT)),
):
    """Create/update saved patient insurance profile used by claim action."""
    async with async_session_factory() as session:
        p_result = await session.execute(select(Patient).where(Patient.id == patient_id))
        patient = p_result.scalar_one_or_none()
        if patient is None:
            raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

        profile_result = await session.execute(
            select(PatientInsuranceProfile).where(PatientInsuranceProfile.patient_id == patient_id)
        )
        profile = profile_result.scalar_one_or_none()

        if profile is None:
            profile = PatientInsuranceProfile(patient_id=patient_id)
            session.add(profile)

        if request.insurance_provider is not None:
            profile.insurance_provider = request.insurance_provider
        if request.plan_type is not None:
            profile.plan_type = request.plan_type
        if request.member_id is not None:
            profile.member_id = request.member_id
        if request.policy_number is not None:
            profile.policy_number = request.policy_number
        if request.group_number is not None:
            profile.group_number = request.group_number

        await session.commit()
        await session.refresh(profile)

    return PatientInsuranceProfileResponse(**profile.to_dict())


@app.post(
    "/patient/billing/{case_id}/claim-insurance",
    response_model=InsuranceClaimResponse,
    summary="Patient portal: create insurance claim for billing case",
)
async def patient_claim_insurance(
    case_id: int,
    request: CreateInsuranceClaimRequest,
    patient_id: int = Query(..., ge=1, description="Patient ID"),
    _: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.STAFF, UserRole.PATIENT)),
):
    """Create an insurance claim for a patient's billing case if not already claimed."""
    async with async_session_factory() as session:
        case_result = await session.execute(select(BillingCase).where(BillingCase.id == case_id))
        case = case_result.scalar_one_or_none()
        if case is None:
            raise HTTPException(status_code=404, detail=f"Billing case {case_id} not found")
        if case.patient_id != patient_id:
            raise HTTPException(status_code=400, detail="Billing case does not belong to this patient")

        existing_claim_result = await session.execute(
            select(InsuranceClaim).where(InsuranceClaim.billing_case_id == case_id)
        )
        existing_claim = existing_claim_result.scalars().first()
        if existing_claim is not None:
            return InsuranceClaimResponse(**existing_claim.to_dict())

        profile_result = await session.execute(
            select(PatientInsuranceProfile).where(PatientInsuranceProfile.patient_id == patient_id)
        )
        profile = profile_result.scalar_one_or_none()

        if profile is None:
            profile = PatientInsuranceProfile(patient_id=patient_id)
            session.add(profile)

        # Keep profile in sync with any explicitly provided request details
        if request.insurance_provider is not None:
            profile.insurance_provider = request.insurance_provider
        if request.plan_type is not None:
            profile.plan_type = request.plan_type
        if request.member_id is not None:
            profile.member_id = request.member_id

        claim_amount = case.estimated_total if case.estimated_total is not None else 0.0
        new_claim = InsuranceClaim(
            patient_id=patient_id,
            billing_case_id=case_id,
            insurance_provider=profile.insurance_provider or "default",
            plan_type=profile.plan_type or "general",
            member_id=profile.member_id,
            status="pending",
            claim_amount=claim_amount,
            approved_amount=0.0,
            eligibility_verified=False,
        )

        session.add(new_claim)
        await session.flush()
        case.insurance_claim_id = new_claim.id
        await session.commit()
        await session.refresh(new_claim)

    return InsuranceClaimResponse(**new_claim.to_dict())


@app.get(
    "/staff/insurance/profiles",
    response_model=list[PatientInsuranceProfileResponse],
    summary="Staff: list saved patient insurance details",
)
async def staff_list_insurance_profiles(
    q: str = Query(default="", description="Optional patient_id filter"),
    _: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.STAFF)),
):
    """List saved insurance profiles so superadmin/staff can verify patient insurance details."""
    async with async_session_factory() as session:
        stmt = select(PatientInsuranceProfile).order_by(PatientInsuranceProfile.updated_at.desc())
        if q.strip().isdigit():
            stmt = stmt.where(PatientInsuranceProfile.patient_id == int(q.strip()))

        result = await session.execute(stmt)
        profiles = result.scalars().all()

    return [PatientInsuranceProfileResponse(**p.to_dict()) for p in profiles]


@app.post("/patients", response_model=PatientResponse, summary="Create a new patient")
async def create_patient(
    request: CreatePatientRequest,
    _: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.STAFF)),
):
    """Create and persist a new patient record."""
    async with async_session_factory() as session:
        patient = Patient(
            name=request.name,
            age=request.age,
            department=request.department.lower().strip(),
            condition=request.condition,
            admitted=False,
        )
        session.add(patient)
        await session.commit()
        await session.refresh(patient)

    return PatientResponse(**patient.to_dict())


@app.post(
    "/patient/resolve",
    response_model=PatientResolveResponse,
    summary="Resolve patient identity and generate patient ID when not registered",
)
async def resolve_patient_identity(request: PatientResolveRequest):
    """
    Resolve whether a patient is already registered.

    Behavior:
    - If patient_id exists in DB → return registered=True.
    - Else if name+age matches existing patient → return registered=True.
    - Else create a new patient and return generated patient_id.
    """
    async with async_session_factory() as session:
        if request.patient_id is not None:
            id_result = await session.execute(select(Patient).where(Patient.id == request.patient_id))
            by_id = id_result.scalar_one_or_none()
            if by_id is not None:
                return PatientResolveResponse(
                    patient_id=by_id.id,
                    patient_name=by_id.name,
                    registered=True,
                    generated=False,
                    message=f"Registered patient found (ID: {by_id.id}).",
                )

        normalized_name = (request.name or "").strip()
        if normalized_name and request.age is not None:
            match_result = await session.execute(
                select(Patient).where(
                    func.lower(Patient.name) == normalized_name.lower(),
                    Patient.age == request.age,
                )
            )
            matched = match_result.scalar_one_or_none()
            if matched is not None:
                return PatientResolveResponse(
                    patient_id=matched.id,
                    patient_name=matched.name,
                    registered=True,
                    generated=False,
                    message=f"Registered patient matched by name and age (ID: {matched.id}).",
                )

        fallback_name = normalized_name or f"Walk-in Patient {datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        fallback_age = request.age if request.age is not None else 30
        fallback_department = (request.department or "general").lower().strip()
        fallback_condition = request.condition or "Pending triage assessment"

        new_patient = Patient(
            name=fallback_name,
            age=fallback_age,
            department=fallback_department,
            condition=fallback_condition,
            admitted=False,
        )
        session.add(new_patient)
        await session.commit()
        await session.refresh(new_patient)

        return PatientResolveResponse(
            patient_id=new_patient.id,
            patient_name=new_patient.name,
            registered=False,
            generated=True,
            message=f"Patient not registered. New patient ID generated: {new_patient.id}.",
        )


@app.get(
    "/staff/patients",
    response_model=list[PatientResponse],
    summary="Staff: list patients",
)
async def staff_list_patients(
    q: str = Query(default="", description="Optional patient name search"),
    _: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.STAFF)),
):
    """List patients for staff operations with optional search by name."""
    async with async_session_factory() as session:
        stmt = select(Patient).order_by(Patient.id.asc())
        if q.strip():
            stmt = stmt.where(Patient.name.ilike(f"%{q.strip()}%"))
        result = await session.execute(stmt)
        patients = result.scalars().all()

    return [PatientResponse(**p.to_dict()) for p in patients]


@app.get(
    "/staff/patients/{patient_id}",
    response_model=PatientDetailResponse,
    summary="Staff: get patient detail",
)
async def staff_get_patient_detail(
    patient_id: int,
    _: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.STAFF)),
):
    """Get single patient with linked appointments, billing cases, and insurance claims."""
    async with async_session_factory() as session:
        p_result = await session.execute(select(Patient).where(Patient.id == patient_id))
        patient = p_result.scalar_one_or_none()
        if patient is None:
            raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

        a_result = await session.execute(
            select(Appointment)
            .where(Appointment.patient_id == patient_id)
            .order_by(Appointment.appointment_start.desc())
        )
        b_result = await session.execute(
            select(BillingCase)
            .where(BillingCase.patient_id == patient_id)
            .order_by(BillingCase.created_at.desc())
        )
        c_result = await session.execute(
            select(InsuranceClaim)
            .where(InsuranceClaim.patient_id == patient_id)
            .order_by(InsuranceClaim.created_at.desc())
        )

        appointments = [AppointmentResponse(**a.to_dict()) for a in a_result.scalars().all()]
        billing_cases = [BillingCaseResponse(**b.to_dict()) for b in b_result.scalars().all()]
        insurance_claims = [InsuranceClaimResponse(**c.to_dict()) for c in c_result.scalars().all()]

    return PatientDetailResponse(
        patient=PatientResponse(**patient.to_dict()),
        appointments=appointments,
        billing_cases=billing_cases,
        insurance_claims=insurance_claims,
    )


@app.patch(
    "/staff/patients/{patient_id}",
    response_model=PatientResponse,
    summary="Staff: update patient",
)
async def staff_patch_patient(
    patient_id: int,
    request: PatientUpdateRequest,
    _: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.STAFF)),
):
    """Update core patient fields used by staff operations."""
    async with async_session_factory() as session:
        result = await session.execute(select(Patient).where(Patient.id == patient_id))
        patient = result.scalar_one_or_none()
        if patient is None:
            raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

        if request.department is not None:
            patient.department = request.department.lower().strip()
        if request.condition is not None:
            patient.condition = request.condition
        if request.admitted is not None:
            patient.admitted = request.admitted
        if request.bed_id is not None:
            patient.bed_id = request.bed_id

        await session.commit()
        await session.refresh(patient)

    return PatientResponse(**patient.to_dict())


@app.get(
    "/staff/beds",
    response_model=list[BedResponse],
    summary="Staff: list beds",
)
async def staff_list_beds(
    ward: str = Query(default="", description="Optional ward filter"),
    status_filter: str = Query(default="", alias="status", description="Optional status filter"),
    _: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.STAFF)),
):
    """List bed inventory with optional ward and status filters."""
    async with async_session_factory() as session:
        stmt = select(Bed).order_by(Bed.ward.asc(), Bed.bed_number.asc())
        if ward.strip():
            stmt = stmt.where(Bed.ward.ilike(ward.strip()))
        if status_filter.strip():
            stmt = stmt.where(Bed.status.ilike(status_filter.strip()))

        result = await session.execute(stmt)
        beds = result.scalars().all()

    return [BedResponse(**b.to_dict()) for b in beds]


@app.patch(
    "/staff/beds/{bed_id}",
    response_model=BedResponse,
    summary="Staff: update bed state",
)
async def staff_patch_bed(
    bed_id: int,
    request: BedUpdateRequest,
    _: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.STAFF)),
):
    """Update bed occupancy/reservation fields for bed management UI operations."""
    async with async_session_factory() as session:
        result = await session.execute(select(Bed).where(Bed.id == bed_id))
        bed = result.scalar_one_or_none()
        if bed is None:
            raise HTTPException(status_code=404, detail=f"Bed {bed_id} not found")

        if request.status is not None:
            bed.status = request.status
        if request.patient_id is not None:
            bed.patient_id = request.patient_id
        if request.reserved_for_patient_id is not None:
            bed.reserved_for_patient_id = request.reserved_for_patient_id

        await session.commit()
        await session.refresh(bed)

    return BedResponse(**bed.to_dict())


@app.get(
    "/staff/billing/cases",
    response_model=list[BillingCaseResponse],
    summary="Staff: list billing cases",
)
async def staff_list_billing_cases(
    status_filter: str = Query(default="", alias="status", description="Optional status filter"),
    _: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.STAFF)),
):
    """List billing cases with optional status filtering."""
    async with async_session_factory() as session:
        stmt = select(BillingCase).order_by(BillingCase.created_at.desc())
        if status_filter.strip():
            stmt = stmt.where(BillingCase.status.ilike(status_filter.strip()))
        result = await session.execute(stmt)
        cases = result.scalars().all()

    return [BillingCaseResponse(**c.to_dict()) for c in cases]


@app.get(
    "/staff/billing/cases/{case_id}",
    response_model=BillingCaseResponse,
    summary="Staff: get billing case detail",
)
async def staff_get_billing_case(
    case_id: int,
    _: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.STAFF)),
):
    """Get a single billing case."""
    async with async_session_factory() as session:
        result = await session.execute(select(BillingCase).where(BillingCase.id == case_id))
        case = result.scalar_one_or_none()

    if case is None:
        raise HTTPException(status_code=404, detail=f"Billing case {case_id} not found")

    return BillingCaseResponse(**case.to_dict())


@app.patch(
    "/staff/billing/cases/{case_id}",
    response_model=BillingCaseResponse,
    summary="Staff: update billing case",
)
async def staff_patch_billing_case(
    case_id: int,
    request: BillingCaseUpdateRequest,
    _: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.STAFF)),
):
    """Update billing case financial/status fields."""
    async with async_session_factory() as session:
        result = await session.execute(select(BillingCase).where(BillingCase.id == case_id))
        case = result.scalar_one_or_none()
        if case is None:
            raise HTTPException(status_code=404, detail=f"Billing case {case_id} not found")

        if request.status is not None:
            case.status = request.status
        if request.estimated_total is not None:
            case.estimated_total = request.estimated_total
        if request.invoice_number is not None:
            case.invoice_number = request.invoice_number

        await session.commit()
        await session.refresh(case)

    return BillingCaseResponse(**case.to_dict())


@app.get(
    "/staff/insurance/claims",
    response_model=list[InsuranceClaimResponse],
    summary="Staff: list insurance claims",
)
async def staff_list_insurance_claims(
    status_filter: str = Query(default="", alias="status", description="Optional status filter"),
    _: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.STAFF)),
):
    """List insurance claims with optional status filtering."""
    async with async_session_factory() as session:
        stmt = select(InsuranceClaim).order_by(InsuranceClaim.created_at.desc())
        if status_filter.strip():
            stmt = stmt.where(InsuranceClaim.status.ilike(status_filter.strip()))
        result = await session.execute(stmt)
        claims = result.scalars().all()

    return [InsuranceClaimResponse(**c.to_dict()) for c in claims]


@app.get(
    "/staff/insurance/claims/{claim_id}",
    response_model=InsuranceClaimResponse,
    summary="Staff: get insurance claim detail",
)
async def staff_get_insurance_claim(
    claim_id: int,
    _: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.STAFF)),
):
    """Get a single insurance claim."""
    async with async_session_factory() as session:
        result = await session.execute(select(InsuranceClaim).where(InsuranceClaim.id == claim_id))
        claim = result.scalar_one_or_none()

    if claim is None:
        raise HTTPException(status_code=404, detail=f"Insurance claim {claim_id} not found")

    return InsuranceClaimResponse(**claim.to_dict())


@app.patch(
    "/staff/insurance/claims/{claim_id}",
    response_model=InsuranceClaimResponse,
    summary="Staff: update insurance claim",
)
async def staff_patch_insurance_claim(
    claim_id: int,
    request: InsuranceClaimUpdateRequest,
    _: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.STAFF)),
):
    """Update insurance claim status and amount fields."""
    async with async_session_factory() as session:
        result = await session.execute(select(InsuranceClaim).where(InsuranceClaim.id == claim_id))
        claim = result.scalar_one_or_none()
        if claim is None:
            raise HTTPException(status_code=404, detail=f"Insurance claim {claim_id} not found")

        if request.status is not None:
            claim.status = request.status
            if request.status.lower() == "submitted":
                claim.submitted_at = datetime.utcnow()
        if request.claim_amount is not None:
            claim.claim_amount = request.claim_amount
        if request.approved_amount is not None:
            claim.approved_amount = request.approved_amount
        if request.rejection_reason is not None:
            claim.rejection_reason = request.rejection_reason

        await session.commit()
        await session.refresh(claim)

    return InsuranceClaimResponse(**claim.to_dict())


@app.get(
    "/staff/reports/summary",
    response_model=StaffReportSummaryResponse,
    summary="Staff: operational summary report",
)
async def staff_reports_summary(
    _: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.STAFF)),
):
    """Return aggregate KPIs for staff dashboard reporting widgets."""
    async with async_session_factory() as session:
        total_patients = (await session.execute(select(func.count(Patient.id)))).scalar() or 0
        admitted_patients = (
            await session.execute(select(func.count(Patient.id)).where(Patient.admitted.is_(True)))
        ).scalar() or 0

        total_beds = (await session.execute(select(func.count(Bed.id)))).scalar() or 0
        occupied_beds = (
            await session.execute(select(func.count(Bed.id)).where(Bed.status.ilike("occupied")))
        ).scalar() or 0
        available_beds = (
            await session.execute(select(func.count(Bed.id)).where(Bed.status.ilike("available")))
        ).scalar() or 0

        open_billing_cases = (
            await session.execute(select(func.count(BillingCase.id)).where(BillingCase.status.ilike("open")))
        ).scalar() or 0
        total_estimated_billing = (
            await session.execute(select(func.coalesce(func.sum(BillingCase.estimated_total), 0.0)))
        ).scalar() or 0.0

        submitted_claims = (
            await session.execute(
                select(func.count(InsuranceClaim.id)).where(InsuranceClaim.status.ilike("submitted"))
            )
        ).scalar() or 0
        pending_claims = (
            await session.execute(
                select(func.count(InsuranceClaim.id)).where(InsuranceClaim.status.ilike("pending"))
            )
        ).scalar() or 0

        confirmed_appointments = (
            await session.execute(
                select(func.count(Appointment.id)).where(Appointment.status.ilike("confirmed"))
            )
        ).scalar() or 0
        completed_appointments = (
            await session.execute(
                select(func.count(Appointment.id)).where(Appointment.status.ilike("completed"))
            )
        ).scalar() or 0
        cancelled_appointments = (
            await session.execute(
                select(func.count(Appointment.id)).where(Appointment.status.ilike("cancelled"))
            )
        ).scalar() or 0

    return StaffReportSummaryResponse(
        total_patients=int(total_patients),
        admitted_patients=int(admitted_patients),
        total_beds=int(total_beds),
        occupied_beds=int(occupied_beds),
        available_beds=int(available_beds),
        open_billing_cases=int(open_billing_cases),
        submitted_claims=int(submitted_claims),
        pending_claims=int(pending_claims),
        confirmed_appointments=int(confirmed_appointments),
        completed_appointments=int(completed_appointments),
        cancelled_appointments=int(cancelled_appointments),
        total_estimated_billing=float(total_estimated_billing),
    )


@app.get("/planning_rules", summary="View all planner rules")
async def get_planning_rules(
    _: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.AUDITOR)),
):
    """View all 9 planning rules in the system."""
    return {
        "rules": planner.list_rules(),
        "total": len(planner.list_rules()),
        "note": "Rules are matched by event pattern (glob-style). "
                "First match (by priority) wins. Add rules to extend without code changes.",
    }


@app.get("/bed_status", summary="View bed inventory and occupancy")
async def get_bed_status(
    current_user: User = Depends(
        require_roles(
            UserRole.SUPER_ADMIN,
            UserRole.STAFF,
            UserRole.DOCTOR,
            UserRole.AUDITOR,
        )
    ),
):
    """
    Get live bed occupancy snapshot across all wards.
    Routes through BedManagementAgent via a quick event.
    """
    try:
        registry = get_registry()
        snapshot = await registry.call(
            "get_occupancy_snapshot",
            {},
            caller_agent="api",
            user_role=current_user.role,
        )
        inventory = await registry.call(
            "get_bed_inventory",
            {"ward": ""},
            caller_agent="api",
            user_role=current_user.role,
        )
        return {
            "occupancy": snapshot.result,
            "inventory": inventory.result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
