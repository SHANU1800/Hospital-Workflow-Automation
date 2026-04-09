"""
Hospital Workflow Automation — FastAPI Application (Plan 1.0).

This is the main entry point. It wires together all layers:
- Initializes the database (including Plan 1.0 tables: beds, lab, billing, etc.)
- Registers all 30 MCP tools (by importing mcp.tools)
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

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# ── Configure logging before anything else ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-24s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("api")

# ── Import all layers ──
from models.database import init_db
from models.schemas import AdmitPatientRequest, GenericEventRequest
from mcp.tool_registry import get_registry
import mcp.tools  # noqa: F401 — triggers all 30 tool registrations

# ── Import all Plan 1.0 agents ──
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

    # 1. Initialize database
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
        "AlertAgent + DataAgent. 30 MCP tools. 9 planning rules."
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


# ─────────────────────────────────────────────
# Workflow Trigger Endpoints
# ─────────────────────────────────────────────

@app.post("/admit_patient", summary="Admit a patient — triggers full 7-step workflow")
async def admit_patient(request: AdmitPatientRequest):
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
        context = {"patient_id": request.patient_id}
        agent_capabilities = orchestrator.get_agent_capabilities()

        plan = await planner.plan(
            event="patient_admitted",
            context=context,
            agent_capabilities=agent_capabilities,
        )

        logger.info(f"📋 Plan generated: {len(plan.tasks)} tasks")
        execution_log = await orchestrator.execute_plan(plan)

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
async def trigger_event(request: GenericEventRequest):
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

        plan = await planner.plan(
            event=request.event,
            context=request.context,
            agent_capabilities=agent_capabilities,
        )

        execution_log = await orchestrator.execute_plan(plan)

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
async def trigger_emergency(request: EmergencyRequest):
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
        }
        agent_capabilities = orchestrator.get_agent_capabilities()

        plan = await planner.plan(
            event=f"emergency_{request.emergency_type}",
            context=context,
            agent_capabilities=agent_capabilities,
        )

        execution_log = await orchestrator.execute_plan(plan)

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
async def create_lab_order(request: LabOrderRequest):
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
        }
        agent_capabilities = orchestrator.get_agent_capabilities()

        plan = await planner.plan(
            event="lab_order_request",
            context=context,
            agent_capabilities=agent_capabilities,
        )

        execution_log = await orchestrator.execute_plan(plan)

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
async def list_agents():
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
async def list_tools():
    """List all 30 registered MCP tools."""
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
        },
    }


@app.get("/execution_logs", summary="View execution history")
async def get_execution_logs():
    """View all past workflow execution logs."""
    history = orchestrator.get_execution_history()
    return {
        "executions": [log.model_dump(mode="json") for log in history],
        "total": len(history),
    }


@app.get("/planning_rules", summary="View all planner rules")
async def get_planning_rules():
    """View all 9 planning rules in the system."""
    return {
        "rules": planner.list_rules(),
        "total": len(planner.list_rules()),
        "note": "Rules are matched by event pattern (glob-style). "
                "First match (by priority) wins. Add rules to extend without code changes.",
    }


@app.get("/bed_status", summary="View bed inventory and occupancy")
async def get_bed_status():
    """
    Get live bed occupancy snapshot across all wards.
    Routes through BedManagementAgent via a quick event.
    """
    try:
        registry = get_registry()
        snapshot = await registry.call("get_occupancy_snapshot", {}, caller_agent="api")
        inventory = await registry.call("get_bed_inventory", {"ward": ""}, caller_agent="api")
        return {
            "occupancy": snapshot.result,
            "inventory": inventory.result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
