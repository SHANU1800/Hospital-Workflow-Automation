# Philips Ideathon — Expanded Interview Q&A (Multi-Agent Workflow)

This file is a focused prep sheet for SDE-style interviews and ideathon judging.

---

## 1) Product & Problem Framing

### Q1. What problem are you solving in one sentence?
**Answer:** We reduce hospital operational delays by orchestrating triage, scheduling, billing, insurance, and bed workflows through specialized collaborating agents instead of siloed manual handoffs.

### Q2. Why is this problem important?
**Answer:** Delays in coordination directly impact patient wait time, staff efficiency, and financial leakage. A workflow-aware system improves care continuity and operational throughput.

### Q3. Who is your primary user?
**Answer:** The system serves three user groups: patients (self-service booking/billing), staff (operations), and superadmin (end-to-end oversight and control).

### Q4. What is your first measurable KPI?
**Answer:** First KPI is appointment workflow turnaround time (symptom intake to confirmed booking). Secondary KPIs are claim submission latency and bed utilization visibility.

### Q5. Why not build this as a standard CRUD app?
**Answer:** CRUD alone can store state, but cannot intelligently coordinate cross-domain decisions. Multi-agent orchestration adds adaptive, domain-specific decision flow with traceability.

---

## 2) Architecture & Multi-Agent Design

### Q6. Why multi-agent over a single LLM agent?
**Answer:** Multi-agent provides clear domain boundaries, better reliability, easier debugging, and safer evolution. Each agent handles a narrow responsibility, reducing cross-domain errors.

### Q7. What are your core agents?
**Answer:** SupervisorAgent, TriageAgent, SchedulerAgent, BillingAgent, InsuranceAgent, BedManagementAgent, DataAgent, AlertAgent, and LabAgent.

### Q8. What does SupervisorAgent do?
**Answer:** It coordinates workflow execution, resolves escalations, and ensures dependent tasks are sequenced correctly.

### Q9. How do agents communicate?
**Answer:** Through structured A2A messages with typed payloads; this gives deterministic contracts and auditability.

### Q10. How do tools fit in?
**Answer:** Agents do not directly mutate domain state arbitrarily; they use registered MCP tools so actions stay controlled, discoverable, and auditable.

### Q11. How are workflows generated?
**Answer:** Event-driven planning rules map incoming events to task plans; the orchestrator executes tasks by dispatching to the relevant agents.

### Q12. How do you avoid tight coupling?
**Answer:** Agents communicate via schemas and tool interfaces, not direct internal calls. This keeps each domain replaceable.

### Q13. How do you add a new agent (e.g., Pharmacy)?
**Answer:** Add the agent class, register capabilities, define tool contracts, then map events/rules to new tasks—without rewriting existing agent logic.

### Q14. What if two agents disagree?
**Answer:** SupervisorAgent acts as conflict resolver using rule priority + deterministic fallbacks, and the final chosen path is logged.

### Q15. Where can this architecture fail?
**Answer:** Bottlenecks can appear at orchestration and DB boundaries; we mitigate with async design, retries, observability, and bounded agent responsibilities.

---

## 3) Backend/API Engineering

### Q16. Why FastAPI?
**Answer:** It gives typed contracts, async performance, straightforward dependency injection, and fast iteration for service APIs.

### Q17. Why async SQLAlchemy?
**Answer:** Workflow systems involve many I/O-bound operations (reads/writes/tool calls). Async improves concurrency under user and system load.

### Q18. How do you enforce RBAC?
**Answer:** Role-based dependencies guard endpoints (`patient`, `staff`, `super_admin`, etc.), and UI route visibility mirrors backend authorization.

### Q19. How do you validate inputs?
**Answer:** Pydantic schemas enforce structure, ranges, and optionality. Domain checks add ownership/consistency validation at endpoint level.

### Q20. How do you version APIs safely?
**Answer:** Keep response models backward-compatible, add new optional fields, and isolate breaking changes under versioned routes when needed.

### Q21. How do you handle partial failures?
**Answer:** Execution logs mark step-level status; failed steps are isolated and surfaced to operators, while completed steps remain traceable.

### Q22. How do you protect from invalid claims?
**Answer:** Claim creation verifies billing-case ownership and existing claim state, then uses validated profile data.

### Q23. Why expose `/staff/insurance/profiles`?
**Answer:** It bridges patient-entered insurance details with admin review, reducing mismatches and enabling operational verification.

### Q24. How do you prevent accidental overreach in patient endpoints?
**Answer:** Explicit patient_id ownership checks plus role restrictions prevent cross-patient data access.

### Q25. What backend improvement would you do next?
**Answer:** Add true subject-based patient scoping from auth identity (mapping user -> patient record) to remove manual patient_id input.

---

## 4) Data Modeling & Consistency

### Q26. Why separate insurance profile from claim record?
**Answer:** Insurance profile is reusable patient master data; claims are transactional snapshots tied to billing cases. Separation improves reuse and audit correctness.

### Q27. How do you keep claim data and profile in sync?
**Answer:** On claim creation, latest profile values are copied into the claim for immutable transactional history.

