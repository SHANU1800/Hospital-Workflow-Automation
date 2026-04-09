# Architecture and Components

## Layered architecture

The system is organized into separable layers:

1. **API Layer (`api/main.py`)**
2. **Planner Layer (`planner/planner.py`)**
3. **Orchestration Layer (`orchestrator/dispatcher.py`)**
4. **Agent Layer (`agents/*.py`)**
5. **MCP Layer (`mcp/tool_registry.py`, `mcp/tools.py`)**
6. **Data Layer (`models/database.py`, `seed_data.py`)**
7. **UI Layer (`static/*`)**

## Component details

## API Layer

Responsibilities:

- App startup/shutdown lifecycle
- Initialize database and seed data
- Register agents in orchestrator
- Expose control endpoints
- Serve dashboard static files

Main endpoints:

- `POST /admit_patient`
- `POST /trigger_event`
- `GET /health`
- `GET /agents`
- `GET /tools`
- `GET /execution_logs`
- `GET /planning_rules`

## Planner Layer

`RuleBasedPlanner` contains a table of planning rules (`PLANNING_RULES`), where each rule defines:

- event pattern
- priority
- task templates

Task templates define:

- `task` (capability name)
- `agent` (target agent)
- parameter mapping
- optional dependencies and priority

Matching behavior:

- First match by priority wins
- Supports wildcard patterns like `emergency_*`
- Includes catch-all `*` fallback rule

Also includes an `LLMPlanner` stub that falls back to `RuleBasedPlanner` if no API key is set.

## Orchestrator Layer

`Orchestrator` is the execution engine.

Responsibilities:

- Register agents and index capabilities
- Route A2A messages between agents
- Execute generated workflow plans step-by-step
- Maintain per-execution shared context
- Capture detailed execution logs

Execution behavior:

- Tries explicit task agent first
- Falls back to capability index if needed
- Merges step results into context (excluding metadata fields)
- Captures tool calls and A2A messages in `StepLog`

## Agent Layer

All agents inherit from `BaseAgent`, which provides:

- `call_tool()` for MCP tool calls
- `send_message()` for A2A routing via orchestrator
- default `receive_message()` handling

### DataAgent

Capabilities:

- `fetch_patient_data`
- `lookup_data`

Also handles A2A requests:

- `get_patient_department`
- `get_patient_info`

### SchedulerAgent

Capabilities:

- `assign_doctor`
- `schedule_appointment` (stub)

Flow for doctor assignment:

- Uses context if patient department already available
- Otherwise asks `DataAgent` via A2A
- Calls MCP tool `assign_doctor`

### AlertAgent

Capabilities:

- `send_alert`
- `notify_staff`

Behavior:

- Builds context-aware messages (patient + assignment + event)
- Calls MCP tool `send_notification`
- Can request patient info from `DataAgent` when needed

## MCP Layer

### Tool registry

`ToolRegistry` is a central singleton where tools are registered and invoked.

Features:

- Decorator-based registration (`@register_tool`)
- Runtime call by tool name
- Structured call log (`MCPToolCall`) including success/failure

### Registered tools

- `get_patient_data`
- `assign_doctor`
- `send_notification`
- `get_patient_department`
- `check_doctor_availability`

## Data Layer

ORM tables:

- `patients`
- `doctors`
- `notifications`
- `execution_logs` (record model exists)

Startup initialization:

- `init_db()` creates tables
- `seed_database()` inserts sample patients/doctors if table is empty

## UI Layer

`index.html`, `styles.css`, and `app.js` provide a command-center style dashboard.

Functions include:

- Admit patient form
- Generic event trigger form
- Execution timeline visualization
- Logs viewer with expandable runs
- Agent and tool registry views

## Hierarchy reference

For tree views of both the current implementation and the target scaled design, see:

- `document/agent-and-mcp-hierarchy.md`
