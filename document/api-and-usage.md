# API and Usage Guide

## Base URL

By default (Docker):

- API + dashboard: `http://localhost:8000`
- Postgres exposed on host: `localhost:5433`

## Endpoints

## `POST /admit_patient`

Triggers the admission workflow for a patient.

Request body:

- `patient_id` (int)

Response highlights:

- execution `status`
- generated `plan`
- full `execution` trace
- summary (`total_steps`, completed/failed, duration)

## `POST /trigger_event`

Triggers any event dynamically.

Request body:

- `event` (string)
- `context` (object)

Example event values:

- `patient_discharged`
- `lab_results_ready`
- `emergency_code_blue`
- `unknown_event` (handled by catch-all rule)

## `GET /health`

Returns current system health with counts of:

- registered agents
- registered tools
- planning rules

## `GET /agents`

Returns registered agent list and capabilities.

## `GET /tools`

Returns MCP tools and their parameter metadata.

## `GET /execution_logs`

Returns in-memory execution history captured by orchestrator.

## `GET /planning_rules`

Returns planner rule summary and task counts.

## Dashboard behavior

The UI at `/` provides:

- **Dashboard:** run statistics + recent activity
- **Admit Patient:** run admission workflow by patient ID
- **Trigger Event:** run arbitrary event workflows
- **Execution Logs:** expandable workflow timelines
- **Agents:** live registry view
- **MCP Tools:** tool metadata view

## Typical usage path

1. Open `/`
2. Use quick action (e.g., Quick Admit)
3. Inspect timeline output
4. Open Logs page for historical runs
5. Check Agents/Tools pages for registry state
