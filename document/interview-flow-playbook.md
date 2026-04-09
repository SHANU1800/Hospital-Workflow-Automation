# Interview Flow Playbook — Hospital Workflow Automation

Use this as your **actual speaking guide** for ideathon judging and SDE-style interviews.

---

## 1) 30-Second Opening (Memorize This)

> We built a multi-agent hospital workflow platform where specialized agents coordinate triage, scheduling, billing, insurance, and operations. Instead of isolated manual handoffs, the system runs auditable, role-aware workflows with clear accountability. The result is faster patient flow, better operational visibility, and production-oriented architecture.

---

## 2) How to Explain the Project (Simple Framework)

Use this order every time:

1. **Problem**: hospital workflows are siloed and slow.
2. **Approach**: multi-agent orchestration + controlled tools + role-based APIs.
3. **Execution**: symptom intake -> triage -> doctor/slot -> booking -> billing/claim.
4. **Trust**: execution logs and step-level traceability.
5. **Outcome**: lower coordination friction and scalable modular design.

If you forget details, fall back to: **Problem -> Architecture -> Demo Flow -> Why it matters**.

---

## 3) Suggested 8-Min Interview Flow

## Minute 0-1: Hook + Problem
- Explain real hospital delay points (triage/scheduling/billing handoff gaps).
- State why this matters: wait time + staff load + revenue leakage.

## Minute 1-2: Architecture Credibility
- Mention key components: API, planner, orchestrator, domain agents, MCP tools, DB, UI.
- One line: "Each agent has bounded responsibility, which improves reliability and debugging."

## Minute 2-5: Patient Journey (Core Demo)
- Symptom intake (+ optional voice).
- Department recommendation from triage.
- Auto doctor/slot loading by department.
- Appointment booking and persisted confirmation.

## Minute 5-6: Financial + Admin Visibility
- Show insurance profile + claims linkage.
- Show staff/superadmin visibility for claim lifecycle and operations.

## Minute 6-7: Doctor Workflow + Calendar
- Show doctor calendar with marked dates and click-to-load appointments.
- Trigger doctor-side multi-agent follow-up workflow and show timeline/logs.

## Minute 7-8: Close Strong
- Show execution logs (auditability).
- End with: "This is not a chatbot demo; it’s an orchestrated healthcare workflow system."

---

## 4) What to Emphasize While Talking

- **Design decisions** > just features.
- Why multi-agent was chosen over monolithic logic.
- How RBAC and data boundaries protect sensitive workflows.
- Why audit logs are mandatory in healthcare contexts.
- How Neon external DB setup supports realistic deployment.

---

## 5) Whiteboard Explanation Flow (If They Ask for System Design)

Draw in this order:

1. **Client/UI** (role-based dashboard)
2. **FastAPI layer** (auth + endpoints)
3. **Planner** (event -> task plan)
4. **Orchestrator** (dispatch/sequence/retries)
5. **Agents** (Triage, Scheduler, Billing, Insurance, etc.)
6. **MCP tool registry** (controlled action boundary)
7. **Postgres (Neon)** + execution logs

Then explain one request end-to-end in 20 seconds.

---

## 6) Expected Question Buckets + How to Answer

## A) Product Questions
Typical: "What pain point?" "Who benefits first?"
- Keep answers KPI-based: turnaround time, booking friction, claim latency.

## B) Architecture Questions
Typical: "Why multi-agent?" "Why supervisor?"
- Say: domain boundaries, lower coupling, easier testing and scaling.

## C) Reliability Questions
Typical: "What if one agent fails?"
- Say: step-level status tracking, partial failure isolation, retry strategy, logs.

## D) Security Questions
Typical: "How do you protect patient data?"
- Say: RBAC, scoped endpoints, minimal sensitive exposure, audit trails.

## E) Scale/Production Questions
Typical: "How will this scale to many hospitals?"
- Say: stateless API scaling, async processing, queue-backed orchestration, observability.

---

## 7) 10 High-Probability Questions (With Sharp Answer Direction)

1. Why multi-agent over single model?
2. How do you prevent double booking?
3. How do you handle partial failures?
4. What does the SupervisorAgent do exactly?
5. How are doctor lists made department-safe?
6. How do you ensure claim/profile consistency?
7. What are your key security controls?
8. What metrics will you track in production?
9. What was your biggest technical tradeoff?
10. What would you build next in 1 week?

Use 20-40 second answers first; expand only when asked.

---

## 8) Delivery Style for Interviews

- Speak in short blocks: **claim -> evidence -> impact**.
- Avoid over-jargon unless they ask deep systems questions.
- After every feature statement, add one outcome line.
- If interrupted, summarize in one sentence and move forward confidently.

Good transition line:
> "Now that the patient flow is clear, let me show how the same architecture supports doctor operations and admin auditability."

---

## 9) If You Get Stuck Mid-Answer

Use this recovery line:

> Great question. Let me answer from architecture first, then implementation detail.

Then respond in two parts:
- architecture intent
- concrete implementation in this repo

---

## 10) Final Closing (15 Seconds)

> We delivered a modular, role-aware, auditable multi-agent platform that connects clinical and financial workflows end-to-end. The system is demo-ready today and structurally aligned with production evolution.
