# Agent and MCP Hierarchy

This document shows both:

- the **current implemented hierarchy** in the project
- the **target expanded hierarchy** for your multi-agent roadmap

---

## Agent hierarchy tree

### Current implemented tree

```text
Orchestrator
├─ DataAgent
│  ├─ fetch_patient_data
│  └─ lookup_data
├─ SchedulerAgent
│  ├─ assign_doctor
│  └─ schedule_appointment
└─ AlertAgent
   ├─ send_alert
   └─ notify_staff
```

### Target expanded tree

```text
Orchestrator
├─ Core Care
│  ├─ DataAgent
│  ├─ TriageAgent
│  ├─ SchedulerAgent
│  ├─ NurseCoordinationAgent
│  ├─ AlertAgent
│  └─ EscalationAgent
├─ Clinical Services
│  ├─ LabAgent
│  ├─ RadiologyAgent
│  ├─ PharmacyAgent
│  ├─ ProcedureCoordinationAgent
│  ├─ MedicationSafetyAgent
│  └─ DischargePlannerAgent
├─ Patient Flow and Operations
│  ├─ BedManagementAgent
│  ├─ TransportAgent
│  ├─ EquipmentAgent
│  ├─ HousekeepingAgent
│  ├─ DietaryAgent
│  ├─ QueueOptimizationAgent
│  ├─ StaffingAgent
│  └─ SLAAgent
├─ Revenue Cycle
│  ├─ BillingAgent
│  ├─ InsuranceAgent
│  ├─ CodingAgent
│  ├─ PriorAuthorizationAgent
│  ├─ ClaimsAgent
│  └─ PaymentFollowupAgent
├─ Patient Experience
│  ├─ PatientCommunicationAgent
│  ├─ AppointmentAgent
│  ├─ InterpreterAgent
│  ├─ FeedbackAgent
│  ├─ EducationAgent
│  ├─ ConsentAgent
│  └─ DocumentAgent
├─ Compliance and Quality
│  ├─ AuditTrailAgent
│  ├─ PrivacyComplianceAgent
│  ├─ ClinicalQualityAgent
│  ├─ IncidentReportingAgent
│  ├─ PolicyEnforcementAgent
│  └─ InfectionControlAgent
├─ Intelligence
│  ├─ ForecastingAgent
│  ├─ ReadmissionRiskAgent
│  ├─ NoShowRiskAgent
│  ├─ ResourceOptimizationAgent
│  └─ DecisionSupportAgent
└─ Integrations
   ├─ EHRSyncAgent
   ├─ HL7FHIRAgent
   ├─ ThirdPartyLabBridgeAgent
   ├─ PACSBridgeAgent
   └─ ERPFinanceBridgeAgent
```

---

## MCP hierarchy tree

### Current implemented MCP tree

```text
ToolRegistry
├─ get_patient_data
├─ assign_doctor
├─ send_notification
├─ get_patient_department
└─ check_doctor_availability
```

### Target expanded MCP tree (domain-organized)

```text
ToolRegistry
├─ Core Platform
│  ├─ identity/workflow/audit/policy/notification tools
│  └─ schema/validation/health-check tools
├─ Triage and Emergency
│  ├─ scoring and prioritization
│  └─ critical escalation and emergency protocol tools
├─ Bed and Patient Flow
│  ├─ inventory, reserve, assign, release
│  └─ transfer, occupancy, and turnover tools
├─ Scheduling and Staffing
│  ├─ doctor and consult scheduling
│  └─ roster/on-call/workload balancing tools
├─ Lab
│  ├─ lab order and sample lifecycle
│  └─ result and critical alert tools
├─ Radiology
│  ├─ imaging order and slot booking
│  └─ report and critical finding tools
├─ Pharmacy and Medication Safety
│  ├─ medication order and inventory
│  └─ interaction checks and administration tools
├─ Procedure and OT
│  ├─ pre-op and theater scheduling
│  └─ intra/post-procedure workflow tools
├─ Discharge and Follow-up
│  ├─ readiness/checklist/summary tools
│  └─ follow-up scheduling and readmission risk tools
├─ Billing, Coding, and Claims
│  ├─ billing estimation/invoicing tools
│  └─ claim create/submit/track/rejection tools
├─ Insurance and Prior Auth
│  ├─ eligibility and benefit checks
│  └─ prior-auth create/submit/track tools
├─ Patient Communication
│  ├─ SMS/email/family notifications
│  └─ reminders, education, consent, feedback tools
├─ Transport and Logistics
│  ├─ patient transport and ETA tools
│  └─ equipment reserve/release tools
├─ Compliance and Quality
│  ├─ incident and policy violation tools
│  └─ audit/export/retention tools
├─ Intelligence and Optimization
│  ├─ forecasting and risk prediction tools
│  └─ bottleneck/capacity optimization tools
└─ External Integrations
   ├─ EHR/FHIR/HL7 sync tools
   ├─ PACS/Lab bridge tools
   └─ ERP finance integration tools
```

---

## Notes for implementation

- Keep each agent focused to **1–3 capabilities** where possible.
- Keep external interactions inside MCP tools (agents remain thin orchestrators).
- Expand in phases (foundation → clinical/revenue → advanced intelligence/integration).
