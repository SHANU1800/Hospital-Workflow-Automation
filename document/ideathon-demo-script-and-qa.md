# Philips Ideathon Demo Script — MedFlow Command Center

## Demo Goal (One-liner)

**“MedFlow Command Center is a hospital workflow platform where specialized AI agents collaborate (not just one chatbot) to automate triage-to-booking-to-billing-to-insurance with full auditability.”**

---

## 8–10 Minute Demo Flow

### 0) Opening Hook (30 sec)

**Say:**

> In hospitals, delays happen because triage, scheduling, billing, insurance, and bed operations are siloed.
> We built a multi-agent orchestration system where domain agents collaborate in real time and every step is traceable.

**Show:** `Dashboard`

---

### 1) Architecture Credibility (60–90 sec)

**Say:**

> This is not a single monolithic agent. We have a Supervisor with domain agents:
> TriageAgent, SchedulerAgent, BillingAgent, InsuranceAgent, BedManagementAgent, DataAgent, and AlertAgent.
> They communicate through structured agent-to-agent messaging and invoke controlled MCP tools.

**Show:**

- `Agents` page
- `MCP Tools` page

**Highlight:**

- Agent capabilities
- Tool governance (MCP registry)

---

### 2) Patient Journey (Core Multi-Agent Wow) (3–4 min)

Go to `Appointments`.

#### A) Identity + Symptom Intake

**Action:**

- Enter patient details
- Optional voice input for symptoms
- Click **Analyze Symptoms**

**Say:**

> DataAgent validates or creates patient identity.
> TriageAgent computes urgency and detects the likely department from symptoms.

**Show:**

- Identity panel
- Symptom input + voice
- Recommendation panel

#### B) Agent-driven Doctor + Slot Loading

**Say:**

> Based on detected department, SchedulerAgent auto-loads only relevant doctors and slots.
> No manual filtering, no mismatch.

**Show:**

- Auto-populated doctor list
- Auto-loaded slots
- Agent workflow panel updates

#### C) Booking

**Action:**

- Pick slot
- Click **Book Appointment**

**Say:**

> Appointment is confirmed and persisted, with full workflow traceability.

**Show:**

- Confirmation block
- PDF appointment letter

---

### 3) Patient Self-service (2 min)

#### A) `My Schedule`

**Action:**

- Enter patient ID + date
- Load schedule

**Say:**

> Patients can check upcoming appointments by date in a calendar-like schedule flow.

#### B) `My Billing`

**Action:**

- Add insurance details
- Save profile
- Claim insurance for bill

**Say:**

> Insurance details are stored once and reused for claims. Patients can see bill and insurance statuses together.

---

### 4) Superadmin / Staff Visibility (2 min)

#### A) `Insurance` page

**Say:**

> Superadmin sees both claim lifecycle and saved patient insurance details, linked end-to-end.

**Show:**

- Claims table
- Saved patient insurance details table

#### B) `Beds`, `Billing`, `Reports`

**Say:**

> Operational teams get filtered tables + KPI summaries to manage throughput and finance.

---

### 5) Trust + Traceability Close (60 sec)

Go to `Execution Logs`.

**Say:**

> Every run is auditable: which agent acted, what tool was used, what result came back, and how long each step took.
> This is essential for healthcare safety and compliance.

---

## High-impact “Why Multi-Agent” Lines

1. Single-agent systems blur responsibilities; our agent-per-domain model maps to hospital departments.
2. Bounded agents improve reliability and debuggability.
3. Cross-agent orchestration gives modular upgrades (triage can evolve without touching billing).
4. Per-step logs and tool traces provide built-in observability.
5. The architecture is production-minded: typed APIs, RBAC, and domain separation.

---

## 30–40 Interview Questions (Practice Bank)

### Product & Problem Framing

1. What real hospital pain point does your system solve first?
2. Why did you choose multi-agent over a single orchestration service?
3. Which KPI would you optimize first in production (TAT, cost, errors, etc.)?
4. What assumptions did you make about hospital workflow?
5. How does your system reduce patient wait time concretely?

### Architecture & Design

6. Explain your end-to-end architecture in 60 seconds.
7. What is the responsibility boundary of each agent?
8. Why do you need a SupervisorAgent if you already have domain agents?
9. How does agent-to-agent communication happen safely?
10. How do you prevent tight coupling between agents?
11. What are MCP tools in your design and why are they useful?
12. How do planning rules map to events?
13. How would you add a new agent (e.g., PharmacyAgent) with minimal changes?
14. How do you ensure idempotency in event handling?
15. What are possible single points of failure in your architecture?

### Backend/API

16. How do you enforce role-based access (patient/staff/superadmin)?
17. Why did you choose FastAPI + async SQLAlchemy?
18. How do you validate and sanitize patient inputs?
19. How do you version your APIs for backward compatibility?
20. How do you handle partial failures in workflow execution?

### Data & Persistence

21. How is patient identity resolved for walk-ins vs registered users?
22. Why did you store insurance profile separately from claims?
23. How do you model claim lifecycle states?
24. How do you ensure data consistency across appointment, billing, and insurance tables?
25. What migration strategy would you use for schema evolution?

### Multi-Agent Workflow Deep Dive

26. Walk through one full patient booking workflow and the participating agents.
27. How does department detection work and what are its limitations?
28. How do you ensure only department-relevant doctors are shown?
29. How does slot allocation avoid race conditions/double-booking?
30. How do agents decide when to escalate to supervisor?
31. How do you debug agent disagreements or conflicting outputs?
32. How do you monitor latency across agent hops?
33. Where can hallucinations happen and how do you mitigate them?

### Security, Privacy, Compliance

34. How do you protect PHI/PII in logs and API responses?
35. What compliance constraints (HIPAA-like) did you consider?
36. How do you secure JWT authentication and refresh flow?
37. How do you audit admin actions on billing/claims?

### Scalability, Reliability, and Ops

38. How would you scale this from one hospital to a hospital network?
39. What is your retry/backoff strategy for external failures?
40. How would you productionize observability (metrics, traces, alerts)?

---

## 30-second Closing Pitch

> This is not just a UI demo. It’s a modular, auditable, multi-agent workflow engine for healthcare operations.
> Specialized agents collaborate across clinical and financial workflows, while every step remains transparent for patients, staff, and administrators.
