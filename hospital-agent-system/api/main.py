"""
Hospital Workflow Automation — FastAPI Application.

This is the main entry point. It wires together all layers:
- Initializes the database
- Registers MCP tools (by importing mcp.tools)
- Creates agents and registers them with the orchestrator
- Exposes API endpoints

Endpoints:
- POST /admit_patient      — Trigger patient admission workflow
- POST /trigger_event       — Trigger ANY event dynamically
- GET  /health              — Health check
- GET  /agents              — List registered agents
- GET  /tools               — List registered MCP tools
- GET  /execution_logs      — View past execution logs
- GET  /planning_rules      — View planner rules
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# ── Configure logging before anything else ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-20s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("api")

# ── Import all layers ──
from models.database import init_db
from models.schemas import AdmitPatientRequest, GenericEventRequest
from mcp.tool_registry import get_registry
import mcp.tools  # noqa: F401 — triggers tool auto-registration
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
# Application Lifespan (startup / shutdown)
# ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup and shutdown handler.
    
    Startup:
    1. Initialize database tables
    2. Seed sample data
    3. Register agents with orchestrator
    4. Log system status
    """
    logger.info("🏥 Hospital Workflow Automation System starting...")

    # 1. Initialize database
    await init_db()

    # 2. Seed sample data
    await seed_database()

    # 3. Create and register agents
    data_agent = DataAgent()
    scheduler_agent = SchedulerAgent()
    alert_agent = AlertAgent()

    orchestrator.register_agent(data_agent)
    orchestrator.register_agent(scheduler_agent)
    orchestrator.register_agent(alert_agent)

    # 4. Log system status
    registry = get_registry()
    logger.info(f"🔧 MCP Tools registered: {registry.get_tool_names()}")
    logger.info(f"🤖 Agents registered: {[a['name'] for a in orchestrator.list_agents()]}")
    logger.info(f"📋 Planning rules: {len(planner.list_rules())}")
    logger.info("✅ System ready!")

    yield  # App is running

    logger.info("🛑 Hospital Workflow Automation System shutting down.")


# ─────────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────────

app = FastAPI(
    title="Hospital Workflow Automation",
    description=(
        "Agent-to-Agent (A2A) hospital workflow system with MCP tool access. "
        "Dynamic planning, modular agents, controlled tool usage."
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
# API Endpoints
# ─────────────────────────────────────────────

@app.post("/admit_patient", summary="Admit a patient — triggers full workflow")
async def admit_patient(request: AdmitPatientRequest):
    """
    Main endpoint: Admit a patient.
    
    Flow:
    1. Planner generates a dynamic plan for 'patient_admitted' event
    2. Orchestrator executes the plan step-by-step
    3. Agents call MCP tools and communicate via A2A
    4. Full execution trace is returned
    """
    logger.info(f"\n{'#'*60}")
    logger.info(f"# NEW REQUEST: Admit Patient {request.patient_id}")
    logger.info(f"{'#'*60}\n")

    try:
        # Step 1: Generate plan dynamically
        context = {"patient_id": request.patient_id}
        agent_capabilities = orchestrator.get_agent_capabilities()
        
        plan = await planner.plan(
            event="patient_admitted",
            context=context,
            agent_capabilities=agent_capabilities,
        )

        logger.info(f"📋 Plan generated: {len(plan.tasks)} tasks")

        # Step 2: Execute plan via orchestrator
        execution_log = await orchestrator.execute_plan(plan)

        # Step 3: Return full execution trace
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
                    "completed": sum(
                        1 for s in execution_log.steps if s.status == "completed"
                    ),
                    "failed": sum(
                        1 for s in execution_log.steps if s.status == "failed"
                    ),
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
    
    The planner will match the event against its rule table
    and generate an appropriate plan.
    
    Examples:
    - {"event": "patient_discharged", "context": {"patient_id": 101}}
    - {"event": "lab_results_ready", "context": {"patient_id": 102}}
    - {"event": "emergency_code_blue", "context": {"patient_id": 103}}
    """
    logger.info(f"\n{'#'*60}")
    logger.info(f"# NEW EVENT: {request.event}")
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
                    "completed": sum(
                        1 for s in execution_log.steps if s.status == "completed"
                    ),
                    "failed": sum(
                        1 for s in execution_log.steps if s.status == "failed"
                    ),
                    "total_duration_ms": execution_log.total_duration_ms,
                },
            },
        )

    except Exception as e:
        logger.error(f"❌ Error processing event: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health", summary="Health check")
async def health_check():
    """Health check endpoint."""
    registry = get_registry()
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "agents": len(orchestrator.list_agents()),
        "tools": len(registry.get_tool_names()),
        "rules": len(planner.list_rules()),
    }


@app.get("/agents", summary="List registered agents")
async def list_agents():
    """List all registered agents and their capabilities."""
    return {
        "agents": orchestrator.list_agents(),
        "total": len(orchestrator.list_agents()),
    }


@app.get("/tools", summary="List registered MCP tools")
async def list_tools():
    """List all registered MCP tools."""
    registry = get_registry()
    return {
        "tools": registry.list_tools(),
        "total": len(registry.list_tools()),
    }


@app.get("/execution_logs", summary="View execution history")
async def get_execution_logs():
    """View all past workflow execution logs."""
    history = orchestrator.get_execution_history()
    return {
        "executions": [log.model_dump(mode="json") for log in history],
        "total": len(history),
    }


@app.get("/planning_rules", summary="View planner rules")
async def get_planning_rules():
    """View all planning rules in the system."""
    return {
        "rules": planner.list_rules(),
        "total": len(planner.list_rules()),
        "note": "Rules are matched by event pattern (glob-style). First match wins.",
    }