### Q28. Why does claim keep provider/plan/member even if profile exists?
**Answer:** To preserve historical accuracy. If profile changes later, old claims remain explainable.

### Q29. How do you model billing lifecycle?
**Answer:** Billing case status transitions from `open -> invoiced/submitted -> paid/closed`, with insurance status tracked separately.

### Q30. How do you avoid orphan links?
**Answer:** Billing case, claim, and patient ownership checks happen before writes; references are updated in one transaction scope.

### Q31. Why do you include created/updated timestamps?
**Answer:** Time metadata is critical for debugging, compliance traceability, and operational SLAs.

### Q32. What migration strategy would you use?
**Answer:** Alembic-based forward migrations with staged rollouts and compatibility windows for new nullable columns/endpoints.

---

## 5) Workflow Logic: Triage, Doctors, Slots

### Q33. How is department detected?
**Answer:** Symptom intake is processed through triage scoring and department recommendation tools, producing urgency + recommended department.

### Q34. How do you guarantee doctor relevance?
**Answer:** Doctors are queried by recommended department, and UI applies department-safe filtering before selection.

### Q35. Why did you remove manual load buttons?
**Answer:** Agent-driven automation reduces user errors and friction. The system now automatically loads doctors and slots after recommendation.

### Q36. How are slots loaded?
**Answer:** Scheduler tooling fetches/creates date-specific availability and returns unbooked slots only.

### Q37. How do you prevent double booking?
**Answer:** Slot state (`is_booked`) is validated at booking write-time; conflicting writes are rejected.

### Q38. What if no doctor/slot is available?
**Answer:** The workflow communicates unavailability clearly and leaves user in a recoverable state (change date/symptoms/department path).

### Q39. Why show agent workflow to patient?
**Answer:** It builds transparency and trust, and demonstrates explainability of automated decisions in healthcare contexts.

### Q40. What is the fallback if triage is uncertain?
**Answer:** Route to General department with explicit rationale and preserve urgency score for staff visibility.

---

## 6) Security, Privacy, Compliance

### Q41. How do you secure authentication?
**Answer:** JWT-based auth with role claims, protected endpoints, and session invalidation on auth failures.

### Q42. How do you handle PHI/PII safely?
**Answer:** Minimize sensitive output in logs/UI, restrict access by role, and expose only necessary fields per endpoint.

### Q43. Is this HIPAA-compliant?
**Answer:** This is a prototype architecture; production HIPAA readiness requires encryption at rest/in transit, audit controls, retention policies, and formal compliance processes.

### Q44. How do you audit admin actions?
**Answer:** Operational mutations and workflow steps are recorded with status/timestamps; admin-facing updates are traceable via logs and data timestamps.

### Q45. What abuse vectors did you consider?
**Answer:** Unauthorized data access, cross-patient operations, invalid state transitions, and over-permissive endpoints. RBAC + ownership validation mitigate these.

---

## 7) Scalability, Reliability, SDE Maturity

### Q46. How do you scale this architecture?
**Answer:** Horizontally scale API workers, isolate orchestration queue, shard/replicate database, and move heavy agents to asynchronous workers.

### Q47. How do you observe system health?
**Answer:** Health endpoints, execution logs, per-step timings, and status aggregates give both operational and workflow-level observability.

### Q48. What would you monitor first in production?
**Answer:** Workflow latency per event type, failure rates per agent/tool, DB query latency, booking conflict rate, and claim submission success rate.

### Q49. How do you handle transient failures?
**Answer:** Retry with backoff for idempotent tool calls, step-level error capture, and explicit failure states surfaced in logs/UI.

### Q50. How would you improve reliability next?
**Answer:** Add queue-based orchestration, circuit breakers for tool calls, and dead-letter handling for failed workflows.

---

## 8) Interviewer “Depth Test” Questions

### Q51. Where is your strongest design tradeoff?
**Answer:** We traded some simplicity for modularity and traceability. Multi-agent complexity is justified by domain separation and maintainability.

### Q52. What technical debt exists today?
**Answer:** Patient identity-to-auth binding can be strengthened, and prompt-based editing UIs should become structured forms/modals.

### Q53. What did you optimize for in this ideathon build?
**Answer:** End-to-end demonstrability of multi-agent orchestration, role-aware workflows, and auditability over perfect production hardening.

### Q54. If you had one extra week, what would you add?
**Answer:** Automated tests for workflow scenarios, stricter state machine validation, and metrics dashboards for agent latency/failures.

### Q55. Why are you a fit for an SDE role from this project?
**Answer:** I showed full-stack ownership: data modeling, backend APIs, workflow orchestration, RBAC, and UI integration with measurable validation.

---

## Rapid 60-second Technical Pitch

> We built a multi-agent hospital workflow platform where domain-specialized agents coordinate triage, scheduling, billing, insurance, and bed operations. 
> The architecture is event-driven, tool-governed, role-aware, and fully auditable via execution logs. 
> On the patient side, symptom intake triggers department detection and automatic doctor/slot loading. On finance side, insurance profile and claim lifecycle are connected to superadmin operations. 
> The result is reduced coordination friction, clearer accountability, and production-oriented modularity.
