# Project Overview

## Purpose

This project demonstrates how to automate hospital workflows using cooperating agents instead of one monolithic service method.

Typical scenarios:

- New patient admitted
- Patient discharged
- Lab results ready
- Emergency events (e.g., `emergency_code_blue`)

The system builds a workflow plan dynamically and executes it step-by-step with full traceability.

## Core ideas

### 1) Dynamic planning (rule-driven)

The planner uses event-pattern rules (for example `patient_admitted` or `emergency_*`) to generate task lists.

This means workflow behavior is **data-driven**:

- Add/change rules → behavior changes
- No need to add endpoint-specific if/else logic for every event

### 2) Agent-to-Agent communication (A2A)

Agents can request data/services from each other via structured messages routed through the orchestrator.

Example:

- `SchedulerAgent` asks `DataAgent` for patient department if context is missing.

### 3) MCP tool boundary

Agents do not directly access database or external services.
They invoke tools from a central registry.

Benefits:

- Auditable calls
- Consistent error handling
- Easy extensibility

### 4) Shared execution context

Each completed step can enrich a shared context object.
Later steps consume that context (for example alert messages use patient data and doctor assignment from prior steps).

## Tech stack

- **Language:** Python 3.11
- **Web API:** FastAPI
- **ASGI server:** Uvicorn
- **Validation/models:** Pydantic v2
- **Database layer:** SQLAlchemy async
- **Database:** PostgreSQL (via Docker Compose)
- **Frontend:** Static HTML/CSS/JS served by FastAPI

## Runtime at a glance

1. App starts → DB tables initialized
2. Seed data inserted if empty
3. MCP tools auto-registered
4. Agents registered to orchestrator
5. API request arrives (`/admit_patient` or `/trigger_event`)
6. Planner generates plan
7. Orchestrator executes tasks through agents
8. Agents call MCP tools and optionally send A2A messages
9. Execution log returned in API response and available in history endpoint

## Repo structure (important folders)

- `hospital-agent-system/api` — FastAPI app and endpoints
- `hospital-agent-system/planner` — dynamic planning logic
- `hospital-agent-system/orchestrator` — execution engine + A2A routing
- `hospital-agent-system/agents` — agent implementations
- `hospital-agent-system/mcp` — tool registry + tool implementations
- `hospital-agent-system/models` — ORM and Pydantic schemas
- `hospital-agent-system/static` — dashboard frontend
