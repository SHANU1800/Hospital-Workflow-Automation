# Workflow Execution (How it works at runtime)

## Startup sequence

When the application starts (`api/main.py` lifespan):

1. Database tables are created (`init_db()`)
2. Seed data is inserted if needed (`seed_database()`)
3. MCP tools are auto-registered (by importing `mcp.tools`)
4. Agents are instantiated and registered to orchestrator
5. System logs registered tools, agents, and planning rules

## Request-to-execution flow

A request to `POST /admit_patient` (or `POST /trigger_event`) follows this path:

1. **API receives event + context**
2. **Planner generates a `WorkflowPlan`**
3. **Orchestrator executes tasks in order**
4. **Agent executes task**
   - Calls MCP tool(s)
   - Sends/receives A2A messages if needed
5. **Orchestrator captures `StepLog`**
6. **Step results merge into shared context**
7. Next task uses enriched context
8. Final `ExecutionLog` returned

## Example: `patient_admitted`

Default rule expands to:

1. `fetch_patient_data` → `DataAgent`
2. `assign_doctor` → `SchedulerAgent`
3. `send_alert` → `AlertAgent`

Runtime behavior:

- `DataAgent` calls `get_patient_data`
- `SchedulerAgent` uses context patient department (or asks DataAgent via A2A), then calls `assign_doctor`
- `AlertAgent` builds message from context (patient + doctor assignment + event) and calls `send_notification`

## Shared context mechanics

Orchestrator keeps a mutable dictionary initialized with:

- original request context
- `_event`
- `_plan_id`

After each successful step, dictionary results are merged into context, excluding metadata keys like:

- `tool_call`
- `a2a_messages`
- `status`

This is what allows downstream steps to use upstream outputs without tight coupling.

## A2A routing mechanics

A2A communication is explicit and structured (`A2AMessage`):

- `from_agent`
- `to_agent`
- `request`
- `payload`
- `response`
- `status`

The orchestrator routes messages to target agent `receive_message()` and returns response to sender.

## Logging and observability

Execution logs track:

- step statuses
- timing per step (`duration_ms`)
- tool calls per step
- A2A messages per step
- total workflow duration

You can inspect runs via:

- `GET /execution_logs`
- Dashboard Logs page

## Failure behavior

- Step-level failures are captured in `StepLog.error`
- Execution continues where possible
- Final execution status becomes `partial_failure` if any step failed
