# Interview Quick Cheat Sheet (Last 10 Minutes)

Keep this open before your interview.

## Your 3 key lines

1. **Problem:** Hospital workflows are siloed; handoffs cause delay and errors.
2. **Solution:** Multi-agent orchestration with role-aware APIs and controlled tool execution.
3. **Value:** Faster coordination + full auditability across patient, doctor, and admin workflows.

## 60-second pitch

> We built a FastAPI-based hospital workflow platform that uses specialized collaborating agents for triage, scheduling, billing, insurance, and operations. Planner + orchestrator route events to the right agents, and all actions are auditable via execution logs. Patients get smoother booking, doctors get workflow support and calendar visibility, and admins get lifecycle transparency for billing and claims.

## Demo order (memory)

- Patient intake -> recommendation
- Doctor/slot auto-load -> booking
- Billing/insurance linkage
- Doctor calendar + workflow trigger
- Execution logs and close

## Answer structure

Use: **What -> Why -> How -> Impact**

Example:
- What: We used multi-agent design.
- Why: Domain boundaries reduce errors.
- How: Planner/orchestrator + typed agent tasks.
- Impact: Better maintainability and traceability.

## If asked “What next?”

Say any 2:
- Queue-backed orchestration for high load
- Stronger user-to-patient identity binding
- Automated workflow regression tests
- Metrics dashboard for agent latency/failures

## If they challenge production readiness

> This is a prototype with production-oriented architecture. Next hardening includes compliance controls, deeper observability, and asynchronous worker queues.

## Confidence reminders

- Keep answers to 20-40 seconds first.
- Don’t rush architecture explanation.
- Always tie feature to impact.
- If uncertain, state tradeoff clearly and propose next step.
